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
#
# Also importable: capture_record(conn, ...) for direct use by soulmem CLI.
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


def check_duplicate(conn, scene_type: str, summary: str, similarity_threshold: float = 0.85) -> bool:
    """Check if a similar memory already exists (simple keyword overlap dedup)."""
    import re
    cur = conn.cursor()

    # Check same scene_type with similar summary
    cur.execute('SELECT id, summary FROM episodic_memory WHERE scene_type = ? ORDER BY id DESC LIMIT 20',
                (scene_type,))
    rows = cur.fetchall()

    if not rows:
        return False

    # Simple dedup: tokenize summaries and check Jaccard similarity
    def tokenize(text):
        return set(re.findall(r'[\u4e00-\u9fff]+|[a-zA-Z0-9]+', text.lower()))

    new_tokens = tokenize(summary)
    if not new_tokens:
        return False

    for row_id, existing_summary in rows:
        existing_tokens = tokenize(existing_summary)
        if not existing_tokens:
            continue
        # Jaccard similarity
        intersection = new_tokens & existing_tokens
        union = new_tokens | existing_tokens
        if union and len(intersection) / len(union) >= similarity_threshold:
            return True

    return False


def capture_record(
    conn,
    scene_type: str,
    summary: str,
    detail: str = "",
    importance: int = 5,
    tags: str = "[]",
    emotional_mark: str = "",
    memory_date: str = None,
    weight: float = 1.0,
    deduplicate: bool = True,
):
    """Write a memory record. Returns the new record's ID (or existing ID if duplicate)."""
    # Dedup check
    if deduplicate and check_duplicate(conn, scene_type, summary):
        # Find and return the existing ID
        cur = conn.cursor()
        cur.execute('SELECT id FROM episodic_memory WHERE scene_type = ? ORDER BY id DESC LIMIT 1',
                    (scene_type,))
        row = cur.fetchone()
        if row:
            return row[0]  # Return existing ID

    now = datetime.now().strftime('%Y-%m-%d')
    mem_date = memory_date or now

    conn.execute("""
        INSERT INTO episodic_memory 
        (scene_type, importance, summary, detail, emotional_mark, memory_date, tags, weight)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (scene_type, importance, summary, detail, emotional_mark, mem_date, tags, weight))
    conn.commit()

    cur = conn.cursor()
    cur.execute('SELECT last_insert_rowid()')
    return cur.fetchone()[0]


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
    parser.add_argument('--no-dedup', action='store_true', help='Skip deduplication')
    args = parser.parse_args()

    conn = init_db()
    record_id = capture_record(
        conn,
        scene_type=args.scene_type,
        summary=args.summary,
        detail=args.detail,
        importance=args.importance,
        tags=args.tags,
        emotional_mark=args.emotional_mark,
        memory_date=args.memory_date,
        weight=args.weight,
        deduplicate=not args.no_dedup,
    )
    conn.close()

    print(f"场景记忆已写入，ID={record_id}")
    print(f"数据库位置: {DB_PATH}")


if __name__ == '__main__':
    main()
