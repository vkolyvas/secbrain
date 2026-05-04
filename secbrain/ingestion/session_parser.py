"""
Claude session JSONL parser for ingestion.
"""
import json
from datetime import datetime
from pathlib import Path
from typing import Optional

from ..config import SECBRAIN_PROJECT_DIR
from ..storage.memory_schema import extract_memory_metadata


class SessionParser:
    """Parser for Claude Code session JSONL files."""

    def __init__(self, project_dir: Optional[Path] = None):
        self.project_dir = project_dir or SECBRAIN_PROJECT_DIR

    def load_sessions(self, limit: int = 10) -> list[dict]:
        """
        Load recent session files.

        Returns list of session data with messages parsed.
        """
        sessions = []

        if not self.project_dir.exists():
            return sessions

        jsonl_files = [
            f for f in self.project_dir.iterdir()
            if f.is_file() and f.suffix == '.jsonl'
        ]

        # Sort by modification time, most recent first
        jsonl_files.sort(key=lambda f: f.stat().st_mtime, reverse=True)

        for jsonl_file in jsonl_files[:limit]:
            try:
                session = self._parse_session(jsonl_file)
                if session:
                    sessions.append(session)
            except Exception as e:
                print(f"Error parsing {jsonl_file}: {e}")

        return sessions

    def _parse_session(self, jsonl_path: Path) -> Optional[dict]:
        """Parse a single JSONL session file."""
        lines = jsonl_path.read_text(encoding='utf-8').split('\n')
        lines = [l.strip() for l in lines if l.strip()]

        if not lines:
            return None

        # Extract session metadata from first valid line
        session_id = jsonl_path.stem
        created_at = datetime.fromtimestamp(jsonl_path.stat().st_mtime).isoformat()

        messages = []
        for line in lines:
            try:
                entry = json.loads(line)
                msg_data = self._extract_message(entry)
                if msg_data:
                    messages.append(msg_data)
            except json.JSONDecodeError:
                continue

        if not messages:
            return None

        return {
            "session_id": session_id,
            "created_at": created_at,
            "messages": messages,
            "message_count": len(messages),
        }

    def _extract_message(self, entry: dict) -> Optional[dict]:
        """Extract message dict with role and content from a JSONL entry."""
        try:
            msg = entry.get("message", {})
            if not msg:
                return None

            role = msg.get("role", "unknown")
            content = msg.get("content", [])

            text_content = ""
            if isinstance(content, str):
                text_content = content
            elif isinstance(content, list):
                parts = []
                for item in content:
                    if isinstance(item, dict):
                        if item.get("type") == "text":
                            parts.append(item.get("text", ""))
                        elif item.get("type") == "thinking":
                            pass
                text_content = "\n".join(parts)

            if not text_content:
                return None

            return {"role": role, "content": text_content}
        except Exception:
            return None

    def extract_memories_from_session(self, session: dict) -> list[dict]:
        """
        Extract individual memory items from a parsed session.

        Returns list of memory metadata dicts ready for Chroma.
        """
        memories = []
        session_id = session.get("session_id", "")

        # Group messages by topic (simple heuristic: consecutive non-user messages)
        current_block = []
        current_block_role = None

        for msg in session.get("messages", []):
            role = msg.get("role", "unknown")
            content = msg.get("content", "")

            if not content or len(content) < 50:
                continue

            if role == current_block_role or current_block_role is None:
                current_block.append(content)
                current_block_role = role
            else:
                # New block started, process previous
                if current_block:
                    memory = self._block_to_memory(current_block, session_id)
                    if memory:
                        memories.append(memory)
                current_block = [content]
                current_block_role = role

        # Don't forget the last block
        if current_block:
            memory = self._block_to_memory(current_block, session_id)
            if memory:
                memories.append(memory)

        return memories

    def _block_to_memory(self, content_blocks: list[str], session_id: str) -> Optional[dict]:
        """Convert a block of messages to a memory entry."""
        combined = "\n\n".join(content_blocks)
        combined = combined.strip()

        if len(combined) < 100:
            return None

        metadata = extract_memory_metadata(
            content=combined,
            source_file=f"session://{session_id}",
            session_id=session_id,
        )
        metadata["source_project"] = "secbrain"
        return metadata
