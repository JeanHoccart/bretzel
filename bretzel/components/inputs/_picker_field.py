"""The shared mechanics of the *picker fields* — editable field + popover.

Three components have exactly the same silhouette: a wrapper ``<div>``
carrying the scope, a frame with a single focus ring containing a
typable ``<input>`` and one or two icon buttons, a form-data-carrying
``<input type=hidden>``, and an anchored panel. Only the **value codec**,
the **blur normaliser** and the **panel's content** change.

  DatePicker · DateRangePicker · TimePicker

This module extracts what is identical — and nothing else. In
particular it does **not** touch the class strings: they stay
per-component (`feedback_no_shared_style_tokens`), and the three do not
even have the same size-table shape (the two date pickers index
`sizes[slot][size]`, the inverted shape still in debt in
``test_size_reaches_slots._INVERTED_SHAPE``; TimePicker uses the
canonical shape). The factories below therefore take **already
composed** classes, never a theme.

Why extract now: the repository's threshold ("twice is a coincidence,
three times is a pattern") was crossed on 2026-08-02 with TimePicker. And
the next arrival counts — three pickers remain to be written (month /
week / date_time), which would otherwise inherit the same copied blocks.

⚠️ **The lesson that motivated the split.** While writing TimePicker I
took DatePicker as a template and copied by hand two blocks the base
layer had ALREADY extracted since (``hidden_carrier_attrs``,
``relocate_server_action``) — because DatePicker predates those
primitives and nobody migrated it. Two gates refused it. That is exactly
what this module stops from happening again: the template and the shared
code are now the same object.
"""

from __future__ import annotations

import json
from typing import Any

from bretzel.components.base import Component, stamp_display_none
from bretzel.components.base._wiring import (
    anchored_dismiss_init,
    anchored_panel_effect,
    bool_attr,
    calendar_value_mirror,
    hidden_carrier_attrs,
    imperative_listeners,
    relocate_server_action,
    server_sync_marker,
)
from bretzel.core.tree import Element, Node

#: The two events declared by the three pickers that DO NOT BUBBLE.
#: It is the whole reason for :func:`relocate_field_events`.
_NON_BUBBLING = ("focus", "blur")


def value_expr(component: Any, *, local: str | None = None) -> str:
    """The expression the DIRECTIVES read for the field's value.

    Bound (``value=state.x``) → the store path. Literal → the BARE name
    of the scope field: a directive runs in a ``with($scope)``, so the
    identifier resolves there.

    ``local`` by default = the key DECLARED on the prop
    (``reactive_prop(scope_keys=)``, read by ``_scope_keys``). It was
    hard-coded to ``"val"``, which made this helper a SECOND source for
    an already declared fact: a picker that changed key would have
    emitted a literal under one name and directives under the other —
    silently, since both exist. The parameter stays, for a caller
    addressing a scope variable that is NOT the prop's value.

    ⚠️ These two lines were written **five times**, one per picker, and
    what differed was not the code — it was the docstrings: four
    explanations of the same mechanism, one absence. It is exactly what
    `creating-a-component.md` holds against unfactored renders, "what
    stopped you knowing whether the two behaved the same without
    re-reading both". The five ALREADY called this family's helpers: it
    was 90 % factored, these two lines had stayed behind.
    """
    binding = component._binding_metadata.get("value")
    if binding is not None:
        return component.path_of(binding)
    return local if local is not None else component._scope_keys("value")[0]


def relocate_field_events(
    root_attrs: dict[str, Any],
    *,
    value_carrier: dict[str, Any],
    focusable: dict[str, Any],
) -> None:
    """Empty the root of its handlers, towards the carrier that can fire them.

    A picker has a ``<div>`` root: **not focusable, and with neither
    ``name`` nor ``value``**. Three things follow, and each is a silent
    bug if forgotten:

    - ``focus`` / ``blur`` do **not bubble**. A handler left on the root
      can structurally NEVER fire — there is no path by which the event
      would reach it. (``change``, for its part, bubbles natively from
      the input, hence the different treatment.)
    - the SERVER action bundle must be routed according to what the
      handler really listens to: a ``change`` towards the value carrier
      (otherwise the FormData leaves empty), a ``focus`` towards the
      focusable element. It is ``relocate_server_action`` that decides,
      by reading ``hx-trigger`` — written by hand, it is the Slider bug
      coming back (a callable ``on_focus`` set on a hidden input, which
      fires on the change).
    - the STRING version of those handlers (``bz-on:focus``) must follow
      the same path as the callable version, otherwise the two shapes of
      the same prop behave differently.

    Both dictionaries are filled IN PLACE; the caller pours them onto
    its elements. ``root_attrs`` is emptied of the moved keys.
    """
    for event in _NON_BUBBLING:
        key = f"bz-on:{event}"
        if key in root_attrs:
            focusable[key] = root_attrs.pop(key)
    relocate_server_action(
        root_attrs, value_carrier=value_carrier, focusable=focusable
    )


