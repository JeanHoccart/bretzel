"""Gate : charger une page de composant ne jette AUCUNE exception JS.

Le défaut qu'elle ferme (2026-08-27)
------------------------------------
``07_calendar.js`` appelle ``customElements.define('bz-calendar', …)`` au
niveau du slab. Cet appel met à niveau **immédiatement** tous les
``<bz-calendar>`` déjà dans le DOM, et leur constructeur lit
``$bz.locale.weekdayNames()``. Or ``$bz.locale`` était installé par
``22_locale.js`` — quinze slabs PLUS LOIN dans le fichier concaténé.

Résultat mesuré : **une exception jetée par calendrier**.

=========================  ==========
page du playground          exceptions
=========================  ==========
``/calendar``               54
``/date_range_picker``      45
``/date_picker``            44
``/month_picker``           35
=========================  ==========

**Rien ne l'a vu pendant deux jours**, et la raison mérite d'être écrite :
``tests/audit/harness.py`` branche bien un ``page.on("pageerror", …)`` —
mais il ne fait qu'``print``. La sortie part dans la capture de pytest,
que personne ne lit tant qu'un test ne tombe pas. Un observateur qui
n'affirme rien est un observateur qui se tait.

Le coût réel n'était pas cosmétique : le flot d'erreurs empêchait
``networkidle`` d'arriver, donc ``probe_server_props_drive_dom`` restait
suspendu, donc ``pytest -m audit`` **pendait**. Une suite d'une heure
rendue inutilisable par une ligne d'ordre de chargement.

Pourquoi cette gate est à l'EXÉCUTION, et pas statique
--------------------------------------------------------
La tentation était d'interdire statiquement qu'un slab lise un
``$bz.<ns>`` installé par un slab postérieur. Mesuré sur le dépôt : **9
cas, et les 9 sont légitimes** — ``00_index`` lit ``$bz.signal`` dans une
fonction appelée bien après le chargement, ``02_directives`` lit
``$bz.helpers`` dans un gestionnaire de directive. La règle statique
ferait 9 faux positifs sur 9, ce que la doctrine de ``gates.md``
interdit.

Ce qui distingue le vrai défaut, c'est le MOMENT de la lecture — au
chargement, pas plus tard. Aucune analyse statique raisonnable ne le
sépare ; un navigateur le sépare gratuitement. D'où cette gate-ci.

Ce qu'elle écarte, et pourquoi ce n'est pas un pansement
---------------------------------------------------------
Le playground tourne en ``mode="dev"``, donc sous
``css_pipeline == "browser"`` : ``@tailwindcss/browser`` est chargé DANS
la page et compile le ``@theme`` à la volée. Ce compilateur part sur un
``MutationObserver`` dès qu'il voit le ``<style>`` — **y compris pendant
que le HTML est encore streamé**. Il lit alors un bloc coupé et jette.

Mesuré le 2026-08-29, 19 occurrences capturées sous ``-m browser -n 4``,
deux messages et deux seulement :

    CssSyntaxError: Missing closing } at @theme
    CssSyntaxError: Invalid custom property, expected a value
        at Pe (https://unpkg.com/@tailwindcss/browser@4:2:5987)

**Le CSS de la page est INTACT** : au moment du jet, le ``<style>`` du
thème mesure ses 7 008 caractères et se termine proprement. C'est la
lecture qui était prématurée, pas la source qui était fausse. Trois
hypothèses ont été éliminées avant celle-ci, chacune par une mesure —
charge CPU (276 s de run, 292 verts), bundle ``runtime.js`` réécrit
pendant le balayage (137 rebuilds, 76 verts), et attribution d'une
erreur tardive à la page suivante (l'``URL`` capturée correspond toujours
à la page accusée).

Ces exceptions sont donc écartées **par leur ORIGINE** — la pile pointe
dans le script tiers — et jamais par leur message. Deux raisons pour que
ce ne soit pas un aveuglement :

1. En production il n'y a AUCUN compilateur dans la page (le CSS est
   compilé et servi en ``<link>``). Ces erreurs ne peuvent atteindre
   personne ; les compter ici, c'est mesurer une course d'outillage.
2. Elles ne sont pas jetées, elles sont RANGÉES —
   ``test_the_dev_css_compiler_noise_stays_what_it_was_measured_to_be``
   rougit sur tout message que ce script n'avait jamais produit.

Ce qu'elle ne fait PAS
-----------------------
Elle ne regarde ni les avertissements de console, ni les erreurs
déclenchées par une INTERACTION — seulement ce que le chargement d'une
page jette tout seul. C'est le sous-ensemble qui casse le plus loin de sa
cause, et le seul qu'on puisse balayer sur tout le catalogue en moins
d'une minute.
"""

