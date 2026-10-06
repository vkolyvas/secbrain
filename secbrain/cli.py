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

    # Import ChatGPT command
    import_chatgpt_parser = subparsers.add_parser("import-chatgpt", help="Import ChatGPT export into secbrain")
    import_chatgpt_parser.add_argument("file", type=str, help="Path to ChatGPT export JSON file")
    import_chatgpt_parser.add_argument("--project", dest="project_id", type=str, default="chatgpt", help="Target project ID (default: chatgpt)")
    import_chatgpt_parser.add_argument("--dry-run", action="store_true", help="Show what would be imported without storing")

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

    elif args.command == "import-chatgpt":
        from pathlib import Path
        from secbrain.ingestion.chatgpt_parser import ChatGPTParser
        from secbrain.mcp.registry import get_registry
        from secbrain.storage.chroma_store import ChromaStore
        from secbrain.config import COLLECTION_NAME

        export_path = Path(args.file)
        if not export_path.exists():
            print(f"[secbrain] Error: File not found: {export_path}")
            return 1

        project_id = args.project_id
        registry = get_registry()

        # Resolve or bootstrap project storage path
        project_path = registry.resolve(project_id)
        if project_path is None:
            # Auto-bootstrap: create project in managed storage
            project_path = Path.home() / ".claude" / "projects" / project_id
            registry.register(project_id, project_path)
            print(f"[secbrain] Auto-registered project: {project_id} -> {project_path}")

        print(f"[secbrain] Importing ChatGPT export from: {export_path}")
        print(f"[secbrain] Target project: {project_id} ({project_path})")

        # Parse the export
        parser = ChatGPTParser(export_path)
        conversations = parser.load_conversations(export_path)
        print(f"[secbrain] Found {len(conversations)} conversations")

        # Create project-scoped store
        chroma_path = project_path / "chroma"
        store = ChromaStore(path=chroma_path, collection_name=COLLECTION_NAME)

        total_memories = 0
        for conv in conversations:
            memories = parser.extract_memories_from_conversation(conv)
            if args.dry_run:
                for m in memories:
                    print(f"  [DRY-RUN] Would store: {m['title'][:60]}...")
            else:
                for m in memories:
                    store.add_memory(
                        content=m["content"],
                        memory_type=m["memory_type"],
                        title=m["title"],
                        source_file=m["source_file"],
                        source_project=project_id,
                        tags=m.get("tags", []),
                        session_id=m["session_id"],
                    )
                    total_memories += 1

        if args.dry_run:
            print(f"[secbrain] Dry run complete. Would have imported {total_memories} memories.")
        else:
            print(f"[secbrain] Successfully imported {total_memories} memories into {project_id}")


if __name__ == "__main__":
    main()
