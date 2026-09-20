"""``Select`` — custom popover-based combobox.

Replaces the native ``<select>`` with a fully-styled trigger +
dropdown panel — same visual identity as the rest of the design
system, full control over option rendering, easier path to future
search / multi-select / custom item layout.

API surface stays identical to a native select :

- ``options`` — list of strings, ``(value, label)`` tuples, or
  dicts ``{"value": ..., "label": ..., "disabled": ...}``
- ``value`` — literal, server-resolved, or ClientBinding (universal
  reactive contract). The displayed label tracks the value via a
  baked value→label map evaluated client-side ; the binding's
  ``set(...)`` is used internally to write back when an option is
  picked.
- ``placeholder`` — shown muted when no value is set
- ``name`` — when present, a hidden ``<input type="hidden">`` rides
  the binding so the value reaches the server on form submit
- ``disabled`` / ``required`` / ``size`` / ``color`` — conventional

Keyboard a11y :
- Tab focuses the trigger
- Space / Enter / ArrowDown opens the panel
- ArrowUp / ArrowDown move the highlight
- Enter on a highlighted option selects + closes
- Escape closes without changing the value
- Click-outside closes

Runtime notes :

- ``scope.absorb`` **invokes** ``decl[key]`` at registration, so any
  ``get foo() {…}`` freezes to a constant — every scope getter is a
  flat method (``_isPicked()``, ``_value()``) called from the
  markup.
- ``bz-on`` carries no modifier grammar, so per-key handlers collapse
  into one ``bz-on:keydown`` with ``$event.key`` guards and inlined
  ``preventDefault()`` / ``stopPropagation()``.
- The anchored panel rides the shared overlay wiring
  (``anchored_panel_effect`` + ``dispatch_root_effect`` +
  ``anchored_dismiss_init``). No open/close imperative listeners —
  Select's imperative surface is value-bearing (``bz-set``).
- Scope methods can't reach ``$refs`` / ``$el``, so pick/set just
  ``_write`` the value ; the SINGLE change dispatcher is a
  ``_change_emit_effect`` on the hidden input (a hidden input fires no
  native ``change``), which dispatches from ``$el`` whenever the value
  mutates. An unbound select does NOT emit ``_serverSync`` so a server
  re-render never re-adopts its value and fires a phantom ``change``.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterable
from typing import Any, ClassVar

from bretzel.components.base import (
    Component,
    reactive_prop,
    stamp_display_none,
)
from bretzel.components.base._wiring import (
    SERVER_ACTION_ATTRS,
    anchored_dismiss_init,
    anchored_panel_effect,
    bool_attr,
    dispatch_root_effect,
    imperative_listeners,
    install_open_close_toggle,
    relocate_server_action,
    server_sync_marker,
    theme_context,
)
from bretzel.components.base._wiring import (
    change_emit_effect as _change_emit_effect,
)
from bretzel.components.feedback.badge.theme import BADGE_THEME
from bretzel.components.inputs._picker import (
    badge_pill_classes,
    build_header_bar,
    build_pills_template,
    has_picks,
    normalise_option,
    option_body,
    option_check,
    render_x_icon,
    sized_slot,
)
from bretzel.components.inputs.select.theme import SELECT_THEME
from bretzel.components.primitives.icon import Icon
from bretzel.core.tree import Element, Node
from bretzel.core.tree import TextNode as TextNode
from bretzel.render import text
from bretzel.state.scopes.client import ClientBinding

# Native HTMX action attrs a callable handler lands on the root via
# ``emit_attrs`` ; relocated wholesale to the hidden input that holds
# name+value (the dispatcher reads form-data from there). The
# ``hx-trigger`` in this bundle says WHICH event fires the POST — for
# the change handler it is pinned to ``change`` below, and a hidden
# input only emits a (synthetic) ``change`` thanks to the
# ``_change_emit_effect`` posted on it.
_ACTION_ATTRS = SERVER_ACTION_ATTRS


class Select(Component):
    """Styled combobox built on a button trigger + dropdown panel."""

    THEME: ClassVar[dict[str, Any]] = SELECT_THEME
    THEME_KEY: ClassVar[str] = "select"
    #: It is the COMPONENT that owns the loop: it iterates ``options=``
    #: and renders one ``<button role="option">`` per entry, on the
    #: SERVER side. The author does not write that loop, so they have
    #: nowhere to put their markup — hence ``render=``, their only entry
    #: point.
    #:
    #: ⚠️ Declared ``"client"`` by mistake on 2026-08-18, on a TRUNCATED
    #: reading of a ``combobox.py`` comment ("built once server-side so
    #: the JS filter only does a…"), read as "the client owns the list"
    #: while it says the opposite. The JS filter is a ``bz-show``: it
    #: HIDES already rendered buttons, it creates none. The distinction
    #: reads in one word of vocabulary — ``bz-for`` clones (that is
    #: ``file_upload``), ``bz-show`` hides.
    #: Cf. ``Component.COLLECTION_OWNER``.
    COLLECTION_OWNER: ClassVar[str | None] = "component"
    IS_CONTAINER: ClassVar[bool] = False
    # Curated reactive surface — selected value + lock flag.
    BINDABLE_PROPS: ClassVar[tuple[str, ...]] = ("value", "disabled")
    #: ⚠️ ``open`` / ``close`` / ``toggle`` added on 2026-09-03, last of
    #: the NINE components of this shape. Select is an anchored panel
    #: carrying a value — like the six pickers and like Combobox — and it
    #: had only the field half. The shape is now UNIFORM: same nature,
    #: same surface.
    IMPERATIVE: ClassVar[tuple[str, ...]] = (
        "open", "close", "toggle",
        "set", "clear", "focus", "blur",
        "select_all", "deselect_all",
    )
    # ``disabled`` is wired by hand in ``render()`` (NOT via
    # ``BINDABLE_CARRIERS``) : the single trigger ``<button>`` already
    # owns the one ``bz-ref`` an element gets (``bztrigger``, the
    # floating anchor) so a second ``bzSingleTrigger`` carrier ref can't
    # coexist — the auto-walk would never find it. Both trigger shapes
    # therefore ``forward_binding`` the ``disabled`` binding explicitly :
    # the single ``<button>`` as the real ``disabled`` attr, the multi
    # ``<div>`` as ``aria-disabled`` (a ``<div>`` ignores ``disabled``).
    EVENTS: ClassVar[tuple[str, ...]] = (
        "change", "focus", "blur",
    )

    name: str | None = reactive_prop(default=None, emit_attr=False)
    value: Any = reactive_prop(default=None, emit_attr=False, writes=True, names_field=True)
    placeholder: str | None = reactive_prop(default=None, emit_attr=False)
    multiple: bool = reactive_prop(default=False, emit_attr=False)
    bulk_actions: bool = reactive_prop(default=False, emit_attr=False)
    disabled: bool = reactive_prop(default=False, emit_attr=False)
    required: bool = reactive_prop(default=False, emit_attr=False)
    color: str = reactive_prop(default="primary", emit_attr=False)
    size: str = reactive_prop(default="md", emit_attr=False)

    def __init__(
        self,
        options: Iterable[Any] = (),
        *,
        render: Callable[[Any, Any], Any] | None = None,
        value: Any = None,
        name: str | None = None,
        placeholder: str | None = None,
        multiple: bool | None = None,
        bulk_actions: bool | None = None,
        disabled: bool | None = None,
        required: bool | None = None,
        color: str | None = None,
        size: str | None = None,
        on_change: Callable[..., Any] | str | None = None,
        on_focus: Callable[..., Any] | str | None = None,
        on_blur: Callable[..., Any] | str | None = None,
        **kwargs: Any,
    ) -> None:
        # Direct forward: the base layer drops reactive None kwargs (keeps the default).
        super().__init__(
            name=name, value=value, placeholder=placeholder,
            multiple=multiple, bulk_actions=bulk_actions,
            disabled=disabled, required=required,
            color=color, size=size,
            on_change=on_change,
            on_focus=on_focus,
            on_blur=on_blur,
            **kwargs,
        )
        self._options = list(options)
        self._render = render
        # AFTER `super().__init__`: the installer reads `_binding_metadata`.
        install_open_close_toggle(self)

    # ── Imperative write-only API ─────────────────────────────────────
    #
    # Six methods returning client source ready to plug into
    # ``on_click=`` (or any ``on_*``). Write-through when ``value=``
    # carries a :class:`ClientBinding` ; DOM dispatch otherwise.
    # ``.focus()`` / ``.blur()`` are pure DOM commands — Select's
    # focusable surface is the trigger ``<button>`` (the wrapper
    # ``<div>`` carries ``self.id`` but is not focusable). We reach
    # the trigger via ``querySelector('[role=combobox]')`` on the
    # rooted wrapper. Cf. `imperative-api.md`.

    def set(self, value: Any) -> str:
        """In single mode ``value`` is a scalar string ; in multi
        mode it should be a list of strings. The binding handles the
        type either way."""
        return self._value_command(value)

    def clear(self) -> str:
        """Single → ``""`` ; multi → ``[]`` (same dispatch contract
        Combobox uses)."""
        is_multi = bool(self._reactive_values.get("multiple"))
        return self.set([] if is_multi else "")

    def focus(self) -> str:
        # The focusable element depends on the trigger shape :
        # - single mode → ``<button role=combobox>`` (default)
        # - multi mode  → ``<div role=combobox tabindex=0>`` (so
        #   the trigger can host pills + still receive keyboard).
        # Both carry ``role=combobox`` so a single querySelector
        # works ; ``.focus()`` works on any focusable element.
        return (
            f"document.getElementById('{self.id}')"
            f".querySelector('[role=combobox]').focus()"
        )

    def blur(self) -> str:
        return (
            f"document.getElementById('{self.id}')"
            f".querySelector('[role=combobox]').blur()"
        )

    def select_all(self) -> str:
        """Pick EVERY non-disabled option. Multi mode only — single
        mode silently no-ops (you can't pick more than one)."""
        return self._dispatch_command("bz-select-all")

    def deselect_all(self) -> str:
        """Clear every pick. Sugar over ``.clear()`` — kept distinct
        so the bulk-actions header button can call it directly."""
        return self._dispatch_command("bz-deselect-all")


    # ── Render ─────────────────────────────────────────────────────────

    def render(self) -> Element:
        _theme, slots, sizes, size_key, _color = theme_context(self)
        placeholder = self._reactive_values.get("placeholder")
        disabled = bool(self._reactive_values.get("disabled"))
        required = bool(self._reactive_values.get("required"))
        is_multi = bool(self._reactive_values.get("multiple"))
        bulk_actions = bool(self._reactive_values.get("bulk_actions"))
        size_map = sizes.get(size_key, sizes.get("md", {}))

        def _resolve(template: str) -> str:
            return template

        # ── Resolve value : literal vs binding ───────────────────────
        # The binding lives in ``_binding_metadata`` ; ``_reactive_values``
        # holds the raw initial value for SSR fallback.
        value_binding = self._binding_metadata.get("value")

        # Form-data name : explicit ``name=`` wins ; otherwise derive
        # from the bound field via autoname. Two sources, in priority
        # order :
        # 1. ClientBinding's ``field_name`` (live client-state mirror).
        # 2. Server-state scalar stamp on the raw value (the value is
        #    a ``_BoundStr`` / ``_BoundInt`` carrying ``field_name``).
        # Skipped when both are absent — the select then doesn't ride
        # the form.
        derived_name = self._derive_field_name()  # reused by value_server_backed below
        name = self._reactive_values.get("name") or derived_name
        if value_binding is not None:
            # V3 read/write path the trigger reads + the option click
            # writes : full ``$bz.state.<path>`` form.
            value_expr = value_binding.binding_path()
        else:
            value_expr = "value"  # local bz-data scope ; see below

        initial_value = self._reactive_values.get("value")
        # ``_serverSync`` re-adopts ``value`` from the server on a
        # @refreshable swap — desirable ONLY when the value is backed by
        # SERVER state (``value=server_state.field``, a stamp carrying a
        # ``field_name``) : there the server is authoritative, a
        # re-render should win (cf. traps.md § a server-bound value). For
        # an UNBOUND select (no ``value=``, or a plain literal) the value
        # is purely client-side ; re-adopting the static SSR initial on
        # every swap would WIPE the user's pick whenever an unrelated
        # handler refreshes the surrounding section. Gate on the stamp so
        # the client keeps its pick. (Binding mode never emits
        # ``_serverSync`` — value lives in ``$bz._store``, patched by the
        # envelope.)
        # ⚠️ NOT ``derived_name``: the autoname answers "where does my
        # HTML name= come from", not "where does my value come from".
        # Borrowing it lost the ``[state.field]`` case (a multi fed by a
        # scalar server pick) and coupled the server-sync to form
        # naming.
        value_server_backed = self._value_server_backed("value")

        # ── Normalise options + build the value→label map ────────────
        normalised: list[tuple[Any, Any, bool]] = [
            normalise_option(opt) for opt in self._options
        ]
        # No options → nothing to pick : auto-disable so the trigger
        # reads as inert (dimmed + not-allowed cursor, can't open an
        # empty panel) instead of a normal-looking control.
        if not normalised:
            disabled = True
        # Map keys must be strings for the JS lookup ; the binding
        # value will get coerced to string for the lookup as well.
        value_label_map = {str(v): str(label) for v, label, _ in normalised}

        # ── Trigger button ───────────────────────────────────────────
        trigger_class = " ".join(
            p
            for p in (
                self.compose_class(
                    "trigger",
                    apply_variant_size_modifiers=False,
                ),
                size_map.get("trigger", ""),
            )
            if p
        )

        # The label inside the trigger : reactive lookup through
        # ``_labelOf``, the scope method that reads the baked ``_labels``
        # map. ``bz-text`` so the label updates whenever the bound value
        # changes (or the placeholder shows when nothing is picked).
        #
        # ⚠️ The two expressions below INLINED the whole map — two more
        # copies, on top of the ``bz-data``'s and the pill template's. On
        # a 20-option select that was four times the same table in a
        # single component. The scope method replaces them all
        # (2026-08-28).
        labels_js = json.dumps(value_label_map, ensure_ascii=False)
        ph_js = json.dumps(placeholder or "", ensure_ascii=False)
        label_bz_text = f"_labelOf({value_expr}) || {ph_js}"
        # Placeholder modifier flips on whenever the lookup misses.
        placeholder_class = slots.get("placeholder", "")
        label_class = slots.get("label", "")
        label_bind_class = (
            f"!_labelOf({value_expr}) ? '{placeholder_class}' : ''"
        )

        # ``with_slot_class``: clone a rendered child to PREPEND the
        # slot's class to it, without overwriting the one it composed for
        # itself. This clone-and-merge lived inline here and in combobox
        # — the two call sites audit F56 had missed. ``bz-class`` MERGES
        # the rotation onto the static classes (``bz-attr:class`` would
        # REPLACE them).
        chevron = Icon(
            "chevron-down", size=size_map.get("chevron_size", "sm"),
        )
        chevron_render = Component.with_slot_class(
            Component.render_detached(chevron),
            slots.get("chevron", ""),
            **{"bz-class": "open ? 'rotate-180' : ''"},
        )

        # ── Resolve event relocations BEFORE building trigger / hidden.
        #
        # The root is a wrapper ``<div>`` that has neither focus nor a
        # native ``change`` event ; without re-attaching listeners to
        # the right child element, focus/blur silently never fire and
        # change reads off an element with no value.
        #
        # Two destinations, two flavours each :
        # - Server callable  : the native HTMX action set (``hx-post`` +
        #   ``hx-trigger`` + …) emitted on the root by ``emit_attrs``.
        # - Client string    : ``bz-on:<event>="<expr>"``.
        # - Change           → hidden input (with ``name`` so the
        #   dispatcher serialises ``name=value`` into form data).
        # - Focus / Blur     → trigger (the only focusable element).
        root_attrs = self.emit_attrs()
        relocated_to_hidden: dict[str, Any] = {}
        relocated_to_trigger: dict[str, Any] = {}
        # Event routing. The string ``change`` handler rides the hidden
        # input (it carries the value). The callable's HTMX bundle is
        # routed by the event it ACTUALLY fires on : a ``change`` bundle
        # rides the hidden input (which dispatches a value-carrying
        # synthetic ``change`` via ``_change_emit_effect``) ; a ``focus`` /
        # ``blur`` bundle rides the TRIGGER (the only focusable element),
        # keeping its native trigger.
        if "bz-on:change" in root_attrs:
            relocated_to_hidden["bz-on:change"] = root_attrs.pop("bz-on:change")
        # The routing itself lives in the base layer:
        # ``relocate_server_action`` reads ``hx-trigger`` and chooses the
        # carrier. This block was the ONLY one in the repository to do it
        # correctly — hence its extraction.
        relocate_server_action(
            root_attrs,
            value_carrier=relocated_to_hidden,
            focusable=relocated_to_trigger,
        )
        for ev_attr in ("bz-on:focus", "bz-on:blur"):
            if ev_attr in root_attrs:
                relocated_to_trigger[ev_attr] = root_attrs.pop(ev_attr)

        # Common keyboard handler — Enter picks/toggles depending on
        # mode ; ArrowDown/Up navigate, Space opens, Escape closes.
        # ``bz-on`` has no modifier grammar, so every per-key handler is
        # fused into ONE ``bz-on:keydown`` with explicit ``$event.key``
        # guards + inlined ``preventDefault()``. Reused for both single
        # (button) and multi (div) triggers — same keyboard contract.
        if is_multi:
            enter_action = (
                "if (open && _highlight >= 0) "
                "{ _togglePick(_options[_highlight]); } "
                "else { open = true; _highlightFromValue(); }"
            )
        else:
            enter_action = (
                "if (open && _highlight >= 0) "
                "{ _pick(_options[_highlight]); } "
                "else { open = true; _highlightFromValue(); }"
            )
        keydown_handler = (
            "const k = $event.key; "
            "if (k === ' ' || k === 'Spacebar') { "
            "$event.preventDefault(); "
            "open = true; _highlightFromValue(); } "
            "else if (k === 'Enter') { "
            f"$event.preventDefault(); {enter_action} }} "
            "else if (k === 'ArrowDown') { "
            "$event.preventDefault(); "
            "if (!open) { open = true; _highlightFromValue(); } "
            "else { _highlight = Math.min("
            "_highlight + 1, _options.length - 1); } } "
            "else if (k === 'ArrowUp') { "
            "$event.preventDefault(); "
            "if (open) { _highlight = Math.max(_highlight - 1, 0); } } "
            "else if (k === 'Escape') { open = false; }"
        )
        common_trigger_attrs: dict[str, Any] = {
            "class": trigger_class,
            "role": "combobox",
            "aria-haspopup": "listbox",
            "bz-attr:aria-expanded": bool_attr("open"),
            "bz-ref": "bztrigger",
            "bz-on:click": "open = !open",
            "bz-on:keydown": keydown_handler,
            **relocated_to_trigger,
        }
        if required:
            common_trigger_attrs["aria-required"] = "true"

        # Reactive disabled : land the binding on the actual trigger
        # element (button or div). The base ``emit_attrs`` lands the
        # directive on the root wrapper which is just a layout div
        # with no DOM effect.
        #
        # The multi-trigger is a ``<div>`` (``disabled`` is not a valid
        # attribute there) so we forward as ``aria-disabled`` instead ;
        # the single trigger is a ``<button>`` and takes the real
        # ``disabled``. Both forwardings go through the same primitive —
        # ``forward_binding`` handles ClientBinding transparently.
        has_disabled_binding = isinstance(
            self._binding_metadata.get("disabled"),
            ClientBinding,
        )

        if is_multi:
            # Multi trigger : <div> hosting pills + clear + chevron.
            # tabindex="0" makes the div focusable so the keyboard
            # handlers work. Nested <button>s (pill × + clear ×) are
            # valid because the trigger is a div, not a button.
            trigger_attrs: dict[str, Any] = {
                **common_trigger_attrs,
                "tabindex": "0",
            }
            if disabled:
                # Soft-disable : no ``disabled`` attr on a div, but
                # we drop tabindex and the click handler.
                trigger_attrs["tabindex"] = "-1"
                trigger_attrs["aria-disabled"] = "true"
                trigger_attrs["bz-on:click"] = ""
            if has_disabled_binding:
                self.forward_binding(
                    "disabled", trigger_attrs, as_attr="aria-disabled",
                )

            # Pills row : <template bz-for> over picked values +
            # placeholder span when no picks.
            # Pill styling sourced from BADGE_THEME (mirroring
            # Combobox) so a Badge theme tweak propagates here.
            badge_pill_class, badge_remove_class = badge_pill_classes(
                _resolve, size=size_map.get("pill_size", "sm"),
                badge_theme=self._resolved_theme("badge", BADGE_THEME),
            )
            pills_template = build_pills_template(
                pill_class=badge_pill_class,
                remove_class=badge_remove_class,
            )
            placeholder_span_attrs: dict[str, Any] = {
                "class": (
                    f"{label_class} {slots.get('placeholder', '')}"
                ).strip(),
                "bz-show": "!_hasPicked()",
            }
            # FOUC pre-stamp : hide unless there are no picks at SSR.
            if has_picks(initial_value, is_multi=True):
                stamp_display_none(placeholder_span_attrs)
            placeholder_span = Element(
                tag="span",
                attrs=placeholder_span_attrs,
                children=(TextNode(placeholder or ""),),
            )
            pills_row = Element(
                tag="div",
                attrs={"class": slots.get("pills_row", "")},
                children=(pills_template, placeholder_span),
            )
            clear_attrs: dict[str, Any] = {
                "type": "button",
                "class": _resolve(slots.get("clear", "")),
                "aria-label": text("select.clear"),
                "tabindex": "-1",
                "bz-on:click": "$event.stopPropagation(); _clearAll()",
                "bz-show": "_hasPicked()",
            }
            if not has_picks(initial_value, is_multi=True):
                stamp_display_none(clear_attrs)
            clear_btn = Element(
                tag="button",
                attrs=clear_attrs,
                children=(
                    render_x_icon(
                        size_map.get("clear_icon_size", "xs"),
                    ),
                ),
            )
            trigger_button = Element(
                tag="div",
                attrs=trigger_attrs,
                children=(pills_row, clear_btn, chevron_render),
            )
        else:
            # Single trigger : original <button> with label span. The
            # button keeps the ``bz-ref="bztrigger"`` floating anchor
            # (from ``common_trigger_attrs``) — an element has a single
            # ``bz-ref``, so the disabled binding can't ride a second
            # ``bzSingleTrigger`` ref. We forward it explicitly onto the
            # button instead (mirroring the multi branch's
            # ``aria-disabled`` forward), landing ``bz-attr:disabled``
            # where it actually disables the control. The static
            # ``disabled`` HTML attr below stamps the SSR snapshot so
            # the lock paints before the runtime boots.
            trigger_attrs = {
                "type": "button",
                **common_trigger_attrs,
            }
            if disabled:
                trigger_attrs["disabled"] = True
            if has_disabled_binding:
                self.forward_binding(
                    "disabled", trigger_attrs, as_attr="disabled",
                )
            trigger_button = Element(
                tag="button",
                attrs=trigger_attrs,
                children=(
                    Element(
                        tag="span",
                        attrs={
                            "class": label_class,
                            # MERGE the placeholder modifier onto the
                            # static label class (bz-class, not
                            # bz-attr:class which would replace it).
                            "bz-class": label_bind_class,
                            "bz-text": label_bz_text,
                        },
                        children=(),
                    ),
                    chevron_render,
                ),
            )

        # ── Option panel ─────────────────────────────────────────────
        option_class_base = " ".join(
            p
            for p in (
                slots.get("option", ""),
                size_map.get("option", ""),
            )
            if p
        )
        option_active_cls = self.compose_class(
            "option_active",
            apply_variant_size_modifiers=False,
        )
        option_selected_cls = self.compose_class(
            "option_selected",
            apply_variant_size_modifiers=False,
        )

        option_nodes: list[Any] = []
        for index, (opt_value, opt_label, opt_disabled) in enumerate(
            normalised
        ):
            opt_v_js = json.dumps(str(opt_value))
            # Per-option click :
            # - single mode → ``_pick(v)`` (sets value, closes panel)
            # - multi mode  → ``_togglePick(v)`` (flips array
            #   membership, panel stays open for further picks)
            # Both just ``_write`` the value ; the hidden input's
            # ``_change_emit_effect`` observes the mutation and fires the
            # ``change`` (+ relocated hx-post). No dispatch in the click
            # handler itself.
            click_action = (
                f"_togglePick({opt_v_js})"
                if is_multi
                else f"_pick({opt_v_js})"
            )
            # "Selected" state : single mode = scalar match ; multi
            # mode = array membership. Use ``_isPicked()`` which
            # branches internally based on mode (defined in bz-data).
            opt_attrs: dict[str, Any] = {
                "type": "button",
                "role": "option",
                # The form-data value the option represents — distinct
                # from the user-facing label. Audit probes and any
                # external automation tooling (visual regression
                # harnesses, accessibility scanners) need the value
                # without parsing the click handler. Standard ARIA
                # listbox pattern.
                "data-value": str(opt_value),
                "class": option_class_base,
                # Two sources of "active" : keyboard highlight or
                # mouse hover. Selected = via _isPicked (mode-aware).
                # ``bz-class`` accepts the array natively AND merges it
                # onto the static ``option_class_base`` — ``bz-attr:class``
                # would stringify the array (→ "active,selected") and
                # wipe the base classes.
                "bz-class": (
                    f"[(_highlight === {index}) "
                    f"? '{option_active_cls}' : '', "
                    f"_isPicked({opt_v_js}) "
                    f"? '{option_selected_cls}' : '']"
                ),
                "bz-attr:aria-selected": (
                    bool_attr(f"_isPicked({opt_v_js})")
                ),
                "bz-on:click": click_action,
                "bz-on:mouseenter": f"_highlight = {index}",
            }
            if opt_disabled:
                opt_attrs["disabled"] = True
            # Multi: the tick on the right. Exact mirror of Combobox —
            # both themes promise to read as a family, and it is the
            # affordance that says "picked" when the accent alone can no
            # longer be told from the hover.
            opt_children: tuple[Any, ...] = option_body(self._render,
                opt_value, opt_label
            )
            if is_multi:
                opt_children += (option_check(
                    slots=slots, size_map=size_map, resolve=_resolve,
                    picked_js=f"_isPicked({opt_v_js})",
                    initially_picked=str(opt_value) in (
                        [str(v) for v in initial_value]
                        if isinstance(initial_value, list) else []
                    ),
                ),)
            option_nodes.append(
                Element(
                    tag="button",
                    attrs=opt_attrs,
                    children=opt_children,
                )
            )

        # Panel children : optional header_bar (multi mode) + options.
        # Header sits above the options, sticky so it stays visible
        # while scrolling. Hidden via bz-show when nothing to show
        # (no picks AND no bulk-actions) so single-mode and empty-
        # multi don't get any extra chrome.
        panel_children: list[Node] = []
        if is_multi:
            panel_children.append(
                self._build_header_bar(
                    slots=slots,
                    size_map=size_map,
                    resolve=_resolve,
                    show_bulk=bulk_actions,
                    total_options=len(normalised),
                    initial_value=initial_value,
                )
            )
        panel_children.extend(option_nodes)

        # ── Anchored panel ───────────────────────────────────────────
        # ``bz-ref="bzpanel"`` + the shared ``anchored_panel_effect``
        # toggles display + attaches ``$bz.helpers.floating`` against
        # the ``bztrigger`` ref. FOUC pre-stamp keeps it hidden before
        # the runtime boots (the panel is open=false at SSR).
        panel_attrs: dict[str, Any] = {
            "class": sized_slot(slots, size_map, "panel", _resolve),
            "role": "listbox",
            "bz-ref": "bzpanel",
            # ``bottom-end`` : the panel's RIGHT edge pins to the
            # trigger's right edge and it grows leftward when an option
            # is wider than the trigger — "starts at the right, extends
            # left". ``match_width`` keeps it at least as wide as the
            # trigger so a short option list never looks cramped.
            "bz-effect": anchored_panel_effect(
                "open", "bottom-end", match_width=True,
            ),
        }
        stamp_display_none(panel_attrs)
        panel = Element(
            tag="div",
            attrs=panel_attrs,
            children=tuple(panel_children),
        )

        # ── Hidden input — form integration + change dispatch target.
        #
        # ``bz-attr:value`` binds to the local ``value`` (literal case)
        # or to the binding path (bound case) so the rendered DOM
        # ``value`` attribute tracks the picked option in real time. The
        # ``_change_emit_effect`` posted here is the change dispatcher.
        #
        # Three gates create the hidden input :
        # 1. Explicit / binding-derived ``name`` — needs form serialisation.
        # 2. Any change handler — needs a dispatch target.
        # 3. Neither — no hidden input emitted (Select renders as
        #    trigger + panel only).
        #
        # When a change handler is wired but no name is derivable
        # (e.g. ``ui.select(opts, on_change=fn)`` with no value-binding),
        # default the hidden input's ``name`` to ``"value"`` so the
        # dispatcher's ``collectFormData`` emits ``value=<picked>`` and
        # the handler signature ``def on_change(value: str)`` receives
        # the picked option without the caller having to wire a name.
        hidden_nodes: list[Any] = []
        has_carrier = bool(name or relocated_to_hidden)
        if has_carrier:
            # Multi mode : the value is a list ; serialise as JSON
            # so the form-data survives one round-trip. Single mode
            # rides the scalar string directly.
            if is_multi:
                initial_str = json.dumps(
                    self._normalise_multi_initial(initial_value)
                )
                value_directive = (
                    f"JSON.stringify({value_expr} || [])"
                )
            else:
                initial_str = (
                    "" if initial_value is None
                    else str(initial_value)
                )
                value_directive = f"String({value_expr})"
            hidden_attrs: dict[str, Any] = {
                "type": "hidden",
                "bz-ref": "bzhidden",
                "bz-attr:value": value_directive,
                "value": initial_str,
                # A hidden input fires no native ``change`` — this effect
                # dispatches one (from ``$el``, so the relocated htmx
                # listener sees it) whenever the value mutates. It's the
                # Select's SINGLE change dispatcher. It must NOT fire on a
                # SERVER re-adoption : an unbound select dodges that by not
                # emitting ``_serverSync`` (cf. ``_build_bz_data_*``).
                "bz-effect": _change_emit_effect(value_directive),
            }
            effective_name = name or (
                "value" if relocated_to_hidden else None
            )
            if effective_name:
                hidden_attrs["name"] = str(effective_name)
            # Move the change listener onto this element so the
            # dispatcher reads its name+value at fire time.
            hidden_attrs.update(relocated_to_hidden)
            hidden_nodes.append(
                Element(tag="input", attrs=hidden_attrs, children=())
            )
        # ``compose_class("root", apply_variant_size_modifiers=False)``
        # so the size class lands on the trigger, not on this wrapper.
        root_attrs["class"] = self.compose_class(
            "root", apply_variant_size_modifiers=False,
        )
        # bz-data : open flag + keyboard highlight + baked option
        # list + mode-aware methods. Multi mode adds pills support
        # (_picked / _togglePick / _selectAll / _clearAll) ; single
        # keeps the lean single-pick API.
        #
        # ⚠️ Two scope rules drive the method shapes :
        # - ``scope.absorb`` invokes ``decl[key]`` at registration, so
        #   any ``get foo(){…}`` freezes to a constant — every getter is
        #   a flat method here.
        # - bare identifiers inside a method body do NOT auto-scope to
        #   ``this`` — always go through ``this.<field>`` for local
        #   state ; binding writes go to the full ``$bz.state.<path>``.
        options_js = json.dumps(
            [str(v) for v, _, _ in normalised], ensure_ascii=False
        )
        # ``write_in_method`` is the method-context path : ``this.value``
        # for the local field, full ``$bz.state.<path>`` for a binding.
        if value_binding is not None:
            write_in_method = value_expr  # full path works anywhere
        else:
            write_in_method = "this.value"

        if is_multi:
            bz_data = self._build_bz_data_multi(
                value_binding=value_binding,
                write=write_in_method,
                initial_value=initial_value,
                options_js=options_js,
                labels_js=labels_js,
                server_backed=value_server_backed,
            )
        else:
            bz_data = self._build_bz_data_single(
                value_binding=value_binding,
                value_expr=value_expr,
                write=write_in_method,
                initial_value=initial_value,
                options_js=options_js,
                labels_js=labels_js,
                server_backed=value_server_backed,
            )
        root_attrs["bz-data"] = bz_data

        # ── Root wiring : open/close dispatch + dismiss + imperative ──
        #
        # - ``dispatch_root_effect`` fires ``open`` / ``close`` events
        #   on transition (no scroll lock — an anchored panel doesn't
        #   trap the page).
        # - ``anchored_dismiss_init`` registers Escape + click-outside
        #   dismiss.
        # No open/close imperative listeners : Select's imperative surface
        # is value-bearing (``bz-set`` below ; ``.clear()`` sends ``bz-set``
        # with ``""`` / ``[]``), wired directly. ``change`` is dispatched by
        # the hidden input's ``_change_emit_effect``, not by a scope method.
        # The open/close/toggle receivers — without them, `.open()` would
        # dispatch an event nobody listens to.
        for _ev, _handler in imperative_listeners("open").items():
            root_attrs.setdefault(_ev, _handler)
        root_attrs["bz-effect"] = dispatch_root_effect("open")
        root_attrs["bz-init"] = anchored_dismiss_init("open")

        # ── Imperative-API listeners ─────────────────────────────────
        #
        # External ``select.set('opt-a')`` / ``.clear()`` dispatch a
        # ``bz-set`` CustomEvent (with ``detail.value`` — ``.clear()``
        # sends ``""`` / ``[]``) on the wrapper ``<div>`` by id. The event bubbles, the
        # wrapper's listener runs inside the bz-data scope and reuses
        # ``_pick(v)`` — the canonical setter that (a) writes the value
        # and (b) closes the dropdown if open. The value write is
        # observed by the hidden input's ``_change_emit_effect``, which
        # fires the change — same contract as the click path.
        #
        # When the binding path is in play, the imperative method writes
        # through the binding directly and these listeners never fire —
        # kept uniform for the no-binding case.
        if is_multi:
            # ``bz-set`` payload : array of values (Combobox uses the
            # same shape). ``_setValue`` does the right thing per mode.
            root_attrs["bz-on:bz-set"] = "_setValue($event.detail.value)"
            root_attrs["bz-on:bz-select-all"] = "_selectAll()"
            root_attrs["bz-on:bz-deselect-all"] = "_clearAll()"
        else:
            root_attrs["bz-on:bz-set"] = (
                "_pick(String($event.detail.value))"
            )

        return Element(
            tag=self._tag,
            attrs=root_attrs,
            children=(*hidden_nodes, trigger_button, panel),
        )

    # ── Helpers ────────────────────────────────────────────────────────

    def _build_header_bar(
        self,
        *,
        slots: dict[str, str],
        size_map: dict[str, str],
        resolve: Callable[[str], str],
        show_bulk: bool,
        total_options: int,
        initial_value: Any,
    ) -> Element:
        """The shared header. Select only builds it in multi (hence
        ``is_multi=True``) and compares against the TOTAL options: it has
        no query, so nothing is ever hidden."""
        return build_header_bar(
            slots=slots, size_map=size_map, resolve=resolve,
            badge_theme=self._resolved_theme("badge", BADGE_THEME),
            is_multi=True, show_bulk=show_bulk,
            total_options=total_options, initial_value=initial_value,
            select_all_disabled_js=(
                "_picked().length === _options.length"
            ),
        )

    @staticmethod
    def _normalise_multi_initial(initial_value: Any) -> list[str]:
        """SSR snapshot of the multi value as a ``list[str]``.

        Single source of truth for the two DOM slots that consume it :
        the hidden input's ``value=`` JSON and the local ``value`` field
        of the multi ``bz-data`` scope. Without one helper the two
        copies must stay in lockstep by hand."""
        if isinstance(initial_value, (list, tuple, set)):
            return [str(v) for v in initial_value]
        if initial_value:
            return [str(initial_value)]
        return []

    def _build_bz_data_single(
        self,
        *,
        value_binding: Any,
        value_expr: str,
        write: str,
        initial_value: Any,
        options_js: str,
        labels_js: str,
        server_backed: bool,
    ) -> str:
        """Single-mode bz-data — open flag + highlight + scalar
        pick/select methods. The methods only ``_write`` the value ;
        ``change`` is dispatched by the hidden input's
        ``_change_emit_effect``, not by the scope.

        The read site uses ``read`` (``this.value`` for the local field,
        full ``$bz.state.<path>`` for a binding) so the two cases collapse
        into one templated object literal — same split the multi builder
        uses."""
        # Methods live ONCE in ``$bz.select.single`` (13_select.js) ;
        # this instance emits only its data + ``_read``/``_write``.
        # ``_options`` stays per-instance. ``_read``/``_write`` (helpers,
        # not frozen) point the shared methods at the value cell —
        # local: a ``value`` field ; binding: ``$bz.state.<path>``. No
        # ``get value()`` (scope.absorb freezes getters) ; the label /
        # hidden input read ``value_expr`` directly.
        if value_binding is None:
            initial_js = json.dumps(
                "" if initial_value is None else str(initial_value)
            )
            # ``_serverSync`` adopts ``value`` from the server on a
            # @refreshable swap — ONLY when the value is server-backed
            # (``value=server_state.field``). An unbound / literal select
            # owns its value client-side : re-adopting the SSR initial on
            # every swap would wipe the user's pick (cf. render()).
            # The options list is server-owned CONFIG: the client never
            # writes it, and it does change for real (a select reloaded
            # from the database at every refresh). Re-seeded
            # UNCONDITIONALLY — otherwise it stays frozen at the first
            # mount's, for life. The VALUE, for its part, stays gated.
            # ``_labels`` travels WITH ``_options`` — same owner, same
            # reason. It joined the scope on 2026-08-28, when the
            # trigger's two expressions stopped inlining the WHOLE map
            # each on their own. Syncing it is not a detail: a
            # non-reseeded map would leave the label stale after a
            # refresh that changes the options, while the inlined
            # attribute did re-render.
            _keys = (["value", "_options", "_labels"] if server_backed
                     else ["_options", "_labels"])
            sync_marker = server_sync_marker(*_keys, enabled=True)
            value_field = f"value: {initial_js},{sync_marker}"
            read_write = (
                "_read() { return this.value; },"
                "_write(v) { this.value = v; },"
            )
        else:
            value_field = ""
            read_write = (
                f"_read() {{ return {write}; }},"
                f"_write(v) {{ {write} = v; }},"
            )

        return (
            "{...$bz.select.single,"
            + value_field
            + read_write
            + "open: false, _highlight: -1,"
            + f"_options: {options_js},"
            + f"_labels: {labels_js}"
            + "}"
        )

    def _build_bz_data_multi(
        self,
        *,
        value_binding: Any,
        write: str,
        initial_value: Any,
        options_js: str,
        labels_js: str,
        server_backed: bool,
    ) -> str:
        """Multi-mode bz-data — pills support, bulk actions, array
        membership semantics. Mirrors the Combobox multi methods
        minus the search/filter logic (no _norm / _tokens / _matches
        — all options always visible).

        ⚠️ ``value`` is exposed as a flat ``_value()`` method, not a
        getter (a getter would freeze at registration). All read sites
        call ``_value()`` / ``_picked()``."""
        # Methods live ONCE in ``$bz.select.multi`` (13_select.js) ; this
        # instance emits its data (``_options`` + ``_labels``) +
        # ``_read``/``_write`` pointing at the value cell (local: a
        # ``value`` array field ; binding: ``$bz.state.<path>``, read
        # raw — the factory's ``_value`` null-guards to []).
        initial_js = json.dumps(
            self._normalise_multi_initial(initial_value)
        )

        if value_binding is None:
            # ``_serverSync`` adopts ``value`` from the server on a
            # @refreshable swap — ONLY when server-backed (same rule as
            # single mode ; an unbound multi keeps its client picks).
            # The options list is server-owned CONFIG: the client never
            # writes it, and it does change for real (a select reloaded
            # from the database at every refresh). Re-seeded
            # UNCONDITIONALLY — otherwise it stays frozen at the first
            # mount's, for life. The VALUE, for its part, stays gated.
            # ``_labels`` travels WITH ``_options`` — same owner, same
            # reason. It joined the scope on 2026-08-28, when the
            # trigger's two expressions stopped inlining the WHOLE map
            # each on their own. Syncing it is not a detail: a
            # non-reseeded map would leave the label stale after a
            # refresh that changes the options, while the inlined
            # attribute did re-render.
            _keys = (["value", "_options", "_labels"] if server_backed
                     else ["_options", "_labels"])
            sync_marker = server_sync_marker(*_keys, enabled=True)
            value_field = f"value: {initial_js},{sync_marker}"
            read_write = (
                "_read() { return this.value; },"
                "_write(v) { this.value = v; },"
            )
        else:
            value_field = ""
            read_write = (
                f"_read() {{ return {write}; }},"
                f"_write(v) {{ {write} = v; }},"
            )

        return (
            "{...$bz.select.multi,"
            + value_field
            + read_write
            + "open: false, _highlight: -1,"
            + f"_options: {options_js},"
            + f"_labels: {labels_js}"
            + "}"
        )


__all__ = ["Select"]
