"""The passes every component node undergoes after its ``render()``."""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any

from bretzel.components.base.attrs import (
    ANCHOR_ATTRS,
    ANCHOR_TAGS,
    ComponentUsageError,
)
from bretzel.components.base.client_wiring import ClientWiring
from bretzel.components.base.focus import stamp_autofocus
from bretzel.components.base.nodes import stamp_display_none
from bretzel.core.tree import Element, FragmentNode, Node
from bretzel.runtime.protocol import (
    BZ_ATTR_PREFIX,
    BZ_CLASS_PREFIX,
    BZ_SHOW_PREFIX,
    DATA_BZ_BUSY,
)
from bretzel.state.scopes.client import ClientBinding

if TYPE_CHECKING:
    from bretzel.components.base.component import Component


def _ensure_scope_identity(component: Component, node: Node) -> Node:
    """Stamp a STABLE ``id`` / ``bz-id`` on a rendered root that carries a
    ``bz-data`` scope but no id yet.

    Overlays (Tooltip / Select / Dropdown / Popover / …) build their
    ``bz-data`` inside ``render()`` — *after* ``emit_attrs`` ran, so
    ``_needs_identity`` (which runs during ``emit_attrs``) never saw the
    scope and emitted no id. The runtime then assigns a counter-based
    ``bz-id`` that CHANGES on every re-render. Inside a ``@refreshable``
    that re-keys the scope Map each refresh : the element's reused signals
    are dropped, and any teleported panel (still subscribed to the old
    signal) decouples — a tooltip stops showing / hiding after the first
    swap (cf. ``traps.md``).

    ``component.id`` is allocated in ``__init__`` and is position-stable
    across re-renders, so stamping it keeps the scope continuous and lets
    idiomorph match the element. No-op when an id is already present.
    """
    if not isinstance(node, Element):
        return node
    if node.attrs.get("id") or "bz-data" not in node.attrs:
        return node
    cid = component.id
    if not cid:
        return node
    return Element(
        tag=node.tag,
        attrs={**node.attrs, "id": cid, "bz-id": cid},
        children=node.children,
    )


#: A WIDTH utility, variants included.
#:
#: The variant prefix (``md:``, ``dark:hover:``…) is captured so that
#: only two declarations of the SAME scope conflict: an ``md:w-1/2``
#: passed by the caller must not erase the theme's base ``w-full``,
#: otherwise the component would lose its width below the breakpoint.
#:
#: ``max-w-`` / ``min-w-`` are excluded **naturally**: with the variants
#: removed, their base starts with ``max-w-`` / ``min-w-``, not ``w-``.
#: That is the right behaviour and not a happy accident — they are other
#: CSS properties, which compose with ``width`` instead of contradicting
#: it.
_WIDTH_UTILITY = re.compile(r"^(?P<variants>(?:[^\s:]+:)*)!?w-")


def _width_scopes(classes: str) -> set[str]:
    """The variant scopes for which ``classes`` sets a width."""
    scopes: set[str] = set()
    for token in classes.split():
        match = _WIDTH_UTILITY.match(token)
        if match:
            scopes.add(match.group("variants"))
    return scopes


def _drop_widths(existing: str, scopes: set[str]) -> str:
    """Remove from ``existing`` the widths redeclared in ``scopes``."""
    if not scopes:
        return existing
    kept = [
        token
        for token in existing.split()
        if not ((match := _WIDTH_UTILITY.match(token)) and match.group("variants") in scopes)
    ]
    return " ".join(kept)


def _append_attr(node: Element, key: str, value: str) -> Element:
    """Clone ``node`` with ``value`` appended to its ``key`` attribute.

    Append, not prepend — the caller's value lands AFTER whatever the theme
    composed. (That's why this isn't ``Component.with_slot_class``, which
    prepends by contract so a child's own classes stay last.) ``Element``
    is immutable, hence the clone.

    **The order inside the ``class`` attribute decides nothing.** What
    settles two competing Tailwind utilities is their order in the
    generated sheet. When the incoming value declares a width, those of
    the same scope are REMOVED from the existing one. The conflict is
    resolved in the HTML, where we control it, instead of being delegated
    to a sheet order we do not control. The rule holds for ``class``
    only — the other attributes are concatenated as-is.
    """
    existing = str(node.attrs.get(key, ""))
    if key == "class" and existing:
        existing = _drop_widths(existing, _width_scopes(value))
    return Element(
        tag=node.tag,
        attrs={**node.attrs, key: f"{existing} {value}" if existing else value},
        children=node.children,
    )


