import os

import pytest
from rank_bm25 import BM25Okapi

from p1.config import settings
from p1.core import database
from p1.core.database import get_collection
from p1.services.indexer import reindex_file
from p2.repositories import search_repository
from p2.services import search
from p2.services.search import bm25_search, rrf_merge, tokenize, vector_search


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
    monkeypatch.setattr(settings, "CHROMA_DIR", str(tmp_path / "other_chroma"))
    monkeypatch.setattr(database, "_collection", None)
    assert bm25_search("divide") == []


# --- rrf_merge ---


def test_rrf_gives_one_over_k_plus_rank_for_each_list():
    assert rrf_merge(["x"], ["x"])["x"] == pytest.approx(2 / 61)


def test_rrf_agreement_wins():
    scores = rrf_merge(["a", "b", "c"], ["b", "a", "c"])
    assert scores["a"] == pytest.approx(scores["b"])
    assert scores["a"] > scores["c"]


def test_rrf_second_in_one_list_and_first_in_the_other_beats_first_and_last():
    scores = rrf_merge(["x", "y", "z"], ["y", "z", "x"])
    assert max(scores, key=scores.get) == "y"


def test_rrf_an_id_missing_from_one_list_gets_points_from_the_other_only():
    assert rrf_merge(["a", "b"], ["a"])["b"] == pytest.approx(1 / 62)


def test_rrf_of_nothing_is_nothing():
    assert rrf_merge([], []) == {}


# --- search ---

FOUR = '''def add(a, b):
    return a + b


def divide(a, b):
    return a / b


def divide_by_zero_message():
    return "cannot divide by zero"


def greet(name):
    return "hello " + name
'''


def test_search_returns_k_chunks_with_everything_a_caller_needs(temp_index):
    reindex_file(write(temp_index, "math.py", FOUR))
    results = search.search("divide", 2)
    assert len(results) == 2
    for result in results:
        assert {"id", "path", "start_line", "end_line", "name", "kind", "hash",
                "text", "similarity", "score"} <= set(result)
    assert results[0]["path"] == "math.py"
    assert results[0]["text"] in FOUR


def test_search_results_are_sorted_by_score_best_first(temp_index):
    reindex_file(write(temp_index, "math.py", FOUR))
    scores = [r["score"] for r in search.search("divide", 4)]
    assert scores == sorted(scores, reverse=True)


def test_search_puts_the_exact_name_first(temp_index):
    reindex_file(write(temp_index, "math.py", FOUR))
    assert search.search("divide by zero", 3)[0]["name"] == "divide_by_zero_message"


def test_search_with_k_larger_than_the_index_returns_every_chunk(temp_index):
    reindex_file(write(temp_index, "math.py", FOUR))
    assert len(search.search("x", 100)) == get_collection().count()


def test_search_on_an_empty_index_returns_nothing(temp_index):
    assert search.search("x", 5) == []


@pytest.mark.parametrize("k", [0, -1])
def test_search_with_k_zero_or_negative_returns_nothing(temp_index, k):
    reindex_file(write(temp_index, "math.py", FOUR))
    assert search.search("divide", k) == []


# --- the Watcher changes the Index while a search runs ---


def test_a_change_while_bm25_reads_the_index_makes_the_next_search_rebuild(temp_index, monkeypatch):
    """If the Index changes between reading the version and reading the texts, the cache must not look fresh."""
    path = write(temp_index, "math.py", MATH)
    reindex_file(path)
    real_all_texts = search_repository.all_texts

    def all_texts_then_the_watcher_changes_the_file():
        found = real_all_texts()
        monkeypatch.setattr(search_repository, "all_texts", real_all_texts)  # only once
        write(temp_index, "math.py", "def square_root(x):\n    return x ** 0.5\n")
        reindex_file(path)
        return found

    monkeypatch.setattr(search_repository, "all_texts", all_texts_then_the_watcher_changes_the_file)
    bm25_search("divide")  # built from the old texts while the file changed
    assert [name_of(i) for i in bm25_search("square root")] == ["square_root"]


def test_search_skips_a_chunk_deleted_after_it_was_ranked(temp_index, monkeypatch):
    reindex_file(write(temp_index, "math.py", MATH))
    real_get_many = search_repository.get_many

    def get_many_after_a_delete(ids):
        get_collection().delete(ids=[ids[0]])  # the Watcher removes the best Chunk just now
        return real_get_many(ids)

    monkeypatch.setattr(search_repository, "get_many", get_many_after_a_delete)
    results = search.search("divide", 5)
    assert [r["name"] for r in results] == ["greet"]
