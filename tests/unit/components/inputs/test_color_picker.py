"""``ColorPicker`` — la valeur, le panneau, le formulaire, les refus."""

from __future__ import annotations

import pytest

from bretzel.components.base.attrs import ComponentDefinitionError
from bretzel.components.inputs.color_picker import ColorPicker
from bretzel.components.inputs.color_picker.color_picker import hex_or_empty
from bretzel.core.serialize import serialize
from bretzel.state import ClientState, field
from bretzel.state.scopes.client import rendering_scope
from bretzel.theme import Theme
from tests.consistency._discovery import render_isolated


class _Brand(ClientState, persist="memory"):
    hue: str = field(default="#2f5fd0")


def _html(**kwargs) -> str:
    with render_isolated(theme=Theme()):
        return serialize(ColorPicker(**kwargs).render())


class TestValue:
    def test_the_hex_seeds_the_field_and_the_swatch(self) -> None:
        out = _html(value="#2f5fd0")
        assert 'value="#2f5fd0"' in out
        assert "background-color:#2f5fd0" in out

    def test_an_empty_value_leaves_the_swatch_neutral(self) -> None:
        """Sans couleur, le gris de repos du thème doit rester visible —
        donc AUCUN style inline sur la pastille. Un ``background`` vide
        écraserait la classe."""
        out = _html()
        # Le style INLINE est ce qui compte : l'expression réactive, elle,
        # nomme forcément la propriété.
        assert 'style="background-color:' not in out
        assert "bg-text/5" in out

    def test_none_is_an_empty_field_not_the_string_none(self) -> None:
        assert hex_or_empty(None) == ""

    def test_a_string_passes_even_mid_typing(self) -> None:
        """Le champ est éditable : ``"#2f"`` est un état intermédiaire
        légitime, pas une faute de l'auteur. Même contrat que
        ``time_to_hhmm``."""
        assert hex_or_empty("#2f") == "#2f"

    def test_a_non_string_raises_and_names_the_component(self) -> None:
        with pytest.raises(ComponentDefinitionError) as exc:
            hex_or_empty(42)
        assert "ColorPicker" in str(exc.value)


class TestPanel:
    def test_the_panel_offers_the_theme_palette(self) -> None:
        """La grille vient du THÈME, pas d'une liste en dur — c'est ce qui
        fait qu'une app qui déclare sa charte la retrouve partout."""
        out = _html()
        palette = Theme().get_palette()
        tomato = palette.resolve("tomato", "light").bg_hex
        assert f"background:{tomato}" in out

    def test_a_brand_colour_reaches_the_panel(self) -> None:
        with render_isolated(theme=Theme(palette={"zzbrand": "#ff00aa"})):
            out = serialize(ColorPicker().render())
        assert "#ff00aa" in out

    def test_the_semantic_slots_are_not_offered(self) -> None:
        """Les onze slots sont la STRUCTURE qu'on édite : les proposer
        comme valeur serait circulaire. Ils ne sont donc pas dans la
        grille — seules les couleurs nommées y sont."""
        with render_isolated(theme=Theme()):
            picker = ColorPicker()
            offered = set(picker._palette_swatches())
        palette = Theme().get_palette()
        primary = palette.resolve("primary", "light").bg_hex
        assert primary not in offered or primary in {
            palette.resolve(n, "light").bg_hex
            for n in palette.envelope_dict()
            if n not in {"primary"}
        }

    def test_the_selected_swatch_is_marked(self) -> None:
        palette = Theme().get_palette()
        tomato = palette.resolve("tomato", "light").bg_hex
        out = _html(value=tomato)
        assert 'data-selected="true"' in out


class TestForm:
    def test_a_hidden_input_carries_the_value(self) -> None:
        out = _html(value="#2f5fd0", name="teinte")
        assert 'type="hidden"' in out
        assert 'name="teinte"' in out

    def test_required_lands_on_the_hidden_carrier(self) -> None:
        """Le ``required`` de la VALIDATION vit sur l'input caché ; le
        champ visible n'en porte que le repère ARIA."""
        out = _html(value="#2f5fd0", name="teinte", required=True)
        assert "required" in out
        assert 'aria-required="true"' in out


class TestAxes:
    @pytest.mark.parametrize("size", ["xs", "sm", "md", "lg", "xl"])
    def test_every_size_reaches_the_frame(self, size: str) -> None:
        """Un palier manquant retombe sur ``md`` EN SILENCE — le champ
        sort alors plus petit que son voisin, et ça ne se voit qu'à
        l'écran."""
        heights = {"xs": "h-7", "sm": "h-8", "md": "h-10",
                   "lg": "h-12", "xl": "h-14"}
        assert heights[size] in _html(value="#2f5fd0", size=size)

    def test_color_lands_on_the_bridge(self) -> None:
        out = _html(value="#2f5fd0", color="success")
        assert "bz-c-success" in out

    def test_disabled_reaches_the_three_carriers(self) -> None:
        """La racine est un ``<div>`` : ``disabled`` n'y fait rien. Il est
        forwardé à la main sur le champ, le × et le déclencheur."""
        out = _html(value="#2f5fd0", disabled=True, clearable=True)
        assert out.count("disabled") >= 3

    def test_clearable_adds_the_cross(self) -> None:
        assert "lucide:x" in _html(value="#2f5fd0", clearable=True)
        assert "lucide:x" not in _html(value="#2f5fd0")


class TestBinding:
    def test_a_bound_value_reads_the_store_path(self) -> None:
        with render_isolated(theme=Theme()), rendering_scope():
            brand = _Brand()
            out = serialize(ColorPicker(brand.hue).render())
        assert "$bz.state._Brand.default.hue" in out

    def test_a_literal_value_carries_its_own_scope(self) -> None:
        """Sans binding, la valeur vit dans le scope local ``val``.

        ``_serverSync`` n'y apparaît que si la valeur est ADOSSÉE au
        serveur : un littéral appartient au client, et le morph doit le
        préserver. C'est ``test_server_sync_completeness`` qui garde
        l'autre moitié — celle où le serveur la possède.
        """
        out = _html(value="#2f5fd0")
        assert "value:" in out
        assert "_serverSync" not in out
