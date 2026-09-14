"""
retrieval.py — Modul Retrieval Top-K
======================================
Menyediakan fungsi retrieve_documents(query, k=5) yang:
  1. Encode query ke vector (model yang sama dengan indexing)
  2. Normalisasi L2
  3. Cari Top-K via FAISS IndexFlatIP (== cosine similarity)
  4. Return list of dict berisi metadata chunk + score

Menggunakan singleton pattern agar model & index hanya di-load SEKALI
selama lifetime proses (penting untuk performa Streamlit).

Cara pakai:
    from retrieval import retrieve_documents
    results = retrieve_documents("berapa lama cuti melahirkan?", k=5)
"""

import json
import re
from pathlib import Path
from typing import List, Dict

import faiss
import numpy as np
from sentence_transformers import SentenceTransformer

# ── Konfigurasi ────────────────────────────────────────────────────────────────
MODEL_NAME = "paraphrase-multilingual-MiniLM-L12-v2"
_ROOT = Path(__file__).parent.parent
INDEX_PATH = _ROOT / "data" / "embeddings" / "faiss.index"
META_PATH = _ROOT / "data" / "embeddings" / "metadata.json"

# Ekspansi akronim membantu model embedding yang sulit mematch akronim ke
# frasa penuh di dokumen (mis. "PHK" vs "Pemutusan Hubungan Kerja").
# Ditegaskan pada frasa multi-kata PERTAMA (longest-match) agar konteks
# "PHK sepihak" mencari pasal larangan (UU 13/2003 Pasal 153).
ACRONYM_EXPANSION = {
    "BPJS": "Badan Penyelenggara Jaminan Sosial",
    "THR": "Tunjangan Hari Raya",
    "K3": "Keselamatan dan Kesehatan Kerja",
    "UMK": "Upah Minimum Kabupaten/Kota",
    "UMP": "Upah Minimum Provinsi",
    "PHK SEPIHAK": "Pemutusan Hubungan Kerja sepihak yang dilarang oleh pengusaha",
    "PHK": "Pemutusan Hubungan Kerja",
}
# ───────────────────────────────────────────────────────────────────────────────

# Singleton state — di-load saat pertama kali retrieve_documents() dipanggil
_model: SentenceTransformer = None
_index: faiss.IndexFlatIP = None
_metadata: List[Dict] = None


def _load() -> None:
    """Lazy-load model, index, dan metadata (hanya sekali per proses)."""
    global _model, _index, _metadata

    if _model is None:
        _model = SentenceTransformer(MODEL_NAME)

    if _index is None:
        if not INDEX_PATH.exists():
            raise FileNotFoundError(
                f"FAISS index tidak ditemukan: {INDEX_PATH}\n"
                "Jalankan terlebih dahulu: python scripts/embed_and_index.py"
            )
        _index = faiss.read_index(str(INDEX_PATH))

    if _metadata is None:
        if not META_PATH.exists():
            raise FileNotFoundError(
                f"Metadata tidak ditemukan: {META_PATH}\n"
                "Jalankan terlebih dahulu: python scripts/embed_and_index.py"
            )
        with open(META_PATH, encoding="utf-8") as f:
            _metadata = json.load(f)


def _expand_acronyms(query: str) -> str:
    """Ganti akronim (case-insensitive, longest-match) dengan frasa penuhnya."""
    keys = sorted(ACRONYM_EXPANSION, key=len, reverse=True)

    def repl(match):
        return ACRONYM_EXPANSION[match.group(0).upper()]

    return re.sub(
        r"\b(" + "|".join(re.escape(k) for k in keys) + r")\b",
        repl,
        query,
        flags=re.IGNORECASE,
    )


def retrieve_documents(query: str, k: int = 5) -> List[Dict]:
    """
    Retrieval Top-K berdasarkan cosine similarity.

    Args:
        query : Pertanyaan user dalam bahasa Indonesia.
        k     : Jumlah chunk yang dikembalikan (default 5).

    Returns:
        List of dict, diurutkan dari yang paling relevan.
        Setiap dict berisi semua field chunk dari chunks.json
        ditambah field 'score' (float, cosine similarity 0–1).

    Example:
        >>> results = retrieve_documents("berapa lama cuti melahirkan?", k=5)
        >>> results[0]["pasal"]
        '82'
        >>> results[0]["score"]
        0.8914...
    """
    _load()

    query = _expand_acronyms(query)

    # Encode & normalisasi query (konsisten dengan cara index dibangun)
    query_vec = _model.encode(
        [query],
        normalize_embeddings=True,
        convert_to_numpy=True,
    )
    query_vec = np.array(query_vec, dtype=np.float32)

    # Search FAISS — returns (scores, indices), shape (1, k)
    scores, indices = _index.search(query_vec, k)

    results = []
    for score, idx in zip(scores[0], indices[0]):
        if idx == -1:           # FAISS returns -1 jika tidak ada cukup hasil
            continue
        doc = dict(_metadata[idx])
        doc["score"] = float(score)
        results.append(doc)

    return results
