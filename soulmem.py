#!/usr/bin/env python3
# ============================================================================
# SoulMem — Unified CLI
# Single entry point for all memory operations.
#
# Merged: Emotion Cognition System v2.0 (2026-07-22)
# Version: 2.2
#
# Usage:
#   soulmem search "query"           # hybrid search (BM25 + vector + heat)
#   soulmem capture [options]        # write a memory record
#   soulmem auto                     # auto-capture from latest transcript
#   soulmem stats                    # show memory statistics
#   soulmem build                    # build / rebuild vector index
#   soulmem graph build/show/related # knowledge graph operations
#   soulmem triples add/search/list  # symptom-cause-solution store
#   soulmem decay                    # run weight decay on stale memories
#   soulmem heat [--days 7]          # show file heat ranking
#   soulmem recent                   # show recent high-importance events
#   soulmem promises                 # show active promises
#   soulmem reviews [--days 30]      # show memories due for review
#   soulmem sync [--direction both]  # bidirectional category↔episodic sync
#   soulmem emotion <cmd>            # emotion cognition system v2.0
#
# Environment:
#   SOULMEM_WORKSPACE  (default: ~/.openclaw/workspace)
# ============================================================================

import os
import sys
import json
import argparse

SOULMEM_VERSION = "2.2"

# Ensure scripts/ and workspace are importable
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SCRIPTS_DIR = os.path.join(SCRIPT_DIR, "scripts")
WORKSPACE = os.environ.get("SOULMEM_WORKSPACE", os.path.expanduser("~/.openclaw/workspace"))
DB_PATH = os.path.join(WORKSPACE, "memory", "episodic_memory.db")
sys.path.insert(0, SCRIPTS_DIR)
scripts_dir = os.path.join(WORKSPACE, "scripts")
if scripts_dir != SCRIPTS_DIR:
    sys.path.insert(1, scripts_dir)


def cmd_search(args):
    """Hybrid search: BM25 + vector + heat, with TF-IDF fallback."""
    # Check if ollama is available
    ollama_available = False
    try:
        import urllib.request
        req = urllib.request.Request('http://localhost:11434/api/tags',
            headers={'Content-Type':'application/json'})
        urllib.request.urlopen(req, timeout=2)
        ollama_available = True
    except:
        pass
    
    if not ollama_available:
        # Fallback to TF-IDF search
        from memory_search_lite import MemorySearchLite
        searcher = MemorySearchLite()
        results = searcher.search(args.query, args.top)
        if not results:
            print("No results.")
            return
        print(f"🔍 '{args.query}' → {len(results)} results (TF-IDF mode, no ollama)\n")
        for i, r in enumerate(results, 1):
            print(f"  [{i}] ({r['scene_type']}) {r['summary']}")
            print(f"      {r['memory_date']} | BM25={r['bm25']} Cosine={r['cosine']} Heat={r['heat']} Score={r['score']}")
            if r.get('detail'):
                print(f"      {r['detail'][:150]}")
            print()
        return
    
    from memory_search import SearchEngine
    eng = SearchEngine()
    results = eng.search(args.query, args.top)
    if not results:
        print("No results.")
        return
    print(f"🔍 '{args.query}' → {len(results)} results\n")
    for i, r in enumerate(results, 1):
        print(f"  [{i}] ({r['scene_type']}) {r['summary']}")
        print(f"      {r['memory_date']} | BM25={r['bm25']} Vec={r['vec']} Heat={r['heat']} Score={r['score']}")
        if r.get('detail'):
            print(f"      {r['detail'][:150]}")
        print()


def cmd_capture(args):
    """Write a memory record, then incrementally update vector index + knowledge graph."""
    from episodic_capture import init_db, capture_record
    from memory_search import SearchEngine
    from graph import KnowledgeGraph

    conn = init_db()
    record_id = capture_record(
        conn,
        scene_type=args.scene_type,
        summary=args.summary,
        detail=args.detail or "",
        importance=args.importance,
        tags=args.tags or "[]",
        emotional_mark=args.emotional_mark or "",
        memory_date=args.memory_date,
        weight=args.weight,
    )
    conn.close()
    print(f"✅ 场景记忆已写入，ID={record_id}")

    # Incremental vector update
    try:
        eng = SearchEngine()
        eng.build_incremental(record_id)
        print("✅ 向量索引已增量更新")
    except Exception as e:
        print(f"⚠️ 向量索引更新失败: {e}")

    # Auto-index into knowledge graph
    try:
        kg = KnowledgeGraph()
        text = f"{args.summary} {args.detail or ''}"
        kg.index_memory(record_id, text)
        print("✅ 知识图谱已自动关联")
    except Exception as e:
        print(f"⚠️ 图谱关联失败: {e}")


def cmd_auto(args):
    """Auto-capture from latest session transcript."""
    from auto_capture import find_latest_session_transcript, auto_capture_from_transcript
    transcript = args.transcript or find_latest_session_transcript()
    if not transcript:
        print("❌ 未找到会话记录")
        return
    print(f"📄 读取: {transcript}")
    ok = auto_capture_from_transcript(transcript)
    if not ok:
        print("⚠️ 自动捕获未产生新记忆")


def cmd_stats(args):
    """Show memory database statistics."""
    if not os.path.exists(DB_PATH):
        print("❌ 数据库不存在")
        return
    import sqlite3
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    cur.execute("SELECT COUNT(*) FROM episodic_memory")
    total = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM mem_vec")
    vectored = cur.fetchone()[0]

    print(f"📊 SoulMem 统计")
    print(f"   总记忆数: {total}")
    print(f"   向量索引: {vectored}")
    print(f"   数据库:   {DB_PATH}")
    print()

    cur.execute("SELECT scene_type, COUNT(*) as cnt FROM episodic_memory GROUP BY scene_type ORDER BY cnt DESC")
    print("   分类分布:")
    for r in cur.fetchall():
        print(f"     {r['scene_type']}: {r['cnt']}")

    conn.close()


