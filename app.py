"""
app.py — Tanya Kerja: RAG Hak & Kewajiban Pekerja
===================================================
Streamlit UI yang mengikuti Stitch design system secara faithful:
- Color tokens dari DESIGN.md (Indigo Dalam, Kunyit, Kertas, dll.)
- Typography: Plus Jakarta Sans + Inter + Courier Prime
- Layout: single-column 800px max, 12-col grid desktop, responsive
- Components: source cards dengan accent bar, relevance meter, skeleton loading
- States: empty, loading (skeleton), loaded, error, validation
"""

import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).parent / "scripts"))

# ── Page config ─────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Tanya Kerja — RAG Ketenagakerjaan",
    page_icon="⚖️",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ── Google Fonts + Design System CSS (faithful to Stitch DESIGN.md) ─────────────
st.markdown("""
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Courier+Prime:ital,wght@0,400;0,700;1,400&family=Inter:wght@400;500;600;700&family=Plus+Jakarta+Sans:wght@600;700&display=swap" rel="stylesheet">
<link href="https://fonts.googleapis.com/css2?family=Material+Symbols+Outlined:opsz,wght,FILL,GRAD@20..48,100..700,0..1,-50..200" rel="stylesheet">

<style>
/* ── Design Tokens (from Stitch DESIGN.md) ─────────────────────────────── */
:root {
  --surface-base:        #F7F5F0;
  --surface-card:        #FFFFFF;
  --surface-code:        #F0EDE8;
  --text-primary:        #1C1917;
  --text-secondary:      #78716C;
  --text-tertiary:       #A8A29E;
  --text-code:           #3D3530;
  --border-default:      #E7E2DC;
  --border-hover:        #C8861A;
  --primary-container:   #1B3A6B;
  --on-primary:          #FFFFFF;
  --interactive-hover:   #162E5A;
  --citation-pill-bg:    #EEF2FA;
  --status-success:      #4A7C59;
  --status-warning:      #B45309;
  --status-error:        #991B1B;
  --status-error-bg:     #FFF5F5;
  --outline:             #747780;
  --pp-color:            #475569;
  --shadow-card:         0 1px 3px rgba(28,25,23,0.06), 0 1px 2px rgba(28,25,23,0.04);
  --shadow-card-hover:   0 4px 12px rgba(28,25,23,0.10), 0 2px 4px rgba(28,25,23,0.06);
  --shadow-btn:          0 2px 4px rgba(27,58,107,0.25);
  --shadow-btn-hover:    0 4px 8px rgba(27,58,107,0.30);
}

/* ── Global Reset ───────────────────────────────────────────────────────── */
html, body, [data-testid="stAppViewContainer"],
[data-testid="stMain"], [data-testid="block-container"] {
  background-color: var(--surface-base) !important;
  font-family: 'Inter', sans-serif;
  color: var(--text-primary);
}

/* Hide Streamlit chrome */
#MainMenu, footer, header,
[data-testid="stToolbar"],
[data-testid="stDecoration"],
[data-testid="stStatusWidget"],
.stDeployButton { display: none !important; }

/* Remove default Streamlit top padding */
[data-testid="stMain"] > div:first-child { padding-top: 0 !important; }
[data-testid="block-container"] {
  padding: 0 !important;
  max-width: 100% !important;
}

/* ── Layout wrapper ─────────────────────────────────────────────────────── */
.tk-layout {
  max-width: 1120px;
  margin: 0 auto;
  padding: 0 16px;
  display: grid;
  grid-template-columns: 1fr;
  gap: 40px;
  align-items: start;
}
@media (min-width: 1024px) {
  .tk-layout { grid-template-columns: 1fr 280px; padding: 0 40px; }
}
@media (min-width: 768px) {
  .tk-layout { padding: 0 24px; }
}

.tk-main { max-width: 800px; width: 100%; }
.tk-sidebar { display: none; }
@media (min-width: 1024px) {
  .tk-sidebar { display: block; position: sticky; top: 32px; }
}

/* ── Header ─────────────────────────────────────────────────────────────── */
.tk-header {
  background: var(--surface-base);
  padding: 32px 16px 24px;
  text-align: center;
}
@media (min-width: 768px) { .tk-header { padding: 32px 40px 24px; } }

.tk-header-inner { max-width: 800px; margin: 0 auto; }

.tk-header-title-row {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  margin-bottom: 4px;
  flex-wrap: wrap;
}

.tk-app-title {
  font-family: 'Plus Jakarta Sans', sans-serif;
  font-size: 22px;
  font-weight: 700;
  color: var(--primary-container);
  letter-spacing: -0.02em;
  line-height: 28px;
  margin: 0;
}
@media (min-width: 768px) { .tk-app-title { font-size: 28px; line-height: 36px; } }

.tk-header-icon {
  font-size: 26px;
  color: var(--primary-container);
  font-variation-settings: 'FILL' 0, 'wght' 400, 'GRAD' 0, 'opsz' 28;
}

.tk-badge {
  display: inline-flex;
  align-items: center;
  padding: 2px 10px;
  border-radius: 9999px;
  border: 1px solid var(--border-hover);
  color: var(--border-hover);
  background: var(--surface-card);
  font-family: 'Inter', sans-serif;
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.01em;
  white-space: nowrap;
}

.tk-header-subtitle {
  font-family: 'Inter', sans-serif;
  font-size: 15px;
  font-weight: 400;
  color: var(--text-secondary);
  line-height: 25.5px;
  max-width: 480px;
  margin: 0 auto;
}

.tk-divider {
  width: 100%;
  height: 1px;
  background: var(--border-default);
  margin-top: 24px;
}

/* ── Input Card ─────────────────────────────────────────────────────────── */
.tk-input-card {
  background: var(--surface-card);
  border: 1.5px solid var(--border-default);
  border-radius: 12px;
  padding: 24px;
  box-shadow: var(--shadow-card);
  margin-bottom: 40px;
}

.tk-input-label-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
  flex-wrap: wrap;
  gap: 8px;
}

.tk-input-label {
  font-family: 'Inter', sans-serif;
  font-size: 11px;
  font-weight: 600;
  color: var(--text-secondary);
  letter-spacing: 0.05em;
  text-transform: uppercase;
}

.tk-status-dot {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-family: 'Inter', sans-serif;
  font-size: 11px;
  font-weight: 500;
  color: var(--status-success);
}
.tk-status-dot::before {
  content: '';
  display: inline-block;
  width: 8px; height: 8px;
  border-radius: 50%;
  background: var(--status-success);
}

/* Override Streamlit textarea */
[data-testid="stTextArea"] textarea {
  font-family: 'Inter', sans-serif !important;
  font-size: 15px !important;
  font-weight: 400 !important;
  color: var(--text-primary) !important;
  background: var(--surface-card) !important;
  border: 1.5px solid var(--border-default) !important;
  border-radius: 8px !important;
  padding: 14px 16px !important;
  box-shadow: inset 0 1px 2px rgba(28,25,23,0.04) !important;
  resize: none !important;
  line-height: 1.7 !important;
  transition: border-color 150ms ease, box-shadow 150ms ease !important;
  min-height: 96px !important;
}
[data-testid="stTextArea"] textarea:focus {
  border-color: var(--primary-container) !important;
  box-shadow: 0 0 0 3px rgba(27,58,107,0.12) !important;
  outline: none !important;
}
[data-testid="stTextArea"] textarea::placeholder {
  color: var(--text-tertiary) !important;
  font-style: italic !important;
}
[data-testid="stTextArea"] label { display: none !important; }
[data-testid="stTextArea"] { margin-bottom: 12px !important; }

/* Example chips row */
.tk-chips-row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
  margin-bottom: 16px;
}
.tk-chips-label {
  font-size: 11px;
  font-weight: 600;
  color: var(--text-secondary);
  letter-spacing: 0.01em;
  font-family: 'Inter', sans-serif;
}
.tk-chip {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  padding: 3px 10px;
  background: var(--surface-code);
  color: var(--text-secondary);
  font-family: 'Inter', sans-serif;
  font-size: 13px;
  font-weight: 400;
  border-radius: 6px;
  border: none;
  cursor: pointer;
  transition: background 150ms ease, color 150ms ease;
  text-decoration: none;
}
.tk-chip:hover {
  background: var(--border-default);
  color: var(--text-primary);
}
.tk-chip .material-symbols-outlined { font-size: 13px; }

/* Primary button — override Streamlit */
[data-testid="stButton"] > button {
  width: 100% !important;
  height: 48px !important;
  background: var(--primary-container) !important;
  color: var(--on-primary) !important;
  font-family: 'Inter', sans-serif !important;
  font-size: 15px !important;
  font-weight: 700 !important;
  border-radius: 8px !important;
  border: none !important;
  box-shadow: var(--shadow-btn) !important;
  transition: background 150ms ease, box-shadow 150ms ease, transform 80ms ease !important;
  display: flex !important;
  align-items: center !important;
  justify-content: center !important;
  gap: 8px !important;
  cursor: pointer !important;
}
[data-testid="stButton"] > button:hover {
  background: var(--interactive-hover) !important;
  box-shadow: var(--shadow-btn-hover) !important;
  transform: translateY(-1px) !important;
}
[data-testid="stButton"] > button:active {
  transform: translateY(1px) !important;
}
[data-testid="stButton"] > button:disabled {
  opacity: 0.7 !important;
  cursor: not-allowed !important;
  transform: none !important;
}

/* Disclaimer */
.tk-disclaimer {
  display: flex;
  align-items: flex-start;
  gap: 6px;
  margin-top: 12px;
  font-family: 'Inter', sans-serif;
  font-size: 11px;
  color: var(--text-secondary);
  line-height: 1.6;
}
.tk-disclaimer .material-symbols-outlined { font-size: 16px; flex-shrink: 0; margin-top: 1px; }

/* ── Validation Warning ──────────────────────────────────────────────────── */
.tk-validation {
  display: flex;
  align-items: flex-start;
  gap: 6px;
  padding: 10px 14px;
  background: #FFFBEB;
  border: 1px solid var(--border-hover);
  border-radius: 6px;
  margin-top: 12px;
  font-family: 'Inter', sans-serif;
  font-size: 13px;
  color: var(--status-warning);
}
.tk-validation .material-symbols-outlined { font-size: 16px; flex-shrink: 0; }

/* ── Section Header ─────────────────────────────────────────────────────── */
.tk-section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding-bottom: 12px;
  border-bottom: 1px solid var(--border-default);
  margin-bottom: 16px;
  flex-wrap: wrap;
  gap: 8px;
}
.tk-section-title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-family: 'Plus Jakarta Sans', sans-serif;
  font-size: 22px;
  font-weight: 700;
  color: var(--primary-container);
  letter-spacing: -0.02em;
  margin: 0;
}
.tk-section-title .material-symbols-outlined { font-size: 24px; }
.tk-section-meta {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 3px 10px;
  background: var(--surface-code);
  border: 1px solid var(--border-default);
  border-radius: 6px;
  font-family: 'Inter', sans-serif;
  font-size: 11px;
  font-weight: 500;
  color: var(--text-secondary);
}
.tk-section-meta .material-symbols-outlined { font-size: 14px; }

/* ── Answer Section ─────────────────────────────────────────────────────── */
.tk-answer-card {
  background: var(--surface-card);
  border: 1px solid var(--border-default);
  border-radius: 12px;
  padding: 24px;
  box-shadow: var(--shadow-card);
  margin-bottom: 40px;
  animation: tk-fadein 0.4s ease-out;
}
@keyframes tk-fadein {
  from { opacity: 0; transform: translateY(8px); }
  to   { opacity: 1; transform: translateY(0); }
}
.tk-answer-body {
  font-family: 'Inter', sans-serif;
  font-size: 17px;
  font-weight: 400;
  color: var(--text-primary);
  line-height: 29.75px;
  letter-spacing: 0em;
}
.tk-answer-body p { margin-bottom: 16px; }
.tk-answer-body p:last-child { margin-bottom: 0; }

.tk-feedback-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding-top: 16px;
  margin-top: 16px;
  border-top: 1px solid var(--border-default);
  flex-wrap: wrap;
  gap: 8px;
}
.tk-feedback-label {
  font-family: 'Inter', sans-serif;
  font-size: 13px;
  font-weight: 500;
  color: var(--text-secondary);
}
.tk-feedback-btns { display: flex; gap: 4px; align-items: center; }
.tk-feedback-btn {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 4px 10px;
  border: 1px solid var(--border-default);
  border-radius: 4px;
  background: transparent;
  font-family: 'Inter', sans-serif;
  font-size: 13px;
  color: var(--text-secondary);
  cursor: pointer;
  transition: all 150ms ease;
}
.tk-feedback-btn:hover { border-color: var(--primary-container); background: var(--citation-pill-bg); color: var(--primary-container); }
.tk-feedback-btn .material-symbols-outlined { font-size: 16px; }

/* ── Source Cards ───────────────────────────────────────────────────────── */
.tk-sources-stack { display: flex; flex-direction: column; gap: 12px; }

.tk-source-card {
  position: relative;
  background: var(--surface-card);
  border: 1.5px solid var(--border-default);
  border-radius: 10px;
  overflow: hidden;
  box-shadow: var(--shadow-card);
  transition: border-color 200ms ease, box-shadow 200ms ease;
  animation: tk-fadein 0.35s ease-out both;
}
.tk-source-card:hover {
  border-color: var(--border-hover);
  box-shadow: var(--shadow-card-hover);
}
.tk-source-card:nth-child(1) { animation-delay: 0ms; }
.tk-source-card:nth-child(2) { animation-delay: 80ms; }
.tk-source-card:nth-child(3) { animation-delay: 160ms; }
.tk-source-card:nth-child(4) { animation-delay: 240ms; }
.tk-source-card:nth-child(5) { animation-delay: 320ms; }

.tk-accent-bar {
  position: absolute;
  left: 0; top: 0; bottom: 0;
  width: 4px;
}
.tk-accent-uu      { background: var(--primary-container); }
.tk-accent-pp      { background: var(--pp-color); }
.tk-accent-permenaker { background: var(--border-hover); }

.tk-card-body { padding: 16px 16px 16px 20px; }

.tk-card-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 4px;
}

.tk-card-left { flex: 1; min-width: 0; }
.tk-card-badge-row { display: flex; align-items: center; gap: 8px; margin-bottom: 4px; flex-wrap: wrap; }

.tk-type-badge {
  display: inline-flex;
  align-items: center;
  padding: 2px 8px;
  border-radius: 4px;
  font-family: 'Inter', sans-serif;
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.05em;
  text-transform: uppercase;
  white-space: nowrap;
}
.tk-type-uu         { background: var(--primary-container); color: var(--on-primary); }
.tk-type-pp         { background: var(--pp-color); color: var(--on-primary); }
.tk-type-permenaker { background: transparent; border: 1px solid var(--border-hover); color: var(--border-hover); }

.tk-card-title {
  font-family: 'Plus Jakarta Sans', sans-serif;
  font-size: 18px;
  font-weight: 600;
  color: var(--primary-container);
  letter-spacing: -0.02em;
  margin: 0;
  line-height: 24px;
}
.tk-card-subtitle {
  font-family: 'Inter', sans-serif;
  font-size: 13px;
  color: var(--text-secondary);
  line-height: 22.1px;
  margin-top: 2px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

/* Relevance meter */
.tk-relevance {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  flex-shrink: 0;
}
.tk-relevance-label {
  font-family: 'Inter', sans-serif;
  font-size: 11px;
  font-weight: 600;
  color: var(--text-tertiary);
  letter-spacing: 0.05em;
  text-transform: uppercase;
  margin-bottom: 2px;
}
.tk-relevance-row { display: flex; align-items: center; gap: 8px; }
.tk-relevance-pct {
  font-family: 'Inter', sans-serif;
  font-size: 13px;
  font-weight: 700;
  min-width: 32px;
  text-align: right;
}
.tk-relevance-pct.high   { color: var(--status-success); }
.tk-relevance-pct.medium { color: var(--border-hover); }
.tk-relevance-pct.low    { color: var(--status-error); }
.tk-relevance-track {
  width: 80px; height: 4px;
  background: var(--border-default);
  border-radius: 2px;
  overflow: hidden;
}
.tk-relevance-fill {
  height: 100%;
  border-radius: 2px;
  transition: width 600ms ease-out;
}
.tk-fill-high   { background: var(--status-success); }
.tk-fill-medium { background: var(--border-hover); }
.tk-fill-low    { background: var(--status-error); }

/* Card expand / article text */
.tk-card-expand {
  margin-top: 16px;
  padding-top: 12px;
  border-top: 1px solid var(--border-default);
}
.tk-card-expand-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
}
.tk-expand-label {
  font-family: 'Inter', sans-serif;
  font-size: 11px;
  color: var(--text-secondary);
}
.tk-article-box {
  background: var(--surface-code);
  border-radius: 6px;
  border-left: 3px solid var(--border-hover);
  padding: 14px 16px;
}
.tk-article-text {
  font-family: 'Courier Prime', monospace;
  font-size: 13px;
  font-weight: 400;
  color: var(--text-code);
  line-height: 24px;
  white-space: pre-wrap;
  word-break: break-word;
  margin: 0;
}

.tk-toggle-btn {
  display: inline-flex;
  align-items: center;
  gap: 2px;
  background: none;
  border: none;
  font-family: 'Inter', sans-serif;
  font-size: 13px;
  font-weight: 600;
  color: var(--primary-container);
  cursor: pointer;
  padding: 2px 0;
  transition: color 150ms ease;
}
.tk-toggle-btn:hover { color: var(--interactive-hover); }
.tk-toggle-btn .material-symbols-outlined { font-size: 16px; }

/* ── Skeleton loading ────────────────────────────────────────────────────── */
@keyframes tk-pulse {
  0%, 100% { opacity: 1; }
  50%       { opacity: 0.45; }
}
@keyframes tk-shimmer {
  0%   { transform: translateX(-100%); }
  100% { transform: translateX(100%); }
}
.tk-skeleton-card {
  background: var(--surface-card);
  border: 1px solid var(--border-default);
  border-radius: 12px;
  padding: 24px;
  box-shadow: var(--shadow-card);
  position: relative;
  overflow: hidden;
  margin-bottom: 40px;
}
.tk-shimmer-overlay {
  position: absolute;
  inset: 0;
  background: linear-gradient(90deg, transparent, rgba(247,245,240,0.7), transparent);
  animation: tk-shimmer 2s infinite;
  pointer-events: none;
}
.tk-skel-line {
  height: 16px;
  border-radius: 4px;
  background: var(--surface-code);
  animation: tk-pulse 1.5s ease-in-out infinite;
  margin-bottom: 10px;
}
.tk-skel-line.w-80  { width: 80%; }
.tk-skel-line.w-95  { width: 95%; }
.tk-skel-line.w-65  { width: 65%; }
.tk-skel-line.w-50  { width: 50%; }
.tk-skel-card-item {
  background: var(--surface-card);
  border: 1px solid var(--border-default);
  border-radius: 10px;
  padding: 16px;
  margin-bottom: 12px;
  overflow: hidden;
  position: relative;
}
.tk-skel-badge {
  height: 20px; width: 36px;
  border-radius: 4px;
  background: var(--primary-container);
  display: inline-block;
}
.tk-skel-title {
  height: 18px; width: 240px; max-width: 70%;
  border-radius: 4px;
  background: var(--surface-code);
  animation: tk-pulse 1.5s ease-in-out infinite;
  display: inline-block;
}
.tk-loading-status {
  display: flex;
  align-items: center;
  gap: 8px;
  font-family: 'Inter', sans-serif;
  font-size: 13px;
  color: var(--text-secondary);
  margin-top: 12px;
  animation: tk-pulse 1.5s ease-in-out infinite;
}
.tk-spinner {
  width: 14px; height: 14px;
  border: 2px solid var(--border-default);
  border-top-color: var(--primary-container);
  border-radius: 50%;
  animation: spin 800ms linear infinite;
  flex-shrink: 0;
}
@keyframes spin { to { transform: rotate(360deg); } }

/* ── Error / No-result state ────────────────────────────────────────────── */
.tk-error-box {
  background: var(--status-error-bg);
  border: 1px solid var(--status-error);
  border-radius: 6px;
  padding: 14px 16px;
  display: flex;
  gap: 8px;
  align-items: flex-start;
  font-family: 'Inter', sans-serif;
}
.tk-error-box .material-symbols-outlined { font-size: 18px; color: var(--status-error); flex-shrink: 0; }
.tk-error-title { font-size: 15px; font-weight: 700; color: var(--status-error); margin-bottom: 2px; }
.tk-error-body  { font-size: 13px; color: #7F1D1D; }

/* ── Sidebar ─────────────────────────────────────────────────────────────── */
.tk-sidebar-card {
  background: var(--surface-card);
  border: 1px solid var(--border-default);
  border-radius: 12px;
  padding: 16px;
  box-shadow: var(--shadow-card);
  margin-bottom: 16px;
}
.tk-sidebar-header {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 12px;
}
.tk-sidebar-title {
  font-family: 'Plus Jakarta Sans', sans-serif;
  font-size: 15px;
  font-weight: 600;
  color: var(--text-primary);
  letter-spacing: -0.01em;
}
.tk-sidebar-sub {
  font-family: 'Inter', sans-serif;
  font-size: 11px;
  color: var(--text-secondary);
  margin-bottom: 8px;
}
.tk-sidebar-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 6px 8px;
  margin: 0 -8px;
  border-radius: 6px;
  font-family: 'Inter', sans-serif;
  font-size: 13px;
  color: var(--text-primary);
  cursor: pointer;
  transition: background 150ms ease, color 150ms ease;
  text-decoration: none;
  border: none;
  background: none;
  width: calc(100% + 16px);
  text-align: left;
}
.tk-sidebar-item:hover {
  background: var(--citation-pill-bg);
  color: var(--primary-container);
}
.tk-sidebar-item .material-symbols-outlined {
  font-size: 14px;
  color: var(--border-hover);
}
.tk-corpus-item {
  border-left: 3px solid;
  padding: 6px 10px;
  margin-bottom: 8px;
}
.tk-corpus-item.uu         { border-color: var(--primary-container); }
.tk-corpus-item.pp         { border-color: var(--outline); }
.tk-corpus-item.permenaker { border-color: var(--border-hover); }
.tk-corpus-label {
  font-family: 'Inter', sans-serif;
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}
.tk-corpus-label.uu         { color: var(--primary-container); }
.tk-corpus-label.pp         { color: var(--text-secondary); }
.tk-corpus-label.permenaker { color: var(--border-hover); }
.tk-corpus-val {
  font-family: 'Inter', sans-serif;
  font-size: 13px;
  color: var(--text-primary);
  margin-top: 1px;
}
.tk-corpus-desc {
  font-family: 'Inter', sans-serif;
  font-size: 11px;
  color: var(--text-secondary);
  margin-top: 1px;
}

/* ── Footer ─────────────────────────────────────────────────────────────── */
.tk-footer {
  max-width: 800px;
  margin: 32px auto 0;
  padding: 24px 16px 48px;
  text-align: center;
}
.tk-footer-divider { width: 100%; height: 1px; background: var(--border-default); margin-bottom: 16px; }
.tk-footer p {
  font-family: 'Inter', sans-serif;
  font-size: 13px;
  color: var(--text-secondary);
  margin-bottom: 4px;
  line-height: 22.1px;
}
.tk-footer p.small { font-size: 11px; color: var(--text-tertiary); }
.tk-footer .accent { color: var(--primary-container); font-weight: 500; }

/* ── Mobile sidebar drawer (bottom) ─────────────────────────────────────── */
.tk-mobile-examples {
  display: block;
  margin-bottom: 16px;
}
@media (min-width: 1024px) { .tk-mobile-examples { display: none; } }

/* Hide Streamlit sidebar */
[data-testid="stSidebar"] { display: none !important; }

/* Streamlit form/widget label override */
[data-testid="stForm"] { border: none !important; padding: 0 !important; }
</style>
""", unsafe_allow_html=True)


