import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from llm import call_gemini_direct


def query(pergunta: str) -> dict:
    """
    Baseline: LLM direto sem RAG, sem contexto externo, sem validação estruturada.
    Usado para comparação experimental com o pipeline RAG.
    """
    t0 = time.time()
    resposta = call_gemini_direct(pergunta)
    return {
        "resposta": resposta,
        "latencia_ms": int((time.time() - t0) * 1000),
        "base_suficiente": None,
        "confianca": None,
        "fontes": [],
        "erro": None,
        "matches": [],
    }
