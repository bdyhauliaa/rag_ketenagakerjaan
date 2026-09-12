# RAG Ketenagakerjaan

Retrieval-Augmented Generation untuk menjawab pertanyaan seputar **hak & kewajiban pekerja/buruh** berdasarkan peraturan resmi Indonesia.

## Isi Proyek

- **Orang 1 — Data & Preprocessing (knowledge base)**: pengumpulan 27 dokumen resmi (UU, PP, Permenaker), ekstraksi teks, cleaning, chunking per Pasal/Ayat, metadata, dan validasi.
- **Orang 2 — Embedding & Retrieval**: menyiapkan indeks embedding dari `data/chunks.json`.
- **Orang 3 — RAG & UI**: pipeline generasi jawaban + antarmuka.

## Menjalankan

```bash
pip install -r requirements.txt   # pdfplumber, requests
python scripts/run_pipeline.py             # download -> extract -> chunk -> validate
python scripts/run_pipeline.py --skip-download   # jika PDF sudah ada
```

Tahap `extract` & `download` butuh akses jaringan + PDF tersimpan di `data/pdf/` (sengaja tidak di-commit).

## Pipeline Preprocessing

```
docs_config.json ──► download_documents.py ──► data/pdf/
                                               data/pdf ──► extract_and_clean.py ──► data/teks/*.clean.txt
data/teks ──► chunk_documents.py ──► data/chunks.json + chunk_report.json
data/chunks.json ──► validate_pipeline.py ──► VALID (0 noise, 0 duplikat, cakupan pasal penuh, reproduksibilitas)
```

Semua tahap sekali jalan: `python scripts/run_pipeline.py`.

## Hasil

- **27 dokumen resmi** → 27 teks bersih → **2.208 chunk** (pasal + penjelasan).
- Setiap chunk punya metadata: `peraturan`, `jenis`, `nomor`, `tahun`, `pasal`, `ayat`, `ayat_pasal`, `halaman`, `bab`, `kronologi`.
- `MAX_LEN = 1500` karakter dengan overlap 2 kalimat agar konteks hukum tidak terpotong.
- `chunks.json` memuat blok `meta` (tanggal generate, parameter chunking, jumlah chunk) untuk penandaan versi embedding.

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
├── run_pipeline.py          # orkestrator satu-perintah
└── docs_config.json
```

Detail skema & metadata di `data/README.md`.