"""``WeekPicker`` — champ de SEMAINE, sélection par ligne.

Usage ::

    ui.week_picker(value=state.semaine)               # "2026-08-03"
    ui.week_picker(value=state.semaine, weekstart=0)  # semaines du dimanche

**La valeur est la date ISO du PREMIER jour de la semaine.** Une semaine
EST son premier jour — c'est ce que la plupart des back-ends stockent, et
ça reste une date ordinaire : comparable, filtrable, affichable, et
compatible avec tout ce qui mange déjà de l'ISO. Qui veut la fin ajoute
six jours.

Le jour de départ suit ``weekstart`` (défaut lundi). Ce n'est pas un
détail cosmétique : la même date n'appartient pas à la même semaine selon
le réglage, donc rendre le lundi quand l'utilisateur a demandé des
semaines du dimanche serait un mensonge sur la valeur.

**Le recalage vaut aussi pour la SAISIE.** Taper une date quelconque dans
le champ ne laisse pas cette date : elle est ramenée au début de sa
semaine au blur, exactement comme un clic. Sans ça, le champ et la grille
diraient deux choses différentes — et la valeur postée dépendrait de la
façon dont l'utilisateur l'a entrée.

Le composant est mince : cadre, popover, input caché et routage viennent
de ``_picker_field`` ; la grille et le surlignage de ligne viennent de
``ui.calendar(mode="week")``. Ce qui reste ici est le codec et le
normaliseur.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, ClassVar

from bretzel.components.base import Component, reactive_prop
from bretzel.components.base._wiring import (
    install_open_close_toggle,
    install_value_commands,
)
from bretzel.components.inputs._picker_field import render_calendar_field, value_expr
from bretzel.components.inputs._wiring import date_to_iso
from bretzel.components.inputs.week_picker.theme import WEEK_PICKER_THEME
from bretzel.core.tree import Element
from bretzel.render import text

#: Saisie libre → date ISO, PUIS recalage sur le début de semaine.
#:
#: Le second temps est ce qui distingue ce normaliseur de celui de
#: DatePicker : sans lui, taper « 2026-08-06 » laisserait le jeudi dans
#: le champ pendant que la grille surligne la semaine du lundi 3 — deux
#: vérités pour une valeur.
#:
#: ``{V}`` est l'expression de valeur, ``{WS}`` le jour de départ. Le
#: modulo est doublé pour la même raison que dans le custom element : JS
#: rend un reste NÉGATIF pour un dividende négatif.
NORMALISE_TO_WEEK_TEMPLATE = (
    "(() => {{ const raw = String({V} || '').trim(); "
    "if (!raw) {{ {V} = ''; return; }} "
    "const d = new Date(raw); "
    "if (isNaN(d.getTime())) {{ {V} = ''; return; }} "
    "const back = (d.getDay() - {WS} + 7) % 7; "
    "d.setDate(d.getDate() - back); "
    "const pad = n => String(n).padStart(2, '0'); "
    "{V} = d.getFullYear() + '-' + pad(d.getMonth() + 1) + "
    "'-' + pad(d.getDate()); }})()"
)


def normalise_to_week_js(value_expr: str, weekstart: int) -> str:
    """Le normaliseur saisie-libre → début de semaine ISO."""
    return NORMALISE_TO_WEEK_TEMPLATE.format(
        V=value_expr, WS=int(weekstart) % 7
    )


def _week_to_iso(value: Any) -> str:
    """``WeekPicker``'s date coercion — la partagée, liée au nom de ce
    composant pour le message d'erreur (même contrat que ses voisins)."""
    return date_to_iso(value, owner="WeekPicker")


class WeekPicker(Component):
    """Render a week field with row-based day selection."""

    THEME: ClassVar[dict[str, Any]] = WEEK_PICKER_THEME
    THEME_KEY: ClassVar[str] = "week_picker"
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
        placeholder: str = "YYYY-MM-DD",
        min: Any = None,
        max: Any = None,
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
        # Transmis tel quel : meme grille de jours que
        # ``ui.calendar``, donc une marque a une cellule ou
        # atterrir. ``ui.month_picker`` ne l'a pas : sa grille
        # est faite de MOIS.
        self._marks = marks
        self._weekstart = int(weekstart) % 7
        self._weekday_names = list(weekday_names) if weekday_names else None
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

        raw = self._reactive_values.get("value")
        initial = _week_to_iso(raw) if raw else ""
        val = value_expr(self)

        cal_kwargs: dict[str, Any] = {
            "mode": "week", "color": color, "size": size_key,
            "weekstart": self._weekstart,
            "marks": self._marks,
        }
        if self._weekday_names:
            cal_kwargs["weekday_names"] = list(self._weekday_names)
        if self._month_names:
            cal_kwargs["month_names"] = list(self._month_names)
        for bound in ("min", "max"):
            if self._reactive_values.get(bound):
                cal_kwargs[bound] = self._reactive_values.get(bound)
        picked = [f"{val} = $event.detail.value"]
        if self._close_on_pick:
            picked.append("open = false")
        cal_kwargs["on_change"] = "; ".join(picked)

        def sized(slot: str) -> str:
            return self.slot_class(slot, size_cfg.get(slot, ""))

        # La valeur d'une semaine est une date ISO scalaire, donc le
        # miroir est EXACTEMENT celui de DatePicker — granularité par
        # défaut, y compris sa garde « n'écris que si c'est une ISO
        # complète » qui évite d'effacer la sélection pendant une frappe.
        return render_calendar_field(
            self,
            initial=initial,
            value_expr=val,
            blur_js=normalise_to_week_js(val, self._weekstart),
            mirror_granularity=None,
            clearable=self._clearable,
            clear_label=text("week_picker.clear"),
            trigger_icon="calendar-range",
            trigger_label=text("week_picker.open"),
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


__all__ = ["WeekPicker", "normalise_to_week_js"]
