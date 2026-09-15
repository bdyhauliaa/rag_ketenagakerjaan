"""
llm.py — Wrapper LLM untuk Generation
=======================================
Module ini menerima query user + list of retrieved chunks,
lalu memanggil LLM untuk menghasilkan jawaban yang grounded
hanya pada konteks pasal-pasal yang diberikan.

Provider yang didukung (diatur lewat .env LLM_PROVIDER):
    - groq   : Groq API, model Llama 3.3 70B (gratis, cepat)
    - gemini : Google Gemini API via google.genai (gratis)
    - openai : OpenAI API (berbayar)

Cara pakai:
    from llm import generate_answer
    jawaban = generate_answer(query, docs)

Integrasi Orang 3:
    Jika Orang 3 mengelola LLM secara terpisah, mereka cukup:
        1. Import retrieve_documents dari retrieval.py
        2. Pass hasil retrieval ke LLM mereka sendiri
    Module ini bisa dibypass sepenuhnya tanpa ubah retrieval.py atau app.py.
"""

import os
import socket
from typing import List, Dict

from dotenv import load_dotenv


def _prefer_ipv4():
    """
    Paksa resolusi DNS ke IPv4 dulu sebelum IPv6.

    Jaringan tertentu (mis. WiFi kampus/ISP) memiliki route IPv6 yang rusak:
    koneksi ke generativelanguage.googleapis.com memilih alamat IPv6 lalu
    menggantung selamanya. Dengan menyimpan getaddrinfo asli dan mengembalikan
    hanya hasil IPv4 untuk host Google, request SDK selalu lewat jalur IPv4.
    """
    _orig_getaddrinfo = socket.getaddrinfo

    def _ipv4_first(host, port, family=0, type=0, proto=0, flags=0):
        result = _orig_getaddrinfo(host, port, family, type, proto, flags)
        if host and (host.endswith("googleapis.com") or "google" in host):
            v4 = [r for r in result if r[0] == socket.AF_INET]
            if v4:
                return v4
        return result

    socket.getaddrinfo = _ipv4_first


_prefer_ipv4()


load_dotenv()

# ── System Prompt ──────────────────────────────────────────────────────────────
SYSTEM_PROMPT = (
    "Kamu adalah asisten hukum ketenagakerjaan Indonesia yang membantu mahasiswa "
    "dan masyarakat umum memahami peraturan resmi. "
    "ATURAN WAJIB:\n"
    "1. Jawab HANYA berdasarkan konteks pasal-pasal yang diberikan. "
    "Jangan mengarang nomor pasal, ayat, nama peraturan, angka hari/besaran, "
    "atau ketentuan hukum yang tidak ada di konteks.\n"
    "2. Jika informasi yang ditanyakan tidak ada di konteks, jawab persis: "
    "\"Informasi tidak ditemukan dalam dokumen yang tersedia.\" lalu sarankan "
    "pertanyaan terkait yang mungkin ada jawabannya.\n"
    "3. Humanization: gunakan bahasa Indonesia natural dan mudah dipahami, "
    "tidak kaku seperti bunyi undang-undang, tapi TETAP pertahankan istilah "
    "hukum penting (mis. PHK, pesangon, UMK, cuti melahirkan) dan JANGAN ubah "
    "makna atau ketentuan hukum.\n"
    "4. Format jawaban selalu tiga bagian:\n"
    "**Jawaban Utama:** 1-2 kalimat inti langsung menjawab pertanyaan.\n"
    "**Penjelasan:** uraian sederhana 2-4 kalimat untuk orang awam.\n"
    "**Dasar Hukum:** daftar sumber (nama peraturan + Pasal + Ayat + halaman "
    "jika ada) yang benar-benar dipakai.\n"
    "5. Setiap klaim hukum harus bisa dilacak ke [Sumber N] yang diberikan."
)
# ───────────────────────────────────────────────────────────────────────────────


