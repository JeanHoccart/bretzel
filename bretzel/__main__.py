"""``python -m bretzel`` — the ``bretzel`` command, wherever Python is.

The console script lives in Python's ``Scripts`` folder, and that folder
is not always on ``PATH``: ``bretzel features`` can answer « command not
found » where ``python`` works. The module form needs nothing more than
the interpreter.
"""

from bretzel.cli.main import main

# Guarded: `bretzel describe` imports every module of the package to read
# it, and an unguarded call ran the CLI with the importer's arguments.
if __name__ == "__main__":
    raise SystemExit(main())
