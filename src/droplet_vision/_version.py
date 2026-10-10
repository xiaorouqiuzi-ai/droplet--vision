"""Single source for Python, application and Windows release versions."""
__version__ = "0.1.0b1"
DISPLAY_VERSION = __version__.replace("b", "-beta.")
WINDOWS_VERSION = tuple(int(v) for v in __version__.split("b")[0].split(".")) + (int(__version__.split("b")[1]),)
