"""
MCP server for secbrain memory retrieval.
Supports both stdio and HTTP/SSE transport.

Architecture: stateless router + explicit project context model + identity registry.
No global state, no hardcoded paths, no Python-level store caching.
Each request carries project_id. Store is resolved per-request via registry.
"""
import argparse
import asyncio
import os
import sys
from pathlib import Path
from typing import Optional

from pydantic import BaseModel

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

from secbrain.config import DEFAULT_TOP_K
from secbrain.mcp.registry import ProjectRegistry, get_registry


# ────────────────────────────────────────────────────────────────
# Project Context (explicit contract)
# ────────────────────────────────────────────────────────────────

class ProjectContext(BaseModel):
    """Every request MUST carry explicit project context."""
    project_id: str

    def __init__(self, **data):
        # Auto-detect project_id if "auto" or empty
        if not data.get("project_id") or data.get("project_id") == "auto":
            resolver = ProjectResolver()
            detected = resolver.detect_project_id()
            if detected:
                data["project_id"] = detected
        super().__init__(**data)


# ────────────────────────────────────────────────────────────────
# Project Resolver (uses registry for decoupled identity)
# ────────────────────────────────────────────────────────────────

class ProjectResolver:
    """
    Resolves project_id to filesystem path via registry.
    Registry is sole source of truth — no fallback.
    Unregistered project_ids fail explicitly.

    Supports auto-detection from Claude Code working directory.
    """

    BASE_DIR = Path.home() / ".claude" / "projects"

    # Claude Code sets CLAUDE_PROJECT_ROOT or PROJECT_ROOT env vars
    CANDIDATE_ENV_VARS = ["CLAUDE_PROJECT_ROOT", "PROJECT_ROOT", "CLAUDE_DIR"]

    def __init__(self):
        self.registry: ProjectRegistry = get_registry()

    def resolve(self, ctx: ProjectContext) -> Optional[Path]:
        """
        Resolve project_id to storage path.
        READ ONLY — never mutates registry state.

        Returns Path if registered, None if not registered.
        Callers must handle None explicitly.
        """
        return self.registry.resolve(ctx.project_id)

    def detect_project_id(self) -> str:
        """
        Infer project_id from Claude Code working directory.
        Returns the basename of the detected project root.
        """
        for env_var in self.CANDIDATE_ENV_VARS:
            val = os.environ.get(env_var)
            if val:
                return Path(val).name

        # Fallback: use cwd if inside .claude/projects
        try:
            cwd = Path.cwd()
            projects_base = self.BASE_DIR.resolve()
            if projects_base in cwd.parents or projects_base == cwd:
                return cwd.name
        except Exception:
            pass

        return ""


# ────────────────────────────────────────────────────────────────
# Store Factory (pure factory - no Python-level caching)
# ────────────────────────────────────────────────────────────────

class StoreFactory:
    """
    Creates ChromaStore instances per request.
    No Python-level caching - Chroma handles internal persistence.
    """

    def create(self, project_path: Path):
        from secbrain.storage.chroma_store import ChromaStore
        from secbrain.config import COLLECTION_NAME

        return ChromaStore(
            path=project_path / "chroma",
            collection_name=COLLECTION_NAME,
        )


# ────────────────────────────────────────────────────────────────
# MCP Router (stateless resolver)
# ────────────────────────────────────────────────────────────────

class MCPRouter:
    """
    Routes MCP requests to the correct project-scoped store.
    Stateless: no cache, no registry, no shared state.
    """

    def __init__(self):
        self.resolver = ProjectResolver()
        self.factory = StoreFactory()

    def resolve_store(self, ctx: ProjectContext):
        """
        Resolve project_id to store. Returns None if not registered.
        READ ONLY — no state mutation.
        """
        project_path = self.resolver.resolve(ctx)
        if project_path is None:
            return None
        return self.factory.create(project_path)


# ────────────────────────────────────────────────────────────────
# Server instance (stateless)
# ────────────────────────────────────────────────────────────────

server = Server("secbrain-memory")
router = MCPRouter()


# ────────────────────────────────────────────────────────────────
# Tool definitions (all require project_id)
# ────────────────────────────────────────────────────────────────

