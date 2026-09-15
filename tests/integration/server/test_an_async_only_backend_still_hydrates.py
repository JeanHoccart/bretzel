"""Un backend qui ne se lit qu'en ``await`` hydrate quand même l'état.

**C'est la suite qui n'existait pas, et son absence n'était pas un test
oublié : c'était un chemin qu'aucun test ne POUVAIT prendre.**
``MemoryBackend`` expose ``load_sync``, donc les 16 980 verts du dépôt
passaient tous par la lecture synchrone. Redis, lui, ne lit que par
``await`` — et ``MyState()`` est un constructeur, qui ne peut pas
attendre. Le framework rendait donc les valeurs par DÉFAUT, en silence ;
puis ``commit`` (qui ne regarde que ``_dirty``) réécrivait cet objet vide
par-dessus la valeur stockée. La première mutation ne ratait pas sa
lecture : elle DÉTRUISAIT ce qui était là.

Ce que ce fichier monte, c'est le seul montage qui l'attrape : un backend
délibérément privé de ``load_sync`` — la forme exacte de Redis — derrière
une vraie app et un vrai aller-retour HTTP. Trois actions de suite : si
l'hydratation marche, le compteur monte ; sinon il repart de zéro à
chaque requête et reste bloqué à 1. Aucune lecture de code ne distingue
les deux, seule la SECONDE requête le fait.

Le fix repose sur ce qui a atterri le matin même : le code d'app
synchrone tourne maintenant dans un thread du pool (``core/invoke.py``),
et un thread a le droit d'attendre pendant que la boucle, elle, exécute
le ``load``. Sur la boucle elle-même — un corps d'app ``async def`` — ce
geste la gèlerait, donc l'état REFUSE de deviner et lève en nommant
``await MonEtat.load()``.

Trois choses sont mesurées ici, et la troisième rend les deux autres
crédibles :

1. le chemin nominal (``def``) hydrate, et l'injection ``form:`` aussi ;
2. le chemin ``async def`` refuse bruyamment, puis marche avec
   ``await ... .load()`` ;
3. ``test_the_harness_would_catch_the_old_behaviour`` remet l'ancien
   geste (``return None``) et exige que ce montage ROUGISSE — sans quoi
   ce fichier resterait vert sur un état qu'il n'aurait pas su regarder.

Tout vit au niveau MODULE : la route d'action résout ses handlers par
``sys.modules`` et refuse un ``<locals>``.
"""

from __future__ import annotations

from typing import Any

import pytest
from starlette.testclient import TestClient

from bretzel import Bretzel, page, ui
from bretzel.server.handlers import encode_action_id, sign_action
from bretzel.state import AppState, MemoryBackend, field
from bretzel.state.registry import StateRegistry

_SECRET = "x" * 32

_app = Bretzel(secret_key=_SECRET, mode="dev")


class AsyncOnlyBackend:
    """Le magasin mémoire, privé de son raccourci synchrone.

    On DÉLÈGUE plutôt que de réimplémenter : ce qui doit différer de
    ``MemoryBackend`` est une seule chose — l'absence de ``load_sync`` —,
    et une copie du stockage ferait diverger le reste sans le dire.
    C'est la forme de ``RedisBackend`` sans le réseau.

    ⚠️ Un ``MemoryBackend`` SOUS-CLASSÉ avec ``load_sync = None`` ne
    marche pas : son propre ``load`` appelle ``self.load_sync``
    (``persistence/memory.py:43``), donc le double perdrait aussi la
    lecture asynchrone. D'où la composition.

    Deux méthodes du protocole manquent volontairement — ``delete`` et
    ``health`` ne sont sur aucun chemin emprunté ici, et les écrire les
    ferait passer pour couvertes.
    """

    def __init__(self) -> None:
        self._inner = MemoryBackend()

    async def load(self, scope: str, key: str) -> dict[str, Any] | None:
        return await self._inner.load(scope, key)

    async def save(
        self,
        scope: str,
        key: str,
        data: dict[str, Any],
        *,
        ttl: int | None = None,
    ) -> None:
        await self._inner.save(scope, key, data, ttl=ttl)

    async def merge(
        self,
        scope: str,
        key: str,
        changes: dict[str, Any],
        *,
        add: dict[str, Any] | None = None,
        ttl: int | None = None,
    ) -> None:
        await self._inner.merge(scope, key, changes, add=add, ttl=ttl)

    async def acquire(
        self, scope: str, key: str, token: str, *, ttl: int
    ) -> bool:
        return await self._inner.acquire(scope, key, token, ttl=ttl)

    async def release(self, scope: str, key: str, token: str) -> None:
        await self._inner.release(scope, key, token)


class Compteur(AppState):
    n: int = field(default=0)


class Profil(AppState):
    nom: str = field(default="")
    ville: str = field(default="")


def incrementer() -> None:
    """Le cas COURANT — un corps ``def``, délesté sur un thread."""
    Compteur().n += 1


async def incrementer_sur_la_boucle() -> None:
    """Le geste qui ne PEUT pas marcher : ``async def`` tourne sur la
    boucle, où attendre le backend la gèlerait pour tout le monde."""
    Compteur().n += 1


async def incrementer_en_attendant() -> None:
    """La porte des corps ``async`` — un ``await``, pas une cérémonie."""
    compteur = await Compteur.load()
    compteur.n += 1


