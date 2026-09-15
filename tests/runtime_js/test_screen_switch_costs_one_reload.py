"""Combien de F5 pour passer de la vue PC à la vue téléphone, et retour ?

La réponse doit être **un**, indéfiniment, dans les deux sens. Elle était de
deux à partir de la deuxième bascule, signalé par l'utilisateur le 2026-08-16
sur ``examples/todo`` : « je dois faire 2 f5 pour passer de la vue telephone a
pc et inversement ».

Mécanisme (cf. ``render/shell.py::_screen_boot_script``) : ``Screen()`` est un
``if`` SERVEUR qui lit le cookie ``bz_screen``, donc le serveur peint toujours
le viewport du chargement PRÉCÉDENT. Le rattrapage est un reload pré-paint,
borné par un drapeau ``sessionStorage``. Ce drapeau n'était jamais effacé : la
première correction de l'onglet le posait pour de bon et toutes les suivantes
étaient avalées — cookie réécrit, peinture périmée à l'écran, second F5 requis.

Ce que ce test ajoute par rapport à la gate déterministe
(``tests/consistency/test_screen_sync_guard_is_consumed.py``, qui lit le texte
du script) : le **comportement du navigateur**, sur quatre bascules d'affilée.
Le nombre de bascules n'est pas décoratif — mesuré, pas supposé :

* la 1ʳᵉ passait déjà AVANT le fix (le drapeau était encore vierge) : un test
  qui s'arrête là est vert sur le bug ;
* c'est la 2ᵉ qui exhibait le symptôme signalé ;
* la 3ᵉ ferme les deux formulations rejetées pendant la conception (elles sont
  décrites dans le docstring de la gate déterministe, qui les possède). Chromium
  headless reste ``pointer: fine`` à 400px, donc ce test ne visite que DEUX
  formes : un drapeau keyé par forme aurait épuisé ses clés dès la 2ᵉ bascule ;
* la 4ᵉ est le témoin du mot « indéfiniment » — sans elle, « ça marche deux
  fois » resterait une lecture possible du résultat.

Run : ``py -m pytest tests/runtime_js/test_screen_switch_costs_one_reload.py -q -m browser``
"""

from __future__ import annotations

import pytest
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from bretzel import Bretzel, Screen, layout, page, ui
from tests.audit.harness import audit_server, browser_page

pytestmark = pytest.mark.browser

#: Largeurs de part et d'autre du seuil par défaut (``mobile_breakpoint=768``).
_DESKTOP = (1400, 900)
_MOBILE = (400, 800)

#: Ce que le SERVEUR a décidé, lu dans le DOM peint.
_READ = """() => {
    const el = document.getElementById('probe');
    return el ? el.getAttribute('data-shape') : null;
}"""


def _probe_app() -> Bretzel:
    """App minimale : un ``@layout`` qui affiche la branche prise par le serveur.

    Volontairement pas ``examples/screen_demo`` — le sujet est le mécanisme, pas
    le balisage d'un exemple. Lire ``<aside>`` contre ``<nav>`` ferait dépendre
    la gate de choix de composants sans rapport.

    ⚠️ Le repère vit dans le LAYOUT, hors de ``ui.outlet()``, et c'est tout le
    dispositif : ``hx-boost`` ne remplace que ``[data-bz-outlet]``. Un repère
    placé dans la page serait échangé par la nav boostée et le test passerait
    en croyant mesurer le layout. C'est exactement l'erreur que le bug de la nav
    boostée exploitait."""
    app = Bretzel(title="Screen probe", secret_key="x" * 32, mode="dev")

    @layout
    def shell() -> None:
        shape = "mobile" if Screen().is_mobile else "desktop"
        with ui.vstack():
            ui.text(shape, id="probe", attrs={"data-shape": shape})
            ui.link("aller en B", href="/b", id="to-b")
            ui.link("aller en A", href="/", id="to-a")
            ui.outlet()

    @page("/", layout=shell, title="A")
    def home() -> None:
        ui.text("page-A", id="page", attrs={"data-page": "A"})

    @page("/b", layout=shell, title="B")
    def other() -> None:
        ui.text("page-B", id="page", attrs={"data-page": "B"})

    app.include(home, other)
    return app


def _switch_to(page_, size: tuple[int, int], expected: str) -> str:
    """Redimensionne, tape F5 UNE fois, laisse le rattrapage pré-paint faire.

    Le reload correctif part pendant le parse du ``<head>``, donc avant même le
    ``load`` du document que ``page.reload()`` attend : il faut donc attendre la
    seconde navigation.

    L'attente est un ``wait_for_function``, pas une temporisation fixe — trois
    fois plus rapide (mesuré 0,18 s contre 0,93 s par bascule) et surtout non
    arbitraire. Elle ne peut pas conclure trop tôt : à chaque bascule le serveur
    peint d'abord la forme du cookie PRÉCÉDENT, donc la valeur attendue
    n'apparaît qu'APRÈS le reload correctif. Le timeout est avalé pour laisser
    l'assertion de l'appelant produire le vrai diagnostic."""
    page_.set_viewport_size({"width": size[0], "height": size[1]})
    page_.reload(wait_until="load")
    try:
        page_.wait_for_function(
            "(want) => {const el = document.getElementById('probe');"
            " return el && el.getAttribute('data-shape') === want;}",
            arg=expected,
            timeout=5000,
        )
    except PlaywrightTimeoutError:
        pass
    return page_.evaluate(_READ)


