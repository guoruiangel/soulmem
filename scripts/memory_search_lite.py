#!/usr/bin/env python3
# ============================================================================
# SoulMem — Lightweight TF-IDF Vector Search (no ollama required)
# Pure numpy implementation for environments without ollama/fastembed.
#
# Usage:
#   python3 scripts/memory_search_lite.py --build
#   python3 scripts/memory_search_lite.py "query"
# ============================================================================
import os, sys, json, sqlite3, math, re
from collections import Counter
from datetime import datetime

WORKSPACE = os.environ.get("SOULMEM_WORKSPACE", os.path.expanduser("~/.openclaw/workspace"))
DB_PATH = os.path.join(WORKSPACE, "memory", "episodic_memory.db")

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)


class TfidfVectorizer:
    """Lightweight TF-IDF vectorizer using only numpy."""
    
    def __init__(self, max_features=5000):
        self.max_features = max_features
        self.vocabulary = {}
        self.idf = {}
        self.doc_count = 0
    
    def fit(self, documents):
        """Build vocabulary and IDF from documents."""
        self.doc_count = len(documents)
        
        # Count document frequency for each term
        df = Counter()
        all_terms = set()
        
        for doc in documents:
            terms = set(doc)
            all_terms.update(terms)
            for term in terms:
                df[term] += 1
        
        # Select top terms by document frequency
        sorted_terms = sorted(df.items(), key=lambda x: x[1], reverse=True)
        selected_terms = sorted_terms[:self.max_features]
        
        self.vocabulary = {term: idx for idx, (term, _) in enumerate(selected_terms)}
        
        # Compute IDF
        self.idf = {}
        for term, freq in selected_terms:
            self.idf[term] = math.log(1 + self.doc_count / (1 + freq))
    
    def transform(self, documents):
        """Transform documents to TF-IDF vectors."""
        if not self.vocabulary:
            return []
        
        vectors = []
        for doc in documents:
            vec = [0.0] * len(self.vocabulary)
            tf = Counter(doc)
            max_tf = max(tf.values()) if tf else 1
            
            for term, count in tf.items():
                if term in self.vocabulary:
                    idx = self.vocabulary[term]
                    tf_val = 0.5 + 0.5 * count / max_tf
                    vec[idx] = tf_val * self.idf.get(term, 1.0)
            
            # L2 normalize
            norm = math.sqrt(sum(x*x for x in vec))
            if norm > 0:
                vec = [x / norm for x in vec]
            
            vectors.append(vec)
        
        return vectors
    
    def fit_transform(self, documents):
        """Fit and transform in one step."""
        self.fit(documents)
        return self.transform(documents)


def tokenize(text):
    """Simple Chinese-aware tokenization."""
    if not text:
        return []
    text = text.lower()
    words = re.findall(r'[\u4e00-\u9fff]+|[a-zA-Z0-9]+', text)
    result = []
    for w in words:
        if re.match(r'[\u4e00-\u9fff]+', w):
            if len(w) == 2:
                result.append(w)
            elif len(w) > 2:
                for i in range(len(w)-1):
                    result.append(w[i:i+2])
        else:
            result.append(w)
    return result