@server.list_tools()
async def list_tools() -> list[Tool]:
    """List available MCP tools."""
    return [
        Tool(
            name="health_check",
            description="Check system status. Returns MCP protocol status and index availability.",
            inputSchema={
                "type": "object",
                "properties": {
                    "project_id": {
                        "type": "string",
                        "description": "Project identifier",
                    },
                },
                "required": ["project_id"],
            },
        ),
        Tool(
            name="query_memory",
            description="Query memories by semantic similarity. Returns top-k most relevant memories ranked by embedding distance.",
            inputSchema={
                "type": "object",
                "properties": {
                    "project_id": {
                        "type": "string",
                        "description": "Project identifier",
                    },
                    "query": {
                        "type": "string",
                        "description": "Natural language query to search memories",
                    },
                    "top_k": {
                        "type": "integer",
                        "description": f"Number of memories to return (default: {DEFAULT_TOP_K})",
                        "default": DEFAULT_TOP_K,
                    },
                    "memory_type": {
                        "type": "string",
                        "enum": ["decision", "pattern", "architecture", "lesson"],
                        "description": "Filter by memory type",
                    },
                },
                "required": ["project_id", "query"],
            },
        ),
        Tool(
            name="inject_context",
            description="Generate a formatted context block for prompt injection. Combines relevant memories with session context.",
            inputSchema={
                "type": "object",
                "properties": {
                    "project_id": {
                        "type": "string",
                        "description": "Project identifier",
                    },
                    "query": {
                        "type": "string",
                        "description": "Topic to search for",
                    },
                    "session_context": {
                        "type": "string",
                        "description": "Current session/project context",
                    },
                    "top_k": {
                        "type": "integer",
                        "description": "Number of memories to include (default: 3)",
                        "default": 3,
                    },
                },
                "required": ["project_id", "query", "session_context"],
            },
        ),
        Tool(
            name="get_memories_by_type",
            description="Retrieve memories filtered by type (decision, pattern, architecture, lesson).",
            inputSchema={
                "type": "object",
                "properties": {
                    "project_id": {
                        "type": "string",
                        "description": "Project identifier",
                    },
                    "memory_type": {
                        "type": "string",
                        "enum": ["decision", "pattern", "architecture", "lesson"],
                        "description": "Memory type to filter by",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum memories to return (default: 10)",
                        "default": 10,
                    },
                },
                "required": ["project_id", "memory_type"],
            },
        ),
        Tool(
            name="get_memory_stats",
            description="Get collection statistics: total memories and breakdown by type.",
            inputSchema={
                "type": "object",
                "properties": {
                    "project_id": {
                        "type": "string",
                        "description": "Project identifier",
                    },
                },
                "required": ["project_id"],
            },
        ),
        Tool(
            name="add_memory",
            description="Manually add a new memory to the store.",
            inputSchema={
                "type": "object",
                "properties": {
                    "project_id": {
                        "type": "string",
                        "description": "Project identifier",
                    },
                    "content": {
                        "type": "string",
                        "description": "Full memory content/text",
                    },
                    "memory_type": {
                        "type": "string",
                        "enum": ["decision", "pattern", "architecture", "lesson"],
                        "description": "Type of memory",
                    },
                    "title": {
                        "type": "string",
                        "description": "Human-readable title/summary",
                    },
                    "tags": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Optional tags for this memory",
                    },
                    "source_project": {
                        "type": "string",
                        "description": "Project name (default: from project_id)",
                    },
                },
                "required": ["project_id", "content", "memory_type", "title"],
            },
        ),
        Tool(
            name="list_projects",
            description="List all registered projects and their storage paths.",
            inputSchema={
                "type": "object",
                "properties": {},
            },
        ),
        Tool(
            name="register_project",
            description="Register an explicit storage path for a project_id. Use after migrating or aliasing a project.",
            inputSchema={
                "type": "object",
                "properties": {
                    "project_id": {
                        "type": "string",
                        "description": "Project identifier",
                    },
                    "storage_path": {
                        "type": "string",
                        "description": "Absolute path to project storage",
                    },
                },
                "required": ["project_id", "storage_path"],
            },
        ),
        Tool(
            name="unregister_project",
            description="Remove a project registration. Storage path reverts to default BASE_DIR / project_id.",
            inputSchema={
                "type": "object",
                "properties": {
                    "project_id": {
                        "type": "string",
                        "description": "Project identifier",
                    },
                },
                "required": ["project_id"],
            },
        ),
        Tool(
            name="validate_registry",
            description="Check registry consistency. Detects orphaned stores, dangling registrations, and alias collisions.",
            inputSchema={
                "type": "object",
                "properties": {
                    "project_id": {
                        "type": "string",
                        "description": "Optional project_id to validate specific entry",
                    },
                },
            },
        ),
        Tool(
            name="bootstrap_project",
            description="Initialize a project if not already registered. Creates registry entry with default storage path. Does not auto-detect — explicit initialization only.",
            inputSchema={
                "type": "object",
                "properties": {
                    "project_id": {
                        "type": "string",
                        "description": "Project identifier to bootstrap",
                    },
                },
                "required": ["project_id"],
            },
        ),
        Tool(
            name="delete_memory",
            description="Delete a memory by ID. Use query_memory first to find the memory ID.",
            inputSchema={
                "type": "object",
                "properties": {
                    "project_id": {
                        "type": "string",
                        "description": "Project identifier",
                    },
                    "memory_id": {
                        "type": "string",
                        "description": "ID of the memory to delete",
                    },
                },
                "required": ["project_id", "memory_id"],
            },
        ),
    ]


