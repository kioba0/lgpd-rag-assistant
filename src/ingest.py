import hashlib
import re
import sys
from pathlib import Path

import chromadb
from langchain_text_splitters import RecursiveCharacterTextSplitter
from pypdf import PdfReader
from sentence_transformers import SentenceTransformer

sys.path.insert(0, str(Path(__file__).parent))
from config import (
    CHROMA_DIR,
    CHUNK_OVERLAP,
    CHUNK_SIZE,
    COLLECTION_NAME,
    DATA_RAW_DIR,
    EMBEDDING_MODEL,
)

_embedder: SentenceTransformer | None = None


def get_embedder() -> SentenceTransformer:
    global _embedder
    if _embedder is None:
        print(f"Carregando modelo de embedding '{EMBEDDING_MODEL}'...")
        _embedder = SentenceTransformer(EMBEDDING_MODEL)
    return _embedder


def load_document(path: Path) -> list[dict]:
    """Carrega PDF ou TXT. Retorna lista de {text, page, source}."""
    if path.suffix.lower() == ".pdf":
        return _load_pdf(path)
    if path.suffix.lower() == ".txt":
        return _load_txt(path)
    raise ValueError(f"Formato não suportado: {path.suffix}")


def _load_pdf(path: Path) -> list[dict]:
    reader = PdfReader(path)
    pages = []
    for i, page in enumerate(reader.pages):
        text = page.extract_text() or ""
        text = _clean_text(text)
        if text.strip():
            pages.append({"text": text, "page": i + 1, "source": path.name})
    return pages


def _load_txt(path: Path) -> list[dict]:
    """Divide arquivo de texto em blocos de ~3000 caracteres simulando 'páginas'."""
    text = path.read_text(encoding="utf-8")
    text = _clean_text(text)
    block_size = 3000
    blocks = [text[i : i + block_size] for i in range(0, len(text), block_size)]
    return [
        {"text": b, "page": i + 1, "source": path.name}
        for i, b in enumerate(blocks)
        if b.strip()
    ]


def _clean_text(text: str) -> str:
    text = re.sub(r"\n{3,}", "\n\n", text)   # quebras múltiplas → dupla
    text = re.sub(r"-\n(\w)", r"\1", text)   # hífens de quebra de linha
    text = re.sub(r"[ \t]+", " ", text)       # espaços múltiplos
    return text.strip()


# Detecta títulos de seção numerados dos guias: "2.3 Título da Seção"
_SECAO_RE = re.compile(
    r"(?:^|\n)(\d+\.(?:\d+\.?)*\s+[A-ZÁÉÍÓÚÀÃÕÂÊÎ][^\n]{5,80})",
    re.MULTILINE,
)


def chunk_pages(pages: list[dict]) -> list[dict]:
    """Aplica RecursiveCharacterTextSplitter preservando metadados de página.

    Cada chunk é prefixado com o título de seção e/ou artigo vigente quando
    esses não aparecem no próprio texto do chunk — resolve o problema de
    títulos/cabeçalhos que ficam no final de um chunk enquanto o conteúdo
    começa no seguinte sem contexto.
    """
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
        separators=["\n\nArt.", "\n\n", "\n", ". ", " "],
    )
    chunks = []
    global_idx = 0
    secao_atual = ""   # persiste entre chunks do mesmo documento
    artigo_atual = ""

    for page in pages:
        # Detecta se esta página introduce nova seção ou artigo
        nova_secao = _detect_secao(page["text"])
        if nova_secao:
            secao_atual = nova_secao

        splits = splitter.split_text(page["text"])
        for split in splits:
            # Atualiza contexto se este chunk contém novo título/artigo
            ns = _detect_secao(split)
            if ns:
                secao_atual = ns
            na = _detect_artigo(split)
            if na:
                artigo_atual = na

            # Prefixar com contexto estrutural ausente
            prefixo_parts = []
            if secao_atual and secao_atual[:40] not in split[:150]:
                prefixo_parts.append(f"[{secao_atual}]")
            if artigo_atual and artigo_atual not in split[:100]:
                prefixo_parts.append(f"[{artigo_atual}]")

            texto_final = " ".join(prefixo_parts) + " " + split if prefixo_parts else split

            chunks.append({
                "text": texto_final.strip(),
                "page": page["page"],
                "source": page["source"],
                "chunk_index": global_idx,
                "artigo_detectado": na or artigo_atual,
            })
            global_idx += 1

    return chunks


