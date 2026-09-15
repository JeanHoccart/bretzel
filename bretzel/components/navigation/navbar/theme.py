"""Default theme for the Navbar family (Navbar / NavbarSection / NavbarItem).

Three pieces, horizontal counterpart to the Sidebar trio :

- **Navbar** — the ``<header>`` container, full-width flex row. Sticky
  optional. Same ``current_path`` reactive scope (``bz-data``) as
  Sidebar so a single page can host both and they stay in sync on
  partial nav.
- **NavbarSection** — positional groupings (``left`` / ``center`` /
  ``right``) inside the navbar. Just flex containers with the right
  margin auto, no behaviour of their own.
- **NavbarItem** — horizontal nav row, mirror of SidebarItem with a
  different look (underline / bg pill on hover-and-active rather than
  fade-on-collapse). Reuses the same htmx partial-nav wiring +
  ``current_path``-driven active state.

Slots :
- ``navbar.root``         : the ``<header>`` flex row
- ``navbar.inner``        : the inner ``<nav>`` flex row (max-width clamp)
- ``navbar.section_left``     : left section flex container
- ``navbar.section_center``   : center section flex container
- ``navbar.section_right``    : right section flex container
- ``item.root``           : NavbarItem outer ``<a>`` / ``<div>``
- ``item.active``         : extra classes layered when the row is active
- ``item.icon``           : icon slot wrapper
- ``item.label``          : label text
- ``item.badge``          : trailing badge
"""

from __future__ import annotations

from typing import Any

NAVBAR_THEME: dict[str, Any] = {
    "slots": {
        # Outer ``<header>`` — full-bleed, surface background, optional
        # border. ``z-30`` sits below the sidebar (z-40) and dialog/drawer
        # (z-50), donc un modal peint au-dessus de la navbar.
        # ⚠️ La raison donnée ici jusqu'au 2026-08-01 — « un sidebar ouvert
        # sur mobile assombrit aussi la navbar via son backdrop » — ne tient
        # plus : la sidebar n'a PLUS de drawer mobile ni de backdrop (retiré
        # du composant le 2026-07-14, le mobile est le ``if
        # Screen().is_mobile`` du dev). L'ordre de z-index reste bon, pour
        # les overlays téléportés.
        "root": (
            "group/navbar w-full bg-surface z-30 "
            "border-b-(length:--bz-stroke) border-text/10"
        ),
        # Inner ``<nav>`` — clamps max-width + horizontal padding for
        # comfortable line length on wide viewports. Mirror of Container
        # but local to navbar so we don't accidentally pick up vertical
        # padding from a future Container theme change.
        "inner": (
            "mx-auto w-full max-w-screen-2xl "
            "px-4 sm:px-6 lg:px-8 "
            "flex flex-row items-center gap-4 h-14"
        ),
        # Per-side section containers. ``mr-auto`` on left + ``ml-auto``
        # on right push them to the edges ; center uses ``mx-auto``.
        # Each section is itself a flex-row so items + components inside
        # align naturally without an extra wrapper.
        "section_left": "flex flex-row items-center gap-2 me-auto",
        "section_center": (
            "flex flex-row items-center gap-2 mx-auto"
        ),
        "section_right": "flex flex-row items-center gap-2 ms-auto",
    },
    # ``sticky=True`` injects fixed positioning so the bar stays at the
    # top during page scroll. Backdrop blur softens content sliding
    # underneath.
    "sticky": "sticky top-0 backdrop-blur-md bg-surface/95",
    # ``variant`` axis kept narrow for v1 — "standard" = the default
    # bordered bar, "floating" = rounded card detached from the viewport
    # edges (Stripe / Linear marketing site idiom).
    "variants": {
        "standard": "",
        "floating": (
            "max-w-screen-2xl mx-auto mt-3 rounded-box "
            "border-(length:--bz-stroke) border-text/10 shadow-sm bg-surface/95 "
            "backdrop-blur-md"
        ),
    },
}


NAVBAR_ITEM_THEME: dict[str, Any] = {
    "slots": {
        # Outer pill — horizontal padding, gap for icon+label, hover bg
        # bump, active bg-color highlight. Same motion idiom as
        # SidebarItem (transition-all + active:scale-[0.97]) so the
        # whole nav family feels consistent.
        "root": (
            "group/row relative inline-flex flex-row items-center gap-2 "
            "px-3 py-1.5 rounded-box cursor-pointer "
            "transition-all duration-200 ease-out "
            "active:scale-[0.97] "
            "whitespace-nowrap "
            "outline-none text-muted text-sm font-medium "
            # ``-surface``, pas ``-background`` : l'écart de l'anneau est
            # PEINT, donc il doit valoir le fond sur lequel l'entrée repose —
            # et le ``<header>`` de la navbar est ``bg-surface``. Avec
            # ``-background`` (plus sombre de deux crans) chaque entrée
            # focalisée s'entourait d'un liseré noir. Même faute que la
            # sidebar, corrigée le même jour ; gatée par
            # ``test_ring_offset_matches_its_surface``. La navbar n'a AUCUN
            # ``overflow``, donc contrairement à la sidebar elle n'avait pas
            # besoin qu'on fasse de la place à l'anneau.
            "focus-visible:ring-2 focus-visible:ring-(--bz-focus) "
            "focus-visible:ring-offset-2 "
            "focus-visible:ring-offset-surface "
            "data-[active=false]:hover:bg-text/10 "
            "data-[active=false]:hover:text-text "
            # Le survol et la pression sont neutralisés EXPLICITEMENT
            # sur un item verrouillé : l'inertie vient du socle
            # (``$bz._inert``, dérivé d'``aria-disabled``), pas d'un
            # ``pointer-events-none`` — qui aurait annulé le curseur.
            "aria-disabled:active:scale-100 "
            "aria-disabled:data-[active=false]:hover:bg-transparent "
            "aria-disabled:data-[active=false]:hover:text-muted "
            "aria-disabled:opacity-50 aria-disabled:cursor-not-allowed"
        ),
        # ⚠️ ``data-[active=true]:`` sur le ``text-`` n'est PAS cosmétique.
        # Le ``text-muted`` du root et un ``text-(--bz-text)`` NU sont deux
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
            "bg-(--bz-bg) data-[active=true]:text-(--bz-text) "
            "data-[active=true]:hover:bg-(--bz-bg-hover)"
        ),
        "icon": (
            "shrink-0 inline-flex items-center justify-center "
            "w-4 h-4 text-current"
        ),
        "label": "truncate",
        "badge": (
            "shrink-0 inline-flex items-center justify-center "
            "ml-1 text-xs"
        ),
    },
}
