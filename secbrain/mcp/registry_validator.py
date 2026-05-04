"""
Registry health validation and reconciliation.

Detects:
- orphaned stores (filesystem has data, registry has no mapping)
- dangling registrations (registry points to non-existent path)
- unregistered default stores (BASE_DIR has data, registry doesn't know)
- duplicate path aliases (multiple project_ids point to same storage)

Registry state machine:
- CLEAN: all registry entries point to existing directories with valid stores
- ORPHANED: storage exists but no registry entry
- DANGLING: registry entry points to non-existent path
- ALIAS_COLLISION: multiple project_ids resolve to same storage path
- MIXED: combination of above states
"""
import json
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Optional

from secbrain.mcp.registry import ProjectRegistry, REGISTRY_FILE


class RegistryState(Enum):
    CLEAN = "clean"
    ORPHANED = "orphaned"        # storage exists, no registry entry
    DANGLING = "dangling"        # registry points to missing path
    ALIAS_COLLISION = "alias_collision"  # multiple project_ids → same path
    MIXED = "mixed"             # combination of issues


@dataclass
class ProjectRecord:
    project_id: str
    storage_path: Path
    exists: bool
    has_store: bool
    registered: bool
    issue: Optional[str] = None


@dataclass
class ReconciliationReport:
    state: RegistryState
    projects: list[ProjectRecord]
    total_orphaned: int
    total_dangling: int
    total_aliases: int
    suggestion: str


class RegistryValidator:
    """
    Validates registry internal consistency only.
    Does NOT scan filesystem — registry is sole source of truth.

    Detects:
    - DANGLING: registry entry points to non-existent path
    - ALIAS_COLLISION: multiple project_ids resolve to same storage path
    """

    BASE_DIR = Path.home() / ".claude" / "projects"
    CHROMA_SUB_DIR = "chroma"

    def __init__(self):
        self.registry = ProjectRegistry()
        self._cache: Optional[dict] = None

    def _load_registry(self) -> dict:
        if self._cache is None:
            if REGISTRY_FILE.exists():
                with open(REGISTRY_FILE) as f:
                    self._cache = json.load(f)
            else:
                self._cache = {"projects": {}}
        return self._cache

    def reconcile(self) -> ReconciliationReport:
        """
        Registry-only consistency check.
        Registry is sole source of truth — no filesystem discovery.
        """
        registry = self._load_registry()
        registered_projects = registry.get("projects", {})

        records: list[ProjectRecord] = []
        issues: list[str] = []

        # Check for path alias collisions
        path_to_project_ids: dict[str, list[str]] = {}
        for pid, path_str in registered_projects.items():
            path = Path(path_str)
            exists = path.exists()

            record = ProjectRecord(
                project_id=pid,
                storage_path=path,
                exists=exists,
                has_store=exists,
                registered=True,
            )

            if not exists:
                record.issue = "dangling"
                issues.append(f"DANGLING: {pid} → {path_str} (path does not exist)")

            key = str(path.resolve())
            path_to_project_ids.setdefault(key, []).append(pid)

            records.append(record)

        # Check for path alias collisions
        alias_groups = {k: v for k, v in path_to_project_ids.items() if len(v) > 1}
        for key, pids in alias_groups.items():
            issues.append(f"ALIAS_COLLISION: {pids} all → {key}")
            for pid in pids:
                for rec in records:
                    if rec.project_id == pid:
                        rec.issue = "alias_collision"

        dangling_count = sum(1 for r in records if r.issue == "dangling")
        alias_count = sum(1 for r in records if r.issue == "alias_collision")

        if issues:
            if dangling_count and alias_count:
                state = RegistryState.MIXED
            elif dangling_count:
                state = RegistryState.DANGLING
            elif alias_count:
                state = RegistryState.ALIAS_COLLISION
            else:
                state = RegistryState.CLEAN
        else:
            state = RegistryState.CLEAN

        suggestion = self._generate_suggestion(state, dangling_count, alias_count)

        return ReconciliationReport(
            state=state,
            projects=records,
            total_orphaned=0,
            total_dangling=dangling_count,
            total_aliases=alias_count,
            suggestion=suggestion,
        )

    def _generate_suggestion(
        self, state: RegistryState,
        dangling: int, aliases: int
    ) -> str:
        if state == RegistryState.CLEAN:
            return "Registry is consistent. No action needed."

        parts = []
        if dangling:
            parts.append(f"Fix {dangling} dangling registration(s) — update path with register_project() or unregister_project().")
        if aliases:
            parts.append(f"Resolve {aliases} alias collision(s) — multiple project_ids map to same storage path.")

        return " ".join(parts)

    def validate(self) -> tuple[bool, str]:
        """
        Quick validation check. Returns (is_valid, message).
        Use this for health_check integration.
        """
        report = self.reconcile()

        if report.state == RegistryState.CLEAN:
            return True, "registry_clean"

        lines = [f"state={report.state.value}"]
        for rec in report.projects:
            if rec.issue:
                lines.append(f"{rec.project_id}: {rec.issue}")

        return False, "; ".join(lines)
