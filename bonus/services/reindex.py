"""POST /bonus/reindex: rebuild the Index on demand, when the Watcher missed a change."""
from p1.services.indexer import indexer_service


class ReindexService:
    def __init__(self, indexer_service):
        # debug: indexer_service is the p1 indexer. reindex() calls its index_all.
        self.indexer_service = indexer_service

    def reindex(self):
        """Make the Index match the Target Project. Return how many Chunks it holds."""
        # debug: TARGET_DIR is /workspace. index_all reconciles every indexable file, then drops
        # Chunks whose file is gone. Unchanged text is not embedded again.
        # return == {"chunks": N}, N is the collection size afterwards. The collection is not wiped.
        return {"chunks": self.indexer_service.index_all()}


reindex_service = ReindexService(indexer_service)