def detach_wrapper_carriers(component: Any, root_attrs: dict[str, Any]) -> str:
    """Remove from the root what makes no sense there, and return the ``name``.

    ``value``: the picker addresses its value by an EXPRESSION (the store
    path, or a scope variable). The directive auto-emitted by the base
    layer would rewrite a useless ``value=""`` on a ``<div>`` at every
    reactive tick — and the carrier-landing audit reports it.

    ``name``: the autoname injects it on the root, but the form-data
    carrier is the ``<input type=hidden>``, which sets it itself.
    Releasing it guarantees the name lives in **exactly one place**.

    Returns the resolved field name — explicit, then autoname, then the
    ``"value"`` fallback that keeps an unbound picker present in the
    form. The three pickers had the same chain.
    """
    component.release_root_attr("value", root_attrs)
    component.release_root_attr("name", root_attrs)
    return str(
        component._reactive_values.get("name")
        or component._derive_field_name()
        or "value"
    )


def hidden_carrier(
    *,
    value_expr: str,
    initial: Any,
    name: str,
    required: bool,
    extra: dict[str, Any] | None = None,
) -> Element:
    """The ``<input type=hidden>`` that carries the value in the form data.

    The skeleton comes from ``hidden_carrier_attrs`` (type / bz-ref /
    SSR value / bz-attr:value); ``name`` and ``required`` stay set here
    because the primitive DELIBERATELY leaves them to the caller — a
    default ``name`` would inject a stray field into every enclosing
    form, which is not the case for a picker but is for a Tabs or an
    Accordion.

    ``required`` lives on this carrier and **not** on the visible field:
    HTML validation must look at the real value, not at the text being
    typed. The visible field only gets an ``aria-required``.

    ⚠️ **``change_emit_effect`` is not decorative — without it the picker
    is INERT.** ``relocate_server_action`` routes the ``on_change=``
    bundle HERE, because it is this carrier the FormData must find; yet a
    hidden input never fires ``change`` by itself, and the panel's
    ``<bz-calendar>`` writes the value **programmatically** — a write of
    ``.value`` emits no event. The five pickers therefore lived without
    any server ``on_change`` ever firing, with no error and no warning
    (measured on 2026-08-21: "the period does not filter"). It is the
    SAME dispatcher as the catalogue's eleven other hidden carriers, and
    the class is gated by
    ``tests/consistency/test_a_relocated_change_reaches_its_carrier.py``.
    """
    attrs: dict[str, Any] = {
        **hidden_carrier_attrs(value_expr, initial=initial),
        "name": name,
    }
    if required:
        attrs["required"] = True
    if extra:
        attrs.update(extra)
    return Element(tag="input", attrs=attrs, children=())


def calendar_picker_scope(
    component: Any, *, value_expr: str, initial: str
) -> str:
    """The ``bz-data`` of a picker whose panel is a ``<bz-calendar>``.

    Two modes, and that is the whole logic:

    - **bound** — the value lives in the store, so the scope carries only
      the ``open`` flag. No sync to maintain: each directive addresses
      ``$bz.state.<path>`` directly.
    - **literal** — a local variable, named by the scope key DECLARED on
      the prop, seeds the SSR value.
      ``scope.absorb`` PRESERVES it across a morph, which is exactly what
      we want for a user's editing — but which would make a SERVER change
      on a ``value=state.x`` be ignored. Hence ``_serverSync``, emitted
      ONLY when the value is server-backed (a pure literal keeps its
      client value).

    Used by :func:`render_calendar_field` for MonthPicker and
    WeekPicker. DatePicker still builds its scope separately;
    DateRangePicker carries two variables (``vstart`` / ``vend``).
    """
    if component._binding_metadata.get("value") is not None:
        return "{open: false}"
    (key,) = component._scope_keys("value")
    sync = server_sync_marker(
        key, enabled=component._value_server_backed("value")
    )
    return (
        f"{{open: false, {key}: {json.dumps(initial)}"
        + (f",{sync}" if sync else "")
        + "}"
    )


