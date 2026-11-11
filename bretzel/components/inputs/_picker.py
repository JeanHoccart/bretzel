"""Shared surface of the panel pickers — Select and Combobox.

The two components are **a mirror of each other** by design: same
anchored trigger, same option panel, same pills in multi mode. Their
themes explicitly promise to "read as a family". This module is where
that promise is kept by the code rather than by discipline.

Both components take their shared helpers from here, including the
whole pills template, so that neither depends on its sibling.

What **deliberately** stays per component: ``.focus()`` / ``.blur()``
(the focusable surface differs: a ``<button>`` for Select, the search
``<input>`` for Combobox), and the chevron (Select composes it inline,
Combobox mounts it as a method).
"""

from __future__ import annotations

from typing import Any

from bretzel.components.base import (
    Component,
    call_render,
    coerce_children,
    stamp_display_none,
)
from bretzel.components.feedback.badge.theme import BADGE_THEME
from bretzel.components.primitives.icon import Icon
from bretzel.core.tree import Element, Node
from bretzel.core.tree import TextNode as TextNode
from bretzel.render import text


def badge_pill_classes(
    *,
    size: str,
    badge_theme: dict[str, Any] | None = None,
    variant: str = "soft",
) -> tuple[str, str]:
    """Compose the ``(pill_class, close_class)`` strings from
    :data:`BADGE_THEME` for use inside a pill-rendering ``bz-for``
    template. Single source of truth for pill styling : Combobox /
    Select multi-pickers both delegate here so a Badge theme tweak
    propagates everywhere automatically.

    ``badge_theme`` MUST be the call site's RESOLVED Badge theme
    (``self._resolved_theme("badge", BADGE_THEME)``): reading the
    ``BADGE_THEME`` constant here would bypass an app's
    ``Theme(components={"badge": …})``, and the pills would not follow
    the override — while the docstring above promises exactly the
    opposite. The ``None`` default only serves tests outside a render
    context.

    ``size`` is REQUIRED — and deliberately without a default. It had
    one (``"sm"``), and all four call sites had let it slip: the pills
    stayed ``sm`` on an ``xl`` picker. A default here is invisible at the
    call site; the absence of a default forces a decision. Pass the token
    from ``sizes[<size>]["pill_size"]``.
    """
    theme = badge_theme if badge_theme is not None else BADGE_THEME
    slots = theme["slots"]
    variants = theme["variants"]
    sizes = theme["sizes"]
    variant_cfg = variants.get(variant, variants["soft"])
    size_cfg = sizes.get(size, sizes["sm"])
    pill = " ".join(p for p in (
        slots.get("root", ""),
        variant_cfg.get("root", ""),
        size_cfg.get("root", ""),
    ) if p)
    close = " ".join(p for p in (
        slots.get("close", ""),
        size_cfg.get("close", ""),
    ) if p)
    return pill, close


def normalise_option(opt: Any) -> tuple[Any, Any, bool]:
    """Return ``(value, label, disabled)`` for any of the accepted
    option shapes : str / tuple / dict.

    The options' shape contract MUST be identical between the two
    pickers — an ``options=`` that works on one and not on the other
    would be incomprehensible.
    """
    if isinstance(opt, dict):
        return (
            opt.get("value", opt.get("label", "")),
            opt.get("label", opt.get("value", "")),
            bool(opt.get("disabled", False)),
        )
    if isinstance(opt, tuple) and len(opt) >= 2:
        return opt[0], opt[1], False
    # Plain scalar (string / int) — value == label.
    return opt, opt, False


def option_classes(component: Component, *, is_multi: bool) -> str:
    """An option row's static classes : the sized ``option`` slot, plus
    ``option_current`` in single mode.

    The current value's tint is single-mode only — a multi list marks
    its picks with a tick or a box, and tinted through it would read as
    one block (``option_check`` is the inverse decision).
    """
    base = component.compose_class("option")
    if is_multi:
        return base
    return " ".join(p for p in (base, component.compose_class("option_current")) if p)


