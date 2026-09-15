"""Default :class:`Alert` theme.

Soft tinted background (10% of the color), 1px tinted border (20%),
generous padding, optional semibold title above the message. Leading
icon and trailing dismiss button are inline-flex aligned so multi-line
messages stay nicely indented.

Slots :
- ``root``     : the flex wrapper that holds everything. **Pas de**
  ``role="alert"`` : Alert ne le pose jamais automatiquement (sémantique
  « interrompre maintenant », injustifiée pour un panneau d'info) — le
  caller le passe s'il le veut. Cf. ``alert.py`` § A11y note.
- ``icon``     : the leading icon (auto-derived from color, override-able)
- ``content``  : vertical stack of title + message
- ``title``    : semibold heading line
- ``message``  : the actual prose
- ``dismiss``  : slot du ``<button>`` × de fermeture — construit par ``dismiss_button``
  (``base/_wiring.py``), **plus** par un IconButton ghost comme jadis
"""

from __future__ import annotations

from typing import Any

ALERT_THEME: dict[str, Any] = {
    "slots": {
        # ``items-center`` (root) + ``justify-center`` (content/icon)
        # keep vertical centering correct for any content shape — with
        # ``items-start`` the icon pins to the top while a short one-line
        # message floats in the middle, a visible offset.
        "root": (
            "flex items-center gap-3 w-full "
            "rounded-box border-(length:--bz-stroke) px-4 py-3 "
            # ⚠️ Portait ``transition-opacity duration-200``, qui
            # n'animait rien : le dismiss pose ``bz-show``, donc un
            # ``display:none`` — mesuré le 2026-09-04, opacité 1
            # jusqu'à la disparition, en deux images.
            #
            # Le remède des panneaux (``starting:opacity-0`` +
            # ``transition-discrete``) ne vaut PAS ici : une alerte
            # est DANS le flux, donc un fondu sans effondrement de
            # hauteur laisserait un trou pendant l'animation. La
            # classe part. Le jour où on veut la sortie animée,
            # c'est la HAUTEUR qu'il faut traiter, pas l'opacité.
            "bg-(--bz-bg) border-(--bz-solid)/20 text-(--bz-text)"
        ),
        # ``leading-none`` neutralises the icon font's line-height so the
        # wrapper hugs the glyph and the centering math works out.
        "icon": (
            "shrink-0 flex items-center justify-center leading-none "
            "text-(--bz-text)"
        ),
        # ``justify-center`` keeps a short single-line message vertically
        # centered when the icon + dismiss button drive the alert's
        # natural height.
        "content": "flex-1 flex flex-col gap-0.5 min-w-0 justify-center",
        "title": "font-semibold text-sm leading-tight text-(--bz-text)",
        # ``text-text/80`` keeps the message readable in any color context ;
        # the title (not the body) carries the colour cue.
        "message": "text-sm leading-snug text-text/80",
        # × ghost button — le look (jadis porté par un IconButton ghost)
        # vit ici depuis l'unification dismiss_button : carré h-8 w-8,
        # rounded-box, teinte ``--bz-bg``, hover/focus ring. Les paliers
        # viennent du pont que le socle pose sur la racine de l'alert.
        "dismiss": (
            "shrink-0 inline-flex items-center justify-center "
            "h-8 w-8 rounded-field text-(--bz-text) "
            "transition-colors duration-200 "
            "not-disabled:hover:bg-(--bz-bg) "
            "focus-visible:outline-none focus-visible:ring-2 "
            "focus-visible:ring-offset-2 focus-visible:ring-offset-background "
            "focus-visible:ring-(--bz-focus)"
        ),
    },
    # Per-color icon defaults (Iconify ``lucide`` names), auto-picked when
    # ``icon=`` isn't passed.
    "color_icons": {
        "info": "info",
        "success": "circle-check",
        "warning": "triangle-alert",
        "error": "octagon-x",
    },
    # Fixed icon size — keeps the icon proportional to the body copy
    # without exposing another prop.
    "icon_size": "lg",
}
