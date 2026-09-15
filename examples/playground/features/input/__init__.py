"""Input feature — public API for the playground.

Only exports what ``app/routes.py`` needs to mount the feature
(``PATH`` + ``page`` function). Internal symbols (state classes,
handlers, refreshable panels, render helpers) stay private to the
package.
"""

from examples.playground.features.input.ui import page

PATH = "/input"

__all__ = ["PATH", "page"]
