"""``ToggleGroup`` + ``ToggleButton`` — multi-button selector cluster.

A joined-button bar (filters, formatting toolbar, multi-select chip
row). Items share edges ; the selected state is a coloured bg fill
via ``data-selected="true"``.

- ``multiple=False`` (default) — value is a scalar str.
- ``multiple=True`` — value is a ``list[str]``.

*(``multiple=`` — the same word as Select / Combobox / FileUpload —
rather than shadcn's ``type="single"|"multiple"``, so the API stays
one-of-a-kind across the framework.)*

Composition pattern : children :class:`ToggleButton` instances live
inside a ``with ToggleGroup(...)`` block. The group holds the bound
``value`` and the visual configuration ; each toggle reads them at
render time and emits a ``<button data-selected="…">`` whose bz-data
expression flips an element in or out of the selection.

Shortcut : pass ``options=[(value, label), ...]`` to the constructor
to build the items in one line — the group materialises the matching
ToggleButtons internally. Mix-and-match with the container API is
**not** supported (one or the other per group).

Imperative API mirrors :class:`Combobox` :

- ``.set(value)`` — replace selection (scalar for single, list for
  multi).
- ``.clear()`` — empty selection (``""`` single, ``[]`` multi).
- ``.focus()`` / ``.blur()`` — target the first focusable item.
- ``.select_all()`` / ``.deselect_all()`` — multi only ; pick every
  ToggleButton in the group / drop every pick.

No per-item ``.add(v)`` / ``.remove(v)`` / ``.toggle(v)`` — the click
handlers already do that UI-side. Server-side mutations use
``.set(new_list)`` (or write through the bound state field directly).

The scope key is called ``value``, like the other controls. It can
coexist with the buttons' HTML ``value`` attribute: the element is
exposed as ``$el`` and does not enter the scope's chain. That contract
is guarded by
``tests/runtime_js/test_a_scope_key_survives_a_child_of_the_same_name.py``.
"""

from __future__ import annotations

import json as _json
from collections.abc import Callable
from typing import Any, ClassVar

from bretzel.components.base import Component, reactive_prop
from bretzel.components.base._wiring import (
    SERVER_ACTION_ATTRS,
    bool_attr,
    hidden_carrier_attrs,
    reject_sealed,
    server_sync_marker,
    theme_context,
    trigger_event,
    unwrap_transparent,
)
from bretzel.components.base.component import finish_render
from bretzel.components.inputs.toggle_group.theme import TOGGLE_GROUP_THEME
from bretzel.components.primitives.icon import Icon
from bretzel.core.tree import Element

# Server-action attrs relocated from the wrapper onto the hidden input
# (the element that actually fires ``change``). Single source :
# ``base/_wiring.SERVER_ACTION_ATTRS``.
_SERVER_ACTION_ATTRS = SERVER_ACTION_ATTRS


def _pop_server_action(root_attrs: dict[str, Any]) -> dict[str, Any] | None:
    """Pop the ``change``-triggered ``hx-*`` server-action bundle off
    ``root_attrs`` for re-stamping on the hidden input.

    Returns the relocated attrs, or ``None`` when no server handler is
    wired. ToggleGroup also exposes ``focus`` / ``blur`` events, but
    those stay on the root (the root carries no focusable element to
    relocate them to — they're client-string only in practice) ; only
    the ``change`` server action moves to the hidden form carrier.
    """
    # The EVENT, not the string: with a ``debounce=`` the trigger is
    # ``"change delay:300ms"``, the comparison failed, and the bundle
    # stayed on the root — a ``<div>`` that never fires ``change``. Dead
    # handler, without a word.
    if trigger_event(root_attrs) != "change":
        return None
    return {
        key: root_attrs.pop(key)
        for key in _SERVER_ACTION_ATTRS
        if key in root_attrs
    }


