"""Default :class:`SignaturePad` theme.

Un cadre pointillé, une ligne de base, et un canvas qui remplit tout.
Trois détails ne sont pas cosmétiques :

- ``touch-none`` (``touch-action: none``) sur le canvas est
  **obligatoire**. Sans lui le navigateur prend le glissement d'un doigt
  pour un défilement de page et n'envoie jamais les ``pointermove`` : le
  pad est inutilisable au tactile, en silence, alors qu'il marche à la
  souris. Même piège que la poignée du Resizable, payé une fois pour
  toutes.
- ``text-text`` sur le canvas n'est pas décoratif : c'est la couleur que
  le runtime LIT (``getComputedStyle(...).color``) pour encrer le trait.
  Elle suit donc le mode sombre sans qu'aucun prop ne l'énonce — un
  ``pen_color`` aurait figé une encre qui devient invisible sur l'autre
  fond.
- La hauteur vient du slot ``pad`` via la table ``sizes``, et de nulle
  part ailleurs : un ``<canvas>`` n'a **aucune taille intrinsèque**, donc
  un pad sans hauteur déclarée est un pad de zéro pixel.

L'invite (``hint``) est masquée dès qu'un trait existe, via
``data-empty`` que le runtime pose sur le cadre. Un attribut plutôt
qu'une classe : ``data-[empty=…]:`` est le variant que le reste du dépôt
utilise pour les états pilotés par le JS (cf. ``data-selected`` des
clusters sélecteurs).

Slots :
- ``root``    : la colonne — cadre puis barre d'actions
- ``pad``     : le cadre pointillé qui porte la hauteur et ``data-empty``
- ``canvas``  : la surface de tracé
- ``hint``    : l'invite centrée, effacée au premier trait
- ``baseline``: la ligne au-dessus de laquelle on signe
- ``actions`` : la rangée sous le cadre (le bouton Effacer)
"""

from __future__ import annotations

from typing import Any

SIGNATURE_PAD_THEME: dict[str, Any] = {
    "slots": {
        "root": "flex flex-col gap-2 w-full",
        "pad": (
            "relative w-full rounded-box overflow-hidden "
            "border-(length:--bz-stroke-strong) border-dashed border-text/15 bg-surface "
            "transition-colors duration-150 ease-out "
            "focus-within:border-(--bz-border-hover) "
            # Le cadre grise ET perd son pointillé quand il est verrouillé
            # : un pad signé ne doit plus INVITER à signer.
            "data-[locked=true]:border-solid "
            "data-[locked=true]:bg-text/5 "
            "data-[locked=true]:cursor-not-allowed"
        ),
        # ``block`` : un canvas est ``inline`` par défaut, donc il traîne
        # la ligne de base de son parent et laisse quelques pixels sous
        # lui — une bande claire au bas du cadre, que personne ne relie
        # jamais à ça.
        "canvas": "block w-full h-full touch-none select-none text-text",
        # Pas de ``text-<taille>`` ici : la table ``sizes`` en pose une,
        # et les deux coexisteraient dans le HTML — c'est Tailwind qui
        # trancherait par l'ordre de SA feuille, pas la string. Le slot
        # ne garde que ce qui ne dépend pas du palier.
        "hint": (
            "pointer-events-none absolute inset-x-0 bottom-3 "
            "text-center text-text/40 "
            # Effacée dès le premier trait — l'invite a dit ce qu'elle
            # avait à dire.
            "transition-opacity duration-150 ease-out "
            "data-[empty=false]:opacity-0"
        ),
        "baseline": (
            "pointer-events-none absolute inset-x-6 bottom-10 "
            "border-b-(length:--bz-stroke) border-text/20"
        ),
        "actions": "flex items-center justify-end",
    },
    # La hauteur du cadre, et rien d'autre : c'est le seul axe de taille
    # qu'un pad ait. Pas de prop ``height=`` en plus — deux façons de
    # dire la même chose (principe 4) ; qui veut une hauteur exacte passe
    # par ``classes="!h-64"``.
    "sizes": {
        "xs": {"pad": "h-24", "hint": "text-xs", "button": "xs"},
        "sm": {"pad": "h-32", "hint": "text-xs", "button": "xs"},
        "md": {"pad": "h-40", "hint": "text-sm", "button": "sm"},
        "lg": {"pad": "h-56", "hint": "text-sm", "button": "sm"},
        "xl": {"pad": "h-72", "hint": "text-base", "button": "md"},
    },
}
