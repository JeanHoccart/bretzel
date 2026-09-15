"""Les écritures d'un commit partent ENSEMBLE, pas l'une après l'autre.

Une boucle ``for … await save(...)`` payait un aller-retour réseau par
état sale, en série. Rien ne casse — c'est du temps, pas une faute — donc
rien ne le dit : la page rend, les tests passent, et la latence s'ajoute
en silence à chaque état de plus.

Ce test mesure la seule chose qui soit exacte ici : **le pic de
simultanéité**. Chronométrer serait bancal — ``asyncio.sleep(1ms)`` sous
Windows a une granularité de timer d'environ 15 ms, donc un test de durée
mesurerait l'horloge de l'OS et non le chevauchement. Compter combien
d'écritures sont en vol au même instant ne dépend d'aucune horloge.

Mesuré le 2026-09-05 : pic de 1 avant, de N après ; 8 états passent de
224 ms à 25 ms à 20 ms de RTT simulé.
"""

from __future__ import annotations

import asyncio

import pytest

from bretzel.state import SessionState, field
from bretzel.state.persistence.memory import MemoryBackend
from bretzel.state.registry import StateRegistry


class _Compteur(MemoryBackend):
    """Un backend qui note combien d'écritures se chevauchent.

    Le ``sleep(0)`` est ce qui rend la mesure possible : il rend la main
    à la boucle, donc si les coroutines sont vraiment groupées elles
    entrent toutes avant que la première ne sorte. Sans lui, une boucle
    séquentielle et un ``gather`` donneraient le même pic de 1 — chaque
    ``merge`` finirait sans jamais céder.
    """

    def __init__(self) -> None:
        super().__init__()
        self.en_cours = 0
        self.pic = 0
        self.appels = 0

    async def merge(self, scope, key, changes, *, add=None, ttl=None):
        self.appels += 1
        self.en_cours += 1
        self.pic = max(self.pic, self.en_cours)
        try:
            await asyncio.sleep(0)
            return await super().merge(scope, key, changes, add=add, ttl=ttl)
        finally:
            self.en_cours -= 1


class Un(SessionState):
    v: int = field(default=0)


class Deux(SessionState):
    v: int = field(default=0)


class Trois(SessionState):
    v: int = field(default=0)


class Quatre(SessionState):
    v: int = field(default=0)


_CLASSES = (Un, Deux, Trois, Quatre)


async def _commit_de(n: int) -> _Compteur:
    """Salir ``n`` états distincts et les commiter. Rend le backend."""
    backend = _Compteur()
    registre = StateRegistry(backend=backend, session_id="s1")
    for cls in _CLASSES[:n]:
        instance = cls()
        registre.register(instance)
        instance.v = 1
    await registre.commit()
    return backend


@pytest.mark.anyio
async def test_four_dirty_states_write_in_one_window() -> None:
    """L'interdiction : quatre écritures, une fenêtre."""
    backend = await _commit_de(4)
    assert backend.appels == 4, (
        f"{backend.appels} écritures pour 4 états sales — le montage ne "
        f"mesure pas ce qu'il croit."
    )
    assert backend.pic == 4, (
        f"pic de simultanéité {backend.pic} au lieu de 4 : les écritures "
        f"repartent en série, donc un aller-retour réseau par état. "
        f"``commit()`` doit les grouper."
    )


@pytest.mark.anyio
async def test_a_single_dirty_state_still_writes() -> None:
    """Le cas courant, qui court-circuite le groupage.

    Le plancher de ce fichier : sans lui, un ``commit`` qui n'écrirait
    plus rien du tout passerait le test d'à côté dès qu'on baisserait le
    pic attendu.
    """
    backend = await _commit_de(1)
    assert backend.appels == 1
    assert backend.pic == 1


@pytest.mark.anyio
async def test_a_clean_state_writes_nothing() -> None:
    """L'autre versant : grouper ne doit pas écrire ce qui n'a pas bougé."""
    backend = _Compteur()
    registre = StateRegistry(backend=backend, session_id="s1")
    registre.register(Un())  # lu, jamais muté
    await registre.commit()
    assert backend.appels == 0, (
        "un état propre a été écrit : le groupage a perdu le filtre "
        "``_dirty``."
    )


@pytest.mark.anyio
async def test_one_failing_write_does_not_swallow_the_others() -> None:
    """Le mode d'échec, et c'est lui qui a choisi ``gather``.

    Un groupe de tâches anyio annulerait ses frères à la première
    erreur — il persisterait donc MOINS que la boucle séquentielle qu'on
    remplace. ``gather`` laisse aboutir ce qui est déjà en vol : les
    autres états sont enregistrés quand même.
    """

    class Capricieux(_Compteur):
        async def merge(self, scope, key, changes, *, add=None, ttl=None):
            if "Deux" in key:
                await asyncio.sleep(0)
                raise RuntimeError("le magasin refuse celui-ci")
            return await super().merge(scope, key, changes, add=add, ttl=ttl)

    backend = Capricieux()
    registre = StateRegistry(backend=backend, session_id="s1")
    for cls in _CLASSES:
        instance = cls()
        registre.register(instance)
        instance.v = 1

    with pytest.raises(RuntimeError):
        await registre.commit()

    ecrits = {
        cle for cle in backend._data  # noqa: SLF001 — on inspecte le stockage
        if "Deux" not in cle
    }
    assert len(ecrits) == 3, (
        f"une écriture a échoué et {3 - len(ecrits)} autre(s) ont été "
        f"perdues avec elle : {sorted(backend._data)}. L'échec d'un état "
        f"ne doit pas emporter les états valides."
    )
