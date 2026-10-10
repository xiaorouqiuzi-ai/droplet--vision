"""Offline README/docs link and Markdown structure audit (standard library only).

A small repository checker, not a full Markdown parser. Covers inline
links/images, reference links, HTML src/href, ATX headings and pipe tables.
External URLs are ignored; no network requests are made.
"""
from __future__ import annotations

import argparse
from html import unescape
from pathlib import Path
import re
from urllib.parse import unquote, urlsplit


def visible_markdown(text: str) -> tuple[str, list[str]]:
    lines, errors = [], []
    fence = None
    for number, line in enumerate(text.splitlines(), 1):
        match = re.match(r"^\s*(\x60{3,}|~{3,})(.*)$", line)
        if match:
            token, rest = match.groups()
            if fence is None:
                fence = (token[0], len(token), number)
            elif token[0] == fence[0] and len(token) >= fence[1] and not rest.strip():
                fence = None
            lines.append("")
        else:
            lines.append(line if fence is None else "")
    if fence:
        errors.append(f"line {fence[2]}: unclosed code fence")
    return "\n".join(lines), errors


def heading_anchors(text: str) -> set[str]:
    visible, _ = visible_markdown(text)
    anchors, counts = set(), {}
    for line in visible.splitlines():
        match = re.match(r"^ {0,3}#{1,6}\s+(.+?)\s*#*\s*$", line)
        if not match:
            continue
        title = re.sub(r"<[^>]+>", "", unescape(match[1])).lower()
        title = re.sub(r"[^\w\s-]", "", title)
        slug = re.sub(r"\s", "-", title)
        count = counts.get(slug, 0)
        counts[slug] = count + 1
        anchors.add(slug if count == 0 else f"{slug}-{count}")
    anchors.update(re.findall(r'\bid=["\']([^"\']+)["\']', visible))
    return anchors


def local_targets(text: str) -> tuple[list[str], list[str]]:
    visible, errors = visible_markdown(text)
    # Mask inline code before interpreting links.
    visible = re.sub(r"(\x60+)(.*?)\1", lambda m: " " * len(m[0]), visible)
    definitions = {
        key.strip().casefold(): target
        for key, target in re.findall(
            r"(?m)^ {0,3}\[([^\]]+)\]:\s*(<[^>]+>|\S+)", visible
        )
    }
    targets = re.findall(
        r"!?\[[^\]\n]*\]\(\s*(<[^>]+>|[^\s)]+)(?:\s+['\"][^)\n]*['\"])?\s*\)",
        visible,
    )
    targets += re.findall(r'\b(?:href|src)=["\']([^"\']+)["\']', visible)
    for label, key in re.findall(r"!?\[([^\]\n]+)\]\[([^\]\n]*)\]", visible):
        key = (key or label).strip().casefold()
        if key not in definitions:
            errors.append(f"undefined reference link: {key}")
        else:
            targets.append(definitions[key])
    targets.extend(definitions.values())
    return [unescape(t.strip("<>")) for t in targets], errors


def structural_errors(text: str) -> list[str]:
    visible, _ = visible_markdown(text)
    errors = []
    last_level = 0
    table_width = None
    for number, line in enumerate(visible.splitlines(), 1):
        heading = re.match(r"^ {0,3}(#{1,6})\s+", line)
        if heading:
            level = len(heading[1])
            if level > last_level + 1:
                errors.append(f"line {number}: heading skips a level")
            last_level = level
        if line.strip().startswith("|") and line.strip().endswith("|"):
            cells = re.split(r"(?<!\\)\|", line.strip())[1:-1]
            if table_width is None:
                table_width = len(cells)
            elif len(cells) != table_width:
                errors.append(f"line {number}: inconsistent table column count")
        else:
            table_width = None
    return errors


def audit(root: Path) -> tuple[list[str], int, int]:
    root = root.resolve()
    files = [root / "README.md"] + sorted(root.glob("README.*.md")) + sorted((root / "docs").rglob("*.md"))
    errors, link_count = [], 0
    for file in files:
        label = file.relative_to(root).as_posix()
        if not file.is_file():
            errors.append(f"{label}: missing document")
            continue
        text = file.read_text(encoding="utf-8-sig")
        targets, parse_errors = local_targets(text)
        errors.extend(f"{label}: {e}" for e in parse_errors + structural_errors(text))
        if re.search(r"(?i)(?<!\w)(?:[A-Z]:[\\/]|\\\\[A-Za-z0-9])", text):
            errors.append(f"{label}: absolute machine path in document")
        for target in targets:
            if re.match(r"(?i)^[a-z]:[\\/]", target) or target.startswith(("\\\\", "file:")):
                errors.append(f"{label}: absolute local link: {target}")
                continue
            parsed = urlsplit(target)
            if parsed.scheme or parsed.netloc:
                continue
            path = unquote(parsed.path)
            if path.startswith("/"):
                errors.append(f"{label}: use a relative local link: {target}")
                continue
            destination = (file.parent / path).resolve() if path else file
            link_count += 1
            if not destination.exists():
                errors.append(f"{label}: missing target: {target}")
            elif parsed.fragment and destination.suffix.lower() == ".md":
                anchors = heading_anchors(destination.read_text(encoding="utf-8-sig"))
                if unquote(parsed.fragment) not in anchors:
                    errors.append(f"{label}: missing heading anchor: {target}")
    return errors, len(files), link_count


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    errors, file_count, link_count = audit(args.root)
    for error in errors:
        print(error)
    print(f"Checked {file_count} Markdown files and {link_count} local links; {len(errors)} errors.")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
