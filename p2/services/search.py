"""Retrieval: rank the whole Index by meaning and by keywords, then merge the two rankings."""
import re

from rank_bm25 import BM25Okapi

from p1.config.settings import settings
from p1.core.chroma_db import chroma_db
from p2.repositories.search_repository import search_repository

# Words that say nothing about which code is meant. Left in, "the function that adds two numbers" would match
# every chunk with "the", "function" or "that" in it, and those matches would push the real answer down.
STOP_WORDS = {
    "a", "an", "and", "any", "are", "as", "at", "be", "by", "can", "do", "does", "for", "from", "has", "have", "how",
    "i", "if", "in", "is", "it", "its", "me", "my", "of", "on", "or", "please", "show", "so", "some", "that", "the",
    "there", "this", "to", "we", "what", "when", "where", "which", "who", "why", "with", "you",
    "code", "file", "function", "functions", "method", "methods",
}


class SearchService:
    def __init__(self, settings, chroma_db, search_repository):
        # debug: _bm25 is None until the first search. _bm25_version == -1 means "never built".
        # POST /context and ask() both call search() on the object at the bottom of this file.
        self.settings = settings
        self.chroma_db = chroma_db
        self.search_repository = search_repository
        self._bm25 = None  # the BM25Okapi object, or None when the Index is empty
        self._bm25_ids = []  # Chunk ids, in the same order as the documents of _bm25
        self._bm25_terms = []  # the set of terms of each of those Chunks, same order
        self._bm25_version = -1  # the INDEX_VERSION they were built from; -1 = never built
        self._bm25_collection = None  # the collection they were built from (a different Index must not reuse them)

    def tokenize(self, text):
        """Lowercase words and numbers. Punctuation and underscores split words: divide_by_zero -> 3 words."""
        # debug: tokenize("division by zero") == ["division", "by", "zero"]
        # tokenize("divide_by_zero") == ["divide", "by", "zero"]
        return re.findall(r"[a-z0-9]+", text.lower())

    def stem(self, word):
        """A small suffix stemmer, the same for the Chunks and the query, so "adds" finds "add"."""
        # debug: "adds" -> "add". "greeting", "greets", "greeted" -> "greet". "divides", "divide" -> "divid"
        # "class" -> "class" (a double s is not a plural). "is" -> "is" (too short to cut)
        if len(word) > 4 and word.endswith("ies"):
            word = word[:-3] + "y"
        elif len(word) > 5 and word.endswith("ing"):
            word = word[:-3]
        elif len(word) > 4 and word.endswith("ed"):
            word = word[:-2]
        elif len(word) > 3 and word.endswith("s") and not word.endswith("ss"):
            word = word[:-1]
        if len(word) > 3 and word.endswith("e"):
            word = word[:-1]
        return word

    def terms(self, text):
        """The BM25 terms of a text: its tokens without STOP_WORDS, stemmed."""
        # debug: terms("the function that adds two numbers") == ["add", "two", "number"]
        # terms("def divide_by_zero():") == ["def", "divid", "zero"]
        return [self.stem(token) for token in self.tokenize(text) if token not in STOP_WORDS]

    def vector_search(self, query):
        """Rank every Chunk by meaning. Return (ids best first, {id: similarity})."""
        # debug: query == "division by zero"
        # return == (["bb22…", "aa11…"], {"bb22…": 0.81, "aa11…": 0.22})
        # bb22… is Calculator.divide. Same pair that rank_by_meaning returns.
        return self.search_repository.rank_by_meaning(query)

    def _build_bm25(self, collection):
        """Read every Chunk from the Index and build the BM25 index from them."""
        # debug: all_texts() == (["aa11…", "bb22…"], ["    def add…", "    def divide…"])
        # _bm25_ids keeps that same order. _bm25_version becomes chroma_db.INDEX_VERSION, for example 3.
        # empty Index: _bm25 stays None, _bm25_ids == []
        # The version is read BEFORE the texts: if the Watcher changes the Index in between, this BM25 index
        # is marked older than the Index and is rebuilt on the next search, instead of staying stale.
        version = self.chroma_db.INDEX_VERSION
        ids, texts = self.search_repository.all_texts()
        documents = [self.terms(text) for text in texts]
        bm25 = BM25Okapi(documents) if ids else None  # BM25Okapi fails on no documents
        # set together, so a search in another thread never mixes two builds
        self._bm25, self._bm25_ids, self._bm25_terms = bm25, ids, [set(words) for words in documents]
        self._bm25_version = version
        self._bm25_collection = collection

    def bm25_search(self, query):
        """Rank the Chunks that share a term with the query by keywords (BM25). Return their ids, best first.

        A Chunk with no shared term is left out: its place in this list would be arbitrary, and RRF would still
        give it points for that place. The vector list ranks every Chunk anyway, so nothing is lost.

        The BM25 index is rebuilt only when the Index changed (a new version, or another Index).
        """
        # debug: query == "division by zero". First call builds _bm25. A later call reuses it
        # while INDEX_VERSION is unchanged.
        # scores is one float per Chunk, same order as _bm25_ids. Higher is a better keyword match.
        # return == ["bb22…"]  # ids only, best first. Calculator.divide is bb22…; add shares no term, so it is left out
        # empty Index, or a query of stop words only: return == []
        collection = self.chroma_db.get_collection()
        if self.chroma_db.INDEX_VERSION != self._bm25_version or collection is not self._bm25_collection:
            self._build_bm25(collection)
        # one consistent triple, even if another thread rebuilds meanwhile
        bm25, ids, documents = self._bm25, self._bm25_ids, self._bm25_terms
        if bm25 is None:
            return []
        terms = set(self.terms(query))
        if not terms:
            return []
        scores = bm25.get_scores(list(terms))
        # BM25Okapi can score a matching Chunk 0 or below (a term in most Chunks), so a match is "shares a term"
        matched = [(chunk_id, score) for chunk_id, score, words in zip(ids, scores, documents)
                   if terms.intersection(words)]
        return [chunk_id for chunk_id, _ in sorted(matched, key=lambda pair: pair[1], reverse=True)]

    def rrf_merge(self, ranked_a, ranked_b, weight_b=1.0):
        """Reciprocal Rank Fusion: add 1 / (RRF_K + rank) for every list an id appears in. Return {id: score}.

        weight_b scales what ranked_b gives: search() passes BM25_WEIGHT (0.5), so meaning counts twice as much.
        """
        # debug: RRF_K == 60. Rank 1 adds 1/61, rank 2 adds 1/62.
        # ranked_a (vector) == ["bb22…", "aa11…"], ranked_b (BM25) == ["bb22…", "aa11…"]
        # bb22… is rank 1 in both lists: score == 1/61 + 1/61
        # return == {"bb22…": 0.0328, "aa11…": 0.0323}
        # weight_b == 0.5: rank 1 in ranked_b adds 0.5/61 instead of 1/61
        scores = {}
        for ranked, weight in ((ranked_a, 1.0), (ranked_b, weight_b)):
            for rank, chunk_id in enumerate(ranked, start=1):
                scores[chunk_id] = scores.get(chunk_id, 0) + weight / (self.settings.RRF_K + rank)
        return scores

    def search(self, query, k):
        """The top k Chunks for a query, best first: the Chunk fields plus id, text, similarity and score."""
        # debug: POST /context {"query": "division by zero", "k": 3} and ask() both land here.
        # top_ids is the RRF order, cut to k. k <= 0 or an empty Index: return == []
        # return == [{
        #     "id": "bb22…",
        #     "text": "    def divide(self, a, b):\n        …",
        #     "path": "calculator/core.py", "start_line": 16, "end_line": 20,
        #     "name": "Calculator.divide", "kind": "method", "hash": "…",
        #     "similarity": 0.81,   # vector only. 0.0 if this id was ranked by BM25 alone
        #     "score": 0.0328,      # the RRF score
        # }]
        vector_ids, similarity = self.vector_search(query)
        scores = self.rrf_merge(vector_ids, self.bm25_search(query), self.settings.BM25_WEIGHT)
        top_ids = sorted(scores, key=scores.get, reverse=True)[:max(k, 0)]
        if not top_ids:
            return []  # empty Index or k <= 0; Chroma refuses to get no ids

        by_id = self.search_repository.get_many(top_ids)
        results = []
        for chunk_id in top_ids:
            if chunk_id not in by_id:
                continue  # the Watcher deleted it after it was ranked (a file changed during this search)
            text, metadata = by_id[chunk_id]
            results.append({**metadata, "id": chunk_id, "text": text,
                            "similarity": similarity.get(chunk_id, 0.0), "score": scores[chunk_id]})
        return results


search_service = SearchService(settings, chroma_db, search_repository)
