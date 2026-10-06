"""
ChatGPT export JSON parser for ingestion.
Supports ChatGPT's official export format (conversations.json).
"""
import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

from ..storage.memory_schema import extract_memory_metadata


class ChatGPTParser:
    """
    Parser for ChatGPT export JSON files.

    Supports two formats:
    1. Official ChatGPT export with 'conversations' array containing mapping-based structure
    2. Simplified flat format with 'messages' array per conversation
    """

    def __init__(self, export_path: Optional[Path] = None):
        self.export_path = export_path

    def load_conversations(self, export_path: Optional[Path] = None) -> list[dict]:
        """
        Load conversations from a ChatGPT export file.

        Returns list of parsed conversation dicts with messages.
        """
        path = Path(export_path) if export_path else self.export_path
        if not path:
            raise ValueError("No export path provided")

        if not path.exists():
            raise FileNotFoundError(f"Export file not found: {path}")

        with open(path, encoding='utf-8') as f:
            data = json.load(f)

        # Handle official export format with 'conversations' key
        if isinstance(data, dict) and 'conversations' in data:
            return [self._parse_official_conversation(conv) for conv in data['conversations']]

        # Handle flat array format
        if isinstance(data, list):
            return [self._parse_flat_conversation(conv) for conv in data if isinstance(conv, dict)]

        raise ValueError(f"Unknown export format in {path}")

    def _parse_official_conversation(self, conv: dict) -> dict:
        """
        Parse official ChatGPT export conversation format.
        Uses mapping to reconstruct message thread.
        """
        conv_id = conv.get('id', str(uuid.uuid4()))
        title = conv.get('title', 'Untitled ChatGPT Session')
        create_time = conv.get('create_time', '')

        if isinstance(create_time, (int, float)):
            created_at = datetime.fromtimestamp(create_time).isoformat()
        else:
            created_at = create_time or datetime.utcnow().isoformat()

        # Build message tree from mapping
        messages = self._build_messages_from_mapping(conv.get('mapping', {}))

        return {
            "session_id": f"chatgpt-{conv_id}",
            "title": title,
            "created_at": created_at,
            "messages": messages,
            "message_count": len(messages),
        }

    def _build_messages_from_mapping(self, mapping: dict) -> list[dict]:
        """Reconstruct ordered messages from the message mapping tree."""
        messages = []

        # Find root nodes (messages with no parent)
        roots = []
        for msg_id, node in mapping.items():
            parent = node.get('parent')
            if parent is None or parent == "null":
                roots.append(msg_id)

        # Traverse from roots, following children
        def traverse(msg_id):
            node = mapping.get(msg_id)
            if not node:
                return

            message = node.get('message')
            if message:
                role = message.get('role', 'unknown')
                content = self._extract_content(message.get('content', {}))

                if content and role in ('user', 'assistant'):
                    messages.append({
                        "role": role,
                        "content": content,
                        "created_at": message.get('create_time', '')
                    })

            # Visit children
            for child_id in node.get('children', []):
                traverse(child_id)

        for root in roots:
            traverse(root)

        return messages

    def _parse_flat_conversation(self, conv: dict) -> dict:
        """Parse simplified flat array format."""
        conv_id = conv.get('id', str(uuid.uuid4()))
        title = conv.get('title', conv.get('name', 'Untitled ChatGPT Session'))
        created_at = conv.get('created_at', datetime.utcnow().isoformat())

        raw_messages = conv.get('messages', [])
        messages = []

        for msg in raw_messages:
            role = msg.get('role', 'unknown')
            content = msg.get('content', '')

            if isinstance(content, dict):
                content = self._extract_content(content)
            elif isinstance(content, list):
                content = ' '.join(str(c) if isinstance(c, str) else str(c.get('text', '')) for c in content)

            if content and role in ('user', 'assistant'):
                messages.append({
                    "role": role,
                    "content": content,
                    "created_at": msg.get('created_at', '')
                })

        return {
            "session_id": f"chatgpt-{conv_id}",
            "title": title,
            "created_at": created_at,
            "messages": messages,
            "message_count": len(messages),
        }

    def _extract_content(self, content_obj: dict) -> str:
        """Extract text content from ChatGPT message content object."""
        if isinstance(content_obj, str):
            return content_obj

        content_type = content_obj.get('content_type', '')

        if content_type == 'text':
            parts = content_obj.get('parts', [])
            return ' '.join(str(p) for p in parts)

        if content_type == 'code':
            # Extract code with language
            language = content_obj.get('language', '')
            code = content_obj.get('text', '')
            return f"```{language}\n{code}\n```" if code else ''

        # Fallback
        if isinstance(content_obj, dict) and 'parts' in content_obj:
            return ' '.join(str(p) for p in content_obj['parts'])

        return str(content_obj) if content_obj else ''

    def extract_memories_from_conversation(self, conversation: dict) -> list[dict]:
        """
        Extract individual memory items from a parsed conversation.

        Returns list of memory metadata dicts ready for Chroma.
        """
        memories = []
        session_id = conversation.get("session_id", "")
        title = conversation.get("title", "ChatGPT Session")

        # Group messages into coherent blocks (user + assistant pairs)
        messages = conversation.get("messages", [])
        current_block = []
        current_block_roles = set()

        for msg in messages:
            role = msg.get("role", "unknown")
            content = msg.get("content", "")

            # Skip very short content
            if not content or len(content) < 50:
                continue

            # Add to current block
            current_block.append(f"[{role}]: {content}")
            current_block_roles.add(role)

            # When we have a complete exchange (user + assistant), process it
            if current_block_roles == {"user", "assistant"}:
                memory = self._block_to_memory(current_block, session_id, title)
                if memory:
                    memories.append(memory)
                current_block = []
                current_block_roles = set()

        # Don't forget the last block (may be incomplete but still valuable)
        if current_block and len(current_block) >= 2:
            memory = self._block_to_memory(current_block, session_id, title)
            if memory:
                memories.append(memory)

        return memories

    def _block_to_memory(
        self,
        content_blocks: list[str],
        session_id: str,
        title: str = ""
    ) -> Optional[dict]:
        """Convert a block of messages to a memory entry."""
        combined = "\n\n".join(content_blocks)
        combined = combined.strip()

        if len(combined) < 100:
            return None

        metadata = extract_memory_metadata(
            content=combined,
            source_file=f"chatgpt://{session_id}",
            session_id=session_id,
        )

        # Use conversation title if available
        if title and title != "ChatGPT Session":
            metadata["title"] = f"[ChatGPT] {title}: {metadata['title']}"

        metadata["tags"] = metadata.get("tags", []) + ["chatgpt"]
        return metadata

    def extract_all_memories(self, export_path: Optional[Path] = None) -> list[dict]:
        """
        Load conversations and extract all memories.

        Returns flat list of memory metadata dicts.
        """
        conversations = self.load_conversations(export_path)
        all_memories = []

        for conv in conversations:
            memories = self.extract_memories_from_conversation(conv)
            all_memories.extend(memories)

        return all_memories