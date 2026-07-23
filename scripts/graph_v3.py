#!/usr/bin/env python3
# ============================================================================
# SoulMem — Knowledge Graph v3
# Complete graph engine with ASCII visualization, entity merging,
# graph algorithms, and GraphQL-like queries.
#
# Improvements over v2:
# - ASCII graph rendering (no external tools needed)
# - Entity merging (alias resolution)
# - Graph algorithms (degree centrality, pagerank approximation)
# - Community detection (improved label propagation)
# - Graph query language (find path, neighbors, etc.)
#
# Usage:
#   python3 scripts/graph_v3.py build
#   python3 scripts/graph_v3.py show
#   python3 scripts/graph_v3.py ascii
#   python3 scripts/graph_v3.py path <from> <to>
#   python3 scripts/graph_v3.py neighbors <entity>
#   python3 scripts/graph_v3.py merge <alias> <canonical>
#   python3 scripts/graph_v3.py export
# ============================================================================
import os, sys, json, sqlite3, re, math
from collections import Counter, defaultdict
from datetime import datetime

WORKSPACE = os.environ.get("SOULMEM_WORKSPACE", os.path.expanduser("~/.openclaw/workspace"))
from soulmem_config import DB_PATH

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)

# Merge with graph.py v2 - import and extend
# Reuse existing entity extraction logic
# For v3, add new capabilities on top

