"""Le seul global de l'app : son thème.

**L'échelle vient du framework**, et l'app n'a rien à demander : c'est
le DÉFAUT livré depuis le 2026-09-13. Elle vivait ici dans un
``core/preset.py`` de 351 lignes qui retaillait onze composants un par
un ; ``examples/ecole`` l'a recopié, s'est retrouvé avec quatre hauteurs
de champ sur un écran (les onze composants NON cités restaient au
défaut), et les deux apps ont fini par prouver la même chose : la densité
se déplace par la BASE de l'échelle, pas composant par composant.

Ce qui reste ici est ce que le framework ne décide pas, parce qu'une
échelle livrée ne porte jamais une marque :

- **les neutres**, gris-mauve très légèrement désaturés plutôt que le
  slate bleuté de Tailwind, et un quasi-noir en sombre — c'est le fond
  d'un tableau de cartes, qui doit s'effacer ;
- **la teinte**, un teal ;
✅ **Les deux raffinements de composant sont partis dans le framework**
le 2026-09-13 — les chiffres tabulaires du badge et la carte au filet
plutôt qu'à l'ombre au repos. Ils vivaient ici en recopiant la chaîne de
slot livrée pour n'y changer qu'un mot, donc ils gelaient la version du
jour : le besoin n'avait rien de propre à un tableau de cartes, et c'est
ce qui en faisait des défauts, pas des surcharges.
"""

from bretzel.theme import Theme

THEME = Theme(
    semantic={
        "primary": "#0d9488",  # teal
        "background": "#fbfbfc",
        "surface": "#ffffff",
        "interface": "#f6f6f8",
        "text": "#17171a",
        "muted": "#6e6e78",
    },
    semantic_dark={
        "background": "#0a0a0c",
        "surface": "#111114",
        "interface": "#191920",
        "text": "#f2f2f4",
        "muted": "#8a8a95",
    },
    components={
        "badge": {
            "slots": {
                "root": (
                    "inline-flex w-fit items-center gap-1 "
                    "max-w-[min(16rem,100%)] rounded-selector font-medium "
                    "leading-normal tabular-nums whitespace-nowrap "
                    "transition-colors duration-150"
                ),
            },
        },
        "card": {
            "slots": {
                "root": (
                    "block w-full rounded-box overflow-hidden "
                    "bg-(--bz-solid) text-(--bz-on-solid) "
                    "border-(length:--bz-stroke) border-text/8"
                ),
            },
            # ⚠️ Les sélecteurs ``aria-disabled:`` sont recopiés tels
            # quels : ils neutralisent le relief par spécificité (0,3,0
            # bat 0,2,0), et les omettre ferait relever une surface
            # verrouillée au survol.
            "hoverable": (
                "transition-all duration-150 ease-out cursor-pointer "
                "relative top-0 "
                "hover:border-text/20 "
                "hover:shadow-sm "
                "hover:-top-px "
                "aria-disabled:cursor-default "
                "aria-disabled:hover:top-0 "
                "aria-disabled:hover:shadow-none "
                "aria-disabled:hover:border-text/8"
            ),
        },
    },
)
