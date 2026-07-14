import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).parent))
import baseline
import rag_pipeline
import retriever

st.set_page_config(page_title="Assistente LGPD", page_icon="⚖️", layout="wide")

try:
    retriever.get_collection()
except Exception:
    st.error("Base vetorial não encontrada. Execute `python src/ingest.py` antes de usar o assistente.")
    st.stop()

st.title("⚖️ Assistente de Consulta sobre LGPD")
st.caption("Base: Lei 13.709/2018 + Resoluções e Guias da ANPD")

# Sidebar
with st.sidebar:
    st.header("Configurações")
    modo = st.radio("Modo de resposta", ["RAG (com contexto)", "LLM Direto (baseline)"])
    top_k = st.slider("Chunks recuperados (top-k)", min_value=2, max_value=8, value=6)
    mostrar_chunks = st.checkbox("Mostrar chunks recuperados", value=False)
    st.divider()
    st.caption("**RAG:** recupera trechos relevantes antes de gerar a resposta.")
    st.caption("**LLM Direto:** resposta sem contexto externo — para comparação.")

pergunta = st.text_area("Digite sua pergunta sobre LGPD:", height=80,
                        placeholder="Ex: Quais são os direitos do titular de dados pessoais?")

if st.button("Consultar", type="primary") and pergunta.strip():
    with st.spinner("Processando..."):
        if modo == "RAG (com contexto)":
            resultado = rag_pipeline.query(pergunta.strip(), top_k=top_k)
            _is_rag = True
        else:
            resultado = baseline.query(pergunta.strip())
            _is_rag = False

    st.divider()

    if _is_rag:
        # Status da base
        if resultado["base_suficiente"]:
            st.success(f"Base suficiente · Confiança: {resultado['confianca']:.0%}")
        else:
            st.warning("Base insuficiente — resposta pode ser incompleta")

        if resultado["erro"]:
            st.error(f"Erro de validação: {resultado['erro']}")

    # Resposta
    st.subheader("Resposta")
    st.write(resultado["resposta"])

    # Fontes (só RAG)
    if _is_rag and resultado.get("fontes"):
        st.subheader("Fontes citadas")
        for f in resultado["fontes"]:
            artigo = f" — {f['artigo']}" if f.get("artigo") else ""
            st.markdown(f"- **{f['documento']}**, p. {f['pagina']}{artigo}")

    # Latência
    st.caption(f"Latência: {resultado['latencia_ms']} ms")

    # Chunks recuperados (debug)
    if _is_rag and mostrar_chunks and resultado.get("matches"):
        st.divider()
        st.subheader("Chunks recuperados")
        for i, m in enumerate(resultado["matches"], 1):
            with st.expander(f"[{i}] {m.source} · p.{m.page} · score={m.score}"):
                st.text(m.text)
