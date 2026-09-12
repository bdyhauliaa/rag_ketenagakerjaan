"""
embed_and_index.py — Fase Indexing (jalankan SEKALI)
=====================================================
Mengubah setiap chunk dari data/chunks.json menjadi vector embedding
menggunakan paraphrase-multilingual-MiniLM-L12-v2, lalu menyimpannya
ke FAISS IndexFlatIP (cosine similarity via inner product setelah L2-norm).

Output:
    data/embeddings/faiss.index   — FAISS binary index
    data/embeddings/metadata.json — metadata chunk paralel dengan index

Referensi:
    - Wang et al. (2024) arXiv:2407.01219 — best practices RAG (chunk size)
    - Reimers & Gurevych (2019) aclanthology.org/D19-1410/ — SBERT
"""

import json
import sys
import time
from pathlib import Path

import faiss
import numpy as np
from sentence_transformers import SentenceTransformer

# ── Konfigurasi ────────────────────────────────────────────────────────────────
MODEL_NAME = "paraphrase-multilingual-MiniLM-L12-v2"
MIN_TEKS_LEN = 50        # filter chunk terlalu pendek (noise/OCR artifacts)
BATCH_SIZE = 64          # chunk per batch encoding
ROOT = Path(__file__).parent.parent
CHUNKS_PATH = ROOT / "data" / "chunks.json"
OUT_DIR = ROOT / "data" / "embeddings"
INDEX_PATH = OUT_DIR / "faiss.index"
META_PATH = OUT_DIR / "metadata.json"
# ───────────────────────────────────────────────────────────────────────────────


def load_chunks() -> list:
    """Load dan filter chunks dari chunks.json."""
    print(f"[1/5] Membaca {CHUNKS_PATH} ...")
    with open(CHUNKS_PATH, encoding="utf-8") as f:
        data = json.load(f)

    all_chunks = data["chunks"]
    chunks = [c for c in all_chunks if len(c["teks"]) >= MIN_TEKS_LEN]

    removed = len(all_chunks) - len(chunks)
    print(f"      Total chunk  : {len(all_chunks)}")
    print(f"      Setelah filter (len >= {MIN_TEKS_LEN}): {len(chunks)} "
          f"({removed} chunk noise dibuang)")
    return chunks


def encode_chunks(chunks: list, model: SentenceTransformer) -> np.ndarray:
    """Encode semua teks chunk menjadi normalized float32 embeddings."""
    print(f"\n[3/5] Encoding {len(chunks)} chunk ...")
    print(f"      Model     : {MODEL_NAME}")
    print(f"      Batch size: {BATCH_SIZE}")
    print(f"      Estimasi  : 2–5 menit (CPU)\n")

    teks_list = [c["teks"] for c in chunks]
    t0 = time.time()
    embeddings = model.encode(
        teks_list,
        batch_size=BATCH_SIZE,
        show_progress_bar=True,
        normalize_embeddings=True,   # L2-norm → inner product == cosine similarity
        convert_to_numpy=True,
    )
    elapsed = time.time() - t0
    print(f"\n      Selesai dalam {elapsed:.1f} detik.")
    print(f"      Shape embedding: {embeddings.shape}  "
          f"(n_chunks × dim={embeddings.shape[1]})")
    return embeddings.astype(np.float32)


def build_faiss_index(embeddings: np.ndarray) -> faiss.IndexFlatIP:
    """
    Buat FAISS IndexFlatIP.

    Kenapa IndexFlatIP?
    - Dengan L2-norm, inner_product(a, b) == cosine_similarity(a, b)
    - Untuk 2000-an vector, exact search sudah sangat cepat (~1ms/query)
    - Tidak perlu approximate methods (IVF/HNSW) yang butuh ribuan vector
    """
    print(f"\n[4/5] Membangun FAISS index ...")
    dim = embeddings.shape[1]
    index = faiss.IndexFlatIP(dim)
    index.add(embeddings)
    print(f"      IndexFlatIP: {index.ntotal} vectors, dim={dim}")
    return index


def save_artifacts(index: faiss.IndexFlatIP, chunks: list) -> None:
    """Simpan FAISS index dan metadata ke disk."""
    print(f"\n[5/5] Menyimpan ke {OUT_DIR} ...")
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    faiss.write_index(index, str(INDEX_PATH))
    print(f"      ✓ {INDEX_PATH.name}  ({INDEX_PATH.stat().st_size / 1e6:.1f} MB)")

    with open(META_PATH, "w", encoding="utf-8") as f:
        json.dump(chunks, f, ensure_ascii=False, indent=2)
    print(f"      ✓ {META_PATH.name}  ({META_PATH.stat().st_size / 1e6:.1f} MB)")


def main() -> None:
    print("=" * 60)
    print("  embed_and_index.py — RAG Ketenagakerjaan")
    print("=" * 60)

    # 1. Load & filter chunks
    chunks = load_chunks()

    # 2. Load model
    print(f"\n[2/5] Memuat model embedding ...")
    print(f"      {MODEL_NAME}")
    model = SentenceTransformer(MODEL_NAME)
    print("      ✓ Model siap")

    # 3. Encode
    embeddings = encode_chunks(chunks, model)

    # 4. Build index
    index = build_faiss_index(embeddings)

    # 5. Simpan
    save_artifacts(index, chunks)

    print("\n" + "=" * 60)
    print("  ✅  Indexing selesai!")
    print(f"      {index.ntotal} chunk siap untuk retrieval.")
    print("      Jalankan selanjutnya: python scripts/test_retrieval.py")
    print("=" * 60)


if __name__ == "__main__":
    main()
