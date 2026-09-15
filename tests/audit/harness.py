"""Test harness — single uvicorn server in a thread + Playwright page
factory + per-component navigation helpers.

Pattern :

.. code-block:: python

    from tests.audit.harness import audit_server, browser_page

    with audit_server() as base_url:
        with browser_page(base_url, "/button") as page:
            # run probes...
            assert ...

The server starts on a free port, hosts the full ``examples/playground``
app, and shuts down cleanly when the context exits. Browser uses
Chromium headless on a fixed 1400x900 viewport so visual probes are
deterministic.
"""

from __future__ import annotations

import contextlib
from collections.abc import Iterator
from typing import Any

from playwright.sync_api import Page

from bretzel.probe._browser import contexts as probe_contexts
from bretzel.probe._server import serve as probe_serve


# ───────────────────────────────────────────────────────────────────────
# Le navigateur est PARTAGÉ par tout le processus
# ───────────────────────────────────────────────────────────────────────
#
# ``browser_page`` ouvrait un ``sync_playwright()`` + un
# ``chromium.launch()`` À CHAQUE APPEL. Ses 120 sites d'appel dans 48
# fichiers payaient donc un démarrage de Chromium complet par page —
# 284 démarrages pour ``-m browser`` + ``-m audit`` réunis.
#
# Mesuré le 2026-08-27 en A/B ALTERNÉ dans un seul processus (un
# avant/après séquentiel ne vaut rien sur cette machine, qui dérive d'un
# facteur 2) : navigateur neuf **633 ms** de médiane, contexte neuf sur
# un navigateur partagé **408 ms**. Soit 225 ms par appel, ~64 s sur les
# deux suites.
#
# ⚠️ L'isolation ne change pas. Elle vivait déjà dans le ``new_context``
# — cookies, storage, cache, permissions sont par CONTEXTE, c'est la
# garantie de Playwright. Ce qui est partagé, c'est le processus
# Chromium, rien de ce qu'un test peut observer.
#
# L'API sync de Playwright n'est pas thread-safe : ce singleton suppose
# un seul thread pilote par processus, ce qui est le cas (pytest est
# séquentiel, et sous ``xdist`` chaque worker est un PROCESSUS, donc a
# le sien).
def _shared_browser() -> Any:
    """Le Chromium du processus — DÉLÉGUÉ à ``bretzel.probe``.

    ⚠️ Ce corps a été remplacé par une délégation le 2026-09-10, et ce
    n'est pas de l'esthétique. ``bretzel.probe`` porte désormais le même
    singleton, promu d'ici ; en garder un second dans ce module ferait
    exactement ce que le bloc ci-dessus interdit — deux
    ``sync_playwright()`` dans un thread — dès qu'un seul processus
    pytest touche aux deux. Le mode d'échec est connu et il est le pire
    possible : vert quand on lance le fichier seul.
    """
    from bretzel.probe._browser import shared_browser

    return shared_browser()


@contextlib.contextmanager
def browser_context(
    *,
    viewport: tuple[int, int] = (1400, 900),
    touch: bool = False,
) -> Iterator[Any]:
    """Un contexte NEUF sur le navigateur partagé — l'unité d'isolation.

    À utiliser quand un test pilote PLUSIEURS pages et n'a donc pas
    l'usage de :func:`browser_page` (qui navigue une fois puis rend la
    main).

    ⚠️ **Ne rouvre jamais ``sync_playwright()`` toi-même dans un test.**
    Un second Playwright dans le même thread entre en conflit avec le
    singleton de ce module : mesuré le 2026-08-27, ``-m browser`` est
    passé de 286 verts à « 1 échec + 75 erreurs » dès qu'un fichier a
    ouvert le sien — et il passait toujours quand on le lançait SEUL,
    ce qui est le pire des symptômes.
    """
    with probe_contexts(1, size=viewport, touch=touch) as opened:
        yield opened[0]


# La fermeture à la sortie du processus appartient elle aussi à
# ``bretzel.probe._browser`` : deux ``atexit`` sur le même navigateur se
# battraient pour le fermer.

# Spinning the playground import here avoids a circular import at
# module load time (the playground imports back into bretzel components).
import examples.playground.app.routes  # noqa: F401 — side-effect imports
import examples.playground.main as _playground_main


