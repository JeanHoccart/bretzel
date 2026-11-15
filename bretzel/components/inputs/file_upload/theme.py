"""Default :class:`FileUpload` theme — the dropzone, over the list.

A ``file_upload`` is ``ui.attachments`` plus a dropzone, so its theme is
the list's (``attachments/theme.py``: the three presentations, the
refusal panel, the × sizes) with the zone's slots and sizes added. An
app override of ``"file_upload"`` therefore reaches its list too;
one of ``"attachments"`` reaches only ``ui.attachments``.

Key UX choices :

- The dropzone auto-shrinks when ``files.length > 0`` — the empty
  state collapses to a compact "Drop more files" hint. Mirror of
  Linear / Notion patterns.
- A global ``dragenter`` listener on ``window`` highlights every
  dropzone on the page when the user drags a file from the OS — the
  dropzone glows so the drop target is obvious from any scroll position.
"""

from __future__ import annotations

from typing import Any

from bretzel.components.inputs.attachments.theme import ATTACHMENTS_THEME

_DROPZONE_SLOTS: dict[str, str] = {
    # The dropzone is a SURFACE, it fills its row; the list under it
    # takes the root's width.
    "root": (
        "bz-file-upload flex flex-col gap-3 min-w-0 w-full"
    ),
    # The big dashed area. Padding + content scale via the ``sizes`` map
    # below ; this slot only owns the colour / focus / interactive parts.
    #
    # Neutral at REST, like an Input : a dashed ``border-text/15`` over
    # ``bg-interface``, no colour tint until the user engages. The
    # coloured accent lives ONLY in the interactive states — hover
    # (border + faint fill), focus ring, and the drag highlights
    # (``dropzone_active`` / ``dropzone_global_drag``).
    "dropzone_wrapper": (
        "group relative flex flex-col items-center justify-center "
        "w-full rounded-box border-(length:--bz-stroke-strong) border-dashed "
        "border-line bg-interface cursor-pointer "
        "transition duration-200 "
        # Switched off, the hover tints nothing (the input inside says it,
        # bound or not): only the not-allowed cursor answers.
        "[&:hover:not(:has(:disabled))]:border-(--bz-border-hover) "
        "[&:hover:not(:has(:disabled))]:bg-(--bz-bg) "
        "has-[:disabled]:opacity-50 has-[:disabled]:cursor-not-allowed "
        "outline-none focus-visible:border-(--bz-solid) "
        "focus-visible:ring-2 focus-visible:ring-offset-2 "
        "focus-visible:ring-offset-background "
        "focus-visible:ring-(--bz-focus)"
    ),
    # Added when the user is dragging files OVER this dropzone (vs the
    # global highlight, which signals a drag on the page).
    "dropzone_active": (
        "border-(--bz-solid) bg-(--bz-bg) scale-[0.99]"
    ),
    # Added when a file is being dragged anywhere on the page: every
    # dropzone surfaces itself.
    "dropzone_global_drag": (
        "border-(--bz-border-hover) bg-(--bz-bg) "
        "ring-2 ring-(--bz-focus-soft) ring-offset-2 "
        "ring-offset-background"
    ),
    "dropzone_empty_state": (
        "flex flex-col items-center justify-center pointer-events-none"
    ),
    # Neutral ``text-muted`` at rest ; lights up in the colour on hover.
    "dropzone_icon": (
        "inline-flex shrink-0 text-muted transition duration-150 "
        "group-[:hover:not(:has(:disabled))]:text-(--bz-text) "
        "group-[:hover:not(:has(:disabled))]:-translate-y-0.5"
    ),
    "dropzone_title": (
        "font-semibold text-text text-center"
    ),
    "dropzone_subtitle": (
        "text-muted text-center"
    ),
}

# ⚠️ **The dropzone padding is split by AXIS, and that is not a style
# choice.** The vertical axis cannot live in BOTH layers (``py-8`` as a
# static ``class=``, ``py-3`` added in ``bz-class`` when files are
# there): both utilities have the SAME specificity — the Tailwind sheet's
# order decides, not the order of addition. Hence three entries:
# ``dropzone_padding_x`` stays static; the vertical one is carried
# EXCLUSIVELY by the dynamic layer, which emits the full ternary —
# ``dropzone_padding_y`` for the EMPTY state, ``dropzone_padding_with_files``
# for the WITH-FILES state. Do NOT put a ``py-*`` in the static padding.
_DROPZONE_SIZES: dict[str, dict[str, str]] = {
    "xs": {
        "dropzone_padding_x": "px-3",
        "dropzone_padding_y": "py-3",
        "dropzone_padding_with_files": "py-2",
        "dropzone_icon_size": "text-lg",
        "dropzone_icon_size_with_files": "text-sm",
        "dropzone_icon_margin": "mb-1",
        "dropzone_title": "text-xs",
        "dropzone_subtitle": "text-xs mt-0.5",
    },
    "sm": {
        "dropzone_padding_x": "px-4",
        "dropzone_padding_y": "py-5",
        "dropzone_padding_with_files": "py-2.5",
        "dropzone_icon_size": "text-xl",
        "dropzone_icon_size_with_files": "text-base",
        "dropzone_icon_margin": "mb-2",
        "dropzone_title": "text-sm",
        "dropzone_subtitle": "text-xs mt-1",
    },
    "md": {
        "dropzone_padding_x": "px-6",
        "dropzone_padding_y": "py-8",
        "dropzone_padding_with_files": "py-3",
        "dropzone_icon_size": "text-3xl",
        "dropzone_icon_size_with_files": "text-xl",
        "dropzone_icon_margin": "mb-3",
        "dropzone_title": "text-sm",
        "dropzone_subtitle": "text-xs mt-1",
    },
    "lg": {
        "dropzone_padding_x": "px-8",
        "dropzone_padding_y": "py-12",
        "dropzone_padding_with_files": "py-4",
        "dropzone_icon_size": "text-4xl",
        "dropzone_icon_size_with_files": "text-2xl",
        "dropzone_icon_margin": "mb-3",
        "dropzone_title": "text-base",
        "dropzone_subtitle": "text-sm mt-1",
    },
    "xl": {
        "dropzone_padding_x": "px-10",
        "dropzone_padding_y": "py-16",
        "dropzone_padding_with_files": "py-5",
        "dropzone_icon_size": "text-5xl",
        "dropzone_icon_size_with_files": "text-3xl",
        "dropzone_icon_margin": "mb-4",
        "dropzone_title": "text-lg",
        "dropzone_subtitle": "text-base mt-1.5",
    },
}

FILE_UPLOAD_THEME: dict[str, Any] = {
    "slots": {**ATTACHMENTS_THEME["slots"], **_DROPZONE_SLOTS},
    "sizes": {
        step: {**ATTACHMENTS_THEME["sizes"][step], **_DROPZONE_SIZES[step]}
        for step in _DROPZONE_SIZES
    },
}
