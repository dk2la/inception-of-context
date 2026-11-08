import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from main import greet, shout
from notes.service import NoteService


def test_create_and_find():
    svc = NoteService()
    note = svc.create("First", body="hello", tags=["a"])
    assert svc.find(note.id) is note


def test_create_rejects_empty_title():
    with pytest.raises(ValueError):
        NoteService().create("   ")


def test_search_is_case_insensitive():
    svc = NoteService()
    svc.create("Groceries", body="Buy MILK")
    assert [n.title for n in svc.search("milk")] == ["Groceries"]
    assert svc.search("") == []


def test_by_tag_and_remove():
    svc = NoteService()
    a = svc.create("A", tags=["work"])
    svc.create("B", tags=["home"])
    assert [n.title for n in svc.by_tag("work")] == ["A"]
    assert svc.remove(a.id) is True
    assert svc.remove(a.id) is False


def test_greetings():
    assert greet("bob") == "Hello, bob!"
    assert shout("bob") == "HELLO, BOB!"
