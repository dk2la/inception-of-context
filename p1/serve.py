#!/usr/bin/env python3
"""Part 1 server: same as `python p1/index.py <target> --serve`."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from index import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:] + ["--serve"]))
