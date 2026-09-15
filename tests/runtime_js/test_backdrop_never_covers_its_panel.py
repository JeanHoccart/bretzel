"""Gate : un fond assombri ne recouvre JAMAIS le panneau qu'il accompagne.

Trois composants déclarent la même recette de fond —
``fixed inset-0 z-40 bg-black/50 backdrop-blur-sm`` : ``ui.dialog``,
``ui.drawer`` et ``ui.sidebar(collapsible="overlay")``. Chacun met son
panneau à ``z-50`` et en déduit qu'il passe devant.

**Cette déduction n'est vraie que si les deux vivent dans le MÊME contexte
d'empilement.** Un ``z-index`` ne se compare qu'entre frères de contexte ;
il ne traverse pas une frontière. Et toute app Bretzel en crée une : le
shell recommandé est ``fixed inset-0`` (``traps.md`` § *Shell layout
h-screen*), et ``position: fixed`` crée un contexte d'empilement. Un
panneau à ``z-50`` posé DEDANS est donc enfermé dedans — face à un fond
téléporté sous ``<body>`` à ``z-40``, la comparaison réelle devient
« shell (``z-auto``) contre fond (``z-40``) », et le fond gagne.

Mesuré le 2026-08-15 sur ``examples/chat`` : sidebar ouverte en mode
overlay, ``elementFromPoint`` au centre de l'aside renvoie **le fond**, et
son ``backdrop-filter: blur(8px)`` floute la sidebar elle-même en plus de
la page. Le docstring de ``_render_backdrop`` affirmait l'inverse — « sous
``<body>`` il est un frère, et son ``z-40`` le range derrière la
sidebar » — vrai seulement quand l'aside est lui aussi enfant direct de
``<body>``, ce qu'aucun shell réel ne fait.

Pourquoi une gate NAVIGATEUR et pas une lecture de classes : le défaut
n'est visible dans aucun HTML. Les deux classes sont exactement celles
qu'on attend (``z-50`` / ``z-40``), les deux nœuds sont présents, et le
CSS est correct. Seule la composition — qui peint au-dessus de qui — ment.
C'est ``elementFromPoint`` qui tranche, rien d'autre.

Elle est écrite pour SURVIVRE à la refonte de la sidebar : elle ne connaît
ni le nom des slots ni la forme du DOM, elle plante un marqueur dans le
panneau et demande au navigateur qui est peint à cet endroit.

Run : ``py -m pytest tests/runtime_js/test_backdrop_never_covers_its_panel.py -q -m browser``
"""

from __future__ import annotations

import pytest

from bretzel import Bretzel, layout, page, ui
from tests.audit.harness import audit_server, browser_page

pytestmark = pytest.mark.browser

_MARKER = "bz-panel-probe"

#: Qui est peint à l'endroit du marqueur ? On interroge le NAVIGATEUR au
#: centre du marqueur : si le résultat ne contient pas le marqueur, c'est
#: qu'un autre nœud est passé devant.
_WHO_IS_ON_TOP = """(MARKER) => {
    const mark = document.getElementById(MARKER);
    if (!mark) return {ok: false, why: 'marqueur absent du DOM'};
    const r = mark.getBoundingClientRect();
    if (r.width === 0 || r.height === 0) {
        return {ok: false, why: 'marqueur de taille nulle (panneau fermé ?)'};
    }
    const hit = document.elementFromPoint(r.left + r.width / 2,
                                          r.top + r.height / 2);
    const backdrop = document.querySelector('[class*="backdrop-blur"]');
    return {
        ok: true,
        covered: !(hit === mark || mark.contains(hit) || hit.contains(mark)),
        hit: hit ? hit.tagName.toLowerCase() + ' .'
             + String(hit.className).slice(0, 44) : null,
        backdropPresent: !!backdrop,
        backdropParent: backdrop ? backdrop.parentElement.tagName.toLowerCase()
                        : null,
    };
}"""


def _build_probe_app() -> Bretzel:
    """Une app minimale, avec le shell ``fixed inset-0`` du dépôt.

    ⚠️ Le ``fixed`` du shell n'est PAS décoratif : c'est LUI qui crée la
    frontière de contexte d'empilement, donc la condition du défaut.

    Vérifié par mutation le 2026-08-15, et c'est ce qui fait passer le
    diagnostic de « je pense » à « c'est mesuré » : en remplaçant ce
    ``fixed inset-0`` par ``h-screen``, le cas sidebar passe **XPASS** —
    le fond cesse de recouvrir l'aside. Le défaut n'existe donc que
    lorsqu'un ancêtre ouvre un contexte d'empilement, ce que fait chaque
    shell réel du dépôt. Ne pas « simplifier » ce shell en croyant qu'il
    est du décor : ce serait rendre la gate aveugle sans qu'elle rougisse.
    """
    app = Bretzel(secret_key="s" * 32, mode="dev")

    @layout
    def shell() -> None:
        with ui.hstack(classes="fixed inset-0 w-full overflow-hidden"):
            ui.outlet(classes="flex-1 min-h-0 flex flex-col")

    @page("/dialog", layout=shell)
    def dialog_page() -> None:
        with ui.dialog(open=True, title="sonde"):
            ui.text("contenu", id=_MARKER)

    @page("/drawer", layout=shell)
    def drawer_page() -> None:
        with ui.drawer(open=True, title="sonde"):
            ui.text("contenu", id=_MARKER)

    @page("/sidebar", layout=shell)
    def sidebar_page() -> None:
        with ui.sidebar(collapsible="overlay", open=True):
            ui.sidebar_title("sonde")
            with ui.sidebar_section(label="X"):
                ui.sidebar_item("contenu", icon="dot", href="/sidebar",
                                id=_MARKER)
        # ``check_sidebars_are_reachable`` (a0cbab3f) refuse une barre
        # ``overlay`` sans moyen de la rouvrir, et elle a raison : ce
        # ``open=True`` est un littéral, donc rien ne la rouvre une fois
        # fermée. Le déclencheur est HORS de l'aside, il ne touche donc
        # ni au contexte d'empilement ni au point de hit-test.
        # ``toggle_page`` ci-dessous exerce l'autre échappatoire
        # (``sb.toggle()``) — les deux sont couvertes.
        ui.sidebar_trigger()

    @page("/toggle", layout=shell)
    def toggle_page() -> None:
        """Sidebar FERMÉE + le bouton qui l'ouvre — le chemin impératif."""
        sb = ui.sidebar(collapsible="overlay", open=False)
        with sb:
            ui.sidebar_title("sonde")
            with ui.sidebar_section(label="X"):
                ui.sidebar_item("contenu", icon="dot", href="/toggle",
                                id=_MARKER)
        ui.button("ouvrir", on_click=sb.toggle(), id="bz-toggle-probe")

    app.include(shell, dialog_page, drawer_page, sidebar_page, toggle_page)
    return app


