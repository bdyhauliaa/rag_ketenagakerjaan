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
      "ayat": "1,2",                  // huruf ayat yang ada (atau "")
      "poin": "1",                    // nomor rincian/list (atau "")
      "halaman": [3],
      "tipe": "pasal",                // pasal | penjelasan
      "teks": "..."
    }
  ]
}
```

- **1 Pasal = 1 chunk utama**; Pasal > 1500 karakter dipecah per ayat/rincian/kalimat dengan overlap 2 kalimat (`MAX_LEN=1500`, `OVERLAP_SENT=2`).
- `tipe: "penjelasan"` untuk bagian Penjelasan undang-undang (ujar "Cukup jelas." dikompres menjadi satu blok).
- Chunk juga membawa metadata `kronologi` (status berlaku, `mengubah`, `diubah_oleh`) untuk seluruh 27 dokumen, sesuai `docs_config.json`.
- `include_pasal` / `page_range` / `pasal_markers` (konfigurasi per dokumen) ada di `scripts/docs_config.json`.
- 27 dokumen; total 2.182 chunk (pasal 1.610, penjelasan 572).

## Statistik chunk saat ini

- Total: 2.182 chunk
- Panjang: mean 512, median 379, maks 1.500 karakter
- Semua chunk memiliki metadata `halaman` (masker "=== HALAMAN N ===").
- Validasi `scripts/validate_pipeline.py`: 0 noise header/footer bocor, 0 karakter sampah, cakupan pasal lengkap.

## Pipeline

1. `scripts/extract_and_clean.py` — ekstraksi pdfplumber + cleaning teks (hapus header/footer `_FOOT` & baris judul berulang, normalisasi spasi, buang karakter aneh).
2. `scripts/chunk_documents.py` — chunking per Pasal + penjelasan, tulis `data/chunks.json` + `scripts/chunk_report.json`.
3. `scripts/validate_pipeline.py` — validasi otomatis hasil (noise, panjang, duplikat, cakupan pasal).
4. Jalankan ulang parsial: `python scripts/chunk_documents.py --batch A|B|C` (menggabung ke chunks.json).

## Sumber dokumen

- Semua PDF diunduh dari sumber resmi: https://peraturan.go.id, https://peraturan.bpk.go.id, https://jdih.kemnaker.go.id, dan situs resmi penyedia (LLG, BPJS, dll).
- Dokumen yang sudah dicabut/dibatalkan (mis. PP 78/2015, PP 51/2023) **tidak** disertakan.