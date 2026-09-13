import json
import os
import sys
import threading
from pathlib import Path

import requests

BASE = Path(r"F:\Semester 5\Pemrosesan Bahasa Alami\TUGAS\Tugas 1")
CONFIG = BASE / "scripts" / "docs_config.json"
PDF_DIR = BASE / "data" / "pdf"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
    "Accept": "application/pdf,application/octet-stream,*/*",
}

try:
    import pdfplumber
except ImportError:
    pdfplumber = None


def is_pdf_content(data):
    return data[:5] == b"%PDF-"


def verify_pdf(path):
    if not path.exists() or path.stat().st_size == 0:
        return False
    with open(path, "rb") as f:
        head = f.read(5)
        return is_pdf_content(head)


def download_url(doc_id, url, dest):
    try:
        r = requests.get(url, headers=HEADERS, timeout=120, stream=True, allow_redirects=True)
        ctype = r.headers.get("content-type", "")
        if r.status_code != 200:
            return f"HTTP {r.status_code}"
        if ctype and not (ctype.startswith("application/pdf") or "octet-stream" in ctype):
            if "text/html" in ctype:
                return f"HTML instead of PDF ({ctype})"
            if "json" in ctype:
                return f"JSON instead of PDF ({ctype})"
        total = 0
        tmp = dest.with_suffix(".part")
        with open(tmp, "wb") as f:
            for chunk in r.iter_content(chunk_size=1 << 16):
                if chunk:
                    f.write(chunk)
                    total += len(chunk)
        r.close()
        if not is_pdf_content(tmp.read_bytes()):
            tmp.unlink(missing_ok=True)
            return "Not a PDF file"
        if pdfplumber is not None:
            try:
                with pdfplumber.open(str(tmp)) as pdf:
                    n = len(pdf.pages)
            except Exception:
                tmp.unlink(missing_ok=True)
                return "Unreadable/corrupt PDF"
        else:
            n = "?"
        tmp.replace(dest)
        return f"OK ({total} bytes, {n} pages)"
    except requests.exceptions.RequestException as e:
        return f"REQ ERROR {e.__class__.__name__}"
    except Exception as e:
        return f"ERROR {e.__class__.__name__}"


def main():
    cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
    docs = cfg["documents"]
    PDF_DIR.mkdir(parents=True, exist_ok=True)

    report = []
    lock = threading.Lock()

    def work(doc):
        meta = {
            "id": doc["id"],
            "source": doc["source"],
            "peraturan": doc["peraturan"],
            "status": "FAILED",
            "detail": "",
            "url": "",
            "skip": False,
        }
        dest = PDF_DIR / doc["source"]
        if verify_pdf(dest):
            meta["status"] = "EXISTS"
            meta["detail"] = "already downloaded"
            meta["skip"] = True
        for url in doc["urls"]:
            if meta["skip"]:
                break
            res = download_url(doc["id"], url, dest)
            meta["url"] = url
            if res.startswith("OK"):
                meta["status"] = "OK"
                meta["detail"] = res
                break
            meta["detail"] = res
        with lock:
            report.append(meta)
            label = meta["status"]
            print(f"[{label:7}] {doc['id']:20} {meta['detail'][:80]}")

    # sequential to be gentle on servers (parallel risks 429)
    for doc in docs:
        work(doc)

    out = BASE / "scripts" / "download_report.json"
    out.write_text(
        json.dumps({"report": report}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    ok = sum(1 for r in report if r["status"] in ("OK", "EXISTS"))
    failed = [r for r in report if r["status"] not in ("OK", "EXISTS")]
    print(f"\nTOTAL OK: {ok}/{len(docs)}")
    print("FAILED:", [r["id"] for r in failed] or "none")


if __name__ == "__main__":
    main()