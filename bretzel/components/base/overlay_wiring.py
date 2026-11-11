"""What opens and floats: panels, their anchoring, focus, dismissal, open/close commands."""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from typing import Any

from bretzel.components.base.composition import _append_class
from bretzel.components.base.scope_wiring import bool_attr
from bretzel.components.base.theme_values import color_bridge_class
from bretzel.core.escape import escape_js
from bretzel.core.tree import Element, Node

_SHRINK_TOKENS = ("inline-block", "inline-flex", "inline-grid", "inline-table")


#: Inline tags BY NATURE: they size themselves to their content without
#: any class declaring it. A <span> root with no display token hugs, an
#: identical <div> fills — the class alone cannot tell them apart.
_INLINE_TAGS = frozenset({"span", "a", "label", "em", "strong", "code",
                          "abbr", "small", "b", "i", "button"})


_SHRINK_WIDTH_RE = re.compile(r"(?:^|\s)(?:w-fit|w-max|w-min|w-auto|w-\d|w-\[)")


#: ⚠️ A WORD, not a substring. ``"w-full" in cls`` is true for
#: ``max-w-full`` — which declares the opposite: a CEILING, not a width.
#: With a substring, ``max-w-full`` on a root would make its tooltip
#: wrapper stretch across the whole line, so the panel would anchor on the
#: row and not on the component. The trap holds for ``sm:w-full``,
#: ``group-hover:w-full``, any prefix at all — and it only shows in the
#: browser.
FILL_WIDTH_RE = re.compile(r"(?:^|\s)w-full(?:\s|$)")


def _class_decides_width(root_cls: str) -> bool | None:
    """Does the CLASS settle it, and which way?

    ``True`` = hugs, ``False`` = fills, ``None`` = the class says nothing
    and it is up to the tag to answer.

    Order matters, and it is the defect the gate found the same day: an
    explicit declaration must beat the tag heuristic. A ``dropdown_item``
    is a ``<button class="… w-full">`` — inline by tag, filling by
    declaration — and a ``skeleton`` is a ``<span class="block">``.
    Asking the tag first classified both the wrong way round.
    """
    if FILL_WIDTH_RE.search(root_cls):
        return False
    if any(token in root_cls for token in _SHRINK_TOKENS):
        return True
    if _SHRINK_WIDTH_RE.search(root_cls):
        return True
    if re.search(r"(?:^|\s)block(?:\s|$)", root_cls):
        return False
    return None


def trigger_is_full_width(triggers: Iterable[Any]) -> bool:
    """True if any trigger fills its row.

    An anchored overlay (Tooltip / Popover / Dropdown) wraps its trigger in
    a ``w-fit`` root. When the trigger fills its parent, that root must
    expand (see :func:`expand_fit_wrapper`) or the trigger collapses to
    content width — a tooltip'd full-width button comes out narrower than
    its plain siblings, and a tooltip'd ``vstack`` collapses onto its
    longest child.

    The question is asked of the trigger's built-in THEME root, of a
    user-passed ``classes=``, and of a rendered :class:`Element`'s class
    (the universal-modifier path).

    ⚠️ « Does it say ``w-full`` » is the wrong question: a block ``div``
    with no declared width fills its parent **without saying so**.
    Answering on that signal would make a tooltip shrink ``grid``,
    ``vstack``, ``hstack``, ``flex``, ``form``, ``radio_group`` or ``tabs``
    to their content's width.
    """
    from bretzel.components.base.component import Component  # deferred : cycle

    for trigger in triggers:
        if trigger is None:
            continue
        if isinstance(trigger, Component):
            theme = getattr(trigger, "THEME", {}) or {}
            root_cls = theme.get("slots", {}).get("root", "") or ""
            # The caller's classes can shrink a root that filled, and
            # the other way round — so we judge the two together.
            verdict = _class_decides_width(f"{root_cls} {trigger._user_classes_str()}")
            if verdict is None:
                # ⚠️ The class says nothing: it is the TAG that decides.
                # ``ui.text`` renders a ``<span>`` with no display token —
                # it hugs because it is inline BY NATURE. Without this
                # fallback, a tooltip on a word would anchor on the whole
                # line.
                verdict = getattr(trigger, "_tag", "div") in _INLINE_TAGS
            if not verdict:
                return True
        elif isinstance(trigger, Element):
            # Same rule, and it MUST be repeated here: this is the
            # branch the universal ``tooltip=`` modifier goes through,
            # which receives the already-rendered node and not the
            # component. Judging only the class classified ``ui.text`` (a
            # ``<span>``) as filling, and its tooltip anchored on the
            # whole line.
            cls = trigger.attrs.get("class", "")
            verdict = _class_decides_width(cls if isinstance(cls, str) else "")
            if verdict is None:
                verdict = trigger.tag in _INLINE_TAGS
            if not verdict:
                return True
    return False


