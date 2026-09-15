"""``DatePicker`` test-bench package.

Re-exports the minimal API ``routes.py`` needs : ``PATH`` and
``page``. Everything else (state classes, handlers, panels) lives in
the sub-modules so the file split per
``playground-pattern.md`` § 7 stays clean.
"""

from examples.playground.features.date_picker.ui import PATH, page

__all__ = ["PATH", "page"]
