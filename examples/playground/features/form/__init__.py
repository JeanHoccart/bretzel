"""Form feature — public API for the playground.

Only exports what ``app/routes.py`` needs to mount the feature
(``PATH`` + ``page`` function). Internal symbols (state classes,
handlers, refreshable cards, render helpers) stay private to the
package.
"""

from examples.playground.features.form.ui import page

PATH = "/form"

__all__ = ["PATH", "page"]
