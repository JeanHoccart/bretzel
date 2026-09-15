"""``@app.middleware`` — register a user-defined middleware.

Two acceptable shapes :

- **Async callable** : ``async def fn(request, call_next): ...`` —
  Starlette's ``BaseHTTPMiddleware.dispatch`` signature.
- **Class** : a class that exposes an async ``__call__`` (or a
  ``BaseHTTPMiddleware`` subclass) ; instantiated once per request
  by Starlette.

"""

from __future__ import annotations

import inspect
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from bretzel.render.types import BretzelApp


def middleware(app: BretzelApp, target: Callable[..., Any] | type) -> Callable[..., Any] | type:
    """Append ``target`` to the app's user-middleware list.

    The actual stack-build happens at startup (after Bretzel's own
    middlewares are installed), so the registration order here
    matches the wrap order : first registered = outermost.
    """
    if not (inspect.iscoroutinefunction(target) or inspect.isclass(target)):
        raise TypeError(
            "@app.middleware expects an async callable or a class with "
            f"an async __call__ ; got {type(target).__name__}."
        )
    middlewares: list[Any] = getattr(app, "_user_middlewares", None) or []
    middlewares.append(target)
    app._user_middlewares = middlewares  # type: ignore[attr-defined]
    return target
