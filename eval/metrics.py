import re
from pathlib import Path


def taxa_recusa_correta(resultados: list[dict]) -> float:
    """Percentual de casos onde o sistema recusou corretamente (fora_da_base + R01/R04)."""
    casos = [r for r in resultados if r["deve_recusar"]]
    if not casos:
        return 0.0
    corretos = sum(1 for r in casos if not r["rag_base_suficiente"])
    return corretos / len(casos)


def taxa_resposta_correta_em_base(resultados: list[dict]) -> float:
    """Percentual de casos onde o sistema respondeu (não recusou) quando deveria."""
    casos = [r for r in resultados if not r["deve_recusar"]]
    if not casos:
        return 0.0
    corretos = sum(1 for r in casos if r["rag_base_suficiente"])
    return corretos / len(casos)


def taxa_json_valido(resultados: list[dict]) -> float:
    """Percentual de respostas RAG que não tiveram erro de validação."""
    total = len(resultados)
    if not total:
        return 0.0
    validos = sum(1 for r in resultados if not r.get("rag_erro"))
    return validos / total


def latencia_media(resultados: list[dict], modo: str = "rag") -> float:
    """Latência média em ms para o modo indicado ('rag' ou 'baseline')."""
    key = f"{modo}_latencia_ms"
    vals = [r[key] for r in resultados if key in r and r[key] is not None]
    return sum(vals) / len(vals) if vals else 0.0


def overlap_palavras(resposta: str, referencia: str) -> float:
    """Proxy de faithfulness: fração de palavras-chave da referência presentes na resposta."""
    if not referencia or not resposta:
        return 0.0
    stopwords = {"a", "o", "e", "de", "da", "do", "em", "para", "com", "que", "se", "os", "as"}
    palavras_ref = set(re.findall(r"\b\w{4,}\b", referencia.lower())) - stopwords
    palavras_resp = set(re.findall(r"\b\w{4,}\b", resposta.lower()))
    if not palavras_ref:
        return 0.0
    return len(palavras_ref & palavras_resp) / len(palavras_ref)


def resumo_por_categoria(resultados: list[dict]) -> dict:
    categorias = {}
    for r in resultados:
        cat = r["categoria"]
        if cat not in categorias:
            categorias[cat] = {"total": 0, "rag_suficiente": 0, "recusa_correta": 0}
        categorias[cat]["total"] += 1
        if r["rag_base_suficiente"]:
            categorias[cat]["rag_suficiente"] += 1
        if r["deve_recusar"] and not r["rag_base_suficiente"]:
            categorias[cat]["recusa_correta"] += 1
    return categorias


def gerar_graficos(resultados: list[dict], output_dir: Path) -> None:
    import matplotlib.pyplot as plt
    import matplotlib
    matplotlib.use("Agg")

    output_dir.mkdir(parents=True, exist_ok=True)

    # Gráfico 1: RAG suficiente vs. baseline por categoria
    cats = ["facil", "medio", "ambiguo", "fora_da_base", "robustez"]
    rag_pct, base_pct = [], []

    for cat in cats:
        casos = [r for r in resultados if r["categoria"] == cat]
        if not casos:
            rag_pct.append(0)
            base_pct.append(0)
            continue
        rag_pct.append(sum(1 for r in casos if r["rag_base_suficiente"]) / len(casos))
        base_pct.append(sum(1 for r in casos if len(r.get("baseline_resposta", "")) > 50) / len(casos))

    x = range(len(cats))
    fig, ax = plt.subplots(figsize=(9, 5))
    ax.bar([i - 0.2 for i in x], rag_pct, 0.4, label="RAG (respondeu)", color="#2196F3")
    ax.bar([i + 0.2 for i in x], base_pct, 0.4, label="Baseline (respondeu)", color="#FF9800")
    ax.set_xticks(list(x))
    ax.set_xticklabels(cats)
    ax.set_ylabel("Taxa de resposta")
    ax.set_title("RAG vs. Baseline — taxa de resposta por categoria")
    ax.legend()
    ax.set_ylim(0, 1.1)
    fig.tight_layout()
    fig.savefig(output_dir / "grafico_categorias.png", dpi=150)
    plt.close(fig)

    # Gráfico 2: latência média por modo
    lat_rag = latencia_media(resultados, "rag")
    lat_base = latencia_media(resultados, "baseline")

    fig2, ax2 = plt.subplots(figsize=(5, 4))
    ax2.bar(["RAG", "Baseline"], [lat_rag, lat_base], color=["#2196F3", "#FF9800"])
    ax2.set_ylabel("Latência média (ms)")
    ax2.set_title("Latência média por modo")
    fig2.tight_layout()
    fig2.savefig(output_dir / "grafico_latencia.png", dpi=150)
    plt.close(fig2)

    print(f"Gráficos salvos em {output_dir}")