# ── Lazy-load retrieval & LLM ────────────────────────────────────────────────
@st.cache_resource(show_spinner=False)
def _load_retrieval():
    from retrieval import retrieve_documents, _load
    _load()
    return retrieve_documents

@st.cache_resource(show_spinner=False)
def _load_llm():
    from llm import generate_answer
    return generate_answer


def _retrieve(q, k=5):
    try:
        fn = _load_retrieval()
        return fn(q, k=k), None
    except FileNotFoundError as e:
        return [], str(e)
    except Exception as e:
        return [], str(e)

def _generate(q, docs):
    try:
        fn = _load_llm()
        return fn(q, docs), None
    except EnvironmentError as e:
        return None, str(e)
    except Exception as e:
        return None, str(e)


# ── Helper HTML builders ─────────────────────────────────────────────────────
def _accent_class(jenis: str) -> str:
    j = jenis.upper()
    if j == "UU": return "tk-accent-uu"
    if j == "PP": return "tk-accent-pp"
    return "tk-accent-permenaker"

def _badge_class(jenis: str) -> str:
    j = jenis.upper()
    if j == "UU": return "tk-type-uu"
    if j == "PP": return "tk-type-pp"
    return "tk-type-permenaker"

def _relevance_classes(score: float):
    pct = int(score * 100)
    if pct >= 70:  return "high",   "tk-fill-high"
    if pct >= 50:  return "medium", "tk-fill-medium"
    return "low", "tk-fill-low"

