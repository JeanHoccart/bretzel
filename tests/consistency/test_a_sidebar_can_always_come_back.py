"""Gate — une barre laterale qui peut disparaitre doit pouvoir revenir.

Le finding [17] du CRM. En ``collapsible="overlay"`` ou ``"offcanvas"``,
la barre quitte l'ecran — et elle emporte avec elle **toutes** les
affordances qu'elle rend : le bouton de son ``sidebar_title`` comme son
arete de repli vivent DANS l'``<aside>``. Le moyen de la faire revenir ne
peut donc etre que dehors.

Mesure du 2026-08-24, banc neuf en 375x667, sans declencheur :

===========================  ==========================================
``<aside>``                  **x = -256** (entierement hors ecran)
elements cliquables a l'ecran  **zero**
reponse HTTP                 **200**, rien de journalise
===========================  ==========================================

C'est ce qui avait rendu **six des onze routes** d'``examples/crm``
injoignables sur telephone, sans qu'aucun test ne bronche.

Ce que cette gate ne dit PAS
-----------------------------
Elle ne reproche pas au composant de ne pas rendre son propre bouton de
retour : ce chevron flottant a existe et a ete **retire le 2026-08-21**,
parce que « c'etait le composant qui decidait de la place d'une
affordance de l'app ». La decision tient. Ce qui manquait apres elle,
c'etait une piece a POSER — d'ou ``ui.sidebar_trigger``.

Les trois formes licites sont donc les trois facons d'etre atteignable,
et la quatrieme colonne du tableau ci-dessous est celle qui compte le
plus : le mode ``rail`` n'est jamais juge, parce qu'une barre qui laisse
une bande d'icones porte son propre retour.

Versant navigateur : ``tests/probes/probe_sidebar_trigger.py`` — le seul
instrument qui dise que le bouton OUVRE vraiment la barre.
"""

from __future__ import annotations

import pytest
from starlette.testclient import TestClient

from bretzel import Bretzel, page, ui
from bretzel.state import ClientState, field

MUTATION_PROOF = "test_an_unreachable_sidebar_is_refused"


def _app() -> Bretzel:
    return Bretzel(secret_key="gate-sidebar-reach-secret-key", mode="dev")


def _items() -> None:
    ui.sidebar_item("Accueil", icon="home", href="/")


# ── Atteignables ───────────────────────────────────────────────────────

def _with_a_trigger() -> None:
    """Tier 1 : le declencheur trouve la barre tout seul."""
    with ui.viewport():
        with ui.sidebar(collapsible="overlay", open=False):
            _items()
        with ui.pane():
            ui.sidebar_trigger()


def _with_a_trigger_written_first() -> None:
    """La barre du haut d'abord — l'ordre naturel d'une coque."""
    with ui.viewport():
        with ui.pane():
            ui.sidebar_trigger()
        with ui.sidebar(collapsible="overlay", open=False):
            _items()


def _with_a_hand_rolled_button() -> None:
    """Tier 2 : l'echappatoire, qui doit rester entiere."""
    with ui.viewport():
        sidebar = ui.sidebar(collapsible="offcanvas", open=False)
        with sidebar:
            _items()
        with ui.pane():
            ui.icon_button("menu", on_click=sidebar.toggle(), tooltip="Menu")


class Menu(ClientState):
    open: bool = field(default=False)


def _driven_by_client_state() -> None:
    """L'app tient l'etat : on ne peut pas savoir d'ou elle le leve."""
    with ui.viewport():
        with ui.sidebar(collapsible="overlay", open=Menu().open):
            _items()
        with ui.pane():
            ui.text("contenu")


def _a_rail_needs_nothing() -> None:
    """Repliee, une barre ``rail`` laisse une bande d'icones : elle revient."""
    with ui.viewport():
        with ui.sidebar(collapsible="rail", open=False):
            _items()
        with ui.pane():
            ui.text("contenu")


# ── Injoignables ───────────────────────────────────────────────────────

