#!/usr/bin/env python3
"""
Bulk ingestion CLI for secbrain memories.
Ingests from Obsidian vault and Claude session logs into Chroma.
"""
import argparse
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.config import SECBRAIN_PROJECT_DIR
from src.ingestion.obsidian_loader import ObsidianLoader
from src.ingestion.session_parser import SessionParser
from src.storage.chroma_store import get_store


def ingest_obsidian(project: str = "secbrain", verbose: bool = False):
    """Ingest memories from Obsidian vault."""
    loader = ObsidianLoader()
    memories = loader.load_memory_files(project)

    if not memories:
        print(f"No Obsidian memories found for project: {project}")
        return 0

    store = get_store()
    added = 0

    for mem in memories:
        try:
            store.add_memory(
                content=mem["content"],
                memory_type=mem["memory_type"],
                title=mem["title"],
                source_file=mem["source_file"],
                source_project=mem["source_project"],
                tags=mem["tags"],
            )
            added += 1
            if verbose:
                print(f"  + {mem['title'][:50]}...")
        except Exception as e:
            print(f"  ! Error adding {mem.get('title', 'unknown')}: {e}")

    return added


def ingest_sessions(limit: int = 10, verbose: bool = False):
    """Ingest memories from Claude session logs."""
    parser = SessionParser()
    sessions = parser.load_sessions(limit=limit)

    if not sessions:
        print("No sessions found")
        return 0

    store = get_store()
    total_added = 0

    for session in sessions:
        session_id = session["session_id"]
        memories = parser.extract_memories_from_session(session)

        if not memories:
            continue

        session_added = 0
        for mem in memories:
            try:
                store.add_memory(
                    content=mem["content"],
                    memory_type=mem["memory_type"],
                    title=mem["title"],
                    source_file=mem["source_file"],
                    source_project=mem["source_project"],
                    tags=mem["tags"],
                    session_id=session_id,
                )
                session_added += 1
            except Exception as e:
                if verbose:
                    print(f"  ! Error: {e}")

        total_added += session_added
        if verbose:
            print(f"  Session {session_id[:8]}...: {session_added} memories")

    return total_added


def show_stats():
    """Show current storage statistics."""
    store = get_store()
    stats = store.get_stats()

    print("## secbrain Memory Stats")
    print(f"**Total:** {stats['total_memories']} memories\n")
    print("**By type:**")
    for mtype, count in stats["by_type"].items():
        bar = "█" * min(count, 50)
        print(f"  {mtype:12}: {count:4} {bar}")


def main():
    parser = argparse.ArgumentParser(description="secbrain memory ingestion")
    parser.add_argument("--source", choices=["obsidian", "sessions", "all"], default="all",
                        help="Source to ingest from")
    parser.add_argument("--project", default="secbrain",
                        help="Project name for Obsidian ingestion")
    parser.add_argument("--session-limit", type=int, default=10,
                        help="Max sessions to process")
    parser.add_argument("--stats", action="store_true",
                        help="Show stats instead of ingesting")
    parser.add_argument("-v", "--verbose", action="store_true",
                        help="Verbose output")

    args = parser.parse_args()

    if args.stats:
        show_stats()
        return

    print("secbrain Memory Ingestion")
    print("=" * 40)

    total_added = 0

    if args.source in ("obsidian", "all"):
        print(f"\nIngesting Obsidian memories from: {args.project}")
        count = ingest_obsidian(args.project, args.verbose)
        print(f"  Added {count} memories")
        total_added += count

    if args.source in ("sessions", "all"):
        print(f"\nIngesting from Claude sessions (limit: {args.session_limit})")
        count = ingest_sessions(args.session_limit, args.verbose)
        print(f"  Added {count} memories")
        total_added += count

    print(f"\n{'=' * 40}")
    print(f"Total added: {total_added}")

    if total_added > 0:
        print("\nCurrent stats:")
        show_stats()


if __name__ == "__main__":
    main()
