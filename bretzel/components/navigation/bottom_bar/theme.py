"""Default theme for the BottomBar family (BottomBar / BottomBarItem).

Deux pièces, pendant *bas d'écran* du trio Navbar :

- **BottomBar** — le ``<nav>`` collé au bas du viewport. ``sticky bottom-0``
  et pas ``fixed`` : un élément sticky **reste dans le flux**, donc il
  réserve sa propre hauteur et le contenu de la page n'est jamais masqué —
  sans le nœud « spacer » qu'un ``fixed`` aurait exigé, et qui aurait cassé
  les kwargs universels (cf. le docstring du composant).
- **BottomBarItem** — un onglet : icône AU-DESSUS du label, ``flex-1`` donc
  tous les onglets ont la même largeur. C'est là toute l'identité visuelle
  vs ``NavbarItem`` (pilule horizontale, largeur au contenu) — le
  comportement, lui, est partagé mot pour mot via ``navigation/_wiring``.

Règle de composition (elle porte deux corrections mesurées, cf. les
commentaires en place) : **une propriété CSS n'est déclarée que par une
couche**, et toute classe qui doit BATTRE une classe du root porte une
variante d'état, jamais la forme nue. Le composant n'ayant plus aucun axe
(ni ``variant``, ni ``sticky`` — les deux coupés, cf. le composant), tout
tient dans ``slots`` et la règle se lit d'un coup d'œil.

Slots :
- ``bottom_bar.root``     : le ``<nav>`` — géométrie seule
- ``bottom_bar.inner``    : la rangée d'onglets (flex-row)
- ``item.root``           : l'onglet, colonne icône + label
- ``item.active``         : couche ajoutée quand l'onglet est actif
- ``item.icon_wrap``      : conteneur relatif icône + badge
- ``item.icon``           : slot icône
- ``item.label``          : le texte sous l'icône
- ``item.badge``          : le PLACEMENT de la pastille, au coin de l'icône
- ``item.badge_pill``     : son LOOK par défaut — scalaire uniquement, un
                            Component passé en badge garde le sien
"""

from __future__ import annotations

from typing import Any

BOTTOM_BAR_THEME: dict[str, Any] = {
    # ⚠️ Règle de composition de CE thème : **une propriété CSS n'est
    # déclarée qu'UNE fois**. Deux utilitaires concurrents de même
    # spécificité laisseraient l'ordre de la feuille Tailwind trancher, pas
    # l'ordre du ``class=`` — c'est le piège documenté sur la couche active
    # de l'item, plus bas, et il a coûté deux couleurs invisibles.
    "slots": {
        # ``mt-auto`` : dans un layout ``flex flex-col`` plus haut que son
        # contenu (le cas d'une app shell en ``min-h-screen``), la barre est
        # poussée en bas plutôt que de flotter sous un contenu court. En
        # flux bloc classique, ``margin-top: auto`` vaut 0 — aucun effet de
        # bord.
        #
        # ``pb-[env(safe-area-inset-bottom)]`` : la barre gestuelle de
        # l'iPhone mange le bas du viewport. Sans ce padding, le dernier
        # onglet est à moitié sous le trait. Sur un appareil sans encoche,
        # ``env()`` vaut 0 — donc aucun coût.
        #
        # ``z-30`` : même palier que la navbar, sous la sidebar (40) et sous
        # dialog/drawer (50) — un modal peint par-dessus la barre.
        # ``sticky bottom-0`` : la barre reste DANS le flux — elle réserve sa
        # hauteur, donc rien n'est jamais masqué — mais refuse de sortir de
        # l'écran par le bas tant que son conteneur descend plus bas. C'est
        # ça, une tab bar : un onglet toujours sous le pouce. Ce n'est pas
        # une option (pas de prop ``sticky=``, cf. le composant) : une barre
        # qui s'en va au scroll n'est plus une tab bar.
        #
        # Le fond passe légèrement translucide + ``backdrop-blur-md`` pour
        # que le contenu qui défile dessous s'adoucisse au lieu de
        # disparaître d'un coup (idiome iOS).
        "root": (
            "group/bottombar w-full mt-auto z-30 "
            "sticky bottom-0 bg-surface/95 backdrop-blur-md "
            "border-t-(length:--bz-stroke) border-text/10 "
            "pb-[env(safe-area-inset-bottom)]"
        ),
        # La rangée. C'est le ``flex-1`` de chaque item qui fait l'égalité de
        # largeur (l'idiome tab bar). ``14`` (56px) aligne la hauteur sur
        # celle de la navbar, donc une app qui porte les deux a le même
        # gabarit en haut et en bas.
        #
        # ⚠️ ``min-h-14`` et PAS ``h-14`` : avec une hauteur FIXE, une icône
        # plus grande que le défaut (``icon=ui.icon(…, size="xl")`` → 36px)
        # plus le gap plus le label dépassent la place disponible, et le
        # ``overflow:hidden`` que ``truncate`` pose sur le label le rogne
        # VERTICALEMENT — le texte se réduit à un liséré de glyphes. Constaté
        # à l'œil sur une capture, invisible à la mesure : ``scrollWidth ==
        # clientWidth`` (rien ne déborde en largeur) et le label a sa largeur
        # normale. Le dépôt tranche ce cas côté framework : un composant ne
        # clippe jamais son propre contenu, c'est un invariant, pas un
        # arbitrage laissé à l'app (cf. todo.md § A-ter, « Containment »).
        "inner": "flex flex-row items-stretch min-h-14 w-full",
    },
    # ⚠️ PAS de table ``variants`` — et c'est délibéré (décision 2026-08-09).
    # Une pilule arrondie détachée des bords (idiome iOS 17 / Material 3) a
    # existé ici en ``variant="floating"`` pendant une journée, puis a été
    # coupée : elle échoue les quatre critères de la règle d'opinionation, et
    # d'abord le décisif — « aurait-on ce composant sous DEUX formes dans la
    # MÊME app ? ». Non : une app a une seule tab bar, et le choix de look se
    # fait une fois. Un axe qu'on ne règle qu'une fois par app est une
    # décision de THÈME, pas un prop.
    #
    # L'échappatoire est le tier 2 documenté (``theme.md``), un override
    # profond-fusionné, gaté par ``test_theme_override_merge`` ::
    #
    #     Bretzel(theme=Theme(components={"bottom_bar": {"slots": {
    #         "root": "group/bottombar w-full mt-auto z-30 mx-3 mb-3 "
    #                 "rounded-box border border-text/10 shadow-lg "
    #                 "pb-[env(safe-area-inset-bottom)]",
    #     }}}))
    #
    # Ne PAS réintroduire de ``variant`` ici sans que deux formes
    # co-occurrent réellement dans une même vue. Même verdict, et même
    # raison, que le ``segmented`` de ToggleGroup.
}


