"""Lets `python -m src.generation ...` work as the CLI entry point (same
reason as src/retrieval/__main__.py: avoids the double-import RuntimeWarning)."""
from .answer import main

if __name__ == "__main__":
    main()
