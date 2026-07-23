#!/usr/bin/env python3
# ============================================================================
# SoulMem — Symptom-Cause-Solution Triple Store
# 
# 存储、检索、关联结构化的问题修复经验。
# 支持：症状匹配、根因检索、方案推荐、自动标签提取。
#
# Usage:
#   python3 scripts/triples.py add --symptom "..." --cause "..." --solution "..." --tags '["tag1","tag2"]'
#   python3/scripts/triples.py search "symptom query" --top 5
#   python3/scripts/triples.py list  # List all triples
#   python3/scripts/triples.py show <id>
# ============================================================================

import os
import sys
import json
import sqlite3
from datetime import datetime

WORKSPACE = os.environ.get("SOULMEM_WORKSPACE", os.path.expanduser("~/.openclaw/workspace"))
from soulmem_config import DB_PATH


class TripleStore:
    """Symptom-Cause-Solution triple storage and retrieval."""
    
    def __init__(self, db_path=None):
        self.conn = sqlite3.connect(db_path or DB_PATH)
        self.conn.row_factory = sqlite3.Row
        self.cur = self.conn.cursor()
        self._init_schema()
    
    def _init_schema(self):
        self.cur.executescript("""
            CREATE TABLE IF NOT EXISTS triples (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symptom TEXT NOT NULL,
                cause TEXT NOT NULL,
                solution TEXT NOT NULL,
                tags TEXT DEFAULT '[]',
                domain TEXT DEFAULT 'general',
                confidence REAL DEFAULT 0.8,
                usage_count INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_used TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE INDEX IF NOT EXISTS idx_triples_domain ON triples(domain);
            CREATE INDEX IF NOT EXISTS idx_triples_tags ON triples(tags);
        """)
        self.conn.commit()
    
    def add(self, symptom, cause, solution, tags=None, domain="general", confidence=0.8):
        tag_json = json.dumps(tags or [], ensure_ascii=False)
        self.cur.execute("""
            INSERT INTO triples (symptom, cause, solution, tags, domain, confidence)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (symptom, cause, solution, tag_json, domain, confidence))
        self.conn.commit()
        return self.cur.lastrowid
    
    def search(self, query, top=5):
        """Search triples by symptom keyword matching."""
        qt = query.lower().split()
        if not qt:
            return []
        
        self.cur.execute("SELECT * FROM triples ORDER BY confidence DESC, usage_count DESC")
        results = []
        for row in self.cur.fetchall():
            text = f"{row['symptom']} {row['cause']} {row['solution']}".lower()
            matches = sum(1 for t in qt if t in text)
            if matches > 0:
                r = dict(row)
                r['tags'] = json.loads(r['tags'])
                r['match_score'] = matches
                results.append(r)
        
        results.sort(key=lambda x: (-x['match_score'], -x['confidence']))
        return results[:top]
    
    def get(self, triple_id):
        self.cur.execute("SELECT * FROM triples WHERE id = ?", (triple_id,))
        row = self.cur.fetchone()
        if not row:
            return None
        r = dict(row)
        r['tags'] = json.loads(r['tags'])
        return r
    
    def list_all(self):
        self.cur.execute("SELECT * FROM triples ORDER BY id DESC")
        results = []
        for row in self.cur.fetchall():
            r = dict(row)
            r['tags'] = json.loads(r['tags'])
            results.append(r)
        return results
    
    def increment_usage(self, triple_id):
        self.cur.execute("""
            UPDATE triples 
            SET usage_count = usage_count + 1, last_used = datetime('now', 'localtime')
            WHERE id = ?
        """, (triple_id,))
        self.conn.commit()
    
    def delete(self, triple_id):
        self.cur.execute("DELETE FROM triples WHERE id = ?", (triple_id,))
        self.conn.commit()
        return self.cur.rowcount > 0


def cmd_add(args):
    """Add a new triple."""
    ts = TripleStore()
    tags = json.loads(args.tags) if args.tags else []
    tid = ts.add(
        symptom=args.symptom,
        cause=args.cause,
        solution=args.solution,
        tags=tags,
        domain=args.domain or "general",
        confidence=args.confidence or 0.8,
    )
    print(f"✅ 三元组写入 ID={tid}")
    
    # Also capture as episodic memory
    try:
        from episodic_capture import init_db, capture_record
        conn = init_db()
        capture_record(
            conn,
            scene_type="学习",
            summary=f"经验沉淀: {args.symptom[:50]}",
            detail=f"症状: {args.symptom}\n根因: {args.cause}\n方案: {args.solution}\n标签: {','.join(tags)}\n领域: {args.domain}",
            importance=7,
            tags=json.dumps(["经验沉淀"] + tags),
        )
        conn.close()
        print("✅ 同步写入场景记忆")
    except Exception as e:
        print(f"⚠️ 场景记忆同步失败: {e}")


def cmd_search(args):
    """Search triples by symptom."""
    ts = TripleStore()
    results = ts.search(args.query, args.top)
    if not results:
        print(f"未找到与「{args.query}」相关的经验")
        # Also search episodic memory as fallback
        try:
            from memory_search import SearchEngine
            eng = SearchEngine()
            fallback = eng.search(args.query, top=3)
            if fallback.get('results'):
                print(f"\n💡 场景记忆中找到 {len(fallback['results'])} 条相关记录：")
                for r in fallback['results']:
                    print(f"   (重要性={r['importance']}) {r['summary'][:70]}")
        except Exception:
            pass
        return
    
    print(f"🔍 '{args.query}' → 找到 {len(results)} 条经验\n")
    for i, t in enumerate(results, 1):
        print(f"  [{i}] 匹配度:{t['match_score']} | 置信度:{t['confidence']}")
        print(f"      症状: {t['symptom'][:80]}")
        print(f"      根因: {t['cause'][:80]}")
        print(f"      方案: {t['solution'][:80]}")
        if t['tags']:
            print(f"      标签: {', '.join(t['tags'])}")
        print()


def cmd_list(args):
    """List all triples."""
    ts = TripleStore()
    results = ts.list_all()
    if not results:
        print("暂无三元组记录")
        return
    print(f"📋 共 {len(results)} 条经验：\n")
    for t in results:
        print(f"  #{t['id']} | {t['domain']} | 使用:{t['usage_count']}次 | {t['symptom'][:50]}")


def cmd_show(args):
    """Show triple details."""
    ts = TripleStore()
    t = ts.get(args.triple_id)
    if not t:
        print(f"未找到 ID={args.triple_id}")
        return
    print(f"📋 三元组 #{t['id']}")
    print(f"  领域: {t['domain']}")
    print(f"  置信度: {t['confidence']} | 使用次数: {t['usage_count']}")
    print(f"  创建: {t['created_at']} | 最后使用: {t['last_used']}")
    print(f"  标签: {', '.join(t['tags'])}")
    print(f"  症状: {t['symptom']}")
    print(f"  根因: {t['cause']}")
    print(f"  方案: {t['solution']}")


def cmd_delete(args):
    """Delete a triple."""
    ts = TripleStore()
    if ts.delete(args.triple_id):
        print(f"✅ 已删除 ID={args.triple_id}")
    else:
        print(f"未找到 ID={args.triple_id}")


def main():
    import argparse
    p = argparse.ArgumentParser(description='SoulMem Triple Store')
    sub = p.add_subparsers(dest='command')
    
    p_add = sub.add_parser('add', help='Add a triple')
    p_add.add_argument('--symptom', required=True, help='Symptom description')
    p_add.add_argument('--cause', required=True, help='Root cause')
    p_add.add_argument('--solution', required=True, help='Solution')
    p_add.add_argument('--tags', default='[]', help='JSON array of tags')
    p_add.add_argument('--domain', default='general', help='Domain/category')
    p_add.add_argument('--confidence', type=float, default=0.8, help='0-1 confidence')
    
    p_search = sub.add_parser('search', help='Search triples')
    p_search.add_argument('query', help='Search query')
    p_search.add_argument('--top', type=int, default=5, help='Number of results')
    
    sub.add_parser('list', help='List all triples')
    
    p_show = sub.add_parser('show', help='Show triple details')
    p_show.add_argument('triple_id', type=int)
    
    p_del = sub.add_parser('delete', help='Delete a triple')
    p_del.add_argument('triple_id', type=int)
    
    args = p.parse_args()
    cmds = {
        'add': cmd_add,
        'search': cmd_search,
        'list': cmd_list,
        'show': cmd_show,
        'delete': cmd_delete,
    }
    
    handler = cmds.get(args.command)
    if handler:
        handler(args)
    else:
        p.print_help()


if __name__ == '__main__':
    main()
