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
#   soulmem decay                    # run weight decay on stale memories
#   soulmem heat [--days 7]          # show file heat ranking
#   soulmem recent                   # show recent high-importance events
#   soulmem promises                 # show active promises
#
# Environment:
#   SOULMEM_WORKSPACE  (default: ~/.openclaw/workspace)
# ============================================================================

import os
import sys
import argparse

# Ensure scripts/ and workspace are importable
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SCRIPTS_DIR = os.path.join(SCRIPT_DIR, "scripts")
WORKSPACE = os.environ.get("SOULMEM_WORKSPACE", os.path.expanduser("~/.openclaw/workspace"))
DB_PATH = os.path.join(WORKSPACE, "memory", "episodic_memory.db")
# Add both soulmem/scripts and workspace/scripts to path
# Add soulmem scripts first, then workspace scripts
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
    """Write a memory record, then incrementally update vector index."""
    from episodic_capture import init_db, capture_record
    from memory_search import SearchEngine

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


def main():
    parser = argparse.ArgumentParser(
        prog="soulmem",
        description="SoulMem — Soul Memory for OpenClaw",
    )
    sub = parser.add_subparsers(dest="command", help="Available commands")

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

    # --- heat ---
    p_heat = sub.add_parser("heat", help="Show file heat ranking")
    p_heat.add_argument("--days", type=int, default=7, help="Scan last N days")
    p_heat.add_argument("--top", type=int, default=20, help="Show Top N")

    # --- recent ---
    p_recent = sub.add_parser("recent", help="Show recent high-importance events")
    p_recent.add_argument("--days", type=int, default=3, help="Lookback days")
    p_recent.add_argument("--min-importance", type=int, default=7, help="Min importance")

    # --- promises ---
    sub.add_parser("promises", help="Show active promises")

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
        "decay": cmd_decay,
        "heat": cmd_heat,
        "recent": cmd_recent,
        "promises": cmd_promises,
    }

    handler = commands.get(args.command)
    if handler:
        handler(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
