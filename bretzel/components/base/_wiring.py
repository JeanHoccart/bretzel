"""The shared base-layer wiring — two jobs, not one.

⚠️ This module long announced itself as "Shared V3 client wiring for
**overlay** components", and that stopped being true on 2026-08-23: it
took on +518 lines that do not speak of overlays at all. A reader
looking for "where does the placement check of a sticky bar live" had no
reason to open a file that presents itself as the popovers' glue.

**1. The client wiring of anchored and modal surfaces** — the original
job, described in detail below.

**2. PLACEMENT questions, settled once the tree is complete.** They
CANNOT be answered at construction: a ``sticky`` bar does not know a
``ui.viewport`` is coming, nor what its real layout parent is. The
pipeline calls them from a single point, once the page is built (cf.
``render/pipeline.py``):

- :func:`register_sticky_bar` / :func:`check_sticky_bar_placement` — is a
  ``sticky`` bar inside a frozen frame, where it means something?
- :func:`wire_sidebar_triggers` / :func:`check_sidebars_are_reachable` —
  which bar does this trigger speak to, and does that bar have a way
  back?
- :func:`unwrap_transparent` — a container that sorts its children must
  see through a ``@refreshable`` zone, which is transparent to layout
  without being an instance of what it carries.
- :func:`drop_tag_bound_attrs` — what a changed tag can no longer carry.

The two jobs live together here because they share the same reason to be
at the ``base/`` level: being importable by every group without creating
a cycle. If they diverge further, it is the second that leaves.

---

Two families share the anchored/modal wiring so it can't drift :

**Modal overlays** (Dialog, Drawer) :
- :func:`show_attrs` — ``data-open`` + ``bz-attr:data-open`` +
  ``data-bz-overlay``. The element stays **MOUNTED** (no ``bz-show``, no
  ``display:none`` prestamp: it is the shell's
  ``[data-bz-overlay][data-open="false"]`` selector that does the
  anti-flash, and a CSS transition needs the node to exist). This line
  announced the old mechanism until 2026-08-01, contradicting the
  docstring of the function itself 90 lines below.
- :func:`focus_trap_effect` — panel ``bz-effect`` engaging
  ``$bz.helpers.focusTrap`` while open (dispose on close).
- :func:`modal_root_effect` — root ``bz-effect`` : scroll lock via
  ``$bz.helpers.scrollLock`` + ``open``/``close`` event dispatch.
- :func:`escape_init` — ``bz-init`` Escape-to-close.

**Anchored overlays** (Popover, Dropdown, Tooltip) :
- :func:`anchored_panel_effect` — panel ``bz-effect`` : display toggle
  + attach / detach ``$bz.helpers.floating`` against the trigger.
- :func:`dispatch_root_effect` — root ``bz-effect`` : open/close
  dispatch only (no scroll lock — an anchored panel doesn't trap the
  page).
- :func:`anchored_dismiss_init` — ``bz-init`` : Escape + click-outside
  via ``$bz.helpers``.

**Both** :
- :func:`imperative_listeners` — ``bz-on:bz-open/close/toggle``
  catching the DOM commands fired by ``.open()``/``.close()``/
  ``.toggle()`` from external triggers.

Base-level shared primitive (June 2026 — promoted from ``overlay/`` per
its own guidance). The same anchored/modal wiring is needed by overlays
(Dialog/Drawer/Dropdown/Popover/Tooltip), inputs (Select/Combobox/the
date pickers/Calendar) AND navigation (SidebarFooter) — i.e. across
groups — so it belongs in ``base/``, importable by anyone, instead of
forcing every consumer to reach into the ``overlay/`` group
(anti-rule 5).
"""

from __future__ import annotations

import re
import sys
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

from bretzel.components.base.attrs import ComponentUsageError
from bretzel.core.tree import Element, Node
from bretzel.runtime import (
    BZ_ATTR_PREFIX,
    BZ_ON_PREFIX,
    DATA_BZ_SIG,
    DATA_BZ_TS,
    SERVERSYNC_KEY,
)
from bretzel.runtime.protocol import outlet_id_for

# Tokens that declare an INTRINSIC width — the box sizes itself to its
# content. Everything else, in normal flow, fills its parent. Same
# vocabulary as ``test_inline_root_hugs_content``, which classifies roots
# on exactly that axis.
#: The HTML attributes whose MEANING is bound to a specific tag, with the
#: list of tags where they have one. Closed and short on purpose: only
#: what changes meaning (or no longer has one) elsewhere goes in, not
#: everything that is "unusual".
#: The flag a component sets to say "I am not here".
#: Two carry it: the section of a ``@refreshable`` zone and
#: ``ui.fragment``. Cf. :func:`unwrap_transparent`.
TRANSPARENT_WRAPPER_FLAG = "IS_TRANSPARENT_WRAPPER"


#: The flag a "frozen document" frame sets to say "the screen is me".
#: Only one carries it:
#: :class:`~bretzel.components.layout.viewport.Viewport`.
FROZEN_FRAME_FLAG = "IS_FROZEN_FRAME"

#: The flex directions that make a full-width bar a COLUMN of the frame
#: instead of a row at the bottom.
_ROW_DIRECTIONS = frozenset({"row", "row-reverse"})


def register_sticky_bar(component: Any, call: str) -> None:
    """Register a ``sticky`` bar for the placement pass.

    Called by ``ui.bottom_bar`` (always stuck) and by
    ``ui.navbar(sticky=True)``. An ordinary navbar scrolls with the
    document: it has nothing to do with the frozen model, and does not
    register.

    The call site is captured HERE, while the stack still carries it —
    the pass itself runs in the pipeline and could no longer say which
    line wrote the bar. That is what lets the message name
    ``file:line`` instead of leaving the reader to search.
    """
    from bretzel.render.context import maybe_current_context

    ctx = maybe_current_context()
    if ctx is None:
        return
    ctx.sticky_bars.append((component, call, _user_call_site()))


def _user_call_site() -> str:
    """``file:line`` of the first frame OUTSIDE the framework, or ``""``.

    We walk up until we leave ``bretzel/``: between the caller and here
    there are the component's ``__init__`` and the base layer's, and
    sometimes a factory. Counting frames would be right only up to the
    first component that adds one.
    """
    frame = sys._getframe(1) if hasattr(sys, "_getframe") else None
    root = str(Path(__file__).parents[2])
    while frame is not None:
        name = frame.f_code.co_filename
        if not name.startswith(root):
            return f"{Path(name).name}:{frame.f_lineno}"
        frame = frame.f_back
    return ""


def check_sticky_bar_placement(roots: Iterable[Any], bars: Iterable[Any]) -> None:
    """Judge the placement of ``sticky`` bars once the tree is built.

    Does **nothing** as long as no frozen frame (``ui.viewport``) is in
    the tree: the default model — the document that scrolls, ten of the
    repository's eighteen apps — is not concerned.

    The two refused placements were measured in Chromium (375×667,
    ``tests/probes/probe_bottom_bar_placement.py``); both render a page
    that looks built:

    - **outside the frame** — a ``ui.viewport`` is ``fixed inset-0``, so
      it leaves the flow. A bar left outside no longer has a document to
      stick to: measured **y = 0**, and the frame covers it.
    - **in a ROW** — the bar is full width, so it takes the whole row:
      measured, the neighbouring ``ui.pane`` drops to **0 px wide** and
      its content disappears, with no error and no trace. It is the more
      treacherous of the two, because the bar itself lands in the right
      place.

    Why here and not at the bar's construction
    -------------------------------------------
    Because it is a question of TREE. A bar written BEFORE the
    ``ui.viewport`` cannot know a frame is coming — and for a navbar,
    "the top bar first" is the natural order. And the LAYOUT parent is
    not the construction parent: a ``ui.fragment`` or a ``@refreshable``
    zone is transparent to CSS and opaque to ``parent_stack``, so the bar
    was judged on its wrapper. Both cases were **measured broken**, and
    both passed a guard placed at construction (2026-08-24).
    """
    bars = list(bars)
    if not bars:
        return
    frames: list[Any] = []
    paths: dict[int, list[Any]] = {}
    _index_tree(roots, [], frames, paths, {id(bar) for bar, _, _ in bars})
    if not frames:
        return

    for bar, call, site in bars:
        path = paths.get(id(bar))
        if path is None:
            # The bar is not in the rendered tree: adopted by a slot, or
            # built in an inspection ``serialize_html``. Nothing to judge
            # — we do not know where it will land.
            continue
        where = f" ({site})" if site else ""
        if not any(getattr(type(a), FROZEN_FRAME_FLAG, False) for a in path):
            raise ComponentUsageError(
                f"{call}{where} is placed OUTSIDE the page's "
                f"`ui.viewport`. A `ui.viewport` is `fixed inset-0`: it "
                f"leaves the document flow, so a bar left outside renders "
                f"at y=0 and the frame covers it (measured in Chromium). "
                f"Write it INSIDE the frame — last child of the scrolling "
                f"`ui.pane`, or direct child of a "
                f'`ui.viewport(direction="col")`.'
            )
        parent = _layout_parent(path)
        if _is_a_row(parent):
            raise ComponentUsageError(
                f"{call}{where} is in a ROW "
                f"(`{_call_name(parent)}`). The bar is full width: it "
                f"takes the whole row and crushes its neighbours — "
                f"measured, the `ui.pane` next to it drops to 0 px wide "
                f"and its content disappears with no error. Put it in the "
                f"column: inside the `ui.pane`, or in a "
                f'`ui.viewport(direction="col")`.'
            )


