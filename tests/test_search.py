import os

import pytest
from rank_bm25 import BM25Okapi

from p1.config.settings import settings
from p1.core.chroma_db import chroma_db
from p1.services.indexer import indexer_service
from p2.repositories.search_repository import search_repository
import p2.services.search as search_module
from p2.services.search import search_service


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
    return chroma_db.get_collection().get(ids=[chunk_id], include=["metadatas"])["metadatas"][0]["name"]


# --- search_service.vector_search ---


def test_vector_search_ranks_the_chunk_with_the_closest_meaning_first(temp_index):
    indexer_service.reindex_file(write(temp_index, "math.py", MATH))
    ids, similarity = search_service.vector_search("split a number into equal parts")
    names = [name_of(i) for i in ids]
    assert names.index("divide") < names.index("greet")


def test_vector_search_returns_every_chunk(temp_index):
    indexer_service.reindex_file(write(temp_index, "math.py", MATH))
    ids, similarity = search_service.vector_search("anything")
    assert len(ids) == chroma_db.get_collection().count()
    assert set(similarity) == set(ids)


def test_vector_similarity_is_between_minus_one_and_one_and_best_first(temp_index):
    indexer_service.reindex_file(write(temp_index, "math.py", MATH))
    ids, similarity = search_service.vector_search("divide")
    assert all(-1 <= s <= 1 for s in similarity.values())
    assert similarity[ids[0]] == max(similarity.values())


def test_vector_search_on_an_empty_index_returns_nothing(temp_index):
    assert search_service.vector_search("anything") == ([], {})


# --- search_service.tokenize ---


@pytest.mark.parametrize("text, tokens", [
    ("def divide(self, a, b):", ["def", "divide", "self", "a", "b"]),
    ("Is there a divide_by_zero?", ["is", "there", "a", "divide", "by", "zero"]),
    ("ioc.config.yml", ["ioc", "config", "yml"]),
    ("x2 = 10", ["x2", "10"]),
    ("", []),
    ("!!! ???", []),
])
def test_tokenize_gives_lowercase_words_and_digits(text, tokens):
    assert search_service.tokenize(text) == tokens


# --- search_service.bm25_search ---

THREE = '''def add(a, b):
    return a + b


def divide_by_zero_message():
    return "cannot divide by zero"


def greet(name):
    return "hello " + name
'''


def test_bm25_search_ranks_the_exact_name_first(temp_index):
    indexer_service.reindex_file(write(temp_index, "math.py", THREE))
    ids = search_service.bm25_search("divide by zero")
    assert name_of(ids[0]) == "divide_by_zero_message"


def test_bm25_search_ranks_only_the_chunks_that_share_a_term(temp_index):
    indexer_service.reindex_file(write(temp_index, "math.py", THREE))
    assert [name_of(i) for i in search_service.bm25_search("divide by zero")] == ["divide_by_zero_message"]
    assert search_service.bm25_search("banana") == []


def test_bm25_search_ignores_a_query_of_stop_words_only(temp_index):
    indexer_service.reindex_file(write(temp_index, "math.py", THREE))
    assert search_service.bm25_search("is there the function that") == []


def test_bm25_search_finds_a_name_through_its_inflected_form(temp_index):
    indexer_service.reindex_file(write(temp_index, "math.py", THREE))
    assert name_of(search_service.bm25_search("the function that adds")[0]) == "add"
    assert name_of(search_service.bm25_search("greeting someone")[0]) == "greet"


def test_a_term_in_every_chunk_still_counts_as_a_match(temp_index):
    # BM25Okapi scores a term found in every document at about 0; the Chunk shares the term, so it stays ranked
    indexer_service.reindex_file(write(temp_index, "math.py", THREE))
    assert len(search_service.bm25_search("return")) == chroma_db.get_collection().count()


@pytest.mark.parametrize("word, stem", [
    ("adds", "add"), ("add", "add"), ("greets", "greet"), ("greeting", "greet"), ("greeted", "greet"),
    ("divides", "divid"), ("divide", "divid"), ("numbers", "number"), ("queries", "query"), ("class", "class"),
    ("is", "is"), ("sing", "sing"), ("bed", "bed"),
])
def test_stem_cuts_common_endings_the_same_way_everywhere(word, stem):
    assert search_service.stem(word) == stem


def test_terms_drop_stop_words_and_stem_the_rest():
    assert search_service.terms("the function that adds two numbers") == ["add", "two", "number"]
    assert search_service.terms("def divide_by_zero():") == ["def", "divid", "zero"]


def test_bm25_search_on_an_empty_index_returns_nothing(temp_index):
    assert search_service.bm25_search("anything") == []


# --- the BM25 cache ---


def count_bm25_builds(monkeypatch):
    """Replace BM25Okapi with a counting wrapper; return the list that gets one item per build."""
    builds = []

    def counting_bm25(documents):
        builds.append(1)
        return BM25Okapi(documents)

    monkeypatch.setattr(search_module, "BM25Okapi", counting_bm25)
    return builds


def test_bm25_is_built_once_while_the_index_does_not_change(temp_index, monkeypatch):
    indexer_service.reindex_file(write(temp_index, "math.py", THREE))
    builds = count_bm25_builds(monkeypatch)
    search_service.bm25_search("divide")
    search_service.bm25_search("greet")
    assert len(builds) == 1


