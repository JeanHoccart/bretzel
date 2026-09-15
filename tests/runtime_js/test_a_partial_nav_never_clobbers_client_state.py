"""Une navigation partielle SÈME l'état client, elle ne l'ÉCRASE pas.

Le bug, rapporté par l'utilisateur le 2026-08-25
-------------------------------------------------
« Dès que je rentre sur la page paramètres, il switch en système. » Le
thème choisi — sombre — revenait au défaut à chaque arrivée sur un écran,
et repartait ensuite proprement dans ``localStorage`` : la préférence
n'était pas masquée, elle était **détruite**.

Le mécanisme, et pourquoi il touchait bien plus que le thème
--------------------------------------------------------------
Sur une navigation partielle (``hx-boost``, le mode par défaut sous une
coque), le serveur ré-émet **toutes** les instances de ``ClientState``
que la page référence — ``_render_delta(ctx, include_unchanged=True)``.
C'est nécessaire : le runtime traverse la navigation sans être rechargé,
donc une instance qu'il n'a jamais vue n'existe pas, et un binding
``$bz.state.X.default.f`` lèverait *Cannot read properties of undefined*.

Mais le serveur ne peut pas connaître les valeurs du NAVIGATEUR — un
``ClientState`` est client-owned. Il envoie donc ses défauts, et le
bridge les appliquait par ``$bz._store.set``, sans distinction. Deux
conséquences, la seconde bien pire que la première :

1. la valeur vivante était remplacée par le défaut ;
2. ``set`` notifie la persistance, donc le défaut partait dans
   ``localStorage`` **avant** qu'``adoptConfig`` n'aille y relire le
   snapshot. Ce qui devait guérir écrivait la mauvaise valeur.

Mesuré avant correction, en Chromium, sur sept compositions (le contrôle
seul, dans un ``@refreshable``, dans un ``ui.form``, avec un ``size=``
serveur, deux contrôles côte à côte…) : **les sept perdaient la valeur**.
Et une page qui ne fait que LIRE l'état — ``ui.text(ColorScheme().mode)``,
sans aucun contrôle lié — la perdait aussi. Le seul témoin resté vert est
la page qui n'y touche pas du tout, ce qui désigne le seed et rien
d'autre.

La correction, et les deux versants qu'il faut garder
------------------------------------------------------
``$bz._store.seed(path, value)`` (``00_index.js``) pose une valeur
INITIALE : elle ne fait rien si le champ en a déjà une. Le bridge
l'emploie sur le chemin de seed et garde ``set`` pour les réponses
d'action, où le serveur a délibérément muté un champ et doit gagner.

Les deux versants comptent autant, et c'est pour ça qu'il y a deux tests
ici. Un correctif qui se contenterait de ne plus rien écrire ferait
passer le premier et rouvrirait, en silence, très exactement le défaut
que le seed avait été ajouté pour fermer.

Lourd (uvicorn + Chromium) — à lancer explicitement ::

    py -m pytest tests/runtime_js/test_a_partial_nav_never_clobbers_client_state.py -q -m browser
"""

from __future__ import annotations

import pytest

from bretzel import Bretzel, layout, page, ui
from bretzel.state import ClientState, field
from tests.audit.harness import audit_server, browser_page


class Reglages(ClientState, persist="local"):
    """Client-owned et PERSISTÉ — les deux moitiés du défaut d'origine."""

    theme: str = field(default='systeme')


class JamaisVue(ClientState):
    """Référencée par UNE seule page, celle qu'on atteint en navigation.

    C'est le cas que le seed existe pour servir : le runtime ne l'a
    jamais vue, donc il faut bien que quelqu'un la crée.
    """

    texte: str = field(default='defaut')


