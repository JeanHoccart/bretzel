"""Thème par défaut de :class:`Diagram`.

Un graphe orienté rendu en couches : les nœuds sont du HTML positionné,
les arêtes un calque ``<svg>`` derrière eux. C'est ce partage qui décide
du thème — les slots de nœud sont des classes Tailwind ordinaires
(donc un nœud a un anneau de focus, une troncature, une teinte de
survol comme n'importe quel contrôle), et les slots d'arête sont des
attributs de présentation SVG.

Slots :

- ``root``      : le conteneur qui défile, EN X seulement. C'est la
  VRAIE racine — ``id`` / ``classes=`` / ``attrs=`` / ``visible`` /
  ``tooltip`` y atterrissent. Un graphe plus large que la page se fait
  défiler, il ne rétrécit pas ; sa HAUTEUR, elle, est celle de son
  contenu, et c'est au parent de décider s'il la borne. Deux barres dans
  deux rectangles, c'est ce qu'on obtient autrement.
- ``canvas``    : la boîte positionnée à l'intérieur, aux dimensions que
  le moteur de placement a calculées. ``relative``, parce que chaque
  nœud est en ``absolute`` par rapport à elle.
- ``edges``     : le ``<svg>`` du calque d'arêtes — ``absolute inset-0``
  et surtout ``pointer-events-none``, sans quoi il avalerait les clics
  destinés aux nœuds qu'il recouvre.
- ``node``      : l'enveloppe positionnée d'un nœud — ``absolute``, le
  rayon (que l'anneau du nœud centré épouse) et l'affordance de clic.
  Aucune décoration : bordure et fond vivent sur ``node_body``, sinon un
  ``render=`` maison les recevrait EN PLUS des siennes. Sa position et sa
  taille arrivent en style inline (cf. l'avertissement plus bas).
- ``node_body`` : la carte par défaut d'un nœud, quand aucun ``render=``
  n'est fourni. Bordure, fond, coin arrondi, et l'anneau de focus.
- ``node_focus``: le nœud sur lequel la vue est centrée. UN seul repère,
  posé sur le corps — sur l'enveloppe il produisait un second trait à un
  pixel de celui du corps.
- ``node_dim``  : un nœud qu'aucune arête ne relie à celui qu'on vient de
  désigner. Une opacité seulement : il reste lisible et cliquable.
- ``label``     : le texte d'un nœud par défaut.
- ``empty``     : le mot affiché quand le graphe est vide.

``edge`` / ``edge_flipped`` / ``edge_dim`` sont des **classes portées par
le ``<path>``**. Elles utilisent les utilitaires ``stroke-*`` de
Tailwind, donc la couleur d'une arête suit le thème comme le reste et
non une valeur en dur.

``sizes`` porte la géométrie, en NOMBRES, parce que le placement en a
besoin avant de rendre quoi que ce soit — c'est la même convention que
les graphiques (``bar_chart`` y range ``h``, ``axis``, ``pad``).

Sizes :

- ``w`` / ``h``   : la taille d'un nœud. **Fixe par palier** : le serveur
  ne mesure pas le texte, donc la largeur se décide à l'avance ou il
  faudrait replacer côté client. Un nœud qui doit respirer passe par
  ``ui.node(width=…)``.
- ``layer``       : l'écart entre deux couches — c'est la longueur
  visible des arêtes.
- ``lane``        : l'écart entre deux nœuds d'une même couche.
- ``text``        : la classe typographique du label.
- ``icon`` / ``badge`` : les paliers que le rendu par défaut passe à
  ``ui.icon`` et ``ui.badge``. Ils vivent ici et pas en dur dans le
  rendu, sinon un ``ui.diagram(size="xl")`` garderait des icônes de la
  taille d'un ``sm`` — le défaut des pastilles figées dans un combobox.

⚠️ **La position et la taille d'un nœud ne passeront JAMAIS par une
classe.** ``left-[240px]`` est une classe ASSEMBLÉE : le compilateur
Tailwind de production ne balaie que des littéraux, donc elle n'existe
qu'en dev, l'HTML est identique des deux côtés et la page se disloque
uniquement en production. Les coordonnées vont en ``style=`` inline, et
c'est aussi ce qui garantit que la boîte dessinée est exactement celle
que le moteur a placée.
"""

from __future__ import annotations

from typing import Any

