"""``send_to_server=False`` empêche-t-il VRAIMENT la remontée ?

``tests/consistency/test_client_state_transport_config.py`` prouve que la
clé part sur le fil avec la bonne valeur, et que le kwarg la règle. Ça ne
prouve pas la moitié qui compte : que **le bridge l'honore**. Le filtre
vit dans ``injectParameters`` (``05_bridge.js``), en JS, dans une fonction
qui tourne sur *chaque* POST d'action — aucun test Python ne l'exécute.

C'est exactement la situation qui a produit le défaut d'origine : la
branche ``if (cfg.send_to_server === false) continue`` était écrite,
lisible, plausible — et morte, faute d'une moitié Python capable de poser
le drapeau. Livrer la moitié manquante sans mesurer le tout referait la
même erreur d'un cran plus haut.

Deux faits que seul un vrai navigateur peut établir, et ils sont
symétriques :

1. un état ``send_to_server=False`` **ne remonte pas** — le handler lit
   le défaut de classe, pas ce que le client avait en mémoire ;
2. un état ordinaire **remonte toujours** — c'est la garde de régression
   qui compte le plus ici, ``injectParameters`` étant le chemin par lequel
   passe la valeur de tout formulaire et de tout binding du framework.

Le résultat est renvoyé par le mécanisme même dont on parle : le handler
écrit dans un ``ClientState``, qui redescend en ``<bz-patch>`` et se pose
dans le DOM via ``bz-text``. Pas de zone ``@refreshable``, donc la
réponse ne porte QUE le delta — ce qui exerce au passage le chemin
« action sans re-render » (``drain_refresh_queue`` § corps bâti sur le
seul delta).

App minimale définie ici plutôt qu'une page de playground : le sujet est
une propriété du transport, pas d'un composant (même raisonnement que
``test_redirect_actually_navigates.py``).

Run : ``py -m pytest tests/runtime_js/test_send_to_server_is_honoured.py -q -m browser``
"""

from __future__ import annotations

import pytest

from bretzel import Bretzel, layout, page, ui
from bretzel.state import ClientState, field
from tests.audit.harness import audit_server, browser_page

pytestmark = pytest.mark.browser

_DEFAULT = "valeur-par-defaut"
_FROM_CLIENT = "ecrit-par-le-client"


class Loud(ClientState):
    """Ordinaire : remonte à chaque POST."""

    token: str = field(default=_DEFAULT)


class Silent(ClientState, send_to_server=False):
    """Descendant seul : le serveur écrit, le client affiche."""

    token: str = field(default=_DEFAULT)


class Seen(ClientState):
    """Ce que le handler a effectivement reçu, renvoyé au DOM."""

    report: str = field(default='')


class Kept(ClientState, persist="local"):
    """Persistant — sert à mesurer que le trou de config n'est PAS propre
    à ``send_to_server``. ``register()`` (04_persistence.js) fait deux
    choses : brancher la sauvegarde, ET superposer le snapshot déjà en
    localStorage. Un état dont l'adaptateur n'est jamais enregistré ne
    sauvegarde donc pas — et ne RECHARGE pas non plus, ce qui est la
    moitié visible pour un utilisateur qui revient."""

    note: str = field(default=_DEFAULT)


def report_what_arrived() -> None:
    # Hors scope de rendu, un champ de ClientState rend sa valeur Python
    # brute — donc exactement ce que la requête a livré (ou le défaut de
    # classe, si rien n'est arrivé pour ce champ).
    Seen().report = f"loud={Loud().token} silent={Silent().token}"


_probe_app = Bretzel(secret_key="s" * 32, mode="dev")


@layout
def shell() -> None:
    """Un shell minimal — **indispensable, pas décoratif**.

    Sans lui, il n'y a pas d'outlet, donc pas de ``hx-boost``, donc le
    clic sur un lien interne fait un CHARGEMENT COMPLET : la page réémet
    son ``<bz-envelope>`` et le test de nav partielle ne mesure rien.
    Mesuré : la première version de ce fichier n'avait pas de shell, et
    son test « nav partielle » passait en rechargeant tout (témoin
    ``window.__marker`` perdu au clic).
    """
    with ui.vstack(gap="md"):
        ui.link("Aller au transport", href="/transport", id="vers-transport")
        ui.outlet()