from __future__ import annotations

import pytest

from tests.audit.checklist import COMPONENT_SPECS
from tests.audit.harness import audit_server, browser_context

pytestmark = pytest.mark.browser

#: Preuve de morsure par contrôle POSITIF : le balayage charge vraiment
#: des pages qui montent des composants, et le collecteur d'erreurs voit
#: vraiment passer une erreur quand on en fabrique une.
MUTATION_PROOF = "test_the_collector_actually_sees_a_throw"

#: 74 routes le 2026-08-27, découvertes depuis le catalogue de l'audit —
#: pas une liste à tenir à jour ici. Le plancher attrape un import cassé
#: ou un catalogue vidé : la gate serait verte en n'ayant rien chargé.
_ROUTES_FLOOR = 60

#: Les deux seuls messages que la course compilateur-vs-streaming a
#: produits, sur 19 occurrences capturées le 2026-08-29. Tout autre
#: message du même script fera rougir : cf.
#: ``test_the_dev_css_compiler_noise_stays_what_it_was_measured_to_be``.
_KNOWN_COMPILER_RACE = (
    "Missing closing } at @theme",
    "Invalid custom property, expected a value",
)


def _routes() -> list[tuple[str, str]]:
    return sorted(
        (spec.name, spec.route)
        for specs in COMPONENT_SPECS.values()
        for spec in specs
    )


#: L'origine du compilateur Tailwind de DÉVELOPPEMENT. Une pile qui y
#: pointe ne peut pas venir de Bretzel : ce script n'existe que sous
#: ``css_pipeline == "browser"``, jamais en production.
_DEV_CSS_COMPILER = "@tailwindcss/browser"


def _is_dev_css_compiler(stack: str | None) -> bool:
    """Cette exception a-t-elle été levée PAR le compilateur dev ?

    Sur la PILE, pas sur le message : un message se ressemble d'un
    émetteur à l'autre, une origine non. Extrait pour être mutable —
    cf. :func:`test_the_third_party_filter_is_narrow`.
    """
    return _DEV_CSS_COMPILER in (stack or "")


@pytest.fixture(scope="module")
def swept() -> tuple[dict[str, list[str]], dict[str, list[str]]]:
    """``({nôtres}, {du compilateur dev})`` par composant.

    Un seul navigateur, une seule page, ~0,6 s par route : un navigateur
    par route coûterait 74 démarrages de Chromium pour répondre à une
    question qui ne demande qu'un ``goto``.
    """
    routes = _routes()
    ours: dict[str, list[str]] = {}
    theirs: dict[str, list[str]] = {}
    # ⚠️ ``browser_context`` et PAS ``sync_playwright()`` : le harnais
    # tient un Playwright de processus, et en ouvrir un second dans le
    # même thread casse tout ce qui suit. Mesuré : ce fichier passait
    # SEUL et faisait « 1 échec + 75 erreurs » dans ``-m browser``.
    with audit_server() as url, browser_context() as ctx:
        page = ctx.new_page()
        mine: list[str] = []
        third: list[str] = []

        def collect(err: object) -> None:
            stack = getattr(err, "stack", None)
            (third if _is_dev_css_compiler(stack) else mine).append(str(err))

        page.on("pageerror", collect)
        for name, route in routes:
            mine.clear()
            third.clear()
            page.goto(url + route, wait_until="load")
            page.wait_for_timeout(400)
            ours[name] = list(mine)
            theirs[name] = list(third)
    return ours, theirs


@pytest.fixture(scope="module")
def page_errors(swept) -> dict[str, list[str]]:
    """Les exceptions dont BRETZEL répond."""
    return swept[0]


@pytest.fixture(scope="module")
def compiler_errors(swept) -> dict[str, list[str]]:
    """Celles que le compilateur CSS de dev a levées lui-même."""
    return swept[1]


