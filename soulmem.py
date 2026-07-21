#!/usr/bin/env python3
# ============================================================================
# SoulMem — Unified CLI
# Single entry point for all memory operations.
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
#   soulmem reviews [--days 30]      # show memories due for review (not accessed in N days)
#   soulmem sync [--direction both]  # bidirectional category↔episodic sync
#
# Environment:
#   SOULMEM_WORKSPACE  (default: ~/.openclaw/workspace)
# ============================================================================

import os
import sys
import json
import argparse

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
    """Hybrid search: BM25 + vector + heat decay."""
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
    """Build / rebuild vector index."""
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
    from triples import TripleStore
    ts = TripleStore()
    if args.triples_command == 'add':
        tags = json.loads(args.tags) if args.tags else []
        tid = ts.add(args.symptom, args.cause, args.solution, tags, args.domain, args.confidence)
        print(f"✅ 三元组写入 ID={tid}")
    elif args.triples_command == 'search':
        results = ts.search(args.query, args.top)
        if not results:
            print(f"未找到与「{args.query}」相关的经验")
            return
        print(f"🔍 '{args.query}' → {len(results)} 条经验")
        for i, t in enumerate(results, 1):
            print(f"  [{i}] 匹配:{t['match_score']} 置信:{t['confidence']} | {t['symptom'][:50]}")
    elif args.triples_command == 'list':
        results = ts.list_all()
        print(f"📋 共 {len(results)} 条经验")
        for t in results:
            print(f"  #{t['id']} | {t['domain']} | 使用:{t['usage_count']}次 | {t['symptom'][:50]}")
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
    else:
        print("Available: add, search, list, show, delete")


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
    p_triples_search = p_triples_sub.add_parser("search", help="Search triples")
    p_triples_search.add_argument("query")
    p_triples_search.add_argument("--top", type=int, default=5)
    p_triples_sub.add_parser("list", help="List all triples")
    p_triples_show = p_triples_sub.add_parser("show", help="Show triple details")
    p_triples_show.add_argument("triple_id", type=int)
    p_triples_del = p_triples_sub.add_parser("delete", help="Delete a triple")
    p_triples_del.add_argument("triple_id", type=int)

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
    }

    handler = commands.get(args.command)
    if handler:
        handler(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