def expand_fit_wrapper(root_cls: str) -> str:
    """Collapse an anchored overlay's ``inline-* w-fit h-fit`` default to a
    one-cell ``grid grid-cols-1 w-full``. Strip the fit tokens too :
    Tailwind's ``w-full w-fit`` ordering is non-deterministic, so leaving
    ``w-fit`` in can still win and the full-width trigger collapses.

    ⚠️ A GRID, not a ``block``. The wrapper stretches with its cell, but a
    block does not hand its height down: a ``ui.card(tooltip=…)`` in a grid
    row would keep its own height while its plain neighbours take the
    row's (``tests/runtime_js/test_a_tooltip_keeps_its_trigger_box.py``). A
    one-cell grid stretches its child both ways; ``grid-cols-1`` is
    ``minmax(0, 1fr)``, so the child may still shrink below its content
    width, as it does in a block."""
    return (
        root_cls
        .replace("inline-block", "grid grid-cols-1 w-full")
        .replace("inline-flex", "grid grid-cols-1 w-full")
        .replace("w-fit", "")
        .replace("h-fit", "")
    )


def show_attrs(open_expr: str, initial_open: bool) -> dict[str, Any]:
    """``data-open`` state for CSS-driven enter/leave animations.

    The overlay element stays MOUNTED (no ``display`` toggle — ``display``
    can't be transitioned, which is why the old ``bz-show`` made the modal
    overlays pop in/out brutally). The theme animates opacity / scale /
    translate / **visibility** off ``data-[open=true|false]`` instead.

    Stringified ternary so the runtime always writes ``"true"``/``"false"``
    (a bare boolean ``false`` makes ``bz-attr`` DROP the attribute, which
    would break the CSS selector).

    ``data-bz-overlay`` is the marker the shell's anti-flash rule reads.
    The ``html:not(.bz-ready) [bz-data] {visibility:hidden}`` guard is NOT
    enough here: ``visibility`` is overridable by a descendant, and
    during its transition the backdrop explicitly computes ``visible``,
    so it wins against its ancestor's ``hidden``.

    What it avoids. The Tailwind CSS arrives AFTER the first paint (dev:
    compiled in the browser; prod: after a partial-nav morph, while the
    inserted subtree gets styled). At that instant the backdrop goes from
    an unstyled state (``static``, ``opacity:1``, ``visible``) to ``fixed
    inset-0 bg-black/50 backdrop-blur-sm`` + ``opacity:0``. The styling
    applies all at once, but ``opacity`` and ``visibility`` are inside a
    ``transition ... 200ms``: they ANIMATE from their unstyled value.
    Result: a full-screen blurred veil fading out over 200 ms on every
    page carrying a dialog / drawer. The marker lets the shell declare
    the closed state BEFORE the first paint: the values no longer move
    when the sheet arrives, so no transition starts.
    """
    return {
        "data-open": "true" if initial_open else "false",
        "bz-attr:data-open": bool_attr(open_expr),
        "data-bz-overlay": "",
    }


def focus_trap_effect(open_expr: str) -> str:
    """Panel ``bz-effect`` : trap focus while open, restore on close."""
    return (
        f"((v) => {{ "
        f"if (v && !$el._bzTrap) {{ "
        f"$el._bzTrap = $bz.helpers.focusTrap($el); }} "
        f"else if (!v && $el._bzTrap) {{ "
        f"$el._bzTrap(); $el._bzTrap = null; }} "
        f"}})(!!({open_expr}))"
    )


