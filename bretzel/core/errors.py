"""Layer 0 — the canonical framework exceptions.

``BretzelError`` lives here (not in ``server/`` or ``state/``) so that
*every* layer can raise **and** catch the same class without violating
the import DAG (``core < state < runtime < render < theme < components
< server``). A backend in ``state/persistence`` and the action
dispatcher in ``server/routing`` must agree on one error type ; the only
module both may import is ``core``.

The exceptions are defined once here and re-exported by higher layers.
``tests/consistency/test_one_name_one_object.py`` guards this identity.
"""

from __future__ import annotations


class BretzelError(RuntimeError):
    """Generic runtime error from Bretzel internals.

    Always carries a human-readable message. The server layer registers
    a FastAPI exception handler for this class and the action dispatcher
    catches it, rendering the ``500`` error page (message kept in debug,
    stripped in production). Any layer that needs to signal a
    framework-level failure raises this — the state persistence backends
    included.
    """


class AuthRequiredError(RuntimeError):
    """Raised when a ``user``-scoped state is resolved with no user.

    Deliberately **not** a :class:`BretzelError` subclass : the action
    dispatcher's ``except BretzelError`` means "framework bug → 500", and
    an anonymous visitor touching ``UserState`` is a 401, not a bug.

    Deliberately **not** a Starlette ``HTTPException`` either : this class
    lives in Layer 0, which the state layer imports and which must stay
    free of any HTTP dependency. The mapping to a 401 response is the
    server layer's job — ``server/routing/errors.py`` registers a handler
    for this class, so both the page path and the action path answer 401
    without either of them knowing about the other.
    """
