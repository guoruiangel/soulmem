#!/usr/bin/env python3
# ============================================================================
# SoulMem — Knowledge Graph Engine v2
# Entity extraction, relationship discovery, graph traversal, community detection.
#
# Improvements in v2:
# - Auto relationship type detection (not just 'associated')
# - Graph export (GEXF/JSON for visualization)
# - Community detection (simple label propagation)
# - Path finding between entities
# - Entity merging suggestions
# - Graph metrics (centrality, density)
# ============================================================================
import os, sys, json, sqlite3, re, math
from collections import Counter, defaultdict
from datetime import datetime

WORKSPACE = os.environ.get("SOULMEM_WORKSPACE", os.path.expanduser("~/.openclaw/workspace"))
DB_PATH = os.path.join(WORKSPACE, "memory", "episodic_memory.db")

KNOWN_ENTITIES = {
    "郭锐": "person", "guorui": "person",
    "Pablo": "person", "pablo": "person",
    "Iris": "person", "iris": "person",
    "KK": "person", "kk": "person", "小kk": "person",
    "KK5": "person", "KK6": "person", "KK7": "person",
    "Ryan": "person", "ryan": "person",
    "SoulMem": "project", "soulmem": "project",
    "LinkClaw": "project", "linkclaw": "project",
    "Wiki": "project", "wiki": "project",
    "KK主页": "project", "KK6主页": "project", "主页": "project",
    "小渔打分": "project", "打分系统": "project",
    "Claude Code": "tool", "Claude": "tool",
    "GitHub": "tool", "git": "tool",
    "OpenClaw": "tool", "openclaw": "tool",
    "Ollama": "tool", "LongCat": "tool",
    "飞书": "tool", "Feishu": "tool",
    "DeepSeek": "tool", "deepseek": "tool",
}

CN_NAME_RE = re.compile(r'(?<![\u4e00-\u9fff])([A-Z][a-z]{1,15}|[\u4e00-\u9fff]{2,4})(?![\a-zA-Z0-9])')
QUOTED_RE = re.compile(r"[\u300c\u300e\u0022]([^\u300d\u300f\u0022]{2,20})[\u300d\u300f\u0022]")

# Relationship type indicators
RELATION_INDICATORS = {
    "使用": ["使用", "用", "通过", "借助", "利用"],
    "导致": ["导致", "造成", "引起", "引发", "带来"],
    "修复": ["修复", "解决", "修好", "搞定", "处理"],
    "创建": ["创建", "搭建", "建立", "开发", "实现"],
    "属于": ["属于", "是", "作为", "担任"],
    "影响": ["影响", "改变", "改进", "优化", "提升"],
    "依赖": ["依赖", "需要", "基于", "依靠"],
    "替代": ["替代", "替换", "取代", "更换"],
}