def _dispatch_arm(open_expr: str) -> str:
    """The open/close ``$dispatch`` arm, shared by every overlay root.

    Bootstraps quietly so the initial state never fires a phantom
    event ; subsequent transitions emit ``open`` / ``close`` on the
    root, where the ``hx-trigger="open"`` / ``"close"`` listeners
    installed from ``on_open=`` / ``on_close=`` catch them.
    """
    return (
        "if ($el._bzLastOpen === undefined) { $el._bzLastOpen = v; } "
        "else if (v !== $el._bzLastOpen) { "
        "$el._bzLastOpen = v; "
        "$dispatch(v ? 'open' : 'close'); }"
    )


def modal_root_effect(open_expr: str) -> str:
    """Root ``bz-effect`` (modal overlays) : scroll lock + dispatch."""
    return (
        f"((v) => {{ "
        f"if (v && !$el._bzLock) {{ "
        f"$el._bzLock = $bz.helpers.scrollLock(); }} "
        f"else if (!v && $el._bzLock) {{ "
        f"$el._bzLock(); $el._bzLock = null; }} "
        f"{_dispatch_arm(open_expr)} "
        f"}})(!!({open_expr}))"
    )


def dispatch_root_effect(open_expr: str) -> str:
    """Root ``bz-effect`` (anchored overlays) : open/close dispatch only.

    No scroll lock — a popover / dropdown doesn't trap the page.
    """
    return (
        f"((v) => {{ {_dispatch_arm(open_expr)} }})(!!({open_expr}))"
    )


#: The flag :func:`changed_since_open_effect` sets on the root, and that
#: the HTMX event filter reads back. Written in ONE place: the writer and
#: the reader are in two languages and two files, so a copied literal
#: would drift in silence — the handler would NEVER fire again, which
#: looks exactly like the intended behaviour.
CHANGED_FLAG = "_bzChanged"


def changed_since_open_effect(open_expr: str, picked_js: str) -> str:
    """``bz-effect``: has the value moved since it was opened?

    A panel you open then close without touching anything must send
    NOTHING. It is the normal gesture — you click a filter to see what it
    offers, you close it again — and it cost a round trip plus a zone
    re-render every time.

    The flag lives on the element (not in the scope) because it is the
    HTMX event filter that reads it back, and that one evaluates with
    ``this`` = the element, outside any signal scope.

    ⚠️ The snapshot is taken at the TRANSITION, not on every tick: this
    effect depends on the value, so it re-runs on every tick. Re-taking
    it then would make it always equal to the current one — the panel
    would never be dirty, and the handler would never fire again. The
    ``_bzOpenWas`` guard is what tells "we have just opened" from "we are
    open and it is moving".

    The values are SORTED before comparison: unticking then reticking the
    same value puts it back at the end of the array, and a different
    order is not a change of selection.
    """
    return (
        f"((v) => {{ "
        f"if ($el._bzOpenWas === v) return; "
        f"$el._bzOpenWas = v; "
        f"const s = JSON.stringify([...({picked_js})].map(String).sort()); "
        f"if (v) {{ $el._bzOpenSnap = s; }} "
        f"else {{ $el.{CHANGED_FLAG} = s !== $el._bzOpenSnap; }} "
        f"}})(!!({open_expr}))"
    )


#: The events :func:`_dispatch_arm` fires ON THE ROOT. A server handler
#: wired to one of them must keep its HTMX bundle THERE, and
#: :func:`relocate_handlers` refuses to move it — onto a value carrier or
#: a focusable child, it would point the listener at an
#: element that never sees the event, and the handler dies silently (no
#: error, no POST : the ``EVENTS`` + ``on_X=`` dead-letter shape of
#: ``traps.md``).
#:
#: Declared here, next to the effect that dispatches them, rather than as
#: each component's private list of what DOES relocate : that inverted
#: form is a whitelist you have to remember to extend, and forgetting is
#: the silent failure it was meant to prevent.
ROOT_DISPATCHED_EVENTS = frozenset({"open", "close"})


#: The values of an anchored panel's ``position=``: a side, or ``auto`` for
#: the roomiest one. ``align=`` is the second half of the placement
#: ``$bz.helpers.floating`` reads.
FLOATING_POSITIONS: tuple[str, ...] = ("auto", "top", "bottom", "left", "right")


FLOATING_ALIGNS: tuple[str, ...] = ("start", "center", "end")


