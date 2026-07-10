"""
Roda o conjunto padrão de perguntas e exibe resultado formatado.
Uso: python eval/testar_perguntas.py [--top-k 4] [--categoria facil]

Flags:
  --top-k N        Número de chunks recuperados (padrão: 4)
  --categoria CAT  Roda só uma categoria (facil|medio|ambiguo|fora_da_base|robustez)
  --modo rag|base  Modo de consulta (padrão: rag)
"""

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
import rag_pipeline
import baseline as baseline_mod

PERGUNTAS = Path(__file__).parent / "perguntas_padrao.json"


def cor_status(ok: bool) -> str:
    return "\033[92m✅\033[0m" if ok else "\033[91m❌\033[0m"


def rodar(pergunta: str, deve_responder: bool, top_k: int, modo: str) -> dict:
    if modo == "base":
        r = baseline_mod.query(pergunta)
        return {
            "resposta":       r["resposta"][:200],
            "latencia_ms":    r["latencia_ms"],
            "base_suficiente": True,  # baseline sempre "responde"
            "confianca":      1.0,
            "erro":           None,
            "acertou":        True,   # baseline não tem critério de recusa
        }
    else:
        r = rag_pipeline.query(pergunta, top_k=top_k)
        acertou = r["base_suficiente"] == deve_responder
        return {
            "resposta":       r["resposta"][:200],
            "latencia_ms":    r["latencia_ms"],
            "base_suficiente": r["base_suficiente"],
            "confianca":      r["confianca"],
            "erro":           r["erro"],
            "acertou":        acertou,
        }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--top-k",    type=int, default=4)
    parser.add_argument("--categoria", type=str, default=None)
    parser.add_argument("--modo",     type=str, default="rag", choices=["rag", "base"])
    args = parser.parse_args()

    with open(PERGUNTAS, encoding="utf-8") as f:
        dados = json.load(f)

    categorias = dados["categorias"]
    if args.categoria:
        if args.categoria not in categorias:
            print(f"Categoria inválida. Disponíveis: {list(categorias.keys())}")
            sys.exit(1)
        categorias = {args.categoria: categorias[args.categoria]}

    print(f"\n{'='*75}")
    print(f"  Perguntas padrão — modo={args.modo.upper()} · top-k={args.top_k}")
    print(f"{'='*75}\n")

    total = acertos = 0
    PAUSA = 3  # segundos entre chamadas

    for cat_nome, cat_dados in categorias.items():
        print(f"\n── {cat_nome.upper()} ── {cat_dados['descricao'][:60]}")
        print(f"  {'ID':5} {'OK':3} {'Suf':5} {'Conf':6} {'ms':>6}  Pergunta")
        print(f"  {'─'*70}")

        for p in cat_dados["perguntas"]:
            r = rodar(p["pergunta"], p["deve_responder"], args.top_k, args.modo)
            total += 1
            acertos += int(r["acertou"])
            flag = cor_status(r["acertou"])
            suf  = "SIM" if r["base_suficiente"] else "NÃO"
            print(f"  {p['id']:5} {flag}  {suf:5} {r['confianca']:.0%}  {r['latencia_ms']:>5}ms  "
                  f"{p['pergunta'][:55]}")
            if r["erro"]:
                print(f"         ⚠️  {r['erro'][:80]}")
            time.sleep(PAUSA)

    print(f"\n{'='*75}")
    print(f"  RESULTADO: {acertos}/{total} corretos  ({acertos/total:.0%})")
    print(f"{'='*75}\n")


if __name__ == "__main__":
    main()
