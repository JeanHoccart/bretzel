"""Un probe ne code pas son port en dur.

Ce que cette gate ferme
-----------------------

``-m probes`` a tourné **strictement séquentiel** jusqu'au 2026-09-13, à
17 min pour 84 probes. La cause n'était pas le navigateur : **60 probes
sur 84 codaient leur port**, et dix de ces ports servaient deux ou trois
bancs différents. Deux probes lancés ensemble sur ``:8973`` se marchent
dessus, donc un ``xdist_group`` épinglait les 84 sur un worker unique
pour protéger une poignée de collisions.

Le défaut a la forme que ce dépôt paie le plus cher : **chaque probe
marchait**. Écrire ``BASE = "http://127.0.0.1:8973"`` est correct tant
qu'on le lance seul, et rien dans le fichier ne dit que le port est
partagé. Ça ne se voit qu'en additionnant les 84, ce que personne ne
fait à la main.

Pourquoi la règle porte sur l'URL, pas sur le nombre
-----------------------------------------------------

Un banc garde un port par DÉFAUT — ``bench_port(8976)`` — et c'est
licite : il sert quand on lance le banc à la main, comme sa docstring
l'annonce, et il cède devant l'argument que le probe passe. Ce qui ne
l'est pas, c'est une ADRESSE écrite en dur côté probe : elle ne cède à
rien, et c'est elle qui collisionne.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Final

import pytest

from tests.consistency._discovery import REPO_ROOT, code_string_literals, parsed_sources

PROBES_DIR: Final[Path] = REPO_ROOT / "tests" / "probes"

#: 84 probes + 52 bancs + le socle le 2026-09-13. Le seuil laisse de la
#: marge sans laisser passer un balayage cassé.
PROBES_FLOOR: Final[int] = 100

#: Preuve de morsure : le seul DÉTECTEUR de ce fichier.
MUTATION_PROOF = "test_the_address_reader_still_bites"

#: Une adresse de boucle locale AVEC un port. ``\b`` et non ``^`` : elle
#: est presque toujours au milieu d'une chaîne.
_ADDRESS = re.compile(r"\b(?:127\.0\.0\.1|localhost|0\.0\.0\.0):(\d{2,5})\b")


def hardcoded_addresses(text: str) -> list[str]:
    """Les adresses locales à port fixe de ce texte."""
    return [m.group(0) for m in _ADDRESS.finditer(text)]


def _exempted() -> dict[str, str]:
    """Les probes dispensés, lus depuis la source qui les épingle VRAIMENT.

    ``test_probes._FIXED_PORT`` est ce qui décide du marqueur ``xdist``.
    Recopier la liste ici en ferait deux, et la seconde autoriserait un
    jour un probe que la première ne protège plus — donc un probe à port
    fixe lancé en parallèle, c'est-à-dire le bug d'origine, rendu légal
    par sa propre gate.
    """
    from tests.probes.test_probes import _FIXED_PORT

    return _FIXED_PORT


def probe_sources() -> list[object]:
    return parsed_sources(PROBES_DIR, floor=PROBES_FLOOR)


def test_the_sweep_is_not_vacuous() -> None:
    """Plancher sur la DÉCOUVERTE : sans lui, « aucun port en dur » se
    dirait sur zéro fichier."""
    assert len(probe_sources()) >= PROBES_FLOOR


def test_the_exemption_list_is_not_a_hole() -> None:
    """Chaque dispense nomme un fichier RÉEL et porte une raison.

    Une allowlist qui garde une entrée périmée autorise plus que la
    réalité — c'est le défaut réparé sur `test_documented_paths_exist`
    le 2026-09-12, et il se reproduit partout où une liste survit à son
    sujet.
    """
    for nom, raison in _exempted().items():
        assert (PROBES_DIR / nom).is_file(), (
            f"`_FIXED_PORT` dispense {nom}, qui n'existe plus : retire la "
            f"ligne, sinon la dispense couvre un fichier futur portant le "
            f"même nom."
        )
        assert len(raison) > 40, (
            f"la dispense de {nom} n'écrit pas pourquoi. Une exemption "
            f"sans raison est un trou qui a l'air d'une décision."
        )


@pytest.mark.parametrize(
    "source",
    probe_sources(),
    ids=lambda s: s.path.name,
)
def test_no_probe_hardcodes_its_address(source: object) -> None:
    """L'interdiction, sur ce que le code FABRIQUE.

    ``code_string_literals`` écarte les chaînes nues en instruction,
    docstrings comprises : un probe qui EXPLIQUE son ancien port dans sa
    docstring n'est pas un contrevenant, et une gate qui lisait le texte
    brut aurait compté sa propre note de migration.
    """
    nom = source.path.name  # type: ignore[attr-defined]
    if nom in _exempted() or nom == "_serve.py":
        return
    fautes = [
        f"ligne {node.lineno} : {adresse}"
        for node in code_string_literals(source.tree)  # type: ignore[attr-defined]
        if isinstance(node.value, str)
        for adresse in hardcoded_addresses(node.value)
    ]
    assert not fautes, (
        f"{nom} code son adresse en dur :\n  " + "\n  ".join(fautes) + "\n\n"
        "  Deux probes sur le même port se marchent dessus dès qu'on "
        "parallélise, et c'est ce qui a tenu `-m probes` en série à 17 min.\n"
        "  Demande un port libre :\n"
        "      from tests.probes._serve import free_port\n"
        "      PORT = free_port()\n"
        '      BASE = f"http://127.0.0.1:{PORT}"\n'
        "  puis passe `str(PORT)` au banc, qui le lira par `bench_port()`.\n"
        "  Si le port DOIT être fixe, inscris le probe dans "
        "`tests/probes/test_probes._FIXED_PORT` avec sa raison."
    )


def test_the_address_reader_still_bites() -> None:
    """Les deux versants du détecteur.

    Le versant qui ÉPARGNE compte autant : un défaut de banc
    (``bench_port(8976)``) est licite — il cède devant l'argument du
    probe — et rougir dessus pousserait à débrancher la règle.
    """
    assert hardcoded_addresses('BASE = "http://127.0.0.1:8973"') == [
        "127.0.0.1:8973"
    ]
    assert hardcoded_addresses('IDP = "http://localhost:8954"') == [
        "localhost:8954"
    ]
    assert not hardcoded_addresses("uvicorn.run(app, port=bench_port(8976))")
    assert not hardcoded_addresses('BASE = f"http://127.0.0.1:{PORT}"')
    # Une adresse SANS port ne collisionne pas : c'est un hôte, pas une
    # réservation.
    assert not hardcoded_addresses('host="127.0.0.1"')