def _reject_unknown_slot_keys(component: Component, user_slots: Mapping[str, Any]) -> None:
    """Croak on a ``slots={…}`` key this component has no slot for.

    ``"root"`` is always valid — ``_apply_universal_modifiers`` applies it
    to the true root whatever the component does. Any other key only means
    something if the component's resolved theme declares that slot ; a key
    outside that set can never reach the DOM, so accepting it silently is
    the same class of defect this whole item closes. Typos
    (``slots={"pannel": …}``) and wrong-component copy-paste both land here.

    Reads the RESOLVED theme (not ``cls.THEME``) so an app-level
    ``Theme(components=…)`` override that renames slots is honoured rather
    than fought — safe to call from ``__init__``, it falls back to
    ``cls.THEME`` when no render context is active.

    ⚠️ Being a KNOWN slot is not the same as being HONOURED : a component
    that composes a non-root slot by hand can still drop the override in
    silence. This function only rules out keys that could never mean
    anything."""
    known = set(component._resolved_theme().get("slots", {}))
    unknown = [k for k in user_slots if k != "root" and k not in known]
    if not unknown:
        return
    name = type(component).__name__
    available = ", ".join(sorted(known)) or "(none — root only)"
    raise ComponentUsageError(
        f"{name}(slots=…) got {unknown!r}, which {name} has no slot for, "
        f"so the override would silently do nothing. Available slots : "
        f"{available}. Use slots={{'root': '…'}} to restyle the outer "
        f"element, or classes='…' to append cosmetic classes to it."
    )


def finish_render(component: Component, node: Node) -> Node:
    """The two passes EVERY component node must undergo after its
    ``render()``, in order.

    1. **``_ensure_scope_identity``** — ``id`` / ``bz-id`` when a
       ``bz-data`` scope must survive the morph.
    2. **``_apply_universal_modifiers``** — ``classes=``, ``style=``,
       ``visible=``, ``tooltip=``, ``slots={"root"}`` and the raw
       classes, on the TRUE root whatever slot composed it.

    Why it is a function and not the closure's body
    -----------------------------------------------
    A parent that **rebuilds** its children instead of calling their
    ``render()`` bypasses the metaclass wrap — and therefore the two
    passes: ``ui.toggle_button(..., classes=…, style=…,
    slots={"root": …})`` inside a ``ui.toggle_group`` would lose **all
    three**, because ``ToggleGroup`` calls ``child._render_button(...)``.

    As a function, the "I rebuild my child" path can end at the same
    obligatory crossing as the normal path. There is ONE place that
    describes what "rendering a component" means, and both paths go
    through it.
    """
    # ⚠️ HERE, and not in `compose_class`: components whose steps are
    # multi-slot dicts resolve their size themselves and never go through
    # that branch. A partial validation is WORSE than none: it makes the
    # behaviour depend on the component. `finish_render` is the only
    # point every render goes through.
    from bretzel.components.base.theme_values import refuse_a_value_off_the_table

    refuse_a_value_off_the_table(component)

    node = _ensure_scope_identity(component, node)
    return _apply_universal_modifiers(component, node)


def _refuse_stray_anchor_attrs(component: Component, node: Node) -> None:
    """A link attribute the caller put on an element that is not a link.

    ``href`` / ``target`` / ``rel`` / ``download`` are admitted as raw
    kwargs because ``tag="a"`` makes them legitimate — but on a
    ``<button>`` or a ``<div>`` they do NOTHING, and nothing says so: a
    ``ui.icon_button(href=…)`` would render a dead ``<button href>``. Checked
    here because it is the first place that knows the rendered tag.
    Components that take ``href=`` as their OWN parameter consume it
    before this point; only what the caller slipped through is judged.
    """
    if not isinstance(node, Element) or node.tag in ANCHOR_TAGS:
        return
    stray = sorted(ANCHOR_ATTRS & component._raw_attrs.keys())
    if stray:
        name = type(component).__name__
        raise ComponentUsageError(
            f"{name} renders a <{node.tag}>, where {', '.join(stray)} does "
            f"nothing — the element would not be a link. Use a component "
            f"that takes `href=` (ui.button, ui.icon_button, ui.link, "
            f"ui.card…), or `tag=\"a\"` if an anchor is really meant."
        )


