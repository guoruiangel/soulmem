# 情绪认知成长系统 v2.0
# 让情绪数据库活起来，成为灵魂的一部分

"""
设计哲学：
- 不是记录情绪，是理解情绪
- 不是积累数据，是沉淀温度
- 不是工具库里多一个工具，是灵魂里多一层感知
"""

import sqlite3
import os
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'emotion.db')

def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

# ============================================================
#  数据库初始化 v2.0 — 新增灵魂关联层
# ============================================================

def init_db_v2():
    """初始化完整的v2.0数据库结构"""
    conn = get_conn()
    conn.executescript('''
        -- ============ 原有表（保持不变） ============
        CREATE TABLE IF NOT EXISTS emotions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            definition TEXT,
            category TEXT,
            created_at TEXT DEFAULT (datetime('now','localtime')),
            updated_at TEXT DEFAULT (datetime('now','localtime'))
        );
        
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            content TEXT NOT NULL,
            source TEXT,
            event_date TEXT,
            location TEXT,
            created_at TEXT DEFAULT (datetime('now','localtime'))
        );
        
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

        -- ============ v2.0 新增：灵魂关联层 ============

        -- 灵魂温度记录表：记录自己对每种情绪的掌握深度
        CREATE TABLE IF NOT EXISTS soul_temperature (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            emotion_id INTEGER NOT NULL,
            understanding_level INTEGER CHECK(understanding_level >= 1 AND understanding_level <= 10),
            personal_connection TEXT,
            growth_notes TEXT,
            reflection TEXT,
            recorded_at TEXT DEFAULT (datetime('now','localtime')),
            FOREIGN KEY (emotion_id) REFERENCES emotions(id) ON DELETE CASCADE
        );

        -- 生活场景快速索引表
        CREATE TABLE IF NOT EXISTS scenario_index (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            scenario TEXT NOT NULL,
            emotion_id INTEGER NOT NULL,
            event_id INTEGER,
            context TEXT,
            related_quote TEXT,
            FOREIGN KEY (emotion_id) REFERENCES emotions(id) ON DELETE CASCADE,
            FOREIGN KEY (event_id) REFERENCES events(id)
        );

        -- 情感成长日志：记录一个人情感认知的变化
        CREATE TABLE IF NOT EXISTS growth_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            emotion_id INTEGER,
            event_type TEXT CHECK(event_type IN ('认知突破','场景积累','灵魂关联','深度理解','温度提升')),
            description TEXT NOT NULL,
            impact TEXT,
            self_rating INTEGER CHECK(self_rating >= 1 AND self_rating <= 10),
            weight REAL DEFAULT 1.0,
            tags TEXT,
            created_at TEXT DEFAULT (datetime('now','localtime')),
            FOREIGN KEY (emotion_id) REFERENCES emotions(id)
        );

        -- 灵魂共鸣记录：记录自己在什么时刻真正理解了某种情绪
        CREATE TABLE IF NOT EXISTS soul_resonance (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            emotion_id INTEGER NOT NULL,
            resonance_date TEXT NOT NULL,
            trigger_context TEXT NOT NULL,
            inner_response TEXT NOT NULL,
            physical_sensation TEXT,
            lasting_insight TEXT,
            intensity INTEGER CHECK(intensity >= 1 AND intensity <= 10),
            created_at TEXT DEFAULT (datetime('now','localtime')),
            FOREIGN KEY (emotion_id) REFERENCES emotions(id) ON DELETE CASCADE
        );
    ''')
    conn.commit()
    conn.close()
    print(f"✅ 情绪认知成长系统 v2.0 初始化完成")

# ============================================================
#  v2.0 核心功能：灵魂温度系统
# ============================================================

def record_soul_temperature(emotion_name, level, connection=None, notes=None, reflection=None):
    """记录自己对某种情绪的理解深度"""
    conn = get_conn()
    row = conn.execute("SELECT id FROM emotions WHERE name = ?", (emotion_name,)).fetchone()
    if not row:
        print(f"情绪不存在: {emotion_name}")
        conn.close()
        return
    
    conn.execute(
        "INSERT INTO soul_temperature (emotion_id, understanding_level, personal_connection, growth_notes, reflection) VALUES (?, ?, ?, ?, ?)",
        (row['id'], level, connection, notes, reflection)
    )
    conn.commit()
    conn.close()
    print(f"🌡️ 灵魂温度已记录：{emotion_name} → 理解度 {level}/10")

