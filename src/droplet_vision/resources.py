"""Read-only bundled resources and writable defaults; no Qt dependency."""
from pathlib import Path
import os
import sys


def is_frozen():
    return bool(getattr(sys, "frozen", False))


def resource_path(relative):
    root = Path(sys._MEIPASS) if is_frozen() else Path(__file__).resolve().parents[2]
    return root / relative


def ui_resource_path(relative):
    prefix = "droplet_vision/ui" if is_frozen() else "src/droplet_vision/ui"
    return resource_path(prefix) / relative


def output_path(relative=""):
    """Source defaults stay unchanged; installed apps never write beside EXE."""
    if is_frozen():
        root = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData/Local") / "DropletVision"
    else:
        root = Path("outputs")
    return root / relative
