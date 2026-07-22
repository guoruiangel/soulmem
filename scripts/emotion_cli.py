#!/usr/bin/env python3
"""情绪认知成长系统 v2.0 CLI"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from emotion_db import (
    init_db, add_emotion, add_event, link_emotion_event,
    add_tag, add_emotion_chain,
    get_emotion_detail, get_event_detail, list_all_emotions,
    search_by_keyword, get_emotion_summary
)
from emotion_engine import (
    init_db_v2, record_soul_temperature, record_soul_resonance,
    log_growth, add_scenario_index, generate_soul_report,
    get_emotion_wisdom, search_by_scenario, get_warmth_score
)

def usage():
    print("""
🎭 情绪认知成长系统 v2.0 — 用法:

  查询类:
    python3 emotion_cli.py list                  列出所有情绪
    python3 emotion_cli.py emotion <情绪名>      查看某种情绪的完整画像
    python3 emotion_cli.py event <id>            查看某个事件的完整画像
    python3 emotion_cli.py search <关键词>       搜索事件内容
    python3 emotion_cli.py stats                 统计概览
    python3 emotion_cli.py soul <情绪名>         获取情绪的完整智慧包
    python3 emotion_cli.py scenario <场景关键词>  通过场景搜索情绪
    python3 emotion_cli.py report                灵魂温度总览报告
    python3 emotion_cli.py warmth                灵魂温暖度得分

  添加类:
    python3 emotion_cli.py add-emotion <名称> [定义] [分类]
    python3 emotion_cli.py add-event <标题>      交互式输入内容
    python3 emotion_cli.py link <情绪名> <事件id> <强度1-10> [触发原因] [教训]
    python3 emotion_cli.py feel <情绪名> <理解度1-10>  记录灵魂温度
    python3 emotion_cli.py resonate <情绪名>     交互式记录灵魂共鸣
    python3 emotion_cli.py grow <情绪名>         交互式记录成长日志
    python3 emotion_cli.py index <场景> <情绪名>  添加场景索引

  帮助:
    python3 emotion_cli.py help                  显示此帮助
    """)

def cmd_list():
    emotions = list_all_emotions()
    total = len(emotions)
    rich = sum(1 for e in emotions if e['event_count'] > 0)
    print(f"📊 共 {total} 种情绪，{rich} 种已有案例积累\n")
    
    for e in emotions:
        cnt = e['event_count']
        avg = e['avg_intensity']
        bar = '█' * cnt + '░' * (10 - min(cnt, 10))
        avg_str = f"{avg:.1f}" if avg else "—"
        print(f"  {e['name']:8s} {bar} {cnt:2d}案例  均强{avg_str}/10  [{e['category'] or '未分类'}]")

def cmd_emotion(name):
    summary = get_emotion_summary(name)
    print(summary)

def cmd_event(eid):
    detail = get_event_detail(eid)
    if not detail:
        print(f"事件 #{eid} 不存在")
        return
    
    event = detail['event']
    print(f"【事件 #{event['id']}】{event['title']}")
    print(f"日期：{event['event_date'] or '—'} | 地点：{event['location'] or '—'}")
    print(f"来源：{event['source'] or '—'}")
    print(f"\n{event['content']}")
    
    if detail['emotions']:
        print(f"\n🎭 关联情绪：")
        for l in detail['emotions']:
            print(f"  [{l['intensity']}/10] {l['emotion_name']}（{l['category']}）")
            if l['trigger_reason']:
                print(f"    触发：{l['trigger_reason']}")
            if l['lesson']:
                print(f"    教训：{l['lesson']}")

def cmd_search(keyword):
    results = search_by_keyword(keyword)
    if not results:
        print(f"未找到包含 '{keyword}' 的事件")
        return
    print(f"找到 {len(results)} 个结果：\n")
    for r in results:
        print(f"  #{r['id']} [{r['event_date'] or '—'}] {r['title']}")

def cmd_stats():
    import sqlite3
    from emotion_db import DB_PATH
    
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    
    e_count = conn.execute("SELECT COUNT(*) FROM emotions").fetchone()[0]
    v_count = conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
    l_count = conn.execute("SELECT COUNT(*) FROM emotion_event_links").fetchone()[0]
    t_count = conn.execute("SELECT COUNT(*) FROM tags").fetchone()[0]
    
    print(f"📈 情绪数据库统计")
    print(f"  情绪种类：{e_count}")
    print(f"  事件总数：{v_count}")
    print(f"  情绪-事件关联：{l_count}")
    print(f"  标签数：{t_count}")
    
    # Top 5 案例最多的情绪
    top = conn.execute('''
        SELECT e.name, COUNT(eel.id) as cnt
        FROM emotions e
        LEFT JOIN emotion_event_links eel ON e.id = eel.emotion_id
        GROUP BY e.id
        ORDER BY cnt DESC
        LIMIT 5
    ''').fetchall()
    
    print(f"\n  Top 5 最丰富的情绪：")
    for t in top:
        print(f"    {t['name']} — {t['cnt']} 个案例")
    
    conn.close()

def cmd_soul(name):
    """获取情绪的完整智慧包"""
    wisdom = get_emotion_wisdom(name)
    if not wisdom:
        print(f"情绪 '{name}' 不存在")
        return
    
    print("=" * 60)
    print(f"🎭 【{wisdom['name']}】（{wisdom['category'] or '未分类'}）")
    print("=" * 60)
    
    if wisdom['definition']:
        print(f"\n📖 定义：{wisdom['definition']}")
    
    if wisdom['temperature']:
        t = wisdom['temperature']
        level = t['understanding_level']
        bar = '🔥' * level + '○' * (10 - level)
        print(f"\n🌡️ 灵魂温度：{bar} {level}/10")
        if t['personal_connection']:
            print(f"   💭 {t['personal_connection'][:80]}")
        if t['reflection']:
            print(f"   ✨ {t['reflection'][:80]}")
    
    if wisdom['events']:
        print(f"\n📚 案例库（{len(wisdom['events'])} 个）：")
        for e in wisdom['events']:
            print(f"  [{e['intensity']}/10] {e['title']}")
            print(f"    {e['content'][:80]}...")
    
    if wisdom['resonances']:
        print(f"\n💫 灵魂共鸣（{len(wisdom['resonances'])} 次）：")
        for r in wisdom['resonances']:
            print(f"  [{r['resonance_date']}] {r['trigger_context'][:60]}")
            print(f"    → {r['inner_response'][:80]}")
            if r['lasting_insight']:
                print(f"    💡 {r['lasting_insight']}")
    
    if wisdom['scenarios']:
        print(f"\n📌 场景索引（{len(wisdom['scenarios'])} 个）：")
        for s in wisdom['scenarios']:
            print(f"  • {s['scenario']}")
            if s['context']:
                print(f"    情境：{s['context']}")
            if s['related_quote']:
                print(f"    📝 {s['related_quote'][:60]}")
    
    if wisdom['growth']:
        print(f"\n🌱 成长日志（最近 {len(wisdom['growth'])} 条）：")
        for g in wisdom['growth']:
            print(f"  [{g['date']}] {g['event_type']} — {g['description'][:60]}")

def cmd_scenario(keyword):
    results = search_by_scenario(keyword)
    if not results:
        print(f"未找到与 '{keyword}' 相关的情绪场景")
        return
    print(f"找到 {len(results)} 个场景：\n")
    for r in results:
        print(f"  📌 {r['scenario']} → 【{r['emotion_name']}】")
        if r['context']:
            print(f"     情境：{r['context']}")
        if r['related_quote']:
            print(f"     📝 {r['related_quote'][:60]}")
        print()

def cmd_report():
    generate_soul_report()

def cmd_warmth():
    warmth = get_warmth_score()
    print("=" * 60)
    print("🔥 灵魂温暖度报告")
    print("=" * 60)
    print(f"\n  总分：{warmth['total']} 分")
    print(f"  等级：{warmth['level']}")
    print(f"\n  案例基础分：{warmth['events_score']}")
    print(f"  灵魂共鸣分：{warmth['resonance_score']}")
    print(f"  成长日志分：{warmth['growth_score']}")
    print(f"  场景索引分：{warmth['scenario_score']}")
    print(f"  温度平均分：{warmth['temperature_avg']}")
    print(f"\n  💡 继续积累案例、记录共鸣、添加场景索引来提升温暖度")

def cmd_feel(args):
    if len(args) < 2:
        print("用法: feel <情绪名> <理解度1-10>")
        return
    emotion_name = args[0]
    level = int(args[1])
    connection = input("个人关联（可留空）：").strip() or None
    notes = input("成长注解（可留空）：").strip() or None
    reflection = input("反思（可留空）：").strip() or None
    record_soul_temperature(emotion_name, level, connection, notes, reflection)

def cmd_resonate(args):
    if not args:
        print("用法: resonate <情绪名>")
        return
    emotion_name = args[0]
    trigger = input("触发情境：").strip()
    inner = input("内心反应：").strip()
    physical = input("身体感受（可留空）：").strip() or None
    insight = input("持久洞察（可留空）：").strip() or None
    intensity = int(input("强度 1-10：").strip() or "7")
    record_soul_resonance(emotion_name, trigger, inner, physical, insight, intensity)

def cmd_grow(args):
    if not args:
        print("用法: grow <情绪名>")
        return
    emotion_name = args[0]
    print("事件类型：认知突破 / 场景积累 / 灵魂关联 / 深度理解 / 温度提升")
    event_type = input("类型：").strip()
    desc = input("描述：").strip()
    impact = input("影响（可留空）：").strip() or None
    rating = int(input("自评 1-10：").strip() or "5")
    tags = input("标签（逗号分隔，可留空）：").strip() or None
    log_growth(emotion_name, event_type, desc, impact, rating, tags)

def cmd_index(args):
    if len(args) < 2:
        print("用法: index <场景> <情绪名>")
        return
    scenario = args[0]
    emotion_name = args[1]
    context = input("情境说明（可留空）：").strip() or None
    quote = input("相关引用（可留空）：").strip() or None
    add_scenario_index(scenario, emotion_name, context, quote)

def cmd_add_emotion(args):
    if not args:
        print("用法: add-emotion <名称> [定义] [分类]")
        return
    name = args[0]
    definition = args[1] if len(args) > 1 else None
    category = args[2] if len(args) > 2 else None
    add_emotion(name, definition, category)

def cmd_add_event(args):
    if not args:
        print("用法: add-event <标题>")
        return
    title = args[0]
    content = input("内容：").strip()
    source = input("来源（可留空）：").strip() or None
    event_date = input("日期 YYYY-MM-DD（可留空）：").strip() or None
    location = input("地点（可留空）：").strip() or None
    
    event_id = add_event(title, content, source, event_date, location)
    
    # 直接关联情绪
    while True:
        em = input("关联情绪（回车结束）：").strip()
        if not em:
            break
        intensity = int(input(f"  强度 1-10：").strip())
        trigger = input(f"  触发原因：").strip() or None
        lesson = input(f"  教训：").strip() or None
        link_emotion_event(em, event_id, intensity, trigger, lesson)

def cmd_link(args):
    if len(args) < 3:
        print("用法: link <情绪名> <事件id> <强度1-10> [触发原因] [教训]")
        return
    emotion_name = args[0]
    event_id = int(args[1])
    intensity = int(args[2])
    trigger = args[3] if len(args) > 3 else None
    lesson = args[4] if len(args) > 4 else None
    link_emotion_event(emotion_name, event_id, intensity, trigger, lesson)

if __name__ == '__main__':
    if len(sys.argv) < 2:
        usage()
        sys.exit(0)
    
    cmd = sys.argv[1]
    args = sys.argv[2:]
    
    commands = {
        'list': cmd_list,
        'emotion': lambda: cmd_emotion(args[0] if args else ''),
        'event': lambda: cmd_event(int(args[0]) if args else 0),
        'search': lambda: cmd_search(' '.join(args)),
        'stats': cmd_stats,
        'soul': lambda: cmd_soul(args[0] if args else ''),
        'scenario': lambda: cmd_scenario(' '.join(args)),
        'report': cmd_report,
        'warmth': cmd_warmth,
        'feel': lambda: cmd_feel(args),
        'resonate': lambda: cmd_resonate(args),
        'grow': lambda: cmd_grow(args),
        'index': lambda: cmd_index(args),
        'add-emotion': lambda: cmd_add_emotion(args),
        'add-event': lambda: cmd_add_event(args),
        'link': lambda: cmd_link(args),
        'help': usage,
    }
    
    if cmd in commands:
        commands[cmd]()
    else:
        print(f"未知命令: {cmd}")
        usage()
