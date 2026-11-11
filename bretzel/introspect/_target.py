"""``module:attribute`` → the object it names. The one reader.

Every entry point that takes an application takes it the way the ASGI
runners do (``uvicorn my_app.main:app``): ``bretzel dev``, ``bretzel
features`` / ``impact`` / ``translations``, ``bretzel check --deep`` and
:mod:`bretzel.probe`. They all read it here, so an app that is not
installed (a uv "virtual" project) loads under every one of them, and a
missing attribute is said in the same words.

It lives HERE because ``introspect`` is the lowest layer the three may
import: ``lint`` and ``probe`` must not import each other
(``.importlinter``: ``lint-stays-extractable``, ``probe-is-tooling``),
and ``introspect`` sits under both.
"""

from __future__ import annotations

import importlib
import os
import sys
from pathlib import Path

#: What every entry point accepts. Aligned with the ASGI runners.
TARGET_SYNTAX = "module:attribute  (e.g. `examples.kanban.main:app`)"


def load_target(target: str) -> tuple[object, Path]:
    """Import ``module:attribute`` and return ``(object, module file)``.

    The file anchors what a caller reports on something openable.

    It calls nothing: a Bretzel app's ``include()`` runs at the module's
    import, so the features and the routables already exist when the
    object does. Starting the server is the caller's business.

    Raises :class:`ValueError` for a target that is not
    ``module:attribute`` or a module without that attribute. An
    ``ImportError`` from the module itself propagates: it is the app's
    own error, and the traceback is what its author needs.
    """
    module_name, _, attribute = target.partition(":")
    if not module_name or not attribute:
        raise ValueError(f"invalid target `{target}` — expected {TARGET_SYNTAX}.")
    # As the ASGI runners do: the app's own directory first. An app that
    # is not installed (a uv "virtual" project) would not be found without
    # PYTHONPATH=.
    if os.getcwd() not in sys.path:
        sys.path.insert(0, os.getcwd())
    module = importlib.import_module(module_name)
    origin = Path(getattr(module, "__file__", "") or f"<{module_name}>")
    try:
        return getattr(module, attribute), origin
    except AttributeError:
        exported = [n for n in vars(module) if not n.startswith("_")]
        raise ValueError(
            f"`{module_name}` does not expose `{attribute}`. "
            f"Available: {sorted(exported)[:10]}."
        ) from None
