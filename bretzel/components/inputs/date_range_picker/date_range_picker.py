"""``DateRangePicker`` — start + end date input with shared calendar popover.

Same UX shape as :class:`DatePicker` — both inputs sit inside one
focus-within frame with the shared calendar icon button. Each input
is editable ; free-form typed dates normalise to ISO on blur (cf.
:func:`normalise_to_iso_js`).

The two endpoints are always local scope vars ``vstart`` / ``vend``
(a range value is a 2-element list, so — unlike :class:`DatePicker` —
there is no single store scalar the two inputs can both address) ::

    bz-data="{open: false, vstart: 'YYYY-MM-DD', vend: 'YYYY-MM-DD'}"

- Both editable ``<input>``s carry ``bz-model="vstart"`` /
  ``bz-model="vend"`` (two-way) + a ``bz-on:blur`` free-form → ISO
  normaliser.
- The hidden form-data input carries
  ``bz-attr:value="JSON.stringify([vstart, vend])"``.
- The inner ``<bz-calendar mode="range">`` mirrors the pair onto its
  observed ``value`` ATTRIBUTE through a wrapper ``bz-effect`` +
  ``setAttribute`` (``bz-attr:value`` on a custom element writes the
  property, not the attribute — cf. traps.md) and writes the pair back
  on ``change`` (``[start, end]`` once the user closes the range — the
  popover auto-closes when ``close_on_close=True``).
- **Bound** (``value=client_state.range_v``) : ``vstart`` / ``vend``
  seed from the store list at SSR ; a wrapper ``bz-effect`` pushes
  ``[vstart, vend]`` back into ``$bz.state.X.y`` on every endpoint
  change.

Form integration : ``AUTONAME_FROM = "value"`` derives the HTML
``name`` from the bound field.
"""

from __future__ import annotations

import dataclasses as _dc
import datetime as _dt
import json
from collections.abc import Callable
from typing import Any, ClassVar

from bretzel.components.base import Component, reactive_prop
from bretzel.components.base._wiring import (
    anchored_dismiss_init,
    calendar_value_mirror,
    imperative_listeners,
    install_open_close_toggle,
    install_value_commands,
    server_sync_marker,
    theme_context,
)
from bretzel.components.inputs._picker_field import (
    anchored_panel,
    clear_button,
    detach_wrapper_carriers,
    hidden_carrier,
    panel_calendar,
    relocate_field_events,
    trigger_button,
)
from bretzel.components.inputs._wiring import date_to_iso
from bretzel.components.inputs.date_picker.date_picker import (
    normalise_to_iso_js,
)
from bretzel.components.inputs.date_range_picker.theme import (
    DATE_RANGE_PICKER_THEME,
)
from bretzel.core.tree import Element
from bretzel.render import text


def _date_to_iso(value: Any) -> str:
    """``DateRangePicker``'s date coercion — the shared one, bound to this
    component's name for the error message (audit F50 : les trois
    composants de la famille date en portaient une copie identique)."""
    return date_to_iso(value, owner="DateRangePicker")


