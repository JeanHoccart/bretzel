"""``Pagination`` — page-navigation widget.

Renders a ``<nav>`` strip of buttons : *Prev* — page numbers — *Next*,
with ellipsis when the page count exceeds ``max_visible``. The page
list is computed in JavaScript from ``value`` / ``total_pages`` /
``max_visible``, so user code that wires ``value=client_state.page``
gets live re-rendering on every state mutation, no server round-trip.
Only ``value`` (two-way) and ``disabled`` are bindable ; ``total_pages``
/ ``max_visible`` are server-/design-time.

A ``compute_range`` Python function ports the same algorithm —
useful for unit tests, server-side pre-renders, and any caller that
wants to mirror the visible window without parsing JS.

Form integration : do NOT declare ``AUTONAME_FROM``: it is **derived**
from ``names_field=True`` on the prop, and an explicit declaration now
raises (cf. the metaclass's guard) so a bound ``value=state.page``
produces ``name="page"`` automatically. A hidden
``<input type="hidden">`` rides the page number into form data, with
the change handler relocated onto it so the dispatcher reads ``name``
+ ``value`` off the input (the root ``<nav>`` has neither — cf.
``traps.md`` § "bz-event:change on a div"). The relocated handler is
either the native HTMX action set (``hx-post`` + ``hx-trigger`` + …,
for a callable ``on_change``) or ``bz-on:change`` (for a string
``on_change``).

Translation ``total_items / page_size → total_pages`` is the
caller's job. The component is UI-pure : it shows N pages and fires
``change`` when the user picks one. The synthetic ``change`` dispatch
lives on a reactive ``bz-effect`` on the hidden input, not in
``setActive`` — a bz-data method has no ``$refs`` / ``$nextTick``.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any, ClassVar

from bretzel.components.base import Component, reactive_prop
from bretzel.components.base._wiring import (
    coerce_index,
    hidden_carrier_attrs,
    server_sync_marker,
    theme_context,
)
from bretzel.components.base._wiring import (
    pop_change_handler as _pop_change_handler,
)
from bretzel.components.navigation.pagination.theme import PAGINATION_THEME
from bretzel.components.primitives.icon import Icon
from bretzel.core.tree import Element, TextNode
from bretzel.render import text

# ───────────────────────────────────────────────────────────────────────────
# Pure range computation — exposed for tests, SSR, custom pickers
# ───────────────────────────────────────────────────────────────────────────


def compute_range(
    active: int, total_pages: int, max_visible: int
) -> list[int | str]:
    """Return the page list to display, with ``"ellipsis"`` markers.

    Examples ::

        compute_range(1, 10, 7)  → [1, 2, 3, 4, 5, "ellipsis", 10]
        compute_range(5, 10, 7)  → [1, "ellipsis", 4, 5, 6, "ellipsis", 10]
        compute_range(10, 10, 7) → [1, "ellipsis", 6, 7, 8, 9, 10]
        compute_range(3, 5, 7)   → [1, 2, 3, 4, 5]   # no ellipsis

    The algorithm clamps ``max_visible`` to a minimum of 5 so the
    layout always has at least ``[1, …, mid, …, last]`` worth of
    slots. The same logic is mirrored in the ``range()`` method inside
    the component's ``bz-data`` — ``compute_range`` is the
    canonical Python reference both sides agree on.
    """
    slots = max(5, max_visible)
    if total_pages <= slots:
        return list(range(1, total_pages + 1))
    side = slots // 2
    show_left = active > side + 1
    show_right = active < total_pages - side
    if not show_left:
        return list(range(1, slots - 1)) + ["ellipsis", total_pages]
    if not show_right:
        return [1, "ellipsis"] + list(
            range(total_pages - (slots - 3), total_pages + 1)
        )
    middle = slots - 4
    start = active - middle // 2
    return (
        [1, "ellipsis"]
        + list(range(start, start + middle))
        + ["ellipsis", total_pages]
    )


# ───────────────────────────────────────────────────────────────────────────
# bz-data template — JS port of compute_range + setActive helper
# ───────────────────────────────────────────────────────────────────────────


def _build_bz_data(
    *,
    scope_key: str,
    has_local_value: bool,
    initial_value: int,
    binding_path: str | None,
    total_pages_expr: str,
    max_visible_expr: str,
    disabled_expr: str,
    server_synced: bool,
) -> str:
    """The instance's ``bz-data``: **data, not code**.

    The algorithm (``range`` / ``current`` / ``setActive`` / …) lives
    once in ``$bz.pagination.scope``
    (``bretzel/runtime/_src/15_pagination.js``). Here we emit only the
    state and the configuration.

    Before that switch, this builder serialised the full JS port of
    ``compute_range`` into EVERY instance — 957 bytes, the repository's
    biggest ``bz-data`` — with the config **baked into the method
    bodies** (``totalPages() {{ return Math.max(1, +(10) || 1); }}``).
    That is precisely what made factoring impossible: two paginations of
    different sizes produced two different CODES instead of two states.

    ``_read`` / ``_write`` cover both modes with the same scope methods —
    the local ``value`` field or the store cell. No ``get value()``:
    ``scope.absorb`` invokes each key at registration and would freeze
    the getter (cf. traps.md).

    ⚠️ ``disabled`` leaves as a **method override**, not as a field. The
    "config as data" move (112fb527) had converted it to ``_disabled:
    <expression>`` — yet a field is evaluated once, outside any effect,
    and ``absorb`` wraps its snapshot in a signal decoupled from the
    store: the binding was dead at mount. Only literals support the
    field shape; a bound expression must live in a method body (same
    mechanics as the Slider's ``_disabledState``).

    ⚠️ ``_total`` / ``_maxVisible`` are fields AND must be **re-seeded**.
    That is where the first fix stopped too early: "they are always
    server-side literals, so real data" confuses LITERAL and CONSTANT.
    They are literals that change at every server render — and
    ``absorb`` NEVER rewrites an existing signal (``03_scope.js``,
    "NEVER reset existing values"). Without declaring them in
    ``_serverSync``, the page count and the window width stayed frozen
    at their first mount's value, for life: the server returned 16, the
    scope answered 20.

    Contrast with ``value``: that one is re-seeded ONLY if the server
    owns it, otherwise a neighbouring refresh would erase the client's
    click. The server always owns the configuration; it only owns the
    value if it comes from a state.
    """
    # The config is ALWAYS re-seedable; the value only when the server
    # is its source.
    sync_keys = ["_total", "_maxVisible"]
    if has_local_value and server_synced:
        sync_keys.insert(0, scope_key)
    sync = server_sync_marker(*sync_keys, enabled=True)

    if has_local_value:
        state = f"{scope_key}: {initial_value},{sync} "
        read_write = (
            f"_read() {{ return this.{scope_key}; }},"
            f"_write(v) {{ this.{scope_key} = v; }},"
        )
    else:
        assert binding_path is not None
        state = f"{sync.lstrip()} "
        read_write = (
            f"_read() {{ return {binding_path}; }},"
            f"_write(v) {{ {binding_path} = v; }},"
        )

    # Overrides the slab's ``isDisabled() { return false; }`` constant
    # only when the lock exists — a ``false`` literal has nothing more to
    # say than the default.
    disabled_override = (
        f"isDisabled() {{ return !!({disabled_expr}); }},"
        if disabled_expr != "false"
        else ""
    )

    return (
        "{...$bz.pagination.scope,"
        + state
        + read_write
        + disabled_override
        + f"_total: {total_pages_expr},"
        + f"_maxVisible: {max_visible_expr}"
        + "}"
    )


# ───────────────────────────────────────────────────────────────────────────
# Pagination component
# ───────────────────────────────────────────────────────────────────────────


class Pagination(Component):
    """Page navigation : *Prev* — N page buttons — *Next*."""

    THEME: ClassVar[dict[str, Any]] = PAGINATION_THEME
    THEME_KEY: ClassVar[str] = "pagination"
    DEFAULT_TAG: ClassVar[str] = "nav"
    IS_CONTAINER: ClassVar[bool] = False
    # Curated reactive surface — current page (two-way) + lock. The user
    # drives ``value`` by clicking ; ``disabled`` gates from client state.
    # ``total_pages`` only changes when the server's result count changes
    # → ``@refreshable`` re-renders it, no client driver, so it stays
    # static per the bindable-surface rule (cf.
    # ``.claude/bretzel/client-reactive-surface.md`` § The rule).
    BINDABLE_PROPS: ClassVar[tuple[str, ...]] = ("value", "disabled")
    # Same cut as Stepper and Carousel — a bounded index is driven by
    # ``set`` + the two directions. No ``first`` / ``last``: ``set(1)``
    # and ``set(total_pages)`` already say them, and a prop (or a method)
    # must earn its place.
    IMPERATIVE: ClassVar[tuple[str, ...]] = ("set", "next", "prev")
    EVENTS: ClassVar[tuple[str, ...]] = ("change",)

    # All reactive props honour the universal contract :
    # literal | server-resolved | ClientBinding.
    value: Any = reactive_prop(default=1, emit_attr=False, writes=True, names_field=True)
    total_pages: Any = reactive_prop(default=1, emit_attr=False)
    max_visible: Any = reactive_prop(default=7, emit_attr=False)
    disabled: bool = reactive_prop(default=False, emit_attr=False)
    color: str = reactive_prop(default="primary", emit_attr=False)
    size: str = reactive_prop(default="md", emit_attr=False)
    # Form-input name lands on the hidden input below ; consumed by
    # the dispatcher to key the form payload sent with ``change``
    # events. Autoname kicks in via ``AUTONAME_FROM = "value"`` when
    # ``value=`` is a ClientBinding ; pass ``name=`` explicitly for
    # literal-valued paginations that still need a server handler.
    name: str | None = reactive_prop(default=None, emit_attr=False)

    def __init__(
        self,
        *,
        value: Any = None,
        total_pages: Any = None,
        max_visible: Any = None,
        disabled: bool | None = None,
        color: str | None = None,
        size: str | None = None,
        name: str | None = None,
        on_change: Callable[..., Any] | str | None = None,
        **kwargs: Any,
    ) -> None:
        # Direct forward: the base layer drops reactive None kwargs (keeps the default).
        super().__init__(
            value=value,
            total_pages=total_pages,
            max_visible=max_visible,
            disabled=disabled,
            color=color,
            size=size,
            name=name,
            on_change=on_change,
            **kwargs,
        )

    # ── Imperative API ─────────────────────────────────────────────────
    #
    # Ordinary CLASS methods: none of these three names shadows a
    # ``reactive_prop``, and the ``test_imperative_classvar_is_complete``
    # gate only reads a ClassDef's public methods — attributes assigned
    # in ``__init__`` would be invisible to it (cf. the same note in
    # ``stepper.py``).

    def set(self, page: int) -> str:
        """Go to page ``page``. Write-through if there is a binding."""
        return self._value_command(coerce_index(page, default=1))

    def next(self) -> str:
        # Always the dispatch, binding or not: "the next page" is
        # computed from the LIVE value and bounded by ``totalPages()``.
        # The server knows neither at render — a write-through would have
        # to bake ``page + 1`` and would overrun.
        return self._dispatch_command("bz-next")

    def prev(self) -> str:
        return self._dispatch_command("bz-prev")

    # ── Render ─────────────────────────────────────────────────────────

    def render(self) -> Element:
        _theme, _slots, sizes, size_key, _color = theme_context(self)
        size_map = sizes.get(size_key, sizes.get("md", {}))

        # ── Resolve each prop to (alpine_expr, raw_initial) ──────────
        value_binding = self._binding_metadata.get("value")
        total_pages_binding = self._binding_metadata.get("total_pages")
        disabled_binding = self._binding_metadata.get("disabled")

        # Initial values for SSR fallback + local bz-data field.
        initial_value = coerce_index(
            self._reactive_values.get("value"), default=1
        )
        # A local ``value=state.page`` carries a ``field_name`` stamp — the
        # server is authoritative, so the ``value`` field opts into
        # ``_serverSync`` (re-adopted on a @refreshable morph, else
        # idiomorph keeps the stale client page). A plain literal has no
        # stamp and stays client-owned. Same gate as Tabs / Select.
        value_server_backed = self._value_server_backed("value")
        initial_total = coerce_index(
            self._reactive_values.get("total_pages"), default=1
        )
        initial_max_visible = coerce_index(
            self._reactive_values.get("max_visible"), default=7
        )
        initial_disabled = bool(self._reactive_values.get("disabled"))

        # Runtime expressions — the binding path when bound, a
        # literal otherwise. ``value_binding_path`` is consumed by
        # ``_build_bz_data`` to wire the active read / write target ;
        # ⚠️ The other values leave as DATA (``_total`` /
        # ``_maxVisible`` / ``_disabled``); the methods live once in
        # ``$bz.pagination.scope`` and read ``this._total``. This comment
        # announced the expression baked INTO the method body until
        # 2026-08-01 — that is precisely the old shape ``_build_bz_data``
        # describes as gone, just above.
        value_binding_path = (
            self.path_of(value_binding) if value_binding is not None else None
        )
        total_pages_expr = (
            self.path_of(total_pages_binding)
            if total_pages_binding is not None
            else str(initial_total)
        )
        # ``max_visible`` is NOT in BINDABLE_PROPS — the constructor
        # rejects any binding on it, so ``max_visible_binding`` is always
        # None (no reactive branch).
        max_visible_expr = str(initial_max_visible)
        disabled_expr = (
            self.path_of(disabled_binding)
            if disabled_binding is not None
            else ("true" if initial_disabled else "false")
        )

        # ``bz-attr:value`` on the hidden input mirrors the active page —
        # the binding path when bound, the local scope field otherwise.
        # Both resolve through the runtime's scope wrap, so the bare key
        # reads the local signal in local mode.
        (scope_key,) = self._scope_keys("value")
        value_expr = value_binding_path or scope_key

        # ── Build the bz-data state ──────────────────────────────────
        bz_data = _build_bz_data(
            scope_key=scope_key,
            has_local_value=value_binding is None,
            initial_value=initial_value,
            binding_path=value_binding_path,
            total_pages_expr=total_pages_expr,
            max_visible_expr=max_visible_expr,
            disabled_expr=disabled_expr,
            server_synced=value_server_backed,
        )

        # ── Static class composition ─────────────────────────────────
        item_class = " ".join(
            p
            for p in (
                self.compose_class(
                    "item",
                    apply_variant_size_modifiers=False,
                ),
                size_map.get("item", ""),
            )
            if p
        )
        nav_class = " ".join(
            p
            for p in (
                self.compose_class(
                    "item",
                    apply_variant_size_modifiers=False,
                ),
                size_map.get("item", ""),
                self.compose_class(
                    "nav",
                    apply_variant_size_modifiers=False,
                ),
                size_map.get("nav", ""),
            )
            if p
        )
        active_class = self.compose_class(
            "active", apply_variant_size_modifiers=False
        )
        ellipsis_class = " ".join(
            p
            for p in (
                self.compose_class(
                    "ellipsis",
                    apply_variant_size_modifiers=False,
                ),
                size_map.get("ellipsis", ""),
            )
            if p
        )

        # ── Prev / Next chevron buttons ──────────────────────────────
        # ``current()`` / ``isDisabled()`` / ``totalPages()`` are V3
        # methods (no object-literal getters) — call them.
        prev_btn = _chevron_button(
            cls=nav_class,
            click="setActive(current() - 1)",
            disabled_expr="isDisabled() || current() <= 1",
            aria_label=text("pagination.previous"),
            icon_name="chevron-left",
        )
        next_btn = _chevron_button(
            cls=nav_class,
            click="setActive(current() + 1)",
            disabled_expr="isDisabled() || current() >= totalPages()",
            aria_label=text("pagination.next"),
            icon_name="chevron-right",
        )

        # ── N item buttons ──────────────────────────────────────────
        # Static slots, each one reads ``range()[i]`` from the bz-data
        # method. Using static buttons (vs ``bz-for``) avoids the morph +
        # loop-clone churn — these slots are bound once and just swap
        # their content.
        #
        # ⚠️ N is ``min(slots, total_pages)``, NOT ``slots``. The window
        # cannot grow on the client side: ``total_pages`` is not in
        # ``BINDABLE_PROPS`` (the constructor refuses a binding on it),
        # so ``_total`` is a constant baked at render — and
        # ``compute_range`` ALWAYS returns exactly ``min(slots,
        # total_pages)`` entries, whatever the active page, including out
        # of bounds. Checked exhaustively on max_visible ∈ [0,15] ×
        # total_pages ∈ [1,79] × active ∈ [-2, tp+2], and the
        # ``test_pagination_emits_no_dead_slot`` gate replays that
        # equality.
        #
        # What left before: up to three extra buttons, each 1,069 B of
        # classes and directives, to stay invisible FOR LIFE — the
        # runtime bound them at every scan all the same. And since the
        # length is exactly N, no emitted slot can be ``undefined``: the
        # ``bz-show="range()[i] !== undefined"`` that guarded the surplus
        # has nothing left to guard, so it goes with them.
        # ``max(0, …)`` and not ``max(1, …)``: a ``total_pages=0`` (or
        # negative — ``coerce_index`` sets no floor) must render ZERO
        # slots. A floor of 1 left an empty and VISIBLE button there,
        # since the ``bz-show`` that hid it went away with the surplus.
        n_slots = min(max(5, initial_max_visible), max(0, initial_total))
        item_nodes: list[Element] = []
        # The bz-class binding layers active / ellipsis on top of the
        # static item base (the runtime tracks the dynamic set separately
        # from the SSR ``class=``). JSON-encoding the templates keeps any
        # embedded quote safe in the expression — loop-invariant, so
        # encode once outside the slot loop.
        active_js = json.dumps(active_class)
        ellipsis_js = json.dumps(ellipsis_class)

        # The server KNOWS the window — it has ``compute_range``,
        # tested and mirror-tested against the JS port. It did not use
        # it: the slots left EMPTY and the numbers only appeared once the
        # JS had run (measured: ``['', '', '', '', '', '', '']``). Hence
        # a blank first paint, and nothing at all without JS, on the
        # repository's only component whose JS decides which controls
        # exist.
        #
        # So we seed the TEXT on the server side. The text only:
        # ``bz-text`` overwrites the content entirely, so seeding and
        # recomputing give the same result. The ``active`` / ``ellipsis``
        # classes, for their part, stay exclusively dynamic —
        # ``bz-class`` can no longer remove a token present in the static
        # ``class=`` (a protected baseline), so an active chip seeded in
        # SSR would stay stuck on its page.
        ssr_range = compute_range(
            initial_value, initial_total, initial_max_visible
        )

        for i in range(n_slots):
            p = f"range()[{i}]"
            slot = ssr_range[i] if i < len(ssr_range) else None
            ssr_text = "…" if slot == "ellipsis" else (
                "" if slot is None else str(slot)
            )
            cls_expr = (
                f"({p} === current() ? {active_js} : '') + ' ' + "
                f"({p} === 'ellipsis' ? {ellipsis_js} : '')"
            )
            item_nodes.append(
                Element(
                    tag="button",
                    attrs={
                        "type": "button",
                        "class": item_class,
                        "bz-class": cls_expr,
                        "bz-on:click": f"setActive({p})",
                        "bz-attr:disabled": (
                            f"{p} === 'ellipsis' || isDisabled()"
                        ),
                        "bz-attr:aria-current": (
                            f"{p} === current() ? 'page' : null"
                        ),
                        "bz-attr:aria-label": (
                            f"{p} === 'ellipsis' "
                            "? 'ellipsis' : 'Page ' + " + p
                        ),
                        "bz-text": (
                            f"{p} === 'ellipsis' ? '…' : {p}"
                        ),
                    },
                    children=(TextNode(ssr_text),) if ssr_text else (),
                )
            )

        # ── Hidden input — form integration + change source ──────────
        # The dispatcher reads name + value off the source element of a
        # ``change`` event ; the wrapper <nav> has neither, so we
        # relocate the change handler onto a hidden input that tracks
        # ``value`` via ``bz-attr:value`` (cf. ``traps.md``).
        root_attrs = self.emit_attrs()
        root_attrs.setdefault("role", "navigation")
        root_attrs.setdefault("aria-label", "Pagination")

        # Relocate the change handler from the root <nav> down onto the
        # hidden input. ``emit_attrs`` stamps either the native HTMX
        # action set (callable ``on_change`` → ``hx-post`` +
        # ``hx-trigger`` + …) or ``bz-on:change`` (string ``on_change``).
        # ``_pop_change_handler`` lifts whichever keys are present so the
        # populated ``name`` + ``value`` of the input back the FormData.
        relocated_change = _pop_change_handler(root_attrs)

        name = self._reactive_values.get("name") or self._derive_field_name()

        # Render the hidden input whenever a name is in play OR the
        # change handler was relocated. Without it, the reactive change
        # dispatch has nothing to fire on and the handler never runs.
        hidden_node: Element | None = None
        if name or relocated_change:
            hidden_attrs: dict[str, Any] = {
                **hidden_carrier_attrs(value_expr, initial=str(initial_value)),
                # Reactive change dispatcher — fires ``change`` on this
                # input (where the relocated handler lives) whenever the
                # active page genuinely mutates.
            }
            if name:
                hidden_attrs["name"] = str(name)
            hidden_attrs.update(relocated_change)
            hidden_node = Element(
                tag="input", attrs=hidden_attrs, children=()
            )

        # ── Root nav element ────────────────────────────────────────
        root_attrs["class"] = self.compose_class(
            "root", apply_variant_size_modifiers=False
        )
        root_attrs["bz-data"] = bz_data
        # Reception of the imperative commands issued by an external
        # trigger (``pager.next()`` on a button elsewhere in the page).
        # The clamp and the lock are in ``setActive``, so all three
        # entries are guarded by construction.
        root_attrs["bz-on:bz-set"] = "setActive($event.detail.value)"
        root_attrs["bz-on:bz-next"] = "next()"
        root_attrs["bz-on:bz-prev"] = "prev()"

        children: list[Element] = [prev_btn, *item_nodes, next_btn]
        if hidden_node is not None:
            children.append(hidden_node)

        return Element(
            tag=self._tag, attrs=root_attrs, children=tuple(children)
        )


# ───────────────────────────────────────────────────────────────────────────
# Helpers
# ───────────────────────────────────────────────────────────────────────────


def _chevron_button(
    *,
    cls: str,
    click: str,
    disabled_expr: str,
    aria_label: str,
    icon_name: str,
) -> Element:
    """Render one of the prev/next chevron buttons.

    The :class:`Icon` is rendered eagerly (and detached from the
    parent stack so it doesn't auto-register as a sibling) since
    we're producing the tree manually inside ``render()`` rather
    than via ``with`` blocks.
    """
    icon = Icon(icon_name, size="sm")
    Component._detach_from_parent(icon)
    icon_node = icon.render()

    return Element(
        tag="button",
        attrs={
            "type": "button",
            "class": cls,
            "bz-on:click": click,
            "bz-attr:disabled": disabled_expr,
            "aria-label": aria_label,
        },
        children=(icon_node,),
    )
