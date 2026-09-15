"""``Slider`` — drag-to-pick numeric value, single or range.

Single mode (default) : one handle, one scalar value. Range mode
(``range=True``) : two handles, a ``[start, end]`` array value.
Both share the same render path ; the difference is the number of
handles and the value shape.

Interactions :

- **Drag** : pointer-down on a handle starts a drag. The track
  ``setPointerCapture`` so the pointer-move keeps tracking even
  when the cursor leaves the handle. Drag-induced updates skip the
  CSS transition (via ``data-dragging``) so the handle tracks the
  pointer 1:1 with no easing lag.
- **Click on track** : in single mode jumps the value to the
  clicked position. In range mode moves whichever handle is
  closer to the click.
- **Keyboard** : arrow keys ±step ; PageUp/Down ±step*10 ;
  Home/End to bounds. Each handle handles its own keyboard.
- **Tooltip** : the live value pops up above the handle on
  hover / focus / drag, hides otherwise.

A11y :

- Each handle wears ``role="slider"`` + ``aria-valuemin``,
  ``aria-valuemax``, reactive ``bz-attr:aria-valuenow``.
- The handle is the focusable element (``tabindex="0"``).
- Range handles get an explicit ``aria-label="start"`` /
  ``"end"`` so screen readers can distinguish them.

Form integration : when ``value`` is a binding, ``AUTONAME_FROM
= "value"`` derives the HTML ``name`` from the field. Range values
ride as ``JSON.stringify([start, end])`` on a hidden input — same
idiom Select / Combobox use for their multi mode.

Imperative API (cf. ``imperative-api.md`` § input-value family) :

- ``.set(value)`` — write-through binding if any, else DOM dispatch.
  ``value`` is a scalar in single mode, ``[start, end]`` in range.
- ``.clear()`` — single → reset to ``min`` ; range → reset to
  ``[min, max]`` (full span). Sugar over ``.set()``.
- ``.focus()`` / ``.blur()`` — direct DOM commands targeting the
  first handle.

Runtime notes :

- ``bz-on`` carries no modifier grammar, so every modifier is inlined :
  ``.stop`` → ``$event.stopPropagation();``, ``.self`` → a target guard,
  key filters → a ``$event.key`` guard.
- There is no ``.window`` modifier : the drag flow registers ONE window
  ``pointermove`` + ``pointerup`` pair on the root via
  ``$bz.helpers.onWindow`` in ``bz-init``. ``_dragging`` carries the
  active target, so a single listener routes correctly.
- Scope methods can't reach ``$refs`` / ``$el``, so the track and change
  carrier are captured into ``_track`` / ``_carrier`` at ``bz-init`` ;
  ``_emitChange`` defers via ``queueMicrotask``.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any, ClassVar

from bretzel.components.base import Component, reactive_prop
from bretzel.components.base._wiring import (
    SERVER_ACTION_ATTRS,
    bool_attr,
    hidden_carrier_attrs,
    relocate_server_action,
    server_sync_marker,
    theme_context,
)
from bretzel.components.inputs.slider.theme import SLIDER_THEME
from bretzel.core.tree import Element, Node
from bretzel.render import text
from bretzel.state.scopes.client import ClientBinding

# Native HTMX action attrs a callable handler lands on the root via
# ``emit_attrs`` ; relocated wholesale to the carrier that holds
# name+value (the dispatcher reads form-data from there).
_ACTION_ATTRS_TO_RELOCATE = SERVER_ACTION_ATTRS


class Slider(Component):
    """Drag-to-pick numeric input, single or range."""

    THEME: ClassVar[dict[str, Any]] = SLIDER_THEME
    THEME_KEY: ClassVar[str] = "slider"
    IS_CONTAINER: ClassVar[bool] = False
    BINDABLE_PROPS: ClassVar[tuple[str, ...]] = ("value", "disabled")
    IMPERATIVE: ClassVar[tuple[str, ...]] = ("set", "clear", "focus", "blur")
    EVENTS: ClassVar[tuple[str, ...]] = ("change", "focus", "blur")

    name: str | None = reactive_prop(default=None, emit_attr=False)
    value: Any = reactive_prop(default=None, emit_attr=False, writes=True, names_field=True)
    min: float = reactive_prop(default=0.0, emit_attr=False)
    max: float = reactive_prop(default=100.0, emit_attr=False)
    step: float = reactive_prop(default=1.0, emit_attr=False)
    range: bool = reactive_prop(default=False, emit_attr=False)
    disabled: bool = reactive_prop(default=False, emit_attr=False)
    required: bool = reactive_prop(default=False, emit_attr=False)
    color: str = reactive_prop(default="primary", emit_attr=False)
    size: str = reactive_prop(default="md", emit_attr=False)

    def __init__(
        self,
        *,
        value: Any = None,
        min: float | None = None,
        max: float | None = None,
        step: float | None = None,
        range: bool | None = None,
        name: str | None = None,
        disabled: bool | None = None,
        required: bool | None = None,
        color: str | None = None,
        size: str | None = None,
        on_change: Callable[..., Any] | str | None = None,
        on_focus: Callable[..., Any] | str | None = None,
        on_blur: Callable[..., Any] | str | None = None,
        **kwargs: Any,
    ) -> None:
        # Forward direct : le socle drope les kwargs reactive None (garde le defaut).
        super().__init__(
            name=name, value=value,
            min=min, max=max, step=step,
            range=range,
            disabled=disabled, required=required,
            color=color, size=size,
            on_change=on_change,
            on_focus=on_focus,
            on_blur=on_blur,
            **kwargs,
        )

    # ── Imperative write-only API ─────────────────────────────────────

    def set(self, value: Any) -> str:
        return self._value_command(value)

    def clear(self) -> str:
        """Reset to a "neutral" value :
        - single mode → ``min``
        - range mode  → ``[min, max]`` (full span)
        Sugar over ``.set()`` so the clear path goes through the
        same code as any external set."""
        is_range = bool(self._reactive_values.get("range"))
        min_v = float(self._reactive_values.get("min") or 0.0)
        max_v = float(self._reactive_values.get("max") or 100.0)
        if is_range:
            return self.set([min_v, max_v])
        return self.set(min_v)

    def focus(self) -> str:
        return (
            f"document.getElementById('{self.id}')"
            f".querySelector('[role=slider]').focus()"
        )

    def blur(self) -> str:
        return (
            f"document.getElementById('{self.id}')"
            f".querySelector('[role=slider]').blur()"
        )


    # ── Render ─────────────────────────────────────────────────────────

    def render(self) -> Element:
        _theme, slots, sizes, size_key, _color = theme_context(self)
        size_map = sizes.get(size_key, sizes.get("md", {}))
        is_range = bool(self._reactive_values.get("range"))
        disabled = bool(self._reactive_values.get("disabled"))
        required = bool(self._reactive_values.get("required"))
        # ``disabled`` is a BINDABLE_PROP : it can be a static bool OR a
        # ClientBinding. ``_disabledState()`` must reflect the LIVE value
        # so the pointer / keyboard guards actually bail (the factory's
        # default returns a constant ``false`` — a div-based control has
        # no native ``disabled`` to lean on, unlike NumberInput's input).
        # ``disabled_js`` is the JS the per-instance override returns ;
        # ``None`` → keep the factory default (never disabled).
        disabled_binding = self._binding_metadata.get("disabled")
        if disabled_binding is not None:
            disabled_js: str | None = f"!!({disabled_binding.binding_path()})"
        elif disabled:
            disabled_js = "true"
        else:
            disabled_js = None
        min_v = float(self._reactive_values.get("min") or 0.0)
        max_v = float(self._reactive_values.get("max") or 100.0)
        step_v = float(self._reactive_values.get("step") or 1.0)

        def _resolve(template: str) -> str:
            return template

        # ── Initial value normalisation ─────────────────────────────
        raw_initial = self._reactive_values.get("value")
        if is_range:
            if isinstance(raw_initial, (list, tuple)) and len(raw_initial) >= 2:
                initial_value = [float(raw_initial[0]), float(raw_initial[1])]
            else:
                initial_value = [min_v, max_v]
        else:
            if raw_initial is None:
                initial_value = min_v
            else:
                try:
                    initial_value = float(raw_initial)
                except (TypeError, ValueError):
                    initial_value = min_v

        # ── Value binding resolution ────────────────────────────────
        value_binding = self._binding_metadata.get("value")
        if value_binding is not None:
            value_expr = value_binding.binding_path()
            write_in_method = value_expr  # full path works anywhere
        else:
            value_expr = "value"
            write_in_method = "this.value"

        # ── Event relocation ────────────────────────────────────────
        # change → hidden input (form-data dispatcher reads name+value)
        # focus / blur → first handle (the focusable element)
        # A callable handler rides as the native HTMX action set, a
        # string handler as ``bz-on:<event>`` ; relocate both flavours.
        root_attrs = self.emit_attrs()
        relocated_to_hidden: dict[str, Any] = {}
        relocated_to_handle: dict[str, Any] = {}
        # Only ONE server callable can be wired per instance (no
        # ALLOW_MULTI_SERVER_EVENTS on Slider), so ``hx-trigger`` — read
        # BEFORE any relocation — tells us which event it actually
        # belongs to. Blindly relocating SERVER_ACTION_ATTRS to the
        # hidden input regardless of that value used to misroute a
        # callable ``on_focus=``/``on_blur=`` there : the hidden input
        # never fires focus/blur natively, and the line below used to
        # force-overwrite ``hx-trigger`` to ``"change"`` unconditionally
        # — so the handler silently fired on ``change`` instead. Cf.
        # traps.md § "Slider on_focus/on_blur callable misrouted".
        # Le routage vit au socle. Il épingle aussi ``hx-trigger="change"``
        # sur le porteur de valeur — un ``<input type=hidden>`` ne fire
        # jamais ``change`` nativement, c'est ``change_emit_effect`` qui le
        # dispatche.
        relocate_server_action(
            root_attrs,
            value_carrier=relocated_to_hidden,
            focusable=relocated_to_handle,
        )
        if "bz-on:change" in root_attrs:
            relocated_to_hidden["bz-on:change"] = root_attrs.pop("bz-on:change")
        for ev_attr in ("bz-on:focus", "bz-on:blur"):
            if ev_attr in root_attrs:
                relocated_to_handle[ev_attr] = root_attrs.pop(ev_attr)

        # ── Form-data name (autoname) ───────────────────────────────
        derived_name = self._derive_field_name()  # reused by value_server_backed below
        fallback = "value" if relocated_to_hidden else None
        name = self._reactive_values.get("name") or derived_name or fallback
        # ``_serverSync`` re-adopts ``value`` from the server on a
        # @refreshable swap — ONLY when server-backed (``value=
        # server_state.field``). An unbound / literal slider owns its
        # position client-side : re-adopting the SSR initial on every swap
        # would reset the user's drag when an unrelated handler refreshes
        # the section. Same gate as Select / Combobox (cf. traps.md).
        # ``derived_name`` (above) already carries the field_name stamp in
        # local mode — reuse it rather than re-reading the value.
        value_server_backed = self._value_server_backed("value")

        # ── Hidden input ────────────────────────────────────────────
        hidden_nodes: list[Node] = []
        if name or relocated_to_hidden:
            if is_range:
                initial_str = json.dumps(
                    [float(v) for v in initial_value]
                )
                value_directive = (
                    f"JSON.stringify({value_expr} || [])"
                )
            else:
                initial_str = str(initial_value)
                value_directive = f"String({value_expr})"
            # ``dispatch=None`` : Slider est le seul contrôle à tirer son
            # ``change`` depuis une MÉTHODE DE SCOPE (``_emitChange``, qui
            # défère par ``queueMicrotask`` après la fin du geste) plutôt
            # que d'un ``bz-effect`` sur la valeur — un drag écrit la
            # valeur en continu, et un dispatch par tick POSTerait à chaque
            # pixel. Le refus est écrit ICI, au site de construction, au
            # lieu de se déduire d'un `bz-effect` absent.
            hidden_attrs: dict[str, Any] = dict(
                hidden_carrier_attrs(
                    value_directive, initial=initial_str, dispatch=None
                )
            )
            if name:
                hidden_attrs["name"] = str(name)
            if required:
                hidden_attrs["required"] = True
            hidden_attrs.update(relocated_to_hidden)
            hidden_nodes.append(
                Element(tag="input", attrs=hidden_attrs, children=())
            )

        # ── bz-data : range or scalar ───────────────────────────────
        bz_data = self._build_bz_data(
            is_range=is_range,
            value_binding=value_binding,
            value_expr=value_expr,
            write=write_in_method,
            initial_value=initial_value,
            min_v=min_v,
            max_v=max_v,
            step_v=step_v,
            server_backed=value_server_backed,
            disabled_js=disabled_js,
        )

        # ── Track + fill + handles ──────────────────────────────────
        track_class = " ".join(p for p in (
            slots.get("track", ""),
            size_map.get("track", ""),
        ) if p)
        fill_class = _resolve(slots.get("fill", ""))
        handle_class = " ".join(p for p in (
            _resolve(slots.get("handle", "")),
            size_map.get("handle", ""),
        ) if p)
        tooltip_class = slots.get("tooltip", "")

        # Fill positioning :
        # - single : ``left: 0%``, ``width: pct(value)%``
        # - range  : ``left: pct(start)%``, ``width: pct(end)-pct(start)%``
        if is_range:
            fill_style = (
                "'left: ' + _pct(_picked()[0]) + '%; "
                "width: ' + (_pct(_picked()[1]) - _pct(_picked()[0])) + '%'"
            )
        else:
            fill_style = (
                "'left: 0%; width: ' + _pct(_picked()) + '%'"
            )
        fill_node = Element(
            tag="div",
            attrs={
                "class": fill_class,
                "bz-attr:style": fill_style,
                # Data-attrs reactive : stringify so the runtime keeps
                # the literal ``"false"`` (CSS ``data-[dragging=true]``
                # selectors need a present attribute). ``bz-attr`` drops
                # the attribute on a bare boolean ``false``.
                "bz-attr:data-dragging": (
                    bool_attr("_dragging !== null")
                ),
            },
            children=(),
        )

        # Handles. Single = 1, range = 2 (start + end).
        handle_nodes: list[Node] = []
        if is_range:
            handle_nodes.append(self._build_handle(
                handle_class=handle_class,
                tooltip_class=tooltip_class,
                target="start",
                pct_expr="_pct(_picked()[0])",
                value_text_expr="_picked()[0]",
                aria_label=text("slider.range_start"),
                relocated_attrs=relocated_to_handle,
                disabled=disabled,
            ))
            handle_nodes.append(self._build_handle(
                handle_class=handle_class,
                tooltip_class=tooltip_class,
                target="end",
                pct_expr="_pct(_picked()[1])",
                value_text_expr="_picked()[1]",
                aria_label=text("slider.range_end"),
                # Only the first handle relays focus / blur events
                # (Combobox / Select do the same with their trigger).
                relocated_attrs={},
                disabled=disabled,
            ))
        else:
            handle_nodes.append(self._build_handle(
                handle_class=handle_class,
                tooltip_class=tooltip_class,
                target="value",
                pct_expr="_pct(_picked())",
                value_text_expr="_picked()",
                aria_label=None,
                relocated_attrs=relocated_to_handle,
                disabled=disabled,
            ))

        track_attrs: dict[str, Any] = {
            "class": track_class,
            "bz-ref": "bztrack",
            # Click anywhere on the track to jump the closest
            # handle there. ``_jumpToPointer`` reads the click
            # X relative to the track and writes the value via
            # the canonical setter. ``.self`` inlined : only react
            # when the track itself (not a handle) is the target.
            "bz-on:pointerdown": (
                "if ($event.target !== $el) return; "
                "_jumpToPointer($event)"
            ),
        }
        # Disabled : block ALL pointer interaction at the track (it
        # cascades to the handles — none re-enables pointer-events). The
        # ``cursor`` / ``opacity`` muted visual lives on the ROOT, NOT
        # here : ``pointer-events: none`` makes the track transparent to
        # the mouse, so its own ``cursor`` is ignored — the hover falls
        # THROUGH to the root (which keeps pointer-events auto), and the
        # root's ``cursor-not-allowed`` is what the user sees. Reactive so
        # a bound ``disabled`` toggles live ; the scope JS guards are
        # defence-in-depth (and cover the imperative ``.set()`` path).
        # Emitted only when disable-able, to avoid a dead effect on every
        # enabled slider.
        if disabled_js is not None:
            track_attrs["bz-class"] = (
                "{'pointer-events-none': _disabledState()}"
            )
        track_node = Element(
            tag="div",
            attrs=track_attrs,
            children=(fill_node, *handle_nodes),
        )

        # ── Root assembly ───────────────────────────────────────────
        root_attrs["class"] = " ".join(p for p in (
            slots.get("root", ""),
        ) if p)
        if disabled:
            root_attrs["aria-disabled"] = "true"
        # Muted visual + the not-allowed cursor : on the ROOT (keeps
        # pointer-events auto) so the cursor actually shows when hovering
        # the pointer-events-none track (cf. track bz-class above).
        if disabled_js is not None:
            root_attrs["bz-class"] = (
                "{'opacity-50 cursor-not-allowed': _disabledState()}"
            )
        root_attrs["bz-data"] = bz_data
        # Capture the track + change carrier (scope methods have no
        # ``$refs`` / ``$el`` in reach), and register the window-level
        # pointer flow ONCE here — V3 ``bz-on`` has no ``.window``
        # modifier, so drag-move / drag-end ride ``$bz.helpers.onWindow``
        # (one pair for both handles ; ``_dragging`` carries the target).
        root_attrs["bz-init"] = (
            "_track = $refs.bztrack; "
            "_carrier = $refs.bzhidden || $el; "
            "$bz.helpers.onWindow('pointermove', (e) => { "
            "if (_dragging !== null) _drag(e); }); "
            "$bz.helpers.onWindow('pointerup', (e) => { "
            "if (_dragging !== null) _endDrag(e); })"
        )
        # Imperative-API listener. The scope ``_setValue`` fires change
        # itself (uniform with drag / keyboard paths).
        root_attrs["bz-on:bz-set"] = "_setValue($event.detail.value)"

        return Element(
            tag=self._tag,
            attrs=root_attrs,
            children=(*hidden_nodes, track_node),
        )

    # ── Helpers ────────────────────────────────────────────────────────

    def _build_handle(
        self,
        *,
        handle_class: str,
        tooltip_class: str,
        target: str,
        pct_expr: str,
        value_text_expr: str,
        aria_label: str | None,
        relocated_attrs: dict[str, Any],
        disabled: bool,
    ) -> Element:
        """One draggable handle + its hover/focus tooltip.

        ``target`` is the field name the drag writes to inside the
        bz-data scope : ``"value"`` for single mode ; ``"start"`` /
        ``"end"`` for range mode. The drag / keyboard handlers route
        to ``_setHandle(target, newValue)`` which knows how to write
        the value (binding path or local field, scalar or array).
        """
        target_js = json.dumps(target)
        # Combine (don't overwrite) when a user-relocated client-string
        # handler targets the SAME event as the handle's own internal
        # focus/blur tooltip-visibility tracking (``_focused``). A blind
        # ``**relocated_attrs`` spread here used to silently destroy the
        # internal wiring by dict-key collision. Internal logic runs
        # FIRST so ``_focused`` stays consistent before the caller's
        # expression runs. Server callables never collide -- they route
        # through ``hx-*``/``data-bz-sig``, never ``bz-on:<event>``.
        _internal_focus_blur = {
            "bz-on:focus": f"_focused = {target_js}",
            "bz-on:blur": "_focused = null",
        }
        for ev_attr, internal_expr in _internal_focus_blur.items():
            if ev_attr in relocated_attrs:
                relocated_attrs = {
                    **relocated_attrs,
                    ev_attr: f"{internal_expr}; {relocated_attrs[ev_attr]}",
                }
        attrs: dict[str, Any] = {
            "class": handle_class,
            "role": "slider",
            "tabindex": "0" if not disabled else "-1",
            "bz-attr:style": f"'left: ' + {pct_expr} + '%'",
            "bz-attr:data-dragging": (
                bool_attr(f"_dragging === {target_js}")
            ),
            "bz-attr:aria-valuenow": value_text_expr,
            "bz-attr:aria-valuemin": "_min",
            "bz-attr:aria-valuemax": "_max",
            "bz-attr:aria-disabled": bool_attr("_disabledState()"),
            # Drag : capture the pointer on the TRACK so the move
            # keeps firing even when the cursor leaves the handle.
            # ``.stop`` inlined so the track's pointerdown ``.self``
            # guard doesn't ALSO fire (we don't want a click-jump on
            # top of the drag). The window pointermove / pointerup
            # flow is registered on the root's bz-init.
            "bz-on:pointerdown": (
                f"$event.stopPropagation(); "
                f"_startDrag({target_js}, $event)"
            ),
            # Keyboard nav : standard slider semantics. Key filters +
            # ``.prevent`` inlined (V3 bz-on has no modifier grammar).
            "bz-on:keydown": (
                f"const k = $event.key; "
                f"if (k === 'ArrowLeft' || k === 'ArrowDown') {{ "
                f"$event.preventDefault(); _nudge({target_js}, -_step); }} "
                f"else if (k === 'ArrowRight' || k === 'ArrowUp') {{ "
                f"$event.preventDefault(); _nudge({target_js}, _step); }} "
                f"else if (k === 'PageDown') {{ "
                f"$event.preventDefault(); _nudge({target_js}, -_step * 10); }} "
                f"else if (k === 'PageUp') {{ "
                f"$event.preventDefault(); _nudge({target_js}, _step * 10); }} "
                f"else if (k === 'Home') {{ "
                f"$event.preventDefault(); _setHandle({target_js}, _min); "
                f"_emitChange(); }} "
                f"else if (k === 'End') {{ "
                f"$event.preventDefault(); _setHandle({target_js}, _max); "
                f"_emitChange(); }}"
            ),
            # Tooltip toggle : hover / focus / drag → visible.
            "bz-on:mouseenter": f"_hovered = {target_js}",
            "bz-on:mouseleave": "_hovered = null",
            "bz-on:focus": f"_focused = {target_js}",
            "bz-on:blur": "_focused = null",
            **relocated_attrs,
        }
        if aria_label:
            attrs["aria-label"] = aria_label
        if disabled:
            attrs["aria-disabled"] = "true"

        # Tooltip child : visible when this handle is hovered /
        # focused / being dragged. ``bz-show`` toggles display ; the
        # FOUC pre-stamp keeps it hidden before the runtime boots.
        tooltip_attrs: dict[str, Any] = {
            "class": tooltip_class,
            "bz-show": (
                f"_hovered === {target_js} || "
                f"_focused === {target_js} || "
                f"_dragging === {target_js}"
            ),
            "bz-text": value_text_expr,
            "style": "display:none",
        }
        tooltip = Element(
            tag="div",
            attrs=tooltip_attrs,
            children=(),
        )

        return Element(tag="div", attrs=attrs, children=(tooltip,))

    def _build_bz_data(
        self,
        *,
        is_range: bool,
        value_binding: ClientBinding | None,
        value_expr: str,
        write: str,
        initial_value: Any,
        min_v: float,
        max_v: float,
        step_v: float,
        server_backed: bool,
        disabled_js: str | None,
    ) -> str:
        """The bz-data scope.

        Two read shapes :
        - **Local mode** (no binding) : ``value`` field carries the
          scalar (single) or ``[start, end]`` array (range).
        - **Binding mode** : ``_read()`` / ``_write()`` lisent et écrivent
          ``$bz.state.<path>``. ⚠️ PAS un ``get value()`` — le commentaire
          25 lignes plus bas explique justement que ``scope.absorb`` gèle les
          getters (cette ligne annonçait le contraire jusqu'au 2026-08-01).

        Methods (mode-aware) :
        - ``_picked()`` → scalar (single) or ``[start, end]`` (range)
        - ``_pct(v)`` → percentage along the track ([0..100])
        - ``_clamp(v)`` → snap to step + clamp to bounds
        - ``_setHandle(target, raw)`` → write one handle's value
          (target = "value" single, "start" / "end" range). Range
          clamps start ≤ end via swap.
        - ``_setValue(raw)`` → external imperative API entry point
          (accepts scalar or array, splits as needed)
        - ``_startDrag / _drag / _endDrag`` → pointer flow
        - ``_jumpToPointer`` → click-on-track snap
        - ``_nudge(target, delta)`` → keyboard step
        - ``_emitChange()`` → dispatch change event from the captured
          carrier (``this._carrier``, no ``$refs`` in a scope method)
        - ``_disabledState()`` → reads reactive disabled if any
        """
        # The ~15 drag/keyboard/pointer/clamp methods live ONCE in the
        # runtime factory ``$bz.slider.scope`` (bretzel/runtime/_src/
        # 12_slider.js). Each instance emits only its state + ``_read``/
        # ``_write`` (value access) + a ``_range`` flag ; the factory's
        # mode-specific methods branch on ``this._range``.
        #
        # ``_read``/``_write`` (helpers, not frozen) point the shared
        # methods at the value cell : local mode → a ``value`` field,
        # binding mode → ``$bz.state.<path>`` (read raw ; ``_picked``
        # handles the null → [min,max] / min fallback). No live
        # ``get value()`` literal — ``scope.absorb`` freezes getters
        # (cf. traps.md). The hidden input reads ``value_expr`` directly.
        if is_range:
            initial_js = json.dumps(list(initial_value))
        else:
            initial_js = json.dumps(float(initial_value))

        # La CONFIG est server-owned : le client ne l'écrit jamais, donc elle
        # se re-sème sans condition. ``absorb`` ne réécrit jamais un signal
        # existant (``03_scope.js``) — sans ces clés, un ``min=`` / ``max=`` /
        # ``step=`` changé côté serveur restait figé à sa valeur du premier
        # montage. Même racine que ``_total`` de Pagination et ``_step`` de
        # NumberInput.
        #
        # ⚠️ PAS ``_dragging`` / ``_hovered`` / ``_focused`` / ``_track`` /
        # ``_carrier`` / ``_precCache`` : état d'interaction CLIENT. Les
        # re-semer couperait un drag en cours.
        config_sync = ["_range", "_min", "_max", "_step"]

        if value_binding is None:
            # ``value`` reste GATÉE, elle : re-semée seulement si le serveur
            # en est propriétaire — un slider littéral garde la position que
            # le client vient de faire glisser.
            keys = ["value", *config_sync] if server_backed else config_sync
            sync_marker = server_sync_marker(*keys, enabled=True)
            value_field = f"value: {initial_js},{sync_marker}"
            read_write = (
                "_read() { return this.value; },"
                "_write(v) { this.value = v; },"
            )
        else:
            # Store client propriétaire de la valeur ; la config reste au
            # serveur.
            value_field = server_sync_marker(
                *config_sync, enabled=True
            ).lstrip()
            read_write = (
                f"_read() {{ return {write}; }},"
                f"_write(v) {{ {write} = v; }},"
            )

        # Override the factory's constant ``_disabledState() {return false}``
        # with the live state (static ``true`` or a binding read) so the
        # pointer / keyboard / imperative guards bail when disabled.
        disabled_override = (
            f"_disabledState() {{ return {disabled_js}; }},"
            if disabled_js is not None else ""
        )
        state = (
            value_field
            + read_write
            + disabled_override
            + f"_range: {'true' if is_range else 'false'},"
            + f"_min: {json.dumps(min_v)},"
            + f"_max: {json.dumps(max_v)},"
            + f"_step: {json.dumps(step_v)},"
            + "_dragging: null, _hovered: null, _focused: null,"
            + "_track: null, _carrier: null,"
            + "_precCache: undefined"
        )

        return "{...$bz.slider.scope," + state + "}"


__all__ = ["Slider"]
