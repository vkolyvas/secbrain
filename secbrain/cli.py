"""CLI entry point for secbrain."""
import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

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

    # Install hooks command
    subparsers.add_parser("install-hooks", help="Install pre-push hook globally for all future clones")

    # Install MCP command
    mcp_install_parser = subparsers.add_parser("install-mcp", help="Install secbrain MCP server globally or per-project")
    mcp_install_parser.add_argument("--global", dest="global_mcp", action="store_true", help="Install globally (default)")
    mcp_install_parser.add_argument("--project", dest="project_path", type=str, help="Install in project directory")

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
    elif args.command == "install-hooks":
        hook_src = Path(__file__).parent.parent / ".git" / "hooks" / "pre-push"
        template_dir = Path.home() / ".git" / "template" / "hooks"

        if not hook_src.exists():
            print("[secbrain] error: pre-push hook not found in repo")
            return 1

        template_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(hook_src, template_dir / "pre-push")
        os.chmod(template_dir / "pre-push", 0o755)
        print(f"[secbrain] pre-push hook installed to {template_dir}")

        result = subprocess.run(
            ["git", "config", "--global", "init.templateDir"],
            capture_output=True, text=True
        )
        if not result.stdout.strip():
            subprocess.run(
                ["git", "config", "--global", "init.templateDir", str(template_dir.parent)],
                check=True
            )
            print("[secbrain] git global template dir configured")
        else:
            print(f"[secbrain] git template already set to: {result.stdout.strip()}")

        print("[secbrain] Done. New clones will have the hook. Existing repos: copy manually.")

    elif args.command == "install-mcp":
        import json
        secbrain_config = {
            "secbrain": {
                "command": "secbrain",
                "args": ["mcp"]
            }
        }

        if args.project_path:
            # Project-level .mcp.json
            mcp_path = Path(args.project_path) / ".mcp.json"
            if mcp_path.exists():
                with open(mcp_path) as f:
                    existing = json.load(f)
                existing.setdefault("mcpServers", {}).update(secbrain_config)
            else:
                existing = {"mcpServers": secbrain_config}
            with open(mcp_path, "w") as f:
                json.dump(existing, f, indent=2)
            print(f"[secbrain] MCP installed to {mcp_path}")

            # Also create .secbrain dir for hook deduplication
            secbrain_dir = Path(args.project_path) / ".secbrain"
            secbrain_dir.mkdir(exist_ok=True)
            print(f"[secbrain] .secbrain dir ready at {secbrain_dir}")
        else:
            # Global .mcp.json
            mcp_path = Path.home() / ".claude" / ".mcp.json"
            mcp_path.parent.mkdir(parents=True, exist_ok=True)
            if mcp_path.exists():
                with open(mcp_path) as f:
                    existing = json.load(f)
                existing.setdefault("mcpServers", {}).update(secbrain_config)
            else:
                existing = {"mcpServers": secbrain_config}
            with open(mcp_path, "w") as f:
                json.dump(existing, f, indent=2)
            print(f"[secbrain] MCP installed globally to {mcp_path}")

        print("[secbrain] Restart Claude Code for changes to take effect.")


if __name__ == "__main__":
    main()
