"""``MessageInput`` — where a message is written: to an AI, or to anyone.

One rounded box, and everything that writes a message lives inside it ::

    with ui.message_input(value=ask.text, on_submit=send,
                          loading=run.busy, on_stop=stop,
                          voice=True, files=(".pdf", "image/*")):
        ui.badge("5e1 · Liste", dismissible=True)          # top of the box
        ui.message_input_tool("Mes documents", icon="folder-open",
                              on_click=documents.open())  # in its bar
        with ui.dropdown(trigger=ui.message_input_tool("Ajouter", icon="plus")):
            ui.dropdown_item("Un modèle", on_click=template)     # a menu of tools

From top to bottom: the children that are not tools (a badge saying
what the message is about, typically), the files joined, the text, then
one bar — the joining clip and the microphone on the left, the
author's tools, the round button on the right. An overlay whose trigger
is a tool goes to the bar with it: many tools behind one button.

What the box does by itself
---------------------------
- **Enter sends, Shift+Enter breaks the line** — the chat convention;
  a composition in progress (an IME) is left alone.
- **It empties itself once the message has left** — the text and the
  files, after the server answered. A failed request keeps them: what
  was typed is not lost.
- **It never sends twice while loading.** ``loading=`` says that an answer is
  being written (the APP knows it — the request that started it ended
  long ago, and a reload mid-answer clicked nothing); the round button
  then becomes « Arrêter », which fires ``on_stop``. Both are optional:
  without them the button only sends — a messaging app's case.
- **The text grows with what is written** (``field-sizing: content``),
  up to a bound where it scrolls; a browser without it keeps two lines.

The browser part lives in ``components/inputs/message_input/message_input.js``:
document-level listeners (Enter, the end of a request, the microphone),
so a box swapped in by a morph needs nothing re-wired.

``voice=True``: the browser's own dictation (the Web Speech API), in the
page's language, appended to what is written. The button only shows in
a browser that has it (Chrome, Edge, Safari) — none in Firefox.

The text travels under the bound field's name (``value=ask.text`` →
``text``), else ``name=``, else ``message``: a handler takes it like any
field. ``files=``: what may be joined (``(".pdf", "image/*")``). The files
travel with the message, under the field name ``files``, through
:class:`~bretzel.components.inputs.file_upload.FileUpload` — its chips,
its paste of a screenshot, its checks. The box is a ``<form>``
(:func:`~bretzel.components.inputs.form.form.form_element`): it does not
go inside another one.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any, ClassVar

from bretzel.components.actions.icon_button import IconButton
from bretzel.components.base import Component, ComponentUsageError, reactive_prop
from bretzel.components.base.commands import ValueCommands
from bretzel.components.base.composition import unwrap_transparent
from bretzel.components.base.focus import FocusCommands
from bretzel.components.inputs._wiring import add_local_value_scope
from bretzel.components.inputs.file_upload import FileUpload
from bretzel.components.inputs.form.form import form_element
from bretzel.components.inputs.message_input.theme import (
    MESSAGE_INPUT_THEME,
    MESSAGE_INPUT_TOOL_THEME,
)
from bretzel.core.tree import Element, Node, TextNode
from bretzel.render import text

#: The field name the joined files travel under — a handler takes
#: ``files`` as it takes any field.
FILES_FIELD = "files"
#: The text's field name when nothing names it — neither a bound state
#: field (autoname) nor ``name=``: a message box always sends its text.
TEXT_FIELD = "message"


class MessageInput(ValueCommands, FocusCommands, Component):
    """A box to write a message in: text, files, voice, tools, send and stop."""

    THEME: ClassVar[dict[str, Any]] = MESSAGE_INPUT_THEME
    THEME_KEY: ClassVar[str] = "message_input"
    DEFAULT_TAG: ClassVar[str] = "form"
    #: Draws its children itself (badges at the top, tools in the bar):
    #: a zone among them is refused (``base/composition.unwrap_transparent``).
    _COMPOSES_CHILDREN: ClassVar[bool] = True
    COLLECTION_OWNER: ClassVar[str | None] = "author"
    #: Retired names, refused with the new one (``attrs.split_kwargs``).
    RENAMED_PROPS: ClassVar[dict[str, str]] = {"busy": "write ``loading=``."}
    BINDABLE_PROPS: ClassVar[tuple[str, ...]] = ("value", "loading")
    IMPERATIVE: ClassVar[tuple[str, ...]] = ("set", "clear", "focus", "blur")
    # Where ``autofocus=`` / ``.focus()`` land: the message field.
    FOCUS_TARGET: ClassVar[tuple[str, ...] | None] = ("textarea",)
    EVENTS: ClassVar[tuple[str, ...]] = ("submit", "stop")
    #: ``on_submit`` on the form, ``on_stop`` relayed from the round button.
    ALLOW_MULTI_SERVER_EVENTS: ClassVar[bool] = True

    name: str | None = reactive_prop(default=None, emit_attr=False)
    value: Any = reactive_prop(default=None, writes=True, names_field=True,
                               emit_attr=False)
    placeholder: str | None = reactive_prop(default=None, emit_attr=False)
    loading: bool = reactive_prop(default=False, emit_attr=False)
    voice: bool = reactive_prop(default=False, emit_attr=False)
    files: Any = reactive_prop(default=None, emit_attr=False)
    max_files: int | None = reactive_prop(default=None, emit_attr=False)
    max_size_mb: float | None = reactive_prop(default=None, emit_attr=False)
    max_length: int | None = reactive_prop(default=None, emit_attr=False)
    disabled: bool = reactive_prop(default=False, emit_attr=False)

    def __init__(
        self,
        *,
        value: Any = None,
        placeholder: str | None = None,
        loading: Any = None,
        voice: bool | None = None,
        files: str | Sequence[str] | None = None,
        max_files: int | None = None,
        max_size_mb: float | None = None,
        max_length: int | None = None,
        disabled: bool | None = None,
        name: str | None = None,
        on_submit: Callable[..., Any] | str | None = None,
        on_stop: Callable[..., Any] | str | None = None,
        **kwargs: Any,
    ) -> None:
        if isinstance(files, str):
            files = (files,)
        super().__init__(
            value=value, placeholder=placeholder, loading=loading, voice=voice,
            files=tuple(files) if files else None, max_files=max_files,
            max_size_mb=max_size_mb, max_length=max_length, disabled=disabled, name=name,
            on_submit=on_submit, on_stop=on_stop, **kwargs,
        )

    def _needs_identity(self) -> bool:
        return True

    # ── Render ────────────────────────────────────────────────────────

    def render(self) -> Element:
        slots = self._resolved_theme()["slots"]
        root_attrs = self.emit_attrs()
        root_attrs["class"] = self.compose_class("root")
        root_attrs["data-bz-message-input"] = ""
        disabled = bool(self._reactive_values.get("disabled"))
        if disabled:
            root_attrs["data-disabled"] = ""
        # ``.set()`` / ``.clear()`` dispatch at the box (its id); the text
        # is a child, which a dispatched event never reaches going down.
        root_attrs["bz-on:bz-set"] = (
            "if ($event.target === $el) { const t = $el.querySelector("
            "'[data-bz-message-field]'); t.value = $event.detail.value; "
            "t.dispatchEvent(new Event('input', {bubbles: true})); }"
        )
        field = self._field(root_attrs, slots)

        # ``unwrap_transparent``: a tool inside a ``@refreshable`` zone is
        # still a tool — it goes to the bar, its zone around it.
        top: list[Node] = []
        tools: list[Node] = []
        for wrapped in self._children:
            child, rewrap = unwrap_transparent(wrapped, self)
            if isinstance(child, MessageInputTool):
                # A box switched off switches its tools off with it: no
                # tool stays clickable in a box that refuses everything else.
                child._within_disabled = disabled
                tools.append(rewrap(child.render()))
                continue
            opener = getattr(child, "_trigger", None)
            if isinstance(opener, MessageInputTool):
                opener._within_disabled = disabled
                menu = self._render_one(child)
                if menu is not None:
                    tools.append(rewrap(menu))
                continue
            node = self._render_one(child)
            if node is not None:
                top.append(rewrap(node))

        # Off, the top row's own controls (a badge's ×) are off too: ``inert``.
        children: list[Node] = [Element(tag="div", attrs={
            "class": slots["top"], **({"inert": True} if disabled else {})},
            children=tuple(top))]
        accepted = self._reactive_values.get("files")
        bar: list[Node] = []
        if accepted:
            # The chips at the top, the native input and its checks: all
            # FileUpload's. Its own trigger gives way to the clip below.
            children.append(Component.render_detached(_Attachments(
                variant="button", list="chips", multiple=True, accept=list(accepted),
                paste=True, name=FILES_FIELD, disabled=disabled,
                max_files=self._reactive_values.get("max_files"),
                max_size_mb=self._reactive_values.get("max_size_mb"),
            )))
            bar.append(Component.render_detached(IconButton(
                "paperclip", variant="ghost", disabled=disabled,
                tooltip=text("message_input.attach"),
                aria_label=text("message_input.attach"),
                on_click="$el.closest('form').querySelector('input[type=file]').click()",
            )))
        if self._reactive_values.get("voice"):
            bar.append(Element(tag="span", attrs={"class": slots["voice"]}, children=(
                Component.render_detached(IconButton(
                    "mic", variant="ghost", disabled=disabled,
                    tooltip=text("message_input.voice"),
                    aria_label=text("message_input.voice"),
                    attrs={"data-bz-voice": "", "aria-pressed": "false"},
                )),)))
        bar.extend(tools)
        bar.append(Element(tag="span", attrs={"class": "flex-1"}, children=()))
        limit = self._reactive_values.get("max_length")
        if limit:
            typed = self._reactive_values.get("value")
            bar.append(Element(tag="span", attrs={"class": slots["count"],
                                                  "data-bz-message-count": "",
                                                  "aria-hidden": "true"},
                               children=(TextNode(f"{len(typed) if isinstance(typed, str) else 0}"
                                                  f" / {limit}"),)))
        bar.extend(self._round_buttons(slots, disabled))
        children.insert(1 if not accepted else 2, field)
        children.append(Element(tag="div", attrs={"class": slots["bar"]}, children=tuple(bar)))
        return form_element(self._tag, root_attrs, (*children, *self._event_carrier_nodes()))

    def _field(self, root_attrs: dict[str, Any], slots: dict[str, str]) -> Element:
        """The ``<textarea>``: the field's name, its binding and its value
        move from the form onto it."""
        attrs: dict[str, Any] = {"class": slots["field"], "rows": 2,
                                 "data-bz-message-field": ""}
        for key in ("name", "value", "bz-attr:value"):
            if key in root_attrs:
                attrs[key] = root_attrs.pop(key)
        name = self._reactive_values.get("name")
        if name:
            attrs["name"] = name
        attrs.setdefault("name", TEXT_FIELD)
        placeholder = self._reactive_values.get("placeholder")
        if placeholder:
            attrs["placeholder"] = placeholder
        # A stable accessible name: a placeholder is a hint that goes away
        # when one types (Stream's test « the label moves from the
        # placeholder to a stable one »).
        attrs["aria-label"] = text("message_input.label")
        limit = self._reactive_values.get("max_length")
        if limit:
            attrs["maxlength"] = int(limit)
        if self._reactive_values.get("disabled"):
            attrs["disabled"] = True
        initial = ""
        if self._bind_x_model(attrs) is None:
            raw = self._reactive_values.get("value")
            attrs.pop("value", None)
            initial = raw if isinstance(raw, str) else ""
        add_local_value_scope(self, attrs, prop="value", ssr_value=initial)
        return Element(tag="textarea", attrs=attrs,
                       children=(TextNode(initial),) if initial else ())

    def _round_buttons(self, slots: dict[str, str], disabled: bool) -> list[Node]:
        """« Envoyer », or « Arrêter » while an answer is being written.

        A bound ``loading`` renders both, each shown by the binding (no round
        trip when the app flips it); a plain one renders the right one."""
        loading = self._reactive_values.get("loading")
        bound = self._binding_metadata.get("loading")
        send = dict(variant="solid", color="primary", type="submit", disabled=disabled,
                    tooltip=text("message_input.send"), aria_label=text("message_input.send"),
                    attrs={"data-bz-message-send": ""})
        stop = dict(variant="soft", color="primary", type="button",
                    tooltip=text("message_input.stop"), aria_label=text("message_input.stop"),
                    on_click="$dispatch('stop')", attrs={"data-bz-message-stop": ""})
        if bound is not None:
            return [Component.render_detached(IconButton("arrow-up", visible=~bound, **send)),
                    Component.render_detached(IconButton("square", visible=bound, **stop))]
        if loading:
            return [Component.render_detached(IconButton("square", **stop))]
        return [Component.render_detached(IconButton("arrow-up", **send))]


class _Attachments(FileUpload):
    """:class:`FileUpload` as the box needs it: its chips, its errors, its
    native input, paste and checks — but no trigger of its own (the clip in
    the bar opens its picker), and a root that steps aside (``contents``)
    so that its chips and its errors are rows of the box.

    A subclass rather than ``slots=``: a slot ADDS its classes, and a
    ``hidden`` added beside the trigger's ``inline-flex`` loses to it in
    Tailwind's order, and the « Upload file » button would stay.
    Private: not a component of its own, ``ui.file_upload`` stays
    the one to use. Its three slots are the box's; every other one is
    FileUpload's, app overrides included."""

    #: The slots that are the box's rows, not the picker's.
    _ROWS: ClassVar[dict[str, str]] = {
        "root": "bz-file-upload contents",
        "chip_list": "flex flex-row flex-wrap items-center gap-2 px-3 pt-3 empty:hidden",
        "error_panel": (
            "mx-3 mt-2 flex flex-col gap-1 px-3 py-2 rounded-box "
            "bg-error/10 border-(length:--bz-stroke) border-error/20"
        ),
    }

    def compose_class(self, slot: str = "root", *,
                      apply_variant_size_modifiers: bool = True) -> str:
        return self._ROWS.get(slot) or super().compose_class(
            slot, apply_variant_size_modifiers=apply_variant_size_modifiers)

    def _render_button(self, s: Any, sz: Any, native_input: Element,
                       relocated_to_wrapper: dict[str, Any]) -> Element:
        return native_input


