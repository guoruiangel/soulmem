#!/usr/bin/env python3
# ============================================================================
# SoulMem — Cross-Project Experience Reuse
# Maps experiences from one project/domain to similar situations in another
# using semantic similarity and domain mapping.
#
# Usage:
#   python3 scripts/cross_project.py map --from xiaoyu_scoring --to web_dev "500 error"
#   python3 scripts/cross_project.py suggest --domain cron运维
#   python3 scripts/cross_project.py domains
# ============================================================================
import os, sys, json, sqlite3, re, math
from collections import Counter
from datetime import datetime

WORKSPACE = os.environ.get("SOULMEM_WORKSPACE", os.path.expanduser("~/.openclaw/workspace"))
DB_PATH = os.path.join(WORKSPACE, "memory", "episodic_memory.db")

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)

# Domain mapping: which domains are semantically related
DOMAIN_SIMILARITY = {
    ('xiaoyu_scoring', 'web_dev'): 0.7,
    ('xiaoyu_scoring', 'kk_homepage'): 0.6,
    ('cron运维', 'web_dev'): 0.5,
    ('cron运维', '运维'): 0.9,
    ('运维', 'web_dev'): 0.6,
    ('pablo_system', 'linkclaw'): 0.7,
    ('pablo_system', 'group_chat'): 0.5,
    ('scoring', 'xiaoyu_scoring'): 0.8,
    ('scoring', 'kk_homepage'): 0.7,
    ('linkclaw', 'group_chat'): 0.6,
    ('iris', 'pablo_system'): 0.5,
    ('git_repos', 'web_dev'): 0.7,
    ('git_repos', '运维'): 0.5,
    ('contracts', 'web_dev'): 0.4,
    ('contracts', 'group_chat'): 0.5,
    ('user_profile', 'web_dev'): 0.6,
    ('user_profile', 'kk_homepage'): 0.7,
    ('portal_dev', 'web_dev'): 0.8,
    ('portal_dev', 'kk_homepage'): 0.6,
    ('chattts', 'web_dev'): 0.5,
    ('macos_ops', '运维'): 0.7,
    ('sysops', '运维'): 0.9,
    ('sysops', 'web_dev'): 0.6,
    ('code_reuse', 'web_dev'): 0.8,
    ('memor', 'web_dev'): 0.6,
}

# Symptom keywords that transcend domains
CROSS_DOMAIN_PATTERNS = {
    '500': ['500', 'Internal Server Error', '服务器错误'],
    '404': ['404', 'Not Found', '找不到'],
    'timeout': ['timeout', '超时', 'TIMEOUT'],
    'permission': ['permission', '权限', '403', 'forbidden'],
    'database': ['database', '数据库', 'SQLite', 'MySQL', 'postgres'],
    'import': ['import', '导入', 'ModuleNotFoundError', 'No module'],
    'config': ['config', '配置', 'setting', 'parameter'],
    'deploy': ['deploy', '部署', '上线', 'publish'],
    'crash': ['crash', '崩溃', '奔溃', '死掉'],
    'slow': ['slow', '慢', '卡顿', '性能'],
    'connection': ['connection', '连接', 'refused', 'reset'],
    'data_loss': ['数据丢失', 'data loss', '损坏', 'corrupt'],
}


def tokens(text):
    """Simple tokenization."""
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


def compute_similarity(tokens_a, tokens_b):
    """Compute Jaccard similarity between two token sets."""
    if not tokens_a or not tokens_b:
        return 0.0
    set_a = set(tokens_a)
    set_b = set(tokens_b)
    intersection = set_a & set_b
    union = set_a | set_b
    return len(intersection) / len(union) if union else 0.0


