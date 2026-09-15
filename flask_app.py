"""
flask_app.py — Flask UI: Tanya Kerja (RAG Ketenagakerjaan)
============================================================
Web app berbasis Flask yang menyajikan antarmuka Tanya Kerja
sesuai 3 tampilan UI (Minimal Chatbot, Katalog Dasar Hukum, & Naskah Reader)
dengan integrasi penuh ke pipeline RAG dan 27 dokumen regulasi Indonesia.

Cara menjalankan:
    python flask_app.py

Pastikan sebelumnya:
    1. python scripts/embed_and_index.py  (buat FAISS index)
    2. cp .env.example .env && isi API key LLM
"""

import os
import sys
import re
import json
import html as html_module
from pathlib import Path
from flask import Flask, request, jsonify

# Tambahkan scripts/ ke path agar bisa import modul retrieval & llm
ROOT_DIR = Path(__file__).parent
sys.path.insert(0, str(ROOT_DIR / "scripts"))

app = Flask(__name__)


# ── Security headers ────────────────────────────────────────────────────────────
@app.after_request
def add_security_headers(resp):
    """
    Header keamanan dasar di semua respons.
    CSP dibuat longgar agar UI (inline style/script + Google Fonts) tetap berfungsi.
    """
    resp.headers.setdefault("X-Content-Type-Options", "nosniff")
    resp.headers.setdefault("X-Frame-Options", "DENY")
    resp.headers.setdefault("Referrer-Policy", "no-referrer")
    resp.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "font-src 'self' https://fonts.gstatic.com; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
        "script-src 'self' 'unsafe-inline'; "
        "connect-src 'self'; "
        "img-src 'self' data:"
    )
    return resp


# ── Data Loading & Singletons ──────────────────────────────────────────────────
_retrieve_fn = None
_generate_fn = None
_docs_catalog = None
_chunks_data = None
_doc_chunks_map = None


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


def get_docs_catalog():
    global _docs_catalog
    if _docs_catalog is None:
        config_path = ROOT_DIR / "config" / "docs_config.json"
        if config_path.exists():
            with open(config_path, encoding="utf-8") as f:
                data = json.load(f)
                _docs_catalog = data.get("documents", [])
        else:
            _docs_catalog = []
    return _docs_catalog


def get_chunks_data():
    global _chunks_data, _doc_chunks_map
    if _chunks_data is None:
        chunks_path = ROOT_DIR / "data" / "chunks.json"
        if chunks_path.exists():
            with open(chunks_path, encoding="utf-8") as f:
                data = json.load(f)
                _chunks_data = data.get("chunks", [])
        else:
            _chunks_data = []

        # Map doc_id or (jenis, nomor, tahun) to chunks
        _doc_chunks_map = {}
        for c in _chunks_data:
            j = str(c.get("jenis", "")).strip().upper()
            no = str(c.get("nomor", "")).strip()
            th = str(c.get("tahun", "")).strip()
            key = f"{j}_{no}_{th}"
            if key not in _doc_chunks_map:
                _doc_chunks_map[key] = []
            _doc_chunks_map[key].append(c)

    return _chunks_data, _doc_chunks_map


# ── Helpers ────────────────────────────────────────────────────────────────────

def detect_jenis(doc: dict) -> str:
    raw = doc.get("jenis", "").upper().strip()
    if raw in ("UU",) or "UNDANG" in raw:
        return "UU"
    elif raw in ("PP",) or "PEMERINTAH" in raw:
        return "PP"
    elif "PERMENAKER" in raw or "MENAKER" in raw or "MENTERI" in raw:
        return "Permenaker"
    return raw or "UU"


def format_source_title(doc: dict) -> str:
    jenis = doc.get("jenis", "").strip()
    nomor = doc.get("nomor", "").strip()
    tahun = doc.get("tahun", "").strip()
    pasal = doc.get("pasal", "").strip()
    ayat  = doc.get("ayat", "").strip()

    title = f"{jenis} No. {nomor} Tahun {tahun}"
    if pasal:
        title += f" — Pasal {pasal}"
    if ayat:
        title += f" ayat ({ayat})"
    return title


def find_doc_id(doc: dict) -> str:
    """Temukan doc_id di docs_config yang cocok dengan chunk metadata."""
    catalog = get_docs_catalog()
    j = str(doc.get("jenis", "")).strip().upper()
    no = str(doc.get("nomor", "")).strip()
    th = str(doc.get("tahun", "")).strip()

    for item in catalog:
        ij = str(item.get("jenis", "")).strip().upper()
        ino = str(item.get("nomor", "")).strip()
        ith = str(item.get("tahun", "")).strip()
        if (j == ij or (j == "UU" and ij == "UU") or (j == "PP" and ij == "PP") or ("PERMEN" in j and "PERMEN" in ij)) and no == ino and th == ith:
            return item.get("id", "")
    # Fallback default doc_id
    return f"{j.lower()}_{no}_{th}"


SCORE_COLORS = {
    "success": {"text": "#4A7C59", "bar": "#4A7C59"},
    "warning": {"text": "#B45309", "bar": "#B45309"},
    "error":   {"text": "#991B1B", "bar": "#991B1B"},
}

JENIS_BADGE_STYLE = {
    "UU":        "background:#1B3A6B; color:#FFFFFF;",
    "PP":        "background:#475569; color:#FFFFFF;",
    "Permenaker":"background:#FFFFFF; color:#C8861A; border:1px solid #C8861A;",
}


def score_style(score_pct: int):
    if score_pct >= 70:
        return SCORE_COLORS["success"]
    elif score_pct >= 50:
        return SCORE_COLORS["warning"]
    else:
        return SCORE_COLORS["error"]


def clean_teks(teks: str, pasal: str) -> str:
    lines = teks.strip().splitlines()
    if lines and pasal and re.match(rf'^\s*[Pp]asal\s+{re.escape(str(pasal))}\s*$', lines[0]):
        lines = lines[1:]
    while lines and not lines[0].strip():
        lines.pop(0)
    return "\n".join(lines).strip()


