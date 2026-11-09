import os

import pytest
from rank_bm25 import BM25Okapi

from p1 import index
from p1.index import get_collection, reindex_file
from p2 import search
from p2.search import bm25_search, tokenize, vector_search

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


# --- bm25_search ---

THREE = '''def add(a, b):
    return a + b


def divide_by_zero_message():
    return "cannot divide by zero"


def greet(name):
    return "hello " + name
'''


def test_bm25_search_ranks_the_exact_name_first(temp_index):
    reindex_file(write(temp_index, "math.py", THREE))
    ids = bm25_search("divide by zero")
    assert name_of(ids[0]) == "divide_by_zero_message"


def test_bm25_search_returns_every_chunk_even_without_shared_words(temp_index):
    reindex_file(write(temp_index, "math.py", THREE))
    assert len(bm25_search("divide by zero")) == get_collection().count()
    assert len(bm25_search("banana")) == get_collection().count()


def test_bm25_search_on_an_empty_index_returns_nothing(temp_index):
    assert bm25_search("anything") == []


# --- the BM25 cache ---


def count_bm25_builds(monkeypatch):
    """Replace BM25Okapi with a counting wrapper; return the list that gets one item per build."""
    builds = []

    def counting_bm25(documents):
        builds.append(1)
        return BM25Okapi(documents)

    monkeypatch.setattr(search, "BM25Okapi", counting_bm25)
    return builds


def test_bm25_is_built_once_while_the_index_does_not_change(temp_index, monkeypatch):
    reindex_file(write(temp_index, "math.py", THREE))
    builds = count_bm25_builds(monkeypatch)
    bm25_search("divide")
    bm25_search("greet")
    assert len(builds) == 1


def test_bm25_sees_a_function_added_to_a_file(temp_index):
    path = write(temp_index, "math.py", THREE)
    reindex_file(path)
    bm25_search("anything")
    write(temp_index, "math.py", THREE + "\n\ndef square_root(x):\n    return x ** 0.5\n")
    reindex_file(path)
    assert name_of(bm25_search("square root")[0]) == "square_root"


def test_bm25_forgets_the_chunks_of_a_deleted_file(temp_index):
    path = write(temp_index, "math.py", THREE)
    reindex_file(path)
    old_ids = bm25_search("anything")
    os.remove(path)
    reindex_file(path)
    assert bm25_search("anything") == []
    assert old_ids  # the Chunks were there before the delete


def test_bm25_does_not_reuse_the_cache_of_another_index(temp_index, tmp_path, monkeypatch):
    reindex_file(write(temp_index, "math.py", THREE))
    bm25_search("divide")
    # A second, empty Index: nothing was reindexed, so INDEX_VERSION is still the same number.
    monkeypatch.setattr(index, "CHROMA_DIR", str(tmp_path / "other_chroma"))
    monkeypatch.setattr(index, "_collection", None)
    assert bm25_search("divide") == []
