"""Default :class:`Resizable` / :class:`ResizablePanel` theme.

The group is a **flex** container each of whose panels carries
``flex-grow: <weight>`` as an inline style, written by the runtime.
Three details of the ``panel`` slot are not cosmetic:

- ``basis-0`` is what makes the split proportional. Without it, a
  panel's basis is its content, so two panels of equal weight show up
  unequal as soon as one is fuller than the other.
- ``min-w-0 min-h-0`` disables flexbox's automatic floor
  (``min-width: auto`` on a flex item). Without them, a panel REFUSES to
  go below its content's width — a wide table, and the handle jams well
  before the declared minimum, with nothing failing.
- ``overflow-hidden`` keeps the content in its box when you shrink it.
  It is the counterpart of ``min-w-0``: together, they make a panel
  really shrink instead of overflowing onto its neighbour.

The handle is a thin bar with a grab zone WIDER than itself, extended by
a pseudo-element (``before:-inset-x-1``). A 1 px bar would match the
drawing and be impossible to catch; a thick bar would be catchable and
ugly. The two halves of the problem do not have the same answer, hence
the visual / grab-zone separation.

``touch-none`` (``touch-action: none``) is MANDATORY and not a
refinement: without it, the browser reads a finger dragging on the
handle as a page scroll and never sends the ``pointermove`` — the
component is then unusable on touch, in silence, while it works with a
mouse.

**The locked state is a BRANCH, not a negative variant.** The
interactive tokens live in ``handle_active``, which the component only
adds if ``disabled`` is false. Writing ``not-aria-disabled:hover:…``
would have fitted in one string, but would have rested the affordance on
a composition of variants unverified in this repository — and a class
that does not compile fails in SILENCE, with identical HTML on both
sides (memory ``project_assembled_tailwind_class_dev_only``). Two static
strings cannot lie.

Slots :
- ``root``           : the flex group — carries the ``bz-data`` scope
- ``horizontal`` / ``vertical`` : the group's direction, one slot per axis
- ``panel``          : one panel (``ui.resizable_panel``)
- ``handle``         : the handle between two panels, at rest
- ``handle_active``  : what the handle gains when it is drivable
- ``handle_locked``  : what it gains when ``disabled=True``
- ``handle_h`` / ``handle_v`` : what depends on the axis (cursor,
  direction of the grab zone)
- ``grip``           : the central mark, revealed on hover and on focus
"""

from __future__ import annotations

from typing import Any

