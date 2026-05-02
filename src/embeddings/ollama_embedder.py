"""
Ollama embeddings wrapper for local embedding generation.
"""
import time
from typing import Optional

import requests

from ..config import EMBEDDING_MODEL, EMBEDDING_DIMENSIONS, OLLAMA_BASE_URL


class OllamaEmbedder:
    """Wrapper for Ollama embeddings API with retries."""

    def __init__(
        self,
        model: str = EMBEDDING_MODEL,
        base_url: str = OLLAMA_BASE_URL,
        batch_size: int = 10,
        max_retries: int = 3,
        retry_delay: float = 1.0,
    ):
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.batch_size = batch_size
        self.max_retries = max_retries
        self.retry_delay = retry_delay

    def embed(self, text: str) -> list[float]:
        """Embed a single text string."""
        return self._embed_with_retry([text])[0]

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Embed multiple text strings."""
        results = []
        for i in range(0, len(texts), self.batch_size):
            batch = texts[i : i + self.batch_size]
            results.extend(self._embed_with_retry(batch))
        return results

    def _embed_with_retry(self, texts: list[str]) -> list[list[float]]:
        """Call Ollama API with retry logic."""
        for attempt in range(self.max_retries):
            try:
                results = []
                for text in texts:
                    response = requests.post(
                        f"{self.base_url}/api/embeddings",
                        json={"model": self.model, "prompt": text},
                        timeout=60,
                    )
                    response.raise_for_status()
                    data = response.json()
                    results.append(data.get("embedding", []))
                return results
            except Exception as e:
                if attempt < self.max_retries - 1:
                    time.sleep(self.retry_delay * (attempt + 1))
                else:
                    raise RuntimeError(f"Ollama embedding failed after {self.max_retries} attempts: {e}")
        return []

    @property
    def dimensions(self) -> int:
        return EMBEDDING_DIMENSIONS


# Singleton instance
_embedder: Optional[OllamaEmbedder] = None


def get_embedder() -> OllamaEmbedder:
    """Get singleton embedder instance."""
    global _embedder
    if _embedder is None:
        _embedder = OllamaEmbedder()
    return _embedder
