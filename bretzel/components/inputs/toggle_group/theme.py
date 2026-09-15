"""Default themes for :class:`ToggleGroup` and :class:`ToggleButton`.

One visual contract — a joined-button bar. Items share their edges
(border-radius only on the first / last), the selected state is a
background fill in ``color``. Natural shape for filters, formatting
toolbars, multi-select pills.

The selected state is driven by ``data-selected="true"`` (Tailwind's
``data-[selected=true]:`` variant) rather than ``aria-pressed:``.
Both attributes ARE emitted by the component (a11y stays correct),
but the visual cue rides on ``data-selected`` because that's the
proven path used by :class:`Tabs` ; we know it composes cleanly with
the Tailwind v4 browser CDN compiler. ``aria-pressed:`` Tailwind
variant works in theory, but binding the visual to ``data-*``
removes any ambiguity.

Vocabulary :
- ``root`` : the container ``<div role="group">``
- ``item`` : the per-button shell (centered button)
"""

from __future__ import annotations

from typing import Any

TOGGLE_GROUP_THEME: dict[str, Any] = {
    "slots": {
        # ``w-fit h-fit`` : forces intrinsic sizing on both axes so the
        # root doesn't get stretched by a parent flex/grid with
        # ``align-items: stretch`` (the default). Without this, the
        # cluster claims the full cross-axis width of its container ;
        # any tooltip / popover that anchors on the cluster centers on
        # the STRETCHED width, not on the actual button row, and the
        # panel floats off to the side. Same fix Popover + Dropdown
        # carry — cf. traps.md § "Root inline-flex étirée par un
        # parent flex/grid items-stretch".
        #
        # Tight border-radius family from the form input design — same
        # scale as Input / Select / Combobox so a toggle group sits
        # naturally in a form row.
        # ⚠️ Pas de ``h-fit`` ici, et la hauteur de palier vit sur CETTE
        # boîte (``sizes[…]["root"]``), pas sur l'item. La bordure du
        # cadre est posée sur la root : un ``h-10`` sur l'item rendait
        # 42 px de cluster contre 40 px pour le select posé à côté dans
        # la même grille — mesuré à toutes les tailles, +2 px partout.
        # Cf. traps.md § "La hauteur d'un palier vit sur l'élément bordé".
        "root": (
            "inline-flex items-stretch w-fit select-none "
            "transition-colors duration-150 "
            "rounded-field bg-interface border-(length:--bz-stroke) border-text/10 "
            "overflow-hidden p-0 gap-0"
        ),
        # Item shell : flex centred, border-r for the inter-item
        # separator, removed on the last child via :last-child. Three
        # states for the text colour, matching the Tabs ``line`` idiom
        # — hover gives a colour preview of what selection looks like :
        # - base   : ``text-muted``
        # - hover  : ``text-(--bz-text)`` (preview, no bg yet)
        # - active : ``bg-(--bz-bg) text-(--bz-text)`` (full)
        "item": (
            "inline-flex items-center justify-center gap-1.5 "
            "font-medium text-muted cursor-pointer "
            "border-r-(length:--bz-stroke) border-text/10 last:border-r-0 "
            "transition-colors duration-150 ease-out "
            "not-disabled:hover:text-(--bz-text) "
            "data-[selected=true]:bg-(--bz-bg) "
            "data-[selected=true]:text-(--bz-text) "
            "focus-visible:outline-none focus-visible:ring-2 "
            "focus-visible:ring-(--bz-focus) "
            "focus-visible:ring-inset "
            "disabled:opacity-50 disabled:cursor-not-allowed"
        ),
    },
    # Sizes scale the root height and the item padding. Clés ``root`` et
    # ``item`` par taille — lues à la main dans ``ToggleGroup.render()``
    # (composant multi-slot, il compose lui-même ses classes).
    #
    # La hauteur est sur ``root`` (l'élément qui porte la bordure) et
    # l'item la remplit en ``h-full`` : c'est ce qui aligne le cluster
    # sur un select / input / bouton de la même taille au pixel près.
    "sizes": {
        "xs": {"root": "h-7", "item": "h-full px-2 text-xs"},
        "sm": {"root": "h-8", "item": "h-full px-3 text-sm"},
        "md": {"root": "h-10", "item": "h-full px-4 text-sm"},
        "lg": {"root": "h-12", "item": "h-full px-5 text-base"},
        # ``xl`` manquait : un ``size="xl"`` retombait en silence sur
        # ``md``, une palier plus petit qu'un select/combobox ``xl``
        # posé à côté dans le même formulaire (audit F91). Le palier
        # calque celui de Select (``h-14 px-5 text-lg``) pour que la
        # famille reste alignée.
        "xl": {"root": "h-14", "item": "h-full px-5 text-lg"},
    },
}