def _build_context(docs: List[Dict]) -> str:
    """Gabungkan chunk-chunk menjadi konteks terstruktur untuk LLM."""
    parts = []
    for i, doc in enumerate(docs, 1):
        header = (
            f"[Sumber {i}] {doc['jenis']} No. {doc['nomor']} Tahun {doc['tahun']}"
            f", Pasal {doc['pasal']}"
        )
        if doc.get("ayat"):
            header += f" Ayat ({doc['ayat']})"
        halaman = doc.get("halaman") or []
        if halaman:
            try:
                hlm = ", ".join(str(h) for h in halaman)
            except TypeError:
                hlm = str(halaman)
            header += f", Hlm. {hlm}"
        parts.append(f"{header}\n{doc['teks']}")
    return "\n\n".join(parts)


def _build_prompt(query: str, docs: List[Dict]) -> str:
    context = _build_context(docs)
    return (
        f"Berikut adalah pasal-pasal yang relevan dengan pertanyaan:\n\n"
        f"{context}\n\n"
        f"Pertanyaan: {query}\n\n"
        f"Jawaban berdasarkan pasal-pasal di atas:"
    )


def generate_answer(query: str, docs: List[Dict]) -> str:
    """
    Generate jawaban dari LLM berdasarkan retrieved chunks.

    Args:
        query : Pertanyaan user.
        docs  : List chunk dari retrieve_documents() (masing-masing dict + 'score').

    Returns:
        String jawaban dalam bahasa Indonesia.

    Raises:
        ValueError : Jika LLM_PROVIDER tidak dikenal.
        Exception  : Error dari provider API.
    """
    if not docs:
        return "Maaf, tidak ditemukan pasal yang relevan untuk menjawab pertanyaan ini."

    prompt = _build_prompt(query, docs)
    provider = os.getenv("LLM_PROVIDER", "gemini").lower()

    if provider == "groq":
        return _call_groq(prompt)
    elif provider == "gemini":
        return _call_gemini(prompt)
    elif provider == "openai":
        return _call_openai(prompt)
    else:
        raise ValueError(
            f"LLM_PROVIDER '{provider}' tidak dikenal. "
            "Pilih: groq | gemini | openai"
        )


# ── Provider implementations ───────────────────────────────────────────────────

# Client singleton — dibuat sekali per proses (meminimalkan overhead request).
_groq_client = None
_genai_client = None
_openai_client = None

TIMEOUT_SECONDS = 60  # batas waktu tiap panggilan API (mencegah request menggantung)


def _call_groq(prompt: str) -> str:
    """Groq API — Llama 3.3 70B (gratis, daftar di console.groq.com)."""
    global _groq_client
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key or api_key.startswith("your_"):
        raise EnvironmentError(
            "GROQ_API_KEY tidak ditemukan. Isi di file .env."
        )

    if _groq_client is None:
        from groq import Groq

        _groq_client = Groq(api_key=api_key, timeout=TIMEOUT_SECONDS)

    response = _groq_client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user",   "content": prompt},
        ],
        temperature=0.1,     # rendah → jawaban konsisten, minim halusinasi
        max_tokens=1024,
    )
    return response.choices[0].message.content


def _call_gemini(prompt: str) -> str:
    """Google Gemini API via google.genai — gemini-3.6-flash (gratis, daftar di aistudio.google.com)."""
    global _genai_client
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key or api_key.startswith("your_"):
        raise EnvironmentError(
            "GEMINI_API_KEY tidak ditemukan. Isi di file .env."
        )

    from google import genai
    from google.genai import types

    if _genai_client is None:
        _genai_client = genai.Client(
            api_key=api_key,
            http_options=types.HttpOptions(timeout=TIMEOUT_SECONDS * 1000),
        )

    response = _genai_client.models.generate_content(
        model="gemini-3.6-flash",
        contents=prompt,
        config=types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,
            temperature=0.2,
            max_output_tokens=1024,
        ),
    )
    return response.text


def _call_openai(prompt: str) -> str:
    """OpenAI API — gpt-4o-mini (berbayar, daftar di platform.openai.com)."""
    global _openai_client
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key or api_key.startswith("your_"):
        raise EnvironmentError(
            "OPENAI_API_KEY tidak ditemukan. Isi di file .env."
        )

    if _openai_client is None:
        from openai import OpenAI

        _openai_client = OpenAI(api_key=api_key, timeout=TIMEOUT_SECONDS)

    response = _openai_client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user",   "content": prompt},
        ],
        temperature=0.1,
        max_tokens=1024,
    )
    return response.choices[0].message.content
