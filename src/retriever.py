"""
Módulo de recuperação vetorial com busca híbrida (semântico + keyword).

Estratégia:
1. Recupera N candidatos via cosine similarity no ChromaDB (N = top_k * 3)
2. Calcula um score de keywords (BM25-like) para cada candidato
3. Combina os scores: hybrid = α × semântico + (1-α) × keyword
4. Re-ordena e retorna os top_k melhores

Isso resolve o problema de termos específicos (ex: "cookies", "RIPD",
"dosimetria") que têm alta relevância lexical mas podem ter score
semântico mediano com embeddings genéricos.
"""

import math
import re
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

import chromadb

sys.path.insert(0, str(Path(__file__).parent))
from config import (
    CHROMA_DIR,
    COLLECTION_NAME,
    HYBRID_ALPHA,
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


import functools

@functools.lru_cache(maxsize=1)
def get_collection():
    try:
        client = chromadb.PersistentClient(path=str(CHROMA_DIR))
        return client.get_collection(name=COLLECTION_NAME)
    except Exception as e:
        raise RuntimeError(
            "Coleção não encontrada. Execute python src/ingest.py primeiro."
        ) from e


# ── Busca por keywords (BM25-like) ───────────────────────────────────

# Stopwords PT — termos que não carregam informação discriminativa
_STOPWORDS = frozenset({
    "a", "ao", "aos", "as", "à", "às", "com", "como", "da", "das", "de",
    "do", "dos", "e", "em", "é", "ela", "elas", "ele", "eles", "entre",
    "era", "essa", "essas", "esse", "esses", "esta", "estas", "este",
    "estes", "eu", "foi", "for", "há", "isso", "isto", "já", "lhe",
    "lhes", "mas", "me", "mesmo", "meu", "minha", "muito", "na", "nas",
    "não", "no", "nos", "nós", "num", "numa", "o", "os", "ou", "para",
    "pela", "pelas", "pelo", "pelos", "por", "qual", "quando", "que",
    "quem", "se", "sem", "ser", "seu", "sua", "são", "só", "também",
    "te", "tem", "têm", "ter", "ti", "tu", "tua", "tudo", "um", "uma",
    "uns", "umas", "você", "vocês",
})


def _tokenize(text: str) -> list[str]:
    """Tokeniza texto em palavras minúsculas >= 3 chars, sem stopwords."""
    tokens = re.findall(r"\b[a-záàâãéêíóôõúüç]{3,}\b", text.lower())
    return [t for t in tokens if t not in _STOPWORDS]


def _bm25_score(
    query_terms: list[str],
    doc_terms: list[str],
    avg_dl: float,
    doc_freq: dict[str, int],
    n_docs: int,
    k1: float = 1.5,
    b: float = 0.75,
) -> float:
    """
    Calcula score BM25 simplificado para um documento.

    Usa IDF aproximado baseado na frequência dos termos nos candidatos
    recuperados (não no corpus inteiro, que seria mais caro).
    """
    if not query_terms or not doc_terms:
        return 0.0

    dl = len(doc_terms)
    tf_doc = Counter(doc_terms)
    score = 0.0

    for term in query_terms:
        if term not in tf_doc:
            continue
        tf = tf_doc[term]
        df = doc_freq.get(term, 0)
        # IDF: log((N - df + 0.5) / (df + 0.5) + 1)
        idf = math.log((n_docs - df + 0.5) / (df + 0.5) + 1.0)
        # TF normalizado por tamanho do documento
        tf_norm = (tf * (k1 + 1)) / (tf + k1 * (1 - b + b * dl / avg_dl))
        score += idf * tf_norm

    return score


def _compute_keyword_scores(
    query: str, docs: list[str]
) -> list[float]:
    """
    Calcula scores BM25 normalizados [0, 1] para uma lista de documentos.
    """
    query_terms = _tokenize(query)
    if not query_terms:
        return [0.0] * len(docs)

    # Tokeniza todos os docs
    docs_tokenized = [_tokenize(d) for d in docs]

    # Estatísticas do corpus (candidatos recuperados)
    n_docs = len(docs)
    avg_dl = sum(len(d) for d in docs_tokenized) / n_docs if n_docs else 1.0

    # Document frequency para cada termo da query
    doc_freq: dict[str, int] = {}
    for term in set(query_terms):
        doc_freq[term] = sum(1 for dt in docs_tokenized if term in dt)

    # Score BM25 por documento
    raw_scores = [
        _bm25_score(query_terms, dt, avg_dl, doc_freq, n_docs)
        for dt in docs_tokenized
    ]

    # Normaliza para [0, 1]
    max_score = max(raw_scores) if raw_scores else 0.0
    if max_score > 0:
        return [s / max_score for s in raw_scores]
    return [0.0] * len(docs)


# ── Busca híbrida ────────────────────────────────────────────────────

def search(query: str, top_k: int = TOP_K) -> tuple[list[Match], bool]:
    """
    Busca híbrida: combina similaridade vetorial (cosine) com score
    BM25 (keywords) para melhorar a recuperação de termos específicos.

    Retorna (matches, base_suficiente).
    base_suficiente=False quando nenhum match supera MIN_SCORE.
    """
    embedder = get_embedder()
    query_embedding = embedder.encode([query])[0].tolist()

    collection = get_collection()

    # Recupera pool maior de candidatos para re-ranking
    n_candidates = 150
    results = collection.query(
        query_embeddings=[query_embedding],
        n_results=n_candidates,
        include=["documents", "metadatas", "distances"],
    )

    documents = results["documents"][0]
    metadatas = results["metadatas"][0]
    distances = results["distances"][0]

    if not documents:
        return [], False

    # Scores semânticos (cosine similarity)
    semantic_scores = [1 - (dist / 2) for dist in distances]

    # Scores BM25 (keywords)
    keyword_scores = _compute_keyword_scores(query, documents)

    # Combina: hybrid = α × semântico + (1-α) × keyword
    alpha = HYBRID_ALPHA
    hybrid_scores = [
        alpha * sem + (1 - alpha) * kw
        for sem, kw in zip(semantic_scores, keyword_scores)
    ]

    # Monta candidatos com score híbrido
    candidates = []
    for i, (doc, meta, hybrid) in enumerate(
        zip(documents, metadatas, hybrid_scores)
    ):
        candidates.append(
            Match(
                text=doc,
                score=round(hybrid, 4),
                source=meta.get("source", ""),
                page=meta.get("page", 0),
                artigo_detectado=meta.get("artigo_detectado", ""),
            )
        )

    # Re-ordena pelo score híbrido (descendente) e pega top_k
    candidates.sort(key=lambda m: m.score, reverse=True)
    matches = candidates[:top_k]

    base_suficiente = any(m.score >= MIN_SCORE for m in matches)
    return matches, base_suficiente
