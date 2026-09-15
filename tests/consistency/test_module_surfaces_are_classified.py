"""Gate : aucune surface publique n'est aveugle, et aucun classement ne ment.

`bretzel.introspect.modules` classe chaque nom d'`__all__` par le BESOIN
qu'il couvre. La population vient du module ; seul le classement est écrit
à la main — c'est exactement ce qu'on veut forcer à décider, et donc
exactement ce qui peut dériver.

Quatre volets, chacun pour une dérive constatée dans ce dépôt :

1. **Non-vacuité** — le balayage voit encore des symboles.
2. **Tout est classé** — un nom ajouté à un `__all__` sans entrée tombe en
   `CATEGORY_UNCLASSIFIED` et rougit ici. On n'élargit pas une surface
   publique sans dire à quoi elle sert.
3. **Aucune clé morte** — une table qui nomme un symbole inexistant. Ce
   n'est pas théorique : `_HELPER_KINDS` contenait `abort`, qui n'a jamais
   été sur `ui`, **dans le module dont la docstring cite un skill supprimé
   pour avoir nommé des symboles inexistants**. Le volet 2 ne l'attrape
   pas — une clé morte ne laisse aucun symbole non classé.
4. **Aucune section aveugle** — tout module du framework qui expose un
   `__all__` est couvert, ou déclaré exempt AVEC sa raison. Sans ce
   volet, la façon la plus simple de faire taire les trois autres serait
   de retirer un module du registre.
"""

from __future__ import annotations

import importlib
import pkgutil

import pytest

import bretzel
from bretzel.introspect import CATEGORY_UNCLASSIFIED, describe_module, module_names
from bretzel.introspect.modules import SECTIONS

#: Pas de détecteur à rendre aveugle — cf.
#: ``test_a_prohibition_gate_is_mutation_tested``.
MUTATION_NOT_APPLICABLE = (
    "compare la surface publique introspectée à une classification "
    "déclarée — une comparaison d'ensembles ne cesse pas de "
    "reconnaître, et trois tests gardent déjà les fantômes et les "
    "exemptions"
)

#: Mesuré le 2026-08-16 : 152 symboles sur les 7 sections couvertes.
_SYMBOL_FLOOR = 120

#: Modules à `__all__` volontairement hors registre, avec leur raison.
#:
#: ⚠️ `bretzel.components` en est SORTI le 2026-09-06. Sa raison — « sa
#: surface EST le catalogue `ui.*`, décrit par un mécanisme plus riche »
#: — restait vraie de ses 102 classes et fausse des treize noms qui ne
#: sont pas du catalogue (`Series`, `Move`, `apply_query`…). Une
#: exemption de MODULE ne pouvait pas exprimer ça ; `describe_module`
#: filtre maintenant les classes de composant, donc la raison est
#: appliquée là où elle vaut, nom par nom.
_EXEMPT: dict[str, str] = {
    "bretzel.introspect": (
        "l'outillage qui écrit ce classement. Se décrire soi-même n'apporte "
        "rien au lecteur du framework et rendrait la gate circulaire."
    ),
    "bretzel.lint": ("même raison que `bretzel.introspect` — outillage, couche 7."),
    "bretzel.probe": (
        "outillage, couche 7, comme ses deux voisines. Et sa surface EST "
        "décrite : `describe bretzel.probe` rend la docstring du paquet, "
        "qui porte le scénario complet. L'index répond à « quelle prop "
        "existe sur ce composant » — un harnais de vérification n'y a rien "
        "à faire."
    ),
}


def _framework_modules_with_all() -> dict[str, tuple[str, ...]]:
    """Les modules de premier niveau de `bretzel/` qui exposent un `__all__`."""
    found: dict[str, tuple[str, ...]] = {}
    for info in pkgutil.iter_modules(bretzel.__path__):
        if not info.ispkg:
            continue
        name = f"bretzel.{info.name}"
        try:
            module = importlib.import_module(name)
        except Exception:  # pragma: no cover — un module cassé a sa propre gate
            continue
        exported = getattr(module, "__all__", None)
        if exported:
            found[name] = tuple(exported)
    return found


def test_the_sweep_is_not_vacuous() -> None:
    """Volet 1."""
    total = sum(len(describe_module(name).symbols) for name in module_names())
    assert total >= _SYMBOL_FLOOR, (
        f"seulement {total} symboles balayés sur les {len(module_names())} "
        f"sections (≥ {_SYMBOL_FLOOR} attendus) — les `__all__` ne sont plus "
        f"lus, la gate ci-dessous ne protège plus rien."
    )


@pytest.mark.parametrize("name", sorted(module_names()))
def test_every_public_symbol_is_classified(name: str) -> None:
    """Volet 2."""
    unclassified = sorted(
        s.name for s in describe_module(name).symbols if s.category == CATEGORY_UNCLASSIFIED
    )
    assert not unclassified, (
        f"{name} expose {unclassified} sans dire à quel besoin ils répondent. "
        f"Ajoute-les à la table de `bretzel/introspect/modules.py` — le "
        f"classement par BESOIN est ce qui rend l'index lisible, et refuser "
        f"de le faire est le seul moyen d'élargir une surface publique en "
        f"silence."
    )


@pytest.mark.parametrize("name", sorted(module_names()))
def test_no_classification_names_a_ghost(name: str) -> None:
    """Volet 3 — la faute que le volet 2 ne peut pas voir."""
    module = importlib.import_module(name)
    exported = set(getattr(module, "__all__", ()) or ())
    ghosts = sorted(set(SECTIONS[name]) - exported)
    assert not ghosts, (
        f"la table de {name} classe {ghosts}, qui ne sont pas dans son "
        f"`__all__`. Une clé morte ne laisse AUCUN symbole non classé, donc "
        f"elle survit à toutes les autres gates — c'est comme ça qu'`abort` "
        f"est resté dans `_HELPER_KINDS` sans qu'`ui.abort` existe jamais."
    )


def test_no_public_surface_is_left_blind() -> None:
    """Volet 4 — le registre ne peut pas rétrécir en silence."""
    blind = sorted(set(_framework_modules_with_all()) - set(SECTIONS) - set(_EXEMPT))
    assert not blind, (
        f"{blind} exposent un `__all__` que rien ne décrit. Ajoute une table "
        f"dans `bretzel/introspect/modules.py`, ou une entrée dans `_EXEMPT` "
        f"AVEC sa raison — sans raison écrite, c'est juste une gate qu'on a "
        f"fait taire."
    )


def test_every_exemption_still_applies() -> None:
    """Une exemption dont le module a disparu est un mensonge résiduel."""
    stale = sorted(set(_EXEMPT) - set(_framework_modules_with_all()))
    assert not stale, (
        f"{stale} sont exemptés mais n'exposent plus d'`__all__` — retire "
        f"l'entrée, elle ne protège plus rien et suggère une couverture."
    )
