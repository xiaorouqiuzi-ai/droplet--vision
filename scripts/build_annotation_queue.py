"""Sample raw Cine frames into a portable work queue, without event labels."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from droplet_vision.sampling import build_annotation_queue, load_sampling_config, AnnotationQueue
from droplet_vision.sampling.sampler import outside_source, summarize_queue
from droplet_vision.sampling.queue import atomic_json


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--config", type=Path)
    recursion = parser.add_mutually_exclusive_group()
    recursion.add_argument("--recursive", dest="recursive", action="store_true", default=True)
    recursion.add_argument("--no-recursive", dest="recursive", action="store_false")
    parser.add_argument("--preview", action="store_true", help="Separate Ref90 contact sheet; not training data")
    args = parser.parse_args()
    outside_source(args.output, args.root)
    for name in ("sampling_summary.json", "sampling_summary.txt", "queue_preview_contact_sheet.png", "preview_diagnostics.json"):
        outside_source(args.output.parent / name, args.root)
    previous = AnnotationQueue.load(args.output) if args.output.exists() else None
    queue = build_annotation_queue(args.root, load_sampling_config(args.config), args.recursive,
                                   progress=lambda path: print("Sampled: " + path, flush=True))
    if previous is not None:
        queue.resume_from(previous)
    queue.save(args.output)
    summary = summarize_queue(queue)
    atomic_json(args.output.parent / "sampling_summary.json", summary)
    (args.output.parent / "sampling_summary.txt").write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    if args.preview:
        from droplet_vision.sampling.preview import write_contact_sheet
        write_contact_sheet(queue, args.root, args.output.parent)
    print(f"Queue: {len(queue.items)} items; {len(queue.failed_files)} failed Cine(s).")


if __name__ == "__main__":
    main()