BOTTOM_BAR_ITEM_THEME: dict[str, Any] = {
    "slots": {
        # L'onglet — colonne icône/label, ``flex-1`` pour l'égalité de
        # largeur, ``min-w-0`` pour que le label puisse ellipser au lieu de
        # pousser ses voisins.
        #
        # ``active:scale-[0.94]`` un cran plus marqué que la navbar (0.97) :
        # une cible tactile a besoin d'un retour plus lisible qu'un survol
        # souris, et c'est un composant fait pour le doigt.
        #
        # Pas de ``hover:bg-*`` ici, contrairement à NavbarItem : sur mobile
        # le survol n'existe pas (memory `user_browser_has_no_fine_pointer`
        # le rappelle même sur desktop), et un fond plein la largeur de
        # l'onglet est visuellement lourd. Le survol ne change que la
        # couleur du texte.
        #
        # ``focus-visible:ring-inset`` et pas ``ring-offset-2`` : la barre
        # est bordée et sans marge interne, un halo débordant serait coupé.
        "root": (
            "group/tab relative flex flex-1 min-w-0 flex-col "
            "items-center justify-center gap-1 px-1 py-1.5 "
            "cursor-pointer select-none "
            "transition-all duration-200 ease-out "
            "active:scale-[0.94] "
            "outline-none text-muted "
            "focus-visible:ring-2 focus-visible:ring-(--bz-focus) "
            "focus-visible:ring-inset "
            "data-[active=false]:hover:text-text "
            # Le survol et la pression sont neutralisés EXPLICITEMENT
            # sur un item verrouillé : l'inertie vient du socle
            # (``$bz._inert``, dérivé d'``aria-disabled``), pas d'un
            # ``pointer-events-none`` — qui aurait annulé le curseur.
            "aria-disabled:active:scale-100 "
            "aria-disabled:data-[active=false]:hover:text-muted "
            "aria-disabled:opacity-50 aria-disabled:cursor-not-allowed"
        ),
        # L'actif ne repeint PAS un fond : sur une tab bar, c'est la couleur
        # de l'icône + du label qui signale l'onglet courant (iOS/Android).
        #
        # ⚠️ ``data-[active=true]:`` n'est PAS cosmétique — c'est ce qui fait
        # GAGNER la couleur active. ``text-(--bz-text)`` nu et le ``text-muted``
        # du root sont deux utilitaires de MÊME spécificité (0,1,0) : le
        # vainqueur est celui qui vient le plus tard dans la feuille Tailwind,
        # et l'ordre de l'attribut ``class=`` n'y change RIEN.
        #
        # Constaté au navigateur : avec la forme nue, ``color=error`` et
        # ``color=info`` rendaient GRIS (les quatre autres passaient). Ne pas
        # se fier à ce partage-là pour en déduire une règle : en dev, Tailwind
        # tourne dans le navigateur et émet ses règles **dans l'ordre où il
        # rencontre les classes dans le DOM** — le camp des perdants dépend
        # donc de la page. Le seul ordre stable est celui du `@theme` généré
        # (`bretzel/theme/tailwind.py`), où ``muted`` sort **en dernier** des
        # onze couleurs sémantiques : dans un build compilé, le nu perdrait
        # vraisemblablement pour les SIX couleurs. Il n'y a pas de build
        # compilé aujourd'hui pour l'affirmer (cf. memory
        # `reference_css_build_reality`), et c'est précisément l'argument : la
        # variante monte la spécificité à (0,2,0), donc le verdict ne dépend
        # plus d'un ordre — ni de celui du dev, ni de celui d'un futur build.
        #
        # Les frères ``navbar`` et ``sidebar`` portent encore la forme nue.
        "active": "data-[active=true]:text-(--bz-text) font-semibold",
        # Conteneur relatif icône + badge : c'est lui qui ancre la pastille
        # au coin de l'ICÔNE, pas au coin de l'onglet (qui est bien plus
        # large que son contenu à cause du flex-1).
        "icon_wrap": "relative inline-flex items-center justify-center",
        # Pas de ``text-*`` ici : ``<iconify-icon>`` se dimensionne par
        # ``font-size``, et une classe de taille posée sur le slot entrerait
        # en concurrence avec celle que le composant Icon compose lui-même
        # (cf. traps.md § iconify-icon). La taille passe donc par
        # ``Icon(size="lg")`` dans ``__init__``.
        "icon": "shrink-0 text-current",
        # ⚠️ ``leading-tight`` et PAS ``leading-none``. ``truncate`` implique
        # ``overflow: hidden`` ; avec ``line-height: 1``, la boîte de ligne
        # vaut exactement la taille de police (11px) alors que les glyphes en
        # demandent ~13 — donc les jambages de « g » / « p » étaient rognés
        # sur CHAQUE label. Mesuré : ``scrollHeight`` 13 vs ``clientHeight``
        # 11 sur les 100 onglets de la page de banc.
        #
        # Le piège d'instrumentation valait la leçon : le probe de containment
        # ne lisait que l'axe HORIZONTAL (``scrollWidth``), donc il était vert
        # pendant que le texte était coupé en hauteur. Un défaut de clipping
        # se mesure sur les deux axes.
        "label": "max-w-full truncate text-[11px] leading-tight",
        # ⚠️ Le badge est en DEUX slots, et la coupure est load-bearing.
        #
        # ``badge`` = le PLACEMENT seul. Il s'applique à toute pastille, y
        # compris un Component que l'appelant a stylé lui-même
        # (``badge=ui.badge("new", color="success")``). ``left-full -ml-1``
        # plutôt que ``-right-2`` : l'ancrage part du bord droit de l'icône,
        # donc il tient quelle que soit la largeur du glyphe.
        #
        # ``badge_pill`` = le LOOK par défaut, appliqué UNIQUEMENT quand la
        # valeur est un scalaire — le seul cas où le framework doit inventer
        # un visuel. Mesuré avant cette coupure : un Component passé en badge
        # ressortait avec ``bg-error`` ET ``bg-success/15``, ``text-[10px]``
        # deux fois, et deux couleurs de texte concurrentes. Il rendait vert
        # en dev par chance d'ordre de feuille ; ``error`` étant généré APRÈS
        # ``success`` dans le `@theme`, un build compilé aurait viré au
        # rouge. Un composant décide de son look ; le parent ne fait que le
        # poser.
        #
        # ``text-error-foreground`` et pas ``text-white`` : le framework émet
        # un compagnon ``-foreground`` pour chaque couleur sémantique
        # (`theme/tailwind.py`), donc le chiffre suit une palette redéfinie —
        # un ``error`` pâle garderait du texte lisible, là où un blanc en dur
        # disparaîtrait. La couleur de la pastille, elle, reste ``error`` en
        # dur : une notification est rouge quelle que soit la couleur de
        # l'onglet.
        "badge": (
            "absolute -top-1 left-full -ml-1 "
            "inline-flex items-center justify-center"
        ),
        "badge_pill": (
            "min-w-4 h-4 px-1 rounded-full "
            "bg-error text-error-foreground text-[10px] font-semibold "
            "leading-none"
        ),
    },
}