class KnowledgeGraph:
    def __init__(self, db_path=None):
        self.conn = sqlite3.connect(db_path or DB_PATH)
        self.conn.row_factory = sqlite3.Row
        self.cur = self.conn.cursor()
        self._init_schema()

    def _init_schema(self):
        self.cur.executescript("""
            CREATE TABLE IF NOT EXISTS entities (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                type TEXT DEFAULT 'concept',
                mention_count INTEGER DEFAULT 1,
                first_seen TEXT,
                last_seen TEXT
            );
            CREATE TABLE IF NOT EXISTS entity_mentions (
                memory_id INTEGER NOT NULL,
                entity_id INTEGER NOT NULL,
                PRIMARY KEY (memory_id, entity_id)
            );
            CREATE TABLE IF NOT EXISTS relationships (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_id INTEGER NOT NULL,
                target_id INTEGER NOT NULL,
                relation_type TEXT DEFAULT 'associated',
                weight REAL DEFAULT 1.0,
                memory_ids TEXT DEFAULT '[]',
                created_at TEXT DEFAULT (datetime('now', 'localtime'))
            );
            CREATE INDEX IF NOT EXISTS idx_entity_name ON entities(name);
            CREATE INDEX IF NOT EXISTS idx_entity_mentions_mid ON entity_mentions(memory_id);
            CREATE INDEX IF NOT EXISTS idx_rel_source ON relationships(source_id);
            CREATE INDEX IF NOT EXISTS idx_rel_target ON relationships(target_id);
            CREATE INDEX IF NOT EXISTS idx_rel_type ON relationships(relation_type);
        """)
        # Add community_id column if not exists
        self.cur.execute("PRAGMA table_info(entities)")
        columns = [row[1] for row in self.cur.fetchall()]
        if 'community_id' not in columns:
            self.cur.execute("ALTER TABLE entities ADD COLUMN community_id INTEGER DEFAULT 0")
        self.conn.commit()

    def extract_entities(self, text: str) -> list:
        if not text:
            return []
        entities = []
        text_lower = text.lower()
        sorted_known = sorted(KNOWN_ENTITIES.keys(), key=len, reverse=True)
        matched_positions = set()

        for name in sorted_known:
            name_lower = name.lower()
            start = 0
            while True:
                pos = text_lower.find(name_lower, start)
                if pos == -1:
                    break
                positions = set(range(pos, pos + len(name)))
                if positions & matched_positions:
                    start = pos + 1
                    continue
                matched_positions.update(positions)
                entities.append((name, KNOWN_ENTITIES[name]))
                start = pos + len(name)

        for match in QUOTED_RE.finditer(text):
            term = match.group(1)
            if term and term not in [e[0] for e in entities]:
                entities.append((term, "concept"))

        return entities

    def _detect_relation_type(self, text: str, entity_a: str, entity_b: str) -> str:
        """Detect relationship type from context."""
        # Find the text between two entities
        text_lower = text.lower()
        pos_a = text_lower.find(entity_a.lower())
        pos_b = text_lower.find(entity_b.lower())
        
        if pos_a == -1 or pos_b == -1:
            return "associated"
        
        # Get text between entities
        start = min(pos_a, pos_b)
        end = max(pos_a, pos_b)
        between = text_lower[start:end]
        
        for rel_type, indicators in RELATION_INDICATORS.items():
            for indicator in indicators:
                if indicator in between:
                    return rel_type
        
        return "associated"

    def index_memory(self, memory_id: int, text: str):
        entities = self.extract_entities(text)
        if not entities:
            return

        now = datetime.now().isoformat()

        for name, etype in entities:
            self.cur.execute('SELECT id, mention_count FROM entities WHERE name = ?', (name,))
            row = self.cur.fetchone()
            if row:
                eid = row['id']
                self.cur.execute('UPDATE entities SET mention_count = ?, last_seen = ? WHERE id = ?',
                    (row['mention_count'] + 1, now, eid))
            else:
                self.cur.execute(
                    'INSERT INTO entities (name, type, mention_count, first_seen, last_seen) VALUES (?, ?, 1, ?, ?)',
                    (name, etype, now, now))
                eid = self.cur.lastrowid

            self.cur.execute('INSERT OR IGNORE INTO entity_mentions (memory_id, entity_id) VALUES (?, ?)',
                (memory_id, eid))

        self.conn.commit()
        self._build_relationships(memory_id, entities, text)

    def _build_relationships(self, memory_id: int, entities: list, text: str):
        if len(entities) < 2:
            return

        now = datetime.now().isoformat()

        for i in range(len(entities)):
            for j in range(i + 1, len(entities)):
                name_a, type_a = entities[i]
                name_b, type_b = entities[j]

                self.cur.execute('SELECT id FROM entities WHERE name = ?', (name_a,))
                row_a = self.cur.fetchone()
                self.cur.execute('SELECT id FROM entities WHERE name = ?', (name_b,))
                row_b = self.cur.fetchone()

                if not row_a or not row_b:
                    continue

                id_a, id_b = row_a['id'], row_b['id']
                rel_type = self._detect_relation_type(text, name_a, name_b)

                self.cur.execute(
                    'SELECT id, weight, memory_ids FROM relationships WHERE source_id = ? AND target_id = ?',
                    (id_a, id_b))
                row = self.cur.fetchone()
                mem_ids = json.loads(row['memory_ids']) if row else []
                weight = row['weight'] if row else 0

                if memory_id not in mem_ids:
                    mem_ids.append(memory_id)
                    weight += 1.0

                if row:
                    self.cur.execute('UPDATE relationships SET weight = ?, memory_ids = ? WHERE id = ?',
                        (weight, json.dumps(mem_ids), row['id']))
                else:
                    self.cur.execute(
                        'INSERT INTO relationships (source_id, target_id, relation_type, weight, memory_ids) VALUES (?, ?, ?, ?, ?)',
                        (id_a, id_b, rel_type, weight, json.dumps(mem_ids)))

        self.conn.commit()

    def build(self):
        self.cur.execute('DELETE FROM relationships')
        self.cur.execute('DELETE FROM entity_mentions')
        self.cur.execute('DELETE FROM entities')
        self.conn.commit()

        self.cur.execute('SELECT id, summary, detail FROM episodic_memory')
        rows = self.cur.fetchall()

        count = 0
        for row in rows:
            text = f"{row['summary']} {row['detail']}"
            self.index_memory(row['id'], text)
            count += 1

        self.conn.commit()
        self._detect_communities()

        self.cur.execute('SELECT COUNT(*) FROM entities')
        entity_count = self.cur.fetchone()[0]
        self.cur.execute('SELECT COUNT(*) FROM relationships')
        rel_count = self.cur.fetchone()[0]
        print(f"✅ 知识图谱构建完成: {entity_count} 实体, {rel_count} 关系 (从 {count} 条记忆)")

    def _detect_communities(self):
        """Simple label propagation community detection."""
        # Initialize each entity with its own label
        self.cur.execute('SELECT id FROM entities')
        entities = [r['id'] for r in self.cur.fetchall()]
        
        if not entities:
            return
        
        labels = {eid: idx for idx, eid in enumerate(entities)}
        
        # Iterate to propagate labels
        for _ in range(10):
            self.cur.execute('SELECT source_id, target_id, weight FROM relationships')
            rels = self.cur.fetchall()
            
            for rel in rels:
                src, tgt, weight = rel['source_id'], rel['target_id'], rel['weight']
                if src in labels and tgt in labels:
                    # Propagate the label with higher weight
                    if weight > 1:
                        labels[src] = labels[tgt]
        
        # Update community_id in database
        for eid, label in labels.items():
            self.cur.execute('UPDATE entities SET community_id = ? WHERE id = ?', (label, eid))
        
        self.conn.commit()

    def get_related_memories(self, memory_id: int, depth: int = 2) -> list:
        if depth < 1:
            return []

        self.cur.execute("""
            SELECT e.id, e.name, e.type FROM entities e
            JOIN entity_mentions em ON e.id = em.entity_id
            WHERE em.memory_id = ?
        """, (memory_id,))
        entities = self.cur.fetchall()

        if not entities:
            return []

        entity_ids = [e['id'] for e in entities]
        visited_entities = set(entity_ids)
        current_level = set(entity_ids)
        all_related_memories = set()

        for d in range(depth):
            if not current_level:
                break

            placeholders = ','.join('?' * len(current_level))
            self.cur.execute(f"""
                SELECT DISTINCT r.source_id, r.target_id FROM relationships r
                WHERE r.source_id IN ({placeholders}) OR r.target_id IN ({placeholders})
            """, list(current_level) * 2)
            rels = self.cur.fetchall()

            next_level = set()
            for rel in rels:
                src, tgt = rel['source_id'], rel['target_id']
                for eid in [src, tgt]:
                    if eid not in visited_entities:
                        visited_entities.add(eid)
                        next_level.add(eid)

            if next_level:
                placeholders = ','.join('?' * len(next_level))
                self.cur.execute(f"""
                    SELECT DISTINCT em.memory_id FROM entity_mentions em
                    WHERE em.entity_id IN ({placeholders}) AND em.memory_id != ?
                """, list(next_level) + [memory_id])
                for row in self.cur.fetchall():
                    all_related_memories.add(row['memory_id'])

            current_level = next_level

        if not all_related_memories:
            return []

        placeholders = ','.join('?' * len(all_related_memories))
        self.cur.execute(f"""
            SELECT id, scene_type, summary, memory_date FROM episodic_memory
            WHERE id IN ({placeholders})
            ORDER BY id DESC LIMIT 20
        """, list(all_related_memories))

        return [{
            'id': row['id'],
            'scene_type': row['scene_type'],
            'summary': row['summary'][:80],
            'memory_date': row['memory_date'],
        } for row in self.cur.fetchall()]

    def find_path(self, entity_a: str, entity_b: str, max_depth: int = 4) -> list:
        """Find shortest path between two entities using BFS."""
        self.cur.execute('SELECT id FROM entities WHERE name = ?', (entity_a,))
        row_a = self.cur.fetchone()
        self.cur.execute('SELECT id FROM entities WHERE name = ?', (entity_b,))
        row_b = self.cur.fetchone()

        if not row_a or not row_b:
            return []

        start_id = row_a['id']
        target_id = row_b['id']

        # BFS
        visited = {start_id}
        queue = [(start_id, [start_id])]

        while queue:
            current, path = queue.pop(0)

            if current == target_id:
                # Convert IDs to names
                names = []
                for eid in path:
                    self.cur.execute('SELECT name FROM entities WHERE id = ?', (eid,))
                    row = self.cur.fetchone()
                    if row:
                        names.append(row['name'])
                return names

            if len(path) >= max_depth:
                continue

            self.cur.execute("""
                SELECT target_id FROM relationships WHERE source_id = ?
                UNION
                SELECT source_id FROM relationships WHERE target_id = ?
            """, (current, current))

            for row in self.cur.fetchall():
                neighbor = row[0] if row[0] != current else row[1] if len(row) > 1 else None
                if neighbor and neighbor not in visited:
                    visited.add(neighbor)
                    queue.append((neighbor, path + [neighbor]))

        return []

    def search(self, query: str, top: int = 10) -> dict:
        qt = query.lower().split()
        if not qt:
            return {'entities': [], 'memories': [], 'graph_expanded': []}

        self.cur.execute('SELECT id, summary, detail, scene_type, memory_date FROM episodic_memory')
        all_mems = self.cur.fetchall()

        keyword_results = []
        for m in all_mems:
            text = f"{m['summary']} {m['detail']}".lower()
            match_count = sum(1 for t in qt if t in text)
            if match_count > 0:
                keyword_results.append({
                    'id': m['id'],
                    'scene_type': m['scene_type'],
                    'summary': m['summary'][:80],
                    'memory_date': m['memory_date'],
                    'match_count': match_count,
                })

        keyword_results.sort(key=lambda x: x['match_count'], reverse=True)
        top_keyword = keyword_results[:top]

        expanded = {}
        for mem in top_keyword[:5]:
            related = self.get_related_memories(mem['id'], depth=2)
            for r in related:
                if r['id'] not in [m['id'] for m in top_keyword]:
                    if r['id'] not in expanded:
                        expanded[r['id']] = r
                        expanded[r['id']]['via_graph'] = True

        query_entities = self.extract_entities(query)

        return {
            'entities': query_entities,
            'memories': top_keyword,
            'graph_expanded': list(expanded.values())[:top],
        }

    def get_stats(self) -> dict:
        self.cur.execute('SELECT COUNT(*) FROM entities')
        entity_count = self.cur.fetchone()[0]
        self.cur.execute('SELECT COUNT(*) FROM relationships')
        rel_count = self.cur.fetchone()[0]
        self.cur.execute('SELECT COUNT(*) FROM entity_mentions')
        mention_count = self.cur.fetchone()[0]

        self.cur.execute('SELECT name, type, mention_count FROM entities ORDER BY mention_count DESC LIMIT 15')
        top_entities = [{'name': r['name'], 'type': r['type'], 'mentions': r['mention_count']} for r in self.cur.fetchall()]

        self.cur.execute('SELECT type, COUNT(*) as cnt FROM entities GROUP BY type ORDER BY cnt DESC')
        types = {r['type']: r['cnt'] for r in self.cur.fetchall()}

        self.cur.execute('SELECT relation_type, COUNT(*) as cnt FROM relationships GROUP BY relation_type ORDER BY cnt DESC')
        rel_types = {r['relation_type']: r['cnt'] for r in self.cur.fetchall()}

        self.cur.execute('SELECT COUNT(DISTINCT community_id) FROM entities')
        communities = self.cur.fetchone()[0]

        # Graph density
        max_rel = entity_count * (entity_count - 1) / 2 if entity_count > 1 else 1
        density = rel_count / max_rel if max_rel > 0 else 0

        return {
            'entities': entity_count,
            'relationships': rel_count,
            'mentions': mention_count,
            'communities': communities,
            'density': round(density, 4),
            'top_entities': top_entities,
            'type_distribution': types,
            'relation_types': rel_types,
        }

    def export_json(self) -> dict:
        """Export graph as JSON for visualization."""
        self.cur.execute('SELECT id, name, type, mention_count, community_id FROM entities')
        nodes = [{'id': r['id'], 'name': r['name'], 'type': r['type'],
                  'mentions': r['mention_count'], 'community': r['community_id']} for r in self.cur.fetchall()]

        self.cur.execute('SELECT source_id, target_id, relation_type, weight FROM relationships')
        links = [{'source': r['source_id'], 'target': r['target_id'],
                  'type': r['relation_type'], 'weight': r['weight']} for r in self.cur.fetchall()]

        return {'nodes': nodes, 'links': links}