class MessageInputTool(Component):
    """A button of one's own in the bar of a :class:`MessageInput`."""

    THEME: ClassVar[dict[str, Any]] = MESSAGE_INPUT_TOOL_THEME
    THEME_KEY: ClassVar[str] = "message_input_tool"
    DEFAULT_TAG: ClassVar[str] = "button"
    IS_CONTAINER: ClassVar[bool] = False
    BINDABLE_PROPS: ClassVar[tuple[str, ...]] = ()
    EVENTS: ClassVar[tuple[str, ...]] = ("click",)

    label: str = reactive_prop(default="", emit_attr=False)
    icon: str = reactive_prop(default="", emit_attr=False)
    disabled: bool = reactive_prop(default=False, emit_attr=False)

    def __init__(
        self,
        label: str,
        *,
        icon: str,
        disabled: bool | None = None,
        on_click: Callable[..., Any] | str | None = None,
        **kwargs: Any,
    ) -> None:
        # ``icon`` may be a binding (R1), which refuses a truth test: only a
        # NAME can be missing.
        if not label or icon is None or (isinstance(icon, str) and not icon):
            raise ComponentUsageError(
                "ui.message_input_tool takes a label and its icon — the label is what a "
                "screen reader says and what the tooltip shows: "
                "``ui.message_input_tool(\"Mes documents\", icon=\"folder-open\")``.")
        super().__init__(icon=icon, label=label, disabled=disabled, on_click=on_click,
                         **kwargs)

    #: Set by its box just before rendering it: the box is switched off,
    #: so is the tool, whatever its own ``disabled`` says. A tool alone may
    #: be off in a box that works (``disabled=True`` on the tool).
    _within_disabled: bool = False

    def render(self) -> Element:
        node = Component.render_detached(IconButton(
            # The binding when there is one: the button follows it live.
            bound if (bound := self._binding_metadata.get("icon")) is not None
            else self._reactive_values["icon"],
            variant="ghost",
            disabled=self._within_disabled or bool(self._reactive_values.get("disabled")),
            aria_label=self._reactive_values["label"], type="button",
            tooltip=self._reactive_values["label"],
        ))
        attrs = {**node.attrs, **self.emit_attrs()}
        return Element(tag=node.tag, attrs=attrs, children=node.children)
