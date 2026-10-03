"""Launch the optional Qt viewer from a source checkout."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

if __name__ == "__main__":
    from droplet_vision.ui.app import main
    raise SystemExit(main())
