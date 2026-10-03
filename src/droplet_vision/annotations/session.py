"""Portable viewer sessions and bookmarks, separate from annotations."""
from __future__ import annotations
import json
from dataclasses import dataclass, field, asdict
from pathlib import Path, PureWindowsPath
from typing import Any, Dict, List, Optional, Union


def _portable(value: str) -> bool:
    return not (Path(value).is_absolute() or PureWindowsPath(value).drive or ".." in value.replace("\\", "/").split("/"))


@dataclass
class Bookmark:
    frame_index: int
    timestamp_time64: Optional[int] = None
    timestamp_s: Optional[float] = None
    note: str = ""
    tags: List[str] = field(default_factory=list)


@dataclass
class ViewerSession:
    cine_filename: str
    file_size_bytes: int
    frame_count: int
    last_frame: int = 0
    bookmarks: List[Bookmark] = field(default_factory=list)
    notes: str = ""
    ui_state: Dict[str, Any] = field(default_factory=dict)
    layer_references: List[str] = field(default_factory=list)
    local_only: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if not _portable(self.cine_filename) or "/" in self.cine_filename or "\\" in self.cine_filename:
            raise ValueError("Session Cine identity must be a filename, not a path")
        if self.frame_count <= 0 or not 0 <= self.last_frame < self.frame_count:
            raise ValueError("Invalid session frame range")
        if any(not _portable(value) for value in self.layer_references):
            raise ValueError("Layer references must be portable relative paths")
        if any(not 0 <= b.frame_index < self.frame_count for b in self.bookmarks):
            raise ValueError("Bookmark outside Cine frame range")

    def to_dict(self, portable: bool = True) -> Dict[str, Any]:
        self.__post_init__()
        value = asdict(self)
        if portable:
            value.pop("local_only")
        value["schema_version"] = 1
        return json.loads(json.dumps(value, allow_nan=False))

    def save(self, path: Union[str, Path]) -> None:
        path = Path(path)
        if path.suffix.lower() != ".json" or path.resolve().suffix.lower() != ".json":
            raise ValueError("Session destination must be a .json file")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), indent=2, allow_nan=False), encoding="utf-8")

    @classmethod
    def load(cls, path: Union[str, Path]) -> ViewerSession:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
        if value.pop("schema_version") != 1:
            raise ValueError("Unsupported session version")
        value["bookmarks"] = [Bookmark(**b) for b in value.get("bookmarks", [])]
        return cls(**value)
