"""``TagsInput`` — free values typed as tags, helped by suggestions.

The recipients of a mail, the guests of an event, the labels of a task:
values one TYPES, each becoming a tag inside the field, on the line one
keeps typing on. Not a :class:`Combobox`: a combobox picks in a closed
list it opens on click; here the list is only a help, shown while typing.

::

    ui.tags_input(value=mail.to, options=contacts, on_search=search,
                  render=contact_row, pattern=EMAIL,
                  placeholder="Add someone")

- ``value`` — the list of values (strings), two-way.
- ``options`` — the known values as ``(value, label)`` (or a string, or a
  dict, as everywhere): the suggestions, and the label a tag shows when
  its value is known (« Sophie Martin » rather than the address).
- ``on_search`` — called with what is typed (``query``), after a pause,
  so the app can change ``options`` (its address book, the directory).
- ``render`` — draws one suggestion, ``(value, label)``. What it draws is
  the app's: a text without ``size=`` follows the field's step (it
  inherits the row's), a component given a size or a colour keeps them.
- ``pattern`` — what a valid typed value is (``ui.input``'s word: the
  whole value must match). An invalid value is still ADDED, in red, the
  reason in its tooltip — it is the app that refuses it, at send time.

Typing: Enter, Tab, ``;`` and ``,`` turn what is typed into a tag (Enter
and Tab take the highlighted suggestion first); pasting
``a@x.fr; b@y.fr`` makes two; leaving the field keeps what was typed. The
suggestions open from the first letter, never on a click, and skip what
is already a tag; Up / Down move, Enter takes. Backspace in the empty
field selects the last tag, a second removes it. A double click on a tag
puts it back into text to correct it. The tooltip of a tag shows its
value (the full address).

Accessibility: the input is a ``combobox`` over the ``listbox`` of
suggestions; the tags are a ``list``, each cross named « Remove … »; an
``aria-live`` region says what was added or removed.

``COLLECTION_OWNER = "component"``: the suggestions are rendered by the
server from ``options=`` (hence ``render=``); the tags are cloned by the
browser from the value (``bz-for``), and carry only text.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterable
from typing import Any, ClassVar

from bretzel.components.base import Component, reactive_prop
from bretzel.components.base.class_composition import merge_app_classes
from bretzel.components.base.commands import ValueCommands
from bretzel.components.base.field_wiring import (
    hidden_carrier_attrs,
    relocate_aria,
    relocate_handlers,
    trigger_event,
)
from bretzel.components.base.focus import FocusCommands
from bretzel.components.base.overlay_wiring import anchored_dismiss_init, anchored_panel
from bretzel.components.base.scope_wiring import bool_attr, scope_literal
from bretzel.components.feedback.badge.theme import BADGE_THEME
from bretzel.components.inputs._picker import (
    badge_pill_classes,
    field_text_pill,
    normalise_option,
    option_body,
)
from bretzel.components.inputs._wiring import ghost_frame
from bretzel.components.inputs.tags_input.theme import TAGS_INPUT_THEME
from bretzel.components.primitives.icon import Icon
from bretzel.core.text import fold
from bretzel.core.tree import Element, Node
from bretzel.render import template, text


class TagsInput(ValueCommands, FocusCommands, Component):
    """Free values typed as tags inside the field, helped by suggestions."""

    THEME: ClassVar[dict[str, Any]] = TAGS_INPUT_THEME
    THEME_KEY: ClassVar[str] = "tags_input"
    COLLECTION_OWNER: ClassVar[str | None] = "component"
    IS_CONTAINER: ClassVar[bool] = False
    BINDABLE_PROPS: ClassVar[tuple[str, ...]] = ("value", "disabled")
    IMPERATIVE: ClassVar[tuple[str, ...]] = ("set", "clear", "add", "focus", "blur")
    FOCUS_TARGET: ClassVar[tuple[str, ...] | None] = ("input[type=text]",)
    EVENTS: ClassVar[tuple[str, ...]] = ("change", "focus", "blur", "search")
    EMPTY_VALUE: ClassVar[Any] = ()
    #: A server ``on_search=`` waits for a pause in the typing.
    SEARCH_DEBOUNCE_MS: ClassVar[int] = 200
    DOM_EVENTS: ClassVar[dict[str, str]] = {
        "search": f"input changed delay:{SEARCH_DEBOUNCE_MS}ms"}

    name: str | None = reactive_prop(default=None, emit_attr=False)
    value: Any = reactive_prop(default=None, emit_attr=False, writes=True, names_field=True)
    placeholder: str | None = reactive_prop(default=None, emit_attr=False)
    pattern: str | None = reactive_prop(default=None, emit_attr=False)
    disabled: bool = reactive_prop(default=False, emit_attr=False)
    color: str = reactive_prop(default="primary", emit_attr=False)
    size: str = reactive_prop(default="md", emit_attr=False)
    #: The look of the field, the words of ``ui.button``: ``surface`` (the
    #: default) is the framed field; ``ghost`` has neither background nor
    #: frame — the container around it structures the screen (the lines
    #: of a mail) — and its focus ring only for a keyboard user
    #: (``data-bz-keyboard`` on ``<html>``, set by ``helpers.js``).
    variant: str = reactive_prop(default="surface", emit_attr=False,
                                 steps=("surface", "ghost"))

    def __init__(
        self,
        options: Iterable[Any] = (),
        *,
        render: Callable[[Any, Any], Any] | None = None,
        value: Any = None,
        pattern: str | None = None,
        placeholder: str | None = None,
        name: str | None = None,
        disabled: bool | None = None,
        color: str | None = None,
        size: str | None = None,
        variant: str | None = None,
        on_change: Callable[..., Any] | str | None = None,
        on_focus: Callable[..., Any] | str | None = None,
        on_blur: Callable[..., Any] | str | None = None,
        on_search: Callable[..., Any] | str | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(
            value=value, pattern=pattern, placeholder=placeholder, name=name,
            disabled=disabled, color=color, size=size, variant=variant,
            on_change=on_change, on_focus=on_focus, on_blur=on_blur,
            on_search=on_search, **kwargs,
        )
        self._options = list(options)
        self._render = render

    def add(self, value: str) -> str:
        """Add one tag — or several, split as a paste is (``;``, ``,``)."""
        return self._dispatch_command("bz-add", value=str(value))

    # ── Render ─────────────────────────────────────────────────────────

    def render(self) -> Element:
        size_map = self._size_row() or {}
        disabled = bool(self._reactive_values.get("disabled"))
        placeholder = self._reactive_values.get("placeholder") or ""
        pattern = self._reactive_values.get("pattern") or None

        options_data = []
        for opt_value, opt_label, _disabled in (normalise_option(o) for o in self._options):
            v_str, l_str = str(opt_value), str(opt_label)
            norm_label, norm_value = fold(l_str), fold(v_str)
            options_data.append({
                "value": v_str, "label": l_str,
                "haystack": norm_label if norm_label == norm_value
                else f"{norm_label} {norm_value}",
            })
        raw = self._reactive_values.get("value")
        if raw is None or raw == "":
            initial: list[str] = []
        elif isinstance(raw, (list, tuple, set)):
            initial = [str(v) for v in raw]
        else:
            initial = [str(raw)]
        # The labels of the tags already there: options change with each
        # search, a tag keeps the name it was given.
        known = {o["value"]: o["label"] for o in options_data}
        labels = {v: known[v] for v in initial if v in known and known[v] != v}

        value_binding = self._binding_metadata.get("value")
        value_expr = self.path_of(value_binding) if value_binding is not None else "value"

        root_attrs = self.emit_attrs()
        to_hidden: dict[str, Any] = {}
        to_input: dict[str, Any] = {}
        to_search: dict[str, Any] = {}
        server_event = trigger_event(root_attrs)
        relocate_handlers(root_attrs, {
            "change": to_hidden, "focus": to_input, "blur": to_input,
            "search": (to_search, "input"),
        })
        relocate_aria(root_attrs, to_input)
        if server_event == "search":
            to_search["hx-trigger"] = "input changed " + (
                self._trigger_modifier or f"delay:{self.SEARCH_DEBOUNCE_MS}ms")
            to_search["hx-include"] = (
                f"#{self.id} input[bz-ref=bzquery], #{self.id} input[bz-ref=bzhidden]")

        name = (self._reactive_values.get("name") or self._derive_field_name()
                or ("value" if to_hidden else None))
        hidden_nodes: list[Node] = []
        if name or to_hidden:
            hidden_attrs: dict[str, Any] = hidden_carrier_attrs(
                f"JSON.stringify({value_expr} || [])", initial=json.dumps(initial))
            if name:
                hidden_attrs["name"] = str(name)
            hidden_attrs.update(to_hidden)
            hidden_nodes.append(Element(tag="input", attrs=hidden_attrs, children=()))
        if to_search:
            hidden_nodes.append(Element(tag="input", attrs={
                **hidden_carrier_attrs("query", ref="bzquery", dispatch=None),
                "name": "query",
            }, children=()))

        bz_data = scope_literal(
            "$bz.tagsInput.scope",
            cell="value",
            initial=json.dumps(initial),
            binding_path=value_expr if value_binding is not None else None,
            server_synced=self._value_server_backed("value"),
            bound_read="v == null ? [] : v",
            fields={
                "open": "false", "query": "''", "_highlight": "-1",
                "_selected": "''", "_said": "''",
                # Never seeded by the server: a field whose server value
                # moves is re-adopted at the next refresh, and a search
                # would wipe the names of the tags already picked.
                "_labels": "{}",
            },
            config={
                "_known": json.dumps(labels, ensure_ascii=False),
                "_options": json.dumps(options_data, ensure_ascii=False),
                "_pattern": json.dumps(pattern),
                "_texts": json.dumps({
                    "invalid": text("tags_input.invalid"),
                    "added": template("tags_input.added"),
                    "removed": template("tags_input.removed"),
                }, ensure_ascii=False),
            },
        )

        tags = self._render_tags(size_map)
        panel_id = f"{self.id}-suggestions"
        input_attrs: dict[str, Any] = {
            "type": "text",
            "class": self.compose_class("input"),
            "role": "combobox",
            "aria-autocomplete": "list",
            "aria-controls": panel_id,
            "bz-attr:aria-expanded": bool_attr("open"),
            "autocomplete": "off",
            "bz-ref": "bzinput",
            "bz-attr:value": "query",
            "bz-on:input": "query = $event.target.value; _typed()",
            # The list shows on focus and on click — not when the PAGE gives
            # the focus (``autofocus=``, a dialog opening on it).
            "bz-on:focus": "if (!$bz.helpers.pageGivesFocus()) _typed()",
            "bz-on:click": "_typed()",
            "bz-on:keydown": "_key($event)",
            "bz-on:paste": "_paste($event)",
            "bz-on:blur": "_commit()",
        }
        if placeholder:
            input_attrs["bz-attr:placeholder"] = (
                f"_picked().length ? '' : {json.dumps(placeholder, ensure_ascii=False)}")
            input_attrs["placeholder"] = "" if initial else placeholder
        if disabled:
            input_attrs["disabled"] = True
        # The component's own ``blur`` / ``focus`` / ``input`` first, then
        # the caller's.
        for own, extra in (("bz-on:blur", to_input), ("bz-on:focus", to_input),
                           ("bz-on:input", to_search)):
            if own in extra:
                extra[own] = f"{input_attrs[own]}; {extra[own]}"
        input_attrs.update(to_input)
        input_attrs.update(to_search)
        self.forward_binding("disabled", input_attrs, root_attrs=root_attrs)

        trigger_attrs: dict[str, Any] = {
            "class": ghost_frame(self, self.compose_class("trigger")),
            "bz-ref": "bztrigger",
            "bz-on:click": "$refs.bzinput && $refs.bzinput.focus()",
        }
        trigger = Element(tag="div", attrs=trigger_attrs, children=(
            Element(tag="div", attrs={"class": self.compose_class("tags_row")},
                    children=(tags, Element(tag="input", attrs=input_attrs, children=()))),
        ))

        option_class = self.compose_class("option")
        options_nodes: list[Node] = []
        for index, opt in enumerate(options_data):
            options_nodes.append(Element(tag="button", attrs={
                "type": "button", "role": "option", "tabindex": "-1",
                "data-bz-value": opt["value"], "data-bz-i": str(index),
                "class": option_class, "aria-selected": "false",
                "bz-show": f"_shows({index})",
            }, children=option_body(self._render, opt["value"], opt["label"])))
        panel = anchored_panel(
            css=self.compose_class("panel"),
            children=tuple(options_nodes),
            role="listbox",
            match_width=True,
            extra_effect="$bz.combobox.paintOptions($el, _highlight, () => false)",
            attrs={
                "id": panel_id,
                "data-bz-opt-active": self.compose_class("option_active"),
                # A press on a suggestion must not take the focus from the
                # input: its blur would turn the half-typed text into a tag.
                "bz-on:mousedown": "$event.preventDefault()",
                "bz-on:click": (
                    "((o) => { if (o) _choose(+o.getAttribute('data-bz-i')); })"
                    "($bz.combobox.optionOf($event))"),
                "bz-on:mouseover": (
                    "((o) => { if (o) _highlight = +o.getAttribute('data-bz-i'); })"
                    "($bz.combobox.optionOf($event))"),
            },
        )
        live = Element(tag="span", attrs={
            "class": "sr-only", "aria-live": "polite", "bz-text": "_said",
        }, children=())

        root_attrs["class"] = self.compose_class("root", apply_variant_size_modifiers=False)
        root_attrs["bz-data"] = bz_data
        # The names the server knows for the tags already there, kept for
        # good: a later search sends other options.
        root_attrs["bz-init"] = "_remember(); " + anchored_dismiss_init("open")
        root_attrs["bz-on:bz-set"] = "_setValue($event.detail.value)"
        root_attrs["bz-on:bz-add"] = "_add(String($event.detail.value))"
        return Element(tag=self._tag, attrs=root_attrs,
                       children=(*hidden_nodes, trigger, panel, live))

    def _render_tags(self, size_map: dict[str, Any]) -> Element:
        """The tags: one badge per value, cloned by the browser."""
        pill_class, close_class = badge_pill_classes(
            size=size_map.get("pill_size", "sm"),
            badge_theme=self._resolved_theme("badge", BADGE_THEME),
        )
        # Its letters are the size of the text typed beside them.
        pill_class = field_text_pill(pill_class, size_map.get("input", ""))
        remove_label = json.dumps(template("tags_input.remove"), ensure_ascii=False)
        remove = Element(tag="button", attrs={
            "type": "button", "tabindex": "-1",
            # The badge's own cross: its contrast is the badge's text's.
            "class": close_class,
            "bz-attr:aria-label": f"{remove_label}.replace('{{text}}', _labelOf(v))",
            "bz-on:click": "$event.stopPropagation(); _remove(v); $refs.bzinput.focus()",
        }, children=(Component.render_detached(
            Icon("x", size=size_map.get("remove_icon_size", "xs"))),))
        tag = Element(tag="span", attrs={
            "role": "listitem",
            # The app's ``slots={"tag": …}`` wins over the badge's classes too.
            "class": merge_app_classes(f"{pill_class} {self.compose_class('tag')}",
                                       self._slot_addition("tag")),
            "data-bz-tip-root": "",
            "bz-attr:data-bz-tip": "_tipOf(v)",
            "bz-attr:aria-invalid": bool_attr("!_valid(v)"),
            "bz-attr:data-selected": bool_attr("_selected === v"),
            "bz-on:dblclick": "_edit(v); $refs.bzinput.focus()",
        }, children=(
            Element(tag="span", attrs={"class": "truncate", "bz-text": "_labelOf(v)"}, children=()),
            remove,
        ))
        return Element(tag="div", attrs={"class": "contents", "role": "list"}, children=(
            Element(tag="template", attrs={"bz-for": "v in _picked() :key=v"}, children=(tag,)),
        ))


__all__ = ["TagsInput"]
