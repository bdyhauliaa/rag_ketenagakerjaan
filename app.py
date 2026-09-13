"""
app.py — Streamlit UI: RAG Hak & Kewajiban Pekerja
====================================================
Antarmuka pengguna untuk sistem RAG berbasis 27 peraturan ketenagakerjaan
Indonesia. Pipeline: query → embedding → FAISS retrieval → LLM generation
→ tampilkan jawaban + sumber pasal.

Cara menjalankan:
    streamlit run app.py

Pastikan sebelumnya:
    1. python scripts/embed_and_index.py  (buat FAISS index)
    2. cp .env.example .env && isi API key LLM
"""

import sys
from pathlib import Path

import streamlit as st

# Tambahkan scripts/ ke path agar bisa import modul retrieval & llm
sys.path.insert(0, str(Path(__file__).parent / "scripts"))

# ── Konfigurasi halaman ─────────────────────────────────────────────────────────
st.set_page_config(
    page_title="RAG Ketenagakerjaan",
    page_icon="⚖️",
    layout="centered",
    initial_sidebar_state="collapsed",
)

# ── Custom CSS minimal ──────────────────────────────────────────────────────────
st.markdown("""
<style>
    .stTextArea textarea { font-size: 1rem; }
    .source-card {
        background: #f8f9fa;
        border-left: 4px solid #1f77b4;
        padding: 0.5rem 1rem;
        margin-bottom: 0.5rem;
        border-radius: 4px;
    }
    .score-badge {
        display: inline-block;
        background: #e3f2fd;
        color: #1565c0;
        padding: 2px 8px;
        border-radius: 12px;
        font-size: 0.8rem;
        font-weight: bold;
    }
</style>
""", unsafe_allow_html=True)


# ── Lazy-load model & index (cached agar tidak reload tiap interaksi) ───────────
@st.cache_resource(show_spinner="Memuat model embedding dan indeks...")
def load_retrieval():
    """Load retrieval module — dijalankan sekali, cache selamanya."""
    from retrieval import retrieve_documents, _load
    _load()
    return retrieve_documents


@st.cache_resource(show_spinner="Memuat modul LLM...")
def load_llm():
    """Load LLM wrapper — dijalankan sekali."""
    from llm import generate_answer
    return generate_answer


# ── Header ─────────────────────────────────────────────────────────────────────
st.title("⚖️ RAG Hak & Kewajiban Pekerja")
st.caption(
    "Sistem tanya-jawab berbasis **27 peraturan ketenagakerjaan resmi Indonesia** "
    "(UU, PP, Permenaker) menggunakan Retrieval-Augmented Generation (RAG)."
)
st.divider()

# ── Contoh pertanyaan (sidebar) ─────────────────────────────────────────────────
with st.sidebar:
    st.header("💡 Contoh Pertanyaan")
    contoh = [
        "Berapa lama cuti melahirkan?",
        "Aturan PHK sepihak bagaimana?",
        "Berapa upah lembur per jam?",
        "Syarat pembentukan serikat pekerja?",
        "Hak cuti tahunan berapa hari?",
        "Batas usia minimum pekerja anak?",
        "Kewajiban pengusaha soal K3?",
    ]
    for c in contoh:
        if st.button(c, key=c, use_container_width=True):
            st.session_state["query_input"] = c

    st.divider()
    st.caption("**Sumber dokumen:** UU No.13/2003, PP 35/2021, PP 36/2021, "
               "UU 24/2011, UU 40/2004, UU 21/2000, dan 21 peraturan lainnya.")

# ── Input area ──────────────────────────────────────────────────────────────────
query_val = st.session_state.get("query_input", "")
query = st.text_area(
    "💬 Pertanyaan Anda",
    value=query_val,
    placeholder="Contoh: Berapa lama cuti melahirkan menurut UU Ketenagakerjaan?",
    height=90,
    key="query_text",
)

col_btn, col_reset = st.columns([5, 1])
with col_btn:
    tanya = st.button("🔍 Tanya", type="primary", use_container_width=True)
with col_reset:
    if st.button("🔄", help="Reset pertanyaan"):
        st.session_state["query_input"] = ""
        st.rerun()