# ────────────────────────────────────────────────────────────────
# Tool execution (fully stateless per request)
# ────────────────────────────────────────────────────────────────

@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    """Handle tool calls - stateless routing, fresh store per request."""

    ctx = ProjectContext(project_id=arguments["project_id"])

    store = router.resolve_store(ctx)

    # ── Registry-only tools (no store needed) ────────────────

    if name == "list_projects":
        registry = get_registry()
        projects = registry.list_projects()
        warnings = registry.get_warnings()
        if not projects:
            return [TextContent(type="text", text="No registered projects.")]
        output = ["## Registered Projects"]
        for pid, info in projects.items():
            policy = info["storage_policy"]
            emoji = "⚠️" if policy == "ephemeral" else "✓"
            output.append(f"- **{pid}** → `{info['path']}` {emoji} {policy}")
        if warnings:
            output.append("\n### Warnings")
            for w in warnings:
                output.append(f"- {w}")
        return [TextContent(type="text", text="\n".join(output))]

    if name == "register_project":
        registry = get_registry()
        registry.register(
            arguments["project_id"],
            Path(arguments["storage_path"])
        )
        return [TextContent(type="text", text=f"Registered {arguments['project_id']} → {arguments['storage_path']}")]

    if name == "unregister_project":
        registry = get_registry()
        ok = registry.unregister(arguments["project_id"])
        if ok:
            return [TextContent(type="text", text=f"Unregistered {arguments['project_id']}. Reverts to default path.")]
        return [TextContent(type="text", text=f"Project {arguments['project_id']} was not explicitly registered.")]

    if name == "bootstrap_project":
        registry = get_registry()
        project_id = arguments["project_id"]
        if registry.is_registered(project_id):
            path = registry.resolve(project_id)
            policy = registry.get_storage_policy(project_id)
            return [TextContent(type="text", text=f"Project {project_id} already registered → {path} ({policy})")]
        # Register with default path if not present
        base_dir = Path.home() / ".claude" / "projects" / project_id
        registry.register(project_id, base_dir)
        policy = registry.get_storage_policy(project_id)
        return [TextContent(type="text", text=f"Bootstrapped {project_id} → {base_dir} ({policy})")]

    if name == "validate_registry":
        from secbrain.mcp.registry_validator import RegistryValidator
        validator = RegistryValidator()
        valid, msg = validator.validate()
        if valid:
            return [TextContent(type="text", text="Registry: CLEAN — all entries consistent.")]
        return [TextContent(type="text", text=f"Registry: {msg}")]

    # ── Store-dependent tools ────────────────────────────────

    # Handle unregistered project_id gracefully
    store = router.resolve_store(ctx)
    if store is None:
        return [TextContent(
            type="text",
            text=f"Project {ctx.project_id} is not registered. Use bootstrap_project() or register_project() first."
        )]

    if name == "health_check":
        stats = store.get_stats()
        return [TextContent(
            type="text",
            text=f"OK project={ctx.project_id}, index={stats.get('total_memories', 0)}"
        )]

    if name == "query_memory":
        query = arguments["query"]
        top_k = arguments.get("top_k", DEFAULT_TOP_K)
        memory_type = arguments.get("memory_type")

        results = store.query(
            query_text=query,
            top_k=top_k,
            memory_type=memory_type,
        )

        if not results:
            return [TextContent(type="text", text="No memories found matching your query.")]

        output = []
        for i, mem in enumerate(results, 1):
            meta = mem["metadata"]
            output.append(
                f"{i}. [{meta['memory_type']}] {meta['title']}\n"
                f"   Score: {mem['score']:.3f}\n"
                f"   Source: {meta['source_file']}\n"
                f"   {mem['content'][:200]}..."
            )
        return [TextContent(type="text", text="\n\n".join(output))]

    elif name == "inject_context":
        query = arguments["query"]
        session_context = arguments["session_context"]
        top_k = arguments.get("top_k", 3)

        results = store.query(query_text=query, top_k=top_k)

        if not results:
            return [TextContent(type="text", text=f"Context ({session_context}): No relevant memories found.")]

        context_parts = [f"## Context: {session_context}\n"]
        context_parts.append("### Relevant memories:\n")

        for i, mem in enumerate(results, 1):
            meta = mem["metadata"]
            context_parts.append(
                f"**{i}. {meta['title']}** ({meta['memory_type']})\n"
                f"{mem['content'][:300]}..."
            )

        return [TextContent(type="text", text="\n\n".join(context_parts))]

    elif name == "get_memories_by_type":
        memory_type = arguments["memory_type"]
        limit = arguments.get("limit", 10)

        results = store.get_by_type(memory_type=memory_type, limit=limit)

        if not results:
            return [TextContent(type="text", text=f"No {memory_type} memories found.")]

        output = [f"## {memory_type.title()} memories\n"]
        for i, mem in enumerate(results, 1):
            meta = mem["metadata"]
            output.append(
                f"{i}. {meta['title']}\n"
                f"   {mem['content'][:150]}..."
            )
        return [TextContent(type="text", text="\n\n".join(output))]

    elif name == "get_memory_stats":
        stats = store.get_stats()

        output = [
            f"## {ctx.project_id} Memory Stats",
            f"**Total memories:** {stats['total_memories']}",
            "\n**By type:**",
        ]
        for mtype, count in stats["by_type"].items():
            output.append(f"- {mtype}: {count}")

        return [TextContent(type="text", text="\n\n".join(output))]

    elif name == "add_memory":
        content = arguments["content"]
        memory_type = arguments["memory_type"]
        title = arguments["title"]
        tags = arguments.get("tags", [])
        source_project = arguments.get("source_project", ctx.project_id)

        memory_id = store.add_memory(
            content=content,
            memory_type=memory_type,
            title=title,
            tags=tags,
            source_project=source_project,
        )

        return [TextContent(type="text", text=f"Memory added successfully. ID: {memory_id}")]

    elif name == "delete_memory":
        memory_id = arguments["memory_id"]
        ok = store.delete(memory_id)
        if ok:
            return [TextContent(type="text", text=f"Memory {memory_id} deleted.")]
        return [TextContent(type="text", text=f"Failed to delete memory {memory_id}.")]

    return [TextContent(type="text", text=f"Unknown tool: {name}")]


