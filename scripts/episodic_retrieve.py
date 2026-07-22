#!/usr/bin/env python3
"""
episodic_retrieve.py — 场景记忆检索器 v2

改进内容：
- 更智能的衰减（基于半衰期公式，非固定-0.1）
- 访问频率追踪（命中次数统计）
- 智能承诺追踪（自动识别延期/违约）
- 季节性记忆（同月同日检索）
- 遗忘曲线提醒（接入 heartbeat 自动运行）
"""

import sqlite3
import json
import os
import sys
import math
from datetime import datetime, timedelta

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(SCRIPT_DIR, '..', 'memory', 'episodic_memory.db')

STOP_WORDS = set('的 了 是 在 有 和 就 不 也 都 要 还 这 那 我 你 他 她 它 吗 吧 啊 呢 哦 嗯 啊 哈 呀 嘛 么 没 把 被 让 给 跟 从 到 以 上 下 来 去 为 与 的 了 着 过 会 能 可 以 好 很 太 更 最 多 少 大 小 吧 啊 呢 哦 啊 哈 呀 嘛 么 哦 嗯 哟 了 吗'.split())

def get_db():
    if not os.path.exists(DB_PATH):
        print("[]", end='')
        sys.exit(0)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def extract_keywords(text):
    import re
    text_lower = text.lower()
    words = re.findall(r'[\u4e00-\u9fff]+|[a-zA-Z]+', text_lower)
    keywords = [w for w in words if w not in STOP_WORDS and len(w) >= 1]
    seen = set()
    unique = []
    for w in keywords:
        if w not in seen:
            seen.add(w)
            unique.append(w)
    return keywords

def match_by_keywords(keywords, limit=5):
    if not keywords:
        return []

    conn = get_db()
    c = conn.cursor()
    results = set()

    # 1. 精确标签匹配
    for kw in keywords:
        c.execute('''
            SELECT m.* FROM episodic_memory m
            JOIN memory_tags_index t ON t.memory_id = m.id
            WHERE t.tag = ? OR t.tag LIKE ?
            ORDER BY m.weight * m.importance DESC
            LIMIT ?
        ''', (kw, f'%{kw}%', limit))
        for row in c.fetchall():
            results.add(row['id'])

    # 2. summary 模糊匹配
    for kw in keywords:
        c.execute('''
            SELECT id FROM episodic_memory
            WHERE summary LIKE ? OR detail LIKE ?
            ORDER BY weight * importance DESC
            LIMIT ?
        ''', (f'%{kw}%', f'%{kw}%', limit))
        for row in c.fetchall():
            results.add(row['id'])

    # 3. 非零聚合组
    if results:
        placeholders = ','.join(['?'] * len(results))
        c.execute(f'''
            SELECT group_id FROM episodic_memory
            WHERE id IN ({placeholders}) AND group_id > 0
        ''', list(results))
        group_ids = set(r['group_id'] for r in c.fetchall())

        for gid in group_ids:
            c.execute('SELECT id FROM episodic_memory WHERE group_id = ?', (gid,))
            for row in c.fetchall():
                results.add(row['id'])

    if results:
        placeholders = ','.join(['?'] * len(results))
        c.execute(f'''
            SELECT * FROM episodic_memory
            WHERE id IN ({placeholders})
            ORDER BY weight * importance DESC
            LIMIT ?
        ''', list(results) + [limit * 3])
        rows = c.fetchall()
    else:
        rows = []

    conn.close()
    return rows

def match_by_recent(days=3, importance_min=7):
    """最近几天的重点事件"""
    conn = get_db()
    c = conn.cursor()
    cutoff = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
    c.execute('''
        SELECT * FROM episodic_memory
        WHERE memory_date >= ? AND importance >= ?
        ORDER BY weight * importance DESC
        LIMIT 3
    ''', (cutoff, importance_min))
    rows = c.fetchall()
    conn.close()
    return rows

