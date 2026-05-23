import uvicorn

if __name__ == "__main__":
    # Start the server and configure the reload option to ONLY watch the 'app' directory.
    # This prevents the SQLite database updates in 'data/cache.db' or logging updates
    # in 'logs/rag.log' from triggering infinite Uvicorn reload loops.
    uvicorn.run(
        "app.main:app",
        host="127.0.0.1",
        port=8000,
        reload=True,
        reload_dirs=["app"]
    )