class ToggleGroup(Component):
    """Cluster of :class:`ToggleButton` items — single or multi-select."""

    THEME: ClassVar[dict[str, Any]] = TOGGLE_GROUP_THEME
    THEME_KEY: ClassVar[str] = "toggle_group"
    #: The author owns the loop: they open a ``with`` and place their
    #: ``ToggleButton``. ``options=`` is the simple case's shortcut and
    #: materialises the same children — it is the two-tier pattern
    #: ``Breadcrumb`` takes up. Cf. ``Component.COLLECTION_OWNER``.
    COLLECTION_OWNER: ClassVar[str | None] = "author"
    BINDABLE_PROPS: ClassVar[tuple[str, ...]] = ("value", "disabled")
    IMPERATIVE: ClassVar[tuple[str, ...]] = ("set", "clear", "focus", "blur", "select_all", "deselect_all")
    EVENTS: ClassVar[tuple[str, ...]] = ("change", "focus", "blur")

    value: Any = reactive_prop(default=None, emit_attr=False, writes=True, names_field=True)
    multiple: bool = reactive_prop(default=False, emit_attr=False)
    color: str = reactive_prop(default="primary", emit_attr=False)
    size: str = reactive_prop(default="md", emit_attr=False)
    disabled: bool = reactive_prop(default=False, emit_attr=False)
    name: str | None = reactive_prop(default=None, emit_attr=False)

    def __init__(
        self,
        *,
        value: Any = None,
        options: list[tuple[str, str]] | None = None,
        multiple: bool | None = None,
        color: str | None = None,
        size: str | None = None,
        disabled: bool | None = None,
        name: str | None = None,
        on_change: Callable[..., Any] | str | None = None,
        on_focus: Callable[..., Any] | str | None = None,
        on_blur: Callable[..., Any] | str | None = None,
        **kwargs: Any,
    ) -> None:
        # Guard: without it, an old ``type="multiple"`` would slip into
        # **kwargs → a dead HTML attribute on the <div> → a silently
        # single group.
        if "type" in kwargs:
            raise TypeError(
                "ToggleGroup(type='single'|'multiple') has been replaced "
                "by multiple=True|False — the same API as Select / "
                "Combobox / FileUpload."
            )
        # Direct forward: the base layer drops reactive None kwargs (keeps the default).
        super().__init__(
            value=value,
            multiple=multiple,
            color=color,
            size=size,
            disabled=disabled,
            name=name,
            on_change=on_change,
            on_focus=on_focus,
            on_blur=on_blur,
            **kwargs,
        )
        # ``options=`` shortcut materialises ToggleButton children at
        # construction time (still inside the ``with self:`` scope,
        # so they auto-attach as our children). Reject 3-tuples or
        # other shapes — surface the misuse explicitly.
        self._shortcut_options: list[tuple[str, str]] = []
        if options is not None:
            for i, item in enumerate(options):
                if not (isinstance(item, tuple) and len(item) == 2):
                    raise TypeError(
                        f"ToggleGroup options[{i}] must be a "
                        f"(value, label) 2-tuple — got {item!r}. "
                        f"For icons or richer items, use the "
                        f"container API : ``with ui.toggle_group(): "
                        f"ui.toggle_button(value, label, icon=...)``."
                    )
                self._shortcut_options.append(item)
            # Build the items now. They register themselves on our
            # parent_stack via Component.__init__ auto-attach.
            with self:
                for value_str, label_str in self._shortcut_options:
                    ToggleButton(value_str, label_str)

    # ── Imperative write-only API ─────────────────────────────────────

    def set(self, value: Any) -> str:
        """Write the picked value. Single → scalar str ; multi → list."""
        return self._value_command(value)

    def clear(self) -> str:
        """Empty the selection. Single → ``""`` ; multi → ``[]``."""
        is_multi = bool(self._reactive_values.get("multiple"))
        return self.set([] if is_multi else "")

    def focus(self) -> str:
        return (
            f"document.getElementById('{self.id}')"
            ".querySelector('button:not([disabled])')?.focus()"
        )

    def blur(self) -> str:
        return (
            f"document.activeElement?.closest("
            f"'#{self.id}')?.querySelector("
            f"'button:focus')?.blur()"
        )

    def select_all(self) -> str:
        """Pick every ToggleButton in the group. Multi-mode only."""
        if not self._reactive_values.get("multiple"):
            raise RuntimeError(
                "ToggleGroup.select_all() is multi-only — "
                "set multiple=True on the group first."
            )
        return self._dispatch_command("bz-select-all")

    def deselect_all(self) -> str:
        """Drop every pick. Multi-mode only (single uses .clear())."""
        if not self._reactive_values.get("multiple"):
            raise RuntimeError(
                "ToggleGroup.deselect_all() is multi-only — "
                "use .clear() for single-mode."
            )
        return self._dispatch_command("bz-deselect-all")


    # ── Render ─────────────────────────────────────────────────────────

    def render(self) -> Element:
        _theme, slots, sizes, size_key, _color = theme_context(self)

        size_cfg = sizes.get(size_key, sizes.get("md", {}))
        is_multi = bool(self._reactive_values.get("multiple"))

        def _resolve(template: str) -> str:
            return template

        # ── Resolve value binding ──────────────────────────────────────
        # Two streams from the user-passed ``value`` :
        # - ``binding_path`` : where the runtime reads/writes when a binding
        #   was provided (``$bz.state.X.Y.field``).
        # - ``initial_value`` : the SSR snapshot rendered into the
        #   ``value`` field of the ``bz-data`` scope + the hidden input's static
        #   ``value=`` + the buttons' static ``data-selected=``.
        value_binding = self._binding_metadata.get("value")
        binding_path: str | None = (
            self.path_of(value_binding) if value_binding is not None else None
        )

        raw_initial = self._reactive_values.get("value")
        if is_multi:
            initial_value: Any = list(raw_initial) if raw_initial else []
        else:
            initial_value = str(raw_initial) if raw_initial is not None else ""

        # Server-backed (``value=state.field`` carries a ``field_name``)
        # vs local literal. A server-backed group must RE-ADOPT its value
        # from the server on a @refreshable swap — ``scope.absorb`` keeps
        # the existing ``value`` signal across the morph (preserving a
        # user's client click), so without an opt-in the new server value
        # never lands. Same ``_serverSync`` boundary the rich inputs use
        # (cf. traps.md § a server-bound value follows the refresh). A
        # local literal stays client-owned (no re-adopt). Binding mode
        # needs nothing — the value lives in ``$bz._store``.
        value_server_backed = self._value_server_backed("value")

        # The scope key — ``value``, like the prop, like everywhere else
        # (cf. the module docstring). With a binding in play, every
        # expression hits the store path instead.
        (scope_key,) = self._scope_keys("value")
        picked_expr = binding_path if binding_path is not None else scope_key

        # ── bz-data ────────────────────────────────────────────────────
        # Local ``bz-data`` state ; carries the live value when no binding
        # is in play. With a binding the path is the source of truth
        # so we don't duplicate it locally (would race the framework's
        # delta apply).
        if binding_path is None:
            # The key comes from ``_scope_keys``, no longer from a
            # literal copied here: it lived in THREE places (the local
            # variable, the declaration, the marker) and a rename had to
            # touch all three (audit F84). It is the naming divergence
            # (value/picked/active/sel) that caused 5 of the 8 forgotten
            # ``_serverSync`` — it is gone since 2026-09-07, the key is
            # the prop's name.
            sync = server_sync_marker(
                *self._scope_keys("value"), enabled=value_server_backed)
            bz_data_obj = (
                f"{scope_key}: {_json.dumps(initial_value)}"
                + (f",{sync}" if sync else "")
            )
        else:
            bz_data_obj = ""

        # ── Click + selected expressions ───────────────────────────────
        # Single-mode click : assign picked = "x".
        # Multi-mode  click : flip membership via filter / spread.
        def _click_expr(item_value: str) -> str:
            quoted = _json.dumps(item_value)
            if is_multi:
                return (
                    f"{picked_expr} = {picked_expr}.includes({quoted}) "
                    f"? {picked_expr}.filter(v => v !== {quoted}) "
                    f": [...{picked_expr}, {quoted}]"
                )
            return f"{picked_expr} = {quoted}"

        def _selected_expr(item_value: str) -> str:
            quoted = _json.dumps(item_value)
            if is_multi:
                return f"{picked_expr}.includes({quoted})"
            return f"{picked_expr} === {quoted}"

        def _is_initially_selected(item_value: str) -> bool:
            """SSR initial state — used to stamp ``data-selected=true``
            on the right button at first paint so the active style is
            visible before the runtime boots (same idiom as Tabs)."""
            if is_multi:
                return item_value in (initial_value or [])
            return item_value == initial_value

        # ── Walk children — collect ToggleButton items only ────────────
        buttons: list[Element] = []
        item_values: list[str] = []
        item_class = " ".join(
            p
            for p in (
                _resolve(slots.get("item", "")),
                size_cfg.get("item", ""),
            )
            if p
        )

        # Group-level ``disabled`` resolution — same dual-stream as
        # ``value`` :
        # - ``group_disabled_binding`` carries the live binding when
        #   one was passed (then each button stamps
        #   ``bz-attr:disabled=<path>`` so the runtime flips the HTML
        #   attr reactively).
        # - ``group_disabled_static`` is the SSR snapshot — used to
        #   stamp the initial ``disabled`` HTML attr at first paint,
        #   so the locked visual lands before the runtime boots.
        # Per-item ``disabled=True`` on a ToggleButton always wins
        # (static, opt-in for "this option locked").
        group_disabled_binding = self._binding_metadata.get("disabled")
        group_disabled_static = bool(
            self._reactive_values.get("disabled")
        )
        group_disabled_path: str | None = (
            self.path_of(group_disabled_binding)
            if group_disabled_binding is not None else None
        )

        for raw in self._children:
            # ``unwrap_transparent``: a WRAPPED button — a
            # ``@refreshable`` zone, a ``ui.fragment`` — is not an
            # instance of ``ToggleButton``, so it fell into the "foreign
            # child" branch and its bare ``render()`` RAISED ("only valid
            # inside a ToggleGroup"). The only one of the five sorting
            # containers to be loud; the others degraded in silence.
            child, rewrap = unwrap_transparent(raw)
            if isinstance(child, ToggleButton):
                buttons.append(rewrap(
                    child._render_button(
                        item_class=item_class,
                        click_expr=_click_expr(child._option_value),
                        selected_expr=_selected_expr(child._option_value),
                        initially_selected=_is_initially_selected(
                            child._option_value
                        ),
                        group_disabled=group_disabled_static,
                        group_disabled_path=group_disabled_path,
                    )
                ))
                item_values.append(child._option_value)
            # Foreign children (rare — text dividers, etc.) flow
            # untouched.
            else:
                rendered = self._render_one(raw)
                if isinstance(rendered, Element):
                    buttons.append(rendered)

        # ── Assemble bz-data ────────────────────────────────────────────
        bz_data: str
        if bz_data_obj:
            bz_data = "{ " + bz_data_obj + " }"
        else:
            bz_data = "{}"

        # ── Hidden input ───────────────────────────────────────────────
        # Form integration — the dispatcher walks up to the nearest
        # <form> and submits the input's value. In multi-mode we
        # JSON.stringify the array so the server-side handler gets
        # a parseable string. Single-mode ships the raw string.
        root_attrs = self.emit_attrs()
        relocated_change = root_attrs.pop("bz-on:change", None)
        relocated_server = _pop_server_action(root_attrs)

        # ── focus / blur: re-keyed to focusin / focusout ────────────────
        # ``focus`` / ``blur`` do NOT BUBBLE: set on the root ``<div>``
        # (not focusable), a listener would never fire — the focusable
        # elements are the CHILD ``<button>``. ``focusin`` / ``focusout``
        # are the BUBBLING twins: set on the container, they fire when
        # any child takes / loses focus. Same relay as ``<bz-calendar>``
        # (07_calendar.js). Preferred over relocating onto the first
        # ``<button>`` (the Select idiom): "the first" would be
        # arbitrary, the focus can come in through any of them.
        for src, dst in (("focus", "focusin"), ("blur", "focusout")):
            attr = f"bz-on:{src}"
            if attr in root_attrs:
                root_attrs[f"bz-on:{dst}"] = root_attrs.pop(attr)
        if root_attrs.get("hx-trigger") in ("focus", "blur"):
            root_attrs["hx-trigger"] = (
                "focusin" if root_attrs["hx-trigger"] == "focus" else "focusout"
            )

        name = self._reactive_values.get("name") or self._derive_field_name()

        hidden_node: Element | None = None
        if (
            name
            or relocated_change is not None
            or relocated_server is not None
        ):
            hidden_value_expr = (
                f"JSON.stringify({picked_expr})" if is_multi else picked_expr
            )
            ssr_value: str
            if is_multi:
                ssr_value = _json.dumps(initial_value)
            else:
                ssr_value = (
                    initial_value if isinstance(initial_value, str)
                    else str(initial_value)
                )
            hidden_attrs: dict[str, Any] = {
                # ``dispatch=``: the catalogue's ONLY caller whose
                # posted value (``hidden_value_expr``, serialised) and
                # observed value (``picked_expr``) are not the same
                # expression. It is that divergence that made us keep the
                # parameter rather than hard-wire the dispatcher.
                **hidden_carrier_attrs(
                    hidden_value_expr, initial=ssr_value, dispatch=picked_expr
                ),
            }
            if name:
                hidden_attrs["name"] = str(name)
            if relocated_change is not None:
                hidden_attrs["bz-on:change"] = relocated_change
            if relocated_server is not None:
                hidden_attrs.update(relocated_server)
            hidden_node = Element(
                tag="input", attrs=hidden_attrs, children=()
            )

        # ── Imperative-API listeners ───────────────────────────────────
        # ``bz-on:bz-set`` / ``bz-on:bz-select-all`` /
        # ``bz-on:bz-deselect-all`` — caught by the wrapper and applied
        # to ``value`` (no-binding case) or to the binding path. When a
        # binding is in play, ``.set(...)`` writes through the binding
        # directly and these listeners never fire ; we still emit them
        # so external callers using the no-binding ``.set()`` path work.
        cmd_listeners: dict[str, Any] = {}
        cmd_listeners["bz-on:bz-set"] = (
            f"{picked_expr} = $event.detail.value"
        )
        if is_multi:
            quoted_items = (
                "[" + ", ".join(_json.dumps(v) for v in item_values) + "]"
            )
            cmd_listeners["bz-on:bz-select-all"] = (
                f"{picked_expr} = [...{quoted_items}]"
            )
            cmd_listeners["bz-on:bz-deselect-all"] = f"{picked_expr} = []"

        # ── Root assembly ──────────────────────────────────────────────
        # ``classes=`` set by the metaclass wrap — not here (duplicate).
        root_class = " ".join(
            p
            for p in (
                _resolve(slots.get("root", "")),
                # The step's height: it is on the root because it is
                # the root that carries the frame's border (cf. the
                # comment on ``TOGGLE_GROUP_THEME["sizes"]``).
                size_cfg.get("root", ""),
            )
            if p
        )
        root_attrs["class"] = root_class
        root_attrs["bz-data"] = bz_data
        root_attrs.setdefault("role", "group")
        for key, val in cmd_listeners.items():
            root_attrs[key] = val

        children: list[Any] = []
        children.extend(buttons)
        if hidden_node is not None:
            children.append(hidden_node)

        return Element(
            tag=self._tag, attrs=root_attrs, children=tuple(children),
        )


