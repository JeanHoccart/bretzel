"""Gate — une barre ``sticky`` refuse les placements qui la cassent.

Le finding [16] du CRM : ``ui.bottom_bar`` est ``sticky``, donc son
accrochage depend de qui la contient. Le modele « document gele »
(``ui.viewport`` + ``ui.pane``, livre le 2026-08-23) change qui la
contient — et deux placements naturels rendent alors une page qui a
l'air construite. Mesures du 2026-08-24, Chromium 375x667 :

===============================  =========================================
placement                        ce qu'il rend
===============================  =========================================
hors du ``ui.viewport``          barre a **y = 0**, recouverte par le cadre
dans un cadre en RANGEE          le ``ui.pane`` voisin tombe a **0 px**
===============================  =========================================

Le second est le plus traitre : c'est la barre qui a l'air correcte, et
c'est le contenu de la page qui disparait.

Pourquoi la question se pose a l'ARBRE
---------------------------------------
Une premiere version jugeait la barre a sa CONSTRUCTION, sur
``parent_stack``. Elle tenait les deux cas ci-dessus et en laissait
passer deux autres, tous deux mesures casses au navigateur le meme jour :

- **une barre ecrite AVANT le cadre** ne peut pas savoir qu'un cadre va
  venir — et pour une navbar, « la barre du haut d'abord » est l'ordre
  naturel. Mesure : la navbar recouvre les 57 premiers pixels du cadre,
  en permanence ;
- **une barre enveloppee** dans un ``ui.fragment`` ou une zone
  ``@refreshable`` n'a pas son vrai parent de DISPOSITION sur
  ``parent_stack`` : l'enveloppe est transparente au CSS et opaque a la
  pile. Mesure : ``ui.pane`` a 0 px, exactement comme sans enveloppe.

D'ou ``base/_wiring.check_sticky_bar_placement``, appelee par
``render/pipeline._drain`` quand l'arbre est complet. Les cinq
compositions fautives sont ici, et les quatre licites avec elles — c'est
le versant qui compte le plus : une garde trop large condamnerait la
forme la plus courte de la coque mobile, ou toute page ecrite dans une
coque, et rien ne le dirait.

⚠️ **Le cas de l'outlet ne se simule pas.** Le pipeline execute le
layout jusqu'au bout puis retrouve l'outlet dans l'arbre bati. Un banc
qui monterait la page dans le corps du layout ne reproduirait pas ce
timing (memory ``gate_harness_must_match_render_timing``), d'ou le vrai
aller-retour HTTP.

Versant navigateur : ``tests/probes/probe_bottom_bar_placement.py``.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from starlette.testclient import TestClient

from bretzel import Bretzel, layout, page, ui

MUTATION_PROOF = "test_the_guard_catches_a_broken_placement"


def _app() -> Bretzel:
    return Bretzel(secret_key="gate-frozen-frame-secret-key", mode="dev")


def _tabs() -> None:
    with ui.bottom_bar():
        ui.bottom_bar_item("Home", icon="home", href="/")


# ── Les compositions LICITES ───────────────────────────────────────────

def _in_the_pane() -> None:
    """La composition d'``examples/crm`` : dernier enfant de la region."""
    with ui.viewport(direction="col"):
        with ui.pane():
            ui.text("contenu")
            _tabs()


def _sibling_of_the_pane() -> None:
    """Enfant direct du cadre. La forme la plus courte d'une coque mobile."""
    with ui.viewport(direction="col"):
        with ui.pane():
            ui.text("contenu")
        _tabs()


def _no_frame_at_all() -> None:
    """Le modele par DEFAUT — le document defile. Dix apps sur dix-huit."""
    with ui.vstack():
        ui.text("contenu")
        _tabs()


def _graded_but_never_a_row() -> None:
    """``direction`` graduee dont aucun cran n'est une rangee."""
    with ui.viewport(direction={"base": "col", "md": "col-reverse"}):
        with ui.pane():
            ui.text("contenu")
        _tabs()


# ── Les compositions FAUTIVES ──────────────────────────────────────────

def _outside_the_frame() -> None:
    with ui.viewport(direction="col"):
        with ui.pane():
            ui.text("contenu")
    _tabs()


def _child_of_a_row() -> None:
    with ui.viewport():          # ``row`` par defaut
        with ui.pane():
            ui.text("contenu")
        _tabs()


