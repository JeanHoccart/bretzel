"""Unit tests for the drag-and-drop family — ``Dropzone`` / ``Draggable``
/ ``drag_each``.

⚠️ **Ces tests n'existaient pas.** La famille a shippé le 2026-08-10 avec
trois suites ``tests/runtime_js/`` — donc du navigateur, donc **hors du
sous-ensemble rapide** qui sert de definition of done au dépôt. Sa
surface Python (structure du rendu, attributs de contrat, porteur, clé
implicite) n'était vérifiée que par les gates génériques. Trou trouvé à
l'audit de conformité du 2026-08-13 ; les quatre autres composants de la
même vague en avaient chacun une.

Ce qu'on fige ici, ce sont les **affirmations du contrat** — celles que
les docstrings des trois briques énoncent, et dont un lecteur déduit un
comportement : « omis ne veut pas dire n'importe quoi », « le porteur est
inconditionnel mais son ``name`` non », « ``disabled`` veut dire ne
s'attrape pas ».
"""

from __future__ import annotations

import re

import pytest

from bretzel.components.base.attrs import ComponentUsageError
from bretzel.components.base.testing import render_isolated
from bretzel.components.layout.draggable import Draggable
from bretzel.components.layout.dropzone import Dropzone
from bretzel.components.layout.dropzone.move import MOVE_WIRE_FIELD
from bretzel.components.meta.iteration.drag_each import drag_each
from bretzel.components.meta.iteration.each import each
from bretzel.components.primitives.text import Text
from bretzel.core.serialize import serialize
from bretzel.render.iteration import _extract_key
from bretzel.state import field
from bretzel.state.scopes.client import ClientState, rendering_scope


# Handler module-level : ``encode_handler_id`` a besoin d'un qualname
# adressable, une lambda ne passe pas.
def _move_handler() -> None:
    pass


class _Prefs(ClientState):
    flag: bool = field(default=False)


def _html(build) -> str:
    """Construire ET rendre dans le MÊME contexte isolé.

    Prend une FABRIQUE, pas une instance : construire hors du contexte
    lève ``No render context is active`` — la construction d'un composant
    en a autant besoin que son rendu.
    """
    with render_isolated():
        return serialize(build().render())


