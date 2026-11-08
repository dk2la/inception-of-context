from ioc_api.retriever import Retriever, tokenize


def test_tokenize_splits_identifiers():
    toks = tokenize("NoteService.by_tag(storageItem)")
    assert {"noteservice", "note", "service", "by_tag", "tag", "storageitem", "storage", "item"} <= set(toks)


def test_exact_identifier_ranks_first(ctx):
    ctx.indexer.full_sync()
    r = Retriever(ctx.store, ctx.embedder)
    hits = r.search("where is by_tag used?", k=3)
    assert hits[0]["symbol"] == "NoteService.by_tag"
    assert all({"score", "vector_score", "bm25_score", "text", "path"} <= set(h) for h in hits)
    assert len(r.search("search notes", k=50)) <= ctx.store.count()
    assert r.search("   ", k=3) == []


def test_bm25_follows_index_changes(ctx, target):
    ctx.indexer.full_sync()
    r = Retriever(ctx.store, ctx.embedder)
    assert r.search("frobnicate", k=1)[0]["symbol"] != "frobnicate"
    (target / "extra.py").write_text("def frobnicate(x):\n    return x * 2\n")
    ctx.indexer.index_file("extra.py")
    assert r.search("frobnicate", k=1)[0]["symbol"] == "frobnicate"