_APP = _build_probe_app()


def _measure(path: str) -> dict:
    with audit_server(_APP) as base_url:
        # ``wait_until="load"`` : une page portant un overlay peut tenir une
        # connexion ouverte, et ``networkidle`` n'arriverait jamais.
        with browser_page(base_url, path, wait_until="load") as browser:
            browser.wait_for_timeout(600)  # laisser les transitions finir
            return browser.evaluate(_WHO_IS_ON_TOP, _MARKER)


@pytest.mark.parametrize("component", ["dialog", "drawer", "sidebar"])
def test_the_panel_stays_above_its_backdrop(component: str) -> None:
    """Les trois gardent leur fond et leur panneau VOISINS.

    Aucun ne téléporte son fond : les deux nœuds naissent au même
    endroit, donc dans le même contexte d'empilement, donc ``z-50`` >
    ``z-40`` s'applique pour de vrai.

    ``ui.sidebar`` a rejoint les deux autres le 2026-08-15. Elle
    téléportait son fond sous ``<body>`` et se retrouvait recouverte par
    lui ; elle a maintenant la structure de ``ui.dialog`` — une racine
    ``display:contents`` qui ne crée aucun contexte, portant le scope et
    les deux frères. Trois composants, une seule façon de faire.
    """
    m = _measure(f"/{component}")
    assert m["ok"], m.get("why")
    assert m["backdropPresent"], (
        f"{component} ouvert ne rend aucun fond assombri — la gate ne "
        "mesure rien. Vérifier que `open=True` ouvre bien le composant."
    )
    assert not m["covered"], (
        f"Le fond de {component} est peint AU-DESSUS de son propre "
        f"panneau (elementFromPoint → {m['hit']}).\n\n"
        "Un z-index ne se compare qu'entre frères de contexte "
        "d'empilement. Si le fond et le panneau ne vivent pas dans le "
        "même, leurs z-index ne se parlent pas — et le shell `fixed "
        "inset-0` de toute app Bretzel crée cette frontière."
    )


def test_the_imperative_toggle_actually_opens_the_panel() -> None:
    """Le bouton ouvre-t-il VRAIMENT le menu ? Personne ne le vérifiait.

    ``sb.toggle()`` compile en
    ``document.getElementById('<id>').dispatchEvent(new CustomEvent(
    'bz-toggle'))``. Tout repose donc sur l'unicité de cet ``id`` — et
    ``getElementById`` renvoie le PREMIER nœud qui le porte.

    Mesuré le 2026-08-15 : en donnant une racine ``display:contents`` à la
    sidebar, le socle a estampillé l'``id`` du composant sur cette racine
    (``_stamp_scope_id`` le fait pour tout hôte de ``bz-data`` sans ``id``)
    alors que l'aside le portait déjà. L'événement partait sur le wrapper,
    qui n'a pas l'écouteur. **Le hamburger est devenu inerte** — signalé
    deux fois à l'écran, et aucune gate ne l'a vu : celle des ``bz-id`` ne
    couvre pas les ``id``, celle du fond ne mesure que l'empilement, et
    rien nulle part ne CLIQUAIT.

    D'où ce test, qui clique. Il double la gate statique
    (``test_page_has_no_duplicate_html_id``) à dessein : celle-là attrape
    la cause connue, celui-ci attrape le symptôme quelle qu'en soit la
    cause — un écouteur non branché, un scope perdu, un id renommé.
    """
    with audit_server(_APP) as base_url:
        with browser_page(base_url, "/toggle", wait_until="load") as browser:
            browser.wait_for_timeout(600)
            def data_open() -> str:
                return browser.evaluate(
                    "() => document.querySelector('aside')"
                    ".getAttribute('data-open')"
                )

            assert data_open() == "false", (
                "la sonde doit démarrer FERMÉE, sinon elle ne mesure rien"
            )

            browser.click("#bz-toggle-probe", force=True)
            browser.wait_for_timeout(600)

            assert data_open() == "true", (
                "Le bouton impératif n'ouvre pas le panneau. Vérifier "
                "d'abord qu'UN SEUL nœud porte l'id du composant : "
                "`document.getElementById` renvoie le premier, et si "
                "l'écouteur `bz-on:bz-toggle` est sur l'autre, le contrôle "
                "est inerte sans rien signaler."
            )
            assert browser.evaluate(
                "() => Math.round(document.querySelector('aside')"
                ".getBoundingClientRect().left)"
            ) == 0, "l'état a basculé mais le panneau n'a pas glissé à l'écran"