class TestDropzoneContract:
    def test_zone_name_lands_on_the_data_attribute(self) -> None:
        out = _html(lambda: Dropzone(name="todo"))
        assert 'data-bz-dropzone="todo"' in out

    def test_nameless_zone_falls_back_to_its_stable_id(self) -> None:
        """Le docstring de ``_needs_identity`` en fait un invariant : une
        zone anonyme reste NOMMABLE, sinon deux zones anonymes rendent
        ``from_zone`` ambigu et tout « retire-le de la source » vise la
        mauvaise liste."""
        out = _html(Dropzone)
        assert 'data-bz-dropzone=""' not in out, (
            "une zone sans name= doit retomber sur son id, pas sortir "
            "avec une identité vide"
        )
        assert "data-bz-dropzone=" in out and 'id="' in out

    def test_accepts_is_comma_joined(self) -> None:
        out = _html(lambda: Dropzone(name="a", accepts=["task", "note"]))
        assert 'data-bz-accepts="task,note"' in out

    def test_omitted_accepts_emits_no_attribute(self) -> None:
        """« Omis ne veut PAS dire n'importe quoi » — le défaut est « mes
        propres items », et c'est l'ABSENCE de l'attribut qui l'encode.
        Émettre ``data-bz-accepts=""`` dirait « n'accepte rien »."""
        assert "data-bz-accepts" not in _html(lambda: Dropzone(name="a"))

    def test_accepts_survives_a_second_render(self) -> None:
        """``accepts=`` peut légitimement être un générateur, et un
        ``@refreshable`` re-rend la MÊME instance : sans la
        matérialisation au construct, la deuxième passe rendrait une
        liste vide en silence."""
        with render_isolated():
            zone = Dropzone(name="a", accepts=(g for g in ("task", "note")))
            first = serialize(zone.render())
            second = serialize(zone.render())
        assert 'data-bz-accepts="task,note"' in first
        assert 'data-bz-accepts="task,note"' in second

    def test_locked_is_emitted_only_when_set(self) -> None:
        with render_isolated():
            assert "data-bz-locked" not in serialize(Dropzone(name="a").render())
            assert 'data-bz-locked="true"' in serialize(
                Dropzone(name="a", locked=True).render()
            )

    def test_carrier_is_unconditional_but_its_name_is_not(self) -> None:
        """Les deux moitiés d'un même arbitrage, donc un seul rendu.

        Le porteur est INCONDITIONNEL — c'est ce que le runtime écrit et
        ce depuis quoi il dispatche ``move`` ; le rendre seulement pour
        le cas serveur ferait d'un ``on_move="…"`` client une lettre
        morte. Son ``name``, lui, ne l'est pas : un nom permanent
        injecterait ``bz_move=`` dans CHAQUE formulaire englobant.
        """
        out = _html(lambda: Dropzone(name="a"))
        assert 'data-bz-move-carrier="true"' in out, "le porteur est inconditionnel"
        assert f'name="{MOVE_WIRE_FIELD}"' not in out, (
            "sans handler serveur, le porteur ne doit pas être nommé — "
            "il polluerait le formulaire englobant"
        )

    def test_server_handler_moves_onto_the_carrier(self) -> None:
        """HTMX doit poster depuis l'élément qui PORTE la charge, sinon le
        blob que le runtime vient d'écrire n'est pas sérialisé."""
        out = _html(lambda: Dropzone(name="a", on_move=_move_handler))
        assert f'name="{MOVE_WIRE_FIELD}"' in out
        root, _, carrier = out.partition("<input")
        assert "hx-post" not in root, (
            "le handler doit être relocalisé sur le porteur, pas rester "
            "sur la racine"
        )
        assert "hx-post" in carrier

    def test_root_slot_override_lands(self) -> None:
        """Régression de l'audit de conformité du 2026-08-10 : un lookup
        ``theme["slots"][…]`` à la main droppait ce override EN SILENCE."""
        out = _html(lambda: Dropzone(name="a", slots={"root": "MARKER-ROOT"}))
        assert out.count("MARKER-ROOT") == 1

    def test_binding_on_a_non_bindable_prop_raises(self) -> None:
        """``BINDABLE_PROPS = ()`` : une zone ne détient aucune valeur
        pilotable côté client, et le refus doit être bruyant — un binding
        accepté puis ignoré rendrait une zone qui ne se verrouille
        jamais."""
        with render_isolated(), rendering_scope():
            with pytest.raises(ComponentUsageError):
                Dropzone(name="a", locked=_Prefs().flag)


