"""Default :class:`Stepper` / :class:`Step` / :class:`StepPanel` theme.

**Une identité visuelle, deux orientations.** La pastille numérotée est
le porteur d'état ; le connecteur qui la suit se teinte quand l'étape est
franchie. Tout est piloté par un SEUL attribut, ``data-status``, posé sur
le ``<li>`` de l'étape et valant ``done`` / ``current`` / ``upcoming`` /
``error`` :

- rendu STATIQUE côté serveur, pour que le premier paint soit juste avant
  que le runtime hydrate (même idiome que le ``data-selected`` de Tabs) ;
- gardé réactif par ``bz-attr:data-status`` — sauf sur une étape en
  ``error``, dont le statut est figé par le développeur et n'a donc aucune
  raison d'être recalculé.

Les descendants le lisent via ``group-data-[status=…]/step:``. Le groupe
est **nommé** (``group/step``) : sans le nom, un stepper imbriqué dans le
panneau d'un autre verrait la pastille interne hériter du statut de
l'étape externe (le sélecteur Tailwind ``group-*`` matche N'IMPORTE quel
ancêtre porteur — c'est exactement le piège des chevrons de Tree).

Slots :
- ``root``        : le wrapper — il porte le scope ``bz-data``, donc aussi
  l'input caché et les panneaux, qu'une ``<ol>`` ne peut pas héberger
  (elle n'accepte que des ``<li>``)
- ``list``        : la ``<ol>`` qui aligne les étapes
- ``step``        : le ``<li>`` — porte ``group/step`` + ``data-status``
- ``rail``        : la ligne pastille + connecteur
- ``bullet``      : la pastille (numéro / check / icône), ``<button>`` si
  ``clickable``, ``<span>`` sinon
- ``connector``   : le trait entre deux pastilles (absent sur la dernière)
- ``body``        : la colonne label + description
- ``label``       : le titre de l'étape
- ``description`` : la ligne secondaire
- ``panels``      : le conteneur des ``StepPanel`` (grid-stack)
- ``panel``       : un ``StepPanel``

Les tailles (``sizes``) portent la pastille, les deux lignes de texte et
le token de taille de l'icône. Ce qui dépend de l'ORIENTATION et non de
la taille — sens des flex, épaisseur et axe du connecteur, marges — vit
dans ``orientations``, lu à la main par ``Stepper.render()`` (le composeur
de base ne connaît que ``variants`` / ``sizes`` / ``modifiers``).
"""

from __future__ import annotations

from typing import Any