def floating_placement(position: str, align: str) -> str:
    """Theme ``position`` + ``align`` → a ``$bz.helpers.floating`` placement.

    The floating helper takes ``"<side>"`` or ``"<side>-<align>"`` ;
    ``center`` is its default so we drop it to keep the string tidy.

    Lives here, next to :func:`anchored_panel_effect` which consumes its
    output.
    """
    return position if align in ("center", "") else f"{position}-{align}"


def anchored_panel_effect(
    open_expr: str,
    placement: str,
    *,
    trigger_ref: str = "bztrigger",
    match_width: bool = False,
) -> str:
    """Panel ``bz-effect`` for anchored overlays.

    Toggles the panel's ``display`` AND attaches / detaches
    ``$bz.helpers.floating`` against the trigger. Display is set
    BEFORE floating measures (so ``offsetWidth`` is correct in the
    same synchronous run — no flash, no zero-size measure).

    Anchor resolution adapts to the trigger shape. Popover / Dropdown /
    Tooltip wrap their trigger in a ``display:contents`` span (no box of
    its own) so we anchor on its ``firstElementChild`` — the real
    trigger box. Select / Combobox put ``bz-ref="bztrigger"`` directly
    on the trigger ``<button>`` / ``<div>`` (a real box), so we anchor
    on the ref itself ; using ``firstElementChild`` there would anchor
    on an inner label span / pills row and mis-align the panel. The
    ``display:contents`` probe picks the right one at runtime without a
    per-component flag. Falls back to the panel's previous sibling if
    the ref is missing.

    ``match_width=True`` pins the panel's width to the trigger's — min
    AND max, so a long option wraps inside the trigger's box instead of
    growing the panel toward the viewport edge (native ``<select>``
    look). Used by Select / Combobox, and by nobody else: Dropdown,
    Popover, Tooltip and the pickers leave their panel at its natural
    width.

    ⚠️ **The pinch has a floor**, set in ``floating()``
    (``MIN_MATCHED_WIDTH``, 192 px): without it, a trigger narrower than
    that — a ``ui.select`` in a sidebar collapsed to ``rail`` — would give
    the panel its own width and wrap the labels letter by letter. Above
    the floor the pinch applies as described.

    The floating instance is re-attached (detach + fresh attach, which
    re-resolves the anchor and re-pins the panel) in TWO cases while the
    panel stays open :

    - **placement CHANGED** : a server refresh rewrote ``position`` /
      ``align`` on an open popover, re-running this effect with a new
      placement literal. Without re-attaching, the already-attached
      instance (pinned to the old placement) would never update — the
      panel would stay put (cf. the popover server playground).
    - **inline position WIPED** (``$el.style.position !== 'fixed'``) : a
      morph of the panel's own @refreshable zone re-stamps the SSR
      ``style`` attribute (``display:none``), clobbering the inline
      ``position:fixed; top; left`` that ``floating`` had set. The
      ``_bzFloat`` guard alone would see the instance still "attached"
      and skip re-positioning, so the panel falls back to its themed
      ``position:absolute`` with no offsets and paints ON TOP of the
      trigger. Re-attaching restores the fixed coordinates. (This is the
      "popover covers the button after an on_open refresh" bug —
      reproduced in ``experiments/v3/runtime/probe_overlay_refresh.py``.)
    """
    opts = (
        "{placement: __p, matchWidth: true}"
        if match_width
        else "{placement: __p}"
    )
    return (
        f"((v) => {{ "
        f"$el.style.display = v ? '' : 'none'; "
        # ``escape_js``: ``position`` / ``align`` are props, and a prop
        # is a value — one with a quote would leave this literal.
        f"const __p = '{escape_js(placement)}'; "
        f"if (v) {{ "
        # Re-attach when the placement changed (server rewrote
        # position/align) OR the inline position was wiped by a morph
        # (re-stamped SSR style) — either way we detach so the block
        # below re-attaches, re-resolving the anchor and re-pinning.
        f"if ($el._bzFloat && "
        f"($el._bzFloatP !== __p || $el.style.position !== 'fixed')) {{ "
        f"$el._bzFloat(); $el._bzFloat = null; }} "
        f"if (!$el._bzFloat) {{ "
        f"const __t = $refs.{trigger_ref}; "
        f"const __a = __t "
        f"? (getComputedStyle(__t).display === 'contents' "
        f"? (__t.firstElementChild || __t) : __t) "
        f": $el.previousElementSibling; "
        f"$el._bzFloat = $bz.helpers.floating(__a, $el, {opts}); "
        f"$el._bzFloatP = __p; }} "
        # OPENING (not a re-attach while open): the field marked
        # ``autofocus=`` inside takes the focus — none, it stays on the
        # trigger (``$bz.helpers.autofocusOpen``).
        f"if (!$el._bzShown) {{ $el._bzShown = true; "
        f"$bz.helpers.autofocusOpen($el); }} "
        f"}} else {{ $el._bzShown = false; if ($el._bzFloat) {{ "
        f"$el._bzFloat(); $el._bzFloat = null; }} }} "
        f"}})(!!({open_expr}))"
    )


