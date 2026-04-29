"""Entry point for `python -m apts_release` invocation.

Useful as a fallback when Windows Application Control blocks the
generated apts-release.exe shim in the Python Scripts directory.
"""

from apts_release.cli import app

if __name__ == "__main__":
    app()
