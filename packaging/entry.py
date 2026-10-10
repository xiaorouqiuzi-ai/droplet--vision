"""Windowed PyInstaller entry, sharing the source application's CLI."""
from droplet_vision.ui.app import main

if __name__ == "__main__":
    raise SystemExit(main())
