"""Le câblage ``loading=`` partagé par Button et IconButton.

Les deux composants ont la même mécanique de chargement — construire le
spinner tôt, verrouiller le bouton pendant la fenêtre asynchrone, et
faire un mutex entre le spinner et l'icône de tête — et seul l'habillage
autour diffère (Button intercale un label et une icône de droite,
IconButton n'a qu'un glyphe).

Ces trois morceaux vivaient en double (audit F09). Le wrapper de mutex
lui-même (``Component._cloak_show``) était déjà un primitive du socle :
ce qui restait non partagé, c'est la construction anticipée du spinner,
le OR-combine ``loading || disabled``, et la colle qui les assemble.
"""

from __future__ import annotations

from typing import Any

from bretzel.components.base import Component
from bretzel.components.primitives.spinner import Spinner
from bretzel.core.tree import Node
from bretzel.runtime.protocol import BZ_ATTR_PREFIX


def build_loading_spinner(component: Component) -> Spinner | None:
    """Le spinner du bouton, construit **dans ``__init__``**.

    ⚠️ Anticipé à dessein : ``Spinner.__init__`` a besoin d'un contexte
    de render vivant pour allouer son id, et ``render()`` peut tourner
    après que ce contexte a été démonté (cas des tests unitaires).

    Construit dès que ``loading`` est vrai **ou** porte un binding — le
    cas réactif a besoin du nœud DOM même si ``loading`` vaut False au
    SSR, puisque le mutex émet les deux branches pour que le runtime les
    bascule en ``bz-show``.
    """
    if not (component._reactive_values.get("loading")
            or "loading" in component._binding_metadata):
        return None
    size = component._reactive_values.get("size") or "md"
    return Component.adopt_slot(Spinner(size=size))


def apply_loading_disabled(
    component: Component, attrs: dict[str, Any], loading_path: str,
) -> None:
    """``bz-attr:disabled = (loading) || (disabled)``.

    L'attribut HTML ``disabled`` doit rester vrai tant que l'UN des deux
    l'est — sinon un ``loading`` qui retombe déverrouillerait un bouton
    par ailleurs désactivé. Le côté ``disabled`` est soit un binding,
    soit l'instantané SSR figé en littéral JS.
    """
    disabled_binding = component._binding_metadata.get("disabled")
    if disabled_binding is not None:
        dis_path = component.path_of(disabled_binding)
    else:
        dis_path = (
            "true" if component._reactive_values.get("disabled") else "false"
        )
    attrs[f"{BZ_ATTR_PREFIX}disabled"] = f"({loading_path}) || ({dis_path})"


def loading_leading_children(
    component: Component,
    *,
    loading: bool,
    loading_path: str | None,
    spinner: Spinner | None,
    icon: Component | None,
) -> list[Node]:
    """Le mutex spinner ↔ icône de tête, dans l'ordre des enfants.

    - **Réactif** (``loading_path``) : les DEUX branches sont émises et
      le runtime les mutexe en ``bz-show`` — on ne peut pas choisir au
      SSR ce que le client décidera.
    - **Statique** : l'une OU l'autre, jamais les deux.

    Chaque appelant ajoute ensuite ce qui lui est propre (le label et
    l'icône de droite pour Button).
    """
    children: list[Node] = []
    if loading_path is not None:
        assert spinner is not None, (
            "un loading réactif exige le spinner construit en __init__"
        )
        children.append(component._cloak_show(
            spinner.render(), loading_path, initial=loading,
        ))
        if icon is not None:
            children.append(component._cloak_show(
                icon.render(), f"!{loading_path}", initial=not loading,
            ))
        return children
    if loading and spinner is not None:
        children.append(spinner.render())
    elif not loading and icon is not None:
        children.append(icon.render())
    return children


__all__ = [
    "apply_loading_disabled",
    "build_loading_spinner",
    "loading_leading_children",
]