def _source_card_html(doc: dict, expanded: bool = False) -> str:
    jenis     = doc.get("jenis", "")
    nomor     = doc.get("nomor", "")
    tahun     = doc.get("tahun", "")
    pasal     = doc.get("pasal", "")
    ayat      = doc.get("ayat", "")
    peraturan = doc.get("peraturan", "")
    bab       = doc.get("bab", "")
    judul_bab = doc.get("judul_bab", "")
    teks      = doc.get("teks", "")
    score     = doc.get("score", 0)
    tipe      = doc.get("tipe", "pasal")

    pct = int(score * 100)
    rel_cls, fill_cls = _relevance_classes(score)
    accent_cls = _accent_class(jenis)
    badge_cls  = _badge_class(jenis)

    pasal_label = f"Pasal {pasal}"
    if ayat: pasal_label += f" Ayat ({ayat})"
    if tipe == "penjelasan": pasal_label += " <em>(Penjelasan)</em>"

    subtitle = peraturan
    if bab: subtitle += f" · <strong>Bab {bab}: {judul_bab}</strong>"

    expand_html = ""
    if expanded:
        import html
        teks_escaped = html.escape(teks)
        expand_html = f"""
        <div class="tk-card-expand">
          <div class="tk-card-expand-header">
            <span class="tk-expand-label">Kutipan Naskah Asli Peraturan:</span>
            <button class="tk-toggle-btn">
              Sembunyikan teks
              <span class="material-symbols-outlined">expand_less</span>
            </button>
          </div>
          <div class="tk-article-box">
            <pre class="tk-article-text">{teks_escaped}</pre>
          </div>
        </div>"""

    return f"""
<div class="tk-source-card">
  <div class="tk-accent-bar {accent_cls}"></div>
  <div class="tk-card-body">
    <div class="tk-card-header">
      <div class="tk-card-left">
        <div class="tk-card-badge-row">
          <span class="tk-type-badge {badge_cls}">{jenis}</span>
          <h4 class="tk-card-title">{jenis} No. {nomor} Tahun {tahun} — {pasal_label}</h4>
        </div>
        <p class="tk-card-subtitle">{subtitle}</p>
      </div>
      <div class="tk-relevance">
        <span class="tk-relevance-label">Relevansi</span>
        <div class="tk-relevance-row">
          <span class="tk-relevance-pct {rel_cls}">{pct}%</span>
          <div class="tk-relevance-track">
            <div class="tk-relevance-fill {fill_cls}" style="width:{pct}%"></div>
          </div>
        </div>
      </div>
    </div>
    {expand_html if expanded else
     f'<div style="text-align:right;margin-top:8px;"><button class="tk-toggle-btn">Lihat teks <span class="material-symbols-outlined">expand_more</span></button></div>'}
  </div>
</div>"""

