"""``Attachments`` — the files joined to something, shown where one wants.

The list of files and what makes it live: the hidden ``<input
type=file>``, its checks, its refusals, the paste of a screenshot, the
drop of files, the emptying after a send. Any button adds to it, by a
command — as ``dialog.open()`` opens a dialog ::

    pieces = ui.attachments(name="pieces", multiple=True, max_size_mb=25,
                            paste=True, drop="form")
    ui.icon_button("paperclip", variant="ghost", on_click=pieces.pick())

There is no button component of its own: a button that joins a file is a
``ui.button``, a ``ui.icon_button`` or a ``ui.dropdown_item`` with
``on_click=pieces.pick()``. The button may sit anywhere in the page; the
list is linked to it by the instance, not by a name.

**It takes no room while it is empty** — neither a file picked nor a
refusal to show: a row of buttons under it never moves.

Two kinds of files, one look:

- **picked in the browser** — by ``.pick()``, a paste (``paste=True``) or
  a drop (``drop=``). They leave with the ``<form>`` around the list (its
  input is the form's field, under ``name=``), or at once with a server
  ``on_change`` (below), or one by one with ``upload_url=``;
- **held by the server** — ``files=[{"name": …, "size": …, "type": …,
  "href": …}]``: the attachments of a mail received, of a draft
  reopened. Rendered by the server, with no form needed: a list may only
  show. ``href`` makes the name a link; ``on_remove=`` puts a × on each,
  which calls the handler with the file's ``key`` (its name when it has
  none).

``display=`` — three shipped presentations, not an escape hatch (the
browser creates the rows: ``COLLECTION_OWNER = "client"``):

- ``"chips"`` (default) — one chip per file: icon, name, inline ×,
  wrapping over several lines;
- ``"strip"`` — one tile per file (thumbnail, name, size, corner ×) on a
  single row that scrolls;
- ``"grid"`` — large tiles that wrap.

``drop=`` — where files can be dropped: ``"form"`` (the whole enclosing
form, the box a message is written in), ``"self"`` (the list), or
``None`` (default). ``paste=True`` — a Ctrl+V anywhere in the enclosing
form joins the files the clipboard carries; a paste that carries TEXT is
left to the field, and a screenshot, which the browser always names
``image.png``, is renamed ``pasted-<date>-<hour>.png``. One ``paste=True``
list per form: two would both take the files.

**A server ``on_change`` carries the files.** The handler takes them
under ``name=`` (``def joined(pieces)``: one ``UploadFile``, or a list)
— outside a form too. Outside a form the list then lets them go: the app
keeps them and shows them back through ``files=`` (the Gmail way: a
piece leaves as soon as it is chosen). Inside a form they stay, and
leave with it. The server holds them to ``accept`` / ``max_size_mb`` /
``max_files`` either way (the limits are signed into the page).

Commands: ``.pick()`` opens the system's picker — the browser opens it
only within a click, so the command goes on an ``on_click``;
``.clear()`` empties what was picked.

Events (the slab dispatches kebab-case DOM events on the root):
``change`` (files added or removed), ``upload_start`` /
``upload_complete`` / ``upload_error`` (``upload_url=`` mode), ``remove``
(the × of a file the server holds).

A test chooses a file with Playwright's ``set_input_files`` on
``[data-bz-attachments-input]``, from a path or from bytes.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterable, Mapping
from typing import Any, ClassVar

from bretzel.components.base import (
    Component,
    ComponentUsageError,
    reactive_prop,
    reject_component,
    stamp_display_none,
)
from bretzel.components.base.dismiss import dismiss_button
from bretzel.components.base.events import item_action_attrs, posts_its_files
from bretzel.components.base.field_wiring import relocate_handlers, trigger_event
from bretzel.components.inputs.attachments.theme import ATTACHMENTS_THEME
from bretzel.core.tree import Element, Node
from bretzel.core.tree import TextNode as _TextNode
from bretzel.render import template, text
from bretzel.render.context import maybe_current_context

# Python event names use underscores ; the slab dispatches kebab-case
# DOM events. ``change`` is already kebab-safe ; only the ``upload_*``
# family needs renaming (both the ``bz-on:`` string form and the
# server-callable ``hx-trigger`` value).
_KEBAB_EVENTS = {
    "upload_start": "upload-start",
    "upload_complete": "upload-complete",
    "upload_error": "upload-error",
}

#: The presentations of the list — ``display=``. It is NOT a style axis:
#: the chip and the tile differ in the DOM (the chip emits neither
#: thumbnail nor size, and its × is in the flow). The grid is the tile,
#: larger, on wrapping lines.
DISPLAYS: tuple[str, ...] = ("chips", "strip", "grid")

#: Where files can be dropped — ``drop=`` (or ``None``).
DROP_HOSTS: tuple[str, ...] = ("form", "self")

#: The slots a presentation substitutes for the strip's. A finite and
#: literal table on BOTH sides — never an assembled name: a Tailwind class
#: nothing writes out in full does not reach the compiled CSS. Here it is
#: the SLOT NAME that is chosen; both sets of classes are written out in
#: full in the theme.
_DISPLAY_SLOTS: dict[str, dict[str, str]] = {
    "strip": {},
    "grid": {
        "file_list": "grid_list",
        "file_item": "grid_item",
        "file_thumb": "grid_thumb",
        "file_icon": "grid_icon",
    },
    "chips": {
        "file_list": "chip_list",
        "file_item": "chip_item",
        "file_icon": "chip_icon",
        "file_name": "chip_name",
        "file_status_done": "chip_status_done",
        "file_status_error": "chip_status_error",
        "file_progress_bar": "chip_progress_bar",
        "remove_btn": "chip_remove_btn",
    },
}

#: The texts ``attachments.js`` shows when it refuses a file.
_RUNTIME_TEXTS = ("too_large", "wrong_format", "skipped", "reason_too_large",
                  "reason_wrong_format", "reason_size_or_format", "only_one",
                  "max_reached", "over_limit", "network_error")

def size_label(size: int) -> str:
    """A size as the server writes it before the browser localises it
    (``$bz.attachments.formatSize``): the same three units, in English."""
    if size >= 1048576:
        return f"{size / 1048576:.1f} MB"
    if size >= 1024:
        return f"{round(size / 1024)} kB"
    return f"{size} B"


def server_files(files: Iterable[Any] | None) -> tuple[dict[str, Any], ...]:
    """``files=`` read into one shape: ``name``, ``size``, ``type``,
    ``href``, ``key`` (the name when absent). A bare string is a name."""
    found: list[dict[str, Any]] = []
    for one in files or ():
        if isinstance(one, str):
            one = {"name": one}
        if not isinstance(one, Mapping) or not one.get("name"):
            raise ComponentUsageError(
                "ui.attachments(files=…) takes the files the server holds, each a "
                "name or a dict with at least a name: "
                "``files=[{\"name\": \"devis.pdf\", \"size\": 48213, "
                f"\"type\": \"application/pdf\", \"href\": \"/pj/12\"}}]`` — got {one!r}."
            )
        size = one.get("size")
        found.append({
            "name": str(one["name"]),
            "size": int(size) if size is not None else None,
            "type": str(one.get("type") or ""),
            "href": str(one["href"]) if one.get("href") else None,
            "key": str(one.get("key") or one["name"]),
        })
    return tuple(found)


class Attachments(Component):
    """The list of files joined to something; any button adds to it with ``.pick()``."""

    THEME: ClassVar[dict[str, Any]] = ATTACHMENTS_THEME
    THEME_KEY: ClassVar[str] = "attachments"
    IS_CONTAINER: ClassVar[bool] = False
    #: It is the BROWSER that owns the list of picked files: a row is
    #: created when a file is picked, by cloning a ``<template bz-for>``.
    #: Neither Python children nor a ``render=`` callback reach it — they
    #: would run at server render, when the list is empty. The mechanism
    #: the author gets instead is ``display=``: three SHIPPED
    #: presentations. Cf. ``Component.COLLECTION_OWNER``.
    COLLECTION_OWNER: ClassVar[str | None] = "client"
    # ``value`` is never bindable: browsers forbid programmatic
    # ``input.files`` assignment outside a DataTransfer, and a FileList is
    # not serialisable for server-side state. Only ``disabled`` earns a
    # client binding (flips live from client state).
    BINDABLE_PROPS: ClassVar[tuple[str, ...]] = ("disabled",)
    # What a carrier (a second server handler) listens to.
    DOM_EVENTS: ClassVar[dict[str, str]] = _KEBAB_EVENTS
    EVENTS: ClassVar[tuple[str, ...]] = (
        "change", "upload_start", "upload_complete", "upload_error", "remove",
    )
    IMPERATIVE: ClassVar[tuple[str, ...]] = ("pick", "clear")
    #: Several server handlers: ``on_change`` on the root, ``on_upload_*``
    #: on carriers.
    ALLOW_MULTI_SERVER_EVENTS: ClassVar[bool] = True

    name: str | None = reactive_prop(default=None, emit_attr=False)
    multiple: bool = reactive_prop(default=False, emit_attr=False)
    accept: str | None = reactive_prop(default=None, emit_attr=False)
    disabled: bool = reactive_prop(default=False, emit_attr=False)
    required: bool = reactive_prop(default=False, emit_attr=False)
    color: str = reactive_prop(default="primary", emit_attr=False)
    size: str = reactive_prop(default="md", emit_attr=False)

    def __init__(
        self,
        *,
        display: str = "chips",
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
        **kwargs: Any,
    ) -> None:
        owner = f"ui.{type(self).THEME_KEY}"
        if display not in DISPLAYS:
            raise ComponentUsageError(
                f"{owner}(display=…) is one of "
                f"{' / '.join(map(repr, DISPLAYS))}, got {display!r}."
            )
        if drop is not None and drop not in DROP_HOSTS:
            raise ComponentUsageError(
                f"{owner}(drop=…) is \"form\" (the whole form around), \"self\" "
                f"(the list) or None, got {drop!r}."
            )
        reject_component(
            accept,
            owner=type(self).__name__,
            prop="accept",
            because=(
                "``accept`` is a MIME filter — it goes into the "
                "``<input type=file>``'s ``accept`` attribute AND into the "
                "JSON literal the runtime reads, where a Component is not "
                "even serialisable."
            ),
            instead="Write ``accept=\"image/*,.pdf\"`` or ``accept=[\"image/*\", \".pdf\"]``.",
        )
        self._display = display
        self._server_files = server_files(files)
        self._max_size_mb = max_size_mb
        self._max_files = max_files
        self._upload_url = upload_url
        self._show_previews = show_previews
        self._paste = paste
        self._drop = drop
        # Per FILE, not on the root: each × of a file the server holds
        # posts its own key (``item_action_attrs``).
        self._on_remove = on_remove

        # ``accept=`` accepts either a comma string ("image/*,.pdf") OR a
        # list (["image/*", ".pdf"]) — normalised to the comma form both
        # for the HTML attribute and the JS factory.
        if isinstance(accept, (list, tuple)):
            accept = ",".join(accept)

        # Direct forward: the base layer drops reactive None kwargs (keeps the default).
        super().__init__(
            name=name,
            multiple=multiple,
            accept=accept,
            disabled=disabled,
            required=required,
            color=color, size=size,
            on_change=on_change,
            on_upload_start=on_upload_start,
            on_upload_complete=on_upload_complete,
            on_upload_error=on_upload_error,
            **kwargs,
        )

    # ── Commands ──────────────────────────────────────────────────────

    def pick(self) -> str:
        """Open the system's file picker — put it on a button's ``on_click``.

        The browser opens a picker only within a user's click: the
        command must be what the click runs, not a later effect."""
        return self._dispatch_command("bz-pick")

    def clear(self) -> str:
        """Empty the files picked in the browser (``change`` follows)."""
        return self._dispatch_command("bz-clear")

    # ── Render ────────────────────────────────────────────────────────

    def render(self) -> Element:
        s = self.compose_class
        multiple = bool(self._reactive_values.get("multiple") or False)
        accept = self._reactive_values.get("accept")
        disabled = bool(self._reactive_values.get("disabled") or False)
        required = bool(self._reactive_values.get("required") or False)

        # The scope's options — one JSON object passed to the factory.
        opts: dict[str, Any] = {
            "multiple": multiple,
            # A chip has no thumbnail: no blob URL to make for it.
            "showPreviews": self._show_previews and self._display != "chips",
        }
        if accept:
            opts["accept"] = accept
        if self._max_size_mb is not None:
            opts["maxSizeMB"] = self._max_size_mb
        if self._max_files is not None:
            opts["maxFiles"] = self._max_files
        if self._upload_url:
            opts["uploadUrl"] = self._upload_url
        # The refusal messages, in the app's language: templates the
        # runtime fills (``{name}``, ``{size}``…), as the calendar does.
        opts["texts"] = {key: template(f"attachments.{key}") for key in _RUNTIME_TEXTS}

        root_attrs = self.emit_attrs()
        root_attrs["class"] = s("root")
        root_attrs["data-bz-attachments"] = ""
        # A labelled group of files: a ``ui.form_field`` around names it,
        # and a screen reader reads a label on a group, not on a bare div.
        root_attrs["role"] = "group"
        # ``el: $el`` captures the root in the scope (methods have no
        # $root). Spliced after the leading brace because ``$el`` is a
        # runtime identifier, not a JSON-serialisable value. ``opts``
        # always carries ``multiple``, so the blob is never ``"{}"``.
        scope_arg = "{el: $el, " + json.dumps(opts, ensure_ascii=False)[1:]
        root_attrs["bz-data"] = f"$bz.attachments.makeScope({scope_arg})"
        # The commands dispatch at the root (its id); a command bubbling
        # up from a nested list is not this one's.
        root_attrs["bz-on:bz-pick"] = "if ($event.target === $el) pick()"
        root_attrs["bz-on:bz-clear"] = "if ($event.target === $el) clear()"

        # The ``upload_*`` names are renamed to kebab (both the ``bz-on:``
        # string form and the ``hx-trigger`` form): the slab dispatches
        # ``upload-start`` etc. on the root, where they bubble.
        relocate_handlers(root_attrs, {
            event: (root_attrs, kebab) for event, kebab in _KEBAB_EVENTS.items()
        })

        input_name = str(self._reactive_values.get("name") or "files")
        native_input = self._native_input(s, input_name, multiple, accept, disabled, required)
        limits = self._limits(accept, multiple)
        ctx = maybe_current_context()
        if ctx is not None:
            # What the server holds the submission to: the form around
            # signs it into its token (``server/handlers.check_uploads``).
            ctx.upload_limits[id(native_input)] = (native_input, limits)

        # A server ``on_change`` posts the files themselves (multipart, its
        # own signed token): a list may send with no form around.
        own_token = (posts_its_files(root_attrs, self.id, ctx, {input_name: limits})
                     if trigger_event(root_attrs) == "change" else None)
        inits = ["watchSend()"]
        if self._paste:
            inits.append("watchPaste()")
        if self._drop:
            inits.append(f"watchDrop('{self._drop}')")
        root_attrs["bz-init"] = "; ".join(inits)

        if self._hides_when_empty() and not self._server_files:
            # Nothing picked, nothing refused, nothing held: no room taken.
            root_attrs["bz-show"] = "files.length > 0 || errors.length > 0"
            stamp_display_none(root_attrs)

        # ── Validation error panel ─────────────────────────────────
        # Hidden at SSR (no errors yet) → FOUC pre-stamp.
        error_panel_attrs: dict[str, Any] = {
            "class": s("error_panel"),
            "bz-show": "errors.length > 0",
            "role": "alert",
        }
        stamp_display_none(error_panel_attrs)
        error_panel = Element(tag="div", attrs=error_panel_attrs, children=(
            Element(tag="span", attrs={"class": s("error_text"), "bz-text": "errors[0]"},
                    children=()),
        ))

        children: list[Node] = [self._trigger(root_attrs, native_input), error_panel,
                                self._render_file_list(s, ctx)]
        if own_token is not None:
            children.append(own_token)
        return Element(tag=self._tag, attrs=root_attrs, children=tuple(children))

    def _hides_when_empty(self) -> bool:
        """The list takes no room while it is empty. ``ui.file_upload``,
        whose dropzone is always there, says no."""
        return True

    def _trigger(self, root_attrs: dict[str, Any], native_input: Element) -> Node:
        """What opens the picker, around the native input. The list has
        none of its own — any button does it with ``.pick()``;
        ``ui.file_upload`` puts its dropzone here."""
        return native_input

    def _native_input(self, s: Callable[[str], str], name: str, multiple: bool,
                      accept: Any, disabled: bool, required: bool) -> Element:
        # ``tabindex="-1"`` + ``aria-hidden="true"`` remove it from the
        # tab order (sr-only alone does NOT, contrary to display: none):
        # it is a pure form-data carrier.
        attrs: dict[str, Any] = {
            "type": "file",
            "class": s("input_native"),
            "name": name,
            "tabindex": "-1",
            "aria-hidden": "true",
            # Where a test sets its files (``set_input_files``) without
            # guessing which input is the list's.
            "data-bz-attachments-input": "",
            # ``stopPropagation``: without it, the input's NATIVE
            # ``change`` bubbles up to the root, which already carries
            # ``hx-trigger="change"`` — and the slab THEN dispatches its
            # own ``change`` there. Two events on the root = TWO POSTs for
            # a single selection. A single source: the slab's dispatch,
            # which also covers a removal (the native input says nothing).
            "bz-on:change": "$event.stopPropagation(); onNativeChange($event)",
        }
        if multiple:
            attrs["multiple"] = True
        if accept:
            attrs["accept"] = str(accept)
        if disabled:
            attrs["disabled"] = True
        if required:
            attrs["required"] = True
        # ``disabled`` only acts on the native input; the root is layout
        # (``traps.md`` § "Un champ de formulaire lié possède un carrier réel").
        self.forward_binding("disabled", attrs)
        return Element(tag="input", attrs=attrs, children=())

    def _limits(self, accept: Any, multiple: bool) -> dict[str, Any]:
        limits: dict[str, Any] = {"accept": str(accept or ""), "multiple": multiple}
        if self._max_size_mb is not None:
            limits["max_bytes"] = int(self._max_size_mb * 1024 * 1024)
        if self._max_files is not None:
            limits["max_files"] = self._max_files
        return limits

    # ── The list ─────────────────────────────────────────────────────

    def _render_file_list(self, s: Callable[[str], str], ctx: Any) -> Element:
        """The files the server holds, rendered here, then the
        ``<template bz-for>`` of the files picked in the browser — the
        same look for both.

        The client card lives inside a ``<template>``, so its ``bz-show``
        / ``bz-attr`` branches need no FOUC pre-stamp — the rows are
        cloned + bound fresh by ``bz-for``."""
        table = _DISPLAY_SLOTS[self._display]

        def slot(name: str) -> str:
            return s(table.get(name, name))

        held = tuple(self._held_item(slot, entry, ctx) for entry in self._server_files)
        picked = Element(tag="template", attrs={"bz-for": "entry in files :key=entry.id"},
                         children=(self._picked_item(slot),))
        list_attrs: dict[str, Any] = {
            "class": slot("file_list"),
            "role": "list",
            "aria-label": text("attachments.label"),
        }
        if not held:
            # Nothing held, nothing picked yet → hidden, FOUC pre-stamp.
            list_attrs["bz-show"] = "files.length > 0"
            stamp_display_none(list_attrs)
        return Element(tag="div", attrs=list_attrs, children=(*held, picked))

    def _remove_button(self, slot: Callable[[str], str], on_click: str,
                       extra_attrs: dict[str, Any] | None = None) -> Element:
        """The × of a row — ``base/dismiss.dismiss_button``, the same × as
        Alert / Badge / Banner, its glyph at the component's step."""
        row = self._size_row()
        return dismiss_button(
            button_class=slot("remove_btn"),
            aria_label=text("attachments.remove"),
            icon_size=row.get("remove_btn_icon_size", "xs") if isinstance(row, dict) else "xs",
            on_click=on_click,
            extra_attrs=extra_attrs,
        )

    def _picked_item(self, slot: Callable[[str], str]) -> Element:
        """One file picked in the browser — the row ``bz-for`` clones."""
        chips = self._display == "chips"
        thumb = None if chips else Element(tag="img", attrs={
            "bz-attr:src": "entry._preview",
            "bz-attr:alt": "entry.name",
            "bz-show": "entry.isImage && entry._preview",
            "class": slot("file_thumb"),
            "loading": "lazy",
        }, children=())
        # A chip shows its icon (it has no thumbnail) — save while a status
        # takes its place: the check, a moment after the file has arrived,
        # or the error, which stays.
        icon_attrs: dict[str, Any] = {"icon": "lucide:file", "class": slot("file_icon")}
        icon_attrs["bz-show"] = (
            "!entry.justDone && entry.status !== 'error'" if chips
            else "!(entry.isImage && entry._preview)"
        )
        icon = Element(tag="iconify-icon", attrs=icon_attrs, children=())

        # Statuses (``upload_url`` mode) — uploading shows the progress bar;
        # done shows a check for a moment (``justDone``, lowered by the
        # engine), then the file's own look comes back; an error stays,
        # its reason in the title.
        status_done = Element(tag="span", attrs={
            "class": slot("file_status_done"),
            "bz-show": "entry.justDone",
            "aria-label": text("attachments.complete"),
        }, children=(Element(tag="iconify-icon", attrs={
            "icon": "lucide:check", "class": slot("file_status_icon")}, children=()),))
        status_error = Element(tag="span", attrs={
            "class": slot("file_status_error"),
            "bz-show": "entry.status === 'error'",
            "bz-attr:title": "entry.error",
            "aria-label": text("attachments.error"),
        }, children=(Element(tag="iconify-icon", attrs={
            "icon": "lucide:alert-triangle", "class": slot("file_status_icon")}, children=()),))
        progress = Element(tag="div", attrs={
            "class": slot("file_progress_bar"),
            "bz-show": ("entry.status === 'uploading' "
                        "|| (entry.status === 'done' && entry.progress < 100)"),
            "role": "progressbar",
            "bz-attr:aria-valuenow": "entry.progress",
            "aria-valuemin": "0",
            "aria-valuemax": "100",
        }, children=(Element(tag="div", attrs={
            "class": slot("file_progress_fill"),
            "bz-attr:style": "'width: ' + entry.progress + '%'",
        }, children=()),))
        # Here the × removes ONE entry. ``.stop`` inlined (no modifiers).
        remove_btn = self._remove_button(
            slot, "$event.stopPropagation(); removeFile(entry, $event)")
        # The name is the card's link: its ``::after`` covers the card
        # (``file_link``), so the whole card opens the file — here its copy
        # in the browser's memory.
        name = Element(tag="a", attrs={
            "class": f"{slot('file_name')} {slot('file_link')}", "bz-text": "entry.name",
            "bz-attr:href": "entry._url", "target": "_blank", "rel": "noopener",
        }, children=())
        size = None if chips else Element(tag="span", attrs={
            "class": slot("file_size"), "bz-text": "entry.sizeLabel"}, children=())
        return Element(tag="div", attrs={
            "class": slot("file_item"), "role": "listitem", "bz-attr:title": "entry.name",
        }, children=tuple(child for child in (
            thumb, icon, status_done, status_error, name, size, progress, remove_btn,
        ) if child is not None))

    def _held_item(self, slot: Callable[[str], str], entry: dict[str, Any], ctx: Any) -> Element:
        """One file the server holds — the same row, written by the server."""
        chips = self._display == "chips"
        is_image = entry["type"].startswith("image/")
        if not chips and self._show_previews and is_image and entry["href"]:
            lead = Element(tag="img", attrs={
                "src": entry["href"], "alt": entry["name"], "class": slot("file_thumb"),
                "loading": "lazy",
            }, children=())
        else:
            lead = Element(tag="iconify-icon", attrs={
                "icon": "lucide:file", "class": slot("file_icon")}, children=())
        if entry["href"]:
            # The whole card opens it, as for a file picked (``file_link``).
            name: Element = Element(tag="a", attrs={
                "class": f"{slot('file_name')} {slot('file_link')}",
                "href": entry["href"], "target": "_blank", "rel": "noopener",
            }, children=(_TextNode(entry["name"]),))
        else:
            name = Element(tag="span", attrs={"class": slot("file_name")},
                           children=(_TextNode(entry["name"]),))
        children: list[Node] = [lead, name]
        if not chips and entry["size"] is not None:
            # Written by the browser, in the page's language (« 1,5 Mo »);
            # the server's English is the fallback.
            children.append(Element(tag="span", attrs={
                "class": slot("file_size"),
                "bz-text": f"$bz.attachments.formatSize({entry['size']})",
            }, children=(_TextNode(size_label(entry["size"])),)))
        if self._on_remove is not None and ctx is not None:
            wired = item_action_attrs(self._on_remove, event="remove", owner_id=self.id,
                                      ctx=ctx, payload={"key": entry["key"]},
                                      dom_event="click")
            # A client ``on_remove`` brings its own click (the one that
            # re-fires ``remove`` with the key); a server one, none — the
            # click then only stays inside the row.
            children.append(self._remove_button(slot, "$event.stopPropagation()", wired))
        return Element(tag="div", attrs={
            "class": slot("file_item"), "role": "listitem", "title": entry["name"],
            "data-bz-held": entry["key"],
        }, children=tuple(children))