#: The collapse modes that can make the bar DISAPPEAR — no icon strip,
#: no residual width. A bar in either of these two modes carries off
#: screen EVERY affordance it renders (the title chevron, the collapse
#: edge), so its way back can only be outside.
_VANISHING_MODES = frozenset({"overlay", "offcanvas"})


#: The fallback for a trigger that found no bar in ITS render — the case
#: of a zone refresh, where the shell is not replayed. We then aim at the
#: stable marker set by ``Sidebar.render``, resolved at CLICK time and
#: not at construction. The ``?.`` avoids raising if the page really has
#: none.
TOGGLE_NEAREST_SIDEBAR = (
    "document.querySelector('[data-bz-sidebar]')?.dispatchEvent("
    "new CustomEvent('bz-toggle', {bubbles: true}))"
)


def wire_sidebar_triggers(triggers: Iterable[Any], sidebars: list[Any]) -> None:
    """Give each ``ui.sidebar_trigger`` the bar it drives.

    Resolved here, on the built tree, and not at the trigger's
    construction: a shell that writes its top bar BEFORE its ``<aside>``
    is perfectly normal, and the order of writing must not decide whether
    the button works. It is the lesson of the ``sticky`` bars, applied to
    the next component that asks a question about the tree.

    One bar in the page: the trigger finds it by itself — that is tier 1,
    and it is the case of every shell in the repository. Several bars: we
    refuse to guess, because a wrong choice would make a button that
    looks like it works and opens the wrong thing.
    """
    for trigger in triggers:
        if trigger._sidebar is not None:      # ``sidebar=`` explicite
            continue
        if len(sidebars) == 1:
            trigger.bind_sidebar(sidebars[0])
        elif len(sidebars) > 1:
            raise ComponentUsageError(
                f"ui.sidebar_trigger() cannot guess which bar it drives: "
                f"this page mounts {len(sidebars)}. Pass it as an argument "
                f"— keep the bar in a variable (`sb = ui.sidebar(...)`) "
                f"then write `ui.sidebar_trigger(sb)`."
            )
        # Zero bars in THIS render (a zone refresh that does not replay
        # the shell): the trigger keeps its selector fallback, which
        # resolves at click time. It works, it just does not announce an
        # ``aria-controls``.


def check_sidebars_are_reachable(sidebars: Iterable[Any]) -> None:
    """A bar that can disappear must have a way back.

    Measured on 2026-08-24, fresh bench at 375x667: a
    ``ui.sidebar(collapsible="overlay", open=False)`` with no trigger
    renders an ``<aside>`` at **x = -256** and **zero clickable element
    on screen**. The page answers 200, nothing is logged, and the
    navigation is simply unreachable — that is what had made six of
    ``examples/crm``'s eleven routes unreachable on a phone.

    It is not an oversight of the component, it is the flip side of a
    good decision: the auto-rendered floating chevron was removed on
    2026-08-21 because "it was the component deciding where an app
    affordance goes". What was missing afterwards was a piece to PLACE —
    hence ``ui.sidebar_trigger``, and hence this check.

    Three ways of being reachable, and the guard keeps quiet if one
    holds:

    - a ``ui.sidebar_trigger`` aims at it (tier 1);
    - a command was issued against it — ``on_click=sb.toggle()`` on any
      button (tier 2, the escape hatch);
    - its ``open=`` is driven by a :class:`ClientBinding`: the state then
      belongs to the app, which can raise it from wherever it wants, and
      the framework has no way of knowing. We do not judge.
    """
    for sidebar in sidebars:
        mode = getattr(sidebar, "_reactive_values", {}).get("collapsible")
        if mode not in _VANISHING_MODES:
            continue
        if getattr(sidebar, "_commanded", False):
            continue
        if sidebar._binding_metadata.get("open") is not None:
            continue
        raise ComponentUsageError(
            f'ui.sidebar(collapsible="{mode}") has no way of being '
            f"reopened. In this mode the bar leaves the screen, and it "
            f"takes with it its title chevron and its collapse edge — "
            f"measured: aside at x=-256, zero clickable element on "
            f"screen, page at 200. Place a `ui.sidebar_trigger()` where "
            f"you want the button (in your top bar, typically), or call "
            f"`sb.toggle()` from your own. If it is your app that holds "
            f"the state, pass `open=` a ClientState: the guard keeps "
            f"quiet."
        )


def _index_tree(
    children: Iterable[Any],
    path: list[Any],
    frames: list[Any],
    paths: dict[int, list[Any]],
    wanted: set[int],
) -> None:
    """Walk the tree noting the frames and the path of the bars.

    A single walk for both questions, and we keep the path only of the
    registered bars: a page makes thousands of nodes, and keeping one
    path per node would cost more than the pass.
    """
    for child in children:
        if getattr(type(child), FROZEN_FRAME_FLAG, False):
            frames.append(child)
        if id(child) in wanted:
            paths[id(child)] = list(path)
        kids = getattr(child, "_children", None)
        if kids:
            path.append(child)
            _index_tree(kids, path, frames, paths, wanted)
            path.pop()


def _layout_parent(path: list[Any]) -> Any:
    """The first ancestor that counts for CSS, wrappers skipped.

    A ``ui.fragment`` and the section of a ``@refreshable`` zone are
    transparent to LAYOUT (``display:contents``, or fusion into their
    only child — cf. ``render/fusion.py``). The real flex parent is
    therefore above them, and it is that one that decides whether the bar
    is in a row.
    """
    for ancestor in reversed(path):
        if not getattr(type(ancestor), TRANSPARENT_WRAPPER_FLAG, False):
            return ancestor
    return None


def _is_a_row(component: Any) -> bool:
    """The component's ``direction``, breakpoint steps included.

    ``direction`` is a RESPONSIVE prop (``Flex.RESPONSIVE_PROPS``):
    ``{"base": "col", "md": "row"}`` is a legal call, and reading it as a
    scalar would let through a frame that IS a row from ``md`` upwards.
    A single step in row is enough to crush the neighbour.
    """
    values = getattr(component, "_reactive_values", None)
    if not values:
        return False
    direction = values.get("direction")
    if isinstance(direction, dict):
        return any(step in _ROW_DIRECTIONS for step in direction.values())
    return direction in _ROW_DIRECTIONS


def _call_name(component: Any) -> str:
    key = getattr(type(component), "THEME_KEY", None)
    return f"ui.{key}" if key else type(component).__name__



# ── Le pont de couleur ──────────────────────────────────────────────────


#: What a theme writes when it reads a STEP rather than a template.
_READS_A_STEP = "(--bz-"


