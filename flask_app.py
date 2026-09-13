"""
flask_app.py — Flask UI: Tanya Kerja (RAG Ketenagakerjaan)
============================================================
Web app berbasis Flask yang menyajikan antarmuka Tanya Kerja
sesuai design system stitch dengan integrasi penuh ke pipeline RAG.

Cara menjalankan:
    python flask_app.py

Pastikan sebelumnya:
    1. python scripts/embed_and_index.py  (buat FAISS index)
    2. cp .env.example .env && isi API key LLM
"""

import sys
import re
import html as html_module
from pathlib import Path
from flask import Flask, request, jsonify

# Tambahkan scripts/ ke path agar bisa import modul retrieval & llm
sys.path.insert(0, str(Path(__file__).parent / "scripts"))

app = Flask(__name__)

# ── Lazy-load singleton ──────────────────────────────────────────────────────────
_retrieve_fn = None
_generate_fn = None


def get_retrieve_fn():
    global _retrieve_fn
    if _retrieve_fn is None:
        from retrieval import retrieve_documents, _load
        _load()
        _retrieve_fn = retrieve_documents
    return _retrieve_fn


def get_generate_fn():
    global _generate_fn
    if _generate_fn is None:
        from llm import generate_answer
        _generate_fn = generate_answer
    return _generate_fn


# ── Helpers ──────────────────────────────────────────────────────────────────────

def detect_jenis(doc: dict) -> str:
    """Deteksi jenis peraturan dari metadata doc (case-insensitive)."""
    raw = doc.get("jenis", "").upper().strip()
    if raw in ("UU",) or "UNDANG" in raw:
        return "UU"
    elif raw in ("PP",) or "PEMERINTAH" in raw or "PERATURAN PEMER" in raw:
        return "PP"
    elif "PERMENAKER" in raw or "MENAKER" in raw or "MENTERI" in raw:
        return "Permenaker"
    return raw or "UU"


def format_source_title(doc: dict) -> str:
    """Format judul kartu sumber yang ringkas."""
    jenis   = doc.get("jenis", "").strip()
    nomor   = doc.get("nomor", "").strip()
    tahun   = doc.get("tahun", "").strip()
    pasal   = doc.get("pasal", "").strip()
    ayat    = doc.get("ayat", "").strip()
    judul   = doc.get("judul_bab", "").strip()

    title = f"{jenis} No. {nomor} Tahun {tahun}"
    if pasal:
        title += f" — Pasal {pasal}"
    if ayat:
        title += f" ayat ({ayat})"
    if judul and len(judul) < 50:
        title += f" ({judul.title()})"
    return title


# Warna tetap — tidak pakai dynamic Tailwind class agar JIT tidak skip
SCORE_COLORS = {
    "success": {"text": "#4A7C59", "bar": "#4A7C59"},
    "warning": {"text": "#B45309", "bar": "#B45309"},
    "error":   {"text": "#991B1B", "bar": "#991B1B"},
}

JENIS_ACCENT = {
    "UU":        "#1B3A6B",
    "PP":        "#475569",
    "Permenaker":"#C8861A",
}

JENIS_BADGE_STYLE = {
    "UU":        "background:#1B3A6B; color:#FFFFFF;",
    "PP":        "background:#475569; color:#FFFFFF;",
    "Permenaker":"background:#FFFFFF; color:#C8861A; box-shadow:inset 0 0 0 1px #C8861A;",
}


def score_style(score_pct: int):
    """Return (text_color_hex, bar_color_hex) based on score."""
    if score_pct >= 70:
        return SCORE_COLORS["success"]
    elif score_pct >= 50:
        return SCORE_COLORS["warning"]
    else:
        return SCORE_COLORS["error"]


def clean_teks(teks: str, pasal: str) -> str:
    """
    Bersihkan teks chunk dari retrieval.
    - Hapus baris pertama jika duplikat header pasal ("Pasal X")
    - Strip whitespace berlebih
    """
    lines = teks.strip().splitlines()
    if lines and pasal and re.match(rf'^\s*[Pp]asal\s+{re.escape(str(pasal))}\s*$', lines[0]):
        lines = lines[1:]
    # Hapus baris kosong berlebih di awal
    while lines and not lines[0].strip():
        lines.pop(0)
    return "\n".join(lines).strip()


def build_annotated_answer(jawaban: str, docs: list) -> str:
    """
    Annotasi teks jawaban LLM dengan citation pills interaktif.
    Mengganti referensi 'Pasal X' dengan tombol yang scroll ke kartu sumber.
    """
    if not jawaban or not docs:
        return f'<p class="mb-4">{html_module.escape(jawaban or "")}</p>'

    # Buat mapping: nomor pasal -> {card_id, label}
    pasal_map: dict[str, dict] = {}
    for i, doc in enumerate(docs, 1):
        pasal = str(doc.get("pasal", "")).strip()
        if not pasal:
            continue
        jenis_short = detect_jenis(doc)
        nomor = doc.get("nomor", "")
        tahun = doc.get("tahun", "")
        label = f"{jenis_short} No. {nomor}/{tahun} Pasal {pasal}"
        # Simpan yang belum ada (prioritaskan urutan skor)
        if pasal not in pasal_map:
            pasal_map[pasal] = {"card_id": f"card-{i}", "label": label}

    def replace_pasal(match):
        pasal_num = match.group(1)
        if pasal_num in pasal_map:
            info = pasal_map[pasal_num]
            label_escaped = html_module.escape(info["label"])
            return (
                f'<button class="citation-pill" '
                f'onclick="scrollToSource(\'{info["card_id"]}\')" '
                f'type="button">[{label_escaped}]</button>'
            )
        return match.group(0)

    # Ganti "Pasal XX" dengan pill (tapi jangan di dalam tanda kutip/kode)
    annotated = re.sub(r'\bPasal\s+(\d+)\b', replace_pasal, jawaban)

    # Format paragraf: pisah per \n\n atau \n
    separator = '\n\n' if '\n\n' in annotated else '\n'
    paragraphs = annotated.split(separator)
    result = []
    for p in paragraphs:
        p = p.strip()
        if not p:
            continue
        # Bold markdown **text**
        p = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', p)
        result.append(f'<p class="mb-4 text-body-lg leading-relaxed">{p}</p>')

    return '\n'.join(result) or f'<p class="mb-4">{html_module.escape(jawaban)}</p>'


