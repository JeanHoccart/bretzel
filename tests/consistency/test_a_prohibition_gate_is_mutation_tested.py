r"""Gate : une gate d'interdiction NEUVE arrive avec sa preuve qu'elle mord.

La quatrième gardienne de gates, et la dernière des quatre pathologies
que l'audit du 2026-07-29 avait listées :

===========================================  ==========================
pathologie                                    ce qui la garde
===========================================  ==========================
population vide                               `test_prohibition_gates_declare_a_floor`
fichier illisible sauté                       `test_no_gate_swallows_a_file`
composant non construit, sauté                `test_no_gate_swallows_a_component`
**gate qui ne mord pas** (regex aveugle)      **celle-ci**
===========================================  ==========================

Le défaut qu'elle ferme
-----------------------
Une gate verte prouve deux choses très différentes : « l'invariant tient »
ou « la gate ne regarde rien ». Ce dépôt a livré **trois** gates du second
genre, chacune verte pendant des mois — une cherchait le préfixe
``x-bz-prop:`` mort depuis le rebrand ; ``test_palette_color_is_prefixed``
lisait ``_reactive_props`` au lieu de ``__reactive_props__`` (0 composant
sélectionné sur 76) ; ``test_bool_attr_is_single_sourced`` est née aveugle
au dialecte concurrent qu'elle prétendait unifier.

Le plancher ne les attrape pas : leur population n'était pas vide, c'est
leur DÉTECTEUR qui était mort. Seule une violation fabriquée le montre.

La règle 8 de `CLAUDE.md` l'exige déjà en prose — « mutation-testée dans
les deux sens ». Cette gate la rend mécanique.

Trois façons de la satisfaire
-------------------------------
1. **Une entrée dans ``_mutation_audit.MUTATIONS``** — pour ce qui se
   mute dans un vrai fichier du framework (`py -m tests.consistency._mutation_audit`).
2. **Un test de mutation dans la gate elle-même** — pour ce qui se
   fabrique en mémoire (un AST bidon, une classe jetable). C'est souvent
   plus honnête : la preuve vit à côté de ce qu'elle prouve, et elle
   tourne à chaque `pytest`.
3. **``MUTATION_PROOF = "nom_du_test"``** — quand la preuve existe déjà
   sous un nom que la liste de marqueurs ne devine pas. Beaucoup de
   gates de ce répertoire prouvent leur détecteur par un **contrôle
   POSITIF** — « le motif est encore reconnu là où il DOIT l'être »
   (``test_the_sweep_reads_something``, ``test_the_owner_still_states_the_rule``)
   — ce qui est aussi concluant qu'une violation fabriquée : un
   détecteur qui reconnaît un cas réel n'est pas aveugle.

   Le pointeur est vérifié : le test nommé doit exister. Le nom
   qu'un auteur choisit pour sa preuve reste libre, mais il doit le
   DÉSIGNER — c'est ce qui remplace une liste de marqueurs qui grossit
   à chaque convention nouvelle.
4. **``MUTATION_NOT_APPLICABLE = "raison"``** — pour une gate qui n'a
   pas de DÉTECTEUR à rendre aveugle.

Le troisième cas est réel et il faut le nommer. ``test_theme_override_merge``
fusionne deux thèmes et lit le résultat. Cette gate ne peut pas devenir
« vertes sur rien » : si leur sujet disparaît, c'est l'assertion
elle-même qui tombe. Leur fabriquer une mutation serait une cérémonie,
et une cérémonie apprend à contourner.

⚠️ **La porte est fermée à clé.** Une gate qui déclare
``MUTATION_NOT_APPLICABLE`` mais qui contient un ``re.compile(`` ou un
``ast.walk(`` est REFUSÉE : elle a bel et bien un détecteur, donc la
déclaration serait un laissez-passer. C'est ce qui empêche cette
troisième voie de vider le ratchet — sans ce contrôle, elle serait la
façon la moins chère de faire taire cette gate.

Ce qu'elle ne peut PAS attraper
--------------------------------
Qu'une mutation soit PERTINENTE. Une mutation trop proche du détecteur
(muter la regex elle-même) le fait rougir sans rien prouver de la dérive
réelle. Cette gate compte des preuves, elle ne les juge pas — c'est la
revue qui juge.

La dette est remboursée — ce qu'elle a appris en tombant
---------------------------------------------------------
113 gates sur 140 n'avaient aucune preuve le matin du 2026-08-19 ;
**zéro** le soir. Le remboursement n'a PAS été d'écrire 113 mutations,
et c'est le point : les lire une par une a montré trois familles, et
seule la première demandait vraiment une violation fabriquée.

Deux faux positifs latents sont tombés en chemin, tous deux trouvés par
le versant « la regex épargne les formes légitimes » :

- ``test_control_height_ladder`` lisait ``h-40`` dans ``max-h-40`` —
  ``\b`` est vrai après un tiret. Aucun slot de contrôle n'en portait,
  donc le bug attendait son premier ``max-h-*`` ;
- la même classe de faute a été vérifiée absente ailleurs, parce que ce
  répertoire écrit ``(?<![\w-])`` par convention.

Le fichier de dette reste, vide et strict : ``test_the_debt_only_shrinks``
interdit qu'il regrossisse.
"""

