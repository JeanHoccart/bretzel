"""Default :class:`Carousel` theme.

The track is a **scroll-snap** container: `overflow-x-auto snap-x
snap-mandatory`, each slide in `snap-start`. The gesture (touch swipe
with inertia, wheel, keyboard) is the browser's — the theme only frames
it.

Two details of the ``track`` slot are not cosmetic:

- ``[scrollbar-width:none] [&::-webkit-scrollbar]:hidden`` hides the
  native scrollbar. Without it, a carousel shows a horizontal bar under
  its slides on every platform that draws one (Windows, Linux) — while
  the control already exists as arrows and dots. Both forms are
  necessary, and Tailwind ships NO scrollbar utility (it is a
  third-party plugin): hence the arbitrary variants rather than a
  ``scrollbar-none``, which compiles nowhere.
- ``scroll-smooth`` is ABSENT on purpose: ``goTo`` passes ``behavior``
  explicitly, and wants it ``auto`` on the first snap (a carousel
  rendered at ``value=2`` must show on slide 2, not scroll to it on
  load). A global CSS declaration would win over the argument and make
  that first jump animated.

Slots :
- ``root``       : the wrapper — carries the ``bz-data`` scope; a column
  stacking the viewport then the dots
- ``viewport``   : the ``relative`` container that ANCHORS the arrows.
  Without it they position themselves on a height that INCLUDES the dot
  row, and visibly fall below the track's centre
- ``track``      : the snapping scrollable container
- ``slide``      : a child's wrapper — it is what carries the width (so
  ``per_view``) and the ``snap-start``
- ``arrow``      : the two buttons, overlaid on the edges
- ``arrow_prev`` / ``arrow_next`` : their lateral position
- ``dots``       : the row of dots
- ``dot``        : one dot — ``data-selected`` drives its active state
"""

from __future__ import annotations

from typing import Any

#: The ``THEME["responsive"]`` key ``_dots_hidden_class`` will read.
#:
#: A CONSTANT and not two literals, for the same reason as the
#: datatable's ``_field()``: the two halves must agree, and a key copied
#: on both sides falls out of step in silence — the lookup returns
#: ``""``, nothing is hidden any more, and the dots reappear where
#: ``per_view`` rises without anything failing. Mutation-tested: it was
#: the only one of the five scenarios the gate did not catch, and making
#: it unrepresentable was better than adding it there as a special
#: case.
DOTS_HIDDEN = "dots_hidden"

CAROUSEL_THEME: dict[str, Any] = {
    "slots": {
        "root": "flex flex-col gap-3 w-full",
        # The container that ANCHORS the arrows. They were set on the
        # root, so their ``top-1/2`` took the dot row's height into its
        # computation and they fell below the track's visual centre. It
        # is what this slot exists to fix.
        "viewport": "relative",
        # ``bz-no-scrollbar`` is a hook of the FRAMEWORK CSS, not a
        # Tailwind utility (cf. ``theme/css.py`` ``_NO_SCROLLBAR``, and
        # the same choice at Sidebar with ``bz-rail-scroll``).
        # ⚠️ The reason changed on 2026-08-29: the equivalent arbitrary
        # variants compile perfectly well in PROD (checked against the
        # binary) — it is the dev mode's browser compiler that does not
        # handle them. The hook stays because it works on both sides.
        "track": (
            "bz-no-scrollbar flex overflow-x-auto snap-x snap-mandatory"
        ),
        # ``shrink-0`` is what stops flexbox squeezing the slides to
        # make them all fit — without it there is nothing to scroll. The
        # WIDTH comes from ``per_view``, composed at render.
        "slide": "shrink-0 snap-start",
        "arrow": (
            "absolute top-1/2 -translate-y-1/2 z-10 "
            "flex items-center justify-center rounded-full "
            "bg-surface/90 backdrop-blur-sm text-text "
            "border-(length:--bz-stroke) border-text/10 shadow-md "
            "transition-[opacity,background-color] duration-200 ease-out "
            "not-disabled:cursor-pointer not-disabled:active:scale-95 "
            "not-disabled:hover:bg-surface "
            "focus-visible:outline-none focus-visible:ring-2 "
            "focus-visible:ring-offset-2 "
            "focus-visible:ring-offset-background "
            "focus-visible:ring-(--bz-focus) "
            # At the edges the arrow fades instead of disappearing: a
            # control that LEAVES the DOM makes the layout jump and
            # leaves the user looking for where it went.
            "disabled:opacity-0 disabled:pointer-events-none"
        ),
        "arrow_prev": "left-2",
        "arrow_next": "right-2",
        "dots": "flex items-center justify-center gap-2",
        "dot": (
            "rounded-full cursor-pointer bg-text/20 "
            "transition-[width,background-color] duration-200 ease-out "
            "focus-visible:outline-none focus-visible:ring-2 "
            "focus-visible:ring-offset-2 "
            "focus-visible:ring-offset-background "
            "focus-visible:ring-(--bz-focus) "
            # The active dot LENGTHENS as well as taking a tint: on a
            # screen where colour comes across badly (brightness, colour
            # blindness), the shape stays readable.
            "data-[selected=true]:bg-(--bz-solid)"
        ),
    },
    # Same scale as Flex / Grid, on purpose: the spacing between two
    # slides is the same design gesture as between two cells, and a
    # `gap="md"` must mean the same thing everywhere.
    "gaps": {
        "none": "gap-0",
        "xs": "gap-1",
        "sm": "gap-2",
        "md": "gap-4",
        "lg": "gap-6",
        "xl": "gap-8",
    },
    # The classes ``_dots_hidden_class`` returns PREFIXED by a
    # breakpoint (``md:hidden``). In the theme and not hard-coded in the
    # component: it is what makes them visible to the safelist, which
    # closes this table over the five breakpoints. Hard-coded, the class
    # existed literally nowhere — except ``md:hidden``, present by pure
    # chance in a docstring, which was enough to fool
    # ``test_emitted_classes_exist_in_source``.
    "responsive": {
        DOTS_HIDDEN: "hidden",
    },
    "sizes": {
        "xs": {
            "arrow": "w-7 h-7",
            "arrow_icon": "xs",
            "dot": "h-1 w-1 data-[selected=true]:w-4",
        },
        "sm": {
            "arrow": "w-8 h-8",
            "arrow_icon": "xs",
            "dot": "h-1.5 w-1.5 data-[selected=true]:w-5",
        },
        "md": {
            "arrow": "w-10 h-10",
            "arrow_icon": "sm",
            "dot": "h-2 w-2 data-[selected=true]:w-6",
        },
        "lg": {
            "arrow": "w-12 h-12",
            "arrow_icon": "md",
            "dot": "h-2.5 w-2.5 data-[selected=true]:w-8",
        },
        "xl": {
            "arrow": "w-14 h-14",
            "arrow_icon": "lg",
            "dot": "h-3 w-3 data-[selected=true]:w-10",
        },
    },
}
