"""
Project identity registry.

Decouples logical project_id from physical storage path.
Allows projects to be renamed, migrated, or aliased without losing memory graphs.

Registry file: ~/.claude/projects/_registry.json

Schema:
{
  "projects": {
    "project_id": "/absolute/path/to/storage"
  }
}
"""
import json
from pathlib import Path
from typing import Optional

from secbrain.config import MEMORY_TYPES


REGISTRY_FILE = Path.home() / ".claude" / "projects" / "_registry.json"


class ProjectRegistry:
    """
    Maps project_id (logical) to storage path (physical).
    Default behavior: BASE_DIR / project_id
    Override: any absolute path via registry.
    """

    BASE_DIR = Path.home() / ".claude" / "projects"

    def __init__(self):
        self._cache: Optional[dict] = None

    def _load(self) -> dict:
        """Load registry from disk, lazily."""
        if self._cache is None:
            if REGISTRY_FILE.exists():
                with open(REGISTRY_FILE) as f:
                    self._cache = json.load(f)
            else:
                self._cache = {"projects": {}}
        return self._cache

    def _save(self):
        """Persist registry to disk."""
        REGISTRY_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(REGISTRY_FILE, "w") as f:
            json.dump(self._cache, f, indent=2)

    def resolve(self, project_id: str) -> Path:
        """
        Resolve project_id to storage path.

        Registry is the SOLE source of truth. No fallback.
        If project_id is not registered, returns None.
        """
        registry = self._load()
        projects = registry.get("projects", {})

        if project_id in projects:
            path = Path(projects[project_id])
            if path.is_absolute():
                return path
            return self.BASE_DIR / path

        # Sole source of truth — no implicit fallback
        return None

    def is_registered(self, project_id: str) -> bool:
        """Check if project_id exists in registry."""
        registry = self._load()
        return project_id in registry.get("projects", {})

    def register(self, project_id: str, storage_path: Path):
        """
        Register an explicit storage path for a project_id.
        Allows projects to be moved without losing their memory graph.
        """
        registry = self._load()
        registry.setdefault("projects", {})[project_id] = str(storage_path)
        self._save()

    def unregister(self, project_id: str) -> bool:
        """Remove a project registration. Storage path reverts to default."""
        registry = self._load()
        if project_id in registry.get("projects", {}):
            del registry["projects"][project_id]
            self._save()
            return True
        return False

    def list_projects(self) -> dict:
        """List all registered projects and their storage paths."""
        registry = self._load()
        return dict(registry.get("projects", {}))

    def migrate(self, project_id: str, new_storage_path: Path):
        """
        Migrate a project's storage to a new location.
        Updates registry to point to new path.
        """
        self.register(project_id, new_storage_path)


# Singleton registry instance
_registry: Optional[ProjectRegistry] = None


def get_registry() -> ProjectRegistry:
    global _registry
    if _registry is None:
        _registry = ProjectRegistry()
    return _registry
