#!/usr/bin/env python3
# ============================================================================
# SoulMem — Spaced Repetition & Smart Review
# Implements forgetting curve reminders and intelligent review scheduling.
#
# Usage:
#   python3 scripts/review.py due          # Show memories due for review
#   python3 scripts/review.py review <id>  # Mark memory as reviewed
#   python3 scripts/review.py stats        # Show review statistics
#   python3 scripts/review.py heatmap      # Show memory activity heatmap
# ============================================================================
import os, sys, json, sqlite3, math
from datetime import datetime, timedelta

WORKSPACE = os.environ.get("SOULMEM_WORKSPACE", os.path.expanduser("~/.openclaw/workspace"))
DB_PATH = os.path.join(WORKSPACE, "memory", "episodic_memory.db")


class ReviewEngine:
    def __init__(self, db_path=None):
        self.conn = sqlite3.connect(db_path or DB_PATH)
        self.conn.row_factory = sqlite3.Row
        self.cur = self.conn.cursor()
        self._init_schema()
    
    def _init_schema(self):
        self.cur.executescript("""
            CREATE TABLE IF NOT EXISTS review_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                memory_id INTEGER NOT NULL,
                reviewed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                performance INTEGER DEFAULT 3,
                next_review DATE,
                interval_days INTEGER DEFAULT 1,
                ease_factor REAL DEFAULT 2.5,
                FOREIGN KEY (memory_id) REFERENCES episodic_memory(id)
            );
            CREATE INDEX IF NOT EXISTS idx_review_memory ON review_log(memory_id);
            CREATE INDEX IF NOT EXISTS idx_review_next ON review_log(next_review);
        """)
        self.conn.commit()
    
    def get_due_memories(self, limit=10):
        """Get memories due for review using SM-2 algorithm."""
        now = datetime.now().strftime('%Y-%m-%d')
        
        self.cur.execute("""
            SELECT m.*, 
                   COALESCE(
                       (SELECT next_review FROM review_log 
                        WHERE memory_id = m.id ORDER BY reviewed_at DESC LIMIT 1),
                       '1970-01-01'
                   ) as next_review,
                   COALESCE(
                       (SELECT interval_days FROM review_log 
                        WHERE memory_id = m.id ORDER BY reviewed_at DESC LIMIT 1),
                       0
                   ) as interval_days
            FROM episodic_memory m
            WHERE m.importance >= 5
            AND (next_review <= ? OR next_review = '1970-01-01')
            ORDER BY m.importance DESC, next_review ASC
            LIMIT ?
        """, (now, limit))
        
        return [dict(r) for r in self.cur.fetchall()]
    
    def record_review(self, memory_id, performance=3):
        """Record a review session using SM-2 algorithm."""
        # Get current interval and ease factor
        self.cur.execute("""
            SELECT interval_days, ease_factor FROM review_log 
            WHERE memory_id = ? ORDER BY reviewed_at DESC LIMIT 1
        """, (memory_id,))
        row = self.cur.fetchone()
        
        if row:
            interval = row['interval_days']
            ease = row['ease_factor']
        else:
            interval = 0
            ease = 2.5
        
        # SM-2 algorithm
        if performance >= 3:
            if interval == 0:
                new_interval = 1
            elif interval == 1:
                new_interval = 6
            else:
                new_interval = int(interval * ease)
        else:
            new_interval = 1
        
        # Update ease factor
        new_ease = max(1.3, ease + (0.1 - (5 - performance) * (0.08 + (5 - performance) * 0.02)))
        
        next_review = (datetime.now() + timedelta(days=new_interval)).strftime('%Y-%m-%d')
        
        self.cur.execute("""
            INSERT INTO review_log (memory_id, performance, next_review, interval_days, ease_factor)
            VALUES (?, ?, ?, ?, ?)
        """, (memory_id, performance, next_review, new_interval, new_ease))
        
        # Update last_accessed in episodic memory
        self.cur.execute("""
            UPDATE episodic_memory SET last_accessed = ? WHERE id = ?
        """, (datetime.now().strftime('%Y-%m-%d %H:%M:%S'), memory_id))
        
        self.conn.commit()
        return new_interval, next_review
    
    def get_stats(self):
        """Get review statistics."""
        self.cur.execute("SELECT COUNT(*) FROM review_log")
        total_reviews = self.cur.fetchone()[0]
        
        self.cur.execute("SELECT COUNT(DISTINCT memory_id) FROM review_log")
        unique_reviewed = self.cur.fetchone()[0]
        
        self.cur.execute("SELECT COUNT(*) FROM episodic_memory WHERE importance >= 5")
        total_important = self.cur.fetchone()[0]
        
        self.cur.execute("""
            SELECT AVG(performance) FROM review_log 
            WHERE reviewed_at > datetime('now', '-30 days')
        """)
        avg_performance = self.cur.fetchone()[0] or 0
        
        return {
            'total_reviews': total_reviews,
            'unique_reviewed': unique_reviewed,
            'total_important': total_important,
            'coverage': round(unique_reviewed / max(total_important, 1) * 100, 1),
            'avg_performance': round(avg_performance, 2)
        }
    
    def get_heatmap(self, days=30):
        """Get memory activity heatmap."""
        cutoff = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
        self.cur.execute("""
            SELECT DATE(reviewed_at) as day, COUNT(*) as cnt
            FROM review_log
            WHERE reviewed_at > ?
            GROUP BY DATE(reviewed_at)
            ORDER BY day
        """, (cutoff,))
        return [dict(r) for r in self.cur.fetchall()]


