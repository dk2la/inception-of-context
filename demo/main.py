"""Entry point of the notes demo application."""
from __future__ import annotations

import sys

from notes.cli import build_parser, dispatch
from notes.service import NoteService


def greet(name: str) -> str:
    return f"Hello, {name}!"


def shout(name: str) -> str:
    return greet(name).upper()


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    service = NoteService()
    for line in dispatch(service, args):
        print(line)
    return 0


if __name__ == "__main__":
    print(greet("world"))
    sys.exit(main())