def anchored_trigger_wrapper(
    node: Any,
    *,
    open_expr: str,
    haspopup: str,
    on_click: str | None = None,
) -> Element:
    """Wrap a caller-supplied trigger for an anchored overlay.

    The ``display:contents`` box is not cosmetic and not optional :
    :func:`anchored_panel_effect` probes ``getComputedStyle(ref).display
    === 'contents'`` to decide whether to anchor on the ref or on its
    ``firstElementChild``. A wrapper that loses ``class="contents"`` or
    ``bz-ref="bztrigger"`` makes the panel anchor on a zero-size box —
    off-screen, silently.

    Popover, Dropdown and Combobox each wrote this by hand, differing
    only in ``aria-haspopup`` (``dialog`` / ``menu`` / ``listbox``) and,
    for Combobox, in the click body (it also hands the keyboard to the
    search field). Three copies of a contract no test covers is the
    repo's own threshold for extracting a primitive.

    ``on_click`` defaults to the plain toggle ; pass one when the trigger
    has to do more than flip the flag.
    """
    return Element(
        tag="div",
        attrs={
            "class": "contents",
            "bz-ref": "bztrigger",
            "bz-on:click": on_click or f"{open_expr} = !{open_expr}",
            "aria-haspopup": haspopup,
            "bz-attr:aria-expanded": bool_attr(f"{open_expr}"),
        },
        children=(node,),
    )


def anchored_panel(
    *,
    css: str,
    children: tuple[Node, ...],
    open_expr: str = "open",
    placement: str = "bottom-start",
    role: str | None = None,
    match_width: bool = False,
    extra_effect: str = "",
    attrs: Mapping[str, Any] | None = None,
    closed: bool = True,
) -> Element:
    """A panel anchored to its trigger by ``$bz.helpers.floating``.

    ``bz-ref="bzpanel"`` is not decorative: the root's ``clickOutside``
    resolves it on EVERY click to know what counts as "inside". Without it,
    a click on the panel's padding (or on a disabled cell, which dispatches
    nothing) would close the panel. Guarded by
    ``test_dismiss_scope_owns_its_panel``.

    ``closed`` pre-stamps ``display:none``: without it the panel appears for
    a frame before the first effect runs. ``attrs`` is what a panel adds of
    its own (the handlers on its options, the event that closes it).
    """
    from bretzel.components.base.nodes import (
        stamp_display_none,  # ``component`` imports this module
    )

    effect = anchored_panel_effect(open_expr, placement, match_width=match_width)
    if extra_effect:
        effect = f"{effect}; {extra_effect}"
    panel_attrs: dict[str, Any] = {"class": css}
    if role:
        panel_attrs["role"] = role
    panel_attrs["bz-ref"] = "bzpanel"
    panel_attrs["bz-effect"] = effect
    panel_attrs.update(attrs or {})
    if closed:
        stamp_display_none(panel_attrs)
    return Element(tag="div", attrs=panel_attrs, children=children)


