"""``Message`` — one message of a conversation, whoever says it.

The pair of :class:`~bretzel.components.inputs.message_input.MessageInput`,
which writes one. Generic: a person-to-person chat as
well as an AI's — it says WHERE a message sits and WHO said it, never
what kind of being they are ::

    ui.message("Bonjour", side="end")                             # mine
    ui.message("Salut !", author="Marie", avatar="MA", time="14:02")
    with ui.message(answer.text, avatar=ui.icon("sparkles"), variant="plain",
                    markdown=True, writing=run.busy, copyable=True,
                    on_retry=regenerate):
        ui.accordion(...)                    # what it did, under its words

The libraries that serve both kinds of chat separate the SIDE from the
identity — Ant Design X's ``placement="start"|"end"`` beside its role,
chatscope's ``direction``. Hence:

- ``side`` — ``"start"`` (the others, the default) or ``"end"`` (mine);
  logical, so a right-to-left page mirrors it;
- ``author`` / ``avatar`` — who says it: a name above the words (and in
  the message's accessible name), an avatar beside them (a string is a
  photo's address — ``https://…``, ``/…``, ``data:`` — or else initials;
  an icon becomes a chip of the same size — an AI's mark —; any other
  component, ``ui.avatar(…)`` included, is shown as it is);
- ``variant`` — ``"bubble"`` (a tinted box sized to its words) or
  ``"plain"`` (the width, no box): the two meet in the same thread — a
  question in its bubble, an AI's answer with a table in plain;
- ``markdown`` — the text read as markdown, or kept as typed (the
  default: a person's ``*`` is a star). Bound to a ClientState field, the
  text is always plain — markdown needs the server.

``writing`` shows a small spinner in a polite live region. ``time`` and
``status`` (``"sending"`` · ``"error"``) say where a message stands;
``copyable`` adds « Copier », ``on_retry`` adds « Réessayer » (beside an
error, or to regenerate an answer). In a :class:`MessageList`, a message
that follows one of the same author and side is grouped: its name and
its avatar are not repeated.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any, ClassVar

from bretzel.components.actions.icon_button import IconButton
from bretzel.components.base import Component, reactive_prop
from bretzel.components.base.composition import unwrap_transparent
from bretzel.components.data.message.theme import MESSAGE_LIST_THEME, MESSAGE_THEME
from bretzel.components.feedback.avatar import Avatar
from bretzel.components.feedback.badge import Badge
from bretzel.components.primitives.icon import Icon
from bretzel.components.primitives.markdown import Markdown
from bretzel.components.primitives.spinner import Spinner
from bretzel.components.primitives.text import Text
from bretzel.core.tree import Element, Node, TextNode
from bretzel.render import text as said
from bretzel.runtime.verbs import copy as copy_verb

SIDES = ("start", "end")
#: An ``avatar`` string that is an address is a photo; any other, initials.
_ADDRESSES = ("http://", "https://", "/", "data:", "blob:")
VARIANTS = ("bubble", "plain")
STATUSES = ("sending", "error")


class Message(Component):
    """One message of a conversation: where it sits, who said it, what it says."""

    THEME: ClassVar[dict[str, Any]] = MESSAGE_THEME
    THEME_KEY: ClassVar[str] = "message"
    COLLECTION_OWNER: ClassVar[str | None] = "author"
    BINDABLE_PROPS: ClassVar[tuple[str, ...]] = ("text", "writing")
    EVENTS: ClassVar[tuple[str, ...]] = ("retry",)

    text: Any = reactive_prop(default=None, emit_attr=False)
    side: str = reactive_prop(default="start", emit_attr=False, steps=SIDES)
    author: str | None = reactive_prop(default=None, emit_attr=False)
    avatar: Any = reactive_prop(default=None, emit_attr=False)
    variant: str = reactive_prop(default="bubble", emit_attr=False, steps=VARIANTS)
    markdown: bool = reactive_prop(default=False, emit_attr=False)
    files: Any = reactive_prop(default=None, emit_attr=False)
    time: str | None = reactive_prop(default=None, emit_attr=False)
    status: str | None = reactive_prop(default=None, emit_attr=False, steps=STATUSES)
    writing: bool = reactive_prop(default=False, emit_attr=False)
    copyable: bool = reactive_prop(default=False, emit_attr=False)

    #: Set by its :class:`MessageList` just before rendering it: it follows
    #: a message of the same author and side — no name, no avatar again.
    _grouped: bool = False

    def __init__(
        self,
        text: Any = None,
        *,
        side: str | None = None,
        author: str | None = None,
        avatar: str | Component | None = None,
        variant: str | None = None,
        markdown: bool | None = None,
        files: Sequence[str] | None = None,
        time: str | None = None,
        status: str | None = None,
        writing: Any = None,
        copyable: bool | None = None,
        on_retry: Callable[..., Any] | str | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(text=text, side=side, author=author, avatar=avatar, variant=variant,
                         markdown=markdown, files=tuple(files) if files else None, time=time,
                         status=status, writing=writing, copyable=copyable,
                         on_retry=on_retry, **kwargs)
        self._retry = on_retry is not None

    def render(self) -> Element:
        slots = self._resolved_theme()["slots"]
        values = self._reactive_values
        end = values["side"] == "end"
        author = values.get("author")

        body: list[Node] = []
        if author and not self._grouped:
            body.append(Element(tag="span", attrs={"class": slots["author"]},
                                children=(TextNode(str(author)),)))
        names = values.get("files")
        if names:
            body.append(Element(tag="div", attrs={"class": slots["files"]}, children=tuple(
                Component.render_detached(Badge(name, variant="outline", color="muted",
                                                icon_left="file-text"))
                for name in names)))
        content = self._text_node(slots)
        if content is not None:
            body.append(content)
        writing = values.get("writing")
        bound = self._binding_metadata.get("writing")
        if bound is not None or writing:
            body.append(Component.render_detached(Spinner(
                size="sm", visible=bound, aria_label=said("message.writing"))))
        body.extend(n for n in (self._render_one(c) for c in self._children) if n is not None)

        column: list[Node] = []
        if values["variant"] == "bubble":
            # Mine in the accent's tint, the others' in a neutral one.
            tone = slots["bubble_end"] if end else slots["bubble_start"]
            column.append(Element(tag="div", attrs={"class": f"{slots['bubble']} {tone}"},
                                  children=tuple(body)))
        else:
            column.extend(body)
        foot = self._foot(slots)
        if foot is not None:
            column.append(foot)

        attrs = self.emit_attrs()
        attrs["class"] = self.compose_class("root")
        attrs["data-side"] = values["side"]
        if self._grouped:
            attrs["data-grouped"] = "true"
        if values.get("status"):
            attrs["data-status"] = values["status"]
        attrs.setdefault("aria-label", said("message.from", author=author) if author
                         else said("message.mine" if end else "message.theirs"))
        live = {"aria-live": "polite"} if (bound is not None or writing) else {}
        children: list[Node] = []
        mark = self._avatar(slots)
        if mark is not None:
            children.append(mark)
        children.append(Element(tag="div", attrs={"class": slots["column"], **live},
                                children=tuple(column)))
        return Element(tag=self._tag, attrs=attrs, children=tuple(children))

    def _text_node(self, slots: dict[str, str]) -> Node | None:
        """Bound: a plain text that follows its field. Given: as typed, or
        markdown when asked."""
        binding = self._binding_metadata.get("text")
        if binding is not None:
            return Component.render_detached(Text(binding, classes=slots["plain"]))
        value = self._reactive_values.get("text")
        if not value:
            return None
        if self._reactive_values.get("markdown"):
            return Component.render_detached(Markdown(str(value)))
        return Component.render_detached(Text(str(value), classes=slots["plain"]))

    def _avatar(self, slots: dict[str, str]) -> Node | None:
        """Beside the words; an empty place when grouped, so a group's
        messages stay aligned."""
        avatar = self._reactive_values.get("avatar")
        # A bound avatar hands its binding to the chip's initials, which
        # follow it live. A photo address stays
        # the server's: ``Avatar.src`` is not bindable.
        bound = self._binding_metadata.get("avatar")
        if avatar is None and bound is None:
            return None
        children: tuple[Node, ...] = ()
        if not self._grouped:
            if bound is not None and not str(avatar).startswith(_ADDRESSES):
                node = Component.render_detached(
                    Avatar(initials=bound, size="sm"))
            elif isinstance(avatar, Icon):
                # An icon is the mark of a non-person (an AI, a bot): a chip
                # of the same size as the initials beside it.
                node = Component.render_detached(Avatar(initials=avatar, size="sm"))
            elif isinstance(avatar, Component):
                node = Component.render_detached(avatar)
            elif str(avatar).startswith(_ADDRESSES):
                node = Component.render_detached(Avatar(src=str(avatar), size="sm",
                                                        name=self._reactive_values.get("author")))
            else:
                node = Component.render_detached(Avatar(initials=str(avatar), size="sm"))
            children = (node,)
        return Element(tag="span", attrs={"class": slots["avatar"], "aria-hidden": "true"},
                       children=children)

    def _foot(self, slots: dict[str, str]) -> Node | None:
        """The line under the words: when, where it stands, what to do."""
        values = self._reactive_values
        parts: list[Node] = []
        if values.get("time"):
            parts.append(Element(tag="span", attrs={}, children=(TextNode(str(values["time"])),)))
        status = values.get("status")
        if status == "sending":
            parts.append(Element(tag="span", attrs={}, children=(
                TextNode(said("message.sending")),)))
        elif status == "error":
            parts.append(Element(tag="span", attrs={"class": slots["error"], "role": "alert"},
                                 children=(TextNode(said("message.error")),)))
        if values.get("copyable"):
            source = self._binding_metadata.get("text") or values.get("text") or ""
            parts.append(Component.render_detached(IconButton(
                "copy", variant="ghost", size="sm", tooltip=said("message.copy"),
                aria_label=said("message.copy"), on_click=copy_verb(source))))
        if self._retry:
            parts.append(Component.render_detached(IconButton(
                "rotate-ccw", variant="ghost", size="sm", tooltip=said("message.retry"),
                aria_label=said("message.retry"), on_click="$dispatch('retry')")))
        if not parts:
            return None
        return Element(tag="div", attrs={"class": slots["foot"]}, children=tuple(parts))


class MessageList(Component):
    """A conversation's messages, which follows its newest one."""

    THEME: ClassVar[dict[str, Any]] = MESSAGE_LIST_THEME
    THEME_KEY: ClassVar[str] = "message_list"
    COLLECTION_OWNER: ClassVar[str | None] = "author"
    BINDABLE_PROPS: ClassVar[tuple[str, ...]] = ()
    #: Draws its children itself (it groups the messages): a zone among
    #: them is refused (``base/composition.unwrap_transparent``).
    _COMPOSES_CHILDREN: ClassVar[bool] = True

    def __init__(self, **kwargs: Any) -> None:
        """No prop of its own: its children are the conversation."""
        super().__init__(**kwargs)

    def _needs_identity(self) -> bool:
        # A stable id: the runtime keeps what the reader did (scrolled up,
        # where to) by it, even when a refresh replaces the element.
        return True

    def render(self) -> Element:
        slots = self._resolved_theme()["slots"]
        nodes: list[Node] = []
        previous: tuple[str, Any] | None = None
        for wrapped in self._children:
            child, rewrap = unwrap_transparent(wrapped, self)
            if isinstance(child, Message):
                who = (child._reactive_values["side"], child._reactive_values.get("author"))
                # Grouped: right after a message of the same side and author
                # (two answers in a row show their avatar once).
                child._grouped = previous == who
                previous = who
            else:
                previous = None
            node = self._render_one(child)
            if node is not None:
                nodes.append(rewrap(node))
        attrs = self.emit_attrs()
        attrs["class"] = self.compose_class("root")
        attrs["role"] = "log"
        attrs.setdefault("aria-label", said("message_list.label"))
        attrs["data-bz-message-list"] = ""
        back = Component.render_detached(IconButton(
            "arrow-down", variant="surface", tooltip=said("message_list.bottom"),
            aria_label=said("message_list.bottom"),
            attrs={"data-bz-message-list-bottom": ""}))
        return Element(tag=self._tag, attrs=attrs, children=(
            Element(tag="div", attrs={"class": slots["thread"]}, children=tuple(nodes)),
            Element(tag="div", attrs={"class": slots["bottom"]}, children=(
                # A backing of ours: the button floats over the text, and its
                # hover tint (``surface``: 5 %) would let the words show through.
                Element(tag="span", attrs={"class": slots["backing"]}, children=(back,)),)),
        ))
