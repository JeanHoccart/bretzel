"""``DatePicker`` — single-date input with an inline calendar popover.

UX model — native ``<input type="date">`` shape, themable popover :
the visible field is **editable**. The user can either type a date
(any format ``new Date()`` parses, normalised to ISO on blur) OR
click the calendar icon button — which lives **inside the same focus
ring** as the input — to open a ``<bz-calendar>`` popover and pick.

The single source of truth for the field's value is a **value
expression** (``_value_expr()``) :

- **Bound** (``value=client_state.picked``) : the value expression IS
  the binding path ``$bz.state.X.y``. The scope is just
  ``bz-data="{open: false}"``. The editable ``<input>`` carries
  ``bz-model="$bz.state.X.y"`` (two-way), the hidden form-data input
  ``bz-attr:value="$bz.state.X.y"``, the inner ``<bz-calendar>``
  ``bz-attr:value="$bz.state.X.y"`` + ``bz-on:change="$bz.state.X.y =
  $event.detail.value"``. Everything addresses the store directly —
  zero ``$watch`` sync.
- **Literal** (``value=date(...)`` / no value) : the value expression
  is a local scope var ``value``. The scope is
  ``bz-data="{open: false, value: '<initial>'}"``, and ``bz-model`` /
  ``bz-attr:value`` / the calendar change handler all address ``value``.

Wired (both modes, ``V`` = ``_value_expr()``) :

- the editable ``<input>`` uses ``bz-model="V"`` (typing → V) ;
- the hidden form-data input uses ``bz-attr:value="V"`` ;
- the clear ``×`` button does ``V = ''`` and is shown only when ``V``
  is non-empty (``bz-show="V"`` + FOUC pre-stamp) ;
- the calendar trigger ``<button>`` toggles ``open`` ;
- the inner ``<bz-calendar>`` reçoit ``V`` par le ``bz-effect`` du wrapper
  (voir le point suivant) — **pas** par ``bz-attr:value``, qui est
  explicitement retiré du calendrier (``release_root_attr``). Il écrit en
  retour sur son ``change`` natif
  (``bz-on:change="V = $event.detail.value; open = false
  [if close_on_pick]"``) ;
- a ``bz-effect`` on the wrapper mirrors ``V`` onto the calendar's
  observed ``value`` ATTRIBUTE via ``setAttribute`` — ``bz-attr:value``
  on a custom element writes the JS property, not the attribute, so it
  would skip ``attributeChangedCallback`` (cf. ``traps.md`` § *bz-attr
  value on a custom element*).

Form integration : ``AUTONAME_FROM = "value"`` derives the HTML
``name`` from the bound field, same idiom as Calendar / Input.
"""

from __future__ import annotations

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
    value_expr,
)
from bretzel.components.inputs._wiring import date_to_iso
from bretzel.components.inputs.date_picker.theme import DATE_PICKER_THEME
from bretzel.core.tree import Element
from bretzel.render import text


def _date_to_iso(value: Any) -> str:
    """``DatePicker``'s date coercion — the shared one, bound to this
    component's name for the error message (audit F50 : les trois
    composants de la famille date en portaient une copie identique)."""
    return date_to_iso(value, owner="DatePicker")


# Client expression — typed text → ISO ``YYYY-MM-DD`` on blur,
# rejecting unparsable input. Templated on the value expression so the
# bound (``$bz.state.X.y``) and literal (``value``) modes — and the
# date_range_picker's ``vstart`` / ``vend`` — reuse the exact same
# parser. ``{V}`` is substituted with the value expression at render.
NORMALISE_TO_ISO_TEMPLATE = (
    "(() => {{ if (!({V})) return; "
    "const m = String({V}).match(/^(\\d{{4}})-(\\d{{2}})-(\\d{{2}})$/); "
    "if (m) return; "
    "const d = new Date({V}); "
    "if (isNaN(d.getTime())) {{ {V} = ''; return; }} "
    "const pad = n => String(n).padStart(2, '0'); "
    "{V} = d.getFullYear() + '-' + pad(d.getMonth() + 1) + "
    "'-' + pad(d.getDate()); }})()"
)
"""On blur : if the value expression is already a clean ISO date, keep
it. Else try ``new Date(...)`` — if it parses, rewrite it in ISO. If
it doesn't parse, clear the field. Free-form (``"July 19 2018"``,
``"2018/07/19"``, …) normalised to ``"2018-07-19"``.

Templated on ``{V}`` (the value expression) so the bound store path,
the local ``value``, and the range picker's ``vstart`` / ``vend`` all
share one parser. Use :func:`normalise_to_iso_js`."""


def normalise_to_iso_js(value_expr: str) -> str:
    """The free-form → ISO blur normaliser for ``value_expr``.

    ``value_expr`` is whatever the field is bound to : a local scope
    var (``value`` / ``vstart`` / ``vend``) or a store path
    (``$bz.state.X.y``). The same body assigns the normalised result
    back into that same expression."""
    return NORMALISE_TO_ISO_TEMPLATE.format(V=value_expr)