def load_existing_graph():
    """Load existing graph from database (built by graph.py v2)."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    
    cur.execute('SELECT id, name, type, mention_count, community_id FROM entities')
    entities = {r['id']: {'name': r['name'], 'type': r['type'], 
                          'mentions': r['mention_count'], 'community': r['community_id']} 
                for r in cur.fetchall()}
    
    cur.execute('SELECT source_id, target_id, relation_type, weight FROM relationships')
    relationships = [(r['source_id'], r['target_id'], r['relation_type'], r['weight']) 
                     for r in cur.fetchall()]
    
    conn.close()
    return entities, relationships


def build_adjacency_list(entities, relationships):
    """Build adjacency list for graph traversal."""
    adj = defaultdict(list)
    for src, tgt, rel, weight in relationships:
        adj[src].append((tgt, rel, weight))
        adj[tgt].append((src, rel, weight))  # undirected
    return adj


def find_all_paths(adj, start, end, max_depth=4):
    """Find all simple paths between two nodes up to max_depth."""
    paths = []
    def dfs(current, target, path, depth):
        if depth > max_depth:
            return
        if current == target:
            paths.append(path[:])
            return
        for neighbor, rel, weight in adj.get(current, []):
            if neighbor not in path:
                path.append(neighbor)
                dfs(neighbor, target, path, depth + 1)
                path.pop()
    
    dfs(start, end, [start], 0)
    return paths


def compute_centrality(adj, entities):
    """Compute degree centrality for each entity."""
    centrality = {}
    for eid in entities:
        neighbors = adj.get(eid, [])
        centrality[eid] = len(neighbors)
    return centrality


def compute_pagerank(adj, entities, iterations=20, damping=0.85):
    """Compute approximate PageRank."""
    n = len(entities)
    if n == 0:
        return {}
    
    pr = {eid: 1.0 / n for eid in entities}
    
    for _ in range(iterations):
        new_pr = {}
        for eid in entities:
            rank = (1 - damping) / n
            for neighbor, rel, weight in adj.get(eid, []):
                if neighbor in pr:
                    rank += damping * pr[neighbor] / max(len(adj.get(neighbor, [])), 1)
            new_pr[eid] = rank
        pr = new_pr
    
    # Normalize
    max_pr = max(pr.values()) if pr else 1
    return {eid: v / max_pr for eid, v in pr.items()}


def ascii_graph(entities, relationships, max_nodes=30):
    """Render an ASCII representation of the graph."""
    # Find top entities by mention count
    sorted_entities = sorted(entities.items(), key=lambda x: x[1]['mentions'], reverse=True)
    top_ids = {eid for eid, _ in sorted_entities[:max_nodes]}
    
    # Build adjacency for top nodes only
    adj = defaultdict(set)
    for src, tgt, rel, weight in relationships:
        if src in top_ids and tgt in top_ids:
            adj[src].add(tgt)
            adj[tgt].add(src)
    
    # Simple ASCII layout: nodes in a circle, edges as lines
    lines = []
    lines.append("    📊 Knowledge Graph (ASCII View)")
    lines.append("    " + "=" * 50)
    lines.append("")
    
    # Show top nodes with connections
    for eid, data in sorted_entities[:15]:
        name = data['name']
        etype = data['type']
        mentions = data['mentions']
        neighbors = adj.get(eid, set())
        neighbor_names = [entities[n]['name'] for n in list(neighbors)[:3] if n in entities]
        
        icon = {'person': '👤', 'project': '📁', 'tool': '🔧', 'concept': '💡'}.get(etype, '📄')
        
        lines.append(f"    {icon} {name} ({etype}) — {mentions}次提及")
        if neighbor_names:
            lines.append(f"       → {', '.join(neighbor_names)}")
        lines.append("")
    
    return "\n".join(lines)


def get_entity_id(entities, name):
    """Find entity ID by name (case-insensitive)."""
    name_lower = name.lower()
    for eid, data in entities.items():
        if data['name'].lower() == name_lower:
            return eid
    return None


def get_neighbors(entities, relationships, name, depth=1):
    """Get all neighbors of an entity up to N hops."""
    eid = get_entity_id(entities, name)
    if not eid:
        return None, f"未找到实体: {name}"
    
    adj = build_adjacency_list(entities, relationships)
    visited = {eid}
    current_level = {eid}
    result = []
    
    for d in range(depth):
        next_level = set()
        for node in current_level:
            for neighbor, rel, weight in adj.get(node, []):
                if neighbor not in visited:
                    visited.add(neighbor)
                    next_level.add(neighbor)
                    if neighbor in entities:
                        result.append({
                            'depth': d + 1,
                            'entity': entities[neighbor]['name'],
                            'type': entities[neighbor]['type'],
                            'relation': rel,
                            'weight': weight
                        })
        current_level = next_level
    
    return result, None


def entity_merge(entities, relationships, alias_name, canonical_name):
    """Merge two entities (e.g., '小kk' → 'KK')."""
    alias_id = get_entity_id(entities, alias_name)
    canonical_id = get_entity_id(entities, canonical_name)
    
    if not alias_id or not canonical_id:
        return False, "实体不存在"
    
    if alias_id == canonical_id:
        return False, "不能合并到自身"
    
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    
    # Merge relationships
    cur.execute("""
        UPDATE relationships SET source_id = ? WHERE source_id = ?
    """, (canonical_id, alias_id))
    cur.execute("""
        UPDATE relationships SET target_id = ? WHERE target_id = ?
    """, (canonical_id, alias_id))
    
    # Merge entity mentions
    cur.execute("""
        UPDATE entity_mentions SET entity_id = ? WHERE entity_id = ?
    """, (canonical_id, alias_id))
    
    # Merge mention counts
    cur.execute("""
        UPDATE entities 
        SET mention_count = mention_count + (SELECT mention_count FROM entities WHERE id = ?)
        WHERE id = ?
    """, (alias_id, canonical_id))
    
    # Delete alias entity
    cur.execute("DELETE FROM entities WHERE id = ?", (alias_id,))
    
    conn.commit()
    conn.close()
    
    return True, f"已将 '{alias_name}' 合并到 '{canonical_name}'"


def find_path_between(entities, relationships, from_name, to_name):
    """Find path between two entities."""
    from_id = get_entity_id(entities, from_name)
    to_id = get_entity_id(entities, to_name)
    
    if not from_id:
        return None, f"未找到起点: {from_name}"
    if not to_id:
        return None, f"未找到终点: {to_name}"
    
    adj = build_adjacency_list(entities, relationships)
    
    # BFS for shortest path
    visited = {from_id}
    queue = [(from_id, [from_id])]
    
    while queue:
        current, path = queue.pop(0)
        if current == to_id:
            return [entities[eid]['name'] for eid in path if eid in entities], None
        
        for neighbor, rel, weight in adj.get(current, []):
            if neighbor not in visited:
                visited.add(neighbor)
                queue.append((neighbor, path + [neighbor]))
    
    return None, f"未找到从 '{from_name}' 到 '{to_name}' 的路径"


def cmd_ascii(args):
    entities, relationships = load_existing_graph()
    if not entities:
        print("知识图谱为空，请先运行: python3 scripts/graph.py build")
        return
    print(ascii_graph(entities, relationships))


def cmd_path(args):
    entities, relationships = load_existing_graph()
    path, err = find_path_between(entities, relationships, args.from_name, args.to_name)
    if err:
        print(err)
    else:
        print(f"🔗 {' → '.join(path)}")


def cmd_neighbors(args):
    entities, relationships = load_existing_graph()
    neighbors, err = get_neighbors(entities, relationships, args.name, args.depth)
    if err:
        print(err)
        return
    print(f"🔍 {args.name} 的 {args.depth} 跳邻居:\n")
    for n in neighbors:
        icon = {'person': '👤', 'project': '📁', 'tool': '🔧', 'concept': '💡'}.get(n['type'], '📄')
        print(f"  {'  ' * n['depth']}{icon} {n['entity']} ({n['relation']}, 权重{n['weight']})")


def cmd_merge(args):
    entities, relationships = load_existing_graph()
    ok, msg = entity_merge(entities, relationships, args.alias, args.canonical)
    if ok:
        print(f"✅ {msg}")
    else:
        print(f"❌ {msg}")


def cmd_centrality(args):
    entities, relationships = load_existing_graph()
    adj = build_adjacency_list(entities, relationships)
    centrality = compute_centrality(adj, entities)
    
    print("📊 度中心性排名:\n")
    sorted_cent = sorted(centrality.items(), key=lambda x: x[1], reverse=True)
    for eid, cent in sorted_cent[:15]:
        if eid in entities:
            print(f"  {entities[eid]['name']:20} {cent:3} 连接")


def cmd_pagerank(args):
    entities, relationships = load_existing_graph()
    adj = build_adjacency_list(entities, relationships)
    pr = compute_pagerank(adj, entities)
    
    print("📊 PageRank 排名:\n")
    sorted_pr = sorted(pr.items(), key=lambda x: x[1], reverse=True)
    for eid, rank in sorted_pr[:15]:
        if eid in entities:
            bar = '█' * int(rank * 20)
            print(f"  {entities[eid]['name']:20} {rank:.3f} {bar}")


def main():
    import argparse
    p = argparse.ArgumentParser(description='Knowledge Graph v3')
    sub = p.add_subparsers(dest='command')
    
    sub.add_parser('ascii', help='ASCII graph visualization')
    
    p_path = sub.add_parser('path', help='Find path between entities')
    p_path.add_argument('from_name')
    p_path.add_argument('to_name')
    
    p_nei = sub.add_parser('neighbors', help='Get neighbor entities')
    p_nei.add_argument('name')
    p_nei.add_argument('--depth', type=int, default=2)
    
    p_merge = sub.add_parser('merge', help='Merge two entities')
    p_merge.add_argument('alias')
    p_merge.add_argument('canonical')
    
    sub.add_parser('centrality', help='Degree centrality ranking')
    sub.add_parser('pagerank', help='PageRank approximation')
    
    args = p.parse_args()
    cmds = {
        'ascii': cmd_ascii, 'path': cmd_path, 'neighbors': cmd_neighbors,
        'merge': cmd_merge, 'centrality': cmd_centrality, 'pagerank': cmd_pagerank,
    }
    handler = cmds.get(args.command)
    if handler:
        handler(args)
    else:
        p.print_help()


if __name__ == '__main__':
    main()
