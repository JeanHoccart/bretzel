"""``Tabs`` / ``Tab`` / ``TabPanel`` — switchable content panels.

Usage ::

    with ui.tabs(value=state.tab):
        ui.tab("overview", label="Overview", icon="info")
        ui.tab("settings", label="Settings")
        with ui.tab_panel("overview"):
            ui.text("Overview content")
        with ui.tab_panel("settings"):
            ui.text("Settings content")

**One style, no variants.** Each tab label rides inside a rounded pill
(a badge) ; the active tab tints its pill and draws a 2px coloured
underline under its slot — a Crédit-Agricole style strip. Geometry +
colours all live in :data:`~bretzel.components.navigation.tabs.theme`.
There is NO orientation fork and NO JavaScript sliding indicator : the
active underline is pure CSS driven by the ``data-selected`` attribute.

The active tab id lives client-side in a ``bz-data`` scope field
(literal mode) or is mirrored to a ``ClientBinding`` (binding mode).
Tab clicks flip the field ; every panel's ``bz-show="value === '<id>'"``
toggles visibility without a server round-trip, and every tab's
``bz-attr:data-selected`` flips its active styling.

Form integration : when ``value`` is a binding, ``AUTONAME_FROM
= "value"`` derives the HTML ``name`` from the field — a hidden
``<input>`` rides the active id into form data, with the change
listener (``bz-on:change`` for a client string handler, the
``hx-*`` server-action bundle for a callable) relocated onto it
(same idiom as :class:`Select` / :class:`ToggleGroup`). The hidden
input fires its own ``change`` from a ``bz-effect`` that reads the
active value — the scope proxy has no ``$refs`` / ``$nextTick``
inside a method body, so the dispatch can't live in ``setTab``.

Children registration : ``Tab`` and ``TabPanel`` auto-attach to the
enclosing ``Tabs._children`` list during their own ``__init__``
(they're constructed inside the ``with ui.tabs(...)`` block).
``Tabs.render()`` walks this list and dispatches each child to the
right slice of the rendered DOM — no parent-stack lookup needed.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any, ClassVar

from bretzel.components.base import (
    Component,
    reactive_prop,
    stamp_display_none,
)
from bretzel.components.base._wiring import (
    bool_attr,
    hidden_carrier_attrs,
    server_sync_marker,
    unwrap_transparent,
)
from bretzel.components.base._wiring import (
    pop_change_handler as _pop_change_handler,
)
from bretzel.components.navigation.tabs.theme import TABS_THEME
from bretzel.core.tree import Element

# ───────────────────────────────────────────────────────────────────────────
# bz-data builder — V3 scope object for the tabs root
# ───────────────────────────────────────────────────────────────────────────


def _build_x_data(
    *,
    scope_key: str,
    has_local_value: bool,
    initial_value: str,
    binding_path: str | None,
    server_synced: bool,
    url_param: str | None = None,
) -> str:
    """Return the ``bz-data`` object literal string for the tabs root.

    Two shapes, both driven by whatever the panels / tabs read as their
    "active id" expression (``active_expr``, built alongside this) :

    - **Local mode** : a local ``active : "<id>"`` signal. ``setTab``
      mutates ``this.value`` ; the directives read the bare ``value``
      signal. When the value is server-backed (``value=state.field``),
      the field also carries ``_serverSync: ['value']`` so the bridge
      re-adopts the fresh server value on a @refreshable morph
      (idiomorph preserves the live signal otherwise — cf.
      ``03_scope.js`` ``resyncScopes`` and ``traps.md`` § "a
      server-bound value follows the refresh"). A plain literal
      (``value="a"``) omits it so a user's tab click survives an
      unrelated section refresh — same gate as Select / Slider.
    - **Binding mode** : NO local field and — critically — **no
      ``get active()`` getter**. The scope's ``absorb`` (03_scope.js)
      evaluates every declared key ONCE and freezes it into a local
      signal ; a getter would be called a single time and its result
      baked into a dead ``value`` signal, disconnected from the store
      — so ``setTab`` (writing ``$bz.state.<path>``) and an external
      writer (a Select bound to the same field) would move the store
      while the tab / panel directives, reading the frozen signal, never
      update. Instead the directives read ``$bz.state.<path>`` DIRECTLY
      (a tracked store cell) and ``setTab`` reads / writes the same
      path. Same idiom as Select — cf. its "No live ``get value()``"
      docstring, and ``traps.md`` § "scope getter frozen by absorb".
      No ``_serverSync`` — the value lives in ``$bz._store``, patched by
      the envelope, never on a scope signal.

    Method shorthands run with ``this`` bound to the scope proxy (the
    runtime binds helpers to the proxy — cf. ``03_scope.js``). In
    local mode ``setTab`` goes through ``this.value`` (the signal) ; in
    binding mode it reads / writes ``$bz.state.<path>`` directly (there
    is no scope ``value``).

    No ``updateIndicator`` : the single-style strip draws its active
    underline in pure CSS (``data-[selected=true]:border-{color}``), so
    the scope carries only the active-value state + its setter.
    """
    initial_js = json.dumps(initial_value)
    if has_local_value:
        # ``scope_key`` comes from ``_scope_keys`` — no longer a
        # hard-coded literal, the same source for the signal AND the
        # ``_serverSync``, they can no longer diverge.
        sync = server_sync_marker(scope_key, enabled=server_synced)
        local_field = f"{scope_key}: {initial_js},{sync} "
        active_read = f"this.{scope_key}"
        write_target = f"this.{scope_key}"
    else:
        assert binding_path is not None
        local_field = ""
        # Read / write the tracked store cell directly — no scope getter
        # (absorb would freeze it, cf. docstring).
        active_read = binding_path
        write_target = binding_path

    # ``setTab`` lives once in ``$bz.tabs.scope``
    # (``bretzel/runtime/_src/16_accordion.js``) — it was not big, but it
    # was serialised per instance, and its ``_read``/``_write`` is
    # exactly the indirection Pagination and Accordion already use to
    # cover both a local field AND a binding with the same methods.
    #
    # (The ``change`` dispatch can NOT live in a scope method: the V3
    # proxy exposes neither ``$refs`` nor ``$nextTick`` there. It is the
    # hidden input's ``bz-effect`` that redoes it when the value moves.)
    # ``_url``: the parameter's name, not its value. ``setTab`` reads it
    # to push the address after writing the signal, and ``_urlInit`` to
    # re-wire the back button. Absent when nobody asked for an address —
    # so the whole mechanism stays inert by default.
    url_field = f"_url: {json.dumps(url_param)}," if url_param else ""
    return (
        "{...$bz.tabs.scope,"
        + local_field
        + url_field
        + f"_read() {{ return {active_read}; }},"
        + f"_write(v) {{ {write_target} = v; }}"
        + "}"
    )


def _tab_from_url(param: str) -> str:
    """The value of ``param`` in the current request's URL, or ``""``.

    Best-effort and never raising: outside a request (the unit tests
    mount a component with no context) there is no URL, and that is not
    a fault — the tab simply falls back on its default.

    ⚠️ We do NOT VALIDATE that the value designates an existing tab. At
    this point in the render the children have not been walked yet, so
    the list of ids does not exist. A ``?tab=whatever`` then leaves NO
    tab selected — which is visible, unlike a silent fallback to the
    default, and stays fixable in one click.
    """
    from bretzel.render.context import maybe_current_context

    ctx = maybe_current_context()
    request = getattr(ctx, "request", None) if ctx is not None else None
    params = getattr(request, "query_params", None)
    if params is None:
        return ""
    try:
        return str(params.get(param) or "")
    except Exception:
        return ""


# ───────────────────────────────────────────────────────────────────────────
# Tabs — root container
# ───────────────────────────────────────────────────────────────────────────


class Tabs(Component):
    """Container that holds Tab buttons + TabPanel content."""

    THEME: ClassVar[dict[str, Any]] = TABS_THEME
    THEME_KEY: ClassVar[str] = "tabs"
    BINDABLE_PROPS: ClassVar[tuple[str, ...]] = ("value",)
    EVENTS: ClassVar[tuple[str, ...]] = ("change",)

    # ``writes=True`` → the metaclass derives ``TWO_WAY_PROPS =
    # ("value",)`` and the scope key, which is the PROP'S NAME. It was
    # called ``active`` and declared as ``scope_keys=("active",)``: one
    # more synonym among the eight the catalogue carried.
    value: Any = reactive_prop(
        default="", emit_attr=False, writes=True, names_field=True
    )
    size: str = reactive_prop(default="md", emit_attr=False)
    color: str = reactive_prop(default="primary", emit_attr=False)
    # Form-input name lands on the hidden input ; consumed by the
    # dispatcher to key the form payload sent with ``change`` events.
    # Autoname via ``AUTONAME_FROM = "value"`` covers binding cases ;
    # pass ``name=`` explicitly for literal-valued Tabs that still
    # need a server handler. Same idiom as Pagination.
    name: str | None = reactive_prop(default=None, emit_attr=False)
    #: The name of the URL parameter that carries the open tab —
    #: ``ui.tabs(url="tab")`` gives ``/contacts/5?tab=activity``.
    #:
    #: **Design-time, never bindable**: it is a name, not a value.
    #: Making it reactive would amount to renaming a URL parameter
    #: mid-course, which would break the back button on the entries
    #: already stacked.
    #:
    #: Absent by default. A tab only has an address if you ask for one —
    #: the same opt-in as ``URL = {…}`` on a server state, and for the
    #: same reason: what is in the URL is PUBLIC.
    url: str | None = reactive_prop(default=None, emit_attr=False)

    def __init__(
        self,
        *,
        value: Any = None,
        size: str | None = None,
        color: str | None = None,
        name: str | None = None,
        url: str | None = None,
        on_change: Callable[..., Any] | str | None = None,
        **kwargs: Any,
    ) -> None:
        # Direct forward: the base layer drops reactive None kwargs (keeps the default).
        super().__init__(
            value=value,
            size=size,
            color=color,
            name=name,
            url=url,
            on_change=on_change,
            **kwargs,
        )

    # ── Render ─────────────────────────────────────────────────────────

    def render(self) -> Element:
        theme = self._resolved_theme()
        sizes = theme.get("sizes", {})
        size_key = self._reactive_values.get("size") or "md"
        size_cfg = sizes.get(size_key, sizes.get("md", {}))

        # Slots via the shared ``compose_class`` composer (resolves the
        # ``{bg_color}`` placeholders against the ``color`` prop ; user
        # ``classes=`` land on the root later, not on these inner slots).
        # ``apply_variant_size_modifiers=False`` : Tabs has no variant,
        # and its sizes are multi-slot (resolved manually below).
        tablist_class = self.compose_class(
            "tablist", apply_variant_size_modifiers=False
        )
        tab_class = self.compose_class(
            "tab", apply_variant_size_modifiers=False
        )
        # Pill badge : slot base + the per-size text/padding.
        pill_class = " ".join(
            p
            for p in (
                self.compose_class(
                    "pill", apply_variant_size_modifiers=False
                ),
                size_cfg.get("pill", ""),
            )
            if p
        )
        panel_class = self.compose_class(
            "panel", apply_variant_size_modifiers=False
        )

        # ── Resolve binding for ``value`` ────────────────────────────
        value_binding = self._binding_metadata.get("value")
        raw_value = self._reactive_values.get("value")
        initial_value = str(raw_value or "")
        # A local ``value=state.field`` carries a ``field_name`` stamp —
        # the server is authoritative, so its ``value`` field opts into
        # ``_serverSync`` (re-adopted on a @refreshable morph). A plain
        # ``value="a"`` literal has no stamp and stays client-owned.
        value_server_backed = self._value_server_backed("value")

        # ── Does the tab come from the URL? ─────────────────────────
        #
        # The SEEDING. Without it, ``/contacts/5?tab=activity`` would
        # open the default tab and the address bar would lie — a shared
        # link would show something other than what the sender saw.
        #
        # It is also what makes the back button work AFTER a reload: the
        # runtime restores the tab from the scope as long as the page is
        # alive, the server does it when it is born again.
        url_param = self._reactive_values.get("url") or None
        if url_param:
            from_url = _tab_from_url(url_param)
            if from_url:
                initial_value = from_url
        # Key of the scope signal, declared on the prop ("active").
        scope_key = self._scope_keys("value")[0]

        binding_path = (
            self.path_of(value_binding)
            if value_binding is not None
            else None
        )
        # The "active id" expression the tab / panel directives read AND
        # the hidden input mirrors : the bare local ``value`` signal in
        # local mode, the tracked ``$bz.state.<path>`` store cell in
        # binding mode (NO scope getter — cf. ``_build_x_data``). Both
        # are reactive, so a click (``setTab``) or an external writer (a
        # Select bound to the same field) re-runs every ``bz-show`` /
        # ``bz-attr:data-selected`` that reads it.
        active_expr = binding_path or scope_key
        # ``bz-attr:value`` on the hidden input reads the same expression.
        value_expr = active_expr

        x_data = _build_x_data(
            scope_key=scope_key,
            has_local_value=value_binding is None,
            initial_value=initial_value,
            binding_path=binding_path,
            server_synced=value_server_backed,
            url_param=url_param,
        )

        # ── Walk children, split into tabs and panels ────────────────
        tab_nodes: list[Element] = []
        panel_nodes: list[Element] = []
        for raw in self._children:
            # ``unwrap_transparent``: a tab is very often WRAPPED — in
            # a ``@refreshable`` zone to refresh alone, or in a
            # ``ui.fragment``. The wrapper is not an instance of
            # ``Tab``, so sorting by type missed it and the tab
            # **disappeared from the bar**, with no error (measured on
            # 2026-08-23: 2,268 → 1,353 characters). ``rewrap`` gives
            # its ``bz-id`` back to the zone on the node just composed —
            # without it the tab would display and never refresh again.
            child, rewrap = unwrap_transparent(raw)
            if isinstance(child, Tab):
                tab_nodes.append(rewrap(
                    child._render_button(
                        tab_class=tab_class,
                        pill_class=pill_class,
                        active_expr=active_expr,
                        initial_active=initial_value,
                    )
                ))
            elif isinstance(child, TabPanel):
                panel_nodes.append(rewrap(
                    child._render_panel(
                        panel_class=panel_class,
                        active_expr=active_expr,
                        initial_active=initial_value,
                    )
                ))
            else:
                child = raw
                # Foreign children (text, comments, etc.) flow through
                # untouched — useful for spacer / divider injections.
                rendered = self._render_one(child)
                if rendered is not None and isinstance(rendered, Element):
                    panel_nodes.append(rendered)

        # ── Hidden input — form integration + change source ──────────
        # The hidden input is BOTH the form-data carrier AND the
        # element the change event fires from. Every change listener
        # (client ``bz-on:change`` + the ``hx-*`` server-action bundle)
        # is relocated off the wrapper <div> (which has no native
        # ``change`` event) onto the hidden input via the shared
        # :func:`pop_change_handler`. Without relocation the listeners
        # sit on the wrapper but nothing fires ``change`` from there —
        # the hidden input's ``bz-effect`` (below) re-fires it on every
        # active-value move.
        root_attrs = self.emit_attrs()
        relocated = _pop_change_handler(root_attrs)

        name = self._reactive_values.get("name") or self._derive_field_name()

        # Render the hidden input whenever a name is in play OR ANY
        # change listener was relocated. The input's ``bz-effect``
        # reads ``value_expr`` (the active id) and re-fires a native
        # ``change`` whenever it moves — that's what re-triggers the
        # relocated listeners (client ``bz-on:change`` or the server
        # ``hx-trigger="change"``). Same idiom ToggleGroup's hidden
        # input uses.
        hidden_node: Element | None = None
        if name or relocated:
            hidden_attrs: dict[str, Any] = {
                **hidden_carrier_attrs(value_expr, initial=initial_value),
                # Fire ``change`` from the input itself on every move of
                # the active value. Reading ``value_expr`` registers the
                # dependency so the effect re-runs on each change ; the
                # bootstrap guard skips the SSR→hydration handoff, the
                # ``!==`` guard skips no-op re-runs, and ``$nextTick``
                # lets the runtime flush ``bz-attr:value`` onto the DOM
                # input BEFORE HTMX serialises it. Same shape as
                # Pagination's ``_change_emit_effect``.
            }
            if name:
                hidden_attrs["name"] = str(name)
            hidden_attrs.update(relocated)
            hidden_node = Element(
                tag="input", attrs=hidden_attrs, children=()
            )

        # ── Assemble the tree ────────────────────────────────────────
        # Root direction (flex-col) is baked into the ``root`` slot —
        # the tablist sits above the panels, single style, no fork.
        root_attrs["class"] = self.compose_class(
            "root", apply_variant_size_modifiers=False
        )
        root_attrs["bz-data"] = x_data
        if url_param:
            # The BACK button. ``setTab`` pushes the address; without
            # this counterpart, the browser's arrow would change the URL
            # and leave the tab in place — the displayed address would
            # then lie about what is on screen, which is worse than
            # having no address at all.
            #
            # ``bz-init`` and not a ``bz-effect``: we subscribe ONCE to a
            # ``window`` event, we do not watch a signal. It is the route
            # ``06_helpers.js`` documents for ``popstate``.
            root_attrs["bz-init"] = "_urlInit()"

        tablist = Element(
            tag="div",
            attrs={"class": tablist_class, "role": "tablist"},
            children=tuple(tab_nodes),
        )

        # Panel container : ``grid`` with all panels in the same
        # cell (``col-start-1 row-start-1``) so they overlap
        # physically instead of stacking in the normal flow. Without
        # this, the brief overlap during a CSS cross-fade (outgoing
        # fade-out + incoming fade-in both visible for ~150ms)
        # shows them stacked vertically — the new panel appears
        # below the old one until the old fades out. Grid-stack
        # keeps them in the same z-area for a clean cross-fade.
        # Container height matches the tallest panel.
        children: list[Element] = [tablist]
        if hidden_node is not None:
            children.append(hidden_node)
        if panel_nodes:
            children.append(
                Element(
                    tag="div",
                    attrs={"class": "grid"},
                    children=tuple(panel_nodes),
                )
            )

        return Element(
            tag=self._tag, attrs=root_attrs, children=tuple(children)
        )


# ───────────────────────────────────────────────────────────────────────────
# Tab — single button
# ───────────────────────────────────────────────────────────────────────────


class Tab(Component):
    """One button inside a :class:`Tabs` strip.

    Carries metadata only — :meth:`Tabs.render` consults each Tab's
    ``id``, ``label``, optional icon, and disabled flag to build the
    actual ``<button role="tab">``. No standalone ``render()`` body :
    when called outside a Tabs ``with`` block the tab simply doesn't
    appear in any tablist (and the auto-attach machinery puts it in
    the active parent anyway, but the parent won't know what to do
    with it — caveat caller).
    """

    THEME_KEY: ClassVar[str] = "tab"
    DEFAULT_TAG: ClassVar[str] = "button"
    IS_CONTAINER: ClassVar[bool] = False
    # Tab is a metadata holder — id/label/disabled are design-time
    # for the strip. Tabs.value (parent) drives selection.
    BINDABLE_PROPS: ClassVar[tuple[str, ...]] = ()
    NAMED_SLOTS: ClassVar[tuple[str, ...]] = ("icon",)
    ICON_SLOTS: ClassVar[tuple[str, ...]] = ("icon",)

    tab_id: str = reactive_prop(default="", emit_attr=False)
    label: str = reactive_prop(default="", emit_attr=False)
    disabled: bool = reactive_prop(default=False, emit_attr=False)

    def __init__(
        self,
        tab_id: str = "",
        *,
        label: str = "",
        icon: Any = None,
        disabled: bool | None = None,
        **kwargs: Any,
    ) -> None:
        # Direct forward: the base layer drops reactive None kwargs (keeps the default).
        super().__init__(
            tab_id=tab_id,
            label=label,
            disabled=disabled,
            icon=icon,
            **kwargs,
        )

    # ── Internal render — invoked by Tabs ─────────────────────────────

    def _render_button(
        self,
        *,
        tab_class: str,
        pill_class: str,
        active_expr: str,
        initial_active: str,
    ) -> Element:
        tab_id = str(self._reactive_values.get("tab_id") or "")
        # NO ``str(...)``: ``label`` is a textual slot (it accepts a
        # Component), and ``emit_text_slot`` sorts it out downstream.
        label = self._reactive_values.get("label") or ""
        disabled = bool(self._reactive_values.get("disabled"))
        id_js = json.dumps(tab_id)
        is_initial_active = tab_id == initial_active

        # ``active_expr`` is the active-id read handed down by
        # ``Tabs.render`` : the bare ``value`` scope signal in local
        # mode, or the tracked ``$bz.state.<path>`` store cell in binding
        # mode (NO scope getter — cf. ``_build_x_data``). Both resolve in
        # the directive's ``with($scope)`` wrap ; ``this.value`` would
        # read the DOM element, not the scope (cf. ``traps.md`` §
        # "this.X in a directive").
        #
        # ``data-selected`` : the active-state driver. Rendered
        # STATIC server-side on the initial active tab so the
        # ``data-[selected=true]:border-{color}`` underline + the pill's
        # ``group-data-[selected=true]:*`` tint pick the active styling
        # up at first paint, BEFORE the runtime boots. Then
        # ``bz-attr:data-selected`` keeps it reactive on subsequent
        # clicks. The expression yields a ``'true'`` / ``'false'``
        # STRING via ``bool_attr``, which emits the stringified ternary —
        # and NOT ``.toString()``, which raises on ``null`` (dialect
        # unified on 2026-07-30). A bare boolean would make
        # ``bz-attr`` strip the attribute on ``false`` and the
        # ``data-[selected=false]`` selectors would never match. Cf.
        # ``traps.md`` § "bz-attr removes the attr on a bare false".
        attrs: dict[str, Any] = {
            "type": "button",
            "role": "tab",
            "class": tab_class,
            "bz-attr:data-selected": bool_attr(f"{active_expr} === {id_js}"),
            "bz-attr:aria-selected": bool_attr(f"{active_expr} === {id_js}"),
            "bz-attr:tabindex": f"{active_expr} === {id_js} ? 0 : -1",
            "bz-on:click": f"setTab({id_js})",
        }
        if is_initial_active:
            attrs["data-selected"] = "true"
        if disabled:
            attrs["disabled"] = True

        # The visible label + optional icon live in a rounded pill
        # (badge) — the button itself is just the click target + the
        # underline carrier. The pill reads the button's data-selected
        # through ``group-*`` selectors (the button carries ``group``).
        pill_children: list[Any] = []
        icon = self._slot_components.get("icon")
        if isinstance(icon, Component):
            Component._detach_from_parent(icon)
            pill_children.append(icon.render())
        if label:
            pill_children.append(self.emit_text_slot(label))
        pill = Element(
            tag="span",
            attrs={"class": pill_class},
            children=tuple(pill_children),
        )

        return Element(tag="button", attrs=attrs, children=(pill,))

    # ── Default render — silent no-op when used outside Tabs ─────────

    def render(self) -> Element:
        # Outside a Tabs container, tabs have no meaningful DOM —
        # emit an inert empty span so a stray ``ui.tab(...)`` at page
        # scope doesn't blow up the renderer.
        return Element(tag="span", attrs={}, children=())


# ───────────────────────────────────────────────────────────────────────────
# TabPanel — content area for one tab
# ───────────────────────────────────────────────────────────────────────────


class TabPanel(Component):
    """Content shown when its ``tab`` matches the active id."""

    THEME_KEY: ClassVar[str] = "tab_panel"
    # Show/hide derived from Tabs.value at the parent level.
    BINDABLE_PROPS: ClassVar[tuple[str, ...]] = ()
    tab: str = reactive_prop(default="", emit_attr=False)

    def __init__(
        self,
        tab: str = "",
        **kwargs: Any,
    ) -> None:
        # Direct forward: the base layer drops reactive None kwargs (keeps the default).
        super().__init__(tab=tab, **kwargs)

    # ── Internal render — invoked by Tabs ─────────────────────────────

    def _render_panel(
        self, *, panel_class: str, active_expr: str, initial_active: str
    ) -> Element:
        tab_id = str(self._reactive_values.get("tab") or "")
        id_js = json.dumps(tab_id)
        is_initial_active = tab_id == initial_active

        # ``bz-show`` toggles ``display`` while the panel stays mounted.
        # The fade between panels is handled by CSS (theme).
        #
        # FOUC : non-active panels are pre-stamped ``display:none`` via
        # :func:`stamp_display_none` so nothing flashes before the
        # runtime's first ``bz-show`` effect runs. The initial active
        # panel is rendered visible SSR ; the runtime takes over after
        # bind. Same idiom as the overlay ``bz-show`` ports.
        attrs: dict[str, Any] = {
            "role": "tabpanel",
            "class": panel_class,
            # ``active_expr`` — the local ``value`` signal or the
            # ``$bz.state.<path>`` store cell (cf. ``Tab._render_button``).
            "bz-show": f"{active_expr} === {id_js}",
        }
        if not is_initial_active:
            stamp_display_none(attrs)
        return Element(
            tag="div",
            attrs=attrs,
            children=self._render_children(),
        )

    def render(self) -> Element:
        # Standalone usage — render a normal div so child content
        # still appears, but without the tab toggle wiring.
        return Element(
            tag="div",
            attrs={"class": "outline-none"},
            children=self._render_children(),
        )


__all__ = ["Tab", "TabPanel", "Tabs"]
