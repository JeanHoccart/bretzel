"""The rules — each pure, each enumerable.

A rule has the signature ``check(module) -> list[Finding]``. It knows
neither corpus, nor floor, nor exit code: it reports on ONE module and
returns :class:`~bretzel.lint.report.Finding`.

**The registry is a list, not a plugin system.** The charter rules out a
plugin system before the core stabilises, and a non-enumerable rule set
would stop ``check`` saying what it can verify — which is precisely the
question one asks a tool of this kind.
"""

from __future__ import annotations

from collections.abc import Callable

from bretzel.lint.corpus import Module
from bretzel.lint.report import Finding
from bretzel.lint.rules import (
    badge_by_hand,
    breadcrumb_by_hand,
    dialog_flag,
    forced_classes,
    handler_script,
    handlers,
    injection,
    kwargs,
    lifespan,
    loop_state,
    nested_link,
    nested_page,
    partial_sizes,
    shape,
    shared_counter,
    sizes,
    specificity,
    tailwind,
    theme,
    theme_colors,
    topics,
    transport,
    variant,
)

Rule = Callable[[Module], list[Finding]]

#: The static rules — AST only, **nothing is executed**. That is what
#: makes it safe to run them over a third party's code.
#:
#: The order is that of the **discretion of the failure**, from the most
#: silent to the loudest, because that is the order one wants to read
#: them in: a state built in an `async def` body works in memory and
#: RAISES the day `redis_url` is set — mute too, but with a delayed
#: silence: it is not the code that stays quiet, it is the developer who
#: does not surface the failure; an assembled Tailwind class only breaks
#: in production with identical HTML; an unknown theme name changes
#: NOTHING anywhere (not even in production: there is no attribute to
#: see, no class to look for, the render is the shipped theme's); a value
#: outside the table removes a class and leaves the component on screen,
#: bare — and a theme override that keeps the name while changing the
#: SHAPE does exactly that: the step loses all its tokens and
#: the component renders at its content's size (its other meaning does
#: raise at render time, which places it just after); a cast on a state
#: value removes nothing either and leaves the component displaying the
#: WRONG state, which only a reload fixes; a class duplicating a prop
#: removes none — BOTH are in the HTML, and it is the Tailwind sheet's
#: order that settles it, so even re-reading the classes shows nothing;
#: mixed sizes remove NOTHING either — the page is correct, two
#: neighbouring fields simply do not have the same height, and one has to
#: look at the screen to see it; an unknown kwarg goes out as an inert
#: attribute; a hand-written `hx-` makes a refused request; a
#: non-literal `ui.html` is a choice to make visible; a lambda raises at
#: render time.
STATIC: dict[str, Rule] = {
    loop_state.RULE: loop_state.check,
    shared_counter.RULE: shared_counter.check,
    topics.RULE: topics.check,
    tailwind.RULE: tailwind.check,
    # A colour no theme has (`border-base-300`): no rule in dev nor in
    # production, the property falls back to the text.
    theme_colors.RULE: theme_colors.check,
    theme.RULE: theme.check,
    variant.RULE: variant.check,
    shape.RULE: shape.check,
    nested_page.RULE: nested_page.check,
    lifespan.RULE: lifespan.check,
    specificity.RULE: specificity.check,
    partial_sizes.RULE: partial_sizes.check,
    sizes.RULE: sizes.check,
    nested_link.RULE: nested_link.check,
    # The app idioms: nothing breaks, the app drifts
    # from the framework — a window opened by a round trip, a pill, a
    # forced component, a breadcrumb drawn by hand.
    dialog_flag.RULE: dialog_flag.check,
    badge_by_hand.RULE: badge_by_hand.check,
    forced_classes.RULE: forced_classes.check,
    breadcrumb_by_hand.RULE: breadcrumb_by_hand.check,
    kwargs.RULE: kwargs.check,
    transport.RULE: transport.check,
    injection.RULE: injection.check,
    # A value pasted into a JavaScript on_* handler.
    handler_script.RULE: handler_script.check,
    handlers.RULE: handlers.check,
}

__all__ = ("STATIC", "Rule")
