"""
test_retrieval.py — Pengujian Relevansi Retrieval
===================================================
Menguji fungsi retrieve_documents() dengan beberapa pertanyaan
representatif untuk memastikan pasal yang dikembalikan relevan.

Cara menjalankan:
    python scripts/test_retrieval.py

Pastikan embed_and_index.py sudah dijalankan terlebih dahulu
sehingga data/embeddings/ sudah berisi faiss.index dan metadata.json.
"""

import sys
from pathlib import Path

# Tambahkan scripts/ ke path agar bisa import retrieval
sys.path.insert(0, str(Path(__file__).parent))
from retrieval import retrieve_documents

# ── Test cases ─────────────────────────────────────────────────────────────────
# Format: (query, pasal_atau_uu_yang_diharapkan_muncul_di_top3)
TEST_CASES = [
    (
        "berapa lama cuti melahirkan?",
        "Pasal 82 UU 13/2003",
    ),
    (
        "aturan PHK sepihak gimana?",
        "Pasal 151-154 UU 13/2003",
    ),
    (
        "berapa upah lembur per jam?",
        "Pasal 78 atau 85 UU 13/2003 / PP 35/2021",
    ),
    (
        "syarat pembentukan serikat pekerja",
        "UU 21/2000",
    ),
    (
        "jaminan sosial ketenagakerjaan BPJS",
        "UU 24/2011 atau UU 40/2004",
    ),
    (
        "batas usia minimum pekerja anak",
        "Pasal 68 UU 13/2003",
    ),
    (
        "hak cuti tahunan pekerja berapa hari",
        "Pasal 79 UU 13/2003",
    ),
]
# ───────────────────────────────────────────────────────────────────────────────


def _relevance_label(score: float) -> str:
    """Label kualitatif berdasarkan cosine similarity score."""
    if score >= 0.70:
        return "🟢 Sangat Relevan"
    elif score >= 0.50:
        return "🟡 Relevan"
    elif score >= 0.35:
        return "🟠 Kurang Relevan"
    else:
        return "🔴 Tidak Relevan"


def run_tests(k: int = 5) -> None:
    print("=" * 70)
    print("  Test Retrieval — RAG Hak & Kewajiban Pekerja")
    print(f"  Model : paraphrase-multilingual-MiniLM-L12-v2  |  Top-K = {k}")
    print("=" * 70)

    for query, expected in TEST_CASES:
        print(f"\nQUERY    : {query}")
        print(f"EXPECTED : {expected}")
        print("-" * 70)

        results = retrieve_documents(query, k=k)
        if not results:
            print("  ⚠️  Tidak ada hasil.")
            continue

        for i, doc in enumerate(results, 1):
            label = _relevance_label(doc["score"])
            pasal_info = (
                f"{doc['jenis']} No.{doc['nomor']}/{doc['tahun']} "
                f"Pasal {doc['pasal']}"
            )
            if doc.get("ayat"):
                pasal_info += f" Ayat ({doc['ayat']})"
            print(
                f"  Top-{i}  [{doc['score']:.4f}] {label}  "
                f"{pasal_info}"
            )
            # Cuplikan teks (50 karakter pertama)
            cuplikan = doc["teks"][:80].replace("\n", " ")
            print(f"          \"{cuplikan}...\"")

    print("\n" + "=" * 70)
    print("  Selesai. Periksa hasil di atas secara manual.")
    print("  Skor cosine similarity: 0–1, semakin tinggi semakin relevan.")
    print("=" * 70)


if __name__ == "__main__":
    run_tests(k=5)
