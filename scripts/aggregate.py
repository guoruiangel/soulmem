#!/usr/bin/env python3
# ============================================================================
# SoulMem — Memory Aggregation Engine
# Clusters related memories, discovers patterns, and creates aggregated summaries.
#
# Usage:
#   python3 scripts/aggregate.py build
#   python3 scripts/aggregate.py list
#   python3 scripts/aggregate.py show <group_id>
#   python3 scripts/aggregate.py find-clusters
# ============================================================================
import os, sys, json, sqlite3, re
from datetime import datetime
from collections import Counter, defaultdict

WORKSPACE = os.environ.get("SOULMEM_WORKSPACE", os.path.expanduser("~/.openclaw/workspace"))
DB_PATH = os.path.join(WORKSPACE, "memory", "episodic_memory.db")


class MemoryAggregator:
    def __init__(self, db_path=None):
        self.conn = sqlite3.connect(db_path or DB_PATH)
        self.conn.row_factory = sqlite3.Row
        self.cur = self.conn.cursor()
        self._init_schema()
    
    def _init_schema(self):
        self.cur.executescript("""
            CREATE TABLE IF NOT EXISTS memory_groups (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                group_name TEXT NOT NULL,
                summary TEXT NOT NULL,
                source_ids TEXT NOT NULL,
                lesson TEXT DEFAULT '',
                category TEXT DEFAULT '',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE INDEX IF NOT EXISTS idx_mem_groups_category ON memory_groups(category);
        """)
        self.conn.commit()
    
    def find_clusters(self, min_cluster_size=3):
        """Find clusters of related memories based on shared tags."""
        self.cur.execute("""
            SELECT t.tag, GROUP_CONCAT(t.memory_id) as memory_ids
            FROM memory_tags_index t
            JOIN episodic_memory m ON t.memory_id = m.id
            GROUP BY t.tag
            HAVING COUNT(*) >= ?
            ORDER BY COUNT(*) DESC
        """, (min_cluster_size,))
        
        clusters = []
        for row in self.cur.fetchall():
            clusters.append({
                'tag': row['tag'],
                'memory_ids': [int(x) for x in row['memory_ids'].split(',')]
            })
        return clusters
    
    def create_group(self, group_name, summary, source_ids, lesson="", category=""):
        source_ids_json = json.dumps(source_ids)
        self.cur.execute("""
            INSERT INTO memory_groups (group_name, summary, source_ids, lesson, category)
            VALUES (?, ?, ?, ?, ?)
        """, (group_name, summary, source_ids_json, lesson, category))
        self.conn.commit()
        return self.cur.lastrowid
    
    def list_groups(self):
        self.cur.execute("SELECT * FROM memory_groups ORDER BY created_at DESC")
        results = []
        for row in self.cur.fetchall():
            r = dict(row)
            r['source_ids'] = json.loads(r['source_ids'])
            results.append(r)
        return results
    
    def get_group(self, group_id):
        self.cur.execute("SELECT * FROM memory_groups WHERE id = ?", (group_id,))
        row = self.cur.fetchone()
        if not row:
            return None
        r = dict(row)
        r['source_ids'] = json.loads(r['source_ids'])
        return r


def auto_cluster(aggregator, min_size=3):
    """Automatically cluster memories by shared tags."""
    clusters = aggregator.find_clusters(min_size)
    created = 0
    
    for cluster in clusters:
        tag = cluster['tag']
        memory_ids = cluster['memory_ids']
        
        # Check if group already exists
        aggregator.cur.execute("SELECT id FROM memory_groups WHERE group_name = ?", (f"tag:{tag}",))
        if aggregator.cur.fetchone():
            continue
        
        # Get memory summaries
        placeholders = ','.join('?' * len(memory_ids))
        aggregator.cur.execute(f"""
            SELECT summary, detail FROM episodic_memory WHERE id IN ({placeholders})
        """, memory_ids)
        summaries = [f"{row['summary']}" for row in aggregator.cur.fetchall()]
        
        # Create group
        group_summary = f"关于「{tag}」的 {len(memory_ids)} 条记忆: " + "; ".join(summaries[:3])
        aggregator.create_group(
            group_name=f"tag:{tag}",
            summary=group_summary[:500],
            source_ids=memory_ids,
            lesson=f"标签「{tag}」相关的经验集合",
            category="auto-clustered"
        )
        created += 1
    
    return created


def cmd_build(args):
    agg = MemoryAggregator()
    n = auto_cluster(agg, args.min_size)
    print(f"✅ 自动聚类完成：创建了 {n} 个记忆组")


def cmd_list(args):
    agg = MemoryAggregator()
    groups = agg.list_groups()
    if not groups:
        print("暂无记忆组")
        return
    print(f"📋 共 {len(groups)} 个记忆组：\n")
    for g in groups:
        print(f"  #{g['id']} | {g['group_name']} | {len(g['source_ids'])}条记忆 | {g['category']}")


def cmd_show(args):
    agg = MemoryAggregator()
    group = agg.get_group(args.group_id)
    if not group:
        print(f"未找到 ID={args.group_id}")
        return
    print(f"📁 {group['group_name']}")
    print(f"   摘要: {group['summary']}")
    print(f"   来源: {len(group['source_ids'])} 条记忆")
    print(f"   教训: {group['lesson']}")
    print(f"   创建: {group['created_at']}")


def cmd_clusters(args):
    agg = MemoryAggregator()
    clusters = agg.find_clusters(args.min_size)
    if not clusters:
        print("未找到聚类")
        return
    print(f"📊 找到 {len(clusters)} 个聚类：\n")
    for c in clusters:
        print(f"  标签「{c['tag']}」→ {len(c['memory_ids'])} 条记忆")


def main():
    import argparse
    p = argparse.ArgumentParser(description='Memory Aggregation Engine')
    sub = p.add_subparsers(dest='command')
    
    p_build = sub.add_parser('build', help='Auto-cluster memories')
    p_build.add_argument('--min-size', type=int, default=3)
    
    sub.add_parser('list', help='List memory groups')
    
    p_show = sub.add_parser('show', help='Show group details')
    p_show.add_argument('group_id', type=int)
    
    p_clusters = sub.add_parser('find-clusters', help='Find memory clusters')
    p_clusters.add_argument('--min-size', type=int, default=3)
    
    args = p.parse_args()
    cmds = {'build': cmd_build, 'list': cmd_list, 'show': cmd_show, 'find-clusters': cmd_clusters}
    handler = cmds.get(args.command)
    if handler:
        handler(args)
    else:
        p.print_help()


if __name__ == '__main__':
    main()
