"""Gate : un nom exporté par deux modules désigne UN SEUL objet.

Le défaut qu'elle ferme
----------------------
Bretzel expose ses couches par façade (``bretzel``, ``bretzel.state``,
``bretzel.server``, …), et le même nom apparaît légitimement dans
plusieurs ``__all__`` — c'est le principe d'un ré-export. Le défaut n'est
pas le doublon, c'est le doublon **qui n'en est pas un** : deux classes
homonymes, sans lien d'héritage, dont une seule est jamais levée.

Deux occurrences mesurées dans ce dépôt, à treize mois d'écart :

- ``BretzelError`` — ``server/errors.py`` et
  ``state/persistence/redis.py``. Le ``except BretzelError`` du
  dispatcher importait la copie serveur, donc une erreur levée par redis
  passait au travers et finissait en 500 nu. Unifié le 2026-07-12.
- ``AuthRequiredError`` — ``state/registry.py`` (``RuntimeError``) et
  ``server/errors.py`` (``HTTPException``). **Seule la première était
  levée** ; la seconde était celle que ``from bretzel import
  AuthRequiredError`` rendait. Un ``except AuthRequiredError`` autour
  d'un ``UserState()`` n'attrapait donc rien, en silence. Unifié le
  2026-08-15.

Le second cas est la preuve que le premier fix était trop local : la même
maladie, dans le même fichier, n'a pas été vue parce que la gate de 2026
nommait ``BretzelError`` au lieu de décrire la classe de défaut. Celle-ci
ne nomme personne — elle balaie les façades et compare les identités.

Ce qu'elle ne peut PAS attraper
-------------------------------
Un homonyme qui n'est exporté **que** d'un côté. ``FormError`` (levé par
les validators) n'est dans aucun ``__all__`` : s'il gagnait un jumeau, le
balayage ne le verrait pas. La frontière publique est gardée ailleurs
(``test_public_surface_is_declared``) ; ici on ne garde que l'identité de
ce qui est déclaré.
"""

from __future__ import annotations

import importlib
from collections import defaultdict

import pytest

#: Pas de détecteur à rendre aveugle — cf.
#: ``test_a_prohibition_gate_is_mutation_tested``.
MUTATION_NOT_APPLICABLE = (
    "importe le même nom depuis deux modules et compare les OBJETS : "
    "l'identité se vérifie, elle ne se reconnaît pas"
)

#: Les façades publiques du paquet. Une couche ajoutée ici est une couche
#: gardée — c'est le seul endroit à toucher.
_FACADES = (
    "bretzel",
    "bretzel.core",
    "bretzel.state",
    "bretzel.render",
    "bretzel.theme",
    "bretzel.server",
    "bretzel.runtime",
    # ⚠️ ABSENTE jusqu'au 2026-08-29, et c'est le trou qui a laissé passer
    # la seule vraie collision du dépôt : ``Fragment`` / ``Html`` / ``Text``
    # nommaient DEUX objets — un nœud d'arbre dans ``core``, un composant
    # ici. Une gate qui s'appelle « un nom, un objet » et qui omet la plus
    # grosse façade du framework ne pouvait pas la voir. (Les nœuds sont
    # depuis suffixés ``Node``.)
    "bretzel.components",
    # Les deux namespaces que le premier étage expose comme MODULES.
    # Ajoutés le 2026-08-29, quand ``@auth.source`` / ``@auth.door`` y
    # sont descendus depuis le top-level : leur implémentation vit dans
    # ``server/decorators/identity.py`` et ``auth`` la ré-exporte, donc
    # c'est exactement le jour où « un nom, un objet » doit couvrir
    # ``auth``. ``test_handler_helpers_have_one_home`` ne peut pas s'en
    # charger — sa règle est « le point d'accès est ``bretzel.<nom>`` »,
    # ce qui est faux pour ces deux-là par construction.
    "bretzel.server.auth",
    "bretzel.server.oauth",
)


def _exports() -> dict[str, dict[str, object]]:
    """``{nom exporté: {module: objet}}`` sur toutes les façades."""
    seen: dict[str, dict[str, object]] = defaultdict(dict)
    for mod_name in _FACADES:
        module = importlib.import_module(mod_name)
        for name in getattr(module, "__all__", ()):
            # ``__version__`` est une str par module, pas un ré-export.
            if name.startswith("__"):
                continue
            seen[name][mod_name] = getattr(module, name)
    return seen


def _shared() -> dict[str, dict[str, object]]:
    """Les noms exportés par au moins deux façades — la population utile."""
    return {n: by_mod for n, by_mod in _exports().items() if len(by_mod) > 1}


@pytest.mark.parametrize("name", sorted(_shared()))
def test_shared_name_is_one_object(name: str) -> None:
    by_mod = _shared()[name]
    objects = list(by_mod.values())
    first_mod, first_obj = next(iter(by_mod.items()))
    for mod_name, obj in by_mod.items():
        assert obj is first_obj, (
            f"{name!r} est exporté par {len(objects)} façades mais désigne "
            f"des objets DIFFÉRENTS : {first_mod}.{name} is not "
            f"{mod_name}.{name}. Un utilisateur qui importe l'un et attend "
            f"l'autre échoue en silence — c'est très exactement le bug "
            f"AuthRequiredError du 2026-08-15. Canonise la définition dans "
            f"la couche la plus basse que les deux peuvent importer "
            f"(``core/`` en général) et ré-exporte."
        )


def test_sweep_is_not_vacuous() -> None:
    """Plancher : le balayage voit des façades ET des noms partagés.

    Ancré sur la DÉCOUVERTE (les noms effectivement partagés), pas sur une
    population qu'on pourrait vider en déplaçant un fichier. Si un refactor
    fait tomber ce compte à zéro, la paramétrisation ci-dessus ne
    produirait plus AUCUN cas et resterait verte — le pire vert.
    """
    shared = _shared()
    assert len(shared) >= 8, (
        f"Seulement {len(shared)} noms partagés trouvés sur "
        f"{len(_FACADES)} façades — le balayage a probablement cassé "
        f"(``__all__`` vidé, façade renommée). Vu au moment de l'écriture : "
        f"BretzelError, AuthRequiredError, Bretzel, abort, redirect, page, "
        f"layout, refreshable…"
    )
    assert "BretzelError" in shared and "AuthRequiredError" in shared, (
        "Les deux noms qui ont motivé cette gate ne sont plus partagés — "
        "soit ils ont été dé-exportés (alors retire-les de ce plancher), "
        "soit le balayage ne lit plus les bons ``__all__``."
    )