from __future__ import annotations

import ast
import functools
import re
from pathlib import Path

import pytest

_GATES_DIR = Path(__file__).resolve().parent
_MUTATION_AUDIT = _GATES_DIR / "_mutation_audit.py"

#: Le nom de la constante par laquelle une gate déclare n'avoir aucun
#: détecteur à rendre aveugle.
_NOT_APPLICABLE = "MUTATION_NOT_APPLICABLE"

#: Celle par laquelle elle DÉSIGNE le test qui prouve sa morsure.
_PROOF_POINTER = "MUTATION_PROOF"

#: Ce qui trahit un DÉTECTEUR : un motif compilé, ou une marche d'AST.
#: Une gate qui en porte un ne peut pas déclarer ``_NOT_APPLICABLE``.
_DETECTOR_SIGNS = ("re.compile(", "ast.walk(")

#: Un test dont le nom porte l'un de ces mots est une preuve de morsure.
#: Le nom EST le canal ici, contrairement au plancher (détecté par sa
#: forme) : une mutation n'a pas de forme commune — elle fabrique un AST,
#: une classe jetable, un thème bidon — mais elle se nomme toujours pour
#: ce qu'elle est.
_MUTATION_MARKERS = (
    "still_bites", "mutation", "detector", "bites", "muted",
    # Les conventions déjà en usage dans ce répertoire, relevées le
    # 2026-08-19 : ``test_the_pattern_catches_the_real_shapes``,
    # ``test_the_gate_would_catch_a_bare_event``,
    # ``test_the_gate_would_notice_an_edit``,
    # ``test_the_rule_catches_the_fabricated_case``. Les ajouter vaut
    # mieux que renommer six tests : le nom qu'un auteur choisit
    # spontanément pour sa preuve EST la donnée.
    "catches", "would_", "fabriqu", "fabricated",
)


@functools.lru_cache(maxsize=1)
def gates_with_a_table_entry() -> frozenset[str]:
    """Les gates nommées dans ``_mutation_audit.MUTATIONS``.

    Lu au texte plutôt qu'importé : ``_mutation_audit`` tire le harnais
    de mutation (subprocess, restauration de fichiers), qu'un `pytest`
    n'a aucune raison de charger.
    """
    source = _MUTATION_AUDIT.read_text(encoding="utf-8-sig")
    return frozenset(re.findall(r'gate="(test_[a-z0-9_]+\.py)"', source))


def has_inline_proof(tree: ast.AST) -> bool:
    """Cet arbre porte-t-il un test de mutation ?"""
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef):
            continue
        if not node.name.startswith("test_"):
            continue
        if any(marker in node.name for marker in _MUTATION_MARKERS):
            return True
    return False


@functools.lru_cache(maxsize=1)
def gates_with_an_inline_proof() -> frozenset[str]:
    """Les gates qui portent leur propre test de mutation."""
    return frozenset(
        path.name for path in _gate_files()
        if has_inline_proof(ast.parse(path.read_text(encoding="utf-8-sig")))
    )


@functools.lru_cache(maxsize=256)
def declares_not_applicable(path: Path) -> str | None:
    """La raison déclarée par la gate, ou ``None``."""
    return _module_string(path, _NOT_APPLICABLE)


