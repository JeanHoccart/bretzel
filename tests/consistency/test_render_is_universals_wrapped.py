"""Le ``render()`` de chaque composant passe par le wrap métaclasse.

Le wrap (``_ComponentMeta.__new__``) est ce qui applique, APRÈS le
``render()`` du composant et pour tout le monde à la fois :

1. ``_apply_bindable_carriers`` — forward d'un ``bz-attr:`` vers le porteur
   déclaré dans ``BINDABLE_CARRIERS`` ;
2. ``_ensure_scope_identity`` — pose ``id`` / ``bz-id`` quand le composant
   émet un scope ``bz-data`` que le runtime doit retrouver après un morph ;
3. ``_apply_universal_modifiers`` — ``classes=``, ``style=``, ``visible=``,
   ``tooltip=`` et ``slots={"root"}`` sur le VRAI root.

Pourquoi cette gate existe (audit du socle 2026-07-29, item « ménage »)
------------------------------------------------------------------------
Trois composants — date_picker, date_range_picker, file_upload — portaient
un ``_needs_identity`` surchargé, avec le même commentaire recopié mot pour
mot dans les trois fichiers. Mesuré avant suppression : ``id`` et ``bz-id``
sont posés **dans les deux cas**, avec la même valeur — seule leur position
dans la liste d'attributs change (en tête via ``emit_attrs``, en queue via
``_ensure_scope_identity``). Les overrides étaient donc morts.

Mais les supprimer déplace la responsabilité sur le wrap. Or le wrap ne
s'installe que si la sous-classe définit ``render`` **dans son propre
namespace** (``namespace.get("render")``) — un composant qui hériterait un
``render`` non wrappé n'aurait ni identité, ni universels, ni carriers, et
**échouerait en silence**. Aujourd'hui 0 cas sur 77, mais rien ne le gardait.

C'est le contre-exemple du pattern « le socle applique, donc 0 dérive » :
le socle applique bien, à condition que le wrap soit là. Cette gate vérifie
la condition.
"""

from __future__ import annotations

import pytest

from bretzel.components.base.component import Component
from tests.consistency._discovery import public_component_classes

_CLASSES = public_component_classes()


def test_the_gate_has_a_population() -> None:
    """Plancher de non-vacuité — cette gate est une vérification par
    composant, elle passerait vide."""
    assert len(_CLASSES) >= 60, (
        f"seulement {len(_CLASSES)} composants publics découverts "
        f"(76 mesurés le 2026-07-29) — la découverte a régressé."
    )


@pytest.mark.parametrize("cls", _CLASSES, ids=lambda c: c.__name__)
def test_render_carries_the_universals_wrap(cls: type) -> None:
    render = cls.render
    assert getattr(render, "_bz_universals_wrapped", False), (
        f"{cls.__name__}.render n'est PAS wrappé par la métaclasse. "
        f"Conséquence silencieuse : pas de `classes=`, pas de `style=`, "
        f"pas de `visible=`, pas de `slots={{'root'}}`, pas de forward "
        f"`BINDABLE_CARRIERS`, et pas d'`id`/`bz-id` sur un scope `bz-data` "
        f"— donc un scope client recréé à chaque morph idiomorph.\n"
        f"  Cause probable : {cls.__name__} ne définit pas `render` dans son "
        f"propre namespace et hérite d'un `render` non wrappé. Le wrap "
        f"s'installe dans `_ComponentMeta.__new__` sur "
        f"`namespace.get('render')`."
    )


def test_the_base_render_is_deliberately_unwrapped() -> None:
    """``Component.render`` lui-même n'est PAS wrappé — c'est voulu (la base
    est abstraite, les universels n'agissent que sur une instance). On le
    fige : si ça changeait, le test ci-dessus deviendrait tautologique."""
    assert not getattr(Component.render, "_bz_universals_wrapped", False), (
        "Component.render est désormais wrappé — le wrap se poserait deux "
        "fois sur les sous-classes, ou la gate ci-dessus ne vérifierait "
        "plus rien. Revoir `_ComponentMeta.__new__`."
    )
