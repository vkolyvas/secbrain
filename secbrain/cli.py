"""CLI entry point for secbrain."""
import argparse
import asyncio
import sys

from secbrain.mcp.server import main as mcp_main


def main():
    parser = argparse.ArgumentParser(description="secbrain - RAG cognitive memory for AI agents")
    parser.add_argument("command", choices=["mcp", "stats", "list"], help="Command to run")
    args = parser.parse_args()

    if args.command == "mcp":
        asyncio.run(mcp_main())
    elif args.command == "stats":
        from secbrain.storage.chroma_store import get_store
        store = get_store()
        stats = store.get_stats()
        print(f"Total memories: {stats['total_memories']}")
        for mtype, count in stats["by_type"].items():
            print(f"  {mtype}: {count}")
    elif args.command == "list":
        from secbrain.storage.chroma_store import get_store
        store = get_store()
        for mtype in ["decision", "pattern", "architecture", "lesson"]:
            results = store.get_by_type(mtype, limit=5)
            if results:
                print(f"\n## {mtype.title()}s")
                for mem in results:
                    meta = mem["metadata"]
                    print(f"  - {meta['title']}")


if __name__ == "__main__":
    main()
