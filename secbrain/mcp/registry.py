"""
Project identity registry.

Decouples logical project_id from physical storage path.
Allows projects to be renamed, migrated, or aliased without losing memory graphs.

Registry file: ~/.claude/projects/_registry.json

Schema v2:
{
  "projects": {
    "project_id": {
      "path": "/absolute/path/to/storage",
      "storage_policy": "persistent" | "ephemeral"
    }
  }
}

storage_policy:
- persistent: stored in ~/.claude/projects/ (safe, survives project deletion)
- ephemeral: stored in project directory (at risk if project is deleted)
"""
import json
from pathlib import Path
from typing import Optional, Union

from secbrain.config import MEMORY_TYPES


REGISTRY_FILE = Path.home() / ".claude" / "projects" / "_registry.json"

# Managed base directories — storage inside these is "persistent"
MANAGED_BASE_DIRS = [
    Path.home() / ".claude" / "projects",
    Path.home() / ".claude" / "memories",
]


class ProjectRegistry:
    """
    Maps project_id (logical) to storage path (physical).
    Supports both old schema (string) and new schema (object with storage_policy).
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

    def _parse_entry(self, entry: Union[str, dict]) -> tuple[Path, str]:
        """
        Parse a registry entry. Handles both old (string) and new (object) schemas.
        Returns (path, storage_policy).
        """
        if isinstance(entry, str):
            # Old schema: "project_id": "/path/to/storage"
            return Path(entry), "ephemeral" if self._is_risky_path(Path(entry)) else "persistent"
        elif isinstance(entry, dict):
            # New schema: "project_id": {"path": "...", "storage_policy": "..."}
            path = Path(entry.get("path", ""))
            policy = entry.get("storage_policy", "ephemeral")
            return path, policy
        else:
            raise ValueError(f"Invalid registry entry type for {entry}")

    def _is_risky_path(self, path: Path) -> bool:
        """
        Detect if path is inside a git repo or project directory (at risk of deletion).
        Returns True if path is potentially ephemeral.
        """
        try:
            resolved = path.resolve()
            # Check if inside a git repository
            if (resolved / ".git").exists() or any((resolved / ".git").iterdir() if (resolved / ".git").is_dir() else False for _ in [None]):
                return True
            # Check if inside a common project directory pattern
            path_str = str(resolved)
            risky_patterns = ["/base/", "/workspace/", "/projects/", "/repos/", "/repo/"]
            for pattern in risky_patterns:
                if pattern in path_str and not path_str.startswith(str(self.BASE_DIR)):
                    return True
            return False
        except Exception:
            return False

    def _detect_storage_policy(self, storage_path: Path) -> str:
        """Auto-detect storage policy based on path location."""
        try:
            resolved = str(storage_path.resolve())
            # Inside managed base = persistent
            for base in MANAGED_BASE_DIRS:
                if resolved.startswith(str(base.resolve())):
                    return "persistent"
            # Inside git repo or project dir = ephemeral
            if self._is_risky_path(storage_path):
                return "ephemeral"
            return "persistent"
        except Exception:
            return "ephemeral"

    def resolve(self, project_id: str) -> Optional[Path]:
        """
        Resolve project_id to storage path.

        Registry is the SOLE source of truth. No fallback.
        Returns None if project_id not registered.
        """
        registry = self._load()
        projects = registry.get("projects", {})

        if project_id in projects:
            path, _ = self._parse_entry(projects[project_id])
            if path.is_absolute():
                return path
            return self.BASE_DIR / path

        return None

    def get_storage_policy(self, project_id: str) -> Optional[str]:
        """Get storage policy for a project. Returns 'persistent' or 'ephemeral'."""
        registry = self._load()
        projects = registry.get("projects", {})
        if project_id in projects:
            _, policy = self._parse_entry(projects[project_id])
            return policy
        return None

    def is_registered(self, project_id: str) -> bool:
        """Check if project_id exists in registry."""
        registry = self._load()
        return project_id in registry.get("projects", {})

    def register(self, project_id: str, storage_path: Path, storage_policy: str = None):
        """
        Register an explicit storage path for a project_id.
        storage_policy: 'persistent' (safe) or 'ephemeral' (at risk).
        If not specified, auto-detected based on path location.
        """
        if storage_policy is None:
            storage_policy = self._detect_storage_policy(storage_path)

        registry = self._load()
        registry.setdefault("projects", {})[project_id] = {
            "path": str(storage_path),
            "storage_policy": storage_policy,
        }
        self._save()

    def unregister(self, project_id: str) -> bool:
        """Remove a project registration."""
        registry = self._load()
        if project_id in registry.get("projects", {}):
            del registry["projects"][project_id]
            self._save()
            return True
        return False

    def list_projects(self) -> dict:
        """List all registered projects with their path and storage_policy."""
        registry = self._load()
        result = {}
        for pid, entry in registry.get("projects", {}).items():
            path, policy = self._parse_entry(entry)
            result[pid] = {
                "path": str(path),
                "storage_policy": policy,
            }
        return result

    def migrate(self, project_id: str, new_storage_path: Path):
        """
        Migrate a project's storage to a new location.
        Preserves storage_policy from existing entry.
        """
        current_policy = self.get_storage_policy(project_id) or "persistent"
        self.register(project_id, new_storage_path, current_policy)

    def get_warnings(self) -> list[str]:
        """
        Return list of warnings for risky configurations.
        """
        warnings = []
        registry = self._load()
        for pid, entry in registry.get("projects", {}).items():
            path, policy = self._parse_entry(entry)
            if policy == "ephemeral":
                warnings.append(f"{pid}: storage is ephemeral — path is inside project directory ({path})")
        return warnings


# Singleton registry instance
_registry: Optional[ProjectRegistry] = None


def get_registry() -> ProjectRegistry:
    global _registry
    if _registry is None:
        _registry = ProjectRegistry()
    return _registry
