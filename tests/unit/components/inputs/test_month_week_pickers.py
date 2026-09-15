"""Unit tests for :class:`MonthPicker` and :class:`WeekPicker`.

Les deux sont des **enveloppes minces** : cadre, popover, input caché et
routage viennent de ``_picker_field``, la grille de ``ui.calendar``. Ces
tests visent donc ce qui leur est PROPRE — le codec de valeur, le
normaliseur de saisie, et le mode passé au calendrier — plus une passe
sur la mécanique partagée, qui doit rester câblée même si elle n'est plus
écrite ici.
"""

from __future__ import annotations

import datetime as dt

import pytest

from bretzel.components.base.attrs import (
    ComponentDefinitionError,
    ComponentUsageError,
)
from bretzel.components.base.testing import render_isolated
from bretzel.components.inputs.month_picker import MonthPicker
from bretzel.components.inputs.month_picker.month_picker import month_to_ym
from bretzel.components.inputs.week_picker import WeekPicker
from bretzel.core.serialize import serialize
from bretzel.state.scopes.client import ClientBinding


def _change_handler() -> None:
    pass


def _html(cls, **kwargs) -> str:
    with render_isolated():
        return serialize(cls(**kwargs).render())


# ── Codec de valeur — ce qui leur est propre ─────────────────────────


class TestMonthCodec:
    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("2026-08", "2026-08"),
            # Une date est TRONQUÉE : qui passe le 14 août veut « août ».
            (dt.date(2026, 8, 14), "2026-08"),
            # Une ISO complète en chaîne est coupée au même endroit.
            ("2026-08-14", "2026-08"),
            (None, ""),
        ],
    )
    def test_month_to_ym(self, raw, expected) -> None:
        assert month_to_ym(raw) == expected

    def test_a_wrong_type_names_the_component(self) -> None:
        with pytest.raises(ComponentDefinitionError, match="MonthPicker"):
            month_to_ym(42)

    def test_the_value_reaches_the_field_and_the_carrier(self) -> None:
        out = _html(MonthPicker, value=dt.date(2026, 8, 14), name="p")
        # Le champ visible ET l'input caché portent la forme tronquée.
        assert out.count('value="2026-08"') >= 2
        assert "2026-08-14" not in out


class TestWeekCodec:
    def test_a_date_becomes_iso(self) -> None:
        out = _html(WeekPicker, value=dt.date(2026, 8, 3), name="s")
        assert out.count('value="2026-08-03"') >= 2

    def test_the_blur_normaliser_snaps_to_the_week_start(self) -> None:
        # Le second temps du normaliseur est ce qui le distingue de celui
        # de DatePicker : sans lui, le champ et la grille diraient deux
        # choses différentes.
        out = _html(WeekPicker, value=dt.date(2026, 8, 3))
        assert "back = (d.getDay() - 1 + 7) % 7" in out
        assert "d.setDate(d.getDate() - back)" in out

    @pytest.mark.parametrize("weekstart,expected", [(0, "0"), (1, "1"), (6, "6")])
    def test_weekstart_reaches_both_the_snap_and_the_calendar(
        self, weekstart, expected
    ) -> None:
        # Le même réglage doit piloter la SAISIE et la GRILLE — les
        # désaccorder rendrait une valeur qui ne correspond pas à la
        # semaine surlignée.
        out = _html(WeekPicker, value=dt.date(2026, 8, 3), weekstart=weekstart)
        assert f"back = (d.getDay() - {expected} + 7) % 7" in out
        assert f'weekstart="{expected}"' in out


# ── Le mode passé au calendrier ──────────────────────────────────────


class TestPanel:
    def test_month_picker_opens_a_month_grid(self) -> None:
        assert 'mode="month"' in _html(MonthPicker, value="2026-08")

    def test_week_picker_opens_a_week_grid(self) -> None:
        assert 'mode="week"' in _html(WeekPicker, value=dt.date(2026, 8, 3))

    def test_month_bounds_are_handed_over_as_dates(self) -> None:
        # Le calendrier attend des dates pour ses bornes et les tronque
        # lui-même — on lui donne le 1er du mois.
        out = _html(MonthPicker, value="2026-08", min="2026-03", max="2026-12")
        assert 'min="2026-03-01"' in out
        assert 'max="2026-12-01"' in out

    @pytest.mark.parametrize("close_on_pick,expected", [(True, 1), (False, 0)])
    def test_close_on_pick_is_wired_into_the_pick_handler(
        self, close_on_pick, expected
    ) -> None:
        # Cibler le handler de PICK, pas la page entière : le dismiss
        # Escape / clic-dehors (``anchored_dismiss_init``) contient lui
        # aussi ``open = false``, donc chercher la chaîne dans tout le
        # HTML passerait dans les deux cas — un test toujours vert.
        out = _html(
            MonthPicker, value="2026-08", close_on_pick=close_on_pick
        )
        handler = out.split("bz-on:change=")[1].split(">")[0]
        assert handler.count("open = false") == expected, handler


