import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# Paths
ROOT_DIR = Path(__file__).parent.parent
DATA_RAW_DIR = ROOT_DIR / "data" / "raw"
CHROMA_DIR = ROOT_DIR / "chroma_db"
EVAL_DIR = ROOT_DIR / "eval"
RESULTS_DIR = EVAL_DIR / "results"

# Chroma
COLLECTION_NAME = "lgpd_anpd"

# Embedding (Sentence Transformers — local, CPU, 384 dim)
EMBEDDING_MODEL = "paraphrase-multilingual-MiniLM-L12-v2"
EMBEDDING_DIM = 384

# Chunking
CHUNK_SIZE = 500
CHUNK_OVERLAP = 80

# Retrieval
TOP_K = 6
MIN_SCORE = 0.22  # abaixo disso → base_suficiente = False antes de chamar o LLM
HYBRID_ALPHA = 0.7  # peso do score semântico vs. keyword (1.0 = só semântico)

# Gemini
GEMINI_MODEL = "gemini-flash-lite-latest"
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