@functools.lru_cache(maxsize=256)
def _module_string(path: Path, const: str) -> str | None:
    """La valeur littérale d'une constante de module, ou ``None``."""
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8-sig"))):
        targets = (
            [node.target] if isinstance(node, ast.AnnAssign)
            else node.targets if isinstance(node, ast.Assign)
            else []
        )
        if any(getattr(t, "id", None) == const for t in targets):
            value = node.value
            if isinstance(value, ast.Constant) and isinstance(value.value, str):
                return value.value
            return ""
    return None


def declared_proof(path: Path) -> str | None:
    """Le nom du test que la gate désigne comme sa preuve."""
    return _module_string(path, _PROOF_POINTER)


def _test_names(path: Path) -> set[str]:
    return {
        node.name
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8-sig")))
        if isinstance(node, ast.FunctionDef) and node.name.startswith("test_")
    }


def _gate_files() -> list[Path]:
    return sorted(_GATES_DIR.glob("test_*.py"))


#: État connu au 2026-08-19 : gates sans aucune preuve de morsure.
#: Égalité STRICTE — une entrée qui gagne sa preuve doit être retirée,
#: sinon la table pourrit comme les allowlists qu'elle remplace.
_NO_PROOF_DEBT: frozenset[str] = frozenset(
    line.strip()
    for line in Path(__file__)
    .with_name("_no_proof_debt.txt")
    .read_text(encoding="utf-8")
    .splitlines()
    if line.strip() and not line.startswith("#")
)


def test_the_sweep_is_not_vacuous() -> None:
    """Plancher : on voit bien les gates, la table et les preuves inline."""
    files = _gate_files()
    assert len(files) >= 100, (
        f"seulement {len(files)} gates découvertes (140 le 2026-08-19) — "
        f"le glob est cassé, et le ratchet ne garde plus rien."
    )
    assert len(gates_with_a_table_entry()) >= 15, (
        "``_mutation_audit`` ne nomme presque plus de gate — le format de "
        "la table a changé et la lecture au texte ne le suit plus."
    )
    assert len(gates_with_an_inline_proof()) >= 5, (
        "aucune preuve de mutation inline n'est reconnue — vérifie "
        "_MUTATION_MARKERS avant de croire que les gates ne mordent pas."
    )


@pytest.mark.parametrize("path", _gate_files(), ids=lambda p: p.name)
def test_a_gate_carries_a_proof_that_it_bites(path: Path) -> None:
    proven = (
        path.name in gates_with_a_table_entry() | gates_with_an_inline_proof()
        or declared_proof(path) is not None
        or declares_not_applicable(path) is not None
    )
    owed = path.name in _NO_PROOF_DEBT

    if proven and owed:
        pytest.fail(
            f"{path.name} porte maintenant sa preuve de morsure — retire-la "
            f"de `_no_proof_debt.txt`. Une table qui garde des noms périmés "
            f"autorise plus que la réalité, ce qui est le défaut même "
            f"qu'elle corrige."
        )

    assert proven or owed, (
        f"{path.name} est une gate neuve sans preuve qu'elle MORD.\n"
        f"  Une gate verte prouve « l'invariant tient » OU « je ne regarde "
        f"rien », et rien ne les distingue de l'extérieur : trois gates de "
        f"ce dépôt sont restées vertes des mois en ne sélectionnant aucun "
        f"composant.\n"
        f"  Deux façons de satisfaire, au choix :\n"
        f"    1. une entrée dans `_mutation_audit.MUTATIONS` (mutation d'un "
        f"vrai fichier) ;\n"
        f"    2. un test dans la gate, nommé avec l'un de "
        f"{_MUTATION_MARKERS}, qui fabrique la violation en mémoire et "
        f"vérifie que le détecteur la voit — ET qu'il ne voit rien sur le "
        f"cas licite d'à côté."
    )