def _skeleton_html() -> str:
    return """
<div class="tk-skeleton-card">
  <div class="tk-shimmer-overlay"></div>
  <div style="display:flex;align-items:center;gap:8px;margin-bottom:16px;">
    <div style="width:28px;height:28px;border-radius:6px;background:var(--surface-code);animation:tk-pulse 1.5s infinite;"></div>
    <div style="width:180px;height:20px;border-radius:4px;background:var(--surface-code);animation:tk-pulse 1.5s infinite;"></div>
    <div style="margin-left:auto;width:120px;height:20px;border-radius:9999px;background:var(--surface-code);animation:tk-pulse 1.5s infinite;"></div>
  </div>
  <div class="tk-skel-line w-95"></div>
  <div style="display:flex;align-items:center;gap:8px;margin-bottom:10px;">
    <div class="tk-skel-line w-50" style="margin-bottom:0;"></div>
    <span style="display:inline-flex;align-items:center;height:20px;padding:0 8px;background:var(--citation-pill-bg);border-radius:4px;font-size:12px;color:var(--primary-container);font-family:monospace;animation:tk-pulse 1.5s infinite;">[Pasal ...]</span>
    <div class="tk-skel-line" style="width:25%;margin-bottom:0;"></div>
  </div>
  <div class="tk-skel-line w-80"></div>
  <div class="tk-skel-line w-65"></div>
</div>

<div style="margin-bottom:12px;">
  <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:12px;">
    <div style="width:180px;height:18px;border-radius:4px;background:var(--surface-code);animation:tk-pulse 1.5s infinite;"></div>
    <div style="width:140px;height:14px;border-radius:4px;background:var(--surface-code);animation:tk-pulse 1.5s infinite;"></div>
  </div>
</div>

<div class="tk-skel-card-item">
  <div style="position:absolute;left:0;top:0;bottom:0;width:4px;background:var(--primary-container);"></div>
  <div style="padding-left:12px;display:flex;align-items:center;justify-content:space-between;">
    <div style="display:flex;align-items:center;gap:8px;">
      <span class="tk-skel-badge"></span>
      <span class="tk-skel-title"></span>
    </div>
    <div style="width:60px;height:4px;background:var(--border-default);border-radius:2px;overflow:hidden;">
      <div style="height:100%;width:80%;background:var(--status-success);border-radius:2px;animation:tk-pulse 1.5s infinite;"></div>
    </div>
  </div>
</div>
<div class="tk-skel-card-item" style="margin-top:12px;">
  <div style="position:absolute;left:0;top:0;bottom:0;width:4px;background:var(--pp-color);"></div>
  <div style="padding-left:12px;display:flex;align-items:center;justify-content:space-between;">
    <div style="display:flex;align-items:center;gap:8px;">
      <span class="tk-skel-badge" style="background:var(--pp-color);"></span>
      <span class="tk-skel-title" style="width:200px;"></span>
    </div>
    <div style="width:60px;height:4px;background:var(--border-default);border-radius:2px;overflow:hidden;">
      <div style="height:100%;width:65%;background:var(--border-hover);border-radius:2px;animation:tk-pulse 1.5s infinite;"></div>
    </div>
  </div>
</div>

<div class="tk-loading-status">
  <div class="tk-spinner"></div>
  Sedang mencari dan mensintesis rujukan hukum resmi...
</div>
"""

