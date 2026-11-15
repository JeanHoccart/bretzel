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

**The line at rest follows ``gap=``** (table ``lines``). With a gutter,
the space already separates the panels, and a line in it would be a
second separator: nothing is drawn. With ``gap="none"`` the panels touch,
and the handle is the border between them: one stroke (``--bz-stroke``)
in the framework's border tint, ``text/10`` — the one of a card's outline
and of ``ui.divider``. ``size=`` sets the grip only; a thicker bar would
be a heavier border than any other. Either way, under the pointer and
while held, the line takes the colour's border and solid steps.

**The grip shows under the pointer, on focus and while held** — never at
rest. Next to a 1 px border or in an empty gutter, a permanent pill reads
as an object of its own; the cursor says the handle can be grabbed. The
price is touch: a finger does not hover, so a gutter handle is only seen
once pressed (``active:``).

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
sides. Two static strings cannot lie.

Slots :
- ``root``           : the flex group — carries the ``bz-data`` scope
- ``horizontal`` / ``vertical`` : the group's direction, one slot per axis
- ``panel``          : one panel (``ui.resizable_panel``)
- ``handle``         : the handle between two panels, at rest
- ``handle_active``  : what the handle gains when it is drivable
- ``handle_locked``  : what it gains when ``disabled=True``
- ``handle_h`` / ``handle_v`` : what depends on the axis (cursor,
  direction of the grab zone)
- ``grip``           : the central mark, drawn under the pointer, on focus
  and while held
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
            # No background here: at rest it comes from ``lines`` (by
            # ``gap``), under the pointer from ``handle_active``.
            "group/rz relative shrink-0 touch-none select-none "
            "transition-colors duration-150 ease-out "
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
            "hover:bg-(--bz-border) active:bg-(--bz-solid)"
        ),
        # No ``pointer-events-none`` beside the cursor: an element that
        # receives no pointer event never paints its cursor, so the class
        # would be present and invisible. It is the bug
        # ``test_disabled_affordance`` locks down, paid for by Tree.
        "handle_locked": "cursor-not-allowed",
        "handle_h": (
            "w-(length:--bz-stroke) cursor-col-resize before:-inset-x-1 before:inset-y-0"
        ),
        "handle_v": (
            "h-(length:--bz-stroke) cursor-row-resize before:-inset-y-1 before:inset-x-0"
        ),
        # Transparent at rest, drawn under the pointer, on keyboard focus
        # and while held (module docstring). A colour, not an
        # ``opacity-0`` reveal: it is a mark, not a control — the handle
        # around it stays where it was, grabbable, and changes the cursor.
        "grip": (
            "pointer-events-none rounded-full bg-transparent "
            "transition-colors duration-150 ease-out "
            "group-hover/rz:bg-faint group-focus-within/rz:bg-faint "
            "group-active/rz:bg-faint"
        ),
    },
    #: The handle's line AT REST, by ``gap`` value — a responsive table
    #: like ``gaps``, so ``gap={"base": "none", "md": "sm"}`` draws the
    #: line on a phone only. Every value names its class, ``bg-transparent``
    #: included: an empty entry would let the ``base`` line through at
    #: ``md``.
    "lines": {
        "none": "bg-line",
        "xs": "bg-transparent",
        "sm": "bg-transparent",
        "md": "bg-transparent",
        "lg": "bg-transparent",
        "xl": "bg-transparent",
    },
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
    #: ancestor's padding can never create space INSIDE the group. It
    #: reaches the panel, whose content still runs to where the handle
    #: starts. Only the panels' parent knows where the handle is.
    "gaps": {
        "none": "gap-0",
        "xs": "gap-(--bz-gap-1)",
        "sm": "gap-(--bz-gap-2)",
        "md": "gap-(--bz-gap-4)",
        "lg": "gap-(--bz-gap-6)",
        "xl": "gap-(--bz-gap-8)",
    },
    # ``grip_*`` = the central mark. The suffix says the GROUP's axis:
    # ``_h`` = panels side by side, so a vertical mark.
    "sizes": {
        "xs": {
            "grip_h": "w-0.5 h-3",
            "grip_v": "h-0.5 w-3",
        },
        "sm": {
            "grip_h": "w-0.5 h-4",
            "grip_v": "h-0.5 w-4",
        },
        "md": {
            "grip_h": "w-1 h-6",
            "grip_v": "h-1 w-6",
        },
        "lg": {
            "grip_h": "w-1.5 h-8",
            "grip_v": "h-1.5 w-8",
        },
        "xl": {
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
