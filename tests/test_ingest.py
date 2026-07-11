"""
Testes unitários para o módulo ingest.py
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
from ingest import _clean_text, _detect_artigo, _detect_artigo_intro, _detect_secao, chunk_pages


# ── Testes de _clean_text ─────────────────────────────────────────────

class TestCleanText:
    def test_remove_hifens_de_quebra(self):
        text = "prote-\nção"
        assert _clean_text(text) == "proteção"

    def test_normaliza_espacos(self):
        text = "dado   pessoal    sensível"
        assert _clean_text(text) == "dado pessoal sensível"

    def test_colapsa_quebras_multiplas(self):
        text = "parágrafo 1\n\n\n\n\nparágrafo 2"
        result = _clean_text(text)
        assert "\n\n\n" not in result
        assert "parágrafo 1\n\nparágrafo 2" == result

    def test_strip_whitespace(self):
        text = "   texto com espaços   "
        assert _clean_text(text) == "texto com espaços"


# ── Testes de _detect_artigo ──────────────────────────────────────────

class TestDetectArtigo:
    def test_artigo_simples(self):
        assert _detect_artigo("Art. 5 define dados pessoais") == "Art. 5"

    def test_artigo_com_grau(self):
        assert _detect_artigo("Art. 6º As atividades") == "Art. 6º"

    def test_ultimo_artigo(self):
        """Deve retornar o ÚLTIMO artigo mencionado."""
        text = "Art. 5 define... Art. 7 estabelece..."
        assert _detect_artigo(text) == "Art. 7"

    def test_sem_artigo(self):
        assert _detect_artigo("texto sem referência a artigos") == ""


# ── Testes de _detect_secao ───────────────────────────────────────────

class TestDetectSecao:
    def test_secao_numerada(self):
        text = "2.3 Obrigações da LGPD sobre segurança"
        result = _detect_secao(text)
        assert "Obrigações da LGPD" in result

    def test_secao_com_subsecao(self):
        text = "3.1.2 Tratamento de dados sensíveis pelo Poder Público"
        result = _detect_secao(text)
        assert "Tratamento" in result

    def test_sem_secao(self):
        assert _detect_secao("texto comum sem numeração de seção") == ""


# ── Testes de _detect_artigo_intro ────────────────────────────────────

class TestDetectArtigoIntro:
    def test_intro_simples(self):
        text = "Art. 18. O titular dos dados pessoais tem direito a obter do controlador"
        result = _detect_artigo_intro(text)
        assert "Art. 18" in result
        assert "titular" in result

    def test_ignora_sumario_com_reticencias(self):
        """Entradas de sumário com reticências devem ser ignoradas."""
        text = "Art. 62 ................................ 15"
        result = _detect_artigo_intro(text)
        assert result == ""

    def test_sem_intro(self):
        assert _detect_artigo_intro("texto sem artigo") == ""


# ── Testes de chunk_pages ─────────────────────────────────────────────

class TestChunkPages:
    def test_gera_chunks_com_metadados(self):
        pages = [
            {"text": "Art. 1 Esta Lei dispõe sobre o tratamento de dados pessoais.",
             "page": 1, "source": "teste.pdf"},
        ]
        chunks = chunk_pages(pages)
        assert len(chunks) >= 1
        assert chunks[0]["source"] == "teste.pdf"
        assert chunks[0]["page"] == 1
        assert chunks[0]["chunk_index"] == 0

    def test_prefixo_contextual_em_inciso_solto(self):
        """Incisos soltos devem receber prefixo do artigo vigente."""
        pages = [
            {"text": "Art. 18. O titular dos dados pessoais tem direito a obter do controlador, em relação aos dados por ele tratados, a qualquer momento e mediante requisição:",
             "page": 1, "source": "lgpd.txt"},
            {"text": "I - confirmação da existência de tratamento;\nII - acesso aos dados;\nIII - correção de dados incompletos;",
             "page": 2, "source": "lgpd.txt"},
        ]
        chunks = chunk_pages(pages)
        # Pelo menos um chunk com inciso deve ter prefixo com Art. 18
        incisos = [c for c in chunks if "I -" in c["text"] or "II -" in c["text"]]
        assert any("Art. 18" in c["text"] for c in incisos), \
            "Incisos soltos deveriam receber prefixo contextual com Art. 18"
