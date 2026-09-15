"""Le balayage gratuit — ce que personne ne réécrit, donc personne n'oublie.

Il tourne à la sortie du ``with``, sur chaque fenêtre, sans qu'un probe
ait à le demander. La liste vient de
``.claude/bretzel/livrer-une-app.md`` § C et D.

Ce qu'il ne fait PAS, et pourquoi : les probes « couleurs distinctes » et
« tailles distinctes » de ``creating-a-component.md`` § 9 comparent les
VARIANTES d'un composant monté seul. Ils n'ont pas de sens sur une app
assemblée, où il n'y a pas deux variantes à comparer. Ils restent au
harnais de composant ; les prétendre ici en ferait deux lignes vertes qui
ne mesurent rien.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any

from bretzel.probe._window import Window

#: Ce que le balayage sait faire d'un constat. Il reçoit la fonction,
#: pas le ``Probe`` : une politique ne consomme pas l'objet qui
#: l'appelle. Sans ça il fallait un import différé « pour casser un
#: cycle » qui n'existait pas.
Check = Callable[[str, bool, object], None]

#: C1 — « la plus PETITE fenêtre plausible, jamais la plus grande ».
#: Mesurer à 1500×940 valide la taille où tout tient. La seconde taille
#: n'est pas un luxe : le probe du kanban affirmait « toutes les colonnes
#: tiennent » et avait raison, à la sienne.
SECOND_SIZE = (1366, 640)

#: ⚠️ Chaîne BRUTE : le JS ci-dessous porte des expressions
#: régulières, et un ``\s`` interprété par Python arriverait au
#: navigateur en espace littéral — erreur de syntaxe à
#: l'évaluation, donc un balayage qui LÈVE au lieu de mesurer.
_GEOMETRY_JS = r"""
() => {
    const doc = document.documentElement;
    const vw = doc.clientWidth, vh = doc.clientHeight;
    const scrollers = [];
    const clipped = [];
    for (const el of document.querySelectorAll('*')) {
        const st = getComputedStyle(el);
        const deborde = el.scrollHeight > el.clientHeight + 1
            && el.clientHeight > 0;
        if (/auto|scroll/.test(st.overflowY) && deborde) {
            const r = el.getBoundingClientRect();
            scrollers.push({
                tag: el.tagName.toLowerCase(),
                cls: (el.getAttribute('class') || '').slice(0, 60),
                bottom: Math.round(r.bottom),
            });
        }
        // Coupé POUR DE BON : ni barre de défilement, ni recours. La
        // marge de 2 px écarte les arrondis sous-pixel d'une ligne de
        // texte, qui ne cachent rien.
        if (/hidden|clip/.test(st.overflowY)
            && el.clientHeight > 0
            && el.scrollHeight > el.clientHeight + 2
            && el.offsetParent !== null) {
            clipped.push({
                tag: el.tagName.toLowerCase(),
                cls: (el.getAttribute('class') || '').slice(0, 40),
                haut: el.clientHeight,
                faut: el.scrollHeight,
                texte: (el.innerText || '').split('\n')[0].slice(0, 30),
            });
        }
    }
    return {
        overflowX: Math.max(0, doc.scrollWidth - vw),
        documentScrolls: doc.scrollHeight > vh + 1,
        viewport: [vw, vh],
        scrollers: scrollers.slice(0, 12),
        clipped: clipped.slice(0, 8),
    };
}
"""

_TAB_JS = """
() => {
    const el = document.activeElement;
    if (!el || el === document.body) return null;
    const r = el.getBoundingClientRect();
    return {
        tag: el.tagName.toLowerCase(),
        x: Math.round(r.x), y: Math.round(r.y),
        w: Math.round(r.width), h: Math.round(r.height),
        closed: el.closest('[data-bz-overlay][data-open="false"]') !== null,
    };
}
"""


def sweep(
    windows: Sequence[Window],
    size: tuple[int, int],
    check: Check,
) -> None:
    """Mesure chaque fenêtre, à deux tailles et dans les deux thèmes.

    Trois attentes ont été retirées le 2026-09-10, mesurées en A/B
    alterné dans un seul processus : le premier ``resize`` remettait
    la fenêtre à la taille qu'elle avait déjà (463 ms de plancher pour
    rien), et les deux bascules de thème ne mutent aucun DOM — une
    capture se synchronise seule sur le rendu. ~1,75 s par fenêtre.
    """
    for window in windows:
        # Une seule fois, pour absorber ce que le scénario a laissé en
        # vol. Les attentes qui suivent ne suivent AUCUN geste, donc
        # elles n'ont pas de plancher à payer.
        window.settle(timeout=2.0)
        _errors_and_requests(check, window)
        _tab_order(check, window)

        _geometry(check, window, f"taille-1 {size[0]}×{size[1]}")
        window.resize(SECOND_SIZE)
        window.settle(timeout=2.0, floor=0)
        _geometry(check, window, f"taille-2 {SECOND_SIZE[0]}×{SECOND_SIZE[1]}")
        window.resize(size)

        # C4 — le clair d'abord : c'est celui que l'auteur qui code en
        # sombre ne regarde jamais.
        for theme in ("light", "dark"):
            window.page.emulate_media(color_scheme=theme)
            window.shot(theme)


def _errors_and_requests(check: Check, window: Window) -> None:
    check(
        f"[{window.name}] aucune erreur JS",
        not window.errors,
        window.errors[:3],
    )
    check(
        f"[{window.name}] aucune requête en échec",
        not window.broken,
        window.broken[:3],
    )
    check(
        f"[{window.name}] aucun avertissement de console",
        not window.console,
        window.console[:3],
    )


def _geometry(check: Check, window: Window, label: str) -> None:
    geo: dict[str, Any] = window.page.evaluate(_GEOMETRY_JS)
    check(
        f"[{window.name}] {label} — la page ne déborde pas latéralement",
        geo["overflowX"] == 0,
        f"{geo['overflowX']} px de trop",
    )
    if not geo["documentScrolls"]:
        # Document GELÉ : toute région qui défile doit finir AU-DESSUS du
        # bord. Une région qui déborde par le bas n'a rien pour la
        # rattraper — le kanban a payé ça avec 878 px dans un cadre de 591.
        below = [s for s in geo["scrollers"] if s["bottom"] > geo["viewport"][1] + 1]
        check(
            f"[{window.name}] {label} — les régions finissent au-dessus du bord",
            not below,
            below[:3],
        )
    # C5 — ce qui est COUPÉ, et qui n'a pas de barre pour le rattraper.
    #
    # ⚠️ **Le débordement et le rognage ne sont pas la même faute.** Les
    # deux constats du dessus mesurent ce qui SORT — d'une page, d'une
    # région. Celui-ci mesure ce qui reste DEDANS et ne se peint pas : une
    # boîte à hauteur imposée sur laquelle un thème pose
    # ``overflow:hidden`` garde son contenu dans le DOM et n'en montre
    # qu'une partie. Aucune erreur, aucune requête en échec, un HTML
    # complet et juste — c'est le mode d'échec le plus coûteux d'un écran,
    # parce qu'on ne peut pas savoir qu'on regarde une information
    # manquante.
    #
    # Mesuré sur ``examples/ecole`` le 2026-09-12 : une case d'emploi du
    # temps affichait sa classe et rien d'autre, la salle et le lien vers
    # le cahier coupés net. Le compte de l'auteur — « deux lignes plus le
    # cadre » — s'est trompé TROIS fois de suite, parce que la hauteur
    # s'écrit dans l'app et le rembourrage dans un thème de composant, et
    # que leur somme ne vit nulle part.
    #
    # Le coût est nul : la boucle du dessus existait déjà.
    check(
        f"[{window.name}] {label} — rien n'est coupé sans recours",
        not geo["clipped"],
        geo["clipped"][:3],
    )


def _tab_order(check: Check, window: Window) -> None:
    """Où la tabulation atterrit — et où elle n'a rien à faire.

    Le hors-écran ne suffit pas. Un ``ui.dialog`` fermé est CENTRÉ : ses
    champs sont pile au milieu du viewport, donc un contrôle joignable
    dans un dialogue fermé passait ce balayage en vert. Mesuré le
    2026-09-07 sur ``examples/messagerie``, où la 2ᵉ tabulation de la
    page tombait dans un dépôt de fichier invisible.

    Le marqueur visé (``data-bz-overlay``) est celui des overlays MODAUX
    — ``dialog`` et ``drawer``. Les ancrés (``popover``, ``dropdown``) se
    ferment en ``display:none``, donc rien ne peut y prendre le focus et
    il n'y a rien à mesurer ; le jour où l'un d'eux passerait à
    ``visibility`` pour animer sa sortie, c'est la gate composant
    (``test_a_closed_overlay_is_out_of_the_tab_order``) qui le dirait,
    pas ce balayage.
    """
    reached = False
    offscreen: list[dict[str, Any]] = []
    in_closed: list[dict[str, Any]] = []
    vw, vh = window.page.evaluate(
        "() => [document.documentElement.clientWidth, "
        "document.documentElement.clientHeight]"
    )
    for _ in range(20):
        window.press("Tab")
        focused = window.page.evaluate(_TAB_JS)
        if focused is None:
            break
        reached = True
        if focused["closed"]:
            in_closed.append(focused)
        if focused["w"] == 0 and focused["h"] == 0:
            continue  # un contrôle volontairement invisible, pas une faute
        if (
            focused["x"] + focused["w"] < 0
            or focused["y"] + focused["h"] < 0
            or focused["x"] > vw
            or focused["y"] > vh
        ):
            offscreen.append(focused)
    check(
        f"[{window.name}] la tabulation atteint quelque chose",
        reached,
        "aucun élément focusable",
    )
    check(
        f"[{window.name}] la tabulation ne sort pas de l'écran",
        not offscreen,
        offscreen[:3],
    )
    check(
        f"[{window.name}] la tabulation n'entre pas dans un overlay fermé",
        not in_closed,
        in_closed[:3],
    )