def build_result_html(query: str, jawaban: str | None, docs: list, llm_error: str | None = None) -> str:
    """Bangun HTML blok hasil: synthesis card + source cards."""
    parts = []

    # ── Banner mode retrieval-only ───────────────────────────────────────────────
    if llm_error:
        parts.append(f"""
    <div class="llm-warning-banner mb-4">
      <div class="flex items-start gap-2">
        <span class="material-symbols-outlined text-[18px] flex-shrink-0" style="color:#B45309">warning</span>
        <div>
          <p class="font-semibold" style="font-size:14px; color:#B45309">Mode retrieval-only aktif</p>
          <p style="font-size:13px; color:#78716C; margin-top:2px">
            LLM belum dikonfigurasi — isi <code style="background:#F0EDE8;padding:1px 4px;border-radius:3px">.env</code> dengan API key
            untuk mendapatkan jawaban sintesis.
          </p>
        </div>
      </div>
    </div>""")

    # ── Synthesis card ───────────────────────────────────────────────────────────
    if jawaban:
        body_html = build_annotated_answer(jawaban, docs)
    else:
        d = docs[0]
        teks = clean_teks(d.get("teks", ""), d.get("pasal", ""))
        body_html = f"""
        <p class="mb-3"><strong style="color:#1C1917">{html_module.escape(d.get('jenis',''))} No. {html_module.escape(d.get('nomor',''))} Tahun {html_module.escape(d.get('tahun',''))}, Pasal {html_module.escape(str(d.get('pasal','')))}</strong></p>
        <p style="font-family:'Courier Prime',monospace; font-size:13px; line-height:24px; color:#3D3530; white-space:pre-wrap">{html_module.escape(teks)}</p>"""

    parts.append(f"""
    <!-- ── Synthesis Card ── -->
    <div class="synthesis-card">
      <div class="synthesis-accent-bar"></div>
      <div class="synthesis-header">
        <div class="synthesis-header-left">
          <span class="synthesis-icon">
            <span class="material-symbols-outlined" style="font-size:14px">auto_awesome</span>
          </span>
          <span class="synthesis-label">Sintesis Jawaban</span>
        </div>
        <button onclick="copyAnswer()" title="Salin jawaban" type="button" class="copy-btn">
          <span class="material-symbols-outlined" style="font-size:18px" id="copy-icon">content_copy</span>
        </button>
      </div>
      <div id="answer-body" class="synthesis-body">
        {body_html}
      </div>
    </div>""")

    # ── Source cards section ─────────────────────────────────────────────────────
    n = len(docs)
    parts.append(f"""
    <!-- ── Source Cards ── -->
    <div class="sources-section">
      <div class="sources-header">
        <div class="sources-header-left">
          <h2 class="sources-title">{n} Rujukan Teratas</h2>
          <span class="sources-count-badge">{n} Dokumen</span>
        </div>
        <span class="sources-rank-label">Peringkat Relevansi</span>
      </div>
      <div class="source-cards-list">""")

    for i, doc in enumerate(docs, 1):
        card_id    = f"card-{i}"
        content_id = f"card-{i}-content"
        jenis      = detect_jenis(doc)
        title      = html_module.escape(format_source_title(doc))
        score_pct  = min(100, int(doc.get("score", 0) * 100))
        colors     = score_style(score_pct)
        accent     = JENIS_ACCENT.get(jenis, "#1B3A6B")
        badge_style = JENIS_BADGE_STYLE.get(jenis, "background:#1B3A6B; color:#FFFFFF;")

        is_first       = i == 1
        content_class  = "accordion-content open" if is_first else "accordion-content closed"
        content_style  = "max-height:2000px; opacity:1;" if is_first else "max-height:0px; opacity:0;"
        toggle_label   = "Tutup detail" if is_first else "Lihat teks"
        toggle_icon    = "expand_less" if is_first else "expand_more"

        # Clean teks (hilangkan duplikat header pasal)
        teks_raw  = doc.get("teks", "").strip()
        pasal_num = str(doc.get("pasal", "")).strip()
        ayat_num  = str(doc.get("ayat", "")).strip()
        teks_clean = clean_teks(teks_raw, pasal_num)
        teks_escaped = html_module.escape(teks_clean)

        # Buat header konten
        pasal_header = f"Pasal {pasal_num}" if pasal_num else ""
        if ayat_num:
            pasal_header += f" Ayat ({ayat_num})"
        halaman_list = doc.get("halaman") or []
        try:
            halaman_txt = ", ".join(str(h) for h in halaman_list) if halaman_list else ""
        except TypeError:
            halaman_txt = str(halaman_list)
        halaman_html = (
            f'<p class="statute-meta">📄 Halaman: {html_module.escape(halaman_txt)}</p>'
            if halaman_txt else ""
        )

        parts.append(f"""
        <!-- Card {i}: {jenis} -->
        <div class="source-card" id="{card_id}">
          <div class="source-accent-bar" style="background:{accent}"></div>
          <div class="source-card-inner">
            <!-- Header -->
            <div class="source-card-header">
              <div class="source-card-meta">
                <span class="jenis-badge" style="{badge_style}">{html_module.escape(jenis)}</span>
                <h3 class="source-title">{title}</h3>
              </div>
              <div class="source-card-controls">
                <!-- Relevance meter -->
                <div class="relevance-meter">
                  <span class="relevance-pct" style="color:{colors['text']}">{score_pct}%</span>
                  <div class="relevance-track">
                    <div class="relevance-fill" style="width:{score_pct}%; background:{colors['bar']}"></div>
                  </div>
                </div>
                <!-- Toggle -->
                <button type="button"
                        data-content="{content_id}"
                        onclick="toggleAccordion('{content_id}', this)"
                        class="accordion-toggle">
                  <span class="acc-label">{toggle_label}</span>
                  <span class="material-symbols-outlined acc-icon" style="font-size:16px">{toggle_icon}</span>
                </button>
              </div>
            </div>

            <!-- Accordion: teks pasal -->
            <div class="{content_class}" id="{content_id}" style="{content_style}">
              <div class="accordion-inner">
                <div class="statute-block">
                  <p class="statute-text"><strong>{html_module.escape(pasal_header)}:</strong>
{teks_escaped}</p>
                  {halaman_html}
                </div>
              </div>
            </div>
          </div>
        </div>""")

    parts.append("""
      </div>
    </div>""")

    return "\n".join(parts)


