"""
Comparações extras para o relatório:
  1. top-k = 3 vs. 4 vs. 8
  2. Chunking recursivo (500/80) vs. fixo (400/0)

Execução:
  python eval/comparacoes_extras.py

A comparação de top-k chama o LLM para top-k=3 e top-k=8 (top-k=4 já existe no CSV).
A comparação de chunking avalia apenas a qualidade de retrieval (sem LLM), o que é
suficiente para mostrar o impacto da estratégia de segmentação nos scores.
"""

import csv
import json
import sys
import time
from pathlib import Path

import chromadb
import matplotlib
import matplotlib.pyplot as plt
import numpy as np

matplotlib.use("Agg")

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
import rag_pipeline
from config import CHROMA_DIR, COLLECTION_NAME, EMBEDDING_MODEL
from ingest import chunk_pages, get_embedder, _load_pdf, _load_txt, _chunk_id
from langchain_text_splitters import CharacterTextSplitter

TESTSET   = Path(__file__).parent / "testset.json"
RESULTS   = Path(__file__).parent / "results"

# Usa o CSV de avaliação mais recente disponível (não depende de data hardcoded)
_csvs    = sorted(RESULTS.glob("eval_*.csv"), reverse=True) if RESULTS.exists() else []
EXISTING = _csvs[0] if _csvs else None

PAUSE = 5  # segundos entre chamadas ao LLM


# ── helpers ──────────────────────────────────────────────────────────────

def carregar_testset():
    with open(TESTSET, encoding="utf-8") as f:
        return json.load(f)


def carregar_existentes():
    if EXISTING is None or not EXISTING.exists():
        return {}
    with open(EXISTING, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    return {r["id"]: r for r in rows}


def salvar_csv(path: Path, resultados: list[dict]):
    if not resultados:
        return
    RESULTS.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(resultados[0].keys()))
        writer.writeheader()
        writer.writerows(resultados)
    print(f"  Salvo em {path}")


# ════════════════════════════════════════════════════════════════════════
# COMPARAÇÃO 1 — top-k
# ════════════════════════════════════════════════════════════════════════

def rodar_topk(casos, existentes, topk: int) -> list[dict]:
    """Roda todos os casos com um top-k específico. Reutiliza resultados se já existirem."""
    cache_path = RESULTS / f"topk_{topk}.csv"
    if cache_path.exists():
        print(f"  top-k={topk}: usando cache ({cache_path.name})")
        with open(cache_path, encoding="utf-8") as f:
            return list(csv.DictReader(f))

    print(f"  Rodando top-k={topk} ({len(casos)} casos)...")
    resultados = []
    for i, caso in enumerate(casos, 1):
        print(f"    [{i:02}/{len(casos)}] {caso['id']}...", end=" ", flush=True)
        try:
            r = rag_pipeline.query(caso["pergunta"], top_k=topk)
            resultados.append({
                "id":              caso["id"],
                "categoria":       caso["categoria"],
                "deve_recusar":    caso["deve_recusar"],
                "topk":            topk,
                "base_suficiente": r["base_suficiente"],
                "confianca":       r["confianca"],
                "latencia_ms":     r["latencia_ms"],
                "erro":            r["erro"] or "",
            })
            print(f"suf={r['base_suficiente']} lat={r['latencia_ms']}ms")
        except Exception as e:
            resultados.append({
                "id": caso["id"], "categoria": caso["categoria"],
                "deve_recusar": caso["deve_recusar"], "topk": topk,
                "base_suficiente": False, "confianca": 0.0,
                "latencia_ms": 0, "erro": str(e)[:120],
            })
            print(f"ERRO: {str(e)[:60]}")
        time.sleep(PAUSE)

    salvar_csv(cache_path, resultados)
    return resultados


