"""The shared body of a navigation item — NavbarItem, SidebarItem,
BottomBarItem.

The three components are **visual variants of one behaviour**: resolve
the active state, wire the HTMX partial-nav, neutralise a disabled item,
render a badge. Only the theme and two sidebar-specific extras (the
scroll-into-view on mount, the collapsed rail's tooltip) really differ.

⚠️ This docstring is the ONLY place where the promise "these components
behave identically" is written — their docstrings lean on it. A fourth
consumer is added here, not only in the imports.

All of this lived in duplicate (audit F15, F16, F54), and the drift **had
already happened** — that is what makes the finding concrete rather than
theoretical:

- the reactive ``aria-disabled`` was written ``'true' : null`` on the
  navbar side and ``'true' : 'false'`` on the sidebar side (F88) — with
  no consequence today, a Tailwind ``aria-disabled:*`` variant only
  matching ``="true"``, but the two components would have diverged the
  day a theme selected ``aria-disabled=false``;
- the sidebar's reactive badge rendered an **empty** chip at the first
  paint, where the navbar's painted the SSR value while waiting for the
  runtime's boot, and knew how to accept a Component.

Both are reconciled here on the better of the two versions.
"""

from __future__ import annotations

import json
from typing import Any, NamedTuple

from bretzel.components.base import Component
from bretzel.components.base._wiring import bool_attr
from bretzel.core.tree import Element
from bretzel.render.context import maybe_current_context
from bretzel.runtime.protocol import outlet_id_for

# The channels through which a click can leave. A disabled item loses
# them ALL: ``href`` (browser nav), ``hx-*`` (partial swap), and the
# optimistic flip of ``current_path`` (otherwise the highlight goes out
# of sync with the URL with no navigation to reconcile it).
_CLICK_CHANNELS = (
    "href", "hx-get", "hx-target", "hx-swap", "hx-push-url", "bz-on:click",
)


def capture_layout() -> str | None:
    """The enclosing layout's name, read **at construction**.

    The ``with @layout(): …`` is still open during an item's
    ``__init__``; ``ctx.layout_stack`` is empty at ``render()`` time. So
    it is here, and nowhere else, that we can know which outlet the
    partial-nav will have to hit.

    Its ONLY consumer is :func:`apply_partial_nav`, just below — hence
    its place here rather than in three copies each of which pulled an
    import from ``bretzel.render.context`` for three lines.
    """
    ctx = maybe_current_context()
    stack = list(getattr(ctx, "layout_stack", ()) or ()) if ctx else []
    return stack[-1] if stack else None


def current_path_scope(extra: str = "") -> str:
    """The ``bz-data`` literal that declares the ``current_path`` signal.

    The "resync" half of this mechanism has always been shared
    (:func:`current_path_resync_init`); the DECLARATION, for its part,
    was copied by hand into navbar, sidebar (twice, by concatenation) and
    bottom_bar. Yet the key is load-bearing: :func:`apply_partial_nav`
    writes ``current_path = "…"`` as a bare identifier, and the resync
    compares ``current_path !== p``. A rename in a single copy killed
    THAT nav's highlighting in silence.

    ``extra`` adds the component's own fields (the sidebar puts its
    ``open`` and the three fields of its rail tooltip there).
    """
    base = "current_path: window.location.pathname"
    return "{ " + (f"{base}, {extra}" if extra else base) + " }"


class NavItemWiring(NamedTuple):
    """What :func:`wire_nav_item` resolved — the behaviour, not the render.

    ``tag`` and ``attrs`` are ready to be set on the root ``Element``;
    the other fields are the already-read values, so the caller composes
    its children without re-reading ``_reactive_values``.
    """

    tag: str
    attrs: dict[str, Any]
    #: ``Any``, not ``str``: ``label`` is a textual slot, so it carries
    #: ``str | ClientBinding | Component``. Annotating it ``str`` had as
    #: its counterpart a ``str(...)`` at read time, which shipped a
    #: Component's Python repr into the page — on ALL THREE nav items at
    #: once, since this body is shared.
    label: Any
    href: Any
    color: str
    disabled: bool
    badge_value: Any
    badge_binding: Any


