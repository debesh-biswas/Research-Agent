"""Local-first weekly AI research intelligence agent."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("research-agent")
except PackageNotFoundError:  # pragma: no cover - only possible without an installed package
    __version__ = "0.0.0"

__all__ = ["__version__"]
