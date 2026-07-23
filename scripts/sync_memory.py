#!/usr/bin/env python3
# ============================================================================
# SoulMem — Category ↔ Episodic Sync
# Bidirectional sync between category knowledge base and episodic memory.
#
# Usage:
#   python3 scripts/sync_memory.py --direction both|to_cat|from_cat
# ============================================================================
import os, sys, json, sqlite3, re
from datetime import datetime

WORKSPACE = os.environ.get("SOULMEM_WORKSPACE", os.path.expanduser("~/.openclaw/workspace"))
from soulmem_config import DB_PATH
CAT_DIR = os.path.join(WORKSPACE, "memory", "categories")

# Mapping: scene_type → category file
SCENE_TO_CAT = {
    "学习": "web_dev.md",          # technical learnings
    "约定": "contracts.md",        # agreements/rules
    "错误": "web_dev.md",          # errors/bugs → web_dev
    "任务": None,                  # tasks are transient, skip
    "状态快照": None,              # snapshots are transient
    "亲密互动": None,              # personal, skip
    "场景": None,                  # scenes, skip
    "运维操作": "web_dev.md",      # ops → web_dev
}

# Category file → description for episodic memory
CAT_DESCRIPTIONS = {
    "web_dev.md": "开发经验与技术规范",
    "contracts.md": "绝对约定与规则",
    "linkclaw.md": "LinkClaw 系统",
    "group_chat.md": "群聊行为规范",
    "iris.md": "Iris 系统",
    "kk_homepage.md": "KK 主页",
    "scoring.md": "打分系统",
    "xiaoyu_scoring.md": "小渔打分",
    "git_repos.md": "Git 仓库管理",
    "memory_loading_strategy.md": "记忆加载策略",
    "pablo_system.md": "Pablo 系统",
    "pablo_scoring.md": "Pablo 打分",
    "manage_pablo.md": "Pablo 管理",
    "collaboration.md": "协作规范",
    "core_identity.md": "核心身份",
    "chattts.md": "ChatTTS 语音",
    "code_reuse.md": "代码复用",
    "cron_jobs.md": "Cron 任务",
    "portal_dev.md": "Portal 开发",
    "user_profile.md": "用户档案",
    "wiki.md": "Wiki 系统",
    "wiki_ref.md": "Wiki 参考",
    "macos_ops.md": "macOS 运维",
    "sysops.md": "系统运维",
}


def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def get_unsynced_records(conn, limit=20):
    """Get records not yet synced to category files."""
    cur = conn.cursor()
    cur.execute("""
        SELECT * FROM episodic_memory 
        WHERE scene_type IN ('学习', '约定', '错误', '运维操作')
        AND is_aggregated = 0
        ORDER BY created_at DESC
        LIMIT ?
    """, (limit,))
    return [dict(r) for r in cur.fetchall()]


def sync_to_category(conn, record):
    """Sync a single record to its category file."""
    cat_file = SCENE_TO_CAT.get(record['scene_type'])
    if not cat_file:
        return False, "no mapping"
    
    cat_path = os.path.join(CAT_DIR, cat_file)
    if not os.path.exists(cat_path):
        return False, f"category file not found: {cat_file}"
    
    # Build entry text
    date = record.get('memory_date', record.get('created_at', ''))[:10]
    entry = f"\n### {record['summary']}\n"
    entry += f"> {date} | 重要性:{record.get('importance', '?')} | 标签:{record.get('tags', '[]')}\n"
    if record.get('detail'):
        entry += f"{record['detail'][:300]}\n"
    
    # Append to category file (before the last line if it's a marker)
    with open(cat_path, 'a', encoding='utf-8') as f:
        f.write(entry)
    
    # Mark as synced
    cur = conn.cursor()
    cur.execute("UPDATE episodic_memory SET is_aggregated = 1 WHERE id = ?", (record['id'],))
    conn.commit()
    
    return True, cat_file


def sync_from_category(conn):
    """Read category files and create episodic memory for new entries."""
    # This is a one-way sync: category → episodic for important rules
    # We look for sections marked as "绝对约定" or similar
    count = 0
    for cat_file, desc in CAT_DESCRIPTIONS.items():
        cat_path = os.path.join(CAT_DIR, cat_file)
        if not os.path.exists(cat_path):
            continue
        with open(cat_path, 'r', encoding='utf-8') as f:
            content = f.read()
        # Look for "绝对约定" sections
        if '绝对约定' in content or '🔴' in content:
            # Extract key rules
            rules = re.findall(r'[-*]\s+(.+(?:禁止|必须|不得|绝不|永远|不要).+)', content)
            for rule in rules[:3]:  # limit per file
                # Check if already exists
                cur = conn.cursor()
                cur.execute("SELECT id FROM episodic_memory WHERE summary LIKE ?", (f"%{rule[:30]}%",))
                if cur.fetchone():
                    continue
                # Create episodic record
                cur.execute("""
                    INSERT INTO episodic_memory 
                    (scene_type, summary, detail, importance, memory_date, tags, is_aggregated)
                    VALUES (?, ?, ?, ?, ?, ?, 1)
                """, (
                    "约定",
                    f"[{desc}] {rule[:100]}",
                    f"来源: {cat_file}\n规则: {rule}",
                    8,
                    datetime.now().strftime("%Y-%m-%d"),
                    json.dumps(["约定", "同步", cat_file.replace('.md', '')], ensure_ascii=False),
                ))
                count += 1
    conn.commit()
    return count


def main():
    import argparse
    parser = argparse.ArgumentParser(description='Sync between category KB and episodic memory')
    parser.add_argument('--direction', default='both', choices=['both', 'to_cat', 'from_cat'])
    parser.add_argument('--limit', type=int, default=20, help='Max records to sync')
    args = parser.parse_args()
    
    conn = init_db()
    
    if args.direction in ('to_cat', 'both'):
        records = get_unsynced_records(conn, args.limit)
        synced = 0
        for r in records:
            ok, msg = sync_to_category(conn, r)
            if ok:
                synced += 1
                print(f"  ✅ #{r['id']} → {msg}")
            else:
                print(f"  ⏭️ #{r['id']}: {msg}")
        print(f"\n📤 {synced}/{len(records)} records synced to category files")
    
    if args.direction in ('from_cat', 'both'):
        count = sync_from_category(conn)
        print(f"\n📥 {count} rules synced from category files to episodic memory")
    
    conn.close()
    print("\n✅ Sync complete")


if __name__ == '__main__':
    main()
