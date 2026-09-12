# Data Preprocessing — RAG Hak & Kewajiban Pekerja

Struktur folder:

```
data/
├── pdf/          # 27 PDF resmi dari sumber (peraturan.go.id, peraturan.bpk.go.id, jdih.kemnaker.go.id, dll)
├── teks/         # hasil ekstraksi + cleaning (.clean.txt, marker halaman "=== HALAMAN N ===")
├── chunks.json   # hasil chunking (input utama untuk embedding)
├── embeddings/   # artefak embedding / indeks (diisi Fase Fatih)
└── README.md
```

`chunks.json` berisi dua kunci: `meta` (info versi/provenance dataset) dan `chunks`.

```json
{
  "meta": {
    "generated_at": "2026-09-12T00:00:00+00:00",   // waktu terakhir dataset di-generate
    "total_chunks": 2208,
    "max_len": 1500,
    "overlap_sentences": 2,
    "schema": "data/README.md"
  },
  "chunks": [ ... ]
}
```

## Skema `chunks.json`

```json
{
  "chunks": [
    {
      "id": "uu_13_2003_0001",
      "source": "uu_13_2003.pdf",
      "peraturan": "Undang-Undang Nomor 13 Tahun 2003 tentang Ketenagakerjaan",
      "jenis": "UU",                  // UU | PP | PERMENAKER
      "nomor": "13",
      "tahun": "2003",
      "bab": "III",
      "judul_bab": "PENGANGKATAN TENAGA KERJA",
      "pasal": "1",
      "ayat": "1,2",                  // ayat yang muncul DI CHUNK ini
      "ayat_pasal": "1,2,3",          // SEMUA ayat yang ada di pasal utuh (untuk filter per pasal)
      "poin": "1",                    // nomor rincian/list (atau "")
      "halaman": [3],
      "tipe": "pasal",                // pasal | penjelasan
      "teks": "..."
    }
  ]
}
```

- `id`, `peraturan`, `jenis`, `nomor`, `tahun`, `pasal`, `ayat`, `halaman` — sesuai metadata tugas Orang 1.
- `ayat_pasal` = daftar lengkap ayat dalam pasal tersebut (beda dari `ayat` yang hanya ayat yang muncul dalam potongan chunk; untuk pasal yang dipecah karena panjang, `ayat` tiap potongan bersifat parsial).

- **1 Pasal = 1 chunk utama**; Pasal > 1500 karakter dipecah per ayat/rincian/kalimat dengan overlap 2 kalimat (`MAX_LEN=1500`, `OVERLAP_SENT=2`).
- `tipe: "penjelasan"` untuk bagian Penjelasan undang-undang (ujar "Cukup jelas." dikompres menjadi satu blok).
- Chunk juga membawa metadata `kronologi` (status berlaku, `mengubah`, `diubah_oleh`) untuk seluruh 27 dokumen, sesuai `docs_config.json`.
- `include_pasal` / `page_range` / `pasal_markers` (konfigurasi per dokumen) ada di `scripts/docs_config.json`.
- Pemisah pasal toleran artefak OCR: `Pasal7` (spasi hilang) dan `Pasa17` (`l` dibaca `1`) tetap dikenali sebagai marker pasal.
- 27 dokumen; total **2.208 chunk** (pasal + penjelasan).

## Statistik chunk saat ini

- Total: 2.208 chunk
- Panjang: mean 512, median 379, maks 1.500 karakter
- Semua chunk memiliki metadata `halaman` (masker "=== HALAMAN N ===").
- Validasi `scripts/validate_pipeline.py`: 0 noise header/footer bocor, 0 karakter sampah, cakupan pasal lengkap, `chunks.json` identik dengan regenerasi dari `data/teks` (cek reproduktibilitas).

## Pipeline

1. `scripts/extract_and_clean.py` — ekstraksi pdfplumber + cleaning teks (hapus header/footer `_FOOT` & baris judul berulang, normalisasi spasi, buang karakter aneh, normalisasi marker pasal).
2. `scripts/chunk_documents.py` — chunking per Pasal + penjelasan, tulis `data/chunks.json` (+ blok `meta`) & `scripts/chunk_report.json`.
3. `scripts/validate_pipeline.py` — validasi otomatis hasil (noise, panjang, duplikat, cakupan pasal, reproduksibilitas, kontinuitas soft).
4. Semua tahap sekali jalan: `python scripts/run_pipeline.py` (ekstra dapat `--stage`, `--skip-download`, `--batch`).
5. Jalankan ulang parsial: `python scripts/chunk_documents.py --batch A|B|C` (menggabung ke chunks.json).

## Sumber dokumen

- Semua PDF diunduh dari sumber resmi: https://peraturan.go.id, https://peraturan.bpk.go.id, https://jdih.kemnaker.go.id, dan situs resmi penyedia (LLG, BPJS, dll).
- Dokumen yang sudah dicabut/dibatalkan (mis. PP 78/2015, PP 51/2023) **tidak** disertakan.