def panel_calendar(owner: Any, cal_kwargs: dict[str, Any]) -> Element:
    """The panel's ``<bz-calendar>`` — detached, but ADDRESSED by its picker.

    The four date pickers built these three lines identically. They live
    here for the ``id``, which is load-bearing and cannot be guessed.

    ⚠️ **Why an explicit ``id``.** A component built during another's
    ``render()`` does not have its constructor on the ``parent_stack`` —
    the picker is not a container, it never stacks there. Its ``id`` is
    therefore derived from ``"root"`` and is ``root_calendar_0``,
    ``root_calendar_1``… **on every page**.

    Yet the ``bz-id`` indexes the runtime's scope store, a ``Map`` that
    SURVIVES an ``hx-boost`` navigation (the runtime is not reloaded).
    Two different picker pages therefore claimed the same scope: after a
    click in the sidebar, the new page's calendar found the old page's
    scope, whose parent is the PREVIOUS page's picker. The ``on_change``
    handler then wrote its value into a dead scope — highlighted grid,
    empty field, and an F5 to get out of it. The old page's ``year`` /
    ``month`` leaked by the same path, which made the calendar appear on
    a year nobody had chosen.

    Deriving the ``id`` from the picker makes it unique per page, so the
    two scopes no longer merge. ``setdefault``: a caller who passes their
    own ``id=`` stays in charge.

    The complementary hardening is on the runtime side — ``ensureScope``
    re-resolves the parent of a recovered scope, so that the CLASS does
    not come back through another id collision.
    """
    import datetime as _dt

    from bretzel.components.inputs.calendar import Calendar

    cal_kwargs.setdefault("id", f"{owner.id}_calendar")
    # ── The displayed month follows the VALUE, not today's date ──────
    # ``Calendar`` already knows how to derive its initial month from
    # ``value`` (``calendar.py``: explicit ``month=``, else the value's
    # month, else today). It still has to RECEIVE the value: the four
    # pickers did not pass it, so a
    # ``ui.date_picker(value=date(2026, 6, 15))`` opened on the CURRENT
    # month, with the selected day invisible because off grid. Measured
    # on 2026-08-19 on all four: ``month="2026-08-01"`` for a June value,
    # and no ``value`` attribute at all on the ``<bz-calendar>``.
    #
    # Only a LITERAL value is passed on: a ``ClientBinding`` has no value
    # at SSR, and it is the mirror ``bz-effect`` that will set it on the
    # client side (cf. ``calendar_value_mirror``).
    # ⚠️ The seed is UNSTAMPED before being passed. A value backed by a
    # ``ServerState`` is not a bare ``date``: it is a ``_BoundDate`` (a
    # ``date`` subclass) carrying its field's name, and from there the
    # nested calendar DERIVED its own ``name=`` — two
    # ``name="appointment"`` in the same page, so a stray field in the
    # FormData. Caught by ``test_autoname_from_server_state_field``.
    def _plain(v: object) -> object:
        if isinstance(v, _dt.date):
            return _dt.date(v.year, v.month, v.day)
        return str(v)

    if "value" not in cal_kwargs:
        seed = getattr(owner, "_reactive_values", {}).get("value")
        literal = (_dt.date, str)
        if isinstance(seed, literal) and seed:
            cal_kwargs["value"] = _plain(seed)
        elif isinstance(seed, (list, tuple)) and seed and all(
            isinstance(v, literal) and v for v in seed
        ):
            cal_kwargs["value"] = [_plain(v) for v in seed]
    inner = Calendar(**cal_kwargs)
    # The calendar is a RENDER child, not a tree child: without this
    # detachment it would stay in ``root_children`` and render a second
    # time as an orphan.
    Component._detach_from_parent(inner)
    return inner.render()


def icon_button(
    *,
    icon: str,
    css: str,
    icon_css: str,
    aria_label: str,
    on_click: str,
    disabled: bool,
    show_when: str | None = None,
    hidden_at_ssr: bool = False,
    extra: dict[str, Any] | None = None,
) -> Element:
    """One of the frame's two buttons: the ``×`` or the panel opener.

    ``show_when`` (the ``×``) makes it appear only when there is
    something to clear; ``hidden_at_ssr`` pre-stamps ``display:none`` so
    it does not flicker before the runtime takes over.

    The caller passes **already composed** classes: the three pickers do
    not have the same size-table shape, and the style strings stay
    per-component anyway.
    """
    attrs: dict[str, Any] = {
        "type": "button",
        "class": css,
        "aria-label": aria_label,
        "bz-on:click": on_click,
    }
    if show_when is not None:
        attrs["bz-show"] = show_when
        if hidden_at_ssr:
            stamp_display_none(attrs)
    if disabled:
        attrs["disabled"] = True
    if extra:
        attrs.update(extra)
    return Element(
        tag="button",
        attrs=attrs,
        children=(
            Element(
                tag="iconify-icon",
                attrs={"icon": f"lucide:{icon}", "class": icon_css},
                children=(),
            ),
        ),
    )


