"""Structural types used by the render layer.

The render layer needs to talk about *the app* (its theme, its
registered pages, its state backend) without importing the concrete
:class:`bretzel.server.app.Bretzel` class — that would close the
import loop ``server → render → server``.

We expose a :class:`~typing.Protocol` describing the subset of the
app's surface that render actually uses. The :class:`Bretzel` class
satisfies it structurally, and ``tests/unit/render/test_types.py``
checks that at RUNTIME — the protocol is ``runtime_checkable``, so the
test asserts ``isinstance`` both ways (a complete fake passes, an
incomplete one fails).

⚠️ This paragraph used to promise something else : that ``mypy
--strict`` validated the conformance « through an explicit
``BretzelApp = Bretzel`` assignment in ``tests/integration/
conformance.py`` ». Neither the file nor the assignment has ever
existed anywhere in the repo — it announced a static guarantee nobody
had.

"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from bretzel.state.persistence.base import Backend
    from bretzel.theme import Theme  # noqa: F401  # forward, real module in Layer 4


@runtime_checkable
class BretzelApp(Protocol):
    """The slice of ``Bretzel`` the render pipeline depends on.

    Defined here so :func:`render_page` & friends can type-annotate
    their ``app`` parameter without dragging the server layer up the
    dependency DAG. Concrete implementations live elsewhere ; this
    Protocol is the contract.
    """

    # ── Resolved configuration / resources ──────────────────────────────

    @property
    def theme(self) -> object:
        """The configured :class:`bretzel.theme.Theme`. Render reads
        ``theme.get_palette()`` and ``theme.get_component_theme(name)``.

        Typed as ``object`` here to keep the Protocol importable from
        any layer (``Theme`` lives one layer up, in Layer 4)."""
        ...

    @property
    def state_backend(self) -> Backend:
        """The persistent backend bound at startup (memory or Redis)."""
        ...

    @property
    def debug(self) -> bool:
        """``True`` when running under ``bretzel dev`` / debug mode.
        Affects ID hashing, error pages, source-map emission."""
        ...

    # ── Registries populated by ``Bretzel.include`` ─────────────────────

    _pages: list[Callable[..., object]]
    _error_handlers: dict[int, Callable[..., object]]

    # SSE broker — populated at startup ; ``None`` in test rigs that
    # don't go through the full lifecycle. Public read-only accessor.
    @property
    def sse_broker(self) -> object | None:
        ...