def refuse_a_value_off_the_table(component: Any) -> None:
    """``size=`` / ``variant=`` outside the table: raise, instead of
    keeping quiet.

    **Silence was the catalogue's behaviour, and it cost.** Measured on
    2026-09-06: of the 57 (component, axis) pairs carrying ``size`` or
    ``variant``, **56 rendered anyway** on an invented value, and not in
    the same way —

        ui.button(size="zzz")  → loses h-10, px-4, gap-2, text-sm
                                  (the button renders WITH NO SIZE)
        ui.badge(size="zzz")   → falls back on `sm`, one size lower

    A typo did not raise, did not show, and could not be seen in review.

    Yet the repository already applies this rule and writes it:
    ``bretzel describe`` says of ``ui.flex``'s ``grow=`` that the "table
    is CLOSED, and a value outside it RAISES: it would render the empty
    string, so a dead kwarg". It is the same sentence, applied to the
    catalogue's two most frequent props.

    Two abstentions, each deliberate: we only raise if the legal values
    are KNOWABLE (cf. below), and a non-``str`` value — a step dict, a
    binding — leaves here without a sound: it is not this function that
    settles that case.

    **``reactive_prop(steps=)`` comes before the table**, and that is
    what closed the last four silent ones on 2026-09-07. The theme's
    table cannot answer for everyone: ``bar_chart.variant`` and
    ``pie_chart.variant`` name a plotting mode (no table),
    ``radio_group.size`` forwards to the children (empty table), and
    ``radio.size`` does have a table but a ``None`` default — and it is
    the default that serves as the anchor for reading a nested table. All
    four therefore rendered anything at all in silence, and the gate's
    old list of abstentions described that limit of the DETECTOR as if it
    were a property of the components.
    """
    theme = component._resolved_theme()
    descriptors = type(component).__reactive_props__
    for prop, table_key in (("size", "sizes"), ("variant", "variants")):
        value = component._reactive_values.get(prop)
        descriptor = descriptors.get(prop)
        declared = getattr(descriptor, "steps", None)
        if declared:
            steps = frozenset(declared)
        else:
            anchor = getattr(descriptor, "default", None)
            steps = declared_steps(theme.get(table_key, {}), anchor=anchor)
        if not steps or not isinstance(value, str) or value in steps:
            continue
        raise ComponentUsageError(
            f"ui.{_ui_name_for_error(component)}: {prop}={value!r} is not "
            f"in the theme's table. Known values: "
            f"{', '.join(sorted(steps))}.\n"
            f"  A value outside the table would not raise by itself: it "
            f"would render the empty string, so a dead kwarg — the "
            f"component would lose that step without a word. For styling "
            f"that no step covers, that is `classes=`."
        )


def declared_steps(
    table: Mapping[str, Any], *, anchor: str | None
) -> frozenset[str]:
    """The steps of a ``sizes`` / ``variants`` table, THREE shapes.

    The catalogue nests the table **both ways round**, and nothing in its
    structure says which — measured on 2026-09-06: 17 flat tables, 37
    nested, and the nested ones share the two orders ::

        sizes = {"sm": "h-8", "md": "h-10"}                    # flat
        sizes = {"input_frame": {"md": "h-10"}}                # date_picker
        sizes = {"md": {"root": "h-10", "close": "size-4"}}    # badge

    Hence the anchor: the component's DEFAULT step, read on its
    descriptor. It is valid by construction, so the level that contains
    it is the level of the steps. No hard-coded vocabulary — otherwise a
    component that invented a step would make the list lie.

    Guessing the order costs: the first draft read the flat table
    everywhere, and the suite went from green to **198 red** because I
    had only measured the refusal on the illicit side (cf. rule 8: prove
    the bite both ways).

    With no readable anchor — no declared default, or a default that
    neither level carries — we return the empty set, and the refusal
    abstains: better to say nothing than to refuse a correct value.
    """
    if not table:
        return frozenset()
    outer = frozenset(table)
    inner = frozenset(
        step
        for slot in table.values()
        if isinstance(slot, Mapping)
        for step in slot
    )
    if not inner or anchor in outer:
        return outer
    return inner if anchor in inner else frozenset()


def _ui_name_for_error(component: Any) -> str:
    """The component's ``ui.*`` name, or its class failing that."""
    key = getattr(type(component), "THEME_KEY", "") or ""
    return key or type(component).__name__


def theme_context(
component: Any, *, size_default: str = "md", color_default: str = "primary"
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], str, str]:
    """``(theme, slots, sizes, size, color)`` — render()'s preamble.

A FUNCTION and not a base-layer method: `component.py` is the crossing
point of 96 components, and `test_the_choke_point_only_shrinks` refuses
that it grow without a decision. Its place is here, beside the other
shared render primitives.

    **Twenty-six components opened their ``render()`` on the same four
    or five lines**, and they split 13 against 11 on the ORDER of two of
    them (``size`` before ``color``, or the other way round). That split
    is the proof it was copy-paste: nobody knowingly writes the same
    block in two orders. And it is what made the duplication invisible —
    two blocks that differ only in order look alike to no tool.

    The repository had already treated this pathology once, but by
    FAMILY (``overlay/_modal``, ``inputs/_picker_field``…). This preamble
    is universal, so no family covered it.

    The defaults are parameterised because they genuinely differ:
    ``ui.icon`` starts on ``color="current"``, a few components on
    another base size. Passing them explicitly keeps the behaviour
    identical to the byte.
    """
    theme = component._resolved_theme()
    return (
        theme,
        theme.get("slots", {}),
        theme.get("sizes", {}),
        component._reactive_values.get("size") or size_default,
        component._reactive_values.get("color") or color_default,
    )


def color_bridge_class(component: Any, node: Node) -> str | None:
    """The bridge class to set on the root, or ``None``.

    A coloured component carries ``bz-c-<colour>``, which installs the
    eleven steps on its subtree (cf. :mod:`bretzel.theme.bridges`). That
    is what replaces the ``{bg_color}`` substitution: the theme writes
    ``bg-(--bz-bg)``, a COMPLETE class the compiler sees, and the bridge
    says which colour it is.

    Three refusals, each for a reason:

    1. **A bridge class already set by the user.** Two ``bz-c-*`` on the
       same element are settled by the order of the SHEET and not by the
       order of the classes, so the ``classes="bz-c-error"`` escape hatch
       would win or lose at random. We leave it the floor.
    2. **A colour that is not a string** — a step dict, a binding.
       Without this refusal the base layer stringifies and sets
       ``bz-c-{'md': 'primary'}`` in the DOM (measured on 2026-08-30).
    3. **No colour at all** — the component is not coloured.

    ⚠️ Case 2 **raises** when the theme reads a step. Not setting the
    bridge would render the component WITH NO STYLE — undefined steps, so
    invalid properties — with no error and no trace. The step dict on
    ``color`` already broke at render before the migration (cf.
    ``tests/consistency/_not_graded.txt``): raising keeps the noise where
    it was, instead of trading it for silence.
    """
    if not isinstance(node, Element):
        return None
    color = component._reactive_values.get("color")
    if color is None:
        return None

    from bretzel.theme.bridges import BRIDGE_CLASS_PREFIX, bridge_class

    root_class = str(node.attrs.get("class", ""))
    user_written = component._user_classes_str() + " " + component._raw_class_str
    if BRIDGE_CLASS_PREFIX in root_class + " " + user_written:
        return None

    if isinstance(color, str):
        _refuse_unknown_color(component, color)

    if not isinstance(color, str):
        if _READS_A_STEP in root_class:
            raise ComponentUsageError(
                f"{type(component).__name__}(color={color!r}): the colour "
                "must be a name, not a "
                f"{type(color).__name__}.\n"
                "  This component paints itself with STEPS "
                "(``bg-(--bz-bg)``…), which are set by its colour's bridge "
                "class. With no colour name there is no bridge, so no "
                "steps, so a component rendered WITH NO STYLE.\n"
                "  ``color=`` does not take breakpoint steps: one colour "
                "per breakpoint makes no sense here."
            )
        return None
    return bridge_class(color)

def unwrap_transparent(child: Any) -> tuple[Any, Any]:
    """``(the real child, what gives it back its wrapper)``.

    The problem it solves, measured on 2026-08-23
    -----------------------------------------------
    Several containers treat their children **by type**: ``ui.tabs``
    looks for ``Tab``, ``ui.stepper`` for ``Step``, ``ui.accordion`` for
    ``AccordionItem``, ``ui.sidebar`` for its title and its footer. Yet a
    child is very often WRAPPED — in a ``@refreshable`` zone (to refresh
    itself) or in a ``ui.fragment``. The wrapper is not an instance of
    what it contains, so the sorting misses it.

    The wrapper is already transparent to LAYOUT (the zone fuses into its
    only child, or renders as ``display:contents`` — cf.
    ``render/fusion.py``). It was not transparent to IDENTITY, and that
    cost, in silence:

    ==================  ==========================================
    ``ui.tabs``         the wrapped tab **disappears** from the bar
    ``ui.stepper``      the step **disappears**
    ``ui.accordion``    the item loses its **header** and its label
    ``ui.sidebar``      the footer fell **into the scrolling zone**
    ``ui.toggle_group`` **raises** — the only loud one
    ==================  ==========================================

    Why it ALSO returns a rewrapping function
    -------------------------------------------
    One cannot simply throw the wrapper away: a zone's wrapper carries
    its ``bz-id``, the target HTMX aims at to refresh it. A parent that
    rendered the child bare would produce a correct tab… that would never
    refresh again. So the parent composes the child as before, then gives
    its identity back to the produced node ::

        real, rewrap = unwrap_transparent(child)
        node = real._render_in_tabs(...)   # the parent composes
        node = rewrap(node)                # the zone dresses again

    On a bare child, ``rewrap`` is the identity — the caller has no
    branch to write.

    ⚠️ **A wrapper with several children is NOT traversed.** It is
    rendered as-is, as before. A parent that sorts cannot cut a node in
    two, and guessing which of the three children is "the real one" would
    be deciding in the caller's place. A zone that contains a tab AND
    something else must be split by whoever writes it.
    """
    if not getattr(type(child), TRANSPARENT_WRAPPER_FLAG, False):
        return child, _identity
    kids = list(getattr(child, "_children", ()) or ())
    if len(kids) != 1:
        return child, _identity
    return kids[0], getattr(child, "_rewrap", _identity)


