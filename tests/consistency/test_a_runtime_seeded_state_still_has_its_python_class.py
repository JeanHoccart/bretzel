"""Toute cellule d'état que le runtime SÈME a encore sa classe Python.

Le fait gardé
--------------
Deux ``ClientState`` sont possédés par le framework et écrits par le
NAVIGATEUR, pas par le serveur : ``ColorScheme`` (le mode de couleur,
persisté en ``localStorage``) et ``LiveConnection`` (l'EventSource est-il
ouvert). Personne ne les mute côté Python — c'est ``00_index.js`` qui
sème leur cellule, en épelant la clé **à la main** ::

    $bz._persistence.register("LiveConnection.default", "memory");
    $bz._store.set("LiveConnection.default.connected", false);

Cette clé est le nom de la classe Python, son instance, et son champ,
collés. Rien ne relie les deux épellations : ni import, ni type, ni
éditeur. Renommer la classe côté Python laisse donc le JS semer une
cellule que plus personne ne lit — et le symptôme est **muet**. Le badge
« LIVE » ne s'allume jamais, la page rend parfaitement, aucune suite
serveur ne bronche, aucune console n'affiche d'erreur : le binding pointe
sur une cellule qui reste indéfinie, ce qui est un état légitime.

C'est arrivé le 2026-08-29 en renommant ``Realtime`` en
``LiveConnection``. Le renommage Python était complet et vert — les 17740
tests rapides passaient — pendant que les quatre ``$bz._store.set`` du
runtime auraient continué d'écrire ``Realtime.default.connected``. Rien
dans le dépôt ne l'aurait dit.

Le sens de lecture
-------------------
**JS → Python**, et c'est le seul sens qui morde. Partir des classes
Python pour chercher leur clé dans le JS ne verrait pas une classe
renommée : la nouvelle n'a simplement aucune clé, ce qui est le cas de
tous les ``ClientState`` d'app. Partir des clés SEMÉES pose la bonne
question — « ce que le navigateur écrit, quelqu'un le lit-il encore ? ».

Ce que la gate n'affirme PAS
-----------------------------
Que la valeur semée a le bon TYPE, ni que le binding s'affiche. Elle
ferme la dérive du NOM, la seule lisible depuis les deux langages sans
navigateur. Le reste est le travail d'une sonde.
"""

from __future__ import annotations

import re
from collections.abc import Iterable

import pytest

from tests.consistency._discovery import (
    assert_runtime_sweep_is_not_vacuous,
    runtime_sources,
    strip_js_comments,
)

#: Le test qui prouve que le détecteur mord — cf. la règle 8 du charter.
MUTATION_PROOF = "test_the_detector_still_bites"

#: Les deux formes par lesquelles le runtime sème une cellule d'état
#: possédée par le framework. ``register`` déclare la persistance,
#: ``set`` pose la valeur ; les deux épellent la même clé.
_REGISTER = re.compile(r"""_persistence\.register\(\s*["']([A-Za-z_]\w*)\.(\w+)["']""")
_SET = re.compile(r"""_store\.set\(\s*["']([A-Za-z_]\w*)\.(\w+)\.(\w+)["']""")

#: PLANCHER — ancré sur la DÉCOUVERTE, pas sur la population. Deux états
#: et quatre cellules DISTINCTES au 2026-08-29 (un ``register`` + un
#: ``set`` chacun ; les trois ``set`` de ``LiveConnection`` visent la même
#: cellule et comptent pour une). Débrancher une des deux expressions fait
#: tomber le compte, donc la gate ne peut pas rester verte en ayant cessé
#: de balayer.
_MIN_STATES = 2
_MIN_CELLS = 4


def seeded_cells(sources: Iterable[str]) -> set[tuple[str, str, str | None]]:
    """``(classe, instance, champ)`` pour chaque cellule semée par le JS.

    ``champ`` vaut ``None`` pour un ``register``, qui ne nomme que
    l'instance. Extrait plutôt qu'inline pour être MUTABLE : c'est ce
    détecteur que :func:`test_the_detector_still_bites` nourrit de
    sources fabriquées. Il prend des SOURCES, pas des fichiers : le nom
    de slab n'apparaît dans aucune assertion, donc l'exiger n'aurait
    servi qu'à faire inventer des noms au test de mutation.
    """
    found: set[tuple[str, str, str | None]] = set()
    for code in sources:
        for cls, inst in _REGISTER.findall(code):
            found.add((cls, inst, None))
        for cls, inst, field in _SET.findall(code):
            found.add((cls, inst, field))
    return found


@pytest.fixture(scope="module")
def cells() -> set[tuple[str, str, str | None]]:
    assert_runtime_sweep_is_not_vacuous()
    return seeded_cells(runtime_sources().values())


