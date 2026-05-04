"""
Chroma DB storage for secbrain memories.
"""
import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

import chromadb
from chromadb.config import Settings

from ..config import CHROMA_PATH, COLLECTION_NAME, MEMORY_TYPES
from ..embeddings.ollama_embedder import get_embedder


class ChromaStore:
    """Chroma-backed memory store with CRUD operations."""

    def __init__(
        self,
        path: Path = CHROMA_PATH,
        collection_name: str = COLLECTION_NAME,
    ):
        self.path = path
        self.collection_name = collection_name
        self._client: Optional[chromadb.PersistentClient] = None
        self._collection = None

    def _ensure_client(self):
        """Lazy initialization of Chroma client and collection."""
        if self._client is None:
            self.path.mkdir(parents=True, exist_ok=True)
            self._client = chromadb.PersistentClient(
                path=str(self.path),
                settings=Settings(anonymized_telemetry=False),
            )
            self._collection = self._client.get_or_create_collection(
                name=self.collection_name,
                metadata={"description": "secbrain memories - RAG knowledge base"},
            )

    @property
    def collection(self):
        self._ensure_client()
        return self._collection

    def add_memory(
        self,
        content: str,
        memory_type: str,
        title: str,
        source_file: str = "",
        source_project: str = "secbrain",
        tags: list[str] = None,
        session_id: str = "",
    ) -> str:
        """
        Add a memory to the store.

        Returns the memory ID.
        """
        if memory_type not in MEMORY_TYPES:
            raise ValueError(f"Invalid memory_type: {memory_type}. Must be one of {MEMORY_TYPES}")

        memory_id = str(uuid.uuid4())
        embedder = get_embedder()
        embedding = embedder.embed(content)

        metadata = {
            "memory_type": memory_type,
            "title": title,
            "source_file": source_file,
            "source_project": source_project,
            "created_at": datetime.utcnow().isoformat(),
            "session_id": session_id,
            "tags": json.dumps(tags or []),
        }

        self.collection.add(
            ids=[memory_id],
            embeddings=[embedding],
            documents=[content],
            metadatas=[metadata],
        )

        return memory_id

    def query(
        self,
        query_text: str,
        top_k: int = 5,
        memory_type: Optional[str] = None,
        source_project: Optional[str] = None,
    ) -> list[dict]:
        """
        Query memories by semantic similarity.

        Returns list of memory dicts sorted by relevance.
        """
        embedder = get_embedder()
        query_embedding = embedder.embed(query_text)

        where_filter = {}
        if memory_type:
            where_filter["memory_type"] = memory_type
        if source_project:
            where_filter["source_project"] = source_project

        results = self.collection.query(
            query_embeddings=[query_embedding],
            n_results=top_k,
            where=where_filter if where_filter else None,
            include=["documents", "metadatas", "distances"],
        )

        memories = []
        if results["ids"] and len(results["ids"]) > 0:
            for i, memory_id in enumerate(results["ids"][0]):
                memories.append({
                    "id": memory_id,
                    "content": results["documents"][0][i],
                    "metadata": results["metadatas"][0][i],
                    "distance": results["distances"][0][i],
                    "score": 1.0 - results["distances"][0][i],  # Convert distance to similarity
                })
        return memories

    def get_by_type(self, memory_type: str, limit: int = 10) -> list[dict]:
        """Get memories filtered by type."""
        if memory_type not in MEMORY_TYPES:
            raise ValueError(f"Invalid memory_type: {memory_type}")

        results = self.collection.get(
            where={"memory_type": memory_type},
            limit=limit,
            include=["documents", "metadatas"],
        )

        memories = []
        if results["ids"]:
            for i, memory_id in enumerate(results["ids"]):
                memories.append({
                    "id": memory_id,
                    "content": results["documents"][i],
                    "metadata": results["metadatas"][i],
                })
        return memories

    def get_stats(self) -> dict:
        """Get collection statistics."""
        self._ensure_client()

        total = self.collection.count()

        by_type = {}
        for memory_type in MEMORY_TYPES:
            count = len(self.collection.get(
                where={"memory_type": memory_type},
                include=[],
            )["ids"])
            by_type[memory_type] = count

        return {
            "total_memories": total,
            "by_type": by_type,
            "collection": self.collection_name,
        }

    def delete(self, memory_id: str) -> bool:
        """Delete a memory by ID."""
        try:
            self.collection.delete(ids=[memory_id])
            return True
        except Exception:
            return False

    def reset(self):
        """Delete all memories (use with caution)."""
        self._ensure_client()
        self._client.delete_collection(self.collection_name)
        self._collection = None
        self._client = None


# Singleton instance
_store: Optional[ChromaStore] = None


def get_store() -> ChromaStore:
    """Get singleton store instance."""
    global _store
    if _store is None:
        _store = ChromaStore()
    return _store