def _identity(node: Any) -> Any:
    return node


TAG_BOUND_ATTRS: dict[str, frozenset[str]] = {
    # On an ``<a>``, ``type`` is a MIME-type hint about the target — not
    # the nature of a button.
    "type": frozenset({"button", "input", "ol", "link", "script", "style"}),
    "href": frozenset({"a", "link", "area", "base"}),
    "src": frozenset({
        "img", "script", "iframe", "video", "audio", "source",
        "embed", "track", "input",
    }),
    "alt": frozenset({"img", "area", "input"}),
    "for": frozenset({"label", "output"}),
    "target": frozenset({"a", "area", "form", "base"}),
}


def drop_tag_bound_attrs(
    tag: str, attrs: dict[str, Any], *, spare: Iterable[str] = ()
) -> None:
    """Remove from ``attrs`` what no longer means anything under ``tag``.

    A component declares its props against its ``DEFAULT_TAG``, and
    several have a non-``None`` default that therefore always comes out:
    ``Button.type`` is ``"button"``, ``Image.alt`` is mandatory. When the
    tag changes — through the universal ``tag=`` kwarg, or because a prop
    implies it (``ui.button(href=…)`` and ``ui.card(href=…)`` render an
    ``<a>``) — those attributes stayed. Measured on 2026-08-23: **four**
    components rendered an attribute bound to another tag, three of them
    a ``type="button"`` on something that no longer was one.

    Called at the end of ``Component.emit_attrs`` — the only place where
    the tag and the attribute bag meet for the whole catalogue. Here and
    not there because the choke point is under ratchet: what is a shared
    primitive lives in this file.

    ``spare`` lists what the caller wrote THEMSELVES —
    ``attrs={"type": "text/html"}`` on an ``<a>`` is a real MIME type,
    and the raw escape hatch has the last word everywhere else (cf.
    ``merge_attr``'s precedence contract). We only remove what the
    component produced on its own.

    ⚠️ Two components set their attribute **after** ``emit_attrs``
    (``menu_item`` its ``type``, ``image`` its ``alt``), so out of reach
    from here: they carry their own guard. That is why the
    ``test_a_changed_tag_drops_what_it_cannot_carry`` gate reads the
    RENDER and not this table.
    """
    spared = set(spare)
    for name, tags in TAG_BOUND_ATTRS.items():
        if name in attrs and name not in spared and tag not in tags:
            del attrs[name]


_SHRINK_TOKENS = ("inline-block", "inline-flex", "inline-grid", "inline-table")
#: Inline tags BY NATURE: they size themselves to their content without
#: any class declaring it. A <span> root with no display token hugs, an
#: identical <div> fills — the class alone cannot tell them apart.
_INLINE_TAGS = frozenset({"span", "a", "label", "em", "strong", "code",
                          "abbr", "small", "b", "i", "button"})

_SHRINK_WIDTH_RE = re.compile(r"(?:^|\s)(?:w-fit|w-max|w-min|w-auto|w-\d|w-\[)")

#: ⚠️ A WORD, not a substring. ``"w-full" in cls`` was true for
#: ``max-w-full`` — which declares the opposite: a CEILING, not a width.
#: Found on 2026-08-25 by setting ``max-w-full`` on the calendar's root:
#: its tooltip wrapper started stretching across the whole line, so the
#: panel anchored on the row and not on the component. The trap holds for
#: ``sm:w-full``, ``group-hover:w-full``, any prefix at all — and it only
#: shows in the browser.
_FILL_WIDTH_RE = re.compile(r"(?:^|\s)w-full(?:\s|$)")


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
    if _FILL_WIDTH_RE.search(root_cls):
        return False
    if any(token in root_cls for token in _SHRINK_TOKENS):
        return True
    if _SHRINK_WIDTH_RE.search(root_cls):
        return True
    if re.search(r"(?:^|\s)block(?:\s|$)", root_cls):
        return False
    return None