def wire_nav_item(item: Component, slots: dict[str, Any]) -> NavItemWiring:
    """The prologue of a nav item's ``render()`` — reading + wiring.

    The three items (Navbar / Sidebar / BottomBar) had exactly these 45
    lines, identically: the eight reads of values and bindings, the
    choice of tag, the resolution of the two class strings,
    ``emit_attrs``, then the three ``apply_*``. What really sets them
    apart begins AFTER — the composition of the children, and two
    sidebar extras.

    ⚠️ It is not aesthetics: this module's header tells how this
    duplication has **already drifted twice** (the reactive
    ``aria-disabled`` written two ways, the reactive badge that painted
    an empty chip on one side only). The third copy arrived with
    ``bottom_bar``.

    The order of the three ``apply_*`` is the one from before, and it
    matters: ``apply_disabled`` comes LAST because it removes the click
    channels the previous two have just set.
    """
    values = item._reactive_values
    bindings = item._binding_metadata

    label = values.get("label") or ""
    href = values.get("href")
    color = values.get("color") or "primary"
    disabled = bool(values.get("disabled"))
    disabled_binding = bindings.get("disabled")

    # An anchor if the item navigates, the component's default tag otherwise.
    tag = "a" if href else item._tag

    # ``bz-class`` only adds/removes what its expression produces — the
    # static ``class=`` is never touched. The base classes therefore live
    # in ``class=`` alone, the expression carries only the active layer.
    base_class = slots.get("root", "")
    active_class = slots.get("active", "")

    attrs: dict[str, Any] = item.emit_attrs()
    attrs["class"] = base_class

    apply_active_state(
        attrs,
        active_binding=bindings.get("active"),
        active_value=values.get("active"),
        href=href,
        base_class=base_class,
        active_class=active_class,
    )
    apply_partial_nav(
        attrs, href=href, captured_layout=item._captured_layout,
    )
    apply_disabled(
        attrs,
        disabled=disabled,
        disabled_path=(
            item.path_of(disabled_binding)
            if disabled_binding is not None else None
        ),
    )
    return NavItemWiring(
        tag=tag, attrs=attrs, label=label, href=href, color=color,
        disabled=disabled, badge_value=values.get("badge"),
        badge_binding=bindings.get("badge"),
    )


def is_external_href(href: Any) -> bool:
    """An href that leaves the site — never partial-nav'd.

    HTMX would XHR-fetch the external host (blocked by CORS) and the
    click would fail in silence.
    """
    return bool(href) and (
        "://" in href or href.startswith(("mailto:", "tel:"))
    )


def apply_active_state(
    attrs: dict[str, Any],
    *,
    active_binding: Any,
    active_value: Any,
    href: Any,
    base_class: str,
    active_class: str,
) -> None:
    """Set the active state on ``attrs`` — three sources, in order.

    1. explicit binding → reactive ``bz-attr:data-active``;
    2. literal boolean → static ``data-active``;
    3. ``None`` (auto) → reactive comparison with ``current_path``, the
       signal the Navbar / Sidebar owns in its ``bz-data``.

    The data-attr expressions are **stringified** ternaries on purpose:
    ``bz-attr`` REMOVES the attribute on a bare ``false``, and the
    theme's ``data-[active=false]:hover:*`` styles need the literal
    string (cf. traps.md § stringified data-attrs).

    ``bz-class`` only adds/removes the classes its expression produces —
    the static ``class=""`` emitted by the server is never touched. The
    expression therefore carries ONLY the active layer (do not repeat the
    base classes in it).
    """
    active_js = json.dumps(active_class)
    if active_binding is not None:
        expr = active_binding.binding_path()
        attrs["bz-attr:data-active"] = bool_attr(expr)
        attrs["bz-class"] = f"({expr}) ? {active_js} : ''"
    elif active_value is True:
        attrs["data-active"] = "true"
        attrs["class"] = f"{base_class} {active_class}".strip()
    elif active_value is False:
        attrs["data-active"] = "false"
    elif href:
        # Auto: ``/`` must match ONLY the root, not every path starting
        # with ``/``.
        #
        # Everything constant AT RENDER is evaluated here, in Python, not
        # 186 times per page in the browser: ``href !== '/'`` compares
        # two literals whose verdict the server already knows, and
        # ``href + '/'`` is a concatenation of constants. The expression
        # goes from ~150 to ~62 characters, and it is copied onto three
        # attributes per entry (cf. todo.md § sidebar).
        #
        # The ``current_path !== '/'`` guard disappears with them, and it
        # is safe: it only protected the ``href == '/'`` case, now
        # handled by its own branch. For any other href,
        # ``'/'.startsWith('/text/')`` is already false.
        if href == "/":
            condition = "(current_path === '/')"
        else:
            condition = (
                f"(current_path === {json.dumps(href)} || "
                f"current_path.startsWith({json.dumps(href + '/')}))"
            )
        attrs["bz-attr:data-active"] = bool_attr(condition)
        attrs["bz-class"] = f"{condition} ? {active_js} : ''"
        attrs["bz-attr:aria-current"] = f"{condition} ? 'page' : null"


