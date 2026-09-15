"""Default :class:`DateRangePicker` theme.

Same layout idea as :data:`DATE_PICKER_THEME` — one focus-within
frame around the two editable inputs, the separator, and the single
shared calendar icon button.
"""

from __future__ import annotations

from typing import Any

DATE_RANGE_PICKER_THEME: dict[str, Any] = {
    "slots": {
        # ``w-full`` (not ``w-fit``) : fills its parent like every other form
        # input, so it aligns with siblings in a grid / form_field and doesn't
        # grow past a constrained cell (same fix as date_picker). Paired with
        # the ``flex-1 min-w-0`` inputs below, the whole field shrinks to fit
        # any cell instead of overflowing.
        "root": (
            "bz-date-range-picker relative flex flex-col w-full"
        ),
        # The unified field — both inputs + separator + buttons sit
        # under one ring.
        "input_frame": (
            "flex items-stretch w-full rounded-field border-(length:--bz-stroke) border-text/10 "
            "bg-interface text-text transition-all duration-200 "
            "focus-within:border-(--bz-solid) focus-within:ring-2 "
            "focus-within:ring-(--bz-focus-soft) focus-within:ring-offset-2 "
            "focus-within:ring-offset-background "
            "has-[input:disabled]:opacity-50 "
            "has-[input:disabled]:cursor-not-allowed"
        ),
        # Each editable date input — ``flex-1 min-w-0`` (NOT a fixed
        # ``w-[8.5rem]``) so the two fields SHARE the frame and shrink with
        # it, same as date_picker's input. A fixed width gave the frame a
        # ~2×8.5rem + separator + button min-content floor : in a cell
        # narrower than that the content overflowed the frame internally
        # (clipped / scrolled) even after the root was capped to the cell.
        # ``h-*`` / ``text-*`` moved to sizes map below so ``size=`` propagates.
        "input_field": (
            "flex-1 min-w-0 px-3 bg-transparent text-text tabular-nums "
            "placeholder:text-muted/60 outline-none "
            "disabled:cursor-not-allowed"
        ),
        # Tight padding-only on the start field so the separator sits
        # snug.
        "input_field_start": (
            "rounded-l-field"
        ),
        # Separator chip between the two inputs.
        "separator": (
            "inline-flex items-center text-text/50 px-1 "
            "select-none"
        ),
        "clear_button": (
            "shrink-0 inline-flex items-center justify-center "
            "text-muted/60 not-disabled:hover:text-text outline-none "
            "transition-colors disabled:opacity-50 "
            "disabled:cursor-not-allowed"
        ),
        "trigger_button": (
            "shrink-0 inline-flex items-center justify-center "
            "text-(--bz-text) not-disabled:hover:bg-(--bz-bg) rounded-r-field "
            "outline-none focus-visible:ring-2 focus-visible:ring-inset "
            "focus-visible:ring-(--bz-focus) transition-colors "
            "disabled:opacity-50 disabled:cursor-not-allowed"
        ),
        "button_icon": (
            "inline-flex shrink-0 text-current"
        ),
        # Positioned by ``$bz.helpers.floating`` (fixed + inline top/left,
        # flip / clamp) — no static ``top-full left-0`` (those fight the inline
        # coords under fixed ; cf. traps.md § "panel left-0 right-0 under
        # floating"). Same as date_picker / Select / Combobox.
        "panel": (
            "absolute z-40 mt-1 "
            "rounded-box border-(length:--bz-stroke) border-text/10 bg-interface shadow-lg "
            # Le fondu entrant, cadence des CHAMPS (75 ms, moitié de
            # celle des menus). Mécanisme des trois classes : un seul
            # exemplaire, dans ``overlay/dropdown/theme.py``.
            "transition-[opacity,display] transition-discrete duration-75 "
            "starting:opacity-0"
        ),
    },
    # ── Size paliers ─────────────────────────────────────────────
    # La hauteur vit sur ``input_frame``, PAS sur ``input_field`` — et
    # c'est load-bearing. Le cadre porte la bordure ; en ``box-sizing:
    # border-box`` (le préréglage Tailwind), un ``h-10`` posé sur le
    # cadre vaut 40 px bordure comprise, exactement comme ``ui.input``,
    # qui pose sa hauteur et sa bordure sur le MÊME élément. Posée sur
    # l'enfant, elle donnait 40 px + les 2 px du cadre : **42 px**, soit
    # 2 px de plus que tout autre contrôle, à chacun des cinq paliers.
    # Mesuré en Chromium le 2026-08-23, gardé par
    # ``tests/runtime_js/test_form_controls_share_one_height.py``.
    #
    # Les enfants n'ont donc plus de ``h-*`` : le cadre est
    # ``items-stretch``, ils remplissent sa hauteur intérieure. Leur en
    # redonner un les ferait dépasser du cadre.
    "sizes": {
        "input_frame": {
            "xs": "h-7",
            "sm": "h-8",
            "md": "h-10",
            "lg": "h-12",
            "xl": "h-14",
        },
        "input_field": {
            "xs": "text-xs",
            "sm": "text-xs",
            "md": "text-sm",
            "lg": "text-base",
            "xl": "text-lg",
        },
        "separator": {
            "xs": "text-xs",
            "sm": "text-xs",
            "md": "text-sm",
            "lg": "text-base",
            "xl": "text-lg",
        },
        "clear_button": {
            "xs": "w-6",
            "sm": "w-7",
            "md": "w-8",
            "lg": "w-9",
            "xl": "w-10",
        },
        "trigger_button": {
            "xs": "w-7",
            "sm": "w-8",
            "md": "w-10",
            "lg": "w-12",
            "xl": "w-14",
        },
        "button_icon": {
            "xs": "text-xs",
            "sm": "text-sm",
            "md": "text-base",
            "lg": "text-lg",
            "xl": "text-xl",
        },
    },
}