def test_each_switch_costs_a_single_f5() -> None:
    with audit_server(_probe_app()) as base_url:
        with browser_page(
            base_url, "/", viewport=_DESKTOP, wait_until="load"
        ) as browser:
            # Premier hit : aucun cookie, le serveur suppose desktop — et il a
            # raison, donc aucun reload n'est dépensé. Témoin : sans ça, les
            # bascules suivantes ne prouveraient pas ce qu'on croit.
            assert browser.evaluate(_READ) == "desktop", (
                "le premier hit en 1400px ne rend pas la branche desktop — le "
                "témoin est faux, la suite ne mesure rien."
            )

            seen = []
            for index, size in enumerate(
                (_MOBILE, _DESKTOP, _MOBILE, _DESKTOP), start=1
            ):
                expected = "mobile" if size == _MOBILE else "desktop"
                got = _switch_to(browser, size, expected)
                seen.append((expected, got))
                assert got == expected, (
                    f"bascule n°{index} vers {expected} ({size[0]}px) : la "
                    f"page rend encore {got!r} après UN F5.\n"
                    f"  Historique : {seen}\n"
                    f"  Le cookie `bz_screen` a bien été réécrit, mais le "
                    f"reload correctif n'est pas parti — le drapeau "
                    f"`bz:screen-synced` a survécu au chargement qu'il "
                    f"gardait. C'est le bug du 2026-08-16 : deux F5 par "
                    f"bascule. Cf. `render/shell.py::_screen_boot_script` — "
                    f"le drapeau se lit ET s'efface avant toute sortie "
                    f"anticipée."
                )


def test_a_boosted_nav_across_the_breakpoint_rebuilds_the_layout() -> None:
    """Le cas que le F5 ne couvre pas : on CLIQUE, on ne recharge pas.

    ``hx-boost`` ne remplace que ``[data-bz-outlet]``, donc ni le layout qui
    porte le ``if Screen().is_mobile``, ni le script de ``<head>`` qui écrit le
    cookie, ne rejouent. Avant le fix, cliquer après un redimensionnement
    repeignait l'ancienne forme **indéfiniment** — et rien ne le signalait :
    pas d'erreur console, pas de 4xx, juste la mauvaise nav à l'écran.

    ⚠️ C'est le trou structurel décrit par ``project_no_suite_navigates`` :
    aucune suite ne navigue, donc tout ce qui ne survit qu'au boost était
    invérifié. Ce test navigue."""
    with audit_server(_probe_app()) as base_url:
        with browser_page(
            base_url, "/", viewport=_DESKTOP, wait_until="load"
        ) as browser:
            assert browser.evaluate(_READ) == "desktop", "témoin initial faux"

            # TÉMOIN : une nav boostée SANS changement de forme doit rester un
            # swap partiel. Sans cette assertion, un fix qui transformerait
            # toute navigation en chargement dur passerait ce test — en ayant
            # supprimé le partial-nav, c'est-à-dire la fonctionnalité.
            boosted = browser.evaluate(
                "() => {window.__bzStillHere = true;"
                " document.getElementById('to-b').click(); return true;}"
            )
            assert boosted
            browser.wait_for_function(
                "() => {const el = document.getElementById('page');"
                " return el && el.getAttribute('data-page') === 'B';}",
                timeout=5000,
            )
            assert browser.evaluate("() => window.__bzStillHere === true"), (
                "le document a été rechargé pour une navigation qui ne "
                "traversait AUCUN seuil : le partial-nav est cassé. La "
                "resynchro doit rendre la main au navigateur uniquement quand "
                "la forme change."
            )

            # Le vrai sujet : on redimensionne, puis on CLIQUE (pas de F5).
            browser.set_viewport_size({"width": _MOBILE[0], "height": _MOBILE[1]})
            browser.evaluate("() => document.getElementById('to-a').click()")
            try:
                browser.wait_for_function(
                    "() => {const el = document.getElementById('probe');"
                    " return el && el.getAttribute('data-shape') === 'mobile';}",
                    timeout=8000,
                )
            except PlaywrightTimeoutError:
                pass

            shape = browser.evaluate(_READ)
            page_marker = browser.evaluate(
                "() => {const el = document.getElementById('page');"
                " return el ? el.getAttribute('data-page') : null;}"
            )
            assert shape == "mobile", (
                f"après un redimensionnement puis un CLIC, le layout rend "
                f"encore {shape!r}.\n"
                f"  `hx-boost` n'a échangé que `[data-bz-outlet]` : le layout "
                f"qui porte `if Screen().is_mobile` est resté en place, et le "
                f"script de `<head>` n'ayant pas rejoué, le cookie `bz_screen` "
                f"est lui aussi périmé — le serveur ne peut même pas le savoir. "
                f"La vue restera fausse jusqu'au prochain chargement DUR.\n"
                f"  Fix attendu : `05_bridge.js` appelle `$bzScreenSync()` sur "
                f"une nav boostée et, si la forme a changé, rend la navigation "
                f"au navigateur (chargement complet)."
            )
            assert page_marker == "A", (
                f"la navigation elle-même n'a pas abouti (page={page_marker!r}) "
                f"— la forme est peut-être bonne par accident."
            )

