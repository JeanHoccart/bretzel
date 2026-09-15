"""Gate : une docstring de thème qui ÉNUMÈRE ses slots ne les invente pas.

La convention du dépôt veut qu'un ``theme.py`` s'ouvre sur un inventaire
de slots ::

    Slot inventory :

    - ``root``  : le wrapper
    - ``label`` : le texte

C'est la première chose que lit quiconque veut surcharger un slot — donc
la première à mentir quand le thème bouge et que la prose reste. Mesuré
le 2026-08-01 : **6 des 34 thèmes qui énumèrent leurs slots nommaient au
moins un slot absent de ``THEME["slots"]``**, et deux d'entre eux
(Dropdown, DropdownItem) décrivaient les slots d'un AUTRE composant
(``MenuItem``), ce qui envoie le lecteur surcharger une clé qui ne sera
jamais lue — en silence, puisque rien ne refuse une clé inconnue à cet
endroit.

La sonde qui l'a trouvé n'était pas un balayage de mots-clés mais une
confrontation prose ↔ donnée. C'est reproductible, donc c'est une gate.

**Portée honnête.** On vérifie l'existence des slots nommés, pas la
justesse de leur description. Le sens inverse — un slot réel que la
docstring oublie — n'est PAS gaté : une docstring a le droit de ne
commenter que les slots intéressants, et l'imposer produirait du bruit.

**Trois pièges d'extraction, payés en direct.** La première version de
cette gate accusait 5 thèmes ; 3 étaient de FAUX POSITIFS, et ce sont des
relecteurs indépendants qui l'ont montré :

1. elle avalait les listes voisines. Un ``theme.py`` énumère aussi ses
   ``Variants :``, ``Modifiers :``, ``Sizes :`` avec la même puce — d'où
   Link (``hover``/``underline``/``text`` sont des *variants*) et Table
   (``clickable`` est un *modifier*) accusés à tort. On ne lit donc que
   les puces qui suivent un titre « Slots », et on s'arrête au titre
   suivant ;
2. elle ne regardait qu'UN dict ``*_THEME`` par module. ``dropdown/theme.py``
   en porte deux (Dropdown + DropdownItem) et documente les deux — les
   slots du second passaient pour des fantômes. On prend l'union ;
3. corollaire : une gate d'interdiction se mutation-teste dans les DEUX
   sens. « Elle rougit sur un cas fabriqué » ne dit rien de son taux de
   faux positifs sur le corpus réel.
"""

from __future__ import annotations

import functools
import importlib
import re

import pytest

from tests.consistency._discovery import public_component_classes

# ``- ``nom`` : description`` — la forme d'inventaire du dépôt.
_BULLET = re.compile(r"^\s*-\s*``(\w+)``\s*:")
# Un titre de rubrique : « Slots : », « Slots — Dropdown : », « Variants : »…
_HEADING = re.compile(r"^\s*(\w[\w /—-]*?)\s*:\s*$")


def _slots_named_in(doc: str) -> frozenset[str]:
    """Les slots énumérés SOUS une rubrique « Slots », et rien d'autre."""
    named: set[str] = set()
    in_slots = False
    for line in doc.splitlines():
        head = _HEADING.match(line)
        if head:
            # Un nouveau titre ouvre ou ferme la zone slots.
            in_slots = "slot" in head.group(1).lower()
            continue
        if in_slots:
            bullet = _BULLET.match(line)
            if bullet:
                named.add(bullet.group(1))
    return frozenset(named)


@functools.lru_cache(maxsize=1)
def _themes() -> tuple[tuple[str, str, frozenset[str], frozenset[str]], ...]:
    """``(composant, module de thème, slots énumérés, slots réels)``."""
    out: list[tuple[str, str, frozenset[str], frozenset[str]]] = []
    seen: set[str] = set()
    for cls in public_component_classes():
        theme_mod = cls.__module__.rsplit(".", 1)[0] + ".theme"
        if theme_mod in seen:
            continue
        try:
            mod = importlib.import_module(theme_mod)
        except ImportError:
            continue
        seen.add(theme_mod)
        # UNION de tous les thèmes du module : un fichier peut en porter
        # plusieurs (Dropdown + DropdownItem) et documenter les deux.
        real: set[str] = set()
        for key, val in vars(mod).items():
            if key.endswith("_THEME") and isinstance(val, dict):
                real |= set(val.get("slots") or {})
        if not real:
            continue
        named = _slots_named_in(mod.__doc__ or "")
        if not named:
            continue          # pas d'inventaire → rien à vérifier
        out.append((cls.__name__, theme_mod, named, frozenset(real)))
    return tuple(out)


def test_discovery_non_trivial() -> None:
    """Plancher : la gate voit bien une population de thèmes.

    Sans lui, un renommage de ``*_THEME`` ou de la forme d'inventaire
    rendrait l'interdiction verte sur zéro fichier.
    """
    assert len(_themes()) >= 25, (
        f"seulement {len(_themes())} thèmes avec un inventaire de slots "
        f"détectés (34 le 2026-08-01) — la découverte ou le motif "
        f"``- ``nom`` :`` a cassé, la gate ne garde plus rien."
    )


@pytest.mark.parametrize(
    ("component", "module", "named", "real"),
    _themes(),
    ids=[c for c, _, _, _ in _themes()],
)
def test_docstring_slots_exist(
    component: str, module: str, named: frozenset[str], real: frozenset[str]
) -> None:
    ghosts = sorted(named - real)
    assert not ghosts, (
        f"la docstring de `{module}` énumère des slots que "
        f"`{component}` n'a pas : {ghosts}\n"
        f"  slots réels : {sorted(real)}\n"
        f"  C'est l'inventaire que lit quiconque veut surcharger un slot. "
        f"Surcharger une clé absente ne lève pas — ça ne fait rien, en "
        f"silence.\n"
        f"  Corrige la liste, ou déplace ces lignes vers la bonne rubrique "
        f"— si ce sont en fait des `variants` / `modifiers` / `sizes`, "
        f"mets-les sous LEUR titre : la gate ne lit que les puces qui "
        f"suivent un titre « Slots »."
    )


def test_the_detector_still_bites() -> None:
    """Mutation : les deux formes de la prose de thème sont reconnues.

    La gate confronte les slots ANNONCÉS par la docstring aux slots
    réels. Si le lecteur de puces ou de titres cessait de matcher, elle
    comparerait un ensemble vide et laisserait la docstring mentir.
    """
    assert _BULLET.match("  - ``panel`` : le popover ancré").group(1) == "panel"
    assert not _BULLET.match("  - panel : sans backticks"), "faux positif"
    assert _HEADING.match("Slots :").group(1) == "Slots"
    assert not _HEADING.match("une phrase qui finit par un point."), "faux positif"
