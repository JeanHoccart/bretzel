"""Gate G6 — une table ``sizes`` couvre les 5 paliers, ou déclare
explicitement qu'elle est plus étroite.

Le défaut n'est pas « avoir moins de 5 paliers » — c'est la **dégradation
silencieuse**. Le render fait ``size_map.get(size_key) or
size_map.get("md")`` : un ``size="xl"`` sur un composant dont la table
s'arrête à ``lg`` rend en ``md``, sans erreur, sans warning. À côté d'un
``ui.select(size="xl")`` dans le même formulaire, le contrôle est
visiblement plus petit et rien ne l'explique (audit F91, ToggleGroup).

La gate exige donc que chaque table couvre ``xs..xl``, **sauf** entrée
dans ``_NARROW_BY_DESIGN`` — qui demande d'écrire les paliers réellement
supportés ET la raison. L'égalité est stricte dans les deux sens : un
composant qui complète sa table doit sortir de la liste, un composant qui
en déclare une fausse rougit aussi. La liste ne peut donc pas pourrir en
« cas acceptés » qu'on empile.

⚠️ Un palier déclaré ici doit l'être aussi dans ``bretzel describe`` (la
signature publique dit `size="sm"|"md"|"lg"`), sinon l'app author lit un
enum à 5 valeurs et en écrit une qui ne fait rien.

Complémentaire de ``test_size_reaches_slots``, qui vérifie que le palier
atteint tous les slots — pas que le palier existe.
"""

from __future__ import annotations

import pytest

from bretzel.components.base import SIZE_SCALE, is_size_keyed
from tests.consistency._discovery import public_component_classes

#: Pas de détecteur à rendre aveugle — cf.
#: ``test_a_prohibition_gate_is_mutation_tested``.
MUTATION_NOT_APPLICABLE = (
    "compare les clés d'une table de tailles à l'échelle déclarée ; "
    "`test_the_scale_itself_is_pinned` épingle l'échelle et "
    "`test_the_sweep_is_not_vacuous` la population"
)

#: Les cinq paliers — lus sur le socle depuis le 2026-08-16. Cette ligne
#: était l'une des CINQ copies de l'échelle dans ``tests/``, pour zéro
#: dans ``bretzel/`` : un enum annoncé « fermé » que le code ne portait
#: nulle part, donc que rien ne pouvait refuser.
_FULL = frozenset(SIZE_SCALE)

# {composant: (paliers supportés, pourquoi)}. Ces trois-là annoncent leur
# enum restreint dans ``bretzel describe`` — c'est un choix, pas un oubli.
_NARROW_BY_DESIGN: dict[str, tuple[frozenset[str], str]] = {
    "Table": (frozenset({"sm", "md", "lg"}),
              "densité de cellule ; `sm` EST l'ancien `compact=True`. "
              "Un tableau xs/xl n'a pas de sens de lecture."),
    "Datatable": (frozenset({"sm", "md", "lg"}),
                  "la taille EST celle de la Table composée — elle en "
                  "hérite les paliers, sinon `datatable(size='xl')` "
                  "rendrait une table `md` avec un pager plus gros."),
    "Tree": (frozenset({"sm", "md", "lg"}),
             "densité de ligne + indentation ; mêmes paliers que Table, "
             "avec qui il partage les usages (explorateur, outline)."),
    "Banner": (frozenset({"sm", "md", "lg"}),
               "bandeau pleine largeur au niveau page : xs serait "
               "illisible, xl occuperait l'écran."),
}