def apply_partial_nav(
    attrs: dict[str, Any],
    *,
    href: Any,
    captured_layout: Any,
) -> None:
    """Wire the HTMX outlet swap when the item carries an href AND a
    layout was captured.

    With no layout, the link falls back to a plain anchor (full reload,
    which is correct). An external href keeps ``target=_blank`` + the
    security ``rel`` pair.
    """
    if not href:
        return
    if captured_layout and not is_external_href(href):
        attrs["href"] = href
        attrs.setdefault("hx-get", href)
        attrs.setdefault("hx-target", f"#{outlet_id_for(captured_layout)}")
        attrs.setdefault("hx-swap", "morph:innerHTML")
        attrs.setdefault("hx-push-url", "true")
        # Optimistic feedback: flip ``current_path`` synchronously so
        # the highlight moves on the click, before the round trip. The
        # item has no ``bz-data`` of its own, so the expression resolves
        # (and writes) in the parent's scope. A bare identifier, with no
        # ``this.`` — in a directive, ``this`` would be the DOM element.
        attrs.setdefault("bz-on:click", f"current_path = {json.dumps(href)}")
        return
    attrs["href"] = href
    if is_external_href(href):
        attrs.setdefault("target", "_blank")
        attrs.setdefault("rel", "noopener noreferrer")


def apply_disabled(
    attrs: dict[str, Any],
    *,
    disabled: bool,
    disabled_path: str | None,
) -> None:
    """Neutralise the item — a11y, tab order, click channels.

    The theme dresses the locked state entirely through the
    ``aria-disabled:*`` variants (``opacity-50``, ``cursor-not-allowed``,
    ``pointer-events-none``), so flipping that single attribute changes
    the appearance AND the interactivity.

    Two complementary layers:

    - ``disabled_path`` (a binding) → ``bz-attr:`` directives so the
      runtime follows the changes with no server round trip;
    - ``disabled`` (the SSR snapshot) → a static lock, including the
      stripping of the click channels, so an item born disabled does not
      navigate before the runtime boots.

    Stripping ``href`` / ``hx-*`` stays SSR-only: the routes are
    design-time, re-baking them on the client would fight the partial-nav
    engine. Once the binding turns true, **it is the runtime base layer
    that blocks** — ``$bz._inert`` derives the inertness from
    ``aria-disabled="true"`` alone and refuses the click, native
    navigation and the server action (``02_directives.js`` +
    ``05_bridge.js``). No stale ``hx-get`` can leave.

    ⚠️ Two versions of this docstring lied before this one, in two
    opposite directions, and that is worth keeping: the first described
    ``pointer-events-none`` as always present — it was, in ``root``, and
    that was the bug (on the same element as ``cursor-not-allowed`` it
    cancels the cursor); the second announced a ``locked_live`` class set
    here, an intermediate solution that left the cursor dead in the
    reactive case. Both disappeared when inertness became a property of
    the base layer.
    """
    if disabled_path is not None:
        # Stringified ternary: on a bare false boolean, ``bz-attr``
        # would remove the attribute instead of writing ``"false"``.
        attrs["bz-attr:aria-disabled"] = bool_attr(disabled_path)
        attrs["bz-attr:tabindex"] = f"({disabled_path}) ? '-1' : null"
    if disabled:
        attrs.setdefault("aria-disabled", "true")
        attrs["tabindex"] = "-1"
        for channel in _CLICK_CHANNELS:
            attrs.pop(channel, None)


