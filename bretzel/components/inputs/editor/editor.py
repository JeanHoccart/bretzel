"""``Editor`` — a text field that formats: bold, italic, lists, links.

Usage ::

    with ui.editor(value=reply.text, placeholder="Votre réponse",
                   on_change=save, debounce=800):
        ui.editor_tool("Demander à Claude", icon="sparkles", on_click=ask)

What one sees is formatted text, never its syntax; **what is stored is
Markdown** — the value, bound both ways as ``ui.textarea``'s is. Claude
writes Markdown, the app keeps it, the editor shows it. Turning it into
the HTML of a mail (a font, a signature) is the app's work, not this
component's.

The bar above the text holds the formatting commands — bold, italic,
bulleted list, numbered list, link — each an icon button with its
tooltip, PRESSED while the cursor is in what it applies (the B is lit in
bold). The set is fixed, the same everywhere. ``ui.editor_tool`` adds a
button of one's own to that bar, as ``ui.message_input_tool`` does in
``ui.message_input``; an overlay whose trigger is a tool goes there with
it (many tools behind one button).

One format
----------
- **Enter goes to the line**, adding no space (as Outlook does); Enter on
  an empty line starts a paragraph, three quarters of a line below. In a
  list, Enter starts the next item and Enter on an empty item leaves the
  list; Tab and Shift+Tab nest and un-nest.
- **Shortcuts**: Ctrl+B, Ctrl+I, Ctrl+K (link). ``- `` or ``* `` at the
  start of a line starts a bulleted list, ``1. `` a numbered one.
- **Paste** keeps bold, italic, lists and links, and drops fonts, sizes,
  colours, spacing and styles — from Word, Outlook or a web page alike.
  An address pasted over selected text makes it a link.
- **A link opens with a click**, in a new tab (the hand shows over it); to
  change one, put the caret in it by the keyboard, then Ctrl+K.
- **Undo / redo**: Ctrl+Z / Ctrl+Y.
- No Enter-to-send: the app decides its own gestures.

The Markdown written is CommonMark: ``**bold**``, ``*italic*``,
``- item`` (two spaces per nesting step), ``1. item``, ``[text](url)``, a
line break as ``\\`` at the end of the line. Syntax the editor does not
show (a heading, a quote, code) stays as written TEXT, so nothing is lost
silently.

The brick is ProseMirror, built once into ``bretzel/render/_vendor/``
(``scripts/prosemirror/``) and loaded only by a page that has an editor
(92 KB compressed). Nothing of it shows in this API: the brick can change
without an app noticing. The browser part — the schema, the keys, the
paste, the dialect — lives in ``components/inputs/editor/editor.js``.

The value travels under the bound field's name (``value=reply.text`` →
``text``), else ``name=``: a handler takes it like any field.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from functools import cache, lru_cache
from typing import Any, ClassVar

import mistune

from bretzel.components.actions.button import Button
from bretzel.components.actions.icon_button import IconButton
from bretzel.components.base import Component, ComponentUsageError, reactive_prop
from bretzel.components.base.commands import ValueCommands
from bretzel.components.base.composition import unwrap_transparent
from bretzel.components.base.field_wiring import hidden_carrier_attrs, relocate_handlers
from bretzel.components.base.focus import FocusCommands
from bretzel.components.base.scope_wiring import scope_literal
from bretzel.components.inputs._wiring import ghost_frame
from bretzel.components.inputs.editor.theme import EDITOR_THEME, VARIANTS
from bretzel.components.inputs.input import Input
from bretzel.components.inputs.message_input import MessageInputTool
from bretzel.components.overlay.popover import Popover
from bretzel.core.base_path import with_base
from bretzel.core.tree import Element, HtmlNode, Node
from bretzel.render import prosemirror_asset, route_for, text
from bretzel.runtime.protocol import DATA_BZ_CLIENT_DOM

#: The formatting commands of the bar, in their order: the name the
#: runtime runs (its tooltip is the text ``editor.<name>``) and the icon.
#: Fixed — the same bar everywhere.
COMMANDS: tuple[tuple[str, str], ...] = (
    ("bold", "bold"),
    ("italic", "italic"),
    ("bullet_list", "list"),
    ("ordered_list", "list-ordered"),
)


class _PreviewRenderer(mistune.HTMLRenderer):
    """An image stays its text, as in the browser: the editor shows none."""

    def image(self, text: str, url: str, title: str | None = None) -> str:
        return f"![{text}]({mistune.util.escape(url)})"


@cache
def _preview_parser() -> mistune.Markdown:
    """The server's reading of the value, for the first paint only.

    The same dialect as the browser's: paragraphs, lists, emphasis, links,
    line breaks — the rest stays text. ``escape=True`` and mistune's
    ``safe_url`` keep markup and ``javascript:`` out."""
    md = mistune.create_markdown(renderer=_PreviewRenderer(escape=True))
    md.block.rules = [r for r in md.block.rules if r in ("list", "ref_link", "blank_line")]
    md.inline.rules = [r for r in md.inline.rules if r in (
        "escape", "emphasis", "link", "auto_link", "auto_email", "linebreak", "softbreak")]
    return md


@lru_cache(maxsize=256)
def preview_html(markdown: str) -> str:
    """The HTML the surface shows until ProseMirror takes over — no
    flash of raw Markdown, no jump of height while the brick loads.
    Cached: a zone refreshed around an unchanged editor re-reads nothing."""
    return str(_preview_parser()(markdown)) if markdown else ""


class Editor(ValueCommands, FocusCommands, Component):
    """A text field that formats — bold, italic, lists, links — and whose value is Markdown."""

    THEME: ClassVar[dict[str, Any]] = EDITOR_THEME
    THEME_KEY: ClassVar[str] = "editor"
    #: Draws its children itself (its tools, in the bar): a zone among
    #: them is refused (``base/composition.unwrap_transparent``).
    _COMPOSES_CHILDREN: ClassVar[bool] = True
    COLLECTION_OWNER: ClassVar[str | None] = "author"
    BINDABLE_PROPS: ClassVar[tuple[str, ...]] = ("value",)
    IMPERATIVE: ClassVar[tuple[str, ...]] = ("set", "clear", "insert", "focus", "blur")
    # Where ``autofocus=`` / ``.focus()`` land: the text ProseMirror edits.
    FOCUS_TARGET: ClassVar[tuple[str, ...] | None] = ("[contenteditable]",)
    EVENTS: ClassVar[tuple[str, ...]] = ("change",)

    value: str | None = reactive_prop(default=None, emit_attr=False, writes=True,
                                      names_field=True)
    placeholder: str | None = reactive_prop(default=None, emit_attr=False)
    disabled: bool = reactive_prop(default=False, emit_attr=False)
    name: str | None = reactive_prop(default=None, emit_attr=False)
    variant: str = reactive_prop(default="surface", emit_attr=False, steps=VARIANTS)

    def __init__(
        self,
        *,
        value: Any = None,
        placeholder: str | None = None,
        disabled: bool | None = None,
        name: str | None = None,
        variant: str | None = None,
        on_change: Callable[..., Any] | str | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(value=value, placeholder=placeholder, disabled=disabled, name=name,
                         variant=variant, on_change=on_change, **kwargs)

    def _needs_identity(self) -> bool:
        return True

    # ── Imperative API ─────────────────────────────────────────────────

    def insert(self, markdown: str) -> str:
        """Insert ``markdown`` at the cursor (at the end when the editor
        never had it). Always a DOM dispatch: where the cursor is, only
        the browser knows."""
        return self._dispatch_command("bz-insert", value=markdown)

    # ── Render ─────────────────────────────────────────────────────────

    def render(self) -> Element:
        slots = self._resolved_theme()["slots"]
        disabled = bool(self._reactive_values.get("disabled"))
        raw = self._reactive_values.get("value")
        initial = raw if isinstance(raw, str) else ""
        binding = self._binding_metadata.get("value")
        scope_key = self._scope_keys("value")[0]
        binding_path = self.path_of(binding) if binding is not None else None

        root_attrs = self.emit_attrs()
        relocated: dict[str, Any] = {}
        relocate_handlers(root_attrs, {"change": relocated})
        root_attrs["class"] = self.compose_class("root")
        root_attrs["data-bz-editor"] = ""
        root_attrs["data-bz-editor-src"] = with_base(route_for(prosemirror_asset()))
        if disabled:
            root_attrs["data-disabled"] = ""
        # The methods live once in ``$bz.editor.scope``; ``_surface`` is
        # filled by the ``bz-init`` (a scope method has no ``$refs``).
        root_attrs["bz-data"] = scope_literal(
            "$bz.editor.scope",
            cell=scope_key,
            initial=json.dumps(initial),
            binding_path=binding_path,
            server_synced=self._value_server_backed("value"),
            fields={"_surface": "null"},
        )
        root_attrs["bz-init"] = "_surface = $refs.bzsurface; _boot($el)"
        # A value written from outside (a server reset, ``.set()``, another
        # control on the same ClientState) is shown; ``_follow`` ignores
        # what the editor itself published.
        root_attrs["bz-effect"] = "_follow()"
        # ``.set()`` / ``.insert()`` dispatch at the editor (its id); the
        # link field inside it must not take them for its own.
        root_attrs["bz-on:bz-set"] = "if ($event.target === $el) _write($event.detail.value)"
        root_attrs["bz-on:bz-insert"] = "if ($event.target === $el) insert($event.detail.value)"

        placeholder = self._reactive_values.get("placeholder")
        surface_attrs: dict[str, Any] = {
            "class": ghost_frame(self, slots["surface"]),
            "bz-ref": "bzsurface",
            # ProseMirror writes this node's DOM: a morph leaves it whole.
            DATA_BZ_CLIENT_DOM: "",
            "role": "textbox",
            "aria-multiline": "true",
            "aria-label": text("editor.label"),
        }
        if placeholder:
            surface_attrs["data-bz-placeholder"] = placeholder
        if not initial:
            surface_attrs["data-empty"] = ""
        surface = Element(tag="div", attrs=surface_attrs,
                          children=(HtmlNode(preview_html(initial)),) if initial else ())

        field_name = self._reactive_values.get("name") or self._derive_field_name()
        hidden = hidden_carrier_attrs(binding_path or scope_key, initial=initial,
                                      ref="bzvalue")
        if field_name:
            hidden["name"] = str(field_name)
        if disabled:
            hidden["disabled"] = True
        hidden.update(relocated)

        return Element(tag=self._tag, attrs=root_attrs, children=(
            self._toolbar(slots, disabled),
            surface,
            Element(tag="input", attrs=hidden, children=()),
            *self._event_carrier_nodes(),
        ))

    def _toolbar(self, slots: dict[str, str], disabled: bool) -> Element:
        """The formatting commands, the link panel, then the author's tools."""
        buttons: list[Node] = [
            Component.render_detached(self._command_button(name, icon, disabled))
            for name, icon in COMMANDS
        ]
        buttons.append(Component.render_detached(self._link_panel(slots, disabled)))

        # ``unwrap_transparent``: a tool inside a ``@refreshable`` zone is
        # still a tool — it goes to the bar, its zone around it.
        tools: list[Node] = []
        for wrapped in self._children:
            child, rewrap = unwrap_transparent(wrapped, self)
            opener = getattr(child, "_trigger", None)
            tool = child if isinstance(child, EditorTool) else opener
            if not isinstance(tool, EditorTool):
                raise ComponentUsageError(
                    "ui.editor holds ui.editor_tool buttons (or an overlay whose trigger "
                    f"is one), not {type(child).__name__}: its text is its value, and "
                    "the rest of the screen goes around it.")
            # An editor switched off switches its tools off with it.
            tool._within_disabled = disabled
            node = child.render() if child is tool else self._render_one(child)
            if node is not None:
                tools.append(rewrap(node))
        if tools:
            buttons.append(Element(tag="span", attrs={"class": slots["separator"],
                                                      "aria-hidden": "true"}, children=()))
            buttons.extend(tools)
        return Element(tag="div", attrs={
            "class": ghost_frame(self, slots["toolbar"]), "role": "toolbar",
            "aria-label": text("editor.toolbar")}, children=tuple(buttons))

    @staticmethod
    def _command_button(name: str, icon: str, disabled: bool) -> IconButton:
        label = text(f"editor.{name}")
        return IconButton(icon, variant="ghost", size="sm", type="button", disabled=disabled,
                          tooltip=label, aria_label=label,
                          attrs={"data-bz-editor-command": name, "aria-pressed": "false"})

    def _link_panel(self, slots: dict[str, str], disabled: bool) -> Popover:
        """The link button and its panel: an address, « Appliquer », and a
        button that takes the link away. The panel goes to ``<body>``, so
        it names its editor (``data-bz-editor-for``)."""
        panel = Popover(trigger=self._command_button("link", "link", disabled),
                        position="bottom", align="start", attrs={"data-bz-editor-link": ""})
        # The popover's own ``autofocus`` rule puts the caret in the address
        # when it opens.
        address = Input(placeholder=text("editor.link_placeholder"), size="sm",
                        autofocus=True,
                        attrs={"data-bz-editor-link-url": "",
                               "aria-label": text("editor.link_address")})
        apply = Button(text("editor.link_apply"), size="sm", type="button",
                       attrs={"data-bz-editor-link-apply": ""})
        remove = IconButton("unlink", variant="ghost", size="sm", type="button",
                            tooltip=text("editor.link_remove"),
                            aria_label=text("editor.link_remove"),
                            attrs={"data-bz-editor-link-remove": ""})
        panel._children[:] = [Element(tag="div", attrs={
            "class": slots["link"], "data-bz-editor-for": self.id}, children=(
                Component.render_detached(address),
                Component.render_detached(apply),
                Component.render_detached(remove),
            ))]
        return panel


class EditorTool(MessageInputTool):
    """A button of one's own in the bar of an :class:`Editor`.

    The bar tool of :class:`MessageInputTool` — its label, its icon (bindable),
    its tooltip, switched off with its editor — at the size of the editor's
    formatting buttons."""

    THEME_KEY: ClassVar[str] = "editor_tool"
    _BUTTON_SIZE: ClassVar[str | None] = "sm"


__all__ = ["Editor", "EditorTool"]
