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
  Deselect-all buttons to the panel header.

``trigger=`` — the widget without its text field :

  By default the search field IS the trigger (that is what a
  type-ahead is). Pass ``trigger=`` any component and the roles
  split : your component opens the panel, and the search field
  moves to the top of the panel, above the header bar ::

      ui.combobox(STATUSES, value=picked, multiple=True,
                  bulk_actions=True,
                  trigger=ui.button("Status", icon_left="list-filter"))

  That is the *filter* shape — you open it, then you tick — as
  opposed to the *picker* shape, which you drive by typing. Same
  panel, same list, same bulk actions ; only the way in changes.
  In this mode the panel drops the trigger pills (the caller's
  trigger says what is picked) and no longer matches the trigger's
  width (a 80px button would give a 80px panel).

Filter strategy (v1, non-configurable) :
- Normalise both query and (label + value) : lowercase + Unicode NFD
  + strip combining marks (diacritics-insensitive).
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
import unicodedata
from collections.abc import Callable, Iterable
from typing import Any, ClassVar

from bretzel.components.base import (
    Component,
    reactive_prop,
    stamp_display_none,
)
from bretzel.components.base._wiring import (
    CHANGED_FLAG,
    ROOT_DISPATCHED_EVENTS,
    SERVER_ACTION_ATTRS,
    anchored_dismiss_init,
    anchored_panel_effect,
    anchored_trigger_wrapper,
    bool_attr,
    changed_since_open_effect,
    dispatch_root_effect,
    imperative_listeners,
    install_open_close_toggle,
    retrigger,
    server_sync_marker,
    shrink_fit_wrapper,
    theme_context,
    trigger_asks_full_width,
    trigger_event,
)
from bretzel.components.base._wiring import (
    change_emit_effect as _change_emit_effect,
)
from bretzel.components.feedback.badge.theme import BADGE_THEME
from bretzel.components.inputs._picker import (
    badge_pill_classes,
    build_header_bar,
    build_pills_template,
    has_picks,
    normalise_option,
    option_body,
    option_check,
    render_x_icon,
    sized_slot,
)
from bretzel.components.inputs.combobox.theme import COMBOBOX_THEME
from bretzel.components.primitives.icon import Icon
from bretzel.core.tree import Element, Node
from bretzel.render import text
from bretzel.state.scopes.client import ClientBinding

# Native HTMX action attrs a callable handler lands on the root via
# ``emit_attrs`` ; relocated wholesale to the hidden input that holds
# name+value for ``change``, or onto the search input for ``search``.
_ACTION_ATTRS = SERVER_ACTION_ATTRS


def _normalise_text(text: str) -> str:
    """Lowercase + Unicode NFD + strip combining marks.

    Used server-side to pre-bake the per-option haystack. The
    client-side JS uses the equivalent recipe (``toLowerCase``,
    ``normalize('NFD')``, ``replace(/\\p{M}/gu, '')``) — same
    contract so server-baked haystacks match runtime queries.
    """
    nfd = unicodedata.normalize("NFD", text)
    return "".join(c for c in nfd if not unicodedata.combining(c)).lower()


# ───────────────────────────────────────────────────────────────────────────
# Combobox
# ───────────────────────────────────────────────────────────────────────────


