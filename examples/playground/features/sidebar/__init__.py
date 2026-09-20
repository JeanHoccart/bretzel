"""The Sidebar feature — the bench's public API.

Exports only what ``app/routes.py`` needs. The state, the handlers and
the panels stay private to the package.
"""

from examples.playground.features.sidebar.state import PATH
from examples.playground.features.sidebar.ui import page

__all__ = ["PATH", "page"]
