# Assistente de Consulta Fundamentada sobre LGPD

Trabalho 3 — Disciplina de Inteligência Artificial  
**Projeto 1:** Assistente de consulta fundamentada sobre base documental  
**Domínio:** LGPD (Lei 13.709/2018) + resoluções e guias oficiais da ANPD

## Arquitetura

```
Pergunta → Embedding (SBERT multilíngue local) → Chroma (cosine top-4) →
Prompt com contexto → Gemini Flash → JSON validado (Pydantic) →
{resposta, fontes[], confianca, base_suficiente}
```

- **LLM:** Google Gemini (`gemini-flash-lite-latest`, free tier)
- **Embedding:** Sentence Transformers `paraphrase-multilingual-MiniLM-L12-v2` (local, CPU, 384 dim)
- **Vector store:** Chroma com persistência em disco

## Pré-requisitos

- Python 3.11+
- API key gratuita do Gemini: https://aistudio.google.com/apikey

## Instalação

```bash
# 1. Criar e ativar ambiente virtual
python3 -m venv .venv
source .venv/bin/activate  # Linux/Mac
# .venv\Scripts\activate   # Windows

# 2. Instalar dependências
pip install -r requirements.txt

# 3. Configurar variável de ambiente
cp .env.example .env
# Editar .env e preencher GEMINI_API_KEY=sua_chave_aqui
```

## Executar a ingestão (rodar uma vez)

```bash
python3 src/ingest.py
```

Lê todos os PDFs em `data/raw/`, gera chunks, cria embeddings e persiste no Chroma em `chroma_db/`. Leva ~2 minutos. Idempotente — pode rodar quantas vezes quiser sem duplicar.

## Iniciar a interface

```bash
streamlit run src/app.py
```

Abre em http://localhost:8501. Permite consultar no modo RAG ou LLM-direto (baseline).

## Rodar a avaliação experimental

```bash
python3 eval/run_eval.py
```

Roda os 30+ casos de `eval/testset.json` nas duas versões (baseline e RAG) e salva resultados em `eval/results/`.

## Estrutura de diretórios

```
entrega/
├── data/raw/          # PDFs LGPD + ANPD (adicionar manualmente)
├── chroma_db/         # gerado pelo ingest.py
├── src/
│   ├── config.py      # constantes centralizadas
│   ├── ingest.py      # loader + chunking + embedding + Chroma
│   ├── retriever.py   # busca top-k por cosine similarity
│   ├── llm.py         # wrapper Gemini + prompt template
│   ├── validator.py   # schema Pydantic + regras de validação
│   ├── rag_pipeline.py # orquestração RAG completa
│   ├── baseline.py    # LLM direto sem contexto (comparação)
│   └── app.py         # frontend Streamlit
└── eval/
    ├── testset.json   # 30+ casos de teste categorizados
    ├── run_eval.py    # executa avaliação em ambas versões
    └── metrics.py     # cálculo de métricas e gráficos
```

## Documentos da base documental

Colocar os PDFs em `data/raw/`. Todos os documentos são públicos e gratuitos:

| Arquivo | Documento | Fonte |
|---|---|---|
| `lgpd_lei_13709.txt` | Lei 13.709/2018 (LGPD) | planalto.gov.br — buscar "Lei 13709 compilada" |
| `anpd_res_01_2021_regimento.pdf` | Resolução CD/ANPD nº 1/2021 | gov.br/anpd → Regulamentação → Resoluções |
| `anpd_res_04_2023_dosimetria.pdf` | Resolução CD/ANPD nº 4/2023 | gov.br/anpd → Regulamentação → Resoluções |
| `anpd_res_11_2023.pdf` | Resolução CD/ANPD nº 11/2023 | gov.br/anpd → Centrais de conteúdo |
| `anpd_guia_encarregado.pdf` | Guia de Atuação do Encarregado | gov.br/anpd → Orientações e publicações |
| `anpd_guia_cookies.pdf` | Guia Orientativo — Cookies | gov.br/anpd → Orientações e publicações |
| `anpd_guia_poder_publico.pdf` | Guia — Tratamento pelo Poder Público | gov.br/anpd → Orientações e publicações |
| `anpd_guia_seguranca_informacao.pdf` | Guia Segurança da Informação | gov.br/anpd → Orientações e publicações |
| `anpd_guia_legitimo_interesse.pdf` | Guia — Legítimo Interesse | gov.br/anpd → Orientações e publicações |
| `anpd_guia_agentes_tratamento.pdf` | Guia de Agentes de Tratamento | gov.br/anpd → Orientações e publicações |

O CSV completo com metadados (páginas, data de coleta) está em `data/base_documental.csv`.
