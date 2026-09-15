"""Gate — aucune ``reactive_prop`` ne porte le nom d'un kwarg
**universel**.

``Component.__init__`` absorbe une liste fermée de kwargs pour tous les
composants : ``classes``, ``style``, ``slots``, ``key``, ``id``, ``tag``,
``attrs``, ``visible``, ``tooltip``, ``debounce``, ``throttle``. Ils sont
``pop``és du dict AVANT le routage vers les ``reactive_prop``.

Conséquence : une ``reactive_prop`` portant un de ces noms ne peut
JAMAIS recevoir de valeur — le ``pop`` la sert avant. La mort est
doublement silencieuse : la valeur part dans le mécanisme universel (en
produisant souvent quelque chose d'absurde) pendant que la prop reste à
son défaut. Ni le constructeur, ni le rendu, ni les tests ne lèvent.

⚠️ Ce n'est PAS « interdire le nom dans la signature ». Intercepter un
kwarg universel pour le transformer est légitime tant que la valeur
finit dans le mécanisme du socle : ``Outlet(id=…)`` dérive l'id puis le
passe à ``super().__init__(id=derived)``, ``ToggleButton(tooltip=…)``
écrit dans ``self._tooltip``, le slot que le socle lit. Les deux
marchent. Le conflit n'existe qu'avec une **``reactive_prop``**, qui a
son propre canal d'alimentation — celui que le ``pop`` court-circuite.

C'est arrivé (audit F27) : ``ui.icon(name, style=…)`` voulait dire le
suffixe Iconify (``"bold"`` / ``"fill"`` / ``"duotone"``). Le socle
prenait la valeur pour du CSS inline, donc l'icône rendait
``style="fill"`` — du CSS invalide — et le glyphe ne changeait jamais.
Le playground l'exerçait sur 4 icônes Phosphor, sans effet, et
``bretzel describe`` documentait le paramètre comme s'il marchait. Renommé
en ``icon_style=``.

La gate lit la liste des kwargs absorbés directement dans le source de
``Component.__init__`` (les ``kwargs.pop("<nom>"``) plutôt que de la
recopier : ajouter un kwarg universel étend automatiquement la
protection, et un rename ne peut pas laisser la gate garder un nom mort.
"""

from __future__ import annotations

import pytest

from bretzel.components.base.component import RESERVED_KWARGS
from tests.consistency._discovery import public_component_classes

#: Pas de détecteur à rendre aveugle — cf.
#: ``test_a_prohibition_gate_is_mutation_tested``.
MUTATION_NOT_APPLICABLE = (
    "intersecte les props réactives déclarées avec l'ensemble des "
    "kwargs universels ; `test_the_universal_set_was_found` garde "
    "l'ensemble, et une intersection n'a pas d'orthographe à rater"
)

# Extrait du socle, pas recopié : ajouter un kwarg universel étend
# automatiquement la protection, et un rename ne peut pas laisser ici un
# nom mort.
_UNIVERSAL = frozenset(RESERVED_KWARGS)


def test_the_universal_set_was_found() -> None:
    """Garde-fou du garde-fou : si l'extraction rend une liste vide (le
    socle refactoré, les ``pop`` déplacés), la gate passerait au vert
    sans rien vérifier."""
    assert len(_UNIVERSAL) >= 8, (
        f"seulement {sorted(_UNIVERSAL)} extraits de Component.__init__ — "
        f"l'extraction des kwargs universels ne suit plus le socle, la "
        f"gate ne protège plus rien."
    )


@pytest.mark.parametrize("cls", public_component_classes(), ids=lambda c: c.__name__)
def test_no_reactive_prop_shadows_a_universal_kwarg(cls: type) -> None:
    offenders = sorted(set(getattr(cls, "__reactive_props__", {}) or {}) & _UNIVERSAL)
    assert not offenders, (
        f"{cls.__name__} déclare la/les reactive_prop {offenders}, dont le "
        f"nom est absorbé par `Component.__init__` pour TOUS les composants "
        f"(kwargs universels : {sorted(_UNIVERSAL)}).\n\n"
        f"La prop ne peut JAMAIS recevoir de valeur : le socle `pop` le "
        f"kwarg avant le routage. La valeur part dans le mécanisme "
        f"universel — et y produit souvent une absurdité, comme le "
        f'`style="fill"` en CSS inline d\'`ui.icon` (audit F27) — pendant '
        f"que la prop reste à son défaut. Rien ne lève.\n\n"
        f"Fix : renommer la prop ET le paramètre hors de l'ensemble "
        f"universel (ex. `style` → `icon_style`), et corriger "
        f"``bretzel describe``."
    )
