"""Unit tests for :class:`bretzel.components.inputs.time_picker.TimePicker`."""

from __future__ import annotations

import datetime as dt
import re

import pytest

from bretzel.components.base.attrs import (
    ComponentDefinitionError,
    ComponentUsageError,
)
from bretzel.components.base.testing import render_isolated
from bretzel.components.inputs.time_picker import TimePicker
from bretzel.core.serialize import serialize
from bretzel.state.scopes.client import ClientBinding


def _change_handler() -> None:
    pass


def _html(**kwargs) -> str:
    with render_isolated():
        return serialize(TimePicker(**kwargs).render())


def _cells(html: str, part: int) -> list[tuple[str, bool]]:
    """Les cellules d'une colonne : ``(valeur, activée)``.

    ⚠️ **Ça ne lit plus des ``<button>``.** Depuis le 2026-09-01 les
    cellules sont peintes par ``$bz.time.fill`` ; le SSR ne rend que la
    DESCRIPTION de la colonne — ses valeurs, et celles qui sont hors
    bornes. Les faits que ces tests jugent (combien de minutes, quelles
    heures sont grisées) sont donc lus à leur nouvelle place, et ils
    restent des faits de Python : le bornage n'a pas déménagé, seul le
    balisage l'a fait.

    La forme rendue est volontairement la MÊME qu'avant — ``(valeur,
    activée)`` — pour que les tests de ``step`` et de bornes n'aient pas
    à changer d'une ligne. S'ils avaient dû changer, ça aurait voulu
    dire que le comportement changeait aussi.
    """
    col = re.search(
        rf'<div[^>]*data-bz-part="{part}"[^>]*>', html
    )
    if col is None:
        return []
    frag = col.group(0)

    def _liste(attr: str) -> list[str]:
        m = re.search(rf'{attr}="([^"]*)"', frag)
        return [v for v in (m.group(1).split(",") if m else []) if v]

    off = set(_liste("data-bz-off"))
    return [(v, v not in off) for v in _liste("data-bz-values")]


class TestStructure:
    def test_root_carries_the_shared_scope(self) -> None:
        out = _html(value=dt.time(9, 30))
        assert "$bz.time.scope" in out
        # Le bz-data ne porte QUE des données : les méthodes vivent une
        # seule fois dans le scope partagé — 28 boutons par panneau, les
        # sérialiser par bouton serait 28 copies de l'algorithme.
        data = out.split('bz-data="')[1].split('"')[0]
        assert "_parts()" not in data
        assert "padStart" not in data

    def test_bound_expressions_live_in_method_bodies(self) -> None:
        binding = ClientBinding(class_name="Slot", instance_key="default",
                                field_name="start", value="09:00")
        out = _html(value=binding)
        data = out.split('bz-data="')[1].split('"')[0]
        # Régression gardée : un CHAMP de bz-data est évalué une fois,
        # hors effet — ``absorb`` en découple le snapshot du store, et
        # plus rien ne le réécrit. Une expression liée DOIT vivre dans un
        # corps de méthode (cf. traps.md).
        assert "_read() { return $bz.state.Slot.default.start; }" in data
        assert "value:" not in data

    def test_literal_value_seeds_a_local_signal(self) -> None:
        out = _html(value=dt.time(9, 30))
        data = out.split('bz-data="')[1].split('"')[0]
        assert "value:" in data
        assert "09:30" in data

    def test_two_columns_declare_their_cells(self) -> None:
        out = _html(value=dt.time(9, 30), step=15)
        assert len(_cells(out, 0)) == 24          # heures
        assert len(_cells(out, 1)) == 4           # 60 / 15
        assert out.count('role="listbox"') == 2

    def test_columns_are_snap_scrollers_without_a_scrollbar(self) -> None:
        out = _html(value=dt.time(9, 30))
        # ``bz-no-scrollbar`` est un hook du CSS framework : la variante
        # Tailwind arbitraire équivalente NE COMPILE PAS (mesuré sur le
        # Carousel).
        assert "bz-no-scrollbar" in out
        assert "snap-y" in out and "snap-mandatory" in out

    def test_no_cell_is_rendered_server_side(self) -> None:
        """Le SSR décrit les colonnes, il ne les remplit pas.

        Ce test disait l'INVERSE jusqu'au 2026-09-01 : il exigeait deux
        ``data-selected="true"`` et un ``bz-attr:data-selected``, au nom
        d'un anti-flash « juste au premier paint, avant hydratation ».

        L'argument ne tenait pas : le panneau est pré-estampillé FERMÉ
        (cf. ``TestPanel``), donc personne ne voit ses cellules au
        premier paint — ni les bonnes, ni les mauvaises. Le seul effet
        réel de ce SSR était son poids : 84 cellules à ``step=1``,
        49 Ko sur les 54 du composant.

        Ce qui remplace la garde : le probe navigateur vérifie que la
        sélection est peinte ET repeinte
        (``tests/probes/probe_time_picker_cells.py``). C'est le bon
        étage — une sélection qui se voit se mesure à l'écran.
        """
        out = _html(value=dt.time(9, 30))
        assert "bz-attr:data-selected" not in out
        assert 'data-bz-v="' not in out
        # Mais la colonne se décrit, sinon le client n'a rien à peindre.
        assert 'data-bz-values="' in out
        assert "$bz.time.fill($el" in out


