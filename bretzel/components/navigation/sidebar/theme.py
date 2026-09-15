"""Default theme for the Sidebar family (Sidebar / SidebarSection / SidebarItem).

Three components : :class:`SidebarItem` takes ``icon`` / ``label`` /
``badge`` props. Au repli bureau, l'icône reste en place ; le
``label`` FOND (``opacity-0`` + ``w-0`` + ``flex-none``, comme
``title_brand``) et le ``badge`` disparaît d'un coup — son ``ml-auto``
mangerait sinon l'espace libre du carré et décentrerait l'icône.

Responsive model :

- The sidebar is DESKTOP navigation chrome only. ``open`` drives
  ``data-open`` which the ``variants`` map reads : ``"rail"`` collapses
  to a 64px icon strip, ``"drawer"`` collapses to width 0.
- Responsive mobile navigation is the app layout's responsibility
  (``if Screen().is_mobile:``), NOT built into this component — the
  sidebar no longer ships a mobile drawer / topbar / hamburger.

Slots :
- ``sidebar.root``        : the ``<aside>`` flex column
- ``sidebar.section``     : grouping div for a single ``SidebarSection``
- ``sidebar.section_label`` : the small uppercase label above a section
- ``sidebar.section_divider`` : rail-only visibility gate wrapping a
  ``ui.divider`` (the collapsed-rail form of a labelled section caption)
- ``item.root``           : every item / nav row's outer ``<a>`` / ``<div>``
- ``item.active``         : extra classes layered when the row is active
- ``item.icon``           : icon slot wrapper (always visible)
- ``item.label``          : label text (fades out on desktop collapse)
- ``item.badge``          : right-aligned trailing badge (``hidden`` au repli bureau, pas un fondu)
"""

from __future__ import annotations

from typing import Any

