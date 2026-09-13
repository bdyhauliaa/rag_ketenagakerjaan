"""Validasi hasil pipeline preprocessing — dijalankan setiap regenerasi.

Memeriksa:
  1. Setiap dokumen di docs_config.json punya PDF + teks bersih + chunk.
  2. Total & jumlah chunk per dokumen konsisten dengan chunk_report.json.
  3. Tidak ada noise ekstraksi yang bocor ke chunk (header "PRESIDEN/REPUBLIK",
     footer JDIH/BSrE/BNRI, "Ttd.", "www.peraturan.go.id", "20XX, No.XX").
  4. Tidak ada karakter sampah (\\ufffd, simbol list) di teks chunk.
  5. Panjang chunk dalam batas MAX_LEN dan tidak di bawah MIN.
  6. Tidak ada duplikat id chunk.
  7. Semua chunk punya metadata halaman.
  8. Cakupan pasal: setiap pasal pada teks (sesuai include_pasal) ter-wakili chunk.
"""

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = Path(__file__).resolve().parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))
from chunk_documents import process_doc

NOISE_PATTERNS = [
    re.compile(r"^\s*PRESIDEN\s*$", re.M),
    re.compile(r"^\s*REPUBLIK\s*$", re.M),
    re.compile(r"^\s*INDONESIA\s*$", re.M),
    re.compile(r"^\s*REPUBLIK\s+INDONESIA\s*$", re.M),
    re.compile(r"jdih\.kemnaker\.go\.id", re.I),
    re.compile(r"Ditandatangani secara elektronik", re.I),
    re.compile(r"Balai Sertifikasi Elektronik", re.I),
    re.compile(r"www\.peraturan\.go\.id", re.I),
    re.compile(r"^\s*20\d{2},\s*No\.\s*(\d+|…)\s*$", re.M),
    re.compile(r"^\s*(Ttd|ttd)\.?\s*$", re.M),
]
JUNK_RE = re.compile(r"[\ufffd\u25aa\u25cf\u25e6\u2766\uf0b7\u20ac]")
# Sinkron dengan chunk_documents: toleran marker dempet ("Pasal7") & OCR "Pasa17".
PASAL_RE = re.compile(r"^Pas(?:al|a1)\s?(\d+[A-Za-z]?)\b")

FAILS = []
WARNS = []


def fail(msg):
    FAILS.append(msg)


