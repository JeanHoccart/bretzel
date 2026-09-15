# -*- coding: utf-8 -*-
"""Non-regression — un tooltip survit-il a un swap ``@refreshable`` ?

Le panneau d'un tooltip est **teleporte** sous ``<body>`` : il ne vit
donc PAS dans le sous-arbre que le morph remplace. Si le declencheur
reconstruit ne retrouve pas son panneau, celui-ci reste affiche pour
toujours — un rectangle de texte colle a l'ecran que plus rien ne peut
fermer, ni la souris ni le clavier.

C'est une regression reelle, reparee le 2026-08-19. Ce fichier est son
garde-fou : il rougit si le panneau reste ouvert (mesure en
neutralisant ``_hide()`` dans ``$bz.tooltip.scope``).

Deux scenarios, et le second est le seul qui compte :

(a) ligne de base — focus le declencheur, il s'ouvre ; on quitte, il se
    cache. Sans morph. Si (a) rougit, (b) ne dit rien.
(b) LE cas — focus, CLIC (le clic rafraichit la zone ou vit le
    declencheur, donc morph), puis on quitte : il doit se cacher quand
    meme.

Histoire de ce fichier
----------------------
Il a passe un temps indetermine rouge **pour une autre raison** : son
selecteur ``chevron-left`` matchait AUSSI le « Toggle sidebar » de la
coque, qui arrive premier dans le document et ne porte aucun tooltip. Il
mesurait donc un bouton sans tooltip et concluait « ne s'ouvre pas au
focus ». D'ou le controle d'unicite, garde en tete : un selecteur ambigu
se REFUSE, il ne se subit pas.

Puis il a passe vingt-quatre heures MORT : il pilotait ``bench_matrix.py``
sur le port 8974, supprime avec la famille ``/matrix`` le 2026-08-30.
Il lancait un ``sys.executable`` sur un chemin inexistant, attendait
vingt secondes et mourait sur « bench never came up ». Declare en dette
le 2026-08-31, repare le meme jour.

Deux choses ont change en le reparant :

1. Plus de banc a lui. Il monte le playground par ``audit_server()``,
   comme les probes recents — un fichier de moins a garder vivant, et
   c'est precisement le mode de panne qu'on vient de payer.
2. Sa cible est la carte « Dans une zone qui se rafraichit » de
   ``/tooltip``, ajoutee le meme jour. Elle existe parce que ce probe a
   revele qu'AUCUN banc ne montrait un tooltip dans une zone
   rafraichissable — la configuration ordinaire d'une barre d'outils.
   Le trou etait dans le produit, pas seulement dans le test. Le
   scenario d'origine tenait a des boutons chevron construits a la main
   dans le banc matrix, que ``ui.stepper`` ne rend pas (verifie : 0
   ``<button>``, 0 ``chevron-left``) — il n'etait donc pas repointable
   tel quel.

Run :  py tests/probes/probe_tooltip.py
"""

from __future__ import annotations

import sys

#: Le texte du panneau est LU dans la page, jamais recopie ici : deux
#: litteraux divergent, et c'est la copie manuelle qui a tue quatre
#: probes le 2026-08-30.
from examples.playground.features.tooltip import REFRESHED_ZONE_TIP

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

FAILURES: list[str] = []

#: Le declencheur porte un ``id`` explicite. Le probe precedent
#: identifiait le sien par son icone, et l'a paye : un selecteur
#: d'icone matche la coque autant que le contenu.
TRIGGER = "#tip-refresh-trigger"


def check(name: str, cond: bool, detail: str = "") -> None:
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}"
          + (f" — {detail}" if detail else ""))
    if not cond:
        FAILURES.append(f"{name}: {detail}")


def panel_state(page) -> str:
    """``shown`` / ``hidden`` / ``absent`` pour le panneau teleporte.

    On lit ``getComputedStyle``, pas la presence : le panneau EXISTE en
    permanence dans le DOM, cache. Compter les noeuds dirait toujours
    « il est la »."""
    return page.evaluate(
        """(txt) => {
            const ps = [...document.querySelectorAll('[role=tooltip]')]
                .filter(e => (e.textContent || '').includes(txt));
            if (!ps.length) return 'absent';
            return ps.some(e => getComputedStyle(e).display !== 'none')
                ? 'shown' : 'hidden';
        }""",
        REFRESHED_ZONE_TIP,
    )


