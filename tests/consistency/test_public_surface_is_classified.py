"""Gate : sur une façade utilisateur, tout nom est classé — public ou interne.

Le défaut qu'elle ferme
-----------------------
``__all__`` avait deux sens dans ce dépôt, sans que ce soit écrit nulle
part : « ce que l'utilisateur écrit » et « ce que cette couche exporte
vers les autres ». Les deux populations vivaient mélangées, sans
marqueur. Mesuré le 2026-08-15 :

=================  ==========  ==========================================
``bretzel.state``  **31** noms  dont 21 de plomberie
``bretzel.theme``  **18** noms  dont 13 jamais cités hors du framework
``bretzel.render`` **26** noms  presque intégralement de la plomberie
=================  ==========  ==========================================

Le critère était même *inversé* : ``FormError`` — le mécanisme de
validation croisée que le playground utilise — n'était PAS dans
``bretzel.state.__all__``, pendant que ``RedisBackend`` y était.

Ce que ça coûtait : un ``from bretzel.state import <tab>`` proposait 31
entrées dont deux tiers ne concernent pas l'auteur d'une app. C'est la
forme concrète de « on va oublier ce qui existe » — non pas parce que les
noms manquent, mais parce qu'ils sont noyés.

Ce que ce nettoyage ne casse PAS : retirer un nom d'``__all__`` ne le
dé-importe pas. Les 21 noms de plomberie étaient déjà importés par leur
chemin profond **partout** (mesuré : zéro import depuis la façade), donc
la modification est déclarative, pas structurelle.

L'invariant gardé
-----------------
Sur chaque façade utilisateur, tout nom défini par ``bretzel`` et
atteignable sur le module est **soit** dans ``__all__`` (API utilisateur)
**soit** dans ``_INTERNAL`` (plomberie de la couche). Un nom ajouté à une
façade force donc une décision, au lieu de rejoindre le tas par défaut.

Les couches internes (``core``, ``render``, ``runtime``) sont hors
balayage : leur ``__all__`` EST le contrat inter-couche, et leur docstring
le déclare. Ce n'est pas un second système — c'est la même règle (« la
liste décrit la surface de CE module ») appliquée à un module dont la
surface n'est pas utilisateur.

Ce qu'elle ne peut PAS attraper
--------------------------------
Un nom **bien** classé mais mal nommé, ou public sans être documenté nulle
part. La couverture par la doc est le travail de ``test_docs_coverage`` ;
ici on ne garde que l'exhaustivité de la classification.
"""

from __future__ import annotations

import importlib
import inspect

import pytest

#: Pas de détecteur à rendre aveugle — cf.
#: ``test_a_prohibition_gate_is_mutation_tested``.
MUTATION_NOT_APPLICABLE = (
    "même forme : deux listes déclarées confrontées aux `__all__` "
    "réels, avec un test par mode d'échec (chevauchement, fantôme, "
    "couche interne)"
)

#: Les façades qu'un auteur d'app tape. Ajouter une entrée = la gater.
#:
#: ``bretzel.server.auth`` est arrivé le 2026-08-15, en constatant qu'il
#: avait échappé au premier passage : c'est un MODULE ré-exposé en
#: attribut (``from bretzel import auth``), pas un package, donc il ne
#: ressemblait pas aux autres. Un trou dans cette liste, pas dans le code
#: — et c'est exactement le genre d'oubli que ``test_internal_layer_says_so``
#: existe pour rendre coûteux : une façade absente d'ici est indiscernable
#: d'une couche interne.
_USER_FACADES = (
    "bretzel",
    "bretzel.state",
    "bretzel.theme",
    "bretzel.server",
    "bretzel.server.auth",
)

#: Les couches internes, explicitement hors balayage. Leur docstring doit
#: le dire — c'est vérifié plus bas, pour que l'exclusion reste un choix
#: écrit et pas un oubli.
_INTERNAL_LAYERS = ("bretzel.core", "bretzel.render", "bretzel.runtime")