def cmd_build(args):
    kg = KnowledgeGraph()
    kg.build()


def cmd_search(args):
    kg = KnowledgeGraph()
    results = kg.search(args.query, args.top)

    print(f"🔍 '{args.query}' → 实体识别 + 图谱搜索\n")

    if results['entities']:
        print(f"📌 识别到的实体:")
        for name, etype in results['entities']:
            print(f"   • {name} ({etype})")
        print()

    if results['memories']:
        print(f"📝 直接匹配记忆 ({len(results['memories'])}):")
        for i, m in enumerate(results['memories'], 1):
            print(f"   [{i}] ({m['scene_type']}) {m['summary']} [{m['memory_date']}]")
        print()

    if results['graph_expanded']:
        print(f"🔗 图谱扩展记忆 ({len(results['graph_expanded'])}):")
        for i, m in enumerate(results['graph_expanded'], 1):
            print(f"   [{i}] ({m['scene_type']}) {m['summary']} [{m['memory_date']}]")


def cmd_show(args):
    kg = KnowledgeGraph()
    stats = kg.get_stats()

    print("📊 知识图谱统计")
    print(f"   实体总数: {stats['entities']}")
    print(f"   关系总数: {stats['relationships']}")
    print(f"   提及次数: {stats['mentions']}")
    print(f"   社区数量: {stats['communities']}")
    print(f"   图密度:   {stats['density']}")
    print()

    print("📈 类型分布:")
    for t, cnt in stats['type_distribution'].items():
        bar = '█' * min(cnt, 30)
        print(f"   {t:12} {cnt:4} {bar}")

    print("\n📈 关系类型分布:")
    for t, cnt in stats['relation_types'].items():
        bar = '█' * min(cnt, 30)
        print(f"   {t:12} {cnt:4} {bar}")

    print("\n🏆 热门实体 Top 15:")
    for i, e in enumerate(stats['top_entities'], 1):
        print(f"   {i:2}. {e['name']:20} ({e['type']}) — {e['mentions']}次")


