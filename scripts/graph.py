#!/usr/bin/env python3
# ============================================================================
# SoulMem — Knowledge Graph Engine
# Entity extraction, relationship discovery, and graph traversal search.
#
# Usage:
#   python3 scripts/graph.py build          # Build graph from all memories
#   python3 scripts/graph.py search "query" # Graph-enhanced search
#   python3 scripts/graph.py show           # Show graph statistics
#   python3 scripts/graph.py entities       # List top entities
#   python3 scripts/graph.py related <id>   # Find related memories via graph
# ============================================================================
import os
import sys
import json
import sqlite3
import re
from collections import Counter, defaultdict
from datetime import datetime

WORKSPACE = os.environ.get("SOULMEM_WORKSPACE", os.path.expanduser("~/.openclaw/workspace"))
DB_PATH = os.path.join(WORKSPACE, "memory", "episodic_memory.db")

# -- Known entity dictionary (for matching without LLM) --
KNOWN_ENTITIES = {
    # People
    "郭锐": "person", "guorui": "person",
    "Pablo": "person", "pablo": "person",
    "Iris": "person", "iris": "person",
    "KK": "person", "kk": "person", "小kk": "person",
    "KK5": "person", "KK6": "person",
    "Ryan": "person", "ryan": "person",
    # Projects
    "SoulMem": "project", "soulmem": "project",
    "LinkClaw": "project", "linkclaw": "project",
    "Wiki": "project", "wiki": "project",
    "KK": "project",  # ambiguous, handled specially
    "KK主页": "project", "KK6主页": "project", "主页": "project",
    "小渔打分": "project", "打分系统": "project",
    "Claude Code": "tool", "Claude": "tool",
    "GitHub": "tool", "git": "tool",
    "OpenClaw": "tool", "openclaw": "tool",
    "Ollama": "tool", "LongCat": "tool",
    "飞书": "tool", "Feishu": "tool",
}

# Chinese name pattern (2-4 hanzi that aren't common words)
CN_NAME_RE = re.compile(r'(?<![\u4e00-\u9fff])([A-Z][a-z]{1,15}|[\u4e00-\u9fff]{2,4})(?![\a-zA-Z0-9])')
# Quoted terms
QUOTED_RE = re.compile(r"[\u300c\u300e\u0022]([^\u300d\u300f\u0022]{2,20})[\u300d\u300f\u0022]")


