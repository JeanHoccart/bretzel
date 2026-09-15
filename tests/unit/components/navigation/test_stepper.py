"""Unit tests for :class:`bretzel.components.navigation.stepper.Stepper`."""

from __future__ import annotations

import pytest

from bretzel.components.base.attrs import ComponentUsageError
from bretzel.components.base.testing import render_isolated
from bretzel.components.navigation.stepper import Step, StepPanel, Stepper
from bretzel.core.serialize import serialize
from bretzel.state.scopes.client import ClientBinding


def _synced_keys(out: str) -> set[str]:
    """Les clés réellement re-semées.

    ``_serverSync`` porte la clé de VALEUR (conditionnelle) ET la config
    server-owned préfixée ``_`` (inconditionnelle) : la simple présence du
    marker ne dit donc plus rien sur la valeur, il faut lire les clés.
    """
    import html as _html
    import re as _re
    keys: set[str] = set()
    for raw in _re.findall(r"_serverSync: \[([^\]]*)\]", _html.unescape(out)):
        keys |= {k.strip().strip("'\"") for k in raw.split(",") if k.strip()}
    return keys




# Module-level handler — encode_handler_id needs an addressable
# qualname (no closures inside test methods).
def _change_handler() -> None:
    pass


def _build(*, value: object = 0, panels: int = 0, steps: int = 3, **kwargs):
    """Stage a Stepper with ``steps`` steps and ``panels`` panels."""
    kwargs["value"] = value
    with Stepper(**kwargs) as s:
        for i in range(steps):
            Step(f"Step {i}")
        for _ in range(panels):
            with StepPanel():
                pass
    return s


def _html(**kwargs) -> str:
    """Construire ET rendre dans le MÊME contexte : la construction d'un
    composant en a besoin autant que son render."""
    with render_isolated():
        return serialize(_build(**kwargs).render())


# ───────────────────────────────────────────────────────────────────────────
# A. Render structure
# ───────────────────────────────────────────────────────────────────────────


class TestStructure:
    def test_root_carries_the_shared_scope(self) -> None:
        out = _html(value=1)
        assert "bz-data=" in out
        # Les méthodes vivent dans le scope partagé, pas sérialisées par
        # instance : le bz-data ne doit porter QUE des données.
        assert "$bz.stepper.scope" in out
        assert "_status(" not in out.split("bz-data=")[1].split(">")[0]

    def test_list_is_a_real_ordered_list(self) -> None:
        out = _html(value=0)
        # L'ordre est natif — pas simulé en ARIA.
        assert "<ol" in out
        assert out.count("<li") == 3

    def test_status_is_derived_not_declared(self) -> None:
        out = _html(value=1)
        assert 'data-status="done"' in out
        assert 'data-status="current"' in out
        assert 'data-status="upcoming"' in out

    def test_status_stays_reactive(self) -> None:
        out = _html(value=1)
        # SSR statique pour le premier paint + bz-attr pour la suite.
        assert 'bz-attr:data-status="_status(0)"' in out
        assert 'bz-attr:data-status="_status(2)"' in out

    def test_last_step_has_no_connector(self) -> None:
        out = _html(value=0, steps=3)
        # Un connecteur par étape SAUF la dernière.
        assert out.count('aria-hidden="true"') == 2

    def test_max_index_counts_the_extra_panel(self) -> None:
        # 2 étapes + 3 panneaux → l'écran « terminé » est l'index 2, et
        # ``next()`` doit pouvoir l'atteindre.
        out = _html(value=0, steps=2, panels=3)
        assert "_max: 2" in out

    def test_max_index_falls_back_to_the_steps(self) -> None:
        out = _html(value=0, steps=4, panels=0)
        assert "_max: 3" in out

    def test_single_step_has_max_zero(self) -> None:
        out = _html(value=0, steps=1)
        assert "_max: 0" in out