def _detect_secao(text: str) -> str:
    """Extrai o primeiro título de seção numerado, ex: '2.3 Obrigações da LGPD...'"""
    match = _SECAO_RE.search(text)
    return match.group(1).strip()[:80] if match else ""


def _detect_artigo(text: str) -> str:
    """Extrai o primeiro artigo mencionado no chunk, ex: 'Art. 5º'."""
    match = re.search(r"Art\.?\s*\d+[º°]?", text)
    return match.group(0) if match else ""


def _chunk_id(text: str, source: str, page: int, chunk_index: int) -> str:
    """ID determinístico — inclui chunk_index para evitar colisão em páginas com texto idêntico."""
    raw = f"{source}|{page}|{chunk_index}|{text}"
    return hashlib.sha256(raw.encode()).hexdigest()[:20]


def ingest_all(data_dir: Path = DATA_RAW_DIR) -> int:
    """Ingere todos os PDFs de data_dir no Chroma. Retorna número de chunks novos."""
    docs = sorted([p for p in data_dir.iterdir() if p.suffix.lower() in {".pdf", ".txt"}])
    if not docs:
        print(f"Nenhum documento encontrado em {data_dir}.")
        print("Adicione os documentos LGPD/ANPD e rode novamente.")
        return 0

    print(f"Encontrados {len(docs)} documento(s): {[p.name for p in docs]}")

    client = chromadb.PersistentClient(path=str(CHROMA_DIR))
    collection = client.get_or_create_collection(
        name=COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"},
    )

    embedder = get_embedder()
    existing_ids = set(collection.get(include=[])["ids"])
    added = 0

    for pdf_path in docs:
        print(f"\nProcessando '{pdf_path.name}'...")
        pages = load_document(pdf_path)
        chunks = chunk_pages(pages)
        print(f"  {len(pages)} páginas → {len(chunks)} chunks")

        new_chunks, new_ids = [], []
        for chunk in chunks:
            cid = _chunk_id(chunk["text"], chunk["source"], chunk["page"], chunk["chunk_index"])
            if cid not in existing_ids:
                new_chunks.append(chunk)
                new_ids.append(cid)

        if not new_chunks:
            print("  Nenhum chunk novo (já indexado).")
            continue

        texts = [c["text"] for c in new_chunks]
        metadatas = [
            {
                "source": c["source"],
                "page": c["page"],
                "chunk_index": c["chunk_index"],
                "artigo_detectado": c["artigo_detectado"],
            }
            for c in new_chunks
        ]

        print(f"  Gerando embeddings para {len(texts)} chunks...")
        embeddings = embedder.encode(texts, show_progress_bar=True).tolist()

        # Lotes de 500 para não estourar memória em bases grandes
        batch_size = 500
        for i in range(0, len(new_chunks), batch_size):
            collection.add(
                ids=new_ids[i : i + batch_size],
                documents=texts[i : i + batch_size],
                embeddings=embeddings[i : i + batch_size],
                metadatas=metadatas[i : i + batch_size],
            )

        existing_ids.update(new_ids)
        added += len(new_chunks)
        print(f"  {len(new_chunks)} chunks adicionados.")

    total = collection.count()
    print(f"\nIngestão concluída.")
    print(f"Coleção '{COLLECTION_NAME}': {total} chunks totais ({added} novos nesta execução).")
    return added


if __name__ == "__main__":
    ingest_all()
