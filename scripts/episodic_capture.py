#!/usr/bin/env python3
"""
episodic_capture.py — 场景记忆写入器

对话结束后调用，从对话内容中提取场景摘要、关键词、情绪等，
写入 episodic_memory.db。

用法：
  python3 episodic_capture.py --scene-type 错误 --summary "..." --tags '["tag1","tag2"]' [--detail "..." --importance 8 --emotional-mark 痛]

首次运行会自动创建数据库和表。
"""

import sqlite3
import json
import os
import sys
import argparse
from datetime import datetime

DB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'memory')
DB_PATH = os.path.join(DB_DIR, 'episodic_memory.db')

os.makedirs(DB_DIR, exist_ok=True)

SCHEMA_SQL = """
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

CREATE TABLE IF NOT EXISTS memory_aggregates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    group_name TEXT NOT NULL,
    summary TEXT NOT NULL,
    source_ids TEXT NOT NULL,
    lesson TEXT DEFAULT '',
    created_at TEXT DEFAULT (datetime('now', 'localtime')),
    target_file TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS memory_tags_index (
    tag TEXT NOT NULL,
    memory_id INTEGER NOT NULL,
    PRIMARY KEY (tag, memory_id)
);

CREATE INDEX IF NOT EXISTS idx_memory_date ON episodic_memory(memory_date);
CREATE INDEX IF NOT EXISTS idx_scene_type ON episodic_memory(scene_type);
CREATE INDEX IF NOT EXISTS idx_importance ON episodic_memory(importance);
CREATE INDEX IF NOT EXISTS idx_tags ON memory_tags_index(tag);
"""

def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.executescript(SCHEMA_SQL)
    conn.commit()
    conn.close()

def insert_memory(scene_type, thing_type, risk_level, importance, summary,
                  detail, emotional_mark, memory_date, half_life_days,
                  file_path, tags, weight):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    tags_json = json.dumps(tags, ensure_ascii=False)
    related_json = '[]'
    
    c.execute('''
        INSERT INTO episodic_memory 
        (scene_type, thing_type, risk_level, importance, summary, detail,
         emotional_mark, memory_date, half_life_days, file_path, 
         related_ids, tags, weight)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (scene_type, thing_type, risk_level, importance, summary, detail,
          emotional_mark, memory_date, half_life_days, file_path,
          related_json, tags_json, weight))
    
    memory_id = c.lastrowid
    
    # 写入 tags 索引
    for tag in tags:
        tag_lower = tag.lower().strip()
        if tag_lower:
            c.execute('INSERT OR IGNORE INTO memory_tags_index (tag, memory_id) VALUES (?, ?)',
                     (tag_lower, memory_id))
    
    conn.commit()
    conn.close()
    return memory_id

def main():
    parser = argparse.ArgumentParser(description='写入场景记忆')
    parser.add_argument('--scene-type', required=True, help='场景类型：对话/任务/错误/约定/冲突/学习')
    parser.add_argument('--thing-type', default='', help='事情类型')
    parser.add_argument('--risk-level', default='中', choices=['低', '中', '高'])
    parser.add_argument('--importance', type=int, default=5, help='重要性 1-10')
    parser.add_argument('--summary', required=True, help='场景摘要')
    parser.add_argument('--detail', default='', help='详细描述')
    parser.add_argument('--emotional-mark', default='', help='情绪印记')
    parser.add_argument('--memory-date', default='', help='事件日期，默认今天')
    parser.add_argument('--half-life', type=int, default=7, help='半衰期天数')
    parser.add_argument('--file-path', default='', help='关联文件路径')
    parser.add_argument('--tags', default='[]', help='标签 JSON 数组')
    parser.add_argument('--weight', type=float, default=1.0, help='初始权重')
    
    args = parser.parse_args()
    
    # 自动根据 importance 计算初始 weight
    if args.weight == 1.0 and args.importance >= 7:
        args.weight = {9: 1.5, 10: 1.5, 8: 1.3, 7: 1.2}.get(args.importance, 1.0)
    
    memory_date = args.memory_date or datetime.now().strftime('%Y-%m-%d')
    tags = json.loads(args.tags) if isinstance(args.tags, str) else args.tags
    
    init_db()
    mid = insert_memory(
        scene_type=args.scene_type,
        thing_type=args.thing_type,
        risk_level=args.risk_level,
        importance=args.importance,
        summary=args.summary,
        detail=args.detail,
        emotional_mark=args.emotional_mark,
        memory_date=memory_date,
        half_life_days=args.half_life,
        file_path=args.file_path,
        tags=tags,
        weight=args.weight
    )
    
    print(f"场景记忆已写入，ID={mid}")
    print(f"数据库位置: {DB_PATH}")

    # Auto-suggest triple for high-importance errors
    if args.scene_type == "错误" and args.importance >= 7:
        print(f"\n💡 建议为这条错误经验创建 symptom-cause-solution 三元组:")
        print(f"   python3 scripts/triples.py add \\")
        print(f"     --symptom '{args.summary[:50]}' \\")
        print(f"     --cause '<根因>' \\")
        print(f"     --solution '<方案>' \\")
        print(f"     --domain '运维' \\")
        print(f"     --tags '{args.tags}'")

if __name__ == '__main__':
    main()
