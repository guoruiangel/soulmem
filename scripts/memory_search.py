#!/usr/bin/env python3
# ============================================================================
# SoulMem — Hybrid Memory Search v2
# BM25 keyword + vector semantic + heat decay weighting + query expansion.
#
# Improvements in v2:
# - Chinese-aware tokenization (jieba if available, fallback to bigram)
# - Query expansion with synonyms and related terms
# - Phrase matching boost
# - Tag importance weighting
# - Adaptive scoring formula
#
# Usage:
#   python3 scripts/memory_search.py "your query"
#   python3 scripts/memory_search.py --build
#   python3 scripts/memory_search.py --stats
# ============================================================================
import os, sys, json, sqlite3, math, re, subprocess
from datetime import datetime, timedelta
from collections import Counter

WORKSPACE = os.environ.get("SOULMEM_WORKSPACE", os.path.expanduser("~/.openclaw/workspace"))
DB_PATH   = os.path.join(WORKSPACE, "memory", "episodic_memory.db")

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)
from sanitize import sanitize, sanitize_record

TOKEN_RE = re.compile(r'[\u4e00-\u9fff]+|[a-zA-Z0-9]+')

# Try jieba for Chinese segmentation
try:
    import jieba
    jieba.setLogLevel(jieba.logging.WARNING)
    HAS_JIEBA = True
except ImportError:
    HAS_JIEBA = False

# Query expansion: synonyms and related terms
SYNONYMS = {
    "错误": ["bug", "报错", "失败", "error", "异常", "问题"],
    "报错": ["错误", "bug", "error", "异常"],
    "修复": ["解决", "修好", "搞定", "处理"],
    "搞定": ["修复", "完成", "解决"],
    "学习": ["研究", "探索", "学会", "掌握"],
    "约定": ["承诺", "规则", "必须", "禁止"],
    "任务": ["工作", "事情", "需求", "项目"],
    "部署": ["上线", "发布", "搭建"],
    "配置": ["设置", "参数", "环境"],
    "超时": ["timeout", "太久", "等不及", "慢"],
    "分段": ["分条", "逐句", "一句一句", "节奏"],
    "暗线": ["关心", "惦记", "温度", "温柔"],
    "心跳": ["heartbeat", "轮询", "检查"],
    "记忆": ["回忆", "记录", "场景", "episodic"],
    "搜索": ["查找", "检索", "查询"],
    "图谱": ["graph", "关系", "关联", "知识图谱"],
    "三元组": ["triple", "经验", "症状", "方案"],
}

def tokens(text):
    """Tokenize with Chinese-aware segmentation."""
    if not text:
        return []
    text = text.lower()
    if HAS_JIEBA:
        # Use jieba for Chinese segmentation
        result = []
        for token in jieba.cut(text):
            token = token.strip()
            if len(token) > 1:
                result.append(token)
        return result
    else:
        # Fallback: bigram for Chinese + word for English
        result = []
        for m in TOKEN_RE.finditer(text):
            word = m.group()
            if re.match(r'[\u4e00-\u9fff]+', word):
                # Chinese: add bigrams
                if len(word) == 2:
                    result.append(word)
                elif len(word) > 2:
                    for i in range(len(word)-1):
                        result.append(word[i:i+2])
            else:
                result.append(word)
        return result

def expand_query(query, max_expansion=3):
    """Expand query with synonyms."""
    qt = tokens(query)
    expanded = set(qt)
    for token in qt:
        for key, syns in SYNONYMS.items():
            if token in syns or token == key:
                for s in syns[:max_expansion]:
                    expanded.add(s)
                expanded.add(key)
    return list(expanded)

def bm25(qt, dt, avg_dl, k1=1.2, b=0.75):
    if not qt or not dt: return 0.0
    tf = Counter(dt)
    score = 0.0
    n = max(len(dt), 1)
    for t in set(qt):
        if t not in tf: continue
        idf = math.log(1 + n / (1 + tf[t]))
        num = tf[t] * (k1 + 1)
        den = tf[t] + k1 * (1 - b + b * len(dt) / max(avg_dl, 1))
        score += idf * num / den
    return score

def phrase_match(query, text):
    """Check if query phrases appear in text."""
    if not query or not text:
        return 0.0
    query = query.lower()
    text = text.lower()
    # Exact phrase match
    if query in text:
        return 1.0
    # Partial phrase match (50% of query in text)
    query_tokens = query.split()
    if len(query_tokens) > 1:
        matches = sum(1 for t in query_tokens if t in text)
        return matches / len(query_tokens)
    return 0.0

def get_emb(text):
    try:
        import urllib.request
        req = urllib.request.Request('http://localhost:11434/api/embeddings',
            data=json.dumps({'model':'nomic-embed-text','prompt':text[:512]}).encode(),
            headers={'Content-Type':'application/json'})
        resp = urllib.request.urlopen(req, timeout=30)
        data = json.loads(resp.read())
        return data.get('embedding', [])
    except: pass
    return []

def cosine(a, b):
    if not a or not b or len(a)!=len(b): return 0.0
    d = sum(x*y for x,y in zip(a,b))
    na = math.sqrt(sum(x*x for x in a)) or 1
    nb = math.sqrt(sum(y*y for y in b)) or 1
    return d/(na*nb)

