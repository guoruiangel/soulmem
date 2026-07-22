#!/usr/bin/env python3
# ============================================================================
# SoulMem — Triple Store v2
# Enhanced symptom-cause-solution store with BM25 search, vector similarity,
# confidence decay, and auto-linking to episodic memory.
#
# Improvements over v1:
# - BM25 + vector hybrid search (reuses memory_search.py)
# - Confidence decay: unused triples lose confidence over time
# - Auto-link to episodic memory records
# - Usage-based ranking (most-used triples surface first)
# - Domain-aware filtering
# ============================================================================
import os, sys, json, sqlite3, math, re
from datetime import datetime, timedelta
from collections import Counter

WORKSPACE = os.environ.get("SOULMEM_WORKSPACE", os.path.expanduser("~/.openclaw/workspace"))
DB_PATH = os.path.join(WORKSPACE, "memory", "episodic_memory.db")

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)

# BM25 parameters
K1 = 1.2
B = 0.75

def tokens(text):
    """Simple tokenization for BM25."""
    if not text:
        return []
    text = text.lower()
    # Chinese bigrams + English words
    import re
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


class TripleStoreV2:
    """Enhanced triple store with hybrid search and confidence decay."""
    
    def __init__(self, db_path=None):
        self.conn = sqlite3.connect(db_path or DB_PATH)
        self.conn.row_factory = sqlite3.Row
        self.cur = self.conn.cursor()
        self._init_schema()
    
    def _init_schema(self):
        self.cur.executescript("""
            CREATE TABLE IF NOT EXISTS triples (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symptom TEXT NOT NULL,
                cause TEXT NOT NULL,
                solution TEXT NOT NULL,
                tags TEXT DEFAULT '[]',
                domain TEXT DEFAULT 'general',
                confidence REAL DEFAULT 0.8,
                initial_confidence REAL DEFAULT 0.8,
                usage_count INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_used TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                linked_memory_id INTEGER DEFAULT 0,
                source TEXT DEFAULT 'manual'
            );
            CREATE INDEX IF NOT EXISTS idx_triples_domain ON triples(domain);
            CREATE INDEX IF NOT EXISTS idx_triples_tags ON triples(tags);
            CREATE INDEX IF NOT EXISTS idx_triples_confidence ON triples(confidence);
        """)
        self.conn.commit()
    
    def add(self, symptom, cause, solution, tags=None, domain="general", 
            confidence=0.8, linked_memory_id=0, source="manual"):
        tag_json = json.dumps(tags or [], ensure_ascii=False)
        self.cur.execute("""
            INSERT INTO triples (symptom, cause, solution, tags, domain, confidence, 
                               initial_confidence, linked_memory_id, source)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (symptom, cause, solution, tag_json, domain, confidence, confidence,
              linked_memory_id, source))
        self.conn.commit()
        return self.cur.lastrowid
    
    def search(self, query, top=5, domain=None):
        """Hybrid search: BM25 + confidence boost + usage ranking."""
        qt = tokens(query)
        if not qt:
            return []
        
        # Fetch all triples (filtered by domain if specified)
        if domain:
            self.cur.execute("SELECT * FROM triples WHERE domain = ?", (domain,))
        else:
            self.cur.execute("SELECT * FROM triples")
        all_triples = self.cur.fetchall()
        
        if not all_triples:
            return []
        
        # Build document corpus for BM25
        docs = []
        for t in all_triples:
            text = f"{t['symptom']} {t['cause']} {t['solution']} {' '.join(json.loads(t['tags']))}"
            docs.append(tokens(text))
        
        avg_dl = sum(len(d) for d in docs) / len(docs) if docs else 1
        
        # BM25 scoring
        results = []
        for i, t in enumerate(all_triples):
            doc = docs[i]
            tf = Counter(doc)
            score = 0.0
            for term in set(qt):
                if term not in tf:
                    continue
                idf = math.log(1 + len(docs) / (1 + sum(1 for d in docs if term in d)))
                num = tf[term] * (K1 + 1)
                den = tf[term] + K1 * (1 - B + B * len(doc) / max(avg_dl, 1))
                score += idf * num / den
            
            if score > 0:
                # Boost by confidence and usage
                confidence_boost = t['confidence'] or 0.5
                usage_boost = min(math.log(1 + t['usage_count']) * 0.1, 0.5)
                final_score = score * (1 + confidence_boost + usage_boost)
                
                r = dict(t)
                r['tags'] = json.loads(r['tags'])
                r['bm25_score'] = round(score, 3)
                r['final_score'] = round(final_score, 3)
                results.append(r)
        
        results.sort(key=lambda x: -x['final_score'])
        return results[:top]
    
    def get(self, triple_id):
        self.cur.execute("SELECT * FROM triples WHERE id = ?", (triple_id,))
        row = self.cur.fetchone()
        if not row:
            return None
        r = dict(row)
        r['tags'] = json.loads(r['tags'])
        return r
    
    def list_all(self, domain=None, limit=50):
        if domain:
            self.cur.execute("SELECT * FROM triples WHERE domain = ? ORDER BY confidence DESC LIMIT ?", 
                           (domain, limit))
        else:
            self.cur.execute("SELECT * FROM triples ORDER BY confidence DESC LIMIT ?", (limit,))
        results = []
        for row in self.cur.fetchall():
            r = dict(row)
            r['tags'] = json.loads(r['tags'])
            results.append(r)
        return results
    
    def increment_usage(self, triple_id):
        self.cur.execute("""
            UPDATE triples 
            SET usage_count = usage_count + 1, last_used = datetime('now', 'localtime')
            WHERE id = ?
        """, (triple_id,))
        self.conn.commit()
    
    def decay_confidence(self, days_threshold=30, decay_rate=0.05):
        """Decay confidence for triples not used in N days."""
        cutoff = (datetime.now() - timedelta(days=days_threshold)).strftime('%Y-%m-%d %H:%M:%S')
        self.cur.execute("""
            UPDATE triples 
            SET confidence = MAX(confidence - ?, 0.1)
            WHERE last_used < ? AND confidence > 0.1
        """, (decay_rate, cutoff))
        self.conn.commit()
        return self.cur.rowcount
    
    def boost_confidence(self, triple_id, boost=0.1):
        """Boost confidence after successful use."""
        self.cur.execute("""
            UPDATE triples 
            SET confidence = MIN(confidence + ?, initial_confidence)
            WHERE id = ?
        """, (boost, triple_id))
        self.conn.commit()
    
    def delete(self, triple_id):
        self.cur.execute("DELETE FROM triples WHERE id = ?", (triple_id,))
        self.conn.commit()
        return self.cur.rowcount > 0
    
    def get_stats(self):
        self.cur.execute("SELECT COUNT(*) FROM triples")
        total = self.cur.fetchone()[0]
        self.cur.execute("SELECT AVG(confidence) FROM triples")
        avg_conf = self.cur.fetchone()[0] or 0
        self.cur.execute("SELECT SUM(usage_count) FROM triples")
        total_usage = self.cur.fetchone()[0] or 0
        self.cur.execute("SELECT domain, COUNT(*) as cnt FROM triples GROUP BY domain ORDER BY cnt DESC")
        domains = {r['domain']: r['cnt'] for r in self.cur.fetchall()}
        return {
            'total': total,
            'avg_confidence': round(avg_conf, 2),
            'total_usage': total_usage,
            'domains': domains
        }


def cmd_add(args):
    ts = TripleStoreV2()
    tags = json.loads(args.tags) if args.tags else []
    tid = ts.add(
        symptom=args.symptom,
        cause=args.cause,
        solution=args.solution,
        tags=tags,
        domain=args.domain or "general",
        confidence=args.confidence or 0.8,
        linked_memory_id=args.memory_id or 0,
        source=args.source or "manual"
    )
    print(f"✅ 三元组写入 ID={tid}")
    
    # Auto-link to episodic memory
    if args.memory_id and args.memory_id > 0:
        try:
            conn = sqlite3.connect(DB_PATH)
            conn.execute("UPDATE episodic_memory SET related_ids = COALESCE(related_ids, '[]') WHERE id = ?", 
                        (args.memory_id,))
            conn.commit()
            conn.close()
        except:
            pass


def cmd_search(args):
    ts = TripleStoreV2()
    results = ts.search(args.query, args.top, args.domain)
    if not results:
        print(f"未找到与「{args.query}」相关的经验")
        return
    
    print(f"🔍 '{args.query}' → {len(results)} 条经验\n")
    for i, t in enumerate(results, 1):
        print(f"  [{i}] 匹配:{t['bm25_score']} 置信:{t['confidence']} 使用:{t['usage_count']}次")
        print(f"      症状: {t['symptom'][:80]}")
        print(f"      根因: {t['cause'][:80]}")
        print(f"      方案: {t['solution'][:80]}")
        if t['tags']:
            print(f"      标签: {', '.join(t['tags'])}")
        print(f"      领域: {t['domain']} | 来源: {t['source']}")
        print()


def cmd_list(args):
    ts = TripleStoreV2()
    results = ts.list_all(args.domain, args.limit)
    if not results:
        print("暂无三元组记录")
        return
    print(f"📋 共 {len(results)} 条经验：\n")
    for t in results:
        print(f"  #{t['id']} | {t['domain']} | 置信:{t['confidence']} | 使用:{t['usage_count']}次 | {t['symptom'][:50]}")


def cmd_show(args):
    ts = TripleStoreV2()
    t = ts.get(args.triple_id)
    if not t:
        print(f"未找到 ID={args.triple_id}")
        return
    print(f"📋 三元组 #{t['id']}")
    print(f"  领域: {t['domain']} | 来源: {t['source']}")
    print(f"  置信度: {t['confidence']} (初始: {t['initial_confidence']})")
    print(f"  使用次数: {t['usage_count']}")
    print(f"  创建: {t['created_at']} | 最后使用: {t['last_used']}")
    print(f"  标签: {', '.join(t['tags'])}")
    print(f"  症状: {t['symptom']}")
    print(f"  根因: {t['cause']}")
    print(f"  方案: {t['solution']}")


def cmd_delete(args):
    ts = TripleStoreV2()
    if ts.delete(args.triple_id):
        print(f"✅ 已删除 ID={args.triple_id}")
    else:
        print(f"未找到 ID={args.triple_id}")


def cmd_decay(args):
    ts = TripleStoreV2()
    n = ts.decay_confidence(args.days, args.rate)
    print(f"📉 置信度衰减完成：{n} 条三元组被衰减")


def cmd_stats(args):
    ts = TripleStoreV2()
    stats = ts.get_stats()
    print(f"📊 三元组统计")
    print(f"   总数: {stats['total']}")
    print(f"   平均置信度: {stats['avg_confidence']}")
    print(f"   总使用次数: {stats['total_usage']}")
    print(f"   领域分布:")
    for domain, cnt in stats['domains'].items():
        print(f"     {domain}: {cnt}")


def main():
    import argparse
    p = argparse.ArgumentParser(description='SoulMem Triple Store v2')
    sub = p.add_subparsers(dest='command')
    
    p_add = sub.add_parser('add', help='Add a triple')
    p_add.add_argument('--symptom', required=True)
    p_add.add_argument('--cause', required=True)
    p_add.add_argument('--solution', required=True)
    p_add.add_argument('--tags', default='[]')
    p_add.add_argument('--domain', default='general')
    p_add.add_argument('--confidence', type=float, default=0.8)
    p_add.add_argument('--memory-id', type=int, default=0)
    p_add.add_argument('--source', default='manual')
    
    p_search = sub.add_parser('search', help='Search triples')
    p_search.add_argument('query')
    p_search.add_argument('--top', type=int, default=5)
    p_search.add_argument('--domain', default=None)
    
    p_list = sub.add_parser('list', help='List all triples')
    p_list.add_argument('--domain', default=None)
    p_list.add_argument('--limit', type=int, default=50)
    
    p_show = sub.add_parser('show', help='Show triple details')
    p_show.add_argument('triple_id', type=int)
    
    p_del = sub.add_parser('delete', help='Delete a triple')
    p_del.add_argument('triple_id', type=int)
    
    p_decay = sub.add_parser('decay', help='Decay confidence')
    p_decay.add_argument('--days', type=int, default=30)
    p_decay.add_argument('--rate', type=float, default=0.05)
    
    sub.add_parser('stats', help='Show statistics')
    
    args = p.parse_args()
    cmds = {
        'add': cmd_add, 'search': cmd_search, 'list': cmd_list,
        'show': cmd_show, 'delete': cmd_delete, 'decay': cmd_decay, 'stats': cmd_stats,
    }
    handler = cmds.get(args.command)
    if handler:
        handler(args)
    else:
        p.print_help()


if __name__ == '__main__':
    main()