def trigger_button(
    *,
    icon: str,
    css: str,
    icon_css: str,
    aria_label: str,
    disabled: bool,
    open_expr: str = "open",
) -> Element:
    """The button that toggles the panel.

    ``$event.stopPropagation()`` is load-bearing: without it the click
    walks up to the ``clickOutside`` set on the root, which immediately
    closes what the toggle has just opened.

    ``aria-expanded`` is rendered STATIC then kept reactive — and through
    ``bool_attr``, because a bare boolean would DROP the attribute at
    false, whereas a screen reader must hear "collapsed".
    """
    return icon_button(
        icon=icon,
        css=css,
        icon_css=icon_css,
        aria_label=aria_label,
        on_click=f"$event.stopPropagation(); {open_expr} = !{open_expr}",
        disabled=disabled,
        extra={
            "aria-expanded": "false",
            "bz-attr:aria-expanded": bool_attr(open_expr),
        },
    )


def clear_button(
    *,
    css: str,
    icon_css: str,
    aria_label: str,
    clear_js: str,
    show_when: str,
    has_value_at_ssr: bool,
    disabled: bool,
) -> Element:
    """The ``×`` — visible only when there is a value to clear."""
    return icon_button(
        icon="x",
        css=css,
        icon_css=icon_css,
        aria_label=aria_label,
        on_click=f"$event.stopPropagation(); {clear_js}",
        disabled=disabled,
        show_when=show_when,
        hidden_at_ssr=not has_value_at_ssr,
    )


def anchored_panel(
    *,
    css: str,
    children: tuple[Node, ...],
    placement: str = "bottom-start",
    open_expr: str = "open",
    extra_effect: str = "",
) -> Element:
    """The popover: anchored by ``$bz.helpers.floating``, closed at SSR.

    ``bz-ref="bzpanel"`` is not decorative — the root's ``clickOutside``
    resolves it on EVERY click to know what counts as "inside". Without
    it, a click on the panel's padding (or on a disabled cell, which
    dispatches nothing) would close the popover. Guarded by
    ``test_dismiss_scope_owns_its_panel``.

    The ``display:none`` pre-stamp is the anti-FOUC: the panel starts
    closed, and without it it appears for a frame before the first effect
    runs.
    """
    effect = anchored_panel_effect(open_expr, placement)
    if extra_effect:
        effect = f"{effect}; {extra_effect}"
    attrs: dict[str, Any] = {
        "class": css,
        "bz-ref": "bzpanel",
        "bz-effect": effect,
    }
    stamp_display_none(attrs)
    return Element(tag="div", attrs=attrs, children=children)