def _sidebar_html(example_questions: list) -> str:
    items = "\n".join(
        f'<button class="tk-sidebar-item" onclick="">'
        f'<span>{q}</span>'
        f'<span class="material-symbols-outlined">arrow_forward</span>'
        f'</button>'
        for q in example_questions
    )
    return f"""
<div class="tk-sidebar-card">
  <div class="tk-sidebar-header">
    <span class="material-symbols-outlined" style="font-size:18px;color:var(--primary-container);">lightbulb</span>
    <span class="tk-sidebar-title">Contoh Pertanyaan</span>
  </div>
  <p class="tk-sidebar-sub">Klik untuk mencoba</p>
  {items}
</div>
<div class="tk-sidebar-card">
  <div class="tk-sidebar-header">
    <span class="material-symbols-outlined" style="font-size:18px;color:var(--primary-container);">menu_book</span>
    <span class="tk-sidebar-title">Sumber Dokumen</span>
    <span style="margin-left:auto;font-size:11px;color:var(--text-secondary);font-family:Inter,sans-serif;">27 Peraturan</span>
  </div>
  <div class="tk-corpus-item uu">
    <div class="tk-corpus-label uu">Undang-Undang</div>
    <div class="tk-corpus-val">UU No. 13/2003 jo. UU No. 6/2023</div>
    <div class="tk-corpus-desc">Ketenagakerjaan &amp; Cipta Kerja</div>
  </div>
  <div class="tk-corpus-item pp">
    <div class="tk-corpus-label pp">Peraturan Pemerintah</div>
    <div class="tk-corpus-val">PP 35/2021 &amp; PP 36/2021</div>
    <div class="tk-corpus-desc">PKWT, Waktu Kerja, PHK &amp; Pengupahan</div>
  </div>
  <div class="tk-corpus-item permenaker">
    <div class="tk-corpus-label permenaker">Permenaker</div>
    <div class="tk-corpus-val">No. 6/2016 &amp; No. 5/2018</div>
    <div class="tk-corpus-desc">THR &amp; K3 Lingkungan Kerja</div>
  </div>
</div>"""


