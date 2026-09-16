"""``MonthPicker`` — champ de MOIS avec grille d'année en popover.

Usage ::

    ui.month_picker(value=state.periode)              # "2026-08"
    ui.month_picker(value=state.periode, min="2026-03", max="2026-12")

**La valeur est une chaîne ``"YYYY-MM"``** — troisième membre de la même
famille de formats que l'ISO des dates et le ``"HH:MM"`` des heures, et
pour la même raison : zéro-paddée, elle se **trie lexicographiquement
comme chronologiquement**, donc borner est une comparaison de chaînes.
Python accepte aussi un ``datetime.date``, TRONQUÉ au mois — quelqu'un
qui passe ``date(2026, 8, 14)`` veut visiblement « août 2026 », et le
refuser lui coûterait un ``strftime`` pour rien.

Le composant est mince à dessein : le cadre, le popover, l'input caché et
le routage des handlers viennent de ``_picker_field`` ; la grille vient
de ``ui.calendar(mode="month")``. Ce qui reste ici est le **codec de
valeur** et le normaliseur de saisie — c'est-à-dire tout ce qui lui est
propre, et rien d'autre.

``min`` / ``max`` acceptent un ``"YYYY-MM"`` ou une ``date``, et sont
tronqués au mois : un ``min`` au 15 mars n'interdit PAS mars, puisqu'une
partie du mois reste permise. Ils ne sont **pas** bindables, même
raisonnement que TimePicker — la règle ne les admet en one-way que pour
la contrainte croisée d'un range de dates.
"""

from __future__ import annotations

import datetime as _dt
from collections.abc import Callable
from typing import Any, ClassVar

from bretzel.components.base import Component, reactive_prop
from bretzel.components.base._wiring import (
    install_open_close_toggle,
    install_value_commands,
)
from bretzel.components.inputs._picker_field import render_calendar_field, value_expr
from bretzel.components.inputs.month_picker.theme import MONTH_PICKER_THEME
from bretzel.core.tree import Element
from bretzel.render import text


def month_to_ym(value: Any, *, owner: str = "MonthPicker") -> str:
    """Coercer une valeur de mois vers ``"YYYY-MM"``.

    ``None`` → ``""`` ; une ``date`` → son mois (TRONQUÉE, cf. docstring
    du module) ; une chaîne passe et est coupée à 7 caractères, ce qui
    accepte aussi bien ``"2026-08"`` que ``"2026-08-14"``. Tout le reste
    est une erreur d'usage, levée avec ``owner`` pour que l'auteur voie
    QUI a refusé — même contrat que ``date_to_iso`` et ``time_to_hhmm``.
    """
    from bretzel.components.base.attrs import ComponentDefinitionError

    if value is None:
        return ""
    if isinstance(value, _dt.date):
        return f"{value.year:04d}-{value.month:02d}"
    if isinstance(value, str):
        return value[:7]
    raise ComponentDefinitionError(
        f"{owner} value must be str / date / None, "
        f"got {type(value).__name__}: {value!r}"
    )


#: Normalisation au blur : la saisie libre devient ``YYYY-MM``, ou se
#: vide. Templatée sur ``{V}`` pour que les modes lié et littéral
#: partagent le même parseur — même forme que chez DatePicker et
#: TimePicker.
NORMALISE_TO_YM_TEMPLATE = (
    "(() => {{ const raw = String({V} || '').trim(); "
    "if (!raw) {{ {V} = ''; return; }} "
    # ``2026-08`` / ``2026/08`` / ``08-2026`` / ``08/2026`` — un seul
    # motif, puis on décide qui est l'année par la LONGUEUR du groupe.
    "const m = raw.match(/^(\\d{{1,4}})[^\\d](\\d{{1,4}})/); "
    "if (!m) {{ {V} = ''; return; }} "
    "let y, mo; "
    "if (m[1].length === 4) {{ y = +m[1]; mo = +m[2]; }} "
    "else {{ mo = +m[1]; y = +m[2]; }} "
    "if (mo < 1 || mo > 12 || y < 1) {{ {V} = ''; return; }} "
    "{V} = String(y).padStart(4, '0') + '-' + "
    "String(mo).padStart(2, '0'); }})()"
)


def normalise_to_ym_js(value_expr: str) -> str:
    """Le normaliseur saisie-libre → ``YYYY-MM`` pour ``value_expr``."""
    return NORMALISE_TO_YM_TEMPLATE.format(V=value_expr)


