import argparse
import datetime
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TEXT_DIR = ROOT / "data" / "teks"
CONFIG_FILE = ROOT / "config" / "docs_config.json"
OUT_FILE = ROOT / "data" / "chunks.json"
REPORT_FILE = ROOT / "data" / "reports" / "chunk_report.json"

MAX_LEN = 1500
OVERLAP_SENT = 2

PAGE_SEP = re.compile(r"^=== HALAMAN (\d+) ===$")
# Marker pasal toleran terhadap artefak OCR/properti teks hasil ekstraksi:
#   "Pasal 7" (normal), "Pasal7" (spasi hilang), "Pasa17" (l dibaca 1 oleh OCR).
PASAL_RE = re.compile(r"^Pas(?:al|a1)\s?(\d+[A-Za-z]?)\b")
BAB_RE = re.compile(r"^BAB\s+([IVXLC]+)\b")
BAGIAN_RE = re.compile(r"^Bagian\s+(\S+)")
AYAT_RE = re.compile(r"^\s*\(\s*(\d+[a-zA-Z]?)\s*\)", re.M)
SENT_RE = re.compile(r"(?<=[.\n;])\s+")
MIN_CHUNK = 15
JUNK_CHARS = re.compile(r"[\ufffd\u2766\u25aa\u25cf\u25e6]")


def split_pages(text):
    pages = {}
    cur = None
    buf = []
    for ln in text.splitlines():
        m = PAGE_SEP.match(ln.strip())
        if m:
            if cur is not None:
                pages[cur] = buf
            cur = int(m.group(1))
            buf = []
        else:
            buf.append(ln)
    if cur is not None:
        pages[cur] = buf
    return pages


def sentences(text):
    return [s for s in SENT_RE.split(text) if s.strip()]


def overlap_tail(text, n=OVERLAP_SENT):
    parts = sentences(text)
    if len(parts) <= n:
        return ""
    return " ".join(parts[-n:])


def chunk_long(text, min_len=550):
    groups = re.split(r"(?=^\s*\(\d+)", text, flags=re.M)
    if len(groups) < 2:
        groups = sentences(text)
    parts = [g.strip() for g in groups if g.strip()]
    result = []
    for p in parts:
        if not result:
            result.append(p)
        elif len(result[-1]) + 1 + len(p) <= MAX_LEN:
            result[-1] += "\n" + p
        else:
            ov = overlap_tail(result[-1])
            result.append((ov + "\n" + p) if ov else p)

    capped = []
    for r in result:
        if len(r) <= MAX_LEN:
            capped.append(r)
            continue
        lines = r.splitlines()
        if len(lines) > 1:
            capped.extend(chunk_by_len(lines))
        else:
            capped.extend(hard_split(r))
    return capped


def chunk_by_len(lines):
    """Gabungkan baris-baris ke <= MAX_LEN dengan overlap."""
    groups = []
    cur = ""
    for s in lines:
        s = s.strip()
        if not s:
            continue
        if not cur:
            cur = s
        elif len(cur) + 1 + len(s) <= MAX_LEN:
            cur += "\n" + s
        else:
            groups.append(cur)
            ov = overlap_tail(cur)
            cur = (ov + "\n" + s) if ov else s
    if cur:
        groups.append(cur)
    out = []
    for g in groups:
        if len(g) > MAX_LEN:
            out.extend(hard_split(g))
        else:
            out.append(g)
    return out


def hard_split(text):
    """Potong satu baris sangat panjang pada batas kata/spasi terdekat."""
    out = []
    while len(text) > MAX_LEN:
        window = text[: MAX_LEN + 1]
        cut = window.rfind(" ")
        if cut < MAX_LEN // 2:
            cut = MAX_LEN
        piece = text[:cut].strip()
        if piece:
            out.append(piece)
        ov = overlap_tail(piece)
        tail = text[cut:].strip()
        text = (ov + "\n" + tail) if ov else tail
    if text.strip():
        out.append(text.strip())
    return out