def test_the_sweep_is_not_vacuous(page_errors) -> None:
    assert len(page_errors) >= _ROUTES_FLOOR, (
        f"seulement {len(page_errors)} routes balayées (74 le 2026-08-27) "
        f"— vérifie que ``COMPONENT_SPECS`` se lit encore avant de croire "
        f"que cette gate passe. Elle serait verte en n'ayant rien chargé."
    )


@pytest.mark.parametrize("name", [n for n, _ in _routes()])
def test_a_component_page_loads_without_throwing(name, page_errors) -> None:
    errors = page_errors.get(name)
    assert errors is not None, f"{name} n'a pas été balayé"
    # Les doublons sont la signature du défaut d'origine — une exception
    # PAR instance — donc on les compte, et on n'en montre que trois.
    unique = sorted(set(errors))
    assert not errors, (
        f"charger la page de ``{name}`` jette {len(errors)} exception(s) "
        f"JS ({len(unique)} distincte(s)) :\n"
        + "\n".join(f"  - {e[:160]}" for e in unique[:3])
        + "\n  Une exception par instance signale une dépendance lue AVANT "
        "d'être posée — vérifie l'ordre des slabs dans "
        "``bretzel/runtime/_src/`` : le nom porte le rang de chargement."
    )


def test_the_collector_actually_sees_a_throw() -> None:
    """Le collecteur n'est pas aveugle — prouvé sur une erreur fabriquée.

    Sans ce test, « zéro exception partout » pourrait vouloir dire « le
    ``page.on('pageerror')`` n'est plus branché », et la gate serait
    verte sur n'importe quel runtime cassé.
    """
    with browser_context() as ctx:
        page = ctx.new_page()
        seen: list[str] = []
        page.on("pageerror", lambda err: seen.append(str(err)))
        page.set_content(
            "<script>setTimeout(() => { "
            "null.deliberatelyMissing; }, 0);</script>"
        )
        page.wait_for_timeout(400)
    assert seen, (
        "le collecteur ``pageerror`` n'a PAS vu une exception fabriquée "
        "exprès — toute assertion « zéro erreur » de ce fichier ne veut "
        "alors rien dire."
    )


def test_the_dev_css_compiler_noise_stays_what_it_was_measured_to_be(
    compiler_errors,
) -> None:
    """Le tiers écarté ne l'est QUE pour la course qu'on a mesurée.

    Écarter par l'origine sans regarder QUOI reviendrait à s'aveugler
    sur tout ce que ce script pourra jeter demain — un chargement
    partiel, une version incompatible, un `@theme` réellement invalide.
    On nomme donc les deux messages connus, et un troisième fera rougir.

    Ce test ne rougit pas quand la course NE se produit PAS : c'est
    normal et fréquent (elle demande une machine chargée).
    """
    seen = sorted({e for errs in compiler_errors.values() for e in errs})
    unknown = [e for e in seen if not any(k in e for k in _KNOWN_COMPILER_RACE)]
    assert not unknown, (
        f"le compilateur CSS de dev jette des messages jamais mesurés : "
        f"{unknown}. Ils sont écartés par leur ORIGINE, donc personne ne "
        f"les regarde — vérifie qu'il ne s'agit pas d'un vrai défaut du "
        f"thème avant d'allonger ``_KNOWN_COMPILER_RACE``."
    )


def test_the_third_party_filter_is_narrow() -> None:
    """Le filtre écarte le compilateur dev, et RIEN d'autre.

    Les deux versants comptent, et c'est le licite qui coûte : un filtre
    trop large rendrait la gate verte sur une vraie erreur de runtime,
    c'est-à-dire exactement ce qu'elle existe pour attraper.
    """
    tiers = (
        "CssSyntaxError: Missing closing } at @theme\n"
        "    at Pe (https://unpkg.com/@tailwindcss/browser@4:2:5987)"
    )
    assert _is_dev_css_compiler(tiers)

    notre = (
        "TypeError: Cannot read properties of undefined\n"
        "    at ensureSse (http://127.0.0.1:8000/_bretzel/runtime.js:150:5)"
    )
    assert not _is_dev_css_compiler(notre)
    # Même message, mais lancé depuis NOTRE code : la pile décide, pas
    # le texte. C'est tout l'intérêt de filtrer sur l'origine.
    homonyme = (
        "CssSyntaxError: Missing closing } at @theme\n"
        "    at http://127.0.0.1:8000/_bretzel/runtime.js:12:1"
    )
    assert not _is_dev_css_compiler(homonyme)
    assert not _is_dev_css_compiler(None)
