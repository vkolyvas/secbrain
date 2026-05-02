"""
OpenAI embeddings wrapper with retry logic and batch support.
"""
import time
from typing import Optional

import openai
from openai import OpenAI

from ..config import EMBEDDING_MODEL, EMBEDDING_DIMENSIONS, OPENAI_API_KEY


class OpenAIEmbedder:
    """Wrapper for OpenAI text-embedding-3-small with retries."""

    def __init__(
        self,
        model: str = EMBEDDING_MODEL,
        api_key: str = OPENAI_API_KEY,
        batch_size: int = 100,
        max_retries: int = 3,
        retry_delay: float = 1.0,
    ):
        self.model = model
        self.batch_size = batch_size
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.client = OpenAI(api_key=api_key)

    def embed(self, text: str) -> list[float]:
        """Embed a single text string."""
        return self._embed_with_retry([text])[0]

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Embed multiple text strings in batches."""
        results = []
        for i in range(0, len(texts), self.batch_size):
            batch = texts[i : i + self.batch_size]
            results.extend(self._embed_with_retry(batch))
        return results

    def _embed_with_retry(self, texts: list[str]) -> list[list[float]]:
        """Call OpenAI API with retry logic."""
        for attempt in range(self.max_retries):
            try:
                response = self.client.embeddings.create(
                    model=self.model,
                    input=texts,
                )
                return [item.embedding for item in response.data]
            except Exception as e:
                if attempt < self.max_retries - 1:
                    time.sleep(self.retry_delay * (attempt + 1))
                else:
                    raise RuntimeError(f"OpenAI embedding failed after {self.max_retries} attempts: {e}")

        return []  # Should not reach here

    @property
    def dimensions(self) -> int:
        return EMBEDDING_DIMENSIONS


# Singleton instance
_embedder: Optional[OpenAIEmbedder] = None


def get_embedder() -> OpenAIEmbedder:
    """Get singleton embedder instance."""
    global _embedder
    if _embedder is None:
        _embedder = OpenAIEmbedder()
    return _embedder
