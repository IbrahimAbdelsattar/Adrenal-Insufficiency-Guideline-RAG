import sys
import json
from pathlib import Path
from graphify.detect import detect
from graphify.extract import collect_files, extract
from graphify.build import build_from_json
from graphify.cluster import cluster, score_all
from graphify.analyze import god_nodes, surprising_connections, suggest_questions
from graphify.report import generate
from graphify.export import to_json
from graphify.detect import save_manifest
from datetime import datetime, timezone

# 1. Detect
print("Running detect...")
result = detect(Path('.'))
Path('graphify-out/.graphify_detect.json').write_text(json.dumps(result, ensure_ascii=False), encoding='utf-8')
print(f"Corpus: {result.get('total_files', 0)} files, ~{result.get('total_words', 0)} words")

# 2. AST Extraction for code files
code_files = []
for f in result.get('files', {}).get('code', []):
    code_files.extend(collect_files(Path(f)) if Path(f).is_dir() else [Path(f)])

if code_files:
    ast_result = extract(code_files, cache_root=Path('.'))
    print(f"AST: {len(ast_result['nodes'])} nodes, {len(ast_result['edges'])} edges")
else:
    ast_result = {'nodes':[], 'edges':[], 'hyperedges':[], 'input_tokens':0, 'output_tokens':0}
    print("No code files found.")

# 3. Empty semantic since docs don't require external LLM if unset, or merge
merged_nodes = list(ast_result['nodes'])
merged_edges = list(ast_result['edges'])
merged = {
    'nodes': merged_nodes,
    'edges': merged_edges,
    'hyperedges': [],
    'input_tokens': 0,
    'output_tokens': 0
}
Path('graphify-out/.graphify_extract.json').write_text(json.dumps(merged, indent=2, ensure_ascii=False), encoding='utf-8')

# 4. Build graph & cluster
G = build_from_json(merged, root='.', directed=False)
if G.number_of_nodes() == 0:
    print("Warning: Graph has 0 nodes.")
    sys.exit(0)

communities = cluster(G)
cohesion = score_all(G, communities)
gods = god_nodes(G)
surprises = surprising_connections(G, communities)
labels = {cid: f"Component {cid}" for cid in communities}
questions = suggest_questions(G, communities, labels)

to_json(G, communities, 'graphify-out/graph.json')
report = generate(G, communities, cohesion, labels, gods, surprises, result, {'input': 0, 'output': 0}, '.', suggested_questions=questions)
Path('graphify-out/GRAPH_REPORT.md').write_text(report, encoding='utf-8')

save_manifest(result.get('all_files') or result['files'], root='.')
print(f"Graph built successfully: {G.number_of_nodes()} nodes, {G.number_of_edges()} edges, {len(communities)} communities.")
