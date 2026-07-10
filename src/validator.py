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
    # Normaliza variações tipográficas antes de comparar.
    def _normalizar(s: str) -> str:
        return s.replace("º", "°").replace("ª", "°").lower().strip()

    # Valores que o modelo usa quando não há artigo específico — ignorar
    _NAO_ARTIGO = {"não especificado", "não mencionado", "não identificado",
                   "sem artigo", "n/a", "", "não citado"}

    chunks_text_norm = _normalizar(" ".join(m.text for m in matches))
    for fonte in resposta.fontes:
        artigo = fonte.artigo.strip()
        # Ignora valores não-artigo
        if not artigo or artigo.lower() in _NAO_ARTIGO:
            continue
        # Ignora numerações de itens de guia (ex: "item 6", "item 31")
        if re.match(r"^item\s+\d+", artigo, re.IGNORECASE):
            continue
        # Referências compostas: "Art. 7º e Art. 11" ou "Art. 52, § 1º (LGPD)"
        # Divide em partes e verifica cada uma; ignora termos entre parênteses e "§"
        partes = re.split(r"\s+e\s+|\s*[,;§(]\s*", artigo, flags=re.IGNORECASE)
        partes = [p.strip().rstrip(")") for p in partes if p.strip()]
        # Só verifica partes que parecem referências de artigo (contêm "art" ou números)
        partes_artigo = [p for p in partes if re.search(r"art\.?|\d", p, re.IGNORECASE)]
        if partes_artigo and not all(_normalizar(p) in chunks_text_norm for p in partes_artigo):
            resposta.confianca = min(resposta.confianca, 0.4)

    return resposta, ""