RESIZABLE_THEME: dict[str, Any] = {
    "slots": {
        # ``w-full`` and not ``w-fit``: a splitter shares a given place,
        # it does not size itself to its content — the "root w-fit" rule
        # of the selector clusters (traps.md) targets controls
        # wrappable in a tooltip, not layout containers.
        "root": "flex w-full",
        "horizontal": "flex-row",
        "vertical": "flex-col",
        "panel": "basis-0 min-w-0 min-h-0 overflow-hidden",
        "handle": (
            # ``group/rz`` names the group the grip watches. Named and
            # not bare: a NESTED Resizable would otherwise make the
            # parent's grip react to hovering the child.
            "group/rz relative shrink-0 touch-none select-none "
            "bg-text/10 transition-colors duration-150 ease-out "
            "flex items-center justify-center "
            # The grab zone overflows the bar — a pseudo-element, so no
            # extra node in the DOM and no box that would take part in
            # the flex.
            "before:absolute before:content-[''] "
            "focus-visible:outline-none focus-visible:ring-2 "
            "focus-visible:ring-inset focus-visible:ring-(--bz-focus)"
        ),
        "handle_active": (
            "cursor-grab active:cursor-grabbing "
            "hover:bg-(--bz-solid)/40 active:bg-(--bz-solid)"
        ),
        # No ``pointer-events-none`` beside the cursor: an element that
        # receives no pointer event never paints its cursor, so the class
        # would be present and invisible. It is the bug
        # ``test_disabled_affordance`` locks down, paid for by Tree.
        "handle_locked": "cursor-not-allowed",
        "handle_h": "cursor-col-resize before:-inset-x-1 before:inset-y-0",
        "handle_v": "cursor-row-resize before:-inset-y-1 before:inset-x-0",
        # The grip is ALWAYS visible, and hover only emphasises it. The
        # opposite reflex (``opacity-0`` then
        # ``group-hover:opacity-100``) is what half the ecosystem does
        # and it is a two-stage trap: a finger does not hover, so on
        # touch the handle no longer announces that it can be grabbed —
        # and the user's browser reports precisely ``any-hover: false``
        # (memory ``project_user_browser_has_no_fine_pointer``). Gated by
        # ``test_hover_only_controls_reachable``, which refused this
        # slot's first version.
        "grip": (
            "pointer-events-none rounded-full bg-text/25 "
            "transition-colors duration-150 ease-out "
            "group-hover/rz:bg-text/60 group-focus-within/rz:bg-text/60"
        ),
    },
    # ``bar_*`` = the bar's THICKNESS, ``grip_*`` = the central mark.
    # The suffix says the GROUP's axis: ``_h`` = panels side by side, so
    # a vertical bar whose width is what varies.
    #: The space between a panel and the handle — the GUTTER. Same
    #: six-step scale as ``ui.flex`` / ``ui.hstack`` / ``ui.vstack`` /
    #: ``ui.grid`` / ``ui.carousel``, because it is the same space: a
    #: flex container separating its children.
    #:
    #: ⚠️ **Copied, not imported from ``FLEX_THEME``**, and it is the
    #: repository's convention: a theme stays self-contained, we
    #: harmonise without factoring. The agreement of the two tables is
    #: held by
    #: ``tests/consistency/test_a_flex_container_spaces_its_children.py``,
    #: which compares them step by step.
    #:
    #: Why it is the GROUP that carries it, and not the panel: an
    #: ancestor's padding can never create space INSIDE the group.
    #: Measurement of 2026-08-23 on the CRM shell (parent at ``p-8``):
    #: the panel did start at x=32, so the padding reached it — but its
    #: content ran to 384, where the handle starts. Zero. Only the
    #: panels' parent knows where the handle is.
    "gaps": {
        "none": "gap-0",
        "xs": "gap-1",
        "sm": "gap-2",
        "md": "gap-4",
        "lg": "gap-6",
        "xl": "gap-8",
    },
    "sizes": {
        "xs": {
            "bar_h": "w-px",
            "bar_v": "h-px",
            "grip_h": "w-0.5 h-3",
            "grip_v": "h-0.5 w-3",
        },
        "sm": {
            "bar_h": "w-px",
            "bar_v": "h-px",
            "grip_h": "w-0.5 h-4",
            "grip_v": "h-0.5 w-4",
        },
        "md": {
            "bar_h": "w-0.5",
            "bar_v": "h-0.5",
            "grip_h": "w-1 h-6",
            "grip_v": "h-1 w-6",
        },
        "lg": {
            "bar_h": "w-1",
            "bar_v": "h-1",
            "grip_h": "w-1.5 h-8",
            "grip_v": "h-1.5 w-8",
        },
        "xl": {
            "bar_h": "w-1.5",
            "bar_v": "h-1.5",
            "grip_h": "w-2 h-10",
            "grip_v": "h-2 w-10",
        },
    },
}

RESIZABLE_PANEL_THEME: dict[str, Any] = {
    # The panel carries NO class of its own: its box is composed by the
    # group (slot ``panel``), which alone knows whether it is in a row or
    # a column and what weight it gets. A theme proper to the panel would
    # give the same box two authors.
    #
    # The dict exists all the same — ``THEME`` is read by
    # ``_resolved_theme`` and by the user override
    # ``Theme(components={…})``, so a component with no slot table
    # declares the EMPTY table rather than leaving the inherited
    # sentinel.
    "slots": {
        "root": "",
    },
}
