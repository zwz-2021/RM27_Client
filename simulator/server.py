#!/usr/bin/env python3
"""Compatibility entry point for the migrated upstream simulator.

Use python -m simulator.server.main from the repository root.
"""
from pathlib import Path
import runpy
import sys


def main():
    repository_root = Path(__file__).resolve().parent.parent
    if str(repository_root) not in sys.path:
        sys.path.insert(0, str(repository_root))
    runpy.run_module("simulator.server.main", run_name="__main__")


if __name__ == "__main__":
    main()
