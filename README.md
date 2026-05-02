---
<p align="center">
  <img src="assets/secbrain.png" style="width: 60%; height: auto;">
</p>

<div align="center" style="line-height: 1;">
  <a href="https://github.com/onchain3r/secbrain" target="_blank"><img alt="GitHub" src="https://img.shields.io/badge/GitHub-secbrain-14C290?logo=github"/></a>
  <a href="https://opensource.org/licenses/MIT" target="_blank"><img alt="License" src="https://img.shields.io/badge/License-MIT-4C72DB?logo=opensourceinitiative&logoColor=white"/></a>
  <a href="https://github.com/onchain3r/secbrain/stargazers" target="_blank"><img alt="Stars" src="https://img.shields.io/github/stars/onchain3r/secbrain?style=social"/></a>
  <a href="https://github.com/onchain3r/secbrain/network/members" target="_blank"><img alt="Forks" src="https://img.shields.io/github/forks/onchain3r/secbrain?style=social"/></a>
</div>

<div align="center">

 secbrain is a RAG-based cognitive memory system for AI agents — combining Chroma vector storage, Ollama embeddings, and MCP tool calling into a persistent, retrievable knowledge layer.

</div>

---

# secbrain: RAG-Powered Cognitive Memory for AI Agents

## News
- [2026-05] **secbrain v0.1.0** released with Chroma + Ollama integration, semantic memory retrieval, MCP server for Claude Code, and 30 demo memories ingested.
- [2026-04] Initial commit — secbrain architecture established with file-based memory and retrieval layer planning.

<div align="center">
<a href="https://www.star-history.com/#onchain3r/secbrain&Date">
 <picture>
   <source media="(prefers-color-scheme: dark)" srcset="https://api.star-history.com/svg?repos=onchain3r/secbrain&type=Date&theme=dark" />
   <source media="(prefers-color-scheme: light)" srcset="https://api.star-history.com/svg?repos=onchain3r/secbrain&type=Date" />
   <img alt="secbrain Star History" src="https://api.star-history.com/svg?repos=onchain3r/secbrain&type=Date" style="width: 80%; height: auto;" />
 </picture>
</a>
</div>

> secbrain provides long-term memory and semantic recall for AI coding agents. Store decisions, patterns, lessons, and architecture notes — then query them naturally when context is relevant.

<div align="center">

 🚀 [Overview](#secbrain-architecture) | ⚡ [Installation](#installation) | 📦 [Usage](#usage) | 🔧 [MCP Server](#mcp-server) | 🤝 [Contributing](#contributing) | 📄 [License](#license)

</div>

## secbrain Architecture

secbrain is built around a retrieval-augmented generation (RAG) pipeline that gives AI agents persistent, queryable memory.

<p align="center">
  <img src="assets/schema.png" style="width: 100%; height: auto;">
</p>

### Core Components

- **Chroma Vector Store** — Persistent embeddings storage with collection management for fast similarity search
- **Ollama Embeddings** — Local embedding generation via `nomic-embed-text` (or any Ollama-supported model)
- **MCP Server** — Model Context Protocol server enabling Claude Code to query and store memories natively
- **Memory Types** — Structured memory slots: `decision`, `pattern`, `architecture`, `lesson`
- **Retrieval Layer** — Semantic similarity search with configurable top-k and memory type filtering

### Memory Schema

Each memory entry contains:
- `title` — Human-readable summary
- `content` — Full memory text
- `memory_type` — One of: `decision`, `pattern`, `architecture`, `lesson`
- `tags` — Optional categorization tags
- `source_project` — Optional project context (defaults to `secbrain`)
- `embedding` — Generated automatically via Ollama

<p align="center">
  <img src="assets/memory-flow.png" width="80%" style="display: inline-block; margin: 0 2%;">
</p>

## Installation

### Prerequisites

- Python 3.10+
- [Ollama](https://ollama.ai/) installed and running
- Chroma (installed via pip)

### Clone and Install

```bash
git clone https://github.com/onchain3r/secbrain.git
cd secbrain
pip install -e .
```

### Start Ollama

```bash
ollama serve
```

Pull the embedding model (if not already present):
```bash
ollama pull nomic-embed-text
```

### Configuration

Copy `.env.example` to `.env` if you need to configure non-default settings:

```bash
cp .env.example .env
```

### Verify Setup

```bash
python -c "from secbrain import SecBrain; sb = SecBrain(); print('secbrain ready')"
```

## Usage

### Python API

```python
from secbrain import SecBrain

sb = SecBrain()

# Store a memory
sb.add_memory(
    title="Use Chroma for vector storage",
    content="Chroma provides fast, local embeddings storage with a clean API. Best choice for self-hosted RAG.",
    memory_type="decision",
    tags=["storage", "rag", "chroma"],
)

# Query memories
results = sb.query_memory("embedding storage options for RAG", top_k=5)
for r in results:
    print(f"[{r['memory_type']}] {r['title']} — distance: {r['distance']:.3f}")
```

### Memory Type Queries

```python
# Get all decisions
decisions = sb.get_memories_by_type("decision")

# Get memory statistics
stats = sb.get_memory_stats()
print(f"Total: {stats['total']} | Decisions: {stats['by_type'].get('decision', 0)}")
```

### Inject Context for Prompts

```python
context = sb.inject_context(
    query="How did we handle auth in past projects?",
    session_context="building a new webapp with JWT auth",
    top_k=3,
)
# Returns formatted string to inject into LLM prompts
```

### CLI

```bash
secbrain                 # Interactive query mode
secbrain add             # Add memory via CLI
secbrain stats           # Show memory collection stats
secbrain list            # List all memories
```

## MCP Server

The MCP server exposes secbrain as a Model Context Protocol tool, enabling Claude Code to natively query and store memories during coding sessions.

```bash
# Start MCP server
secbrain mcp

# Or run directly
python -m secbrain.mcp_server
```

Available MCP tools:
- `secbrain_query_memory` — Semantic search across memories
- `secbrain_add_memory` — Store new memories
- `secbrain_get_memories_by_type` — Filter by memory type
- `secbrain_get_memory_stats` — Collection statistics
- `secbrain_inject_context` — Generate prompt-ready context blocks

## Contributing

Contributions are welcome! Whether it's adding new memory types, improving retrieval logic, or fixing bugs.

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/my-feature`)
3. Commit your changes
4. Push to your fork and open a Pull Request

See [`docs/CONTRIBUTING.md`](docs/CONTRIBUTING.md) for development setup.

## License

secbrain is open source under the MIT License.

```
MIT License
Copyright (c) 2026 onchain3r
Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:
The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.
THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND.
```

## Citation

If secbrain helps your research or workflow, cite it:

```
@misc{secbrain2026,
      title={secbrain: RAG-Powered Cognitive Memory for AI Agents},
      author={onchain3r},
      year={2026},
      url={https://github.com/onchain3r/secbrain},
}
```