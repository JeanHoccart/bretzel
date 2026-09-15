"""Theme slots for ``ui.draggable``.

Slots :

- ``root``     : the grabbable wrapper. ``touch-action`` y laisse le
                 PAN (``touch-pan-x touch-pan-y``) : la carte occupe
                 toute la surface d'une colonne de kanban, donc lui
                 interdire le geste de défilement revient à interdire de
                 défiler tout court. C'est le geste ATTRAPÉ qui reprend
                 la main, pas la CSS — cf. le ``touchmove`` non passif de
                 ``19_dnd.js``, et le § ci-dessous.
- ``dragging`` : composed over ``root`` while this item is in flight.
- ``handle``   : the opt-in grip. Sized ≥ 24×24 px (WCAG 2.2 target
                 size) because a 16 px grip is unusable with a finger, and
                 the browser of record is touch-first.
- ``disabled`` : an item that cannot be picked up.
"""

from __future__ import annotations

from typing import Any

DRAGGABLE_THEME: dict[str, Any] = {
    "slots": {
        # No ``cursor-grab``: it is a no-op on a touch device and would be
        # the only affordance if it were the only one. The visible signal
        # is the handle (when asked for) and the drag state itself.
        "root": "relative transition-shadow duration-150",
        # ``select-none`` matters during the gesture specifically: without
        # it a long-press on touch starts a text selection that fights the
        # drag and leaves the page with a blue smear.
        #
        # ⚠️ ``touch-pan-x touch-pan-y`` et surtout PAS ``touch-none``,
        # qui a vécu ici jusqu'au 2026-08-21. ``touch-action: none``
        # retire au navigateur le geste de défilement sur toute la
        # surface de la carte : dans une colonne pleine de cartes, le
        # doigt ne pouvait plus rien faire défiler dès qu'il se posait —
        # « le tactile ne marche pas, je ne peux pas scroller en
        # sélectionnant les cards ». Le comble : ``19_dnd.js`` porte un
        # seuil commenté « c'est elle qui PRÉSERVE LE SCROLL », qui
        # marchait très bien — au-dessus d'une CSS qui rendait le
        # défilement impossible.
        #
        # Le pan seul NE SUFFIT PAS, et c'est mesuré : il rend le
        # défilement et **perd l'attrape**, le navigateur emportant le
        # geste. La seconde moitié est le ``touchmove`` non passif de
        # ``19_dnd.js``, qui reprend la main quand l'appui long aboutit —
        # à cet instant le doigt n'a pas bougé, donc rien n'est en cours.
        # Les deux moitiés sont gatées séparément par
        # ``tests/runtime_js/test_a_draggable_card_still_lets_the_finger_scroll.py``.
        "grab_all": "touch-pan-x touch-pan-y select-none",
        # Avec une poignée, la racine devient une RANGÉE : sinon le
        # grip est un enfant bloc et prend sa propre ligne au-dessus
        # du contenu. Invisible à tous les tests — le DOM et les
        # attributs sont identiques dans les deux cas ; ça ne se voit
        # qu'à la capture d'écran.
        "with_handle": "flex items-center gap-2",
        # ``min-w-0`` : sans lui, un enfant flex refuse de rétrécir
        # sous sa largeur de contenu et déborde la colonne.
        "handle_body": "min-w-0 grow",
        # Pendant le geste, l'original devient un EMPLACEMENT, pas une
        # carte en double : c'est le clone (`.bz-drag-preview`, un hook
        # dans theme/css.py) qui porte le relief et suit le pointeur.
        # Lui laisser une ombre ferait deux cartes soulevées à la fois.
        # ⚠️ **La carte GARDE sa taille, et c'est un choix** — tranché le
        # 2026-09-13 après l'avoir essayée dans les deux sens.
        #
        # Pendant le geste, l'original pâlit et reste à sa place : la zone
        # d'arrivée s'ouvre de la hauteur d'une carte, et les voisins vont
        # d'un coup à leur nouvelle position. C'est lisible parce que ce
        # qu'on voit est ce qu'on va obtenir, à l'échelle où on l'obtiendra.
        #
        # L'autre voie — réduire la carte à un emplacement en pointillés,
        # comme react-beautiful-dnd — a été écrite, mesurée (50 px au repos
        # contre 9 en vol) puis RETIRÉE du défaut : elle demande à l'œil de
        # relier un trait fin à une carte qui flotte ailleurs, et sur une
        # liste courte ça coûte plus que ça ne rend.
        #
        # ⚠️ **Elle reste atteignable, et c'est le sujet de ce commentaire.**
        # Le runtime publie ``data-bz-drag-axis`` sur l'élément en vol
        # (``y`` pour une liste verticale, ``x`` pour une rangée) — pour une
        # zone qui INSÈRE seulement ; une zone ``holds="one"`` n'insère rien
        # et n'en reçoit pas. Une app qui veut l'emplacement surcharge ce
        # slot, une fois, pour toute l'app ::
        #
        #     Theme(components={"draggable": {"slots": {"dragging": (
        #         "data-[bz-dragging=true]:opacity-30 "
        #         "data-[bz-drag-axis]:opacity-100 "
        #         "data-[bz-drag-axis]:overflow-hidden "
        #         "data-[bz-drag-axis]:rounded-box "
        #         "data-[bz-drag-axis]:border-(length:--bz-stroke) "
        #         "data-[bz-drag-axis]:border-dashed "
        #         "data-[bz-drag-axis=y]:h-3 "
        #         "data-[bz-drag-axis=x]:w-3 "
        #         "transition-[height,width] duration-150 ease-out"
        #     )}}})
        #
        # Pas de prop pour ça, et c'est délibéré : ``holds=`` décrit un
        # FAIT de la zone — combien d'éléments elle tient, ce dont le
        # serveur se sert — tandis que « la carte doit-elle rétrécir » est
        # un goût. Les faits vivent sur le composant, les goûts dans le
        # thème. Une prop de plus ferait trancher chaque auteur, sur chaque
        # zone, une question sur laquelle il n'a pas d'avis — et ``check``
        # n'en pourrait rien dire, faute de mauvaise réponse.
        "dragging": (
            "data-[bz-dragging=true]:opacity-30 "
            "data-[bz-dragging=true]:grayscale"
        ),
        # ⚠️ **PAS de ``pointer-events-none``.** Le mettre sur le même
        # élément que ``cursor-not-allowed`` ANNULE le curseur : un
        # élément qui ne reçoit aucun événement de pointeur n'en peint
        # jamais. C'est le piège exact que
        # ``test_disabled_affordance`` documente (le Tree l'avait shippé),
        # et l'inertie est de toute façon déjà obtenue côté runtime, qui
        # ignore un ``data-bz-disabled`` au ``pointerdown``.
        "disabled": "opacity-50 cursor-not-allowed",
        # 24px floor = WCAG 2.2 § 2.5.8. iOS HIG asks 44, Material 48 —
        # this is the accessible minimum, not a comfortable target, and a
        # touch-first app should pass a bigger one via ``classes=``.
        # ⚠️ ``touch-none`` reste JUSTE ici, et pour la raison inverse :
        # la poignée est une cible de 24 px dédiée au geste, pas une
        # surface de lecture. Personne ne pose le doigt dessus pour faire
        # défiler, et l'y autoriser rendrait le geste hésitant.
        "handle": (
            "inline-flex items-center justify-center "
            "min-w-6 min-h-6 shrink-0 touch-none select-none "
            "text-muted hover:text-(--bz-text) "
            "focus-visible:outline-none focus-visible:ring-2 "
            "focus-visible:ring-(--bz-focus) rounded"
        ),
    },
}
