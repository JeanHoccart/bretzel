"""``NumberInput`` — numeric input with vertical ± stepper buttons.

Sits next to :class:`Input` in the form family. We ship a dedicated
component (rather than ``ui.input(type="number")``) because the
behavior surface is too different :

- stepper buttons (``+ step`` / ``- step``)
- clamp to ``min`` / ``max`` on blur (browser native ``type=number``
  silently lets out-of-range values stick — the user submits invalid
  data)
- float precision rounding (``0.1 + 0.1 + 0.1 === 0.30000000000000004``
  — same trick as Slider, ``toFixed(stepPrecision)``)
- keyboard nav (ArrowUp/Down ± step, PageUp/Down ± step*10)
- optional wheel-while-focused inc/dec
- imperative ``.increment()`` / ``.decrement()`` (in addition to the
  standard ``.set / .clear / .focus / .blur``)

Form integration : ``AUTONAME_FROM = "value"``, single hidden value
on the visible ``<input>`` itself (no separate hidden node ; the
form-data reads the input directly).

Imperative API (cf. ``imperative-api.md`` § input-value family) :

- ``.set(value)`` — write-through binding if any, else DOM dispatch.
- ``.clear()`` — reset to ``min`` if bounded, else ``0``.
- ``.focus()`` / ``.blur()`` — direct DOM commands on the input.
- ``.increment()`` / ``.decrement()`` — dispatch a ``bz-step``
  CustomEvent with ``detail.delta = ±step`` ; the bz-data listener
  computes the new value (clamped, snapped to step) and writes it.

The ``bz-on`` directive has no modifier grammar (no ``.prevent`` / key
filters), so those are inlined into the handler bodies below. Scope
methods run bound to the proxy and can't reach ``$refs`` / ``$el`` — the
carrier ``<input>`` is captured into ``_carrier`` at ``bz-init`` so
``_emitChange`` can dispatch the synthetic ``change`` from there.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any, ClassVar

from bretzel.components.base import Component, reactive_prop
from bretzel.components.base._wiring import (
    SERVER_ACTION_ATTRS,
    server_sync_marker,
    theme_context,
)
from bretzel.components.inputs.number_input.theme import (
    NUMBER_INPUT_THEME,
)
from bretzel.components.primitives.icon import Icon
from bretzel.core.tree import Element, Node
from bretzel.render import text
from bretzel.state.scopes.client import ClientBinding

# Action attrs land on the root by default, but must move onto the
# focusable ``<input>`` (the form-data carrier) so the dispatcher reads
# name+value from the element that actually holds them.
_ACTION_ATTRS_TO_RELOCATE = SERVER_ACTION_ATTRS


class NumberInput(Component):
    """Numeric input with vertical ± stepper buttons."""

    THEME: ClassVar[dict[str, Any]] = NUMBER_INPUT_THEME
    THEME_KEY: ClassVar[str] = "number_input"
    IS_CONTAINER: ClassVar[bool] = False
    BINDABLE_PROPS: ClassVar[tuple[str, ...]] = ("value", "disabled")
    IMPERATIVE: ClassVar[tuple[str, ...]] = ("set", "clear", "focus", "blur", "increment", "decrement")
    EVENTS: ClassVar[tuple[str, ...]] = ("change", "focus", "blur")

    name: str | None = reactive_prop(default=None, emit_attr=False)
    value: Any = reactive_prop(default=None, emit_attr=False, writes=True, names_field=True)
    min: Any = reactive_prop(default=None, emit_attr=False)
    max: Any = reactive_prop(default=None, emit_attr=False)
    step: float = reactive_prop(default=1.0, emit_attr=False)
    placeholder: str | None = reactive_prop(default=None, emit_attr=False)
    wheel: bool = reactive_prop(default=True, emit_attr=False)
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
        name: str | None = None,
        placeholder: str | None = None,
        wheel: bool | None = None,
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
            name=name, value=value,
            min=min, max=max, step=step,
            placeholder=placeholder, wheel=wheel,
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
        """Reset to ``min`` if bounded, else ``0``."""
        min_v = self._reactive_values.get("min")
        target = float(min_v) if min_v is not None else 0.0
        return self.set(target)

    def focus(self) -> str:
        return (
            f"document.getElementById('{self.id}')"
            f".querySelector('input[type=text]').focus()"
        )

    def blur(self) -> str:
        return (
            f"document.getElementById('{self.id}')"
            f".querySelector('input[type=text]').blur()"
        )

    def increment(self) -> str:
        """Bump the value by ``+step``. Goes through the bz-data's
        ``_nudge`` method so clamping + precision are respected."""
        return self._dispatch_command("bz-step", value=1)

    def decrement(self) -> str:
        """Bump the value by ``-step``."""
        return self._dispatch_command("bz-step", value=-1)


    # ── Render ─────────────────────────────────────────────────────────

    def render(self) -> Element:
        _theme, slots, sizes, size_key, _color = theme_context(self)
        size_map = sizes.get(size_key, sizes.get("md", {}))
        disabled = bool(self._reactive_values.get("disabled"))
        required = bool(self._reactive_values.get("required"))
        placeholder = self._reactive_values.get("placeholder") or ""
        wheel_on = bool(self._reactive_values.get("wheel", True))

        min_raw = self._reactive_values.get("min")
        max_raw = self._reactive_values.get("max")
        step_raw = self._reactive_values.get("step") or 1.0
        min_js = "null" if min_raw is None else json.dumps(float(min_raw))
        max_js = "null" if max_raw is None else json.dumps(float(max_raw))
        step_js = json.dumps(float(step_raw))

        def _resolve(template: str) -> str:
            return template

        # ── Initial value ───────────────────────────────────────────
        raw_initial = self._reactive_values.get("value")
        if raw_initial is None or raw_initial == "":
            initial_value: float | None = None
        else:
            try:
                initial_value = float(raw_initial)
            except (TypeError, ValueError):
                initial_value = None

        # ── Value binding resolution ────────────────────────────────
        value_binding = self._binding_metadata.get("value")
        if value_binding is not None:
            value_expr = value_binding.binding_path()
            write_in_method = value_expr
        else:
            value_expr = "value"
            write_in_method = "this.value"

        # ── Event relocation ────────────────────────────────────────
        # The shell wrapper just holds layout — all events live on the
        # focusable input. Relocate both flavours : a callable handler
        # (native HTMX action set) and a string handler (``bz-on:<event>``).
        root_attrs = self.emit_attrs()
        relocated_to_input: dict[str, Any] = {}
        for ev_attr in (
            "bz-on:change", "bz-on:focus", "bz-on:blur",
            *_ACTION_ATTRS_TO_RELOCATE,
        ):
            if ev_attr in root_attrs:
                relocated_to_input[ev_attr] = root_attrs.pop(ev_attr)

        # ── on_change must see the COMMITTED value, not the raw DOM ──
        # The browser fires a NATIVE ``change`` on blur *before* our
        # ``bz-on:blur`` reformats the draft — so a user ``on_change``
        # listening on ``change`` would read the dirty raw text (and
        # fire twice, once more for our synthetic dispatch). We route
        # every observer onto a private ``bzchange`` event that ONLY
        # ``_emitChange`` dispatches — after ``_write`` + the reactive
        # flush settle, so ``$event.target.value`` is canonical. The
        # native ``change`` is left with no listeners. Covers both the
        # string handler (``bz-on:change``) and the callable handler
        # (``hx-trigger="change"`` ± a debounce/throttle modifier).
        if "bz-on:change" in relocated_to_input:
            relocated_to_input["bz-on:bzchange"] = relocated_to_input.pop("bz-on:change")
        # ``hx-trigger`` is ``"change"`` ± a leading-token modifier
        # (``"change delay:300ms"``) — rewrite only that first token.
        if trigger := relocated_to_input.get("hx-trigger"):
            relocated_to_input["hx-trigger"] = trigger.replace("change", "bzchange", 1)

        # ── Form-data name (autoname) ───────────────────────────────
        name = self._reactive_values.get("name") or self._derive_field_name()

        # ── Input attrs ─────────────────────────────────────────────
        input_class = " ".join(p for p in (
            slots.get("input", ""),
            size_map.get("input", ""),
        ) if p)
        # ``inputmode="decimal"`` triggers the numeric keyboard on
        # mobile without forcing ``type="number"`` (which has a lot
        # of cross-browser quirks : leading zeros stripped, ``e``
        # accepted as scientific notation, no consistent clamp, etc.).
        input_attrs: dict[str, Any] = {
            "type": "text",
            "inputmode": "decimal",
            "class": input_class,
            "bz-ref": "bzinput",
            # Capture the carrier so the scope methods (which run bound
            # to the proxy, with no ``$refs`` / ``$el`` in reach) can
            # dispatch the synthetic ``change`` from ``_emitChange``.
            "bz-init": "_carrier = $refs.bzinput || $el",
            # The visible display value : during typing the user
            # sees their raw text (so they can backspace freely) ;
            # when the input loses focus we re-render the canonical
            # form from the bound value.
            "bz-attr:value": (
                "_focused ? _draft : _displayValue()"
            ),
            # Keystroke filter. The carrier is ``type="text"`` (so we can
            # read partial drafts — ``type="number"`` returns "" on any
            # transient-invalid value, killing the draft model ; cf. the
            # module docstring). The flip side is the browser blocks
            # nothing, so a user could type letters into a "number" field.
            # ``beforeinput`` is cancelable for ``insertText`` /
            # ``insertFromPaste`` : we reject any insertion carrying a
            # char outside ``[0-9.-]`` *before* it lands, so no letter
            # ever shows and there's no caret-restore dance. ``data`` is
            # null for deletions / IME composition — left untouched.
            "bz-on:beforeinput": (
                "if ($event.data != null && "
                "/[^0-9.-]/.test($event.data)) $event.preventDefault();"
            ),
            "bz-on:input": "_draft = $event.target.value; _commitDraft(false)",
            # NOTE : we do NOT wire ``bz-on:change="_commitDraft(true)"``
            # on the input. ``_commitDraft(true)`` ends by calling
            # ``_emitChange`` which dispatches a synthetic ``change``
            # event — wiring our own listener back onto ``change`` would
            # make every commit re-trigger itself → infinite loop, page
            # froze. ``bz-on:blur`` already covers the "commit on lose
            # focus" path. Synthetic ``change`` events stay for
            # downstream observers (user's ``on_change=`` handler
            # relocated below) ; we don't listen to them ourselves.
            "bz-on:focus": (
                "_focused = true; "
                "_draft = _displayValue()"
            ),
            "bz-on:blur": "_focused = false; _commitDraft(true)",
            # Key filters inlined : the V3 ``bz-on`` directive carries no
            # ``.arrow-up`` / ``.prevent`` modifier grammar.
            "bz-on:keydown": (
                "if ($event.key === 'ArrowUp') { "
                "$event.preventDefault(); _nudge(_step); } "
                "else if ($event.key === 'ArrowDown') { "
                "$event.preventDefault(); _nudge(-_step); } "
                "else if ($event.key === 'PageUp') { "
                "$event.preventDefault(); _nudge(_step * 10); } "
                "else if ($event.key === 'PageDown') { "
                "$event.preventDefault(); _nudge(-_step * 10); }"
            ),
        }
        if wheel_on:
            # ``preventDefault`` so the page doesn't scroll while the
            # user is wheel-tweaking the value. Only when focused —
            # we don't want the page-scroll to bump unrelated number
            # inputs.
            input_attrs["bz-on:wheel"] = (
                "if (_focused) { $event.preventDefault(); "
                "_nudge($event.deltaY < 0 ? _step : -_step); }"
            )
        if placeholder:
            input_attrs["placeholder"] = placeholder
        if name:
            input_attrs["name"] = name
        if disabled:
            input_attrs["disabled"] = True
        if required:
            input_attrs["required"] = True
        # Combine (don't overwrite) when a user-relocated client-string
        # handler targets the SAME event as the component's own internal
        # wiring. A blind ``dict.update`` here used to silently destroy
        # ``_commitDraft(true)`` on ``on_blur=`` (clamp/snap/commit lost —
        # ``_emitChange`` never fires either, so ``on_change=`` goes dead
        # too) and the draft-reset on ``on_focus=``. Internal logic runs
        # FIRST so the committed state is consistent before the caller's
        # expression sees it. Server callables never collide here — they
        # route through ``hx-*``/``data-bz-sig`` (SERVER_ACTION_ATTRS),
        # never a ``bz-on:<event>`` key. Cf. traps.md § "NumberInput
        # on_blur= clobbers _commitDraft".
        for ev_attr in ("bz-on:focus", "bz-on:blur"):
            if ev_attr in relocated_to_input and ev_attr in input_attrs:
                relocated_to_input[ev_attr] = (
                    f"{input_attrs[ev_attr]}; {relocated_to_input[ev_attr]}"
                )
        input_attrs.update(relocated_to_input)

        # Reactive disabled : land the binding on the inner input.
        # The base ``emit_attrs`` already lands ``bz-attr:disabled``
        # on the wrapper, but the +/- buttons + native ``<input>`` are
        # what the disabled attribute actually acts on. Forward to the
        # carrier — ``forward_binding`` also handles ClientExpression
        # transparently (it's a ClientBinding subclass).
        self.forward_binding("disabled", input_attrs)

        input_el = Element(
            tag="input", attrs=input_attrs, children=(),
        )

        # ── Stepper buttons ─────────────────────────────────────────
        stepper_class = _resolve(slots.get("stepper", ""))
        chevron_up = self._render_chevron("chevron-up")
        chevron_down = self._render_chevron("chevron-down")
        up_btn = Element(
            tag="button",
            attrs={
                "type": "button",
                "class": stepper_class,
                "tabindex": "-1",
                "aria-label": text("number_input.increment"),
                "bz-attr:disabled": "_atMax()",
                "bz-on:click": "_nudge(_step)",
            },
            children=(chevron_up,),
        )
        down_btn = Element(
            tag="button",
            attrs={
                "type": "button",
                "class": stepper_class,
                "tabindex": "-1",
                "aria-label": text("number_input.decrement"),
                "bz-attr:disabled": "_atMin()",
                "bz-on:click": "_nudge(-_step)",
            },
            children=(chevron_down,),
        )
        steppers = Element(
            tag="div",
            attrs={"class": slots.get("steppers", "")},
            children=(up_btn, down_btn),
        )

        # ── Shell (border + focus ring around input + steppers) ────
        shell_class = " ".join(p for p in (
            _resolve(slots.get("shell", "")),
            size_map.get("shell", ""),
        ) if p)
        shell = Element(
            tag="div",
            attrs={"class": shell_class},
            children=(input_el, steppers),
        )

        # ── bz-data ─────────────────────────────────────────────────
        bz_data = self._build_bz_data(
            value_binding=value_binding,
            value_expr=value_expr,
            write=write_in_method,
            initial_value=initial_value,
            min_js=min_js,
            max_js=max_js,
            step_js=step_js,
        )

        # ── Root ────────────────────────────────────────────────────
        root_attrs["class"] = slots.get("root", "")
        root_attrs["bz-data"] = bz_data
        # Imperative listeners. These live on a directive, so ``$refs``
        # / ``$nextTick`` ARE in reach — but the scope methods they call
        # do the change-firing through ``_emitChange`` / ``this._carrier``
        # uniformly, so we just delegate.
        root_attrs["bz-on:bz-set"] = (
            "_setValue($event.detail.value)"
        )
        root_attrs["bz-on:bz-step"] = (
            "_nudge(_step * Number($event.detail.value))"
        )

        children: list[Node] = [shell]
        return Element(
            tag=self._tag, attrs=root_attrs, children=tuple(children),
        )

    # ── Helpers ────────────────────────────────────────────────────────

    def _render_chevron(self, name: str) -> Element:
        """A stepper button's glyph, dressed by the ``chevron`` slot.

        The slot was declared in the theme and documented, but never
        applied (audit F36): an override
        ``Theme(components={"number_input": {"slots": {"chevron": …}}})``
        did nothing. With no visual consequence — the ``shrink-0`` it
        carries ALREADY comes from Icon's root slot — but the theme's
        contract was broken.
        """
        icon = Icon(name, size="xs")
        Component._detach_from_parent(icon)
        return Component.with_slot_class(
            icon.render(),
            self._resolved_theme().get("slots", {}).get("chevron", ""),
        )

    def _build_bz_data(
        self,
        *,
        value_binding: ClientBinding | None,
        value_expr: str,
        write: str,
        initial_value: float | None,
        min_js: str,
        max_js: str,
        step_js: str,
    ) -> str:
        """The bz-data scope.

        Four pieces of state (the count said "three" until 2026-08-01,
        for the four bullets that follow):

        - **``value``** : the canonical numeric value (or ``null`` ⇄
          empty). Lives locally (no binding) or in
          ``$bz.state.<path>`` (binding mode).
        - **``_draft``** : the raw string in the input box during
          typing. Lets the user freely type intermediate states
          (``"-"``, ``"1."``, ``"1.0"``) without immediate clamp.
        - **``_focused``** : true while the user types. The input's
          ``bz-attr:value`` shows ``_draft`` while focused, the
          canonical re-formatted value when blurred.
        - **``_carrier``** : the ``<input>`` element, captured at
          ``bz-init`` so ``_emitChange`` (a scope method with no
          ``$refs`` in reach) can dispatch the synthetic ``change``.

        Commit flow :
        - ``bz-on:input`` → ``_commitDraft(false)`` parses the draft
          and, if valid, writes to ``value`` (no clamp yet — let user
          type ``"15"`` even if max is 10, clamp on blur).
        - ``bz-on:blur`` → ``_commitDraft(true)`` clamps + snaps to
          step + emits change.
        """
        # The heavy method bodies live ONCE in the runtime factory
        # ``$bz.numberInput.scope`` (bretzel/runtime/_src/11_number_input.js).
        # Each instance only emits its state + the ``_read`` / ``_write``
        # pair that points the shared methods at the right value cell :
        #
        # - local mode  → a ``value`` signal field on the scope ;
        # - binding mode → the ``$bz.state.<path>`` store cell (no local
        #   ``value`` ; ``_read`` null-coerces empty → null).
        #
        # We use ``_read``/``_write`` (small per-instance functions, so
        # they register as helpers — NOT frozen) rather than a live
        # ``get value()`` literal, which ``scope.absorb`` would read once
        # and freeze (cf. traps.md).
        if initial_value is None:
            initial_value_js = "null"
            initial_draft_js = "''"
        else:
            initial_value_js = json.dumps(float(initial_value))
            initial_draft_js = json.dumps(str(initial_value))

        # ``_min`` / ``_max`` / ``_step`` are CONFIG: the server always
        # owns them, the client never writes them. They must therefore be
        # re-seeded UNCONDITIONALLY — ``absorb`` never rewrites an
        # existing signal (``03_scope.js``), so without that a ``min=`` /
        # ``max=`` / ``step=`` changed server-side stayed frozen at its
        # first mount's value: the bench moved the control, the component
        # kept its old bounds. Same root as Pagination's ``_total`` /
        # ``_maxVisible``.
        #
        # ⚠️ Most certainly NOT ``_draft`` / ``_focused`` / ``_precCache``:
        # these are CLIENT buffers. Re-seeding them would overwrite the
        # typing in progress at every neighbouring swap — exactly the
        # damage the guard below avoids for ``value``.
        config_sync = ["_min", "_max", "_step"]

        if value_binding is None:
            # ``value`` stays GATED: re-seeded only if the server owns
            # it (``value=state.field``). For a literal, the bridge would
            # rewrite the signal at every swap and overwrite the user's
            # typing.
            keys = (
                ["value", *config_sync]
                if self._value_server_backed()
                else config_sync
            )
            value_field = (
                f"value: {initial_value_js},"
                f"{server_sync_marker(*keys, enabled=True)}"
            )
            read_write = (
                "_read() { return this.value; },"
                "_write(v) { this.value = v; },"
            )
        else:
            # The value as a ClientBinding: the store owns it, nothing
            # to re-seed for it — but the config stays server-owned.
            value_field = f"{server_sync_marker(*config_sync, enabled=True).lstrip()}"
            read_write = (
                f"_read() {{ const v = {write}; "
                f"return v == null || v === '' ? null : Number(v); }},"
                f"_write(v) {{ {write} = v; }},"
            )

        state = (
            value_field
            + read_write
            + f"_min: {min_js},"
            + f"_max: {max_js},"
            + f"_step: {step_js},"
            + f"_draft: {initial_draft_js},"
            + "_focused: false,"
            + "_carrier: null,"
            + "_precCache: undefined"
        )

        return "{...$bz.numberInput.scope," + state + "}"


__all__ = ["NumberInput"]
