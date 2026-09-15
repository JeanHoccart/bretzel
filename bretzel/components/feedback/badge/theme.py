"""Default :class:`Badge` theme.

Small inline label : softly-rounded background or solid fill,
sometimes carrying an inline icon, optionally dismissible via a
trailing ``×`` button (``dismissible=True`` or ``on_close``).

Slots :
- ``root``        : the pill itself
- ``label``       : the inline text (truncates on long labels)
- ``close``       : the ``×`` button (rendu dès que ``dismissible=True``
                    OU ``on_close`` est passé — pas seulement ``on_close``)

Le dimensionnement de l'icône du bouton close n'est PAS un slot : il vit
dans ``sizes[size]["close_icon_size"]``.

Note : no ``icon`` slot — Badge's leading/trailing icons are pre-built
:class:`Icon` instances sized via the theme's ``sizes[size].icon_size``
(see ``_adopt_icon`` in ``badge.py``). Their own class handles styling.

Variants :
- ``soft``    : tinted bg + coloured text (default — subtle)
- ``solid``   : full bg + foreground text (stronger emphasis)
- ``outline`` : coloured border + text, transparent fill

Radius — ``rounded-selector`` (not a pill) so it reads as "label / chip"
and pairs with the form components, not as a "tracker / counter".
"""

from __future__ import annotations

from typing import Any

BADGE_THEME: dict[str, Any] = {
    "slots": {
        # ``max-w`` is what makes the label's ``truncate`` fire — a pill
        # with no width bound just grows to fit and the ellipsis never
        # triggers. Cf. the ``truncate ⇒ width-bound`` drift gate.
        # ``leading-normal`` (NOT ``leading-none``) : with ``line-height:1``
        # the ``truncate`` overflow:hidden clips descenders (y/g/p) ~2px ;
        # the fixed ``h-*`` + ``items-center`` make the roomier line-height
        # visually free.
        # ``w-fit`` : as a direct child of a flex parent (``ui.vstack`` /
        # ``ui.hstack``) the CSS spec blockifies ``inline-flex`` → ``flex``,
        # and the stack's default ``align-items: stretch`` then balloons the
        # pill to the full cross-axis width. ``width: fit-content`` pins it
        # back to its content regardless of container. Same class of bug —
        # and same fix — as the date_picker ``w-fit`` overflow.
        "root": (
            # ``min(16rem,100%)`` et non ``max-w-[16rem]`` seul : un
            # plafond FIXE ne connaît pas son conteneur, donc il laisse
            # la pastille en sortir dès que la colonne est plus étroite
            # que lui. Mesuré le 2026-08-25 dans une cellule de 240 px :
            # 256 px rendus, **17 px dehors**, par-dessus le voisin. Les
            # six autres racines à plafond du catalogue écrivent
            # ``max-w-full`` ; celle-ci était la seule à ne pas le faire.
            #
            # Une CLASSE, pas deux : ``max-w-full max-w-[16rem]`` posent
            # toutes deux ``max-width`` et le vainqueur dépend de l'ordre
            # de la FEUILLE, pas de celui des classes.
            # ``tabular-nums`` : un badge porte presque toujours un
            # COMPTEUR, et des chiffres proportionnels n'ont pas la même
            # largeur — le « 1 » est plus étroit que le « 8 ». La pastille
            # change donc de largeur à chaque incrément, et la ligne qui
            # la contient sautille. Adopté du thème d'``examples/kanban``
            # le 2026-09-13, où il vivait en surcharge d'app : le besoin
            # n'a rien de propre à un tableau de cartes.
            "inline-flex w-fit items-center gap-1 max-w-[min(16rem,100%)] "
            "rounded-selector font-medium leading-normal tabular-nums "
            "whitespace-nowrap "
            "transition-colors duration-150"
        ),
        "label": "truncate",
        "close": (
            "shrink-0 inline-flex items-center justify-center "
            "rounded-selector cursor-pointer "
            "outline-none "
            "focus-visible:ring-2 focus-visible:ring-(--bz-focus) "
            "transition-colors duration-100"
        ),
    },
    # Multi-slot variants — each variant tweaks both the root AND
    # the close button so the × stays legible against its bg.
    "variants": {
        "soft": {
            "root": "bg-(--bz-bg) text-(--bz-text)",
            "close": (
                "text-(--bz-text-muted) hover:text-(--bz-text) "
                "hover:bg-(--bz-bg-hover)"
            ),
        },
        "solid": {
            "root": "bg-(--bz-solid) text-(--bz-on-solid)",
            "close": (
                "text-(--bz-on-solid)/80 hover:text-(--bz-on-solid) "
                "hover:bg-black/10"
            ),
        },
        "outline": {
            # ``/50`` : in an outline badge the border IS the
            # container, so it has to read at the same weight as
            # the label. Measured on the 6-alpha bench, ``/40``
            # reads visibly paler than the text and the box looks
            # unfinished ; past ``/60`` the 2 px stroke drowns it.
            # ``/50`` is also the repo's dominant border strength.
            "root": "border-(length:--bz-stroke-strong) border-(--bz-border-hover) text-(--bz-text)",
            "close": (
                "text-(--bz-text-muted) hover:text-(--bz-text) "
                "hover:bg-(--bz-bg)"
            ),
        },
    },
    "sizes": {
        "xs": {
            "root": "px-1.5 py-0 text-[10px] h-4",
            "close": "h-3 w-3",
            "icon_size": "xs",
            "close_icon_size": "xs",
        },
        "sm": {
            "root": "px-2 py-0.5 text-xs h-5",
            "close": "h-3.5 w-3.5",
            "icon_size": "xs",
            "close_icon_size": "xs",
        },
        "md": {
            "root": "px-2 py-0.5 text-sm h-6",
            "close": "h-4 w-4",
            "icon_size": "sm",
            "close_icon_size": "xs",
        },
        "lg": {
            "root": "px-2.5 py-1 text-sm h-7",
            "close": "h-5 w-5",
            "icon_size": "sm",
            "close_icon_size": "sm",
        },
        "xl": {
            "root": "px-3 py-1 text-base h-8",
            "close": "h-5 w-5",
            "icon_size": "md",
            "close_icon_size": "sm",
        },
    },
}