# ── State management ─────────────────────────────────────────────────────────
EXAMPLE_QUESTIONS = [
    "Berapa lama cuti melahirkan?",
    "Aturan PHK sepihak bagaimana?",
    "Berapa upah lembur per jam?",
    "Syarat pembentukan serikat pekerja?",
    "Hak cuti tahunan berapa hari?",
    "Batas usia minimum pekerja anak?",
    "Kewajiban BPJS pengusaha?",
]

if "query_val" not in st.session_state: st.session_state.query_val = ""
if "results"   not in st.session_state: st.session_state.results   = None
if "answer"    not in st.session_state: st.session_state.answer    = None
if "error"     not in st.session_state: st.session_state.error     = None
if "loading"   not in st.session_state: st.session_state.loading   = False
if "llm_warn"  not in st.session_state: st.session_state.llm_warn  = None


# ── Handle chip / example clicks via query params ────────────────────────────
qp = st.query_params.get("q", "")
if qp and qp != st.session_state.query_val:
    st.session_state.query_val = qp
    st.query_params.clear()


# ── HEADER ───────────────────────────────────────────────────────────────────
st.markdown("""
<div class="tk-header">
  <div class="tk-header-inner">
    <div class="tk-header-title-row">
      <span class="material-symbols-outlined tk-header-icon">balance</span>
      <h1 class="tk-app-title">Tanya Kerja</h1>
      <span class="tk-badge">27 Peraturan · UU · PP · Permenaker</span>
    </div>
    <p class="tk-header-subtitle">
      Tanya seputar hak dan kewajiban pekerja berdasarkan peraturan resmi Indonesia.
    </p>
    <div class="tk-divider"></div>
  </div>
</div>
""", unsafe_allow_html=True)


