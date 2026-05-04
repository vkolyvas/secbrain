# secbrain - Retrieval-augmented cognitive memory system

from secbrain.storage.chroma_store import get_store

class SecBrain:
    """Main interface for secbrain memory operations."""

    def __init__(self):
        self._store = None

    @property
    def store(self):
        if self._store is None:
            self._store = get_store()
        return self._store

    def add_memory(self, title, content, memory_type, tags=None, source_project="secbrain"):
        """Add a memory to the store."""
        return self.store.add_memory(
            content=content,
            memory_type=memory_type,
            title=title,
            source_project=source_project,
            tags=tags or [],
        )

    def query_memory(self, query, top_k=5, memory_type=None):
        """Query memories by semantic similarity."""
        return self.store.query(
            query_text=query,
            top_k=top_k,
            memory_type=memory_type,
        )

    def get_memories_by_type(self, memory_type, limit=10):
        """Get memories by type."""
        return self.store.get_by_type(memory_type=memory_type, limit=limit)

    def get_memory_stats(self):
        """Get memory statistics."""
        return self.store.get_stats()

    def inject_context(self, query, session_context, top_k=3):
        """Generate context block for prompt injection."""
        results = self.store.query(query_text=query, top_k=top_k)
        if not results:
            return f"Context ({session_context}): No relevant memories found."

        parts = [f"## Context: {session_context}\n### Relevant memories:\n"]
        for i, mem in enumerate(results, 1):
            meta = mem["metadata"]
            parts.append(f"**{i}. {meta['title']}** ({meta['memory_type']})\n{mem['content'][:300]}...")
        return "\n\n".join(parts)