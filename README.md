# RAG Ketenagakerjaan

Retrieval-Augmented Generation untuk menjawab pertanyaan seputar hak & kewajiban pekerja/buruh berdasarkan peraturan resmi Indonesia.

## Kelompok 4

1. Aulia Rahma Bidayah (L0224003)
2. Fatih Dzaki Nabhani (L0224042)
3. Meiva Yusnita Amalia W.K. (L0224044)

## Cara Menjalankan

```bash
# 1. Instal dependensi (Python >= 3.10)
pip install -r requirements.txt

# 2. Salin .env.example menjadi .env, lalu isi LLM_PROVIDER dan API key (GEMINI_API_KEY)
copy .env.example .env   # Windows (Linux/Mac: cp .env.example .env)

# 3. (Opsional) Bangun knowledge base jika file data/chunks.json belum ada
python scripts/run_pipeline.py --skip-download

# 4. Jalankan aplikasi
python flask_app.py
```

Buka aplikasi di: http://127.0.0.1:5001