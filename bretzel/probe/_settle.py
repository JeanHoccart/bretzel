"""Attendre l'ÉTAT, jamais une durée.

Promu depuis ``tests/audit/interaction.py`` le 2026-09-10, avec sa
mesure : ce helper a remplacé un ``setTimeout(1500)`` inconditionnel le
2026-08-31, qui pesait **88 à 92 % du temps de tout l'audit visuel** —
46 s sur 52 pour ``button``. La suite coûtait 52 minutes, donc elle ne se
lançait jamais, et pendant ce silence deux sélecteurs d'ancrage sont
morts 24 h sans que personne le voie.

⚠️ **Ce n'est pas ``networkidle``, et ça ne peut pas l'être.** Une page
qui porte une zone ``@refreshable(broadcast=[…])`` ouvre un
``EventSource``, donc une connexion HTTP qui ne se ferme jamais :
l'inactivité réseau n'arrive alors JAMAIS et l'attente expire au bout de
30 s (mesuré le 2026-08-15 en montant ``examples/chat``). On regarde
donc les requêtes d'ACTION — le marqueur ``.htmx-request`` que le pont
pose le temps d'un aller-retour — et le silence du DOM.

Deux phases, et la première n'est pas négociable : un contrôle peut
DÉBOUNCER avant de poster, donc rendre la main dès que le DOM est calme
lirait un état périmé et rapporterait « ça ne fait rien » sur quelque
chose qui marche.
"""

from __future__ import annotations

from typing import Any

#: Le plancher couvre un debounce de 300 ms ; le silence de 120 ms
#: déclare le swap retombé. Les deux restent sous le plafond, qui a le
#: dernier mot.
FLOOR_MS = 320
QUIET_MS = 120

_JS = """
async (args) => {
    const t0 = Date.now();
    let last = 0;
    const obs = new MutationObserver(() => { last = Date.now(); });
    obs.observe(document.documentElement, {
        subtree: true, childList: true,
        attributes: true, characterData: true,
    });
    try {
        // Phase 1 — laisser le coup partir : une requête en vol, une
        // mutation, ou l'expiration du plancher.
        while (Date.now() - t0 < args.floor) {
            await new Promise(r => setTimeout(r, 20));
            if (last || document.querySelector('.htmx-request')) break;
        }
        // Phase 2 — attendre le retour au calme, sous plafond.
        while (Date.now() - t0 < args.ceiling) {
            await new Promise(r => setTimeout(r, 20));
            if (document.querySelector('.htmx-request')) continue;
            if (last && Date.now() - last >= args.quiet) return 'SETTLED';
            if (!last && Date.now() - t0 >= args.floor + args.quiet) {
                return 'NOTHING_MOVED';
            }
        }
        return 'TIMEOUT';
    } finally {
        obs.disconnect();
    }
}
"""


def settle_page(page: Any, *, timeout: float, floor: int = FLOOR_MS) -> str:
    """Rend ``SETTLED``, ``NOTHING_MOVED``, ``NAVIGATED`` ou ``TIMEOUT``.

    ``floor=0`` pour une attente qui NE SUIT AUCUN GESTE — un
    redimensionnement, un changement de thème, une navigation qui a
    déjà attendu ``load``. Mesuré le 2026-09-10 en A/B alterné sur la
    même page : **463 ms avec le plancher, 136 ms sans**. Le plancher
    ne paie que derrière un contrôle qui peut débouncer avant de
    poster ; ailleurs il est du sommeil pur, exactement ce que ce
    module existe pour avoir supprimé.

    ``NOTHING_MOVED`` n'est pas une faute : beaucoup de gestes ne
    changent rien à l'écran, et c'est parfois exactement ce qu'on
    mesure (un dépôt refusé qui remet la carte en place).
    """
    args = {"floor": floor, "quiet": QUIET_MS, "ceiling": int(timeout * 1000)}
    try:
        return str(page.evaluate(_JS, args))
    except Exception as exc:
        if "Execution context was destroyed" not in str(exc):
            raise
        # Une NAVIGATION a emporté le document sous l'attente. C'est un
        # calme, pas une panne : le clic a fait ce qu'on lui demandait.
        # Trouvé le 2026-09-10 en montant le premier scénario avec une
        # connexion — un POST de formulaire qui redirige. Aucun probe
        # d'app ne peut éviter ce cas, donc le harnais doit le tenir.
        page.wait_for_load_state("load")
        # Plancher à zéro : le nouveau document vient de se charger, il
        # n'y a aucun debounce en cours à couvrir.
        page.evaluate(_JS, {**args, "floor": 0})
        return "NAVIGATED"
