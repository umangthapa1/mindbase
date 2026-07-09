import asyncio
import logging
import re
from typing import AsyncGenerator, Dict, List, Optional

from ollama import ollama_client
from memory import memory_manager

logger = logging.getLogger(__name__)


class ResearchAgent:
    # FIX 12: Cache model name to avoid redundant calls on concurrent requests
    _model_cache: Optional[str] = None

    async def _get_model(self) -> str:
        if not self._model_cache:
            self._model_cache = await ollama_client.get_model()
        return self._model_cache

    # FIX 10: Centralized LLM call with timeout so Ollama can't hang forever
    async def _safe_generate(self, model: str, messages: List[Dict], **kwargs) -> str:
        try:
            return await asyncio.wait_for(
                ollama_client.generate(model, messages, **kwargs),
                timeout=60.0
            )
        except asyncio.TimeoutError:
            raise RuntimeError("LLM timed out after 60 seconds")

    async def research(
        self,
        query: str,
        max_subqueries: int = 5,  # FIX 8: renamed from max_steps — this limits sub-questions, not steps
    ) -> AsyncGenerator[Dict, None]:
        """
        Async generator — must be consumed with `async for`, not `await`.
        Yields dicts with type: start | step | findings | report | complete | error
        """
        yield {"type": "start", "query": query}

        try:
            model = await self._get_model()
            queries = await self._decompose_query(query, model)
        except Exception as e:
            yield {"type": "error", "message": str(e)}
            return

        queries = queries[:max_subqueries]
        all_findings = []

        for i, sub_query in enumerate(queries):
            # FIX 11: Added progress percentage to step yields
            yield {
                "type": "step",
                "number": i + 1,
                "total": len(queries),
                "progress": round((i / len(queries)) * 100),
                "query": sub_query,
                "status": "researching"
            }

            findings = await self._research_subtopic(sub_query, model)
            all_findings.append({
                "query": sub_query,
                "findings": findings
            })

            # FIX 2: Yield all findings (was [:3]) to match what gets saved to report ([:5])
            yield {
                "type": "findings",
                "query": sub_query,
                "findings": findings
            }

        report = await self._generate_report(query, all_findings, model)

        yield {
            "type": "report",
            "title": report["title"],
            "content": report["content"],
            "sections": report["sections"]
        }

        yield {"type": "complete"}

    async def _user_context(self, query: str) -> str:
        parts = []
        try:
            for mem_type in ("profile", "project", "goal"):
                for m in await memory_manager.get_memories_by_type(mem_type, limit=3):
                    parts.append(m["content"][:200])
            relevant = await memory_manager.search_memories(query, limit=3)
            for m in relevant:
                if m.get("relevance", 0) >= 0.4:
                    parts.append(m["content"][:200])
        except Exception as e:
            # FIX 6: Log instead of silently swallowing
            logger.warning("Could not load user context: %s", e)
        return "\n".join(parts[:8])

    async def _decompose_query(self, query: str, model: str) -> List[str]:
        user_ctx = await self._user_context(query)
        ctx_block = f"\nUser context:\n{user_ctx}\n" if user_ctx else ""

        prompt = f"""You are planning offline research (no web). Break the main question into 3-5 focused sub-questions that together fully answer it.
Avoid overlap. Order from foundations to synthesis.{ctx_block}

Main question: {query}

Output ONLY numbered sub-questions, one per line (e.g. "1. ...")."""

        # FIX 10: Use _safe_generate with timeout
        response = await self._safe_generate(
            model, [{"role": "user", "content": prompt}], temperature=0.4
        )

        if response.lstrip().startswith("[Error:"):
            raise RuntimeError(response.strip())

        lines = response.strip().split("\n")
        questions = []
        for q in lines:
            q = q.strip()
            if not q or q.startswith("#"):
                continue
            q = re.sub(r"^\d+[\.\)]\s*", "", q)
            if len(q) > 10:
                questions.append(q)
        return questions[:5] if questions else [query]

    async def _research_subtopic(self, topic: str, model: str) -> List[str]:
        prompt = f"""Research this sub-topic using general knowledge. Provide 4-6 bullet findings.
Each bullet: one clear claim + brief rationale. Flag uncertainty where needed.

Sub-topic: {topic}

Bullets:"""

        # FIX 10: Use _safe_generate with timeout
        response = await self._safe_generate(
            model, [{"role": "user", "content": prompt}], temperature=0.5
        )

        # FIX 7: Check for LLM error response (was only done in _decompose_query)
        if response.lstrip().startswith("[Error:"):
            logger.warning("LLM error in _research_subtopic for topic: %s", topic)
            return []

        findings = []
        for line in response.split('\n'):
            line = line.strip()
            if line and (line.startswith('-') or line.startswith('•') or line[0].isdigit()):
                findings.append(line.lstrip('-•0123456789. '))

        # FIX 3: Guard against blank fallback when response is empty/whitespace
        if findings:
            return findings[:5]
        fallback = response.strip()[:200]
        return [fallback] if fallback else []

    async def _generate_report(self, original_query: str, findings: List[Dict], model: str) -> Dict:
        findings_text = "\n\n".join([
            f"### {f['query']}\n" + "\n".join(f["findings"])
            for f in findings
        ])

        prompt = f"""Generate a research report on: {original_query}

Research findings:
{findings_text}

Write a comprehensive report with:
1. Executive Summary
2. Key Findings
3. Analysis
4. Conclusions

Format with markdown headers."""

        # FIX 9: Lowered temperature from 0.6 to 0.3 for consistent structured output
        # FIX 10: Use _safe_generate with timeout
        content = await self._safe_generate(
            model,
            [{"role": "user", "content": prompt}],
            temperature=0.3,
            num_predict=4096
        )

        # FIX 7: Check for LLM error in report generation
        if content.lstrip().startswith("[Error:"):
            logger.warning("LLM error during report generation for query: %s", original_query)
            content = "Report generation failed. Please try again."

        sections = []
        current_section = None

        for line in content.split('\n'):
            # FIX 4: Handle #, ##, and ### headers (was only ##)
            if line.startswith('#'):
                if current_section:
                    sections.append(current_section)
                current_section = {
                    "title": line.lstrip('# ').strip(),
                    "content": "",
                    "level": len(line) - len(line.lstrip('#'))
                }
            elif current_section:
                current_section["content"] += line + "\n"

        if current_section:
            sections.append(current_section)

        return {
            "title": original_query,
            "content": content,
            "sections": sections
        }

    async def save_report_to_note(self, report: Dict, db_session) -> str:
        from database import NoteDB
        # FIX 5: Removed redundant `from memory import memory_manager` —
        # memory_manager is already imported at the top of this file

        note = NoteDB(
            title=f"Research: {report['title']}",
            content=report['content'],
            tags="research,generated"
        )
        db_session.add(note)
        db_session.commit()
        db_session.refresh(note)

        await memory_manager.upsert_note_memory(
            note.id,
            note.title,
            note.content,
            ["research", "generated"]
        )

        return note.id


research_agent = ResearchAgent()
