"""
llm.py — Wrapper LLM untuk Generation
=======================================
Module ini menerima query user + list of retrieved chunks,
lalu memanggil LLM untuk menghasilkan jawaban yang grounded
hanya pada konteks pasal-pasal yang diberikan.

Provider yang didukung (diatur lewat .env LLM_PROVIDER):
    - groq   : Groq API, model Llama 3.3 70B (gratis, cepat)
    - gemini : Google Gemini API (gratis)
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
from typing import List, Dict

from dotenv import load_dotenv

load_dotenv()

# ── System Prompt ──────────────────────────────────────────────────────────────
SYSTEM_PROMPT = (
    "Kamu adalah asisten hukum ketenagakerjaan Indonesia yang membantu menjawab "
    "pertanyaan berdasarkan peraturan resmi. "
    "Jawab HANYA berdasarkan konteks pasal-pasal yang diberikan. "
    "Jika informasi yang ditanyakan tidak ada di konteks, katakan dengan jelas "
    "bahwa informasi tersebut tidak ditemukan dalam dokumen yang tersedia. "
    "Gunakan bahasa Indonesia yang formal namun mudah dipahami. "
    "Sertakan nomor pasal dan nama peraturan yang relevan dalam jawabanmu."
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
    provider = os.getenv("LLM_PROVIDER", "groq").lower()

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

def _call_groq(prompt: str) -> str:
    """Groq API — Llama 3.3 70B (gratis, daftar di console.groq.com)."""
    from groq import Groq

    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise EnvironmentError(
            "GROQ_API_KEY tidak ditemukan. Isi di file .env."
        )

    client = Groq(api_key=api_key)
    response = client.chat.completions.create(
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
    """Google Gemini API — gemini-1.5-flash (gratis, daftar di aistudio.google.com)."""
    import google.generativeai as genai

    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise EnvironmentError(
            "GEMINI_API_KEY tidak ditemukan. Isi di file .env."
        )

    genai.configure(api_key=api_key)
    model = genai.GenerativeModel(
        "gemini-1.5-flash",
        system_instruction=SYSTEM_PROMPT,
    )
    response = model.generate_content(
        prompt,
        generation_config={"temperature": 0.1, "max_output_tokens": 1024},
    )
    return response.text


def _call_openai(prompt: str) -> str:
    """OpenAI API — gpt-4o-mini (berbayar, daftar di platform.openai.com)."""
    from openai import OpenAI

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise EnvironmentError(
            "OPENAI_API_KEY tidak ditemukan. Isi di file .env."
        )

    client = OpenAI(api_key=api_key)
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user",   "content": prompt},
        ],
        temperature=0.1,
        max_tokens=1024,
    )
    return response.choices[0].message.content