def normalize_teks(s):
    s = JUNK_CHARS.sub("", s)
    s = re.sub(r"[ \t]{2,}", " ", s)
    s = re.sub(r"[ \t]*\n[ \t]*", "\n", s)
    s = re.sub(r"\n{3,}", "\n\n", s)
    return s.strip()


def parse_bab(ln):
    m = BAB_RE.match(ln)
    return m.group(1) if m else None


def parse_bagian(ln):
    m = BAGIAN_RE.match(ln)
    return m.group(1) if m else None


def detach_digits(num_str):
    m = re.match(r"(\d+)", num_str)
    return int(m.group(1)) if m else None


def find_line(lines, pred):
    for i, ln in enumerate(lines):
        if pred(ln.strip()):
            return i
    return None


def page_of_line(ln):
    m = PAGE_SEP.match(ln.strip())
    return int(m.group(1)) if m else None


def process_doc(doc):
    doc_id = doc["id"]
    raw = (TEXT_DIR / f"{doc_id}.clean.txt").read_text(encoding="utf-8")
    pages = split_pages(raw)

    pg_range = doc.get("page_range")
    if pg_range:
        lo, hi = pg_range
        lines = []
        for pno in sorted(pages):
            if lo <= pno <= hi:
                lines.append("=== HALAMAN %d ===" % pno)
                lines.extend(pages[pno])
    else:
        lines = raw.splitlines()

    start = find_line(lines, lambda s: s.upper().startswith("MEMUTUSKAN"))
    body_start = start + 1 if start is not None else 0
    # Kalimat penutup selalu diawali "Agar" ("Agar setiap orang mengetahuinya...");
    # wajib kapital agar tidak tertabrak kalimat isi berawalan "agar" (huruf kecil).
    sig = find_line(lines, lambda s: s.startswith(("AGAR", "Agar")))
    body_end = sig if sig is not None else len(lines)

    body = lines[body_start:body_end]
    tail = lines[body_end:] if sig is not None else []

    penjelasan_lines = []
    pj = find_line(tail, lambda s: s.upper().startswith("PENJELASAN"))
    if pj is not None:
        j = pj + 1
        p = 1
        while j < len(tail):
            s = tail[j].strip()
            pg = page_of_line(s)
            if pg is not None:
                p = pg
            elif s.upper().startswith("LAMPIRAN"):
                break
            elif s:
                penjelasan_lines.append((tail[j], p))
            j += 1

    segments = []
    cur = None
    curpg = 1
    bab = None
    judul_bab = ""
    bagian = None
    n = len(body)
    i = 0
    while i < n:
        ln = body[i].strip()
        i += 1
        if not ln:
            continue
        pg = page_of_line(ln)
        if pg is not None:
            curpg = pg
            if cur is not None:
                cur["pages"].append(pg)
            continue
        b = parse_bab(ln)
        if b:
            bab = b
            rest = []
            for j in range(i, n):
                t = body[j].strip()
                if not t or page_of_line(t) is not None or PASAL_RE.match(t) or BAB_RE.match(t) or BAGIAN_RE.match(t):
                    break
                rest.append(t)
            judul_bab = " ".join(rest)[:120]
            if cur:
                segments.append(cur)
                cur = None
            continue
        g = parse_bagian(ln)
        if g:
            bagian = g
            continue
        m = PASAL_RE.match(ln)
        if m:
            allowed = doc.get("pasal_markers")
            if allowed is None or m.group(1) in allowed:
                if cur:
                    segments.append(cur)
                cur = {
                    "num": m.group(1),
                    "lines": [ln],
                    "bab": bab,
                    "judul_bab": judul_bab,
                    "bagian": bagian,
                    "pages": [curpg],
                }
                continue
        if cur is not None:
            cur["lines"].append(ln)
    if cur:
        segments.append(cur)

    out = []
    seq = 0
    include_pasal = doc.get("include_pasal")
    for seg in segments:
        num = seg["num"]
        if include_pasal is not None:
            base = detach_digits(num)
            if base not in include_pasal:
                continue
        text = "\n".join(seg["lines"]).strip()
        if not text:
            continue
        body_only = re.sub(r"^Pasal\s+\d+[A-Za-z]?[.\s]*\n?", "", text, count=1, flags=re.M)
        if not body_only.strip():
            continue
        pages_l = sorted(set(seg["pages"]))
        deft = {
            "source": doc["source"],
            "peraturan": doc["peraturan"],
            "jenis": doc["jenis"],
            "nomor": doc["nomor"],
            "tahun": doc["tahun"],
            "tipe": "pasal",
            "bab": seg["bab"],
            "judul_bab": seg["judul_bab"],
            "pasal": num,
            "ayat": "",
            "ayat_pasal": ",".join(AYAT_RE.findall(text)),
            "poin": "",
            "halaman": pages_l,
            "kronologi": doc.get("kronologi", ""),
        }
        if re.search(r"(?m)^\d+\.\s", text) and len(seg["lines"]) > 3:
            raw_items = re.split(r"(?=^\d+\.\s)", text, flags=re.M)
            item_mode = any(len(x) > 150 for x in raw_items[1:])
        else:
            raw_items = [text]
            item_mode = False

        def emit(text_unit, poin=""):
            nonlocal seq
            subs = chunk_long(text_unit) if len(text_unit) > MAX_LEN else [text_unit]
            for part in subs:
                t = normalize_teks(part)
                if len(t) < MIN_CHUNK:
                    continue
                seq += 1
                chunk = dict(deft)
                chunk["id"] = f"{doc_id}_{seq:04d}"
                chunk["ayat"] = ",".join(a for a in AYAT_RE.findall(t))
                chunk["poin"] = poin
                chunk["teks"] = t
                out.append(chunk)

        if item_mode:
            groups = []
            cur_it = ""
            cur_poin = ""
            for item in raw_items:
                it = item.strip()
                if not it:
                    continue
                poin_m = re.match(r"^(\d+)\.", it)
                poin = poin_m.group(1) if poin_m else ""
                if not cur_it:
                    cur_it = it
                    cur_poin = poin
                elif len(cur_it) + 1 + len(it) <= MAX_LEN:
                    cur_it += "\n" + it
                else:
                    groups.append((cur_it, cur_poin))
                    ov = overlap_tail(cur_it)
                    cur_it = (ov + "\n" + it) if ov else it
                    cur_poin = poin
            if cur_it:
                groups.append((cur_it, cur_poin))
            for t, p in groups:
                subs = chunk_long(t) if len(t) > MAX_LEN else [t]
                for part in subs:
                    emit(part, p)
        else:
            emit("\n".join(seg["lines"]).strip())

    if penjelasan_lines and not pg_range:
        for ref, text, epages in parse_penjelasan(penjelasan_lines):
            t = normalize_teks(text)
            if len(t) < MIN_CHUNK:
                continue
            seq += 1
            out.append({
                "id": f"{doc_id}_{seq:04d}",
                "source": doc["source"],
                "peraturan": doc["peraturan"],
                "jenis": doc["jenis"],
                "nomor": doc["nomor"],
                "tahun": doc["tahun"],
                "tipe": "penjelasan",
                "bab": "",
                "judul_bab": "",
                "pasal": ref,
                "ayat": "",
                "ayat_pasal": "",
                "poin": "",
                "halaman": sorted(epages),
                "kronologi": doc.get("kronologi", ""),
                "teks": t,
            })
    return out


