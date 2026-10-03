"""Inspect headers/timing without decoding or exporting images."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from droplet_vision.cine import CineReader
from droplet_vision.cine.inventory import _output_path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--json", type=Path, help="Optional JSON output (portable filename only)")
    args = parser.parse_args()
    with CineReader(args.input) as reader:
        metadata = reader.metadata.to_dict()
        metadata["path"] = metadata["filename"]
        document = {"metadata": metadata, "timing": reader.timing_summary.to_dict()}
    content = json.dumps(document, indent=2, ensure_ascii=False, allow_nan=False)
    if args.json:
        _output_path(args.json).write_text(content + "\n", encoding="utf-8")
    print(content)


if __name__ == "__main__":
    main()
