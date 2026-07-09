import sys
import time
from pathlib import Path

import google.generativeai as genai
from google.api_core.exceptions import ResourceExhausted

sys.path.insert(0, str(Path(__file__).parent))
from config import GEMINI_API_KEY, GEMINI_MODEL
from retriever import Match

genai.configure(api_key=GEMINI_API_KEY)

_MAX_RETRIES = 4
_RETRY_DELAYS = [60, 90, 120, 180]  # segundos


def _call_with_backoff(model, prompt, config):
    """Executa generate_content com retry exponencial em caso de 429."""
    for attempt, delay in enumerate(_RETRY_DELAYS, 1):
        try:
            return model.generate_content(prompt, generation_config=config)
        except ResourceExhausted:
            if attempt == _MAX_RETRIES:
                raise
            print(f"  Rate limit — aguardando {delay}s antes de tentar novamente ({attempt}/{_MAX_RETRIES})...")
            time.sleep(delay)
    raise RuntimeError("Máximo de retries atingido")

_SYSTEM = (
    "Você é um assistente jurídico especializado em LGPD e regulamentações da ANPD. "
    "Responde EXCLUSIVAMENTE com base no contexto fornecido. "
    "Nunca inventa artigos, números ou informações ausentes do contexto."
)

_PROMPT_TEMPLATE = """\
Use APENAS o contexto abaixo para responder à pergunta.
Se o contexto não contiver informação suficiente, preencha "base_suficiente": false
e explique brevemente o que está faltando em "resposta".
Não invente artigos, números ou datas ausentes do contexto.

CONTEXTO:
{context}

PERGUNTA: {pergunta}

Responda SOMENTE em JSON válido, sem markdown, sem ```json:
{{
  "resposta": "...",
  "fontes": [{{"documento": "...", "pagina": 0, "artigo": "..."}}],
  "confianca": 0.0,
  "base_suficiente": true
}}
"""


def _format_context(matches: list[Match]) -> str:
    parts = []
    for i, m in enumerate(matches, 1):
        artigo = f" [{m.artigo_detectado}]" if m.artigo_detectado else ""
        parts.append(
            f"[{i}] Fonte: {m.source}, p.{m.page}{artigo} (score={m.score})\n{m.text}"
        )
    return "\n\n---\n\n".join(parts)


def call_gemini(pergunta: str, matches: list[Match]) -> str:
    """Chama Gemini Flash com o contexto recuperado. Retorna string JSON bruta."""
    context = _format_context(matches)
    prompt = _PROMPT_TEMPLATE.format(context=context, pergunta=pergunta)

    model = genai.GenerativeModel(
        model_name=GEMINI_MODEL,
        system_instruction=_SYSTEM,
    )
    cfg = genai.GenerationConfig(temperature=0.0)
    response = _call_with_backoff(model, prompt, cfg)
    return response.text.strip()


def call_gemini_direct(pergunta: str) -> str:
    """Chama Gemini sem contexto externo (baseline). Retorna texto livre."""
    model = genai.GenerativeModel(model_name=GEMINI_MODEL)
    cfg = genai.GenerationConfig(temperature=0.0)
    response = _call_with_backoff(
        model,
        f"Responda sobre LGPD e proteção de dados pessoais no Brasil:\n\n{pergunta}",
        cfg,
    )
    return response.text.strip()
