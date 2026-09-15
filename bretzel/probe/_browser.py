"""Le navigateur — un seul Chromium par processus, un contexte par fenêtre.

Promu depuis ``tests/audit/harness.py`` le 2026-09-10, avec ses mesures.

⚠️ **Un seul ``sync_playwright()`` par processus.** L'API sync de
Playwright n'est pas thread-safe et deux instances dans le même thread
se marchent dessus : mesuré le 2026-08-27, ``-m browser`` est passé de
286 verts à « 1 échec + 75 erreurs » dès qu'un fichier a ouvert le sien
— et il passait toujours quand on le lançait SEUL, ce qui est le pire
des symptômes. C'est la raison pour laquelle ce module porte le singleton, et
pourquoi ``tests/audit/harness.py`` lui délègue au lieu d'en garder un
second.

⚠️ **Ce n'est pas encore une exclusivité de processus** :
``tests/e2e/conftest.py`` ouvre toujours le sien. Sans conflit
aujourd'hui — ``-m e2e`` a son propre créneau — mais la garantie
n'est vraie que des suites qui passent par ici.

Le navigateur est PARTAGÉ, le contexte est NEUF. Mesuré en A/B alterné
dans un seul processus (un avant/après séquentiel ne vaut rien sur cette
machine, qui dérive d'un facteur 2) : navigateur neuf **633 ms** de
médiane, contexte neuf sur un navigateur partagé **408 ms**.

L'isolation ne change pas : cookies, stockage, cache et permissions sont
par CONTEXTE, c'est la garantie de Playwright. Ce qui est partagé, c'est
le processus Chromium — rien de ce qu'un probe peut observer. **C'est
exactement pour ça que ``windows=`` ouvre des contextes et pas des
onglets** : deux onglets d'un même contexte partagent les cookies, donc
la même session, donc un scénario à deux utilisateurs ne mesurerait plus
rien.
"""

from __future__ import annotations

import atexit
import contextlib
from collections.abc import Iterator
from typing import Any

_PW: Any = None
_BROWSER: Any = None


def shared_browser() -> Any:
    """Le Chromium du processus — démarré à la première demande.

    Relance si le navigateur s'est déconnecté : un probe qui le fait
    planter ne doit pas condamner tous les suivants du même processus.
    """
    global _PW, _BROWSER
    from playwright.sync_api import sync_playwright

    if _PW is None:
        _PW = sync_playwright().start()
    if _BROWSER is None or not _BROWSER.is_connected():
        _BROWSER = _PW.chromium.launch(headless=True)
    return _BROWSER


@contextlib.contextmanager
def contexts(
    count: int,
    *,
    size: tuple[int, int],
    headed: bool = False,
    touch: bool = False,
) -> Iterator[list[Any]]:
    """``count`` contextes neufs, fermés ensemble à la sortie.

    ``headed=True`` sort du singleton : on lance un navigateur visible
    pour l'appel et on le referme. Un Chromium visible partagé entre des
    probes headless serait une surprise, pas une optimisation.

    ``touch=True`` ouvre un contexte TACTILE. C'est le seul mode où le
    navigateur applique vraiment ``touch-action`` : sans lui, un test
    qui dispatche des ``PointerEvent`` synthétiques mesure notre code
    et pas la décision du navigateur, donc il reste vert quel que soit
    le ``touch-action`` du composant.
    """
    if headed:
        from playwright.sync_api import sync_playwright

        pw: Any = sync_playwright().start()
        browser = pw.chromium.launch(headless=False)
    else:
        pw = None
        browser = shared_browser()

    opened: list[Any] = []
    try:
        for _ in range(count):
            opened.append(
                browser.new_context(
                    viewport={"width": size[0], "height": size[1]},
                    has_touch=touch,
                    is_mobile=touch,
                )
            )
        yield opened
    finally:
        for ctx in opened:
            with contextlib.suppress(Exception):
                ctx.close()
        if pw is not None:
            with contextlib.suppress(Exception):
                browser.close()
                pw.stop()


@atexit.register
def _close_shared_browser() -> None:
    global _PW, _BROWSER
    with contextlib.suppress(Exception):
        if _BROWSER is not None:
            _BROWSER.close()
    with contextlib.suppress(Exception):
        if _PW is not None:
            _PW.stop()
    _BROWSER = _PW = None