# ── HTML page (dirender sekali, pakai Jinja2 raw block untuk JS) ─────────────────

SUGGESTION_CHIPS = [
    "Berapa lama cuti melahirkan?",
    "Aturan PHK sepihak bagaimana?",
    "Berapa upah lembur per jam?",
    "Hak cuti tahunan berapa hari?",
    "Kewajiban pengusaha soal K3?",
    "Syarat pembentukan serikat pekerja?",
    "Batas usia minimum pekerja anak?",
]

# HTML page dibuat sebagai string Python murni (bukan Jinja2 template)
# agar tidak ada konflik {{ }} antara Jinja2 dan JS/Tailwind config
def build_page_html(chips: list[str]) -> str:
    chips_html = "\n".join(
        f'<button type="button" onclick="setQuery(this.dataset.q)" '
        f'data-q="{html_module.escape(c)}" class="chip-btn">'
        f'{html_module.escape(c)}</button>'
        for c in chips
    )

    return f"""<!DOCTYPE html>
<html lang="id">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Tanya Kerja — RAG Ketenagakerjaan</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link href="https://fonts.googleapis.com/css2?family=Inter:ital,wght@0,400;0,500;0,600;0,700;1,400&family=Plus+Jakarta+Sans:wght@600;700&family=Courier+Prime&display=swap" rel="stylesheet">
  <link href="https://fonts.googleapis.com/css2?family=Material+Symbols+Outlined:opsz,wght,FILL,GRAD@24,400,0,0" rel="stylesheet">
  <style>
    /* ── Reset ─────────────────────────────────────────────────── */
    *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
    html {{ scroll-behavior: smooth; }}
    body {{
      font-family: 'Inter', sans-serif;
      background: #F7F5F0;
      color: #1C1917;
      min-height: 100vh;
      display: flex;
      flex-direction: column;
      overscroll-behavior: none;
      -webkit-font-smoothing: antialiased;
    }}
    ::-webkit-scrollbar {{ display: none; }}
    ::selection {{ background: #d7e2ff; color: #001a40; }}

    /* ── Typography ─────────────────────────────────────────────── */
    .font-display {{ font-family: 'Plus Jakarta Sans', sans-serif; }}
    .font-code    {{ font-family: 'Courier Prime', monospace; }}

    /* ── Layout ─────────────────────────────────────────────────── */
    .page-container {{
      width: 100%;
      max-width: 760px;
      margin: 0 auto;
      padding: 0 16px;
    }}
    @media (min-width: 768px) {{
      .page-container {{ padding: 0 24px; }}
    }}

    /* ── Header ─────────────────────────────────────────────────── */
    .site-header {{
      position: fixed;
      top: 0; left: 0; right: 0;
      z-index: 40;
      background: rgba(247, 245, 240, 0.92);
      backdrop-filter: blur(12px);
      -webkit-backdrop-filter: blur(12px);
      box-shadow: 0 1px 8px rgba(0,0,0,0.02);
      border-bottom: 1px solid rgba(231, 226, 220, 0.6);
    }}
    .site-header-inner {{
      height: 64px;
      max-width: 760px;
      margin: 0 auto;
      padding: 0 16px;
      display: flex;
      align-items: center;
      justify-content: space-between;
    }}
    @media (min-width: 768px) {{
      .site-header-inner {{ padding: 0 24px; }}
    }}
    .brand-link {{
      display: flex;
      flex-direction: column;
      text-decoration: none;
      gap: 2px;
    }}
    .brand-name-row {{
      display: flex;
      align-items: center;
      gap: 8px;
    }}
    .brand-dot {{
      width: 8px; height: 8px;
      border-radius: 50%;
      background: #1B3A6B;
      display: inline-block;
      flex-shrink: 0;
    }}
    .brand-name {{
      font-family: 'Plus Jakarta Sans', sans-serif;
      font-size: 18px;
      font-weight: 700;
      color: #1B3A6B;
      letter-spacing: -0.02em;
    }}
    .brand-tagline {{
      font-size: 11px;
      font-weight: 600;
      color: #78716C;
      letter-spacing: 0.01em;
      margin-left: 16px;
      display: none;
    }}
    @media (min-width: 640px) {{
      .brand-tagline {{ display: block; }}
    }}
    .nav-link {{
      font-size: 13px;
      font-weight: 500;
      color: #44474f;
      text-decoration: none;
      transition: color 150ms;
    }}
    .nav-link:hover {{ color: #1C1917; }}

    /* ── Main ───────────────────────────────────────────────────── */
    main {{
      flex: 1;
      width: 100%;
      max-width: 760px;
      margin: 0 auto;
      padding: 96px 16px 64px;
      display: flex;
      flex-direction: column;
    }}
    @media (min-width: 768px) {{
      main {{ padding: 96px 24px 64px; }}
    }}

    /* ── Input Box ──────────────────────────────────────────────── */
    .input-wrapper {{
      background: #FFFFFF;
      border-radius: 12px;
      padding: 8px;
      box-shadow: 0 2px 8px rgba(28, 25, 23, 0.05);
      transition: box-shadow 200ms;
      margin-bottom: 40px;
    }}
    .input-wrapper:focus-within {{
      box-shadow: 0 4px 16px rgba(27, 58, 107, 0.12);
    }}
    .input-row {{
      display: flex;
      align-items: flex-start;
      gap: 8px;
      padding: 4px 4px 0;
    }}
    .input-icon {{
      font-family: 'Material Symbols Outlined';
      font-size: 20px;
      color: #1B3A6B;
      opacity: 0.75;
      margin-top: 4px;
      flex-shrink: 0;
      font-variation-settings: 'FILL' 0, 'wght' 400, 'GRAD' 0, 'opsz' 24;
    }}
    #chat-input {{
      width: 100%;
      background: transparent;
      border: none;
      outline: none;
      resize: none;
      font-family: 'Inter', sans-serif;
      font-size: 15px;
      line-height: 25.5px;
      color: #1C1917;
      min-height: 56px;
      max-height: 240px;
      overflow-y: auto;
    }}
    #chat-input::placeholder {{
      color: #A8A29E;
      font-style: italic;
    }}
    .input-footer {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      margin-top: 8px;
      padding: 6px 4px 0;
      border-top: 1px solid rgba(231, 226, 220, 0.6);
    }}
    .char-counter {{
      font-size: 11px;
      font-weight: 600;
      color: #A8A29E;
      letter-spacing: 0.01em;
    }}
    .char-counter.over-limit {{ color: #991B1B; }}

    .btn-tanya {{
      display: inline-flex;
      align-items: center;
      gap: 6px;
      background: #1B3A6B;
      color: #FFFFFF;
      font-family: 'Inter', sans-serif;
      font-size: 15px;
      font-weight: 600;
      padding: 10px 16px;
      border: none;
      border-radius: 8px;
      cursor: pointer;
      transition: background 150ms, box-shadow 150ms, transform 80ms;
      box-shadow: 0 2px 4px rgba(27, 58, 107, 0.25);
      white-space: nowrap;
    }}
    .btn-tanya:hover {{
      background: #162E5A;
      box-shadow: 0 4px 8px rgba(27, 58, 107, 0.30);
    }}
    .btn-tanya:active {{ transform: translateY(1px); }}
    .btn-tanya:disabled {{
      opacity: 0.6;
      cursor: not-allowed;
      transform: none;
    }}
    .btn-tanya .mat-icon {{
      font-family: 'Material Symbols Outlined';
      font-size: 16px;
      font-variation-settings: 'FILL' 0, 'wght' 400, 'GRAD' 0, 'opsz' 24;
    }}

    /* ── Error Alert ────────────────────────────────────────────── */
    .error-alert {{
      display: none;
      margin-top: 8px;
      background: #FFF5F5;
      border: 1px solid #991B1B;
      border-radius: 6px;
      padding: 12px 16px;
    }}
    .error-alert.visible {{ display: block; }}
    .error-alert p {{
      font-family: 'Inter', sans-serif;
      font-size: 15px;
      font-weight: 700;
      color: #991B1B;
    }}

    /* ── Suggestion Chips ───────────────────────────────────────── */
    .chips-row {{
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      margin-top: 10px;
      align-items: center;
    }}
    .chips-label {{
      font-size: 11px;
      font-weight: 600;
      color: #A8A29E;
      letter-spacing: 0.01em;
    }}
    .chip-btn {{
      font-family: 'Inter', sans-serif;
      font-size: 13px;
      color: #78716C;
      background: #F0EDE8;
      border: 1px solid transparent;
      border-radius: 6px;
      padding: 4px 12px;
      cursor: pointer;
      transition: background 150ms, color 150ms;
      white-space: nowrap;
    }}
    .chip-btn:hover {{
      background: #E7E2DC;
      color: #1C1917;
    }}

    /* ── Loading skeleton ───────────────────────────────────────── */
    #loading-skeleton {{ display: none; margin-bottom: 40px; }}
    #loading-skeleton.active {{ display: flex; flex-direction: column; gap: 12px; }}
    @keyframes shimmer {{
      0%   {{ background-position: -200% 0; }}
      100% {{ background-position:  200% 0; }}
    }}
    .skeleton {{
      background: linear-gradient(90deg, #f0ede8 25%, #e7e2dc 50%, #f0ede8 75%);
      background-size: 200% 100%;
      animation: shimmer 1.4s ease-in-out infinite;
      border-radius: 4px;
    }}
    .skeleton-card {{
      background: #FFFFFF;
      border-radius: 10px;
      padding: 20px;
      box-shadow: 0 1px 4px rgba(28,25,23,0.05);
    }}
    .skeleton-row {{ display: flex; gap: 8px; align-items: center; margin-bottom: 12px; }}

    /* ── Spinner ────────────────────────────────────────────────── */
    @keyframes spin {{ to {{ transform: rotate(360deg); }} }}
    .spinner {{
      width: 14px; height: 14px;
      border: 2px solid rgba(255,255,255,0.35);
      border-top-color: white;
      border-radius: 50%;
      animation: spin 0.7s linear infinite;
      display: inline-block;
    }}

    /* ── LLM Warning Banner ─────────────────────────────────────── */
    .llm-warning-banner {{
      background: #FFFBEB;
      border: 1px solid #B45309;
      border-radius: 6px;
      padding: 12px 16px;
    }}

    /* ── Synthesis Card ─────────────────────────────────────────── */
    .synthesis-card {{
      position: relative;
      background: #FFFFFF;
      border-radius: 10px;
      padding: 24px 24px 20px 28px;
      box-shadow: 0 2px 8px rgba(28, 25, 23, 0.04);
      overflow: hidden;
      margin-bottom: 40px;
    }}
    .synthesis-accent-bar {{
      position: absolute;
      top: 0; left: 0; bottom: 0;
      width: 4px;
      background: #1B3A6B;
    }}
    .synthesis-header {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      margin-bottom: 16px;
    }}
    .synthesis-header-left {{
      display: flex;
      align-items: center;
      gap: 8px;
    }}
    .synthesis-icon {{
      display: inline-flex;
      align-items: center;
      justify-content: center;
      width: 24px; height: 24px;
      border-radius: 4px;
      background: #1B3A6B;
      color: #FFFFFF;
      font-family: 'Material Symbols Outlined';
      font-variation-settings: 'FILL' 0, 'wght' 400, 'GRAD' 0, 'opsz' 24;
    }}
    .synthesis-label {{
      font-family: 'Inter', sans-serif;
      font-size: 13px;
      font-weight: 500;
      color: #1B3A6B;
      letter-spacing: 0;
    }}
    .copy-btn {{
      background: none;
      border: none;
      cursor: pointer;
      padding: 4px;
      border-radius: 4px;
      color: #A8A29E;
      transition: color 150ms, background 150ms;
      display: flex;
      align-items: center;
      font-family: 'Material Symbols Outlined';
      font-variation-settings: 'FILL' 0, 'wght' 400, 'GRAD' 0, 'opsz' 24;
    }}
    .copy-btn:hover {{ color: #1C1917; background: #F0EDE8; }}
    .synthesis-body {{
      font-family: 'Inter', sans-serif;
      font-size: 17px;
      line-height: 29.75px;
      color: #1C1917;
    }}
    .synthesis-body p {{ margin-bottom: 16px; }}
    .synthesis-body p:last-child {{ margin-bottom: 0; }}
    .synthesis-body strong {{ font-weight: 700; color: #1C1917; }}

    /* ── Citation Pills ─────────────────────────────────────────── */
    .citation-pill {{
      display: inline-flex;
      align-items: center;
      padding: 1px 6px;
      background: #EEF2FA;
      color: #1B3A6B;
      font-family: 'Inter', sans-serif;
      font-size: 11px;
      font-weight: 600;
      letter-spacing: 0.01em;
      border: 1px solid #1B3A6B;
      border-radius: 4px;
      cursor: pointer;
      transition: background 150ms, color 150ms;
      vertical-align: baseline;
      margin-left: 4px;
      white-space: nowrap;
    }}
    .citation-pill:hover {{
      background: #1B3A6B;
      color: #FFFFFF;
    }}

    /* ── Citation pulse ─────────────────────────────────────────── */
    @keyframes citationPulse {{
      0%   {{ box-shadow: 0 0 0 0 rgba(27, 58, 107, 0.30); }}
      50%  {{ box-shadow: 0 0 0 6px rgba(27, 58, 107, 0.15); }}
      100% {{ box-shadow: 0 0 0 0 rgba(27, 58, 107, 0.00); }}
    }}
    .citation-pulse {{
      animation: citationPulse 1500ms ease-out forwards;
    }}

    /* ── Sources Section ────────────────────────────────────────── */
    .sources-section {{ display: flex; flex-direction: column; gap: 0; }}
    .sources-header {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding-bottom: 10px;
      margin-bottom: 4px;
    }}
    .sources-header-left {{
      display: flex;
      align-items: center;
      gap: 8px;
    }}
    .sources-title {{
      font-family: 'Plus Jakarta Sans', sans-serif;
      font-size: 18px;
      font-weight: 700;
      color: #1C1917;
      letter-spacing: -0.02em;
    }}
    .sources-count-badge {{
      display: inline-flex;
      align-items: center;
      padding: 2px 8px;
      border-radius: 9999px;
      background: #1B3A6B;
      color: #FFFFFF;
      font-family: 'Inter', sans-serif;
      font-size: 11px;
      font-weight: 600;
      letter-spacing: 0.01em;
    }}
    .sources-rank-label {{
      font-family: 'Inter', sans-serif;
      font-size: 11px;
      font-weight: 600;
      color: #78716C;
      letter-spacing: 0.01em;
    }}
    .source-cards-list {{
      display: flex;
      flex-direction: column;
      gap: 10px;
    }}

    /* ── Source Card ────────────────────────────────────────────── */
    .source-card {{
      position: relative;
      background: #FFFFFF;
      border-radius: 10px;
      overflow: hidden;
      border: 1.5px solid #E7E2DC;
      box-shadow: 0 1px 3px rgba(28,25,23,0.06), 0 1px 2px rgba(28,25,23,0.04);
      transition: border-color 200ms, box-shadow 200ms;
    }}
    .source-card:hover {{
      border-color: #C8861A;
      box-shadow: 0 4px 12px rgba(28,25,23,0.10), 0 2px 4px rgba(28,25,23,0.06);
    }}
    .source-accent-bar {{
      position: absolute;
      top: 0; left: 0; bottom: 0;
      width: 4px;
    }}
    .source-card-inner {{
      padding: 14px 16px 14px 20px;
      display: flex;
      flex-direction: column;
      gap: 0;
    }}
    .source-card-header {{
      display: flex;
      flex-direction: column;
      gap: 8px;
    }}
    @media (min-width: 640px) {{
      .source-card-header {{
        flex-direction: row;
        align-items: center;
        justify-content: space-between;
      }}
    }}
    .source-card-meta {{
      display: flex;
      align-items: center;
      gap: 8px;
      flex: 1;
      min-width: 0;
    }}
    .jenis-badge {{
      display: inline-flex;
      align-items: center;
      padding: 2px 8px;
      border-radius: 4px;
      font-family: 'Inter', sans-serif;
      font-size: 11px;
      font-weight: 600;
      letter-spacing: 0.01em;
      text-transform: uppercase;
      flex-shrink: 0;
      white-space: nowrap;
    }}
    .source-title {{
      font-family: 'Inter', sans-serif;
      font-size: 15px;
      font-weight: 600;
      color: #1C1917;
      line-height: 20px;
      letter-spacing: -0.01em;
    }}
    .source-card-controls {{
      display: flex;
      align-items: center;
      gap: 16px;
      flex-shrink: 0;
    }}
    .relevance-meter {{
      display: flex;
      align-items: center;
      gap: 6px;
    }}
    .relevance-pct {{
      font-family: 'Inter', sans-serif;
      font-size: 11px;
      font-weight: 600;
      letter-spacing: 0.01em;
      min-width: 28px;
      text-align: right;
    }}
    .relevance-track {{
      width: 56px;
      height: 4px;
      background: #f6ece6;
      border-radius: 2px;
      overflow: hidden;
    }}
    .relevance-fill {{
      height: 100%;
      border-radius: 2px;
      transition: width 400ms ease;
    }}
    .accordion-toggle {{
      display: inline-flex;
      align-items: center;
      gap: 4px;
      background: none;
      border: none;
      cursor: pointer;
      font-family: 'Inter', sans-serif;
      font-size: 11px;
      font-weight: 600;
      color: #1B3A6B;
      letter-spacing: 0.01em;
      padding: 0;
      transition: color 150ms;
      white-space: nowrap;
    }}
    .accordion-toggle:hover {{ color: #162E5A; }}
    .accordion-toggle .acc-icon {{
      font-family: 'Material Symbols Outlined';
      font-variation-settings: 'FILL' 0, 'wght' 400, 'GRAD' 0, 'opsz' 24;
      transition: transform 200ms;
    }}

    /* ── Accordion ──────────────────────────────────────────────── */
    .accordion-content {{
      overflow: hidden;
      transition: max-height 280ms ease, opacity 220ms ease;
    }}
    .accordion-content.closed {{
      max-height: 0 !important;
      opacity: 0;
    }}
    .accordion-content.open {{
      opacity: 1;
    }}
    .accordion-inner {{
      padding-top: 10px;
      border-top: 1px solid rgba(231, 226, 220, 0.7);
      margin-top: 10px;
    }}
    .statute-block {{
      background: #F0EDE8;
      border-radius: 6px;
      padding: 14px 16px;
      border-left: 3px solid #C8861A;
    }}
    .statute-text {{
      font-family: 'Courier Prime', monospace;
      font-size: 13px;
      line-height: 24px;
      color: #3D3530;
      white-space: pre-wrap;
      word-break: break-word;
    }}
    .statute-meta {{
      font-family: 'Inter', sans-serif;
      font-size: 12px;
      color: #78716C;
      margin-top: 8px;
    }}

    /* ── Footer ─────────────────────────────────────────────────── */
    footer {{
      background: #F7F5F0;
      border-top: 1px solid rgba(231, 226, 220, 0.5);
      padding: 32px 16px;
    }}
    .footer-inner {{
      max-width: 760px;
      margin: 0 auto;
      display: flex;
      flex-direction: column;
      gap: 4px;
    }}
    .footer-text {{
      font-family: 'Inter', sans-serif;
      font-size: 11px;
      font-weight: 600;
      color: #A8A29E;
      letter-spacing: 0.01em;
      text-align: center;
    }}

    /* ── Design Token Reference (tidak dipakai langsung, hanya referensi)
       Status Success  : #4A7C59
       Status Warning  : #B45309
       Status Error    : #991B1B
       Citation Pill BG: #EEF2FA
       PP Accent/Slate : #475569
    ─────────────────────────────────────────────────────────────────── */
  </style>
</head>

<body>
  <!-- ── HEADER ─────────────────────────────────────────────────────────────── -->
  <header class="site-header">
    <div class="site-header-inner">
      <a class="brand-link" href="/">
        <div class="brand-name-row">
          <span class="brand-dot"></span>
          <span class="brand-name font-display">Tanya Kerja</span>
        </div>
        <span class="brand-tagline">Tanya seputar hak dan kewajiban pekerja berdasarkan peraturan pemerintah RI</span>
      </a>
      <nav>
        <a class="nav-link" href="#tentang">Dasar Hukum &amp; Tentang</a>
      </nav>
    </div>
  </header>

  <!-- ── MAIN ───────────────────────────────────────────────────────────────── -->
  <main>
    <!-- Input Area -->
    <div id="input-section">
      <div class="input-wrapper" id="input-box">
        <div class="input-row">
          <span class="input-icon">chat_bubble</span>
          <textarea
            id="chat-input"
            placeholder="Tuliskan pertanyaanmu tentang hak dan kewajiban pekerja..."
            rows="2"
            aria-label="Pertanyaan"
          ></textarea>
        </div>
        <div class="input-footer">
          <span class="char-counter" id="char-count">0 / 500</span>
          <button class="btn-tanya" id="btn-tanya" type="button" aria-label="Kirim pertanyaan">
            <span id="btn-label">Tanya</span>
            <span class="mat-icon" id="btn-icon">arrow_forward</span>
          </button>
        </div>
      </div>

      <!-- Error Alert -->
      <div class="error-alert" id="error-alert" role="alert">
        <p id="error-text"></p>
      </div>

      <!-- Suggestion Chips -->
      <div class="chips-row" id="suggestion-chips">
        <span class="chips-label">Coba tanya:</span>
        {chips_html}
      </div>
    </div>

    <!-- Loading Skeleton -->
    <div id="loading-skeleton">
      <div class="skeleton-card">
        <div class="skeleton-row">
          <div class="skeleton" style="width:24px; height:24px; border-radius:4px; flex-shrink:0"></div>
          <div class="skeleton" style="width:130px; height:14px"></div>
        </div>
        <div class="skeleton" style="width:100%; height:14px; margin-bottom:8px"></div>
        <div class="skeleton" style="width:100%; height:14px; margin-bottom:8px"></div>
        <div class="skeleton" style="width:75%;  height:14px; margin-bottom:8px"></div>
        <div class="skeleton" style="width:100%; height:14px; margin-top:8px; margin-bottom:8px"></div>
        <div class="skeleton" style="width:85%;  height:14px"></div>
      </div>
      <div class="skeleton" style="width:180px; height:22px; border-radius:4px; margin-top:8px"></div>
      <div class="skeleton-card" style="margin-top:0">
        <div style="display:flex; align-items:center; justify-content:space-between">
          <div style="display:flex; align-items:center; gap:8px">
            <div class="skeleton" style="width:30px; height:18px; border-radius:4px"></div>
            <div class="skeleton" style="width:200px; height:14px"></div>
          </div>
          <div class="skeleton" style="width:60px; height:10px; border-radius:9999px"></div>
        </div>
      </div>
      <div class="skeleton-card">
        <div style="display:flex; align-items:center; justify-content:space-between">
          <div style="display:flex; align-items:center; gap:8px">
            <div class="skeleton" style="width:30px; height:18px; border-radius:4px"></div>
            <div class="skeleton" style="width:180px; height:14px"></div>
          </div>
          <div class="skeleton" style="width:60px; height:10px; border-radius:9999px"></div>
        </div>
      </div>
      <div class="skeleton-card">
        <div style="display:flex; align-items:center; justify-content:space-between">
          <div style="display:flex; align-items:center; gap:8px">
            <div class="skeleton" style="width:30px; height:18px; border-radius:4px"></div>
            <div class="skeleton" style="width:160px; height:14px"></div>
          </div>
          <div class="skeleton" style="width:60px; height:10px; border-radius:9999px"></div>
        </div>
      </div>
    </div>

    <!-- Result Container (diisi AJAX) -->
    <div id="result-container"></div>
  </main>

  <!-- ── FOOTER ─────────────────────────────────────────────────────────────── -->
  <footer id="tentang">
    <div class="footer-inner">
      <p class="footer-text">© 2024 Tanya Kerja — Sistem RAG berbasis 27 peraturan ketenagakerjaan resmi Indonesia</p>
      <p class="footer-text">Sumber: UU No.13/2003, PP 35/2021, PP 36/2021, UU 24/2011, UU 40/2004, UU 21/2000, dan 21 peraturan lainnya.</p>
    </div>
  </footer>

  <!-- ── SCRIPTS ─────────────────────────────────────────────────────────────── -->
  <script>
    /* ── Auto-resize textarea ─────────────────────────────────────────────── */
    const textarea = document.getElementById('chat-input');
    const charCounter = document.getElementById('char-count');

    function resizeTextarea() {{
      textarea.style.height = 'auto';
      textarea.style.height = Math.min(textarea.scrollHeight, 240) + 'px';
    }}

    textarea.addEventListener('input', () => {{
      resizeTextarea();
      const len = textarea.value.length;
      charCounter.textContent = len + ' / 500';
      charCounter.classList.toggle('over-limit', len > 500);
    }});

    /* ── Enter = submit, Shift+Enter = newline ─────────────────────────────── */
    textarea.addEventListener('keydown', (e) => {{
      if (e.key === 'Enter' && !e.shiftKey) {{
        e.preventDefault();
        submitQuery();
      }}
    }});

    /* ── Set query from suggestion chip ────────────────────────────────────── */
    function setQuery(q) {{
      textarea.value = q;
      textarea.dispatchEvent(new Event('input'));
      textarea.focus();
    }}

    /* ── Toggle accordion ──────────────────────────────────────────────────── */
    function toggleAccordion(contentId, btn) {{
      const content = document.getElementById(contentId);
      if (!content) return;
      const label = btn.querySelector('.acc-label');
      const icon  = btn.querySelector('.acc-icon');
      const isOpen = content.classList.contains('open');

      if (isOpen) {{
        content.classList.replace('open', 'closed');
        content.style.maxHeight = '0px';
        content.style.opacity = '0';
        if (label) label.textContent = 'Lihat teks';
        if (icon)  icon.textContent  = 'expand_more';
      }} else {{
        content.classList.replace('closed', 'open');
        content.style.maxHeight = content.scrollHeight + 'px';
        content.style.opacity = '1';
        if (label) label.textContent = 'Tutup detail';
        if (icon)  icon.textContent  = 'expand_less';
      }}
    }}

    /* ── Scroll & pulse highlight source card ──────────────────────────────── */
    function scrollToSource(cardId) {{
      const card = document.getElementById(cardId);
      if (!card) return;

      // Buka accordion jika tertutup
      const content = card.querySelector('.accordion-content');
      const toggleBtn = card.querySelector('.accordion-toggle');
      if (content && content.classList.contains('closed') && toggleBtn) {{
        toggleAccordion(content.id, toggleBtn);
      }}

      // Scroll
      setTimeout(() => {{
        card.scrollIntoView({{ behavior: 'smooth', block: 'center' }});
        card.classList.add('citation-pulse');
        setTimeout(() => card.classList.remove('citation-pulse'), 1600);
      }}, 50);
    }}

    /* ── Copy answer ────────────────────────────────────────────────────────── */
    function copyAnswer() {{
      const el = document.getElementById('answer-body');
      if (!el) return;
      navigator.clipboard.writeText(el.innerText.trim()).then(() => {{
        const icon = document.getElementById('copy-icon');
        if (icon) {{
          icon.textContent = 'done';
          setTimeout(() => icon.textContent = 'content_copy', 2000);
        }}
      }}).catch(() => {{/* clipboard not available */}});
    }}

    /* ── Error handling ─────────────────────────────────────────────────────── */
    function showError(msg) {{
      const el = document.getElementById('error-alert');
      document.getElementById('error-text').textContent = msg;
      el.classList.add('visible');
    }}
    function hideError() {{
      document.getElementById('error-alert').classList.remove('visible');
    }}

    /* ── Re-init first accordion after AJAX inject ──────────────────────────── */
    function initAccordions() {{
      // Pastikan card-1 terbuka dan max-height tepat
      const firstContent = document.getElementById('card-1-content');
      if (firstContent && firstContent.classList.contains('open')) {{
        firstContent.style.maxHeight = firstContent.scrollHeight + 'px';
      }}
      // Tutup yang lain (sudah closed dari HTML, tapi reset style)
      document.querySelectorAll('.accordion-content.closed').forEach(el => {{
        el.style.maxHeight = '0px';
        el.style.opacity = '0';
      }});
    }}

    /* ── Main submit ─────────────────────────────────────────────────────────── */
    async function submitQuery() {{
      const query = textarea.value.trim();
      hideError();

      // Client-side validation
      if (!query) {{
        showError('Pertanyaan tidak boleh kosong. Silakan ketik pertanyaan terlebih dahulu.');
        return;
      }}
      if (query.length < 5) {{
        showError('Pertanyaan terlalu pendek. Mohon masukkan pertanyaan yang lebih lengkap.');
        return;
      }}
      if (query.length > 500) {{
        showError('Pertanyaan terlalu panjang (maks 500 karakter). Mohon sederhanakan pertanyaan.');
        return;
      }}

      // Loading state
      const btn       = document.getElementById('btn-tanya');
      const btnLabel  = document.getElementById('btn-label');
      const btnIcon   = document.getElementById('btn-icon');
      btn.disabled = true;
      btnLabel.textContent = 'Memproses...';
      btnIcon.innerHTML = '<span class="spinner"></span>';
      document.getElementById('loading-skeleton').classList.add('active');
      document.getElementById('result-container').innerHTML = '';
      document.getElementById('suggestion-chips').style.display = 'none';

      try {{
        const resp = await fetch('/api/tanya', {{
          method: 'POST',
          headers: {{ 'Content-Type': 'application/json' }},
          body: JSON.stringify({{ query }}),
        }});
        const data = await resp.json();

        document.getElementById('loading-skeleton').classList.remove('active');

        if (!resp.ok || data.error) {{
          showError(data.error || 'Terjadi kesalahan pada server. Silakan coba lagi.');
        }} else {{
          document.getElementById('result-container').innerHTML = data.html;
          initAccordions();
          // Smooth scroll ke hasil
          setTimeout(() => {{
            document.getElementById('result-container').scrollIntoView({{
              behavior: 'smooth', block: 'start'
            }});
          }}, 100);
        }}
      }} catch (err) {{
        document.getElementById('loading-skeleton').classList.remove('active');
        showError('Gagal terhubung ke server. Periksa koneksi Anda dan coba lagi.');
      }} finally {{
        btn.disabled = false;
        btnLabel.textContent = 'Tanya';
        btnIcon.innerHTML = 'arrow_forward';
        btnIcon.className = 'mat-icon';
        document.getElementById('suggestion-chips').style.display = '';
      }}
    }}

    document.getElementById('btn-tanya').addEventListener('click', submitQuery);
  </script>
</body>
</html>"""


