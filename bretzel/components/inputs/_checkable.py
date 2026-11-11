"""The shared render of the two checkable controls — ``Checkbox`` and ``Switch``.

What is shared
--------------
What really sets them apart is **visual, and only that**: the box has a
frame plus a tick SVG, the switch has a rail plus a thumb. All the rest
— the real ``<input type=checkbox>`` carrying the framework's
attributes, the two-way ``bz-model``, the local scope that makes a
toggle survive a morph, the forcing of the boolean into the form data,
the imperative API's listeners, the root ``<label>`` — is the same word
for word.

⚠️ The unsubmitted-boolean trap (an unticked box sends NOTHING, so the
``false`` never reaches the server and the refresh re-ticks it) is
handled once, here.

What stays with the caller
---------------------------
The visual nodes, built with its own composed classes: each component
keeps its own, they are harmonised, not factored. This module never
reads a theme: it receives nodes and places them under the ``<label>``.
"""

from __future__ import annotations

from typing import Any

from bretzel.components.base.arguments import has_content
from bretzel.components.inputs._wiring import (
    add_local_value_scope,
    checked_command_listeners,
    false_companion_input,
    force_boolean_form_vals,
)
from bretzel.core.tree import Element, Node


def render_checkable(
    component: Any,
    *,
    visuals: tuple[Node, ...],
) -> Element:
    """``<label>``: the real ``<input>``, the fake visuals, then the label.

    ``visuals`` are the decorative nodes that follow the input in the
    container — box + tick for a checkbox, rail + thumb for a switch.
    They are purely decorative: it is the hidden ``<input>`` that carries
    the interaction, the focus and the accessibility.
    """
    # The real input — hidden but interactive. It carries ALL the
    # framework's attributes (id / bz-id / events / bz-model); the fake
    # visuals are decorative descendants under the same ``<label>``.
    input_attrs: dict[str, Any] = {
        "type": "checkbox",
        "class": component.compose_class("input"),
    }
    input_attrs.update(component.emit_attrs())

    # ``bz-model`` writes both ways; on the way it removes the read-only
    # ``bz-attr:checked`` ``emit_attrs`` had set for a binding. A literal
    # ``checked=True``, for its part, has already arrived as a static
    # HTML attribute through ``emit_attrs``.
    component._bind_x_model(input_attrs, prop="checked")

    # Local + interactive: a ``checked`` scope signal on the ``<input>``
    # so a user's toggle survives the morph of an enclosing
    # ``@refreshable`` — without it, idiomorph puts the native
    # ``.checked`` back to the SSR value. No effect in binding mode, nor
    # with no handler.
    add_local_value_scope(
        component, input_attrs, prop="checked",
        ssr_value=bool(component._reactive_values.get("checked")),
    )

    # Server-bound toggle: an UNTICKED box submits nothing, so the
    # ``false`` would never reach the server and the refresh would
    # re-tick it. Skipped for a ClientBinding (the bridge already ships
    # the store) and for an explicit ``value=`` (value-list semantics,
    # where "unticked = absent" is the right HTML). Cf. traps.md.
    #
    # TWO mechanisms, because there are TWO possible requests, and
    # neither covers the other:
    #
    # - ``hx-vals`` covers the request the BOX pulls itself (its
    #   ``on_change``): htmx evaluates it at send time and overrides the
    #   native value. It only exists if there is an ``hx-post`` on the
    #   input;
    # - the hidden companion covers the parent FORM's submission, where
    #   the event does not come from the box and where
    #   ``event.target.checked`` means nothing. It carries the same
    #   ``name`` and the value ``"false"``, and it is placed BEFORE the
    #   box: both leave when it is ticked, and the server keeps the last
    #   (``FormData`` like ``parse_qsl``: the last one wins).
    #
    # Without them, a ``ui.switch`` with no ``on_change``, unticked on
    # screen, comes back ticked after the form is saved — a boolean
    # setting stuck on ``True``.
    server_bound_boolean = (
        component._binding_metadata.get("checked") is None
        and component._reactive_values.get("value") is None
        and bool(input_attrs.get("name"))
    )
    if server_bound_boolean:
        force_boolean_form_vals(input_attrs, name=input_attrs.get("name"))

    # The imperative API's listeners — they catch the DOM commands
    # ``.toggle()`` / ``.set(bool)`` dispatch on this input by its id.
    # The listener flips ``$el.checked`` then pulls a synthetic
    # ``change``, so that ``bz-model`` (binding case) syncs AND the
    # user's ``on_change=`` runs. In binding mode, the imperative methods
    # write straight through the binding and these events never fire — we
    # keep the uniform shape for the case with no binding. Cf.
    # `imperative-api.md` / ``inputs/_wiring.py``.
    input_attrs.update(checked_command_listeners())

    # The hidden companion — the other half of the same mechanism, hence
    # its place in ``inputs/_wiring.py`` right beside
    # ``force_boolean_form_vals``.
    companion: tuple[Node, ...] = (
        (false_companion_input(
            input_attrs["name"],
            # The same fate as the box: a disabled control submits
            # nothing, and a companion left active would be the only one
            # to leave.
            disabled=bool(input_attrs.get("disabled")),
        ),)
        if server_bound_boolean else ()
    )

    # Beside a label, the container is at least ONE LINE of it high: the
    # box centres on the first line, and a label that wraps runs on below
    # it instead of pulling the box down to its middle. One line or a
    # bigger visual (a switch's rail), nothing moves. The LABEL's size
    # on the container, on purpose: ``1lh`` is a line of the label.
    size_map = component._size_row() or {}
    # ``has_content``, not ``if label:``: a bound label (a ClientBinding)
    # refuses a truth test, and counts as present.
    has_label = has_content(component._label)
    line = f" min-h-[1lh] {size_map.get('label', '')}" if has_label else ""
    container = Element(
        tag="div",
        attrs={
            "class": component.compose_class("container") + line
        },
        children=(
            *companion,
            Element(tag="input", attrs=input_attrs, children=()),
            *visuals,
        ),
    )

    children: list[Node] = [container]
    if has_label:
        label_class = component.compose_class("label")
        children.append(
            Element(
                tag="span",
                attrs={"class": label_class},
                children=(component.emit_text_slot(component._label),),
            )
        )

    # No scope on the root — the ``bz-on:`` set on the input resolve
    # against the runtime's root scope.
    return Element(
        tag=component._tag,
        attrs={"class": component.compose_class("root")},
        children=tuple(children),
    )


__all__ = ["render_checkable"]