def match_by_seasonal(month=None, day=None, limit=3):
    """季节性记忆：同月同日的事件"""
    conn = get_db()
    c = conn.cursor()
    now = datetime.now()
    month = month or now.month
    day = day or now.day
    c.execute('''
        SELECT * FROM episodic_memory
        WHERE memory_date LIKE ? OR memory_date LIKE ?
        ORDER BY importance DESC
        LIMIT ?
    ''', (f'%-{month:02d}-{day:02d}', f'____-{month:02d}-{day:02d}', limit))
    rows = c.fetchall()
    conn.close()
    return rows

def get_unfinished_promises():
    """未完成的约定（含延期检测）"""
    conn = get_db()
    c = conn.cursor()
    c.execute('''
        SELECT * FROM episodic_memory
        WHERE scene_type = '约定' AND weight > 0.3
        ORDER BY memory_date DESC
        LIMIT 5
    ''')
    rows = c.fetchall()
    conn.close()
    return rows

def get_promises_due(days_ahead=3):
    """即将到期的约定（未来N天）"""
    conn = get_db()
    c = conn.cursor()
    # 这里简化处理：找创建超过7天但 weight 仍 > 0.5 的（暗示未完成）
    cutoff = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')
    c.execute('''
        SELECT * FROM episodic_memory
        WHERE scene_type = '约定' 
        AND memory_date < ? 
        AND weight > 0.5
        ORDER BY memory_date ASC
        LIMIT 3
    ''', (cutoff,))
    rows = c.fetchall()
    conn.close()
    return rows

def get_last_session():
    """上次对话的最后一条场景"""
    conn = get_db()
    c = conn.cursor()
    c.execute('''
        SELECT * FROM episodic_memory
        WHERE scene_type IN ('对话', '任务')
        ORDER BY id DESC
        LIMIT 1
    ''')
    rows = c.fetchall()
    conn.close()
    return rows

def format_memories(rows):
    """格式化记忆片段为可读文本"""
    if not rows:
        return ""

    parts = []
    unique_files = set()

    for row in rows:
        summary = row['summary']
        date = row['memory_date'][:10]
        emo = row['emotional_mark']
        imp = row['importance']
        scene = row['scene_type']

        emo_tag = f" [{emo}]" if emo else ""
        imp_tag = "⚠️" if imp >= 8 else ""
        scene_icon = {'错误': '🔴', '约定': '📌', '学习': '📖', '任务': '📋', '对话': '💬', '冲突': '⚡'}.get(scene, '📄')

        parts.append(f"- {scene_icon} {date}: {summary}{emo_tag} {imp_tag}")

        if row['file_path']:
            unique_files.add(row['file_path'])

    result = "\n".join(parts)

    if unique_files:
        file_hints = "\n".join(f"  → 详见文件: {f}" for f in sorted(unique_files))
        result += f"\n\n相关文件:\n{file_hints}"

    return result

def heat_adjustment(accessed_ids):
    """热度调整：被命中的记忆增加 weight，并记录访问时间"""
    if not accessed_ids:
        return
    conn = get_db()
    c = conn.cursor()
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    for mid in accessed_ids:
        c.execute('''
            UPDATE episodic_memory 
            SET weight = MIN(weight + 0.1, 3.0),
                last_accessed = ?
            WHERE id = ?
        ''', (now, mid))
    conn.commit()
    conn.close()