# ── MAIN BODY ────────────────────────────────────────────────────────────────
# Open layout grid
st.markdown('<div class="tk-layout"><div class="tk-main">', unsafe_allow_html=True)

# ── Input Card HTML frame ────────────────────────────────────────────────────
st.markdown(f"""
<div class="tk-input-card">
  <div class="tk-input-label-row">
    <span class="tk-input-label">Pertanyaan Anda</span>
    <span class="tk-status-dot">Korpus Terverifikasi Aktif</span>
  </div>
""", unsafe_allow_html=True)

# Streamlit textarea (native, for actual user input)
query = st.text_area(
    label="query",
    value=st.session_state.query_val,
    placeholder="Contoh: Berapa lama hak cuti melahirkan? atau Apa yang dimaksud dengan PHK sepihak?",
    height=96,
    key="query_textarea",
    label_visibility="collapsed",
)

# Example chips (mobile + inside card on desktop)
st.markdown(f"""
  <div class="tk-chips-row">
    <span class="tk-chips-label">Coba:</span>
    <a href="?q=Berapa+lama+cuti+melahirkan%3F" class="tk-chip">
      Cuti melahirkan <span class="material-symbols-outlined">north_east</span>
    </a>
    <a href="?q=Aturan+PHK+sepihak+bagaimana%3F" class="tk-chip">
      PHK sepihak <span class="material-symbols-outlined">north_east</span>
    </a>
    <a href="?q=Berapa+upah+lembur+per+jam%3F" class="tk-chip">
      Upah lembur <span class="material-symbols-outlined">north_east</span>
    </a>
  </div>
""", unsafe_allow_html=True)

# Button
tanya_clicked = st.button("🔍 Tanya Rujukan Hukum")

# Disclaimer
st.markdown("""
  <div class="tk-disclaimer">
    <span class="material-symbols-outlined">info</span>
    Jawaban didasarkan pada dokumen hukum resmi. Untuk keputusan penting,
    konsultasikan dengan advokat atau Dinas Ketenagakerjaan setempat.
  </div>
</div>
""", unsafe_allow_html=True)  # close tk-input-card


# ── Handle submit ─────────────────────────────────────────────────────────────
if tanya_clicked:
    q = query.strip()
    st.session_state.query_val = q

    if not q:
        st.markdown("""
        <div class="tk-validation">
          <span class="material-symbols-outlined">warning</span>
          Ketik pertanyaanmu sebelum melanjutkan.
        </div>""", unsafe_allow_html=True)
    elif len(q) < 5:
        st.markdown("""
        <div class="tk-validation">
          <span class="material-symbols-outlined">warning</span>
          Pertanyaan terlalu pendek. Mohon masukkan pertanyaan yang lebih lengkap.
        </div>""", unsafe_allow_html=True)
    elif len(q) > 500:
        st.markdown("""
        <div class="tk-validation">
          <span class="material-symbols-outlined">warning</span>
          Pertanyaan terlalu panjang (maks 500 karakter).
        </div>""", unsafe_allow_html=True)
    else:
        # Show skeleton loading
        st.markdown(_skeleton_html(), unsafe_allow_html=True)

        # Retrieve
        docs, err = _retrieve(q, k=5)
        if err:
            st.session_state.results = []
            st.session_state.error   = err
        else:
            st.session_state.results = docs
            # Generate
            if docs:
                answer, llm_err = _generate(q, docs)
                st.session_state.answer   = answer
                st.session_state.llm_warn = llm_err
            st.session_state.error = None
        st.rerun()


