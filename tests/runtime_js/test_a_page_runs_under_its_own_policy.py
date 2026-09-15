"""Une page Bretzel fonctionne sous la CSP que Bretzel calcule.

C'est LE test qui autorise à livrer la fonctionnalité. Une politique qui
casse le runtime serait pire que pas de politique du tout : elle
donnerait une page morte avec, pour seul indice, une ligne dans la
console du navigateur.

Et c'est un test navigateur PAR NÉCESSITÉ, pas par zèle. Le serveur ne
peut rien en dire : il pose un en-tête, point. Toute la mécanique — les
empreintes qui doivent correspondre aux octets exacts entre les balises,
``'unsafe-eval'`` qui doit couvrir le ``new Function`` du moteur de
directives, ``'unsafe-inline'`` qui doit couvrir les attributs
``style=`` — ne s'évalue QUE dans un navigateur. Un ``TestClient`` qui
lit l'en-tête ne prouve rien.

Le témoin est l'événement DOM ``securitypolicyviolation``, que le
navigateur émet pour chaque ressource refusée. On l'arme AVANT la
navigation (``add_init_script``), sinon les violations du chargement —
justement celles qui comptent — passent avant l'écouteur.
"""

from __future__ import annotations

import pytest

from bretzel import Bretzel, page, ui
from tests.audit.harness import audit_server, browser_page

pytestmark = pytest.mark.browser

_SECRET = "x" * 32

#: Armé avant tout script de la page. Chaque violation est empilée sur
#: ``window.__CSP__`` que le test relit ensuite.
_MOUCHARD = """
window.__CSP__ = [];
document.addEventListener('securitypolicyviolation', (e) => {
  window.__CSP__.push({
    directive: e.effectiveDirective || e.violatedDirective,
    blocked: String(e.blockedURI).slice(0, 120),
    sample: String(e.sample || '').slice(0, 80),
  });
});
"""


def _app(**kwargs) -> Bretzel:
    """Une app qui exerce ce que la politique doit laisser passer.

    Le choix des composants n'est pas décoratif : ``ui.icon`` déclenche
    l'appel sortant d'iconify (``connect-src``), ``ui.dialog`` et
    ``ui.tabs`` font tourner le moteur de directives (``'unsafe-eval'``),
    et le shell pose ses trois scripts inline (les empreintes) et ses
    attributs ``style=`` (``'unsafe-inline'`` sur ``style-src``).
    """
    app = Bretzel(secret_key=_SECRET, mode="dev", **kwargs)

    @page("/")
    def home() -> None:
        ui.icon("lucide:home")
        with ui.tabs(value="a"):
            ui.tab("a", label="A")
            ui.tab("b", label="B")
            with ui.tab_panel("a"):
                ui.text("contenu A")
            with ui.tab_panel("b"):
                ui.text("contenu B")
        with ui.dialog(title="Titre") as boite:
            ui.text("dans la boite")
        ui.button("ouvrir", on_click=boite.open())

    app.include(home)
    return app


def _violations(base_url: str) -> list[dict]:
    with browser_page(base_url, "/", wait_until="load") as p:
        p.wait_for_timeout(1200)
        return p.evaluate("window.__CSP__ || []")


@pytest.fixture
def armed(monkeypatch):
    """``browser_page`` ne sait pas armer un script d'init — on l'ajoute."""
    from tests.audit import harness

    vrai = harness.browser_context

    import contextlib

    @contextlib.contextmanager
    def arme(**kwargs):
        with vrai(**kwargs) as ctx:
            ctx.add_init_script(_MOUCHARD)
            yield ctx

    monkeypatch.setattr(harness, "browser_context", arme)


def test_a_page_raises_no_violation_under_the_policy(armed) -> None:
    """Le versant qui compte : la politique ne casse rien."""
    with audit_server(_app(csp=True)) as base_url:
        vues = _violations(base_url)
    assert vues == [], (
        "La politique que Bretzel calcule bloque ses propres ressources : "
        f"{vues}. Une page livrée comme ça serait morte à l'écran avec "
        "pour seul indice la console."
    )


def test_the_runtime_still_reacts_under_the_policy(armed) -> None:
    """Zéro violation ne suffit pas : une page BLANCHE n'en lève aucune.

    Le plancher de ce fichier — sans lui, casser le rendu rendrait le
    test d'à côté vert.
    """
    with audit_server(_app(csp=True)) as base_url, browser_page(
        base_url, "/", wait_until="load"
    ) as p:
        p.wait_for_timeout(800)
        avant = p.locator("[role=dialog]").count()
        p.get_by_text("ouvrir").click()
        p.wait_for_timeout(400)
        ouvert = p.evaluate(
            "!!document.querySelector('[role=dialog]')?.checkVisibility?.()"
        )
    assert avant >= 1, "le dialogue n'est pas rendu — le montage est cassé"
    assert ouvert, (
        "le dialogue ne s'ouvre pas sous CSP : le moteur de directives "
        "n'a pas pu compiler, donc 'unsafe-eval' ne couvre pas ce qu'il "
        "fait."
    )


def test_a_forged_script_is_refused(armed) -> None:
    """La preuve que la politique MORD, et la raison d'être de tout ça.

    Sans ce versant, une politique vide passerait les deux tests
    au-dessus. On injecte ce qu'une faille XSS injecterait — une balise
    ``<script>`` — et on exige que le navigateur refuse de l'exécuter.
    """
    with audit_server(_app(csp=True)) as base_url, browser_page(
        base_url, "/", wait_until="load"
    ) as p:
        p.wait_for_timeout(600)
        p.evaluate(
            "const s = document.createElement('script');"
            "s.textContent = 'window.__VOLE__ = 1';"
            "document.body.appendChild(s);"
        )
        p.wait_for_timeout(300)
        vole = p.evaluate("window.__VOLE__ === 1")
        vues = p.evaluate("window.__CSP__ || []")
    assert not vole, (
        "un <script> injecté s'est EXÉCUTÉ malgré la CSP — la politique "
        "ne protège de rien."
    )
    assert any(v["directive"].startswith("script-src") for v in vues), (
        f"aucune violation script-src signalée : {vues}"
    )


def test_without_the_policy_the_same_script_runs(armed) -> None:
    """Le contrôle : le montage détecterait-il seulement la différence ?

    Si ce test échouait, le précédent ne prouverait rien — il pourrait
    passer parce que l'injection ne marche pas du tout.
    """
    with audit_server(_app(csp=False)) as base_url, browser_page(
        base_url, "/", wait_until="load"
    ) as p:
        p.wait_for_timeout(600)
        p.evaluate(
            "const s = document.createElement('script');"
            "s.textContent = 'window.__VOLE__ = 1';"
            "document.body.appendChild(s);"
        )
        p.wait_for_timeout(300)
        vole = p.evaluate("window.__VOLE__ === 1")
    assert vole, (
        "l'injection ne marche même pas SANS CSP : le test d'à côté ne "
        "mesure donc pas la protection."
    )