class TestStep:
    @pytest.mark.parametrize(
        "step,expected", [(1, 60), (5, 12), (15, 4), (30, 2), (60, 1)]
    )
    def test_step_decides_the_minute_cells(self, step, expected) -> None:
        assert len(_cells(_html(step=step), 1)) == expected

    @pytest.mark.parametrize("step", [0, -5, 61, 90])
    def test_an_impossible_step_raises_at_construct(self, step) -> None:
        # Sans la garde, step=0 boucle à l'infini et step=90 rend une
        # colonne vide — toutes deux en silence.
        with render_isolated(), pytest.raises(ComponentUsageError):
            TimePicker(step=step)


class TestBounds:
    def test_min_and_max_gate_the_hours(self) -> None:
        active = [h for h, ok in _cells(
            _html(value=dt.time(9, 0), min="09:00", max="18:00"), 0) if ok]
        assert active == [f"{h:02d}" for h in range(9, 19)]

    def test_an_hour_survives_if_any_of_its_minutes_fits(self) -> None:
        # ``min="09:30"`` ne doit PAS griser l'heure 09 : 09:45 est
        # valide, et le griser la rendrait inatteignable.
        active = [h for h, ok in _cells(_html(min="09:30"), 0) if ok]
        assert "09" in active
        assert "08" not in active

    def test_no_bounds_leaves_everything_open(self) -> None:
        assert all(ok for _, ok in _cells(_html(), 0))

    def test_out_of_bounds_value_is_still_displayed(self) -> None:
        # On ne réécrit jamais ce que le serveur a envoyé.
        out = _html(value=dt.time(3, 0), min="09:00", max="18:00")
        assert 'value="03:00"' in out


class TestValueCoercion:
    def test_a_time_becomes_hhmm(self) -> None:
        assert 'value="09:05"' in _html(value=dt.time(9, 5))

    def test_a_string_passes_through(self) -> None:
        assert 'value="09:05"' in _html(value="09:05")

    def test_none_is_an_empty_field(self) -> None:
        out = _html()
        assert 'value=""' in out

    def test_a_wrong_type_raises_with_the_component_name(self) -> None:
        with render_isolated(), pytest.raises(
            ComponentDefinitionError, match="TimePicker"
        ):
            TimePicker(value=42).render()


