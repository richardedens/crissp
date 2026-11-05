"""C.R.I.S.S.P.: a way of working for a product owner, Claude and its agents in one repository, with the guards that
prove it. `crissp init` brings a project in; `crissp check`, `check-all`, `deploy`, `dashboard`, `ux` and `mcp` run the
framework for it."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("crissp")
except PackageNotFoundError:  # pragma: no cover - a checkout that was never installed
    __version__ = "0+unknown"
