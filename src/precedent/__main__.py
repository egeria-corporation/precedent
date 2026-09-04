"""``python -m precedent``, so the package runs without the console script on PATH."""

from __future__ import annotations

from precedent.cli import main

if __name__ == "__main__":
    main()
