"""Un calendrier garde sa grille quand la zone qui le contient se rafraîchit.

Le bug, mesuré le 2026-08-21 (finding [25], rapporté par l'utilisateur en
se servant du CRM) : « cliquer sur une date fait planter le composant des
dates ». L'agenda gardait son en-tête et sa ligne de jours, et **rien** en
dessous. 42 cellules au premier rendu, **0** après un refresh de sa zone,
et définitivement.

Le mécanisme, et pourquoi rien ne l'attrapait
----------------------------------------------
Le SSR émet un conteneur de grille VIDE (``data-bz-cal-grid``) que le
custom element remplit dans son ``connectedCallback``. Quand idiomorph
morphe le ``<bz-calendar>`` EN PLACE — ce que fait le refresh d'une zone
``@refreshable`` qui le contient — ses enfants reviennent à la version
serveur, donc vides. Or :

- ``connectedCallback`` ne re-tourne pas : **le nœud a survécu** ;
- ``attributeChangedCallback`` non plus : le refresh ne change aucun
  attribut observé (ici un compteur sans rapport) ;
- et ``bz-init`` est **one-shot par NŒUD** (``el._bzInitDone``, qui
  survit au rebind), donc il ne rattrape rien non plus.

Personne ne re-remplissait. L'en-tête de ``calendar.py`` annonce que la
configuration vit dans des attributs « que idiomorph peut morpher
librement » : c'est vrai des ATTRIBUTS, ça ne l'est pas des ENFANTS — et
c'est la contrepartie que le choix « custom element » n'avait pas tenue.

Le fix : un ``bz-effect`` sur la racine (le seul hook du framework qui
re-tourne à CHAQUE rescan — il est disposé et refait par ``bindEl``)
appelle ``rehydrate()``, qui repeint **seulement** si le corps a vraiment
été effacé.

Pourquoi ce test passe par le vrai transport
---------------------------------------------
Rendre la zone à la main dans le corps du test ne reproduit RIEN : c'est
le morph d'idiomorph sur un aller-retour HTTP qui remet les enfants à la
version serveur. Une gate qui monterait le composant deux fois resterait
verte avec le fix retiré (cf. la memory
``project_gate_harness_must_match_render_timing``). D'où l'app minimale
servie ici : un vrai ``@refreshable``, un vrai bouton, un vrai swap.

Le bump ne touche AUCUN attribut du calendrier — c'est la condition du
bug, et c'est ce qui rend le test spécifique : un refresh qui changerait
``value`` ou ``month`` serait rattrapé par ``attributeChangedCallback`` et
ne prouverait rien.

Lourd (uvicorn + Chromium) — à lancer explicitement ::

    py -m pytest tests/runtime_js/test_calendar_survives_its_zone_refresh.py -q -m browser
"""

from __future__ import annotations

import pytest

from bretzel import Bretzel, page, refreshable, ui
from bretzel.state import SessionState, field
from tests.audit.harness import audit_server, browser_page

#: Le sélecteur du conteneur que le custom element remplit. Écrit une
#: fois ici plutôt que dans chaque assertion : c'est le seul littéral que
#: ce test emprunte à l'implémentation.
_CELLS = "#cal [data-bz-cal-grid] > *"


#: L'app est bâtie AVANT les pages : ``@page`` / ``@refreshable`` marquent
#: les fonctions, et ``app.include`` les enregistre à la fin — l'idiome des
#: bancs de ce dépôt.
app = Bretzel(
    secret_key="dev-calendar-morph-gate-secret-key",
    title="Bretzel · calendrier sous morph",
    mode="dev",
)


class Bump(SessionState):
    n: int = field(default=0)


def bump() -> None:
    """Muter un état SANS rapport avec le calendrier.

    C'est le cœur du cas : le calendrier n'a aucune raison de re-rendre,
    et pourtant le morph passe sur lui.
    """
    Bump().n += 1


@refreshable(deps=[Bump])
def zone() -> None:
    with ui.vstack(gap="sm"):
        ui.text(f"n = {Bump().n}", id="n")
        ui.calendar(
            value="2026-08-05", month="2026-08-05", weekstart=1,
            size="sm", id="cal",
        )