class MonthPicker(Component):
    """Render a month field with a year-grid popover."""

    THEME: ClassVar[dict[str, Any]] = MONTH_PICKER_THEME
    THEME_KEY: ClassVar[str] = "month_picker"
    IS_CONTAINER: ClassVar[bool] = False
    BINDABLE_PROPS: ClassVar[tuple[str, ...]] = ("value", "disabled")
    #: Un picker est les DEUX natures à la fois : un panneau ancré
    #: (comme `dialog`) et un champ qui porte une valeur (comme
    #: `input`). Sa surface est donc l'union des deux vocabulaires
    #: déjà fixés par ses voisins — rien d'inventé ici.
    IMPERATIVE: ClassVar[tuple[str, ...]] = (
        "open", "close", "toggle", "set", "clear", "focus", "blur",
    )
    EVENTS: ClassVar[tuple[str, ...]] = ("change", "focus", "blur")

    name: str | None = reactive_prop(default=None, emit_attr=False)
    value: Any = reactive_prop(
        default=None, writes=True, names_field=True
    )
    min: Any = reactive_prop(default=None, emit_attr=False)
    max: Any = reactive_prop(default=None, emit_attr=False)
    # ``emit_attr=False`` : la racine est un ``<div>``, où ``disabled`` ne
    # fait rien. Forwardé à la main sur les trois porteurs réels.
    disabled: bool = reactive_prop(default=False, emit_attr=False)
    required: bool = reactive_prop(default=False, emit_attr=False)
    color: str = reactive_prop(default="primary", emit_attr=False)
    size: str = reactive_prop(default="md", emit_attr=False)

    def __init__(
        self,
        value: Any = None,
        *,
        placeholder: str = "YYYY-MM",
        min: Any = None,
        max: Any = None,
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
        self._month_names = list(month_names) if month_names else None
        self._clearable = clearable
        self._close_on_pick = close_on_pick
        # Forward direct : le socle drope les kwargs reactive None (garde le défaut).
        super().__init__(
            name=name, value=value, min=min, max=max,
            color=color, size=size, disabled=disabled, required=required,
            on_change=on_change, on_focus=on_focus, on_blur=on_blur,
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
        theme = self._resolved_theme()
        sizes = theme.get("sizes", {})
        size_key = self._reactive_values.get("size") or "md"
        size_cfg = sizes.get(size_key, sizes.get("md", {}))
        color = self._reactive_values.get("color") or "primary"

        initial = month_to_ym(self._reactive_values.get("value"))
        val = value_expr(self)

        cal_kwargs: dict[str, Any] = {
            "mode": "month", "color": color, "size": size_key,
        }
        if self._month_names:
            cal_kwargs["month_names"] = list(self._month_names)
        for bound in ("min", "max"):
            raw = self._reactive_values.get(bound)
            if raw:
                # Le calendrier attend une DATE pour ses bornes et les
                # tronque lui-même ; on lui donne le 1er du mois.
                cal_kwargs[bound] = f"{month_to_ym(raw)}-01"
        picked = [f"{val} = $event.detail.value"]
        if self._close_on_pick:
            picked.append("open = false")
        cal_kwargs["on_change"] = "; ".join(picked)

        def sized(slot: str) -> str:
            return self.slot_class(slot, size_cfg.get(slot, ""))

        return render_calendar_field(
            self,
            initial=initial,
            value_expr=val,
            blur_js=normalise_to_ym_js(val),
            mirror_granularity="month",
            clearable=self._clearable,
            clear_label=text("month_picker.clear"),
            trigger_icon="calendar",
            trigger_label=text("month_picker.open"),
            calendar_kwargs=cal_kwargs,
            root_css=self.compose_class(
                "root", apply_variant_size_modifiers=False),
            # ``sized`` et non ``compose_class`` : la hauteur du palier
            # vit sur le CADRE, qui porte la bordure (cf. la note du
            # thème) — sinon le contrôle rend 2 px de trop.
            frame_css=sized("input_frame"),
            panel_css=self.compose_class(
                "panel", apply_variant_size_modifiers=False),
            field_css=sized("input_field"),
            clear_css=sized("clear_button"),
            trigger_css=sized("trigger_button"),
            icon_css=sized("button_icon"),
        )


__all__ = ["MonthPicker", "month_to_ym", "normalise_to_ym_js"]
