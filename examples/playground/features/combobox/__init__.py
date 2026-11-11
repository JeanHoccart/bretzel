"""Combobox feature — public API for the playground.

Only exports what ``app/routes.py`` needs to mount the feature
(``PATH`` + ``page``). Split into a package on 2026-11-05, when the
``creatable=`` card took the single file past the 900-line threshold
(playground-pattern.md § 7).
"""

from examples.playground.features.combobox.ui import page

PATH = "/combobox"

__all__ = ["PATH", "page"]
