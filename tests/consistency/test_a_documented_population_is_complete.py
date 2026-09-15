"""Gate : une table de doc qui ÉNUMÈRE une population du code l'énumère en ENTIER.

Le défaut qu'elle ferme (2026-08-26)
------------------------------------
Le funnel est gaté sur trois classes de prétention — les chemins cités
existent, les inventaires de slots sont justes, la règle bindable a une
source unique. Les trois vont dans le **même sens** : de la doc vers le
code. ``test_documented_paths_exist`` le dit dans son titre : « un chemin
CITÉ par la doc existe ».

Personne ne gardait le sens inverse. Résultat, mesuré :

===============================  ==========  ==========
table                             citait      réel
===============================  ==========  ==========
``runtime.md`` § modules          13          **22**
``components.md`` § ClassVars     7           **16**
===============================  ==========  ==========

Aucune de ces tables n'était fausse — elles étaient **incomplètes**, ce
qu'aucune relecture ne voit : rien ne cloche dans une liste à qui il
manque une entrée. ``22_locale.js`` avait dix jours, ``SEALED_PROPS``
aussi, et les deux étaient introuvables pour qui lit la doc.

Pire : la table de ``runtime.md`` s'était DÉJÀ arrêtée trop tôt une fois
(à 14 alors que 15 et 16 existaient, corrigé le 2026-08-01). Elle a été
réparée sans gate. Elle a redérivé en trois semaines. C'est l'exemple
type de la règle 8 du charter — « un invariant réparé sans gate
redérive » — et ce fichier est la gate qui manquait.

Les deux sens, ici
-------------------
- **code → doc** : chaque membre de la population a une ligne. C'est le
  trou qu'on ferme.
- **doc → code** : la table ne cite rien qui n'existe plus. Sans ça, une
  table resterait « complète » en gardant les fantômes d'un module
  supprimé — et le versant licite est celui qui trouve les vrais bugs de
  gate (mesuré sur ce dépôt).

Ajouter une population
-----------------------
Une entrée dans ``_POPULATIONS``. Le contrat est volontairement pauvre :
un nom, un fichier de doc, une fonction qui rend les membres, un
plancher. Tout ce qui demande plus n'est probablement pas une
énumération.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from tests.consistency._discovery import REPO_ROOT

_FUNNEL = REPO_ROOT / ".claude" / "bretzel"

#: Preuve de morsure par contrôle POSITIF : les deux populations sont
#: lues et non vides, et le détecteur reconnaît un membre absent sur un
#: cas fabriqué.
MUTATION_PROOF = "test_the_detector_sees_a_missing_entry"

#: Les ``ClassVar`` de ``Component`` qui ne sont PAS de la config de
#: composant — donc n'ont pas à figurer dans la table de ``components.md``.
#: Nommés plutôt que filtrés par un motif : un dunder de plus doit être
#: une décision, pas un effet de bord de ``startswith("__")``.
_NOT_COMPONENT_CONFIG = frozenset({
    # Dérivés par la métaclasse depuis les props elles-mêmes ; ce sont des
    # index internes, pas une surface à déclarer.
    "__reactive_props__",
    "__scope_keys__",
})


def _runtime_modules() -> list[str]:
    """Les slabs de ``bretzel/runtime/_src/`` — ``["00_index.js", …]``."""
    return sorted(
        p.name for p in (REPO_ROOT / "bretzel" / "runtime" / "_src").glob("*.js")
    )


def _component_classvars() -> list[str]:
    """Les ``ClassVar`` déclarés sur ``Component``, dans l'ordre du code."""
    source = (
        REPO_ROOT / "bretzel" / "components" / "base" / "component.py"
    ).read_text(encoding="utf-8-sig")
    cls = next(
        node
        for node in ast.parse(source).body
        if isinstance(node, ast.ClassDef) and node.name == "Component"
    )
    return [
        node.target.id
        for node in cls.body
        if isinstance(node, ast.AnnAssign)
        and isinstance(node.target, ast.Name)
        and ast.unparse(node.annotation).startswith("ClassVar")
        and node.target.id not in _NOT_COMPONENT_CONFIG
    ]


#: ``(étiquette, fichier de doc, membres, plancher)``.
_POPULATIONS = (
    ("modules runtime", "runtime.md", _runtime_modules, 20),
    ("ClassVar de Component", "components.md", _component_classvars, 14),
)