DIAGRAM_THEME: dict[str, Any] = {
    "slots": {
        # Il défile en X, et EN X SEULEMENT.
        #
        # `overflow-auto` (les deux axes) faisait de ce composant le
        # seul du catalogue à scroller verticalement — mesuré : tous les
        # autres conteneurs qui défilent (`table`, `carousel`,
        # `file_upload`) écrivent `overflow-x-auto`. Le prix se voyait
        # dès qu'on le posait dans une colonne bornée : la colonne
        # scrollait ET le diagramme scrollait, deux barres dans deux
        # rectangles différents, l'une dedans l'autre dehors.
        #
        # Un placement en couches grandit SUR LE CÔTÉ, pas vers le bas :
        # la hauteur est celle de la couche la plus fournie, et c'est au
        # parent — la page, ou un `ui.pane` — de décider si elle défile.
        "root": (
            # Pas de `bg-` : la racine hérite de la page, comme celle de
            # `ui.table`. Un fond posé ici est teinté par le pont de
            # couleur, donc TOUTE la surface prend la couleur — c'est
            # une nappe, pas un accent, et ça écrase le dessin.
            "bz-diagram "  # marqueur d'audit — cf. tests/audit/checklist.py
            "relative overflow-x-auto max-w-full rounded-box "
            "border-(length:--bz-stroke) border-text/10"
        ),
        # La boîte placée. Ses dimensions arrivent en style inline.
        "canvas": "relative",
        # Le calque d'arêtes. `pointer-events-none` est structurel : il
        # recouvre les nœuds, donc sans ça aucun clic n'atteindrait un
        # nœud — et ça se voit uniquement à l'essai, jamais en relecture.
        "edges": "absolute inset-0 pointer-events-none overflow-visible",
        # L'enveloppe d'un nœud : le positionnement, plus le RAYON.
        #
        # Le rayon n'est pas décoratif ici : c'est lui que suit l'anneau
        # du nœud centré. Sans lui l'anneau est un RECTANGLE posé autour
        # d'un nœud arrondi — deux formes concentriques qui ne coïncident
        # pas, ce qui se voit tout de suite et se corrige à cet endroit
        # seulement.
        # `cursor-pointer` INCONDITIONNEL, et ce n'est pas une
        # approximation : un nœud répond TOUJOURS au clic — il éclaire
        # ses voisins même sans `on_item_click=`. Le réserver aux nœuds
        # qui portent un handler serveur mentirait dans l'autre sens.
        # `select-none` avec lui : sans ça un clic un peu appuyé
        # surligne le label au lieu de désigner le nœud.
        "node": "absolute rounded-box cursor-pointer select-none",
        # La carte par défaut. `h-full w-full` pour qu'elle remplisse
        # exactement la boîte que le moteur a réservée — sinon le dessin
        # et le placement divergent d'un ou deux pixels par nœud.
        #
        # ⚠️ Où la couleur passe, et où elle ne passe PAS. Le FOND reste
        # neutre (`bg-surface`) : un palier coloré là teinte toute la
        # boîte, et vingt boîtes teintées font une nappe qui écrase le
        # dessin. La BORDURE, elle, lit le palier du pont
        # (`--bz-border`), donc `color=` se voit — un liseré, pas un
        # aplat. Sans ça `color=` ne fait plus RIEN, et un kwarg qui ne
        # fait rien est le mode d'échec dominant de ce dépôt.
        "node_body": (
            "h-full w-full flex items-center gap-2 px-3 rounded-box "
            "border-(length:--bz-stroke) border-(--bz-border) bg-surface "
            "transition-[opacity,background-color,border-color] "
            # Le survol : il avait DISPARU en neutralisant la palette.
            # Un nœud cliquable qui ne réagit pas au pointeur ne se
            # signale plus comme cliquable.
            "hover:bg-(--bz-bg) hover:border-(--bz-border-hover) "
            "focus-visible:outline-none focus-visible:ring-2 "
            "focus-visible:ring-(--bz-focus)"
        ),
        # Le nœud sur lequel la vue est centrée. Un anneau sur
        # l'enveloppe — qui porte maintenant le même rayon que le corps,
        # donc il l'épouse au lieu de l'encadrer.
        "node_focus": "ring-2 ring-(--bz-focus)",
        # L'estompage, quand un autre nœud est désigné. Une opacité et
        # rien d'autre : le nœud reste lisible et cliquable, il passe
        # juste en arrière-plan.
        "node_dim": "opacity-25",
        "label": "truncate",
        # L'enveloppe de l'état vide. Le CONTENU, lui, est un vrai
        # `ui.empty_state` — pas un texte gris posé au centre.
        "empty": "p-6",
    },
    # Les arêtes. `fill-none` est obligatoire : un `<path>` est rempli
    # par défaut, donc une courbe sans lui s'affiche en aplat noir.
    # Le palier de BORDURE du pont, pas un aplat : une arête suit la
    # couleur du composant sans capter l'œil. C'est l'autre endroit — avec
    # le liseré des nœuds — où `color=` reste visible.
    "edge": "fill-none stroke-(--bz-border) stroke-[1.5]",
    "edge_flipped": (
        "fill-none stroke-(--bz-border) stroke-[1.5] [stroke-dasharray:4_3]"
    ),
    "edge_dim": "fill-none stroke-(--bz-border) stroke-[1.5] opacity-15",
    # Les cinq paliers de l'enum standard. En manquer un ne lève pas :
    # le rendu retombe sur `md` en silence, donc un `size="xl"` serait
    # plus PETIT qu'un voisin au même palier.
    "sizes": {
        "xs": {"w": 100, "h": 30, "layer": 44, "lane": 10,
               "text": "text-xs", "icon": "xs", "badge": "xs"},
        "sm": {"w": 120, "h": 36, "layer": 56, "lane": 14,
               "text": "text-xs", "icon": "xs", "badge": "xs"},
        "md": {"w": 160, "h": 44, "layer": 72, "lane": 20,
               "text": "text-sm", "icon": "sm", "badge": "sm"},
        "lg": {"w": 200, "h": 52, "layer": 88, "lane": 26,
               "text": "text-base", "icon": "md", "badge": "md"},
        "xl": {"w": 240, "h": 60, "layer": 104, "lane": 32,
               "text": "text-lg", "icon": "lg", "badge": "md"},
    },
}