def anchored_dismiss_init(open_expr: str) -> str:
    """Root ``bz-init`` for anchored overlays : Escape + click-outside.

    Both registered once at mount. ``clickOutside`` targets the ROOT
    (which contains the trigger) AND is handed ``() => $refs.bzpanel`` as
    the "also inside" element : every anchored overlay teleports its panel
    to ``<body>`` (out of the root's subtree), so without this a click
    ANYWHERE in the panel counts as outside and dismisses. That's mostly
    masked for menus (an enabled item dispatches its own close first, so
    the deferred dismiss is a no-op) — but a click that dispatches NOTHING
    (a disabled row, the panel's own padding, rich Popover content) would
    close the overlay. The guard resolves the ref on EACH click (the
    teleported panel registers its ref after this handler is wired, so it
    can't be captured up front) and every overlay names its panel
    ``bz-ref="bzpanel"``.

    The click-outside dismiss is DEFERRED (``setTimeout 0``) with a
    double guard so an EXTERNAL control handling the SAME click wins the
    race. ``clickOutside`` fires in the CAPTURE phase — BEFORE a sibling
    button's bubble-phase ``bz-on:click`` runs the command it carries
    (``.toggle()`` / ``.open()`` from ``_dispatch_command``). A
    synchronous ``open = false`` here would land first, then the
    command's ``open = !open`` would read ``false`` and RE-OPEN — the
    overlay could never be closed by an outside toggle (the ".toggle()
    only opens" bug). So : snapshot ``open`` at click time (``__w``) and
    only dismiss if it was open THEN **and** is still open after the
    click's handlers ran. A toggle that CLOSED it leaves ``open=false``
    → skip ; a toggle that OPENED it had ``__w=false`` → skip ; a genuine
    outside click leaves ``open`` unchanged (true) → dismiss.

    Why ``setTimeout`` and NOT ``queueMicrotask`` : for a TRUSTED click
    the browser runs a microtask checkpoint BETWEEN each event listener
    (the JS stack empties between the capture and bubble listeners of a
    user click), so a microtask scheduled in the capture phase runs
    BEFORE the bubble-phase toggle — the exact race we're trying to
    escape (it fired ``open=false`` first, then the toggle re-opened).
    A macrotask (``setTimeout``) is the earliest defer that is
    GUARANTEED to run only after the WHOLE click event finished both
    phases. A naive defer WITHOUT ``__w`` also breaks the open direction
    (open→callback sees true→re-closes).
    """
    return (
        f"$bz.helpers.escapeKey(() => {{ "
        f"if ($el.isConnected && ({open_expr})) {{ {open_expr} = false; return true; }} }}, $el); "
        f"$bz.helpers.clickOutside($el, () => {{ "
        f"const __w = ({open_expr}); "
        f"setTimeout(() => {{ "
        f"if ($el.isConnected && __w && ({open_expr})) {{ {open_expr} = false; }} "
        f"}}, 0); }}, () => $refs.bzpanel)"
    )


def imperative_listeners(open_expr: str) -> dict[str, str]:
    """``bz-on:bz-open/close/toggle`` — the imperative-API receivers.

    Harmless when ``open=`` is bound (the binding's own setter writes
    the path directly, the event never fires) ; uniform for both cases
    keeps the contract simple.

    The command bubbles (``_dispatch_command``), so the first overlay
    that receives it STOPS it: an overlay nested in another was the
    command's addressee, not its parent. Without it ``popover.close()``
    on a popover inside a drawer would close the drawer too
    (``test_a_panel_in_a_drawer_closes_alone``).
    """
    return {
        "bz-on:bz-open": f"$event.stopPropagation(); {open_expr} = true",
        "bz-on:bz-close": f"$event.stopPropagation(); {open_expr} = false",
        "bz-on:bz-toggle": f"$event.stopPropagation(); {open_expr} = !{open_expr}",
    }