@pytest.mark.parametrize("path", _gate_files(), ids=lambda p: p.name)
def test_a_not_applicable_claim_is_true(path: Path) -> None:
    """Déclarer « pas de détecteur » quand on en a un est un laissez-passer.

    C'est la seule chose qui empêche la troisième voie de vider le
    ratchet : sans ce contrôle, écrire une ligne
    ``MUTATION_NOT_APPLICABLE`` serait la façon la moins chère de faire
    taire cette gate.
    """
    reason = declares_not_applicable(path)
    if reason is None:
        return
    assert reason, (
        f"{path.name} déclare {_NOT_APPLICABLE} sans raison. La raison EST "
        f"la déclaration : « pas de détecteur » se justifie, ça ne s'affirme "
        f"pas."
    )
    source = path.read_text(encoding="utf-8-sig")
    signs = [s for s in _DETECTOR_SIGNS if s in source]
    assert not signs, (
        f"{path.name} déclare {_NOT_APPLICABLE} (« {reason} ») mais porte "
        f"{signs} : elle a bien un détecteur, qui peut donc devenir "
        f"aveugle. Écris la mutation."
    )


@pytest.mark.parametrize("path", _gate_files(), ids=lambda p: p.name)
def test_a_proof_pointer_resolves(path: Path) -> None:
    """``MUTATION_PROOF`` doit désigner un test QUI EXISTE.

    Sans ce contrôle, le pointeur serait la voie la moins chère pour
    faire taire cette gate : une chaîne quelconque suffirait. Un
    pointeur qui ne résout plus signale aussi le cas réel — la preuve
    a été renommée ou supprimée, et plus rien ne garde le détecteur.
    """
    named = declared_proof(path)
    if named is None:
        return
    assert named, (
        f"{path.name} déclare {_PROOF_POINTER} vide. Nomme le test qui "
        f"prouve que ton détecteur mord."
    )
    assert named in _test_names(path), (
        f"{path.name} désigne `{named}` comme sa preuve de morsure, mais "
        f"ce test n'existe pas dans le fichier. Il a été renommé ou "
        f"supprimé — donc plus rien ne garde le détecteur."
    )


def test_the_debt_table_names_real_gates() -> None:
    """Une entrée de dette qui ne désigne aucun fichier est un mensonge."""
    ghosts = sorted(_NO_PROOF_DEBT - {p.name for p in _gate_files()})
    assert not ghosts, (
        f"`_no_proof_debt.txt` nomme des gates qui n'existent pas : "
        f"{ghosts}. Une table qui survit à ses fichiers autorise en silence."
    )


def test_the_debt_only_shrinks() -> None:
    """Ratchet : la dette figée ne peut que descendre.

    Vidée le 2026-08-19. L'exigence est ce qui empêche d'ajouter une gate
    ET son exemption dans le même commit — le geste qui a fait pourrir
    toutes les allowlists de ce dépôt.
    """
    assert not _NO_PROOF_DEBT, (
        f"la dette de preuves est repassée à {len(_NO_PROOF_DEBT)} "
        f"({sorted(_NO_PROOF_DEBT)}) — elle était à ZÉRO le 2026-08-19. "
        f"Une gate neuve s'écrit avec sa mutation, son `MUTATION_PROOF` ou "
        f"son `MUTATION_NOT_APPLICABLE`, pas avec une ligne de plus dans "
        f"la table."
    )


def test_the_proof_detector_still_bites() -> None:
    """Mutation : la reconnaissance d'une preuve inline mord encore.

    Sans ce test, ``has_inline_proof`` pourrait cesser de reconnaître quoi
    que ce soit — et le ratchet exigerait alors une preuve de gates qui en
    portent déjà une, ce qui pousse à gonfler la dette pour faire taire le
    rouge. L'échec le plus coûteux d'une gardienne de gates n'est pas
    d'être aveugle, c'est d'être bruyante.
    """
    avec = ast.parse("def test_the_detector_still_bites():\n    assert True\n")
    assert has_inline_proof(avec), (
        "has_inline_proof ne reconnaît plus un test de mutation nommé — "
        "vérifie _MUTATION_MARKERS."
    )

    sans = ast.parse(
        "def test_no_component_does_the_bad_thing():\n"
        "    assert not offenders\n"
    )
    assert not has_inline_proof(sans), (
        "has_inline_proof voit une preuve dans une interdiction nue : il "
        "déclarerait prouvée n'importe quelle gate, ce qui vide ce fichier "
        "de son objet."
    )
