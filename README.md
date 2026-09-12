# RAG Ketenagakerjaan

Retrieval-Augmented Generation untuk menjawab pertanyaan seputar **hak & kewajiban pekerja/buruh** berdasarkan peraturan resmi Indonesia.

## Isi Proyek

- **Orang 1 — Data & Preprocessing (knowledge base)**: pengumpulan 27 dokumen resmi (UU, PP, Permenaker), ekstraksi teks, cleaning, chunking per Pasal/Ayat, metadata, dan validasi.
- **Orang 2 — Embedding & Retrieval**: menyiapkan indeks embedding dari `data/chunks.json`.
- **Orang 3 — RAG & UI**: pipeline generasi jawaban + antarmuka.

## Pipeline Preprocessing

```
docs_config.json ──► download_documents.py ──► data/pdf/
                                               data/pdf ──► extract_and_clean.py ──► data/teks/*.clean.txt
data/teks ──► chunk_documents.py ──► data/chunks.json + chunk_report.json
data/chunks.json ──► validate_pipeline.py ──► VALID (0 noise, 0 duplikat, cakupan pasal penuh)
```

## Hasil

- **27 dokumen resmi** → 27 teks bersih → **2.182 chunk** (pasal + penjelasan).
- Setiap chunk punya metadata: `peraturan`, `jenis`, `nomor`, `tahun`, `pasal`, `ayat`, `halaman`, `bab`, `kronologi`.
- `MAX_LEN = 1500` karakter dengan overlap 2 kalimat agar konteks hukum tidak terpotong.

## Struktur

```
data/
├── pdf/          # PDF resmi (tidak di-commit; unduh via config)
├── teks/         # teks bersih + marker halaman
├── chunks.json   # hasil chunking (input embedding)
├── embeddings/   # artefak embedding (bagian Orang 2)
└── README.md
scripts/
├── download_documents.py
├── extract_and_clean.py
├── chunk_documents.py
├── validate_pipeline.py
└── docs_config.json
```

Detail skema & metadata di `data/README.md`.