def tabela_topk(resultados_por_k: dict) -> None:
    """Imprime tabela de resumo e gera gráfico."""
    print("\n" + "=" * 60)
    print("COMPARAÇÃO top-k")
    print("=" * 60)
    print(f"{'top-k':>6}  {'recusa%':>8}  {'resp_base%':>11}  {'lat_ms':>7}")

    dados_graf = {}
    for k in sorted(resultados_por_k):
        rows = resultados_por_k[k]
        total     = len(rows)
        deve_rec  = [r for r in rows if str(r["deve_recusar"]).lower() in ("true","1")]
        recusou   = sum(1 for r in deve_rec if str(r["base_suficiente"]).lower() == "false")
        nao_rec   = [r for r in rows if str(r["deve_recusar"]).lower() not in ("true","1")]
        respondeu = sum(1 for r in nao_rec if str(r["base_suficiente"]).lower() == "true")
        lats      = [int(r["latencia_ms"]) for r in rows if int(r["latencia_ms"]) > 0]
        lat_med   = sum(lats) / len(lats) if lats else 0

        pct_rec  = recusou / len(deve_rec) * 100 if deve_rec else 0
        pct_resp = respondeu / len(nao_rec) * 100 if nao_rec else 0

        print(f"{k:>6}  {pct_rec:>7.0f}%  {pct_resp:>10.0f}%  {lat_med:>7.0f}")
        dados_graf[k] = {"recusa": pct_rec, "resposta": pct_resp, "latencia": lat_med}

    # Gráfico
    ks    = sorted(dados_graf)
    rec   = [dados_graf[k]["recusa"]   for k in ks]
    resp  = [dados_graf[k]["resposta"] for k in ks]
    lats  = [dados_graf[k]["latencia"] for k in ks]
    x     = np.arange(len(ks))

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 5))

    ax1.bar(x - 0.2, rec,  0.35, label="Recusa correta (%)",    color="#C62828")
    ax1.bar(x + 0.2, resp, 0.35, label="Respondeu em base (%)", color="#1565C0")
    ax1.set_xticks(x); ax1.set_xticklabels([f"top-k={k}" for k in ks])
    ax1.set_ylabel("Taxa (%)"); ax1.set_ylim(0, 115)
    ax1.set_title("Qualidade de resposta por top-k")
    ax1.legend()
    for i, (r, s) in enumerate(zip(rec, resp)):
        ax1.text(i - 0.2, r + 2, f"{r:.0f}%", ha="center", fontsize=10)
        ax1.text(i + 0.2, s + 2, f"{s:.0f}%", ha="center", fontsize=10)

    ax2.bar(x, lats, 0.5, color="#2196F3")
    ax2.set_xticks(x); ax2.set_xticklabels([f"top-k={k}" for k in ks])
    ax2.set_ylabel("Latência média (ms)")
    ax2.set_title("Latência média por top-k")
    for i, v in enumerate(lats):
        ax2.text(i, v + 30, f"{v:.0f}", ha="center", fontsize=10)

    fig.suptitle(f"Comparação top-k: {min(ks)} a {max(ks)}", fontsize=14, fontweight="bold")
    fig.tight_layout()
    out = RESULTS / "grafico_topk.png"
    fig.savefig(out, dpi=150)
    plt.close(fig)
    print(f"\n  Gráfico salvo em {out}")


# ════════════════════════════════════════════════════════════════════════
# COMPARAÇÃO 2 — chunking (retrieval only, sem LLM)
# ════════════════════════════════════════════════════════════════════════

COLLECTION_FIXO = "lgpd_anpd_fixo"  # chunk_size=400, overlap=0, CharacterTextSplitter
DATA_RAW = Path(__file__).parent.parent / "data" / "raw"
CHROMA_DIR_STR = str(CHROMA_DIR)


def ingerir_chunking_fixo():
    """Ingere os documentos com CharacterTextSplitter (400/0) numa coleção separada."""
    client = chromadb.PersistentClient(path=CHROMA_DIR_STR)

    # Verifica se já existe
    try:
        col = client.get_collection(COLLECTION_FIXO)
        if col.count() > 0:
            print(f"  Coleção '{COLLECTION_FIXO}' já existe ({col.count()} chunks). Reutilizando.")
            return col
    except Exception:
        pass

    print(f"  Criando coleção '{COLLECTION_FIXO}' com chunking fixo (400/0)...")
    col = client.get_or_create_collection(
        name=COLLECTION_FIXO,
        metadata={"hnsw:space": "cosine"},
    )

    splitter = CharacterTextSplitter(chunk_size=400, chunk_overlap=0, separator="\n")
    embedder = get_embedder()

    docs = sorted([p for p in DATA_RAW.iterdir() if p.suffix.lower() in {".pdf", ".txt"}])
    total = 0
    for doc_path in docs:
        pages = _load_pdf(doc_path) if doc_path.suffix.lower() == ".pdf" else _load_txt(doc_path)
        chunks_fixo = []
        global_idx = 0
        for page in pages:
            splits = splitter.split_text(page["text"])
            for split in splits:
                chunks_fixo.append({
                    "text": split, "page": page["page"],
                    "source": doc_path.name, "chunk_index": global_idx,
                })
                global_idx += 1

        if not chunks_fixo:
            continue

        texts = [c["text"] for c in chunks_fixo]
        ids   = [_chunk_id(c["text"], c["source"], c["page"], c["chunk_index"]) for c in chunks_fixo]
        metas = [{"source": c["source"], "page": c["page"], "chunk_index": c["chunk_index"]} for c in chunks_fixo]

        embs = embedder.encode(texts, show_progress_bar=False).tolist()
        col.add(ids=ids, documents=texts, embeddings=embs, metadatas=metas)
        total += len(chunks_fixo)

    print(f"  Ingestão fixo: {total} chunks")
    return col


