"""``Outlet`` — page-content injection point inside an ``@layout``.

The outlet is the only thing that bridges a layout's frame and the
page's body :

- The :func:`bretzel.render.decorators.layout.layout` decorator marks
  a function as a layout.
- At render time, the pipeline runs the layout first (which calls
  ``ui.outlet()`` once or more), finds the Outlet instances in the
  resulting tree, and feeds the page's children into them.
- The outlet renders a ``<main id="outlet_<layout>">`` whose ``id``
  doubles as the htmx swap target — clicks on internal links land
  inside this element without re-rendering the whole layout.

Auto-id : when no explicit ``id=`` is passed, the outlet derives it
from the active layout name on the render context (``ctx.layout``).
A custom suffix can be passed via ``id="left"`` to support multiple
outlets in the same layout (``outlet_<layout>_left``).

⚠️ **Full-height layout: the outlet passes on NO constraint.**

The ``<main>`` is an ordinary block, with no height and no ``flex``. A
page that wants to fill the screen and scroll an INTERNAL zone (chat,
mailbox, dashboard) must therefore wire the chain by hand, on TWO links
— the outlet's parent **and** the outlet ::

    with ui.container(classes="flex-1 min-h-0 overflow-hidden flex flex-col"):
        ui.outlet(classes="flex-1 min-h-0 flex flex-col")

    # then, in the page:
    with ui.vstack(classes="flex-1 min-h-0"):
        ...
        with ui.vstack(classes="flex-1 min-h-0 overflow-y-auto"):  # ← scrolls

Both are necessary: ``ui.container`` is a ``block``, so its child cannot
take ``flex-1`` without the ``flex flex-col``.

**The failure mode is silent**, and that is what makes it expensive:
without these classes, the internal zone grows with its content instead
of overflowing, the ``overflow-y-auto`` never has anything to do, and
the excess is simply clipped by an ancestor. Measured on 2026-08-15 by
mounting ``examples/chat``: ``<main>`` at 1,888 px in an 855 px parent,
no scrollbar, no error. Gate:
``tests/runtime_js/test_full_height_layout_scrolls.py``.

Why it is not fixed in the component: baking these classes in would
change every existing layout, and ``display:contents`` — which would
make the slot really transparent — risks dropping the ``<main>``'s ARIA
landmark depending on the browser. To settle when the shell is
redesigned; the work is in ``.claude/work/todo.md``.

"""

from __future__ import annotations

from typing import Any, ClassVar

from bretzel.components.base import Component
from bretzel.core.tree import Element
from bretzel.render.context import maybe_current_context
from bretzel.runtime.protocol import outlet_id_for


def _derive_outlet_id(
    explicit_id: str | None,
) -> str:
    """Return the outlet's HTML ``id`` attribute value.

    The base form is ``outlet_<layout-name>``, where ``<layout-name>``
    is the innermost layout function currently being rendered. If a
    non-empty ``explicit_id`` is passed we append it as a suffix
    (``outlet_<layout>_<suffix>``) so a single layout can host
    multiple outlets. When no layout is active and no suffix was
    passed we fall back to a plain ``outlet`` — the component still
    renders, the ``id`` is just less informative.
    """
    ctx = maybe_current_context()
    layout_stack = list(getattr(ctx, "layout_stack", ()) or ()) if ctx else []
    base = outlet_id_for(layout_stack[-1]) if layout_stack else "outlet"
    if explicit_id:
        return f"{base}_{explicit_id}"
    return base


class Outlet(Component):
    """``<main>`` slot where the page content lands inside a layout."""

    DEFAULT_TAG: ClassVar[str] = "main"
    BINDABLE_PROPS: ClassVar[tuple[str, ...]] = ()
    def __init__(
        self,
        id: str | None = None,
        **kwargs: Any,
    ) -> None:
        # Resolve the outlet's id NOW (still inside the layout's
        # ``with`` block, where ``ctx.layout_stack`` is populated).
        # The base ``Component.__init__`` accepts this ``id`` via the
        # explicit-id branch and stops auto-numbering.
        derived = _derive_outlet_id(id)
        super().__init__(id=derived, **kwargs)
        self._explicit_suffix = id

    @property
    def child_scope_id(self) -> str:
        """The id the page's children take as their parent.

        **It DIVERGES from ``self.id``, and that is the whole
        mechanism.** The outlet renders a stable id — htmx sends it back
        as ``HX-Target``, so moving it would break the next partial
        navigation. But what the PAGE builds beneath must be unique to
        the page: without that, ``/accordion`` and ``/markdown`` emit the
        same ``outlet_shell_container_0_…_accordion_0``, and the
        runtime's scope store — a ``Map`` indexed by that string, which
        an ``hx-boost`` does not empty — gives the second the first's
        state.

        Measured on 2026-08-13: 13 collisions over the playground's 68
        pages. Cf. ``RenderContext.page_scope``.
        """
        ctx = maybe_current_context()
        return f"{self.id}{ctx.child_scope_root}" if ctx else self.id

    # ── Render ─────────────────────────────────────────────────────────

    def render(self) -> Element:
        attrs = self.emit_attrs()
        # The outlet always carries its own ``id`` (not auto-numbered
        # — _derive_outlet_id baked it). Make sure ``emit_attrs``
        # didn't drop it because the ``_needs_identity`` heuristic
        # said no (no bindings / events / raw directives on this
        # element).
        attrs["id"] = self.id
        attrs.setdefault("data-bz-outlet", "1")
        # NO reveal-gate (``bz-show`` + ``display:none``) : the outlet is
        # server-rendered content, idiomorph morphs it in place on a swap.
        # A gate keyed on "outlet WAS the swap target" would break nested
        # layouts — a partial-nav swap targets the OUTERMOST outlet, so an
        # inner sub-layout outlet never gets the event → stays hidden →
        # sub-page renders BLANK. Cf. ``traps.md`` § "Nested partial-nav
        # blanks the inner outlet".
        children = self._render_children()
        return Element(tag=self._tag, attrs=attrs, children=children)


__all__ = ["Outlet"]
