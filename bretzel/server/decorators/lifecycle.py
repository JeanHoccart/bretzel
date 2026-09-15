"""``@app.startup`` / ``@app.shutdown`` decorators.

Pure markers — both append the function to a per-app list. The
:py:meth:`Bretzel._lifespan` async context manager iterates the
lists at the right moment of FastAPI's lifespan protocol.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from bretzel.render.types import BretzelApp


def startup(app: BretzelApp, fn: Callable[..., Any]) -> Callable[..., Any]:
    """Register a startup hook. Hooks fire after framework internals."""
    hooks: list[Callable[..., Any]] = getattr(app, "_startup_hooks", None) or []
    hooks.append(fn)
    # Frozen ``app`` is unusual ; tests sometimes pass a stub without
    # this list pre-attached, so we re-pin defensively.
    app._startup_hooks = hooks  # type: ignore[attr-defined]
    return fn


def shutdown(app: BretzelApp, fn: Callable[..., Any]) -> Callable[..., Any]:
    """Register a shutdown hook. Hooks fire LIFO before framework teardown."""
    hooks: list[Callable[..., Any]] = getattr(app, "_shutdown_hooks", None) or []
    hooks.append(fn)
    app._shutdown_hooks = hooks  # type: ignore[attr-defined]
    return fn
