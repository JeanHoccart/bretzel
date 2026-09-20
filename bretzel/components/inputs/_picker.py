"""Shared surface of the panel pickers — Select and Combobox.

The two components are **a mirror of each other** by design: same
anchored trigger, same option panel, same pills in multi mode. Their
themes explicitly promise to "read as a family". This module is where
that promise is kept by the code rather than by discipline.

Before, two helpers (``_sized_slot``, ``_badge_pill_classes``) lived in
``combobox.py`` and ``select.py`` imported them from there — a component
depending on a sibling for want of a common home. The four others were
copied on both sides (audit F13, F52), including the whole pills
template, whose copy select's docstring conceded without the extraction
ever arriving.

What **deliberately** stays per component: ``.focus()`` / ``.blur()``
(the focusable surface differs: a ``<button>`` for Select, the search
``<input>`` for Combobox), and the chevron (Select composes it inline,
Combobox mounts it as a method).
"""

from __future__ import annotations

from typing import Any

from bretzel.components.base import (
    Component,
    coerce_children,
    stamp_display_none,
)
from bretzel.components.feedback.badge.theme import BADGE_THEME
from bretzel.components.primitives.icon import Icon
from bretzel.core.tree import Element, Node
from bretzel.core.tree import TextNode as TextNode
from bretzel.render import text


def sized_slot(
    slots: dict[str, str],
    size_map: dict[str, str],
    slot: str,
    resolve_fn: Any,
) -> str:
    """Compose ``slots[slot]`` + ``sizes[<size>][slot]`` into one string.

    The multi-slot components' idiom: the base composer silently SKIPS a
    ``sizes`` table that is a dict, so every sized slot composes here.

    ``resolve_fn`` is applied systematically: ``_resolve_template``
    short-circuits when the template has no ``{``, so slots with no
    placeholder pay nothing.
    """
    return " ".join(p for p in (
        resolve_fn(slots.get(slot, "")), size_map.get(slot, ""),
    ) if p)


