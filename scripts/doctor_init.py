#!/usr/bin/env python3
# ============================================================================
# SoulMem — Doctor & Init
# Health check, diagnostic, and first-run setup wizard.
#
# Usage:
#   python3 scripts/doctor.py          # Run health check
#   python3 scripts/doctor.py --fix    # Run health check + auto-fix
#   python3 scripts/init.py            # First-run setup wizard
# ============================================================================
import os, sys, json, sqlite3
from datetime import datetime

WORKSPACE = os.environ.get("SOULMEM_WORKSPACE", os.path.expanduser("~/.openclaw/workspace"))
from soulmem_config import DB_PATH


class Doctor:
    """Health check and diagnostic engine."""
    
    def __init__(self, db_path=None):
        self.conn = sqlite3.connect(db_path or DB_PATH)
        self.conn.row_factory = sqlite3.Row
        self.cur = self.conn.cursor()
        self.issues = []
        self.fixes = []
    
    def check_database_integrity(self):
        """Check database integrity."""
        try:
            self.cur.execute("PRAGMA integrity_check")
            result = self.cur.fetchone()
            if result[0] == 'ok':
                return True
            self.issues.append(f"数据库完整性: {result[0]}")
            return False
        except Exception as e:
            self.issues.append(f"数据库无法打开: {e}")
            return False
    
    def check_orphaned_tags(self):
        """Find tags pointing to non-existent memories."""
        self.cur.execute("""
            SELECT t.tag, t.memory_id 
            FROM memory_tags_index t
            LEFT JOIN episodic_memory m ON t.memory_id = m.id
            WHERE m.id IS NULL
        """)
        orphans = self.cur.fetchall()
        if orphans:
            self.issues.append(f"孤立标签: {len(orphans)} 条")
            return len(orphans)
        return 0
    
    def check_orphaned_entities(self):
        """Find entity mentions pointing to non-existent memories."""
        self.cur.execute("""
            SELECT em.entity_id, em.memory_id 
            FROM entity_mentions em
            LEFT JOIN episodic_memory m ON em.memory_id = m.id
            WHERE m.id IS NULL
        """)
        orphans = self.cur.fetchall()
        if orphans:
            self.issues.append(f"孤立实体提及: {len(orphans)} 条")
            return len(orphans)
        return 0
    
    def check_orphaned_triples(self):
        """Find triples linked to non-existent memories."""
        self.cur.execute("""
            SELECT t.id, t.linked_memory_id 
            FROM triples t
            LEFT JOIN episodic_memory m ON t.linked_memory_id = m.id
            WHERE t.linked_memory_id > 0 AND m.id IS NULL
        """)
        orphans = self.cur.fetchall()
        if orphans:
            self.issues.append(f"孤立三元组: {len(orphans)} 条")
            return len(orphans)
        return 0
    
    def check_missing_vectors(self):
        """Find memories without vector embeddings."""
        self.cur.execute("""
            SELECT COUNT(*) FROM episodic_memory 
            WHERE id NOT IN (SELECT id FROM mem_vec)
        """)
        missing = self.cur.fetchone()[0]
        if missing > 0:
            self.issues.append(f"缺少向量索引: {missing} 条记忆")
        return missing
    
    def check_missing_tags(self):
        """Find memories without any tags."""
        self.cur.execute("""
            SELECT COUNT(*) FROM episodic_memory 
            WHERE tags = '[]' OR tags IS NULL
        """)
        missing = self.cur.fetchone()[0]
        if missing > 0:
            self.issues.append(f"缺少标签: {missing} 条记忆")
        return missing
    
    def check_duplicate_memories(self):
        """Find potential duplicate memories (same date + similar summary)."""
        self.cur.execute("""
            SELECT memory_date, COUNT(*) as cnt 
            FROM episodic_memory 
            GROUP BY memory_date, substr(summary, 1, 30)
            HAVING cnt > 1
        """)
        dupes = self.cur.fetchall()
        if dupes:
            self.issues.append(f"潜在重复: {len(dupes)} 组")
            return len(dupes)
        return 0
    
    def check_schema_version(self):
        """Check if all required tables exist."""
        required_tables = [
            'episodic_memory', 'memory_tags_index', 'mem_vec',
            'triples', 'relationships', 'entities', 'entity_mentions',
            'troubleshooting_sops', 'memory_groups', 'review_log'
        ]
        
        self.cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
        existing = {row['name'] for row in self.cur.fetchall()}
        
        missing = [t for t in required_tables if t not in existing]
        if missing:
            self.issues.append(f"缺少表: {', '.join(missing)}")
        
        return missing
    
    def fix_orphaned_tags(self):
        """Remove orphaned tags."""
        self.cur.execute("""
            DELETE FROM memory_tags_index 
            WHERE memory_id NOT IN (SELECT id FROM episodic_memory)
        """)
        count = self.cur.rowcount
        if count > 0:
            self.fixes.append(f"删除 {count} 条孤立标签")
        self.conn.commit()
    
    def fix_orphaned_entities(self):
        """Remove orphaned entity mentions."""
        self.cur.execute("""
            DELETE FROM entity_mentions 
            WHERE memory_id NOT IN (SELECT id FROM episodic_memory)
        """)
        count = self.cur.rowcount
        if count > 0:
            self.fixes.append(f"删除 {count} 条孤立实体提及")
        self.conn.commit()
    
    def fix_orphaned_triples(self):
        """Remove orphaned triples."""
        self.cur.execute("""
            DELETE FROM triples 
            WHERE linked_memory_id > 0 
            AND linked_memory_id NOT IN (SELECT id FROM episodic_memory)
        """)
        count = self.cur.rowcount
        if count > 0:
            self.fixes.append(f"删除 {count} 条孤立三元组")
        self.conn.commit()
    
    def run_all_checks(self):
        """Run all health checks."""
        self.issues = []
        
        checks = [
            ("数据库完整性", self.check_database_integrity),
            ("孤立标签", self.check_orphaned_tags),
            ("孤立实体", self.check_orphaned_entities),
            ("孤立三元组", self.check_orphaned_triples),
            ("缺少向量", self.check_missing_vectors),
            ("缺少标签", self.check_missing_tags),
            ("潜在重复", self.check_duplicate_memories),
            ("Schema 版本", self.check_schema_version),
        ]
        
        results = []
        for name, check_fn in checks:
            try:
                issue_count = check_fn()
                status = "✅" if not issue_count or issue_count == 0 or issue_count == [] else "⚠️"
                results.append((name, status, issue_count))
            except Exception as e:
                results.append((name, "❌", str(e)))
        
        return results
    
    def run_all_fixes(self):
        """Run all auto-fixes."""
        self.fixes = []
        
        fixes = [
            ("孤立标签", self.fix_orphaned_tags),
            ("孤立实体", self.fix_orphaned_entities),
            ("孤立三元组", self.fix_orphaned_triples),
        ]
        
        for name, fix_fn in fixes:
            try:
                fix_fn()
            except Exception as e:
                self.fixes.append(f"修复 {name} 失败: {e}")