def compact_penjelasan(chunks):
    """Gabungkan rangkaian 'Pasal N ... Cukup jelas' menjadi satu blok."""
    out = []
    i = 0
    n = len(chunks)
    while i < n:
        ref, text, pages = chunks[i]
        if is_cukup(text):
            j = i + 1
            while j < n and is_cukup(chunks[j][1]):
                j += 1
            run = chunks[i:j]
            refs = [r for r, _, _ in run]
            uniq = set()
            for _, _, pgs in run:
                uniq |= set(pgs)
            first = refs[0]
            last = refs[-1]
            label = f"Pasal {first} sampai dengan Pasal {last}" if first != last else f"Pasal {first}"
            out.append((first, f"{label}: {run[0][1]}", uniq))
            i = j
        else:
            out.append(chunks[i])
            i += 1
    return out


def is_cukup(text):
    lines = [re.sub(r"^Pasal\s+\d+[A-Za-z]?\s*", "", l) for l in text.splitlines()]
    body = " ".join(lines).replace("\u201c", "").replace("\u201d", "").strip().lower()
    body = re.sub(r"[^a-z ]", "", body)
    return body.replace(" ", "").startswith("cukupjelas")


def parse_penjelasan(lines):
    chunks = []
    cur_ref = None
    cur_lines = []
    cur_pages = set()

    def flush():
        nonlocal cur_ref, cur_lines, cur_pages
        if cur_ref is None:
            return
        text = "\n".join(cur_lines).strip()
        if text:
            if len(text) > MAX_LEN:
                for part in chunk_long(text):
                    chunks.append((cur_ref, part, cur_pages))
            else:
                chunks.append((cur_ref, text, cur_pages))
        cur_ref = None
        cur_lines = []
        cur_pages = set()

    for ln, p in lines:
        s = ln.strip()
        if not s:
            continue
        m = PASAL_RE.match(s)
        ang = re.match(r"^Angka\s+(\d+)\s+Pasal\s+(\d+[A-Za-z]?)\b", s)
        if m and s.upper().startswith(("PASAL", "PASA1")):
            flush()
            cur_ref = m.group(1)
            cur_lines = [ln]
            cur_pages = {p} if p else set()
        elif ang and s.upper().startswith("ANGKA"):
            flush()
            cur_ref = ang.group(2)
            cur_lines = [ln]
            cur_pages = {p} if p else set()
        elif cur_ref is not None:
            cur_lines.append(ln)
            if p:
                cur_pages.add(p)
    flush()
    return compact_penjelasan(chunks)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--batch", default=None, help="hanya batch A/B/C")
    args = ap.parse_args()

    cfg = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
    docs = cfg["documents"]
    if args.batch:
        docs = [d for d in docs if d.get("batch") == args.batch]

    processed = {d["id"] for d in docs}
    existing = []
    if OUT_FILE.exists():
        existing = json.loads(OUT_FILE.read_text(encoding="utf-8"))["chunks"]
    merged = [c for c in existing if c["id"].rsplit("_", 1)[0] not in processed]

    report = {}
    for doc in docs:
        ch = process_doc(doc)
        merged.extend(ch)
        report[doc["id"]] = len(ch)
        print(f"{doc['id']:<18} -> {len(ch):4d} chunks")

    merged.sort(key=lambda c: c["id"])
    from collections import Counter
    by_source = Counter(c["source"] for c in merged)
    per_source = {d["id"]: by_source.get(d["source"], 0) for d in cfg["documents"]}
    OUT_FILE.parent.mkdir(exist_ok=True)
    meta = {
        "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
        "total_chunks": len(merged),
        "max_len": MAX_LEN,
        "overlap_sentences": OVERLAP_SENT,
        "schema": "data/README.md",
    }
    OUT_FILE.write_text(
        json.dumps({"meta": meta, "chunks": merged}, ensure_ascii=False, indent=1),
        encoding="utf-8",
    )
    REPORT_FILE.write_text(
        json.dumps({"total": len(merged), "per_source": per_source},
                   ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"\nTOTAL: {len(merged)} chunks -> {OUT_FILE}")
    print(json.dumps(report, indent=1))


if __name__ == "__main__":
    main()