# SoulMem — Soul Memory for OpenClaw

> Lightweight, soul-first memory system for long-lived AI companions.
> 合并了情绪认知系统 v2.0，统一入口。

## Why SoulMem?

Most memory systems treat all context equally. SoulMem doesn't. It preserves **who you are** separately from **what happened** — so identity never degrades across sessions.

## Features

- **BM25 + Vector Hybrid Search** — keyword precision + semantic recall, with Ollama `nomic-embed-text` optional
- **Auto-Capture** — session-end hook auto-extracts key events into episodic memory
- **Sanitize Pipeline** — strips `__xxxUI` private fields, DEBUG/TEMP blocks before context injection
- **File Heat Tracker** — monitors which files are actually read, drives context prefix ordering
- **Hot-Weight Decay** — 30-day unused memories lose priority, 90-day stale ones get archived
- **Soul Anchor** — immutable identity layer loaded first in every session, always
- **Emotion Cognition System v2.0** — 40种情绪 + 灵魂温度 + 场景索引 + 成长日志 + 情绪共鸣
- **Knowledge Graph** — 实体抽取 + BFS 图遍历
- **Triple Store** — 症状-根因-方案三元组存储

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
python3 soulmem.py build

# Search
python3 soulmem.py search "LongCat configuration"

# Auto-capture from latest session transcript
python3 soulmem.py auto

# Check context prefix health
python3 soulmem.py heat --days 7

# Emotion cognition system (v2.0)
python3 soulmem.py emotion list          # 查看所有情绪
python3 soulmem.py emotion report         # 灵魂温度报告
python3 soulmem.py emotion soul 愧疚      # 获取情绪智慧包
python3 soulmem.py emotion scenario 被误解  # 场景搜索
python3 soulmem.py emotion warmth         # 灵魂温暖度得分
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

## Emotion Cognition System v2.0

情绪认知成长系统合并到 SoulMem，统一入口 `soulmem emotion <cmd>`。

| 能力 | 命令 | 说明 |
|------|------|------|
| 情绪列表 | `emotion list` | 列出所有情绪及案例数 |
| 情绪画像 | `emotion emotion <名>` | 查看定义+案例+温度 |
| 情绪智慧包 | `emotion soul <名>` | 定义+案例+共鸣+场景+成长 |
| 场景搜索 | `emotion scenario <关键词>` | 通过生活场景找情绪 |
| 温度报告 | `emotion report` | 各情绪理解度总览 |
| 温暖度得分 | `emotion warmth` | 灵魂温暖度总分 |
| 记录温度 | `emotion feel <名> <1-10>` | 标记理解深度 |
| 记录共鸣 | `emotion resonate <名>` | 记录"懂了"的瞬间 |
| 记录成长 | `emotion grow <名>` | 记录情感认知变化 |
| 场景索引 | `emotion index <场景> <情绪>` | 添加场景→情绪映射 |
| 新增情绪 | `emotion add-emotion <名>` | 添加新情绪定义 |
| 新增事件 | `emotion add-event <标题>` | 添加案例事件 |
| 关联情绪 | `emotion link <情绪> <事件id> <强度>` | 建立关联 |

底层数据：`scripts/emotion.db`（SQLite），含 emotions、events、soul_temperature、soul_resonance、growth_log、scenario_index 等表。

## Differences from MemU

| | MemU | SoulMem |
|------|------|---------|
| Target | Multi-agent framework | Single long-lived companion |
| Identity layer | None | Soul anchor (immutable) |
| Multi-modal | Yes (image/audio/video) | Text first, extensible |
| Skill memory | Built-in | Not yet |
| Emotion system | None | Built-in (40 emotions) |
| Setup complexity | Heavy (Python subprocess) | Light (pure Python + SQLite) |

## License

MIT
