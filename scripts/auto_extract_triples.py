#!/usr/bin/env python3
# ============================================================================
# SoulMem — Auto Causal Tag Extraction
# Automatically extracts symptom-cause-solution triples from error memories
# using keyword patterns and LLM-free heuristics.
#
# Usage:
#   python3 scripts/auto_extract_triangles.py --memory-id 42
#   python3 scripts/auto_extract_triangles.py --all
# ============================================================================
import os, sys, json, sqlite3, re
from datetime import datetime

WORKSPACE = os.environ.get("SOULMEM_WORKSPACE", os.path.expanduser("~/.openclaw/workspace"))
DB_PATH = os.path.join(WORKSPACE, "memory", "episodic_memory.db")

# Symptom keywords (what went wrong)
SYMPTOM_PATTERNS = [
    (r'(错误|报错|失败|error|ERROR|fail|FAIL|crash|exception)', '功能异常'),
    (r'(超时|timeout|TIMEOUT)', '超时问题'),
    (r'(不能|无法|没法|不行|不起作用|不工作)', '功能失效'),
    (r'(崩溃|crash|奔溃|挂掉|死掉)', '服务崩溃'),
    (r'(慢|卡顿|卡死|无响应|hang)', '性能问题'),
    (r'(连接不上|连不上|无法连接|connection refused|Connection refused)', '连接失败'),
    (r'(找不到|不存在|404|not found|No such file)', '资源缺失'),
    (r('|权限|禁止|403|forbidden|permission)', '权限问题'),
    (r'(数据丢失|数据损坏|损坏|corrupt)', '数据问题'),
    (r'(配置错误|配置不对|配置缺失|misconfiguration)', '配置问题'),
]

# Root cause keywords
CAUSE_PATTERNS = [
    (r'(缺少|缺失|丢失|not found|No such module|No module named)', '模块/文件缺失'),
    (r'(版本不兼容|版本冲突|version mismatch|incompatible)', '版本问题'),
    (r'(配置错误|配置参数|config|setting|parameter)', '配置错误'),
    (r'(数据库|SQLite|MySQL|postgres|db|database)', '数据库问题'),
    (r'(API|接口|endpoint|route|URL)', 'API问题'),
    (r'(服务|进程|process|service|daemon)', '服务未运行'),
    (r'(网络|network|connection|socket|TCP|HTTP)', '网络问题'),
    (r'(权限|permission|access|auth|token)', '权限/认证问题'),
    (r'(内存|memory|OOM|out of memory)', '内存问题'),
    (r'(并发|线程|thread|race condition|deadlock)', '并发问题'),
]

# Solution keywords  
SOLUTION_PATTERNS = [
    (r'(重启|restart|reboot)', '重启服务'),
    (r'(修复|fix|patch|modify|update|upgrade)', '修复代码'),
    (r'(配置|config|set|parameter|ENV|environment)', '修改配置'),
    (r'(安装|install|pip|npm|brew)', '安装依赖'),
    (r'(清理|clear|clean|flush|purge)', '清理缓存/数据'),
    (r'(回滚|rollback|revert|downgrade)', '版本回滚'),
    (r'(重建|rebuild|recreate|init)', '重建资源'),
]


def extract_causal_elements(text):
    """Extract symptom, cause, solution from text."""
    symptom = None
    cause = None
    solution = None
    
    for pattern, label in SYMPTOM_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            symptom = label
            break
    
    for pattern, label in CAUSE_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            cause = label
            break
    
    for pattern, label in SOLUTION_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            solution = label
            break
    
    return symptom, cause, solution


def auto_extract_from_memory(memory_id):
    """Extract triple from a single memory record."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    
    cur.execute("SELECT * FROM episodic_memory WHERE id = ?", (memory_id,))
    row = cur.fetchone()
    if not row:
        conn.close()
        return None
    
    text = f"{row['summary']} {row['detail']}"
    symptom, cause, solution = extract_causal_elements(text)
    
    if symptom and cause:
        # Check if triple already exists for this memory
        cur.execute("SELECT id FROM triples WHERE linked_memory_id = ?", (memory_id,))
        if cur.fetchone():
            conn.close()
            return None
        
        tags = json.loads(row['tags']) if row['tags'] else []
        tags.extend(['auto-extracted', cause])
        tags = list(set(tags))
        
        cur.execute("""
            INSERT INTO triples (symptom, cause, solution, tags, domain, confidence, linked_memory_id, source)
            VALUES (?, ?, ?, ?, ?, 0.6, ?, 'auto-extracted')
        """, (
            f"[{row['scene_type']}] {symptom} — {row['summary'][:60]}",
            cause,
            solution or '待补充',
            json.dumps(tags, ensure_ascii=False),
            row['scene_type'],
            memory_id
        ))
        conn.commit()
        triple_id = cur.lastrowid
        conn.close()
        return {
            'id': triple_id,
            'memory_id': memory_id,
            'symptom': symptom,
            'cause': cause,
            'solution': solution
        }
    
    conn.close()
    return None


def auto_extract_all():
    """Extract triples from all error/learning memories."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    
    cur.execute("""
        SELECT id FROM episodic_memory 
        WHERE scene_type IN ('错误', '学习', '任务')
        AND id NOT IN (SELECT linked_memory_id FROM triples WHERE linked_memory_id > 0)
    """)
    memory_ids = [row['id'] for row in cur.fetchall()]
    conn.close()
    
    results = []
    for mid in memory_ids:
        result = auto_extract_from_memory(mid)
        if result:
            results.append(result)
            print(f"  ✅ #{mid} → {result['symptom']} | {result['cause']}")
        else:
            print(f"  ⏭️ #{mid} → 无因果模式")
    
    return results


def main():
    import argparse
    p = argparse.ArgumentParser(description='Auto-extract causal triples from memories')
    p.add_argument('--memory-id', type=int, help='Extract from specific memory')
    p.add_argument('--all', action='store_true', help='Extract from all memories')
    args = p.parse_args()
    
    if args.memory_id:
        result = auto_extract_from_memory(args.memory_id)
        if result:
            print(f"✅ 提取成功: {result}")
        else:
            print(f"⏭️ 无因果模式或已存在")
    elif args.all:
        print("🔍 扫描所有错误/学习记忆...\n")
        results = auto_extract_all()
        print(f"\n✅ 共提取 {len(results)} 条因果三元组")
    else:
        p.print_help()


if __name__ == '__main__':
    main()
