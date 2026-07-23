#!/usr/bin/env python3
# ============================================================================
# SoulMem — Troubleshooting Decision Tree Engine
# Maps symptoms to diagnostic SOPs (Standard Operating Procedures).
#
# Usage:
#   python3 scripts/troubleshooter.py search "500 error"
#   python3 scripts/troubleshooter.py run <sop_id>
#   python3 scripts/troubleshooter.py list
#   python3 scripts/troubleshooter.py add --symptom "..." --steps '["...","..."]'
# ============================================================================
import os, sys, json, sqlite3
from datetime import datetime

WORKSPACE = os.environ.get("SOULMEM_WORKSPACE", os.path.expanduser("~/.openclaw/workspace"))
from soulmem_config import DB_PATH


class Troubleshooter:
    def __init__(self, db_path=None):
        self.conn = sqlite3.connect(db_path or DB_PATH)
        self.conn.row_factory = sqlite3.Row
        self.cur = self.conn.cursor()
        self._init_schema()
    
    def _init_schema(self):
        self.cur.executescript("""
            CREATE TABLE IF NOT EXISTS troubleshooting_sops (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symptom TEXT NOT NULL,
                category TEXT DEFAULT 'general',
                steps TEXT NOT NULL,
                expected_outcomes TEXT DEFAULT '[]',
                success_count INTEGER DEFAULT 0,
                fail_count INTEGER DEFAULT 0,
                avg_resolution_minutes REAL DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_used TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE INDEX IF NOT EXISTS idx_sops_category ON troubleshooting_sops(category);
        """)
        self.conn.commit()
    
    def add_sop(self, symptom, steps, category="general", expected_outcomes=None):
        steps_json = json.dumps(steps, ensure_ascii=False)
        outcomes_json = json.dumps(expected_outcomes or [], ensure_ascii=False)
        self.cur.execute("""
            INSERT INTO troubleshooting_sops (symptom, category, steps, expected_outcomes)
            VALUES (?, ?, ?, ?)
        """, (symptom, category, steps_json, outcomes_json))
        self.conn.commit()
        return self.cur.lastrowid
    
    def search_sop(self, query, top=3):
        qt = query.lower().split()
        self.cur.execute("SELECT * FROM troubleshooting_sops ORDER BY success_count DESC")
        results = []
        for row in self.cur.fetchall():
            text = f"{row['symptom']} {row['category']}".lower()
            matches = sum(1 for t in qt if t in text)
            if matches > 0:
                r = dict(row)
                r['steps'] = json.loads(r['steps'])
                r['expected_outcomes'] = json.loads(r['expected_outcomes'])
                r['match_score'] = matches
                results.append(r)
        results.sort(key=lambda x: (-x['match_score'], -x['success_count']))
        return results[:top]
    
    def record_result(self, sop_id, success, resolution_minutes=0):
        if success:
            self.cur.execute("""
                UPDATE troubleshooting_sops 
                SET success_count = success_count + 1,
                    avg_resolution_minutes = (avg_resolution_minutes * success_count + ?) / (success_count + 1),
                    last_used = datetime('now', 'localtime')
                WHERE id = ?
            """, (resolution_minutes, sop_id))
        else:
            self.cur.execute("""
                UPDATE troubleshooting_sops 
                SET fail_count = fail_count + 1,
                    last_used = datetime('now', 'localtime')
                WHERE id = ?
            """, (sop_id,))
        self.conn.commit()
    
    def list_all(self):
        self.cur.execute("SELECT * FROM troubleshooting_sops ORDER BY success_count DESC")
        results = []
        for row in self.cur.fetchall():
            r = dict(row)
            r['steps'] = json.loads(r['steps'])
            r['expected_outcomes'] = json.loads(r['expected_outcomes'])
            results.append(r)
        return results


def cmd_search(args):
    ts = Troubleshooter()
    results = ts.search_sop(args.query, args.top)
    if not results:
        print(f"未找到与「{args.query}」相关的排查SOP")
        return
    print(f"🔍 '{args.query}' → {len(results)} 个SOP\n")
    for i, sop in enumerate(results, 1):
        print(f"  [{i}] #{sop['id']} {sop['symptom']}")
        print(f"      类别: {sop['category']} | 成功: {sop['success_count']}次 | 匹配: {sop['match_score']}")
        print(f"      步骤:")
        for j, step in enumerate(sop['steps'], 1):
            print(f"        {j}. {step}")
        print()


def cmd_list(args):
    ts = Troubleshooter()
    results = ts.list_all()
    if not results:
        print("暂无排查SOP")
        return
    print(f"📋 共 {len(results)} 个排查SOP：\n")
    for sop in results:
        print(f"  #{sop['id']} | {sop['category']} | 成功:{sop['success_count']}次 | {sop['symptom']}")


def cmd_add(args):
    ts = Troubleshooter()
    steps = json.loads(args.steps) if args.steps else []
    outcomes = json.loads(args.outcomes) if args.outcomes else []
    sid = ts.add_sop(args.symptom, steps, args.category or "general", outcomes)
    print(f"✅ SOP写入 ID={sid}")


def cmd_record(args):
    ts = Troubleshooter()
    ts.record_result(args.sop_id, args.success == "true", args.minutes or 0)
    print(f"✅ 记录结果: SOP #{args.sop_id} → {'成功' if args.success == 'true' else '失败'}")


def main():
    import argparse
    p = argparse.ArgumentParser(description='Troubleshooting Decision Tree')
    sub = p.add_subparsers(dest='command')
    
    p_search = sub.add_parser('search', help='Search SOPs by symptom')
    p_search.add_argument('query')
    p_search.add_argument('--top', type=int, default=3)
    
    sub.add_parser('list', help='List all SOPs')
    
    p_add = sub.add_parser('add', help='Add a SOP')
    p_add.add_argument('--symptom', required=True)
    p_add.add_argument('--steps', required=True, help='JSON array of steps')
    p_add.add_argument('--category', default='general')
    p_add.add_argument('--outcomes', default='[]', help='JSON array')
    
    p_record = sub.add_parser('record', help='Record SOP result')
    p_record.add_argument('sop_id', type=int)
    p_record.add_argument('success', choices=['true', 'false'])
    p_record.add_argument('--minutes', type=int, default=0)
    
    args = p.parse_args()
    cmds = {'search': cmd_search, 'list': cmd_list, 'add': cmd_add, 'record': cmd_record}
    handler = cmds.get(args.command)
    if handler:
        handler(args)
    else:
        p.print_help()


if __name__ == '__main__':
    main()
