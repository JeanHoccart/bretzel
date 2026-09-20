"""``Stepper`` / ``Step`` / ``StepPanel`` — progress through ordered steps.

Usage ::

    with ui.stepper(value=state.step, on_change=goto):
        ui.step("Account", description="Email and password", icon="user")
        ui.step("Address", description="Delivery")
        ui.step("Payment", status="error")

        with ui.step_panel():          # panel 0
            ui.input("Email", value=state.email)
        with ui.step_panel():          # panel 1
            ui.input("City", value=state.city)

**The current step is an integer INDEX, 0-based** (``value`` in JS), like
Ant ``Steps.current`` / MUI ``activeStep`` / Mantine ``active``. Each
step's status is DERIVED from it — ``index < current`` = done, ``==
current`` = current, ``> current`` = upcoming — so there is nothing to
declare, and the comparison is an integer on the client side. One id per
step would have forced each chip to do an ``indexOf`` in a baked list for
the same information.

``status="error"`` is the ONLY explicit status: it freezes the step (a
static attribute, no ``bz-attr``), the derived triptych covering
everything else.

The panels are paired by **declaration order** — the n-th
``ui.step_panel()`` shows when ``current == n``. One panel more than
steps is legitimate and that is the point: it becomes the "done" screen,
reached by one last ``.next()`` (Mantine's ``Stepper.Completed`` idiom,
without the fourth component). That is why ``next()``'s bound is
``max(len(steps), len(panels)) - 1`` and not ``len(steps) - 1``.

In ``vertical`` orientation the panels stay BELOW the list, they do not
interleave between the steps (which MUI does). It is an abstention, not
an oversight: interleaving doubles the render structure for a gain that
only concerns the vertical form wizard.

Form integration : ``names_field=True`` on ``value`` derives the HTML
``name`` from the bound field — an ``<input type="hidden">`` carries the
index in the form data, and the ``change`` listener is relocated onto it
(an ``<ol>`` has neither ``name``/``value`` nor a native ``change``).
Idiom shared with Tabs / Pagination / Accordion.

Imperative API : ``.set(i)`` / ``.next()`` / ``.prev()``. ``.set`` writes
straight into the binding when there is one (write-through); ``.next`` /
``.prev`` ALWAYS dispatch a DOM command, binding or not — their result
depends on the LIVE value and on the bound, which the server does not
know at render time. Cf. ``imperative-api.md``.
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
    coerce_index,
    hidden_carrier_attrs,
    server_sync_marker,
    unwrap_transparent,
)
from bretzel.components.base._wiring import (
    pop_change_handler as _pop_change_handler,
)
from bretzel.components.navigation.stepper.theme import STEPPER_THEME
from bretzel.components.primitives.icon import Icon
from bretzel.core.tree import Element, Node
from bretzel.core.tree import TextNode as TextNode


def _build_bz_data(
    *,
    scope_key: str,
    has_local_value: bool,
    initial_value: int,
    binding_path: str | None,
    max_index: int,
    server_synced: bool,
) -> str:
    """The instance's ``bz-data``: **data, not code**.

    The methods (``_status`` / ``goTo`` / ``next`` / ``prev``) live once
    in ``$bz.stepper.scope``
    (``bretzel/runtime/_src/16_accordion.js``). All that leaves from here
    is the state, the read/write indirection, and the ``_max`` bound.

    Two modes, like Tabs:

    - **local**: a ``value`` signal. When the value comes from the server
      (``value=state.step``), it carries ``_serverSync`` so that a
      ``@refreshable``'s morph re-adopts it — the server is
      authoritative. A literal (``value=1``) abstains, otherwise a
      neighbouring refresh would overwrite the client's navigation.
    - **binding**: NO local signal and most certainly no getter —
      ``scope.absorb`` evaluates each key once and would freeze a getter
      on its first value. The directives and ``_read``/``_write``
      address the ``$bz.state.<path>`` cell directly.
    """
    # ``_max`` is CONFIG: the number of steps comes from the server, the
    # client never writes it → re-seeded unconditionally. ``absorb``
    # never rewrites an existing signal, so without this a stepper that
    # gains or loses a step kept its old bound (``next()`` stopped at the
    # old maximum). Same root as Pagination's ``_total``.
    config_sync = ["_max"]
    if has_local_value:
        # The VALUE stays gated: with no server ownership, a
        # neighbouring refresh would overwrite the step the client has
        # just reached.
        keys = [scope_key, *config_sync] if server_synced else config_sync
        sync = server_sync_marker(*keys, enabled=True)
        state = f"{scope_key}: {json.dumps(initial_value)},{sync} "
        target = f"this.{scope_key}"
    else:
        assert binding_path is not None
        state = f"{server_sync_marker(*config_sync, enabled=True).lstrip()} "
        target = binding_path

    return (
        "{...$bz.stepper.scope,"
        + state
        + f"_read() {{ return {target}; }},"
        + f"_write(v) {{ {target} = v; }},"
        + f"_max: {max_index}"
        + "}"
    )


class Stepper(Component):
    """Render an ordered sequence of steps with matching content panels."""

    THEME: ClassVar[dict[str, Any]] = STEPPER_THEME
    THEME_KEY: ClassVar[str] = "stepper"
    BINDABLE_PROPS: ClassVar[tuple[str, ...]] = ("value",)
    IMPERATIVE: ClassVar[tuple[str, ...]] = ("set", "next", "prev")
    EVENTS: ClassVar[tuple[str, ...]] = ("change",)

    # ``writes=True`` → the metaclass derives ``TWO_WAY_PROPS``.
    # The scope key is the prop's name — ``value`` — in the ``bz-data``
    # (≠ the prop's name) — declared here, not hard-coded in the builder
    # nor in ``server_sync_marker``.
    value: Any = reactive_prop(
        default=0,
        emit_attr=False,
        writes=True,
        names_field=True,
    )
    orientation: str = reactive_prop(default="horizontal", emit_attr=False)
    clickable: bool = reactive_prop(default=False, emit_attr=False)
    size: str = reactive_prop(default="md", emit_attr=False)
    color: str = reactive_prop(default="primary", emit_attr=False)
    # Like Tabs / Pagination: the autoname covers the bound case,
    # ``name=`` is still there for a stepper with a literal value that
    # still wants to post its index.
    name: str | None = reactive_prop(default=None, emit_attr=False)

    def __init__(
        self,
        *,
        value: Any = None,
        orientation: str | None = None,
        clickable: bool | None = None,
        size: str | None = None,
        color: str | None = None,
        name: str | None = None,
        on_change: Callable[..., Any] | str | None = None,
        **kwargs: Any,
    ) -> None:
        # Direct forward: the base layer drops reactive None kwargs (keeps the default).
        super().__init__(
            value=value,
            orientation=orientation,
            clickable=clickable,
            size=size,
            color=color,
            name=name,
            on_change=on_change,
            **kwargs,
        )

    # ── Imperative API ─────────────────────────────────────────────────
    #
    # Ordinary CLASS methods, not instance attributes: the overlays'
    # non-data-descriptor trick exists only so as not to shadow a
    # same-named ``reactive_prop`` (``open``), and none of these three
    # names is one. Taking it anyway would cost twice — the
    # ``test_imperative_classvar_is_complete`` gate only reads a
    # ClassDef's PUBLIC methods, so assigned ``_imperative_*`` would be
    # invisible to it.

    def set(self, index: int) -> str:
        """Go to ``index``. Write-through binding if there is one."""
        return self._value_command(coerce_index(index, minimum=0))

    def next(self) -> str:
        # Always the dispatch, binding or not: "the next step" is
        # computed from the LIVE value and stops at ``_max``. The server
        # knows neither at render time — a write-through would have to
        # bake ``index + 1`` and would overrun.
        return self._dispatch_command("bz-next")

    def prev(self) -> str:
        return self._dispatch_command("bz-prev")

    # ── Render ─────────────────────────────────────────────────────────

    def render(self) -> Element:
        theme = self._resolved_theme()
        sizes = theme.get("sizes", {})
        orientations = theme.get("orientations", {})

        size_key = self._reactive_values.get("size") or "md"
        size_cfg = sizes.get(size_key, sizes.get("md", {}))
        orientation = self._reactive_values.get("orientation") or "horizontal"
        axis = orientations.get(orientation) or orientations["horizontal"]
        clickable = bool(self._reactive_values.get("clickable"))

        # ── Binding de ``value`` ─────────────────────────────────────
        value_binding = self._binding_metadata.get("value")
        initial_index = coerce_index(self._reactive_values.get("value"), minimum=0)
        value_server_backed = self._value_server_backed("value")
        scope_key = self._scope_keys("value")[0]
        binding_path = (
            self.path_of(value_binding) if value_binding is not None else None
        )
        # The expression the directives read: the local signal, or the
        # tracked store cell in binding mode (NEVER a scope getter, which
        # ``absorb`` would freeze — cf. ``_build_bz_data``).
        active_expr = binding_path or scope_key

        # ── Walking the children ─────────────────────────────────────
        # The ``(child, rewrap)`` pairs: a step is often WRAPPED — a
        # ``@refreshable`` zone to refresh alone, a ``ui.fragment``. The
        # wrapper is not an instance of ``Step``, so sorting by type
        # missed it and the step **disappeared**, with no error (measured
        # on 2026-08-23: 4,022 → 2,185 characters). The rewrap travels
        # WITH the child because the render happens further down, once
        # the indices are known.
        steps: list[tuple[Step, Any]] = []
        panels: list[tuple[StepPanel, Any]] = []
        passthrough: list[Element] = []
        for raw in self._children:
            child, rewrap = unwrap_transparent(raw)
            if isinstance(child, Step):
                steps.append((child, rewrap))
            elif isinstance(child, StepPanel):
                panels.append((child, rewrap))
            else:
                rendered = self._render_one(raw)
                if isinstance(rendered, Element):
                    passthrough.append(rendered)

        # The greatest reachable index: one panel more than steps is
        # the "done" screen, and ``next()`` must be able to reach it.
        max_index = max(max(len(steps), len(panels)) - 1, 0)

        # ── The chrome, computed ONCE for all the steps ──────────────
        # Nine values identical from one step to the next: passing them
        # one by one would make a signature with thirteen keywords of
        # which only four vary. The context groups them; ``step_class``
        # and ``body_class`` stay parameters because they depend on the
        # rank (the last step claims no share and pushes nothing below
        # it any more).
        chrome: dict[str, Any] = {
            "clickable": clickable,
            "rail_class": self.slot_class("rail", axis.get("rail", "")),
            "bullet_class": self.slot_class("bullet", size_cfg.get("bullet", "")),
            "connector_class": self.slot_class("connector", axis.get("connector", "")
            ),
            "label_class": self.slot_class("label", size_cfg.get("label", "")),
            "description_class": self.slot_class("description", size_cfg.get("description", "")
            ),
            "icon_size": size_cfg.get("icon_size", "sm"),
            "active_expr": active_expr,
            "initial_index": initial_index,
        }

        last_index = len(steps) - 1
        step_nodes = [
            rewrap(step._render_in_stepper(
                index=index,
                is_last=index == last_index,
                step_class=self.slot_class("step", axis.get(
                        "step_last" if index == last_index else "step", ""
                    ),
                ),
                body_class=self.slot_class("body", axis.get("body", ""),
                    axis.get("body_last", "") if index == last_index else "",
                ),
                chrome=chrome,
            ))
            for index, (step, rewrap) in enumerate(steps)
        ]

        panel_class = self.slot_class("panel")
        panel_nodes = [
            rewrap(panel._render_panel(
                index=index,
                panel_class=panel_class,
                active_expr=active_expr,
                initial_index=initial_index,
            ))
            for index, (panel, rewrap) in enumerate(panels)
        ]

        # ── Hidden input — form data + source of the ``change`` ─────
        # An ``<ol>`` has neither ``name``/``value`` nor a native
        # ``change``: we relocate any change listener (client
        # ``bz-on:change`` or the server ``hx-*`` bundle) onto the input,
        # whose ``bz-effect`` re-fires a ``change`` at every move of the
        # index.
        root_attrs = self.emit_attrs()
        relocated = _pop_change_handler(root_attrs)
        name = self._reactive_values.get("name") or self._derive_field_name()

        hidden_node: Element | None = None
        if name or relocated:
            hidden_attrs: dict[str, Any] = {
                **hidden_carrier_attrs(active_expr, initial=initial_index),
            }
            if name:
                hidden_attrs["name"] = str(name)
            hidden_attrs.update(relocated)
            hidden_node = Element(tag="input", attrs=hidden_attrs, children=())

        # ── Assembly ─────────────────────────────────────────────────
        # The scope + the imperative listeners live on the WRAPPER, not
        # on the ``<ol>``: the panels and the hidden input are outside
        # the list (an ``<ol>`` only accepts ``<li>``) and must
        # nevertheless read the same signal. The wrapper is also the real
        # root — that is where ``classes=`` and a possible
        # ``slots={"root": …}`` land.
        ordered_list = Element(
            tag="ol",
            attrs={"class": self.slot_class("list", axis.get("list", ""))},
            children=tuple(step_nodes),
        )
        wrapper_children: list[Node] = [ordered_list]
        if hidden_node is not None:
            wrapper_children.append(hidden_node)
        if panel_nodes:
            wrapper_children.append(
                Element(
                    tag="div",
                    attrs={"class": self.slot_class("panels")},
                    children=tuple(panel_nodes),
                )
            )
        # A foreign child (text, an injected divider) lands on the
        # WRAPPER, not in the ``<ol>`` — for the reason that made this
        # wrapper exist: an ordered list only accepts ``<li>``, and
        # slipping it in there would produce invalid HTML.
        wrapper_children.extend(passthrough)

        root_attrs["class"] = self.slot_class("root")
        root_attrs["bz-data"] = _build_bz_data(
            scope_key=scope_key,
            has_local_value=value_binding is None,
            initial_value=initial_index,
            binding_path=binding_path,
            max_index=max_index,
            server_synced=value_server_backed,
        )
        # Reception of the imperative commands issued by an external
        # trigger (``wizard.next()`` on a button elsewhere in the page).
        root_attrs["bz-on:bz-set"] = "goTo($event.detail.value)"
        root_attrs["bz-on:bz-next"] = "next()"
        root_attrs["bz-on:bz-prev"] = "prev()"

        return Element(
            tag=self._tag, attrs=root_attrs, children=tuple(wrapper_children)
        )


class Step(Component):
    """Describe one step in a stepper."""

    THEME_KEY: ClassVar[str] = "step"
    IS_CONTAINER: ClassVar[bool] = False
    # The current index lives at the parent's: one binding per step
    # would mean N bindings for the same information.
    BINDABLE_PROPS: ClassVar[tuple[str, ...]] = ()
    NAMED_SLOTS: ClassVar[tuple[str, ...]] = ("icon",)
    ICON_SLOTS: ClassVar[tuple[str, ...]] = ("icon",)

    label: Any = reactive_prop(default="", emit_attr=False)
    description: Any = reactive_prop(default="", emit_attr=False)
    status: str | None = reactive_prop(default=None, emit_attr=False)
    disabled: bool = reactive_prop(default=False, emit_attr=False)

    def __init__(
        self,
        label: Any = "",
        *,
        description: Any = None,
        icon: Any = None,
        status: str | None = None,
        disabled: bool | None = None,
        **kwargs: Any,
    ) -> None:
        # Direct forward: the base layer drops reactive None kwargs (keeps the default).
        super().__init__(
            label=label,
            description=description,
            status=status,
            disabled=disabled,
            icon=icon,
            **kwargs,
        )

    # ── Internal render — called by Stepper ───────────────────────────

    def _render_in_stepper(
        self,
        *,
        index: int,
        is_last: bool,
        step_class: str,
        body_class: str,
        chrome: dict[str, Any],
    ) -> Element:
        """``chrome`` = the chrome identical for every step, computed
        once by ``Stepper.render()`` (composed classes, icon size, index
        expression, clickable flag)."""
        clickable: bool = chrome["clickable"]
        icon_size: str = chrome["icon_size"]
        initial_index: int = chrome["initial_index"]

        label = self._reactive_values.get("label")
        description = self._reactive_values.get("description")
        frozen_status = self._reactive_values.get("status")
        disabled = bool(self._reactive_values.get("disabled"))
        status_expr = f"_status({index})"

        # ── The state driver ─────────────────────────────────────────
        # An explicit status is frozen: it does not depend on the current
        # index, so there is no reason to recompute it on the client
        # side.
        step_attrs: dict[str, Any] = {"class": step_class}
        if frozen_status:
            step_attrs["data-status"] = str(frozen_status)
        else:
            initial_status = (
                "done"
                if index < initial_index
                else ("current" if index == initial_index else "upcoming")
            )
            # Static SSR so the first paint is right, then reactive.
            # The literal string is mandatory: a bare boolean would DROP
            # the attribute at false and ``data-[status=…]`` would never
            # match (cf. ``bool_attr``, same class of trap).
            step_attrs["data-status"] = initial_status
            step_attrs["bz-attr:data-status"] = status_expr
            step_attrs["bz-attr:aria-current"] = (
                f"({status_expr} === 'current') ? 'step' : false"
            )
            if initial_status == "current":
                step_attrs["aria-current"] = "step"

        # ── La pastille ──────────────────────────────────────────────
        bullet_children: list[Node] = []
        icon = self._slot_components.get("icon")
        if isinstance(icon, Component):
            # An explicit icon: it replaces BOTH number and check, in
            # all four statuses.
            bullet_children.append(Component.render_detached(icon))
        elif frozen_status == "error":
            bullet_children.append(
                Component.render_detached(Icon("triangle-alert", size=icon_size))
            )
        else:
            # Two glyphs mounted, one visible: the number as long as
            # the step is not done, the check afterwards. Two nodes
            # rather than rewritten content — the runtime does not
            # replace text, it toggles a ``display``.
            #
            # The pre-stamp follows the INDEX, not ``frozen_status``: the
            # only explicit status is ``error``, handled above. Accepting
            # a ``status="done"`` here would only half work — the
            # ``data-status`` would be frozen but both ``bz-show`` would
            # go on reading ``_status(index)``, so the runtime would
            # invert the pre-stamp as soon as it hydrated.
            is_done = index < initial_index
            number = Element(
                tag="span",
                attrs={"bz-show": f"{status_expr} !== 'done'"},
                children=(TextNode(str(index + 1)),),
            )
            if is_done:
                stamp_display_none(number.attrs)
            check = Icon("check", size=icon_size)
            check_node = Component.render_detached(check)
            if isinstance(check_node, Element):
                check_node.attrs["bz-show"] = f"{status_expr} === 'done'"
                if not is_done:
                    stamp_display_none(check_node.attrs)
            bullet_children.extend((number, check_node))

        bullet_attrs: dict[str, Any] = {"class": chrome["bullet_class"]}
        if disabled:
            # In BOTH modes. When clickable the ``<button disabled>``
            # below would be enough for a11y, but it is ``aria-disabled``
            # that the theme reads to dim — and when NOT clickable the
            # chip is a ``<span>``, where ``:disabled`` never matches:
            # ``disabled=True`` therefore had NO effect there, neither
            # visual nor announced (measured on 2026-08-13, while
            # clearing ``_UNAUDITED``).
            bullet_attrs["aria-disabled"] = "true"
        if clickable and not disabled:
            bullet_tag = "button"
            bullet_attrs["type"] = "button"
            bullet_attrs["bz-on:click"] = f"goTo({index})"
        elif clickable:
            bullet_tag = "button"
            bullet_attrs["type"] = "button"
            bullet_attrs["disabled"] = True
        else:
            # Not clickable = no ``<button>`` at all: nothing in the
            # tab order, nothing to announce as actionable.
            bullet_tag = "span"
        bullet = Element(
            tag=bullet_tag, attrs=bullet_attrs, children=tuple(bullet_children)
        )

        rail_children: list[Node] = [bullet]
        if not is_last:
            rail_children.append(
                Element(
                    tag="span",
                    attrs={"class": chrome["connector_class"], "aria-hidden": "true"},
                    children=(),
                )
            )

        # ── Le corps ─────────────────────────────────────────────────
        body_children: list[Node] = []
        if label is not None and label != "":
            body_children.append(
                Element(
                    tag="span",
                    attrs={"class": chrome["label_class"]},
                    children=(_text_or_component(label),),
                )
            )
        if description is not None and description != "":
            body_children.append(
                Element(
                    tag="span",
                    attrs={"class": chrome["description_class"]},
                    children=(_text_or_component(description),),
                )
            )

        children: list[Node] = [
            Element(
                tag="div", attrs={"class": chrome["rail_class"]},
                children=tuple(rail_children),
            )
        ]
        if body_children:
            children.append(
                Element(
                    tag="div",
                    attrs={"class": body_class},
                    children=tuple(body_children),
                )
            )

        return Element(tag="li", attrs=step_attrs, children=tuple(children))

    def render(self) -> Element:
        # Outside a Stepper, a step has no status context.
        return Element(tag="span", attrs={}, children=())


class StepPanel(Component):
    """Render content when its step is active."""

    THEME_KEY: ClassVar[str] = "step_panel"
    BINDABLE_PROPS: ClassVar[tuple[str, ...]] = ()

    def __init__(self, **kwargs: Any) -> None:
        # An explicit signature although it adds no parameter: without
        # it, public introspection reports the base layer's ``*_args`` as
        # if it were a surface of the component.
        super().__init__(**kwargs)

    def _render_panel(
        self,
        *,
        index: int,
        panel_class: str,
        active_expr: str,
        initial_index: int,
    ) -> Element:
        # ``Number(...)``: the value can come back from a form data as
        # a string (the hidden input serialises it), and ``"1" === 1`` is
        # false.
        # No ``role``: a step panel is not a ``tabpanel`` (there is no
        # ``tablist``, and linking it to a chip with ``aria-controls``
        # would lie about the control's nature). The hidden panel is
        # hidden by ``display:none``, which screen readers already
        # respect.
        attrs: dict[str, Any] = {
            "class": panel_class,
            "bz-show": f"Number({active_expr}) === {index}",
        }
        if index != initial_index:
            # Anti-FOUC: pre-stamped hidden, otherwise the panel
            # flickers before the first ``bz-show`` effect.
            stamp_display_none(attrs)
        return Element(
            tag="div", attrs=attrs, children=tuple(self._render_children())
        )

    def render(self) -> Element:
        # Standalone use — the content appears, without the toggle wiring.
        return Element(
            tag="div",
            attrs={"class": "outline-none"},
            children=tuple(self._render_children()),
        )


def _text_or_component(value: Any) -> Node:
    """A textual slot's content: a rendered Component, otherwise text.

    No ClientBinding branch — ``label`` / ``description`` are not
    bindable, and a binding lives in ``_binding_metadata``, never in
    ``_reactive_values`` (cf. traps.md § "Reading a binding through
    _reactive_values + isinstance").
    """
    if isinstance(value, Component):
        return Component.render_detached(value)
    return TextNode(str(value))


__all__ = ["Step", "StepPanel", "Stepper"]