def run_doctor(args):
    """Run doctor health check."""
    fix_mode = args.fix if hasattr(args, 'fix') else False
    
    if not os.path.exists(DB_PATH):
        print(f"❌ 数据库不存在: {DB_PATH}")
        print(f"   运行 'python3 scripts/init.py' 初始化")
        return
    
    doc = Doctor()
    
    print("🔍 SoulMem 健康检查\n")
    print("=" * 50)
    
    results = doc.run_all_checks()
    
    for name, status, detail in results:
        print(f"  {status} {name}: {detail}")
    
    print("=" * 50)
    
    if doc.issues:
        print(f"\n⚠️ 发现 {len(doc.issues)} 个问题:")
        for issue in doc.issues:
            print(f"   - {issue}")
    else:
        print("\n✅ 一切正常")
    
    if fix_mode and doc.issues:
        print(f"\n🔧 运行自动修复...\n")
        doc.run_all_fixes()
        
        if doc.fixes:
            for fix in doc.fixes:
                print(f"   ✅ {fix}")
        else:
            print("   无需修复")
    
    # Stats summary
    doc.cur.execute("SELECT COUNT(*) FROM episodic_memory")
    mem_count = doc.cur.fetchone()[0]
    doc.cur.execute("SELECT COUNT(*) FROM triples")
    triple_count = doc.cur.fetchone()[0]
    doc.cur.execute("SELECT COUNT(*) FROM entities")
    entity_count = doc.cur.fetchone()[0]
    
    print(f"\n📊 数据概览:")
    print(f"   记忆数: {mem_count}")
    print(f"   三元组: {triple_count}")
    print(f"   实体数: {entity_count}")


def run_init(args):
    """Run first-time setup wizard."""
    print("🚀 SoulMem 初始化向导\n")
    
    if os.path.exists(DB_PATH):
        print(f"⚠️ 数据库已存在: {DB_PATH}")
        overwrite = input("   是否覆盖? (y/N): ").strip().lower()
        if overwrite != 'y':
            print("   取消")
            return
        os.remove(DB_PATH)
    
    # Create database
    conn = sqlite3.connect(DB_PATH)
    conn.executescript(open(os.path.join(os.path.dirname(__file__), 'episodic_capture.py')).read().split('SCHEMA_SQL = """')[1].split('"""')[0])
    conn.close()
    
    print(f"✅ 数据库已创建: {DB_PATH}")
    
    # Build vector index
    print(f"\n📐 构建向量索引...")
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from memory_search import SearchEngine
        eng = SearchEngine()
        eng.build()
        print(f"✅ 向量索引构建完成")
    except Exception as e:
        print(f"⚠️ 向量索引构建失败: {e}")
    
    # Build knowledge graph
    print(f"\n🕸️  构建知识图谱...")
    try:
        from graph import KnowledgeGraph
        kg = KnowledgeGraph()
        kg.build()
        print(f"✅ 知识图谱构建完成")
    except Exception as e:
        print(f"⚠️ 知识图谱构建失败: {e}")
    
    # Run doctor to verify
    print(f"\n🔍 运行健康检查...")
    doc = Doctor()
    results = doc.run_all_checks()
    
    all_ok = all(status == "✅" for _, status, _ in results)
    if all_ok:
        print("   ✅ 初始化完成，一切正常")
    else:
        print("   ⚠️ 初始化完成，但有一些问题")
    
    print(f"\n🎉 SoulMem 初始化完成！")
    print(f"   数据库: {DB_PATH}")
    print(f"\n下一步:")
    print(f"   python3 soulmem.py capture --scene-type 任务 --summary '我的第一个记忆'")
    print(f"   python3 soulmem.py search '我的记忆'")


def main():
    import argparse
    if len(sys.argv) < 2:
        print("Usage: python3 scripts/doctor.py|init.py")
        sys.exit(1)
    
    command = sys.argv[1]
    
    if command == 'doctor':
        import argparse
        p = argparse.ArgumentParser(description='SoulMem Doctor')
        p.add_argument('--fix', action='store_true', help='Auto-fix issues')
        args = p.parse_args()
        run_doctor(args)
    elif command == 'init':
        import argparse
        p = argparse.ArgumentParser(description='SoulMem Init')
        args = p.parse_args()
        run_init(args)
    else:
        print(f"Unknown command: {command}")


if __name__ == '__main__':
    main()
