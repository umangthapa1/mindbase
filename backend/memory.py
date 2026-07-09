import chromadb
import uuid
from typing import List, Optional, Dict
from datetime import datetime
from pathlib import Path
import re

from config import CHROMA_DIR
from ollama import ollama_client

class MemoryManager:
    def __init__(self):
        self.client = chromadb.PersistentClient(path=str(CHROMA_DIR))
        self.collection = self.client.get_or_create_collection(
            name="memories",
            metadata={"hnsw:space": "cosine"}
        )
        self.embedding_model = "nomic-embed-text"

    async def create_memory(
        self,
        content: str,
        memory_type: str,
        tags: List[str] = None,
        metadata: Dict = None,
        skip_duplicate: bool = True,
    ) -> Dict:
        if skip_duplicate:
            similar = await self.search_memories(content, limit=1)
            if similar and similar[0].get("relevance", 0) >= 0.88:
                return similar[0]

        memory_id = str(uuid.uuid4())

        embedding = await ollama_client.generate_embedding(content, self.embedding_model)

        self.collection.add(
            ids=[memory_id],
            embeddings=[embedding] if embedding else None,
            documents=[content],
            metadatas=[{
                "type": memory_type,
                "tags": ",".join(tags or []),
                "created_at": datetime.utcnow().isoformat(),
                "updated_at": datetime.utcnow().isoformat(),
                **(metadata or {})
            }]
        )

        return {
            "id": memory_id,
            "content": content,
            "type": memory_type,
            "tags": tags or [],
            "metadata": metadata or {},
            "created_at": datetime.utcnow().isoformat()
        }

    async def upsert_note_memory(
        self,
        note_id: str,
        title: str,
        content: str,
        tags: List[str] = None
    ) -> Dict:
        memory_id = f"note:{note_id}"
        memory_content = f"Note: {title}\n\n{content}".strip()
        memory_tags = ["note", *(tags or [])]
        metadata = {
            "source": "note",
            "source_id": note_id,
            "note_title": title,
        }

        existing = self.collection.get(ids=[memory_id])
        if existing and existing.get("ids"):
            updated = await self.update_memory(
                memory_id,
                content=memory_content,
                tags=memory_tags,
                metadata=metadata
            )
        if updated:
            return updated
        else:
            print(f"Warning: update_memory failed for {memory_id}, re-adding as new entry")

        embedding = await ollama_client.generate_embedding(memory_content, self.embedding_model)
        now = datetime.utcnow().isoformat()

        self.collection.add(
            ids=[memory_id],
            embeddings=[embedding] if embedding else None,
            documents=[memory_content],
            metadatas=[{
                "type": "reference",
                "tags": ",".join(memory_tags),
                "created_at": now,
                "updated_at": now,
                **metadata
            }]
        )

        return {
            "id": memory_id,
            "content": memory_content,
            "type": "reference",
            "tags": memory_tags,
            "metadata": metadata,
            "created_at": now
        }

    async def delete_note_memory(self, note_id: str) -> bool:
        return await self.delete_memory(f"note:{note_id}")

    async def search_memories(
        self,
        query: str,
        memory_type: Optional[str] = None,
        limit: int = 5
    ) -> List[Dict]:
        embedding = await ollama_client.generate_embedding(query, self.embedding_model)

        if not embedding:
            return []

        where_filter = {"type": {"$eq": memory_type}} if memory_type else None

        results = self.collection.query(
            query_embeddings=[embedding],
            n_results=limit,
            where=where_filter
        )
        # After line 97 (the self.collection.query(...) call), add:
        if not results or not results.get('documents') or not results['documents'][0]:
            return []
        memories = []
        if results and results['documents']:
            for i, doc in enumerate(results['documents'][0]):
                metadata = results['metadatas'][0][i] if results['metadatas'] else {}
                distance = results['distances'][0][i] if results['distances'] else 0

                memories.append({
                    "id": results['ids'][0][i] if results['ids'] else f"mem_{i}",
                    "content": doc,
                    "type": metadata.get("type", "reference"),
                    "tags": metadata.get("tags", "").split(",") if metadata.get("tags") else [],
                    "relevance": round(1 - distance, 3),
                    "created_at": metadata.get("created_at", ""),
                    "metadata": {k: v for k, v in metadata.items() if k not in ["type", "tags", "created_at", "updated_at"]}
                })

        return memories

    async def get_memories_by_type(self, memory_type: str, limit: int = 10) -> List[Dict]:
        results = self.collection.get(
            where={"type": {"$eq": memory_type}},
            limit=limit
        )

        memories = []
        if results and results['documents']:
            for i, doc in enumerate(results['documents']):
                metadata = results['metadatas'][i] if results['metadatas'] else {}

                memories.append({
                    "id": results['ids'][i],
                    "content": doc,
                    "type": memory_type,
                    "tags": metadata.get("tags", "").split(",") if metadata.get("tags") else [],
                    "created_at": metadata.get("created_at", ""),
                    "metadata": {k: v for k, v in metadata.items() if k not in ["type", "tags", "created_at", "updated_at"]}
                })

        return memories

    async def get_note_memories(self, limit: int = 5) -> List[Dict]:
        results = self.collection.get(
            where={"source": {"$eq": "note"}},
            limit=limit
        )

        memories = []
        if results and results['documents']:
            for i, doc in enumerate(results['documents']):
                metadata = results['metadatas'][i] if results['metadatas'] else {}

                memories.append({
                    "id": results['ids'][i],
                    "content": doc,
                    "type": metadata.get("type", "reference"),
                    "tags": metadata.get("tags", "").split(",") if metadata.get("tags") else [],
                    "created_at": metadata.get("created_at", ""),
                    "updated_at": metadata.get("updated_at", ""),
                    "metadata": {k: v for k, v in metadata.items() if k not in ["type", "tags", "created_at", "updated_at"]}
                })

        return sorted(memories, key=lambda m: m.get("updated_at") or m.get("created_at"), reverse=True)[:limit]

    async def update_memory(
        self,
        memory_id: str,
        content: Optional[str] = None,
        tags: Optional[List[str]] = None,
        metadata: Optional[Dict] = None
    ) -> Optional[Dict]:
        try:
            existing = self.collection.get(ids=[memory_id])
            if not existing or not existing['documents']:
                return None

            new_content = content or existing['documents'][0]
            embedding = await ollama_client.generate_embedding(new_content, self.embedding_model)

            old_metadata = existing['metadatas'][0] if existing['metadatas'] else {}

            new_metadata = {**old_metadata}
            if tags is not None:
                new_metadata["tags"] = ",".join(tags)
            if metadata:
                new_metadata.update(metadata)
            new_metadata["updated_at"] = datetime.utcnow().isoformat()

            self.collection.update(
                ids=[memory_id],
                embeddings=[embedding] if embedding else None,
                documents=[new_content],
                metadatas=[new_metadata]
            )

            return {
                "id": memory_id,
                "content": new_content,
                "type": new_metadata.get("type", "reference"),
                "tags": tags if tags is not None else old_metadata.get("tags", "").split(","),
                "updated_at": datetime.utcnow().isoformat()
            }
        except Exception as e:
            print(f"Error updating memory: {e}")
            return None

    async def delete_memory(self, memory_id: str) -> bool:
        try:
            self.collection.delete(ids=[memory_id])
            return True
        except Exception as e:
            print(f"Error deleting memory: {e}")
            return False

    async def get_all_memories(self, limit: int = 100) -> List[Dict]:
        results = self.collection.get(limit=limit)

        memories = []
        if results and results['documents']:
            for i, doc in enumerate(results['documents']):
                metadata = results['metadatas'][i] if results['metadatas'] else {}

                memories.append({
                    "id": results['ids'][i],
                    "content": doc,
                    "type": metadata.get("type", "reference"),
                    "tags": metadata.get("tags", "").split(",") if metadata.get("tags") else [],
                    "created_at": metadata.get("created_at", ""),
                    "metadata": {k: v for k, v in metadata.items() if k not in ["type", "tags", "created_at", "updated_at"]}
                })

        return memories
    
    @staticmethod
    def _classify_memory_type(text: str) -> str:
        """
        Score the text against each memory type and return the winner.
        Avoids the old bug where a single keyword early in the string
        wins even if the overall meaning points elsewhere.
        """
        lower = text.lower()
        scores: Dict[str, int] = {
            "project": 0,
            "goal": 0,
            "preference": 0,
            "profile": 0,
            "personal": 0,
        }

        # project signals
        for kw in ("building", "working on", "developing", "creating", "startup",
                   "project", "app", "workspace", "website", "business", "company",
                   "launched", "shipping", "deployed", "repo", "codebase"):
            if kw in lower:
                scores["project"] += 2 if len(kw) > 5 else 1

        # goal signals
        for kw in ("want to", "goal", "learn", "learning", "improve", "improving",
                   "become", "trying to", "aim to", "plan to", "hoping to",
                   "working towards", "aspire"):
            if kw in lower:
                scores["goal"] += 2 if len(kw) > 5 else 1

        # preference signals
        for kw in ("prefer", "preferred", "like ", "favorite", "favourite",
                   "usually use", "always use", "i use ", "my go-to", "i enjoy",
                   "i hate", "i don't like", "i love"):
            if kw in lower:
                scores["preference"] += 2

        # profile signals
        for kw in ("my name", "years old", "i am ", "i'm ", "live in", "from ",
                   "i work at", "my job", "i study", "laptop", "computer", "pc",
                   "device", "phone", "dell", "macbook", "windows", "linux",
                   "my email", "my number"):
            if kw in lower:
                scores["profile"] += 2 if len(kw) > 4 else 1

        best = max(scores, key=scores.__getitem__)
        # Fall back to "personal" if nothing scored
        return best if scores[best] > 0 else "personal"

    async def auto_extract_memory_from_chat(
        self,
        conversation_id: str,
        messages: List[Dict]
    ) -> Optional[Dict]:

        if not messages:
            return None

        latest_user_message = None
        for msg in reversed(messages):
            if msg.get("role") == "user":
                latest_user_message = msg.get("content", "").strip()
                break

        if not latest_user_message:
            return None

        lower_message = latest_user_message.lower()

        triggers = [
            "remember",
            "save this",
            "save that",
            "store this",
            "store that",
            "don't forget",
            "memorize",
            "keep this in mind",
            "keep in mind",
            "add this to memory",
            "note that",
            "fyi ",    
        ]

        if not any(trigger in lower_message for trigger in triggers):
            return None

        fast_path_patterns = [
            r"^remember\s+that\s+",
            r"^remember\s+",
            r"^save\s+this\s*:\s*",
            r"^store\s+this\s*:\s*",
            r"^note\s+that\s+",
            r"^keep\s+(this\s+)?in\s+mind[,:\s]+",
            r"^fyi[,:\s]+",
            r"^don.t\s+forget\s+(that\s+)?",
        ]

        fact = None
        for pattern in fast_path_patterns:
            m = re.match(pattern, lower_message)
            if m:
                fact = latest_user_message[m.end():].strip()
                break

        if fact and len(fact) > 3:
            memory_type = self._classify_memory_type(fact)
            tags = ["explicit_memory"]
            return await self.create_memory(
                content=fact,
                memory_type=memory_type,
                tags=tags,
                metadata={
                    "source": f"conversation:{conversation_id}",
                    "auto_extracted": True
                }
            )

        context = "\n".join(
            f"{m['role']}: {m['content'][:300]}"
            for m in messages[-8:]
        )

        extraction_prompt = f"""Extract one memory from the user's message. Reply with exactly one line.

            FORMAT: TYPE|tag1,tag2|memory content

            TYPES: PROJECT, GOAL, PREFERENCE, PROFILE, PERSONAL
            If nothing worth saving, reply: null

            EXAMPLES:
            user: remember I'm learning Rust for systems programming
            → GOAL|learning,rust|User is learning Rust for systems programming

            user: keep in mind I prefer dark mode in all my editors
            → PREFERENCE|ui,editors|User prefers dark mode in all editors

            user: remember I work at a fintech startup as a backend engineer
            → PROFILE|work,career|User works at a fintech startup as a backend engineer

            user: save this: I'm building a local AI workspace called Mindbase
            → PROJECT|ai,project|User is building a local AI workspace called Mindbase

            user: how do I sort a list in Python?
            → null

            NOW EXTRACT:
            user: {latest_user_message}

            Conversation context:
            {context}

            Reply (one line only):"""

        try:
            model = await ollama_client.get_model()
            response = (
                await ollama_client.generate(
                    model,
                    [{"role": "user", "content": extraction_prompt}],
                    temperature=0.2,
                )
            ).strip()

            # Strip any leading "→" or whitespace the model might echo
            response = re.sub(r"^[→>\-–]\s*", "", response).strip()

            if not response or response.lower() == "null":
                return None

            match = re.search(
                r"(PROJECT|GOAL|PREFERENCE|PROFILE|PERSONAL)\|(.+?)\|(.+)",
                response,
                re.IGNORECASE
            )

            if not match:
                return None

            memory_type = match.group(1).lower()
            tags = [
                tag.strip()
                for tag in match.group(2).split(",")
                if tag.strip()
            ]
            content = match.group(3).strip()

            if len(content) < 5:
                return None

            return await self.create_memory(
                content=content,
                memory_type=memory_type,
                tags=tags,
                metadata={
                    "source": f"conversation:{conversation_id}",
                    "auto_extracted": True
                }
            )

        except Exception as e:
            print(f"Error during memory extraction: {e}")
            return None

memory_manager = MemoryManager()