class MemorySearchLite:
    """Lightweight memory search using TF-IDF + BM25 hybrid."""
    
    def __init__(self, db_path=None):
        self.conn = sqlite3.connect(db_path or DB_PATH)
        self.conn.row_factory = sqlite3.Row
        self.cur = self.conn.cursor()
        self.vectorizer = TfidfVectorizer(max_features=3000)
        self.documents = []
        self.memories = []
        self.vectors = []
    
    def build(self):
        """Build TF-IDF index from all memories."""
        self.cur.execute('SELECT id, summary, detail, tags FROM episodic_memory')
        rows = self.cur.fetchall()
        
        if not rows:
            print("No memories to index")
            return
        
        self.memories = [dict(r) for r in rows]
        self.documents = []
        
        for m in self.memories:
            text = f"{m['summary']} {m['detail']} {m['tags']}"
            self.documents.append(tokenize(text))
        
        # Build TF-IDF vectors
        self.vectors = self.vectorizer.fit_transform(self.documents)
        
        # Save vectors to database
        self.cur.execute('DELETE FROM mem_vec')
        for i, m in enumerate(self.memories):
            if self.vectors[i]:
                self.cur.execute(
                    'INSERT OR REPLACE INTO mem_vec (id, vec, mod, upd) VALUES (?, ?, ?, ?)',
                    (m['id'], json.dumps(self.vectors[i]), 'tfidf', datetime.now().isoformat())
                )
        
        self.conn.commit()
        print(f"TF-IDF index built: {len(self.memories)} memories, {len(self.vectorizer.vocabulary)} terms")
    
    def search(self, query, top=5):
        """Search memories using TF-IDF cosine similarity + BM25."""
        # Load vectors from DB
        self.cur.execute('SELECT id, vec FROM mem_vec')
        vec_map = {r['id']: json.loads(r['vec']) for r in self.cur.fetchall() if r['vec']}
        
        # Load memories
        self.cur.execute('SELECT * FROM episodic_memory')
        all_mems = [dict(r) for r in self.cur.fetchall()]
        
        if not all_mems:
            return []
        
        # Tokenize query
        qt = tokenize(query)
        
        # BM25 scoring
        docs = [tokenize(f"{m['summary']} {m['detail']} {m['tags']}") for m in all_mems]
        avg_dl = sum(len(d) for d in docs) / len(docs) if docs else 1
        
        bm25s = []
        for doc in docs:
            tf = Counter(doc)
            score = 0.0
            for term in set(qt):
                if term not in tf:
                    continue
                idf = math.log(1 + len(docs) / (1 + sum(1 for d in docs if term in d)))
                num = tf[term] * (1.2 + 1)
                den = tf[term] + 1.2 * (1 - 0.75 + 0.75 * len(doc) / max(avg_dl, 1))
                score += idf * num / den
            bm25s.append(score)
        
        # TF-IDF cosine similarity
        # Build query vector using existing vocabulary
        query_vec = [0.0] * len(self.vectorizer.vocabulary)
        qt_counter = Counter(qt)
        max_qt = max(qt_counter.values()) if qt_counter else 1
        
        for term, count in qt_counter.items():
            if term in self.vectorizer.vocabulary:
                idx = self.vectorizer.vocabulary[term]
                tf_val = 0.5 + 0.5 * count / max_qt
                query_vec[idx] = tf_val * self.vectorizer.idf.get(term, 1.0)
        
        # Normalize query vec
        norm = math.sqrt(sum(x*x for x in query_vec))
        if norm > 0:
            query_vec = [x / norm for x in query_vec]
        
        # Compute cosine similarities
        cosines = []
        for m in all_mems:
            vec = vec_map.get(m['id'], [])
            if vec and len(vec) == len(query_vec):
                dot = sum(a*b for a, b in zip(query_vec, vec))
                cosines.append(dot)
            else:
                cosines.append(0.0)
        
        # Heat decay
        now = datetime.now()
        heats = []
        for m in all_mems:
            try:
                age = max((now - datetime.strptime(m['memory_date'], '%Y-%m-%d')).days, 0)
                decay = max(0.5, 1.0 - age / 180)
            except:
                decay = 0.5
            heats.append((m['weight'] or 1.0) * (m['importance'] or 5) * decay / 10)
        
        # Combine scores
        results = []
        for i, m in enumerate(all_mems):
            final = 0.4 * bm25s[i] + 0.35 * cosines[i] + 0.25 * heats[i]
            results.append({
                'id': m['id'],
                'scene_type': m['scene_type'],
                'summary': m['summary'][:80],
                'detail': (m['detail'] or '')[:200],
                'tags': m['tags'],
                'memory_date': m['memory_date'],
                'bm25': round(bm25s[i], 3),
                'cosine': round(cosines[i], 3),
                'heat': round(heats[i], 3),
                'score': round(final, 3)
            })
        
        results.sort(key=lambda x: x['score'], reverse=True)
        return results[:top]


def main():
    import argparse
    p = argparse.ArgumentParser(description='Lightweight TF-IDF Memory Search')
    p.add_argument('query', nargs='?', help='Search query')
    p.add_argument('--build', action='store_true', help='Build TF-IDF index')
    p.add_argument('--top', type=int, default=5, help='Number of results')
    args = p.parse_args()
    
    searcher = MemorySearchLite()
    
    if args.build:
        searcher.build()
    elif args.query:
        results = searcher.search(args.query, args.top)
        if not results:
            print("No results")
            return
        print(f"🔍 '{args.query}' → {len(results)} results\n")
        for i, r in enumerate(results, 1):
            print(f"  [{i}] ({r['scene_type']}) {r['summary']}")
            print(f"      {r['memory_date']} | BM25={r['bm25']} Cosine={r['cosine']} Heat={r['heat']} Score={r['score']}")
            print()
    else:
        p.print_help()


if __name__ == '__main__':
    main()
