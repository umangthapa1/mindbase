from pathlib import Path
import uuid
import logging
from typing import List, Optional, Dict
from datetime import datetime
import json
import io
import time

from pypdf import PdfReader

logger = logging.getLogger(__name__)
from docx import Document as DocxDocument
from config import UPLOADS_DIR, CHROMA_DIR
from ollama import ollama_client
import chromadb

class DocumentManager:
    def __init__(self):
        self.uploads_dir = UPLOADS_DIR
        self.uploads_dir.mkdir(exist_ok=True)
        self.client = chromadb.PersistentClient(path=str(CHROMA_DIR))
        self.collection = self.client.get_or_create_collection(
            name="documents",
            metadata={"hnsw:space": "cosine"}
        )
        self.embedding_model = "nomic-embed-text"
        # Cache the document list. list_documents is called every chat turn
        # (intelligence._gather_documents) while the collection itself changes
        # only on upload or delete. A short TTL keeps the cache fresh without
        # hitting Chroma on every message.
        self._list_cache: Optional[List[Dict]] = None
        self._list_cache_at: float = 0.0
        self._list_cache_ttl: float = 30.0

    def _invalidate_list_cache(self) -> None:
        self._list_cache = None
        self._list_cache_at = 0.0

    async def upload_document(self, filename: str, content: bytes) -> Optional[Dict]:
        doc_id = str(uuid.uuid4())
        file_ext = Path(filename).suffix.lower()

        text = await self._extract_text(filename, content, file_ext)
        if not text or len(text.strip()) == 0:
            raise ValueError("Document contains no readable text or text extraction failed.")

        file_path = self.uploads_dir / f"{doc_id}{file_ext}"
        file_path.write_bytes(content)

        chunks = self._chunk_text(text)
        if not chunks:
            raise ValueError("Failed to split document into readable chunks.")

        embeddings = []
        for i, chunk in enumerate(chunks):
            emb = await ollama_client.generate_embedding(chunk, self.embedding_model)
            if not emb:
                raise RuntimeError(
                    f"Failed to generate embedding for chunk {i+1}/{len(chunks)}. "
                    f"Verify that Ollama is running and the embedding model '{self.embedding_model}' is installed (run 'ollama pull {self.embedding_model}')."
                )
            embeddings.append(emb)

        chunk_ids = [f"{doc_id}_{i}" for i in range(len(chunks))]

        self.collection.add(
            ids=chunk_ids,
            embeddings=embeddings,
            documents=chunks,
            metadatas=[{
                "document_id": doc_id,
                "filename": filename,
                "chunk_index": i,
                "created_at": datetime.utcnow().isoformat(),
                "file_type": file_ext
            } for i in range(len(chunks))]
        )

        self._invalidate_list_cache()

        return {
            "id": doc_id,
            "filename": filename,
            "type": file_ext,
            "chunks": len(chunks),
            "size": len(content),
            "created_at": datetime.utcnow().isoformat()
        }

    async def _extract_text(self, filename: str, content: bytes, file_ext: str) -> Optional[str]:
        try:
            if file_ext == ".pdf":
                pdf = PdfReader(io.BytesIO(content))
                text = ""
                for page in pdf.pages:
                    text += page.extract_text()
                return text

            elif file_ext == ".txt":
                return content.decode('utf-8', errors='ignore')

            elif file_ext == ".docx":
                doc = DocxDocument(io.BytesIO(content))
                text = "\n".join([para.text for para in doc.paragraphs])
                return text

            return None
        except Exception as e:
            logger.warning("Error extracting text: %s", e)
            return None

    def _chunk_text(self, text: str, chunk_size: int = 512, overlap: int = 100) -> List[str]:
        words = text.split()
        chunks = []
        current_chunk = []
        current_size = 0

        for word in words:
            current_chunk.append(word)
            current_size += len(word) + 1

            if current_size >= chunk_size:
                chunks.append(" ".join(current_chunk))
                overlap_count = min(len(current_chunk) // 4, overlap)
                current_chunk = current_chunk[-overlap_count:] if overlap_count > 0 else []
                current_size = sum(len(w) for w in current_chunk)

        if current_chunk:
            chunks.append(" ".join(current_chunk))

        return [c.strip() for c in chunks if c.strip()]

    async def search_documents(
        self, query: str, top_k: int = 4, min_relevance: float = 0.35
    ) -> Dict:
        embedding = await ollama_client.generate_embedding(query, self.embedding_model)
        if not embedding:
            return {"chunks": []}

        results = self.collection.query(
            query_embeddings=[embedding],
            n_results=top_k,
        )

        chunks = []
        if results and results.get("documents") and results["documents"][0]:
            for i, text in enumerate(results["documents"][0]):
                meta = results["metadatas"][0][i] if results["metadatas"] else {}
                distance = results["distances"][0][i] if results.get("distances") else 1.0
                relevance = round(1 - distance, 3)
                if relevance < min_relevance:
                    continue
                chunks.append({
                    "text": text,
                    "filename": meta.get("filename"),
                    "document_id": meta.get("document_id"),
                    "chunk_index": meta.get("chunk_index"),
                    "relevance": relevance,
                })

        return {"chunks": chunks}

    async def ask_document(self, query: str, document_id: Optional[str] = None, top_k: int = 3) -> Dict:
        embedding = await ollama_client.generate_embedding(query, self.embedding_model)
        if not embedding:
            return {"answer": "Error generating embedding", "sources": []}

        where_filter = {"document_id": {"$eq": document_id}} if document_id else None

        results = self.collection.query(
            query_embeddings=[embedding],
            n_results=top_k,
            where=where_filter
        )

        context_text = "\n".join(results['documents'][0]) if results['documents'] else ""

        prompt = f"""Answer using ONLY the document excerpts below. If the answer is not in the excerpts, say so.

Excerpts:
{context_text}

Question: {query}

Answer (cite which excerpt when possible):"""

        messages = [{"role": "user", "content": prompt}]

        answer = ""
        model = await ollama_client.get_model()
        async for chunk in ollama_client.stream_generate(model, messages):
            answer += chunk

        sources = []
        if results and results['metadatas']:
            for meta in results['metadatas'][0]:
                sources.append({
                    "filename": meta.get("filename"),
                    "chunk": meta.get("chunk_index")
                })

        return {
            "answer": answer.strip(),
            "sources": sources[:2]
        }

    async def summarize_document(self, document_id: str) -> Optional[str]:
        try:
            results = self.collection.get(
                where={"document_id": {"$eq": document_id}},
                limit=20
            )

            if not results or not results['documents']:
                return None

            text = "\n".join(results['documents'][:10])

            prompt = f"""Summarize this document in 3-4 sentences:

{text}

Summary:"""

            messages = [{"role": "user", "content": prompt}]

            summary = ""
            model = await ollama_client.get_model()
            async for chunk in ollama_client.stream_generate(model, messages):
                summary += chunk

            return summary.strip()
        except Exception as e:
            logger.warning("Error summarizing: %s", e)
            return None

    def delete_document(self, document_id: str) -> bool:
        try:
            results = self.collection.get(where={"document_id": {"$eq": document_id}})
            if results and results['ids']:
                self.collection.delete(ids=results['ids'])

            file_pattern = f"{document_id}*"
            for file in self.uploads_dir.glob(file_pattern):
                file.unlink()

            self._invalidate_list_cache()
            return True
        except Exception as e:
            logger.warning("Error deleting document: %s", e)
            return False

    def clear_all(self) -> int:
        """Delete every document (vectors + original files) and return how many.

        Same reasoning as `MemoryManager.clear_all`: Chroma has no truncate and a
        bulk id-delete leaves the HNSW index tombstoned, so drop the collection and
        recreate it with the same settings. Synchronous — call via `asyncio.to_thread`.
        """
        try:
            ids = self.collection.get(limit=100_000).get("metadatas") or []
            removed = len({m.get("document_id") for m in ids if m.get("document_id")})
        except Exception as e:
            logger.warning("Could not count documents before clearing: %s", e)
            removed = 0

        self.client.delete_collection(name="documents")
        self.collection = self.client.get_or_create_collection(
            name="documents",
            metadata={"hnsw:space": "cosine"}
        )

        for file in self.uploads_dir.iterdir():
            if file.is_file():
                try:
                    file.unlink()
                except OSError as e:
                    logger.warning("Could not delete upload %s: %s", file.name, e)

        self._invalidate_list_cache()
        return removed

    async def list_documents(self) -> List[Dict]:
        if (
            self._list_cache is not None
            and (time.monotonic() - self._list_cache_at) < self._list_cache_ttl
        ):
            return list(self._list_cache)

        docs = {}
        results = self.collection.get(limit=1000)

        if results and results['metadatas']:
            for meta in results['metadatas']:
                doc_id = meta.get("document_id")
                if doc_id and doc_id not in docs:
                    docs[doc_id] = {
                        "id": doc_id,
                        "filename": meta.get("filename"),
                        "type": meta.get("file_type"),
                        "created_at": meta.get("created_at"),
                        "chunks": 0
                    }
                if doc_id:
                    docs[doc_id]["chunks"] += 1

        self._list_cache = list(docs.values())
        self._list_cache_at = time.monotonic()
        return list(self._list_cache)

document_manager = DocumentManager()