_CASES = [
    (label, doc, member)
    for label, doc, members, _ in _POPULATIONS
    for member in members()
]


@pytest.mark.parametrize(("label", "doc", "floor"),
                         [(p[0], p[1], p[3]) for p in _POPULATIONS],
                         ids=[p[0] for p in _POPULATIONS])
def test_the_population_is_not_vacuous(label: str, doc: str, floor: int) -> None:
    """Plancher : la gate a bien LU une population.

    Sans lui, un glob mort ou un ``ClassDef`` renommé rendrait cette gate
    verte en n'ayant rien à vérifier — la pathologie que ce répertoire
    traque, et qui a rendu ``test_palette_color_is_prefixed`` aveugle
    pendant des mois.
    """
    members = next(m for lbl, _, m, _ in _POPULATIONS if lbl == label)()
    assert len(members) >= floor, (
        f"la population « {label} » ne compte plus que {len(members)} "
        f"membres (plancher {floor}) — vérifie la DÉCOUVERTE avant de "
        f"croire que cette gate passe."
    )


@pytest.mark.parametrize(
    ("label", "doc", "member"), _CASES,
    ids=[f"{lbl}:{m}" for lbl, _, m in _CASES],
)
def test_a_member_of_the_population_is_documented(
    label: str, doc: str, member: str
) -> None:
    text = (_FUNNEL / doc).read_text(encoding="utf-8-sig")
    assert member in text, (
        f"``{member}`` ({label}) n'est cité NULLE PART dans "
        f"`.claude/bretzel/{doc}`.\n"
        f"  Une table qui énumère une population du code doit l'énumérer "
        f"en entier : rien ne cloche dans une liste à qui il manque une "
        f"entrée, donc aucune relecture ne le voit.\n"
        f"  Ajoute sa ligne — et dis ce qu'il FAIT, pas seulement qu'il "
        f"existe."
    )


@pytest.mark.parametrize(("label", "doc"),
                         [(p[0], p[1]) for p in _POPULATIONS],
                         ids=[p[0] for p in _POPULATIONS])
def test_the_table_cites_no_ghost(label: str, doc: str) -> None:
    """Le versant LICITE : la table ne garde pas les morts.

    Une table « complète » qui cite encore un module supprimé est fausse
    dans l'autre sens, et la complétude seule ne l'attrape pas.
    """
    text = (_FUNNEL / doc).read_text(encoding="utf-8-sig")
    members = next(m for lbl, _, m, _ in _POPULATIONS if lbl == label)()
    if label == "modules runtime":
        import re

        cited = set(re.findall(r"\b\d{2}_[a-z_]+\.js\b", text))
        ghosts = sorted(cited - set(members))
        assert not ghosts, (
            f"`{doc}` cite des modules runtime qui n'existent plus : "
            f"{ghosts}. Retire-les — une table qui garde ses fantômes "
            f"envoie chercher du code supprimé."
        )
    else:
        # Les ClassVar sont cités en prose autant qu'en table ; on ne
        # peut pas extraire « ce que la table prétend » sans deviner.
        # Le versant licite utile ici est le contrôle positif ci-dessous.
        pytest.skip(
            "pas d'extraction fiable des ClassVar cités — le versant "
            "licite de cette population est test_the_detector_sees_a_"
            "missing_entry"
        )


def test_the_detector_sees_a_missing_entry() -> None:
    """Le détecteur reconnaît une absence — sur un cas fabriqué.

    Un ``in`` sur du texte est trivial, et c'est justement pourquoi il
    faut le prouver : si l'un des deux fichiers devenait illisible ou
    vide, tout passerait ou tout tomberait, et aucune des deux formes ne
    dirait ce qui se passe.
    """
    for _, doc, members, _ in _POPULATIONS:
        text = (_FUNNEL / doc).read_text(encoding="utf-8-sig")
        assert len(text) > 2000, (
            f"`{doc}` fait {len(text)} caractères — s'il a été vidé, la "
            f"gate ci-dessus rougirait pour la mauvaise raison."
        )
        assert "ZZ_un_membre_qui_n_existe_pas" not in text
        # Et le contrôle positif : un vrai membre est bien reconnu.
        assert members()[0] in text, (
            f"le premier membre réel n'est pas trouvé dans `{doc}` — le "
            f"détecteur ne lit pas ce qu'il croit lire."
        )
