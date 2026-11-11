"""Checks run once a page's tree is built: what a component cannot judge alone."""

from __future__ import annotations

import sys
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from bretzel.components.base.attrs import ComponentUsageError

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

    Both refused placements render a page that looks built
    (``tests/probes/probe_bottom_bar_placement.py``):

    - **outside the frame** — a ``ui.viewport`` is ``fixed inset-0``, so
      it leaves the flow. A bar left outside has no document to stick to:
      it lands at **y = 0**, and the frame covers it.
    - **in a ROW** — the bar is full width, so it takes the whole row:
      the neighbouring ``ui.pane`` drops to **0 px wide** and its content
      disappears, with no error and no trace. It is the more
      treacherous of the two, because the bar itself lands in the right
      place.

    Why here and not at the bar's construction
    -------------------------------------------
    Because it is a question of TREE. A bar written BEFORE the
    ``ui.viewport`` cannot know a frame is coming — and for a navbar,
    "the top bar first" is the natural order. And the LAYOUT parent is
    not the construction parent: a ``ui.fragment`` or a ``@refreshable``
    zone is transparent to CSS and opaque to ``parent_stack``, so the bar
    would be judged on its wrapper. Both cases get past a guard placed at
    construction.
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
        if not any(getattr(type(a), "IS_FROZEN_FRAME", False) for a in path):
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


def check_sidebars_are_reachable(sidebars: Iterable[Any]) -> None:
    """A bar that can disappear must have a way back.

    On a phone, a ``ui.sidebar(collapsible="overlay", open=False)`` with
    no trigger renders an ``<aside>`` off screen and **no clickable
    element on screen**. The page answers 200, nothing is logged, and the
    navigation is simply unreachable.

    The component renders no floating chevron of its own: where an app
    affordance goes is not the component's decision. The app needs a piece
    to PLACE — hence ``ui.sidebar_trigger``, and hence this check.

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
        if getattr(type(child), "IS_FROZEN_FRAME", False):
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
        if not getattr(type(ancestor), "IS_TRANSPARENT_WRAPPER", False):
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