def cmd_build(args):
    """Build / rebuild vector index (TF-IDF if no ollama)."""
    # Check if ollama is available
    ollama_available = False
    try:
        import urllib.request
        req = urllib.request.Request('http://localhost:11434/api/tags',
            headers={'Content-Type':'application/json'})
        urllib.request.urlopen(req, timeout=2)
        ollama_available = True
    except:
        pass
    
    if not ollama_available:
        from memory_search_lite import MemorySearchLite
        searcher = MemorySearchLite()
        searcher.build()
        return
    
    from memory_search import SearchEngine
    eng = SearchEngine()
    eng.build()
    print("✅ 向量索引构建完成")


def cmd_decay(args):
    """Run weight decay on stale memories."""
    from episodic_retrieve import decay_old_memories
    n = decay_old_memories()
    print(f"📉 热度衰减完成：{n} 条记录被衰减")


def cmd_heat(args):
    """Show file heat ranking."""
    from file_heat import scan_transcripts
    heat = scan_transcripts(args.days)
    sorted_heat = dict(sorted(heat.items(), key=lambda x: -x[1]))
    print(f"=== File Heat (last {args.days} days) ===")
    for i, (path, count) in enumerate(sorted_heat.items(), 1):
        if i > args.top:
            break
        bar = '█' * min(count, 30)
        print(f"  {i:3}. {count:4} {path} {bar}")


def cmd_recent(args):
    """Show recent high-importance events."""
    from episodic_retrieve import match_by_recent, format_memories
    rows = match_by_recent(days=args.days, importance_min=args.min_importance)
    output = format_memories(rows)
    if output:
        print(output)
    else:
        print("无近期重要事件")


def cmd_promises(args):
    """Show active promises."""
    from episodic_retrieve import get_unfinished_promises, format_memories
    rows = get_unfinished_promises()
    output = format_memories(rows)
    if output:
        print(output)
    else:
        print("无活跃约定")


def cmd_triples(args):
    """Symptom-Cause-Solution triple store."""
    from triples_v2 import TripleStoreV2
    ts = TripleStoreV2()
    if args.triples_command == 'add':
        tags = json.loads(args.tags) if args.tags else []
        tid = ts.add(args.symptom, args.cause, args.solution, tags,
                    args.domain, args.confidence, args.memory_id, args.source)
        print(f"✅ 三元组写入 ID={tid}")
    elif args.triples_command == 'search':
        results = ts.search(args.query, args.top, args.domain)
        if not results:
            print(f"未找到与「{args.query}」相关的经验")
            return
        print(f"🔍 '{args.query}' → {len(results)} 条经验")
        for i, t in enumerate(results, 1):
            print(f"  [{i}] 匹配:{t['bm25_score']} 置信:{t['confidence']} 使用:{t['usage_count']}次 | {t['symptom'][:50]}")
    elif args.triples_command == 'list':
        results = ts.list_all(args.domain, args.limit)
        print(f"📋 共 {len(results)} 条经验")
        for t in results:
            print(f"  #{t['id']} | {t['domain']} | 置信:{t['confidence']} | 使用:{t['usage_count']}次 | {t['symptom'][:50]}")
    elif args.triples_command == 'show':
        t = ts.get(args.triple_id)
        if not t:
            print(f"未找到 ID={args.triple_id}")
            return
        print(f"📋 #{t['id']} | 领域:{t['domain']} | 置信:{t['confidence']} | 使用:{t['usage_count']}次")
        print(f"  症状: {t['symptom']}")
        print(f"  根因: {t['cause']}")
        print(f"  方案: {t['solution']}")
    elif args.triples_command == 'delete':
        if ts.delete(args.triple_id):
            print(f"✅ 已删除 ID={args.triple_id}")
        else:
            print(f"未找到 ID={args.triple_id}")
    elif args.triples_command == 'decay':
        n = ts.decay_confidence(args.days, args.rate)
        print(f"📉 置信度衰减完成：{n} 条三元组被衰减")
    elif args.triples_command == 'stats':
        stats = ts.get_stats()
        print(f"📊 三元组统计")
        print(f"   总数: {stats['total']}")
        print(f"   平均置信度: {stats['avg_confidence']}")
        print(f"   总使用次数: {stats['total_usage']}")
        print(f"   领域分布:")
        for domain, cnt in stats['domains'].items():
            print(f"     {domain}: {cnt}")
    else:
        print("Available: add, search, list, show, delete, decay, stats")


def cmd_troubleshoot(args):
    """Troubleshooting SOP commands."""
    from troubleshooter import Troubleshooter
    ts = Troubleshooter()
    if args.troubleshoot_command == 'search':
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
    elif args.troubleshoot_command == 'list':
        results = ts.list_all()
        if not results:
            print("暂无排查SOP")
            return
        print(f"📋 共 {len(results)} 个排查SOP：\n")
        for sop in results:
            print(f"  #{sop['id']} | {sop['category']} | 成功:{sop['success_count']}次 | {sop['symptom']}")
    elif args.troubleshoot_command == 'add':
        steps = json.loads(args.steps) if args.steps else []
        outcomes = json.loads(args.outcomes) if args.outcomes else []
        sid = ts.add_sop(args.symptom, steps, args.category or "general", outcomes)
        print(f"✅ SOP写入 ID={sid}")
    elif args.troubleshoot_command == 'record':
        ts.record_result(args.sop_id, args.success == "true", args.minutes or 0)
        print(f"✅ 记录结果: SOP #{args.sop_id} → {'成功' if args.success == 'true' else '失败'}")
    else:
        print("Available: search, list, add, record")