def install_open_close_toggle(component: Any, prop: str = "open") -> None:
    """Install the write-only imperative API ``.open()`` / ``.close()`` /
    ``.toggle()`` as INSTANCE ATTRIBUTES on ``component``.

    Byte-identical on every open-driven overlay (Dialog / Drawer / Dropdown /
    Popover): each method writes through the ``prop`` binding if it was
    passed at construction, otherwise dispatches a DOM command the root
    (via :func:`imperative_listeners`) catches. The assignment is
    per-instance ON PURPOSE — it SHADOWS the ``open`` ``reactive_prop``
    descriptor (a non-data descriptor, no ``__set__``): ``dialog.open``
    returns the callable, the descriptor stays in the class dict for the
    ``__reactive_props__`` collection + the kwarg routing. Must run in
    ``__init__`` AFTER ``super().__init__`` (it needs a populated
    ``_binding_metadata``). Removes the 3 ``def _imperative_*`` + 3
    assignments copied into every overlay. Cf. imperative-api.md; guarded
    by ``test_imperative_classvar`` (the names are callable on the
    instance).
    """
    # ``_commanded``: "somebody asked for a command on me". That is what
    # tells a component you can drive from a component nothing reaches —
    # the question :func:`check_sidebars_are_reachable` asks. Set here
    # rather than at the caller because both tiers of the API go through
    # it: the tier-1 component (``ui.sidebar_trigger``) as much as the
    # tier-2 escape hatch (``on_click=sb.toggle()``).
    def _open() -> str:
        component._commanded = True
        binding = component._binding_metadata.get(prop)
        if binding is not None:
            return binding.set(True)
        return component._dispatch_command("bz-open")

    def _close() -> str:
        component._commanded = True
        binding = component._binding_metadata.get(prop)
        if binding is not None:
            return binding.set(False)
        return component._dispatch_command("bz-close")

    def _toggle() -> str:
        component._commanded = True
        binding = component._binding_metadata.get(prop)
        if binding is not None:
            return binding.toggle()
        return component._dispatch_command("bz-toggle")

    component.open = _open
    component.close = _close
    component.toggle = _toggle


def teleport_to_body(panel: Node, owner: Any = None) -> Node:
    """Wrap an overlay ``panel`` in a ``<template bz-teleport="body">`` so the
    runtime projects it under ``<body>`` at init.

    **Real scope: the ANCHORED overlays only** — Tooltip, Popover,
    Dropdown, and `SidebarFooter`'s popover. They are ``position: fixed``
    and float against their trigger, so any ancestor with ``overflow`` (a
    scrollable container, a ``Card``'s ``overflow-hidden``) or with a
    stacking context / ``transform`` would clip them or mis-stack them.

    ⚠️ **Dialog and Drawer do NOT go through here.** It is an abstention:
    their full-screen backdrop makes them less sensitive to clipping. The
    risk stays **latent** — an app layout that sets a ``transform`` above
    a Dialog makes it the containing block.

    Teleporting to ``<body>`` frees the panel from those traps ; the runtime
    keeps the projected clone bound to THIS component's ORIGIN scope
    (``node._bzScopeHost = template`` — bare signal names and ``$refs`` still
    resolve here, and morphs re-project on content change). Cf.
    ``runtime/_src/directives.js::bindTeleport`` + traps.md.

    ``bz-teleport`` is a STRUCTURAL directive on a ``<template>`` : the runtime
    moves the template's *content* (the panel) to the target, not the template
    element itself. So the panel becomes the template's single child.

    ``owner`` — THE COLOUR BRIDGE TRAVELS WITH THE PANEL
    -----------------------------------------------------

    The steps (``--bz-bg``, ``--bz-text``…) are inherited properties, set
    by the bridge class on the component's root. A panel teleported under
    ``<body>`` **is no longer a descendant of that root**: it loses the
    eleven steps at once, and renders with no colour — with no error and
    no trace, since an undefined custom property simply makes the
    declaration invalid.

    Passing ``owner`` copies the bridge onto the panel itself. It is done
    HERE, at the assembly point, and not in each component: the Tooltip
    is the only one concerned today (the Dropdown, the Popover and the
    Sidebar footer write no colour in their panel), but the next coloured
    overlay would have no reason to think of it.
    """
    if owner is not None:
        bridge = color_bridge_class(owner, panel)
        if bridge is not None:
            panel = _append_class(panel, bridge)
    return Element(
        tag="template",
        attrs={"bz-teleport": "body"},
        children=(panel,),
    )


def escape_init(open_expr: str) -> str:
    """``bz-init`` : Escape closes the overlay while it is open — the
    deepest open one only (``escapeKey`` is handed ``$el``, and the
    handler says it closed), so that Escape on a popover inside a drawer
    does not close both."""
    return (
        f"$bz.helpers.escapeKey(() => {{ "
        f"if ($el.isConnected && ({open_expr})) "
        f"{{ {open_expr} = false; return true; }} }}, $el)"
    )
