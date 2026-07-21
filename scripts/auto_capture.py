#!/usr/bin/env python3
# ============================================================================
# SoulMem — Auto Capture v2
# Automatically extract key events from session transcripts into episodic memory.
# Improvements: larger scan, keyword-density ranking, dedup, quality filter.
#
# Usage:
#   python3 scripts/auto_capture.py
#   python3 scripts/auto_capture.py --transcript /path/to/session.jsonl
# ============================================================================
import os, sys, json, subprocess, re, sqlite3
from datetime import datetime

WORKSPACE = os.environ.get("SOULMEM_WORKSPACE", os.path.expanduser("~/.openclaw/workspace"))
SCRIPTS_DIR = os.path.join(WORKSPACE, "scripts")
DB_PATH = os.path.join(WORKSPACE, "memory", "episodic_memory.db")
CAPTURE_SCRIPT = os.path.join(SCRIPTS_DIR, "episodic_capture.py")
SIMILARITY_THRESHOLD = 0.6  # skip if existing summary is >60% similar

KEYWORDS = {
    "错误": ["error", "ERROR", "fail", "FAIL", "crash", "exception", "报错", "失败", "死掉", "超时", "timeout", "bug"],
    "学习": ["learn", "study", "研究", "学到了", "发现", "懂了", "理解了", "原来", "改进", "优化"],
    "约定": ["约定", "承诺", "不要", "禁止", "never", "always", "规则", "必须", "铁律"],
    "任务": ["修复", "完成", "搞定", "部署", "搭建", "上线", "优化", "实现", "排错", "排查", "调试"],
    "亲密": ["亲密", "惩罚", "温度", "白衬衣", "高跟鞋"],
    "运维操作": ["重启", "启动", "关闭", "配置", "升级", "备份", "迁移"],
}

# Generic responses that should be filtered out
WEAK_PATTERNS = ["好的", "嗯", "明白了", "收到", "OK", "不错", "没问题", "了解", "可以", "是", "对"]

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
    # Filter: skip pure code/SQL lines (over 30% special chars)
    if important:
        code_chars = sum(1 for c in s if c in ";{}[]()=<>|/\\")
        if code_chars / max(len(s), 1) > 0.3:
            important.pop()
    if not important: important = sentences[:3]

    # Filter: remove lines that are mostly code/patterns
    filtered = []
    for s in important:
        # Skip if over 25% special chars (code-like)
        code_chars = sum(1 for c in s if c in ";{}[]()=<>|/\\")
        if code_chars / max(len(s), 1) > 0.25:
            continue
        # Skip if matches common code patterns
        stripped = s.strip()
        if any(stripped.startswith(p) for p in ["def ", "class ", "import ", "from ", "return ", "print(", "if ", "for ", "while ", "try:", "except", "with ", "async ", "await "]):
            continue
        # Skip JSON structural lines from JSONL transcripts
        if '"type":"' in s or '"id":"' in s or '"parentId":"' in s or '"timestamp":"' in s:
            continue
        if s.count('"') > 4 and s.count(':') > 2:
            continue
        filtered.append(s)
    important = filtered if filtered else sentences[:3]
    scored_sentences = []
    for s in important:
        score = sum(1 for p in KEYWORDS.get(best_type, []) if p.lower() in s.lower())
        scored_sentences.append((score, s))
    scored_sentences.sort(key=lambda x: x[0], reverse=True)
    summary = scored_sentences[0][1][:120] if scored_sentences else "自动捕获"
    detail = "\n".join(s for _, s in scored_sentences[:5])[:800]
    importance = min(5 + scores[best_type], 10)
    return best_type, summary, detail, importance, [best_type, "auto-capture"]

def is_duplicate_or_weak(summary: str, detail: str) -> bool:
    """Check if this capture is too weak or already exists in episodic memory."""
    # Weak filter: too short or too generic
    if len(summary) < 10 or len(detail) < 20:
        return True
    if summary.strip() in WEAK_PATTERNS:
        return True
    # Dedup: check existing records with similar summary
    try:
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        cur.execute("SELECT summary FROM episodic_memory WHERE created_at > datetime('now', '-7 days')")
        existing = [row[0] for row in cur.fetchall()]
        conn.close()
        s1 = set(summary[i:i+2] for i in range(len(summary)-1))
        if not s1:
            return False
        for existing_summary in existing:
            s2 = set(existing_summary[i:i+2] for i in range(len(existing_summary)-1))
            if not s2:
                continue
            jaccard = len(s1 & s2) / len(s1 | s2)
            if jaccard > SIMILARITY_THRESHOLD:
                return True
    except Exception:
        pass
    return False

def auto_capture_from_transcript(transcript_path: str):
    if not os.path.exists(transcript_path):
        print(f"Transcript not found: {transcript_path}"); return
    with open(transcript_path, 'r', errors='ignore') as f: content = f.read()
    if len(content) < 100: return
    # If JSONL transcript, extract meaningful text first
    if content.strip().startswith('{'):
        try:
            lines = content.strip().split('\n')
            text_parts = []
            for line in lines:
                if not line.strip(): continue
                obj = json.loads(line)
                msg = obj.get('message', {})
                role = msg.get('role', '')
                if role in ('user', 'assistant'):
                    c = msg.get('content', '')
                    if isinstance(c, str) and len(c) > 5:
                        text_parts.append(c)
                    elif isinstance(c, list):
                        for item in c:
                            if isinstance(item, dict) and item.get('type') == 'text':
                                t = item.get('text', '')
                                if len(t) > 5:
                                    text_parts.append(t)
            content = '\n'.join(text_parts)
        except (json.JSONDecodeError, KeyError):
            pass
    if len(content) < 50:
        return
    scene_type, summary, detail, importance, tags = detect_scene(content[-20000:])
    if not scene_type: return
    if is_duplicate_or_weak(summary, detail):
        print(f"⏭️ Skipped (weak or duplicate): {summary[:60]}")
        return
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
