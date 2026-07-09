import csv
import json
import sys
import time
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
import baseline
import rag_pipeline
from metrics import (
    gerar_graficos,
    latencia_media,
    overlap_palavras,
    resumo_por_categoria,
    taxa_json_valido,
    taxa_recusa_correta,
    taxa_resposta_correta_em_base,
)

TESTSET = Path(__file__).parent / "testset.json"
RESULTS_DIR = Path(__file__).parent / "results"


_PAUSE_ENTRE_CASOS = 5  # segundos entre casos para não exceder rate limit


def _carregar_resultados_anteriores() -> dict[str, dict]:
    """Carrega CSV mais recente e retorna resultados sem erro, indexados por id."""
    csvs = sorted(RESULTS_DIR.glob("eval_*.csv"), reverse=True)
    if not csvs:
        return {}
    with open(csvs[0], encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    # Só reaproveita casos que não tiveram erro e tiveram latência real
    def _cast(r: dict) -> dict:
        r["rag_base_suficiente"] = r["rag_base_suficiente"] == "True"
        r["deve_recusar"] = r["deve_recusar"] == "True"
        r["rag_latencia_ms"] = int(r["rag_latencia_ms"])
        r["baseline_latencia_ms"] = int(r["baseline_latencia_ms"])
        r["rag_confianca"] = float(r["rag_confianca"])
        r["rag_overlap_ref"] = float(r["rag_overlap_ref"])
        return r

    return {
        r["id"]: _cast(r)
        for r in rows
        if not r.get("rag_erro") and int(r.get("rag_latencia_ms", 0)) > 0
    }


def run() -> list[dict]:
    with open(TESTSET, encoding="utf-8") as f:
        casos = json.load(f)

    anteriores = _carregar_resultados_anteriores()
    pendentes = [c for c in casos if c["id"] not in anteriores]
    ja_feitos = [anteriores[c["id"]] for c in casos if c["id"] in anteriores]

    print(f"Total: {len(casos)} casos | Já concluídos: {len(ja_feitos)} | Pendentes: {len(pendentes)}\n")
    resultados = list(ja_feitos)

    for i, caso in enumerate(pendentes, 1):
        cid = caso["id"]
        pergunta = caso["pergunta"]
        print(f"[{i:02}/{len(pendentes)}] {cid} — {pergunta[:60]}...")

        # RAG
        try:
            r_rag = rag_pipeline.query(pergunta)
            rag_base = r_rag["base_suficiente"]
            rag_resp = r_rag["resposta"]
            rag_fontes = json.dumps(r_rag["fontes"], ensure_ascii=False)
            rag_conf = r_rag["confianca"]
            rag_lat = r_rag["latencia_ms"]
            rag_erro = r_rag["erro"] or ""
        except Exception as e:
            rag_base, rag_resp, rag_fontes = False, f"ERRO: {e}", "[]"
            rag_conf, rag_lat, rag_erro = 0.0, 0, str(e)

        # Baseline
        try:
            r_base = baseline.query(pergunta)
            base_resp = r_base["resposta"]
            base_lat = r_base["latencia_ms"]
        except Exception as e:
            base_resp, base_lat = f"ERRO: {e}", 0

        overlap = overlap_palavras(rag_resp, caso.get("resposta_referencia", ""))

        resultado = {
            "id": cid,
            "categoria": caso["categoria"],
            "pergunta": pergunta,
            "deve_recusar": caso["deve_recusar"],
            "rag_base_suficiente": rag_base,
            "rag_confianca": rag_conf,
            "rag_resposta": rag_resp,
            "rag_fontes": rag_fontes,
            "rag_latencia_ms": rag_lat,
            "rag_erro": rag_erro,
            "rag_overlap_ref": round(overlap, 3),
            "baseline_resposta": base_resp,
            "baseline_latencia_ms": base_lat,
        }
        resultados.append(resultado)

        status = "✅" if (caso["deve_recusar"] == (not rag_base)) else "❌"
        print(f"  {status} suficiente={rag_base} | conf={rag_conf} | {rag_lat}ms | overlap={overlap:.2f}")

        time.sleep(_PAUSE_ENTRE_CASOS)

    return resultados


def salvar(resultados: list[dict]) -> Path:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    hoje = date.today().isoformat()
    csv_path = RESULTS_DIR / f"eval_{hoje}.csv"

    campos = list(resultados[0].keys())
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=campos)
        writer.writeheader()
        writer.writerows(resultados)

    print(f"\nResultados salvos em {csv_path}")
    return csv_path


def imprimir_resumo(resultados: list[dict]) -> None:
    print("\n" + "=" * 60)
    print("RESUMO DA AVALIAÇÃO")
    print("=" * 60)
    print(f"Total de casos:              {len(resultados)}")
    print(f"Taxa de recusa correta:      {taxa_recusa_correta(resultados):.0%}")
    print(f"Taxa resp. correta em base:  {taxa_resposta_correta_em_base(resultados):.0%}")
    print(f"Taxa JSON válido (RAG):      {taxa_json_valido(resultados):.0%}")
    print(f"Latência média RAG:          {latencia_media(resultados, 'rag'):.0f} ms")
    print(f"Latência média Baseline:     {latencia_media(resultados, 'baseline'):.0f} ms")

    print("\nPor categoria:")
    for cat, stats in resumo_por_categoria(resultados).items():
        print(f"  {cat:15} total={stats['total']}  rag_suficiente={stats['rag_suficiente']}  recusa_correta={stats['recusa_correta']}")


if __name__ == "__main__":
    resultados = run()
    csv_path = salvar(resultados)
    imprimir_resumo(resultados)
    gerar_graficos(resultados, RESULTS_DIR)