def option_body(
    render: Any, value: Any, label: Any
) -> tuple[Node, ...]:
    """The BODY of an option — what ``render=`` replaces.

    The wrapper stays with the component: the ``<button role="option">``,
    its ``data-bz-value``, its ``bz-on:click``, its ``aria-selected`` and —
    most importantly — its ``bz-show="_matches(<haystack>)"``. The
    callback only fills the inside.

    Why a callback here and children elsewhere
    -------------------------------------------

    ``COLLECTION_OWNER = "component"``: it is the picker that iterates
    ``options=``, the author does not write that loop — so they have
    nowhere to put their markup without this callback. Cf.
    ``Component.COLLECTION_OWNER`` and
    ``tests/consistency/test_collection_owner_decides_the_api.py``.

    ⚠️ Signature ``(value, label)``, both **already normalised**, and not
    the raw option. It is deliberate: ``options=`` accepts three shapes
    (str, tuple, dict), so a callback written ``lambda opt:
    opt["label"]`` would crash on two of them.
    ``ui.column(render=lambda value, row)`` has the same arity for the
    same reason.

    Three limits to know, all structural:

    1. the **filter** searches the haystack, built server-side from the
       TEXT label — a badge rendered here does not change what is
       searched;
    2. a ``Select``'s closed field DOES show it — every body rendered a
       second time there, the picked one shown (``picked_bodies``). What
       stays text: a ``Combobox``'s field (an
       ``<input>`` carries no markup, and it is where one types) and the
       removable pills of both (a body inside a badge would be a badge in
       a badge);
    3. the callback touches neither the ``value``, nor the click, nor the
       selected state.
    """
    if render is None:
        return (TextNode(str(label)),)
    return coerce_children(call_render(render, value, label))


def has_picks(initial_value: Any, *, is_multi: bool) -> bool:
    """SSR snapshot: does the picker have a selection at the first paint?

    Drives the FOUC pre-stamp ``stamp_display_none`` — on the clear
    button (Combobox), on the pills / clear / placeholder branches of the
    multi trigger (Select) — so they paint in the right state before the
    runtime boots.
    """
    if is_multi:
        if isinstance(initial_value, (list, tuple, set)):
            return len(initial_value) > 0
        return bool(initial_value)
    return initial_value not in (None, "")


def render_x_icon(icon_size: str) -> Element:
    """The clear button's ``×`` glyph, at the picker's size."""
    return Component.render_detached(Icon("x", size=icon_size))


def option_check(
    component: Component,
    *,
    picked_js: str,
    initially_picked: bool,
) -> Element:
    """The tick of a PICKED option, in multi mode.

    Without it, "picked" only reads from ``option_selected``'s bold +
    accent text — colour only, and on an open list with everything
    picked the eye sees a uniformly accented list, so no selection at
    all.

    On the RIGHT, and not a checkbox on the left: in a picker the control
    is the whole row, and the tick reports its state. It is what Linear /
    Notion / GitHub do, and it leaves the labels aligned on the same
    column as in single mode. The FILTER shape (a Combobox with a custom
    ``trigger=``) is the exception, and draws a checkbox instead: there
    the panel IS a tick-list, opened to tick several values, and it reads
    as one.

    MULTI mode only: in single, the trigger already shows the picked
    label, and a tick on the single accented row would say the same thing
    twice.

    ``picked_js`` is the call site's predicate (``_isPicked("x")``);
    ``initially_picked`` pre-stamps the SSR state so no tick flickers
    before the runtime boots.
    """
    attrs: dict[str, Any] = {
        "class": component.compose_class("option_check"),
        "bz-show": picked_js,
        "aria-hidden": "true",
    }
    if not initially_picked:
        stamp_display_none(attrs)
    return Element(
        tag="span",
        attrs=attrs,
        children=(Component.render_detached(
            Icon("check", size=(component._size_row() or {}).get("check_icon_size", "sm")),
        ),),
    )


def build_pills_template(
    *, pill_class: str, remove_class: str,
) -> Element:
    """Reactive pills via ``<template bz-for>``. Each picked value
    renders as ``<span class="pill">label <button>×</button></span>``.

    The label goes through ``_labelOf(v)``, a scope method, so this
    template does not inline the ``{value: label}`` map in its
    ``bz-text``. Each picker resolves a label
    its own way: Select reads its map, Combobox sweeps ``_options``,
    which already carries it.

    ``bz-for`` lives on a ``<template>`` with a SINGLE root child ;
    the key rides inside the attribute (``v in _picked() :key=v``)
    per the directive grammar.
    """
    return Element(
        tag="template",
        attrs={"bz-for": "v in _picked() :key=v"},
        children=(
            Element(
                tag="span",
                attrs={"class": pill_class},
                children=(
                    Element(
                        tag="span",
                        attrs={
                            "bz-text": "_labelOf(v) || v",
                        },
                        children=(),
                    ),
                    Element(
                        tag="button",
                        attrs={
                            "type": "button",
                            "class": remove_class,
                            "tabindex": "-1",
                            "aria-label": text("picker.remove"),
                            "bz-on:click": (
                                "$event.stopPropagation(); _removeOne(v)"
                            ),
                        },
                        children=(
                            Element(
                                tag="span",
                                attrs={
                                    "class": (
                                        "inline-block w-3 h-3 "
                                        "leading-none text-center"
                                    ),
                                },
                                children=(TextNode("×"),),
                            ),
                        ),
                    ),
                ),
            ),
        ),
    )


