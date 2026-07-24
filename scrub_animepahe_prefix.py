#!/usr/bin/env python3
"""Remove the AnimePahe_ prefix from filenames under show series/.

Examples:
  py scrub_animepahe_prefix.py --dry-run
  py scrub_animepahe_prefix.py
"""

from __future__ import annotations

import argparse
from pathlib import Path


def scrub_prefix(root: Path, dry_run: bool) -> int:
    if not root.exists():
        raise FileNotFoundError(f"Folder not found: {root}")

    renamed_count = 0
    skipped_count = 0

    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue

        old_name = path.name
        if "AnimePahe_" not in old_name:
            continue

        new_name = old_name.replace("AnimePahe_", "")
        if not new_name or new_name == old_name:
            continue

        target = path.with_name(new_name)
        if target.exists():
            print(f"SKIP (target exists): {path} -> {target}")
            skipped_count += 1
            continue

        print(f"RENAME: {path} -> {target}")
        if not dry_run:
            path.rename(target)
        renamed_count += 1

    print(f"Done. Renamed: {renamed_count}, Skipped: {skipped_count}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Scrub AnimePahe_ from file names under show series/.")
    parser.add_argument(
        "--root",
        type=Path,
        default=Path("show series"),
        help="Root folder to scan (default: show series)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print planned renames without changing files",
    )
    args = parser.parse_args()

    return scrub_prefix(root=args.root, dry_run=args.dry_run)


if __name__ == "__main__":
    raise SystemExit(main())
