"""Unit tests for :class:`bretzel.components.layout.resizable.Resizable`."""

from __future__ import annotations

import pytest

from bretzel import refreshable
from bretzel.components.base.attrs import ComponentUsageError
from bretzel.components.base.testing import render_isolated
from bretzel.components.layout.resizable import (
    Resizable,
    ResizablePanel,
    normalize_weights,
)
from bretzel.components.layout.resizable.theme import RESIZABLE_THEME
from bretzel.components.meta.fragment import Fragment
from bretzel.components.primitives.text import Text
from bretzel.core.serialize import serialize
from bretzel.state import PageState, field
from bretzel.state.scopes.client import ClientState, rendering_scope


# Module-level handler — encode_handler_id needs an addressable qualname.
def _change_handler() -> None:
    pass


class _Zone(PageState):
    n: int = field(default=0)


class Layout(ClientState, persist="local"):
    split: list = field(default_factory=lambda: [30, 70])


def _build(*, panels: int = 2, mins: tuple[float, ...] = (), **kwargs):
    with Resizable(**kwargs) as group:
        for index in range(panels):
            with ResizablePanel(
                min_size=mins[index] if index < len(mins) else None
            ):
                Text(f"panel {index}")
    return group


def _html(**kwargs) -> str:
    """Construire ET rendre dans le MÊME contexte : la construction d'un
    composant en a besoin autant que son render."""
    with render_isolated():
        return serialize(_build(**kwargs).render())


class TestNormalizeWeights:
    """``normalize_weights`` est le MIROIR de ``_weights()`` dans
    ``_src/20_resizable.js`` — les deux décident de la même chose, le
    serveur pour le premier paint, le runtime pour la suite."""

    def test_none_splits_evenly(self) -> None:
        assert normalize_weights(None, 2) == [50.0, 50.0]
        assert normalize_weights(None, 4) == [25.0, 25.0, 25.0, 25.0]

    def test_ratios_are_normalised_to_percent(self) -> None:
        # [1, 3] et [25, 75] disent la même chose : c'est le RAPPORT qui
        # compte, pas l'unité.
        assert normalize_weights([1, 3], 2) == normalize_weights([25, 75], 2)
        assert normalize_weights([1, 3], 2) == [25.0, 75.0]

    def test_short_list_is_padded_not_rejected(self) -> None:
        # Les panneaux viennent souvent des données : leur nombre change
        # sans que la valeur persistée dans localStorage l'ait su. Lever
        # ferait planter la page sur un état vieux de trois jours.
        assert len(normalize_weights([50], 3)) == 3

    def test_garbage_entries_fall_back_per_panel(self) -> None:
        # Aucun panneau ne doit DISPARAÎTRE à cause d'une valeur cassée.
        out = normalize_weights([-10, "nope", 40], 3)
        assert len(out) == 3
        assert all(w > 0 for w in out)

    def test_result_always_sums_to_a_hundred(self) -> None:
        for raw in (None, [1, 3], [50], [-1, -1], ["a", "b"], [0, 0]):
            out = normalize_weights(raw, 3)
            assert sum(out) == pytest.approx(100.0, abs=0.05)

    def test_zero_panels_is_empty_not_a_crash(self) -> None:
        assert normalize_weights([50, 50], 0) == []


