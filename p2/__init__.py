"""Part 2: retrieval and answers (RAG), the API and the dashboard. Uses Part 1.

    models/        Answer
    schemas/       request and response bodies of /context and /ask
    repositories/  search_repository (reading the Index for retrieval)
    services/      search, router, ask
    views/         /context /ask (questions), / (dashboard), errors (503)
    app.py         the FastAPI app: Part 1 and Part 2 routes, the Watcher in the background
"""