# ── Validasi & Proses ───────────────────────────────────────────────────────────
if tanya:
    q = query.strip()

    # Validasi input
    if not q:
        st.warning("⚠️ Pertanyaan tidak boleh kosong. Silakan ketik pertanyaan terlebih dahulu.")
        st.stop()

    if len(q) < 5:
        st.warning("⚠️ Pertanyaan terlalu pendek. Mohon masukkan pertanyaan yang lebih lengkap.")
        st.stop()

    if len(q) > 500:
        st.warning("⚠️ Pertanyaan terlalu panjang (maks 500 karakter). Mohon sederhanakan pertanyaan.")
        st.stop()

    # Proses retrieval
    try:
        retrieve_fn = load_retrieval()
    except FileNotFoundError as e:
        st.error(
            f"❌ **Index belum tersedia.**\n\n"
            f"Jalankan terlebih dahulu:\n```\npython scripts/embed_and_index.py\n```\n\n"
            f"Detail: {e}"
        )
        st.stop()

    with st.spinner("🔍 Mencari pasal yang relevan..."):
        docs = retrieve_fn(q, k=5)

    if not docs:
        st.error("❌ Tidak ditemukan pasal yang relevan untuk pertanyaan ini.")
        st.stop()

    # Proses generation LLM
    generate_fn = load_llm()

    try:
        with st.spinner("✍️ Menyusun jawaban..."):
            jawaban = generate_fn(q, docs)
    except EnvironmentError as e:
        # LLM API key belum diset — tampilkan mode retrieval-only
        st.warning(
            f"⚠️ **API key LLM belum dikonfigurasi.** "
            f"Mode retrieval-only diaktifkan.\n\n"
            f"Untuk jawaban penuh, isi `.env` dengan API key provider LLM. Detail: {e}"
        )
        jawaban = None
    except Exception as e:
        st.error(f"❌ Gagal menghubungi LLM: {e}")
        jawaban = None

    st.divider()

    # ── Area Jawaban ────────────────────────────────────────────────────────────
    st.subheader("💡 Jawaban")

    if jawaban:
        st.markdown(jawaban)
    else:
        # Fallback: tampilkan teks chunk teratas
        st.info(
            "📄 *Jawaban dari LLM tidak tersedia. Menampilkan pasal paling relevan:*"
        )
        st.markdown(
            f"**{docs[0]['jenis']} No. {docs[0]['nomor']} Tahun {docs[0]['tahun']}, "
            f"Pasal {docs[0]['pasal']}**\n\n"
            + docs[0]["teks"]
        )

    # ── Area Sumber & Referensi ─────────────────────────────────────────────────
    st.divider()
    st.subheader("📎 Sumber & Referensi")
    st.caption(f"Ditemukan **{len(docs)} pasal** paling relevan (cosine similarity ↓):")

    for i, doc in enumerate(docs, 1):
        # Label expander
        score_pct = int(doc["score"] * 100)
        pasal_label = f"Pasal {doc['pasal']}"
        if doc.get("ayat"):
            pasal_label += f" Ayat ({doc['ayat']})"
        tipe_label = " *(Penjelasan)*" if doc.get("tipe") == "penjelasan" else ""

        expander_label = (
            f"**Top-{i}** &nbsp;|&nbsp; {doc['jenis']} No. {doc['nomor']}/{doc['tahun']} "
            f"— {pasal_label}{tipe_label} &nbsp; "
            f"🎯 *skor: {doc['score']:.3f} ({score_pct}%)*"
        )

        with st.expander(expander_label, expanded=(i == 1)):
            # Metadata header
            st.markdown(f"**📄 {doc['peraturan']}**")
            meta_cols = st.columns(3)
            meta_cols[0].metric("Jenis", doc["jenis"])
            meta_cols[1].metric("Nomor/Tahun", f"{doc['nomor']}/{doc['tahun']}")
            meta_cols[2].metric("Cosine Score", f"{doc['score']:.4f}")

            if doc.get("bab"):
                st.caption(f"📂 Bab {doc['bab']}: {doc.get('judul_bab', '')}")
            halaman = doc.get("halaman") or []
            if halaman:
                try:
                    hlm = ", ".join(str(h) for h in halaman)
                except TypeError:
                    hlm = str(halaman)
                st.caption(f"📄 Halaman: {hlm}")
            if doc.get("kronologi"):
                st.caption(f"📅 Status: {doc['kronologi']}")

            st.markdown("---")
            st.markdown(f"```\n{doc['teks']}\n```")
