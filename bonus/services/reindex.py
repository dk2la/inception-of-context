"""POST /bonus/reindex: rebuild the Index on demand, when the Watcher missed a change."""
from p1.services.indexer import indexer_service


class ReindexService:
    def __init__(self, indexer_service):
        self.indexer_service = indexer_service

    def reindex(self):
        """Make the Index match the Target Project. Return how many Chunks it holds."""
        return {"chunks": self.indexer_service.index_all()}


reindex_service = ReindexService(indexer_service)
