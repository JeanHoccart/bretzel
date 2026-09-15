"""Tout POST émis par le runtime porte le jeton CSRF.

Le middleware CSRF de Bretzel est **toujours** actif et protège chaque
méthode non-sûre, à la seule exception de ``/_bretzel/action/*`` (qui a son
propre HMAC par appel). Un slab qui POSTe sans le header
``X-Bretzel-CSRF`` se fait donc rejeter en 403 par son propre framework.

C'est arrivé, et c'est resté invisible longtemps : le slab file_upload
ouvrait son ``XMLHttpRequest`` sans le header, si bien que
``ui.file_upload(upload_url=…)`` — le mode async documenté — ne pouvait
fonctionner dans AUCUNE application. Le playground le contournait en
n'ayant simplement pas d'endpoint de démo, et `todo.md` avait enregistré
le symptôme (« la CSRF middleware est délibérément always-on sans knob
d'exemption ») comme une fatalité au lieu d'un bug.

La gate est volontairement étroite : elle ne juge PAS l'ensemble du trafic
réseau, seulement les ``xhr.open('POST' …)`` écrits à la main dans les
slabs. C'est là que la classe de bug vit — htmx et le bridge passent tous
deux par ``05_bridge.js``, déjà couvert.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from bretzel.runtime.protocol import HEADER_CSRF

_SRC = Path(__file__).resolve().parents[2] / "bretzel" / "runtime" / "_src"

# ``xhr.open('POST', …)`` / ``.open("POST", …)`` — la forme manuelle.
_POST_OPEN = re.compile(r"""\.open\(\s*['"]POST['"]""", re.I)

# Fenêtre de recherche du header après le ``open`` : le contrat XHR impose
# ``setRequestHeader`` APRÈS ``open`` et AVANT ``send``, donc quelques
# lignes suffisent — et rester serré évite d'accepter un header posé pour
# une toute autre requête plus bas dans le fichier.
_WINDOW_LINES = 12


def _slabs() -> list[Path]:
    return sorted(_SRC.glob("[0-9]*_*.js"))


def test_there_is_at_least_one_manual_post() -> None:
    """Garde-fou : si plus rien ne matche, la gate ne garde plus rien."""
    found = [p.name for p in _slabs() if _POST_OPEN.search(p.read_text(encoding="utf8"))]
    assert found, (
        "Aucun `xhr.open('POST', …)` trouvé dans les slabs — soit le "
        "pattern a changé, soit le dernier POST manuel a disparu. Dans les "
        "deux cas cette gate est devenue aveugle : ajuste-la ou retire-la."
    )


@pytest.mark.parametrize("slab", _slabs(), ids=lambda p: p.name)
def test_manual_post_sets_the_csrf_header(slab: Path) -> None:
    lines = slab.read_text(encoding="utf8").splitlines()
    for i, line in enumerate(lines):
        if not _POST_OPEN.search(line):
            continue
        window = "\n".join(lines[i : i + _WINDOW_LINES])
        assert HEADER_CSRF in window, (
            f"{slab.name}:{i + 1} ouvre un POST manuel sans poser "
            f"`{HEADER_CSRF}` dans les {_WINDOW_LINES} lignes qui suivent.\n"
            f"  Le middleware CSRF rejettera cette requête en 403 — c'est "
            f"le framework qui refuse son propre composant, et le symptôme "
            f"(un 403 sans message) n'accuse jamais le slab.\n"
            f"  Fix : `if ($bz._csrf) xhr.setRequestHeader('{HEADER_CSRF}', "
            f"$bz._csrf);` entre `open` et `send`, comme 05_bridge.js."
        )


def test_the_detector_still_bites() -> None:
    """Mutation : un POST écrit à la main est encore reconnu.

    La gate exige que tout POST manuel pose l'en-tête CSRF. Si la regex
    cessait de matcher, elle passerait sur zéro POST — verte, pendant
    qu'un POST sans en-tête se ferait refuser en production.
    """
    for offending in ("xhr.open('POST', url)", 'x.open( "POST" , u)'):
        assert _POST_OPEN.search(offending), f"{offending!r} devrait mordre"
    for licit in ("xhr.open('GET', url)", "openPost(url)"):
        assert not _POST_OPEN.search(licit), f"{licit!r} : faux positif"
