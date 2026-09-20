"""The Diagram feature — the bench's public API.

Exports only what ``app/routes.py`` needs. The state, the handlers and
the panels stay private to the package.
"""

from examples.playground.features.diagram.ui import page

PATH = "/diagram"

__all__ = ["PATH", "page"]
