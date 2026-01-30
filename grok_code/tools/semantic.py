"""Semantic codebase index: embeddings + dep graph."""

import json
import pickle
from pathlib import Path
from typing import List, Dict, Tuple
import numpy as np
from dataclasses import dataclass
import networkx as nx
from sentence_transformers import SentenceTransformer
import ast  # Python import graph
from .base import Tool
from .file_ops import glob

@dataclass
class Chunk:
    path: str
    start_line: int
    end_line: int
    text: str
    embedding: List[float]

class SemanticIndex:
    def __init__(self, project_root: str = "."):
        self.root = Path(project_root).resolve()
        self.embed_model = SentenceTransformer('all-MiniLM-L6-v2')
        self.chunks_file = self.root / ".grok" / "embeddings.jsonl"
        self.graph_file = self.root / ".grok" / "dep_graph.pkl"
        self._chunks: List[Chunk] = []
        self._embeddings: np.ndarray = np.array([])
        self._graph: nx.DiGraph = nx.DiGraph()
        self._path_to_idx: Dict[str, int] = {}

    def build(self) -> Tuple[int, int]:
        \"\"\"Build embeddings + graph. Returns (chunks, nodes/edges)\"\"\"
        self._chunks = []
        py_files = glob("**/*.py", path=str(self.root))
        for file_path in py_files[:100]:  # Limit
            full_path = self.root / file_path
            chunks = self._chunk_file(full_path)
            for chunk in chunks:
                emb = self.embed_model.encode(chunk.text).tolist()
                self._chunks.append(Chunk(file_path, chunk.start, chunk.end, chunk.text, emb))
        self._embeddings = np.array([c.embedding for c in self._chunks])
        self._path_to_idx = {c.path: i for i, c in enumerate(self._chunks)}
        self._save()
        nodes = len(self._graph.nodes)
        edges = len(self._graph.edges)
        return len(self._chunks), nodes + edges

    def _chunk_file(self, path: Path) -> List:
        \"\"\"Chunk into funcs/classes (AST).\"\"\"
        chunks = []
        try:
            content = path.read_text()
            tree = ast.parse(content)
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.ClassDef, ast.AsyncFunctionDef)):
                    start = node.lineno
                    end = node.end_lineno or start
                    lines = content.splitlines()
                    text = '\\n'.join(lines[start-1:end])
                    chunks.append(type('Chunk', (), {'start': start, 'end': end, 'text': text})())
        except:
            # Fallback whole file
            chunks.append(type('Chunk', (), {'start': 1, 'end': 999, 'text': path.read_text()})())
        return chunks

    def _build_graph(self):
        \"\"\"Import dep graph (AST).\"\"\"
        self._graph = nx.DiGraph()
        for chunk in self._chunks:
            path = self.root / chunk.path
            tree = ast.parse(chunk.text)
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom):
                    mod = node.module
                    if mod:
                        self._graph.add_edge(chunk.path, f"{mod}.py")  # Stub
        nx.write_gpickle(self._graph, self._graph_file)

    def _save(self):
        Path(self.chunks_file).parent.mkdir(exist_ok=True)
        with open(self.chunks_file, 'w') as f:
            for chunk in self._chunks:
                f.write(json.dumps({
                    'path': chunk.path, 'start': chunk.start, 'end': chunk.end,
                    'text': chunk.text, 'embedding': chunk.embedding
                }) + '\\n')
        nx.write_gpickle(self._graph, self._graph_file)

    def _load(self):
        self._chunks = []
        if self.chunks_file.exists():
            with open(self.chunks_file) as f:
                for line in f:
                    data = json.loads(line)
                    self._chunks.append(Chunk(**data))
            self._embeddings = np.array([c.embedding for c in self._chunks])
        if self.graph_file.exists():
            self._graph = nx.read_gpickle(self._graph_file)

    def search(self, query: str, k: int = 5, hops: int = 1) -> str:
        self._load()
        if not self._chunks:
            return "Index empty. Run build_semantic_index first."
        q_emb = self.embed_model.encode([query])
        sims = np.dot(self._embeddings, q_emb.T).flatten()
        top_idx = np.argsort(sims)[-k:][::-1]
        results = []
        for i in top_idx:
            chunk = self._chunks[i]
            score = sims[i]
            results.append(f"**{chunk.path}:{chunk.start}-{chunk.end}** ({score:.2f})\\n{chunk.text[:200]}...")
            # Graph hops: files connected
            if hops > 0 and chunk.path in self._path_to_idx:
                neighbors = nx.ego_graph(self._graph, chunk.path, radius=hops).nodes
                results.append(f"Related: {', '.join(neighbors[:3])}")
        return '\\n\\n'.join(results)