def build_annotated_answer(jawaban: str, docs: list) -> str:
    if not jawaban or not docs:
        return f'<p class="mb-4">{html_module.escape(jawaban or "")}</p>'

    pasal_map: dict[str, dict] = {}
    for i, doc in enumerate(docs, 1):
        pasal = str(doc.get("pasal", "")).strip()
        if not pasal:
            continue
        jenis_short = detect_jenis(doc)
        nomor = doc.get("nomor", "")
        tahun = doc.get("tahun", "")
        doc_id = find_doc_id(doc)
        label = f"{jenis_short} No. {nomor}/{tahun} Pasal {pasal}"
        if pasal not in pasal_map:
            pasal_map[pasal] = {"card_id": f"card-{i}", "doc_id": doc_id, "pasal": pasal, "label": label}

    def replace_pasal(match):
        pasal_num = match.group(1)
        if pasal_num in pasal_map:
            info = pasal_map[pasal_num]
            label_escaped = html_module.escape(info["label"])
            return (
                f'<button class="citation-pill" '
                f'onclick="openDocument(\'{info["doc_id"]}\', \'{info["pasal"]}\')" '
                f'type="button">[{label_escaped}]</button>'
            )
        return match.group(0)

    annotated = re.sub(r'\bPasal\s+(\d+)\b', replace_pasal, jawaban)

    separator = '\n\n' if '\n\n' in annotated else '\n'
    paragraphs = annotated.split(separator)
    result = []
    for p in paragraphs:
        p = p.strip()
        if not p:
            continue
        p = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', p)
        result.append(f'<p class="mb-4 text-body-lg leading-relaxed">{p}</p>')

    return '\n'.join(result) or f'<p class="mb-4">{html_module.escape(jawaban)}</p>'


def build_result_html(query: str, jawaban: str | None, docs: list, llm_error: str | None = None) -> str:
    parts = []

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

    if jawaban:
        body_html = build_annotated_answer(jawaban, docs)
    else:
        d = docs[0]
        teks = clean_teks(d.get("teks", ""), d.get("pasal", ""))
        body_html = f"""
        <p class="mb-3"><strong style="color:#1C1917">{html_module.escape(d.get('jenis',''))} No. {html_module.escape(d.get('nomor',''))} Tahun {html_module.escape(d.get('tahun',''))}, Pasal {html_module.escape(str(d.get('pasal','')))}</strong></p>
        <p style="font-family:'Courier Prime',monospace; font-size:13px; line-height:24px; color:#3D3530; white-space:pre-wrap">{html_module.escape(teks)}</p>"""

    parts.append(f"""
    <!-- Sintesis Card -->
    <div class="synthesis-card">
      <div class="synthesis-header">
        <div class="synthesis-header-left">
          <span class="synthesis-icon">
            <span class="material-symbols-outlined" style="font-size:16px">auto_awesome</span>
          </span>
          <span class="synthesis-label">Ikhtisar Jawaban</span>
        </div>
        <button onclick="copyAnswer()" title="Salin jawaban" type="button" class="copy-btn">
          <span class="material-symbols-outlined" style="font-size:18px" id="copy-icon">content_copy</span>
        </button>
      </div>
      <div id="answer-body" class="synthesis-body">
        {body_html}
      </div>
    </div>""")

    n = len(docs)
    parts.append(f"""
    <!-- Source Cards -->
    <div class="sources-section">
      <div class="sources-header">
        <div class="sources-header-left">
          <h2 class="sources-title">{n} Rujukan Teratas</h2>
        </div>
        <span class="sources-rank-label">Paling Relevan</span>
      </div>
      <div class="source-cards-list">""")

    for i, doc in enumerate(docs, 1):
        card_id    = f"card-{i}"
        content_id = f"card-{i}-content"
        jenis      = detect_jenis(doc)
        title      = html_module.escape(format_source_title(doc))
        score_pct  = min(100, int(doc.get("score", 0) * 100))
        colors     = score_style(score_pct)
        badge_style = JENIS_BADGE_STYLE.get(jenis, "background:#1B3A6B; color:#FFFFFF;")

        doc_id = find_doc_id(doc)
        pasal_num = str(doc.get("pasal", "")).strip()

        is_first       = i == 1
        content_class  = "accordion-content open" if is_first else "accordion-content closed"
        content_style  = "max-height:2000px; opacity:1;" if is_first else "max-height:0px; opacity:0;"
        toggle_icon    = "expand_less" if is_first else "expand_more"

        teks_raw  = doc.get("teks", "").strip()
        ayat_num  = str(doc.get("ayat", "")).strip()
        teks_clean = clean_teks(teks_raw, pasal_num)
        teks_escaped = html_module.escape(teks_clean)

        pasal_header = f"Pasal {pasal_num}" if pasal_num else ""
        if ayat_num:
            pasal_header += f" Ayat ({ayat_num})"

        parts.append(f"""
        <!-- Card {i}: {jenis} -->
        <div class="source-card" id="{card_id}">
          <div class="source-card-inner">
            <div class="source-card-header">
              <div class="source-card-meta">
                <span class="jenis-badge" style="{badge_style}">{html_module.escape(jenis)}</span>
                <h3 class="source-title">{title}</h3>
              </div>
              <div class="source-card-controls">
                <button type="button" class="naskah-btn" onclick="openDocument('{doc_id}', '{pasal_num}')">
                  <span>{score_pct}%</span>
                  <span class="font-medium">Lihat Naskah</span>
                  <span class="material-symbols-outlined" style="font-size:14px">arrow_forward</span>
                </button>
                <button type="button"
                        data-content="{content_id}"
                        onclick="toggleAccordion('{content_id}', this)"
                        class="accordion-toggle" title="Toggle Detail">
                  <span class="material-symbols-outlined acc-icon" style="font-size:18px">{toggle_icon}</span>
                </button>
              </div>
            </div>

            <div class="{content_class}" id="{content_id}" style="{content_style}">
              <div class="accordion-inner">
                <div class="statute-block">
                  <p class="statute-text"><strong>{html_module.escape(pasal_header)}:</strong> {teks_escaped}</p>
                </div>
              </div>
            </div>
          </div>
        </div>""")

    parts.append("""
      </div>
    </div>""")

    return "\n".join(parts)