SIDEBAR_THEME: dict[str, Any] = {
    "slots": {
        # Le cadre. Les règles ``data-[open=false]`` des tables
        # ``widths`` + ``collapse`` basculent la largeur au repli.
        "root": (
            # ⚠️ AUCUN utilitaire de ``position`` ici — il vit dans la
            # table ``collapse``, une entrée par mode. Ce n'est pas du
            # rangement : ``relative`` et ``fixed`` sont deux utilitaires
            # de MÊME spécificité, donc le vainqueur est le dernier de la
            # feuille Tailwind, pas le dernier de l'attribut ``class``.
            # Mesuré le 2026-08-15 : avec ``relative`` sur le root, le
            # mode ``overlay`` rendait ``position: relative`` et
            # ``transform: none`` — la sidebar restait dans le flux et ne
            # se fermait pas. Exactement le même piège que ``h-screen``
            # contre ``h-full``, rencontré le même jour.
            "group/sidebar shrink-0 flex flex-col h-screen "
            # ⚠️ NI ``position`` NI ``z-index`` ici — les deux vivent dans la
            # table ``collapse``, une entrée par mode. Même raison, et le
            # ``z-40`` qui traînait ici a coûté un bug visible : il
            # disputait le ``z-50`` du mode ``overlay`` (deux utilitaires
            # ``z-index`` de MÊME spécificité → l'ordre de la feuille
            # tranche), la sidebar retombait au niveau du fond assombri et
            # se retrouvait FLOUTÉE sous son propre backdrop.
            "p-2 gap-1 bg-surface "
            # La bordure vivait dans une table ``sides`` a deux entrees,
            # supprimee avec la prop ``side=`` le 2026-08-15 : une nav
            # laterale est a gauche, donc la bordure est a droite.
            "border-r-(length:--bz-stroke) border-text/10 "
            # NO ``overflow-y-auto`` here — the scroll lives on the
            # ``scroll`` slot (the middle region) so an overflowing nav
            # list scrolls WITHOUT dragging the footer down with it. The
            # aside stays a rigid ``flex-col h-screen`` frame : title +
            # footer are ``shrink-0`` siblings, the scroll box is
            # ``flex-1``. ``overflow-x-hidden`` stays : it clips the
            # horizontal jitter during the rail width-collapse animation.
            "overflow-x-hidden "
            # ``width`` covers the desktop rail collapse animation.
            "transition-[width] duration-300 ease-in-out "
            # (La position est dans ``collapse``, cf. plus haut.)
            ""
        ),
        # ── Scroll region (auto-wraps the middle children) ───────────
        # Everything that is NOT a SidebarTitle / SidebarFooter lands in
        # this box (see ``Sidebar.render``). ``flex-1`` makes it eat the
        # space the pinned header + footer leave ; ``min-h-0`` is
        # load-bearing — a flex child defaults to ``min-height:auto`` and
        # would refuse to shrink below its content, so the ``overflow``
        # never triggers and the footer gets pushed off-screen (the exact
        # bug this fixes ; cf. traps.md). ``flex flex-col gap-1`` keeps the
        # same inter-section rhythm the aside used to give as the direct
        # parent. ``overflow-x-hidden`` mirrors the aside so the rail
        # collapse doesn't show a horizontal bar.
        # ``bz-rail-scroll`` is a CSS hook (not a Tailwind utility) : the
        # global theme CSS (css.py ``_RAIL_SCROLL``) targets it to HIDE the
        # scrollbar in the collapsed desktop rail so the icon column stays
        # perfectly centred (no reserved gutter) ; scroll still works via
        # wheel. The expanded sidebar keeps the normal thin scrollbar
        # (la règle est gatée sur ``[data-open=false]`` seul).
        # ⚠️ ``-mx-1.5 px-1.5`` : de la PLACE POUR L'ANNEAU DE FOCUS, pas une
        # marge décorative. L'anneau est un ``box-shadow`` qui déborde de 4px
        # (offset 2 + ring 2) et un ancêtre en ``overflow`` non-visible rogne
        # les ombres de ses descendants. Mesuré le 2026-08-15 : la ligne était
        # à 0px des deux bords de cette boîte, donc l'anneau était rasé à
        # gauche ET à droite, dans TOUS les états (pas seulement dans le rail).
        # La marge négative reprend les 6px que le padding ajoute : la ligne
        # garde exactement sa position et sa largeur, seule la boîte de
        # rognage s'élargit. 6px pour 4px d'anneau = 2px de marge.
        #
        # ``overflow-x-hidden`` ne peut PAS simplement sauter : ``overflow-y:
        # auto`` force l'axe X à une valeur de défilement (``visible`` calcule
        # en ``auto``), donc le retirer rendrait une barre horizontale
        # possible au lieu de rien.
        "scroll": (
            "bz-rail-scroll flex-1 min-h-0 flex flex-col gap-1 "
            "-mx-1.5 px-1.5 "
            "overflow-y-auto overflow-x-hidden"
        ),
        "section": "flex flex-col gap-0.5",
        # ``font-semibold``, pas ``font-bold`` : recensé le 2026-08-15, les
        # quatre micro-capitales du catalogue sont ``divider.label``
        # (semibold), l'``avatar`` de cette sidebar (semibold) et
        # ``calendar.weekday`` (medium). Le ``bold`` d'ici était le seul, et
        # dans un fichier qui utilise déjà semibold pour son autre capitale.
        "section_label": (
            "text-xs font-semibold text-muted uppercase tracking-wide "
            "px-2 py-1 mt-2 "
            # Fond au repli (le rail montre son séparateur à la place).
            # Pas ``hidden`` : ``display:none`` tuerait le fondu, cf.
            # ``title_text``.
            "overflow-hidden "
            "transition-[opacity,visibility,height,padding,margin] "
            "duration-200 "
            "group-data-[open=false]/sidebar:opacity-0 "
            "group-data-[open=false]/sidebar:invisible "
            "group-data-[open=false]/sidebar:h-0 "
            "group-data-[open=false]/sidebar:py-0 "
            "group-data-[open=false]/sidebar:mt-0"
        ),
        # Rail divider — the collapsed form of a section LABEL. The
        # uppercase ``section_label`` hides at md+ when ``data-open=false``
        # ; this is its exact mirror : ``hidden`` by default + in the
        # expanded sidebar, shown ONLY at md+ collapse. So in the rail the
        # "MAIN" / "ACCOUNT" caption visually turns into a separator line.
        # This is just the visibility GATE — a plain wrapper with no base
        # ``display`` (so ``hidden``/``:block`` toggle cleanly) ; the line
        # itself is a real ``ui.divider`` rendered inside. ``px-2`` insets
        # it slightly from the 64px rail edges. Rendered ONLY for labelled
        # sections — an unlabelled group has no caption to collapse.
        "section_divider": (
            "hidden px-2 group-data-[open=false]/sidebar:block"
        ),
        # ── Rail tooltip : UN panneau partagé pour toute la sidebar ──
        # Dans le rail replié le label de chaque entrée est ``hidden``, donc
        # on le ramène au survol. Un panneau UNIQUE, déplacé sur l'entrée
        # survolée, au lieu d'un ``ui.tooltip`` par entrée : 62 panneaux
        # pré-rendus pesaient 94 ko, soit un tiers de la sidebar, pour une
        # affordance qui n'en montre jamais qu'un (mesuré 2026-07-27).
        #
        # La visibilité est ENTIÈREMENT en CSS — pas de ``bz-show``, qui
        # poserait un ``display`` inline et écraserait le gate du rail. Deux
        # conditions composées en variantes, comme les entrées elles-mêmes :
        # ``group-data-[open=false]/sidebar:`` = rail replié, et
        # ``data-[tip=on]`` = quelque chose est survolé.
        # ``position: fixed`` + ``top``/``left`` posés depuis le rect de
        # l'entrée : aucune hypothèse sur la largeur du rail ni sur le côté.
        # ⚠️ Les tokens de surface sont ceux de ``TOOLTIP_THEME["panel"]``,
        # littéralement — ``bg-text text-text-foreground``, ``px-2.5
        # py-1.5``, ``rounded-selector``, ``text-xs font-medium leading-tight``,
        # ``shadow-md``, ``max-w-xs``. Ce panneau n'EST pas un
        # ``ui.tooltip`` (un seul panneau partagé au lieu de 62, cf.
        # ci-dessus), mais il doit s'en distinguer par rien de visible.
        # Mesuré le 2026-08-25, avant alignement : le texte tirait sur
        # ``text-background`` (248,250,252) contre (244,245,245) pour le
        # vrai tooltip, et le panneau n'avait AUCUNE flèche.
        #
        # ``whitespace-nowrap`` est la SEULE divergence assumée : une
        # entrée de rail porte un libellé court, et le replier sur deux
        # lignes à côté d'une icône de 40 px se lit mal.
        "rail_tip": (
            "fixed z-50 px-2.5 py-1.5 rounded-box "
            "text-xs font-medium leading-tight whitespace-nowrap "
            # Les PALIERS, et le pont ``bz-c-text`` posé sur le nœud au
            # rendu : c'est exactement ce qu'écrit le panneau d'un
            # ``ui.tooltip``, et les deux se lisent côte à côte dans la
            # même app (``test_rail_tip_looks_like_a_tooltip``).
            "bg-(--bz-solid) text-(--bz-on-solid) shadow-md "
            "max-w-xs break-words pointer-events-none "
            # ``top`` reçoit le CENTRE vertical de l'entrée survolée ; le
            # décalage de moitié se fait ici, pas en JS avec une hauteur
            # de panneau devinée.
            "-translate-y-1/2 "
            "opacity-0 invisible transition-opacity duration-150 "
            "group-data-[open=false]/sidebar:data-[tip=on]:opacity-100 "
            "group-data-[open=false]/sidebar:data-[tip=on]:visible"
        ),
        # La flèche du panneau de rail. UN seul jeu de classes, pas les
        # quatre côtés de ``TOOLTIP_THEME["arrow"]`` : une nav latérale
        # vit à gauche (``Sidebar._CUT["side"]``) et le panneau s'ancre
        # sur ``aside.right + 8``, donc il est TOUJOURS à droite de
        # l'entrée. La flèche est donc toujours sur son bord gauche.
        # ``right-full`` = ``right: 100%``, ce qui pousse le carré
        # entièrement hors du panneau par la gauche ; ``-mr-1`` le
        # ramène de 4 px pour qu'il se fonde dans l'angle.
        #
        # Le parent est ``fixed``, donc il est déjà un bloc conteneur
        # pour un enfant ``absolute`` — pas de ``relative`` à ajouter.
        "rail_tip_arrow": (
            "absolute h-2 w-2 rotate-45 bg-(--bz-solid) "
            "right-full top-1/2 -translate-y-1/2 -mr-1"
        ),
        # ── L'ARÊTE cliquable ────────────────────────────────────────
        # La bordure droite de l'aside (``border-r border-text/10``) est
        # déjà peinte en permanence : on ne fait que la rendre
        # ATTEIGNABLE. C'est ce qui distingue cette affordance du rail de
        # shadcn, invisible au repos et révélée au survol — que
        # ``test_hover_only_controls_reachable`` interdit ici, et qui
        # n'existerait de toute façon pas sur une machine tactile.
        #
        # 24 px de large pour le plancher de cible WCAG 2.2 § 2.5.8 (le
        # même que cite le thème de ``ui.draggable``), posés à cheval sur
        # la bordure : ``-right-3`` sort la moitié au-dessus du contenu,
        # ce qui évite de manger la zone de clic des icônes du rail — à
        # 64 px de large, une bande INTÉRIEURE de 24 px en recouvrirait
        # 12 sur 40.
        #
        # ⚠️ ``cursor-pointer`` et surtout PAS ``cursor-w-resize`` :
        # shadcn met le second, qui promet un glissement qui n'existe
        # pas. Bretzel a un vrai geste de redimensionnement
        # (``ui.resizable``), et lui voler son signal rendrait les deux
        # illisibles.
        #
        # Le survol n'ENRICHIT que : le trait s'épaissit et se teinte. La
        # règle du dépôt l'autorise explicitement — « ``hover:`` reste
        # bienvenu pour ENRICHIR, jamais pour révéler ».
        "rail_edge": (
            # ⚠️ ``right-0``, JAMAIS un débordement négatif. L'aside porte
            # ``overflow-x-hidden`` (il retient le contenu déplié pendant
            # l'animation de largeur), donc un ``-right-3`` fait COUPER la
            # moitié extérieure : la bande se retrouve à ~12 px utiles,
            # décentrée, et on ne peut la viser que par la gauche.
            # Rapporté ainsi — « je dois cliquer au millimètre », « je
            # peux déborder à gauche mais pas à droite ».
            # ⚠️ ``w-4`` = 16 px, et c'est un ARBITRAGE, pas un réglage.
            # 24 px (le plancher de cible WCAG 2.2 § 2.5.8) recouvraient
            # les 13 px de droite des icônes de nav du rail — mesuré :
            # il ne leur restait que 28 px cliquables sur 40, et ça se
            # sentait. 16 px n'en prennent plus que 4 (les icônes gardent
            # 36 px) tout en restant bien plus visables que les ~12 px
            # utiles de la version coupée.
            #
            # Ce qu'on perd : la bande seule n'atteint plus le plancher
            # tactile. Elle reste haute de toute la barre — donc une
            # cible de 16 × 600 px, confortable à la souris — et sur une
            # barre AVEC titre le bouton de 40 px de l'en-tête reste la
            # commande de plein droit. C'est écrit dans la gate, qui
            # distingue les deux formes.
            "group/railedge absolute top-0 right-0 z-50 h-full w-4 "
            "hidden md:block bg-transparent border-0 p-0 "
            # Le curseur EST l'annonce. ``pointer`` ne distingue pas cette
            # bande du reste de la page ; un curseur de redimensionnement
            # DIRECTIONNEL dit à la fois « cette arête bouge » et dans
            # quel sens — ``e-resize`` quand la barre est repliée (elle
            # va s'ouvrir vers la droite), ``w-resize`` quand elle est
            # dépliée. C'est le choix de shadcn, et je m'y range : je
            # l'avais écarté par crainte de promettre un glissement, mais
            # sans lui la bande n'existe pas pour la souris.
            "cursor-w-resize group-data-[open=false]/sidebar:cursor-e-resize "
            "focus-visible:outline-none"
        ),
        # Le trait DANS l'arête : 2 px centrés, transparent au repos (la
        # bordure de l'aside est déjà là, sous lui), teinté au survol et
        # au focus clavier.
        # Le trait DANS l'arête. Il est collé au bord DROIT (``right-0``)
        # et pas centré : c'est là qu'est la bordure de l'aside, donc
        # c'est elle qu'il épaissit — un trait centré dans la bande
        # peindrait une seconde ligne à 12 px de la première.
        #
        # 4 px et non 2 : à 2 px, « la ligne reste encore très fine » et
        # ne se voit pas venir. Elle reste transparente au repos — la
        # bordure de l'aside est déjà là, sous elle.
        "rail_edge_line": (
            "absolute inset-y-0 right-0 w-1 "
            "bg-transparent transition-colors duration-150 "
            "group-hover/railedge:bg-primary/60 "
            "group-focus-visible/railedge:bg-primary"
        ),
        # ── SidebarTitle (header : logo + title + collapse toggle) ───
        # Row when expanded ; stacks + centers on desktop collapse so
        # the logo sits centered in the 64px rail with the chevron under.
        "title_root": (
            "relative flex flex-row items-center gap-2 px-2 py-3 shrink-0 "
            "group-data-[open=false]/sidebar:flex-col "
            "group-data-[open=false]/sidebar:items-center "
            "group-data-[open=false]/sidebar:justify-center "
            "group-data-[open=false]/sidebar:gap-1 "
            "group-data-[open=false]/sidebar:px-0"
        ),
        # The logo + title, a clickable home link. ``min-w-0`` lets the
        # title truncate ; ``flex-1`` pushes the toggle to the far edge.
        # Hidden entirely on desktop collapse — in the rail we show ONLY
        # the chevron (centered), not the logo.
        "title_brand": (
            "flex flex-row items-center gap-2 min-w-0 flex-1 "
            "text-text font-bold no-underline "
            # ⚠️ Fondu ET libération de la largeur, les deux. Ce bloc
            # portait ``hidden`` : ``display:none`` retire bien la place
            # mais tue toute transition, donc le titre SAUTAIT (mesuré :
            # ``display:none`` à 60 ms, opacité encore à 1.00). Un simple
            # ``opacity-0`` fait l'inverse — il fond, mais garde sa place
            # dans la ligne, et le logo déborde alors de 8 px de la bande
            # de 64 px (mesuré aussi, par le probe, en écrivant ce fix).
            #
            # Il faut donc les deux : l'opacité anime, ``w-0`` +
            # ``flex-none`` rendent la place au chevron centré du rail, et
            # ``visibility`` bascule à la fin pour sortir du parcours de
            # tabulation. ``flex-none`` est indispensable — ``flex-1``
            # regonflerait la boîte malgré ``w-0``.
            "overflow-hidden "
            "transition-[opacity,visibility,width,height] duration-200 "
            "group-data-[open=false]/sidebar:opacity-0 "
            "group-data-[open=false]/sidebar:invisible "
            "group-data-[open=false]/sidebar:flex-none "
            "group-data-[open=false]/sidebar:w-0 "
            "group-data-[open=false]/sidebar:h-0"
        ),
        # Header lockup is sized UNIFORMLY at ``text-2xl`` (24px) : the logo
        # glyph, the title text, and the collapse chevron all share the SAME
        # scale as the collapsed-rail logo (``title_rail_brand``, lui aussi en
        # ``text-2xl``). C'est ce qui rend le repli propre : le logo ne
        # change jamais de taille, seuls le libellé et le chevron fondent.
        # 24 px est le cran ``lg`` de l'échelle Icon, donc le chevron
        # (``Icon(size="lg")`` dans un IconButton ``size="md"``, boîte
        # ``h-10 w-10``) fait bien 40 px comme le logo du rail.
        #
        # ⚠️ Le commentaire d'origine disait « matches the rail toggle's
        # 40px box » et nommait un slot ``title_rail_toggle``. Il n'existe
        # pas, et le bouton auquel il renvoyait non plus : le chevron
        # flottant auto a été retiré le 2026-08-21. Corrigé le 2026-08-29.
        #
        # Logo glyph — sized by FONT-SIZE (iconify-icon renders at 1em ;
        # w-7/h-7 would only grow the box and leave a small glyph top-left),
        # the same convention as the Icon primitive.
        # Colour (``text-primary`` for a string icon, or the passed
        # ``ui.icon(...)``'s own colour) is injected by ``render()``.
        "title_logo": (
            "shrink-0 inline-flex items-center justify-center text-2xl"
        ),
        # Title text — ``text-2xl`` (matches the logo + rail glyph) ; bold
        # comes from ``title_brand``. Hides on desktop collapse.
        # ⚠️ Le fondu, et pourquoi ce n'est PAS ``hidden``. Ce slot
        # portait ``transition-opacity duration-200`` ET
        # ``group-data-[open=false]:hidden`` : ``display:none`` n'est pas
        # animable, donc la transition était DÉCLARÉE ET MORTE. Mesuré
        # image par image le 2026-08-18 — le texte sautait à
        # ``display:none`` en 60 ms, opacité encore à 1.00, puis la bande
        # rétrécissait pendant 300 ms sur une boîte déjà vide.
        #
        # ``visibility`` accompagne l'opacité (le motif du thème de
        # ``ui.drawer``) : elle bascule à la FIN de la durée, donc le
        # texte fond pendant le repli puis sort du parcours de
        # tabulation. Un simple ``opacity-0`` le laisserait focalisable.
        "title_text": (
            "text-2xl truncate "
            "transition-[opacity,visibility] duration-200 "
            "group-data-[open=false]/sidebar:opacity-0 "
            "group-data-[open=false]/sidebar:invisible"
        ),
        # Expanded-state collapse chevron (right of the title). Its glyph is
        # sized to 24px by the explicit ``Icon(size="lg")`` passed to the
        # IconButton (see sidebar.py) — matches the logo + title + rail glyph.
        # Masqué dans le rail, où c'est le logo (``title_rail_brand``) qui
        # rouvre — il n'y a pas de second bouton.
        "title_toggle": (
            "shrink-0 "
            "group-data-[open=false]/sidebar:hidden"
        ),
        # Le LOGO du rail replié — visible uniquement dans le rail bureau.
        #
        # ⚠️ Ce commentaire décrivait, jusqu'au 2026-08-26, le mécanisme
        # que le bloc ci-dessous explique avoir SUPPRIMÉ : « a single
        # button : logo by default, swapped to a chevron on hover ;
        # ``group/railtoggle`` drives the icon swap ». Deux paragraphes
        # voisins racontaient donc deux designs opposés — et c'est le
        # périmé qu'on lisait en premier. ``probe_sidebar`` a cherché
        # ``button[class*="railtoggle"]`` pendant cinq jours, n'a rien
        # trouvé, et a conclu que Tailwind ne compilait pas.
        #
        # ``grid place-items-center`` (et pas flex) centre le glyphe dans
        # la cellule unique, quelle que soit sa taille.
        # Le logo, dans le rail replié. C'était un BOUTON de repli qui
        # portait le logo et se changeait en chevron AU SURVOL — donc,
        # sur une machine sans survol, un logo qui n'annonçait jamais
        # qu'il repliait quoi que ce soit. Le geste existait et personne
        # ne pouvait le découvrir (finding [29], 2026-08-21).
        #
        # C'est maintenant un LIEN, qui mène là où mène le logo déplié
        # (``href=``, ``/`` par défaut) : le logo arrête de changer de
        # métier selon l'état de la barre. Le repli, lui, a son arête
        # (``rail_edge``) — visible dans les deux états.
        "title_rail_brand": (
            "hidden place-items-center no-underline "
            "rounded-selector text-text hover:bg-text/10 transition-colors "
            "group-data-[open=false]/sidebar:grid "
            "group-data-[open=false]/sidebar:w-10 "
            "group-data-[open=false]/sidebar:h-10 "
            "group-data-[open=false]/sidebar:mx-auto "
            "group-data-[open=false]/sidebar:p-0"
        ),
    },
    # Desktop EXPANDED width preset.
    "widths": {
        "sm": "w-48",
        "md": "w-64",
        "lg": "w-80",
    },
    # ── Un SEUL axe : ce que « replié » veut dire ────────────────────
    # Remplace le couple ``variant=`` (rail/drawer) + ``collapsible=``
    # (True/False) du 2026-08-15. Deux props, quatre combinaisons, dont
    # une absurde (``collapsible=False`` + drawer = une sidebar qu'on ne
    # peut ni replier ni atteindre). Un axe, quatre valeurs, zéro
    # combinaison illégale — le découpage de shadcn, plus ``overlay``.
    #
    # ⚠️ AUCUN gate ``md:`` sur aucun des quatre modes, et c'est une
    # décision. Ils l'étaient tous jusqu'au 2026-08-15 — héritage de
    # l'époque où la sidebar était « du chrome desktop » et devait
    # refuser de se replier sur un petit écran.
    #
    # Ce n'est plus vrai : c'est le DEV qui choisit le mode, dans son
    # ``if Screen().is_mobile``. Le CSS n'a pas à le contredire. Tant
    # qu'il le faisait, deux bugs vivaient ensemble — replier sous
    # 768px ne faisait RIEN (mesuré : 256px → 256px), et il suffisait
    # que le cookie ``bz_screen`` soit en retard d'un rendu (un
    # redimensionnement, un premier chargement) pour qu'on se retrouve
    # avec une sidebar ouverte impossible à fermer.
    #
    # Chaque mode porte aussi sa ``position`` ET son ``z-index`` : ce
    # sont des utilitaires dont deux valeurs se disputent à
    # spécificité égale, donc les laisser sur ``root`` faisait dépendre
    # le vainqueur de l'ordre de la feuille Tailwind. Les deux s'en
    # sont fait prendre le même jour.
    "collapse": {
        # Les trois modes DE FLUX portent ``relative`` (une colonne
        # ordinaire du layout) ; ``overlay`` porte ``fixed``. Un seul
        # utilitaire de position par mode, donc aucun conflit d'ordre.
        "rail": "relative z-40 data-[open=false]:w-16",
        "offcanvas": (
            "relative z-40 "
            "data-[open=false]:w-0 data-[open=false]:p-0 "
            "data-[open=false]:border-0 "
            "data-[open=false]:overflow-hidden"
        ),
        # Hors du flux, ancré au bord gauche, glissé hors écran quand il
        # est fermé. ``z-50`` passe devant le fond assombri (``z-40``).
        # La translation plutôt qu'un ``display:none`` : elle s'anime, et
        # elle garde le nœud monté donc le scope client survit.
        "overlay": (
            "fixed inset-y-0 left-0 z-50 shadow-2xl "
            "transition-transform duration-300 ease-in-out "
            "data-[open=false]:-translate-x-full"
        ),
        "none": "relative z-40",
    },
    # Le fond assombri du mode ``overlay``, téléporté sous ``<body>`` par
    # ``Sidebar.render`` — sinon il vivrait DANS l'aside, donc au-dessus
    # de lui-même et sous rien du tout.
    "backdrop": (
        "fixed inset-0 z-40 bg-black/50 backdrop-blur-sm "
        "transition-opacity duration-300 "
        "data-[open=false]:opacity-0 data-[open=false]:invisible "
        "data-[open=false]:pointer-events-none"
    ),
}