@contextlib.contextmanager
def audit_server(app: object | None = None) -> Iterator[str]:
    """Spin a uvicorn server on a free port, hosting ``app``.

    Yields the base URL (``"http://127.0.0.1:<port>"``) for the
    duration of the ``with`` block. The server shuts down cleanly on
    exit.

    ``app`` défaut = l'app du playground, ce que font les 20+ appelants
    historiques. Le paramètre existe pour les tests navigateur dont le
    sujet n'est PAS un composant — une propriété du transport, par
    exemple — et qui servent leur propre app minimale plutôt que
    d'ajouter une page au playground. Sans lui, le premier de ces tests
    a recopié ce corps de huit lignes en important deux privés d'ici.
    """
    # DÉLÉGUÉ à ``bretzel.probe._server`` le 2026-09-10, comme le
    # navigateur au-dessus. Ce corps était une copie ligne pour ligne de
    # ``_ThreadServer`` — au détail près qui compte : celui d'ici ne
    # LEVAIT jamais, il dormait 0,5 s de plus et rendait la main en
    # espérant. Un serveur pas prêt donnait donc un probe rouge sur la
    # page, pas sur la cause.
    with probe_serve(_playground_main.app if app is None else app,
                     mode="thread") as (base_url, _app):
        yield base_url


@contextlib.contextmanager
def browser_page(
    base_url: str,
    path: str,
    *,
    viewport: tuple[int, int] = (1400, 900),
    wait_until: str = "networkidle",
    touch: bool = False,
) -> Iterator[Page]:
    """Open a Playwright headless Chromium page navigated to ``path``.

    The page settles on ``networkidle`` before yielding so probes don't
    race the htmx settle. Console / page errors are surfaced via
    print so subagents see them.

    ⚠️ **``wait_until="load"`` est OBLIGATOIRE sur une page temps-réel.**
    Une page qui porte une zone ``@refreshable(..., broadcast=[…])`` ouvre
    un ``EventSource``, donc une connexion HTTP qui ne se ferme jamais :
    ``networkidle`` n'arrive alors JAMAIS et ``page.goto`` expire au bout
    de 30 s. Mesuré le 2026-08-15 en montant ``examples/chat`` — le défaut
    convient à toutes les pages qui se posent, et il faut le désarmer pour
    celles qui écoutent. Le ``wait_for_timeout(600)`` qui suit reste le
    filet commun aux deux cas.

    ``touch=True`` ouvre un contexte TACTILE (``has_touch``,
    ``is_mobile``) — le seul mode où le navigateur applique vraiment
    ``touch-action``. Sans lui, un test qui dispatche des
    ``PointerEvent`` synthétiques mesure notre code et **pas** la
    décision du navigateur : il reste vert quel que soit le
    ``touch-action`` du composant, donc il ne peut rien dire d'un geste
    qui se bat avec le défilement. Ajouté le 2026-08-21 pour le finding
    [27] (une carte déplaçable qui interdisait tout défilement au doigt).
    """
    # Navigateur PARTAGÉ, contexte NEUF — cf. le bloc en tête de module.
    # C'est le contexte qui isole, et il reste par appel.
    with browser_context(viewport=viewport, touch=touch) as ctx:
        page = _wire_page(ctx.new_page())
        page.goto(
            base_url.rstrip("/") + path, wait_until=wait_until,  # type: ignore[arg-type]
        )
        page.wait_for_timeout(600)
        yield page


def _wire_page(page: Page) -> Page:
    # Surface JS errors — they often hint at the real bug.
    #
    # ⚠️ Ces deux ``print`` NE FONT QU'IMPRIMER, et ça a coûté : 178
    # exceptions JS ont vécu deux jours dans la sortie capturée par
    # pytest, que personne ne lit tant qu'un test ne tombe pas. C'est
    # ``tests/runtime_js/test_no_page_throws_on_load.py`` qui ASSERTE,
    # depuis le 2026-08-27 ; ici on ne fait qu'aider au diagnostic.
    page.on("pageerror", lambda err: print(
        f"[probe pageerror] {err}",
    ))
    page.on("console", lambda msg: (
        print(f"[probe console.{msg.type}] {msg.text}")
        if msg.type in ("error", "warning") else None
    ))
    return page
