"""Command-line entry point: python main.py 2 + 3"""
import sys

from calculator.cli import run

if __name__ == "__main__":
    sys.exit(run(sys.argv[1:]))