def _written_before_the_frame() -> None:
    """Le cas qu'une garde a la construction ne peut PAS voir."""
    with ui.navbar(sticky=True):
        ui.navbar_item("Home", href="/")
    with ui.viewport():
        with ui.pane():
            ui.text("contenu")


def _wrapped_in_a_transparent_parent() -> None:
    """Le cas ou ``parent_stack`` donne l'enveloppe, pas le parent CSS."""
    with ui.viewport():          # ``row``
        with ui.pane():
            ui.text("contenu")
        with ui.fragment():
            _tabs()


def _graded_into_a_row() -> None:
    """Une rangee a partir de ``md`` reste une rangee."""
    with ui.viewport(direction={"base": "col", "md": "row"}):
        with ui.pane():
            ui.text("contenu")
        _tabs()


def _status(body) -> int:
    app = _app()
    app.include(page("/", title="banc")(body))
    with TestClient(app, raise_server_exceptions=False) as client:
        return client.get("/").status_code


LICIT = (
    ("dans le pane", _in_the_pane),
    ("frere du pane", _sibling_of_the_pane),
    ("aucun cadre", _no_frame_at_all),
    ("graduee, jamais une rangee", _graded_but_never_a_row),
)
BROKEN = (
    ("hors du cadre", _outside_the_frame),
    ("enfant direct d'une rangee", _child_of_a_row),
    ("ecrite avant le cadre", _written_before_the_frame),
    ("enveloppee dans un fragment", _wrapped_in_a_transparent_parent),
    ("graduee en rangee a md", _graded_into_a_row),
)


@pytest.mark.parametrize("name,body", LICIT, ids=[n for n, _ in LICIT])
def test_a_licit_placement_still_renders(name: str, body) -> None:
    assert _status(body) == 200, (
        f"la passe rougit sur « {name} », qui est mesure JUSTE au "
        f"navigateur (probe_bottom_bar_placement.py) — elle refuse trop"
    )


@pytest.mark.parametrize("name,body", BROKEN, ids=[n for n, _ in BROKEN])
def test_the_guard_catches_a_broken_placement(name: str, body) -> None:
    assert _status(body) == 500, (
        f"« {name} » se rend sans rien dire — c'est exactement le finding "
        f"[16] : la page a l'air construite et ne l'est pas"
    )


def test_the_message_names_the_line_that_wrote_the_bar() -> None:
    """La passe tourne dans le pipeline : sans ça, plus de site d'appel.

    C'est ce que le report du contrôle a coûté, et ce qui le rembourse.
    ``register_sticky_bar`` capture le premier cadre hors du framework au
    moment de la construction, là où la pile le porte encore.
    """
    app = _app()
    app.include(page("/", title="banc")(_outside_the_frame))
    with TestClient(app) as client:
        with pytest.raises(Exception) as caught:
            client.get("/")
    assert Path(__file__).name + ":" in str(caught.value), str(caught.value)


def test_a_page_written_inside_a_shell_is_not_condemned() -> None:
    """Le cas de l'outlet — la page et sa coque sont deux arbres cousus.

    Une page écrite dans une coque qui porte le cadre : au moment où elle
    s'exécute, la coque a fini et ses ``with`` sont refermés. C'est la
    couture faite par le pipeline qui rend la question répondable — et
    c'est pour ça que la passe attend l'arbre fini.
    """
    app = _app()

    @layout
    def shell() -> None:
        with ui.viewport(direction="col"):
            with ui.pane():
                ui.outlet()

    @page("/", title="banc", layout=shell)
    def body() -> None:
        ui.text("contenu")
        _tabs()

    app.include(body)
    with TestClient(app, raise_server_exceptions=False) as client:
        assert client.get("/").status_code == 200


def test_a_non_sticky_navbar_is_never_judged() -> None:
    """Une navbar ordinaire défile avec le document : rien à juger.

    Le versant licite qui délimite la passe par le HAUT — sans lui, la
    condition ``sticky`` pourrait disparaître du code sans rien rougir.
    """
    def body() -> None:
        with ui.viewport():
            with ui.pane():
                ui.text("contenu")
        with ui.navbar():
            ui.navbar_item("Home", href="/")

    assert _status(body) == 200