# ── Results display ────────────────────────────────────────────────────────────
if st.session_state.error:
    st.markdown(f"""
    <div class="tk-error-box">
      <span class="material-symbols-outlined">error</span>
      <div>
        <div class="tk-error-title">Gagal memuat indeks</div>
        <div class="tk-error-body">
          Jalankan terlebih dahulu:<br>
          <code>python scripts/embed_and_index.py</code><br>
          Detail: {st.session_state.error}
        </div>
      </div>
    </div>""", unsafe_allow_html=True)

elif st.session_state.results is not None:
    docs   = st.session_state.results
    answer = st.session_state.answer

    if not docs:
        st.markdown("""
        <div class="tk-error-box" style="background:#F0EDE8;border-color:var(--border-default);">
          <span class="material-symbols-outlined" style="color:var(--text-secondary);">search_off</span>
          <div>
            <div class="tk-error-title" style="color:var(--text-primary);">Tidak ditemukan pasal yang relevan</div>
            <div class="tk-error-body" style="color:var(--text-secondary);">
              Coba ubah kata kunci pertanyaanmu. Gunakan istilah lebih umum seperti
              "cuti", "PHK", atau "upah lembur".
            </div>
          </div>
        </div>""", unsafe_allow_html=True)
    else:
        # ── Jawaban section ──────────────────────────────────────────────────
        n = len(docs)
        st.markdown(f"""
        <div class="tk-answer-card">
          <div class="tk-section-header">
            <h2 class="tk-section-title">
              <span class="material-symbols-outlined">chat</span>
              Jawaban Sintesis
            </h2>
            <span class="tk-section-meta">
              <span class="material-symbols-outlined">assured_workload</span>
              Berdasarkan {n} pasal
            </span>
          </div>
        """, unsafe_allow_html=True)

        if st.session_state.llm_warn:
            st.markdown(f"""
            <div class="tk-validation" style="margin-bottom:16px;">
              <span class="material-symbols-outlined">warning</span>
              <span>Mode retrieval-only — LLM belum dikonfigurasi. Isi
              <code>.env</code> dengan API key. ({st.session_state.llm_warn})</span>
            </div>""", unsafe_allow_html=True)

        if answer:
            # Render LLM answer preserving paragraphs
            paragraphs = [p.strip() for p in answer.split("\n\n") if p.strip()]
            body = "".join(f"<p>{p}</p>" for p in paragraphs)
            st.markdown(f'<div class="tk-answer-body">{body}</div>', unsafe_allow_html=True)
        else:
            # Fallback: top chunk text
            import html
            teks_esc = html.escape(docs[0]["teks"])
            j = docs[0]["jenis"]; n0 = docs[0]["nomor"]; t = docs[0]["tahun"]; p = docs[0]["pasal"]
            st.markdown(f"""
            <div class="tk-answer-body">
              <p><strong>{j} No. {n0} Tahun {t}, Pasal {p}</strong></p>
              <p>{teks_esc}</p>
            </div>""", unsafe_allow_html=True)

        st.markdown("""
          <div class="tk-feedback-row">
            <span class="tk-feedback-label">Apakah jawaban ini membantu?</span>
            <div class="tk-feedback-btns">
              <button class="tk-feedback-btn">
                <span class="material-symbols-outlined">thumb_up</span> Ya
              </button>
              <button class="tk-feedback-btn" style="--hover-border:var(--status-error);">
                <span class="material-symbols-outlined">thumb_down</span> Kurang
              </button>
            </div>
          </div>
        </div>""", unsafe_allow_html=True)  # close tk-answer-card

        # ── Sources section ──────────────────────────────────────────────────
        st.markdown(f"""
        <div class="tk-section-header" style="margin-top:0;">
          <h3 class="tk-section-title" style="font-size:18px;">
            <span class="material-symbols-outlined" style="font-size:20px;">auto_stories</span>
            Sumber &amp; Referensi Statuta
          </h3>
          <span class="tk-section-meta">{len(docs)} pasal paling relevan</span>
        </div>
        <div class="tk-sources-stack">
        """, unsafe_allow_html=True)

        for i, doc in enumerate(docs):
            st.markdown(_source_card_html(doc, expanded=(i == 0)), unsafe_allow_html=True)

        st.markdown("</div>", unsafe_allow_html=True)  # close tk-sources-stack


# ── Close main, open sidebar ──────────────────────────────────────────────────
st.markdown(f"""
</div>
<div class="tk-sidebar">
  {_sidebar_html(EXAMPLE_QUESTIONS)}
</div>
</div>
""", unsafe_allow_html=True)  # close tk-main, tk-sidebar, tk-layout


# ── FOOTER ────────────────────────────────────────────────────────────────────
st.markdown("""
<div class="tk-footer">
  <div class="tk-footer-divider"></div>
  <p>
    Tanya Kerja · Data bersumber dari
    <span class="accent">peraturan.go.id</span>,
    <span class="accent">jdih.kemnaker.go.id</span>,
    dan <span class="accent">peraturan.bpk.go.id</span>
  </p>
  <p class="small">
    Sintesis informasi hukum perburuhan ini bersifat edukatif dan penelaahan rujukan awal,
    bukan pengganti nasihat advokat resmi atau penetapan lembaga peradilan ketenagakerjaan.
  </p>
</div>
""", unsafe_allow_html=True)
