"""Retrieval: rank the whole Index by meaning and by keywords, then merge the two rankings."""
import re

from rank_bm25 import BM25Okapi

from p1.config.settings import settings
from p1.core.chroma_db import chroma_db
from p2.repositories.search_repository import search_repository


class SearchService:
    def __init__(self, settings, chroma_db, search_repository):
        self.settings = settings
        self.chroma_db = chroma_db
        self.search_repository = search_repository
        self._bm25 = None
        self._bm25_ids = []
        self._bm25_version = -1
        self._bm25_collection = None

    def tokenize(self, text):
        """Lowercase words and numbers. Punctuation and underscores split words: divide_by_zero -> 3 words."""
        return re.findall(r"[a-z0-9]+", text.lower())

    def vector_search(self, query):
        """Rank every Chunk by meaning. Return (ids best first, {id: similarity})."""
        return self.search_repository.rank_by_meaning(query)

    def _build_bm25(self, collection):
        """Read every Chunk from the Index and build the BM25 index from them."""
        version = self.chroma_db.INDEX_VERSION
        ids, texts = self.search_repository.all_texts()
        bm25 = BM25Okapi([self.tokenize(text) for text in texts]) if ids else None
        self._bm25, self._bm25_ids = bm25, ids
        self._bm25_version = version
        self._bm25_collection = collection

    def bm25_search(self, query):
        """Rank every Chunk by keywords (BM25). Return the ids, best first.

        The BM25 index is rebuilt only when the Index changed (a new version, or another Index).
        """
        collection = self.chroma_db.get_collection()
        if self.chroma_db.INDEX_VERSION != self._bm25_version or collection is not self._bm25_collection:
            self._build_bm25(collection)
        bm25, ids = self._bm25, self._bm25_ids
        if bm25 is None:
            return []
        scores = bm25.get_scores(self.tokenize(query))
        ranked = sorted(zip(ids, scores), key=lambda pair: pair[1], reverse=True)
        return [chunk_id for chunk_id, _ in ranked]

    def rrf_merge(self, ranked_a, ranked_b):
        """Reciprocal Rank Fusion: add 1 / (RRF_K + rank) for every list an id appears in. Return {id: score}."""
        scores = {}
        for ranked in (ranked_a, ranked_b):
            for rank, chunk_id in enumerate(ranked, start=1):
                scores[chunk_id] = scores.get(chunk_id, 0) + 1 / (self.settings.RRF_K + rank)
        return scores

    def search(self, query, k):
        """The top k Chunks for a query, best first: the Chunk fields plus id, text, similarity and score."""
        vector_ids, similarity = self.vector_search(query)
        scores = self.rrf_merge(vector_ids, self.bm25_search(query))
        top_ids = sorted(scores, key=scores.get, reverse=True)[:max(k, 0)]
        if not top_ids:
            return []

        by_id = self.search_repository.get_many(top_ids)
        results = []
        for chunk_id in top_ids:
            if chunk_id not in by_id:
                continue
            text, metadata = by_id[chunk_id]
            results.append({**metadata, "id": chunk_id, "text": text,
                            "similarity": similarity.get(chunk_id, 0.0), "score": scores[chunk_id]})
        return results


search_service = SearchService(settings, chroma_db, search_repository)
