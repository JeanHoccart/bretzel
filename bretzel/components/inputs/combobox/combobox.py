"""``Combobox`` — search-as-you-type select with optional multi-pick.

Sits between :class:`Input` (free text) and :class:`Select` (closed
list) — the user types to **filter** a known list of options and
either picks one (single mode) or builds a list of picks rendered
as removable pills (multi mode).

Two value shapes :

- **single** (``multiple=False``, default) : ``value`` is a string,
  the picked option's id. Empty string ``""`` means no pick.
- **multiple** (``multiple=True``) : ``value`` is a list of strings.
  Picks render as removable pills inside the trigger ; pills can
  be removed by the inline ``×`` or by hitting Backspace on an
  empty input. Optional ``bulk_actions=True`` adds Select-all /
  Clear buttons to the panel footer, under the list.

``trigger=`` — the widget without its text field :

  By default the search field IS the trigger (that is what a
  type-ahead is). Pass ``trigger=`` any component and the roles
  split : your component opens the panel, and the search field
  moves to the top of the panel ::

      ui.combobox(STATUSES, value=picked, multiple=True,
                  bulk_actions=True,
                  trigger=ui.button("Status", icon_left="list-filter"))

  That is the *filter* shape — you open it, then you tick — as
  opposed to the *picker* shape, which you drive by typing. Same
  panel, same list, same bulk actions ; only the way in changes.
  In this mode the panel drops the trigger pills (the caller's
  trigger says what is picked) and no longer matches the trigger's
  width (a 80px button would give a 80px panel). In multi mode each
  option carries a checkbox on its left — a list you tick reads as
  one — and the panel offers Clear as soon as something is picked.
  The search field only shows past ``SEARCH_ABOVE`` options : five
  values need no search, and the field would sit between the
  reader and the list for nothing.

``creatable=True`` — a value not in the list :

  Typing a text no option says (label or value, case and accents
  folded) offers a last row « Create "…" ». Picking it — a click, or
  Enter when it is highlighted or no option is left — makes the typed
  text the value (a pill in multi mode), and ``on_change`` fires as for
  any pick. Enter keeps its meaning: it picks the first filtered option
  first. A value in no option then shows as itself (only in this mode:
  an unknown id does not show in clear). What to do with a new value —
  store it as a place, a tag — is the app's: the server receives the
  text ::

      ui.combobox(places, value=event.location, name="location",
                  creatable=True)

Filter strategy (v1, non-configurable) :
- Fold both query and (label + value) with the framework's one ``fold``
  (``bretzel/core/text.py``, browser twin ``$bz.fold``): case- and
  accent-insensitive.
- Split the normalised query on whitespace → tokens.
- An option matches iff EVERY token is a substring of its
  normalised haystack.
- Options keep their declared order (no scoring / re-ranking in v1).

The full options list ships server-side. Filtering runs client-side
— zero network round-trip per keystroke. Suitable for lists up to a
few thousand options. Async loading (server-side ``fetch`` callback)
is deferred to a future version.

Keyboard a11y :
- Tab focuses the input.
- ArrowDown / ArrowUp move the keyboard highlight through the
  CURRENTLY-VISIBLE options (skipping filtered-out ones).
- Enter picks the highlighted option ; in multi mode the input
  clears after each pick so the user can keep typing.
- Escape closes the panel without changing the value.
- Backspace on an empty input (multi mode) pops the last pill.

Form integration : when ``value`` is a binding, ``AUTONAME_FROM
= "value"`` derives the HTML ``name`` from the field. Multi values
ride a JSON-stringified hidden input (single round-trip recovery
via ``json.loads`` on the server).

Imperative API (cf. ``imperative-api.md`` § Combobox) :

- ``.set(value)`` — write-through binding if any, else DOM dispatch.
- ``.clear()`` — sugar for ``.set("")`` (single) or ``.set([])`` (multi).
- ``.focus()`` / ``.blur()`` — direct DOM commands targeting the
  inner ``<input>`` via ``querySelector('input[type=text]')``.
- ``.select_all()`` / ``.deselect_all()`` — multi-mode only ; pick
  every visible option / clear all picks. Bound to the bulk-actions
  buttons internally ; also callable from external triggers.

Runtime notes (twin of Select) :

- ``scope.absorb`` **invokes** ``decl[key]`` at registration, so any
  ``get foo() {…}`` freezes to a constant — every getter is a flat
  method (``_value()``). The whole client behaviour lives inline in the
  ``bz-data`` scope, keyed by ``bz-id`` so it survives morph natively.
- ``bz-on`` carries no modifier grammar, so per-key handlers collapse
  into one ``bz-on:keydown`` with ``$event.key`` guards and inlined
  ``preventDefault()`` / ``stopPropagation()``.
- The anchored panel rides the shared overlay wiring
  (``anchored_panel_effect`` + ``dispatch_root_effect`` +
  ``anchored_dismiss_init``, search input as the floating anchor).
- Scope methods can't reach ``$refs`` / ``$el``, so pick/set just
  ``_write`` the value ; the SINGLE change dispatcher is a
  ``_change_emit_effect`` on the hidden input (which fires no native
  ``change``), dispatching whenever the value mutates.
- ``on_search=`` relocates onto the search input's native ``input``
  event ; a callable handler's ``hx-trigger`` is re-pinned to ``input``
  (with the configured debounce) and a second hidden input named
  ``query`` mirrors the live query for FormData.
- ``on_close=`` is the ONLY handler that stays on the root : the
  ``close`` event is dispatched there by ``dispatch_root_effect`` on the
  ``open`` transition. It is what a multi-pick panel wants when the
  picks must land in ONE request rather than one per tick — the reader
  ticks freely, the server hears about it on the way out. The value
  rides the hidden input, which the root ``<div>`` would NOT post on its
  own — so wiring ``on_close=`` also stamps the ``hx-include`` that
  reaches it. Nothing to remember at the call site.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterable
from typing import Any, ClassVar

from bretzel.components.base import (
    Component,
    reactive_prop,
    stamp_display_none,
)
from bretzel.components.base.arguments import has_content, shown
from bretzel.components.base.field_wiring import change_emit_effect as _change_emit_effect
from bretzel.components.base.field_wiring import (
    relocate_aria,
    relocate_handlers,
    retrigger,
    trigger_event,
)
from bretzel.components.base.focus import FocusCommands
from bretzel.components.base.overlay_wiring import (
    CHANGED_FLAG,
    FILL_WIDTH_RE,
    anchored_dismiss_init,
    anchored_panel,
    anchored_trigger_wrapper,
    changed_since_open_effect,
    dispatch_root_effect,
    imperative_listeners,
    install_open_close_toggle,
    trigger_is_full_width,
)
from bretzel.components.base.scope_wiring import bool_attr, scope_literal
from bretzel.components.base.theme_values import theme_context
from bretzel.components.feedback.badge.theme import BADGE_THEME
from bretzel.components.inputs._picker import (
    badge_pill_classes,
    build_footer_bar,
    build_header_bar,
    build_pills_template,
    has_picks,
    normalise_option,
    option_body,
    option_check,
    option_classes,
    render_x_icon,
)
from bretzel.components.inputs._wiring import ChoiceCommands
from bretzel.components.inputs.combobox.theme import COMBOBOX_THEME
from bretzel.components.primitives.icon import Icon
from bretzel.core.text import fold
from bretzel.core.tree import Element, Node
from bretzel.render import template, text
from bretzel.state.scopes.client import ClientBinding

#: Pre-bakes the per-option haystack: the framework's one ``fold``
#: (``bretzel/core/text.py``), whose browser twin ``$bz.fold`` folds the
#: query — same string on both sides, or a typed word misses its option.
_normalise_text = fold


# ───────────────────────────────────────────────────────────────────────────
# Combobox
# ───────────────────────────────────────────────────────────────────────────


def shrink_fit_wrapper(root_cls: str) -> str:
    """The other direction : a ``w-full`` root that must hug its trigger.

    :func:`expand_fit_wrapper` serves the overlays, whose root defaults to
    ``w-fit`` and must GROW for a full-width trigger. A form control
    defaults to ``w-full`` (a field fills its row) and has the symmetric
    problem the day it stops being a field : ``ui.combobox(trigger=…)``
    wraps the caller's « Status » button, and ``w-full`` stretches it
    across the toolbar.

    SUBSTITUTED, never appended, for the same reason the sibling strips :
    ``w-full w-fit`` resolves in an order Tailwind does not promise, so
    the loser is decided by stylesheet position rather than by intent.
    """
    return root_cls.replace("w-full", "w-fit")


def trigger_asks_full_width(component: Any, triggers: list[Any]) -> bool:
    """Does anything ask this wrapper to fill its row ?

    Two sources, and BOTH matter — that is the whole point of the helper.
    :func:`trigger_is_full_width` reads the trigger ; a caller can also
    ask on the wrapper itself, and does so through two different doors :
    ``classes="w-full"`` (``_user_classes_str``) and ``class_=`` /
    ``attrs={"class": …}`` (``_raw_class_str``, appended after render by
    the universal-modifier pass). Checking only the first silently shrank
    a combobox whose caller had used the second.
    """
    for source in (component._user_classes_str(), component._raw_class_str):
        # Same word, same trap: a caller who writes
        # ``classes="max-w-full"`` asks for a CEILING, not a width.
        if FILL_WIDTH_RE.search(source or ""):
            return True
    return trigger_is_full_width(triggers)


class Combobox(ChoiceCommands, FocusCommands, Component):
    """Search-as-you-type select with single / multi modes."""

    THEME: ClassVar[dict[str, Any]] = COMBOBOX_THEME
    THEME_KEY: ClassVar[str] = "combobox"
    #: It is the COMPONENT that owns the loop: it iterates ``options=``
    #: and renders one ``<button role="option">`` per entry, on the
    #: SERVER side. The author does not write that loop, so they have
    #: nowhere to put their markup — hence ``render=``, their only entry
    #: point.
    #:
    #: ⚠️ Not ``"client"``, despite the JS filter: the filter is a
    #: ``bz-show``, it HIDES already rendered buttons and creates none.
    #: The distinction reads in one word of vocabulary — ``bz-for`` clones
    #: (that is ``file_upload``), ``bz-show`` hides.
    #: Cf. ``Component.COLLECTION_OWNER``.
    COLLECTION_OWNER: ClassVar[str | None] = "component"
    IS_CONTAINER: ClassVar[bool] = False
    # Curated reactive surface — picked value + lock flag.
    BINDABLE_PROPS: ClassVar[tuple[str, ...]] = ("value", "disabled")
    #: ``open`` / ``close`` / ``toggle``, as on the six pickers: Combobox
    #: is an anchored panel carrying a value — exactly their shape — and a
    #: single shape has a single convention.
    IMPERATIVE: ClassVar[tuple[str, ...]] = (
        "open", "close", "toggle",
        "set", "clear", "focus", "blur",
        "select_all", "deselect_all",
    )
    # Where ``autofocus=`` / ``.focus()`` land: the search field.
    FOCUS_TARGET: ClassVar[tuple[str, ...] | None] = ("input[type=text]",)
    EVENTS: ClassVar[tuple[str, ...]] = (
        "change", "focus", "blur", "search", "close",
    )
    # Debounce (ms) for a callable ``on_search=`` server handler so a
    # POST doesn't fire on every keystroke. A subclass can override.
    SEARCH_DEBOUNCE_MS: ClassVar[int] = 200
    # What a carrier (a second server handler) listens to: the search, as
    # its own handler would — a typed query, after a pause.
    DOM_EVENTS: ClassVar[dict[str, str]] = {
        "search": f"input changed delay:{SEARCH_DEBOUNCE_MS}ms"}
    # A detached panel (``trigger=``) shows its search field only past
    # this many options. Below, the field stays in the DOM, invisible and
    # read-only : it still holds the keyboard (arrows, Enter, Escape).
    SEARCH_ABOVE: ClassVar[int] = 8

    name: str | None = reactive_prop(default=None, emit_attr=False)
    value: Any = reactive_prop(default=None, emit_attr=False, writes=True, names_field=True)
    placeholder: str | None = reactive_prop(default=None, emit_attr=False)
    multiple: bool = reactive_prop(default=False, emit_attr=False)
    bulk_actions: bool = reactive_prop(default=False, emit_attr=False)
    # Typing a value no option says offers « Create « … » » — the value
    # becomes the typed text.
    creatable: bool = reactive_prop(default=False, emit_attr=False)
    # ``None`` and not the English sentence: a ``reactive_prop``
    # default is evaluated at the module's IMPORT, so before an app has
    # declared its language — it would freeze English. The value is read
    # at render.
    empty_text: str | Component | None = reactive_prop(default=None, emit_attr=False)
    disabled: bool = reactive_prop(default=False, emit_attr=False)
    required: bool = reactive_prop(default=False, emit_attr=False)
    color: str = reactive_prop(default="primary", emit_attr=False)
    size: str = reactive_prop(default="md", emit_attr=False)

    def __init__(
        self,
        options: Iterable[Any] = (),
        *,
        render: Callable[[Any, Any], Any] | None = None,
        value: Any = None,
        multiple: bool | None = None,
        bulk_actions: bool | None = None,
        creatable: bool | None = None,
        empty_text: str | Component | None = None,
        name: str | None = None,
        placeholder: str | None = None,
        trigger: Component | None = None,
        disabled: bool | None = None,
        required: bool | None = None,
        color: str | None = None,
        size: str | None = None,
        on_change: Callable[..., Any] | str | None = None,
        on_focus: Callable[..., Any] | str | None = None,
        on_blur: Callable[..., Any] | str | None = None,
        on_search: Callable[..., Any] | str | None = None,
        on_close: Callable[..., Any] | str | None = None,
        **kwargs: Any,
    ) -> None:
        # Direct forward: the base layer drops reactive None kwargs (keeps the default).
        super().__init__(
            name=name, value=value,
            placeholder=placeholder,
            multiple=multiple,
            bulk_actions=bulk_actions,
            creatable=creatable,
            empty_text=empty_text,
            disabled=disabled, required=required,
            color=color, size=size,
            on_change=on_change,
            on_focus=on_focus,
            on_blur=on_blur,
            on_search=on_search,
            on_close=on_close,
            **kwargs,
        )
        self._options = list(options)
        self._render = render
        self._trigger: Component | None = trigger
        # AFTER `super().__init__`: the installer reads `_binding_metadata`.
        install_open_close_toggle(self)

    # ── Render ─────────────────────────────────────────────────────────

    def render(self) -> Element:
        _theme, slots, _sizes, _size_key, _color = theme_context(self)
        # The row's settings (glyph and pill tokens, ``panel_free``); its
        # classes reach the slots through ``compose_class``.
        size_map = self._size_row() or {}
        is_multi = bool(self._reactive_values.get("multiple"))
        bulk_actions = bool(self._reactive_values.get("bulk_actions"))
        disabled = bool(self._reactive_values.get("disabled"))
        required = bool(self._reactive_values.get("required"))
        placeholder = self._reactive_values.get("placeholder") or ""
        # ``shown``: a bound empty text is drawn live; ``has_content``
        # because a binding refuses ``or``.
        empty_text = shown(self, "empty_text")
        if not has_content(empty_text):
            empty_text = text("combobox.empty")
        # ``trigger=`` splits the two roles the text field plays by
        # default (open the panel / type to filter) : the caller's
        # component opens, and the field moves INTO the panel.
        detached = self._trigger is not None
        # Detached, a short list keeps its field out of sight (cf.
        # ``SEARCH_ABOVE``).
        creatable = bool(self._reactive_values.get("creatable"))
        # ``creatable`` needs somewhere to type: it keeps the field.
        searchable = (not detached or creatable
                      or len(self._options) > self.SEARCH_ABOVE)

        # ── Resolve options + pre-bake the normalised haystack ──────
        # Each option becomes (value, label, disabled, haystack)
        # where haystack is ``norm(label) + " " + norm(value)`` —
        # built once server-side so the JS filter only does a
        # token-by-token substring check.
        normalised = [
            normalise_option(opt) for opt in self._options
        ]
        options_data = []
        for opt_value, opt_label, opt_disabled in normalised:
            v_str = str(opt_value)
            l_str = str(opt_label)
            # The label THEN the value, except when they normalise
            # alike — which is the common case: ``options=["open",
            # "merged"]`` gives label == value, and the haystack came out
            # as "open open". It pays TWICE (in ``_options``, and in each
            # option's ``bz-show``), so that is ~4 × the value per
            # option, for nothing.
            #
            # Deduplicating changes NO verdict: ``_matches`` tests
            # ``haystack.includes(token)`` on tokens split at spaces, so
            # none can straddle the join — the only place where "X X"
            # says yes when "X" says no.
            norm_label = _normalise_text(l_str)
            norm_value = _normalise_text(v_str)
            haystack = (
                norm_label if norm_label == norm_value
                else f"{norm_label} {norm_value}"
            )
            options_data.append(
                {
                    "value": v_str,
                    "label": l_str,
                    "disabled": bool(opt_disabled),
                    "haystack": haystack,
                }
            )
        options_js = json.dumps(options_data, ensure_ascii=False)

        # ── Resolve the value binding ───────────────────────────────
        value_binding = self._binding_metadata.get("value")
        raw_initial = self._reactive_values.get("value")
        if is_multi:
            if raw_initial is None or raw_initial == "":
                initial_value: Any = []
            elif isinstance(raw_initial, (list, tuple, set)):
                initial_value = [str(v) for v in raw_initial]
            else:
                initial_value = [str(raw_initial)]
        else:
            initial_value = str(raw_initial or "")

        # Two read/write expressions because the runtime's evaluation
        # context differs by surface :
        # - **directives** (``bz-attr:value``, ``bz-class``,
        #   ``bz-show``, ``bz-text``) are wrapped with
        #   ``with($scope) { return expr }`` → bare ``value`` resolves
        #   to the local scope's field.
        # - **method shorthand bodies** (``_pick(v) { ... }``) are NOT
        #   wrapped → bare ``value`` would create a global on
        #   ``window`` instead of touching ``this.value``.
        # ``"value"`` bare: a directive context.
        value_expr = (
            self.path_of(value_binding) if value_binding is not None else "value"
        )

        # ── Resolve event relocations ───────────────────────────────
        # change → hidden input, focus/blur → inner input.
        root_attrs = self.emit_attrs()
        relocated_to_hidden: dict[str, Any] = {}
        relocated_to_input: dict[str, Any] = {}
        relocated_to_input_search: dict[str, Any] = {}
        server_event = trigger_event(root_attrs)
        # ``on_search=`` is exposed as a native ``input`` event on the
        # inner text field, so the caller can mirror the query into state
        # or trigger a fetch.
        relocate_handlers(root_attrs, {
            "change": relocated_to_hidden,
            "focus": relocated_to_input,
            "blur": relocated_to_input,
            "search": (relocated_to_input_search, "input"),
        })
        # Name, description and validity name the FOCUSABLE element (the
        # search input), not the wrapper.
        relocate_aria(root_attrs, relocated_to_input)
        if server_event == "search":
            # A POST per keystroke, debounced: the caller's ``debounce=``
            # beats the component's default.
            relocated_to_input_search["hx-trigger"] = "input changed " + (
                self._trigger_modifier or f"delay:{self.SEARCH_DEBOUNCE_MS}ms"
            )
            # The search input has no name and sits in no form: this brings
            # the ``query`` mirror and the value, as ``on_close=`` brings the
            # value below.
            relocated_to_input_search["hx-include"] = (
                f"#{self.id} input[bz-ref=bzquery], #{self.id} input[bz-ref=bzhidden]"
            )

        # ── Hidden inputs — form integration + change dispatch ──────
        # For multi the picked value ships as JSON-stringified array.
        derived_name = self._derive_field_name()  # reused by value_server_backed below
        fallback = "value" if relocated_to_hidden else None
        name = self._reactive_values.get("name") or derived_name or fallback
        # ``_serverSync`` re-adopts ``value`` from the server on a
        # @refreshable swap — ONLY when the value is server-backed
        # (``value=server_state.field``, a stamp carrying a
        # ``field_name``). An unbound / literal combobox owns its value
        # client-side : re-adopting the SSR initial on every swap would
        # WIPE the user's pick + fire a phantom ``change`` (empty value)
        # when an unrelated handler refreshes the section. Same fix as
        # Select (cf. traps.md). Binding mode never emits ``_serverSync``.
        # ``derived_name`` (above) already carries the field_name stamp in
        # local mode — reuse it rather than re-reading the value.
        # A single rule — cf. Component._value_server_backed (the
        # autoname does not answer this question: it lost
        # ``[state.field]``).
        value_server_backed = self._value_server_backed("value")

        hidden_nodes: list[Node] = []
        if name or relocated_to_hidden:
            if is_multi:
                value_directive = (
                    f"JSON.stringify({value_expr} || [])"
                )
                value_initial_str = json.dumps(
                    [str(v) for v in initial_value]
                )
            else:
                value_directive = f"String({value_expr})"
                value_initial_str = str(initial_value or "")
            hidden_attrs: dict[str, Any] = {
                "type": "hidden",
                "bz-ref": "bzhidden",
                "value": value_initial_str,
                "bz-attr:value": value_directive,
                # A hidden input fires no native ``change`` — this
                # effect dispatches one whenever the bound value mutates
                # so the relocated change handler / hx-post fires.
                "bz-effect": _change_emit_effect(value_directive),
            }
            if name:
                hidden_attrs["name"] = str(name)
            hidden_attrs.update(relocated_to_hidden)
            hidden_nodes.append(
                Element(tag="input", attrs=hidden_attrs, children=())
            )
        # Second hidden input — exposes the live ``query`` field to
        # any wired ``on_search=`` handler. Only emitted when the
        # caller actually wants the search event ; otherwise pure
        # overhead.
        if relocated_to_input_search:
            query_hidden = Element(
                tag="input",
                attrs={
                    "type": "hidden",
                    "bz-ref": "bzquery",
                    "name": "query",
                    "value": "",
                    "bz-attr:value": "query",
                },
                children=(),
            )
            hidden_nodes.append(query_hidden)

        # ── bz-data : state + filter + pick helpers ─────────────────
        # The ~30 normalise / filter / nav / pick methods live ONCE in
        # ``combobox.js``: a shared ``$bz.combobox.common`` (filter +
        # nav) plus the mode's ``.single`` / ``.multi``. The instance
        # emits its data; ``_options`` (each entry carries its label and
        # its pre-normalised haystack) is server config, re-seeded so a
        # list reloaded at every refresh does not stay frozen. A bound
        # ``_read`` null-guards so the factory's ``_value()`` gets
        # ``[]`` / ``''`` instead of ``null``.
        empty_js = "[]" if is_multi else "''"
        bz_data = scope_literal(
            "$bz.combobox.common",
            "$bz.combobox.multi" if is_multi else "$bz.combobox.single",
            cell="value",
            initial=json.dumps(initial_value),
            binding_path=value_expr if value_binding is not None else None,
            server_synced=value_server_backed,
            bound_read=f"v == null ? {empty_js} : v",
            fields={"open": "false", "query": "''", "_highlight": "-1"},
            config={"_options": options_js,
                    **({"_creatable": "true"} if creatable else {})},
        )

        # ── Trigger : pills (multi only) + input + clear + chevron ──
        trigger_class = self.compose_class("trigger")
        input_class = self.compose_class("input")

        # Trigger pills (multi only, CLOSED state). When the panel is
        # open the picks move to the panel header (the ``header_bar``
        # slot, built by ``_build_header_bar`` — there is no
        # "selected_bar" anywhere in the repository
        # below the input) so the trigger becomes a clean search
        # field. Pattern : Notion / Linear / GitHub user picker.
        #
        # We wrap the pills in a ``contents`` div so the wrapper is
        # transparent to the flex layout of ``pills_row`` ; ``bz-show``
        # on the wrapper hides ALL the pills at once when ``open``.
        pills_children: list[Node] = []
        if is_multi and not detached:
            # Pill styling sourced from :data:`BADGE_THEME` so the
            # multi-picker pills track the canonical Badge visual
            # identity. Drop in a Badge theme tweak (radius, padding,
            # color recipe) and the Combobox pills inherit it for
            # free — no duplicate maintenance burden.
            badge_pill_class, badge_remove_class = badge_pill_classes(
                size=size_map.get("pill_size", "sm"),
                badge_theme=self._resolved_theme("badge", BADGE_THEME),
            )
            pill_template = build_pills_template(
                pill_class=badge_pill_class,
                remove_class=badge_remove_class,
            )
            pills_wrapper_attrs: dict[str, Any] = {
                "class": "contents",
                "bz-show": "!open",
            }
            # FOUC pre-stamp : the wrapper is hidden only when ``open``
            # is true at SSR — but the panel starts CLOSED, so the
            # pills are visible at first paint. No pre-stamp needed.
            pills_children.append(
                Element(
                    tag="div",
                    attrs=pills_wrapper_attrs,
                    children=(pill_template,),
                )
            )
        # The inner <input type="text">.
        # **Display logic** (decoupled from value state) :
        #   - OPEN  : input shows ``query`` — clean search field.
        #   - CLOSED single : input shows the label of the picked
        #     value (so the trigger looks like a regular input with
        #     a value).
        #   - CLOSED multi  : input is empty ; pills next to it
        #     carry the visual.
        # A two-way ``bz-model="query"`` would freeze the input
        # value to the typing buffer regardless of open/closed —
        # we use ``bz-attr:value`` + ``bz-on:input`` instead to
        # compute the display ourselves.
        if detached:
            # Detached : the field only ever exists inside an OPEN
            # panel, so there is no "closed" display to compute — it
            # shows the query, full stop.
            value_display_expr = "query"
        elif is_multi:
            value_display_expr = "open ? query : ''"
        else:
            # ``_value()`` is the mode-aware reader (local field OR
            # binding path) — a method works in any surface, unlike a
            # bare ``value`` which only resolves the local field in
            # literal mode. ``_labelOf`` reads the label in
            # ``_options``, which already carries it, so there is no
            # ``_labels`` map.
            value_display_expr = "open ? query : _labelOf(_value())"
        # Keyboard handler — every per-key handler is fused into ONE
        # ``bz-on:keydown`` with explicit ``$event.key`` guards + inlined
        # ``preventDefault()`` (the runtime has no modifier grammar).
        # Mirrors Select's fused keydown.
        if is_multi:
            backspace_branch = (
                "else if (k === 'Backspace') { "
                "if (!this.query && this._picked().length) "
                "{ this._removeLast(); } }"
            )
        else:
            # Single mode : leave the default text-delete behaviour.
            backspace_branch = ""
        keydown_handler = (
            "const k = $event.key; "
            "if (k === 'ArrowDown') { $event.preventDefault(); "
            "open = true; _moveHighlight(1); } "
            "else if (k === 'ArrowUp') { $event.preventDefault(); "
            "open = true; _moveHighlight(-1); } "
            "else if (k === 'Enter') { $event.preventDefault(); "
            "_pickHighlighted(); } "
            "else if (k === 'Escape') { open = false; } "
            + backspace_branch
        )
        input_attrs: dict[str, Any] = {
            "type": "text",
            # Unsearchable : out of sight and read-only, so typing filters
            # nothing the reader cannot see — but still focused on open,
            # so the arrows, Enter and Escape keep working.
            "class": input_class if searchable else "sr-only",
            "bz-attr:value": value_display_expr,
            "bz-on:input": "query = $event.target.value; open = true",
            "bz-ref": "bzinput",
            "bz-on:keydown": keydown_handler,
        }
        if not detached:
            # Opening the panel : clear the search buffer so the user
            # starts fresh, and signal open. Both focus and the
            # trigger's click route here.
            #
            # Detached : the field lives INSIDE the panel, so it can only
            # be focused once the panel is already open — and re-focusing
            # it (after a Tab out and back) would wipe a query the reader
            # is still using. Only the click guard remains, so a click on
            # the field isn't read as a click-outside dismiss.
            #
            # Not when the PAGE gives the focus (``autofocus=``, a dialog
            # opening on it): the list would cover what follows before
            # anyone asked for it (``$bz.helpers.pageGivesFocus``).
            input_attrs["bz-on:focus"] = (
                "if (!$bz.helpers.pageGivesFocus()) { open = true; query = '' }"
            )
            input_attrs["bz-on:click"] = (
                "$event.stopPropagation(); open = true; query = ''"
            )
        else:
            input_attrs["bz-on:click"] = "$event.stopPropagation()"
        # Placeholder strategy :
        # - Single mode : static ``placeholder`` attribute. The
        #   browser hides it automatically when the input has a
        #   value (which happens when CLOSED + picked → label shows
        #   via bz-attr:value), so no extra logic needed.
        # - Multi mode : use ``bz-attr:placeholder`` reactive.
        #   Suppressed when the trigger is CLOSED + has picks (pills
        #   already fill the area, a tiny "Pick countries" hint
        #   squeezed between them is just noise). Kept when no picks
        #   OR when open (search hint while typing).
        # - Detached : static too. The "pills already fill the area"
        #   argument is about the trigger, and there is no trigger left
        #   to crowd — the field is alone at the top of the panel.
        if placeholder or is_multi:
            placeholder_text = placeholder or ""
            if is_multi and not detached:
                input_attrs["bz-attr:placeholder"] = (
                    f"(_hasPicked() && !open) ? '' : "
                    f"{json.dumps(placeholder_text)}"
                )
            elif placeholder:
                input_attrs["placeholder"] = placeholder
        if not searchable:
            input_attrs["readonly"] = True
        if disabled:
            input_attrs["disabled"] = True
        if required:
            input_attrs["required"] = True
        # Combine (don't overwrite) when a user-relocated client-string
        # ``on_focus=`` handler targets the same event as the input's
        # own internal "open panel + clear search buffer" wiring. A
        # blind ``dict.update`` here would silently destroy
        # ``open = true; query = ''`` — the panel would never open on
        # focus once a user handler is wired to the same event.
        # Internal logic runs FIRST so the panel state is consistent
        # before the caller's expression sees it. Server callables
        # never collide here — they route through ``hx-*``/
        # ``data-bz-sig`` (SERVER_ACTION_ATTRS), never a
        # ``bz-on:<event>`` key.
        if "bz-on:focus" in relocated_to_input and "bz-on:focus" in input_attrs:
            relocated_to_input["bz-on:focus"] = (
                f"{input_attrs['bz-on:focus']}; {relocated_to_input['bz-on:focus']}"
            )
        input_attrs.update(relocated_to_input)
        # Same rule for the search: if the caller's ``on_search`` expression
        # replaced the component's own ``query = …; open = true``, the
        # query would stop following the typing, the list would stop
        # filtering and the server would receive « query= ». The
        # component's first, then the caller's.
        if "bz-on:input" in relocated_to_input_search and "bz-on:input" in input_attrs:
            relocated_to_input_search["bz-on:input"] = (
                f"{input_attrs['bz-on:input']}; {relocated_to_input_search['bz-on:input']}"
            )
        input_attrs.update(relocated_to_input_search)
        # Reactive disabled : route the binding to the actual input.
        # ``forward_binding`` handles ClientBinding — the runtime's
        # bz-attr directive evaluates the ``$bz.state.<path>`` form.
        self.forward_binding("disabled", input_attrs, root_attrs=root_attrs)

        search_field = Element(tag="input", attrs=input_attrs, children=())

        # ── Trigger : the caller's, or the default search shell ──────
        search_row: Element | None = None
        if detached:
            # The bordered shell is NOT re-invented for the panel : the
            # ``trigger`` slot IS that shell, and it follows the widget
            # into the panel with its border, its focus ring and its
            # size row intact — including the ``w-full`` that makes it
            # span the header bar.
            if searchable:
                search_row = Element(
                    tag="div",
                    attrs={"class": trigger_class},
                    children=(search_field,),
                )
            # Shared ``contents`` wrapper (Popover / Dropdown use the
            # same one) : ``anchored_panel_effect`` probes that display
            # to anchor on the caller's real box rather than on a
            # zero-size wrapper. The click body is ours — toggle, then
            # hand the keyboard to the search field. ``$nextTick``
            # because the panel is ``display:none`` until the panel
            # effect flushes, and focusing a hidden input is a no-op.
            detached_trigger = anchored_trigger_wrapper(
                self._trigger.render(),
                open_expr="open", haspopup="listbox",
                on_click=(
                    "open = !open; query = ''; if (open) $nextTick("
                    "() => $refs.bzinput && $refs.bzinput.focus())"
                ),
            )
            trigger_attrs = dict(detached_trigger.attrs)
            trigger_children: tuple[Node, ...] = detached_trigger.children
        else:
            pills_children.append(search_field)
            pills_row = Element(
                tag="div",
                attrs={"class": slots.get("pills_row", "")},
                children=tuple(pills_children),
            )

            # Clear button — only meaningful when there's a value.
            clear_attrs: dict[str, Any] = {
                "type": "button",
                "class": slots.get("clear", ""),
                "aria-label": text("combobox.clear"),
                "tabindex": "-1",
                "bz-on:click": "$event.stopPropagation(); _clearAll()",
                "bz-show": "_hasPicked()",
            }
            if not has_picks(initial_value, is_multi=is_multi):
                stamp_display_none(clear_attrs)
            clear_btn = Element(
                tag="button",
                attrs=clear_attrs,
                children=(
                    render_x_icon(size_map.get("clear_icon_size", "xs")),
                ),
            )

            chevron = self._render_chevron(
                slots.get("chevron", ""),
                size_map.get("chevron_size", "sm"),
            )

            trigger_attrs = {
                "class": trigger_class,
                "role": "combobox",
                "aria-haspopup": "listbox",
                "bz-attr:aria-expanded": bool_attr("open"),
                # The search input is the floating anchor.
                "bz-ref": "bztrigger",
                **({"aria-labelledby": relocated_to_input["aria-labelledby"]}
                   if "aria-labelledby" in relocated_to_input else {}),
                # Click anywhere on the shell focuses the input —
                # makes the whole bordered area feel like one widget.
                "bz-on:click": "$refs.bzinput && $refs.bzinput.focus()",
            }
            trigger_children = (pills_row, clear_btn, chevron)
        # Disabled : the trigger is a ``<div>`` (no native ``disabled``
        # attribute), so — like Select's multi trigger — expose
        # ``aria-disabled`` for screen readers and neutralise the
        # focus-the-input click. The inner search input already carries the
        # real ``disabled``. Handles both the static prop and a ClientBinding.
        if disabled:
            trigger_attrs["aria-disabled"] = "true"
            trigger_attrs["bz-on:click"] = ""
        if isinstance(self._binding_metadata.get("disabled"), ClientBinding):
            self.forward_binding(
                "disabled", trigger_attrs, as_attr="aria-disabled",
            )
        trigger = Element(
            tag="div",
            attrs=trigger_attrs,
            children=trigger_children,
        )

        # ── Panel : header + options + empty + footer ──────────────
        # The header (sticky top) carries the picks as pills — or, when
        # the caller took the trigger over, the relocated search field :
        # the field rides INSIDE the header rather than above it so the
        # panel keeps ONE sticky block at the top. A detached panel too
        # short to search keeps its invisible field, and no header.
        #
        # The footer (sticky bottom) carries the commands : the counter,
        # Select all with ``bulk_actions``, and Clear — which a detached
        # multi panel offers on its own, since a filter is opened to tick
        # and untick.
        panel_children: list[Node] = []
        if not searchable:
            panel_children.append(search_field)
        else:
            panel_children.append(build_header_bar(
                self,
                badge_theme=self._resolved_theme("badge", BADGE_THEME),
                initial_value=initial_value, is_multi=is_multi,
                lead=search_row,
            ))
        # The filter shape's checkbox : one node, the same for every
        # option (its checked state is CSS off the option's
        # ``aria-selected``), so it is built once.
        option_box = (
            self._render_option_box(size_map)
            if is_multi and detached else None
        )

        option_class_base = option_classes(
            self, is_multi=is_multi,
        )
        if option_box is not None:
            # ``group`` : the option's ``aria-selected`` paints its box.
            option_class_base = f"{option_class_base} group"
        option_active_cls = self.compose_class("option_active")
        option_selected_cls = self.compose_class("option_selected")

        for index, opt in enumerate(options_data):
            opt_v_js = json.dumps(opt["value"])
            haystack_js = json.dumps(opt["haystack"])
            label_str = opt["label"]
            # ⚠️ ``bz-class``, ``bz-attr:aria-selected`` and the two
            # ``bz-on:`` are not on this option, where they would be
            # copied identically N times. They live ONCE on the panel:
            # one effect that repaints, two delegated listeners.
            #
            # ``bz-show`` STAYS per option: it is the search filter, and
            # the runtime has its own hiding machinery (anti-FOUC guard
            # included).
            #
            # ``aria-selected`` is set at SSR in addition to being
            # repainted: the accessibility tree must be right at the
            # first paint, before the effect runs.
            picked_at_ssr = opt["value"] in (
                initial_value if isinstance(initial_value, list)
                else [initial_value]
            )
            opt_attrs: dict[str, Any] = {
                "type": "button",
                "role": "option",
                # The form-data value the option represents — distinct
                # from the user-facing label. Standard ARIA listbox.
                "data-bz-value": opt["value"],
                # The index, read by the delegated hover to set
                # ``_highlight``. The keyboard already uses it.
                "data-bz-i": str(index),
                "class": option_class_base,
                "aria-selected": "true" if picked_at_ssr else "false",
                "bz-show": f"_matches({haystack_js})",
            }
            if opt["disabled"]:
                opt_attrs["disabled"] = True
            # Multi: a tick on the right says "picked". The accent
            # text alone is colour only, and a list picked through
            # would read as no selection at all.
            opt_children: tuple[Node, ...] = option_body(self._render,
                opt["value"], label_str
            )
            if option_box is not None:
                opt_children = (option_box, *opt_children)
            elif is_multi:
                opt_children += (option_check(
                    self,
                    picked_js=f"_isPicked({opt_v_js})",
                    initially_picked=opt["value"] in (
                        initial_value if isinstance(initial_value, list) else []
                    ),
                ),)
            panel_children.append(
                Element(
                    tag="button",
                    attrs=opt_attrs,
                    children=opt_children,
                )
            )

        # ``creatable`` — the « Create « … » » row, LAST of the options:
        # ``paintOptions`` lights the n-th ``[role=option]`` for
        # ``_highlight === n``, and the scope puts it at
        # ``_options.length``. Shown while ``_createText()`` says what
        # would be created (nothing typed, or an option already says it:
        # hidden). Its words travel as a template, filled in the browser.
        if creatable:
            create_attrs: dict[str, Any] = {
                "type": "button",
                "role": "option",
                "data-bz-create": "",
                "class": option_class_base,
                "aria-selected": "false",
                "bz-show": "_createText()",
            }
            stamp_display_none(create_attrs)
            create_js = json.dumps(template("combobox.create"), ensure_ascii=False)
            panel_children.append(Element(
                tag="button",
                attrs=create_attrs,
                children=(Element(
                    tag="span",
                    attrs={"bz-text": f"{create_js}.replace('{{text}}', _createText())"},
                    children=(),
                ),),
            ))

        # Empty state — shown when filter returns 0 visible options (and,
        # ``creatable``, nothing to create: the row above takes its place).
        # Hidden at SSR (every option visible with an empty query).
        empty_attrs: dict[str, Any] = {
            "class": self.compose_class("empty"),
            "bz-show": "_visibleCount() === 0 && !_createText()",
        }
        stamp_display_none(empty_attrs)
        panel_children.append(
            Element(
                tag="div",
                attrs=empty_attrs,
                children=(self.emit_text_slot(empty_text),),
            )
        )
        if is_multi and (bulk_actions or detached):
            panel_children.append(self._build_footer_bar(
                options_data=options_data, initial_value=initial_value,
                select_all=bulk_actions,
            ))

        # ── Anchored panel ───────────────────────────────────────────
        # ``bz-ref="bzpanel"`` + the shared ``anchored_panel_effect``
        # toggles display + attaches ``$bz.helpers.floating`` against
        # the ``bztrigger`` ref. FOUC pre-stamp keeps it hidden before
        # the runtime boots (the panel is open=false at SSR).
        # ``match_width`` pins the panel to the trigger's width — right
        # when the trigger IS the field, wrong when it's a small button
        # (an 80px « Status » would give an 80px panel). Detached, the
        # panel sizes itself off a ``min-w`` floor instead.
        # Detached, ``panel_free`` REPLACES the size row rather than adding
        # to it : it carries its own ``max-h``, tall enough for
        # ``SEARCH_ABOVE`` options plus the footer — a five-value filter
        # that scrolls hides its last value under the footer. Two ``max-h``
        # on one element would be settled by Tailwind's order, not ours.
        panel_class = (
            " ".join(p for p in (
                self.compose_class("panel", apply_variant_size_modifiers=False),
                size_map.get("panel_free", ""),
            ) if p)
            if detached else self.compose_class("panel")
        )
        # Two effects composed: the anchoring, then the painting of the options.
        panel = anchored_panel(
            css=panel_class,
            children=tuple(panel_children),
            role="listbox",
            match_width=not detached,
            extra_effect="$bz.combobox.paintOptions($el, _highlight, (v) => _isPicked(v))",
            attrs={
                # The two class strings travel ONCE here, instead of being
                # copied into each option's ``bz-class``.
                "data-bz-opt-active": option_active_cls,
                "data-bz-opt-picked": option_selected_cls,
                # The click ALWAYS goes through ``_togglePick``, in both
                # modes: multi flips membership in the array, single
                # deselects when you re-click the already picked option. It
                # is the use one expects of a stateful selection control.
                # Enter (keyboard) calls ``_pick`` in single mode — Enter
                # CONFIRMS the highlighted one, it does not toggle.
                #
                # The click and the hover, DELEGATED. ⚠️ ``mouseover`` and
                # not ``mouseenter``: the latter DOES NOT BUBBLE, so it
                # cannot be delegated — a ``bz-on:mouseenter`` on the panel
                # would never see the options.
                # The « Create » row (``creatable``) answers the same two.
                "bz-on:click": (
                    "((o) => { if (o) { $event.stopPropagation(); "
                    "if (o.hasAttribute('data-bz-create')) _create(); "
                    "else _togglePick(o.getAttribute('data-bz-value')); } })"
                    "($bz.combobox.optionOf($event))"
                ),
                "bz-on:mouseover": (
                    "((o) => { if (o) _highlight = "
                    "o.hasAttribute('data-bz-create') ? _options.length "
                    ": +o.getAttribute('data-bz-i'); })"
                    "($bz.combobox.optionOf($event))"
                ),
            },
        )

        # ── Root assembly ───────────────────────────────────────────
        root_attrs["class"] = self.compose_class(
            "root", apply_variant_size_modifiers=False,
        )
        # A form field fills its row ; a filter button hugs its label.
        # Detached, the root wraps the CALLER's component, so ``w-full``
        # would stretch a « Status » button across its whole toolbar.
        # ``shrink_fit_wrapper`` is the twin of the overlays'
        # ``expand_fit_wrapper`` — same question, opposite default.
        if detached and not trigger_asks_full_width(self, [self._trigger]):
            root_attrs["class"] = shrink_fit_wrapper(root_attrs["class"])
        root_attrs["bz-data"] = bz_data
        # ── Root wiring : open/close dispatch + dismiss ──────────────
        #
        # - ``dispatch_root_effect`` fires ``open`` / ``close`` events
        #   on transition (no scroll lock — an anchored panel doesn't
        #   trap the page).
        # - ``anchored_dismiss_init`` registers Escape + click-outside
        #   dismiss. No carrier capture — ``change`` is dispatched by the
        #   hidden input's own ``_change_emit_effect``, not by a scope
        #   method.
        root_attrs["bz-effect"] = dispatch_root_effect("open")
        # ── ``on_close=``: send nothing if nothing moved ─────────────
        #
        # Opening a panel to SEE what it offers, then closing it, is a
        # normal gesture — and it cost a full round trip plus a zone
        # re-render. The HTMX event filter (``close[…]``) gates the
        # REQUEST, not the event: ``close`` still fires, so a client-side
        # ``on_close="…"`` still sees it. It is the right cut — "the
        # panel closed" stays true, only the server action becomes
        # conditional.
        if server_event == "close":
            root_attrs["bz-effect"] = (
                changed_since_open_effect("open", "_picked()")
                + "; " + root_attrs["bz-effect"]
            )
            # ``retrigger``: the event filter replaces the event, not
            # the modifiers that follow it.
            root_attrs["hx-trigger"] = retrigger(
                root_attrs.get("hx-trigger", ""), f"close[this.{CHANGED_FLAG}]"
            )
        root_attrs["bz-init"] = anchored_dismiss_init("open")

        # ── Imperative-API listeners ─────────────────────────────────
        #
        # External ``combobox.set('a')`` / ``.clear()`` /
        # ``.select_all()`` dispatch a ``bz-set`` (with ``detail.value``)
        # or a valueless ``bz-*`` CustomEvent on the wrapper ``<div>``
        # by id. The event bubbles ; the wrapper's listener runs inside
        # the bz-data scope and reuses the canonical setters
        # (``_setValue`` / ``_selectAll`` / ``_clearAll``), which
        # ``_write`` the value ; the hidden input's
        # ``_change_emit_effect`` observes the write and fires change.
        # ── ``on_close=`` : carry the value the handler came for ─────
        #
        # The root is a ``<div>``, and a ``<div>`` posts NO descendant
        # field of its own — a close handler would arrive with an empty
        # body and read nothing. So the component stamps the
        # ``hx-include`` itself, exactly as RadioGroup does for the same
        # reason (``radio.py`` § "on_change value vide"). Scoped by
        # ``bz-ref`` and not by ``input[type=hidden]`` : a wired
        # ``on_search=`` renders a SECOND hidden input (``query``), and
        # the broad selector would sweep it into the close POST.
        #
        # ``setdefault`` so an explicit ``attrs={"hx-include": …}`` still
        # wins — a caller pulling in a field of their own is a legitimate
        # escape hatch, and silently overriding it would be the worse
        # surprise.
        if server_event == "close" and name:
            root_attrs.setdefault(
                "hx-include", f"#{self.id} input[bz-ref=bzhidden]",
            )

        # The open/close/toggle receivers — without them, `.open()`
        # would dispatch an event nobody listens to.
        for _ev, _handler in imperative_listeners("open").items():
            root_attrs.setdefault(_ev, _handler)
        root_attrs["bz-on:bz-set"] = "_setValue($event.detail.value)"
        root_attrs["bz-on:bz-select-all"] = "_selectAll()"
        root_attrs["bz-on:bz-deselect-all"] = "_clearAll()"

        return Element(
            tag=self._tag,
            attrs=root_attrs,
            children=(*hidden_nodes, trigger, panel),
        )

    # ── Render sub-helpers ────────────────────────────────────────────

    def _render_chevron(self, chevron_class: str, icon_size: str) -> Element:
        # ``with_slot_class``: clones + prepends the slot class without
        # overwriting the child's. Same as select. The rotation is in the
        # slot (``in-aria-expanded:``), not in a ``bz-class``.
        return Component.with_slot_class(
            Component.render_detached(Icon("chevron-down", size=icon_size)),
            chevron_class,
        )

    def _render_option_box(self, size_map: dict[str, str]) -> Element:
        """The filter shape's checkbox, on the left of an option.

        Painted by CSS alone (``group-aria-selected:``) off the option's
        ``aria-selected``, which SSR stamps and ``paintOptions`` repaints
        — no directive per option, and no flicker before the runtime
        boots. ``aria-hidden`` : the option already says it is selected.
        """
        return Element(
            tag="span",
            attrs={
                "class": self.compose_class("option_box"),
                "aria-hidden": "true",
            },
            children=(Component.render_detached(
                Icon("check", size=size_map.get("box_icon_size", "xs")),
            ),),
        )

    def _build_footer_bar(
        self,
        *,
        options_data: list[dict[str, Any]],
        initial_value: list[str],
        select_all: bool,
    ) -> Element:
        """The shared footer. Combobox compares against the VISIBLE
        options: the query hides some, so "select all" stays offered as
        long as one visible unpicked one remains — and not on a list
        filtered to empty, hence the ``c === 0`` term."""
        return build_footer_bar(
            self,
            total_options=len(options_data), initial_value=initial_value,
            usable_values=[o["value"] for o in options_data
                           if not o["disabled"]],
            select_all=select_all,
            select_all_done_js=(
                "((c) => c === 0 || _picked().length >= c)(_visibleCount())"
            ),
        )


__all__ = ["Combobox"]
