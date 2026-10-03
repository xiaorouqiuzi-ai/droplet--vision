"""Errors at the optional Cine backend boundary."""


class CineDependencyError(ImportError):
    """The optional Cine backend cannot be imported."""


class CineFormatError(ValueError):
    """A Cine header, index or tagged block is structurally invalid."""