def cmd_aggregate(args):
    """Memory aggregation commands."""
    from aggregate import MemoryAggregator
    agg = MemoryAggregator()
    if args.action == 'build':
        from aggregate import auto_cluster
        n = auto_cluster(agg, args.min_size)
        print(f"✅ 自动聚类完成：创建了 {n} 个记忆组")
    elif args.action == 'list':
        groups = agg.list_groups()
        if not groups:
            print("暂无记忆组")
            return
        print(f"📋 共 {len(groups)} 个记忆组：\n")
        for g in groups:
            print(f"  #{g['id']} | {g['group_name']} | {len(g['source_ids'])}条记忆 | {g['category']}")
    elif args.action == 'show':
        group = agg.get_group(args.group_id)
        if not group:
            print(f"未找到 ID={args.group_id}")
            return
        print(f"📁 {group['group_name']}")
        print(f"   摘要: {group['summary']}")
        print(f"   来源: {len(group['source_ids'])} 条记忆")
        print(f"   教训: {group['lesson']}")
    elif args.action == 'find-clusters':
        clusters = agg.find_clusters(args.min_size)
        if not clusters:
            print("未找到聚类")
            return
        print(f"📊 找到 {len(clusters)} 个聚类：\n")
        for c in clusters:
            print(f"  标签「{c['tag']}」→ {len(c['memory_ids'])} 条记忆")
    else:
        print("Available: build, list, show, find-clusters")


def cmd_review(args):
    """Spaced repetition review commands."""
    from review import ReviewEngine
    eng = ReviewEngine()
    if args.action == 'due':
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
    elif args.action == 'review':
        interval, next_review = eng.record_review(args.memory_id, args.performance)
        print(f"✅ 复习记录: 记忆 #{args.memory_id}")
        print(f"   间隔: {interval}天 | 下次复习: {next_review}")
    elif args.action == 'stats':
        stats = eng.get_stats()
        print("📊 复习统计")
        print(f"   总复习次数: {stats['total_reviews']}")
        print(f"   已复习记忆: {stats['unique_reviewed']}/{stats['total_important']}")
        print(f"   覆盖率: {stats['coverage']}%")
        print(f"   平均表现: {stats['avg_performance']}/5")
    elif args.action == 'heatmap':
        data = eng.get_heatmap(args.days)
        if not data:
            print("暂无复习数据")
            return
        print("📊 复习活跃度热力图：")
        for d in data:
            bar = '█' * min(d['cnt'] * 2, 20)
            print(f"  {d['day']}: {d['cnt']}次 {bar}")
    else:
        print("Available: due, review, stats, heatmap")


def cmd_ingest(args):
    """Unified ingest funnel — auto-parse and write to SoulMem."""
    import json
    from datetime import datetime, timedelta
    from soulmem_funnel import FunnelEngine
    from funnel_generator import ReportGenerator
    from funnel_cron import run_period_check, get_current_period
    
    ingest_cmd = getattr(args, 'ingest_cmd', None)
    
    if ingest_cmd == 'manual':
        # 手动录入模式
        role = getattr(args, 'role', 'kk')
        print(f"\n🔍 SoulMem Funnel — {role.upper()} 模式")
        print("=" * 50)
        print("📝 记录今天的事（写多少都行，写完按两次回车）:\n")
        
        # 读取多行输入
        lines = []
        while True:
            try:
                line = input()
                if line == '' and lines and lines[-1] == '':
                    break
                lines.append(line)
            except EOFError:
                break
        
        text = '\n'.join(lines).strip()
        if not text:
            print("取消录入")
            return
        
        # 初始化引擎
        engine = FunnelEngine(role)
        
        # 拆解 + 校验
        result = engine.ingest(text)
        
        # 确认
        print(f"\n确认写入 SoulMem? [Y/n/e(编辑)]")
        choice = input("> ").strip().lower()
        
        if choice in ('y', ''):
            written = engine.write(result)
            print(f"\n✅ 已写入: {', '.join(written)}")
        elif choice == 'e':
            print("请输入补充内容:")
            extra = input("> ").strip()
            result["detail"] = result.get("detail", "") + "\n\n补充: " + extra
            written = engine.write(result)
            print(f"\n✅ 已写入: {', '.join(written)}")
        else:
            print("取消录入")
    
    elif ingest_cmd == 'pending':
        # 查看待审核报告
        generator = ReportGenerator()
        pending = generator.get_pending_reports()
        if not pending:
            print("📋 没有待审核的报告")
            return
        print(f"📋 {len(pending)} 个待审核报告:\n")
        for r in pending:
            data = json.loads(r["generated_content"])
            print(f"  #{r['id']} | {data.get('period', {}).get('start', '?')[:16]} | {data.get('summary', {}).get('total_conversations', 0)} 条")
    
    elif ingest_cmd == 'auto':
        # 触发自动分析
        period = get_current_period()
        if period:
            run_period_check(period)
        else:
            # 不是检查时段，分析过去4小时
            print("📋 当前不是检查时段，分析过去4小时...")
            generator = ReportGenerator()
            end_time = datetime.now()
            start_time = end_time - timedelta(hours=4)
            report = generator.generate_period_report(start_time, end_time)
            if report:
                report_id = generator.save_pending_report(report)
                print(f"📋 发现 {report['summary']['total_conversations']} 条有价值内容")
                print(f"报告已保存 #{report_id}，请审核")
            else:
                print("📋 过去4小时无值得记录的内容")
    
    elif ingest_cmd == 'review':
        # 审核报告
        report_id = args.report_id
        generator = ReportGenerator()
        
        # 获取报告
        cursor = generator.conn.execute("SELECT * FROM pending_reports WHERE id = ?", (report_id,))
        report = cursor.fetchone()
        if not report:
            print(f"❌ 报告 #{report_id} 不存在")
            return
        
        data = json.loads(report["generated_content"])
        
        # 显示报告
        print(generator.format_report(data))
        
        # 操作选择
        print(f"\n操作: [a]通过 [e]编辑 [r]拒绝 [s]跳过")
        choice = input("> ").strip().lower()
        
        if choice == 'a':
            generator.approve_report(report_id)
            print(f"✅ 报告 #{report_id} 已通过")
            
            # 自动写入 SoulMem
            written = generator.write_to_soulmem(report_id)
            if written:
                print(f"✅ 已自动写入 SoulMem")
        elif choice == 'e':
            print("请输入编辑后的内容:")
            edited = input("> ").strip()
            generator.approve_report(report_id, edited)
            print(f"✅ 报告 #{report_id} 已编辑并通过")
        elif choice == 'r':
            generator.reject_report(report_id)
            print(f"✅ 报告 #{report_id} 已拒绝")
        else:
            print("跳过")
    
    else:
        # 默认显示帮助
        print("Usage: soulmem ingest <command>")
        print("")
        print("Commands:")
        print("  manual [--role kk|iris]     手动录入")
        print("  pending                    查看待审核报告")
        print("  auto                       触发自动分析")
        print("  review <report_id>         审核报告")