# ── La mécanique partagée — toujours câblée, bien qu'externalisée ────


class TestSharedPlumbing:
    @pytest.mark.parametrize("cls", [MonthPicker, WeekPicker])
    def test_hidden_carrier_carries_the_shared_ref(self, cls) -> None:
        # ``bz-ref="bzhidden"`` vient du squelette partagé. S'il manque,
        # c'est que quelqu'un a réécrit le porteur à la main — la faute
        # exacte que ``_picker_field`` existe pour rendre impossible.
        out = _html(cls, value="2026-08" if cls is MonthPicker else "2026-08-03",
                    name="f")
        assert 'bz-ref="bzhidden"' in out
        assert 'name="f"' in out

    @pytest.mark.parametrize("cls", [MonthPicker, WeekPicker])
    def test_panel_is_anchored_and_dismissable(self, cls) -> None:
        out = _html(cls)
        assert 'bz-ref="bzpanel"' in out
        assert 'bz-ref="bztrigger"' in out
        assert "clickOutside" in out
        assert "display:none" in out       # anti-FOUC

    @pytest.mark.parametrize("cls", [MonthPicker, WeekPicker])
    def test_disabled_binding_reaches_the_three_carriers(self, cls) -> None:
        binding = ClientBinding(class_name="F", instance_key="default",
                                field_name="locked", value=False)
        out = _html(cls, value="2026-08" if cls is MonthPicker else "2026-08-03",
                    disabled=binding)
        assert out.count("bz-attr:disabled") == 3

    @pytest.mark.parametrize("cls", [MonthPicker, WeekPicker])
    def test_focus_handler_lands_on_the_editable_field(self, cls) -> None:
        # La racine est un <div> non focusable et focus ne bulle pas.
        out = _html(cls, on_focus=_change_handler)
        assert "hx-post" not in out.split("<input")[0]
        assert 'hx-trigger="focus"' in out

    @pytest.mark.parametrize("cls", [MonthPicker, WeekPicker])
    def test_a_binding_on_a_static_prop_raises(self, cls) -> None:
        binding = ClientBinding(class_name="F", instance_key="default",
                                field_name="x", value="")
        with render_isolated(), pytest.raises(
            (ComponentUsageError, TypeError)
        ):
            cls(min=binding)

    @pytest.mark.parametrize("cls", [MonthPicker, WeekPicker])
    def test_bound_value_leaves_no_local_signal(self, cls) -> None:
        binding = ClientBinding(class_name="F", instance_key="default",
                                field_name="v", value="")
        out = _html(cls, value=binding)
        data = out.split('bz-data="')[1].split('"')[0]
        assert data == "{open: false}", (
            f"en mode lié la valeur vit dans le store, le scope ne porte "
            f"que le drapeau d'ouverture : {data}"
        )

    @pytest.mark.parametrize("cls", [MonthPicker, WeekPicker])
    def test_clearable_false_drops_the_cross(self, cls) -> None:
        seed = "2026-08" if cls is MonthPicker else "2026-08-03"
        assert "Clear" in _html(cls, value=seed)
        assert "Clear" not in _html(cls, value=seed, clearable=False)


class TestAxes:
    @pytest.mark.parametrize("cls", [MonthPicker, WeekPicker])
    @pytest.mark.parametrize(
        "left,right", [("xs", "sm"), ("md", "lg"), ("lg", "xl")]
    )
    def test_sizes_are_distinct(self, cls, left, right) -> None:
        assert _html(cls, size=left) != _html(cls, size=right)

    @pytest.mark.parametrize("cls", [MonthPicker, WeekPicker])
    @pytest.mark.parametrize("color", ["primary", "success", "error"])
    def test_color_reaches_the_frame(self, cls, color) -> None:
        assert "focus-within:border-(--bz-solid)" in _html(cls, color=color)
        assert f"bz-c-{color}" in _html(cls, color=color)
