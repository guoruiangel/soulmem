#!/usr/bin/env python3
# ============================================================================
# SoulMem — 多 Agent 数据库路由
# 所有脚本共享的 DB_PATH 配置
# ============================================================================

import os

WORKSPACE = os.environ.get("SOULMEM_WORKSPACE", os.path.expanduser("~/.openclaw/workspace"))
AGENT = os.environ.get("SOULMEM_AGENT", "kk")

# 根据 agent 选择数据库
if AGENT == "kk":
    DB_PATH = os.path.join(WORKSPACE, "memory", "episodic_memory.db")
elif AGENT == "iris":
    DB_PATH = os.path.join(WORKSPACE, "soulmem", "agents", "iris", "episodic_memory.db")
elif AGENT == "mira":
    DB_PATH = os.path.join(WORKSPACE, "soulmem", "agents", "mira", "episodic_memory.db")
else:
    DB_PATH = os.path.join(WORKSPACE, "memory", "episodic_memory.db")

# 共享数据库
SHARED_DB_PATH = os.path.join(WORKSPACE, "soulmem", "shared", "episodic_memory.db")

# 确保目录存在
os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
os.makedirs(os.path.dirname(SHARED_DB_PATH), exist_ok=True)
