import os

import pytest

from p1 import index
from p1.index import get_collection, reindex_file
from p2.search import tokenize, vector_search

# --- helpers ---

MATH = '''def divide(a, b):
    return a / b


def greet(name):
    return "hello " + name
'''


def write(target, name, text):
    """Write a file into the temporary Target Project and return its absolute path."""
    path = os.path.join(target, name)
    with open(path, "w") as f:
        f.write(text)
    return path


def name_of(chunk_id):
    return get_collection().get(ids=[chunk_id], include=["metadatas"])["metadatas"][0]["name"]


# --- vector_search ---


def test_vector_search_ranks_the_chunk_with_the_closest_meaning_first(temp_index):
    reindex_file(write(temp_index, "math.py", MATH))
    ids, similarity = vector_search("split a number into equal parts")
    names = [name_of(i) for i in ids]
    assert names.index("divide") < names.index("greet")


def test_vector_search_returns_every_chunk(temp_index):
    reindex_file(write(temp_index, "math.py", MATH))
    ids, similarity = vector_search("anything")
    assert len(ids) == get_collection().count()
    assert set(similarity) == set(ids)


def test_vector_similarity_is_between_minus_one_and_one_and_best_first(temp_index):
    reindex_file(write(temp_index, "math.py", MATH))
    ids, similarity = vector_search("divide")
    assert all(-1 <= s <= 1 for s in similarity.values())
    assert similarity[ids[0]] == max(similarity.values())


def test_vector_search_on_an_empty_index_returns_nothing(temp_index):
    assert vector_search("anything") == ([], {})


# --- tokenize ---


@pytest.mark.parametrize("text, tokens", [
    ("def divide(self, a, b):", ["def", "divide", "self", "a", "b"]),
    ("Is there a divide_by_zero?", ["is", "there", "a", "divide", "by", "zero"]),
    ("ioc.config.yml", ["ioc", "config", "yml"]),
    ("x2 = 10", ["x2", "10"]),
    ("", []),
    ("!!! ???", []),
])
def test_tokenize_gives_lowercase_words_and_digits(text, tokens):
    assert tokenize(text) == tokens