def _size_keysets(cls: type) -> list[tuple[str, frozenset[str]]]:
    """``(étiquette, clés)`` par table de tailles trouvée sur le thème.

    Deux formes vivent dans le repo : ``sizes[palier]`` (plate ou
    size-first) et la forme inversée ``sizes[slot][palier]``.

    La DISCRIMINATION entre les deux est lue sur le socle
    (:func:`bretzel.components.base.is_size_keyed`) plutôt que refaite ici
    — elle est identique à celle dont la règle de lint ``value-outside-the-table``
    a besoin, et deux implémentations d'un même arbitrage finissent par ne
    plus trancher pareil. Ce qui reste local, c'est le FORMAT du retour :
    cette gate a besoin d'un keyset par slot pour nommer le coupable, là
    où le linter n'a besoin que du vocabulaire à plat.
    """
    sizes = (getattr(cls, "THEME", {}) or {}).get("sizes")
    if not isinstance(sizes, dict) or not sizes:
        return []
    if is_size_keyed(sizes):
        return [("sizes", frozenset(sizes))]
    return [
        (f"sizes[{slot!r}]", frozenset(row))
        for slot, row in sizes.items()
        if isinstance(row, dict) and is_size_keyed(row)
    ]


def test_the_scale_itself_is_pinned() -> None:
    """Plancher : ``SIZE_SCALE`` ne peut pas rétrécir en silence.

    Ce test n'existait pas avant le 2026-08-16 et il n'aurait servi à rien :
    l'échelle était recopiée dans chaque gate, donc l'amputer demandait
    cinq éditions visibles. Depuis qu'elle a un domicile unique, **une
    seule ligne** gouverne ce fichier, ``test_size_reaches_slots``,
    ``test_sizes_are_distinct``, ``test_playground_demos_the_api`` et la
    règle de lint ``value-outside-the-table``.

    Mutation-testé : réduire ``SIZE_SCALE`` à ``("sm", "md", "lg")``
    laissait les trois gates **vertes**. Chacune compare une population à
    l'échelle ; une échelle plus petite rend l'exigence plus facile, jamais
    plus rouge. La centralisation supprime cinq dérives possibles et en
    crée une, plus grave — d'où ce plancher, qui est le prix de la
    consolidation.
    """
    assert SIZE_SCALE == ("xs", "sm", "md", "lg", "xl"), (
        f"`SIZE_SCALE` vaut {SIZE_SCALE!r}. Cette constante gouverne quatre "
        f"gates et une règle de lint : en retirer un palier les assouplit "
        f"TOUTES d'un coup, sans qu'aucune ne rougisse. Si l'échelle des "
        f"contrôles change pour de vrai, c'est une décision d'API — mets "
        f"``bretzel describe`` à jour et change cette ligne exprès."
    )


_SIZED = [c for c in public_component_classes() if _size_keysets(c)]


@pytest.mark.parametrize("cls", _SIZED, ids=lambda c: c.__name__)
def test_size_table_covers_the_declared_enum(cls: type) -> None:
    declared, why = _NARROW_BY_DESIGN.get(
        cls.__name__, (_FULL, "l'enum standard du framework"))

    for label, keys in _size_keysets(cls):
        tiers = keys & _FULL
        missing = sorted(declared - tiers)
        assert not missing, (
            f"{cls.__name__}.THEME[{label}] n'a pas {missing} — un "
            f"`size={missing[0]!r}` retombe EN SILENCE sur `md` (le render "
            f"fait `size_map.get(k) or size_map.get('md')`), donc plus petit "
            f"qu'un composant voisin au même palier.\n"
            f"Paliers attendus : {sorted(declared)} ({why}).\n"
            f"Fix : compléter la table, ou — si la restriction est voulue — "
            f"l'inscrire dans `_NARROW_BY_DESIGN` AVEC la raison, et écrire "
            f"l'enum réel dans la signature publique d'``bretzel describe``."
        )
        extra = sorted(tiers - declared)
        assert not extra, (
            f"{cls.__name__}.THEME[{label}] porte {extra}, hors de l'enum "
            f"déclaré {sorted(declared)}. Si la table a été complétée, "
            f"retire l'entrée de `_NARROW_BY_DESIGN` (l'égalité est stricte "
            f"pour que la liste ne devienne pas un cimetière de cas "
            f"acceptés)."
        )


def test_the_sweep_is_not_vacuous() -> None:
    """Plancher : les composants dimensionnés sont bien découverts."""
    assert len(_SIZED) >= 35, (
        f"seulement {len(_SIZED)} composants dimensionnés découverts (44 le "
        f"2026-08-19) — la découverte est cassée."
    )