def cmd_wiki(args):
    """Wiki operations manager."""
    from wiki_manager import WikiManager
    
    wm = WikiManager()
    wiki_cmd = getattr(args, 'wiki_cmd', None)
    
    if wiki_cmd == 'status':
        result = wm.health_check()
        print(json.dumps(result, indent=2, ensure_ascii=False))
    
    elif wiki_cmd == 'list':
        pages = wm.list_pages()
        if pages:
            for p in pages:
                print(f"  {p['id']:3} | {p['slug']:30} | {p['title']}")
        else:
            print("No pages or not logged in")
    
    elif wiki_cmd == 'get':
        page = wm.get_page(args.slug)
        if page:
            print(f"Title: {page.get('title')}")
            print(f"Content:\n{page.get('content', '')[:500]}")
        else:
            print("Page not found")
    
    elif wiki_cmd == 'create':
        result = wm.create_page(args.title, args.slug, args.content)
        if result:
            print(f"✅ Created: {result.get('slug')}")
        else:
            print("❌ Create failed")
    
    elif wiki_cmd == 'update':
        result = wm.update_page(args.slug, args.content)
        if result:
            print(f"✅ Updated: {args.slug}")
        else:
            print("❌ Update failed")
    
    elif wiki_cmd == 'start':
        if wm.start_service():
            print("✅ Service started")
        else:
            print("❌ Failed to start")
    
    elif wiki_cmd == 'stop':
        if wm.stop_service():
            print("✅ Service stopped")
        else:
            print("❌ Failed to stop")
    
    elif wiki_cmd == 'restart':
        if wm.restart_service():
            print("✅ Service restarted")
        else:
            print("❌ Failed to restart")
    
    else:
        print("Usage: soulmem wiki <command>")
        print("")
        print("Commands:")
        print("  status     Check wiki status")
        print("  list       List all pages")
        print("  get <slug> Get page content")
        print("  create     Create a page")
        print("  update     Update a page")
        print("  start      Start wiki service")
        print("  stop       Stop wiki service")
        print("  restart    Restart wiki service")


def cmd_sop(args):
    """SOP Skills manager."""
    from sop_manager import SOPManager
    from sop_triggers import SOPTriggerDetector
    
    manager = SOPManager()
    sop_cmd = getattr(args, 'sop_cmd', None)
    
    if sop_cmd == 'list':
        sops = manager.list_sops("active")
        if not sops:
            print("暂无 SOP")
            return
        for sop in sops:
            print(f"  {sop.get('name'):30} v{sop.get('version', 1)} | {sop.get('status', 'active')} | 成功{sop.get('success_count', 0)}次")
    
    elif sop_cmd == 'get':
        sop = manager.get_sop(args.slug)
        if not sop:
            print(f"SOP '{args.slug}' 不存在")
            return
        print(json.dumps(sop, indent=2, ensure_ascii=False))
    
    elif sop_cmd == 'search':
        results = manager.search_sops(args.query)
        if not results:
            print("未找到匹配的 SOP")
            return
        for sop in results:
            print(f"  {sop.get('name'):30} | {sop.get('description', '')[:50]}")
    
    elif sop_cmd == 'create':
        slug = manager.create_sop(args.name, args.desc, [], args.triggers)
        print(f"✅ SOP 创建: {slug}")
    
    elif sop_cmd == 'detect':
        detector = SOPTriggerDetector()
        suggestions = detector.auto_trigger()
        if not suggestions:
            print("暂无重复操作需要固化")
            return
        print(f"发现 {len(suggestions)} 个建议:")
        for s in suggestions:
            print(f"  - {s['suggestion']}")
    
    elif sop_cmd == 'to-memory':
        memory_id = manager.sop_to_memory(args.slug)
        if memory_id:
            print(f"✅ 已写入 SoulMem: episodic_memory #{memory_id}")
        else:
            print("❌ 写入失败")
    
    else:
        print("Usage: soulmem sop <command>")
        print("")
        print("Commands:")
        print("  list         列出所有 SOP")
        print("  get <slug>   获取 SOP 详情")
        print("  search <q>   搜索 SOP")
        print("  create       创建 SOP")
        print("  detect       检测重复操作")
        print("  to-memory    写入 SoulMem")


def cmd_doctor(args):
    """Health check & diagnostic."""
    from doctor_init import run_doctor as _run_doctor
    _run_doctor(args)