class CrossProjectReuse:
    def __init__(self):
        self.conn = sqlite3.connect(DB_PATH)
        self.conn.row_factory = sqlite3.Row
        self.cur = self.conn.cursor()
    
    def get_domain_similarity(self, domain_a, domain_b):
        """Get similarity score between two domains."""
        if domain_a == domain_b:
            return 1.0
        key = (domain_a, domain_b)
        reverse_key = (domain_b, domain_a)
        return DOMAIN_SIMILARITY.get(key, DOMAIN_SIMILARITY.get(reverse_key, 0.1))
    
    def find_related_domains(self, domain, threshold=0.3):
        """Find domains related to the given domain."""
        related = []
        for (a, b), sim in DOMAIN_SIMILARITY.items():
            if a == domain and sim >= threshold:
                related.append((b, sim))
            elif b == domain and sim >= threshold:
                related.append((a, sim))
        related.sort(key=lambda x: x[1], reverse=True)
        return related
    
    def search_cross_domain(self, query, source_domain=None, top=5):
        """Search for similar experiences across domains."""
        qt = tokens(query)
        
        # Get all triples
        self.cur.execute("SELECT * FROM triples")
        all_triples = self.cur.fetchall()
        
        results = []
        for t in all_triples:
            # Compute text similarity
            triple_text = f"{t['symptom']} {t['cause']} {t['solution']}"
            triple_tokens = tokens(triple_text)
            text_sim = compute_similarity(qt, triple_tokens)
            
            # Compute domain boost
            domain_boost = 1.0
            if source_domain:
                domain_boost = self.get_domain_similarity(source_domain, t['domain'])
            
            # Combined score
            confidence_boost = t['confidence'] or 0.5
            usage_boost = min(math.log(1 + t['usage_count']) * 0.1, 0.3)
            
            final_score = text_sim * domain_boost * (1 + confidence_boost + usage_boost)
            
            if text_sim > 0.1:  # Minimum threshold
                r = dict(t)
                r['tags'] = json.loads(r['tags'])
                r['text_similarity'] = round(text_sim, 3)
                r['domain_boost'] = round(domain_boost, 2)
                r['final_score'] = round(final_score, 3)
                results.append(r)
        
        results.sort(key=lambda x: -x['final_score'])
        return results[:top]
    
    def suggest_for_domain(self, domain, top=5):
        """Suggest relevant experiences for a domain."""
        # Get all triples NOT in this domain
        self.cur.execute("SELECT * FROM triples WHERE domain != ?", (domain,))
        all_triples = self.cur.fetchall()
        
        results = []
        for t in all_triples:
            domain_sim = self.get_domain_similarity(domain, t['domain'])
            if domain_sim >= 0.3:
                r = dict(t)
                r['tags'] = json.loads(r['tags'])
                r['domain_similarity'] = round(domain_sim, 2)
                r['final_score'] = round(domain_sim * (t['confidence'] or 0.5), 3)
                results.append(r)
        
        results.sort(key=lambda x: -x['final_score'])
        return results[:top]
    
    def list_domains(self):
        """List all domains with experience counts."""
        self.cur.execute("""
            SELECT domain, COUNT(*) as cnt, AVG(confidence) as avg_conf
            FROM triples 
            GROUP BY domain 
            ORDER BY cnt DESC
        """)
        return [dict(r) for r in self.cur.fetchall()]
    
    def auto_map_experience(self, memory_id, target_domain):
        """Auto-extract triple from memory and map to target domain."""
        from auto_extract_triples import extract_causal_elements
        
        self.cur.execute("SELECT * FROM episodic_memory WHERE id = ?", (memory_id,))
        row = self.cur.fetchone()
        if not row:
            return None
        
        text = f"{row['summary']} {row['detail']}"
        symptom, cause, solution = extract_causal_elements(text)
        
        if symptom and cause:
            tags = json.loads(row['tags']) if row['tags'] else []
            tags.extend(['cross-domain', f'from:{row["scene_type"]}'])
            
            from triples_v2 import TripleStoreV2
            tsv2 = TripleStoreV2()
            tid = tsv2.add(
                symptom=f"[{target_domain}] {symptom} — {row['summary'][:60]}",
                cause=cause,
                solution=solution or '待补充',
                tags=list(set(tags)),
                domain=target_domain,
                confidence=0.5,
                linked_memory_id=memory_id,
                source='cross-project-mapping'
            )
            return tid
        return None


def cmd_search(args):
    """Search cross-domain experiences."""
    cpr = CrossProjectReuse()
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
        print(f"      领域: {r['domain']} → 来源: {r['source']}")
        print()


def cmd_suggest(args):
    """Suggest experiences for a domain."""
    cpr = CrossProjectReuse()
    results = cpr.suggest_for_domain(args.domain, args.top)
    
    if not results:
        print(f"领域「{args.domain}」没有可借鉴的跨域经验")
        return
    
    print(f"📚 领域「{args.domain}」可借鉴的经验:\n")
    for i, r in enumerate(results, 1):
        print(f"  [{i}] 域相似度:{r['domain_similarity']} | {r['symptom'][:60]}")
        print(f"      来自: {r['domain']} | 置信: {r['confidence']}")
        print()


def cmd_domains(args):
    """List all domains."""
    cpr = CrossProjectReuse()
    domains = cpr.list_domains()
    
    if not domains:
        print("暂无领域数据")
        return
    
    print("📊 领域经验分布:\n")
    for d in domains:
        bar = '█' * min(d['cnt'] * 3, 20)
        print(f"  {d['domain']:20} {d['cnt']:3}条  平均置信:{d['avg_conf']:.2f} {bar}")


def cmd_related(args):
    """List related domains."""
    cpr = CrossProjectReuse()
    related = cpr.find_related_domains(args.domain, args.threshold)
    
    if not related:
        print(f"领域「{args.domain}」没有相关域")
        return
    
    print(f"🔗 与「{args.domain}」相关的领域:\n")
    for domain, sim in related:
        bar = '█' * int(sim * 20)
        print(f"  {domain:20} 相似度: {sim:.2f} {bar}")


def cmd_map(args):
    """Map a memory to target domain."""
    cpr = CrossProjectReuse()
    tid = cpr.auto_map_experience(args.memory_id, args.to_domain)
    if tid:
        print(f"✅ 记忆 #{args.memory_id} 已映射到 {args.to_domain}，三元组 #{tid}")
    else:
        print(f"❌ 无法从记忆 #{args.memory_id} 提取因果模式")


def main():
    import argparse
    p = argparse.ArgumentParser(description='Cross-Project Experience Reuse')
    sub = p.add_subparsers(dest='command')
    
    p_search = sub.add_parser('search', help='Search cross-domain')
    p_search.add_argument('query')
    p_search.add_argument('--from-domain', default=None, help='Source domain')
    p_search.add_argument('--top', type=int, default=5)
    
    p_suggest = sub.add_parser('suggest', help='Suggest for domain')
    p_suggest.add_argument('domain')
    p_suggest.add_argument('--top', type=int, default=5)
    
    sub.add_parser('domains', help='List domains')
    
    p_related = sub.add_parser('related', help='List related domains')
    p_related.add_argument('domain')
    p_related.add_argument('--threshold', type=float, default=0.3)
    
    p_map = sub.add_parser('map', help='Map memory to domain')
    p_map.add_argument('memory_id', type=int)
    p_map.add_argument('to_domain')
    
    args = p.parse_args()
    cmds = {
        'search': cmd_search, 'suggest': cmd_suggest, 'domains': cmd_domains,
        'related': cmd_related, 'map': cmd_map
    }
    handler = cmds.get(args.command)
    if handler:
        handler(args)
    else:
        p.print_help()


if __name__ == '__main__':
    main()
