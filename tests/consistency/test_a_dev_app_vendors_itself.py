"""Une app en DEV rapatrie ses scripts tiers, sans qu'on le lui demande.

Ce que cette gate ferme
-----------------------

Le rapatriement (``bretzel.render.vendor``) existait depuis le
2026-08-27, et il ne se faisait QUE sur commande —
``python -m bretzel.render.vendor``. Donc le repli CDN était la règle
pour tout le monde sauf pour qui savait que la commande existe : quatre
scripts chez deux CDN à chaque page, plus les glyphes chez trois hôtes
Iconify.

Ça s'est payé ailleurs que sur le confort. Les 84 probes tournent en
dev : la fiabilité de la suite entière tenait à unpkg.com, et sa rouge se
déplaçait d'un probe à l'autre sans jamais parler du code (mesuré le
2026-09-13 : CDN coupé, l'encre d'un bouton passe de ``oklab(…)`` à
``rgb(0, 0, 0)``).

Ce que la gate vérifie, et dans les deux sens
----------------------------------------------

- **dev rapatrie**, une fois, au premier appel ASGI ;
- **la prod ne décide rien** — sortir du réseau au démarrage d'un serveur
  serait une surprise, et c'est une décision d'exploitant ;
- **un échec n'arrête rien** : sans réseau, l'app démarre quand même et
  la page retombe sur le CDN, ce qui est le comportement d'avant.

Le versant prod et le versant échec comptent autant que le premier : une
gate qui ne vérifierait que « dev télécharge » laisserait passer les deux
régressions les plus chères — une prod qui se met à sortir du réseau, et
un démarrage qui casse chez qui n'a pas internet.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from bretzel import Bretzel

#: Preuve de morsure ET plancher de non-vacuité : les trois contrôles
#: ci-dessous observent un EFFET DE BORD. Si ``__call__`` cessait
#: d'appeler le rapatriement, le versant « la prod s'abstient » passerait
#: quand même — vert sur rien. Celui-là prouve que le chemin est emprunté.
MUTATION_PROOF = "test_the_harness_is_not_blind"


def app_for(mode: str) -> Bretzel:
    return Bretzel(secret_key="k" * 32, mode=mode)


async def _first_asgi_call(app: Bretzel) -> None:
    """Le premier appel ASGI, réduit à ce qui déclenche le montage.

    On ne passe PAS par ``TestClient`` : il ferait tourner le lifespan
    entier — état, SSE, routes — pour observer une ligne. Ici le corps de
    ``__call__`` suffit, et ce qu'il délègue ensuite est remplacé.
    """
    app.fastapi = _AvaleTout()  # type: ignore[assignment]
    await app({"type": "lifespan"}, _rien, _rien)


class _AvaleTout:
    """Un faux ASGI qui accepte tout ce qu'on lui demande.

    ``build_middleware_stack`` tourne juste après le crochet et parle au
    vrai ``fastapi`` (``add_middleware``…). Un double qui ne répondrait
    qu'à ``__call__`` ferait échouer les contrôles sur une raison qui n'a
    rien à voir avec leur sujet.
    """

    async def __call__(self, *a: Any, **k: Any) -> None:
        return None

    def __getattr__(self, _nom: str) -> Any:
        return lambda *a, **k: None


async def _rien() -> dict[str, str]:
    return {"type": "lifespan.startup"}


def test_a_dev_app_vendors_on_its_first_call(monkeypatch: pytest.MonkeyPatch) -> None:
    """Le versant qui AGIT."""
    appels: list[str] = []
    monkeypatch.setattr(
        "bretzel.render.ensure_vendored", lambda: appels.append("fait") or True
    )
    asyncio.run(_first_asgi_call(app_for("dev")))
    assert appels == ["fait"], (
        "une app de dev n'a pas rapatrié ses scripts tiers : ses pages "
        "iront les chercher chez unpkg et chez Iconify, à chaque "
        "chargement, et une suite de probes en dépendra."
    )


def test_a_prod_app_decides_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    """Le versant qui S'ABSTIENT — il compte autant.

    Un serveur de production qui sort du réseau à son démarrage est une
    surprise, et le rapatriement y reste une décision d'exploitant
    (``python -m bretzel.render.vendor``, qui vaut encore plus là-bas :
    644 ms → 110 ms de ``DOMContentLoaded``, mesuré le 2026-08-27).
    """
    appels: list[str] = []
    monkeypatch.setattr(
        "bretzel.render.ensure_vendored", lambda: appels.append("fait") or True
    )
    asyncio.run(_first_asgi_call(app_for("prod")))
    assert not appels, (
        "une app de PROD est sortie du réseau à son démarrage. C'est une "
        "décision d'exploitant, pas un défaut du framework."
    )


def test_a_failure_never_stops_the_app(monkeypatch: pytest.MonkeyPatch) -> None:
    """Le versant le plus cher : sans réseau, l'app démarre quand même.

    C'est la promesse écrite du module vendor — « le repli est la règle,
    pas l'exception ». Une app qui refuserait de démarrer parce qu'un
    cache de confort manque serait une régression bien pire que le CDN.
    """
    def _explose() -> bool:
        raise OSError("pas de réseau")

    monkeypatch.setattr("bretzel.render.ensure_vendored", _explose)
    with pytest.raises(OSError):
        _explose()  # le double garde la mutation honnête : il lève bien
    asyncio.run(_first_asgi_call(app_for("dev")))


def test_the_harness_is_not_blind() -> None:
    """Preuve de morsure : sans le crochet, les tests ci-dessus sont vides.

    Ils observent un effet de bord ; si ``__call__`` cessait d'appeler le
    rapatriement, ``appels`` resterait vide et
    :func:`test_a_prod_app_decides_nothing` passerait **quand même**. Le
    seul contrôle qui les rend honnêtes est celui-ci : le chemin existe et
    il est emprunté.
    """
    app = app_for("dev")
    assert hasattr(app, "_vendor_third_party"), (
        "``Bretzel._vendor_third_party`` a disparu — les contrôles de ce "
        "fichier observent alors un effet de bord que plus personne ne "
        "produit, et ils sont verts sur rien."
    )
    vu: list[str] = []
    app._vendor_third_party = lambda: vu.append("appele") or _done()  # type: ignore[assignment]
    asyncio.run(_first_asgi_call(app))
    assert vu == ["appele"], (
        "``__call__`` ne passe plus par ``_vendor_third_party`` : le "
        "rapatriement automatique est débranché."
    )


def _done() -> Any:
    async def _noop() -> None:
        return None

    return _noop()