def warn(msg):
    WARNS.append(msg)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--quiet", action="store_true", help="hanya cetak ringkasan")
    args = ap.parse_args()

    cfg = json.loads((ROOT / "scripts" / "docs_config.json").read_text(encoding="utf-8"))
    docs = cfg["documents"]
    chunks = json.loads((ROOT / "data" / "chunks.json").read_text(encoding="utf-8"))["chunks"]
    report = json.loads((ROOT / "scripts" / "chunk_report.json").read_text(encoding="utf-8")) if (ROOT / "scripts" / "chunk_report.json").exists() else {}

    per_source = {}
    for c in chunks:
        per_source.setdefault(c["source"], []).append(c)

    # 1. Kelengkapan artefak
    # PDF sengaja di-gitignore, jadi "PDF hilang" hanya fatal bila artefak
    # turunannya (teks/chunk) juga hilang; kalau PDF kurang tapi turunan
    # lengkap & sinkron, cukup catatan (mis. clone baru tanpa data/pdf).
    for d in docs:
        pdf = ROOT / "data" / "pdf" / d["source"]
        teks = ROOT / "data" / "teks" / f"{d['id']}.clean.txt"
        n = len(per_source.get(d["source"], []))
        if not pdf.exists():
            if not teks.exists() or n == 0:
                fail(f"[1] PDF hilang: {d['source']}")
            else:
                warn(f"[1] PDF tidak ada (turunan lengkap): {d['source']}")
        if not teks.exists():
            fail(f"[1] teks hilang: {d['id']}.clean.txt")
        if n == 0:
            fail(f"[1] tidak ada chunk untuk {d['id']}")

    # 2. Konsistensi count dengan chunk_report.json
    if report:
        if report.get("total") != len(chunks):
            fail(f"[2] chunk_report.total ({report.get('total')}) != chunks.json ({len(chunks)})")
        for d in docs:
            exp = report.get("per_source", {}).get(d["id"])
            act = len(per_source.get(d["source"], []))
            if exp is not None and exp != act:
                fail(f"[2] {d['id']}: report {exp} vs aktual {act}")

    # 3-5. Kualitas per chunk
    seen = {}
    for c in chunks:
        teks = c.get("teks", "")
        if c["id"] in seen:
            fail(f"[6] duplikat id: {c['id']}")
        seen[c["id"]] = True
        if not c.get("halaman"):
            fail(f"[7] chunk tanpa halaman: {c['id']}")
        if len(teks) > 1500:
            fail(f"[5] chunk {c['id']} melebihi 1500 char ({len(teks)})")
        if len(teks) < 15:
            fail(f"[5] chunk {c['id']} terlalu pendek ({len(teks)})")
        for pat in NOISE_PATTERNS:
            if pat.search(teks):
                fail(f"[3] noise di {c['id']}: {pat.pattern[:40]}")
        if JUNK_RE.search(teks):
            fail(f"[4] junk char di {c['id']}")

    # 8. Cakupan pasal
    for d in docs:
        teks_path = ROOT / "data" / "teks" / f"{d['id']}.clean.txt"
        if not teks_path.exists():
            continue
        raw = teks_path.read_text(encoding="utf-8")
        lines = raw.splitlines()
        body = lines
        for i, ln in enumerate(lines):
            if ln.startswith(("AGAR", "Agar")):
                body = lines[:i]
                break
        teks_pasal = {m.group(1) for ln in body for m in [PASAL_RE.match(ln)] if m}
        markers = set(d.get("pasal_markers") or [])
        include = set(d.get("include_pasal") or [])
        covered = {c["pasal"] for c in per_source.get(d["source"], []) if c.get("tipe") == "pasal"}
        if markers:
            wanted = {str(x) for x in markers}
        elif include:
            wanted = {p for p in teks_pasal if int(re.match(r"\d+", p).group()) in {int(x) for x in include}}
        else:
            max_cov = max((int(re.match(r"\d+", p).group()) for p in covered), default=0)
            wanted = {p for p in teks_pasal if int(re.match(r"\d+", p).group()) <= max_cov + 1}
        miss = sorted(wanted - covered, key=lambda x: int(re.match(r"\d+", x).group()))
        if miss:
            fail(f"[8] {d['id']}: pasal tanpa chunk: {', '.join(miss[:20])}")

    # 9. Reproduksibilitas: chunk di chunks.json harus identik dengan hasil
    #    regenerasi langsung dari data/teks (menjamin tidak ada isi hukum yang
    #    terpotong/terlewat pada pasal yang dipecah, karena teks utuh dijamin
    #    tersambung oleh chunk_documents).
    for d in docs:
        teks_path = ROOT / "data" / "teks" / f"{d['id']}.clean.txt"
        if not teks_path.exists():
            continue
        try:
            fresh = process_doc(d)
        except Exception as e:
            fail(f"[9] {d['id']}: gagal regenerasi ({e.__class__.__name__})")
            continue
        actual = per_source.get(d["source"], [])
        if len(fresh) != len(actual):
            fail(f"[9] {d['id']}: tidak sinkron ({len(fresh)} baru vs {len(actual)} tersimpan)")
            continue
        for fc, ac in zip(fresh, actual):
            if fc["id"] != ac["id"] or fc["teks"] != ac["teks"]:
                fail(f"[9] {d['id']}: chunk '{fc['id']}' tidak sinkron dgn data/teks")
                break

    # 10. Kontinuitas pasal ter-split (soft): chunk berikut 'seharusnya' dibuka
    #     dengan overlap tail (2 kalimat) chunk sebelumnya. Karena chunk pendek
    #     sah tanpa overlap, cek ini non-fatal dan hanya untuk telaah manual.
    groups = {}
    for c in chunks:
        if c.get("tipe") == "pasal" and c.get("teks"):
            groups.setdefault((c["source"], c["pasal"]), []).append(c)
    n_no_overlap = 0
    for key, cs in groups.items():
        cs.sort(key=lambda c: c["id"])
        for i in range(1, len(cs)):
            prev, cur = cs[i - 1], cs[i]
            if len(prev["teks"]) < 1000:
                continue
            tail = re.sub(r"\s+", " ", prev["teks"])[-200:]
            head = re.sub(r"\s+", " ", cur["teks"])[:500]
            if tail and tail not in head:
                n_no_overlap += 1
                if n_no_overlap <= 10:
                    warn(f"[10] kontinuitas tak terverifikasi: {prev['id']} -> {cur['id']}")
    if n_no_overlap > 10:
        warn(f"[10] ... dan {n_no_overlap - 10} pasang lainnya tanpa overlap terverifikasi")

    ok = not FAILS
    if args.quiet:
        print("VALID" if ok else f"INVALID ({len(FAILS)} masalah)")
        if WARNS:
            print(f"CATATAN SOFT: {len(WARNS)}")
    else:
        print("=" * 60)
        print("VALIDASI PIPELINE")
        print("=" * 60)
        print(f"dokumen di config : {len(docs)}")
        print(f"total chunk       : {len(chunks)}")
        if WARNS:
            print(f"\n{len(WARNS)} CATATAN SOFT (tidak fatal, untuk telaah):")
            for w in WARNS[:30]:
                print("  -", w)
            if len(WARNS) > 30:
                print(f"  ... dan {len(WARNS) - 30} catatan lainnya")
        if FAILS:
            print(f"\n{len(FAILS)} MASALAH DITEMUKAN:")
            for m in FAILS:
                print("  -", m)
            sys.exit(1)
        print("Semua cek LULUS.")
    return ok


if __name__ == "__main__":
    main()