SUGGESTION_CHIPS = [
    "Berapa lama hak cuti melahirkan menurut UU Ketenagakerjaan?",
    "Aturan PHK sepihak bagaimana?",
    "Berapa upah lembur per jam?",
    "Hak cuti tahunan berapa hari?",
    "Kewajiban pengusaha soal K3?",
    "Syarat pembentukan serikat pekerja?",
    "Batas usia minimum pekerja anak?",
]


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
  <title>Tanya Kerja — Konsultasi Regulasi Ketenagakerjaan Indonesia</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=Plus+Jakarta+Sans:wght@600;700;800&family=Courier+Prime&display=swap" rel="stylesheet">
  <link href="https://fonts.googleapis.com/css2?family=Material+Symbols+Outlined:opsz,wght,FILL,GRAD@24,400,0,0" rel="stylesheet">
  <style>
    /* ── Reset & CSS Variables ─────────────────────────────────── */
    *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
    :root {{
      --bg-warm: #FBF9F5;
      --bg-card: #FFFFFF;
      --border-color: #E7E2DC;
      --text-main: #1C1917;
      --text-muted: #78716C;
      --brand-navy: #1B3A6B;
      --brand-blue: #2563EB;
      --brand-amber: #C8861A;
      --radius-lg: 12px;
      --radius-md: 8px;
    }}
    html {{ scroll-behavior: smooth; }}
    body {{
      font-family: 'Inter', sans-serif;
      background: var(--bg-warm);
      color: var(--text-main);
      min-height: 100vh;
      display: flex;
      flex-direction: column;
      -webkit-font-smoothing: antialiased;
    }}
    ::-webkit-scrollbar {{ width: 6px; height: 6px; }}
    ::-webkit-scrollbar-thumb {{ background: #CBD5E1; border-radius: 3px; }}

    /* ── Typography ─────────────────────────────────────────────── */
    .font-display {{ font-family: 'Plus Jakarta Sans', sans-serif; }}
    .font-code    {{ font-family: 'Courier Prime', monospace; }}

    /* ── Header Navbar ─────────────────────────────────────────── */
    .site-header {{
      position: sticky;
      top: 0; left: 0; right: 0;
      z-index: 50;
      background: rgba(251, 249, 245, 0.94);
      backdrop-filter: blur(10px);
      border-bottom: 1px solid var(--border-color);
    }}
    .site-header-inner {{
      max-width: 900px;
      margin: 0 auto;
      height: 64px;
      padding: 0 20px;
      display: flex;
      align-items: center;
      justify-content: space-between;
    }}
    .brand-group {{
      display: flex;
      align-items: center;
      gap: 10px;
      cursor: pointer;
      text-decoration: none;
    }}
    .brand-dot {{
      width: 10px; height: 10px;
      border-radius: 50%;
      background: var(--brand-navy);
    }}
    .brand-title {{
      font-family: 'Plus Jakarta Sans', sans-serif;
      font-size: 18px;
      font-weight: 800;
      color: var(--brand-navy);
      letter-spacing: -0.02em;
    }}
    .nav-link {{
      font-size: 13px;
      font-weight: 600;
      color: var(--brand-navy);
      text-decoration: none;
      padding: 6px 14px;
      border-radius: 20px;
      background: #F0EBE1;
      transition: all 0.2s;
      display: inline-flex;
      align-items: center;
      gap: 4px;
    }}
    .nav-link:hover {{
      background: #E2DBD0;
    }}

    /* ── Main Layout ────────────────────────────────────────────── */
    .app-main {{
      max-width: 900px;
      width: 100%;
      margin: 0 auto;
      padding: 24px 20px 60px;
      flex: 1;
    }}

    /* ── Views Switcher ─────────────────────────────────────────── */
    .view-panel {{
      display: none;
    }}
    .view-panel.active {{
      display: block;
    }}

    /* ── Search / Input Box ─────────────────────────────────────── */
    .search-card {{
      background: var(--bg-card);
      border: 1px solid var(--border-color);
      border-radius: var(--radius-lg);
      padding: 20px;
      box-shadow: 0 2px 10px rgba(0,0,0,0.02);
      margin-bottom: 24px;
    }}
    .query-textarea {{
      width: 100%;
      min-height: 80px;
      border: none;
      outline: none;
      resize: vertical;
      font-family: 'Inter', sans-serif;
      font-size: 15px;
      color: var(--text-main);
      background: transparent;
      line-height: 1.5;
    }}
    .query-textarea::placeholder {{
      color: #A8A29E;
    }}
    .search-action-row {{
      display: flex;
      align-items: center;
      justify-content: flex-end;
      margin-top: 12px;
      padding-top: 12px;
      border-top: 1px solid #F4F1EA;
    }}
    .btn-submit {{
      background: var(--brand-navy);
      color: #FFFFFF;
      border: none;
      padding: 10px 20px;
      border-radius: var(--radius-md);
      font-family: 'Plus Jakarta Sans', sans-serif;
      font-weight: 700;
      font-size: 14px;
      cursor: pointer;
      display: inline-flex;
      align-items: center;
      gap: 8px;
      transition: background 0.2s;
    }}
    .btn-submit:hover {{
      background: #11284A;
    }}
    .btn-submit:disabled {{
      opacity: 0.6;
      cursor: not-allowed;
    }}

    .chips-wrapper {{
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      margin-bottom: 24px;
    }}
    .chip-btn {{
      background: #F2EFE9;
      border: 1px solid #E2DCD3;
      border-radius: 16px;
      padding: 6px 14px;
      font-size: 12px;
      color: #44403C;
      cursor: pointer;
      transition: all 0.2s;
    }}
    .chip-btn:hover {{
      background: var(--brand-navy);
      color: #FFFFFF;
      border-color: var(--brand-navy);
    }}

    /* ── Synthesis Card ─────────────────────────────────────────── */
    .synthesis-card {{
      background: var(--bg-card);
      border: 1px solid var(--border-color);
      border-radius: var(--radius-lg);
      padding: 24px;
      margin-bottom: 28px;
      box-shadow: 0 2px 10px rgba(0,0,0,0.02);
    }}
    .synthesis-header {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      margin-bottom: 16px;
      padding-bottom: 12px;
      border-bottom: 1px solid #F4F1EA;
    }}
    .synthesis-header-left {{
      display: flex;
      align-items: center;
      gap: 8px;
    }}
    .synthesis-icon {{
      width: 28px; height: 28px;
      border-radius: 50%;
      background: #EFF6FF;
      color: #1D4ED8;
      display: flex; align-items: center; justify-content: center;
    }}
    .synthesis-label {{
      font-family: 'Plus Jakarta Sans', sans-serif;
      font-size: 15px;
      font-weight: 700;
      color: var(--brand-navy);
    }}
    .copy-btn {{
      background: transparent;
      border: none;
      color: var(--text-muted);
      cursor: pointer;
      padding: 4px;
      border-radius: 4px;
    }}
    .copy-btn:hover {{ color: var(--text-main); background: #F4F1EA; }}
    .synthesis-body {{
      font-size: 14.5px;
      line-height: 1.65;
      color: #292524;
    }}
    .citation-pill {{
      display: inline-block;
      background: #EFF6FF;
      color: #1E40AF;
      font-size: 12px;
      font-weight: 600;
      padding: 2px 8px;
      border-radius: 10px;
      border: 1px solid #BFDBFE;
      cursor: pointer;
      margin: 0 2px;
    }}
    .citation-pill:hover {{
      background: #DBEAFE;
    }}

    /* ── Sources Section ────────────────────────────────────────── */
    .sources-section {{
      margin-top: 12px;
    }}
    .sources-header {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      margin-bottom: 14px;
    }}
    .sources-title {{
      font-family: 'Plus Jakarta Sans', sans-serif;
      font-size: 16px;
      font-weight: 700;
      color: var(--brand-navy);
    }}
    .sources-rank-label {{
      font-size: 12px;
      font-weight: 600;
      color: var(--text-muted);
    }}
    .source-cards-list {{
      display: flex;
      flex-direction: column;
      gap: 10px;
    }}
    .source-card {{
      background: var(--bg-card);
      border: 1px solid var(--border-color);
      border-radius: var(--radius-md);
      padding: 16px;
      transition: border-color 0.2s;
    }}
    .source-card-header {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
    }}
    .source-card-meta {{
      display: flex;
      align-items: center;
      gap: 10px;
      flex: 1;
      min-width: 0;
    }}
    .jenis-badge {{
      font-size: 10px;
      font-weight: 700;
      padding: 3px 8px;
      border-radius: 4px;
      letter-spacing: 0.03em;
      flex-shrink: 0;
    }}
    .source-title {{
      font-size: 13.5px;
      font-weight: 600;
      color: var(--text-main);
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }}
    .source-card-controls {{
      display: flex;
      align-items: center;
      gap: 10px;
    }}
    .naskah-btn {{
      background: #F4F1EA;
      border: 1px solid #E2DCD3;
      color: var(--brand-navy);
      padding: 5px 12px;
      border-radius: 14px;
      font-size: 12px;
      font-weight: 600;
      cursor: pointer;
      display: inline-flex;
      align-items: center;
      gap: 6px;
      transition: all 0.2s;
    }}
    .naskah-btn:hover {{
      background: var(--brand-navy);
      color: #FFFFFF;
      border-color: var(--brand-navy);
    }}
    .accordion-toggle {{
      background: transparent;
      border: none;
      color: var(--text-muted);
      cursor: pointer;
      display: flex;
      align-items: center;
    }}
    .accordion-content {{
      overflow: hidden;
      transition: max-height 0.3s ease, opacity 0.3s ease;
    }}
    .accordion-inner {{
      padding-top: 12px;
      margin-top: 10px;
      border-top: 1px dashed #E7E2DC;
    }}
    .statute-text {{
      font-family: 'Courier Prime', monospace;
      font-size: 12.5px;
      line-height: 1.6;
      color: #383532;
      white-space: pre-wrap;
    }}

    /* ── Catalog View ───────────────────────────────────────────── */
    .catalog-hero {{
      margin-bottom: 24px;
    }}
    .hero-pill {{
      display: inline-block;
      font-size: 11px;
      font-weight: 700;
      letter-spacing: 0.05em;
      color: var(--brand-navy);
      text-transform: uppercase;
      margin-bottom: 8px;
    }}
    .hero-title {{
      font-family: 'Plus Jakarta Sans', sans-serif;
      font-size: 26px;
      font-weight: 800;
      color: var(--brand-navy);
      margin-bottom: 8px;
    }}
    .hero-desc {{
      font-size: 14px;
      color: var(--text-muted);
      line-height: 1.5;
      max-width: 720px;
    }}
    .info-card {{
      background: var(--bg-card);
      border: 1px solid var(--border-color);
      border-radius: var(--radius-lg);
      padding: 20px;
      margin-bottom: 24px;
    }}
    .info-card-title {{
      font-family: 'Plus Jakarta Sans', sans-serif;
      font-weight: 700;
      font-size: 15px;
      color: var(--brand-navy);
      margin-bottom: 6px;
    }}
    .info-card-text {{
      font-size: 13px;
      color: #57534E;
      line-height: 1.5;
    }}

    .catalog-filter-bar {{
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      margin-bottom: 20px;
    }}
    .tab-group {{
      display: flex;
      gap: 6px;
      background: #F0EBE1;
      padding: 4px;
      border-radius: 20px;
    }}
    .tab-btn {{
      border: none;
      background: transparent;
      padding: 6px 14px;
      border-radius: 16px;
      font-size: 12px;
      font-weight: 600;
      color: #57534E;
      cursor: pointer;
      transition: all 0.2s;
    }}
    .tab-btn.active {{
      background: var(--brand-navy);
      color: #FFFFFF;
    }}
    .catalog-search-input {{
      padding: 8px 14px;
      border: 1px solid var(--border-color);
      border-radius: 20px;
      font-size: 13px;
      outline: none;
      width: 240px;
      background: var(--bg-card);
    }}

    .doc-grid {{
      display: flex;
      flex-direction: column;
      gap: 12px;
      margin-bottom: 24px;
    }}
    .doc-card {{
      background: var(--bg-card);
      border: 1px solid var(--border-color);
      border-radius: var(--radius-lg);
      padding: 20px;
      display: flex;
      align-items: flex-start;
      justify-content: space-between;
      gap: 16px;
      transition: transform 0.2s, box-shadow 0.2s;
    }}
    .doc-card:hover {{
      transform: translateY(-2px);
      box-shadow: 0 4px 12px rgba(0,0,0,0.04);
    }}
    .doc-main {{
      flex: 1;
    }}
    .doc-header-row {{
      display: flex;
      align-items: center;
      gap: 10px;
      margin-bottom: 8px;
    }}
    .doc-name {{
      font-family: 'Plus Jakarta Sans', sans-serif;
      font-size: 16px;
      font-weight: 700;
      color: var(--brand-navy);
    }}
    .doc-desc {{
      font-size: 13px;
      color: #57534E;
      line-height: 1.5;
      margin-bottom: 12px;
    }}
    .doc-tags {{
      display: flex;
      gap: 8px;
      align-items: center;
    }}
    .meta-tag {{
      background: #F4F1EA;
      color: #78716C;
      font-size: 11px;
      font-weight: 600;
      padding: 2px 8px;
      border-radius: 10px;
    }}

    /* ── Document Reader View ───────────────────────────────────── */
    .reader-hero {{
      background: var(--bg-card);
      border: 1px solid var(--border-color);
      border-radius: var(--radius-lg);
      padding: 24px;
      margin-bottom: 20px;
    }}
    .reader-title {{
      font-family: 'Plus Jakarta Sans', sans-serif;
      font-size: 22px;
      font-weight: 800;
      color: var(--brand-navy);
      margin-bottom: 8px;
      line-height: 1.3;
    }}
    .reader-desc {{
      font-size: 13.5px;
      color: #57534E;
      line-height: 1.5;
      margin-bottom: 16px;
    }}
    .reader-meta-row {{
      display: flex;
      flex-wrap: wrap;
      gap: 12px;
      padding-top: 12px;
      border-top: 1px solid #F4F1EA;
    }}
    .reader-meta-pill {{
      font-size: 12.5px;
      color: #57534E;
      font-weight: 500;
      display: inline-flex;
      align-items: center;
      gap: 5px;
      background: #F5F2EB;
      padding: 4px 10px;
      border-radius: 12px;
    }}

    .reader-toolbar {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      margin-bottom: 20px;
    }}
    .pasal-search-box {{
      position: relative;
      flex: 1;
      max-width: 320px;
    }}
    .pasal-search-box input {{
      width: 100%;
      padding: 8px 14px 8px 36px;
      border: 1px solid var(--border-color);
      border-radius: 20px;
      font-size: 13px;
      outline: none;
      background: var(--bg-card);
    }}
    .pasal-search-box .search-icon {{
      position: absolute;
      left: 12px; top: 50%;
      transform: translateY(-50%);
      font-size: 18px;
      color: #A8A29E;
    }}

    .bab-header {{
      text-align: center;
      font-family: 'Plus Jakarta Sans', sans-serif;
      font-size: 12px;
      font-weight: 700;
      letter-spacing: 0.08em;
      color: #78716C;
      text-transform: uppercase;
      margin: 28px 0 16px;
      position: relative;
    }}
    .bab-header::before, .bab-header::after {{
      content: '';
      position: absolute;
      top: 50%;
      width: 30%;
      height: 1px;
      background: var(--border-color);
    }}
    .bab-header::before {{ left: 0; }}
    .bab-header::after {{ right: 0; }}

    .pasal-card {{
      background: var(--bg-card);
      border: 1px solid var(--border-color);
      border-radius: var(--radius-lg);
      padding: 20px;
      margin-bottom: 14px;
    }}
    .pasal-card-header {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      margin-bottom: 10px;
    }}
    .pasal-number {{
      font-family: 'Plus Jakarta Sans', sans-serif;
      font-size: 15px;
      font-weight: 700;
      color: var(--brand-navy);
    }}
    .pasal-actions {{
      display: flex;
      gap: 12px;
    }}
    .action-link {{
      font-size: 12px;
      color: var(--text-muted);
      cursor: pointer;
      text-decoration: none;
      display: inline-flex;
      align-items: center;
      gap: 4px;
    }}
    .action-link:hover {{ color: var(--brand-navy); }}

    /* ── Pagination Bar ─────────────────────────────────────────── */
    .pagination-bar {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      margin-top: 24px;
      padding-top: 16px;
      border-top: 1px solid var(--border-color);
    }}
    .page-info {{
      font-size: 13px;
      color: var(--text-muted);
    }}
    .page-btns {{
      display: flex;
      align-items: center;
      gap: 6px;
    }}
    .page-btn {{
      background: var(--bg-card);
      border: 1px solid var(--border-color);
      padding: 6px 12px;
      border-radius: 6px;
      font-size: 12px;
      font-weight: 600;
      color: var(--text-main);
      cursor: pointer;
    }}
    .page-btn.active {{
      background: var(--brand-navy);
      color: #FFFFFF;
      border-color: var(--brand-navy);
    }}
    .page-btn:disabled {{
      opacity: 0.4; cursor: not-allowed;
    }}

    /* ── Footer ─────────────────────────────────────────────────── */
    .site-footer {{
      text-align: center;
      padding: 24px;
      font-size: 12px;
      color: var(--text-muted);
      border-top: 1px solid var(--border-color);
      margin-top: auto;
    }}

    /* ── Skeleton Loading ───────────────────────────────────────── */
    .skeleton-box {{
      background: linear-gradient(90deg, #F4F1EA 25%, #EBE7DF 50%, #F4F1EA 75%);
      background-size: 200% 100%;
      animation: loading 1.5s infinite;
      border-radius: 6px;
    }}
    @keyframes loading {{
      0% {{ background-position: 200% 0; }}
      100% {{ background-position: -200% 0; }}
    }}
  </style>
</head>
<body>

  <!-- Navbar Header -->
  <header class="site-header">
    <div class="site-header-inner">
      <a class="brand-group" onclick="showView('chat')">
        <div class="brand-dot"></div>
        <span class="brand-title">Tanya Kerja</span>
      </a>
      <div id="nav-actions">
        <!-- Rendered dynamically -->
      </div>
    </div>
  </header>

  <!-- Main Application Body -->
  <main class="app-main">

    <!-- ── VIEW 1: MINIMAL CHATBOT ── -->
    <section id="view-chat" class="view-panel active">
      <!-- Search Input Card -->
      <div class="search-card">
        <textarea id="query-input" class="query-textarea" placeholder="Berapa lama hak cuti melahirkan menurut UU Ketenagakerjaan?"></textarea>
        <div class="search-action-row">
          <button type="button" id="btn-tanya" class="btn-submit" onclick="submitQuery()">
            <span>Ajukan Pertanyaan</span>
            <span class="material-symbols-outlined" style="font-size:18px">arrow_forward</span>
          </button>
        </div>
      </div>

      <!-- Chips Suggestion -->
      <div class="chips-wrapper">
        {chips_html}
      </div>

      <!-- Loading skeleton -->
      <div id="chat-loading" style="display:none;" class="synthesis-card">
        <div class="skeleton-box" style="height:20px; width:40%; margin-bottom:12px"></div>
        <div class="skeleton-box" style="height:14px; width:100%; margin-bottom:8px"></div>
        <div class="skeleton-box" style="height:14px; width:85%; margin-bottom:8px"></div>
        <div class="skeleton-box" style="height:14px; width:92%;"></div>
      </div>

      <!-- Results Container -->
      <div id="result-container">
        <!-- RAG Answer & 5 Sources injected here -->
      </div>
    </section>


    <!-- ── VIEW 2: DASAR HUKUM & KATALOG REGULASI ── -->
    <section id="view-catalog" class="view-panel">
      <div class="catalog-hero">
        <span class="hero-pill">DOKUMEN HUKUM & TENTANG PLATFORM</span>
        <h1 class="hero-title">Dasar Hukum & Tentang Platform</h1>
        <p class="hero-desc">Inisiatif independen yang menyederhanakan rujukan hukum ketenagakerjaan Indonesia secara objektif, berkeadilan, dan langsung bersumber dari undang-undang resmi.</p>
      </div>

      <div class="info-card">
        <h2 class="info-card-title">Sistem Teruji Berbasis Regulasi Resmi</h2>
        <p class="info-card-text">Tanya Kerja mengolah naskah resmi 27 dokumen hukum (UU, PP, Permenaker) ketenagakerjaan Indonesia. Setiap jawaban dihasilkan melalui analisis pencarian konteks hukum yang presisi tanpa mengarang pasal.</p>
      </div>

      <div class="catalog-filter-bar">
        <div class="tab-group">
          <button class="tab-btn active" onclick="filterCatalog('all', this)">Semua</button>
          <button class="tab-btn" onclick="filterCatalog('UU', this)">Undang-Undang (UU)</button>
          <button class="tab-btn" onclick="filterCatalog('PP', this)">Peraturan Pemerintah (PP)</button>
          <button class="tab-btn" onclick="filterCatalog('Permenaker', this)">Permenaker</button>
        </div>
        <input type="text" id="catalog-search" class="catalog-search-input" placeholder="🔍 Cari regulasi..." oninput="renderCatalog()">
      </div>

      <div id="catalog-list" class="doc-grid">
        <!-- Catalog cards injected here -->
      </div>

      <div class="pagination-bar" id="catalog-pagination">
        <!-- Catalog pagination -->
      </div>

      <div style="margin-top: 32px; padding: 16px; background: #F5F2EB; border-radius: 8px; font-size: 12px; color: #78716C;">
        <strong>DISCLAIMER:</strong> Tanya Kerja adalah sistem informasi dan literasi publik berbasis kecerdasan buatan. Jawaban yang dihasilkan bukan merupakan nasihat hukum formal (legal advice). Untuk tindakan hukum kompleks, berkonsultasilah dengan praktisi hukum profesional.
      </div>
    </section>


    <!-- ── VIEW 3: ARSIP NASKAH REGULASI & READER ── -->
    <section id="view-reader" class="view-panel">
      <div id="reader-hero-container">
        <!-- Reader header injected here -->
      </div>

      <div class="reader-toolbar">
        <div class="pasal-search-box">
          <span class="material-symbols-outlined search-icon">search</span>
          <input type="text" id="pasal-search-input" placeholder="Lompat ke nomor pasal (misal: 82, 156)..." oninput="onPasalSearch()">
        </div>
        <span id="reader-status-count" style="font-size:13px; color:var(--text-muted)"></span>
      </div>

      <div id="reader-passages-list">
        <!-- Articles & chapters injected here -->
      </div>

      <div class="pagination-bar" id="reader-pagination">
        <!-- Reader pagination -->
      </div>
    </section>

  </main>

  <footer class="site-footer">
    © 2026 Tanya Kerja — Hak & Kewajiban Ketenagakerjaan Indonesia
  </footer>

  <script>
    // State global
    let currentView = 'chat';
    let catalogDocs = [];
    let currentCategory = 'all';
    let catalogPage = 1;
    const catalogPerPage = 5;

    let currentDocId = '';
    let currentDocData = null;
    let readerPage = 1;
    const readerPerPage = 5;
    let pasalFilter = '';

    // Initialize
    window.addEventListener('DOMContentLoaded', async () => {{
      await fetchCatalog();
      updateNavActions();
    }});

    function updateNavActions() {{
      const navContainer = document.getElementById('nav-actions');
      if (currentView === 'chat') {{
        navContainer.innerHTML = `<a class="nav-link" onclick="showView('catalog')">
          <span>Dasar Hukum & Tentang</span>
          <span class="material-symbols-outlined" style="font-size:16px">arrow_forward</span>
        </a>`;
      }} else if (currentView === 'catalog') {{
        navContainer.innerHTML = `<a class="nav-link" onclick="showView('chat')">
          <span class="material-symbols-outlined" style="font-size:16px">arrow_back</span>
          <span>Tanya Kerja</span>
        </a>`;
      }} else if (currentView === 'reader') {{
        navContainer.innerHTML = `<a class="nav-link" onclick="showView('catalog')">
          <span class="material-symbols-outlined" style="font-size:16px">arrow_back</span>
          <span>Kembali ke Dasar Hukum & Tentang</span>
        </a>`;
      }}
    }}

    function showView(viewId) {{
      currentView = viewId;
      document.querySelectorAll('.view-panel').forEach(el => el.classList.remove('active'));
      document.getElementById(`view-${{viewId}}`).classList.add('active');
      updateNavActions();
      window.scrollTo({{ top: 0, behavior: 'smooth' }});
    }}

    function setQuery(q) {{
      document.getElementById('query-input').value = q;
      submitQuery();
    }}

    async function submitQuery() {{
      const qInput = document.getElementById('query-input');
      const query = qInput.value.trim();
      if (!query) return;

      const btn = document.getElementById('btn-tanya');
      btn.disabled = true;
      document.getElementById('chat-loading').style.display = 'block';
      document.getElementById('result-container').innerHTML = '';

      try {{
        const resp = await fetch('/api/tanya', {{
          method: 'POST',
          headers: {{ 'Content-Type': 'application/json' }},
          body: JSON.stringify({{ query }})
        }});
        const data = await resp.json();
        document.getElementById('chat-loading').style.display = 'none';

        if (data.error) {{
          document.getElementById('result-container').innerHTML = `
            <div style="padding:16px; background:#FEE2E2; border:1px solid #FCA5A5; color:#991B1B; border-radius:8px; font-size:14px">
              ${{data.error}}
            </div>`;
        }} else {{
          document.getElementById('result-container').innerHTML = data.html;
        }}
      }} catch (e) {{
        document.getElementById('chat-loading').style.display = 'none';
        document.getElementById('result-container').innerHTML = `
          <div style="padding:16px; background:#FEE2E2; border:1px solid #FCA5A5; color:#991B1B; border-radius:8px; font-size:14px">
            Gagal terhubung ke server. Periksa koneksi Anda.
          </div>`;
      }} finally {{
        btn.disabled = false;
      }}
    }}

    function toggleAccordion(contentId, btn) {{
      const content = document.getElementById(contentId);
      const icon = btn.querySelector('.acc-icon');
      if (content.classList.contains('open')) {{
        content.classList.remove('open');
        content.style.maxHeight = '0px';
        content.style.opacity = '0';
        icon.textContent = 'expand_more';
      }} else {{
        content.classList.add('open');
        content.style.maxHeight = '2000px';
        content.style.opacity = '1';
        icon.textContent = 'expand_less';
      }}
    }}

    function copyAnswer() {{
      const body = document.getElementById('answer-body');
      if (body) {{
        navigator.clipboard.writeText(body.innerText);
        const icon = document.getElementById('copy-icon');
        icon.textContent = 'check';
        setTimeout(() => icon.textContent = 'content_copy', 2000);
      }}
    }}

    function formatStatus(statusStr) {{
      if (!statusStr) return 'Berlaku';
      const clean = statusStr.replace(/_/g, ' ');
      return clean.charAt(0).toUpperCase() + clean.slice(1);
    }}

    // CATALOG FUNCTIONS
    async function fetchCatalog() {{
      try {{
        const resp = await fetch('/api/catalog');
        const data = await resp.json();
        catalogDocs = data.documents || [];
        renderCatalog();
      }} catch (e) {{
        console.error('Failed to fetch catalog', e);
      }}
    }}

    function filterCatalog(cat, btn) {{
      currentCategory = cat;
      catalogPage = 1;
      document.querySelectorAll('.tab-group .tab-btn').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      renderCatalog();
    }}

    function renderCatalog() {{
      const searchVal = document.getElementById('catalog-search').value.toLowerCase().trim();
      let filtered = catalogDocs.filter(d => {{
        const matchCat = (currentCategory === 'all') || (d.jenis.toUpperCase() === currentCategory.toUpperCase());
        const matchSearch = !searchVal || d.peraturan.toLowerCase().includes(searchVal) || d.catatan.toLowerCase().includes(searchVal);
        return matchCat && matchSearch;
      }});

      const total = filtered.length;
      const totalPages = Math.ceil(total / catalogPerPage) || 1;
      if (catalogPage > totalPages) catalogPage = totalPages;

      const start = (catalogPage - 1) * catalogPerPage;
      const paged = filtered.slice(start, start + catalogPerPage);

      const listContainer = document.getElementById('catalog-list');
      if (paged.length === 0) {{
        listContainer.innerHTML = `<div style="text-align:center; padding:40px; color:#78716C; font-size:14px">Tidak ada dokumen yang sesuai.</div>`;
      }} else {{
        listContainer.innerHTML = paged.map(d => {{
          let badgeStyle = "background:#1B3A6B; color:#FFF;";
          if (d.jenis === 'PP') badgeStyle = "background:#475569; color:#FFF;";
          if (d.jenis === 'Permenaker') badgeStyle = "background:#FFF; color:#C8861A; border:1px solid #C8861A;";

          return `
          <div class="doc-card">
            <div class="doc-main">
              <div class="doc-header-row">
                <span class="jenis-badge" style="${{badgeStyle}}">${{d.jenis}}</span>
                <h3 class="doc-name">${{d.jenis}} No. ${{d.nomor}} Tahun ${{d.tahun}}</h3>
              </div>
              <p class="doc-desc">${{d.peraturan}} — ${{d.catatan || ''}}</p>
              <div class="doc-tags">
                <span class="meta-tag">${{d.total_pasal || 0}} Pasal</span>
                ${{d.kronologi ? `<span class="meta-tag">${{d.kronologi}}</span>` : ''}}
              </div>
            </div>
            <button type="button" class="naskah-btn" onclick="openDocument('${{d.id}}')">
              <span>Lihat Naskah</span>
              <span class="material-symbols-outlined" style="font-size:14px">arrow_forward</span>
            </button>
          </div>`;
        }}).join('');
      }}

      // Pagination
      const pagContainer = document.getElementById('catalog-pagination');
      pagContainer.innerHTML = `
        <span class="page-info">Menampilkan ${{start + 1}}-${{Math.min(start + catalogPerPage, total)}} dari ${{total}} regulasi</span>
        <div class="page-btns">
          <button class="page-btn" ${{catalogPage === 1 ? 'disabled' : ''}} onclick="changeCatalogPage(${{catalogPage - 1}})">Sebelumnya</button>
          ${{Array.from({{length: totalPages}}, (_, i) => i + 1).map(p => `
            <button class="page-btn ${{p === catalogPage ? 'active' : ''}}" onclick="changeCatalogPage(${{p}})">${{p}}</button>
          `).join('')}}
          <button class="page-btn" ${{catalogPage === totalPages ? 'disabled' : ''}} onclick="changeCatalogPage(${{catalogPage + 1}})">Berikutnya</button>
        </div>`;
    }}

    function changeCatalogPage(p) {{
      catalogPage = p;
      renderCatalog();
    }}

    // READER FUNCTIONS
    async function openDocument(docId, targetPasal = '') {{
      currentDocId = docId;
      readerPage = 1;
      pasalFilter = targetPasal;
      document.getElementById('pasal-search-input').value = targetPasal;
      showView('reader');

      document.getElementById('reader-passages-list').innerHTML = `
        <div class="synthesis-card">
          <div class="skeleton-box" style="height:20px; width:50%; margin-bottom:12px"></div>
          <div class="skeleton-box" style="height:14px; width:100%; margin-bottom:8px"></div>
          <div class="skeleton-box" style="height:14px; width:80%;"></div>
        </div>`;

      await fetchDocumentDetail();
    }}

    async function fetchDocumentDetail() {{
      try {{
        const resp = await fetch(`/api/document/${{currentDocId}}?page=${{readerPage}}&pasal=${{encodeURIComponent(pasalFilter)}}`);
        currentDocData = await resp.json();
        renderReader();
      }} catch (e) {{
        console.error('Failed to fetch doc detail', e);
      }}
    }}

    function renderReader() {{
      if (!currentDocData || !currentDocData.doc) return;
      const d = currentDocData.doc;

      // Hero Header
      let badgeStyle = "background:#1B3A6B; color:#FFF;";
      if (d.jenis === 'PP') badgeStyle = "background:#475569; color:#FFF;";
      if (d.jenis === 'Permenaker') badgeStyle = "background:#FFF; color:#C8861A; border:1px solid #C8861A;";

      document.getElementById('reader-hero-container').innerHTML = `
        <div class="reader-hero">
          <div style="margin-bottom:12px">
            <span class="jenis-badge" style="${{badgeStyle}}">${{d.jenis.toUpperCase()}}</span>
          </div>
          <h1 class="reader-title">${{d.peraturan}}</h1>
          <p class="reader-desc">${{d.catatan || 'Dokumen resmi peraturan ketenagakerjaan Indonesia.'}}</p>
          <div class="reader-meta-row">
            <span class="reader-meta-pill"><span class="material-symbols-outlined" style="font-size:15px; color:var(--brand-navy)">calendar_today</span> Tahun: ${{d.tahun}}</span>
            <span class="reader-meta-pill"><span class="material-symbols-outlined" style="font-size:15px; color:var(--brand-navy)">gavel</span> Status: ${{formatStatus(d.status_berlaku || 'berlaku')}}</span>
            <span class="reader-meta-pill"><span class="material-symbols-outlined" style="font-size:15px; color:var(--brand-navy)">description</span> Total: ${{d.total_pasal || 0}} Pasal</span>
          </div>
        </div>`;

      // Passages
      const passages = currentDocData.passages || [];
      const total = currentDocData.total_passages || 0;
      const totalPages = currentDocData.total_pages || 1;

      document.getElementById('reader-status-count').textContent = `Menampilkan ${{(readerPage-1)*readerPerPage + 1}}-${{Math.min(readerPage*readerPerPage, total)}} dari ${{total}} naskah`;

      const listContainer = document.getElementById('reader-passages-list');
      if (passages.length === 0) {{
        listContainer.innerHTML = `<div style="text-align:center; padding:40px; color:#78716C; font-size:14px">Pasal/naskah tidak ditemukan.</div>`;
      }} else {{
        let html = '';
        let lastBab = '';

        passages.forEach(p => {{
          if (p.bab && p.bab !== lastBab) {{
            lastBab = p.bab;
            html += `<div class="bab-header">BAB ${{p.bab}} ${{p.judul_bab ? '- ' + p.judul_bab.toUpperCase() : ''}}</div>`;
          }}

          html += `
          <div class="pasal-card" id="pasal-${{p.pasal}}">
            <div class="pasal-card-header">
              <span class="pasal-number">Pasal ${{p.pasal}} ${{p.ayat ? 'Ayat ('+p.ayat+')' : ''}}</span>
              <div class="pasal-actions">
                <a class="action-link" onclick="copyPasal('pasal-text-${{p.pasal}}')">
                  <span class="material-symbols-outlined" style="font-size:14px">content_copy</span>
                  <span>Salin</span>
                </a>
              </div>
            </div>
            <p id="pasal-text-${{p.pasal}}" class="statute-text">${{htmlEscape(p.teks)}}</p>
          </div>`;
        }});
        listContainer.innerHTML = html;
      }}

      // Reader Pagination
      const pagContainer = document.getElementById('reader-pagination');
      pagContainer.innerHTML = `
        <span class="page-info">Halaman ${{readerPage}} dari ${{totalPages}}</span>
        <div class="page-btns">
          <button class="page-btn" ${{readerPage === 1 ? 'disabled' : ''}} onclick="changeReaderPage(${{readerPage - 1}})">Sebelumnya</button>
          ${{Array.from({{length: Math.min(5, totalPages)}}, (_, i) => i + 1).map(p => `
            <button class="page-btn ${{p === readerPage ? 'active' : ''}}" onclick="changeReaderPage(${{p}})">${{p}}</button>
          `).join('')}}
          <button class="page-btn" ${{readerPage === totalPages ? 'disabled' : ''}} onclick="changeReaderPage(${{readerPage + 1}})">Berikutnya</button>
        </div>`;
    }}

    function onPasalSearch() {{
      pasalFilter = document.getElementById('pasal-search-input').value.trim();
      readerPage = 1;
      fetchDocumentDetail();
    }}

    function changeReaderPage(p) {{
      readerPage = p;
      fetchDocumentDetail();
      window.scrollTo({{ top: 0, behavior: 'smooth' }});
    }}

    function copyPasal(elemId) {{
      const elem = document.getElementById(elemId);
      if (elem) {{
        navigator.clipboard.writeText(elem.innerText);
        alert('Teks pasal berhasil disalin!');
      }}
    }}

    function htmlEscape(str) {{
      return (str || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
    }}
  </script>
</body>
</html>"""


_CACHED_PAGE: str | None = None


def get_page_html() -> str:
    global _CACHED_PAGE
    if _CACHED_PAGE is None:
        _CACHED_PAGE = build_page_html(SUGGESTION_CHIPS)
    return _CACHED_PAGE


# ── Flask API Endpoints ────────────────────────────────────────────────────────

@app.route("/")
def index():
    return get_page_html(), 200, {"Content-Type": "text/html; charset=utf-8"}


@app.route("/api/catalog", methods=["GET"])
def api_catalog():
    catalog = get_docs_catalog()
    _, doc_chunks_map = get_chunks_data()

    # Enrich catalog with total pasal and total chunks count
    enriched = []
    for item in catalog:
        item_copy = dict(item)
        j = str(item.get("jenis", "")).strip().upper()
        no = str(item.get("nomor", "")).strip()
        th = str(item.get("tahun", "")).strip()
        key = f"{j}_{no}_{th}"
        chunks = doc_chunks_map.get(key, [])
        pasal_set = set(str(c.get("pasal")).strip() for c in chunks if c.get("pasal"))
        item_copy["total_chunks"] = len(chunks)
        item_copy["total_pasal"] = len(pasal_set)
        enriched.append(item_copy)

    return jsonify({"documents": enriched})


@app.route("/api/document/<doc_id>", methods=["GET"])
def api_document_detail(doc_id):
    catalog = get_docs_catalog()
    _, doc_chunks_map = get_chunks_data()

    # Find doc config
    target_doc = None
    for item in catalog:
        if item.get("id") == doc_id:
            target_doc = item
            break

    if not target_doc:
        return jsonify({"error": f"Dokumen '{doc_id}' tidak ditemukan"}), 404

    j = str(target_doc.get("jenis", "")).strip().upper()
    no = str(target_doc.get("nomor", "")).strip()
    th = str(target_doc.get("tahun", "")).strip()
    key = f"{j}_{no}_{th}"

    chunks = doc_chunks_map.get(key, [])
    pasal_set = set(str(c.get("pasal")).strip() for c in chunks if c.get("pasal"))

    target_doc_enriched = dict(target_doc)
    target_doc_enriched["total_pasal"] = len(pasal_set)
    target_doc_enriched["total_chunks"] = len(chunks)

    # Filtering & Pagination
    pasal_filter = request.args.get("pasal", "").strip()
    page = int(request.args.get("page", 1))
    per_page = int(request.args.get("per_page", 5))

    filtered_chunks = chunks
    if pasal_filter:
        filtered_chunks = [
            c for c in chunks if pasal_filter.lower() in str(c.get("pasal", "")).lower() or pasal_filter.lower() in str(c.get("teks", "")).lower()
        ]

    total_passages = len(filtered_chunks)
    total_pages = max(1, (total_passages + per_page - 1) // per_page)
    if page > total_pages:
        page = total_pages

    start_idx = (page - 1) * per_page
    paged_chunks = filtered_chunks[start_idx : start_idx + per_page]

    return jsonify({
        "doc": target_doc_enriched,
        "passages": paged_chunks,
        "page": page,
        "per_page": per_page,
        "total_passages": total_passages,
        "total_pages": total_pages
    })


@app.route("/api/tanya", methods=["POST"])
def api_tanya():
    data  = request.get_json(silent=True) or {}
    query = (data.get("query") or "").strip()

    if not query:
        return jsonify({"error": "Pertanyaan tidak boleh kosong."}), 400
    if len(query) < 5:
        return jsonify({"error": "Pertanyaan terlalu pendek. Mohon masukkan pertanyaan yang lebih lengkap."}), 400
    if len(query) > 500:
        return jsonify({"error": "Pertanyaan terlalu panjang (maks 500 karakter). Mohon sederhanakan pertanyaan."}), 400

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

    jawaban   = None
    llm_error = None
    try:
        generate_fn = get_generate_fn()
        jawaban = generate_fn(query, docs)
    except EnvironmentError as exc:
        app.logger.exception("Kesalahan konfigurasi LLM (API key belum diset)")
        llm_error = str(exc)
    except Exception as exc:
        app.logger.exception("Kesalahan panggilan LLM")
        llm_error = str(exc)

    result_html = build_result_html(query, jawaban, docs, llm_error)
    return jsonify({"html": result_html, "error": None})


if __name__ == "__main__":
    import os

    port = int(os.getenv("PORT", "5001"))  # 5001 default; 5000 sering dipakai sistem Windows
    print("=" * 60)
    print("  [Tanya Kerja] RAG Ketenagakerjaan")
    print(f"  Buka: http://127.0.0.1:{port}")
    print("=" * 60)
    app.run(debug=False, host="0.0.0.0", port=port, use_reloader=False)
