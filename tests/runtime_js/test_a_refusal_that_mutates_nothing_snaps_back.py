"""Refuser un dépôt en ne mutant RIEN doit remettre la carte en place.

C'est la façon de refuser que ``Move`` documente — « there is no
``reject()`` to call and no exception to raise : a handler that does not
mutate leaves the server's next render disagreeing with the DOM, and the
morph puts the card back ». Cette phrase était fausse, et elle l'est
restée longtemps parce que la gate censée la prouver ne la prouvait pas.

Ce que la gate d'à côté ne pouvait pas voir
--------------------------------------------
``test_dnd_end_to_end.test_a_refused_move_snaps_back`` s'appuie sur le
banc du playground, dont le handler de refus fait
``state.refused = state.refused + 1`` avant de sortir. Un état change,
donc la zone se re-rend, donc le morph replace le nœud : le snap-back
venait du COMPTEUR, pas du refus. Sa docstring dit pourtant « refuses …
by mutating nothing ».

Un handler qui ne mute vraiment rien ne fait re-rendre aucune zone : le
serveur répond zéro octet, et la carte reste là où le doigt l'a lâchée.
Mesuré le 2026-09-09 sur ``examples/kanban`` — une limite d'en-cours
refusait côté serveur, et l'écran affichait quatre cartes dans une
colonne qui en accepte trois. ``examples/crm`` refuse de la même façon.

Les DEUX bras comptent
-----------------------
Un garde-fou qui défait TOUS les dépôts « répare » le refus en cassant
l'acceptation, et aucune mesure du seul versant interdit ne le verrait.
Le premier test tient donc le versant licite : un déplacement accepté
doit rester où il a atterri.

Lourd (uvicorn + Chromium) — à lancer explicitement ::

    py -m pytest tests/runtime_js/test_a_refusal_that_mutates_nothing_snaps_back.py -q -m browser
"""

from __future__ import annotations

import pytest

from bretzel import Bretzel, page, refreshable, ui
from bretzel.components import Move
from bretzel.state import SessionState, field
from tests.audit.harness import audit_server, browser_page

GROUPE = "carte"


class Bac(SessionState):
    """Les cartes de la colonne de gauche, dans leur ordre."""

    cartes: list[str] = field(
        default_factory=lambda: ["alpha", "beta", "gamma", "delta"])


def accepter(m: Move) -> None:
    """Le versant licite : réordonner dans la colonne de gauche."""
    bac = Bac()
    if m.to_zone != "gauche" or m.item_key not in bac.cartes:
        return
    restantes = [c for c in bac.cartes if c != m.item_key]
    place = max(0, min(m.to_index, len(restantes)))
    bac.cartes = [*restantes[:place], m.item_key, *restantes[place:]]


def refuser(m: Move) -> None:
    """Le versant interdit : refuser EN NE MUTANT RIEN.

    Pas de compteur, pas de notification, pas de journal — rien. C'est la
    forme minimale que la documentation présente comme LA façon de
    refuser, et c'est la seule qui mette le garde-fou sous contrainte.
    """


app = Bretzel(secret_key="r" * 32, title="Bretzel · refus sans mutation",
              mode="dev")


@refreshable(deps=[Bac])
def plateau() -> None:
    with ui.hstack(gap="lg", classes="p-6"):
        with ui.dropzone(name="gauche", accepts=[GROUPE], on_move=accepter,
                         classes="w-64 p-2 border border-text/20 "
                                 "rounded min-h-96"), ui.vstack(gap="sm"):
            for carte in ui.drag_each(Bac().cartes, group=GROUPE,
                                      key=lambda c: c):
                with ui.card(padding="sm"):
                    ui.text(carte)
        with ui.dropzone(name="droite", accepts=[GROUPE], on_move=refuser,
                         classes="w-64 p-2 border border-text/20 "
                                 "rounded min-h-96"), ui.vstack(gap="sm"):
            ui.text("cette zone refuse tout")


@page("/")
def home() -> None:
    plateau()


app.include(__name__)


@pytest.fixture(scope="module")
def base_url():
    with audit_server(app) as url:
        yield url


def cartes(page, zone: str) -> list[str]:
    return page.evaluate(
        """(zone) => [...document.querySelectorAll(
             `[data-bz-dropzone="${zone}"] [data-bz-draggable]`)]
           .map(e => e.innerText.trim())""",
        zone,
    )


def actions(page) -> list[str]:
    """Les POST d'action partis de la page, pour ancrer les planchers."""
    envoyes: list[str] = []
    page.on("request", lambda r: envoyes.append(r.url)
            if "/_bretzel/action/" in r.url else None)
    return envoyes


