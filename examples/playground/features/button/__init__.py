"""Button feature — public API for the playground.

Only exports what ``app/routes.py`` needs to mount the feature
(``PATH`` + ``page`` function). Internal symbols (state classes,
handlers, refreshable panels, render helpers) stay private to the
package.
"""

from examples.playground.features.button.ui import page

PATH = "/button"

__all__ = ["PATH", "page"]