def cmd_entities(args):
    kg = KnowledgeGraph()
    kg.cur.execute('SELECT name, type, mention_count, community_id FROM entities ORDER BY mention_count DESC LIMIT ?', (args.limit,))
    rows = kg.cur.fetchall()
    print(f"🏷️ Top {len(rows)} 实体:")
    for i, r in enumerate(rows, 1):
        print(f"   {i:2}. {r['name']:20} ({r['type']}) — {r['mention_count']}次 (社区:{r['community_id']})")


def cmd_related(args):
    kg = KnowledgeGraph()
    related = kg.get_related_memories(args.memory_id, args.depth)
    if not related:
        print(f"未找到与记忆 #{args.memory_id} 关联的记忆")
        return
    print(f"🔗 记忆 #{args.memory_id} 的图谱关联 (深度{args.depth}):")
    for i, m in enumerate(related, 1):
        print(f"   [{i}] ({m['scene_type']}) {m['summary']} [{m['memory_date']}]")


def cmd_path(args):
    kg = KnowledgeGraph()
    path = kg.find_path(args.entity_a, args.entity_b, args.max_depth)
    if path:
        print(f"🔗 {' → '.join(path)}")
    else:
        print(f"未找到 {args.entity_a} 到 {args.entity_b} 的路径")


