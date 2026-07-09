import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from config import TOP_K
from llm import call_gemini
from retriever import Match, search
from validator import RespostaLGPD, parse_and_validate

_RECUSA_JSON = """{
  "resposta": "A base documental disponível não contém informação suficiente para responder esta pergunta com segurança.",
  "fontes": [],
  "confianca": 0.0,
  "base_suficiente": false
}"""


def query(pergunta: str, top_k: int = TOP_K) -> dict:
    """
    Pipeline RAG completo.
    Retorna dict com: resposta, fontes, confianca, base_suficiente,
    matches (chunks recuperados), latencia_ms.
    """
    t0 = time.time()

    # 1. Recuperação vetorial
    matches, base_suficiente = search(pergunta, top_k=top_k)

    # 2. Atalho: base insuficiente antes de chamar o LLM
    if not base_suficiente:
        return {
            "resposta": "A base documental disponível não contém informação suficiente para responder esta pergunta.",
            "fontes": [],
            "confianca": 0.0,
            "base_suficiente": False,
            "matches": matches,
            "latencia_ms": int((time.time() - t0) * 1000),
            "erro": None,
        }

    # 3. Chamada ao LLM com contexto
    raw = call_gemini(pergunta, matches)

    # 4. Validação — com 1 retry em caso de falha
    resultado, erro = parse_and_validate(raw, matches)
    if resultado is None:
        retry_prompt = (
            f"A resposta anterior falhou na validação: {erro}. "
            "Corrija e responda APENAS com JSON válido conforme o formato solicitado."
        )
        raw = call_gemini(retry_prompt + "\n\nPERGUNTA ORIGINAL: " + pergunta, matches)
        resultado, erro = parse_and_validate(raw, matches)

    latencia = int((time.time() - t0) * 1000)

    if resultado is None:
        return {
            "resposta": "Erro ao processar a resposta do modelo.",
            "fontes": [],
            "confianca": 0.0,
            "base_suficiente": False,
            "matches": matches,
            "latencia_ms": latencia,
            "erro": erro,
        }

    return {
        "resposta": resultado.resposta,
        "fontes": [f.model_dump() for f in resultado.fontes],
        "confianca": resultado.confianca,
        "base_suficiente": resultado.base_suficiente,
        "matches": matches,
        "latencia_ms": latencia,
        "erro": None,
    }
