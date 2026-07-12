#!/usr/bin/env python3
# ============================================================================
# SoulMem — Auto Capture
# Automatically extract key events from session transcripts into episodic memory.
#
# Usage:
#   python3 scripts/auto_capture.py
#   python3 scripts/auto_capture.py --transcript /path/to/session.jsonl
# ============================================================================
import os, sys, json, subprocess, re
from datetime import datetime

WORKSPACE = os.environ.get("SOULMEM_WORKSPACE", os.path.expanduser("~/.openclaw/workspace"))
SCRIPTS_DIR = os.path.join(WORKSPACE, "scripts")
DB_PATH = os.path.join(WORKSPACE, "memory", "episodic_memory.db")
CAPTURE_SCRIPT = os.path.join(SCRIPTS_DIR, "episodic_capture.py")

KEYWORDS = {
    "错误": ["error", "ERROR", "fail", "FAIL", "crash", "exception", "报错", "失败", "死掉"],
    "学习": ["learn", "study", "研究", "学到了", "发现", "懂了", "理解了", "原来"],
    "约定": ["约定", "承诺", "不要", "禁止", "never", "always", "规则", "必须"],
    "任务": ["修复", "完成", "搞定", "部署", "搭建", "上线", "优化", "实现"],
    "亲密": ["亲密", "惩罚", "温度", "白衬衣", "高跟鞋"],
}

def detect_scene(text: str) -> tuple:
    text_lower = text.lower()
    scores = {}
    for scene_type, patterns in KEYWORDS.items():
        count = sum(1 for p in patterns if p.lower() in text_lower)
        if count > 0:
            scores[scene_type] = count
    if not scores:
        return None, None, None, None, None
    best_type = max(scores, key=scores.get)
    sentences = re.split(r'[。！？\n]+', text)
    important = []
    for s in sentences:
        s = s.strip()
        if not s or len(s) < 5: continue
        for p in KEYWORDS.get(best_type, []):
            if p.lower() in s.lower():
                important.append(s[:200]); break
    if not important: important = sentences[:3]
    summary = important[0][:100] if important else "自动捕获"
    detail = "\n".join(important[:3])[:500]
    importance = min(5 + scores[best_type], 10)
    return best_type, summary, detail, importance, [best_type, "auto-capture"]

def auto_capture_from_transcript(transcript_path: str):
    if not os.path.exists(transcript_path):
        print(f"Transcript not found: {transcript_path}"); return
    with open(transcript_path, 'r', errors='ignore') as f: content = f.read()
    if len(content) < 100: return
    scene_type, summary, detail, importance, tags = detect_scene(content[-8000:])
    if not scene_type: return
    cmd = [sys.executable, CAPTURE_SCRIPT, "--scene-type", scene_type,
           "--summary", summary, "--detail", detail,
           "--importance", str(importance), "--tags", json.dumps(tags)]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        if result.returncode == 0 and "已写入" in result.stdout:
            print(f"✅ [{scene_type}] {summary[:60]}")
            return True
        else:
            print(f"⚠️ Failed: {result.stdout[:100]}"); return False
    except Exception as e:
        print(f"❌ {e}"); return False

def find_latest_session_transcript():
    import glob, os
    files = []
    for agent_dir in ["kk", "main", "default"]:
        d = os.path.expanduser(f"~/.openclaw/agents/{agent_dir}/sessions")
        if os.path.exists(d):
            for f in os.listdir(d):
                if f.endswith('.jsonl'):
                    fp = os.path.join(d, f)
                    files.append(fp)
    if not files: return None
    files.sort(key=lambda x: os.path.getmtime(x), reverse=True)
    return files[0]

if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='Auto-capture session events into episodic memory')
    parser.add_argument('--transcript', help='Path to transcript JSONL file')
    args = parser.parse_args()
    if args.transcript:
        auto_capture_from_transcript(args.transcript)
    else:
        t = find_latest_session_transcript()
        if t: auto_capture_from_transcript(t)
        else: print("No transcript found")