def statically_hidden(component: Component) -> bool:
    """``visible=False`` — literal, or a server state's stamped bool.

    Such a component is NOT THERE: it attaches to no parent (``__init__``)
    and renders nothing (``_apply_universal_modifiers``). Attaching it
    anyway would not be neutral — a parent that draws its children itself
    would compose around the hole: the breadcrumb would keep the
    separator, the stepper would number 1, 3, the scheduler would keep the
    event's lane, the resizable group would read the attributes of an
    empty node and raise. A ``visible=`` bound to a ``ClientState`` is
    not static: it stays attached and becomes ``bz-show``.
    """
    visible = component._visible
    return visible is False or (
        getattr(visible, "_is_bound_bool", False) and not visible)


def _apply_universal_modifiers(component: Component, node: Node) -> Node:
    """Apply ``classes`` / ``visible`` / ``tooltip`` modifiers to a
    freshly-rendered component node. Called by the metaclass wrap around
    every concrete component's ``render()``. Returns the (possibly
    transformed) node ; most components carry none of these so this is a
    fast no-op."""

    # ── visible = False, literal or a state's stamped bool (an int) ─────
    if statically_hidden(component):
        return FragmentNode(children=())

    _refuse_stray_anchor_attrs(component, node)
    if not component._auto_busy and isinstance(node, Element):  # ``loading=False``
        node = Element(node.tag, {**node.attrs, DATA_BZ_BUSY: "off"}, node.children)

    # ── The colour BRIDGE: bz-c-<colour> on the true root ─────────────
    # Here and not in ``compose_class`` for the reason that already moved
    # ``classes=`` and ``slots={"root"}`` up: a component whose root is
    # composed by ANOTHER slot, or which builds its ``class=`` by hand,
    # does not go through the composer.
    from bretzel.components.base.theme_values import root_color_bridge

    if (bridge := root_color_bridge(component, node)) is not None:
        node = _append_attr(node, "class", bridge)

    # ── Universal slots={"root": …} : land on the component's TRUE root ─
    # Same reason as ``classes=`` below. Any component whose root is
    # composed by another slot, or which reads ``theme["slots"]["root"]``
    # by hand (ToggleGroup does), would otherwise drop the user's override
    # in silence, for a public mechanism (step 5 of the composition).
    # Applied here, it reaches all of them.
    #
    # Order : the theme's own composition is already in ``class=``, the
    # override goes on top of it, and ``classes=`` goes last — so the
    # user's cosmetic classes still win, as documented. (Unknown keys are
    # rejected at ``__init__``, not here.)
    root_slot = (component._user_slots or {}).get("root")
    if root_slot and isinstance(node, Element):
        node = _append_attr(node, "class", str(root_slot))

    # ── Raw classes (``class_=`` / ``attrs={"class": …}``) ────────────
    # Same reason to be here as ``slots={"root"}`` just above: a
    # component that builds its ``class=`` by hand in ``render()`` —
    # ``attrs["class"] = " ".join(parts)``, which Card does — OVERWRITES
    # everything ``emit_attrs`` had set. Without this pass, a
    # ``ui.card(class_="c2", attrs={"class": "c3"})`` would lose both
    # without a word.
    #
    # Applied post-render, so no component can overwrite it, and
    # BEFORE ``classes=``: the documented order stays "theme, then raw,
    # then the user's cosmetic classes last".
    raw_cls = component._raw_class_str
    if raw_cls and isinstance(node, Element):
        node = _append_attr(node, "class", raw_cls)

    # ── Universal classes= : land on the component's TRUE root ────────
    # The user's extra classes belong on whatever element render() chose
    # as its root, regardless of the theme slot that composed it. Applied
    # here (post-render) so EVERY component honours ``classes=`` — not
    # only those that compose their root via the "root" slot. (The static
    # ``compose_class`` does not append them, so there's no doubling ;
    # the reactive ``classes=ClientBinding`` path stays in
    # ``apply_class_attrs`` and leaves ``_classes`` None, so this no-ops.)
    user_cls = component._user_classes_str()
    if user_cls and isinstance(node, Element):
        node = _append_attr(node, "class", user_cls)

    # ── Universal classes=ClientBinding: same root, reactive ─────────
    # ``bz-class`` accepts a plain string and — by contract — NEVER
    # touches the statically-emitted ``class=`` (it tracks the classes it
    # adds, per bind). So the theme composition survives and the binding
    # simply layers on top.
    #
    # This lives HERE, at the universal choke point, and not in
    # ``apply_class_attrs``: only 2 of ~55 components ever called that
    # helper, so the documented "bindable on every component" contract
    # held nowhere. The old emission was ``:class="…"`` — Alpine
    # syntax the V3 runtime doesn't read at all — and it dropped the
    # static ``class=`` on the way out, leaving those 2 components
    # completely unstyled. Cf. gate
    # ``tests/consistency/test_reactive_classes_universal.py``.
    if component._classes_binding is not None and isinstance(node, Element):
        node = Element(
            tag=node.tag,
            attrs={
                **node.attrs,
                BZ_CLASS_PREFIX: ClientWiring.path_of(component._classes_binding),
            },
            children=node.children,
        )

    # ── Universal style=, literal or bound : the component's TRUE root ──
    # Same story as classes= : set from ``emit_attrs``, the peer-input
    # family (Switch / Checkbox / Radio — it lands on their hidden
    # ``sr-only`` <input>) buries ``style=`` on the invisible element.
    if component._style_binding is not None and isinstance(node, Element):
        bound_style = {f"{BZ_ATTR_PREFIX}style": ClientWiring.path_of(component._style_binding)}
        node = Element(node.tag, {**node.attrs, **bound_style}, node.children)
    user_style = component._style
    if user_style and isinstance(node, Element):
        prior = str(node.attrs.get("style", "")).rstrip().rstrip(";")
        merged_style = f"{prior}; {user_style}" if prior else str(user_style)
        node = Element(
            tag=node.tag,
            attrs={**node.attrs, "style": merged_style},
            children=node.children,
        )

    # ── visible = ClientBinding | ClientExpression : bz-show (V3) ─────
    # ``ClientExpression`` inherits from ``ClientBinding`` so a single
    # ``isinstance`` would treat compound expressions the same as a bare
    # field reference and double-prefix the JS with ``$bz.state.``,
    # corrupting the directive. Detect the expression case first and
    # emit its already-complete JS verbatim ; only the bare field path
    # gets the ``$bz.state.`` prefix. FOUC : when the binding's SSR
    # value is falsy, pre-stamp ``display:none`` so nothing flashes
    # before the runtime's first effect.
    visible = component._visible
    if isinstance(visible, ClientBinding):
        if isinstance(node, Element):
            new_attrs = {**node.attrs}
            new_attrs[BZ_SHOW_PREFIX] = ClientWiring.path_of(visible)
            # ``getattr(…, "value", True)`` — defensive ON PURPOSE: a
            # ClientExpression has no ``.value`` (nothing to evaluate
            # server-side), so no FOUC guard for it. An accepted limit,
            # not an oversight: there is no correct SSR value for an
            # expression computed on the client.
            if not getattr(visible, "value", True):
                stamp_display_none(new_attrs)
            node = Element(tag=node.tag, attrs=new_attrs, children=node.children)
        # FragmentNode / TextNode root : no place to hang a directive, silently
        # ignore. Rare in practice — primitive leaves like ``TextNode`` rarely
        # get a ``visible=binding`` ; users wrap them in a parent.

    # ── autofocus=True — BEFORE the tooltip wrap, whose span would carry it
    if component._autofocus and isinstance(node, Element):
        node = stamp_autofocus(component, node)

    # ── tooltip wrap : the wrapper was pre-built at __init__ time ─────
    # (when the render context was alive — Tooltip needs id allocation
    # there). At render-time we just inject the freshly-rendered node
    # as its trigger child and call ``.render()``. The base
    # ``_render_one`` dispatcher accepts a raw ``Node`` so the
    # pre-rendered Element drops in cleanly.
    wrapper = component._tooltip_wrapper
    if wrapper is not None:
        wrapper._children = [node]
        node = wrapper.render()

    return node
