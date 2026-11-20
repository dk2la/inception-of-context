"""Part 1: the Index and the Watcher, plus what every part shares.

    config/        settings.py: every setting
    core/          database.py (the one Chroma client), llm.py (the only call to the model)

    models/        Chunk, Event
    schemas/       response bodies of the Part 1 routes
    repositories/  chunk_repository (writing and browsing the Index), file_repository (disk), event_repository
    services/      chunker, indexer, watcher, overview
    views/         /status /files /file /chunks (overview), /events
    index.py       the console command: python -m p1.index [dir] [--watch]
"""