def _python_client_states() -> dict[str, type]:
    """Les ``ClientState`` que le FRAMEWORK définit, par nom de classe.

    Découverts par sous-classes, pas par ``bretzel.__all__`` : la
    question posée est « cette classe existe-t-elle ? », pas « est-elle
    publique ? ». Un état possédé par le framework, semé par le runtime
    mais non ré-exporté au premier étage, serait sinon rapporté comme
    orphelin — un rouge sur une décision d'EXPORT, avec un message qui
    désigne le runtime.

    Restreint aux modules sous ``bretzel.`` : les ``ClientState`` des
    apps et des suites n'ont aucune raison d'avoir une clé semée.
    ``import bretzel`` d'abord, sinon les sous-classes ne sont pas encore
    chargées et le balayage serait vide — ce que le plancher attrape.
    """
    import bretzel  # noqa: F401 — charge les sous-classes du framework
    from bretzel.state import ClientState

    found: dict[str, type] = {}
    stack = list(ClientState.__subclasses__())
    while stack:
        cls = stack.pop()
        stack.extend(cls.__subclasses__())
        if cls.__module__.startswith("bretzel."):
            found[cls.__name__] = cls
    return found


def test_the_sweep_is_not_vacuous(cells: set[tuple[str, str, str | None]]) -> None:
    """Le balayage voit encore des cellules — sinon la gate ne dit rien."""
    classes = {cls for cls, _, _ in cells}
    assert len(classes) >= _MIN_STATES, (
        f"le balayage ne trouve plus que {len(classes)} état(s) semé(s) par "
        f"le runtime ({sorted(classes)}), plancher {_MIN_STATES}."
    )
    # C'est CELUI-CI qui mord en pratique — débrancher une des deux
    # expressions fait tomber le compte de cellules avant celui d'états,
    # puisque chaque état contribue aujourd'hui un ``register`` et un
    # ``set``. D'où le diagnostic complet ici plutôt que sur l'autre.
    assert len(cells) >= _MIN_CELLS, (
        f"{len(cells)} cellule(s) distincte(s) semée(s) ({sorted(cells)}), "
        f"plancher {_MIN_CELLS}. Soit une forme de semis a changé et les "
        f"expressions ne la voient plus, soit un état possédé par le "
        f"framework a disparu — dans les deux cas cette gate a cessé de "
        f"garder quelque chose."
    )


def test_every_seeded_cell_has_its_python_class(
    cells: set[tuple[str, str, str | None]],
) -> None:
    """Chaque clé semée nomme une classe Python vivante, et son champ."""
    states = _python_client_states()
    orphans: list[str] = []
    for cls, inst, field in sorted(cells, key=lambda c: (c[0], c[2] or "")):
        key = f"{cls}.{inst}" + (f".{field}" if field else "")
        target = states.get(cls)
        if target is None:
            orphans.append(
                f"  {key} — aucune classe `{cls}` parmi les ClientState "
                f"exportés ({sorted(states)})"
            )
            continue
        fields = target._all_fields()
        if field is not None and field not in fields:
            orphans.append(
                f"  {key} — `{cls}` existe mais n'a pas de champ `{field}` "
                f"(champs : {sorted(fields)})"
            )
    assert not orphans, (
        "le runtime sème des cellules que plus aucune classe Python ne lit :\n"
        + "\n".join(orphans)
        + "\n\nLe symptôme est MUET : la page rend, la suite serveur passe, "
        "et le binding pointe simplement sur une cellule indéfinie. Renomme "
        "la clé dans `bretzel/runtime/_src/`, rebâtis le bundle "
        "(`py -m bretzel.runtime._build`), et vérifie le témoin à l'écran."
    )


def test_the_detector_still_bites() -> None:
    """Le détecteur rougit sur une clé morte, et pas sur une clé vivante.

    Les deux versants comptent. Le licite est celui qui coûte cher : une
    gate qui rougirait sur le semis réel serait débranchée le lendemain.
    """
    states = _python_client_states()

    illicite = seeded_cells(
        ['$bz._store.set("Realtime.default.connected", false);']
    )
    assert illicite == {("Realtime", "default", "connected")}
    assert "Realtime" not in states, (
        "le versant illicite de cette preuve suppose que `Realtime` n'existe "
        "plus côté Python ; s'il revenait, choisis un autre nom mort."
    )

    licite = seeded_cells(
        ['$bz._store.set("LiveConnection.default.connected", true);']
    )
    assert licite == {("LiveConnection", "default", "connected")}
    assert "LiveConnection" in states

    # Un commentaire n'est PAS un semis — même règle que la gate du
    # vocabulaire ``$bz.*`` : la prose du runtime cite des clés qu'elle
    # explique, et les lire ferait rougir sur du code juste.
    prose = seeded_cells(
        {"prose.js": '// $bz._store.set("Disparu.default.x", 1) n\'existe plus'}
    )
    assert prose == set()