class TestStructure:
    def test_root_carries_the_shared_scope(self) -> None:
        out = _html()
        assert "$bz.resizable.scope" in out
        # Le bz-data ne porte QUE des données : les méthodes vivent une
        # seule fois dans le scope partagé.
        head = out.split("bz-data=")[1].split("bz-init=")[0]
        assert "_start(" not in head
        assert "getBoundingClientRect" not in head

    def test_group_is_captured_for_the_scope(self) -> None:
        # Une méthode de scope n'a pas ``$el`` — seules les directives
        # en ont, d'où la capture au bz-init.
        assert 'bz-init="_group = $el"' in _html()

    def test_every_panel_is_marked_and_weighted(self) -> None:
        out = _html(panels=3)
        assert out.count("data-bz-rz-panel") == 3
        # ``basis-0`` est ce qui rend le partage proportionnel : sans
        # lui la base d'un panneau est son CONTENU.
        assert out.count("basis-0") == 3
        # ``min-w-0`` désactive le plancher ``min-width:auto`` de
        # flexbox — sans lui un panneau refuse de descendre sous la
        # largeur de son contenu et la poignée se bloque avant le
        # minimum déclaré.
        assert out.count("min-w-0") == 3

    def test_handles_are_derived_one_fewer_than_panels(self) -> None:
        for panels in (1, 2, 3, 5):
            out = _html(panels=panels)
            assert out.count("data-bz-rz-handle") == max(0, panels - 1)

    def test_empty_group_renders_without_crashing(self) -> None:
        with render_isolated():
            out = serialize(Resizable().render())
        assert "data-bz-rz-handle" not in out

    def test_weights_land_in_the_ssr_style(self) -> None:
        # Le style inline dès le SSR : la mise en page est juste au
        # premier paint, avant que le runtime reprenne la main.
        out = _html(sizes=[25, 75])
        assert "flex-grow:25" in out
        assert "flex-grow:75" in out

    def test_integral_weights_carry_no_decimal_noise(self) -> None:
        out = _html(sizes=[25, 75])
        assert "flex-grow:25.0" not in out
        assert "sizes: [25, 75]" in out

    def test_mins_travel_as_data(self) -> None:
        out = _html(mins=(15, 5))
        assert "_mins: [15, 5]" in out

    def test_a_stray_child_becomes_a_panel(self) -> None:
        # **Chaque enfant direct EST un panneau.** Le groupe enveloppe
        # ce qui n'est pas un ``resizable_panel`` dans la MÊME boîte —
        # donc rien à refuser, et la composition marche.
        with render_isolated():
            with Resizable() as group:
                Text("nu")
                with ResizablePanel():
                    Text("déclaré")
            out = serialize(group.render())
        assert out.count("data-bz-rz-panel") == 2
        assert out.count("basis-0") == 2
        assert "nu" in out
        # Deux panneaux ⇒ une poignée, quelle que soit leur provenance.
        assert out.count("data-bz-rz-handle") == 1

    def test_a_refreshable_zone_can_be_a_panel(self) -> None:
        # Le cas qui a fait retirer la levée : ``@refreshable`` attache
        # un ``_RefreshableSection`` au parent courant comme n'importe
        # quel composant. Refuser les enfants étrangers rendait
        # ``ui.resizable`` incompatible avec la zone de rafraîchissement
        # — et le message d'erreur citait une classe interne que
        # l'appelant n'a jamais tapée.
        @refreshable(deps=[_Zone])
        def pane() -> None:
            with ResizablePanel():
                Text("gauche")

        with render_isolated():
            with Resizable() as group:
                pane()
                with ResizablePanel():
                    Text("droite")
            out = serialize(group.render())
        assert "gauche" in out and "droite" in out
        assert out.count("data-bz-rz-handle") == 1

    def test_a_fragment_can_be_a_panel(self) -> None:
        with render_isolated():
            with Resizable() as group:
                with Fragment():
                    Text("a")
                with ResizablePanel():
                    Text("b")
            out = serialize(group.render())
        assert out.count("data-bz-rz-panel") == 2

    def test_an_explicit_panel_id_wins_and_aria_follows_it(self) -> None:
        # ``aria-controls`` est RELU sur le nœud rendu : le déduire des
        # deux côtés, c'est la paire qui se désaccorde dès qu'un
        # appelant passe son propre ``id=``.
        with render_isolated():
            with Resizable() as group:
                with ResizablePanel(id="my-pane"):
                    Text("a")
                with ResizablePanel():
                    Text("b")
            out = serialize(group.render())
        assert 'id="my-pane"' in out
        assert 'aria-controls="my-pane"' in out

    def test_unknown_orientation_raises(self) -> None:
        with render_isolated(), pytest.raises(ComponentUsageError):
            Resizable(orientation="diagonal")


class TestOrientation:
    def test_horizontal_lays_panels_side_by_side(self) -> None:
        assert "flex-row" in _html(orientation="horizontal")

    def test_vertical_stacks_them(self) -> None:
        assert "flex-col" in _html(orientation="vertical")

    def test_separator_orientation_is_the_inverse_of_the_group(self) -> None:
        # La confusion classique du motif : des panneaux CÔTE À CÔTE
        # sont séparés par une barre VERTICALE.
        assert 'aria-orientation="vertical"' in _html(
            orientation="horizontal"
        )
        assert 'aria-orientation="horizontal"' in _html(
            orientation="vertical"
        )

    def test_the_axis_picks_the_grab_cursor(self) -> None:
        assert "cursor-col-resize" in _html(orientation="horizontal")
        assert "cursor-row-resize" in _html(orientation="vertical")