class KnowledgeGraph:
    def __init__(self, db_path=None):
        self.conn = sqlite3.connect(db_path or DB_PATH)
        self.conn.row_factory = sqlite3.Row
        self.cur = self.conn.cursor()
        self._init_schema()

    def _init_schema(self):
        """Create graph tables if not exist."""
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
                PRIMARY KEY (memory_id, entity_id),
                FOREIGN KEY (memory_id) REFERENCES episodic_memory(id),
                FOREIGN KEY (entity_id) REFERENCES entities(id)
            );
            CREATE TABLE IF NOT EXISTS relationships (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_id INTEGER NOT NULL,
                target_id INTEGER NOT NULL,
                relation_type TEXT DEFAULT 'associated',
                weight REAL DEFAULT 1.0,
                memory_ids TEXT DEFAULT '[]',
                created_at TEXT DEFAULT (datetime('now', 'localtime')),
                FOREIGN KEY (source_id) REFERENCES entities(id),
                FOREIGN KEY (target_id) REFERENCES entities(id)
            );
            CREATE INDEX IF NOT EXISTS idx_entity_name ON entities(name);
            CREATE INDEX IF NOT EXISTS idx_entity_mentions_mid ON entity_mentions(memory_id);
            CREATE INDEX IF NOT EXISTS idx_rel_source ON relationships(source_id);
            CREATE INDEX IF NOT EXISTS idx_rel_target ON relationships(target_id);
        """)
        self.conn.commit()

    def extract_entities(self, text: str) -> list:
        """Extract entities from text using known dictionary + heuristics."""
        if not text:
            return []

        entities = []
        text_lower = text.lower()

        # Known entity matching (case-insensitive, longest match first)
        sorted_known = sorted(KNOWN_ENTITIES.keys(), key=len, reverse=True)
        matched_positions = set()

        for name in sorted_known:
            name_lower = name.lower()
            start = 0
            while True:
                pos = text_lower.find(name_lower, start)
                if pos == -1:
                    break
                # Check for overlapping matches
                positions = set(range(pos, pos + len(name)))
                if positions & matched_positions:
                    start = pos + 1
                    continue
                matched_positions.update(positions)
                entities.append((name, KNOWN_ENTITIES[name]))
                start = pos + len(name)

        # Quoted terms (potential entities)
        for match in QUOTED_RE.finditer(text):
            term = match.group(1)
            if term and term not in [e[0] for e in entities]:
                entities.append((term, "concept"))

        return entities

    def index_memory(self, memory_id: int, text: str):
        """Extract entities from a memory and add to graph."""
        entities = self.extract_entities(text)
        if not entities:
            return

        now = datetime.now().isoformat()

        for name, etype in entities:
            # Insert or update entity
            self.cur.execute(
                'SELECT id, mention_count FROM entities WHERE name = ?', (name,)
            )
            row = self.cur.fetchone()
            if row:
                eid = row['id']
                self.cur.execute(
                    'UPDATE entities SET mention_count = ?, last_seen = ? WHERE id = ?',
                    (row['mention_count'] + 1, now, eid)
                )
            else:
                self.cur.execute(
                    'INSERT INTO entities (name, type, mention_count, first_seen, last_seen) VALUES (?, ?, 1, ?, ?)',
                    (name, etype, now, now)
                )
                eid = self.cur.lastrowid

            # Link entity to memory
            self.cur.execute(
                'INSERT OR IGNORE INTO entity_mentions (memory_id, entity_id) VALUES (?, ?)',
                (memory_id, eid)
            )

        self.conn.commit()

        # Build relationships between co-occurring entities
        self._build_relationships(memory_id, entities)

    def _build_relationships(self, memory_id: int, entities: list):
        """Create relationships between entities appearing in the same memory."""
        if len(entities) < 2:
            return

        now = datetime.now().isoformat()

        for i in range(len(entities)):
            for j in range(i + 1, len(entities)):
                name_a, type_a = entities[i]
                name_b, type_b = entities[j]

                # Get entity IDs
                self.cur.execute('SELECT id FROM entities WHERE name = ?', (name_a,))
                row_a = self.cur.fetchone()
                self.cur.execute('SELECT id FROM entities WHERE name = ?', (name_b,))
                row_b = self.cur.fetchone()

                if not row_a or not row_b:
                    continue

                id_a, id_b = row_a['id'], row_b['id']

                # Check if relationship exists
                self.cur.execute(
                    'SELECT id, weight, memory_ids FROM relationships WHERE source_id = ? AND target_id = ?',
                    (id_a, id_b)
                )
                row = self.cur.fetchone()
                mem_ids = json.loads(row['memory_ids']) if row else []
                weight = row['weight'] if row else 0

                if memory_id not in mem_ids:
                    mem_ids.append(memory_id)
                    weight += 1.0

                if row:
                    self.cur.execute(
                        'UPDATE relationships SET weight = ?, memory_ids = ? WHERE id = ?',
                        (weight, json.dumps(mem_ids), row['id'])
                    )
                else:
                    self.cur.execute(
                        'INSERT INTO relationships (source_id, target_id, relation_type, weight, memory_ids) VALUES (?, ?, ?, ?, ?)',
                        (id_a, id_b, 'associated', weight, json.dumps(mem_ids))
                    )

        self.conn.commit()

    def build(self):
        """Rebuild entire graph from all memories."""
        # Clear existing graph data
        self.cur.execute('DELETE FROM relationships')
        self.cur.execute('DELETE FROM entity_mentions')
        self.cur.execute('DELETE FROM entities')
        self.conn.commit()

        # Process all memories
        self.cur.execute('SELECT id, summary, detail FROM episodic_memory')
        rows = self.cur.fetchall()

        count = 0
        for row in rows:
            text = f"{row['summary']} {row['detail']}"
            self.index_memory(row['id'], text)
            count += 1

        self.conn.commit()

        # Stats
        self.cur.execute('SELECT COUNT(*) FROM entities')
        entity_count = self.cur.fetchone()[0]
        self.cur.execute('SELECT COUNT(*) FROM relationships')
        rel_count = self.cur.fetchone()[0]

        print(f"✅ 知识图谱构建完成: {entity_count} 实体, {rel_count} 关系 (从 {count} 条记忆)")

    def get_related_memories(self, memory_id: int, depth: int = 2) -> list:
        """Find related memories via graph traversal (BFS)."""
        if depth < 1:
            return []

        # Get entities in this memory
        self.cur.execute("""
            SELECT e.id, e.name, e.type FROM entities e
            JOIN entity_mentions em ON e.id = em.entity_id
            WHERE em.memory_id = ?
        """, (memory_id,))
        entities = self.cur.fetchall()

        if not entities:
            return []

        entity_ids = [e['id'] for e in entities]

        # BFS: find related entities then their memories
        visited_entities = set(entity_ids)
        current_level = set(entity_ids)
        all_related_memories = set()

        for d in range(depth):
            if not current_level:
                break

            # Find relationships involving current level entities
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

            # Get memories of these entities
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

        # Fetch the actual memory records
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

    def search(self, query: str, top: int = 10) -> dict:
        """Enhanced search: combine keyword match + graph expansion."""
        # First: standard keyword search across all memories
        qt = query.lower().split()
        if not qt:
            return {'entities': [], 'memories': [], 'graph_expanded': []}

        self.cur.execute('SELECT id, summary, detail, scene_type, memory_date FROM episodic_memory')
        all_mems = self.cur.fetchall()

        # Keyword matching
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

        # Sort by match count
        keyword_results.sort(key=lambda x: x['match_count'], reverse=True)
        top_keyword = keyword_results[:top]

        # Graph expansion: for each keyword result, find graph-related
        expanded = {}
        for mem in top_keyword[:5]:
            related = self.get_related_memories(mem['id'], depth=2)
            for r in related:
                if r['id'] not in [m['id'] for m in top_keyword]:
                    if r['id'] not in expanded:
                        expanded[r['id']] = r
                        expanded[r['id']]['via_graph'] = True

        # Entities found in query
        query_entities = self.extract_entities(query)

        return {
            'entities': query_entities,
            'memories': top_keyword,
            'graph_expanded': list(expanded.values())[:top],
        }

    def get_stats(self) -> dict:
        """Return graph statistics."""
        self.cur.execute('SELECT COUNT(*) FROM entities')
        entity_count = self.cur.fetchone()[0]
        self.cur.execute('SELECT COUNT(*) FROM relationships')
        rel_count = self.cur.fetchone()[0]
        self.cur.execute('SELECT COUNT(*) FROM entity_mentions')
        mention_count = self.cur.fetchone()[0]

        # Top entities
        self.cur.execute('SELECT name, type, mention_count FROM entities ORDER BY mention_count DESC LIMIT 15')
        top_entities = [{'name': r['name'], 'type': r['type'], 'mentions': r['mention_count']} for r in self.cur.fetchall()]

        # Type distribution
        self.cur.execute('SELECT type, COUNT(*) as cnt FROM entities GROUP BY type ORDER BY cnt DESC')
        types = {r['type']: r['cnt'] for r in self.cur.fetchall()}

        return {
            'entities': entity_count,
            'relationships': rel_count,
            'mentions': mention_count,
            'top_entities': top_entities,
            'type_distribution': types,
        }

    def get_top_entities(self, limit: int = 20) -> list:
        """Return top entities by mention count."""
        self.cur.execute('SELECT name, type, mention_count FROM entities ORDER BY mention_count DESC LIMIT ?', (limit,))
        return [{'name': r['name'], 'type': r['type'], 'mentions': r['mention_count']} for r in self.cur.fetchall()]


def cmd_build(args):
    """Build knowledge graph from all memories."""
    kg = KnowledgeGraph()
    kg.build()


def cmd_search(args):
    """Graph-enhanced search."""
    kg = KnowledgeGraph()
    query = args.query
    results = kg.search(query, args.top)

    print(f"🔍 '{query}' → 实体识别 + 图谱搜索\n")

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
    """Show graph statistics."""
    kg = KnowledgeGraph()
    stats = kg.get_stats()

    print("📊 知识图谱统计")
    print(f"   实体总数: {stats['entities']}")
    print(f"   关系总数: {stats['relationships']}")
    print(f"   提及次数: {stats['mentions']}")
    print()

    print("📈 类型分布:")
    for t, cnt in stats['type_distribution'].items():
        bar = '█' * min(cnt, 30)
        print(f"   {t:12} {cnt:4} {bar}")

    print("\n🏆 热门实体 Top 15:")
    for i, e in enumerate(stats['top_entities'], 1):
        print(f"   {i:2}. {e['name']:20} ({e['type']}) — {e['mentions']}次")


def cmd_entities(args):
    """List top entities."""
    kg = KnowledgeGraph()
    entities = kg.get_top_entities(args.limit)
    print(f"🏷️ Top {len(entities)} 实体:")
    for i, e in enumerate(entities, 1):
        print(f"   {i:2}. {e['name']:20} ({e['type']}) — {e['mentions']}次提及")


def cmd_related(args):
    """Find related memories for a given memory ID via graph."""
    kg = KnowledgeGraph()
    related = kg.get_related_memories(args.memory_id, args.depth)

    if not related:
        print(f"未找到与记忆 #{args.memory_id} 关联的记忆")
        return

    print(f"🔗 记忆 #{args.memory_id} 的图谱关联 (深度{args.depth}):")
    for i, m in enumerate(related, 1):
        print(f"   [{i}] ({m['scene_type']}) {m['summary']} [{m['memory_date']}]")


def main():
    import argparse
    p = argparse.ArgumentParser(description='SoulMem Knowledge Graph')
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

    args = p.parse_args()
    commands = {
        'build': cmd_build,
        'search': cmd_search,
        'show': cmd_show,
        'entities': cmd_entities,
        'related': cmd_related,
    }

    handler = commands.get(args.command)
    if handler:
        handler(args)
    else:
        p.print_help()


if __name__ == '__main__':
    main()
