"""Lets `python -m src.retrieval ...` work as the CLI entry point.

Running `python -m src.retrieval.retriever` directly triggers a
RuntimeWarning: importing the `src.retrieval` package (to get here at all)
already imports retriever.py once via __init__.py's re-exports, then -m
tries to import it a second time as __main__, and Python warns that a
module already in sys.modules is being re-executed. Routing through this
separate __main__.py file avoids that: the package import and the "module
being run as a script" are two different modules, as normal.
"""
from .retriever import main

if __name__ == "__main__":
    main()
