import argparse
import json
import re
from pathlib import Path

import pdfplumber

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "config" / "docs_config.json"
PDF_DIR = ROOT / "data" / "pdf"
TEKS_DIR = ROOT / "data" / "teks"
REPORT_FILE = ROOT / "data" / "reports" / "extract_report.json"

PAGE_SEP = "\n\n=== HALAMAN {n} ===\n\n"


def clean_page(text, page_no):
    if not text:
        return ""
    text = text.replace("\u2010", "-").replace("\u2011", "-")
    text = text.replace("\ufffd", " ")
    text = text.replace("\uf0b7", " ").replace("\u20ac", " ")
    lines = text.splitlines()

    out = []
    prev_blank = True
    for ln in lines:
        s = ln.strip()
        if not s:
            prev_blank = True
            continue
        if re.fullmatch(r"[-–—\s]+", s):
            continue
        if re.fullmatch(r"\d{1,4}\s*(/\s*)*\d{0,4}", s):
            continue
        if len(s) <= 4 and s.isdigit():
            continue
        if re.fullmatch(r"-?\s*\d+\s*-?", s) and len(s) <= 6:
            continue
        if s.lower() in _running_headers():
            continue
        if _FOOT.match(s):
            continue
        if _is_heading_noise(s):
            continue
        pm = re.match(r"^Pas(?:al|a1)(\d)", s)
        if pm:
            s = "Pasal " + pm.group(1)
        out.append(s)

    # join hyphen-broken line pairs
    joined = []
    i = 0
    while i < len(out):
        line = out[i]
        if (
            i + 1 < len(out)
            and line.endswith("-")
            and out[i + 1][:1].islower()
            and not line.endswith(("--", " - "))
        ):
            joined.append(line[:-1] + out[i + 1])
            i += 2
            continue
        joined.append(line)
        i += 1
    return "\n".join(joined)


_RUNNING = None

_FOOT = re.compile(
    r"^(SK\s*No\s*[A-Za-z0-9.\s]+"
    r"|DIREKTUR\s*$"
    r"|JDIH\s+.*\bKETENAGAKERJAAN\b.*"
    r"|KEMENTERIAN\s*KETENAGAKERJAAN\s*$"
    r"|jdih\.kemnaker\.go\.id\s*$"
    r"|www\.peraturan\.go\.id\s*$"
    r"|20\d{2},\s*No\.\s*\d+\s*$"
    r"|Dokumen ini telah ditandatangani.*"
    r"|ttd\.?\s*$)",
    re.I,
)

# Baris header lari ("PRESIDEN REPUBLIK INDONESIA") yang dalam hasil scan
# terpecah per baris atau rusak oleh OCR (`REPUEL|K`, `REPTTEL|K`, dll).
_NORM_RE = re.compile(r"[^a-z0-9]")
_RUNNING_MAX_LEN = 40


def _running_headers():
    global _RUNNING
    if _RUNNING is None:
        _RUNNING = {
            "menimbang", "mengingat", "memutuskan", "menetapkan",
            "dengan rahmat tuhan yang maha esa",
            "menteri ketenagakerjaan republik indonesia",
        }
    return _RUNNING


def _is_heading_noise(s):
    if not s or len(s) > _RUNNING_MAX_LEN:
        return False
    norm = _NORM_RE.sub("", s.lower())
    if not norm:
        return False
    if norm == "presiden":
        return True
    if norm.startswith("presidenrepublik") and "ndonesia" in norm:
        return True
    if norm.startswith("repu") and "ndonesia" in norm and len(norm) >= 12:
        return True
    return False


def extract_pdf(path, source):
    pages_text = []
    with pdfplumber.open(str(path)) as pdf:
        for n, page in enumerate(pdf.pages, 1):
            txt = page.extract_text() or ""
            pages_text.append(clean_page(txt, n))
    chunks = []
    for n, body in enumerate(pages_text, 1):
        if n > 1:
            chunks.append(PAGE_SEP.format(n=n))
        chunks.append(body)
    return "".join(chunks)


def main():
    ap = argparse.ArgumentParser(description="Ekstraksi teks pdfplumber + cleaning")
    ap.add_argument("--ids", default=None, help="hanya id dipisah koma, mis. uu_4_2024,pp_49_2025")
    ap.add_argument("--batch", default=None, help="hanya batch A/B/C")
    args = ap.parse_args()

    cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
    docs = cfg["documents"]
    if args.batch:
        docs = [d for d in docs if d.get("batch") == args.batch]
    if args.ids:
        wanted = set(x.strip() for x in args.ids.split(",") if x.strip())
        docs = [d for d in docs if d["id"] in wanted]

    TEKS_DIR.mkdir(parents=True, exist_ok=True)

    old = {}
    if REPORT_FILE.exists():
        for r in json.loads(REPORT_FILE.read_text(encoding="utf-8")):
            old[r["id"]] = r

    stat = []
    for doc in docs:
        src = doc["source"]
        pdf_path = PDF_DIR / src
        if not pdf_path.exists():
            print("SKIP (no pdf)", src)
            continue
        body = extract_pdf(pdf_path, src)
        dst = TEKS_DIR / f"{Path(src).stem}.clean.txt"
        dst.write_text(body, encoding="utf-8")
        nchars = len(body)
        print(f"{doc['id']:20} -> {dst.name}  ({nchars:,} chars)")
        stat.append({"id": doc["id"], "source": src, "teks": dst.name, "chars": nchars})

    for doc in cfg["documents"]:
        if doc["id"] in old and doc["id"] not in {r["id"] for r in stat}:
            stat.append(old[doc["id"]])
            print(f"{doc['id']:20} -> (dipertahankan dari report lama)")

    REPORT_FILE.write_text(
        json.dumps(stat, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print("\nDONE")


if __name__ == "__main__":
    main()