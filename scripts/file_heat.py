#!/usr/bin/env python3
# ============================================================================
# SoulMem — File Heat Tracker
# Scan session transcripts to find which files are read frequently → use this
# data to decide context prefix ordering (high-frequency = load first).
#
# Usage:
#   python3 scripts/file_heat.py --days 7 --top 20
#   python3 scripts/file_heat.py --output memory/file_heat.json
# ============================================================================
import os, sys, json, glob, argparse
from datetime import datetime, timedelta
from pathlib import Path

WORKSPACE = os.environ.get("SOULMEM_WORKSPACE", os.path.expanduser("~/.openclaw/workspace"))

def scan_transcripts(days=7):
    cutoff = datetime.now() - timedelta(days=days)
    sessions_dir = os.path.expanduser("~/.openclaw/agents/*/sessions")
    files = glob.glob(sessions_dir + "/*.jsonl") if False else []
    for agent in ["kk", "main", "default"]:
        d = os.path.expanduser(f"~/.openclaw/agents/{agent}/sessions")
        if os.path.exists(d):
            for f in os.listdir(d):
                if f.endswith('.jsonl'):
                    fp = os.path.join(d, f)
                    if datetime.fromtimestamp(os.path.getmtime(fp)) >= cutoff:
                        files.append(fp)
    
    heat = {}
    for fp in files:
        try:
            with open(fp, 'r', errors='ignore') as f:
                for line in f:
                    if '/workspace/' in line or '.md' in line:
                        # Very rough: just look for workspace file references
                        for part in line.split('"'):
                            if '/workspace/' in part and part.endswith('.md'):
                                norm = part.split('/workspace/')[-1]
                                heat[norm] = heat.get(norm, 0) + 1
        except:
            pass
    return heat

def main():
    parser = argparse.ArgumentParser(description='Track file read frequency from sessions')
    parser.add_argument('--days', type=int, default=7, help='Scan last N days')
    parser.add_argument('--top', type=int, default=20, help='Show Top N')
    parser.add_argument('--output', help='Write JSON to file')
    args = parser.parse_args()
    
    heat = scan_transcripts(args.days)
    sorted_heat = dict(sorted(heat.items(), key=lambda x: -x[1]))
    
    print(f"=== File Heat (last {args.days} days) ===")
    for i, (path, count) in enumerate(sorted_heat.items(), 1):
        if i > args.top: break
        bar = '█' * min(count, 30)
        print(f"  {i:3}. {count:4} {path} {bar}")
    
    if args.output:
        with open(args.output, 'w') as f:
            json.dump({"generated": datetime.now().isoformat(), "heat": sorted_heat},
                     f, indent=2)
        print(f"\nWrote to {args.output}")

if __name__ == '__main__':
    main()