def panel_count(page) -> int:
    return page.evaluate(
        """(txt) => [...document.querySelectorAll('[role=tooltip]')]
             .filter(e => (e.textContent || '').includes(txt)).length""",
        REFRESHED_ZONE_TIP,
    )


def wait_state(page, wanted: str, timeout: int = 3000) -> bool:
    """Attend l'ETAT, pas un delai.

    Le tooltip a un ``delay`` d'ouverture et une transition de
    fermeture : un ``wait_for_timeout`` fixe soit gaspille, soit mesure
    le milieu de l'animation. Rendre ``False`` plutot que lever laisse le
    ``check`` afficher l'etat REELLEMENT lu."""
    try:
        page.wait_for_function(
            """([txt, want]) => {
                const ps = [...document.querySelectorAll('[role=tooltip]')]
                    .filter(e => (e.textContent || '').includes(txt));
                if (!ps.length) return want === 'absent';
                const shown = ps.some(
                    e => getComputedStyle(e).display !== 'none');
                return (shown ? 'shown' : 'hidden') === want;
            }""",
            arg=[REFRESHED_ZONE_TIP, wanted],
            timeout=timeout,
        )
        return True
    except Exception:
        return False


def main() -> int:
    from tests.audit.harness import audit_server, browser_context

    blur = "() => document.activeElement && document.activeElement.blur()"

    with audit_server() as base:
        with browser_context() as ctx:
            page = ctx.new_page()
            errs: list[str] = []
            page.on("console", lambda m: errs.append(m.text)
                    if m.type == "error" else None)
            page.goto(f"{base}/tooltip", wait_until="networkidle")
            page.wait_for_function(
                "document.documentElement.classList.contains('bz-ready')"
            )

            # Un selecteur qui matche deux fois ne se REPERE pas :
            # Playwright prend le premier et le probe mesure autre chose.
            # On refuse l'ambiguite au lieu de la subir.
            found = page.locator(TRIGGER).count()
            check("le declencheur est identifie sans ambiguite", found == 1,
                  f"{found} noeud(s) matchent {TRIGGER}")
            if found != 1:
                print("\nTOOLTIP PROBE FAILED — selecteur inutilisable.")
                return 1

            print("\n(a) Ligne de base — focus puis blur, SANS morph")
            page.focus(TRIGGER)
            check("le panneau s'ouvre au focus", wait_state(page, "shown"),
                  panel_state(page))
            page.evaluate(blur)
            check("il se cache quand on quitte", wait_state(page, "hidden"),
                  panel_state(page))

            print("\n(b) LE cas — focus, CLIC (morph), puis blur")
            page.focus(TRIGGER)
            check("il se rouvre", wait_state(page, "shown"),
                  panel_state(page))

            avant = page.inner_text("body")
            page.click(TRIGGER)
            # On attend que la ZONE ait vraiment change, sinon le blur
            # qui suit arriverait avant le morph et le probe validerait
            # le scenario (a) une seconde fois.
            page.wait_for_function(
                "(txt) => document.body.innerText !== txt",
                arg=avant, timeout=5000,
            )
            print(f"  panneaux apres le morph : {panel_count(page)} "
                  f"(etat : {panel_state(page)})")

            page.evaluate(blur)
            check("il se cache APRES le morph", wait_state(page, "hidden"),
                  panel_state(page))
            # Le second mode de panne : le morph reconstruit le
            # declencheur, qui se teleporte un SECOND panneau. Le premier
            # n'a alors plus de proprietaire.
            check("aucun panneau en double", panel_count(page) <= 1,
                  f"{panel_count(page)} panneaux portent le meme texte")

            check("aucune erreur console", not errs, "; ".join(errs[:5]))

            page.screenshot(path="tests/probes/tooltip_screenshot.png")

    print()
    if FAILURES:
        print(f"TOOLTIP PROBE FAILED — {len(FAILURES)} rouge(s) :")
        for f in FAILURES:
            print("  -", f)
        return 1
    print("TOOLTIP PROBE PASSED — le panneau suit son scope.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