@page("/accueil", layout=shell)
def accueil_page() -> None:
    """Le point de départ — il ne LIE aucun des deux états, ce qui est tout
    l'intérêt : ils sont donc absents de SON ``<bz-envelope>``."""
    ui.text("accueil", id="accueil")


@page("/transport", layout=shell)
def transport_page() -> None:
    ui.button("Envoyer", on_click=report_what_arrived, id="go")
    ui.text(Seen().report, id="report")
    # Les deux états sont LIÉS ici, et pas seulement écrits par le
    # handler : c'est le rendu qui les fait entrer dans l'``<bz-envelope>``,
    # donc dans ``$bz._config`` — et sans config, le bridge n'a aucun
    # drapeau à lire et remonte tout. Un état qu'aucune page ne lie
    # n'arrive de toute façon jamais au navigateur.
    ui.text(Loud().token, id="loud-view")
    ui.text(Silent().token, id="silent-view")
    ui.text(Kept().note, id="kept-view")


_probe_app.include(shell, accueil_page, transport_page)


_FROM_STORAGE = "depuis-le-stockage"

#: Pré-remplir localStorage AVANT que la page ne se charge. ``add_init_script``
#: tourne à chaque document, donc avant le boot du runtime — c'est ce qui
#: permet de tester la superposition du snapshot, qui n'a lieu qu'une fois.
#:
#: ⚠️ C'est un CORPS de script, pas une fonction. ``add_init_script``
#: exécute ce qu'on lui donne ; ``evaluate``, lui, APPELLE la fonction
#: qu'on lui passe. Écrit en ``() => …`` comme partout ailleurs dans ce
#: fichier, ça définit une fonction anonyme que personne n'invoque — et
#: le test échoue en accusant le framework (mesuré le 2026-08-15 : le
#: contrôle « chargement dur » est parti rouge, localStorage vide).
_SEED_STORAGE = (
    'localStorage.setItem("$bz:Kept.default", '
    f'JSON.stringify({{note: "{_FROM_STORAGE}"}}))'
)


def _assert_partial_nav(browser, marker: str = "vivant") -> None:  # type: ignore[no-untyped-def]
    """Poser un témoin, sauter, et EXIGER qu'il ait survécu.

    Sans ça un test de nav partielle mesure un rechargement : sans layout
    + outlet il n'y a pas de ``hx-boost``, le clic recharge le document,
    la page réémet son ``<bz-envelope>`` et tout a l'air de marcher.
    Mesuré le 2026-08-15 — cf. ``traps.md`` § *Process trap — un test de
    nav partielle sans témoin*.
    """
    browser.evaluate(f"() => {{ window.__marker = '{marker}'; }}")
    browser.click("#vers-transport")
    browser.wait_for_selector("#go", timeout=5000)
    assert browser.evaluate("() => window.__marker || 'PERDU'") == marker, (
        "Le témoin n'a pas survécu au clic : ce n'était PAS une navigation "
        "partielle mais un rechargement complet. Le test ne mesure donc "
        "rien de ce qu'il annonce."
    )


def _drive(browser) -> str:  # type: ignore[no-untyped-def]
    """Écrire dans le store, cliquer, rendre le rapport du handler."""
    # On écrit dans le store côté client SANS passer par un composant : le
    # sujet est le transport, et un input aurait mêlé la question du
    # binding à celle de la remontée.
    browser.evaluate(
        """(v) => {
            $bz._store.set("Loud.default.token", v);
            $bz._store.set("Silent.default.token", v);
        }""",
        _FROM_CLIENT,
    )
    browser.click("#go")
    browser.wait_for_function(
        "() => document.querySelector('#report')"
        "?.textContent.startsWith('loud=')",
        timeout=5000,
    )
    return browser.locator("#report").inner_text()