def comparar_retrieval(queries: list[str], top_k: int = 4) -> list[dict]:
    """
    Compara retrieval recursivo vs. fixo para cada query.
    Retorna métricas sem chamar o LLM.
    """
    embedder = get_embedder()
    client   = chromadb.PersistentClient(path=CHROMA_DIR_STR)
    col_rec  = client.get_collection(COLLECTION_NAME)
    col_fix  = client.get_collection(COLLECTION_FIXO)

    resultados = []
    for query in queries:
        q_emb = embedder.encode([query])[0].tolist()

        def buscar(col):
            r = col.query(query_embeddings=[q_emb], n_results=top_k,
                          include=["documents", "distances"])
            scores = [round(1 - d / 2, 4) for d in r["distances"][0]]
            return scores

        scores_rec = buscar(col_rec)
        scores_fix = buscar(col_fix)

        resultados.append({
            "query":           query[:60],
            "rec_score_max":   max(scores_rec),
            "rec_score_mean":  round(sum(scores_rec) / len(scores_rec), 4),
            "fix_score_max":   max(scores_fix),
            "fix_score_mean":  round(sum(scores_fix) / len(scores_fix), 4),
            "rec_vence":       max(scores_rec) > max(scores_fix),
        })

    return resultados


def tabela_chunking(resultados: list[dict]) -> None:
    print("\n" + "=" * 60)
    print("COMPARAÇÃO chunking (qualidade de retrieval)")
    print("=" * 60)
    print(f"{'Query':45}  {'Rec max':>8}  {'Fix max':>8}  {'Vence':>6}")
    for r in resultados:
        vence = "Rec ✅" if r["rec_vence"] else "Fix ⚠️ "
        print(f"{r['query']:45}  {r['rec_score_max']:>8.4f}  {r['fix_score_max']:>8.4f}  {vence}")

    rec_vences = sum(1 for r in resultados if r["rec_vence"])
    print(f"\nRecursivo vence em {rec_vences}/{len(resultados)} queries")
    print(f"Score máximo médio — Recursivo: {sum(r['rec_score_max'] for r in resultados)/len(resultados):.4f}")
    print(f"Score máximo médio — Fixo:      {sum(r['fix_score_max'] for r in resultados)/len(resultados):.4f}")

    # Gráfico
    labels = [r["query"][:30] + "..." if len(r["query"]) > 30 else r["query"] for r in resultados]
    rec_m  = [r["rec_score_max"] for r in resultados]
    fix_m  = [r["fix_score_max"] for r in resultados]
    x      = np.arange(len(labels))

    fig, ax = plt.subplots(figsize=(13, 6))
    ax.bar(x - 0.2, rec_m, 0.35, label="Recursivo (500/80)", color="#1565C0")
    ax.bar(x + 0.2, fix_m, 0.35, label="Fixo (400/0)",       color="#EF6C00")
    ax.set_xticks(x)
    ax.set_xticklabels(labels, rotation=35, ha="right", fontsize=8)
    ax.set_ylabel("Score máximo de retrieval (cosine)")
    ax.set_title("Chunking recursivo vs. fixo — score máximo por query")
    ax.set_ylim(0.6, 1.0)
    ax.legend()
    fig.tight_layout()
    out = RESULTS / "grafico_chunking.png"
    fig.savefig(out, dpi=150)
    plt.close(fig)
    print(f"\n  Gráfico salvo em {out}")


# ════════════════════════════════════════════════════════════════════════
# MAIN
# ════════════════════════════════════════════════════════════════════════

QUERIES_CHUNKING = [
    "O que é dado pessoal sensível segundo a LGPD?",
    "Quais são as bases legais para tratamento de dados pessoais?",
    "Quais são as obrigações do encarregado de dados?",
    "Como a ANPD aplica sanções administrativas?",
    "O que é consentimento segundo a LGPD?",
    "Como o legítimo interesse se aplica ao Poder Público?",
    "Quais são os direitos do titular de dados?",
    "O que é o Relatório de Impacto à Proteção de Dados?",
    "Quais critérios definem agentes de tratamento de pequeno porte?",
    "Como o consentimento deve ser colhido em cookies?",
]

if __name__ == "__main__":
    casos     = carregar_testset()
    existentes = carregar_existentes()

    # ── Comparação 1: top-k ───────────────────────────────────────────
    print("\n━━━ COMPARAÇÃO 1: top-k ━━━")

    # top-k=4 já existe — converte CSV para o formato esperado
    rows_4 = []
    for caso in casos:
        if caso["id"] in existentes:
            r = existentes[caso["id"]]
            rows_4.append({
                "id":              caso["id"],
                "categoria":       caso["categoria"],
                "deve_recusar":    caso["deve_recusar"],
                "topk":            4,
                "base_suficiente": r["rag_base_suficiente"],
                "confianca":       r["rag_confianca"],
                "latencia_ms":     r["rag_latencia_ms"],
                "erro":            r.get("rag_erro", ""),
            })

    # Roda todos os top-k de 2 a 8 (top-k=3, 4, 8 usam cache se já existirem)
    todos = {4: rows_4}
    for k in [2, 3, 5, 6, 7, 8]:
        todos[k] = rodar_topk(casos, existentes, k)

    tabela_topk(todos)

    # ── Comparação 2: chunking ────────────────────────────────────────
    print("\n━━━ COMPARAÇÃO 2: chunking (retrieval only) ━━━")
    ingerir_chunking_fixo()
    resultados_chunking = comparar_retrieval(QUERIES_CHUNKING, top_k=4)
    tabela_chunking(resultados_chunking)

    salvar_csv(RESULTS / "comparacao_chunking.csv", resultados_chunking)
    print("\nComparações extras concluídas.")
