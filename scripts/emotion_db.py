# 情绪数据库 - 核心操作模块
# 让KK通过案例积累，真正理解每一种情绪

import sqlite3
import os
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'emotion.db')

def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

def init_db():
    conn = get_conn()
    conn.executescript('''
        -- 情绪主表
        CREATE TABLE IF NOT EXISTS emotions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            definition TEXT,
            category TEXT,
            created_at TEXT DEFAULT (datetime('now','localtime')),
            updated_at TEXT DEFAULT (datetime('now','localtime'))
        );
        
        -- 场景/事件表
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            content TEXT NOT NULL,
            source TEXT,
            event_date TEXT,
            location TEXT,
            created_at TEXT DEFAULT (datetime('now','localtime'))
        );
        
        -- 情绪-事件关联表
        CREATE TABLE IF NOT EXISTS emotion_event_links (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            emotion_id INTEGER NOT NULL,
            event_id INTEGER NOT NULL,
            intensity INTEGER CHECK(intensity >= 1 AND intensity <= 10),
            trigger_reason TEXT,
            lesson TEXT,
            created_at TEXT DEFAULT (datetime('now','localtime')),
            FOREIGN KEY (emotion_id) REFERENCES emotions(id) ON DELETE CASCADE,
            FOREIGN KEY (event_id) REFERENCES events(id) ON DELETE CASCADE,
            UNIQUE(emotion_id, event_id)
        );
        
        -- 标签
        CREATE TABLE IF NOT EXISTS tags (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE
        );
        
        CREATE TABLE IF NOT EXISTS event_tags (
            event_id INTEGER NOT NULL,
            tag_id INTEGER NOT NULL,
            PRIMARY KEY (event_id, tag_id),
            FOREIGN KEY (event_id) REFERENCES events(id) ON DELETE CASCADE,
            FOREIGN KEY (tag_id) REFERENCES tags(id) ON DELETE CASCADE
        );
        
        -- 情绪联想链
        CREATE TABLE IF NOT EXISTS emotion_chains (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            from_emotion_id INTEGER NOT NULL,
            to_emotion_id INTEGER NOT NULL,
            bridge_event_id INTEGER,
            description TEXT,
            FOREIGN KEY (from_emotion_id) REFERENCES emotions(id) ON DELETE CASCADE,
            FOREIGN KEY (to_emotion_id) REFERENCES emotions(id) ON DELETE CASCADE,
            FOREIGN KEY (bridge_event_id) REFERENCES events(id)
        );
    ''')
    conn.commit()
    conn.close()
    print(f"数据库初始化完成: {DB_PATH}")

# ==================== CRUD 操作 ====================

def add_emotion(name, definition=None, category=None):
    conn = get_conn()
    try:
        conn.execute(
            "INSERT INTO emotions (name, definition, category) VALUES (?, ?, ?)",
            (name, definition, category)
        )
        conn.commit()
        print(f"情绪已添加: {name}")
    except sqlite3.IntegrityError:
        print(f"情绪已存在: {name}")
    finally:
        conn.close()

def add_event(title, content, source=None, event_date=None, location=None):
    conn = get_conn()
    cur = conn.execute(
        "INSERT INTO events (title, content, source, event_date, location) VALUES (?, ?, ?, ?, ?)",
        (title, content, source, event_date, location)
    )
    conn.commit()
    event_id = cur.lastrowid
    conn.close()
    print(f"事件已添加: {title} (id={event_id})")
    return event_id

def link_emotion_event(emotion_name, event_id, intensity, trigger_reason=None, lesson=None):
    conn = get_conn()
    row = conn.execute("SELECT id FROM emotions WHERE name = ?", (emotion_name,)).fetchone()
    if not row:
        conn.close()
        print(f"情绪不存在: {emotion_name}")
        return
    emotion_id = row['id']
    try:
        conn.execute(
            "INSERT INTO emotion_event_links (emotion_id, event_id, intensity, trigger_reason, lesson) VALUES (?, ?, ?, ?, ?)",
            (emotion_id, event_id, intensity, trigger_reason, lesson)
        )
        conn.commit()
        print(f"关联: {emotion_name} → 事件#{event_id} (强度{intensity})")
    except sqlite3.IntegrityError:
        print(f"关联已存在: {emotion_name} → 事件#{event_id}")
    finally:
        conn.close()