class TestBullet:
    def test_number_and_check_are_both_mounted(self) -> None:
        out = _html(value=1)
        # Deux glyphes montés, un seul visible — le runtime bascule un
        # display, il ne réécrit pas du texte.
        assert 'bz-show="_status(0) !== \'done\'"' in out
        assert 'bz-show="_status(0) === \'done\'"' in out

    def test_hidden_glyph_is_prestamped(self) -> None:
        out = _html(value=1)
        # Anti-FOUC : le glyphe caché au SSR l'est en inline style.
        assert "display:none" in out

    def test_explicit_icon_replaces_both_glyphs(self) -> None:
        with render_isolated():
            with Stepper(value=0) as s:
                Step("Profile", icon="user")
            out = serialize(s.render())
        assert "lucide:user" in out
        assert "lucide:check" not in out

    def test_error_status_is_frozen(self) -> None:
        with render_isolated():
            with Stepper(value=2) as s:
                Step("A")
                Step("B", status="error")
            out = serialize(s.render())
        assert 'data-status="error"' in out
        # Figé = pas recalculé côté client (l'index courant ne le
        # concerne pas).
        assert 'bz-attr:data-status="_status(1)"' not in out

    def test_not_clickable_renders_no_focusable_element(self) -> None:
        out = _html(value=0)
        assert "<button" not in out
        assert "bz-on:click" not in out

    def test_clickable_renders_buttons_that_move_the_index(self) -> None:
        out = _html(value=0, clickable=True)
        assert out.count('bz-on:click="goTo(') == 3

    def test_disabled_step_is_inert_even_when_clickable(self) -> None:
        with render_isolated():
            with Stepper(value=0, clickable=True) as s:
                Step("A")
                Step("B", disabled=True)
            out = serialize(s.render())
        assert "disabled" in out
        # Le bouton désactivé n'embarque pas le geste.
        assert out.count('bz-on:click="goTo(') == 1


class TestPanels:
    def test_panels_are_paired_by_declaration_order(self) -> None:
        out = _html(value=0, steps=2, panels=2)
        assert 'bz-show="Number(value) === 0"' in out
        assert 'bz-show="Number(value) === 1"' in out

    def test_inactive_panel_is_prestamped_hidden(self) -> None:
        with render_isolated():
            with Stepper(value=0) as s:
                Step("A")
                with StepPanel():
                    pass
                with StepPanel():
                    pass
            out = serialize(s.render())
        # Le panneau 1 est caché au SSR, le 0 non.
        panels = out.split("Number(value) === ")
        assert "display:none" in panels[2]

    def test_no_panels_renders_no_panel_container(self) -> None:
        out = _html(value=0, panels=0)
        assert "Number(value)" not in out


class TestValueModes:
    def test_literal_value_has_no_server_sync(self) -> None:
        out = _html(value=1)
        # Un littéral est client-owned : un refresh voisin ne doit pas
        # écraser la navigation (même garde que Tabs / Select).
        assert "value" not in _synced_keys(out)

    def test_binding_mode_has_no_local_signal(self) -> None:
        binding = ClientBinding(class_name="Wiz", instance_key="default", field_name="step", value=0)
        out = _html(value=binding)
        # Pas de champ local NI de getter : absorb figerait un getter sur
        # sa première valeur.
        assert "value:" not in out
        assert "get current()" not in out
        assert "$bz.state.Wiz.default.step" in out

    def test_string_value_is_coerced(self) -> None:
        # La valeur revient d'une form data en chaîne — « 2 » vaut 2.
        out = _html(value="2")
        assert "value: 2," in out

    def test_garbage_value_falls_back_to_zero(self) -> None:
        out = _html(value="nope")
        assert "value: 0," in out

    def test_binding_on_a_non_bindable_prop_raises(self) -> None:
        binding = ClientBinding(class_name="Wiz", instance_key="default", field_name="flag", value=False)
        with render_isolated(), pytest.raises(ComponentUsageError):
            Stepper(clickable=binding)