def test_bm25_sees_a_function_added_to_a_file(temp_index):
    path = write(temp_index, "math.py", THREE)
    indexer_service.reindex_file(path)
    search_service.bm25_search("anything")
    write(temp_index, "math.py", THREE + "\n\ndef square_root(x):\n    return x ** 0.5\n")
    indexer_service.reindex_file(path)
    assert name_of(search_service.bm25_search("square root")[0]) == "square_root"


def test_bm25_forgets_the_chunks_of_a_deleted_file(temp_index):
    path = write(temp_index, "math.py", THREE)
    indexer_service.reindex_file(path)
    old_ids = search_service.bm25_search("return")
    os.remove(path)
    indexer_service.reindex_file(path)
    assert search_service.bm25_search("return") == []
    assert old_ids  # the Chunks were there before the delete


def test_bm25_does_not_reuse_the_cache_of_another_index(temp_index, tmp_path, monkeypatch):
    indexer_service.reindex_file(write(temp_index, "math.py", THREE))
    search_service.bm25_search("divide")
    # A second, empty Index: nothing was reindexed, so INDEX_VERSION is still the same number.
    monkeypatch.setattr(settings, "CHROMA_DIR", str(tmp_path / "other_chroma"))
    monkeypatch.setattr(chroma_db, "_collection", None)
    assert search_service.bm25_search("divide") == []


# --- search_service.rrf_merge ---


def test_rrf_gives_one_over_k_plus_rank_for_each_list():
    assert search_service.rrf_merge(["x"], ["x"])["x"] == pytest.approx(2 / 61)


def test_rrf_agreement_wins():
    scores = search_service.rrf_merge(["a", "b", "c"], ["b", "a", "c"])
    assert scores["a"] == pytest.approx(scores["b"])
    assert scores["a"] > scores["c"]


def test_rrf_second_in_one_list_and_first_in_the_other_beats_first_and_last():
    scores = search_service.rrf_merge(["x", "y", "z"], ["y", "z", "x"])
    assert max(scores, key=scores.get) == "y"


def test_rrf_an_id_missing_from_one_list_gets_points_from_the_other_only():
    assert search_service.rrf_merge(["a", "b"], ["a"])["b"] == pytest.approx(1 / 62)


def test_rrf_weight_scales_only_the_second_list():
    scores = search_service.rrf_merge(["a"], ["b"], 0.5)
    assert scores == {"a": 1 / 61, "b": 0.5 / 61}


def test_rrf_of_nothing_is_nothing():
    assert search_service.rrf_merge([], []) == {}


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
    indexer_service.reindex_file(write(temp_index, "math.py", FOUR))
    results = search_service.search("divide", 2)
    assert len(results) == 2
    for result in results:
        assert {"id", "path", "start_line", "end_line", "name", "kind", "hash",
                "text", "similarity", "score"} <= set(result)
    assert results[0]["path"] == "math.py"
    assert results[0]["text"] in FOUR


def test_search_results_are_sorted_by_score_best_first(temp_index):
    indexer_service.reindex_file(write(temp_index, "math.py", FOUR))
    scores = [r["score"] for r in search_service.search("divide", 4)]
    assert scores == sorted(scores, reverse=True)


def test_search_puts_the_exact_name_first(temp_index):
    indexer_service.reindex_file(write(temp_index, "math.py", FOUR))
    assert search_service.search("divide by zero", 3)[0]["name"] == "divide_by_zero_message"


def test_search_with_k_larger_than_the_index_returns_every_chunk(temp_index):
    indexer_service.reindex_file(write(temp_index, "math.py", FOUR))
    assert len(search_service.search("x", 100)) == chroma_db.get_collection().count()


def test_search_on_an_empty_index_returns_nothing(temp_index):
    assert search_service.search("x", 5) == []


@pytest.mark.parametrize("k", [0, -1])
def test_search_with_k_zero_or_negative_returns_nothing(temp_index, k):
    indexer_service.reindex_file(write(temp_index, "math.py", FOUR))
    assert search_service.search("divide", k) == []


# --- the Watcher changes the Index while a search runs ---


def test_a_change_while_bm25_reads_the_index_makes_the_next_search_rebuild(temp_index, monkeypatch):
    """If the Index changes between reading the version and reading the texts, the cache must not look fresh."""
    path = write(temp_index, "math.py", MATH)
    indexer_service.reindex_file(path)
    real_all_texts = search_repository.all_texts

    def all_texts_then_the_watcher_changes_the_file():
        found = real_all_texts()
        monkeypatch.setattr(search_repository, "all_texts", real_all_texts)  # only once
        write(temp_index, "math.py", "def square_root(x):\n    return x ** 0.5\n")
        indexer_service.reindex_file(path)
        return found

    monkeypatch.setattr(search_repository, "all_texts", all_texts_then_the_watcher_changes_the_file)
    search_service.bm25_search("divide")  # built from the old texts while the file changed
    assert [name_of(i) for i in search_service.bm25_search("square root")] == ["square_root"]


def test_search_skips_a_chunk_deleted_after_it_was_ranked(temp_index, monkeypatch):
    indexer_service.reindex_file(write(temp_index, "math.py", MATH))
    real_get_many = search_repository.get_many

    def get_many_after_a_delete(ids):
        chroma_db.get_collection().delete(ids=[ids[0]])  # the Watcher removes the best Chunk just now
        return real_get_many(ids)

    monkeypatch.setattr(search_repository, "get_many", get_many_after_a_delete)
    results = search_service.search("divide", 5)
    assert [r["name"] for r in results] == ["greet"]