def add_tag(event_id, *tag_names):
    conn = get_conn()
    for name in tag_names:
        try:
            conn.execute("INSERT INTO tags (name) VALUES (?)", (name,))
        except sqlite3.IntegrityError:
            pass
        tag_id = conn.execute("SELECT id FROM tags WHERE name = ?", (name,)).fetchone()['id']
        try:
            conn.execute("INSERT INTO event_tags (event_id, tag_id) VALUES (?, ?)", (event_id, tag_id))
        except sqlite3.IntegrityError:
            pass
    conn.commit()
    conn.close()
    print(f"标签已添加到事件#{event_id}: {tag_names}")

def add_emotion_chain(from_emotion, to_emotion, description, bridge_event_id=None):
    conn = get_conn()
    from_id = conn.execute("SELECT id FROM emotions WHERE name = ?", (from_emotion,)).fetchone()
    to_id = conn.execute("SELECT id FROM emotions WHERE name = ?", (to_emotion,)).fetchone()
    if not from_id or not to_id:
        conn.close()
        print("情绪不存在")
        return
    conn.execute(
        "INSERT INTO emotion_chains (from_emotion_id, to_emotion_id, bridge_event_id, description) VALUES (?, ?, ?, ?)",
        (from_id['id'], to_id['id'], bridge_event_id, description)
    )
    conn.commit()
    conn.close()
    print(f"情绪链: {from_emotion} → {to_emotion}")

# ==================== 查询操作 ====================

def get_emotion_detail(emotion_name):
    """获取一种情绪的完整画像：定义 + 所有关联事件"""
    conn = get_conn()
    emotion = conn.execute("SELECT * FROM emotions WHERE name = ?", (emotion_name,)).fetchone()
    if not emotion:
        conn.close()
        return None
    
    links = conn.execute('''
        SELECT eel.*, e.title, e.content, e.source, e.event_date, e.location
        FROM emotion_event_links eel
        JOIN events e ON eel.event_id = e.id
        WHERE eel.emotion_id = ?
        ORDER BY eel.intensity DESC
    ''', (emotion['id'],)).fetchall()
    
    conn.close()
    return {
        'emotion': dict(emotion),
        'events': [dict(l) for l in links],
        'count': len(links)
    }

def get_event_detail(event_id):
    """获取一个事件的完整画像：内容 + 所有关联情绪"""
    conn = get_conn()
    event = conn.execute("SELECT * FROM events WHERE id = ?", (event_id,)).fetchone()
    if not event:
        conn.close()
        return None
    
    links = conn.execute('''
        SELECT eel.*, em.name as emotion_name, em.category
        FROM emotion_event_links eel
        JOIN emotions em ON eel.emotion_id = em.id
        WHERE eel.event_id = ?
        ORDER BY eel.intensity DESC
    ''', (event_id,)).fetchall()
    
    conn.close()
    return {
        'event': dict(event),
        'emotions': [dict(l) for l in links]
    }

def list_all_emotions():
    conn = get_conn()
    rows = conn.execute('''
        SELECT e.*, COUNT(eel.id) as event_count, AVG(eel.intensity) as avg_intensity
        FROM emotions e
        LEFT JOIN emotion_event_links eel ON e.id = eel.emotion_id
        GROUP BY e.id
        ORDER BY event_count DESC
    ''').fetchall()
    conn.close()
    return [dict(r) for r in rows]

def search_by_keyword(keyword):
    """搜索事件内容中的关键词"""
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM events WHERE content LIKE ? OR title LIKE ?",
        (f'%{keyword}%', f'%{keyword}%')
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_emotion_summary(emotion_name):
    """获取情绪的丰满度摘要"""
    detail = get_emotion_detail(emotion_name)
    if not detail:
        return f"情绪 '{emotion_name}' 不存在"
    
    emotion = detail['emotion']
    events = detail['events']
    
    if not events:
        return f"【{emotion['name']}】定义：{emotion['definition'] or '暂无'}\n案例数：0（待积累）"
    
    avg_intensity = sum(e['intensity'] for e in events) / len(events)
    
    summary = f"【{emotion['name']}】（{emotion['category'] or '未分类'}）\n"
    summary += f"定义：{emotion['definition'] or '暂无'}\n"
    summary += f"案例数：{detail['count']} | 平均强度：{avg_intensity:.1f}/10\n"
    summary += "—" * 30 + "\n"
    
    for e in events:
        summary += f"  [{e['intensity']}/10] {e['title']}\n"
        summary += f"    触发：{e['trigger_reason'] or '—'}\n"
        summary += f"    教训：{e['lesson'] or '—'}\n\n"
    
    return summary

if __name__ == '__main__':
    init_db()