@page("/")
def home() -> None:
    with ui.vstack(gap="md", classes="p-6"):
        ui.button("bump", on_click=bump, id="bumpbtn")
        zone()


app.include(__name__)


@pytest.fixture(scope="module")
def base_url():
    with audit_server(app) as url:
        yield url


@pytest.mark.browser
def test_the_grid_is_painted_at_all(base_url) -> None:
    """Le plancher. Sans lui, un calendrier qui ne rendrait PLUS RIEN
    ferait passer l'interdiction ci-dessous — zéro cellule avant, zéro
    après, « rien n'a été perdu »."""
    with browser_page(base_url, "/") as page_:
        page_.wait_for_selector("html.bz-ready")
        page_.wait_for_timeout(400)
        painted = page_.locator(_CELLS).count()
        assert painted >= 28, (
            f"le calendrier ne peint que {painted} cellule(s) au premier "
            f"rendu — la grille d'un mois en fait 42. Ce n'est pas le "
            f"sujet de cette gate, mais elle ne peut rien prouver sans."
        )


@pytest.mark.browser
def test_the_grid_survives_a_refresh_of_its_zone(base_url) -> None:
    with browser_page(base_url, "/") as page_:
        page_.wait_for_selector("html.bz-ready")
        page_.wait_for_timeout(400)
        before = page_.locator(_CELLS).count()

        for turn in (1, 2):
            page_.click("#bumpbtn")
            page_.wait_for_function(
                f"document.querySelector('#n').textContent.includes('n = {turn}')"
            )
            page_.wait_for_timeout(250)
            after = page_.locator(_CELLS).count()
            assert after == before, (
                f"après {turn} refresh de sa zone, le calendrier n'a plus "
                f"que {after} cellule(s) au lieu de {before}. idiomorph a "
                f"remis ses enfants à la version SERVEUR — c'est-à-dire la "
                f"grille vide — et rien ne l'a re-remplie.\n"
                f"  Le hook est le `bz-effect` de la racine (`rehydrate()`), "
                f"le SEUL qui re-tourne à chaque rescan : `bz-init` est "
                f"one-shot par nœud et le nœud SURVIT au morph."
            )


@pytest.mark.browser
def test_the_client_navigation_survives_the_refresh(base_url) -> None:
    """Le contre-point, et c'est lui qui départage les deux corrections.

    Le mois AFFICHÉ est un état CLIENT : ``_displayedYear`` /
    ``_displayedMonth`` vivent dans le custom element, et le SSR ne
    connaît que le mois initial. Une correction qui aurait fait rendre la
    grille COMPLÈTE au serveur — l'autre sortie envisagée pour ce
    finding — aurait donc réparé le vide en cassant ça : après un refresh,
    la grille peinte par le serveur aurait montré le mois INITIAL pendant
    que l'élément croyait toujours être sur le suivant. DOM et état
    divergents, ce qui est pire que la panne d'origine.

    Ici on repeint depuis l'état de l'élément, donc la navigation tient.
    """
    with browser_page(base_url, "/") as page_:
        page_.wait_for_selector("html.bz-ready")
        page_.wait_for_timeout(400)
        page_.click("#cal [aria-label='Next month']")
        page_.wait_for_timeout(300)
        navigated = page_.get_attribute("#cal", "month")
        assert navigated and not navigated.startswith("2026-08"), (
            f"le clic « mois suivant » n'a pas navigué (month={navigated!r})"
        )

        page_.click("#bumpbtn")
        page_.wait_for_function(
            "document.querySelector('#n').textContent.includes('n = 1')"
        )
        page_.wait_for_timeout(250)

        assert page_.locator(_CELLS).count() >= 28, (
            "la grille a disparu après le refresh — cf. le test précédent."
        )
        assert page_.get_attribute("#cal", "month") == navigated, (
            f"le refresh a ramené le calendrier au mois du SERVEUR "
            f"({page_.get_attribute('#cal', 'month')!r}) alors que "
            f"l'utilisateur avait navigué vers {navigated!r}. Le repaint "
            f"doit partir de l'état de l'ÉLÉMENT, pas du SSR."
        )
