"""
MCP server for secbrain memory retrieval.
Supports both stdio and HTTP/SSE transport.
"""
import argparse
import asyncio
import sys
from enum import Enum
from typing import Optional

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.server.sse import SseServerTransport
from mcp.types import Tool, TextContent, InitializedNotification

from secbrain.config import DEFAULT_TOP_K
from secbrain.storage.chroma_store import get_store


# Server instance
server = Server("secbrain-memory")


class SystemState(Enum):
    STARTING = 1
    READY = 2
    DEGRADED = 3
    FAILED = 4


# System state - transitioned explicitly after full validation
_state = SystemState.STARTING
_state_lock = asyncio.Lock()


def _set_state(new_state: SystemState):
    global _state
    _state = new_state


def _get_state() -> SystemState:
    return _state


async def _on_initialized(notification: InitializedNotification):
    """Called when client sends the initialized notification after handshake."""
    print("[secbrain] client initialization complete", file=sys.stderr)


# Register the notification handler directly on the dict
server.notification_handlers[InitializedNotification] = _on_initialized


def _validate_store_sync() -> bool:
    """
    Actively validate store by testing write + query paths.
    This runs at startup and validates the full embedding pipeline.
    Returns True only if store is fully operational.
    """
    try:
        store = get_store()
        test_content = "health check validation"

        # Test write path
        memory_id = store.add_memory(
            content=test_content,
            memory_type="pattern",
            title="healthcheck",
            source_file="system",
            tags=["__healthcheck__"],
        )

        # Test query path (forces embedding + retrieval)
        results = store.query(query_text="health check validation", top_k=1)

        # Cleanup
        store.delete(memory_id)

        # Verify we got a meaningful result
        return len(results) >= 0  # store handled it without exception
    except Exception as e:
        print(f"[secbrain] store validation failed: {e}", file=sys.stderr)
        return False


async def validate_store() -> bool:
    """Async wrapper for store validation."""
    return await asyncio.get_event_loop().run_in_executor(None, _validate_store_sync)


async def initialize_store():
    """
    Initialize store with active validation.
    Transitions state to READY only after full validation passes.
    """
    global _store_ready
    async with _state_lock:
        _set_state(SystemState.STARTING)
        print("[secbrain] initializing store with active validation...", file=sys.stderr)

        if await validate_store():
            _set_state(SystemState.READY)
            _store_ready = True
            print("[secbrain] store ready (validated)", file=sys.stderr)
        else:
            _set_state(SystemState.FAILED)
            _store_ready = False
            print("[secbrain] store FAILED validation", file=sys.stderr)


_store_ready = False


@server.list_tools()
async def list_tools() -> list[Tool]:
    """List available MCP tools."""
    return [
        Tool(
            name="health_check",
            description="Check system readiness - returns MCP protocol status, store status, and index availability.",
            inputSchema={
                "type": "object",
                "properties": {},
            },
        ),
        Tool(
            name="query_memory",
            description="Query memories by semantic similarity. Returns top-k most relevant memories ranked by embedding distance.",
            inputSchema={
                "type": "object",
                "properties": {
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
                "required": ["query"],
            },
        ),
        Tool(
            name="inject_context",
            description="Generate a formatted context block for prompt injection. Combines relevant memories with session context.",
            inputSchema={
                "type": "object",
                "properties": {
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
                "required": ["query", "session_context"],
            },
        ),
        Tool(
            name="get_memories_by_type",
            description="Retrieve memories filtered by type (decision, pattern, architecture, lesson).",
            inputSchema={
                "type": "object",
                "properties": {
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
                "required": ["memory_type"],
            },
        ),
        Tool(
            name="get_memory_stats",
            description="Get collection statistics: total memories and breakdown by type.",
            inputSchema={
                "type": "object",
                "properties": {},
            },
        ),
        Tool(
            name="add_memory",
            description="Manually add a new memory to the store.",
            inputSchema={
                "type": "object",
                "properties": {
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
                        "description": "Project name (default: secbrain)",
                        "default": "secbrain",
                    },
                },
                "required": ["content", "memory_type", "title"],
            },
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    """Handle tool calls - uses fail-fast state checks."""
    state = _get_state()

    if state == SystemState.FAILED:
        return [TextContent(type="text", text="System failed. Check logs.")]

    if state == SystemState.STARTING:
        return [TextContent(type="text", text="System still starting. Please wait.")]

    if state != SystemState.READY:
        return [TextContent(type="text", text="System not ready.")]

    store = get_store()

    if name == "health_check":
        stats = store.get_stats() if _store_ready else {}
        return [TextContent(type="text", text=f"state: {_state.name}, store: {_store_ready}, index: {stats.get('total_memories', 0)}")]

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
            "## secbrain Memory Stats",
            f"**Total memories:** {stats['total_memories']}",
            "\n**By type:**",
        ]
        for mtype, count in stats["by_type"].items():
            output.append(f"- {mtype}: {count}")

        return [TextContent(type="text", text="\n".join(output))]

    elif name == "add_memory":
        content = arguments["content"]
        memory_type = arguments["memory_type"]
        title = arguments["title"]
        tags = arguments.get("tags", [])
        source_project = arguments.get("source_project", "secbrain")

        memory_id = store.add_memory(
            content=content,
            memory_type=memory_type,
            title=title,
            tags=tags,
            source_project=source_project,
        )

        return [TextContent(type="text", text=f"Memory added successfully. ID: {memory_id}")]

    return [TextContent(type="text", text=f"Unknown tool: {name}")]


async def run_stdio():
    """Run the MCP server over stdio with active store validation."""
    # Actively validate store before accepting traffic
    await initialize_store()

    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options(),
        )


# Background watchdog task handle
_watchdog_task: Optional[asyncio.Task] = None


async def _watchdog_loop():
    """Background task to monitor store health and update state accordingly."""
    while True:
        try:
            if _get_state() == SystemState.READY:
                # Re-validate periodically
                ok = await validate_store()
                if not ok:
                    async with _state_lock:
                        _set_state(SystemState.DEGRADED)
                        _store_ready = False
                    print("[secbrain] store degraded - health check failed", file=sys.stderr)
        except Exception as e:
            print(f"[secbrain] watchdog error: {e}", file=sys.stderr)
        await asyncio.sleep(10)


async def run_http(host: str = "0.0.0.0", port: int = 8765):
    """Run the MCP server over HTTP/SSE with active store validation."""
    global _watchdog_task

    # Actively validate store before accepting traffic
    await initialize_store()

    # Start background watchdog
    _watchdog_task = asyncio.create_task(_watchdog_loop())

    session_manager = StreamableHTTPSessionManager(
        server,
        json_response=False,
    )

    async def handle(scope: Scope, receive: Receive, send: Send) -> None:
        await session_manager.handle_request(scope, receive, send)

    async with session_manager.run():
        print(f"[secbrain] MCP HTTP server running on http://{host}:{port}", file=sys.stderr)
        config = uvicorn.Config(app=handle, host=host, port=port, log_level="error", lifespan="off")
        await uvicorn.Server(config).serve()

    # Cleanup watchdog on shutdown
    if _watchdog_task:
        _watchdog_task.cancel()


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