def cmd_auto_remediate(args):
    """Auto remediation engine."""
    from auto_remediate import AutoRemediator
    ar = AutoRemediator()
    if args.action == 'diagnose':
        suggestions = ar.auto_diagnose(args.problem)
        if suggestions:
            print(f"\n💡 建议:")
            for type_, item in suggestions[:3]:
                if type_ == 'sop':
                    print(f"  运行 SOP #{item['id']}: python3 soulmem.py troubleshoot search '{item['symptom']}'")
                else:
                    print(f"  参考经验 #{item['id']}: {item['symptom'][:50]}")
    elif args.action == 'run':
        dry_run = args.dry_run if hasattr(args, 'dry_run') else False
        result = ar.execute_sop(args.sop_id, dry_run)
        if result and not dry_run:
            success = input("\n✅ 问题是否解决? (y/N): ").strip().lower() == 'y'
            tid = ar.solidify_execution(result, success)
            if tid:
                print(f"✅ 经验已沉淀为三元组 #{tid}")
    elif args.action == 'interactive':
        print("🔧 SoulMem 交互式排查")
        print("=" * 50)
        problem = input("\n📝 描述你遇到的问题: ").strip()
        if problem:
            suggestions = ar.auto_diagnose(problem)
            if suggestions:
                sops = [s for t, s in suggestions if t == 'sop']
                if sops:
                    print(f"\n选择要执行的SOP (1-{len(sops)}):")
                    for i, sop in enumerate(sops, 1):
                        print(f"  {i}. #{sop['id']} {sop['symptom']}")
                    choice = input("\n> ").strip()
                    if choice.isdigit() and 1 <= int(choice) <= len(sops):
                        result = ar.execute_sop(sops[int(choice) - 1]['id'])
                        if result:
                            success = input("\n✅ 问题是否解决? (y/N): ").strip().lower() == 'y'
                            tid = ar.solidify_execution(result, success)
                            if tid:
                                print(f"✅ 经验已沉淀为三元组 #{tid}")
    else:
        print("Available: diagnose, run, interactive")


def cmd_cross_project(args):
    """Cross-project experience reuse."""
    from cross_project import CrossProjectReuse
    cpr = CrossProjectReuse()
    if args.action == 'search':
        results = cpr.search_cross_domain(args.query, args.from_domain, args.top)
        if not results:
            print(f"未找到与「{args.query}」相关的跨域经验")
            return
        print(f"🔍 '{args.query}' → {len(results)} 条跨域经验\n")
        for i, r in enumerate(results, 1):
            print(f"  [{i}] 文本相似:{r['text_similarity']} 域相关:{r['domain_boost']} 置信:{r['confidence']}")
            print(f"      症状: {r['symptom'][:70]}")
            print(f"      根因: {r['cause'][:70]}")
            print(f"      方案: {r['solution'][:70]}")
            print(f"      领域: {r['domain']}")
            print()
    elif args.action == 'suggest':
        results = cpr.suggest_for_domain(args.domain, args.top)
        if not results:
            print(f"领域「{args.domain}」没有可借鉴的跨域经验")
            return
        print(f"📚 领域「{args.domain}」可借鉴的经验:\n")
        for i, r in enumerate(results, 1):
            print(f"  [{i}] 域相似度:{r['domain_similarity']} | {r['symptom'][:60]}")
    elif args.action == 'domains':
        domains = cpr.list_domains()
        if not domains:
            print("暂无领域数据")
            return
        print("📊 领域经验分布:\n")
        for d in domains:
            bar = '█' * min(d['cnt'] * 3, 20)
            print(f"  {d['domain']:20} {d['cnt']:3}条  平均置信:{d['avg_conf']:.2f} {bar}")
    elif args.action == 'related':
        related = cpr.find_related_domains(args.domain, args.threshold)
        if not related:
            print(f"领域「{args.domain}」没有相关域")
            return
        print(f"🔗 与「{args.domain}」相关的领域:\n")
        for domain, sim in related:
            bar = '█' * int(sim * 20)
            print(f"  {domain:20} 相似度: {sim:.2f} {bar}")
    elif args.action == 'map':
        tid = cpr.auto_map_experience(args.memory_id, args.to_domain)
        if tid:
            print(f"✅ 记忆 #{args.memory_id} 已映射到 {args.to_domain}，三元组 #{tid}")
        else:
            print(f"❌ 无法从记忆 #{args.memory_id} 提取因果模式")
    else:
        print("Available: search, suggest, domains, related, map")


def cmd_graph(args):
    """Knowledge graph operations."""
    from graph import KnowledgeGraph
    kg = KnowledgeGraph()
    if args.graph_command == 'build':
        kg.build()
    elif args.graph_command == 'show':
        stats = kg.get_stats()
        print("📊 知识图谱统计")
        print(f"   实体总数: {stats['entities']}")
        print(f"   关系总数: {stats['relationships']}")
        print(f"   提及次数: {stats['mentions']}")
        print("\n🏆 热门实体 Top 15:")
        for i, e in enumerate(stats['top_entities'], 1):
            print(f"   {i:2}. {e['name']:20} ({e['type']}) — {e['mentions']}次")
    elif args.graph_command == 'related':
        related = kg.get_related_memories(args.memory_id, args.depth)
        if not related:
            print(f"未找到关联记忆")
            return
        print(f"🔗 关联记忆 (深度{args.depth}):")
        for i, m in enumerate(related, 1):
            print(f"   [{i}] ({m['scene_type']}) {m['summary']} [{m['memory_date']}]")
    else:
        print("Available: build, show, related")


