"""Une gate d'interdiction déclare son plancher de non-vacuité.

La gate qui garde les gates.

Le problème qu'elle ferme
-------------------------
La plupart des fichiers de ce répertoire sont des **interdictions** : ils
balaient une population et affirment « zéro contrevenant ». Or un tel test
passe **exactement aussi bien** quand la population est vide — chemin
déplacé, motif devenu introuvable, découverte cassée par un refactor. Le
test est vert, il n'a rien vérifié, et personne ne le sait.

Ce n'est pas théorique dans ce dépôt. Trois précédents, tous mesurés :

- une gate a cherché le préfixe ``x-bz-prop:`` pendant des mois **après** le
  rebrand vers ``bz-`` — elle ne matchait plus aucun attribut ;
- ``test_palette_color_is_prefixed`` lisait ``_reactive_props`` au lieu de
  ``__reactive_props__`` : sa clause sélectionnait **0** composant sur 76 et
  n'était sauvée que par un fallback ;
- ``test_bool_attr_is_single_sourced`` est née aveugle au dialecte
  concurrent qu'elle prétendait unifier — verte le jour de sa livraison.

Pourquoi un RATCHET et pas une exigence immédiate
--------------------------------------------------
25 gates sur 45 n'ont pas de plancher aujourd'hui. Les rendre rouges d'un
coup serait un effet de bord non demandé, qui masquerait les vraies
régressions pendant qu'on les rattrape. La table ci-dessous fige donc l'état
connu : **aucune gate NOUVELLE ne peut s'ajouter sans plancher**, et une
entrée dont le plancher arrive doit être retirée (égalité stricte).

⚠️ Preuve que ça se reproduit, et pas seulement que c'est de l'historique :
``test_themes_use_semantic_colours`` a été ajoutée au commit ``e9039252`` —
celui juste avant le chantier du socle — sans plancher. La pathologie
s'ajoute une gate à la fois.

⚠️ Ce que cette gate ne peut PAS attraper
------------------------------------------
Elle ne couvre qu'**une** des quatre pathologies trouvées par l'audit : le
plancher manquant. L'allowlist devenue vide de sens et la regex aveugle sont
des bugs de **contenu sémantique** — aucune vérification structurelle ne les
trouve, il faut relire le code. Ne pas lire un vert ici comme « les gates
mordent ».
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

_GATES_DIR = Path(__file__).resolve().parent

# Noms qui dénotent un test de plancher. Une gate peut aussi appeler
# ``assert_sweep_is_not_vacuous`` — détecté séparément.
_FLOOR_MARKERS = (
    "vacuous", "population", "sweep", "not_blind", "non_trivial",
    "finds_", "is_not_empty", "has_a_", "not_stale",
)

# La dette est REMBOURSÉE (2026-08-19). Elle valait 25 entrées au
# 2026-07-29 ; le ratchet a tenu — aucune gate neuve ne s'est ajoutée en
# trois semaines, alors que 57 gates ont été écrites — mais il n'avait
# rien remboursé non plus, parce qu'un ratchet n'y oblige jamais.
#
# Cinq des 25 avaient en réalité un vrai plancher, sous un nom que la
# liste de marqueurs ne reconnaissait pas (``test_the_gate_sees_its_consumers``,
# ``test_the_universal_set_was_found``…). D'où ``_asserts_a_minimum`` :
# on détecte la FORME (``assert len(x) >= N``) plutôt que le nom, parce
# qu'une gate qu'il faut renommer pour être reconnue n'apprend rien à
# personne. Les 20 autres ont reçu un plancher qui lit LEUR découverte.
#
# ⚠️ Vide et STRICT : la table reste là pour qu'on puisse y écrire une
# exception motivée, pas pour qu'on y range ce qu'on n'a pas fait.
_NO_FLOOR_DEBT: frozenset[str] = frozenset()


def _is_prohibition(tree: ast.Module) -> bool:
    """``assert not <collection>`` ou ``assert <collection> == []``.

    La forme « je balaie et j'affirme qu'il n'y a rien », c'est-à-dire celle
    qui passe aussi bien sur une population vide."""
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assert):
            continue
        test = node.test
        if (
            isinstance(test, ast.UnaryOp)
            and isinstance(test.op, ast.Not)
            and isinstance(test.operand, ast.Name)
        ):
            return True
        if (
            isinstance(test, ast.Compare)
            and isinstance(test.left, ast.Name)
            and any(
                isinstance(c, (ast.List, ast.Set, ast.Dict))
                for c in test.comparators
            )
        ):
            return True
    return False


def _asserts_a_minimum(node: ast.AST) -> bool:
    """``assert len(x) >= N`` — un plancher, quel que soit son nom.

    Détecté STRUCTURELLEMENT depuis le 2026-08-19. Avant, seul le nom du
    test comptait, et cinq gates de la dette portaient en réalité un vrai
    plancher sous un nom que la liste de marqueurs ne reconnaissait pas
    (``test_the_gate_sees_its_consumers``, ``test_the_universal_set_was_found``…).
    Une gate qui doit être RENOMMÉE pour être reconnue n'apprend rien à
    personne — c'est la forme qui compte.
    """
    for sub in ast.walk(node):
        if not isinstance(sub, ast.Assert):
            continue
        test = sub.test
        if not isinstance(test, ast.Compare):
            continue
        if not any(isinstance(op, (ast.GtE, ast.Gt)) for op in test.ops):
            continue
        if any(
            isinstance(call, ast.Call)
            and getattr(call.func, "id", None) == "len"
            for call in ast.walk(test.left)
        ):
            return True
    return False


def _reads_a_floored_sweep(node: ast.AST) -> bool:
    """``parsed_sources(root, floor=…)`` porte SON plancher en argument.

    La primitive lève si la racine ne rend pas assez de fichiers ; une
    gate qui l'appelle a donc son plancher, dans la primitive plutôt que
    dans un test à elle. Ne pas le reconnaître poussait à écrire un
    second plancher qui recompte la même chose — exactement la duplication
    que la primitive existe pour supprimer.
    """
    for sub in ast.walk(node):
        if (
            isinstance(sub, ast.Call)
            and getattr(sub.func, "id", None) == "parsed_sources"
            and any(kw.arg == "floor" for kw in sub.keywords)
        ):
            return True
    return False


def _has_floor(tree: ast.Module) -> bool:
    if _reads_a_floored_sweep(tree):
        return True
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef) or not node.name.startswith("test_"):
            continue
        if any(marker in node.name for marker in _FLOOR_MARKERS):
            return True
        if "assert_sweep_is_not_vacuous" in ast.dump(node):
            return True
        if _asserts_a_minimum(node):
            return True
    return False


_GATE_FILES = sorted(
    p for p in _GATES_DIR.glob("test_*.py") if p.name != Path(__file__).name
)


def test_this_gate_sees_the_others() -> None:
    """Plancher de non-vacuité — de la gate qui exige des planchers.

    Sans lui, un ``glob`` cassé rendrait cette gate verte sur zéro fichier,
    ce qui serait particulièrement ironique."""
    assert len(_GATE_FILES) >= 55, (
        f"seulement {len(_GATE_FILES)} fichiers de gate découverts (66 le "
        f"2026-07-29) — le glob est cassé."
    )
    prohibitions = [
        p for p in _GATE_FILES if _is_prohibition(ast.parse(p.read_text(encoding="utf8")))
    ]
    assert len(prohibitions) >= 35, (
        f"seulement {len(prohibitions)} gates classées « interdiction » "
        f"(45 le 2026-07-29) — le classifieur AST ne reconnaît plus la "
        f"forme, cette gate ne vérifie plus rien."
    )


@pytest.mark.parametrize("path", _GATE_FILES, ids=lambda p: p.name)
def test_a_prohibition_gate_declares_a_floor(path: Path) -> None:
    tree = ast.parse(path.read_text(encoding="utf8"))
    if not _is_prohibition(tree):
        pytest.skip("pas une gate d'interdiction")

    has_floor = _has_floor(tree)
    owed = path.name in _NO_FLOOR_DEBT

    if not has_floor and not owed:
        pytest.fail(
            f"{path.name} est une gate d'INTERDICTION sans plancher de "
            f"non-vacuité.\n"
            f"  Elle affirme « zéro contrevenant » — et elle l'affirmera "
            f"tout aussi bien le jour où sa population sera vide (chemin "
            f"déplacé, motif introuvable, découverte cassée). Verte, sur "
            f"rien.\n"
            f"  Ajoute un test dont le nom contient l'un de {_FLOOR_MARKERS} "
            f"et qui asserte que la population balayée est significative, "
            f"ou appelle `assert_sweep_is_not_vacuous()` de `_discovery`.\n"
            f"  Trois gates de ce dépôt sont déjà restées vertes des mois "
            f"sur zéro vérification."
        )
    if has_floor and owed:
        pytest.fail(
            f"{path.name} a désormais un plancher — retire-le de "
            f"`_NO_FLOOR_DEBT`. La table est un RATCHET : elle ne doit que "
            f"décroître, sinon elle pourrit comme les allowlists qu'on "
            f"vient de réparer."
        )


def test_the_debt_only_lists_real_files() -> None:
    """Une entrée qui nomme un fichier disparu est du bruit qui achète un
    faux sentiment de suivi."""
    names = {p.name for p in _GATE_FILES}
    ghosts = sorted(_NO_FLOOR_DEBT - names)
    assert not ghosts, (
        f"_NO_FLOOR_DEBT liste des fichiers qui n'existent plus : {ghosts}"
    )


def test_the_floor_detector_still_bites() -> None:
    """Mutation : ``_has_floor`` reconnaît les trois formes, et rien d'autre.

    Sans ce test, la détection pourrait cesser de reconnaître quoi que ce
    soit et la gate rendrait TOUTES les autres « sans plancher » — ou,
    pire dans l'autre sens, en déclarer une saine par accident. La dette
    ayant été vidée le 2026-08-19, plus aucune table ne rattraperait
    l'erreur.
    """
    par_le_nom = ast.parse(
        "def test_the_sweep_is_not_vacuous():\n    assert True\n"
    )
    par_la_forme = ast.parse(
        "def test_quelque_chose():\n    assert len(items) >= 12, 'plancher'\n"
    )
    par_la_primitive = ast.parse(
        "def test_quelque_chose():\n"
        "    for s in parsed_sources(ROOT, floor=200):\n        pass\n"
    )
    for tree, forme in (
        (par_le_nom, "le nom"),
        (par_la_forme, "la forme assert len(x) >= N"),
        (par_la_primitive, "parsed_sources(..., floor=…)"),
    ):
        assert _has_floor(tree), f"_has_floor ne reconnaît plus {forme}"

    sans_plancher = ast.parse(
        "def test_quelque_chose():\n    assert not offenders, 'interdiction'\n"
    )
    assert not _has_floor(sans_plancher), (
        "_has_floor voit un plancher dans une interdiction nue — il "
        "déclarerait saine n'importe quelle gate, ce qui est le mode "
        "d'échec exact que ce fichier existe pour empêcher."
    )