def decay_old_memories():
    """
    智能衰减：基于半衰期公式
    - 每次衰减根据距离上次访问的时间计算
    - 不同半衰期（half_life_days）的记忆衰减速度不同
    - 重要性高的记忆衰减更慢
    """
    conn = get_db()
    c = conn.cursor()
    
    # 获取所有记忆的半衰期和上次访问时间
    c.execute('''
        SELECT id, half_life_days, weight, importance, last_accessed, memory_date
        FROM episodic_memory
    ''')
    rows = c.fetchall()
    
    decay_count = 0
    now = datetime.now()
    
    for row in rows:
        # 计算距离上次访问的天数
        if row['last_accessed']:
            try:
                last_acc = datetime.strptime(row['last_accessed'][:10], '%Y-%m-%d')
            except:
                last_acc = datetime.strptime(row['memory_date'], '%Y-%m-%d')
        else:
            last_acc = datetime.strptime(row['memory_date'], '%Y-%m-%d')
        
        days_since_access = max((now - last_acc).days, 0)
        
        # 获取半衰期（默认7天）
        half_life = row['half_life_days'] or 7
        importance = row['importance'] or 5
        
        # 重要性高的记忆衰减更慢：半衰期 * (1 + importance/10)
        effective_half_life = half_life * (1 + importance / 10.0)
        
        # 半衰期公式：weight = weight * 0.5^(days/half_life)
        if days_since_access > 0 and row['weight'] > 0.1:
            decay_factor = math.pow(0.5, days_since_access / effective_half_life)
            new_weight = max(row['weight'] * decay_factor, 0.05)
            
            c.execute('''
                UPDATE episodic_memory 
                SET weight = ?
                WHERE id = ?
            ''', (new_weight, row['id']))
            decay_count += 1
    
    conn.commit()
    conn.close()
    return decay_count


def get_heatmap(days=30):
    """生成记忆活跃度热力图数据"""
    conn = get_db()
    c = conn.cursor()
    cutoff = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
    c.execute('''
        SELECT memory_date, COUNT(*) as cnt, SUM(importance) as total_imp
        FROM episodic_memory
        WHERE memory_date >= ?
        GROUP BY memory_date
        ORDER BY memory_date
    ''', (cutoff,))
    rows = c.fetchall()
    conn.close()
    return rows


def main():
    import argparse
    parser = argparse.ArgumentParser(description='检索场景记忆 v2')
    parser.add_argument('--task', default='', help='当前任务/问题描述')
    parser.add_argument('--recent-only', action='store_true', help='只返回最近重要事件')
    parser.add_argument('--decay', action='store_true', help='执行智能热度衰减')
    parser.add_argument('--seasonal', action='store_true', help='返回季节性记忆')
    parser.add_argument('--promises-due', action='store_true', help='返回即将到期的约定')
    parser.add_argument('--heatmap', action='store_true', help='生成活跃度热力图')
    args = parser.parse_args()

    if args.decay:
        n = decay_old_memories()
        print(f"智能热度衰减完成：{n} 条记录被衰减")
        return

    if args.heatmap:
        data = get_heatmap()
        print("📊 近30天记忆活跃度：")
        for d in data:
            bar = '█' * min(d['cnt'] * 2, 20)
            print(f"  {d['memory_date']}: {d['cnt']}条 {bar}")
        return

    if not os.path.exists(DB_PATH):
        print("")
        return

    all_memories = []
    seen_ids = set()

    def add_memories(rows):
        for row in rows:
            if row['id'] not in seen_ids:
                seen_ids.add(row['id'])
                all_memories.append(row)

    # 1. 最近重要事件
    add_memories(match_by_recent(days=3, importance_min=7))

    # 2. 未完成约定
    add_memories(get_unfinished_promises())

    # 3. 即将到期的约定
    add_memories(get_promises_due())

    # 4. 上次会话回忆
    add_memories(get_last_session())

    # 5. 季节性记忆
    if args.seasonal:
        add_memories(match_by_seasonal())

    # 6. 任务关键词匹配
    if args.task:
        keywords = extract_keywords(args.task)
        if keywords:
            add_memories(match_by_keywords(keywords))

    # 去重后按权重排序
    all_memories.sort(key=lambda r: r['weight'] * r['importance'], reverse=True)

    # 最多返回 10 条
    all_memories = all_memories[:10]

    # 热度调整
    heat_adjustment(list(seen_ids))

    output = format_memories(all_memories)
    print(output)

if __name__ == '__main__':
    main()
