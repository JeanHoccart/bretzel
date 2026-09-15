"""Le ternaire ``'true'``/``'false'`` sort d'UN seul endroit.

Un attribut réactif qui doit porter la **chaîne** ``"true"``/``"false"`` —
et non la sémantique des booléens natifs, où la présence de l'attribut EST
l'information — se construit avec :func:`bretzel.components.base._wiring.bool_attr`.

Deux familles en dépendent :

- **ARIA** (``aria-disabled``, ``aria-expanded``, ``aria-pressed``…) : un
  lecteur d'écran lit la valeur, et la variante Tailwind ``aria-disabled:``
  compile vers ``[aria-disabled="true"]`` ;
- **les ``data-*`` de style** (``data-open``, ``data-active``,
  ``data-menu-open``) : ``data-[open=true]:`` matche le littéral.

Dans les deux cas, se tromper ne casse **rien de visible** : ni le style ni
l'annonce ne s'appliquent, en silence. C'est le mode d'échec le plus cher —
personne ne le voit, et les tests SSR trouvent le HTML « correct ».

**Ce que le recensement a mesuré** (2026-07-28) : la règle était écrite en
commentaire à trois endroits, et **dix-neuf sites la ré-implémentaient à la
main — dont dix sans parenthéser leur opérande**. Deux autres l'avaient
carrément oubliée (`select` multi et `combobox`), et là c'était un vrai bug.

Le parenthésage n'est pas cosmétique : ``a || b ? 'true' : 'false'`` se lit
``(a || b) ? …`` par chance, mais une expression plus lâche re-associerait.
Même classe que le parenthésage de l'algèbre de bindings
(``test_client_expression_atomic.py``).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from tests.consistency._discovery import PACKAGE_FLOOR, parsed_sources, source_of

_BRETZEL = Path(__file__).resolve().parents[2] / "bretzel"

# Le module qui a le DROIT de contenir le littéral : il le produit.
_OWNER = _BRETZEL / "components" / "base" / "_wiring.py"

_TERNARY = re.compile(r"\?\s*'true'\s*:\s*'false'")

# ── Le dialecte CONCURRENT, et pourquoi la gate était aveugle ─────────
# Écrite le 2026-07-28 pour unifier le ternaire, elle ne cherchait QUE la
# forme ``? 'true' : 'false'`` — donc elle ne voyait pas les sites qui
# obtiennent la même chaîne par ``(<expr>).toString()``. Verte le jour de sa
# naissance sur un motif qu'elle prétendait unifier, présent en deux formes.
#
# Les deux ne sont PAS équivalents : sur un opérande ``null``/``undefined``,
# ``(x).toString()`` **lève** là où ``bool_attr`` écrit ``'false'``. Une
# expression qui lève dans un ``bz-attr`` est un mode d'échec silencieux de
# plus, pas un choix de style.
_TOSTRING = re.compile(r"\)\s*\.toString\(\)")

# Dette mesurée le 2026-07-29, à ÉGALITÉ STRICTE par fichier : le fix de
# fond (router toute émission d'attribut réactif par le dérivateur de
# ``forward_binding``, qui dérive déjà le ternaire du nom d'attribut depuis
# `fab936d9`) est suivi comme un item à part. Cette table rend la dette
# VISIBLE en attendant — c'est tout ce qu'on lui demande.
#
# Quand tu migres un site : baisse le compte. Quand un fichier tombe à 0 :
# retire sa ligne. Égalité stricte et non « au plus », pour qu'un 14ᵉ site
# rougisse et qu'un compte périmé ne puisse pas dormir ici.
#
# Clés = chemin relatif à ``bretzel/``, PAS le nom de fichier : il y a deux
# ``tree.py`` (``components/data/tree/`` et ``core/``) et une clé par basename
# faisait porter la dette du premier au second. Attrapé par la gate elle-même
# à l'écriture.
# ✅ VIDE depuis le 2026-07-29 — les 13 sites sont passés à ``bool_attr``.
#
# Le passage n'était PAS un simple remplacement de forme : mesuré au
# navigateur, les deux dialectes ne coïncident que sur de vrais booléens.
#
#   valeur      .toString()   (v) ? 'true' : 'false'
#   true        "true"        "true"      ← identique
#   false       "false"       "false"     ← identique
#   0           "0"           "false"     ← DIVERGENT
#   "x"         "x"           "true"      ← DIVERGENT
#   null        THROWS        "false"     ← le gain
#
# Les 13 expressions ont donc été prouvées booléennes une par une avant la
# bascule — ``indexOf(v) >= 0``, ``String(a) === String(b)``,
# ``includes(...)``, ``a === b``, et des variables de scope initialisées à
# ``false``. Sans cette preuve, la « simplification » aurait changé le
# rendu sur les valeurs non booléennes.
_TOSTRING_DEBT: dict[str, int] = {}


def _rel(path: Path) -> str:
    return path.relative_to(_BRETZEL).as_posix()


def _python_sources() -> list[Path]:
    return [s.path for s in parsed_sources(_BRETZEL, floor=PACKAGE_FLOOR)]


def _count_tostring(path: Path) -> int:
    """Les émissions du dialecte concurrent, commentaires exclus — trois des
    quinze occurrences brutes sont de la prose qui EXPLIQUE le motif."""
    return sum(
        1 for line in source_of(path).text.splitlines()
        if not line.strip().startswith("#") and _TOSTRING.search(line)
    )


@pytest.mark.parametrize(
    "path", _python_sources(), ids=lambda p: p.name
)
def test_no_hand_written_bool_ternary(path: Path) -> None:
    if path == _OWNER:
        pytest.skip("le module qui possède le helper")
    lines = path.read_text(encoding="utf8").splitlines()
    offenders = [
        (i, line.strip())
        for i, line in enumerate(lines, 1)
        if _TERNARY.search(line)
    ]
    assert not offenders, (
        f"{path.name} écrit le ternaire à la main :\n"
        + "\n".join(f"    :{i}  {text[:88]}" for i, text in offenders)
        + "\n  Passe par `bool_attr(<expr>)` (base/_wiring.py). Il "
          "parenthèse l'opérande — dix des dix-neuf sites d'origine ne le "
          "faisaient pas — et il porte le POURQUOI, qui vivait jusqu'ici "
          "dans trois commentaires recopiés."
    )


@pytest.mark.parametrize(
    "path", _python_sources(), ids=lambda p: p.name
)
def test_tostring_dialect_only_where_it_is_owed(path: Path) -> None:
    """Le second dialecte n'existe QUE là où la dette est déclarée, et en
    quantité exacte. C'est la moitié que la regex d'origine ne voyait pas."""
    if path == _OWNER:
        pytest.skip("le module qui possède le helper")

    found = _count_tostring(path)
    owed = _TOSTRING_DEBT.get(_rel(path), 0)

    if found == owed:
        return

    if owed == 0:
        pytest.fail(
            f"{path.name} : {found} émission(s) `(<expr>).toString()` — le "
            f"dialecte concurrent de `bool_attr`. Les deux ne sont PAS "
            f"équivalents : sur null/undefined, `.toString()` LÈVE là où "
            f"`bool_attr` écrit 'false'. Passe par `bool_attr(<expr>)` "
            f"(base/_wiring.py), ou déclare la dette dans _TOSTRING_DEBT "
            f"avec la raison."
        )
    pytest.fail(
        f"{path.name} : {found} émission(s) `.toString()`, la dette déclarée "
        f"en dit {owed}. Si tu en as migré une, BAISSE le compte dans "
        f"_TOSTRING_DEBT (retire la ligne à 0). Si tu en as ajouté une, "
        f"passe plutôt par `bool_attr(<expr>)`."
    )


def test_the_tostring_debt_is_not_stale() -> None:
    """Chaque fichier listé porte encore de la dette. Une ligne à zéro qui
    dort dans la table rachète un faux sentiment de couverture — c'est
    exactement comme ça que la regex d'origine est restée aveugle."""
    sources = {_rel(p): p for p in _python_sources()}
    for rel, owed in sorted(_TOSTRING_DEBT.items()):
        path = sources.get(rel)
        assert path is not None, (
            f"_TOSTRING_DEBT liste {rel!r}, qui n'existe plus dans "
            f"bretzel/ — retire la ligne."
        )
        assert _count_tostring(path) > 0, (
            f"_TOSTRING_DEBT liste {rel!r} avec {owed}, mais le fichier n'en "
            f"porte plus aucune — la dette est payée, retire la ligne."
        )


def test_the_helper_parenthesises_its_operand() -> None:
    """Le contrat du helper lui-même, pas seulement son adoption."""
    from bretzel.components.base._wiring import bool_attr

    assert bool_attr("open") == "(open) ? 'true' : 'false'"
    # Le cas qui justifie les parenthèses : un opérande lâche.
    assert bool_attr("a || b") == "(a || b) ? 'true' : 'false'"


def test_the_gate_is_not_blind() -> None:
    """Garde-fou : le helper doit rester détectable là où il est utilisé."""
    used_in = [
        p.name for p in _python_sources()
        if p != _OWNER and "bool_attr(" in p.read_text(encoding="utf8")
    ]
    assert len(used_in) >= 8, (
        f"`bool_attr` n'est appelé que dans {len(used_in)} fichiers "
        f"({used_in}) — le recensement en comptait 19 sites sur 9 modules. "
        f"Soit l'adoption a régressé, soit le motif a changé."
    )