class DatePicker(Component):
    """Single-date input with an inline calendar popover."""

    THEME: ClassVar[dict[str, Any]] = DATE_PICKER_THEME
    THEME_KEY: ClassVar[str] = "date_picker"
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
    value: Any = reactive_prop(default=None, writes=True, names_field=True)
    min: Any = reactive_prop(default=None, emit_attr=False)
    max: Any = reactive_prop(default=None, emit_attr=False)
    # ``emit_attr=False`` : la racine est un ``<div>`` wrapper, où
    # ``disabled`` ne fait RIEN. Le binding est forwardé à la main dans
    # ``render()`` sur les trois carriers réels (champ, ×, trigger) —
    # cf. gate ``test_binding_lands_on_carrier``.
    disabled: bool = reactive_prop(default=False, emit_attr=False)
    required: bool = reactive_prop(default=False, emit_attr=False)
    color: str = reactive_prop(default="primary", emit_attr=False)
    size: str = reactive_prop(default="md", emit_attr=False)

    def __init__(
        self,
        value: Any = None,
        *,
        placeholder: str = "YYYY-MM-DD",
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
        close_on_pick: bool = True,
        name: str | None = None,
        on_change: Callable[..., Any] | str | None = None,
        on_focus: Callable[..., Any] | str | None = None,
        on_blur: Callable[..., Any] | str | None = None,
        **kwargs: Any,
    ) -> None:
        self._placeholder = placeholder
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
        self._close_on_pick = close_on_pick

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

        disabled = bool(self._reactive_values.get("disabled"))
        required = bool(self._reactive_values.get("required"))

        def sz(group: str) -> str:
            """Per-size class string for ``group`` in ``THEME["sizes"]``.
            Without this the input + buttons all render ``h-10`` no matter
            the ``size=``.
            """
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

        raw_value = self._reactive_values.get("value")
        initial_iso = _date_to_iso(raw_value) if raw_value else ""

        value_binding = self._binding_metadata.get("value")
        min_binding = self._binding_metadata.get("min")
        max_binding = self._binding_metadata.get("max")
        disabled_binding = self._binding_metadata.get("disabled")

        # ── Root attrs + scope (bz-data) ──────────────────────────
        # Les deux appels sont la mécanique commune aux trois pickers
        # (``inputs/_picker_field.py``, extrait le 2026-08-02) : router
        # chaque handler vers le porteur capable de le tirer, et vider la
        # racine de ce qu'un ``<div>`` ne peut pas porter. Les blocs
        # qu'ils remplacent vivaient ici en trois copies dont les
        # commentaires expliquaient trois fois la même chose.
        val = value_expr(self)
        root_attrs = self.emit_attrs()
        hidden_extra: dict[str, Any] = {}
        relocated_to_field: dict[str, Any] = {}
        relocate_field_events(
            root_attrs,
            value_carrier=hidden_extra,
            focusable=relocated_to_field,
        )
        name = detach_wrapper_carriers(self, root_attrs)
        root_attrs["class"] = slots.get("root", "")

        # bz-data : just the popover ``open`` flag when bound (the value
        # lives in the store) ; ``open`` + a local ``value`` seed in the
        # literal case. No ``$watch`` sync — every directive addresses the
        # value expression directly.
        if value_binding is not None:
            root_attrs["bz-data"] = "{open: false}"
        else:
            # ``value`` lives in the bz-data scope, which ``scope.absorb``
            # PRESERVES across an idiomorph morph — great for a user's edit,
            # but it means a SERVER change to a bound ``value=state.field``
            # is ignored on refresh (the stale signal re-asserts). Opt the
            # key into ``_serverSync`` so a refresh re-adopts it — but ONLY
            # when server-backed (a plain literal keeps its client value).
            (key,) = self._scope_keys("value")
            sync = server_sync_marker(
                key, enabled=self._value_server_backed("value"))
            root_attrs["bz-data"] = (
                f"{{open: false, {key}: {json.dumps(initial_iso)}"
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
            root_attrs.setdefault(
                "bz-on:bz-set", f"{value_expr(self)} = $event.detail.value"
            )
        # Mirror the value expression onto the inner ``<bz-calendar>``'s
        # observed ``value`` ATTRIBUTE. Shared with DateRangePicker via
        # ``calendar_value_mirror`` (centralises the trap-prone
        # ``setAttribute`` dance + captures the value expression once).
        root_attrs["bz-effect"] = (
            "(() => { " + calendar_value_mirror(val, is_range=False) + "})()"
        )
        # Escape + click-outside dismiss (the shared helper registers
        # both on ``$el`` — ``bz-on`` has no ``.outside`` / ``.escape``).
        root_attrs["bz-init"] = anchored_dismiss_init("open")

        # ── Hidden form-data input ────────────────────────────────
        # Passe désormais par la primitive partagée : le squelette (type
        # / bz-ref / value SSR / bz-attr:value) vient de
        # ``hidden_carrier_attrs``, que ce composant réécrivait à la main
        # parce qu'il est ANTÉRIEUR à son extraction. Le ``bz-ref``
        # manquait donc ici — c'est ce qui a fait rougir
        # ``test_hidden_carrier_skeleton_is_shared`` sur TimePicker quand
        # j'ai recopié ce bloc.
        hidden_input = hidden_carrier(
            value_expr=val,
            initial=initial_iso,
            name=name,
            required=required,
            extra=hidden_extra,
        )

        # ── Visible editable input ────────────────────────────────
        field_attrs: dict[str, Any] = {
            "type": "text",
            "placeholder": self._placeholder,
            "class": slot_with_size("input_field"),
            "value": initial_iso,
            "bz-model": val,
            # On blur — try to normalise free-form input into ISO.
            "bz-on:blur": normalise_to_iso_js(val),
            "autocomplete": "off",
            "inputmode": "numeric",
            "spellcheck": "false",
            "aria-label": self._placeholder,
        }
        if disabled:
            field_attrs["disabled"] = True
        if required:
            # Pure visual ``required`` cue — the actual ``required`` for
            # form-data validation lives on the hidden input.
            field_attrs["aria-required"] = "true"
        if "bz-on:blur" in relocated_to_field:
            relocated_to_field["bz-on:blur"] = (
                f"{field_attrs['bz-on:blur']}; {relocated_to_field['bz-on:blur']}"
            )
        field_attrs.update(relocated_to_field)
        # Reactive ``disabled`` → le champ éditable, pas le wrapper. Le
        # frame se grise tout seul avec (``has-[input:disabled]`` dans le
        # thème), donc l'anneau suit le binding sans directive de plus.
        self.forward_binding("disabled", field_attrs)
        field_input = Element(
            tag="input", attrs=field_attrs, children=()
        )

        # ── Clear button (only emitted when clearable) ────────────
        children_in_frame: list[Any] = [field_input]
        if self._clearable:
            clear_btn = clear_button(
                css=slot_with_size("clear_button"),
                icon_css=slot_with_size("button_icon"),
                aria_label=text("date_picker.clear"),
                clear_js=f"{val} = ''",
                show_when=val,
                has_value_at_ssr=bool(initial_iso),
                disabled=disabled,
            )
            self.forward_binding("disabled", clear_btn.attrs)
            children_in_frame.append(clear_btn)

        # ── Calendar trigger button ───────────────────────────────
        trigger_btn = trigger_button(
            icon="calendar",
            css=slot_with_size("trigger_button"),
            icon_css=slot_with_size("button_icon"),
            aria_label=text("date_picker.open"),
            disabled=disabled,
        )
        self.forward_binding("disabled", trigger_btn.attrs)
        children_in_frame.append(trigger_btn)

        # ── The visible field frame (input + buttons, one ring) ───
        # ``bz-ref="bztrigger"`` : the floating anchor the panel's
        # ``anchored_panel_effect`` pins against (same idiom as Select /
        # Combobox — the panel opens against this box).
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

        # ── Popover panel hosting the calendar ────────────────────
        cal_kwargs: dict[str, Any] = {
            "mode": "picker",
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
        # On pick : write the picked value back into the value
        # expression (which propagates to the input + the hidden
        # form-data carrier + — when bound — the store, all addressing
        # the same expression). Optionally close.
        on_change_parts = [f"{val} = $event.detail.value"]
        if self._close_on_pick:
            on_change_parts.append("open = false")
        cal_kwargs["on_change"] = "; ".join(on_change_parts)

        # Drop the calendar's static ``value`` attr — sync lives on the
        # wrapper's ``bz-effect`` (see ``root_attrs[bz-effect]`` above),
        # which has direct access to the value expression without going
        # through the bz-calendar's nested ``bz-data="{year, month}"``
        # header scope.
        import dataclasses as _dc
        cal_el = panel_calendar(self, cal_kwargs)
        cal_attrs = {**cal_el.attrs}
        cal_attrs.pop("value", None)
        cal_el = _dc.replace(cal_el, attrs=cal_attrs)

        # ``bz-ref="bzpanel"`` + the shared ``anchored_panel_effect`` toggles
        # display AND attaches ``$bz.helpers.floating`` against ``bztrigger``
        # (best-fit ``bottom-start`` : opens below, left-aligned, flips /
        # clamps to stay in the viewport). Replaces the old ``bz-show`` +
        # static ``absolute top-full left-0`` panel that clipped at the edge.
        panel_node = anchored_panel(
            css=slots.get("panel", ""),
            children=(cal_el,),
        )

        return Element(
            tag=self._tag,
            attrs=root_attrs,
            children=(hidden_input, input_frame, panel_node),
        )