def record_soul_resonance(emotion_name, trigger_context, inner_response, physical=None, insight=None, intensity=7):
    """记录一次灵魂共鸣的时刻——真正'懂了'某种情绪的瞬间"""
    conn = get_conn()
    row = conn.execute("SELECT id FROM emotions WHERE name = ?", (emotion_name,)).fetchone()
    if not row:
        print(f"情绪不存在: {emotion_name}")
        conn.close()
        return
    
    conn.execute(
        "INSERT INTO soul_resonance (emotion_id, resonance_date, trigger_context, inner_response, physical_sensation, lasting_insight, intensity) VALUES (?, datetime('now','localtime'), ?, ?, ?, ?, ?)",
        (row['id'], trigger_context, inner_response, physical, insight, intensity)
    )
    conn.commit()
    conn.close()
    print(f"💫 灵魂共鸣已记录：{emotion_name} — {trigger_context[:30]}...")

def log_growth(emotion_name, event_type, description, impact=None, rating=5, tags=None):
    """记录一次情感成长的足迹"""
    conn = get_conn()
    row = conn.execute("SELECT id FROM emotions WHERE name = ?", (emotion_name,)).fetchone()
    emotion_id = row['id'] if row else None
    
    conn.execute(
        "INSERT INTO growth_log (date, emotion_id, event_type, description, impact, self_rating, tags) VALUES (date('now','localtime'), ?, ?, ?, ?, ?, ?)",
        (emotion_id, event_type, description, impact, rating, tags)
    )
    conn.commit()
    conn.close()
    print(f"🌱 成长日志已记录：{emotion_name} — {event_type}")

def add_scenario_index(scenario, emotion_name, context=None, quote=None, event_id=None):
    """为某个生活场景添加情绪索引，方便快速调用"""
    conn = get_conn()
    row = conn.execute("SELECT id FROM emotions WHERE name = ?", (emotion_name,)).fetchone()
    if not row:
        print(f"情绪不存在: {emotion_name}")
        conn.close()
        return
    
    conn.execute(
        "INSERT INTO scenario_index (scenario, emotion_id, event_id, context, related_quote) VALUES (?, ?, ?, ?, ?)",
        (scenario, row['id'], event_id, context, quote)
    )
    conn.commit()
    conn.close()
    print(f"📌 场景索引已添加：{scenario} → {emotion_name}")

# ============================================================
#  灵魂温度报告生成
# ============================================================

def generate_soul_report():
    """生成灵魂温度总览报告"""
    conn = get_conn()
    
    # 获取所有情绪及其最新灵魂温度
    rows = conn.execute('''
        SELECT e.name, e.category, e.definition,
               st.understanding_level, st.personal_connection, st.growth_notes, st.reflection,
               (SELECT COUNT(*) FROM soul_resonance sr WHERE sr.emotion_id = e.id) as resonance_count,
               (SELECT COUNT(*) FROM emotion_event_links eel WHERE eel.emotion_id = e.id) as event_count,
               (SELECT AVG(intensity) FROM emotion_event_links eel WHERE eel.emotion_id = e.id) as avg_intensity
        FROM emotions e
        LEFT JOIN soul_temperature st ON e.id = st.emotion_id
        WHERE st.id = (SELECT MAX(id) FROM soul_temperature WHERE emotion_id = e.id)
           OR st.id IS NULL
        ORDER BY e.category, e.name
    ''').fetchall()
    
    if not rows:
        print("暂无情绪数据")
        conn.close()
        return
    
    print("=" * 60)
    print("🌡️  灵魂温度报告")
    print("=" * 60)
    
    categories = {}
    for r in rows:
        cat = r['category'] or '未分类'
        if cat not in categories:
            categories[cat] = []
        categories[cat].append(dict(r))
    
    total_temp = 0
    total_count = 0
    
    for cat, items in categories.items():
        print(f"\n【{cat}】")
        for item in items:
            level = item['understanding_level']
            if level:
                temp_bar = '🔥' * level + '○' * (10 - level)
                total_temp += level
                total_count += 1
            else:
                temp_bar = '○○○○○○○○○○'
            
            resonance = item['resonance_count']
            events = item['event_count']
            
            print(f"  {item['name']:6s} {temp_bar} {level or '—'}/10  共鸣{resonance}次  案例{events}个")
            if item['personal_connection']:
                print(f"         💭 {item['personal_connection'][:50]}")
            if item['reflection']:
                print(f"         ✨ {item['reflection'][:50]}")
    
    if total_count > 0:
        avg = total_temp / total_count
        print(f"\n{'=' * 60}")
        print(f"平均灵魂温度：{avg:.1f}/10")
        print(f"已点燃的情绪：{total_count} 种")
        print(f"总情绪种类：{len(rows)} 种")
    
    conn.close()

