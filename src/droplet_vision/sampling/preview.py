"""Optional contact sheets; display preprocessing never feeds sampling scores."""
from __future__ import annotations
from collections import defaultdict
from pathlib import Path
import math
from PIL import Image, ImageDraw, ImageFont
from ..cine import CineReader
from ..display.photometric import load_photometric_preset, cine_reference_index, estimate_reference, apply_locked_gain
from .schema import resolve_relative
from .sampler import outside_source, source_signature, verify_source
from .queue import atomic_json


def write_contact_sheet(queue, root, output_dir):
    output_dir = Path(output_dir)
    output = output_dir / "queue_preview_contact_sheet.png"
    outside_source(output, root)
    outside_source(output_dir / "preview_diagnostics.json", root)
    groups = defaultdict(list)
    for item in queue.items:
        groups[item.relative_cine_path].append(item)
    font = ImageFont.load_default(size=14)
    width, cell_h, columns = 320, 292, 4
    height = 65 + sum(32 + math.ceil(len(items)/columns)*cell_h for items in groups.values())
    # Large datasets use the JSON queue; avoid accidentally allocating an enormous sheet.
    if height * width * columns > 80_000_000:
        raise ValueError("Preview exceeds 80 megapixels; use smaller dataset groups")
    sheet = Image.new("RGB", (width*columns, max(height, 100)), "#242424")
    draw = ImageDraw.Draw(sheet)
    draw.text((10, 8), "REF90 DISPLAY PREVIEW — NOT TRAINING DATA", font=font, fill="white")
    draw.text((10, 30), "SAMPLING WAS PERFORMED ON RAW PIXELS", font=font, fill="white")
    preset = load_photometric_preset()
    diagnostics = []
    y = 65
    baseline = {name: source_signature(resolve_relative(root, name)) for name in groups}
    for name, items in sorted(groups.items()):
        path = resolve_relative(root, name)
        draw.text((10, y), name, font=font, fill="#ffd166")
        y += 32
        decoded = 0
        try:
            verify_source(path, baseline[name])
            with CineReader(path) as reader:
                try:
                    reference = estimate_reference(reader.read_frame(cine_reference_index(reader.frame_count)), reader.frame_count, preset)
                    decoded += 1
                    diagnostic = reference.to_dict()
                except ValueError as error:
                    reference = None
                    diagnostic = {"fallback": "RAW", "reason": str(error)}
                for offset, item in enumerate(sorted(items, key=lambda i: i.frame_index)):
                    raw = reader.read_frame(item.frame_index)
                    decoded += 1
                    pixels = apply_locked_gain(raw, reference) if reference is not None else raw
                    image = Image.fromarray(pixels)
                    image.thumbnail((224, 224))
                    xx, yy = (offset % columns)*width, y+(offset//columns)*cell_h
                    sheet.paste(image.convert("RGB"), (xx, yy))
                    score = "—" if item.change_score is None else f"{item.change_score:.5f}"
                    label = (f"{item.cine_filename}\nframe {item.frame_index} | fraction {item.frame_fraction:.4f}\n"
                             f"{', '.join(item.sample_reasons)} | change {score}")
                    draw.text((xx, yy+226), label, font=font, fill="white", spacing=2)
                diagnostics.append({"relative_path": name, "preview_frames_decoded": decoded, **diagnostic})
        finally:
            verify_source(path, baseline[name])
        y += math.ceil(len(items)/columns)*cell_h
    for name, signature in baseline.items():
        verify_source(resolve_relative(root, name), signature)
    output_dir.mkdir(parents=True, exist_ok=True)
    sheet.save(output)
    atomic_json(output_dir / "preview_diagnostics.json", {"preview_only": True, "source_unchanged": True, "cines": diagnostics})
    return output