class Combobox(Component):
    """Search-as-you-type select with single / multi modes."""

    THEME: ClassVar[dict[str, Any]] = COMBOBOX_THEME
    THEME_KEY: ClassVar[str] = "combobox"
    #: It is the COMPONENT that owns the loop: it iterates ``options=``
    #: and renders one ``<button role="option">`` per entry, on the
    #: SERVER side. The author does not write that loop, so they have
    #: nowhere to put their markup — hence ``render=``, their only entry
    #: point.
    #:
    #: ⚠️ Declared ``"client"`` by mistake on 2026-08-18, on a TRUNCATED
    #: reading of a ``combobox.py`` comment ("built once server-side so
    #: the JS filter only does a…"), read as "the client owns the list"
    #: while it says the opposite. The JS filter is a ``bz-show``: it
    #: HIDES already rendered buttons, it creates none. The distinction
    #: reads in one word of vocabulary — ``bz-for`` clones (that is
    #: ``file_upload``), ``bz-show`` hides.
    #: Cf. ``Component.COLLECTION_OWNER``.
    COLLECTION_OWNER: ClassVar[str | None] = "component"
    IS_CONTAINER: ClassVar[bool] = False
    # Curated reactive surface — picked value + lock flag.
    BINDABLE_PROPS: ClassVar[tuple[str, ...]] = ("value", "disabled")
    #: ⚠️ ``open`` / ``close`` / ``toggle`` added on 2026-09-03, AT THE
    #: SAME TIME as on the six pickers. Combobox is an anchored panel
    #: carrying a value — exactly their shape — and it exposed only the
    #: field half. Giving it to them without giving it to this one would
    #: have made two conventions for a single shape.
    IMPERATIVE: ClassVar[tuple[str, ...]] = (
        "open", "close", "toggle",
        "set", "clear", "focus", "blur",
        "select_all", "deselect_all",
    )
    EVENTS: ClassVar[tuple[str, ...]] = (
        "change", "focus", "blur", "search", "close",
    )
    # Debounce (ms) for a callable ``on_search=`` server handler so a
    # POST doesn't fire on every keystroke. A subclass can override.
    SEARCH_DEBOUNCE_MS: ClassVar[int] = 200

    name: str | None = reactive_prop(default=None, emit_attr=False)
    value: Any = reactive_prop(default=None, emit_attr=False, writes=True, names_field=True)
    placeholder: str | None = reactive_prop(default=None, emit_attr=False)
    multiple: bool = reactive_prop(default=False, emit_attr=False)
    bulk_actions: bool = reactive_prop(default=False, emit_attr=False)
    # ``None`` and not the English sentence: a ``reactive_prop``
    # default is evaluated at the module's IMPORT, so before an app has
    # declared its language — it would freeze English. The value is read
    # at render.
    empty_text: str | None = reactive_prop(default=None, emit_attr=False)
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
        empty_text: str | None = None,
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
        # Detached from the parent stack at CONSTRUCTION — a component
        # registers with the active parent in its own ``__init__``, and
        # without that it would paint once as a sibling before we adopt
        # it (cf. ``test_slot_adoption``). Same gesture as
        # Popover.trigger.
        self._trigger: Component | None = Component.adopt_slot(trigger)
        # AFTER `super().__init__`: the installer reads `_binding_metadata`.
        install_open_close_toggle(self)

    # ── Imperative write-only API ─────────────────────────────────────

    def set(self, value: Any) -> str:
        """Write the picked value. In multi mode, ``value`` should be
        a list ; in single mode, a scalar."""
        return self._value_command(value)

    def clear(self) -> str:
        """Clear the picked value(s). Single → ``""`` ; multi → ``[]``."""
        is_multi = bool(self._reactive_values.get("multiple"))
        return self.set([] if is_multi else "")

    def focus(self) -> str:
        return (
            f"document.getElementById('{self.id}')"
            ".querySelector('input[type=text]').focus()"
        )

    def blur(self) -> str:
        return (
            f"document.getElementById('{self.id}')"
            ".querySelector('input[type=text]').blur()"
        )

    def select_all(self) -> str:
        """Pick every CURRENTLY-VISIBLE option. Multi mode only ;
        single-mode picks no-op (you can't pick more than one)."""
        return self._dispatch_command("bz-select-all")

    def deselect_all(self) -> str:
        """Clear every pick. Sugar over ``.clear()`` — kept distinct
        for symmetry with ``.select_all()`` (and so the bulk-actions
        buttons can call it directly)."""
        return self._dispatch_command("bz-deselect-all")


    # ── Render ─────────────────────────────────────────────────────────

    def render(self) -> Element:
        _theme, slots, sizes, size_key, _color = theme_context(self)
        size_map = sizes.get(size_key, sizes.get("md", {}))
        is_multi = bool(self._reactive_values.get("multiple"))
        bulk_actions = bool(self._reactive_values.get("bulk_actions"))
        disabled = bool(self._reactive_values.get("disabled"))
        required = bool(self._reactive_values.get("required"))
        placeholder = self._reactive_values.get("placeholder") or ""
        empty_text = (
            self._reactive_values.get("empty_text") or text("combobox.empty")
        )
        # ``trigger=`` splits the two roles the text field plays by
        # default (open the panel / type to filter) : the caller's
        # component opens, and the field moves INTO the panel.
        detached = self._trigger is not None

        def _resolve(template: str) -> str:
            return template

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
        #   ``window`` instead of touching ``this.value``. Cf.
        #   ``traps.md`` § "open = false in a shorthand method of a
        #   ``bz-data`` scope".
        if value_binding is not None:
            value_expr = self.path_of(value_binding)
            value_method = value_expr  # full path works in both surfaces
        else:
            value_expr = "value"        # directive context
            value_method = "this.value"  # method shorthand context

        # ── Resolve event relocations ───────────────────────────────
        # change → hidden input, focus/blur → inner input.
        root_attrs = self.emit_attrs()
        relocated_to_hidden: dict[str, Any] = {}
        relocated_to_input: dict[str, Any] = {}
        relocated_to_input_search: dict[str, Any] = {}
        # A single server handler lands ONE HTMX bundle on the root
        # (the base enforces one ``hx-post`` per element) ; its
        # ``hx-trigger`` names the event it serves. Pop the whole
        # bundle once and route it by event — ``change`` → hidden
        # input, ``search`` → search input (re-pinned to ``input``).
        # The EVENT, not the string: ``hx-trigger`` carries the
        # modifiers of a ``debounce=`` / ``throttle=``. Comparing the
        # whole string made the three tests below fail as soon as a
        # ``debounce=`` was set, and the bundle popped below was then
        # re-stamped NOWHERE — ``hx-post`` lost, ``on_change`` dead in
        # silence.
        server_event = trigger_event(root_attrs)
        action_bundle: dict[str, Any] = {}
        # ``close`` is the exception : it is dispatched ON the root by
        # ``dispatch_root_effect``, so its bundle is already where it
        # belongs. Popping it here would strip the ``hx-post`` and put
        # it back nowhere — a silently dead ``on_close=``. The set is the
        # framework's (``_wiring.ROOT_DISPATCHED_EVENTS``), not a local
        # whitelist of what DOES move : the whitelist form has to be
        # extended by hand for every new event, and forgetting is exactly
        # the silent death it guards against.
        if ("hx-post" in root_attrs
                and server_event not in ROOT_DISPATCHED_EVENTS):
            for ev_attr in _ACTION_ATTRS:
                if ev_attr in root_attrs:
                    action_bundle[ev_attr] = root_attrs.pop(ev_attr)
        # change handler — string form rides ``bz-on:change``, the
        # callable's bundle rides the hidden input pinned to ``change``
        # (the only event a hidden input fires, via
        # ``_change_emit_effect``).
        if "bz-on:change" in root_attrs:
            relocated_to_hidden["bz-on:change"] = root_attrs.pop(
                "bz-on:change"
            )
        if server_event == "change":
            # ``hx-trigger`` travels IN ``action_bundle``: the re-pin
            # that lived here rewrote it to a bare ``"change"`` and threw
            # away the caller's ``debounce=``.
            relocated_to_hidden.update(action_bundle)
        for ev_attr in ("bz-on:focus", "bz-on:blur"):
            if ev_attr in root_attrs:
                relocated_to_input[ev_attr] = root_attrs.pop(ev_attr)
        # ``on_search=`` is exposed as a native ``input`` event on the
        # inner text field — fires on every keystroke so the caller can
        # mirror the query into state, log analytics, trigger a fetch
        # in a future async v2, etc. The string form rides
        # ``bz-on:input`` ; the callable form re-pins its ``hx-trigger``
        # to ``input`` (with the debounce HTMX understands) so it POSTs
        # per keystroke.
        if "bz-on:search" in root_attrs:
            relocated_to_input_search["bz-on:input"] = root_attrs.pop(
                "bz-on:search"
            )
        if server_event == "search":
            relocated_to_input_search.update(action_bundle)
            # ``search`` changes EVENT (``search`` → native ``input``),
            # so here the trigger really is rewritten. The caller's
            # debounce beats the component's default — otherwise
            # ``debounce=`` was accepted then ignored, which is worse
            # than refused.
            relocated_to_input_search["hx-trigger"] = "input changed " + (
                self._trigger_modifier or f"delay:{self.SEARCH_DEBOUNCE_MS}ms"
            )
        # focus / blur callable → the focusable search input (the base
        # emitted ``hx-trigger="focus"``/``"blur"`` ; keep it). Without
        # this the bundle was popped off the root above and only re-applied
        # for change / search, so a callable ``on_focus`` / ``on_blur`` was
        # silently DROPPED (no hx-post anywhere on the component).
        if server_event in ("focus", "blur"):
            relocated_to_input.update(action_bundle)

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
        bz_data = self._build_bz_data(
            is_multi=is_multi,
            value_binding=value_binding,
            value_method=value_method,
            initial_value=initial_value,
            options_js=options_js,
            server_backed=value_server_backed,
        )

        # ── Trigger : pills (multi only) + input + clear + chevron ──
        trigger_class = " ".join(
            p for p in (
                _resolve(slots.get("trigger", "")),
                size_map.get("trigger", ""),
            ) if p
        )
        input_class = " ".join(
            p for p in (
                slots.get("input", ""),
                size_map.get("input", ""),
            ) if p
        )

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
                _resolve, size=size_map.get("pill_size", "sm"),
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
            # ``_options`` — which already carries it, hence the
            # disappearance of the ``_labels`` map (2026-08-28).
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
            "class": input_class,
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
            input_attrs["bz-on:focus"] = "open = true; query = ''"
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
        if disabled:
            input_attrs["disabled"] = True
        if required:
            input_attrs["required"] = True
        # Combine (don't overwrite) when a user-relocated client-string
        # ``on_focus=`` handler targets the same event as the input's
        # own internal "open panel + clear search buffer" wiring. A
        # blind ``dict.update`` here used to silently destroy
        # ``open = true; query = ''`` — the panel would never open on
        # focus once a user handler was wired to the same event.
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
            # claim its own line in the flex-wrap header bar.
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
                "class": _resolve(slots.get("clear", "")),
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

        # ── Panel : header bar + options + empty ────────────────────
        # Single sticky header at the top of the panel that hosts
        # (left → right) :
        #   - the relocated search field, on its own line, when the
        #     caller took the trigger over
        #   - counter ``N / total`` in multi mode
        #   - picks rendered as removable pills
        #   - bulk actions (Select all / Clear) when opt-in
        # Hidden entirely when nothing to show.
        #
        # The search field rides INSIDE the header rather than above it
        # so the panel keeps ONE sticky block : two ``sticky top-0``
        # siblings would pin to the same line and one would slide under
        # the other as the option list scrolls.
        panel_children: list[Node] = []
        show_bulk = is_multi and bulk_actions
        total_options = len(options_data)
        panel_children.append(
            self._build_header_bar(
                slots=slots,
                size_map=size_map,
                resolve=_resolve,
                is_multi=is_multi,
                show_bulk=show_bulk,
                total_options=total_options,
                initial_value=initial_value,
                lead=search_row,
            )
        )

        option_class_base = " ".join(
            p for p in (
                slots.get("option", ""),
                size_map.get("option", ""),
            ) if p
        )
        option_active_cls = self.compose_class(
            "option_active",
            apply_variant_size_modifiers=False,
        )
        option_selected_cls = self.compose_class(
            "option_selected",
            apply_variant_size_modifiers=False,
        )

        for index, opt in enumerate(options_data):
            opt_v_js = json.dumps(opt["value"])
            haystack_js = json.dumps(opt["haystack"])
            label_str = opt["label"]
            # ⚠️ FOUR directives left this option on 2026-09-02 —
            # ``bz-class``, ``bz-attr:aria-selected`` and the two
            # ``bz-on:``. They now live ONCE on the panel: one effect
            # that repaints, two delegated listeners. Measured before:
            # 461 B per option, of which 177 for those directives alone,
            # copied identically N times.
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
                "data-value": opt["value"],
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
            # alone is not enough — ``option_active`` (hover / keyboard)
            # is accented too, and a whole open list that is picked (the
            # normal case of a column filter) no longer reads.
            opt_children: tuple[Node, ...] = option_body(self._render,
                opt["value"], label_str
            )
            if is_multi:
                opt_children += (option_check(
                    slots=slots, size_map=size_map, resolve=_resolve,
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

        # Empty state — shown when filter returns 0 visible options.
        # Hidden at SSR (every option visible with an empty query).
        empty_attrs: dict[str, Any] = {
            "class": sized_slot(slots, size_map, "empty", _resolve),
            "bz-show": "_visibleCount() === 0",
        }
        stamp_display_none(empty_attrs)
        panel_children.append(
            Element(
                tag="div",
                attrs=empty_attrs,
                children=(self.emit_text_slot(empty_text),),
            )
        )

        # ── Anchored panel ───────────────────────────────────────────
        # ``bz-ref="bzpanel"`` + the shared ``anchored_panel_effect``
        # toggles display + attaches ``$bz.helpers.floating`` against
        # the ``bztrigger`` ref. FOUC pre-stamp keeps it hidden before
        # the runtime boots (the panel is open=false at SSR).
        # ``match_width`` pins the panel to the trigger's width — right
        # when the trigger IS the field, wrong when it's a small button
        # (an 80px « Status » would give an 80px panel). Detached, the
        # panel sizes itself off a ``min-w`` floor instead.
        panel_class = sized_slot(slots, size_map, "panel", _resolve)
        if detached:
            panel_class = " ".join(
                p for p in (panel_class, size_map.get("panel_free", "")) if p
            )
        panel_attrs: dict[str, Any] = {
            "class": panel_class,
            "role": "listbox",
            "bz-ref": "bzpanel",
            # Two effects composed with ``;`` — the anchoring, then the
            # painting of the options. The picker already composes like
            # that (``_picker_field.anchored_panel(extra_effect=…)``).
            "bz-effect": anchored_panel_effect(
                "open", "bottom-start", match_width=not detached,
            ) + (
                "; $bz.combobox.paintOptions("
                "$el, _highlight, (v) => _isPicked(v))"
            ),
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
            "bz-on:click": (
                "((o) => { if (o) { $event.stopPropagation(); "
                "_togglePick(o.getAttribute('data-value')); } })"
                "($bz.combobox.optionOf($event))"
            ),
            "bz-on:mouseover": (
                "((o) => { if (o) _highlight = "
                "+o.getAttribute('data-bz-i'); })"
                "($bz.combobox.optionOf($event))"
            ),
        }
        stamp_display_none(panel_attrs)
        panel = Element(
            tag="div",
            attrs=panel_attrs,
            children=tuple(panel_children),
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
        # overwriting the child's. Same as select — the last two call
        # sites of the inline clone-and-merge (audit F56).
        # ``bz-class`` MERGES the rotation; ``bz-attr:class`` would
        # REPLACE it.
        return Component.with_slot_class(
            Component.render_detached(Icon("chevron-down", size=icon_size)),
            chevron_class,
            **{"bz-class": "open ? 'rotate-180' : ''"},
        )

    def _build_header_bar(
        self,
        *,
        slots: dict[str, str],
        size_map: dict[str, str],
        resolve: Callable[[str], str],
        is_multi: bool,
        show_bulk: bool,
        total_options: int,
        initial_value: Any,
        lead: Element | None = None,
    ) -> Element:
        """The shared header. Combobox compares against the VISIBLE
        options: the query hides some, so "select all" stays active as
        long as one visible unpicked one remains (and inactive on a list
        filtered to empty, hence the ``c > 0`` guard)."""
        return build_header_bar(
            slots=slots, size_map=size_map, resolve=resolve,
            badge_theme=self._resolved_theme("badge", BADGE_THEME),
            is_multi=is_multi, show_bulk=show_bulk,
            total_options=total_options, initial_value=initial_value,
            lead=lead,
            select_all_disabled_js=(
                "((c) => c > 0 && _picked().length === c)(_visibleCount())"
            ),
        )

    def _build_bz_data(
        self,
        *,
        is_multi: bool,
        value_binding: ClientBinding | None,
        value_method: str,
        initial_value: Any,
        options_js: str,
        server_backed: bool,
    ) -> str:
        """The big bz-data blob — single source of truth for the
        Combobox's runtime behaviour. Assembled by ``json.dumps`` +
        f-strings + concatenation. (The ``%``-formatting announced here
        until 2026-08-01 is used nowhere in this file — zero ``%s``.)

        Two read shapes (mirrors Select / Tabs / Accordion idiom) :

        - **Local mode** : a local ``value`` field. ``_setValue``
          writes ``this.value`` directly.
        - **Binding mode** : no local field, ``_value()`` reads
          ``$bz.state.<path>``. Writes go to the same path.

        ⚠️ ``value`` is exposed as a flat ``_value()`` method, not a
        getter (a getter would freeze at registration via
        ``scope.absorb``). All read sites call ``_value()`` /
        ``_picked()``.

        Methods exposed :

        - ``_norm(s)`` — JS-side equivalent of :func:`_normalise_text`.
        - ``_tokens()`` — split + normalise the current ``query``.
        - ``_matches(haystack)`` — true iff every token is in the
          pre-normalised haystack.
        - ``_visibleCount()`` / ``_visibleIndices()`` — filter stats
          used by arrow-key navigation to skip filtered-out rows.
        - ``_moveHighlight(delta)`` — bounded keyboard nav.
        - ``_pickHighlighted()`` — Enter handler.
        - Single :  ``_pick(v)`` — write the value, close the panel.
        - Multi :   ``_picked()`` returns the current array (handles
          the binding/local split), ``_togglePick(v)`` flips
          membership, ``_removeOne(v)`` / ``_removeLast()`` remove,
          ``_selectAll()`` / ``_clearAll()``.
        - ``_isPicked(v)`` / ``_hasPicked()`` — selection predicates.
        - ``_setValue(raw)`` — used by the imperative ``bz-set``
          dispatch. Accepts a string (single) or array (multi).
        - ``_value()`` — mode-aware reader (local field or binding
          path, null-guarded).

        Pick / set methods only ``_write`` the value ; ``change`` is
        dispatched by the hidden input's ``_change_emit_effect``, not by
        the scope.
        """
        # The ~30 normalise/filter/nav + pick/membership methods live
        # ONCE in the runtime factory (14_combobox.js) : a shared
        # ``$bz.combobox.common`` (filter + nav) + a mode-specific
        # ``.single`` / ``.multi``. Each instance spreads both and emits
        # only its data (``_options``, per-instance) +
        # ``_read``/``_write`` pointing at the value cell.
        #
        # ``_read``/``_write`` (helpers, not frozen) : local → a ``value``
        # field, binding → ``$bz.state.<path>`` (read raw + null-guard so
        # the factory's ``_value`` gets [] / '' instead of null). No live
        # ``get value()`` — scope.absorb freezes getters (cf. traps.md) ;
        # the input/hidden read ``value_expr`` directly.
        initial_js = (
            json.dumps([str(v) for v in initial_value])
            if is_multi
            else json.dumps(str(initial_value or ""))
        )

        if value_binding is None:
            # ``_serverSync`` adopts ``value`` from the server on a
            # @refreshable swap — ONLY when server-backed (cf. render() ;
            # an unbound / literal combobox keeps its client pick).
            # The options list is server-owned CONFIG: the client never
            # writes it, and it does change for real (a select reloaded
            # from the database at every refresh). Re-seeded
            # UNCONDITIONALLY — otherwise it stays frozen at the first
            # mount's, for life. The VALUE, for its part, stays gated.
            _keys = (["value", "_options"] if server_backed
                     else ["_options"])
            sync_marker = server_sync_marker(*_keys, enabled=True)
            value_field = "value: " + initial_js + "," + sync_marker
            read_write = (
                "_read() { return this.value; },"
                "_write(v) { this.value = v; },"
            )
        else:
            empty_js = "[]" if is_multi else "''"
            value_field = ""
            read_write = (
                f"_read() {{ const v = {value_method}; "
                f"return v == null ? {empty_js} : v; }},"
                f"_write(v) {{ {value_method} = v; }},"
            )

        scope = "multi" if is_multi else "single"
        return (
            "{...$bz.combobox.common, ...$bz.combobox." + scope + ","
            + value_field
            + read_write
            + "open: false, query: '', _highlight: -1,"
            + f"_options: {options_js}"
            + "}"
        )


__all__ = ["Combobox"]