def _framework_names(mod_name: str) -> set[str]:
    """Les noms du module qui viennent de ``bretzel`` — pas des imports
    stdlib/typing que tout ``__init__`` traîne."""
    module = importlib.import_module(mod_name)
    found = set()
    for name in dir(module):
        if name.startswith("_"):
            continue
        value = getattr(module, name)
        if inspect.ismodule(value):
            continue
        origin = getattr(value, "__module__", None)
        if origin and origin.startswith("bretzel"):
            found.add(name)
    return found


def _declared(mod_name: str) -> tuple[set[str], set[str]]:
    module = importlib.import_module(mod_name)
    return set(getattr(module, "__all__", ())), set(getattr(module, "_INTERNAL", ()))


@pytest.mark.parametrize("mod_name", _USER_FACADES)
def test_every_framework_name_is_classified(mod_name: str) -> None:
    public, internal = _declared(mod_name)
    unclassified = _framework_names(mod_name) - public - internal
    assert not unclassified, (
        f"{mod_name} porte {sorted(unclassified)} sans les classer. Sur une "
        f"façade utilisateur, un nom est SOIT dans ``__all__`` (ce que "
        f"l'auteur d'une app écrit) SOIT dans ``_INTERNAL`` (la plomberie "
        f"de la couche, importable par son chemin). Le tas par défaut est "
        f"exactement ce qui a mis 21 noms de plomberie dans "
        f"``bretzel.state.__all__`` pendant que ``FormError`` en était exclu."
    )


@pytest.mark.parametrize("mod_name", _USER_FACADES)
def test_the_two_lists_do_not_overlap(mod_name: str) -> None:
    public, internal = _declared(mod_name)
    both = public & internal
    assert not both, (
        f"{mod_name} : {sorted(both)} est à la fois public et interne. "
        f"La classification doit trancher."
    )


@pytest.mark.parametrize("mod_name", _USER_FACADES)
def test_no_declared_name_is_a_ghost(mod_name: str) -> None:
    """Une liste qui nomme ce qui n'existe pas est une liste qui a pourri."""
    module = importlib.import_module(mod_name)
    public, internal = _declared(mod_name)
    ghosts = sorted(n for n in public | internal if not hasattr(module, n))
    assert not ghosts, (
        f"{mod_name} déclare {ghosts}, qui n'existe(nt) pas sur le module."
    )


@pytest.mark.parametrize("mod_name", _INTERNAL_LAYERS)
def test_internal_layer_says_so(mod_name: str) -> None:
    """L'exclusion du balayage est un choix ÉCRIT, pas un oubli.

    Sans cette assertion, une façade utilisateur qu'on oublierait
    d'ajouter à ``_USER_FACADES`` serait indistinguable d'une couche
    interne — et la gate resterait verte en ne la regardant pas.
    """
    doc = importlib.import_module(mod_name).__doc__ or ""
    assert "Couche INTERNE" in doc, (
        f"{mod_name} est exclu du balayage mais sa docstring ne le déclare "
        f"pas. Écris « **Couche INTERNE — aucune surface utilisateur.** » "
        f"et dis ce que ``__all__`` y signifie, ou déplace le module dans "
        f"``_USER_FACADES``."
    )


def test_sweep_is_not_vacuous() -> None:
    """Plancher : le balayage voit de vrais noms sur chaque façade.

    Ancré sur la DÉCOUVERTE. Un ``dir()`` qui ne rendrait plus rien — ou
    un ``__module__`` qui cesserait de commencer par « bretzel » après un
    refactor de packaging — rendrait ``unclassified`` vide et les trois
    tests ci-dessus verts sans avoir rien lu.
    """
    for mod_name in _USER_FACADES:
        names = _framework_names(mod_name)
        assert len(names) >= 10, (
            f"{mod_name} : seulement {len(names)} noms issus de bretzel "
            f"découverts (>= 10 attendus) — le balayage ne lit plus rien."
        )
    public, internal = _declared("bretzel.state")
    assert "FormError" in public, (
        "``FormError`` est le nom qui a motivé cette gate : user-facing, "
        "utilisé par le playground, et absent d'``__all__``. S'il en sort, "
        "c'est une décision à écrire, pas un effet de bord."
    )
    assert len(internal) >= 10, (
        f"``bretzel.state._INTERNAL`` est tombé à {len(internal)} entrées — "
        f"la plomberie a-t-elle vraiment disparu, ou la liste a-t-elle été "
        f"vidée ?"
    )