def test_a_silent_state_does_not_ride_the_action_post() -> None:
    with audit_server(_probe_app) as base_url:
        with browser_page(base_url, "/transport") as browser:
            report = _drive(browser)

            assert f"loud={_FROM_CLIENT}" in report, (
                "Un ClientState ORDINAIRE n'est pas remonté au serveur : "
                f"reçu {report!r}. C'est le chemin de toute valeur de "
                "formulaire et de tout binding du framework — la "
                "régression la plus chère que ce fichier puisse attraper."
            )
            assert f"silent={_DEFAULT}" in report, (
                "Un ClientState send_to_server=False est quand même remonté : "
                f"reçu {report!r}. Le filtre d'injectParameters "
                "(05_bridge.js) ne lit pas la config, ou l'envelope ne la "
                "porte pas jusqu'à $bz._config (00_index.js § boot)."
            )


def test_a_silent_state_survives_a_partial_navigation() -> None:
    """Le même fait, mais l'état est découvert APRÈS un ``hx-boost``.

    C'est le chemin NORMAL dans une vraie app : avec une sidebar, presque
    toute navigation est boostée. Un réglage qui ne tient que sur F5 ne
    sert donc à rien — d'où ce test à côté de son voisin, qui charge
    ``/transport`` en dur.

    Il a vécu quelques heures en ``xfail(strict=True)`` : le trou avait
    été mesuré avant d'être réparé (la config de transport ne voyageait
    que dans l'``<bz-envelope>``, absent d'une réponse boostée). Le
    ``strict`` a fait son travail — il est passé XPASS à la minute où le
    ``<bz-patch>`` de seed s'est mis à porter la config, ce qui est la
    seule façon d'apprendre qu'une dette est éteinte plutôt que de le
    supposer.

    Il répare aussi l'angle mort décrit par la memory
    ``project_no_suite_navigates`` (« aucune suite ne navigue ») : un test
    qui monte une page et s'arrête ne dit rien du chemin boosté.
    """
    with audit_server(_probe_app) as base_url:
        with browser_page(base_url, "/accueil") as browser:
            _assert_partial_nav(browser)
            report = _drive(browser)

            assert f"silent={_DEFAULT}" in report


def test_persist_survives_a_partial_navigation() -> None:
    """Le MÊME trou, sur un réglage antérieur de plusieurs mois.

    ``persist=`` voyage par le même canal que ``send_to_server`` — la
    config de l'``<bz-envelope>``, lue au seul boot — et
    ``$bz._persistence.register`` est appelé dans le même bloc. Un état
    ``persist="local"`` découvert par nav partielle n'a donc aucun
    adaptateur.

    On mesure la moitié la plus visible pour un utilisateur : ``register()``
    ne branche pas seulement la sauvegarde, il **superpose le snapshot
    déjà stocké** (« the user's browser knows better than the server's
    defaults », 04_persistence.js). Sans adaptateur, la valeur sauvegardée
    n'est jamais relue — l'utilisateur qui revient retrouve les défauts.

    Le témoin de chargement dur sert de contrôle : il prouve que le
    mécanisme fonctionne, donc qu'un échec ci-dessous vient bien du
    chemin de navigation et pas d'un test mal câblé.
    """
    with audit_server(_probe_app) as base_url:
        # ── Contrôle : chargement dur, le snapshot doit gagner ──────────
        with browser_page(base_url, "/accueil") as browser:
            browser.add_init_script(_SEED_STORAGE)
            browser.goto(f"{base_url}/transport")
            browser.wait_for_selector("#kept-view", timeout=5000)
            assert browser.locator("#kept-view").inner_text() == _FROM_STORAGE, (
                "Même en chargement dur, le snapshot localStorage ne "
                "remonte pas — le test est mal câblé, pas le framework."
            )

        # ── La mesure : même page, atteinte en nav partielle ────────────
        with browser_page(base_url, "/accueil") as browser:
            browser.add_init_script(_SEED_STORAGE)
            browser.reload()
            browser.wait_for_selector("#vers-transport", timeout=5000)
            _assert_partial_nav(browser, marker="persist")

            assert browser.locator("#kept-view").inner_text() == _FROM_STORAGE, (
                "Un ClientState persist='local' découvert par nav partielle "
                "n'a pas d'adaptateur de persistance : $bz._persistence."
                "register n'est appelé qu'au boot (00_index.js), et une "
                "réponse hx-boost ne porte qu'un <bz-patch>. La valeur "
                "sauvegardée n'est donc jamais relue."
            )