def render_badge(
    value: Any,
    slot_class: str,
    *,
    reactive_path: str | None = None,
) -> Element:
    """A nav item's badge chip.

    Accepts a Component (rendered as is, the slot class merged into its
    attrs) or a scalar (rendered as a small chip).

    With ``reactive_path`` (the JS path of a ``ClientBinding`` carried by
    the ``badge`` prop), the chip becomes a live counter: ``bz-text``
    writes the current value there and ``bz-show`` folds it away when the
    count is falsy (0 / "" / null) — a "0 unread" disappears instead of
    showing a stale zero. The SSR value still paints the first frame
    before the runtime boots.
    """
    if isinstance(value, Component):
        Component._detach_from_parent(value)
        node = value.render()
        if isinstance(node, Element):
            extra = (
                {"bz-text": reactive_path, "bz-show": reactive_path}
                if reactive_path is not None else {}
            )
            return Component.with_slot_class(node, slot_class, **extra)

    # ── Scalar → a REAL chip ─────────────────────────────────────────
    # Deferred import: ``primitives`` is below ``navigation`` in the DAG,
    # but importing it at the top would pull the badge module in on every
    # nav load for a case that only happens at render. (The base layer
    # allows the import; it is the cost we avoid.)
    #
    # The navigation families' ``badge`` slots are only positioners; the
    # Badge component provides the chip's look. ``error`` + ``xs``: red
    # is the unread-counter idiom, and ``xs`` does not grow a 36px nav
    # row. A caller who wants something else passes a full
    # ``ui.badge(...)`` — that is the Component branch above, and the
    # framework's two-tier contract (magic by default, escape hatch for
    # the 20 %).
    if value is not None:
        from bretzel.components.feedback.badge import Badge

        pill = Badge(str(value), color="error", size="xs")
        Component._detach_from_parent(pill)
        node = pill.render()
        if isinstance(node, Element):
            extra = (
                {"bz-text": reactive_path, "bz-show": reactive_path}
                if reactive_path is not None else {}
            )
            return Component.with_slot_class(node, slot_class, **extra)

    # Null value: the empty wrapper stays, it carries the ``bz-show``
    # that will make it appear when the binding fills.
    attrs: dict[str, Any] = {"class": slot_class}
    if reactive_path is not None:
        # ``bz-text`` owns the textContent at runtime: the SSR child is
        # only the first paint's scaffolding (omitted when there is no
        # SSR value, to avoid a flash of an empty chip).
        attrs["bz-text"] = reactive_path
        attrs["bz-show"] = reactive_path
    return Element(tag="span", attrs=attrs, children=())


__all__ = [
    "apply_active_state",
    "NavItemWiring",
    "capture_layout",
    "current_path_scope",
    "current_path_resync_init",
    "apply_disabled",
    "apply_partial_nav",
    "is_external_href",
    "render_badge",
    "wire_nav_item",
]


def current_path_resync_init() -> str:
    """``bz-init`` that keeps ``current_path`` stuck to the real URL.

    The ``current_path`` scope (which Navbar and Sidebar each own in
    their ``bz-data``) drives the active highlighting. A click on an item
    flips it optimistically, but **anything that navigates otherwise**
    would leave it stale: the browser's back/forward, and a partial nav
    triggered elsewhere in the page (a sidebar item when a navbar is
    mounted beside it, an in-page link).

    Two listeners, then: ``popstate`` and ``htmx:after-request`` — the
    second covers both success AND the error rollback in one handler
    (htmx skips ``hx-push-url`` on 4xx/5xx, so the URL is already back
    when we re-read it).

    ⚠️ They go through ``$bz.helpers.onWindow``: ``bz-on:`` listens on
    the ELEMENT and has no ``.window`` modifier. ``popstate`` only fires
    on window, and an htmx event triggered outside the component never
    walks up through it.

    ⚠️ The compare-then-assign guard is not cosmetic: without it, EVERY
    htmx event on the page would re-evaluate every item's
    ``bz-attr:data-active`` / ``bz-class`` — an O(N) reactive cascade for
    nothing.

    Both sources are necessary to keep the highlighting in sync with the
    URL, including after a history navigation.
    """
    guard = (
        "const p = window.location.pathname; "
        "if (current_path !== p) { current_path = p; } "
    )
    return (
        f"$bz.helpers.onWindow('popstate', () => {{ {guard}}}); "
        f"$bz.helpers.onWindow('htmx:after-request', () => {{ {guard}}})"
    )