class TestDraggableContract:
    def test_marks_itself_and_reports_its_key(self) -> None:
        out = _html(lambda: Draggable(key="k1"))
        assert 'data-bz-draggable="true"' in out
        assert 'data-bz-key="k1"' in out

    def test_key_falls_back_to_the_iteration_key(self) -> None:
        """C'est ce qui rend ``key=`` optionnel — le mécanisme que tous
        les composants à état client consultent déjà."""
        with render_isolated():
            rendered = []
            for item in each([{"id": "a"}, {"id": "b"}]):
                rendered.append(serialize(Draggable().render()))
        assert 'data-bz-key="a"' in rendered[0]
        assert 'data-bz-key="b"' in rendered[1]

    def test_explicit_key_beats_the_iteration_key(self) -> None:
        with render_isolated():
            for _ in each([{"id": "a"}]):
                out = serialize(Draggable(key="mine").render())
        assert 'data-bz-key="mine"' in out

    def test_group_is_emitted_only_when_set(self) -> None:
        assert "data-bz-group" not in _html(lambda: Draggable(key="k"))
        assert 'data-bz-group="task"' in _html(lambda: Draggable(key="k", group="task"))

    def test_disabled_is_announced_to_assistive_tech(self) -> None:
        """``data-bz-disabled`` pilote le runtime et ne dit RIEN à un
        lecteur d'écran : la racine est un ``<div>``. Écart n°3 de l'audit
        du 2026-08-10 — la carte verrouillée se présentait comme une
        carte ordinaire."""
        out = _html(lambda: Draggable(key="k", disabled=True))
        assert 'data-bz-disabled="true"' in out
        assert 'aria-disabled="true"' in out

    def test_handle_renders_a_labelled_grip(self) -> None:
        out = _html(lambda: Draggable(key="k", handle=True))
        assert 'data-bz-handle="true"' in out
        assert 'data-bz-drag-handle="true"' in out
        assert 'role="button"' in out and 'tabindex="0"' in out
        assert 'aria-label="Drag to reorder"' in out

    def test_disabled_handle_renders_no_grip(self) -> None:
        """Une poignée qu'on ne peut pas saisir est une affordance qui
        ment."""
        out = _html(lambda: Draggable(key="k", handle=True, disabled=True))
        assert "data-bz-drag-handle" not in out

    def test_grab_surface_switches_with_the_handle(self) -> None:
        """``touch-action: none`` migre de la carte vers le grip — c'est ce
        qui garde la carte scrollable au doigt quand une poignée existe."""
        from bretzel.components.layout.draggable.theme import DRAGGABLE_THEME

        slots = DRAGGABLE_THEME["slots"]
        assert slots["grab_all"] in _html(lambda: Draggable(key="k"))
        assert slots["with_handle"] in _html(lambda: Draggable(key="k", handle=True))

    def test_root_slot_override_lands(self) -> None:
        out = _html(lambda: Draggable(key="k", slots={"root": "MARKER-ROOT"}))
        assert out.count("MARKER-ROOT") == 1


class TestDragEach:
    def test_group_propagates_to_every_wrapper(self) -> None:
        with render_isolated():
            with Dropzone(name="todo") as zone:
                for item in drag_each(["a", "b"], group="task"):
                    Text(str(item))
            out = serialize(zone.render())
        assert out.count('data-bz-draggable="true"') == 2
        assert out.count('data-bz-group="task"') == 2

    def test_the_keys_are_the_ones_each_would_have_given(self) -> None:
        """Le docstring promet « exactement comme ``ui.each`` ». On fige
        cette ÉGALITÉ plutôt que les chaînes : pour un primitif hashable,
        la cascade de ``_extract_key`` rend un ``hash()``, et épingler la
        valeur ferait rougir un refactor correct."""
        items = ["a", "b"]
        expected = [_extract_key(item, None, i) for i, item in enumerate(items)]
        with render_isolated():
            with Dropzone(name="todo") as zone:
                for item in drag_each(items):
                    Text(str(item))
            out = serialize(zone.render())
        assert re.findall(r'data-bz-key="([^"]*)"', out) == expected
        assert len(set(expected)) == len(items), "les clés doivent être distinctes"

    def test_disabled_is_a_per_item_predicate(self) -> None:
        """Pas un drapeau de liste : ce qui est déplaçable est une
        propriété de la LIGNE."""
        with render_isolated():
            with Dropzone(name="todo") as zone:
                for item in drag_each(
                    ["a", "b"], disabled=lambda i: i == "b"
                ):
                    Text(str(item))
            out = serialize(zone.render())
        assert out.count('data-bz-disabled="true"') == 1

    def test_the_body_lands_inside_the_wrapper(self) -> None:
        with render_isolated():
            with Dropzone(name="todo") as zone:
                for _ in drag_each(["a"]):
                    Text("inside")
            out = serialize(zone.render())
        wrapper = out.index('data-bz-draggable="true"')
        assert out.index("inside") > wrapper

    def test_the_key_stack_is_restored_after_the_loop(self) -> None:
        """Un ``finally`` le promet ; sans lui une clé fuiterait sur le
        composant suivant de la page."""
        from bretzel.render.iteration import _KEY_STACK

        with render_isolated():
            before = _KEY_STACK.get()
            with Dropzone(name="todo"):
                for item in drag_each(["a", "b"]):
                    Text(str(item))
            assert _KEY_STACK.get() == before