class TestFormIntegration:
    def test_no_name_no_hidden_input(self) -> None:
        out = _html(value=0)
        assert 'type="hidden"' not in out

    def test_explicit_name_emits_the_carrier(self) -> None:
        out = _html(value=1, name="step")
        assert 'type="hidden"' in out
        assert 'name="step"' in out
        assert 'value="1"' in out

    def test_change_handler_is_relocated_onto_the_input(self) -> None:
        out = _html(value=0, on_change=_change_handler)
        # Une <ol> n'a pas de ``change`` natif : le bundle serveur doit
        # vivre sur l'input, sinon la FormData part vide.
        assert 'type="hidden"' in out
        head = out.split("<input")[0]
        assert "hx-post" not in head
        assert "hx-post" in out.split("<input")[1]

    def test_change_is_redispatched_on_every_move(self) -> None:
        out = _html(value=0, on_change=_change_handler)
        assert "bz-effect=" in out


class TestImperative:
    def test_root_carries_the_three_receivers(self) -> None:
        out = _html(value=0)
        assert 'bz-on:bz-set="goTo($event.detail.value)"' in out
        assert 'bz-on:bz-next="next()"' in out
        assert 'bz-on:bz-prev="prev()"' in out

    def test_methods_return_client_expression_strings(self) -> None:
        with render_isolated():
            wiz = _build(value=0)
            assert isinstance(wiz.next(), str)
            assert isinstance(wiz.prev(), str)
            assert isinstance(wiz.set(2), str)

    def test_set_writes_through_the_binding(self) -> None:
        binding = ClientBinding(class_name="Wiz", instance_key="default", field_name="step", value=0)
        with render_isolated():
            wiz = _build(value=binding)
            assert "$bz.state.Wiz.default.step" in wiz.set(2)

    def test_next_dispatches_even_with_a_binding(self) -> None:
        # La destination dépend de la valeur vivante ET de la borne — le
        # serveur ne connaît ni l'une ni l'autre au rendu, donc un
        # write-through devrait baker index+1 et déborderait.
        binding = ClientBinding(class_name="Wiz", instance_key="default", field_name="step", value=0)
        with render_isolated():
            wiz = _build(value=binding)
            assert "bz-next" in wiz.next()
            assert "bz-prev" in wiz.prev()

    def test_imperative_forces_identity(self) -> None:
        out = _html(value=0)
        # Sans id rendu, le dispatch d'un trigger externe échouerait en
        # silence.
        assert "bz-id=" in out


class TestAxes:
    @pytest.mark.parametrize("axis", ["horizontal", "vertical"])
    def test_orientation_reaches_the_list(self, axis: str) -> None:
        out = _html(value=0, orientation=axis)
        assert ("flex-row" if axis == "horizontal" else "flex-col") in out

    def test_orientations_render_differently(self) -> None:
        assert _html(value=0, orientation="horizontal") != _html(value=0, orientation="vertical")

    def test_unknown_orientation_falls_back_to_horizontal(self) -> None:
        assert _html(value=0, orientation="sideways") == _html(value=0, orientation="horizontal")

    @pytest.mark.parametrize(
        "left,right",
        [("xs", "sm"), ("sm", "md"), ("md", "lg"), ("lg", "xl")],
    )
    def test_sizes_are_distinct(self, left: str, right: str) -> None:
        assert _html(value=0, size=left) != _html(value=0, size=right)

    @pytest.mark.parametrize("color", ["primary", "success", "error"])
    def test_color_reaches_the_bullet(self, color: str) -> None:
        out = _html(value=1, color=color)
        assert "group-data-[status=done]/step:bg-(--bz-solid)" in out
        assert f"bz-c-{color}" in out


class TestStandalone:
    def test_step_outside_a_stepper_is_inert(self) -> None:
        with render_isolated():
            out = serialize(Step("Orphan").render())
        assert out == "<span></span>"

    def test_panel_outside_a_stepper_still_shows_its_content(self) -> None:
        with render_isolated():
            panel = StepPanel()
            out = serialize(panel.render())
        assert "<div" in out


