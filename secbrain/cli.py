"""CLI entry point for secbrain."""
import argparse
import asyncio
import sys

from secbrain.mcp import server as mcp_server


def main():
    parser = argparse.ArgumentParser(description="secbrain - RAG cognitive memory for AI agents")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # MCP command
    mcp_parser = subparsers.add_parser("mcp", help="Start the MCP server")
    mcp_parser.add_argument(
        "--transport",
        choices=["stdio", "http"],
        default="stdio",
        help="Transport to use (default: stdio)",
    )
    mcp_parser.add_argument(
        "--host", default="0.0.0.0", help="Host for HTTP transport (default: 0.0.0.0)"
    )
    mcp_parser.add_argument(
        "--port", type=int, default=8765, help="Port for HTTP transport (default: 8765)"
    )

    # Stats command
    subparsers.add_parser("stats", help="Show memory statistics")

    # List command
    subparsers.add_parser("list", help="List recent memories")

    args = parser.parse_args()

    if args.command == "mcp":
        sys.argv = ["mcp", "--transport", args.transport, "--host", args.host, "--port", str(args.port)]
        mcp_server.main()
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
