# SoulMem — Soul Memory for OpenClaw

> Lightweight, soul-first memory system for long-lived AI companions.

## Why SoulMem?

Most memory systems treat all context equally. SoulMem doesn't. It preserves **who you are** separately from **what happened** — so identity never degrades across sessions.

## Features

- **BM25 + Vector Hybrid Search** — keyword precision + semantic recall, with Ollama `nomic-embed-text` optional
- **Auto-Capture** — session-end hook auto-extracts key events into episodic memory
- **Sanitize Pipeline** — strips `__xxxUI` private fields, DEBUG/TEMP blocks before context injection
- **File Heat Tracker** — monitors which files are actually read, drives context prefix ordering
- **Hot-Weight Decay** — 30-day unused memories lose priority, 90-day stale ones get archived
- **Soul Anchor** — immutable identity layer loaded first in every session, always

## Architecture

```
episodic_memory.db          ← records (scene_type, summary, detail, tags, weight)
memory_vectors table        ← embeddings (one row per memory record)
file_heat.json              ← read-frequency ranking → context prefix order
```

## Setup

```bash
git clone https://github.com/guoruiangel/soulmem.git
cd soulmem

# Required: place your episodic_memory.db at ~/.openclaw/workspace/memory/episodic_memory.db
# Optional: ollama pull nomic-embed-text  (enables semantic vector search)

# Build vector index (requires ollama for full features, falls back to TF-IDF)
python3 scripts/memory_search.py --build

# Search
python3 scripts/memory_search.py "LongCat configuration"

# Auto-capture from latest session transcript
python3 scripts/auto_capture.py

# Check context prefix health
python3 scripts/file_heat.py --days 7
```

## Context Prefix Ordering

| Priority | File | Stability |
|----------|------|-----------|
| P0 | `SOUL.md` | **Immutable** — identity anchor, never changes |
| P1 | `AGENTS.md` | Stable — operational rules |
| P2 | `USER.md` | Stable — user identity |
| P3 | `TOOLS.md` | Stable — tool documentation |
| P4 | `MEMORY.md` | Dynamic — daily logs (load on-demand) |
| P5 | `categories/` | Task-triggered knowledge |

This ordering maximizes cache hit rate: the longest unchanging prefix = highest cache reuse.

## Sanitize

Content injected through SoulMem is passed through `sanitize.py` which removes:

- `__xxx` and `_xxx` private fields (timestampUI, debugUI, docVersion, etc.)
- `# DEBUG`, `# TODO`, `# TEMP`, `# FIXME` comment lines
- `[DEBUG]`, `[TEMP]`, `[PRIVATE]` blocks

So your model never sees internal framework noise.

## Differences from MemU

| | MemU | SoulMem |
|------|------|---------|
| Target | Multi-agent framework | Single long-lived companion |
| Identity layer | None | Soul anchor (immutable) |
| Multi-modal | Yes (image/audio/video) | Text first, extensible |
| Skill memory | Built-in | Not yet |
| Setup complexity | Heavy (Python subprocess) | Light (pure Python + SQLite) |

## License

MIT
