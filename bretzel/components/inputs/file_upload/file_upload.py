"""``FileUpload`` — a dropzone, and the list of files under it.

It is :class:`~bretzel.components.inputs.attachments.Attachments` plus a
dropzone: the same list (``display="strip" | "chips" | "grid"``), the
same checks, the same paste, the same ``.pick()`` / ``.clear()``, the same
server ``on_change`` that carries the files — and a large dashed area
above it: drop OR click anywhere on the zone OR press Enter / Space when
focused. Modern Drive / Notion / Linear shape.

A compact button that imports is not a ``file_upload``: it is the list
and a button ::

    pieces = ui.attachments(name="pieces", multiple=True)
    ui.button("Importer", icon_left="upload", on_click=pieces.pick())

The list shows under the zone (``display="strip"`` by default, the tiles
that scroll). It is the BROWSER that owns it — the client creates a row
when a file is dropped, by cloning a ``<template bz-for>``, so neither
children nor a ``render=`` callback could reach it: ``display=`` offers
three shipped presentations instead (``COLLECTION_OWNER = "client"``).

Two upload modes :

- **Form mode** (default) — files just accumulate in the hidden
  ``<input type="file">``. Submit the surrounding ``<form>`` and the
  browser sends each file as multipart.
- **Async mode** (set ``upload_url=``) — each accepted file is POSTed
  immediately via XHR. Per-file progress bar renders below the
  thumbnail ; ``upload_complete`` fires server-side per file.

Events: those of the list (``change``, ``upload_start`` /
``upload_complete`` / ``upload_error``, ``remove``), and ``focus`` /
``blur`` relayed from the focusable zone. ``upload_progress`` exists as a
DOM event but is never bridged to the server — it would melt the wire.

Runtime notes :

- Window-level drag highlight has no per-element equivalent — the window
  subscriptions are registered once at ``bz-init`` via
  ``$bz.helpers.onWindow`` (page-scoped, unsubscribe dropped).
- Reactive class uses ``bz-class`` (MERGE onto static ``class=``), never
  ``bz-attr:class`` (which REPLACES).
- ``on_focus`` / ``on_blur`` relocate onto the focusable zone — **in both
  shapes** (string AND callable): ``focus``/``blur`` do not bubble, so an
  ``hx-trigger`` set on the root would never fire.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterable
from typing import Any, ClassVar

from bretzel.components.base import reject_component, stamp_display_none
from bretzel.components.base.field_wiring import (
    activate_keydown,
    keep_own_name,
    relocate_aria,
    relocate_handlers,
)
from bretzel.components.base.focus import FocusCommands
from bretzel.components.inputs.attachments import Attachments
from bretzel.components.inputs.file_upload.theme import FILE_UPLOAD_THEME
from bretzel.core.tree import Element, Node
from bretzel.core.tree import TextNode as _TextNode
from bretzel.render import template, text

# Enter / Space open the picker. The guard (three key names + the target)
# lives in ``base/field_wiring.activate_keydown``.
_ACTIVATE_KEYDOWN = activate_keydown("pick();")


class FileUpload(FocusCommands, Attachments):
    """A dropzone, and the list of the files dropped on it."""

    THEME: ClassVar[dict[str, Any]] = FILE_UPLOAD_THEME
    THEME_KEY: ClassVar[str] = "file_upload"
    EVENTS: ClassVar[tuple[str, ...]] = (*Attachments.EVENTS, "focus", "blur")
    IMPERATIVE: ClassVar[tuple[str, ...]] = (*Attachments.IMPERATIVE, "focus", "blur")
    # Where ``autofocus=`` / ``.focus()`` land: the focusable drop zone, not the hidden file input.
    FOCUS_TARGET: ClassVar[tuple[str, ...] | None] = ("[role=button][tabindex]",)
    #: Retired names, refused with the new one (``attrs.split_kwargs``).
    RENAMED_PROPS: ClassVar[dict[str, str]] = {
        "list": "write ``display=``: \"strip\" (the tiles), \"chips\" or \"grid\".",
    }
    #: A name this component deliberately does not take.
    REFUSED_PROPS: ClassVar[dict[str, str]] = {
        "variant": (
            "a file_upload is a dropzone. A compact button that joins files is "
            "a list and a button: ``pieces = ui.attachments(…)`` then "
            "``ui.button(\"Joindre\", icon_left=\"paperclip\", "
            "on_click=pieces.pick())``."
        ),
    }

    def __init__(
        self,
        label: str | None = None,
        *,
        display: str = "strip",
        files: Iterable[Any] | None = None,
        multiple: bool | None = None,
        accept: str | list[str] | None = None,
        max_size_mb: float | None = None,
        max_files: int | None = None,
        disabled: bool | None = None,
        required: bool | None = None,
        color: str | None = None,
        size: str | None = None,
        upload_url: str | None = None,
        show_previews: bool = True,
        paste: bool = False,
        drop: str | None = None,
        name: str | None = None,
        on_change: Callable[..., Any] | str | None = None,
        on_upload_start: Callable[..., Any] | str | None = None,
        on_upload_complete: Callable[..., Any] | str | None = None,
        on_upload_error: Callable[..., Any] | str | None = None,
        on_remove: Callable[..., Any] | str | None = None,
        on_focus: Callable[..., Any] | str | None = None,
        on_blur: Callable[..., Any] | str | None = None,
        **kwargs: Any,
    ) -> None:
        reject_component(
            label,
            owner="FileUpload",
            prop="label",
            because=(
                "the label ALSO serves as ``aria-label`` on the dropzone, and "
                "an HTML attribute can only carry a string (the Component was "
                "serialised there as its Python repr, and announced as such "
                "to the screen reader)."
            ),
            instead="For rich content, compose around the FileUpload.",
        )
        self._label = label
        super().__init__(
            display=display, files=files, multiple=multiple, accept=accept,
            max_size_mb=max_size_mb, max_files=max_files, disabled=disabled,
            required=required, color=color, size=size, upload_url=upload_url,
            show_previews=show_previews, paste=paste, drop=drop, name=name,
            on_change=on_change, on_upload_start=on_upload_start,
            on_upload_complete=on_upload_complete, on_upload_error=on_upload_error,
            on_remove=on_remove, on_focus=on_focus, on_blur=on_blur, **kwargs,
        )

    def _hides_when_empty(self) -> bool:
        """The dropzone is always there: the root never hides."""
        return False

    # ── The dropzone ─────────────────────────────────────────────────

    def _trigger(self, root_attrs: dict[str, Any], native_input: Element) -> Node:
        s = self.compose_class
        size_row = self._size_row() or {}

        def sz(key: str) -> str:
            return size_row.get(key, "")

        # ``focus`` / ``blur`` relocate onto the focusable zone (the only
        # element that fires them) — IN BOTH SHAPES. The field's label
        # comes first, the action the zone names next.
        relocated: dict[str, Any] = {}
        relocate_handlers(root_attrs, {"focus": relocated, "blur": relocated})
        relocate_aria(root_attrs, relocated, takes_required=False)
        keep_own_name(relocated, f"{self.id}_trigger")

        label = self._label or text("file_upload.dropzone")
        accept = self._reactive_values.get("accept")
        multiple = bool(self._reactive_values.get("multiple") or False)
        disabled = bool(self._reactive_values.get("disabled") or False)

        # Two empty states share the same DOM space, swapped via
        # ``bz-show`` based on files.length : the FULL one (icon + label +
        # hint lines) when no files are picked yet; the COMPACT one (small
        # icon + "Drop more files") when files are present, so the zone
        # does not steal vertical room from the list.
        full_children: list[Node] = [
            Element(tag="iconify-icon", attrs={
                "icon": "lucide:cloud-upload",
                "class": " ".join(filter(None, [
                    s("dropzone_icon"), sz("dropzone_icon_size"), sz("dropzone_icon_margin"),
                ])),
            }, children=()),
            Element(tag="span", attrs={"class": s("dropzone_title")},
                    children=(_TextNode(label),)),
        ]
        if accept:
            full_children.append(Element(tag="span", attrs={"class": s("dropzone_subtitle")},
                                         children=(_TextNode(text("file_upload.accepted",
                                                                  types=accept)),)))
        if self._max_size_mb is not None:
            # The size is written by the browser, in the page's language
            # (« 1,5 Mo »); the server's « 1.5 MB » is the fallback.
            ceiling = int(self._max_size_mb * 1024 * 1024)
            full_children.append(Element(tag="span", attrs={
                "class": s("dropzone_subtitle"),
                "bz-text": (f"{json.dumps(template('file_upload.max_size'))}"
                            f".replace('{{size}}', $bz.attachments.formatSize({ceiling}))"),
            }, children=(_TextNode(text("file_upload.max_size",
                                        size=f"{self._max_size_mb} MB")),)))
        if multiple:
            # Two WHOLE sentences rather than a re-glued suffix: a
            # translation does not necessarily put the ceiling at the end.
            hint = (text("file_upload.multiple_capped", max=self._max_files)
                    if self._max_files is not None else text("file_upload.multiple"))
            full_children.append(Element(tag="span", attrs={"class": s("dropzone_subtitle")},
                                         children=(_TextNode(hint),)))
        full_empty_state = Element(tag="div", attrs={
            "class": s("dropzone_empty_state"), "bz-show": "files.length === 0",
        }, children=tuple(full_children))

        compact_attrs: dict[str, Any] = {
            "class": self.slot_class("dropzone_empty_state", "flex-row gap-2"),
            "bz-show": "files.length > 0",
        }
        stamp_display_none(compact_attrs)
        compact_empty_state = Element(tag="div", attrs=compact_attrs, children=(
            Element(tag="iconify-icon", attrs={
                "icon": "lucide:cloud-upload",
                "class": " ".join(filter(None, [
                    s("dropzone_icon"), sz("dropzone_icon_size_with_files"),
                ])),
            }, children=()),
            Element(tag="span", attrs={"class": s("dropzone_subtitle")}, children=(
                _TextNode(text("file_upload.drop_more" if multiple
                               else "file_upload.drop_replace")),)),
        ))

        # ⚠️ The padding is split by AXIS (cf. the theme): the horizontal
        # one is static, the vertical one is EXCLUSIVELY in the
        # ``bz-class`` — same specificity, the Tailwind sheet decides, and
        # a static ``py-8`` would beat the compact ``py-3`` for ever.
        # ``bz-class`` MERGES onto the static ``class=``.
        pad_compact = sz("dropzone_padding_with_files")
        pad_empty = sz("dropzone_padding_y")
        active_cls = s("dropzone_active")
        global_drag_cls = s("dropzone_global_drag")
        wrapper_attrs: dict[str, Any] = {
            "class": f"{s('dropzone_wrapper')} {sz('dropzone_padding_x')}",
            "bz-class": (
                "["
                f"files.length > 0 ? '{pad_compact}' : '{pad_empty}', "
                f"isDragging ? '{active_cls}' : '', "
                f"(isGlobalDragActive && !isDragging) ? '{global_drag_cls}' : ''"
                "]"
            ),
            "bz-on:click": "pick()",
            # ``.prevent`` inlined (``bz-on`` has no modifier grammar).
            "bz-on:dragenter": "$event.preventDefault(); onDragEnter($event)",
            "bz-on:dragover": "$event.preventDefault(); onDragOver($event)",
            "bz-on:dragleave": "$event.preventDefault(); onDragLeave($event)",
            "bz-on:drop": "$event.preventDefault(); onDrop($event)",
            # Window-level drag detection: every zone of the page lights up
            # while a file from the OS is dragged anywhere on it.
            "bz-init": (
                "$bz.helpers.onWindow('dragenter', e => onWindowDragEnter(e)); "
                "$bz.helpers.onWindow('dragleave', e => onWindowDragLeave(e)); "
                "$bz.helpers.onWindow('drop', () => onWindowDrop()); "
                "$bz.helpers.onWindow('dragend', () => onWindowDrop())"
            ),
            "tabindex": "0" if not disabled else "-1",
            "bz-on:keydown": _ACTIVATE_KEYDOWN,
            "role": "button",
            "aria-label": label,
            **relocated,
        }
        if disabled:
            wrapper_attrs["aria-disabled"] = "true"
        return Element(tag="div", attrs=wrapper_attrs,
                       children=(native_input, full_empty_state, compact_empty_state))