class SearchEngine:
    def __init__(self):
        self.conn = sqlite3.connect(DB_PATH)
        self.conn.row_factory = sqlite3.Row
        self.cur = self.conn.cursor()
        self.cur.execute('CREATE TABLE IF NOT EXISTS mem_vec (id INTEGER PRIMARY KEY, vec TEXT, mod TEXT, upd TEXT)')

    def build(self):
        """Rebuild entire vector index from scratch."""
        self.cur.execute('SELECT id, summary, detail, tags FROM episodic_memory')
        rows = self.cur.fetchall()
        if not rows: return
        sample = get_emb("test")
        use_oll = len(sample) > 0
        cnt = 0
        for r in rows:
            vec = get_emb(f"{r['summary']} {r['detail']} {r['tags']}"[:512]) if use_oll else None
            if vec:
                self.cur.execute('REPLACE INTO mem_vec VALUES (?,?,?,?)',
                                 (r['id'], json.dumps(vec), 'nomic-embed-text', datetime.now().isoformat()))
                cnt += 1
        self.conn.commit()
        print(f"Vector index built: {cnt}/{len(rows)}")

    def build_incremental(self, record_id: int):
        """Update vector index for a single record."""
        self.cur.execute('SELECT id, summary, detail, tags FROM episodic_memory WHERE id = ?', (record_id,))
        row = self.cur.fetchone()
        if not row:
            return
        vec = get_emb(f"{row['summary']} {row['detail']} {row['tags']}"[:512])
        if vec:
            self.cur.execute('REPLACE INTO mem_vec VALUES (?,?,?,?)',
                             (row['id'], json.dumps(vec), 'nomic-embed-text', datetime.now().isoformat()))
            self.conn.commit()

    def search(self, query, top=5):
        # Expand query with synonyms
        expanded_query = expand_query(query)
        qt = tokens(query)
        qt_expanded = tokens(' '.join(expanded_query))
        
        self.cur.execute('SELECT * FROM episodic_memory')
        mems = self.cur.fetchall()
        if not mems: return []

        docs = [tokens(f"{m['summary']} {m['detail']} {m['tags']}") for m in mems]
        avg = sum(len(d) for d in docs) / len(docs)
        
        # BM25 with expanded query
        bm25s = [bm25(qt_expanded, d, avg) for d in docs]
        
        # Phrase match boost
        phrase_scores = []
        for m in mems:
            text = f"{m['summary']} {m['detail']}"
            phrase_scores.append(phrase_match(query, text))

        # Vector similarity
        self.cur.execute('SELECT id, vec FROM mem_vec')
        vmap = {r['id']: json.loads(r['vec']) for r in self.cur.fetchall() if r['vec']}
        qvec = get_emb(query[:256])
        vecs = [cosine(qvec, vmap.get(m['id'], [])) for m in mems] if qvec else [0]*len(mems)

        # Heat decay
        now = datetime.now()
        heats = []
        for m in mems:
            try:
                age = max((now - datetime.strptime(m['memory_date'], '%Y-%m-%d')).days, 0)
                decay = max(0.5, 1.0 - age / 180)
            except: decay = 0.5
            heats.append((m['weight'] or 1.0) * (m['importance'] or 5) * decay / 10)

        # Tag boost: if query matches tag, boost score
        tag_boosts = []
        for m in mems:
            tags = json.loads(m['tags']) if m['tags'] else []
            boost = 0.0
            for qt_token in qt:
                for tag in tags:
                    if qt_token in tag.lower():
                        boost += 0.3
            tag_boosts.append(boost)

        results = []
        for i, m in enumerate(mems):
            # Adaptive scoring: phrase match gets high weight
            final = (0.3 * bm25s[i] + 
                     0.25 * vecs[i] + 
                     0.2 * heats[i] + 
                     0.15 * phrase_scores[i] + 
                     0.1 * tag_boosts[i])
            results.append({
                'id': m['id'], 'scene_type': m['scene_type'],
                'summary': m['summary'][:80], 'detail': (m['detail'] or '')[:200],
                'tags': m['tags'], 'memory_date': m['memory_date'],
                'bm25': round(bm25s[i],3), 'vec': round(vecs[i],3),
                'heat': round(heats[i],3), 'phrase': round(phrase_scores[i],3),
                'tag_boost': round(tag_boosts[i],3),
                'score': round(final,3)
            })
        results.sort(key=lambda x: x['score'], reverse=True)
        return [sanitize_record(r) for r in results[:top]]

def main():
    import argparse
    p = argparse.ArgumentParser(description='Hybrid memory search v2 (BM25 + vector + heat + expansion)')
    p.add_argument('query', nargs='?')
    p.add_argument('--build', action='store_true', help='Build vector index')
    p.add_argument('--top', type=int, default=5, help='Number of results')
    p.add_argument('--stats', action='store_true', help='Show memory statistics')
    args = p.parse_args()
    eng = SearchEngine()

    if args.build: eng.build(); return
    if args.stats:
        cur = eng.cur
        cur.execute('SELECT COUNT(*) FROM episodic_memory'); print(f"Total memories: {cur.fetchone()[0]}")
        cur.execute('SELECT COUNT(*) FROM mem_vec');        print(f"Vector indexed: {cur.fetchone()[0]}")
        cur.execute('SELECT scene_type, COUNT(*) FROM episodic_memory GROUP BY scene_type')
        for r in cur.fetchall(): print(f"  {r[0]}: {r[1]}")
        return
    if not args.query: print("Usage: python3 memory_search.py <query>"); return

    rs = eng.search(args.query, args.top)
    print(f"🔍 '{args.query}' → {len(rs)} results")
    for i, r in enumerate(rs, 1):
        print(f"  [{i}] ({r['scene_type']}) {r['summary']}")
        print(f"      {r['memory_date']} | BM25={r['bm25']} Vec={r['vec']} Heat={r['heat']} Phrase={r['phrase']} Tag={r['tag_boost']} Score={r['score']}")

if __name__ == '__main__':
    main()
