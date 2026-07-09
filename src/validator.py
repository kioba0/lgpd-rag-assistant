import json
import re
import sys
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, field_validator, model_validator

sys.path.insert(0, str(Path(__file__).parent))
from retriever import Match


class Fonte(BaseModel):
    documento: str
    pagina: int
    artigo: str = ""


class RespostaLGPD(BaseModel):
    resposta: str
    fontes: list[Fonte]
    confianca: float
    base_suficiente: bool

    @field_validator("confianca")
    @classmethod
    def clamp_confianca(cls, v: float) -> float:
        return max(0.0, min(1.0, v))

    @model_validator(mode="after")
    def fontes_obrigatorias_quando_suficiente(self) -> "RespostaLGPD":
        if self.base_suficiente and not self.fontes:
            raise ValueError("fontes não pode ser vazio quando base_suficiente=true")
        return self


def _strip_markdown(raw: str) -> str:
    """Remove blocos ```json ... ``` que o modelo às vezes insere."""
    raw = re.sub(r"^```json\s*", "", raw.strip())
    raw = re.sub(r"^```\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)
    return raw.strip()


def parse_and_validate(raw: str, matches: list[Match]) -> tuple[Optional[RespostaLGPD], str]:
    """
    Parseia JSON e valida com Pydantic.
    Retorna (RespostaLGPD, "") em sucesso ou (None, mensagem_de_erro).
    """
    try:
        data = json.loads(_strip_markdown(raw))
    except json.JSONDecodeError as e:
        return None, f"JSON inválido: {e}"

    try:
        resposta = RespostaLGPD(**data)
    except Exception as e:
        return None, str(e)

    # Regra extra: alerta se artigo citado não aparece em nenhum chunk recuperado.
    # Normaliza variações tipográficas (° U+00B0 vs º U+00BA, espaços) antes de comparar.
    def _normalizar(s: str) -> str:
        return s.replace("º", "°").replace("ª", "°").lower().strip()

    chunks_text_norm = _normalizar(" ".join(m.text for m in matches))
    for fonte in resposta.fontes:
        if fonte.artigo and _normalizar(fonte.artigo) not in chunks_text_norm:
            resposta.confianca = min(resposta.confianca, 0.4)

    return resposta, ""