SIDEBAR_ITEM_THEME: dict[str, Any] = {
    "slots": {
        "root": (
            # ⚠️ ``text-sm`` DÉCLARÉ. Il manquait, et une ligne de nav sans
            # taille hérite du ``text-base`` du navigateur : mesuré le
            # 2026-08-15 au banc, ``fontSize: 16`` sur la ligne, contre 14
            # pour ``navbar_item`` ET pour ``sidebar_footer_item`` — l'autre
            # type de rangée du MÊME fichier. Ce n'était donc pas un choix,
            # c'était l'omission qui fait dépasser cette rangée-là de toute
            # l'échelle typographique du dépôt. Effet de bord voulu : la
            # hauteur de ligne passe de 40 à 36px (l'interligne suit la
            # taille), ce qui resserre le rythme sans toucher au padding et
            # garde une cible tactile correcte.
            "group/row relative flex flex-row items-center gap-2 w-full "
            "shrink-0 px-2 py-2 rounded-box cursor-pointer text-sm "
            # Desktop collapse : turn the row into a FIXED ``w-10 h-10``
            # square, centered in the 64px rail via ``mx-auto`` (the rail
            # inner box is 48px, so 4px gutters), with ``p-0`` so the
            # 20px icon owns the whole square. Le ``label`` tombe à
            # ``w-0`` + ``flex-none`` (cf. son slot) et le ``badge`` à
            # ``hidden``, donc la ligne flex ne tient plus que l'icône →
            # ``justify-center`` la pose au centre. Content-independent.
            "group-data-[open=false]/sidebar:justify-center "
            "group-data-[open=false]/sidebar:items-center "
            "group-data-[open=false]/sidebar:w-10 "
            "group-data-[open=false]/sidebar:h-10 "
            "group-data-[open=false]/sidebar:mx-auto "
            "group-data-[open=false]/sidebar:p-0 "
            "group-data-[open=false]/sidebar:gap-0 "
            # Motion + tactile feedback — aligned with Button. ``-all``
            # so the bg/text transition AND the click scale animate
            # together. ``active:scale-[0.97]`` is a touch gentler than
            # Button's 0.95 — rows are full-width so the inset reads as
            # "pressed" without making neighbors visually shift. Sur une
            # ligne verrouillée c'est ``aria-disabled:active:scale-100``
            # qui l'annule ; l'inertie, elle, vient du socle runtime.
            "transition-all duration-200 ease-out "
            "active:scale-[0.97] "
            "overflow-hidden whitespace-nowrap "
            "outline-none text-muted "
            # ⚠️ ``ring-offset-SURFACE``, pas ``-background``, et ce n'est pas
            # cosmétique. L'écart de l'anneau est PEINT : il doit se confondre
            # avec le fond sur lequel la ligne repose. Or l'aside est
            # ``bg-surface`` (#0f172a) et le token ``background`` vaut #020617
            # — plus SOMBRE. Mesuré au navigateur le 2026-08-15 :
            # ``--tw-ring-offset-shadow: 0 0 0 2px rgb(2 6 23)`` sur un aside
            # en ``rgb(15 23 42)``, ce qui dessine un liseré noir autour de la
            # ligne focalisée au lieu d'un écart invisible.
            # Les 30 autres ``ring-offset-background`` du catalogue sont
            # justes : ce sont des contrôles posés sur le fond de PAGE. La
            # sidebar (comme la navbar) est le cas particulier — elle peint sa
            # propre surface sous ses enfants focusables.
            "focus-visible:ring-2 focus-visible:ring-(--bz-focus) "
            "focus-visible:ring-offset-2 "
            "focus-visible:ring-offset-surface "
            # Hover bump aligned with Button's ghost variant (/10
            # rather than /5) so the row clearly responds to pointer.
            "data-[active=false]:hover:bg-text/10 "
            "data-[active=false]:hover:text-text "
            # Le survol et la pression sont neutralisés EXPLICITEMENT
            # sur un item verrouillé : l'inertie vient du socle
            # (``$bz._inert``, dérivé d'``aria-disabled``), pas d'un
            # ``pointer-events-none`` — qui aurait annulé le curseur.
            "aria-disabled:active:scale-100 "
            "aria-disabled:data-[active=false]:hover:bg-transparent "
            "aria-disabled:data-[active=false]:hover:text-muted "
            # ``<a>`` n'a pas d'attribut ``disabled`` natif, donc les
            # classes aria seules rendraient l'item gris pendant que le
            # lien continue de naviguer. Ce qui le rend VRAIMENT inerte,
            # c'est ``apply_disabled`` : il retire ``href``, les ``hx-*``
            # et pose ``tabindex=-1``. Le cas RÉACTIF, où ce strip SSR
            # n'a pas eu lieu, est couvert par ``$bz._inert`` côté
            # runtime — plus aucun ``pointer-events-none`` ici.
            "aria-disabled:opacity-50 aria-disabled:cursor-not-allowed"
        ),
        # ⚠️ ``data-[active=true]:`` sur le ``text-`` n'est PAS cosmétique.
        # Le ``text-muted`` du root et un ``text-(--bz-on-solid)`` NU sont deux
        # utilitaires de MÊME spécificité (0,1,0) : le vainqueur est le
        # dernier de la feuille Tailwind, et l'ordre de l'attribut
        # ``class=`` n'y change rien. Mesuré sur `bottom_bar`, qui portait
        # la même forme : deux couleurs sur six rendaient GRIS en dev — et
        # dans le `@theme` généré (`theme/tailwind.py`), ``muted`` sort en
        # DERNIER des onze couleurs sémantiques, donc un build compilé les
        # perdrait vraisemblablement toutes. La variante monte la
        # spécificité à (0,2,0) : le verdict ne dépend plus d'aucun ordre.
        # Gardé par `tests/consistency/test_active_layer_outranks_root.py`.
        "active": (
            "bg-(--bz-solid) data-[active=true]:text-(--bz-on-solid) font-medium "
            "data-[active=true]:hover:bg-(--bz-solid)/90"
        ),
        # Icon slot — fixed 1.25rem square, sits before the label.
        "icon": (
            "shrink-0 inline-flex items-center justify-center "
            "w-5 h-5 text-current"
        ),
        # Label — il FOND au repli, exactement comme ``title_brand``.
        #
        # ⚠️ Il a porté ``hidden`` jusqu'au 2026-09-01, et le commentaire
        # d'alors présentait ça comme un arbitrage : « on échange le
        # fondu contre un centrage inconditionnel ». L'échange n'avait
        # pas lieu d'être — ``w-0`` + ``flex-none`` rendent la place
        # AUSSI complètement que ``display:none``, donc la ligne flex ne
        # tient toujours que l'icône et ``justify-center`` la pose au
        # centre du carré ``w-10 h-10``, quelle que soit la longueur du
        # libellé. Le centrage ne coûte rien au fondu ; il n'y avait
        # qu'à écrire les deux.
        #
        # Les trois classes sont solidaires, et aucune n'est décorative :
        # ``opacity-0`` anime, ``w-0`` rend la place, ``flex-none``
        # empêche le ``flex-1`` du dépli de regonfler la boîte malgré
        # ``w-0``. Un simple ``opacity-0`` garde sa place et fait
        # déborder la ligne hors de la bande de 64 px — mesuré sur
        # ``title_brand``, qui est arrivé là par le même chemin.
        #
        # Pas de ``invisible`` ici, contrairement à ``title_brand`` : ce
        # ``<span>`` n'est pas focusable, il n'y a pas de parcours de
        # tabulation à protéger. Le nom accessible de la ligne repliée
        # ne dépend de toute façon pas de ce slot — il voyage sur
        # l'``aria-label`` du lien (cf. ``SidebarItem.render``).
        "label": (
            "flex-1 min-w-0 truncate "
            "transition-[opacity,width] duration-200 "
            "group-data-[open=false]/sidebar:opacity-0 "
            "group-data-[open=false]/sidebar:flex-none "
            "group-data-[open=false]/sidebar:w-0"
        ),
        # Badge — removed from layout entirely on collapse (its
        # ``ml-auto`` would otherwise fight the icon's centering).
        "badge": (
            "shrink-0 inline-flex items-center justify-center "
            "ms-auto transition-opacity duration-200 "
            "group-data-[open=false]/sidebar:hidden"
        ),
        # NB : le tooltip du rail replié (le nom de l'item au survol) vient
        # du panneau PARTAGÉ ``rail_tip`` — un seul nœud, dernier enfant de
        # l'aside, que chaque item déplace en écrivant ``rail_tip`` /
        # ``rail_tip_x`` / ``rail_tip_y`` dans le scope de l'aside.
        # ⚠️ Ce commentaire annonçait un ``ui.tooltip(...)`` par item
        # jusqu'au 2026-08-01 : ``sidebar.py`` n'importe ni n'instancie
        # Tooltip (zéro occurrence). Un panneau unique déplacé coûte un nœud
        # au lieu de N ; c'est un choix, pas un oubli de dogfooding.
    },
}