class ToggleButton(Component):
    """One item inside a :class:`ToggleGroup`."""

    THEME_KEY: ClassVar[str] = "toggle_button"
    DEFAULT_TAG: ClassVar[str] = "button"
    IS_CONTAINER: ClassVar[bool] = False
    BINDABLE_PROPS: ClassVar[tuple[str, ...]] = ("disabled",)
    option_value: str = reactive_prop(default="", emit_attr=False)
    # Fed from the option's positional ``value``. Passing it explicitly
    # is refused by ``reject_sealed``, called at the head of
    # ``__init__`` — it MUST be there, before the ``super().__init__``:
    # the kwarg collision is raised by Python when building the call, so
    # the base layer never sees it.
    #
    # ⚠️ This comment said "produces a multiple values" and left it at
    # that, until 2026-09-04. That was describing an unreadable message
    # instead of fixing it — nothing would have prompted a return to it.
    SEALED_PROPS: ClassVar[tuple[str, ...]] = ("option_value",)
    #: The refusal's message. Without it, ``reject_sealed``'s default
    #: speaks of an AXIS — true for a stack, false here.
    SEALED_REASONS: ClassVar[dict[str, str]] = {
        "option_value": (
            "ToggleButton(option_value=…): this prop is fed by the "
            "option's positional ``value`` — write "
            "``ui.toggle_button(\"my-value\")``. Passing it as well would "
            "produce two values for the same field, which is an "
            "ambiguity, not a shortcut."
        ),
    }
    disabled: bool = reactive_prop(default=False, emit_attr=False)

    def __init__(
        self,
        value: str,
        label: str | None = None,
        *,
        icon: str | Component | None = None,
        disabled: bool | None = None,
        tooltip: str | None = None,
        **kwargs: Any,
    ) -> None:
        reject_sealed(kwargs, type(self))
        # Direct forward: the base layer drops reactive None kwargs (keeps the default).
        # ``option_value`` (the item's positional ``value``) is always
        # passed on — it is not a None guard.
        super().__init__(
            option_value=value,
            disabled=disabled,
            **kwargs,
        )
        self._option_value = value
        self._label = label
        self._tooltip = tooltip
        # ⚠️ An ``icon="star"`` keeps its NAME here: its size depends
        # on the GROUP's ``size=``, which a child does not know at its
        # construction. It is derived at render, where ``item_class``
        # finally carries the label's text class — one step above, cf.
        # ``base.sizes.ICON_SIZE_ABOVE``.
        #
        # A literal size here would be frozen whatever the group's
        # ``size=``: that is the debt
        # ``test_child_component_size_is_not_frozen`` forbids, and it
        # shows — ``xs`` wants an ``sm`` icon, ``xl`` an ``lg``.
        #
        # A Component passed by hand keeps ITS size: the author chose
        # it.
        self._icon_name = icon if isinstance(icon, str) else None
        if icon is None or self._icon_name:
            self._icon: Component | None = None
        else:
            self._icon = Component.adopt_slot(icon, icon_shortcut=True)

    def render(self) -> Element:
        raise RuntimeError(
            "ToggleButton.render() is only valid inside a "
            "ToggleGroup ``with`` block. Use ``ui.toggle_group(...)`` "
            "and put your ``ui.toggle_button(...)`` items inside it."
        )

    # ── Internal API for ToggleGroup.render() ─────────────────────────

    def _render_button(
        self,
        *,
        item_class: str,
        click_expr: str,
        selected_expr: str,
        initially_selected: bool,
        group_disabled: bool,
        group_disabled_path: str | None = None,
    ) -> Element:
        """Materialise the actual ``<button>``. Called by the parent
        group with composed expressions + the SSR initial-selected
        flag (so the active style paints before the runtime hydrates — same
        idiom as Tabs ``data-selected``).

        ``group_disabled_path`` is the JS expression carrying the
        group's disabled binding (``$bz.state.X.Y.disabled``) when one
        was passed. When set, the button stamps ``bz-attr:disabled``
        so the runtime writes the disabled HTML attribute reactively
        (truthy → empty attr present, falsy → attr removed, exactly the
        boolean-attr semantics ``disabled`` needs). Without the path,
        ``group_disabled`` is the static SSR snapshot used to lock the
        button at first paint only."""
        attrs: dict[str, Any] = {
            "type": "button",
            "class": item_class,
            "bz-on:click": click_expr,
            # ``data-selected`` is the source of truth for the Tailwind
            # variant ``data-[selected=true]:bg-…``. Both static SSR
            # value AND reactive bind so the active style is right at
            # first paint AND tracks live state. The reactive expression
            # yields a ``true`` / ``false`` value ; ``bz-attr`` keeps
            # the data attribute present in both states only because
            # ``data-[selected=false]`` needs the literal string —
            # ``selected_expr`` is an equality / ``.includes`` test that
            # returns a real boolean, so wrap it to a string to dodge
            # the "bz-attr strips the attr on false" trap.
            "data-selected": "true" if initially_selected else "false",
            "bz-attr:data-selected": bool_attr(f"{selected_expr}"),
            # ``aria-pressed`` stays for accessibility — screen readers
            # announce the toggle state. Same expression, stringified
            # for the same reason.
            "bz-attr:aria-pressed": bool_attr(f"{selected_expr}"),
            "value": self._option_value,
        }
        # Disabled — composed from up to FOUR sources : the per-item lock
        # (static ``disabled=True`` OR a per-item ClientBinding) and the
        # group lock (static OR a group binding). The button is disabled if
        # ANY is truthy. Reactive bindings drive ``bz-attr:disabled`` live ;
        # the static snapshots stamp the HTML attr for first paint. Both the
        # per-item and group bindings flow into one OR-expression.
        per_item_binding = self._binding_metadata.get("disabled")
        per_item_path = (
            self.path_of(per_item_binding)
            if per_item_binding is not None else None
        )
        per_item_static = bool(self._reactive_values.get("disabled"))

        def _term(path: str | None, static: bool) -> str | None:
            if path is not None:
                return f"({path})"
            return "true" if static else None

        reactive_terms = [
            t for t in (_term(per_item_path, per_item_static),
                        _term(group_disabled_path, group_disabled))
            if t
        ]
        has_binding = (per_item_path is not None
                       or group_disabled_path is not None)
        if has_binding and reactive_terms:
            attrs["bz-attr:disabled"] = " || ".join(reactive_terms)
        if per_item_static or group_disabled:
            attrs["disabled"] = True

        if self._tooltip:
            attrs["title"] = self._tooltip

        # Icon + label children. ``label is None`` is a valid case —
        # icon-only buttons. Don't emit a stray empty text node.
        children: list[Any] = []
        icon = self._icon
        if icon is None and self._icon_name:
            from bretzel.components.base.sizes import icon_size_for

            icon = Icon(
                self._icon_name, size=icon_size_for(item_class) or "md"
            )
            Component._detach_from_parent(icon)
        if icon is not None:
            children.append(icon.render())
        # ``is not None`` is NOT enough: ``emit_text_slot`` also
        # returns ``None`` for the empty string, and a ``None`` in
        # ``children`` makes the serialiser raise. It is the emitted node
        # we test, not the input value.
        label_node = self.emit_text_slot(self._label)
        if label_node is not None:
            children.append(label_node)

        # ⚠️ ``finish_render`` and not an ``Element`` rendered as is.
        #
        # This path short-circuits the child's ``render()`` — so the
        # metaclass wrap, so the three passes EVERY component node must
        # undergo. Measured before this fix:
        # ``ui.toggle_button(..., classes=…, style=…, slots={"root": …})``
        # lost **all three** universal kwargs, in silence, as soon as it
        # was inside a ``ui.toggle_group`` — while they work on the 75
        # other components.
        #
        # Any parent that rebuilds a child instead of calling it must end
        # up here. It is the only place that describes what "rendering a
        # component" means.
        return finish_render(
            self,
            Element(
                tag=self.DEFAULT_TAG, attrs=attrs, children=tuple(children),
            ),
        )


__all__ = ["ToggleGroup", "ToggleButton"]