def cmd_due(args):
    eng = ReviewEngine()
    memories = eng.get_due_memories(args.limit)
    if not memories:
        print("📋 没有需要复习的记忆")
        return
    
    print(f"📝 {len(memories)} 条记忆需要复习：\n")
    for i, m in enumerate(memories, 1):
        print(f"  [{i}] (#{m['id']}) {m['scene_type']}")
        print(f"      {m['summary'][:80]}")
        print(f"      重要:{m['importance']} | 间隔:{m['interval_days']}天 | 下次:{m['next_review']}")
        print()


def cmd_review(args):
    eng = ReviewEngine()
    interval, next_review = eng.record_review(args.memory_id, args.performance)
    print(f"✅ 复习记录: 记忆 #{args.memory_id}")
    print(f"   间隔: {interval}天 | 下次复习: {next_review}")


def cmd_stats(args):
    eng = ReviewEngine()
    stats = eng.get_stats()
    print("📊 复习统计")
    print(f"   总复习次数: {stats['total_reviews']}")
    print(f"   已复习记忆: {stats['unique_reviewed']}/{stats['total_important']}")
    print(f"   覆盖率: {stats['coverage']}%")
    print(f"   平均表现: {stats['avg_performance']}/5")


def cmd_heatmap(args):
    eng = ReviewEngine()
    data = eng.get_heatmap(args.days)
    if not data:
        print("暂无复习数据")
        return
    print("📊 复习活跃度热力图：")
    for d in data:
        bar = '█' * min(d['cnt'] * 2, 20)
        print(f"  {d['day']}: {d['cnt']}次 {bar}")


def main():
    import argparse
    p = argparse.ArgumentParser(description='Spaced Repetition & Smart Review')
    sub = p.add_subparsers(dest='command')
    
    p_due = sub.add_parser('due', help='Show due memories')
    p_due.add_argument('--limit', type=int, default=10)
    
    p_review = sub.add_parser('review', help='Record a review')
    p_review.add_argument('memory_id', type=int)
    p_review.add_argument('--performance', type=int, default=3, help='1-5 (5=perfect)')
    
    sub.add_parser('stats', help='Show statistics')
    
    p_heat = sub.add_parser('heatmap', help='Show activity heatmap')
    p_heat.add_argument('--days', type=int, default=30)
    
    args = p.parse_args()
    cmds = {'due': cmd_due, 'review': cmd_review, 'stats': cmd_stats, 'heatmap': cmd_heatmap}
    handler = cmds.get(args.command)
    if handler:
        handler(args)
    else:
        p.print_help()


if __name__ == '__main__':
    main()