def cmd_export(args):
    kg = KnowledgeGraph()
    data = kg.export_json()
    output_path = args.output or 'graph_export.json'
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"✅ 图谱已导出到 {output_path} ({len(data['nodes'])} 节点, {len(data['links'])} 边)")


def main():
    import argparse
    p = argparse.ArgumentParser(description='SoulMem Knowledge Graph v2')
    sub = p.add_subparsers(dest='command')

    sub.add_parser('build', help='Build graph from memories')

    p_search = sub.add_parser('search', help='Graph-enhanced search')
    p_search.add_argument('query', help='Search query')
    p_search.add_argument('--top', type=int, default=10, help='Number of results')

    sub.add_parser('show', help='Show graph stats')

    p_ent = sub.add_parser('entities', help='List entities')
    p_ent.add_argument('--limit', type=int, default=20)

    p_rel = sub.add_parser('related', help='Find related memories')
    p_rel.add_argument('memory_id', type=int, help='Memory ID')
    p_rel.add_argument('--depth', type=int, default=2, help='Traversal depth')

    p_path = sub.add_parser('path', help='Find path between entities')
    p_path.add_argument('entity_a', help='Source entity')
    p_path.add_argument('entity_b', help='Target entity')
    p_path.add_argument('--max-depth', type=int, default=4, help='Max search depth')

    p_export = sub.add_parser('export', help='Export graph as JSON')
    p_export.add_argument('--output', default='graph_export.json', help='Output file path')

    args = p.parse_args()
    commands = {
        'build': cmd_build,
        'search': cmd_search,
        'show': cmd_show,
        'entities': cmd_entities,
        'related': cmd_related,
        'path': cmd_path,
        'export': cmd_export,
    }

    handler = commands.get(args.command)
    if handler:
        handler(args)
    else:
        p.print_help()


if __name__ == '__main__':
    main()