def glisser(page, depuis: tuple[str, int], vers: tuple[str, int | None]) -> None:
    """Glisser la carte ``depuis`` vers la zone ``vers``, à la vraie souris.

    ``vers[1]`` vise un item existant de la zone d'arrivée ; ``None`` vise
    le vide sous le dernier, ce qui est le seul geste possible vers une
    colonne qui n'a pas de carte.
    """
    boites = page.evaluate(
        """([dz, di, az, ai]) => {
             const item = (z, i) => [...document.querySelectorAll(
               `[data-bz-dropzone="${z}"] [data-bz-draggable]`)][i];
             const src = item(dz, di).getBoundingClientRect();
             let dst;
             if (ai === null) {
               const z = document.querySelector(
                 `[data-bz-dropzone="${az}"]`).getBoundingClientRect();
               dst = {x: z.left + z.width / 2, y: z.bottom - 30};
             } else {
               const r = item(az, ai).getBoundingClientRect();
               dst = {x: r.left + r.width / 2, y: r.bottom - 4};
             }
             return {x1: src.left + src.width / 2,
                     y1: src.top + src.height / 2, x2: dst.x, y2: dst.y};
           }""",
        [depuis[0], depuis[1], vers[0], vers[1]],
    )
    page.mouse.move(boites["x1"], boites["y1"])
    page.mouse.down()
    for fraction in (0.25, 0.6, 1.0):
        page.mouse.move(
            boites["x1"] + (boites["x2"] - boites["x1"]) * fraction,
            boites["y1"] + (boites["y2"] - boites["y1"]) * fraction,
            steps=8,
        )
    page.mouse.up()
    page.wait_for_timeout(1200)


@pytest.mark.browser
def test_the_bench_really_moves_a_card(base_url: str) -> None:
    """Plancher : sans un geste qui aboutit, les deux bras ne disent rien."""
    with browser_page(base_url, "/") as pg:
        pg.wait_for_selector("html.bz-ready")
        avant = cartes(pg, "gauche")
        assert len(avant) >= 3, f"le banc ne rend que {avant}"
        envoyes = actions(pg)
        glisser(pg, ("gauche", 0), ("gauche", 2))
        assert envoyes, "aucun POST d'action : le geste n'a pas abouti"


@pytest.mark.browser
def test_an_accepted_move_is_not_undone(base_url: str) -> None:
    """Le versant LICITE, et c'est lui qui coûte cher à casser.

    Un garde-fou qui défait tous les dépôts rendrait le second test vert
    sans rien réparer.
    """
    with browser_page(base_url, "/") as pg:
        pg.wait_for_selector("html.bz-ready")
        avant = cartes(pg, "gauche")
        glisser(pg, ("gauche", 0), ("gauche", 2))
        apres = cartes(pg, "gauche")
        assert apres != avant, (
            f"le déplacement accepté n'a rien changé : {avant} → {apres}")
        assert sorted(apres) == sorted(avant), (
            f"une carte a été perdue : {avant} → {apres}")
        assert apres[0] != avant[0], (
            "la carte prise en tête est revenue en tête — le garde-fou "
            f"a défait un dépôt ACCEPTÉ : {avant} → {apres}")

        # Et il tient au-delà du temps de pose du morph : le garde-fou
        # attend deux images avant de trancher, donc une mesure faite trop
        # tôt le raterait.
        pg.wait_for_timeout(900)
        assert cartes(pg, "gauche") == apres, (
            "le déplacement accepté a été défait après coup")


@pytest.mark.browser
def test_a_refusal_that_mutates_nothing_puts_the_card_back(
    base_url: str,
) -> None:
    """Le versant INTERDIT : le handler ne mute rien, la carte revient."""
    with browser_page(base_url, "/") as pg:
        pg.wait_for_selector("html.bz-ready")
        avant = cartes(pg, "gauche")
        envoyes = actions(pg)

        glisser(pg, ("gauche", 0), ("droite", None))

        assert envoyes, (
            "le dépôt refusé n'a posté aucune action — le test mesurerait "
            "un geste qui n'a jamais eu lieu")
        assert cartes(pg, "droite") == [], (
            f"la carte est restée dans la zone qui refuse : "
            f"{cartes(pg, 'droite')}")
        assert cartes(pg, "gauche") == avant, (
            f"la carte n'est pas revenue à sa place : {avant} → "
            f"{cartes(pg, 'gauche')}")
