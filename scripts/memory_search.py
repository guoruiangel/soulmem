#!/usr/bin/env python3
# ============================================================================
# SoulMem — Hybrid Memory Search
# BM25 keyword + vector semantic + heat decay weighting.
#
# Usage:
#   python3 scripts/memory_search.py "your query"
#   python3 scripts/memory_search.py --build
#   python3 scripts/memory_search.py --stats
#
# Optional: if `ollama` is installed, uses nomic-embed-text for semantic search.
# ============================================================================
import os, sys, json, sqlite3, math, re, subprocess
from datetime import datetime, timedelta
from collections import Counter

WORKSPACE = os.environ.get("SOULMEM_WORKSPACE", os.path.expanduser("~/.openclaw/workspace"))
DB_PATH   = os.path.join(WORKSPACE, "memory", "episodic_memory.db")

# Import shared sanitize module
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)
from sanitize import sanitize, sanitize_record

TOKEN_RE  = re.compile(r'[\u4e00-\u9fff]+|[a-zA-Z0-9]+')

def tokens(text): return [t.lower() for t in TOKEN_RE.findall(text or '') if len(t) > 1]

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
        """Update vector index for a single record (called after capture)."""
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
        qt = tokens(query)
        if not qt: return []
        self.cur.execute('SELECT * FROM episodic_memory')
        mems = self.cur.fetchall()
        if not mems: return []

        docs = [tokens(f"{m['summary']} {m['detail']} {m['tags']}") for m in mems]
        avg = sum(len(d) for d in docs) / len(docs)
        bm25s = [bm25(qt, d, avg) for d in docs]

        self.cur.execute('SELECT id, vec FROM mem_vec')
        vmap = {r['id']: json.loads(r['vec']) for r in self.cur.fetchall() if r['vec']}
        qvec = get_emb(query[:256])
        vecs = [cosine(qvec, vmap.get(m['id'], [])) for m in mems] if qvec else [0]*len(mems)

        now = datetime.now()
        heats = []
        for m in mems:
            try:
                age = max((now - datetime.strptime(m['memory_date'], '%Y-%m-%d')).days, 0)
                decay = max(0.5, 1.0 - age / 180)
            except: decay = 0.5
            heats.append((m['weight'] or 1.0) * (m['importance'] or 5) * decay / 10)

        results = []
        for i, m in enumerate(mems):
            final = 0.4*bm25s[i] + 0.4*vecs[i] + 0.2*heats[i]
            results.append({
                'id': m['id'], 'scene_type': m['scene_type'],
                'summary': m['summary'][:80], 'detail': (m['detail'] or '')[:200],
                'tags': m['tags'], 'memory_date': m['memory_date'],
                'bm25': round(bm25s[i],3), 'vec': round(vecs[i],3),
                'heat': round(heats[i],3), 'score': round(final,3)
            })
        results.sort(key=lambda x: x['score'], reverse=True)
        return [sanitize_record(r) for r in results[:top]]

def main():
    import argparse
    p = argparse.ArgumentParser(description='Hybrid memory search (BM25 + vector + heat)')
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
        print(f"      {r['memory_date']} | BM25={r['bm25']} Vec={r['vec']} Heat={r['heat']} Score={r['score']}")

if __name__ == '__main__':
    main()
