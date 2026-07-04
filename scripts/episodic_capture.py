#!/usr/bin/env python3
# ============================================================================
# SoulMem — Episodic Capture
# Write a scene memory record into the episodic_memory SQLite database.
#
# Usage:
#   python3 scripts/episodic_capture.py \
#     --scene-type "错误" \
#     --summary "Short summary" \
#     --detail "Detailed description" \
#     --importance 8 \
#     --tags '["error","LongCat"]'
# ============================================================================
import os, sys, json, sqlite3, argparse
from datetime import datetime

WORKSPACE = os.environ.get("SOULMEM_WORKSPACE", os.path.expanduser("~/.openclaw/workspace"))
DB_PATH   = os.path.join(WORKSPACE, "memory", "episodic_memory.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS episodic_memory (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    scene_type TEXT NOT NULL,
    thing_type TEXT DEFAULT '',
    risk_level TEXT DEFAULT '中',
    importance INTEGER DEFAULT 5,
    summary TEXT NOT NULL,
    detail TEXT DEFAULT '',
    emotional_mark TEXT DEFAULT '',
    memory_date TEXT NOT NULL,
    created_at TEXT DEFAULT (datetime('now', 'localtime')),
    half_life_days INTEGER DEFAULT 7,
    file_path TEXT DEFAULT '',
    related_ids TEXT DEFAULT '[]',
    tags TEXT DEFAULT '[]',
    weight REAL DEFAULT 1.0,
    last_accessed TEXT DEFAULT '',
    group_id INTEGER DEFAULT 0,
    is_aggregated INTEGER DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_mem_date ON episodic_memory(memory_date);
CREATE INDEX IF NOT EXISTS idx_scene_type ON episodic_memory(scene_type);
CREATE INDEX IF NOT EXISTS idx_importance ON episodic_memory(importance);
"""

def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.executescript(SCHEMA)
    conn.commit()
    return conn

def main():
    parser = argparse.ArgumentParser(description='Write a scene memory record')
    parser.add_argument('--scene-type', required=True, help='Type of scene')
    parser.add_argument('--summary', required=True, help='One-line summary')
    parser.add_argument('--detail', default='', help='Detailed description')
    parser.add_argument('--importance', type=int, default=5, help='1-10 importance')
    parser.add_argument('--tags', default='[]', help='JSON array of tags')
    parser.add_argument('--emotional-mark', default='', help='Emotional notes')
    parser.add_argument('--memory-date', default=None, help='YYYY-MM-DD (default: today)')
    parser.add_argument('--weight', type=float, default=1.0, help='Initial weight')
    args = parser.parse_args()

    conn = init_db()
    now = datetime.now().strftime('%Y-%m-%d')
    mem_date = args.memory_date or now

    conn.execute("""
        INSERT INTO episodic_memory 
        (scene_type, importance, summary, detail, emotional_mark, memory_date, tags, weight)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (args.scene_type, args.importance, args.summary, args.detail,
          args.emotional_mark, mem_date, args.tags, args.weight))
    conn.commit()

    cur = conn.cursor()
    cur.execute('SELECT COUNT(*) FROM episodic_memory')
    total = cur.fetchone()[0]
    conn.close()

    print(f"场景记忆已写入，ID={total}")
    print(f"数据库位置: {DB_PATH}")

if __name__ == '__main__':
    main()