SIDEBAR_FOOTER_THEME: dict[str, Any] = {
    "slots": {
        # Pinned to the bottom of the sidebar column (``mt-auto``) ;
        # holds the trigger row + the (floating) popover panel.
        "root": "relative mt-auto shrink-0 px-1 pb-1 pt-2",
        # The clickable account row : [avatar] [name + subtitle] [chevron].
        # Collapses to a centered avatar-only square in the rail — same
        # ``w-10`` box + centering as :data:`SIDEBAR_ITEM_THEME` rows.
        "trigger": (
            "group/acct flex flex-row items-center gap-2 w-full "
            "px-2 py-2 rounded-selector cursor-pointer text-start "
            "hover:bg-text/10 transition-colors outline-none "
            # Stays SELECTED while the popover is open (``data-menu-open``
            # mirrors the ``acct_open`` flag) — not just on hover. A
            # distinct attr (not ``data-open``, which is the sidebar's
            # collapse state) so the two never clash.
            "data-[menu-open=true]:bg-text/10 "
            # ``-surface`` pour la même raison que la ligne de nav : le footer
            # repose sur l'aside, pas sur le fond de page.
            "focus-visible:ring-2 focus-visible:ring-(--bz-focus) "
            "focus-visible:ring-offset-2 focus-visible:ring-offset-surface "
            "group-data-[open=false]/sidebar:w-10 "
            "group-data-[open=false]/sidebar:h-10 "
            "group-data-[open=false]/sidebar:mx-auto "
            "group-data-[open=false]/sidebar:p-0 "
            "group-data-[open=false]/sidebar:justify-center "
            "group-data-[open=false]/sidebar:gap-0"
        ),
        # Initials/image chip. ``shrink-0`` keeps it square next to text ;
        # stays visible (centered) in the collapsed rail. Tinted by the
        # ``color`` prop via son pont (default primary).
        "avatar": (
            "shrink-0 inline-flex items-center justify-center "
            "h-9 w-9 rounded-selector bg-(--bz-bg) text-(--bz-text) "
            "text-xs font-semibold uppercase overflow-hidden"
        ),
        # Name + subtitle column ; folds away in the rail.
        "meta": (
            "flex flex-col min-w-0 flex-1 leading-tight text-start "
            "group-data-[open=false]/sidebar:hidden"
        ),
        "name": "text-sm font-semibold text-text truncate",
        "subtitle": "text-xs text-muted truncate",
        # Up/down chevron at the far edge ; folds away in the rail.
        "chevron": (
            "shrink-0 ms-auto "
            "group-data-[open=false]/sidebar:hidden"
        ),
        # The popover menu. ``$bz.helpers.floating`` flips it to
        # ``position:fixed`` on open, so it ESCAPES the sidebar's
        # ``overflow-y-auto`` clip. Same card identity as the Dropdown
        # panel ; ``z-50`` sits above the aside (z-40).
        "panel": (
            "min-w-[14rem] py-1 z-50 "
            "rounded-box border-(length:--bz-stroke) border-text/10 bg-interface "
            # Le fondu entrant. Les trois classes vont ensemble et
            # aucune ne sert seule — le pourquoi est en un seul
            # exemplaire dans ``overlay/dropdown/theme.py``.
            "shadow-lg "
            "transition-[opacity,display] transition-discrete duration-150 "
            "starting:opacity-0"
        ),
    },
}