def render_calendar_field(
    component: Any,
    *,
    initial: str,
    value_expr: str,
    blur_js: str,
    mirror_granularity: str | None,
    clearable: bool,
    clear_label: str,
    trigger_icon: str,
    trigger_label: str,
    calendar_kwargs: dict[str, Any],
    root_css: str,
    frame_css: str,
    panel_css: str,
    field_css: str,
    clear_css: str,
    trigger_css: str,
    icon_css: str,
) -> Element:
    """The WHOLE render of a picker with a ``<bz-calendar>`` panel.

    Measured on 2026-08-19: ``MonthPicker.render`` and
    ``WeekPicker.render`` were 130 and 125 lines, of which **107
    identical** — 82 %. They are not two components that resemble each
    other, it is one component written twice, whose differences fit in
    seven values: the initial value's format, the mirror's granularity,
    the blur-normalisation JS, two labels, an icon, and the calendar's
    kwargs.

    This module's factories (``hidden_carrier``, ``trigger_button``…)
    already covered the PIECES; what remained copied was their
    ORCHESTRATION — the order of the calls, the routing of the handlers
    to the right carrier, the blur chaining. That is where divergences
    hurt: a picker that forgets to chain the user's ``on_blur=`` loses
    their callback without breaking anything visible.

    ⚠️ **The classes arrive COMPOSED, never a theme** — this module's
    rule (`feedback_no_shared_style_tokens`), and a technical necessity:
    the two date pickers index their size table in the inverted shape
    (``sizes[slot][size]``), the others in the canonical shape. A
    function that read the theme itself would have to know both, and
    would get one of the two wrong.
    """
    root_attrs = component.emit_attrs()
    hidden_extra: dict[str, Any] = {}
    relocated: dict[str, Any] = {}
    relocate_field_events(
        root_attrs, value_carrier=hidden_extra, focusable=relocated
    )
    name = detach_wrapper_carriers(component, root_attrs)
    root_attrs["class"] = root_css
    root_attrs["bz-data"] = calendar_picker_scope(
        component, value_expr=value_expr, initial=initial
    )
    # ── The receivers of the imperative API ──────────────────────────
    #
    # Without them, `.open()` and `.set()` dispatch an event NOBODY
    # listens to: the methods exist, they emit valid JS, and nothing
    # happens. It is the costliest failure mode — it does not raise and
    # cannot be seen in review.
    #
    # In BOUND mode, the method writes straight into the store and these
    # listeners never fire; we set them anyway, so the contract is the
    # same in both modes. It is the choice already made by Sidebar,
    # Dialog and Select.
    for _ev, _handler in imperative_listeners("open").items():
        root_attrs.setdefault(_ev, _handler)
    root_attrs.setdefault(
        "bz-on:bz-set", f"{value_expr} = $event.detail.value"
    )
    # Mirror onto the ``<bz-calendar>``'s OBSERVED ``value`` attribute.
    # ``bz-attr:value`` on a custom element writes the PROPERTY, not the
    # attribute, so it would short-circuit ``attributeChangedCallback``
    # — hence the explicit ``setAttribute`` (cf. traps.md).
    mirror = (
        calendar_value_mirror(value_expr, is_range=False)
        if mirror_granularity is None
        else calendar_value_mirror(
            value_expr, is_range=False, granularity=mirror_granularity
        )
    )
    root_attrs["bz-effect"] = "(() => { " + mirror + "})()"
    root_attrs["bz-init"] = anchored_dismiss_init("open")

    disabled = bool(component._reactive_values.get("disabled"))
    required = bool(component._reactive_values.get("required"))

    hidden_input = hidden_carrier(
        value_expr=value_expr, initial=initial, name=name,
        required=required, extra=hidden_extra,
    )

    field_attrs: dict[str, Any] = {
        "type": "text",
        "placeholder": component._placeholder,
        "class": field_css,
        "value": initial,
        "bz-model": value_expr,
        "bz-on:blur": blur_js,
        "autocomplete": "off",
        "inputmode": "numeric",
        "spellcheck": "false",
        "aria-label": component._placeholder,
    }
    if disabled:
        field_attrs["disabled"] = True
    if required:
        field_attrs["aria-required"] = "true"
    if "bz-on:blur" in relocated:
        # Chain them: the internal normalisation AND the user's
        # ``on_blur=`` must both run.
        relocated["bz-on:blur"] = (
            f"{field_attrs['bz-on:blur']}; {relocated['bz-on:blur']}"
        )
    field_attrs.update(relocated)
    component.forward_binding("disabled", field_attrs)

    frame_children: list[Node] = [
        Element(tag="input", attrs=field_attrs, children=())
    ]
    if clearable:
        cross = clear_button(
            css=clear_css, icon_css=icon_css,
            aria_label=clear_label, clear_js=f"{value_expr} = ''",
            show_when=value_expr, has_value_at_ssr=bool(initial),
            disabled=disabled,
        )
        component.forward_binding("disabled", cross.attrs)
        frame_children.append(cross)
    opener = trigger_button(
        icon=trigger_icon, css=trigger_css, icon_css=icon_css,
        aria_label=trigger_label, disabled=disabled,
    )
    component.forward_binding("disabled", opener.attrs)
    frame_children.append(opener)

    frame = Element(
        tag="div",
        attrs={"class": frame_css, "bz-ref": "bztrigger"},
        children=tuple(frame_children),
    )

    if disabled:
        calendar_kwargs["disabled"] = True

    return Element(
        tag=component._tag,
        attrs=root_attrs,
        children=(
            hidden_input,
            frame,
            anchored_panel(
                css=panel_css,
                children=(panel_calendar(component, calendar_kwargs),),
            ),
        ),
    )


__all__ = [
    "anchored_panel",
    "clear_button",
    "detach_wrapper_carriers",
    "hidden_carrier",
    "icon_button",
    "panel_calendar",
    "relocate_field_events",
    "render_calendar_field",
    "trigger_button",
]