class DateRangePicker(Component):
    """Start + end date input with shared calendar popover."""

    THEME: ClassVar[dict[str, Any]] = DATE_RANGE_PICKER_THEME
    THEME_KEY: ClassVar[str] = "date_range_picker"
    IS_CONTAINER: ClassVar[bool] = False
    BINDABLE_PROPS: ClassVar[tuple[str, ...]] = (
        "value", "min", "max", "disabled",
    )
    #: Un picker est les DEUX natures à la fois : un panneau ancré
    #: (comme `dialog`) et un champ qui porte une valeur (comme
    #: `input`). Sa surface est donc l'union des deux vocabulaires
    #: déjà fixés par ses voisins — rien d'inventé ici.
    IMPERATIVE: ClassVar[tuple[str, ...]] = (
        "open", "close", "toggle", "set", "clear", "focus", "blur",
    )
    EVENTS: ClassVar[tuple[str, ...]] = ("change", "focus", "blur")

    name: str | None = reactive_prop(default=None, emit_attr=False)
    value: Any = reactive_prop(default=None, writes=True, scope_keys=("vstart", "vend"), names_field=True)
    min: Any = reactive_prop(default=None, emit_attr=False)
    max: Any = reactive_prop(default=None, emit_attr=False)
    # ``emit_attr=False`` : la racine est un ``<div>`` wrapper, où
    # ``disabled`` ne fait RIEN. Le binding est forwardé à la main dans
    # ``render()`` sur les quatre carriers réels (champ start, champ end,
    # ×, trigger) — cf. gate ``test_binding_lands_on_carrier``.
    disabled: bool = reactive_prop(default=False, emit_attr=False)
    required: bool = reactive_prop(default=False, emit_attr=False)
    color: str = reactive_prop(default="primary", emit_attr=False)
    size: str = reactive_prop(default="md", emit_attr=False)

    def __init__(
        self,
        value: Any = None,
        *,
        placeholder_start: str = "Start",
        placeholder_end: str = "End",
        separator: str = "→",
        min: Any = None,
        max: Any = None,
        disabled_dates: list[_dt.date] | None = None,
        weekstart: int = 1,
        marks: Any = None,
        weekday_names: list[str] | None = None,
        month_names: list[str] | None = None,
        color: str | None = None,
        size: str | None = None,
        disabled: bool | None = None,
        required: bool | None = None,
        clearable: bool = True,
        close_on_close: bool = True,
        name: str | None = None,
        on_change: Callable[..., Any] | str | None = None,
        on_focus: Callable[..., Any] | str | None = None,
        on_blur: Callable[..., Any] | str | None = None,
        **kwargs: Any,
    ) -> None:
        self._placeholder_start = placeholder_start
        self._placeholder_end = placeholder_end
        # ``adopt_slot`` + ``emit_text_slot`` sont un COUPLE (cf. le docstring
        # d'emit_text_slot) : le 1er détache le Component (sinon rendu 2×), le
        # 2nd le REND (sinon il file dans TextNode() qui attend une string →
        # `'Text' object has no attribute 'replace'` au serialize). Faire l'un
        # sans l'autre échange un bug contre un autre.
        self._separator = Component.adopt_slot(separator)
        # ``None`` = « laisse le navigateur nommer », depuis
        # ``<html lang>``. Figer l'anglais ici obligeait chaque app à
        # repasser les 19 chaînes à chaque montage. Cf. ``ui.calendar``.
        self._weekday_names = list(weekday_names) if weekday_names else None
        self._month_names = list(month_names) if month_names else None
        self._disabled_dates = list(disabled_dates or [])
        # Transmis tel quel : la grille de jours est la MEME que
        # celle de ``ui.calendar``, donc une marque a une cellule ou
        # atterrir. ``ui.month_picker`` ne l'a pas : sa grille est
        # faite de MOIS, pas de jours.
        self._marks = marks
        self._weekstart = weekstart
        self._clearable = clearable
        self._close_on_close = close_on_close

        # Forward direct : le socle drope les kwargs reactive None (garde le defaut).
        super().__init__(
            name=name, value=value,
            min=min, max=max,
            color=color, size=size,
            disabled=disabled, required=required,
            on_change=on_change,
            on_focus=on_focus,
            on_blur=on_blur,
            **kwargs,
        )
        # APRÈS `super().__init__` : les deux installeurs lisent
        # `_binding_metadata`, qui n'est peuplé qu'à ce moment-là.
        install_open_close_toggle(self)
        # ⚠️ PAS `"input"` : le premier `<input>` d'un picker est le
        # porteur CACHÉ (`hidden_carrier`), qui ne prend pas le
        # focus. Mesuré — `.focus()` ne faisait rien sur les six.
        install_value_commands(
            self, focus_selector="input:not([type=hidden])"
        )

    def render(self) -> Element:
        theme, slots, _sizes, size_key, color = theme_context(self)
        size_map = theme.get("sizes", {})


        def sz(group: str) -> str:
            """Per-size lookup — cf. date_picker.render for rationale."""
            row = size_map.get(group, {})
            return row.get(size_key) or row.get("md") or ""

        def slot_with_size(slot: str) -> str:
            # ``compose_class`` resolves the slot's ``{bg_color}`` against
            # ``color=`` (the same seam ``ui.input`` uses for its multi-slot
            # theme) so ``color=`` reaches the frame ring + trigger icon, not
            # just the calendar popover. The per-slot size map stays local.
            return " ".join(filter(None, [
                self.compose_class(slot, apply_variant_size_modifiers=False),
                sz(slot),
            ]))
        disabled = bool(self._reactive_values.get("disabled"))
        required = bool(self._reactive_values.get("required"))

        # ── Initial start / end ISO ───────────────────────────────
        raw_value = self._reactive_values.get("value")
        initial_start = ""
        initial_end = ""
        if isinstance(raw_value, (list, tuple)) and len(raw_value) == 2:
            initial_start = _date_to_iso(raw_value[0])
            initial_end = _date_to_iso(raw_value[1])

        value_binding = self._binding_metadata.get("value")
        min_binding = self._binding_metadata.get("min")
        max_binding = self._binding_metadata.get("max")
        disabled_binding = self._binding_metadata.get("disabled")

        # A range field round-trips as a 2-element LIST (store/wire shape),
        # and ``list`` is stamped ``_BoundList`` — so ``_derive_field_name``
        # autonames a server-bound range like every other input.
        name = self._reactive_values.get("name") or self._derive_field_name() or "value"

        # ── Wrapper + scope (bz-data) ─────────────────────────────
        root_attrs = self.emit_attrs()
        # ``focus``/``blur`` are declared EVENTS but root is a
        # non-focusable wrapper ``<div>`` — native focus/blur don't
        # bubble, so a handler left on root_attrs can structurally
        # never fire (unlike ``change``, which DOES bubble natively
        # from the field inputs below). Relocate both handler flavours
        # onto BOTH the start and end fields (unlike Slider's handles,
        # start/end are semantically distinct fields a user can
        # independently focus — dropping either would silently miss
        # events), combined below with each field's own internal
        # blur-normalise wiring instead of colliding with it. Same bug
        # class as number_input/slider/combobox/date_picker.
        hidden_extra: dict[str, Any] = {}
        relocated_to_fields: dict[str, Any] = {}
        relocate_field_events(
            root_attrs,
            value_carrier=hidden_extra,
            focusable=relocated_to_fields,
        )
        name = detach_wrapper_carriers(self, root_attrs)
        root_attrs["class"] = slots.get("root", "")

        # bz-data : ``open`` flag + the two endpoint vars. In bound mode
        # the vars SEED from the store list ; in literal mode from the
        # SSR ISO pair. (A range value is a 2-element list, so unlike
        # DatePicker the two inputs can't both address one store scalar
        # — the local vars are the working copy in both modes.)
        if value_binding is not None:
            store = self.path_of(value_binding)
            init_vstart = f"({store} || [])[0] || ''"
            init_vend = f"({store} || [])[1] || ''"
        else:
            store = None
            init_vstart = json.dumps(initial_start)
            init_vend = json.dumps(initial_end)
        # ``vstart``/``vend`` are scope signals absorb preserves across a
        # morph — opt them into ``_serverSync`` so a server-backed ``value``
        # re-adopts on refresh (gate leaves ClientBinding/literal untouched).
        # ⚠️ Ici la divergence était VIVANTE, pas latente : la valeur d'un
        # range est une LISTE de 2 éléments, donc le pattern documenté
        # ``value=[state.debut, state.fin]`` (deux dates stampées dans une
        # liste littérale) n'a pas de ``field_name`` sur la liste
        # elle-même. L'inline répondait False → aucun ``_serverSync``, et
        # un changement serveur de la plage était perdu au morph.
        # ``_value_server_backed`` gère ce cas (branche « case 3 »).
        sync = server_sync_marker(
            "vstart", "vend", enabled=self._value_server_backed("value"))
        root_attrs["bz-data"] = (
            f"{{open: false, vstart: {init_vstart}, vend: {init_vend}"
            + (f",{sync}" if sync else "") + "}"
        )
        # ── Les récepteurs de l'API impérative ───────────────────
        #
        # En mode LIÉ, `.open()` / `.set()` écrivent directement dans le
        # store et ces écouteurs ne se déclenchent jamais ; on les pose
        # quand même pour que le contrat soit le même dans les deux
        # modes — le choix déjà fait par Sidebar, Dialog et Select.
        for _ev, _handler in imperative_listeners("open").items():
            root_attrs.setdefault(_ev, _handler)
        # Deux variables, donc pas de `bz-set` scalaire :
        # `.set()` pose le DÉBUT de la plage.
        root_attrs.setdefault(
            "bz-on:bz-set", "vstart = $event.detail.value"
        )
        # Single ``bz-effect`` (one per element) doing two jobs :
        # 1. (bound only) push ``[vstart, vend]`` back into the store on
        #    every endpoint change — a reactive effect re-reads the vars
        #    each tick and writes through an equality guard.
        # 2. Mirror the (vstart, vend) pair onto the inner
        #    ``<bz-calendar>``'s observed ``value`` ATTRIBUTE, shared
        #    with DatePicker via ``calendar_value_mirror`` (cf. traps.md
        #    § bz-attr value on a custom element).
        push_store = ""
        if store is not None:
            push_store = (
                f"const _cur = {store} || ['', '']; "
                f"if (_cur[0] !== vstart || _cur[1] !== vend) "
                f"{store} = [vstart, vend]; "
            )
        root_attrs["bz-effect"] = (
            "(() => { "
            + push_store
            + calendar_value_mirror("[vstart, vend]", is_range=True)
            + "})()"
        )
        # Escape + click-outside dismiss (the shared helper registers
        # both on ``$el`` — ``bz-on`` has no modifiers).
        root_attrs["bz-init"] = anchored_dismiss_init("open")

        # ── Hidden form-data input — JSON pair ─────────────────────
        hidden_input = hidden_carrier(
            value_expr="JSON.stringify([vstart, vend])",
            initial=json.dumps([initial_start, initial_end])
            if (initial_start or initial_end) else "",
            name=name,
            required=required,
            extra=hidden_extra,
        )

        # ── Visible editable start / end inputs ───────────────────
        def _make_field(
            varname: str,
            placeholder: str,
            extra_class: str = "",
        ) -> Element:
            cls = slot_with_size("input_field")
            if extra_class:
                cls = f"{cls} {extra_class}"
            initial = initial_start if varname == "vstart" else initial_end
            attrs: dict[str, Any] = {
                "type": "text",
                "placeholder": placeholder,
                "class": cls,
                "value": initial,
                "bz-model": varname,
                "bz-on:blur": normalise_to_iso_js(varname),
                "autocomplete": "off",
                "inputmode": "numeric",
                "spellcheck": "false",
                "aria-label": placeholder,
            }
            if disabled:
                attrs["disabled"] = True
            # Copy, not mutate — ``relocated_to_fields["bz-on:blur"]``
            # combines against THIS field's own normalise expression
            # (varname-specific), so the merge can't be shared across
            # the start/end calls.
            merged = dict(relocated_to_fields)
            if "bz-on:blur" in merged:
                merged["bz-on:blur"] = (
                    f"{attrs['bz-on:blur']}; {merged['bz-on:blur']}"
                )
            attrs.update(merged)
            # Reactive ``disabled`` → les deux champs éditables, pas le
            # wrapper. Le frame se grise tout seul avec
            # (``has-[input:disabled]`` dans le thème).
            self.forward_binding("disabled", attrs)
            return Element(tag="input", attrs=attrs, children=())

        start_input_el = _make_field(
            "vstart",
            self._placeholder_start,
            slots.get("input_field_start", ""),
        )
        end_input_el = _make_field("vend", self._placeholder_end)

        # ``emit_text_slot`` returns ``None`` for an empty slot (``separator=""``)
        # and its contract requires the caller to skip it — dropping ``None`` into
        # ``children`` would crash serialize. Filter before building the span.
        sep_text = self.emit_text_slot(self._separator)
        separator_node = Element(
            tag="span",
            attrs={"class": slot_with_size("separator")},
            children=tuple(c for c in (sep_text,) if c is not None),
        )

        children_in_frame: list[Any] = [
            start_input_el,
            separator_node,
            end_input_el,
        ]

        # ── Clear button ──────────────────────────────────────────
        if self._clearable:
            clear_btn = clear_button(
                css=slot_with_size("clear_button"),
                icon_css=slot_with_size("button_icon"),
                aria_label=text("date_range_picker.clear"),
                clear_js="vstart = ''; vend = ''",
                show_when="vstart || vend",
                has_value_at_ssr=bool(initial_start or initial_end),
                disabled=disabled,
            )
            self.forward_binding("disabled", clear_btn.attrs)
            children_in_frame.append(clear_btn)

        # ── Calendar trigger button ───────────────────────────────
        trigger_btn = trigger_button(
            icon="calendar",
            css=slot_with_size("trigger_button"),
            icon_css=slot_with_size("button_icon"),
            aria_label=text("date_range_picker.open"),
            disabled=disabled,
        )
        self.forward_binding("disabled", trigger_btn.attrs)
        children_in_frame.append(trigger_btn)

        # ``bz-ref="bztrigger"`` : the floating anchor the panel pins against
        # (same idiom as date_picker / Select / Combobox).
        input_frame = Element(
            tag="div",
            attrs={
                # ``slot_with_size`` et non ``compose_class`` : la
                # hauteur du palier vit sur le CADRE, qui porte la
                # bordure — sinon le contrôle rend 2 px de plus que
                # ``ui.input`` au même ``size=`` (cf. la note du thème).
                "class": slot_with_size("input_frame"),
                "bz-ref": "bztrigger",
            },
            children=tuple(children_in_frame),
        )

        # ── Popover panel with Calendar(mode=range) ───────────────
        cal_kwargs: dict[str, Any] = {
            "mode": "range",
            "color": color,
            "size": size_key,
            "weekstart": self._weekstart,
            "marks": self._marks,
            "weekday_names": list(self._weekday_names)
            if self._weekday_names else None,
            "month_names": list(self._month_names)
            if self._month_names else None,
        }
        if min_binding is not None:
            cal_kwargs["min"] = min_binding
        elif self._reactive_values.get("min"):
            cal_kwargs["min"] = self._reactive_values.get("min")
        if max_binding is not None:
            cal_kwargs["max"] = max_binding
        elif self._reactive_values.get("max"):
            cal_kwargs["max"] = self._reactive_values.get("max")
        if disabled_binding is not None:
            cal_kwargs["disabled"] = disabled_binding
        elif disabled:
            cal_kwargs["disabled"] = True
        if self._disabled_dates:
            cal_kwargs["disabled_dates"] = self._disabled_dates

        # On change : Calendar emits the (start, end) pair as
        # ``$event.detail.value`` (array). Write both endpoints back
        # into the scope vars, close the popover if requested.
        on_change_parts = [
            "vstart = ($event.detail.value || [])[0] || ''",
            "vend = ($event.detail.value || [])[1] || ''",
        ]
        if self._close_on_close:
            on_change_parts.append("open = false")
        cal_kwargs["on_change"] = "; ".join(on_change_parts)

        # Drop the calendar's static ``value`` attr — sync lives on the
        # wrapper's ``bz-effect`` (cf. ``root_attrs[bz-effect]`` above)
        # where vstart/vend are directly in scope.
        cal_el = panel_calendar(self, cal_kwargs)
        cal_attrs = {**cal_el.attrs}
        cal_attrs.pop("value", None)
        cal_el = _dc.replace(cal_el, attrs=cal_attrs)

        # ``bz-ref="bzpanel"`` + shared ``anchored_panel_effect`` : floating
        # best-fit (``bottom-start``, flip / clamp to the viewport) instead of
        # the old static ``absolute top-full left-0`` that clipped at the edge.
        panel_node = anchored_panel(
            css=slots.get("panel", ""),
            children=(cal_el,),
        )

        return Element(
            tag=self._tag,
            attrs=root_attrs,
            children=(hidden_input, input_frame, panel_node),
        )
