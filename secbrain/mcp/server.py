"""
MCP server for secbrain memory retrieval.
Supports both stdio and HTTP/SSE transport.
"""
import argparse
import asyncio
import sys
from typing import Optional

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.server.sse import SseServerTransport
from mcp.types import Tool, TextContent, InitializedNotification

from secbrain.config import DEFAULT_TOP_K
from secbrain.storage.chroma_store import get_store


# Server instance
server = Server("secbrain-memory")

# Readiness gate - blocks tool execution until MCP protocol initialization completes
_initialization_complete = asyncio.Event()


def _set_ready():
    _initialization_complete.set()


async def _on_initialized(notification: InitializedNotification):
    """Called when client sends the initialized notification after handshake."""
    print("[secbrain] client initialization complete", file=sys.stderr)
    _set_ready()


# Register the notification handler directly on the dict
server.notification_handlers[InitializedNotification] = _on_initialized


@server.list_tools()
async def list_tools() -> list[Tool]:
    """List available MCP tools."""
    return [
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
    """Handle tool calls - blocks until initialization is complete."""
    # Wait for MCP protocol initialization to complete before accepting tool calls
    await _initialization_complete.wait()

    store = get_store()

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
    """Run the MCP server over stdio with proper initialization synchronization."""
    # Pre-initialize the store to ensure Chroma and Ollama are ready
    _ = get_store()
    print("[secbrain] chroma loaded, waiting for client initialization...", file=sys.stderr)

    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options(),
        )


async def run_http(host: str = "0.0.0.0", port: int = 8765):
    """Run the MCP server over HTTP/SSE."""
    import uvicorn
    from starlette.types import Scope, Receive, Send
    from mcp.server.streamable_http_manager import StreamableHTTPSessionManager

    session_manager = StreamableHTTPSessionManager(
        server,
        json_response=False,
    )

    async def handle(scope: Scope, receive: Receive, send: Send) -> None:
        await session_manager.handle_request(scope, receive, send)

    # Start session manager in background task
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