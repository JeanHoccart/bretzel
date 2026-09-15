"""Un composant ne redéclare pas ce que la classe de base dit déjà.

``DEFAULT_TAG = "div"``, ``IS_CONTAINER = True``, ``EVENTS = ()`` — écrits
dans un composant, ces trois-là ne font **rien** : ils recopient le défaut
de ``Component``. Le rendu est identique avec ou sans.

Pourquoi c'est une gate et pas juste du ménage (audit du socle, item 8)
------------------------------------------------------------------------
Le contrat d'auteur de Bretzel est plus large que celui de ses pairs — 6
ClassVar quasi-universelles contre 2 chez Svelte ou LiveView. C'est assumé :
ce contrat est **introspectable, donc gatable**, et c'est ce qui paie les
gates de ce répertoire.

Mais 90 des déclarations mesurées ne portaient **aucune information** — de
la cérémonie. Et la cérémonie a un coût précis : elle rend invisibles les
déclarations qui, elles, disent quelque chose. Un lecteur qui voit
``IS_CONTAINER`` écrit sur 72 composants n'apprend rien ; écrit sur les 43
qui divergent du défaut, il apprend exactement quels composants refusent un
bloc ``with``.

Supprimer les redites fait passer le contrat obligatoire de 6 à 3-4 **sans
toucher à un seul mécanisme**. C'est là que la surface maigrit sans rien
perdre.

⚠️ ``THEME_KEY`` n'est PAS dans cette gate, délibérément. Il vaut
``snake_case(nom de classe)`` pour 66 composants sur 71 — donc dérivable en
apparence — mais les 5 qui ne le déclarent pas ont tous un ``THEME`` **vide** :
``THEME_KEY = ""`` dit correctement « je n'ai pas de thème », alors qu'un
``"fragment"`` dérivé pointerait vers un thème inexistant. L'exception est
porteuse de sens, on la garde.
"""

from __future__ import annotations

import pytest

from bretzel.components.base.component import Component
from tests.consistency._discovery import public_component_classes

# ClassVar dont redéclarer le défaut est un no-op mesuré. La valeur de
# référence est LUE sur ``Component`` — pas recopiée ici, sinon la gate se
# périme le jour où un défaut change.
_CHECKED: tuple[str, ...] = ("DEFAULT_TAG", "IS_CONTAINER", "EVENTS")

_CLASSES = public_component_classes()


def test_the_gate_has_a_population() -> None:
    """Plancher de non-vacuité."""
    assert len(_CLASSES) >= 60, (
        f"seulement {len(_CLASSES)} composants découverts (76 le "
        f"2026-07-29) — la découverte a régressé."
    )


@pytest.mark.parametrize("cls", _CLASSES, ids=lambda c: c.__name__)
def test_no_classvar_merely_restates_the_base_default(cls: type) -> None:
    offenders = [
        name
        for name in _CHECKED
        if name in cls.__dict__ and cls.__dict__[name] == getattr(Component, name)
    ]
    assert not offenders, (
        f"{cls.__name__} redéclare {offenders} avec la valeur que "
        f"``Component`` donne déjà — la ligne ne porte aucune information "
        f"et rend invisibles les déclarations qui en portent une.\n"
        f"  Retire-la : le rendu est identique au byte près (vérifié sur "
        f"les 76 composants lors de la suppression des 90 redites)."
    )


def test_the_checked_names_still_exist_on_the_base() -> None:
    """Garde-fou : si l'une des trois ClassVar disparaissait du socle, la
    comparaison ci-dessus lèverait ``AttributeError`` au lieu de tester —
    ou pire, ``getattr`` avec un défaut la rendrait vacuously verte."""
    for name in _CHECKED:
        assert hasattr(Component, name), (
            f"``Component.{name}`` n'existe plus — cette gate compare à un "
            f"défaut fantôme. Mets ``_CHECKED`` à jour."
        )
