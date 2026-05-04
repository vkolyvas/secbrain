"""
secbrain configuration
"""
import os
from pathlib import Path

# Project paths
PROJECT_ROOT = Path("/mnt/projects/secbrain")
DATA_DIR = Path.home() / ".claude" / "projects" / "-mnt-projects-secbrain"
CHROMA_PATH = DATA_DIR / "chroma"
OBSIDIAN_VAULT = Path.home() / "obsidian-vault" / "projects"
SECBRAIN_PROJECT_DIR = DATA_DIR

# Memory schema
MEMORY_TYPES = ["decision", "pattern", "architecture", "lesson"]
COLLECTION_NAME = "secbrain_memories"

# Embedding settings
EMBEDDING_MODEL = "nomic-embed-text"
EMBEDDING_DIMENSIONS = 768  # nomic-embed-text outputs 768 dimensions

# Ollama (local)
OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")

# Ingestion defaults
DEFAULT_TOP_K = 5
MAX_MEMORY_CONTENT_LENGTH = 10000  # Truncate memories longer than this