def trigger_hugs_its_content(root_cls: str) -> bool:
    """Does the root size itself to its content?

    ⚠️ **Do NOT answer with "it contains ``w-full``"**, and that is the
    2026-08-10 correction: a block ``div`` with no declared width fills
    its parent **without saying so**. The repository already knew it
    elsewhere — ``test_input_root_fills_width`` writes in black and white
    "radio_group / form fill without a literal ``w-full``, so we forbid
    the shrink tokens rather than require ``w-full``" — but this very
    function was still using the signal that gate declares unreliable.

    Measured before the correction: **eight shipped components** rendered
    a tooltip that shrank them to their content's width — ``grid``,
    ``vstack``, ``hstack``, ``flex``, ``form``, ``radio_group``, ``tabs``
    (and ``dropzone``, which brought it up). Including *the two* the gate
    cited as examples.
    """
    return bool(_class_decides_width(root_cls))


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
    (the universal-modifier path). Cf. :func:`trigger_hugs_its_content`
    for why « does it say ``w-full`` » is the wrong question.
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
    """Collapse an anchored overlay's ``inline-* w-fit h-fit`` default to
    ``block w-full``. Strip the fit tokens too : Tailwind's ``w-full w-fit``
    ordering is non-deterministic, so leaving ``w-fit`` in can still win and
    the full-width trigger collapses."""
    return (
        root_cls
        .replace("inline-block", "block w-full")
        .replace("inline-flex", "block w-full")
        .replace("w-fit", "")
        .replace("h-fit", "")
    )


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

    Lives here, next to its twin, so the pair is read together — the
    inline ``.replace()`` this replaces restated the ordering rationale a
    second time, three lines below a comment citing the first.
    """
    return root_cls.replace("w-full", "w-fit")


def trigger_asks_full_width(component: Any, triggers: Iterable[Any]) -> bool:
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
        if _FILL_WIDTH_RE.search(source or ""):
            return True
    return trigger_is_full_width(triggers)


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
#: wired to one of them must keep its HTMX bundle THERE — relocating it
#: onto a value carrier or a focusable child points the listener at an
#: element that never sees the event, and the handler dies silently (no
#: error, no POST : the ``EVENTS`` + ``on_X=`` dead-letter shape of
#: ``traps.md``).
#:
#: Declared here, next to the effect that dispatches them, rather than as
#: each component's private list of what DOES relocate : that inverted
#: form is a whitelist you have to remember to extend, and forgetting is
#: the silent failure it was meant to prevent.
ROOT_DISPATCHED_EVENTS = frozenset({"open", "close"})


def floating_placement(position: str, align: str) -> str:
    """Theme ``position`` + ``align`` → a ``$bz.helpers.floating`` placement.

    The floating helper takes ``"<side>"`` or ``"<side>-<align>"`` ;
    ``center`` is its default so we drop it to keep the string tidy.

    Lives here, next to :func:`anchored_panel_effect` which consumes its
    output, because Popover and Dropdown each carried a private copy
    (audit F58) — the same converter feeding the same helper, maintained
    twice.
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
    (``MIN_MATCHED_WIDTH``, 192 px): below a trigger narrower than that —
    a ``ui.select`` in a sidebar collapsed to ``rail``, measured at 31 px
    — the panel rendered the trigger's width and wrapped its labels
    letter by letter. Above the floor the behaviour is unchanged, to the
    identical.

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
        f"const __p = '{placement}'; "
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
        f"}} else if ($el._bzFloat) {{ "
        f"$el._bzFloat(); $el._bzFloat = null; }} "
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
    (open→callback sees true→re-closes). Cf. ``traps.md`` § *anchored
    overlay .toggle() only opens (microtask-between-listeners)*.
    """
    return (
        f"$bz.helpers.escapeKey(() => {{ "
        f"if ($el.isConnected && ({open_expr})) {{ {open_expr} = false; }} }}); "
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
    keeps the contract simple. Cf. ``.claude/bretzel/imperative-api.md``.
    """
    return {
        "bz-on:bz-open": f"{open_expr} = true",
        "bz-on:bz-close": f"{open_expr} = false",
        "bz-on:bz-toggle": f"{open_expr} = !{open_expr}",
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


def install_value_commands(
    component: Any,
    *,
    empty: Any = "",
    focus_selector: str | None = None,
) -> None:
    """Install ``.set()`` / ``.clear()`` / ``.focus()`` / ``.blur()``.

    The twin of :func:`install_open_close_toggle`, for the other half of
    the imperative API: the one for components that carry a VALUE.

    Why a factory here rather than four methods per class
    ------------------------------------------------------
    Because the six pickers arrived WITHOUT any imperative surface — the
    only whole group of the catalogue in that case (measured on
    2026-09-02: 22 components had one, they had zero) — and writing them
    by hand would have copied the same block six times. That is exactly
    the kind of debt this module exists to avoid.

    ``Input``, ``Select`` and ``Combobox`` keep their own methods, and it
    is not a second convention: their ``focus`` aim at GENUINELY
    different elements (the root, a ``[role=combobox]``, an
    ``input[type=text]``), and their ``clear`` depends on a ``multiple``
    mode. What they share — ``set`` = ``_value_command`` — fits on one
    line.

    ``focus_selector`` names the element to aim at INSIDE the component;
    ``None`` aims at the root. The six pickers all render an ``<input>``
    as their first focusable element (checked on the six rendered HTML),
    hence their shared ``"input"``.
    """

    def _set(value: Any) -> str:
        return component._value_command(value)

    def _clear() -> str:
        return component._value_command(empty)

    def _target() -> str:
        root = f"document.getElementById('{component.id}')"
        return root if focus_selector is None else (
            f"{root}.querySelector('{focus_selector}')"
        )

    def _focus() -> str:
        return f"{_target()}.focus()"

    def _blur() -> str:
        return f"{_target()}.blur()"

    component.set = _set
    component.clear = _clear
    component.focus = _focus
    component.blur = _blur


# ── Client-local dismiss (Alert / Badge / Banner) ────────────────────────
#
# The "pure client" dismiss shared by the dismissible feedback family: a
# ``bz-data="{open: true}"`` flag + ``bz-show="open"`` on the root, and a
# × that does ``open = false`` (hide) + ``$dispatch('close')`` (bubbles the
# event ``on_close=`` listens to). Copied identically 3× — extracted here.

#: The × button's handler: hides the component client-side AND
#: re-dispatches ``close`` so the server/client ``on_close=`` fires.
DISMISS_TOGGLE_CLICK = "open = false; $dispatch('close')"


def close_handler_wired(attrs: dict[str, Any]) -> bool:
    """True if a ``close`` handler is wired on ``attrs`` — server
    (``hx-trigger="close"``) or client (``bz-on:close``).

    Encodes the rule "declaring an ``on_close=`` MUST bring out the ×
    affordance that fires it": without it, the handler was a silent
    dead letter (no × ever dispatched ``close``). The peek was copied
    identically into Alert / Badge / Banner.
    """
    return attrs.get("hx-trigger") == "close" or "bz-on:close" in attrs


def dismiss_local_scope() -> dict[str, str]:
    """The dismiss's client-local scope: ``bz-data="{open: true}"`` +
    ``bz-show="open"`` to set on the root. Keyed by ``bz-id`` (survives
    morphs); no FOUC pre-stamp (the initial ``open: true`` eval is
    truthy). Copied identically into Alert / Badge / Banner."""
    return {"bz-data": "{open: true}", "bz-show": "open"}


def dismiss_button(
    *,
    button_class: str,
    aria_label: str,
    icon_size: str = "sm",
    on_click: str = DISMISS_TOGGLE_CLICK,
    extra_attrs: dict[str, Any] | None = None,
) -> Element:
    """The × button — ONE emission for the whole framework.

    ``on_click`` defaults to the dismiss's local toggle (feedback family:
    Alert / Badge / Banner). FileUpload overrides it: its × removes ONE
    entry from a list, not the whole component. The gesture differs, the
    CONSTRUCTION is the same — and it is that which this helper
    single-sources, and it was the last × made by hand (it emitted a raw
    ``<iconify-icon>`` with ``lucide:`` hard-coded, so without the FOUC
    guard nor the theme's icon set — finding #2 of the composition
    audit).

    Before: the *wiring* (``DISMISS_TOGGLE_CLICK`` / ``dismiss_local_scope``
    / ``close_handler_wired``) was single-sourced here, but the **button's
    construction** had drifted into 3 shapes — Alert through
    ``IconButton`` (detach ✓), Badge/Banner as a raw ``<button>`` + Icon
    (Banner had forgotten the detach → the × leaked to the root through
    ``serialize_html``). This helper closes the *construction* axis as the
    wiring already was:

    - **detach baked in**: the Icon is built then
      :meth:`Component.render_detached` — impossible to make a × leak
      again.
    - **bz-show/FOUC gating single-sourced**: ``(path) && open`` +
      ``display:none`` pre-stamp when the SSR snapshot is falsy. (Alert
      omitted the ``&& open`` — drift harmonised; with no observable
      effect, the × lives in a root already hidden by
      ``bz-show="open"``.)

    The **style strings stay per-theme**: ``button_class`` is composed by
    the caller from ITS theme (cf. ``feedback_no_shared_style_tokens`` —
    we factor out the logic, not the visual tokens).

    ⚠️ The × no longer has a ``bz-show`` gating: it existed for a
    ``dismissible=<ClientBinding>`` that the three constructors REFUSE
    since the 2026-07-16 cut (``dismissible`` is in no
    ``BINDABLE_PROPS``). The ``show_path`` / ``hidden_ssr`` parameters
    were therefore always at their default — removed (audit F05/F06/F07).
    The × lives in any case in a root already hidden by
    ``bz-show="open"``.
    """
    # Deferred: base.component depends on base._wiring, top-level = cycle.
    from bretzel.components.base.component import (
        Component,
    )
    from bretzel.components.primitives.icon import Icon

    attrs: dict[str, Any] = {
        "type": "button",
        "class": button_class,
        "aria-label": aria_label,
        f"{BZ_ON_PREFIX}click": on_click,
    }
    if extra_attrs:
        attrs.update(extra_attrs)
    return Element(
        tag="button",
        attrs=attrs,
        children=(Component.render_detached(Icon("x", size=icon_size)),),
    )


def teleport_to_body(panel: Node, owner: Any = None) -> Node:
    """Wrap an overlay ``panel`` in a ``<template bz-teleport="body">`` so the
    runtime projects it under ``<body>`` at init.

    **Real scope: the ANCHORED overlays only** — Tooltip, Popover,
    Dropdown, and `SidebarFooter`'s popover. They are ``position: fixed``
    and float against their trigger, so any ancestor with ``overflow`` (a
    scrollable container, a ``Card``'s ``overflow-hidden``) or with a
    stacking context / ``transform`` would clip them or mis-stack them.

    ⚠️ **Dialog and Drawer do NOT go through here**, contrary to what this
    docstring announced until 2026-08-01 by saying it covered "modal"
    panels. It is an abstention, not an observed oversight: their
    full-screen backdrop makes them less sensitive to clipping, and no
    ``transform`` ancestor was found in the current shell. The risk stays
    **latent** — an app layout that set a ``transform`` above a Dialog
    would make it the containing block. To settle: teleport the modals
    too, or keep the abstention (cf. `todo.md`).
    Teleporting to ``<body>`` frees the panel from those traps ; the runtime
    keeps the projected clone bound to THIS component's ORIGIN scope
    (``node._bzScopeHost = template`` — bare signal names and ``$refs`` still
    resolve here, and morphs re-project on content change). Cf.
    ``runtime/_src/02_directives.js::bindTeleport`` + traps.md.

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



def _refuse_unknown_color(component: Any, color: str) -> None:
    """Raise if ``color`` has no bridge — so no steps.

    ⚠️ **This refusal is the remaining half of a gate**, and it nearly
    disappeared with the 2026-08-30 removal.

    ``resolve_slot_or_keyword`` had raised on an unknown colour since
    2026-08-18, after the bug measured on ``ui.badge(color="neutral")``:
    it built, it rendered, ``bretzel check`` said nothing, and the element
    came out **with no style in production** — because the resolved class
    existed in no source, so in no compiled CSS. Correct in dev (the
    browser compiler scans the live DOM), dead in prod, identical HTML on
    both sides.

    The steps changed the mechanism and **not** the failure mode:
    ``bz-c-neutral`` is a class with no rule, so the twelve steps are
    undefined, so every declaration that reads them is invalid. The
    component renders bare, with no error. The refusal therefore had to be
    re-placed here, where the colour name is now consumed.

    Outside a render context (a bench, a unit test) we cannot read the
    palette: we keep quiet rather than refuse wrongly.
    """
    from bretzel.render.context import maybe_current_context

    ctx = maybe_current_context()
    theme = getattr(getattr(ctx, "app", None), "theme", None)
    getter = getattr(theme, "get_palette", None)
    if not callable(getter):
        return

    from bretzel.theme.bridges import bridged_color_names

    known = bridged_color_names(getter())
    if color in known:
        return
    raise ComponentUsageError(
        f"{type(component).__name__}(color={color!r}): unknown colour.\n"
        f"  The available colours are {sorted(known)}.\n"
        "  A colour outside that list has no bridge class, so no steps: "
        "the component would render WITH NO STYLE, with no error and no "
        "trace — and only in production, because the dev compiler scans "
        "the live DOM.\n"
        "  To add a brand colour: "
        '``Theme(palette={"brand": "#..."})``.'
    )


def _append_class(node: Node, extra: str) -> Node:
    """``node`` with ``extra`` added to its ``class``."""
    if not isinstance(node, Element):
        return node
    current = str(node.attrs.get("class", "")).strip()
    return Element(
        tag=node.tag,
        attrs={**node.attrs, "class": f"{current} {extra}".strip()},
        children=node.children,
    )


#: The pattern of a COMPLETE value, by picker granularity.
#:
#: It is the only thing that set MonthPicker's mirror apart from its
#: three neighbours' — and it is for that one-character gap that it
#: carried a fourth copy written by hand. The guard they encode is the
#: same everywhere: write ONLY what is complete, otherwise a typing in
#: progress ("2026-0") would erase the calendar's selection.
_COMPLETE_VALUE_RE: dict[str, str] = {
    "day": "/^\\d{4}-\\d{2}-\\d{2}$/",
    "month": "/^\\d{4}-\\d{2}$/",
}


def calendar_value_mirror(
    value_expr: str, *, is_range: bool, granularity: str = "day"
) -> str:
    """``bz-effect`` body mirroring ``value_expr`` onto a child
    ``<bz-calendar>``'s observed ``value`` ATTRIBUTE.

    V3 ``bz-attr:value`` on a custom element writes the JS *property*,
    which skips ``attributeChangedCallback`` — so the date pickers do
    an explicit ``setAttribute`` from the wrapper instead (cf.
    ``traps.md`` § *bz-attr value on a custom element*). The body :

    - captures ``value_expr`` ONCE (so a bound store path is read a
      single time per tick, not 2-3×) ;
    - pushes the empty string to clear, a clean value (single) / JSON
      pair (range) to set, and ``null`` (no write) while the user is
      mid-typing a partial one ;
    - only ``setAttribute`` when the attribute actually differs.

    Shared by DatePicker and WeekPicker (``is_range=False``, scalar
    ISO), MonthPicker (``granularity="month"``, ``"YYYY-MM"``) and
    DateRangePicker (``is_range=True``, the body's caller prepends its
    own store-push fragment before this in the same single
    ``bz-effect``). Returns the inner statements — the caller wraps
    them in its ``(() => { … })()`` effect shell.

    ``granularity`` exists because MonthPicker kept a hand-written copy:
    the helper hard-coded ``YYYY-MM-DD``, so the only picker with a
    ``YYYY-MM`` value could not use it. A parameter rather than a
    divergence — it was the 4th copy of a trap that has its own entry in
    ``traps.md``, the worst category to leave duplicated.
    """
    iso_re = _COMPLETE_VALUE_RE[granularity]
    if is_range:
        # ``value_expr`` is a ``[start, end]`` pair expression ; the
        # caller addresses ``vstart`` / ``vend`` locals, so the mirror
        # reads them directly rather than re-capturing.
        return (
            "const cal = $el.querySelector('bz-calendar'); "
            "if (!cal) return; "
            "let _v = null; "
            "if (!vstart && !vend) _v = ''; "
            f"else if ({iso_re}.test(vstart) && {iso_re}.test(vend)) "
            "_v = JSON.stringify([vstart, vend]); "
            "if (_v !== null && cal.getAttribute('value') !== _v) "
            "cal.setAttribute('value', _v); "
        )
    return (
        "const cal = $el.querySelector('bz-calendar'); "
        "if (!cal) return; "
        f"const _val = ({value_expr}); "
        f"const _v = !_val ? '' : ({iso_re}.test(_val) ? _val : null); "
        "if (_v !== null && cal.getAttribute('value') !== _v) "
        "cal.setAttribute('value', _v); "
    )


def change_emit_effect(value_expr: str) -> str:
    """``bz-effect`` body that fires ``change`` on a hidden input.

    Runs in directive context (``$el`` / ``$nextTick`` injected, unlike a
    bz-data method body), re-evaluating ``value_expr`` on every state tick.
    Bootstraps quietly — the first run only records the baseline, so the
    SSR→hydration handoff never fires a phantom change ; a genuine change
    dispatches a bubbling ``change`` so the relocated ``hx-post`` /
    ``bz-on:change`` handler on the same input fires with a populated
    FormData. ``$nextTick`` lets the runtime flush ``bz-attr:value`` onto
    the DOM input BEFORE HTMX serialises it.

    Shared by every value-holding control that relocates its change wiring
    onto a hidden input. The population is NOT copied here — it used to be
    (six names for ten callers, drifted by 2026-08-21); it is read in
    ``tests/consistency/test_a_relocated_change_reaches_its_carrier.py``,
    which DISCOVERS it. Promoted to ``base/`` (2026-06-23) — it used to be
    copied byte-for-byte into all six because the old anti-rule 5 banned
    the cross-group import ; the rule is now "no cycles", and ``base/`` is
    importable by all, so the single source lives here.
    """
    return (
        f"((v) => {{ "
        f"if ($el._bzLast === undefined) {{ $el._bzLast = v; }} "
        f"else if (v !== $el._bzLast) {{ $el._bzLast = v; "
        f"$nextTick(() => $el.dispatchEvent("
        f"new Event('change', {{bubbles: true}}))); }} "
        f"}})({value_expr})"
    )


# ── Server-action wire attrs — the ONE definition ────────────────────
# The native-HTMX bundle ``emit_attrs`` stamps on a component root for a
# callable ``on_change=`` handler : ``hx-post`` + ``hx-trigger`` +
# ``hx-target`` + ``hx-swap`` + optional ``hx-vals`` + the HMAC stamps
# ``data-bz-sig`` / ``data-bz-ts``. Value-holding controls whose root
# carries no ``name`` / ``value`` (Accordion, Pagination, Tree, Tabs,
# Select, Combobox, ToggleGroup, Slider, NumberInput, Calendar) relocate
# this bundle onto a hidden ``<input>`` so the dispatched FormData is
# non-empty (cf. traps.md § "bz-event:change on a div").
#
# ``DATA_BZ_TS`` MUST travel with ``DATA_BZ_SIG`` : the HMAC v2 signature
# is computed over ``action_id|args|render_ts`` and the bridge reads the
# ts off ``closest("[data-bz-sig]")`` — i.e. the SAME element as the sig.
# Relocating the sig without the ts leaves the ts on the (now
# handler-less) root, so the bridge forwards an empty ``X-Bz-Ts`` and
# every POST 403s. This bit the framework once already : at the HMAC-v2
# rollout four component-LOCAL copies of this tuple missed ``data-bz-ts``
# (cf. traps.md § "data-bz-ts forgotten at relocate"). There are now NO
# component-local copies — every value-holding control imports
# ``SERVER_ACTION_ATTRS`` from here, so the sig+ts couple can only change
# in one place. Guarded by ``tests/consistency/test_action_wire_attrs.py``.
SERVER_ACTION_ATTRS: tuple[str, ...] = (
    "hx-post",
    "hx-trigger",
    "hx-target",
    "hx-swap",
    "hx-vals",
    DATA_BZ_SIG,
    DATA_BZ_TS,
)

# ``SERVER_ACTION_ATTRS`` plus the string-handler shape ``bz-on:change``.
# Controls that relocate BOTH handler shapes off the root (Accordion,
# Pagination, Tree, Tabs) pop this superset ; the rich inputs route the
# string handler per-event separately and relocate only
# ``SERVER_ACTION_ATTRS``.
CHANGE_HANDLER_KEYS: tuple[str, ...] = (
    *SERVER_ACTION_ATTRS,
    f"{BZ_ON_PREFIX}change",
)


def trigger_event(attrs: Mapping[str, Any]) -> str:
    """The EVENT ``hx-trigger`` serves, without its modifiers.

    ``action_attrs`` writes ``hx-trigger`` in the form
    ``"<event> [modifier] [from:#id]"`` — the modifier coming from a
    ``debounce=`` (``delay:300ms``) or a ``throttle=``. **The event is the
    first word, never the whole string.**

    Why this reader exists (measured on 2026-08-19)
    ------------------------------------------------
    Seven relocation sites compared the WHOLE STRING to an event name
    (``== "change"``, ``in ("focus", "blur")``) or, worse, looked for a
    substring in it (``"change" in trigger``). Setting a ``debounce=``
    therefore made the comparison fail — and each site failed
    DIFFERENTLY:

    ===================================  ==================================
    ``ui.combobox(on_change=, debounce=)``   the popped bundle was re-set
                                             nowhere → ``hx-post``
                                             **gone**, handler dead
    ``ui.toggle_group(…)`` likewise          bundle left on the root, which
                                             does not fire ``change`` →
                                             handler dead
    ``ui.file_upload(on_focus=, …)``         same on the focusable wrapper
    Select / Slider / the 4 pickers          modifier overwritten → the
                                             requested ``debounce=``
                                             **silently lost**
    ===================================  ==================================

    And the substring test was wrong the other way round too:
    ``"change" in "month_change"`` is true, so the day Calendar adopted
    :func:`relocate_server_action`, its ``on_month_change`` would leave
    on the value carrier with a trigger rewritten to ``change``.

    Gated by ``tests/consistency/test_trigger_modifiers_survive.py``.
    """
    return str(attrs.get("hx-trigger", "")).split(" ", 1)[0]


def retrigger(trigger: str, event: str) -> str:
    """Rename an ``hx-trigger``'s event while KEEPING its modifiers.

    Calendar renames ``month_change`` to the kebab CustomEvent
    ``month-change``; rewriting the whole string would throw away the
    ``delay:`` that ``debounce=`` had put in it.
    """
    _, separator, modifiers = str(trigger).partition(" ")
    return event + separator + modifiers


def pop_change_handler(attrs: dict[str, Any]) -> dict[str, Any]:
    """Pop every change-handler attribute out of ``attrs`` (in place).

    Returns the popped subset — empty when no ``on_change`` was wired.
    The caller stamps the result onto its hidden form input.

    ⚠️ **Only suits SINGLE-TARGET components** — those whose ``EVENTS``
    contains only ``("change",)``, so for which "the only server bundle is
    the change" is a true invariant (Tabs, Pagination, Tree, Accordion). A
    component that also exposes ``focus`` / ``blur`` must go through
    :func:`relocate_server_action`, which ROUTES instead of moving
    everything to a single target.
    """
    return {key: attrs.pop(key) for key in CHANGE_HANDLER_KEYS if key in attrs}


#: ``dispatch=`` by default: "the same expression as the value". A string
#: impossible to write by accident, rather than a ``None`` that would mean
#: two things ("by default" and "certainly not").
_SAME_AS_VALUE = "\x00same-as-value"


def hidden_carrier_attrs(
    value_expr: str,
    *,
    initial: Any = "",
    ref: str = "bzhidden",
    dispatch: str | None = _SAME_AS_VALUE,
) -> dict[str, Any]:
    """The SKELETON of a value-carrying ``<input type="hidden">``.

    A ``<div>`` carries neither ``name``/``value`` nor a native
    ``change``. Components whose root is not a form control therefore set
    a hidden input that does both — 12 sites in 11 files.

    This helper renders the **five invariant attributes**:

    - ``type="hidden"``;
    - ``bz-ref`` — how the scope finds the carrier again;
    - ``value`` — the SSR value, so the first POST leaves correct even
      before the runtime has booted;
    - ``bz-attr:value`` — the reactive binding that keeps it up to date;
    - ``bz-effect`` — :func:`change_emit_effect`, **the dispatcher
      without which everything above is mute**.

    The dispatcher came in here on 2026-08-21, and it is an INVERSION
    --------------------------------------------------------------------
    It was left to the caller, in the name of an argument written in
    black and white: "the ``change`` dispatch genuinely differs
    (``change_emit_effect`` for most, a scope method for Slider)".
    **Slider is not a caller** — it writes its skeleton by hand (declared
    in ``_SKELETON_DEBT``), like Calendar and Dropzone, the two others
    that dispatch from the runtime. The counter-example that justified
    the variance therefore did not live in the population concerned: of
    the **ten** real callers, ten set ``change_emit_effect``, and **nine**
    on the same expression as the one they had just passed here.

    What it cost: the carrier relocates the ``hx-post`` bundle of a
    server ``on_change=`` — but a hidden input never fires ``change`` by
    itself, and a programmatic write of ``.value`` emits no event.
    Forgetting the ``bz-effect`` is therefore an INERT control, with no
    error and no warning. The five date pickers forgot it, and nobody saw
    it before a human used the app.

    Hence the inversion: the dispatch is **acquired**, and one refuses it
    explicitly (``dispatch=None``) or sets it on another expression
    (``dispatch=<expr>``, ToggleGroup's case, whose posted value and
    observed value differ). An opt-out is read back; an opt-in is
    forgotten.

    ⚠️ **``name`` and ``required``, though, stay with the caller.**

    ``name`` is the important case: sticking a default ``name="value"``
    on a ``Tabs`` or an ``Accordion`` would inject a **stray field into
    every enclosing form**. A Tabs is not a form control — it has a
    ``name`` only if the caller wants one. It is a LEGITIMATE variance,
    and a ``hidden_carrier_input`` that uniformised it would uniformise a
    bug. ``required`` concerns only form controls.

    Gated by ``tests/consistency/test_hidden_carrier_skeleton_is_shared.py``
    (the skeleton comes from here) and
    ``tests/consistency/test_a_relocated_change_reaches_its_carrier.py``
    (no mute carrier receives a server action) — the second also covers
    the four hand-written carriers, out of reach of this default.
    """
    attrs: dict[str, Any] = {
        "type": "hidden",
        "bz-ref": ref,
        "value": initial,
        f"{BZ_ATTR_PREFIX}value": value_expr,
    }
    if dispatch is not None:
        attrs["bz-effect"] = change_emit_effect(
            value_expr if dispatch == _SAME_AS_VALUE else dispatch
        )
    return attrs


def relocate_server_action(
    root_attrs: dict[str, Any],
    *,
    value_carrier: dict[str, Any],
    focusable: dict[str, Any],
) -> None:
    """Route the server-action bundle to the right target, **in place**.

    A rich component has two carriers and they are not interchangeable:

    - the **value carrier** — a ``<input type="hidden">`` that carries
      ``name`` + ``value`` and dispatches a synthetic ``change``; that is
      the one the FormData must find;
    - the **focusable element** — the trigger, the only one to receive
      ``focus`` / ``blur`` natively.

    The choice is read in ``hx-trigger``, which ``action_attrs`` has
    already set from the event the handler REALLY listens to. That is the
    decision this function takes away from the caller.

    Why it exists (base layer audit, item 10)
    -------------------------------------------
    ``pop_change_handler`` factored out only the **pop** — the easy part —
    and left the **routing** — the hard part — to the caller. Measured
    result: 4 adopters, all 4 being precisely the single-target
    components, against 8 manual loops among the rich components.

    And the flaw had a cost. ``slider.py`` moved the bundle to the hidden
    input *without looking at* ``hx-trigger``, then forced
    ``hx-trigger="change"``: a callable ``on_focus=`` therefore left on
    the hidden input, which never fires ``focus``, and fired on the
    ``change``. Not dead — **worse than dead**: the handler ran at the
    wrong moment (an analytics ``on_focus`` on every drag).

    The fix was propagated BY HAND over the 8 sites: the bugs are dead,
    but no primitive was extracted, so **the 9th component would decide
    alone again**. It is a repair, not a mechanism — and that is exactly
    what this function turns it into.
    """
    if "hx-post" not in root_attrs:
        return
    # ``hx-trigger`` says which event the server handler listens to. A
    # ``change`` bundle joins the value carrier — the hidden input does
    # not fire ``change`` by itself, it is ``change_emit_effect`` that
    # dispatches it there, and the trigger travels with the bundle.
    # Everything else — focus, blur — can only live on the focusable
    # element. ``open`` / ``close`` are dispatched ON the root by
    # ``dispatch_root_effect`` : moving their bundle anywhere else points
    # the listener at an element that never fires them. Leave it put.
    event = trigger_event(root_attrs)
    if event in ROOT_DISPATCHED_EVENTS:
        return
    bundle = {a: root_attrs.pop(a) for a in SERVER_ACTION_ATTRS if a in root_attrs}
    # EQUALITY on the event, never a substring of the trigger: ``"change"
    # in "month_change"`` is true, and so is ``"change" in "input changed
    # delay:200ms"``. Cf. :func:`trigger_event`.
    if event == "change":
        # ``hx-trigger`` travels IN the bundle (it is in
        # ``SERVER_ACTION_ATTRS``), so it arrives intact on the carrier —
        # modifiers included. The old line rewrote it to a bare
        # ``"change"`` and threw away the caller's ``debounce=``.
        value_carrier.update(bundle)
    else:
        focusable.update(bundle)


def activate_keydown(action_js: str) -> str:
    """Enter / Space activate a NON-native element.

    A ``<button>`` gets keyboard activation for free from the browser. A
    ``<div role="button">`` / ``<tr role="button">`` / ``<div
    role="treeitem">`` gets **nothing**: without this handler, the element
    is reachable with Tab and completely inert at the keyboard.

    Three modules wrote that same guard in three ways (affordance census,
    2026-07-28) — and two of the gaps were FUNCTIONAL, not cosmetic:

    - ``'Spacebar'``, the old key name (IE, old Firefox), was handled only
      by the dropzone: one activated on Space, the other did not;
    - the **target guard** ``$event.target === $el`` existed only in
      Table. Without it, a keystroke on a CHILD control bubbles up to the
      parent and activates it too — a Space on a button nested in a tree
      node fired the node.

    The helper takes the correct superset: the three key names and the
    guard. ``action_js`` is the component's gesture — ``$el.click()`` to
    delegate to its own ``hx-trigger``, a scope call, or inlined JS.
    """
    return (
        "if ($event.target === $el && ($event.key === 'Enter' "
        "|| $event.key === ' ' || $event.key === 'Spacebar')) "
        f"{{ $event.preventDefault(); {action_js} }}"
    )


def reject_sealed(kwargs: dict[str, Any], cls: type) -> None:
    """A SEALED prop passed at the call: we say so, with a sentence.

    A sealed prop is declared on the class and deliberately REFUSED at the
    call — a ``VStack``'s axis is its identity, and a ``Radio``'s
    ``option_value`` is fed by its positional ``value``.
    ``bretzel.introspect`` subtracts them from the card, so they are
    announced nowhere; what remained was to answer properly whoever writes
    them anyway.

    ⚠️ **Promoted from ``layout/stack.py`` on 2026-09-04, because half the
    family had no access to it.** The stacks called this guard and answered
    "HStack has a fixed axis — pass no ``direction``". ``Radio`` and
    ``ToggleButton``, for their part, let the collision reach
    ``super().__init__`` and rendered ::

        TypeError: Component.__init__() got multiple values for
        keyword argument 'option_value'

    — which does not name the component, does not say the prop is sealed,
    and reads like a framework bug. Their comment even assumed that
    message ("passing it explicitly produces a multiple values"), so
    nothing would have prompted anyone to fix it.

    The refusal must stay IN the subclass, before its ``super().__init__``:
    the collision is raised by Python when building the call, so the base
    layer never sees it.

    ``SEALED_REASONS`` lets a subclass seal something other than the axis
    (``Pane`` seals ``wrap``) without inheriting a wrong message.
    """
    reasons = getattr(cls, "SEALED_REASONS", {})
    for name in getattr(cls, "SEALED_PROPS", ()):
        if name in kwargs:
            raise ComponentUsageError(
                reasons.get(name)
                or f"{cls.__name__} has a fixed axis — pass no ``{name}``. "
                f"Use the other shortcut, or ``ui.flex(direction=…)`` for "
                f"a runtime-chosen axis."
            )


def coerce_index(
    value: Any, *, default: int = 0, minimum: int | None = None
) -> int:
    """The SSR value of a driven index — best effort, never an exception.

    Three components carry the same "bounded index" archetype —
    ``Pagination``, ``Stepper``, ``Carousel``, all three
    ``IMPERATIVE = ("set", "next", "prev")`` — and each had its copy of
    this conversion, under two names (``_coerce_int`` /
    ``_coerce_index``). The repository's threshold ("twice is a
    coincidence, three times is a pattern") was crossed on 2026-08-02,
    when Pagination gained the imperative trio.

    Why a tolerant conversion and not a cast: **the value crosses a form
    data**. The hidden input serialises it, so it comes back as a STRING
    (``"2"``), and a carousel driven by a binding can receive it empty.
    The FINE bounding, though, is not here: it lives in the scope methods,
    the only place that knows the live value and the real bound (the
    number of pages, the track's geometry). Here we only produce a
    reasonable SSR starting point.

    - ``default``: what an absent or unreadable value is worth — ``0`` for
      a 0-based index, ``1`` for a pagination.
    - ``minimum``: optional floor, for the 0-based indices that must never
      go negative. ``None`` = no floor (pagination lets its ``setActive``
      bound it).
    """
    if value is None:
        return default
    try:
        result = int(value)
    except (TypeError, ValueError):
        return default
    return result if minimum is None else max(minimum, result)


def bool_attr(expr: str) -> str:
    """A reactive attribute that must carry the STRING ``"true"``/``"false"``.

    ``bz-attr`` treats a boolean the way HTML wants: ``true`` → **empty**
    attribute, ``false`` → attribute **removed**. That is the right
    semantics for ``disabled`` / ``checked`` / ``required``, where the
    PRESENCE of the attribute is the information.

    Two families need the opposite — the literal value:

    - **ARIA** (``aria-disabled``, ``aria-expanded``, ``aria-pressed``,
      ``aria-selected``): a screen reader reads the value, and the
      Tailwind ``aria-disabled:`` variant compiles to
      ``[aria-disabled="true"]``, which an empty attribute does not match;
    - **the ``data-*`` that drive a style** (``data-open``,
      ``data-active``, ``data-menu-open``): ``data-[open=true]:`` matches
      the literal.

    In both cases, forgetting the ternary breaks NOTHING visible — neither
    the style nor the announcement applies, in silence. The rule was
    written as a comment in three places; **nineteen sites
    re-implemented it by hand, ten of them without parenthesising their
    operand** (affordance census, 2026-07-28). It lives here now.

    The parentheses are not cosmetic: ``a || b ? 'true' : 'false'`` reads
    as ``(a || b) ? …`` by luck, but any looser expression would
    re-associate. Same class as the parenthesising of the binding algebra
    (cf. ``tests/consistency/test_client_expression_atomic.py``).
    """
    return f"({expr}) ? 'true' : 'false'"


def server_sync_marker(*props: str, enabled: bool) -> str:
    """``_serverSync`` fragment for a component's ``bz-data`` object literal.

    ``" _serverSync: ['<prop>', …],"`` when ``enabled`` (the value(s) are
    server-backed → a ``@refreshable`` morph re-adopts them from the freshly
    rendered attr, server wins) ; ``""`` otherwise (a client-owned value
    keeps its state through the morph). Accepts one OR several keys — a
    control whose scope holds several server-driven signals (calendar's
    ``year``+``month``, the range picker's ``vstart``+``vend``) lists them
    all in one marker. The ``_serverSync`` key is single-sourced from
    :data:`protocol.SERVERSYNC_KEY` and mirrored into the JS scope reader, so
    a rename can't silently strand one control. The leading space + trailing
    comma suit emission after a leading field in a ``{...}`` literal.
    """
    if not enabled:
        return ""
    keys = ", ".join(f"'{p}'" for p in props)
    return f" {SERVERSYNC_KEY}: [{keys}],"


def escape_init(open_expr: str) -> str:
    """``bz-init`` : global Escape-to-close while the overlay is open."""
    return (
        f"$bz.helpers.escapeKey(() => {{ "
        f"if ($el.isConnected && ({open_expr})) "
        f"{{ {open_expr} = false; }} }})"
    )


def outlet_target_attrs(component_name: str, outlet: Any) -> dict[str, str]:
    """``{"hx-target": "#outlet_<shell>"}`` for a link that names its region.

    Without ``outlet=``, the shell boosts every internal link towards
    ``[data-bz-outlet]`` (``render/shell.py``) and htmx keeps the FIRST
    outlet in the document. With nested shells that is always the
    outermost: the server therefore re-renders the inner shell AS WELL AS
    the page, whereas the link only changes the page.

    Measured in alternating A/B in the same process on 2026-09-08, twenty
    clicks per variant: **1,204 bytes and 10 ms** aiming at the outer one,
    **569 bytes and 3 ms** aiming at the inner one.

    ⚠️ **We take the shell FUNCTION, never its id**, and that is what
    makes the mistake impossible. The id is written ``outlet_<name>``;
    writing it by hand gives a selector that matches nothing, and htmx
    then sends NO request — with no error, no trace. That is exactly what
    happened to the bench that produced the measurement above.
    """
    if outlet is None:
        return {}
    if not callable(outlet) or not hasattr(outlet, "_bz_layout"):
        raise ComponentUsageError(
            f"{component_name}: ``outlet=`` takes a function decorated "
            f"``@layout``, not {type(outlet).__name__}. It is the shell "
            f"whose region must be replaced."
        )
    return {"hx-target": "#" + outlet_id_for(outlet.__name__)}