def poser_la_ville() -> None:
    Profil().ville = "Strasbourg"


def enregistrer_le_nom(form: Profil) -> None:
    """L'autre moitié du fix : l'injection ``form: MonEtat``.

    Elle tourne sur la BOUCLE — elle précède le délestage du handler —
    donc elle ne pouvait pas hydrater non plus. La soumission ne porte
    que ``nom`` : si ``ville`` survit, c'est que l'état a bien été lu
    avant d'y écrire.
    """
    assert form.nom


@page("/")
def montrer() -> None:
    ui.text(f"n={Compteur().n} profil={Profil().nom}/{Profil().ville}")


_app.include(montrer)


# ───────────────────────────────────────────────────────────────────────────
# Le montage
# ───────────────────────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def client():
    with TestClient(_app) as c:
        yield c


@pytest.fixture(autouse=True)
def async_only_store():
    """Un magasin NEUF par test, et async-only.

    Neuf, parce que les états de ce fichier sont en portée ``app`` : sans
    ça le compteur d'un test se lirait dans le suivant, et un test
    passerait pour vert en héritant du travail du précédent.
    """
    _app._state_backend = AsyncOnlyBackend()
    yield _app._state_backend


def _post(client: TestClient, handler: Any, **data: str):
    action_id = encode_action_id(handler)
    sig = sign_action(_app.config._action_key, action_id, "")
    return client.post(
        f"/_bretzel/action/{action_id}",
        headers={"X-Bz-Sig": sig},
        data={"_args": "", **data},
    )


def _lire(client: TestClient) -> str:
    response = client.get("/")
    assert response.status_code == 200
    return response.text


# ───────────────────────────────────────────────────────────────────────────
# Le plancher — sans lui, cette suite mesurerait le chemin mémoire
# ───────────────────────────────────────────────────────────────────────────


def test_the_backend_under_test_really_has_no_sync_read(async_only_store) -> None:
    """Le discriminant est-il encore un discriminant ?

    Deux moitiés, et la seconde compte autant : que le double n'ait pas
    ``load_sync`` ne prouve rien si l'original ne l'a plus non plus — le
    jour où ``MemoryBackend`` perd sa lecture synchrone, ce fichier
    testerait deux fois le même chemin en restant vert.
    """
    assert not hasattr(async_only_store, "load_sync")
    assert callable(getattr(MemoryBackend(), "load_sync", None))
    assert _app._state_backend is async_only_store


# ───────────────────────────────────────────────────────────────────────────
# Le chemin nominal
# ───────────────────────────────────────────────────────────────────────────


def test_a_sync_handler_hydrates_through_an_async_only_backend(client) -> None:
    """Trois actions, trois incréments — c'est la SECONDE qui prouve.

    La première réussit même sans hydratation (0 + 1 = 1) : c'est
    exactement pourquoi le trou a survécu à toutes les relectures.
    """
    for _ in range(3):
        assert _post(client, incrementer).status_code in (200, 204)
    assert "n=3" in _lire(client)


def test_the_form_injection_does_not_wipe_the_stored_fields(client) -> None:
    assert _post(client, poser_la_ville).status_code in (200, 204)
    assert _post(client, enregistrer_le_nom, nom="Jean").status_code in (200, 204)
    assert "profil=Jean/Strasbourg" in _lire(client)


# ───────────────────────────────────────────────────────────────────────────
# Le chemin qui ne peut pas attendre
# ───────────────────────────────────────────────────────────────────────────


def test_an_async_handler_refuses_and_names_the_gesture(client) -> None:
    """Refuser fort plutôt que rendre des défauts.

    Ce n'est pas un durcissement gratuit : rendre les défauts ici, c'est
    laisser ``commit`` écraser la valeur stockée. Une erreur coûte une
    requête, le silence coûte les données.
    """
    response = _post(client, incrementer_sur_la_boucle)
    assert response.status_code == 500
    assert "await Compteur.load()" in response.text
    assert "n=0" in _lire(client)


def test_an_async_handler_can_await_the_state(client) -> None:
    for _ in range(2):
        assert _post(client, incrementer_en_attendant).status_code in (200, 204)
    assert "n=2" in _lire(client)


# ───────────────────────────────────────────────────────────────────────────
# La preuve que ce montage MORD
# ───────────────────────────────────────────────────────────────────────────


def test_the_harness_would_catch_the_old_behaviour(client, monkeypatch) -> None:
    """L'ancien geste remis en place : ``return None`` au lieu du pont.

    Sans ce test, un fichier vert ne dirait pas s'il regarde quelque
    chose. Avec lui, il dit ce qu'il verrait partir.
    """
    monkeypatch.setattr(
        StateRegistry,
        "_load_via_loop",
        lambda self, cls, scope, storage_key: None,
    )
    for _ in range(3):
        assert _post(client, incrementer).status_code in (200, 204)
    # Trois incréments, et la page affiche zéro : chaque requête est
    # repartie des défauts, a écrit 1, et la suivante l'a écrasé. La page
    # ne lit pas mieux qu'elles — c'est la forme complète de la panne,
    # pas seulement un compteur en retard.
    rendu = _lire(client)
    assert "n=0" in rendu
    assert "n=3" not in rendu
