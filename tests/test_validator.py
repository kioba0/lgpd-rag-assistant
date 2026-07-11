"""
Testes unitários para o módulo validator.py
"""
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
from validator import RespostaLGPD, Fonte, parse_and_validate, _strip_markdown


# ── Fixtures ──────────────────────────────────────────────────────────

def _make_match(text="Art. 18. O titular dos dados pessoais tem direito",
                source="lgpd_lei_13709.txt", page=10, score=0.85,
                artigo_detectado="Art. 18"):
    """Cria um Match fake para testes."""
    m = MagicMock()
    m.text = text
    m.source = source
    m.page = page
    m.score = score
    m.artigo_detectado = artigo_detectado
    return m


def _json_valido(**overrides):
    """Gera string JSON válida para testes."""
    data = {
        "resposta": "O titular tem direito de acesso aos dados.",
        "fontes": [{"documento": "lgpd_lei_13709.txt", "pagina": 10, "artigo": "Art. 18"}],
        "confianca": 0.9,
        "base_suficiente": True,
    }
    data.update(overrides)
    return json.dumps(data, ensure_ascii=False)


# ── Testes de _strip_markdown ─────────────────────────────────────────

class TestStripMarkdown:
    def test_remove_bloco_json(self):
        raw = '```json\n{"a": 1}\n```'
        assert _strip_markdown(raw) == '{"a": 1}'

    def test_remove_bloco_simples(self):
        raw = '```\n{"a": 1}\n```'
        assert _strip_markdown(raw) == '{"a": 1}'

    def test_sem_markdown(self):
        raw = '{"a": 1}'
        assert _strip_markdown(raw) == '{"a": 1}'

    def test_whitespace(self):
        raw = '  ```json\n  {"a": 1}  \n```  '
        result = _strip_markdown(raw)
        assert "```" not in result


# ── Testes de RespostaLGPD (Pydantic) ─────────────────────────────────

class TestRespostaLGPD:
    def test_confianca_clamp_acima_de_1(self):
        r = RespostaLGPD(
            resposta="teste", fontes=[Fonte(documento="x", pagina=1)],
            confianca=1.5, base_suficiente=True,
        )
        assert r.confianca == 1.0

    def test_confianca_clamp_abaixo_de_0(self):
        r = RespostaLGPD(
            resposta="teste", fontes=[],
            confianca=-0.3, base_suficiente=False,
        )
        assert r.confianca == 0.0

    def test_fontes_obrigatorias_quando_suficiente(self):
        with pytest.raises(ValueError, match="fontes"):
            RespostaLGPD(
                resposta="teste", fontes=[],
                confianca=0.8, base_suficiente=True,
            )

    def test_fontes_vazias_ok_quando_insuficiente(self):
        r = RespostaLGPD(
            resposta="teste", fontes=[],
            confianca=0.0, base_suficiente=False,
        )
        assert r.base_suficiente is False


# ── Testes de parse_and_validate ──────────────────────────────────────

class TestParseAndValidate:
    def test_json_valido(self):
        matches = [_make_match()]
        resultado, erro = parse_and_validate(_json_valido(), matches)
        assert resultado is not None
        assert erro == ""
        assert resultado.resposta == "O titular tem direito de acesso aos dados."

    def test_json_invalido(self):
        resultado, erro = parse_and_validate("not json", [_make_match()])
        assert resultado is None
        assert "JSON inválido" in erro

    def test_json_com_markdown(self):
        raw = f"```json\n{_json_valido()}\n```"
        resultado, erro = parse_and_validate(raw, [_make_match()])
        assert resultado is not None

    def test_campos_faltando(self):
        raw = json.dumps({"resposta": "teste"})
        resultado, erro = parse_and_validate(raw, [_make_match()])
        assert resultado is None
        assert erro != ""

    def test_artigo_ausente_reduz_confianca(self):
        """Quando o modelo cita um artigo que não está nos chunks, confiança deve ser ≤ 0.4."""
        matches = [_make_match(text="Art. 18. O titular dos dados pessoais")]
        raw = _json_valido(
            fontes=[{"documento": "lgpd_lei_13709.txt", "pagina": 1, "artigo": "Art. 99"}],
            confianca=0.95,
        )
        resultado, erro = parse_and_validate(raw, matches)
        assert resultado is not None
        assert resultado.confianca <= 0.4

    def test_artigo_nao_especificado_ignora(self):
        """Valores como 'não especificado' devem ser ignorados na checagem."""
        matches = [_make_match()]
        raw = _json_valido(
            fontes=[{"documento": "lgpd_lei_13709.txt", "pagina": 10, "artigo": "não especificado"}],
        )
        resultado, erro = parse_and_validate(raw, matches)
        assert resultado is not None
        assert resultado.confianca == 0.9  # não reduzida