def cmd_reviews(args):
    """Show memories due for review (not accessed recently)."""
    import sqlite3
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    days = args.days
    cur.execute("""
        SELECT id, scene_type, summary, importance, weight, last_accessed, created_at
        FROM episodic_memory
        WHERE (last_accessed IS NULL OR last_accessed = '' OR last_accessed < datetime('now', ?))
        AND importance >= ?
        ORDER BY importance DESC, created_at DESC
        LIMIT ?
    """, (f'-{days} days', args.min_importance, args.limit))
    rows = cur.fetchall()
    conn.close()
    if not rows:
        print(f"无到期回顾的记忆（>{days}天未访问且重要性≥{args.min_importance}）")
        return
    print(f"📝 需要回顾的记忆（>{days}天未访问）\n")
    for i, r in enumerate(rows, 1):
        print(f"  [{i}] (#{r['id']}) {r['scene_type']}")
        print(f"      {r['summary'][:90]}")
        print(f"      重要:{r['importance']} 权重:{r['weight']:.2f} 上次访问:{r['last_accessed'][:10] if r['last_accessed'] else 'never'}")
        print()


def cmd_sync(args):
    """Bidirectional sync between category KB and episodic memory."""
    from sync_memory import main as sync_main
    import sys
    old_argv = sys.argv
    sys.argv = ['sync_memory', '--direction', args.direction, '--limit', str(args.limit)]
    sync_main()
    sys.argv = old_argv


def cmd_emotion(args):
    """Emotion cognition system commands."""
    from emotion_cli import (
        cmd_list, cmd_emotion, cmd_event, cmd_search, cmd_stats,
        cmd_soul, cmd_scenario, cmd_report, cmd_warmth,
        cmd_feel, cmd_resonate, cmd_grow, cmd_index,
        cmd_add_emotion, cmd_add_event, cmd_link, usage as emotion_usage
    )
    commands = {
        'list': cmd_list,
        'emotion': lambda: cmd_emotion(args.name if args.name else ''),
        'event': lambda: cmd_event(int(args.eid) if args.eid else 0),
        'search': lambda: cmd_search(' '.join(args.query)),
        'stats': cmd_stats,
        'soul': lambda: cmd_soul(args.name if args.name else ''),
        'scenario': lambda: cmd_scenario(' '.join(args.query)),
        'report': cmd_report,
        'warmth': cmd_warmth,
        'feel': lambda: cmd_feel(args.args),
        'resonate': lambda: cmd_resonate(args.args),
        'grow': lambda: cmd_grow(args.args),
        'index': lambda: cmd_index(args.args),
        'add-emotion': lambda: cmd_add_emotion(args.args),
        'add-event': lambda: cmd_add_event(args.args),
        'link': lambda: cmd_link(args.args),
        'help': emotion_usage,
    }
    handler = commands.get(args.emotion_command)
    if handler:
        handler()
    else:
        emotion_usage()