STEPPER_THEME: dict[str, Any] = {
    "slots": {
        # La liste au-dessus des panneaux ; le ``gap`` ne compte pas
        # l'input caché (un élément ``display:none`` n'est pas un flex item).
        "root": "flex flex-col gap-5",
        "list": "flex list-none",
        # ``group/step`` NOMMÉ — cf. docstring (piège du group anonyme).
        "step": "group/step relative flex min-w-0",
        "rail": "flex",
        # Aucune dimension ici : la boîte vient de ``sizes``, l'axe de
        # ``orientations``. Les quatre statuts se disputent le même
        # élément, dans l'ordre upcoming (base) → current → done → error.
        "bullet": (
            "flex items-center justify-center shrink-0 rounded-full "
            "border-(length:--bz-stroke-strong) font-semibold "
            "transition-[color,background-color,border-color] "
            "duration-200 ease-out "
            "border-text/15 bg-background text-muted "
            "group-data-[status=current]/step:border-(--bz-solid) "
            "group-data-[status=current]/step:bg-(--bz-bg) "
            "group-data-[status=current]/step:text-(--bz-text) "
            "group-data-[status=done]/step:border-(--bz-solid) "
            "group-data-[status=done]/step:bg-(--bz-solid) "
            "group-data-[status=done]/step:text-(--bz-on-solid) "
            "group-data-[status=error]/step:border-error "
            "group-data-[status=error]/step:bg-error "
            # ``text-background`` et non ``text-white`` : la pastille en
            # erreur est REMPLIE, il lui faut le contraire du fond de
            # page — un blanc figé serait juste en clair et faux en
            # sombre, sans que ça se voie dans le mode qu'on teste.
            "group-data-[status=error]/step:text-background "
            "focus-visible:outline-none focus-visible:ring-2 "
            "focus-visible:ring-offset-2 "
            "focus-visible:ring-offset-background "
            "focus-visible:ring-(--bz-focus) "
            # ``enabled:`` compile vers ``&:enabled``, qui ne matche QUE
            # les contrôles de formulaire : sur la pastille ``<span>`` du
            # mode non-cliquable, ces deux règles sont des no-op — c'est
            # exactement ce qu'on veut, un indicateur n'a pas de curseur
            # pointer. Pas de teinte au survol : elle se battrait avec
            # les quatre remplissages de statut sur le même élément (et
            # elle serait morte de toute façon sur un pointeur grossier).
            #
            # ⚠️ C'était ``not-disabled:`` jusqu'au 2026-08-13, et le
            # commentaire ci-dessus décrivait déjà l'intention — mais
            # PAS ce que la variante fait. En Tailwind v4 ``not-*`` est
            # une négation générique : ``&:not(:disabled)`` matche tout
            # élément non désactivé, ``<span>`` compris. Mesuré au
            # navigateur : la pastille d'un stepper indicateur rendait
            # ``cursor: pointer`` — elle avait l'air cliquable sans que
            # rien ne le soit.
            "enabled:cursor-pointer enabled:active:scale-95 "
            # ⚠️ ``aria-disabled:`` et NON ``disabled:`` : la pastille
            # est un ``<span>`` en mode non cliquable, et ``:disabled``
            # ne matche que les contrôles de formulaire — les deux
            # règles y étaient donc mortes. Contrairement aux deux
            # ``not-disabled:`` ci-dessus, dont le no-op est VOULU (un
            # indicateur n'a pas de curseur pointer), celui-ci était un
            # défaut : une étape verrouillée ne ternissait même pas.
            "aria-disabled:opacity-50 aria-disabled:cursor-not-allowed"
        ),
        "connector": (
            "shrink-0 rounded-full bg-text/15 "
            "transition-colors duration-200 ease-out "
            "group-data-[status=done]/step:bg-(--bz-solid)"
        ),
        "body": "flex flex-col min-w-0",
        "label": (
            "font-medium truncate text-muted "
            "transition-colors duration-200 ease-out "
            "group-data-[status=current]/step:text-text "
            "group-data-[status=done]/step:text-text "
            "group-data-[status=error]/step:text-error"
        ),
        "description": "text-muted truncate",
        # Les panneaux se superposent dans la MÊME cellule de grid : un
        # fondu croisé les empilerait verticalement sinon (idiome repris
        # de Tabs, où le symptôme a été payé).
        "panels": "grid",
        "panel": "outline-none col-start-1 row-start-1",
    },
    "sizes": {
        "xs": {
            "bullet": "w-6 h-6 text-[10px]",
            "label": "text-xs",
            "description": "text-[10px]",
            "icon_size": "xs",
        },
        "sm": {
            "bullet": "w-7 h-7 text-xs",
            "label": "text-sm",
            "description": "text-xs",
            "icon_size": "xs",
        },
        "md": {
            "bullet": "w-9 h-9 text-sm",
            "label": "text-base",
            "description": "text-xs",
            "icon_size": "sm",
        },
        "lg": {
            "bullet": "w-11 h-11 text-base",
            "label": "text-lg",
            "description": "text-sm",
            "icon_size": "md",
        },
        "xl": {
            "bullet": "w-14 h-14 text-lg",
            "label": "text-xl",
            "description": "text-base",
            "icon_size": "lg",
        },
    },
    # Lu à la main par ``render()`` — le composeur n'applique que
    # ``variants`` (root seul) / ``sizes`` / ``modifiers``.
    "orientations": {
        "horizontal": {
            "list": "flex-row items-start",
            # Chaque étape prend une part égale ET son connecteur mange
            # l'espace restant ; la DERNIÈRE n'a pas de connecteur, donc
            # elle ne doit pas revendiquer une part (son label collerait
            # au centre d'une colonne vide).
            "step": "flex-col flex-1",
            "step_last": "flex-col flex-none",
            "rail": "flex-row items-center w-full gap-2",
            "connector": "h-0.5 flex-1",
            "body": "mt-2 pr-3",
            "body_last": "",
        },
        "vertical": {
            "list": "flex-col",
            "step": "flex-row gap-3",
            "step_last": "flex-row gap-3",
            "rail": "flex-col items-center gap-1 self-stretch",
            "connector": "w-0.5 flex-1 min-h-5",
            "body": "pb-6",
            # La dernière étape ne pousse plus rien sous elle.
            "body_last": "pb-0",
        },
    },
}
