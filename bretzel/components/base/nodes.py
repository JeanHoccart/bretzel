"""Small helpers that build or adjust rendered nodes."""

from __future__ import annotations

from collections.abc import Iterable
from typing import TYPE_CHECKING, Any, Final

from bretzel.components.base.attrs import (
    ComponentUsageError,
)
from bretzel.core.tree import Element, Node, TextNode

if TYPE_CHECKING:
    pass


# Attributes whose several sources COMPOSE instead of overwriting. They
# have list semantics: two classes is both classes; two style
# declarations is both.
_COMPOSABLE_ATTRS: Final[dict[str, str]] = {"class": " ", "style": "; "}


def merge_attr(attrs: dict[str, Any], name: str, value: Any) -> None:
    """Set ``value`` on ``attrs[name]`` **per the precedence contract**.

    The contract, in one sentence: *nothing the user writes disappears
    silently*.

    - ``class`` / ``style`` **compose** — each source is added to the
      previous one, in application order (theme, then raw attrs, then the
      universal layer, which therefore comes last and wins a Tailwind
      conflict).
    - everything else **overwrites** — an element has only one ``id``,
      one ``role``, one ``name``.

    Why it exists: left to the order of the ``attrs.update``, the same
    collision on a ``ui.card(id=…, classes=…, class_=…, attrs={…},
    style=…)`` resolves differently from one pair of sources to the next,
    and a user input can disappear without a word.
    """
    if value is None:
        return
    sep = _COMPOSABLE_ATTRS.get(name)
    existing = attrs.get(name)
    if sep is None or not existing or not isinstance(existing, str) or not isinstance(value, str):
        attrs[name] = value
        return
    # Composable AND both sides are strings: we concatenate, without
    # duplicating a value already present (a component recomposing its
    # slot must not make ``class=`` swell).
    if value in existing.split(sep.strip() or None):
        return
    attrs[name] = f"{existing}{sep}{value}"


def stamp_display_none(attrs: dict[str, Any]) -> None:
    """Append ``display:none`` to an attrs dict's inline ``style``.

    The V3 FOUC strategy: the server pre-stamps
    the hidden state of every ``bz-show`` whose initial evaluation is
    falsy, so nothing flashes before the runtime's first effect takes
    over. Appending (rather than replacing) preserves any style the
    component already emitted. Public — every component port that
    emits a ``bz-show`` branch uses it.
    """
    existing = str(attrs.get("style", "")).rstrip().rstrip(";")
    attrs["style"] = f"{existing}; display:none" if existing else "display:none"


def coerce_children(rendered: Any) -> tuple[Node, ...]:
    """Normalise what a `render=` escape hatch returned, into children.

    The other end of the contract for components rendering a COLLECTION:
    the component owns the wrapper (a cell's ``<td>``, a breadcrumb's
    ``<a href>``, its ``aria-current``), the author fills the BODY. This
    function is the crossing from one to the other, and it accepts the
    four shapes a callback can return:

    - ``None`` → no children. The component keeps its wrapper empty
      rather than displaying ``"None"``.
    - a :class:`Component` → **detached then rendered**, through
      :meth:`Component.render_detached`. It is the half of the contract
      one forgets: a Component built in the callback's body registers
      itself with the active parent, so without the detachment it renders
      TWICE — once here, once as a sibling. Gated by
      ``test_render_never_orphans``.
    - an already-built :class:`Node` → passed through as-is.
    - everything else → ``str()`` inside a :class:`TextNode`.

    This shared behaviour lives in ``base/`` so that components from
    several families can use it without a cross-cutting import.
    """
    from bretzel.components.base.component import Component

    if rendered is None:
        return ()
    if isinstance(rendered, Component):
        return (Component.render_detached(rendered),)
    if isinstance(rendered, Node):
        return (rendered,)
    return (TextNode(str(rendered)),)


def reject_component(
    value: Any,
    *,
    owner: str,
    prop: str,
    because: str,
    instead: str,
) -> None:
    """Refuse a Component on a parameter that is NOT a slot.

    The other half of the contract :meth:`Component.emit_text_slot`
    carries just above: a textual slot accepts ``str | ClientBinding |
    Component``, but not every textual parameter is a slot. A source to
    parse (``markdown.text``), a markup string (``ui.html.content``),
    data serialised as JSON (``file_upload.accept``), or a text that
    **doubles as an HTML attribute** — an ``aria-label`` carries only a
    string, so a Component there would be announced to the screen reader
    under its Python ``repr``.

    The refusal is a **legitimate** state of the contract, on one
    condition: that it be said. Before this function, those parameters
    fell into a ``str(value)`` and shipped ``<bretzel…object at 0x…>``
    into the page, or crashed deep in ``escape_html`` on ``'TextNode'
    object has no attribute 'replace'`` — an error with no visible
    relation to what the author had written.

    ``because`` says what the parameter really is, ``instead`` says what
    to compose with in its place. Both are mandatory: a refusal that does
    not explain reads as a framework bug, and the
    ``test_text_slot_contract_universal`` gate requires the message to
    name the parameter and justify.

    Raised at CONSTRUCTION, never at render — that is
    :class:`ComponentUsageError`'s contract ("raised at instantiation
    time") and the only way a component built then dropped by a
    conditional branch still surfaces the fault.

    The function lives next to :class:`Component`, available in lexical
    scope, and does not depend on the discipline proper to bindings.
    """
    from bretzel.components.base.component import Component

    if not isinstance(value, Component):
        return
    raise ComponentUsageError(
        f"{owner} does not accept a Component for ``{prop}=`` — {because} "
        f"It is not a content slot: pass a string. {instead}"
    )


def el(tag: str, attrs: dict[str, Any] | None = None, children: Iterable[Any] = ()) -> Element:
    """Tiny ergonomic wrapper around :class:`bretzel.core.tree.Element`.

    Components don't have to use it — building :class:`Element` directly
    is just as good — but the helper accepts a loose iterable for
    children and auto-wraps bare strings in :class:`TextNode`, which is
    what most ``render()`` bodies want anyway.
    """
    from bretzel.components.base.component import Component

    coerced: list[Node] = []
    for c in children:
        if c is None:
            continue
        if isinstance(c, Node):
            coerced.append(c)
        elif isinstance(c, Component):
            coerced.append(c.render())
        elif isinstance(c, str):
            coerced.append(TextNode(c))
        else:
            raise ComponentUsageError(f"el(): unsupported child type {type(c).__name__}")
    return Element(tag=tag, attrs=attrs or {}, children=tuple(coerced))
