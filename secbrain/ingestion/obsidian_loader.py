"""
Obsidian vault file ingestion.
"""
import json
from datetime import datetime
from pathlib import Path
from typing import Optional

from ..config import OBSIDIAN_VAULT
from ..storage.memory_schema import extract_memory_metadata


class ObsidianLoader:
    """Loader for Obsidian vault markdown files."""

    def __init__(self, vault_path: Optional[Path] = None):
        self.vault_path = vault_path or OBSIDIAN_VAULT

    def load_memory_files(self, project: str = "secbrain") -> list[dict]:
        """
        Load all memory files from a project in the Obsidian vault.

        Returns list of memory metadata dicts ready for Chroma insertion.
        """
        memory_dir = self.vault_path / project / "memory"
        if not memory_dir.exists():
            return []

        memories = []
        for md_file in memory_dir.glob("*.md"):
            try:
                memory = self._load_file(md_file, project)
                if memory:
                    memories.append(memory)
            except Exception as e:
                print(f"Error loading {md_file}: {e}")

        return memories

    def _load_file(self, file_path: Path, project: str) -> Optional[dict]:
        """Load and parse a single markdown file."""
        if file_path.name.startswith('.'):
            return None

        content = file_path.read_text(encoding='utf-8')
        if not content.strip():
            return None

        # Extract metadata
        metadata = extract_memory_metadata(
            content=content,
            source_file=str(file_path.relative_to(self.vault_path)),
            session_id="",
        )
        metadata["source_project"] = project
        metadata["file_mtime"] = datetime.fromtimestamp(file_path.stat().st_mtime).isoformat()

        return metadata

    def scan_all_projects(self) -> dict[str, list[dict]]:
        """
        Scan all projects in the vault.

        Returns dict mapping project name -> list of memory metadata.
        """
        projects = {}
        memory_root = self.vault_path

        if not memory_root.exists():
            return projects

        for project_dir in memory_root.iterdir():
            if project_dir.is_dir() and (project_dir / "memory").exists():
                memories = self.load_memory_files(project_dir.name)
                if memories:
                    projects[project_dir.name] = memories

        return projects
