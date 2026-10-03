"""Build a portable Cine inventory without exporting frames."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from droplet_vision.cine import build_inventory
from droplet_vision.cine.inventory import write_inventory_csv, write_inventory_json


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--csv", type=Path)
    parser.add_argument("--json", type=Path)
    parser.add_argument("--no-recursive", action="store_true")
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--hash", action="store_true", help="Stream SHA-256 for each file (expensive)")
    args = parser.parse_args()
    if not args.csv and not args.json:
        parser.error("At least one of --csv or --json is required")
    rows = build_inventory(args.root, recursive=not args.no_recursive,
                           strict=args.strict, compute_hash=args.hash)
    if args.csv:
        write_inventory_csv(rows, args.csv)
    if args.json:
        write_inventory_json(rows, args.json)
    print("Inspected {} Cine files; {} unreadable".format(
        len(rows), sum(not row["readable"] for row in rows)))


if __name__ == "__main__":
    main()
