#!/usr/bin/env python3
"""Move top-level result files into results/archived with timestamped names."""

from __future__ import annotations

import argparse
import shutil
from datetime import datetime, timezone
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RESULTS_DIR = PROJECT_ROOT / "results"
ARCHIVE_DIR = RESULTS_DIR / "archived"


def timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def archive_name(path: Path, stamp: str) -> Path:
    candidate = ARCHIVE_DIR / f"{path.stem}_{stamp}{path.suffix}"
    index = 1

    while candidate.exists():
        candidate = ARCHIVE_DIR / f"{path.stem}_{stamp}_{index}{path.suffix}"
        index += 1

    return candidate


def result_files(include_all: bool) -> list[Path]:
    if not RESULTS_DIR.exists():
        return []

    files: list[Path] = []
    for path in sorted(RESULTS_DIR.iterdir()):
        if path == ARCHIVE_DIR or not path.is_file():
            continue
        if include_all or path.suffix.lower() == ".csv":
            files.append(path)
    return files


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Archive top-level files from results/ into results/archived/."
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Archive all top-level files in results/, not just CSV files.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would move without changing files.",
    )
    args = parser.parse_args()

    files = result_files(include_all=args.all)
    if not files:
        print("No result files to archive.")
        return 0

    stamp = timestamp()
    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)

    for src in files:
        dst = archive_name(src, stamp)
        rel_src = src.relative_to(PROJECT_ROOT)
        rel_dst = dst.relative_to(PROJECT_ROOT)
        if args.dry_run:
            print(f"Would move {rel_src} -> {rel_dst}")
        else:
            shutil.move(str(src), str(dst))
            print(f"Moved {rel_src} -> {rel_dst}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
