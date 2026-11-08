"""Command-line front-end: parses arguments and dispatches to NoteService."""
from __future__ import annotations

import argparse

from .service import NoteService


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="notes", description="Tiny notes app")
    sub = parser.add_subparsers(dest="command")
    add = sub.add_parser("add", help="create a note")
    add.add_argument("title")
    add.add_argument("--body", default="")
    add.add_argument("--tag", action="append", default=[])
    search = sub.add_parser("search", help="search notes")
    search.add_argument("term")
    sub.add_parser("list", help="list all notes")
    return parser


def dispatch(service: NoteService, args: argparse.Namespace) -> list[str]:
    if args.command == "add":
        note = service.create(args.title, body=args.body, tags=args.tag)
        return [f"created #{note.id}: {note.title}"]
    if args.command == "search":
        return [f"#{n.id} {n.title}" for n in service.search(args.term)]
    if args.command == "list":
        return [f"#{n.id} {n.title}" for n in service.storage.list_all()]
    return ["nothing to do (try --help)"]
