"""python -m src.api [--host 0.0.0.0] [--port 8000]: run the API with uvicorn."""
import argparse

import uvicorn


def main() -> None:
    parser = argparse.ArgumentParser(description="Run The Librarian API.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    # One worker: each worker loads its own copy of the index and reranker.
    uvicorn.run("src.api.main:app", host=args.host, port=args.port, workers=1)


if __name__ == "__main__":
    main()
