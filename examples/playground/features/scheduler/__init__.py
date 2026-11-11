"""Scheduler feature — public API for the playground.

Only exports what ``app/routes.py`` needs to mount the feature
(``PATH`` + ``page`` function).
"""

from examples.playground.features.scheduler.ui import page

PATH = "/scheduler"

__all__ = ["PATH", "page"]
