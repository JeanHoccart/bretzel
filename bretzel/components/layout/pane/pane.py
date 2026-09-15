"""``Pane`` — la région qui défile.

Une colonne qui prend la place restante de son parent et défile quand
son contenu la dépasse. C'est tout ce qu'elle fait, et c'est
délibérément peu : ce qui justifie le composant n'est pas le nombre de
classes qu'il économise, c'est que **deux d'entre elles ne se devinent
pas** — cf. le thème, qui porte les deux mesures.

Où on l'écrit
--------------
Partout où une zone doit défiler pendant que ses voisines restent en
place. Mesuré sur le dépôt au 2026-08-23 : dix-sept sites, treize apps,
et **quatre hors coque** — le fil de messages de ``examples/chat``, les
deux colonnes maître-détail de ``examples/crm`` (liste + fiche), une
colonne du pipeline. Ce n'est donc pas du mobilier de coque.

Ce qu'elle attend de son parent
--------------------------------
Une hauteur. Soit parce qu'il est une colonne flex à hauteur définie
(``ui.viewport``, une carte ``h-full``), soit parce qu'il a lui-même une
hauteur (un ``ui.resizable_panel``). Sans hauteur nulle part au-dessus,
``h-full`` ne résout pas, ``flex-1`` n'a rien à partager, et le pane
grandit au lieu de défiler — silencieusement. C'est la contrainte connue
du modèle « document gelé » (Quasar la documente pareil pour son mode
``container``).

Dans un parent BLOC, elle prend toute la hauteur : elle doit alors être
le seul enfant. Un frère en-tête déborderait, faute d'espace restant à
calculer — c'est une propriété du bloc, pas du composant.

Pourquoi pas de ``wrap``
-------------------------
:class:`VStack` l'expose, pas elle. Une colonne qui défile ne se replie
pas — et ``wrap`` est très exactement la prop qui a produit le finding
[4] (un item dont la base vaut 100 % ne peut jamais partager une ligne
de repli).

"""

from __future__ import annotations

from typing import Any, ClassVar

from bretzel.components.base import reactive_prop
from bretzel.components.layout.pane.theme import PANE_THEME
from bretzel.components.layout.stack import VStack


class Pane(VStack):
    """Région qui défile : une colonne qui prend la place restante."""

    THEME: ClassVar[dict[str, Any]] = PANE_THEME
    THEME_KEY: ClassVar[str] = "pane"

    #: ``direction`` vient de :class:`VStack` (un pane est une colonne) ;
    #: ``wrap`` est scellé ici. Déclarer plutôt que taire : une prop
    #: héritée et refusée à l'appel serait annoncée utilisable par
    #: ``bretzel describe``, et le lecteur prendrait un ``TypeError``.
    SEALED_PROPS: ClassVar[tuple[str, ...]] = ("direction", "wrap")
    SEALED_REASONS: ClassVar[dict[str, str]] = {
        "wrap": (
            "ui.pane ne se replie pas : une colonne qui DÉFILE n'a pas de "
            "lignes à répartir. C'est aussi la prop qui a produit le "
            "finding [4] — un item dont la base vaut 100 % ne peut jamais "
            "partager une ligne de repli. Mets un ui.flex(wrap=True) DANS "
            "le pane."
        ),
    }

    #: Respiration intérieure. ``none`` par défaut : la moitié des sites
    #: n'en veut pas (une coque met son padding plus bas, autour de
    #: l'outlet), et une valeur non nulle par défaut serait à retirer
    #: plus souvent qu'à poser.
    padding: str = reactive_prop(default="none", emit_attr=False)

    def __init__(
        self,
        *,
        gap: str | dict | None = None,
        padding: str | None = None,
        align: str | None = None,
        justify: str | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(
            gap=gap, padding=padding, align=align, justify=justify, **kwargs
        )

    def _compose_classes(self) -> str:
        """Les classes de :class:`Flex`, plus la table ``paddings``.

        On étend plutôt qu'on ne réécrit : la composition d'un flex
        (direction, alignement, gap, responsive) est déjà résolue en
        amont, et la redupliquer ici la ferait diverger au premier
        changement.
        """
        base = super()._compose_classes()
        padding = self._reactive_values.get("padding") or "none"
        extra = self._resolved_theme().get("paddings", {}).get(padding, "")
        return f"{base} {extra}".strip() if extra else base
