"""
Memory schema enforcement and classification.
"""
import re
from datetime import datetime
from typing import Optional

from ..config import MEMORY_TYPES, MAX_MEMORY_CONTENT_LENGTH


# Classification patterns (order matters - first match wins)
CLASSIFICATION_PATTERNS = [
    ("decision", [
        r"\bdecided\b",
        r"\bchose\b",
        r"\bchoice\b",
        r"\bbecause\b",
        r"\brationale\b",
        r"\bwent with\b",
        r"\bopted for\b",
    ]),
    ("pattern", [
        r"\bpattern\b",
        r"\breusable\b",
        r"\bwhen \w+ then \w+\b",
        r"\bsingleton\b",
        r"\bfactory\b",
        r"\bobserver\b",
        r"\bstrategy\b",
        r"\badapter\b",
        r"\bfacade\b",
    ]),
    ("architecture", [
        r"\bsystem design\b",
        r"\barchitecture\b",
        r"\bmicroservices\b",
        r"\bevent[- ]driven\b",
        r"\bapi\b",
        r"\bendpoints?\b",
        r"\blayered\b",
        r"\bhexagonal\b",
    ]),
    ("lesson", [
        r"\blearned\b",
        r"\bmistake\b",
        r"\bfailure\b",
        r"\binsight\b",
        r"\bnever\b",
        r"\bavoid\b",
        r"\bcritical\b",
        r"\bwarning\b",
        r"\bnot recommended\b",
    ]),
]


def classify_memory(content: str) -> str:
    """
    Classify memory content into one of the MEMORY_TYPES.
    Uses pattern matching to determine the most likely type.
    """
    content_lower = content.lower()

    scores = {}
    for memory_type, patterns in CLASSIFICATION_PATTERNS:
        score = 0
        for pattern in patterns:
            if re.search(pattern, content_lower):
                score += 1
        if score > 0:
            scores[memory_type] = score

    if not scores:
        return "lesson"  # Default fallback

    return max(scores, key=scores.get)


def extract_title(content: str, max_length: int = 100) -> str:
    """
    Extract a title/summary from memory content.
    Uses first meaningful line or first sentence.
    """
    # Clean up markdown
    content = content.strip()
    content = re.sub(r'^#+\s*', '', content, flags=re.MULTILINE)  # Remove headers
    content = re.sub(r'\[\[([^\]]+)\]\]', r'\1', content)  # Remove Obsidian links

    # Take first line if non-empty
    lines = [l.strip() for l in content.split('\n') if l.strip()]
    if lines:
        first_line = lines[0]
        if len(first_line) <= max_length:
            return first_line
        return first_line[:max_length - 3] + "..."

    # Fallback: first sentence
    sentences = re.split(r'[.!?]+', content)
    if sentences:
        first_sentence = sentences[0].strip()
        if len(first_sentence) <= max_length:
            return first_sentence
        return first_sentence[:max_length - 3] + "..."

    return "Untitled memory"


def extract_tags(content: str) -> list[str]:
    """
    Extract keywords/tags from content.
    Returns list of meaningful terms.
    """
    # Remove common stop words
    stop_words = {
        'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for',
        'of', 'with', 'by', 'from', 'is', 'are', 'was', 'were', 'be', 'been',
        'being', 'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would',
        'could', 'should', 'may', 'might', 'must', 'shall', 'can', 'this',
        'that', 'these', 'those', 'i', 'we', 'you', 'he', 'she', 'it', 'they',
        'what', 'which', 'who', 'whom', 'when', 'where', 'why', 'how',
    }

    # Extract words
    words = re.findall(r'\b[a-zA-Z][a-zA-Z0-9_-]{2,}\b', content.lower())
    words = [w for w in words if w not in stop_words and len(w) > 3]

    # Count frequency
    freq = {}
    for word in words:
        freq[word] = freq.get(word, 0) + 1

    # Get top tags
    sorted_words = sorted(freq.items(), key=lambda x: x[1], reverse=True)
    return [word for word, _ in sorted_words[:10]]


def truncate_content(content: str, max_length: int = MAX_MEMORY_CONTENT_LENGTH) -> str:
    """Truncate content to maximum length."""
    if len(content) <= max_length:
        return content
    return content[:max_length - 3] + "..."


def parse_frontmatter(content: str) -> tuple[dict, str]:
    """
    Parse YAML frontmatter from markdown content.

    Returns (metadata_dict, remaining_content).
    """
    frontmatter = {}
    remaining = content

    if content.startswith('---'):
        parts = content.split('---', 2)
        if len(parts) >= 3:
            fm_text = parts[1]
            remaining = parts[2]

            for line in fm_text.strip().split('\n'):
                if ':' in line:
                    key, value = line.split(':', 1)
                    key = key.strip()
                    value = value.strip().strip('"\'')
                    frontmatter[key] = value

    return frontmatter, remaining.strip()


def extract_memory_metadata(
    content: str,
    source_file: str = "",
    session_id: str = "",
) -> dict:
    """
    Extract all metadata from a memory for storage.

    Returns dict with: memory_type, title, content, tags, source_file, session_id, created_at
    """
    # Parse frontmatter if present
    frontmatter, body = parse_frontmatter(content)

    # Classify
    memory_type = frontmatter.get('type') or frontmatter.get('memory_type') or classify_memory(body)

    # Title from frontmatter or extracted
    title = frontmatter.get('name') or frontmatter.get('title') or extract_title(body)

    # Truncate content
    truncated = truncate_content(body)

    # Extract tags
    tags = extract_tags(truncated)

    # Created at from frontmatter or now
    created_at = frontmatter.get('created_at') or datetime.utcnow().isoformat()

    return {
        "memory_type": memory_type,
        "title": title,
        "content": truncated,
        "tags": tags,
        "source_file": source_file,
        "session_id": session_id,
        "created_at": created_at,
    }