class TestFormIntegration:
    def test_hidden_carrier_uses_the_shared_skeleton(self) -> None:
        out = _html(value=dt.time(9, 30), name="start_at")
        assert 'type="hidden"' in out
        assert 'name="start_at"' in out
        # ``bz-ref`` fait partie du squelette partagé — s'il manque,
        # c'est que le skeleton a été réécrit à la main.
        assert 'bz-ref="bzhidden"' in out

    def test_required_lands_on_the_carrier_not_the_visible_field(self) -> None:
        out = _html(value=dt.time(9, 30), name="t", required=True)
        hidden = out.split("<input")[1]
        assert "required" in hidden
        # Le champ visible ne porte qu'un repère ARIA.
        assert 'aria-required="true"' in out

    def test_change_handler_is_routed_onto_the_carrier(self) -> None:
        out = _html(value=dt.time(9, 30), on_change=_change_handler)
        # ``relocate_server_action`` lit hx-trigger et choisit la cible :
        # un change va au porteur de valeur, pas au wrapper (qui n'a ni
        # name ni value, donc enverrait une FormData vide).
        assert "hx-post" not in out.split("<input")[0]

    def test_focus_handler_is_routed_onto_the_editable_field(self) -> None:
        out = _html(value=dt.time(9, 30), on_focus=_change_handler)
        # La racine est un <div> non focusable et focus ne bulle pas —
        # laissé là, le handler ne partirait jamais.
        assert "hx-post" not in out.split("<input")[0]
        assert 'hx-trigger="focus"' in out


class TestBindings:
    def test_value_binding_drives_every_carrier(self) -> None:
        binding = ClientBinding(class_name="Slot", instance_key="default",
                                field_name="start", value="09:00")
        out = _html(value=binding)
        path = "$bz.state.Slot.default.start"
        assert f'bz-model="{path}"' in out          # champ éditable
        assert f'bz-attr:value="{path}"' in out     # input caché

    def test_disabled_binding_reaches_the_three_carriers(self) -> None:
        binding = ClientBinding(class_name="Slot", instance_key="default",
                                field_name="locked", value=False)
        out = _html(value=dt.time(9, 0), disabled=binding)
        # Le wrapper est un <div> : ``disabled`` n'y ferait rien. Il doit
        # atterrir sur le champ, le × et le trigger.
        assert out.count("bz-attr:disabled") == 3

    @pytest.mark.parametrize("prop", ["min", "max", "step"])
    def test_a_binding_on_a_static_prop_raises(self, prop: str) -> None:
        binding = ClientBinding(class_name="Slot", instance_key="default",
                                field_name="x", value="09:00")
        with render_isolated(), pytest.raises(
            (ComponentUsageError, TypeError)
        ):
            TimePicker(**{prop: binding})


class TestPanel:
    def test_panel_is_prestamped_closed(self) -> None:
        out = _html(value=dt.time(9, 0))
        assert "display:none" in out

    def test_panel_is_anchored_and_dismissable(self) -> None:
        out = _html(value=dt.time(9, 0))
        assert 'bz-ref="bzpanel"' in out
        assert 'bz-ref="bztrigger"' in out
        # Escape + clic-dehors : ``bz-on`` n'a AUCUN modificateur, donc
        # les deux passent par le helper posé en bz-init.
        assert "bz-init=" in out
        assert "clickOutside" in out

    def test_opening_scrolls_the_selection_into_view(self) -> None:
        # 24 heures : ouvrir à 14:00 en montrant 00-06 obligerait à
        # chercher.
        assert "scrollIntoView" in _html(value=dt.time(14, 0))

    def test_close_on_pick_is_data_not_code(self) -> None:
        data_on = _html(value=dt.time(9, 0)).split('bz-data="')[1]
        data_off = _html(
            value=dt.time(9, 0), close_on_pick=False
        ).split('bz-data="')[1]
        assert "_closeOnPick: true" in data_on
        assert "_closeOnPick: false" in data_off


class TestAxes:
    @pytest.mark.parametrize(
        "left,right",
        [("xs", "sm"), ("sm", "md"), ("md", "lg"), ("lg", "xl")],
    )
    def test_sizes_are_distinct(self, left: str, right: str) -> None:
        assert _html(size=left) != _html(size=right)

    @pytest.mark.parametrize("color", ["primary", "success", "error"])
    def test_color_reaches_the_selected_cell(self, color: str) -> None:
        assert "data-[selected=true]:bg-(--bz-solid)" in _html(color=color)
        assert f"bz-c-{color}" in _html(color=color)

    def test_clearable_false_drops_the_cross(self) -> None:
        assert "Clear time" not in _html(value=dt.time(9, 0), clearable=False)
        assert "Clear time" in _html(value=dt.time(9, 0))

    def test_labels_are_translatable(self) -> None:
        out = _html(hour_label="Heures", minute_label="Min")
        assert "Heures" in out and "Min" in out
