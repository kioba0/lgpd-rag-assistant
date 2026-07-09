import sys
from dataclasses import dataclass
from pathlib import Path

import chromadb
from sentence_transformers import SentenceTransformer

sys.path.insert(0, str(Path(__file__).parent))
from config import (
    CHROMA_DIR,
    COLLECTION_NAME,
    EMBEDDING_MODEL,
    MIN_SCORE,
    TOP_K,
)
from ingest import get_embedder


@dataclass
class Match:
    text: str
    score: float
    source: str
    page: int
    artigo_detectado: str


_collection = None


def get_collection():
    global _collection
    if _collection is None:
        client = chromadb.PersistentClient(path=str(CHROMA_DIR))
        _collection = client.get_collection(name=COLLECTION_NAME)
    return _collection


def search(query: str, top_k: int = TOP_K) -> tuple[list[Match], bool]:
    """
    Vetoriza query com SBERT, busca top_k chunks por cosine similarity no Chroma.
    Retorna (matches, base_suficiente).
    base_suficiente=False quando nenhum match supera MIN_SCORE.
    """
    embedder: SentenceTransformer = get_embedder()
    query_embedding = embedder.encode([query])[0].tolist()

    collection = get_collection()
    results = collection.query(
        query_embeddings=[query_embedding],
        n_results=top_k,
        include=["documents", "metadatas", "distances"],
    )

    matches = []
    for doc, meta, dist in zip(
        results["documents"][0],
        results["metadatas"][0],
        results["distances"][0],
    ):
        # Chroma com hnsw:space=cosine retorna distância (0=idêntico, 2=oposto)
        # Convertemos para score de similaridade [0, 1]
        score = 1 - (dist / 2)
        matches.append(
            Match(
                text=doc,
                score=round(score, 4),
                source=meta.get("source", ""),
                page=meta.get("page", 0),
                artigo_detectado=meta.get("artigo_detectado", ""),
            )
        )

    base_suficiente = any(m.score >= MIN_SCORE for m in matches)
    return matches, base_suficiente
