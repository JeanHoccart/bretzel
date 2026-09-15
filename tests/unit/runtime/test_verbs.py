"""Unit tests for :mod:`bretzel.runtime.verbs` — les verbes clients."""

from __future__ import annotations

import pytest

from bretzel.runtime.verbs import (
    copy,
    fullscreen,
    print_page,
    share,
    vibrate,
)
from bretzel.state import ClientState, field
from bretzel.state.scopes.client import _RENDERING


@pytest.fixture
def rendering():
    """Le contexte où un champ d'état rend un ``ClientBinding``.

    ⚠️ Sans lui, ``C().api_key`` rend la VALEUR (une ``str`` vide) et pas
    le binding — c'est le contrat de ``ClientState.__getattribute__``, et
    c'est ce qui m'a fait croire une première fois que ``copy`` ne
    résolvait pas les états liés. Le test était faux, pas le code.
    """
    token = _RENDERING.set(True)
    try:
        yield
    finally:
        _RENDERING.reset(token)


class Secrets(ClientState):
    api_key: str = field(default="")


class TestCopy:
    def test_a_literal_travels_as_a_js_literal(self) -> None:
        assert copy("bretzel") == '$bz.verbs.copy("bretzel")'

    def test_a_quote_cannot_break_out_of_the_expression(self) -> None:
        """Un guillemet dans la valeur ne sort pas de l'expression JS.

        ⚠️ Ce test a d'abord exigé que ``</script>`` soit neutralisé
        aussi. **Il avait tort**, et le dire vaut mieux que de le
        supprimer : ``json.dumps`` ne le touche pas, et il n'a pas à le
        faire. Un verbe est interpolé dans un ATTRIBUT
        (``bz-on:click="…"``), jamais dans un ``<script>`` — le
        sérialiseur y échappe ``<``, ``>`` et ``"``, donc rien ne peut
        fermer une balise qui n'existe pas. La seule sortie possible est
        celle du littéral JS, et c'est elle qu'on ferme ici.

        Le jour où une source client atterrirait vraiment dans un
        ``<script>``, c'est ``core.escape.escape_inline_json`` qu'il
        faudrait, comme pour l'``<bz-envelope>``.
        """
        assert copy('a"b') == '$bz.verbs.copy("a\\"b")'
        assert copy("l'apostrophe") == "$bz.verbs.copy(\"l'apostrophe\")"

    def test_a_bound_field_travels_as_its_PATH(self, rendering) -> None:
        # Le point du verbe : copier une valeur que le SERVEUR ne connaît
        # pas. Un littéral figerait ce que valait le champ au rendu.
        assert copy(Secrets().api_key) == (
            "$bz.verbs.copy($bz.state.Secrets.default.api_key)"
        )

    def test_a_non_string_is_still_valid_js(self) -> None:
        assert copy(42) == "$bz.verbs.copy(42)"
        assert copy(None) == "$bz.verbs.copy(null)"


class TestPrintPage:
    def test_it_is_the_native_dialog(self) -> None:
        assert print_page() == "window.print()"


class TestFullscreen:
    def test_no_target_means_the_document(self) -> None:
        assert "document.documentElement.requestFullscreen" in fullscreen()

    def test_a_target_is_found_by_its_id(self) -> None:
        class Fake:
            id = "dashboard"

        assert 'document.getElementById("dashboard")' in fullscreen(Fake())

    def test_a_missing_feature_does_not_throw(self) -> None:
        # Un verbe s'évalue dans un ``on_*=``, où personne n'attrape. Une
        # exception y remonterait en erreur console non gérée.
        js = fullscreen()
        assert ".requestFullscreen &&" in js      # absence
        assert ".catch(" in js                    # refus de l'utilisateur

    def test_a_target_without_an_id_is_REFUSED(self) -> None:
        # Silencieux sinon : ``getElementById(null)`` rend ``null`` et le
        # clic ne ferait rien, sans un mot.
        class Anonyme:
            id = None

        with pytest.raises(ValueError, match="id"):
            fullscreen(Anonyme())


class TestShare:
    def test_no_argument_means_the_current_page(self) -> None:
        """Le défaut n'est pas de la commodité.

        Depuis que l'état s'écrit dans l'adresse (``addressable=True``),
        l'URL courante PORTE la vue — filtres, onglet, page. Partager la
        page, c'est partager ce qu'on regarde. Le JS pose
        ``location.href`` quand ``url`` manque, donc Python n'envoie
        rien.
        """
        assert share() == "$bz.verbs.share({})"

    def test_the_named_parts_travel(self) -> None:
        js = share("https://x.test/v?f=1", title="Rapport")
        assert 'url: "https://x.test/v?f=1"' in js
        assert 'title: "Rapport"' in js

    def test_an_omitted_part_is_not_sent_as_null(self) -> None:
        # ``{title: null}`` ferait afficher un titre vide dans la feuille
        # native au lieu de laisser le navigateur choisir.
        assert "null" not in share("https://x.test/")

    def test_a_bound_value_travels_as_its_path(self, rendering) -> None:
        assert "$bz.state.Secrets.default.api_key" in share(
            Secrets().api_key
        )


class TestVibrate:
    def test_the_default_is_a_single_short_buzz(self) -> None:
        assert vibrate() == "$bz.verbs.vibrate(50)"

    def test_a_pattern_alternates_buzz_and_pause(self) -> None:
        assert vibrate([50, 30, 50]) == "$bz.verbs.vibrate([50, 30, 50])"


def test_the_five_verbs_are_reachable_from_the_package() -> None:
    """Un verbe qu'on ne peut pas importer n'existe pas.

    L'arbitrage du 2026-09-01 les met sur ``bretzel``, pas sur ``ui`` :
    ce qui FAIT quelque chose est sur ``bretzel``, ce qui EST quelque
    chose est sur ``ui``.
    """
    import bretzel

    for nom in ("copy", "print_page", "fullscreen", "share", "vibrate"):
        assert nom in bretzel.__all__, f"{nom} absent de bretzel.__all__"
        assert callable(getattr(bretzel, nom))