class TestGesture:
    def test_handle_wires_the_full_pointer_cycle(self) -> None:
        out = _html()
        for directive in ("pointerdown", "pointermove", "pointerup",
                          "pointercancel"):
            assert f"bz-on:{directive}" in out

    def test_handle_disables_native_touch_scrolling(self) -> None:
        # Sans ``touch-none`` le navigateur prend le glissement pour un
        # défilement et n'envoie JAMAIS les pointermove : inutilisable
        # au tactile, en silence, alors que la souris marche.
        assert "touch-none" in _html()

    def test_handle_is_keyboard_operable(self) -> None:
        out = _html()
        assert 'tabindex="0"' in out
        assert "bz-on:keydown" in out

    def test_disabled_handle_leaves_the_tab_order(self) -> None:
        out = _html(disabled=True)
        assert 'aria-disabled="true"' in out
        assert 'tabindex="0"' not in out
        assert "bz-on:pointerdown" not in out
        # Le curseur reste peint : ``pointer-events-none`` à côté de
        # ``cursor-not-allowed`` annulerait le curseur en silence.
        assert "cursor-not-allowed" in out


class TestA11y:
    def test_handle_declares_the_window_splitter_pattern(self) -> None:
        out = _html(sizes=[25, 75])
        assert 'role="separator"' in out
        assert 'aria-valuemin="0"' in out
        assert 'aria-valuemax="100"' in out
        assert 'aria-valuenow="25"' in out

    def test_handle_points_at_the_panel_it_resizes(self) -> None:
        out = _html()
        assert "aria-controls=" in out
        # L'id désigné doit EXISTER dans le document rendu, sinon
        # l'attribut ment aux lecteurs d'écran.
        target = out.split('aria-controls="')[1].split('"')[0]
        assert f'id="{target}"' in out

    def test_grip_is_visible_at_rest(self) -> None:
        # Un doigt ne survole pas : un grip qui n'apparaît qu'au
        # ``hover:`` n'annonce jamais qu'il y a quelque chose à
        # attraper. Gaté aussi par test_hover_only_controls_reachable.
        out = _html()
        assert "opacity-0" not in out


class TestBinding:
    def test_bound_sizes_address_the_store_directly(self) -> None:
        with render_isolated(), rendering_scope():
            group = _build(sizes=Layout().split)
            out = serialize(group.render())
        assert "$bz.state.Layout.default.split" in out
        # En mode binding le scope ne stocke PAS de copie locale : la
        # valeur vit dans le store, que l'envelope patche déjà.
        assert "sizes: [" not in out

    def test_binding_on_a_non_bindable_prop_raises(self) -> None:
        with render_isolated(), rendering_scope():
            with pytest.raises(ComponentUsageError):
                Resizable(orientation=Layout().split)

    def test_local_mode_keeps_the_weights_in_the_scope(self) -> None:
        out = _html(sizes=[40, 60])
        assert "sizes: [40, 60]" in out


class TestCarrier:
    def test_no_carrier_without_a_name_or_a_handler(self) -> None:
        # Coller un ``name`` par défaut injecterait un champ parasite
        # dans chaque formulaire englobant.
        assert "<input" not in _html()

    def test_explicit_name_creates_the_carrier(self) -> None:
        out = _html(name="split")
        assert 'name="split"' in out
        assert "JSON.stringify" in out

    def test_change_handler_is_relocated_onto_the_carrier(self) -> None:
        out = _html(on_change=_change_handler)
        # Un <div> ne porte pas de ``change`` natif : le bundle serveur
        # descend sur l'input caché, dont la FormData est non vide.
        assert "hx-post" in out
        head = out.split("<input")[0]
        assert "hx-post" not in head


class TestImperative:
    def test_set_and_reset_are_client_expressions(self) -> None:
        with render_isolated():
            group = _build()
            assert isinstance(group.set([30, 70]), str)
            assert isinstance(group.reset(), str)

    def test_root_listens_to_both_commands(self) -> None:
        out = _html()
        assert "bz-on:bz-set" in out
        assert "bz-on:bz-reset" in out

    def test_reset_always_dispatches_even_when_bound(self) -> None:
        # La part égale dépend du NOMBRE de panneaux vivants, que le
        # serveur ne connaît plus après un morph qui en a ajouté.
        with render_isolated(), rendering_scope():
            group = _build(sizes=Layout().split)
            assert "bz-reset" in group.reset()


class TestTheme:
    @pytest.mark.parametrize("size", ["xs", "sm", "md", "lg", "xl"])
    def test_every_size_reaches_the_handle(self, size: str) -> None:
        # Asserter la CLASSE du palier, pas « le HTML n'est pas vide » :
        # la première version de ce test passait sur n'importe quel
        # rendu, donc elle ne pouvait pas échouer pour la raison que son
        # nom annonce.
        assert RESIZABLE_THEME["sizes"][size]["bar_h"] in _html(size=size)

    def test_two_sizes_render_differently(self) -> None:
        assert _html(size="xs") != _html(size="xl")

    def test_color_lands_on_the_handle_states(self) -> None:
        out = _html(color="success")
        assert "hover:bg-(--bz-solid)/40" in out
        assert "bz-c-success" in out
        assert "focus-visible:ring-(--bz-focus)" in out
