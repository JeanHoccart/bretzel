"""``Radio`` + ``RadioGroup`` — single-choice input cluster.

Composition pattern : children ``Radio`` instances live inside a
``RadioGroup`` ``with`` block. The group provides the ``value=``
(currently selected) ; each radio emits an ``<input type="radio">``
named PRIVATELY to its group (``_<group id>``), plus a styled
fake-circle + dot overlay (same idiom as checkbox / switch). The
FIELD (``name=``, or the autoname ``State.field``) rides one hidden
carrier per group: two groups of one field are two groups for the
browser, not one.

Two-way bind via ``value=state.field`` on the GROUP — the radio
children all wire ``bz-model`` to that path. Native browser semantics
(only one radio in a group can be checked) carry through.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, ClassVar

from bretzel.components.base import Component, reactive_prop
from bretzel.components.base.arguments import has_content, reject_sealed
from bretzel.components.base.attrs import ComponentUsageError
from bretzel.components.base.commands import ValueCommands
from bretzel.components.base.focus import FocusCommands
from bretzel.components.inputs.radio.theme import (
    RADIO_GROUP_THEME,
    RADIO_THEME,
)
from bretzel.core.tree import Element

#: Marks a group's hidden value carrier (``RadioGroup.render``).
_CARRIER = "data-bz-radio-value"


class RadioGroup(ValueCommands, FocusCommands, Component):
    """Container for a cluster of ``Radio`` items. Owns the ``name``
    and the bound ``value``."""

    THEME: ClassVar[dict[str, Any]] = RADIO_GROUP_THEME
    THEME_KEY: ClassVar[str] = "radio_group"
    BINDABLE_PROPS: ClassVar[tuple[str, ...]] = ("value", "disabled")
    IMPERATIVE: ClassVar[tuple[str, ...]] = ("set", "clear", "focus", "blur")
    # Where ``autofocus=`` / ``.focus()`` land: the checked radio, else the first.
    FOCUS_TARGET: ClassVar[tuple[str, ...] | None] = (
        "input:checked:not([disabled])", "input:not([disabled])",
    )
    EVENTS: ClassVar[tuple[str, ...]] = ("change",)

    name: str | None = reactive_prop(default=None, emit_attr=False)
    value: Any = reactive_prop(default=None, emit_attr=False, writes=True, names_field=True)
    direction: str = reactive_prop(default="col", emit_attr=False)
    color: str = reactive_prop(default="primary", emit_attr=False)
    # No ``steps=`` here: the group has no table of its own, and the
    # child's is only read THROUGH ITS RESOLUTION (an app's
    # ``Theme(components={"radio": …})`` replaces it). It is the child
    # that refuses the EFFECTIVE size, at render — cf. ``Radio.render``.
    size: str = reactive_prop(default="md", emit_attr=False)
    disabled: bool = reactive_prop(default=False, emit_attr=False)
    required: bool = reactive_prop(default=False, emit_attr=False)

    def __init__(
        self,
        *,
        name: str | None = None,
        value: Any = None,
        direction: str | None = None,
        color: str | None = None,
        size: str | None = None,
        disabled: bool | None = None,
        required: bool | None = None,
        on_change: Callable[..., Any] | str | None = None,
        **kwargs: Any,
    ) -> None:
        # Direct forward: the base layer drops reactive None kwargs (keeps the default).
        super().__init__(
            name=name, value=value, direction=direction,
            color=color, size=size, disabled=disabled,
            required=required,
            on_change=on_change,
            **kwargs,
        )
        # An unknown direction would render NO class, without a word, and
        # the choices would go in a cramped row. Same refusal as
        # ``Flex``'s tables. A bound direction is not a literal: it is
        # not checked here.
        literal = self._reactive_values.get("direction")
        directions = self._resolved_theme().get("directions", {})
        if isinstance(literal, str) and literal not in directions:
            accepted = ", ".join(repr(k) for k in directions)
            raise ComponentUsageError(
                f"RadioGroup(direction={literal!r}) is not a known value. "
                f"Accepted values: {accepted}.\n"
                f"  Without this refusal, the call would render an EMPTY "
                f"class — valid HTML, no error, the choices simply in a row."
            )

    def render(self) -> Element:
        theme = self._resolved_theme()
        direction = self._reactive_values.get("direction") or "col"
        direction_class = theme.get("directions", {}).get(direction, "")
        # ``classes=`` set on the real root by the
        # ``_apply_universal_modifiers`` metaclass wrap — not here
        # (otherwise a duplicate). Guarded by
        # test_no_manual_user_class_append.py.
        root_class = " ".join(
            p
            for p in (
                theme.get("slots", {}).get("root", ""),
                direction_class,
            )
            if p
        )
        attrs = self.emit_attrs()
        attrs["class"] = root_class
        # Server ``on_change`` lands on THIS group ``<div>`` (the
        # group-level event), but the picked value lives on a child
        # ``<input type="radio">`` — and only the checked one serialises.
        # A ``<div>`` has no form value of its own and htmx does NOT walk
        # descendants by default, so without this the POST carries an
        # EMPTY form and ``on_change(value=...)`` never sees the pick
        # (the bound value still rides as namespaced signal state, but
        # that's consumed as state-sync, not handler kwargs). Pull the
        # group's VALUE CARRIER (below) into the request via
        # ``hx-include`` scoped to this group's id. Works for BOTH bound
        # (autoname ``name="State.field"``) and unbound (explicit
        # ``name=``) groups.
        if "hx-post" in attrs:
            group_id = attrs.get("id")
            if group_id:
                attrs["hx-include"] = f"#{group_id} input[{_CARRIER}]"
        # role + aria-required for screen readers : the cluster is the
        # actual semantic radiogroup, not the individual <input>s.
        attrs.setdefault("role", "radiogroup")
        if self._reactive_values.get("required"):
            attrs.setdefault("aria-required", "true")
        # Imperative-API listener — catches ``radio_group.set(value)``
        # when no binding is in play. Iterate the child radios, flip
        # ``.checked`` to match the payload, then fire a synthetic
        # ``change`` on the selected one so ``on_change=`` handlers run
        # (and ``bz-model`` syncs in the binding case). Nothing ticked
        # (``.clear()``): no radio can tell, so the group empties the field
        # and fires the ``change`` itself. Cf. `imperative-api.md`.
        attrs["bz-on:bz-set"] = (
            "let hit = false; "
            "$el.querySelectorAll('input[type=\"radio\"]').forEach("
            "r => { r.checked = (r.value === String($event.detail.value)); "
            "if (r.checked) { hit = true; r.dispatchEvent("
            "new Event('change', {bubbles: true})); } }); "
            f"if (!hit) {{ const c = $el.querySelector('[{_CARRIER}]'); "
            "if (c) c.value = ''; "
            "$el.dispatchEvent(new Event('change', {bubbles: true})); }"
        )
        # ── Two names, two jobs ──────────────────────────────────────
        # A radio's ``name`` does TWO things: the browser groups every
        # radio of one name (one ticked among them), and a form sends the
        # ticked one under it. One name cannot do both once two groups
        # share a field: several groups bound to one ``value`` would be
        # ONE group for the browser, and ticking an option in the first
        # would untick it everywhere else. Same with two
        # ``ui.radio_group(name="plan")`` in two cards.
        #
        # So the radios take a name PRIVATE to this group — its identity,
        # prefixed ``_``, the wire's mark for plumbing (never handed to a
        # ``**kwargs`` handler) — and the FIELD rides a hidden carrier:
        # an explicit ``name=``, else the autoname (``State.field``). The
        # carrier follows the ticked radio (each radio writes it on
        # ``change``, before the group's own ``hx-trigger`` reads it) and,
        # bound, the store (a mirror group elsewhere ticking for it).
        self._radio_name = f"_{self.id}"
        field_name = self._reactive_values.get("name") or attrs.get("name")
        self._carries_value = bool(field_name)
        children = list(self._render_children())
        if field_name:
            initial = self._reactive_values.get("value")
            carrier: dict[str, Any] = {
                "type": "hidden",
                "name": field_name,
                "value": "" if initial is None else str(initial),
                _CARRIER: "",
            }
            binding = self._binding_metadata.get("value")
            if binding is not None:
                carrier["bz-attr:value"] = self.path_of(binding)
            # A disabled group sends nothing, as its disabled radios do.
            if self._reactive_values.get("disabled") is True:
                carrier["disabled"] = True
            self.forward_binding("disabled", carrier)
            children.insert(0, Element(tag="input", attrs=carrier, children=()))
        return Element(
            tag=self._tag,
            attrs=attrs,
            children=tuple(children),
        )


class Radio(Component):
    """One choice inside a :class:`RadioGroup`. Inherits ``name``,
    ``value`` (binding), ``color``, ``size`` from the group's
    reactive props at render time — explicit kwargs on the radio
    override per-item if needed."""

    THEME: ClassVar[dict[str, Any]] = RADIO_THEME
    THEME_KEY: ClassVar[str] = "radio"
    DEFAULT_TAG: ClassVar[str] = "label"
    IS_CONTAINER: ClassVar[bool] = False
    # An individual Radio item inherits the binding from the group ;
    # the only per-item bindable is ``disabled`` (rare but legit
    # for "this option locked, others available" patterns).
    BINDABLE_PROPS: ClassVar[tuple[str, ...]] = ("disabled",)
    EVENTS: ClassVar[tuple[str, ...]] = ("change", "focus", "blur")

    # The radio's own ``value`` (the option's value, not the bound
    # value) — kept distinct from the group's ``value=binding``.
    option_value: str = reactive_prop(default="", emit_attr=False)
    # Fed from the option's positional ``value``. Passing it explicitly
    # is refused by ``reject_sealed``, called at the head of
    # ``__init__`` — it MUST be there, before the ``super().__init__``:
    # the kwarg collision is raised by Python when building the call, so
    # the base layer never sees it.
    SEALED_PROPS: ClassVar[tuple[str, ...]] = ("option_value",)
    #: The refusal's message. Without it, ``reject_sealed``'s default
    #: speaks of an AXIS — true for a stack, false here.
    SEALED_REASONS: ClassVar[dict[str, str]] = {
        "option_value": (
            "Radio(option_value=…): this prop is fed by the option's "
            "positional ``value`` — write "
            "``ui.radio(\"my-value\")``. Passing it as well would produce "
            "two values for the same field, which is an ambiguity, not a "
            "shortcut."
        ),
    }
    name: str | None = reactive_prop(default=None)
    color: str | None = reactive_prop(default=None, emit_attr=False)
    # ``None`` = inherit from the group, so the generic refusal cannot
    # read this table: it is the DEFAULT that serves as the anchor for
    # knowing which of a nested table's two levels carries the steps. The
    # effective size is therefore refused at render — cf. ``render``.
    size: str | None = reactive_prop(default=None, emit_attr=False)
    disabled: bool = reactive_prop(default=False)
    required: bool = reactive_prop(default=False)

    def __init__(
        self,
        value: str,
        *,
        label: str | Component | None = None,
        name: str | None = None,
        color: str | None = None,
        size: str | None = None,
        disabled: bool | None = None,
        required: bool | None = None,
        on_change: Callable[..., Any] | str | None = None,
        on_focus: Callable[..., Any] | str | None = None,
        on_blur: Callable[..., Any] | str | None = None,
        **kwargs: Any,
    ) -> None:
        reject_sealed(kwargs, type(self))
        # Direct forward: the base layer drops reactive None kwargs (keeps the default).
        # ``option_value`` (the option's positional ``value``) is always
        # passed on — it is not a None guard.
        super().__init__(
            option_value=value,
            name=name, color=color, size=size,
            disabled=disabled, required=required,
            on_change=on_change,
            on_focus=on_focus,
            on_blur=on_blur,
            **kwargs,
        )
        self._label = label
        # Capture the enclosing RadioGroup at construction time : the
        # ``with RadioGroup(...) as rg`` block is still active here, so
        # the group is on ``parent_stack``. By render time the ``with``
        # has exited and the stack lookup would return None.
        self._group: RadioGroup | None = self._lookup_group()

    def _size_key(self) -> str | None:
        """Its own ``size=``, else its group's, else ``md``: a radio's
        size is ``None`` by default — "inherit"."""
        group = self._group
        return self._reactive_values.get("size") or (
            group._reactive_values.get("size") if group else None
        ) or "md"

    def render(self) -> Element:
        # Inherit name / size / disabled / value-binding from the
        # enclosing RadioGroup captured at construction time.
        #
        # ``color`` is NOT in that list, and it is not an oversight: the
        # group carries the ``bz-c-<colour>`` bridge class on its root,
        # and the eleven steps flow down in CSS over the whole subtree.
        group = self._group
        size_key = self._size_key()
        # The out-of-table refusal, HERE and not on the prop — it is
        # the only point where the EFFECTIVE size exists. Two reasons:
        #
        # - ``Radio.size`` is ``None`` by default ("inherit"), and the
        #   generic refusal uses the default as an ANCHOR to know which
        #   of a nested table's two levels carries the steps. With no
        #   anchor it abstains, and ``size="zzz"`` would render a radio
        #   WITH NO SIZE AT ALL;
        # - the size can come from the GROUP, which has no table of its
        #   own. ``ui.radio_group(size="zzz")`` would therefore go through
        #   the whole render without a word.
        #
        # The table is read RESOLVED: an app's ``Theme(components=
        # {"radio": …})`` replaces the steps, and a list frozen in the
        # class body would then refuse a correct value.
        steps = self._resolved_theme().get("sizes", {})
        if steps and size_key not in steps:
            raise ComponentUsageError(
                f"ui.radio: size={size_key!r} is not in the theme's "
                f"table. Known values: {', '.join(sorted(steps))}.\n"
                f"  A value outside the table does not raise by itself: "
                f"the radio would render with no size at all, without a "
                f"word. The size can come from the radio or from its "
                f"group."
            )
        # Inherit the group's EFFECTIVE name (explicit ``name=`` OR the
        # autoname derived from its ``value=`` binding), stashed on the
        # group at render time. A bound group's autoname (``name="value"``)
        # only reaches the radios this way — ``_reactive_values["name"]``
        # is None for autoname.
        name = self._reactive_values.get("name") or (
            getattr(group, "_radio_name", None) if group else None
        )
        # ``disabled`` from the group propagates to every radio (native
        # HTML has no "disable a radio group" — the only way to lock
        # the cluster is to stamp ``disabled`` on each ``<input>``).
        # Two paths :
        # - Group has a ClientBinding → adopt it as this radio's own
        #   ``disabled`` binding so emit_attrs stamps the reactive
        #   ``bz-attr:disabled`` directive on the input. Only when
        #   the radio doesn't already have its own per-item binding.
        # - Group has a literal truthy ``disabled`` → force-lock this
        #   radio (static, no reactivity). Wins over per-item state.
        if group is not None:
            group_disabled_binding = group._binding_metadata.get("disabled")
            if (
                group_disabled_binding is not None
                and "disabled" not in self._binding_metadata
            ):
                self._binding_metadata["disabled"] = group_disabled_binding
                # ``getattr(…, "value", False)``: a ClientExpression has
                # no server value (it is computed by the runtime) — same
                # contract as the base layer, which stores ``None`` for
                # the SSR and lets the runtime decide at boot. Without
                # the default, a ``ui.radio_group(disabled=expr)`` crashed
                # the render of every child Radio.
                self._reactive_values["disabled"] = bool(
                    getattr(group_disabled_binding, "value", False)
                )
            elif group._reactive_values.get("disabled"):
                self._reactive_values["disabled"] = True
        # Two streams from the group : the binding (for ``bz-model``)
        # and the underlying SSR value (for the static ``checked``
        # match below). The binding lives in ``_binding_metadata`` ;
        # ``_reactive_values["value"]`` carries the resolved SSR value
        # whether or not a binding was passed.
        group_binding = (
            group._binding_metadata.get("value") if group else None
        )
        bound_value = (
            group._reactive_values.get("value") if group else None
        )

        opt_value = self._reactive_values.get("option_value") or ""

        # The real <input>. Sr-only ; carries name + value + framework
        # attrs ; bz-model when the group has a binding.
        input_attrs: dict[str, Any] = {
            "type": "radio",
            "value": str(opt_value),
            "class": self.compose_class("input"),
        }
        input_attrs.update(self.emit_attrs())

        if name:
            input_attrs["name"] = name
        # The group's value carrier follows the ticked radio — written on
        # the radio itself, so before the group's ``hx-trigger="change"``
        # (bubbling, on the root) serialises it (``RadioGroup.render``).
        if group is not None and getattr(group, "_carries_value", False):
            write = (
                "$el.closest('[role=radiogroup]')"
                f".querySelector('[{_CARRIER}]').value = $el.value"
            )
            prior = input_attrs.get("bz-on:change")
            input_attrs["bz-on:change"] = f"{write}; {prior}" if prior else write
        # Binding lives on the GROUP, not on this radio — inject it
        # through ``_bind_x_model``'s explicit-binding overload. When
        # the group has no binding the helper is a no-op and we fall
        # back to the static-value match for the SSR initial state.
        if (
            self._bind_x_model(
                input_attrs, prop="value", binding=group_binding
            )
            is None
            and bound_value is not None
            and str(bound_value) == str(opt_value)
        ):
            input_attrs["checked"] = True

        circle_class = self.compose_class("circle")
        dot_class = self.compose_class("dot")

        container = Element(
            tag="div",
            attrs={
                "class": self.compose_class("container")
            },
            children=(
                Element(tag="input", attrs=input_attrs, children=()),
                Element(
                    tag="div", attrs={"class": circle_class}, children=()
                ),
                Element(
                    tag="div", attrs={"class": dot_class}, children=()
                ),
            ),
        )

        children: list[Any] = [container]
        # A bound label (ClientBinding) refuses a truth test — has_content.
        if has_content(self._label):
            label_class = self.compose_class("label")
            children.append(
                Element(
                    tag="span",
                    attrs={"class": label_class},
                    children=(self.emit_text_slot(self._label),),
                )
            )

        return Element(
            tag=self._tag,
            attrs={"class": self.compose_class("root")},
            children=tuple(children),
        )

    def _lookup_group(self) -> RadioGroup | None:
        """Find the nearest ``RadioGroup`` on the parent stack at
        construction time. Called from ``__init__`` while the
        ``with RadioGroup(...)`` block is still active."""
        from bretzel.render.context import maybe_current_context

        ctx = maybe_current_context()
        if ctx is None:
            return None
        for parent in reversed(ctx.parent_stack):
            if isinstance(parent, RadioGroup):
                return parent
        return None
