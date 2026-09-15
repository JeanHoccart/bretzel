"""Unit tests for
:class:`bretzel.components.inputs.signature_pad.SignaturePad`."""

from __future__ import annotations

import pytest

from bretzel.components.base.attrs import ComponentUsageError
from bretzel.components.base.testing import render_isolated
from bretzel.components.inputs.signature_pad import SignaturePad
from bretzel.components.inputs.signature_pad.theme import SIGNATURE_PAD_THEME
from bretzel.core.serialize import serialize
from bretzel.state import field
from bretzel.state.scopes.client import ClientState, rendering_scope
from bretzel.state.scopes.server import _BoundStr


# Module-level handler — encode_handler_id needs an addressable qualname.
def _change_handler() -> None:
    pass


class Draft(ClientState, persist="memory"):
    sig: str = field(default="")


def _html(**kwargs) -> str:
    with render_isolated():
        return serialize(SignaturePad(**kwargs).render())


class TestStructure:
    def test_root_carries_the_shared_scope(self) -> None:
        out = _html()
        assert "$bz.signaturePad.scope" in out
        # Le bz-data ne porte QUE des données : le tracé, la publication
        # et le redimensionnement vivent une fois dans le scope partagé.
        head = out.split("bz-data=")[1].split("bz-init=")[0]
        assert "toDataURL" not in head
        assert "getContext" not in head

    def test_canvas_is_captured_for_the_scope(self) -> None:
        # Une méthode de scope n'a pas ``$refs`` — seules les directives
        # en ont, d'où la capture au bz-init.
        assert 'bz-init="_canvas = $refs.bzcanvas"' in _html()

    def test_it_renders_exactly_one_canvas(self) -> None:
        assert _html().count("<canvas") == 1

    def test_canvas_disables_native_touch_scrolling(self) -> None:
        # Sans ``touch-none`` le navigateur prend le glissement d'un
        # doigt pour un défilement et n'envoie JAMAIS les pointermove :
        # inutilisable au tactile, en silence, alors que la souris
        # marche.
        assert "touch-none" in _html()

    def test_canvas_wires_the_full_pointer_cycle(self) -> None:
        out = _html()
        for directive in ("pointerdown", "pointermove", "pointerup",
                          "pointercancel"):
            assert f"bz-on:{directive}" in out

    def test_the_resize_observer_rides_an_effect_not_an_init(self) -> None:
        # ``bz-init`` est one-shot par NŒUD : un canvas remplacé par un
        # morph ne serait jamais observé, donc jamais redimensionné,
        # donc flou puis vide.
        assert 'bz-effect="_observe()"' in _html()

    def test_placeholder_and_baseline_are_rendered(self) -> None:
        out = _html(placeholder="Signez ici")
        assert "Signez ici" in out
        assert "border-b" in out

    def test_empty_placeholder_drops_the_hint(self) -> None:
        assert "Sign here" not in _html(placeholder="")

    def test_empty_clear_label_drops_the_button(self) -> None:
        assert "<button" not in _html(clear_label="")

    def test_the_clear_button_is_a_real_ui_button(self) -> None:
        # Dogfooding : il apporte gratuitement l'anneau de focus, l'état
        # disabled et l'échelle de tailles.
        out = _html()
        assert "<button" in out
        assert "focus-visible:ring" in out


class TestEmptiness:
    def test_a_fresh_pad_declares_itself_empty(self) -> None:
        # ⚠️ L'invariant qui compte : un canvas neuf rend un PNG
        # parfaitement valide — un rectangle blanc — et le publier ferait
        # passer « pas encore signé » pour « signé ».
        out = _html()
        assert 'data-empty="true"' in out
        assert 'value=""' in out

    def test_an_existing_signature_is_not_empty(self) -> None:
        out = _html(value="data:image/png;base64,AAA")
        assert 'data-empty="false"' in out
        assert "data:image/png;base64,AAA" in out

    def test_the_scope_declares_its_base_layer(self) -> None:
        # ``_base`` porte la signature DÉJÀ LÀ, chargée à l'hydratation
        # et peinte sous les traits neufs. Déclarée dans le bz-data et
        # pas posée à la volée : un champ non déclaré devient un signal
        # à sa première écriture, donc l'assigner depuis le ``onload``
        # de l'image réveillerait les effets du scope pour rien.
        #
        # Ce que ce test NE prouve pas : que l'image est peinte. Aucun
        # test SSR ne le peut — le HTML était parfaitement correct quand
        # le cadre s'affichait vide. C'est
        # ``tests/runtime_js/test_signature_pad_repaints_existing.py``
        # qui compte les pixels.
        assert "_base: null" in _html()


