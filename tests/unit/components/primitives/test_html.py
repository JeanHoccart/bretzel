"""``Html`` — le contenu sort verbatim, et le constructeur refuse deux choses.

Le contrat, pas la chaîne : on n'épingle pas la classe marqueur ailleurs
que là où elle EST le contrat (le sélecteur d'ancrage de l'audit).
"""

from __future__ import annotations

import pytest

from bretzel.components.base import ComponentUsageError
from bretzel.components.base.testing import render_isolated
from bretzel.components.primitives.html.html import Html
from bretzel.core.serialize import serialize
from bretzel.state import ClientState, field
from bretzel.state.scopes.client import rendering_scope


class HtmlState(ClientState, persist="memory"):
    """Un état client, pour fabriquer une vraie ``ClientBinding``."""

    source: str = field(default="<b>x</b>")


def render(*args, **kwargs) -> str:
    with render_isolated():
        return serialize(Html(*args, **kwargs).render())


class TestVerbatim:
    def test_markup_is_not_escaped(self) -> None:
        """La raison d'être du composant. Si ça casse, il ne sert plus."""
        out = render("<b>gras</b>")
        assert "<b>gras</b>" in out
        assert "&lt;b&gt;" not in out

    def test_a_script_tag_would_reach_the_page_verbatim(self) -> None:
        """Le danger, figé explicitement plutôt que laissé implicite.

        Ce test ne réclame pas un changement : il DOCUMENTE que rien
        n'assainit. Le jour où quelqu'un ajoute un filtre « pour la
        sécurité », il rougira — et ce sera la bonne conversation, parce
        qu'un assainissement à moitié fait est pire que pas
        d'assainissement (il donne confiance sans garantir)."""
        out = render("<script>x=1</script>")
        assert "<script>x=1</script>" in out

    def test_attributes_inside_the_content_survive(self) -> None:
        out = render("<iframe title='Carte' srcdoc='<p>hi</p>'></iframe>")
        assert "srcdoc='<p>hi</p>'" in out

    def test_empty_content_still_renders_the_wrapper(self) -> None:
        """Les kwargs universels ont besoin d'un porteur, même sans
        contenu — sinon ``id=`` / ``classes=`` tomberaient dans le vide."""
        out = render("", id="mine")
        assert 'id="mine"' in out

    def test_none_content_is_treated_as_empty(self) -> None:
        assert render() == render("")


class TestWrapper:
    def test_default_tag_is_a_div(self) -> None:
        assert render("<b>x</b>").startswith("<div ")

    def test_tag_kwarg_changes_the_wrapper(self) -> None:
        assert render("<b>x</b>", tag="span").startswith("<span ")

    def test_marker_class_is_present(self) -> None:
        """``bz-html`` est le contrat : c'est la prise CSS de l'app ET le
        sélecteur d'ancrage de l'audit navigateur (`checklist.py`)."""
        assert "bz-html" in render("<b>x</b>")

    def test_user_classes_join_the_marker(self) -> None:
        out = render("<b>x</b>", classes="text-sm")
        assert "bz-html" in out and "text-sm" in out


class TestConstructorRefusals:
    def test_client_binding_raises(self) -> None:
        """Décision de SÉCURITÉ : un binding ferait écrire du balisage au
        runtime depuis l'état client."""
        with render_isolated(), rendering_scope():
            state = HtmlState()
            with pytest.raises(ComponentUsageError, match="ClientBinding"):
                Html(state.source)

    def test_component_raises(self) -> None:
        """``content`` est une string de balisage, pas un slot — un
        Component y serait stringifié en son repr Python."""
        from bretzel.components.primitives.text import Text

        with render_isolated(), pytest.raises(ComponentUsageError,
                                             match="Component"):
            Html(Text("salut"))

    def test_the_refusal_names_the_alternative(self) -> None:
        """Un message qui dit « non » sans dire « fais plutôt ceci »
        oblige à relire la source du framework."""
        with render_isolated(), rendering_scope():
            state = HtmlState()
            with pytest.raises(ComponentUsageError) as exc:
                Html(state.source)
        assert "PageState" in str(exc.value)