def _overlay_with_nothing() -> None:
    with ui.viewport():
        with ui.sidebar(collapsible="overlay", open=False):
            _items()
        with ui.pane():
            ui.text("contenu")


def _offcanvas_with_nothing() -> None:
    with ui.viewport():
        with ui.sidebar(collapsible="offcanvas", open=False):
            _items()
        with ui.pane():
            ui.text("contenu")


def _a_title_is_not_a_way_back() -> None:
    """Le bouton du titre part AVEC la barre — c'est tout le finding."""
    with ui.viewport():
        with ui.sidebar(collapsible="overlay", open=False):
            ui.sidebar_title("App", icon="zap")
            _items()
        with ui.pane():
            ui.text("contenu")


def _open_is_not_a_way_back() -> None:
    """Ouverte au depart, mais refermable par Escape ou par le fond."""
    with ui.viewport():
        with ui.sidebar(collapsible="overlay", open=True):
            _items()
        with ui.pane():
            ui.text("contenu")


def _status(body) -> int:
    app = _app()
    app.include(page("/", title="banc")(body))
    with TestClient(app, raise_server_exceptions=False) as client:
        return client.get("/").status_code


REACHABLE = (
    ("un declencheur", _with_a_trigger),
    ("un declencheur ecrit avant la barre", _with_a_trigger_written_first),
    ("un bouton maison (tier 2)", _with_a_hand_rolled_button),
    ("open= pilote par l'app", _driven_by_client_state),
    ("le mode rail", _a_rail_needs_nothing),
)
UNREACHABLE = (
    ("overlay sans rien", _overlay_with_nothing),
    ("offcanvas sans rien", _offcanvas_with_nothing),
    ("un titre ne suffit pas", _a_title_is_not_a_way_back),
    ("ouverte au depart ne suffit pas", _open_is_not_a_way_back),
)


@pytest.mark.parametrize(
    "name,body", REACHABLE, ids=[n for n, _ in REACHABLE]
)
def test_a_reachable_sidebar_still_renders(name: str, body) -> None:
    assert _status(body) == 200, (
        f"la garde rougit sur « {name} », qui est une facon LICITE "
        f"d'atteindre la barre — elle refuse trop"
    )


@pytest.mark.parametrize(
    "name,body", UNREACHABLE, ids=[n for n, _ in UNREACHABLE]
)
def test_an_unreachable_sidebar_is_refused(name: str, body) -> None:
    assert _status(body) == 500, (
        f"« {name} » rend une navigation qu'on ne peut plus atteindre, "
        f"sans rien dire — mesure : aside a x=-256, zero element "
        f"cliquable a l'ecran, page a 200"
    )


def test_the_message_names_the_gesture_to_write() -> None:
    """Un refus qui ne dit pas quoi ecrire fait perdre le temps qu'il gagne."""
    app = _app()
    app.include(page("/", title="banc")(_overlay_with_nothing))
    with TestClient(app) as client:
        with pytest.raises(Exception) as caught:
            client.get("/")
    message = str(caught.value)
    assert "ui.sidebar_trigger()" in message
    assert "sb.toggle()" in message


def test_a_trigger_cannot_guess_between_two_sidebars() -> None:
    """Deviner ferait un bouton qui a l'air de marcher et ouvre l'autre."""
    def body() -> None:
        with ui.viewport():
            with ui.sidebar(collapsible="rail"):
                _items()
            with ui.sidebar(collapsible="rail"):
                _items()
            with ui.pane():
                ui.sidebar_trigger()

    assert _status(body) == 500


def test_two_sidebars_are_fine_when_the_trigger_is_told_which() -> None:
    """Le versant licite du refus ci-dessus — sinon il condamnerait la page."""
    def body() -> None:
        with ui.viewport():
            first = ui.sidebar(collapsible="overlay", open=False)
            with first:
                _items()
            with ui.sidebar(collapsible="rail"):
                _items()
            with ui.pane():
                ui.sidebar_trigger(first)

    assert _status(body) == 200