# Cache halaman HTML agar tidak dibangun ulang setiap request
_CACHED_PAGE: str | None = None


def get_page_html() -> str:
    global _CACHED_PAGE
    if _CACHED_PAGE is None:
        _CACHED_PAGE = build_page_html(SUGGESTION_CHIPS)
    return _CACHED_PAGE


# ── Routes ───────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return get_page_html(), 200, {"Content-Type": "text/html; charset=utf-8"}


@app.route("/api/tanya", methods=["POST"])
def api_tanya():
    """
    POST /api/tanya
    Body  : { "query": "..." }
    Return: { "html": "...", "error": null }
          | { "html": null, "error": "pesan error" }
    """
    data  = request.get_json(silent=True) or {}
    query = (data.get("query") or "").strip()

    # ── Validasi ──────────────────────────────────────────────────────────────
    if not query:
        return jsonify({"error": "Pertanyaan tidak boleh kosong."}), 400
    if len(query) < 5:
        return jsonify({"error": "Pertanyaan terlalu pendek. Mohon masukkan pertanyaan yang lebih lengkap."}), 400
    if len(query) > 500:
        return jsonify({"error": "Pertanyaan terlalu panjang (maks 500 karakter). Mohon sederhanakan pertanyaan."}), 400

    # ── Retrieval ─────────────────────────────────────────────────────────────
    try:
        retrieve_fn = get_retrieve_fn()
    except FileNotFoundError:
        return jsonify({
            "error": (
                "Index FAISS belum tersedia. "
                "Jalankan: python scripts/embed_and_index.py"
            )
        }), 503
    except Exception as exc:
        return jsonify({"error": f"Gagal memuat model retrieval: {exc}"}), 503

    try:
        docs = retrieve_fn(query, k=5)
    except Exception as exc:
        return jsonify({"error": f"Gagal melakukan pencarian: {exc}"}), 500

    if not docs:
        return jsonify({"error": "Tidak ditemukan pasal yang relevan untuk pertanyaan ini."}), 404

    # ── Generation (LLM) ──────────────────────────────────────────────────────
    jawaban   = None
    llm_error = None
    try:
        generate_fn = get_generate_fn()
        jawaban = generate_fn(query, docs)
    except EnvironmentError as exc:
        llm_error = str(exc)          # API key belum diset → mode retrieval-only
    except Exception as exc:
        llm_error = str(exc)          # Error lain dari LLM provider

    # ── Build HTML ────────────────────────────────────────────────────────────
    result_html = build_result_html(query, jawaban, docs, llm_error)
    return jsonify({"html": result_html, "error": None})


# ── Entrypoint ───────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 60)
    print("  🏛  Tanya Kerja — RAG Ketenagakerjaan")
    print("  Buka: http://127.0.0.1:5000")
    print("=" * 60)
    app.run(debug=True, host="0.0.0.0", port=5000, use_reloader=False)