class TestDisabled:
    def test_disabled_locks_the_canvas_and_says_so(self) -> None:
        out = _html(disabled=True)
        assert "data-bz-pad-locked" in out
        assert 'data-locked="true"' in out
        # Aucun geste câblé : le runtime n'a même pas à se garder.
        assert "bz-on:pointerdown" not in out

    def test_disabled_takes_the_carrier_out_of_the_form(self) -> None:
        # Un champ désactivé ne doit pas être soumis — sinon un pad
        # verrouillé réécrirait la signature à chaque envoi.
        assert "disabled" in _html(disabled=True).split("<input")[1]


class TestCarrier:
    def test_no_name_without_a_binding_or_an_explicit_one(self) -> None:
        # Coller un ``name`` par défaut injecterait un champ parasite
        # dans chaque formulaire englobant.
        assert "name=" not in _html().split("<input")[1].split(">")[0]

    def test_autoname_derives_from_a_server_state_field(self) -> None:
        # LE cas du composant : la valeur vit dans un ServerState, et
        # ``_hydrate_state`` la réécrit à la soumission.
        out = _html(value=_BoundStr("", "signature"))
        assert 'name="signature"' in out

    def test_explicit_name_wins(self) -> None:
        assert 'name="paraphe"' in _html(
            value=_BoundStr("", "signature"), name="paraphe"
        )

    def test_change_handler_is_relocated_onto_the_carrier(self) -> None:
        out = _html(on_change=_change_handler)
        # Un <div> ne porte pas de ``change`` natif : le bundle serveur
        # descend sur l'input caché, dont la FormData est non vide.
        assert "hx-post" in out
        assert "hx-post" not in out.split("<input")[0]


class TestBinding:
    def test_bound_value_addresses_the_store_directly(self) -> None:
        with render_isolated(), rendering_scope():
            out = serialize(SignaturePad(value=Draft().sig).render())
        assert "$bz.state.Draft.default.sig" in out
        # En mode binding le scope ne stocke PAS de copie locale.
        assert "value: " not in out.split("bz-data=")[1].split("bz-init=")[0]

    def test_binding_on_a_non_bindable_prop_raises(self) -> None:
        with render_isolated(), rendering_scope():
            with pytest.raises(ComponentUsageError):
                SignaturePad(placeholder=Draft().sig)


class TestImperative:
    def test_clear_is_a_client_expression(self) -> None:
        with render_isolated():
            assert isinstance(SignaturePad().clear(), str)

    def test_root_listens_to_the_clear_command(self) -> None:
        assert "bz-on:bz-clear" in _html()

    def test_clear_always_dispatches_even_when_bound(self) -> None:
        # Vider n'est pas « écrire la chaîne vide » : il faut aussi
        # jeter les points et repeindre, et seul le runtime sait le
        # faire.
        with render_isolated(), rendering_scope():
            pad = SignaturePad(value=Draft().sig)
            assert "bz-clear" in pad.clear()


class TestA11y:
    def test_the_canvas_is_hidden_from_assistive_tech(self) -> None:
        # Ce qui est annoncé et atteignable au clavier, c'est l'input
        # caché et le bouton — pas la surface de dessin. Déclarer un
        # rôle sur un canvas annoncerait un contrôle qu'aucune touche ne
        # pilote.
        canvas = _html().split("<canvas")[1].split(">")[0]
        assert 'aria-hidden="true"' in canvas


class TestTheme:
    @pytest.mark.parametrize("size", ["xs", "sm", "md", "lg", "xl"])
    def test_every_size_reaches_the_frame(self, size: str) -> None:
        assert SIGNATURE_PAD_THEME["sizes"][size]["pad"] in _html(size=size)

    def test_two_sizes_render_differently(self) -> None:
        assert _html(size="xs") != _html(size="xl")

    def test_color_lands_on_the_focused_frame(self) -> None:
        assert "focus-within:border-(--bz-border-hover)" in _html(color="success")
        assert "bz-c-success" in _html(color="success")

    def test_the_ink_colour_is_a_theme_token_not_a_prop(self) -> None:
        # Le runtime LIT ``getComputedStyle(canvas).color`` — donc la
        # classe doit être là, et il n'existe aucun ``pen_color=``.
        assert "text-text" in _html().split("<canvas")[1].split(">")[0]