# Rows inside the SidebarFooter popover — same look + slot contract as
# DropdownItem (both are :class:`MenuItem` shells), kept here so the
# sidebar doesn't reach into the overlay group for a theme (anti-règle 5).
SIDEBAR_FOOTER_ITEM_THEME: dict[str, Any] = {
    "slots": {
        # hover/focus bg lives in ``colors`` (incl. ``neutral``), not root —
        # so coloured rows tint cleanly. Plain ``hover:`` so ``<a>`` link
        # rows tint. Disabled : aria-only + NO ``pointer-events-none`` so the
        # ``cursor-not-allowed`` affordance paints (MenuItem keeps the row
        # inert by stripping the handlers). Same contract as
        # DROPDOWN_ITEM_THEME (both are MenuItem).
        "root": (
            "flex items-center gap-2 w-full text-start "
            "px-3 py-1.5 text-sm cursor-pointer outline-none "
            "transition-colors duration-100 "
            "aria-disabled:opacity-50 aria-disabled:cursor-not-allowed"
        ),
        # ``opacity-70`` so the icon inherits the row's tint (a ``color=``
        # row's icon matches its label instead of staying grey).
        "icon_left": "shrink-0 opacity-70",
        "label": "flex-1 truncate",
        "icon_right": "shrink-0 opacity-70",
        "shortcut": "shrink-0 ms-auto text-xs text-muted/70 tabular-nums",
    },
    "colors": {
        "neutral": "hover:bg-text/[0.06] focus:bg-text/[0.06]",
        "error":   "text-error hover:bg-error/10 focus:bg-error/10",
        "warning": "text-warning hover:bg-warning/10 focus:bg-warning/10",
        "success": "text-success hover:bg-success/10 focus:bg-success/10",
    },
}