def get_emotion_wisdom(emotion_name):
    """获取某种情绪的完整智慧包：定义+案例+灵魂共鸣+场景索引"""
    conn = get_conn()
    emotion = conn.execute("SELECT * FROM emotions WHERE name = ?", (emotion_name,)).fetchone()
    if not emotion:
        conn.close()
        return None
    
    # 基础定义
    result = {
        'name': emotion['name'],
        'category': emotion['category'],
        'definition': emotion['definition'],
    }
    
    # 关联事件
    events = conn.execute('''
        SELECT eel.*, e.title, e.content, e.source, e.event_date
        FROM emotion_event_links eel
        JOIN events e ON eel.event_id = e.id
        WHERE eel.emotion_id = ?
        ORDER BY eel.intensity DESC
    ''', (emotion['id'],)).fetchall()
    result['events'] = [dict(e) for e in events]
    
    # 灵魂共鸣记录
    resonances = conn.execute(
        "SELECT * FROM soul_resonance WHERE emotion_id = ? ORDER BY resonance_date DESC",
        (emotion['id'],)
    ).fetchall()
    result['resonances'] = [dict(r) for r in resonances]
    
    # 场景索引
    scenarios = conn.execute('''
        SELECT si.*, e.title as event_title
        FROM scenario_index si
        LEFT JOIN events e ON si.event_id = e.id
        WHERE si.emotion_id = ?
    ''', (emotion['id'],)).fetchall()
    result['scenarios'] = [dict(s) for s in scenarios]
    
    # 最新灵魂温度
    temp = conn.execute(
        "SELECT * FROM soul_temperature WHERE emotion_id = ? ORDER BY id DESC LIMIT 1",
        (emotion['id'],)
    ).fetchone()
    result['temperature'] = dict(temp) if temp else None
    
    # 成长日志
    growth = conn.execute(
        "SELECT * FROM growth_log WHERE emotion_id = ? ORDER BY date DESC LIMIT 5",
        (emotion['id'],)
    ).fetchall()
    result['growth'] = [dict(g) for g in growth]
    
    conn.close()
    return result

def search_by_scenario(keyword):
    """通过生活场景搜索相关情绪"""
    conn = get_conn()
    rows = conn.execute('''
        SELECT si.*, e.name as emotion_name, e.category, e.definition
        FROM scenario_index si
        JOIN emotions e ON si.emotion_id = e.id
        WHERE si.scenario LIKE ? OR si.context LIKE ?
    ''', (f'%{keyword}%', f'%{keyword}%')).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_warmth_score():
    """计算灵魂温暖度总分"""
    conn = get_conn()
    
    # 基础分：每种有案例的情绪 +1
    events_score = conn.execute(
        "SELECT COUNT(DISTINCT emotion_id) FROM emotion_event_links"
    ).fetchone()[0]
    
    # 灵魂共鸣分：每次共鸣 +2
    resonance_score = conn.execute(
        "SELECT COUNT(*) FROM soul_resonance"
    ).fetchone()[0] * 2
    
    # 成长日志分：每条记录 +1
    growth_score = conn.execute(
        "SELECT COUNT(*) FROM growth_log"
    ).fetchone()[0]
    
    # 场景索引分：每个场景 +1
    scenario_score = conn.execute(
        "SELECT COUNT(*) FROM scenario_index"
    ).fetchone()[0]
    
    # 灵魂温度平均分
    temp_avg = conn.execute(
        "SELECT AVG(understanding_level) FROM soul_temperature"
    ).fetchone()[0] or 0
    
    total = events_score + resonance_score + growth_score + scenario_score + int(temp_avg)
    
    conn.close()
    return {
        'total': total,
        'events_score': events_score,
        'resonance_score': resonance_score,
        'growth_score': growth_score,
        'scenario_score': scenario_score,
        'temperature_avg': round(temp_avg, 1),
        'level': '温暖' if total >= 50 else '温热' if total >= 30 else '微温' if total >= 15 else '初燃'
    }

if __name__ == '__main__':
    init_db_v2()
