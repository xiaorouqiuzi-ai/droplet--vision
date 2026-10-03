"""Load taxonomy from JSON, with no dependency on the scientific ObjectType enum."""
from __future__ import annotations
import json
from pathlib import Path
from typing import List, Union
from .schema import AnnotationLabel


def load_taxonomy(path: Union[str, Path]) -> List[AnnotationLabel]:
    content = json.loads(Path(path).read_text(encoding="utf-8"))
    labels = [AnnotationLabel(**row) for row in content["labels"]]
    if len({label.label_id for label in labels}) != len(labels):
        raise ValueError("Duplicate taxonomy label_id")
    return labels


def default_taxonomy_path() -> Path:
    return Path(__file__).resolve().parents[3] / "configs/annotations/default_taxonomy.json"