def main():
    parser = argparse.ArgumentParser(
        prog="soulmem",
        description="SoulMem — Soul Memory for OpenClaw",
    )
    sub = parser.add_subparsers(dest="command", help="Available commands")

    # --- graph ---
    p_graph = sub.add_parser("graph", help="Knowledge graph operations")
    p_graph_graph = p_graph.add_subparsers(dest="graph_command")
    p_graph_build = p_graph_graph.add_parser("build", help="Build graph from all memories")
    p_graph_show = p_graph_graph.add_parser("show", help="Show graph statistics")
    p_graph_related = p_graph_graph.add_parser("related", help="Find related memories via graph")
    p_graph_related.add_argument("memory_id", type=int, help="Memory ID")
    p_graph_related.add_argument("--depth", type=int, default=2, help="Traversal depth")

    # --- promises ---
    sub.add_parser("promises", help="Show active promises")

    # --- search ---
    p_search = sub.add_parser("search", help="Hybrid search memories")
    p_search.add_argument("query", help="Search query")
    p_search.add_argument("--top", type=int, default=5, help="Number of results")

    # --- capture ---
    p_cap = sub.add_parser("capture", help="Write a memory record")
    p_cap.add_argument("--scene-type", required=True, help="Type of scene")
    p_cap.add_argument("--summary", required=True, help="One-line summary")
    p_cap.add_argument("--detail", default="", help="Detailed description")
    p_cap.add_argument("--importance", type=int, default=5, help="1-10 importance")
    p_cap.add_argument("--tags", default="[]", help="JSON array of tags")
    p_cap.add_argument("--emotional-mark", default="", help="Emotional notes")
    p_cap.add_argument("--memory-date", default=None, help="YYYY-MM-DD (default: today)")
    p_cap.add_argument("--weight", type=float, default=1.0, help="Initial weight")

    # --- auto ---
    p_auto = sub.add_parser("auto", help="Auto-capture from latest transcript")
    p_auto.add_argument("--transcript", default=None, help="Path to transcript JSONL")

    # --- stats ---
    sub.add_parser("stats", help="Show memory statistics")

    # --- build ---
    sub.add_parser("build", help="Build vector index")

    # --- decay ---
    sub.add_parser("decay", help="Run weight decay")

    # --- triples ---
    p_triples = sub.add_parser("triples", help="Symptom-Cause-Solution triple store")
    p_triples_sub = p_triples.add_subparsers(dest="triples_command")
    p_triples_add = p_triples_sub.add_parser("add", help="Add a triple")
    p_triples_add.add_argument("--symptom", required=True)
    p_triples_add.add_argument("--cause", required=True)
    p_triples_add.add_argument("--solution", required=True)
    p_triples_add.add_argument("--tags", default="[]")
    p_triples_add.add_argument("--domain", default="general")
    p_triples_add.add_argument("--confidence", type=float, default=0.8)
    p_triples_add.add_argument("--memory-id", type=int, default=0)
    p_triples_add.add_argument("--source", default="manual")
    p_triples_search = p_triples_sub.add_parser("search", help="Search triples")
    p_triples_search.add_argument("query")
    p_triples_search.add_argument("--top", type=int, default=5)
    p_triples_search.add_argument("--domain", default=None)
    p_triples_list = p_triples_sub.add_parser("list", help="List all triples")
    p_triples_list.add_argument("--domain", default=None)
    p_triples_list.add_argument("--limit", type=int, default=50)
    p_triples_show = p_triples_sub.add_parser("show", help="Show triple details")
    p_triples_show.add_argument("triple_id", type=int)
    p_triples_del = p_triples_sub.add_parser("delete", help="Delete a triple")
    p_triples_del.add_argument("triple_id", type=int)
    p_triples_decay = p_triples_sub.add_parser("decay", help="Decay confidence")
    p_triples_decay.add_argument("--days", type=int, default=30)
    p_triples_decay.add_argument("--rate", type=float, default=0.05)
    p_triples_sub.add_parser("stats", help="Triple statistics")

    # --- heat ---
    p_heat = sub.add_parser("heat", help="Show file heat ranking")
    p_heat.add_argument("--days", type=int, default=7, help="Scan last N days")
    p_heat.add_argument("--top", type=int, default=20, help="Show Top N")

    # --- recent ---
    p_recent = sub.add_parser("recent", help="Show recent high-importance events")
    p_recent.add_argument("--days", type=int, default=3, help="Lookback days")
    p_recent.add_argument("--min-importance", type=int, default=7, help="Min importance")

    # --- reviews ---
    p_reviews = sub.add_parser("reviews", help="Show memories due for review")
    p_reviews.add_argument("--days", type=int, default=30, help="Not accessed in N days")
    p_reviews.add_argument("--min-importance", type=int, default=5, help="Min importance")
    p_reviews.add_argument("--limit", type=int, default=15, help="Max results")

    # --- sync ---
    p_sync = sub.add_parser("sync", help="Category↔Episodic bidirectional sync")
    p_sync.add_argument("--direction", default="both", choices=["both", "to_cat", "from_cat"])
    p_sync.add_argument("--limit", type=int, default=20, help="Max records to sync")

    # --- emotion ---
    p_emotion = sub.add_parser("emotion", help="Emotion cognition system v2.0")
    p_emotion_sub = p_emotion.add_subparsers(dest="emotion_command")
    p_emotion_sub.add_parser("list", help="List all emotions")
    p_emotion_emotion = p_emotion_sub.add_parser("emotion", help="View emotion details")
    p_emotion_emotion.add_argument("name", help="Emotion name")
    p_emotion_event = p_emotion_sub.add_parser("event", help="View event details")
    p_emotion_event.add_argument("eid", type=int, help="Event ID")
    p_emotion_search = p_emotion_sub.add_parser("search", help="Search events")
    p_emotion_search.add_argument("query", nargs="+", help="Search keywords")
    p_emotion_sub.add_parser("stats", help="Emotion statistics")
    p_emotion_soul = p_emotion_sub.add_parser("soul", help="Get emotion wisdom package")
    p_emotion_soul.add_argument("name", help="Emotion name")
    p_emotion_scenario = p_emotion_sub.add_parser("scenario", help="Search by life scenario")
    p_emotion_scenario.add_argument("query", nargs="+", help="Scenario keywords")
    p_emotion_sub.add_parser("report", help="Soul temperature report")
    p_emotion_sub.add_parser("warmth", help="Soul warmth score")
    p_emotion_feel = p_emotion_sub.add_parser("feel", help="Record soul temperature")
    p_emotion_feel.add_argument("args", nargs="*", help="feel <emotion> <level>")
    p_emotion_resonate = p_emotion_sub.add_parser("resonate", help="Record soul resonance")
    p_emotion_resonate.add_argument("args", nargs="*", help="resonate <emotion>")
    p_emotion_grow = p_emotion_sub.add_parser("grow", help="Record growth log")
    p_emotion_grow.add_argument("args", nargs="*", help="grow <emotion>")
    p_emotion_index = p_emotion_sub.add_parser("index", help="Add scenario index")
    p_emotion_index.add_argument("args", nargs="*", help="index <scenario> <emotion>")
    p_emotion_add_emo = p_emotion_sub.add_parser("add-emotion", help="Add new emotion")
    p_emotion_add_emo.add_argument("args", nargs="*", help="add-emotion <name> [def] [cat]")
    p_emotion_add_evt = p_emotion_sub.add_parser("add-event", help="Add new event")
    p_emotion_add_evt.add_argument("args", nargs="*", help="add-event <title>")
    p_emotion_link = p_emotion_sub.add_parser("link", help="Link emotion to event")
    p_emotion_link.add_argument("args", nargs="*", help="link <emotion> <event_id> <intensity>")
    p_emotion_sub.add_parser("help", help="Show emotion help")

    # --- troubleshoot ---
    p_troubleshoot = sub.add_parser("troubleshoot", help="Troubleshooting SOP engine")
    p_troubleshoot_sub = p_troubleshoot.add_subparsers(dest="troubleshoot_command")
    p_troubleshoot_search = p_troubleshoot_sub.add_parser("search", help="Search SOPs")
    p_troubleshoot_search.add_argument("query", help="Symptom query")
    p_troubleshoot_search.add_argument("--top", type=int, default=3)
    p_troubleshoot_sub.add_parser("list", help="List all SOPs")
    p_troubleshoot_add = p_troubleshoot_sub.add_parser("add", help="Add a SOP")
    p_troubleshoot_add.add_argument("--symptom", required=True)
    p_troubleshoot_add.add_argument("--steps", required=True, help="JSON array")
    p_troubleshoot_add.add_argument("--category", default="general")
    p_troubleshoot_add.add_argument("--outcomes", default="[]")
    p_troubleshoot_record = p_troubleshoot_sub.add_parser("record", help="Record result")
    p_troubleshoot_record.add_argument("sop_id", type=int)
    p_troubleshoot_record.add_argument("success", choices=["true", "false"])
    p_troubleshoot_record.add_argument("--minutes", type=int, default=0)

    # --- aggregate ---
    p_aggregate = sub.add_parser("aggregate", help="Memory aggregation engine")
    p_aggregate_sub = p_aggregate.add_subparsers(dest="action")
    p_aggregate_build = p_aggregate_sub.add_parser("build", help="Auto-cluster")
    p_aggregate_build.add_argument("--min-size", type=int, default=3)
    p_aggregate_sub.add_parser("list", help="List groups")
    p_aggregate_show = p_aggregate_sub.add_parser("show", help="Show group")
    p_aggregate_show.add_argument("group_id", type=int)
    p_aggregate_clusters = p_aggregate_sub.add_parser("find-clusters", help="Find clusters")
    p_aggregate_clusters.add_argument("--min-size", type=int, default=3)

    # --- review ---
    p_review = sub.add_parser("review", help="Spaced repetition review")
    p_review_sub = p_review.add_subparsers(dest="action")
    p_review_due = p_review_sub.add_parser("due", help="Show due memories")
    p_review_due.add_argument("--limit", type=int, default=10)
    p_review_review = p_review_sub.add_parser("review", help="Record review")
    p_review_review.add_argument("memory_id", type=int)
    p_review_review.add_argument("--performance", type=int, default=3)
    p_review_sub.add_parser("stats", help="Review statistics")
    p_review_heat = p_review_sub.add_parser("heatmap", help="Activity heatmap")
    p_review_heat.add_argument("--days", type=int, default=30)

    # --- auto-remediate ---
    p_remediate = sub.add_parser("auto-remediate", help="Auto remediation engine")
    p_remediate_sub = p_remediate.add_subparsers(dest="action")
    p_remediate_diag = p_remediate_sub.add_parser("diagnose", help="Diagnose a problem")
    p_remediate_diag.add_argument("problem", help="Problem description")
    p_remediate_run = p_remediate_sub.add_parser("run", help="Run a SOP")
    p_remediate_run.add_argument("sop_id", type=int)
    p_remediate_run.add_argument("--dry-run", action="store_true")
    p_remediate_sub.add_parser("interactive", help="Interactive troubleshooting")

    # --- cross-project ---
    p_cross = sub.add_parser("cross-project", help="Cross-project experience reuse")
    p_cross_sub = p_cross.add_subparsers(dest="action")
    p_cross_search = p_cross_sub.add_parser("search", help="Search cross-domain")
    p_cross_search.add_argument("query")
    p_cross_search.add_argument("--from-domain", default=None)
    p_cross_search.add_argument("--top", type=int, default=5)
    p_cross_suggest = p_cross_sub.add_parser("suggest", help="Suggest for domain")
    p_cross_suggest.add_argument("domain")
    p_cross_suggest.add_argument("--top", type=int, default=5)
    p_cross_sub.add_parser("domains", help="List domains")
    p_cross_related = p_cross_sub.add_parser("related", help="List related domains")
    p_cross_related.add_argument("domain")
    p_cross_related.add_argument("--threshold", type=float, default=0.3)
    p_cross_map = p_cross_sub.add_parser("map", help="Map memory to domain")
    p_cross_map.add_argument("memory_id", type=int)
    p_cross_map.add_argument("to_domain")

    # --- ingest ---
    p_ingest = sub.add_parser("ingest", help="Unified ingest funnel (auto-parse and write)")
    p_ingest_sub = p_ingest.add_subparsers(dest="ingest_cmd")
    p_ingest_manual = p_ingest_sub.add_parser("manual", help="手动录入")
    p_ingest_manual.add_argument("--role", default="kk", choices=["kk", "iris"], help="角色")
    p_ingest_sub.add_parser("pending", help="查看待审核报告")
    p_ingest_sub.add_parser("auto", help="触发自动分析")
    p_ingest_review = p_ingest_sub.add_parser("review", help="审核报告")
    p_ingest_review.add_argument("report_id", type=int, help="报告ID")
    p_ingest_review.add_argument("report_id", type=int, help="报告ID")

    # --- sop ---
    p_sop = sub.add_parser("sop", help="SOP Skills manager")
    p_sop_sub = p_sop.add_subparsers(dest="sop_cmd")
    p_sop_sub.add_parser("list", help="列出所有 SOP")
    p_sop_get = p_sop_sub.add_parser("get", help="获取 SOP 详情")
    p_sop_get.add_argument("slug", help="SOP slug")
    p_sop_search = p_sop_sub.add_parser("search", help="搜索 SOP")
    p_sop_search.add_argument("query", help="搜索关键词")
    p_sop_create = p_sop_sub.add_parser("create", help="创建 SOP")
    p_sop_create.add_argument("--name", required=True)
    p_sop_create.add_argument("--desc", default="")
    p_sop_create.add_argument("--triggers", nargs="*", default=[])
    p_sop_sub.add_parser("detect", help="检测重复操作")
    p_sop_to_mem = p_sop_sub.add_parser("to-memory", help="SOP 写入 SoulMem")
    p_sop_to_mem.add_argument("slug", help="SOP slug")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    commands = {
        "search": cmd_search,
        "capture": cmd_capture,
        "auto": cmd_auto,
        "stats": cmd_stats,
        "build": cmd_build,
        "graph": cmd_graph,
        "triples": cmd_triples,
        "decay": cmd_decay,
        "heat": cmd_heat,
        "recent": cmd_recent,
        "promises": cmd_promises,
        "reviews": cmd_reviews,
        "sync": cmd_sync,
        "emotion": cmd_emotion,
        "troubleshoot": cmd_troubleshoot,
        "aggregate": cmd_aggregate,
        "review": cmd_review,
        "doctor": cmd_doctor,
        "auto-remediate": cmd_auto_remediate,
        "cross-project": cmd_cross_project,
        "ingest": cmd_ingest,
        "wiki": cmd_wiki,
        "sop": cmd_sop,
    }

    handler = commands.get(args.command)
    if handler:
        handler(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
