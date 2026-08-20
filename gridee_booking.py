"""Compatibility entry point for the merged UI booking command."""

from __future__ import annotations

import sys

from gridee.cli import main


if __name__ == "__main__":
    sys.argv.insert(1, "booking")
    raise SystemExit(main())