__all__ = [
    "badge_pill_classes",
    "build_footer_bar",
    "build_header_bar",
    "build_pills_template",
    "has_picks",
    "normalise_option",
    "option_check",
    "option_classes",
    "render_x_icon",
]


def build_header_bar(
    component: Component,
    *,
    badge_theme: dict[str, Any],
    initial_value: Any,
    is_multi: bool,
    lead: Element | None = None,
) -> Element:
    """The panel's sticky header: the picks, or the relocated search.

    - **Pills**: the current picks as removable badges (the ``×``
      removes without leaving the panel). Shown only while something is
      picked — through ``bz-show``, with a FOUC pre-stamp so an empty
      picker paints no strip at SSR.
    - ``lead``: a full-width row that REPLACES the pills — the
      Combobox's search field when a custom ``trigger=`` has evicted it
      from the trigger. A filter's trigger, which belongs to the caller,
      already says what is picked, so the badges would only repeat it.
      A header carrying the search never hides: hiding it would take the
      field with it.

    The commands (counter, Select all, Clear) are NOT here: they live in
    :func:`build_footer_bar`, under the list. Above it they sat between
    the search field and the options — the two things the reader goes
    back and forth between.
    """
    bar_class = component.compose_class("header_bar")
    if lead is not None:
        return Element(tag="div", attrs={"class": bar_class}, children=(lead,))

    # Same Badge-theme delegation as the trigger pills.
    pill_class, remove_class = badge_pill_classes(
        size=(component._size_row() or {}).get("pill_size", "sm"),
        badge_theme=badge_theme,
    )
    header_attrs: dict[str, Any] = {
        "class": bar_class,
        "bz-show": "_hasPicked()",
    }
    if not has_picks(initial_value, is_multi=is_multi):
        stamp_display_none(header_attrs)
    return Element(
        tag="div",
        attrs=header_attrs,
        children=(Element(
            tag="div",
            attrs={"class": component.compose_class("header_pills")},
            children=(build_pills_template(
                pill_class=pill_class,
                remove_class=remove_class,
            ),),
        ),),
    )


def build_footer_bar(
    component: Component,
    *,
    total_options: int,
    initial_value: list[str],
    usable_values: list[str],
    select_all: bool,
    select_all_done_js: str,
) -> Element:
    """The panel's sticky footer — the counter, then the commands.

    - **Counter**: ``"N / total"``, the selection at a glance.
    - **Select all** (if ``select_all``): shown while something usable
      is left to pick.
    - **Clear**: shown while something is picked.

    Each command HIDES when it would do nothing rather than greying out:
    the counter holds the left edge and the commands sit at the right
    one, so nothing in the list moves when they come and go.

    With Select all (``bulk_actions=True``) the strip stays up even with
    no pick — Select all must be found before the first click. Without
    it (a filter's panel, which offers Clear only) the strip appears
    with the first pick.

    ``select_all_done_js`` is the ONLY real divergence between the two
    pickers: Select compares against every usable option, Combobox
    against what the query leaves visible. ``usable_values`` gives the
    same answer at SSR, for the pre-stamp.
    """
    picked = set(initial_value)
    any_picked = has_picks(initial_value, is_multi=True)
    all_picked = bool(usable_values) and all(v in picked for v in usable_values)
    children: list[Any] = [Element(
        tag="span",
        attrs={
            "class": component.compose_class("footer_counter"),
            "bz-text": f"_picked().length + ' / {total_options}'",
        },
        children=(TextNode(f"{len(picked)} / {total_options}"),),
    )]

    commands: list[Any] = []
    if select_all:
        select_attrs: dict[str, Any] = {
            "type": "button",
            "class": component.compose_class("footer_btn_primary"),
            "bz-on:click": "$event.stopPropagation(); _selectAll()",
            "bz-show": f"!({select_all_done_js})",
        }
        if all_picked:
            stamp_display_none(select_attrs)
        commands.append(Element(
            tag="button", attrs=select_attrs,
            children=(TextNode(text("picker.select_all")),),
        ))
    clear_attrs: dict[str, Any] = {
        "type": "button",
        "class": component.compose_class("footer_btn_muted"),
        "bz-on:click": "$event.stopPropagation(); _clearAll()",
        "bz-show": "_hasPicked()",
    }
    if not any_picked:
        stamp_display_none(clear_attrs)
    commands.append(Element(
        tag="button", attrs=clear_attrs,
        children=(TextNode(text("picker.clear")),),
    ))
    children.append(Element(
        tag="div",
        attrs={"class": component.compose_class("footer_actions")},
        children=tuple(commands),
    ))

    footer_attrs: dict[str, Any] = {"class": component.compose_class("footer_bar")}
    if not select_all:
        footer_attrs["bz-show"] = "_hasPicked()"
        if not any_picked:
            stamp_display_none(footer_attrs)
    return Element(tag="div", attrs=footer_attrs, children=tuple(children))