def build_app() -> Bretzel:
    app = Bretzel(
        secret_key="dev-partial-nav-seed-secret-key",
        title="seed bench",
        mode="dev",
    )

    @layout
    def shell() -> None:
        # ``ui.viewport`` + ``ui.pane`` : la vraie coque, donc les liens
        # sont boostés et la navigation est PARTIELLE. Une page sans
        # coque rechargerait tout et ne reproduirait rien — mesuré.
        with ui.viewport():
            with ui.pane(gap="none"):
                with ui.hstack(gap="md", classes="p-4"):
                    ui.link("Accueil", href="/", id="vers-accueil")
                    ui.link("Reglages", href="/reglages", id="vers-reglages")
                    ui.link("Neuve", href="/neuve", id="vers-neuve")
                    ui.button("Sombre", id="poser",
                              on_click=Reglages().theme.set("sombre"))
                ui.outlet()

    @page("/", layout=shell, title="accueil")
    def home() -> None:
        # AUCUNE lecture de ``Reglages`` ici : c'est ce qui rend le
        # départ propre — la valeur ne vient que du clic.
        ui.heading("Accueil", level=1, classes="p-6")

    @page("/reglages", layout=shell, title="reglages")
    def reglages() -> None:
        etat = Reglages()
        with ui.vstack(classes="p-6"):
            ui.text(etat.theme, id="lu")

    @page("/neuve", layout=shell, title="neuve")
    def neuve() -> None:
        etat = JamaisVue()
        with ui.vstack(classes="p-6"):
            ui.input(value=etat.texte, id="champ")
            ui.text(etat.texte, id="echo")

    for fn in (home, reglages, neuve):
        app.include(fn)
    return app


@pytest.fixture(scope="module")
def base_url():
    with audit_server(build_app()) as url:
        yield url


def read_store(page, path: str):
    return page.evaluate("(p) => $bz._store.peek(p)", path)


@pytest.mark.browser
def test_a_live_value_survives_the_navigation(base_url) -> None:
    """Le versant du BUG : la valeur choisie traverse l'arrivée sur une
    page qui référence son état."""
    with browser_page(base_url, "/") as page:
        page.click("#poser")
        page.wait_for_timeout(300)
        assert read_store(page, "Reglages.default.theme") == "sombre", (
            "le clic n'a pas posé la valeur — le reste du test ne "
            "prouverait rien."
        )

        page.click("#vers-reglages")
        page.wait_for_timeout(800)

        assert read_store(page, "Reglages.default.theme") == "sombre", (
            "le seed de navigation partielle a écrasé la valeur vivante "
            "avec le défaut du serveur. Le serveur ne peut pas connaître "
            "l'état du navigateur : ses valeurs ne doivent servir qu'à "
            "CRÉER ce qui manque (``$bz._store.seed``, 00_index.js)."
        )
        assert page.locator("#lu").inner_text().strip() == "sombre"


@pytest.mark.browser
def test_the_persisted_snapshot_is_not_rewritten(base_url) -> None:
    """Le second effet, et le plus coûteux : ``set`` notifie la
    persistance, donc l'écrasement partait dans ``localStorage``.

    Sans ce test, un correctif qui rétablirait la valeur en mémoire mais
    laisserait le défaut dans le stockage passerait — et la préférence
    serait perdue au prochain rechargement, pas tout de suite. C'est très
    exactement le mode d'échec qui a été rapporté.
    """
    with browser_page(base_url, "/") as page:
        page.click("#poser")
        page.wait_for_timeout(300)
        page.click("#vers-reglages")
        page.wait_for_timeout(800)

        page.reload()
        page.wait_for_selector("html.bz-ready", state="attached")
        page.wait_for_timeout(600)

        assert read_store(page, "Reglages.default.theme") == "sombre", (
            "la valeur n'a pas survécu au rechargement : le défaut du "
            "serveur a été écrit dans localStorage pendant la navigation."
        )


@pytest.mark.browser
def test_an_unseen_instance_is_still_created(base_url) -> None:
    """Le versant LICITE, et il coûte autant que l'autre.

    Ne plus rien écrire du tout ferait passer les deux tests ci-dessus et
    rouvrirait le défaut que le seed ferme : une instance que le runtime
    n'a jamais vue n'existerait pas, et son binding lèverait *Cannot read
    properties of undefined*.
    """
    with browser_page(base_url, "/") as page:
        assert read_store(page, "JamaisVue.default.texte") is None, (
            "l'instance est déjà connue au départ — le test ne mesurerait "
            "pas la création."
        )

        page.click("#vers-neuve")
        page.wait_for_timeout(800)

        assert read_store(page, "JamaisVue.default.texte") == "defaut", (
            "le seed n'a pas créé l'instance : une navigation partielle "
            "vers une page qui référence un ClientState inconnu laisse "
            "ses bindings sans magasin."
        )
        # …et elle doit être PILOTABLE, pas seulement présente.
        page.fill("#champ", "modifie")
        page.wait_for_timeout(300)
        assert read_store(page, "JamaisVue.default.texte") == "modifie"
        assert page.locator("#echo").inner_text().strip() == "modifie"