def badge_pill_classes(
    resolve_fn: Any,
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

    ``resolve_fn`` is the call site's ``_resolve_template(template,
    color)`` partial so ``{bg_color}`` / ``{fg_color}`` placeholders
    get filled with the picker's chosen color.

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
        resolve_fn(slots.get("root", "")),
        resolve_fn(variant_cfg.get("root", "")),
        size_cfg.get("root", ""),
    ) if p)
    close = " ".join(p for p in (
        resolve_fn(slots.get("close", "")),
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


def option_body(
    render: Any, value: Any, label: Any
) -> tuple[Node, ...]:
    """The BODY of an option — what ``render=`` replaces.

    The wrapper stays with the component: the ``<button role="option">``,
    its ``data-value``, its ``bz-on:click``, its ``aria-selected`` and —
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
    opt["label"]`` would crash on two of them. The same default had been
    shipped then removed on ``breadcrumb`` on 2026-08-18.
    ``ui.column(render=lambda value, row)`` has the same arity for the
    same reason.

    Three limits to know, all structural:

    1. the **filter** searches the haystack, built server-side from the
       TEXT label — a badge rendered here does not change what is
       searched;
    2. the **trigger** and the **pills** read a value→label map in JS
       (``bz-text``), so they display the text, never this markup — a
       text node carries no markup;
    3. the callback touches neither the ``value``, nor the click, nor the
       selected state.
    """
    if render is None:
        return (TextNode(str(label)),)
    return coerce_children(render(value, label))


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
    *,
    slots: dict[str, str],
    size_map: dict[str, str],
    resolve: Any,
    picked_js: str,
    initially_picked: bool,
) -> Element:
    """The tick of a PICKED option, in multi mode.

    Without it, "picked" only reads from ``option_selected``'s bold +
    accent — and on an open list with EVERYTHING picked (which a column
    filter does: "nothing unticked" = "nothing filtered") the eye sees
    only a uniformly blue list, so no selection at all. Worse, a hover
    sets ``option_active``, which is also accented: hovered-not-picked
    and picked look alike.

    On the RIGHT, and not a checkbox on the left: the checkbox belongs to
    the form, where it is the control itself; here the control is the
    whole row, and the tick reports its state. It is what Linear / Notion
    / GitHub do, and it leaves the labels aligned on the same column as
    in single mode.

    MULTI mode only: in single, the trigger already shows the picked
    label, and a tick on the single accented row would say the same thing
    twice.

    ``picked_js`` is the call site's predicate (``_isPicked("x")``);
    ``initially_picked`` pre-stamps the SSR state so no tick flickers
    before the runtime boots.
    """
    attrs: dict[str, Any] = {
        "class": sized_slot(slots, size_map, "option_check", resolve),
        "bz-show": picked_js,
        "aria-hidden": "true",
    }
    if not initially_picked:
        stamp_display_none(attrs)
    return Element(
        tag="span",
        attrs=attrs,
        children=(Component.render_detached(
            Icon("check", size=size_map.get("check_icon_size", "sm")),
        ),),
    )


def build_pills_template(
    *, pill_class: str, remove_class: str,
) -> Element:
    """Reactive pills via ``<template bz-for>``. Each picked value
    renders as ``<span class="pill">label <button>×</button></span>``.

    The label goes through ``_labelOf(v)``, a scope method. This template
    inlined the WHOLE ``{value: label}`` map in its ``bz-text`` until
    2026-08-28 — a second copy for Select, a THIRD for Combobox (which
    also carried it in ``_options``). Each picker now resolves a label
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
    "build_header_bar",
    "build_pills_template",
    "has_picks",
    "normalise_option",
    "option_check",
    "render_x_icon",
    "sized_slot",
]


def build_header_bar(
    *,
    slots: dict[str, str],
    size_map: dict[str, str],
    resolve: Any,
    badge_theme: dict[str, Any],
    is_multi: bool,
    show_bulk: bool,
    total_options: int,
    initial_value: Any,
    select_all_disabled_js: str,
    lead: Element | None = None,
) -> Element:
    """The panel's sticky header — three zones in one flex row.

    - **Counter** (multi only): ``"N / total"``, the number of
      selections at a glance.
    - **Pills**: the current picks as removable badges (the ``×``
      removes without leaving the panel).
    - **Actions** (on the right, if ``show_bulk``): ``Select all`` +
      ``Clear``. Disabled rather than hidden — the layout stays stable.

    Visibility: the whole bar hides through ``bz-show`` when there is
    neither a pick nor an action. A FOUC pre-stamp keeps it hidden at SSR
    when neither condition holds.

    ``lead`` is a full-width row placed at the HEAD of the bar — the
    Combobox's search field when a custom ``trigger=`` has evicted it
    from the trigger. The bar being ``flex-wrap``, a ``w-full`` child
    takes its own line and the rest (counter, actions) sits below. A bar
    carrying the search can no longer hide: ``lead`` forces ``bz-show``
    to true and cancels the pre-stamp.

    ``lead`` also removes the pills: a filter opens with ALL its values
    ticked, so the badges would be a wall above the list they repeat —
    and the trigger, which belongs to the caller, already says what is
    picked. Derived rather than passed as a second flag: two booleans
    that must agree are one boolean that can contradict itself.

    ``select_all_disabled_js`` is the ONLY real divergence between the
    two pickers (audit F14): Select compares against the total options,
    Combobox against what the query leaves visible. All the rest — ~100
    lines — was copied, for a visual contract both themes explicitly
    promise to keep in phase ("reads as a family"). An adjustment to the
    header therefore drifted silently between Select-multi and
    Combobox-multi.
    """
    bar_class = slots.get("header_bar", "")
    counter_class = sized_slot(slots, size_map, "header_counter", resolve)
    pills_class = slots.get("header_pills", "")
    actions_class = slots.get("header_actions", "")
    # Same Badge-theme delegation as the trigger pills.
    pill_class, remove_class = badge_pill_classes(
        resolve, size=size_map.get("pill_size", "sm"),
        badge_theme=badge_theme,
    )
    btn_primary = sized_slot(slots, size_map, "header_btn_primary", resolve)
    btn_muted = sized_slot(slots, size_map, "header_btn_muted", resolve)

    # Bulk on → the bar stays visible even with no pick (the actions
    # must be discoverable). A search at the head makes it
    # unconditional: hiding it would take the field with it.
    # ONE variable, read by the runtime ``bz-show`` AND by the SSR
    # pre-stamp further down. They were two independent expressions of
    # opposite polarity: adding a zone required a term in each, with a
    # different sign, and getting the pre-stamp wrong is invisible to the
    # whole suite (no SSR test evaluates a ``bz-show``).
    always_visible = show_bulk or lead is not None
    bar_bz_show = "true" if always_visible else "_hasPicked()"

    children: list[Any] = []

    if lead is not None:
        children.append(lead)

    if is_multi:
        children.append(Element(
            tag="span",
            attrs={
                "class": counter_class,
                "bz-text": f"_picked().length + ' / {total_options}'",
            },
            children=(),
        ))

    if lead is None:
        children.append(Element(
            tag="div",
            attrs={"class": pills_class},
            children=(build_pills_template(
                pill_class=pill_class,
                remove_class=remove_class,
            ),),
        ))

    if show_bulk:
        children.append(Element(
            tag="div",
            attrs={"class": actions_class},
            children=(
                Element(
                    tag="button",
                    attrs={
                        "type": "button",
                        "class": btn_primary,
                        "bz-on:click": (
                            "$event.stopPropagation(); _selectAll()"
                        ),
                        "bz-attr:disabled": select_all_disabled_js,
                    },
                    children=(TextNode(text("picker.select_all")),),
                ),
                Element(
                    tag="button",
                    attrs={
                        "type": "button",
                        "class": btn_muted,
                        "bz-on:click": (
                            "$event.stopPropagation(); _clearAll()"
                        ),
                        "bz-attr:disabled": "!_hasPicked()",
                    },
                    children=(TextNode(text("picker.clear")),),
                ),
            ),
        ))

    header_attrs: dict[str, Any] = {
        "class": bar_class,
        "bz-show": bar_bz_show,
    }
    if not always_visible and not has_picks(initial_value, is_multi=is_multi):
        stamp_display_none(header_attrs)
    return Element(tag="div", attrs=header_attrs, children=tuple(children))