# ────────────────────────────────────────────────────────────────
# Server runners
# ────────────────────────────────────────────────────────────────

async def run_stdio():
    """Run the MCP server over stdio."""
    print("[secbrain] starting stateless MCP server", file=sys.stderr)

    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options(),
        )


async def run_http(host: str = "0.0.0.0", port: int = 8765):
    """Run the MCP server over HTTP/SSE."""
    from secbrain.mcp.http_server import StreamableHTTPSessionManager
    import uvicorn

    session_manager = StreamableHTTPSessionManager(
        server,
        json_response=False,
    )

    async def handle(scope, receive, send) -> None:
        await session_manager.handle_request(scope, receive, send)

    async with session_manager.run():
        print(f"[secbrain] MCP HTTP server running on http://{host}:{port}", file=sys.stderr)
        config = uvicorn.Config(app=handle, host=host, port=port, log_level="error", lifespan="off")
        await uvicorn.Server(config).serve()


def main():
    """Run the MCP server."""
    parser = argparse.ArgumentParser(description="secbrain MCP server")
    parser.add_argument(
        "--transport",
        choices=["stdio", "http"],
        default="stdio",
        help="Transport to use (default: stdio)",
    )
    parser.add_argument(
        "--host",
        default="0.0.0.0",
        help="Host to bind to for HTTP transport (default: 0.0.0.0)",
    )
    parser.add_argument(
        "--port", type=int, default=8765, help="Port to bind to for HTTP transport (default: 8765)"
    )
    args = parser.parse_args()

    if args.transport == "http":
        asyncio.run(run_http(args.host, args.port))
    else:
        asyncio.run(run_stdio())


if __name__ == "__main__":
    main()
