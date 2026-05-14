# secbrain

RAG cognitive memory for AI agents. Captures and retrieves project knowledge using ChromaDB and Ollama.

## MCP Server

```bash
secbrain mcp          # Start MCP server (stdio transport)
secbrain mcp --http   # Start MCP server (HTTP/SSE transport)
```

MCP tools: `health_check`, `query_memory`, `inject_context`, `get_memories_by_type`, `get_memory_stats`, `add_memory`, `delete_memory`, `list_projects`, `register_project`, `bootstrap_project`, `validate_registry`.

## Pre-Push Hook

Automatically captures git push metadata to secbrain's vector memory store.

### Setup (global, for all future clones)

```bash
# One-time: configure git global template
git config --global init.templateDir ~/.git/template

# Copy hook to template (one-time, or after updating hook)
mkdir -p ~/.git/template/hooks
cp .git/hooks/pre-push ~/.git/template/hooks/pre-push
chmod +x ~/.git/template/hooks/pre-push
```

New clones will automatically get this hook. For existing repos, manually copy the hook:
```bash
cp .git/hooks/pre-push /path/to/your/project/.git/hooks/pre-push
chmod +x /path/to/your/project/.git/hooks/pre-push
```

### How it works

On every `git push`, the hook:
1. Reads commit SHAs from stdin (pre-push provides refs)
2. Deduplicates against `.secbrain/captured_shAs.txt`
3. Extracts commit messages and metadata
4. Stores to both `.secbrain/git_push_memories.jsonl` (local) and secbrain vector DB
5. Prints captured memories after push completes

### Verification

After pushing, you'll see output like:
```
[secbrain] pre-push hook fired
[secbrain] commits to capture: 1
[secbrain] captured: feat: your commit message
[secbrain] stored in vector DB: feat: your commit message...
[secbrain] memories saved:
  - feat: your commit message
```

## Project Structure

- `secbrain/mcp/` - MCP server implementation
- `secbrain/storage/` - ChromaDB storage adapter
- `secbrain/ingestion/` - Memory ingestion logic
- `secbrain/embeddings/` - Ollama embedding integration