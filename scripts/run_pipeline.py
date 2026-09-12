"""Orkestrator pipeline preprocessing — jalankan semua tahap dengan satu perintah.

Contoh:
  python scripts/run_pipeline.py             # semua tahap (download -> extract -> chunk -> validate)
  python scripts/run_pipeline.py --stage extract   # hanya tahap tertentu
  python scripts/run_pipeline.py --stage download --skip-if-exists

Setiap tahap dipanggil sebagai subproses terpisah; pipeline berhenti jika
suatu tahap gagal.
"""

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"
PY = sys.executable

STAGES = ["download", "extract", "chunk", "validate"]


def run_stage(name, extra=None):
    script = SCRIPTS / {
        "download": "download_documents.py",
        "extract": "extract_and_clean.py",
        "chunk": "chunk_documents.py",
        "validate": "validate_pipeline.py",
    }[name]
    cmd = [PY, str(script)]
    if extra:
        cmd.extend(extra)
    print("\n=== [%s/%s] %s ===" % (STAGES.index(name) + 1, len(STAGES), name.upper()))
    print(">>>", " ".join(str(c) for c in cmd))
    r = subprocess.run(cmd, cwd=str(ROOT))
    if r.returncode != 0:
        print(f"\n[run_pipeline] TAHAP '{name}' GAGAL (exit {r.returncode})")
        sys.exit(r.returncode)
    return True


def main():
    ap = argparse.ArgumentParser(description="Jalankan pipeline preprocessing data RAG")
    ap.add_argument(
        "--stage",
        default="all",
        choices=["all"] + STAGES,
        help="tahap yang dijalankan (default: all)",
    )
    ap.add_argument(
        "--skip-download",
        action="store_true",
        help="lewati pengunduhan PDF (mis. PDF sudah ada / ofline)",
    )
    ap.add_argument("--batch", default=None, help="filter batch A/B/C untuk extract & chunk")
    args = ap.parse_args()

    stages = STAGES if args.stage == "all" else [args.stage]
    if args.skip_download and "download" in stages:
        stages.remove("download")

    batch_extra = []
    if args.batch:
        batch_extra = ["--batch", args.batch]

    for s in stages:
        extra = None
        if s in ("extract", "chunk") and batch_extra:
            extra = batch_extra
        run_stage(s, extra)

    print("\n[run_pipeline] SELESAI. Tahap: %s" % " -> ".join(stages))


if __name__ == "__main__":
    main()