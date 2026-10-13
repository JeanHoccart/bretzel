"""Gate : every count a layout prop accepts reaches the production sheet.

Two props take an int and turn it into a class at render : ``ui.grid``'s
``cols=N`` assembles ``grid-cols-N``, ``ui.carousel``'s ``per_view=N``
looks up a slide width computed by a formula. No source file writes
either, so the production compiler only has their rule if the safelist
(the ``@source inline(...)`` directive of the theme entry) names it. In
dev the browser compiler reads the live DOM and every count works.

Measured on 2026-10-07 : ``ui.grid(cols=37)`` rendered 37 columns in dev
and ONE in production, with no error — the safelist stops at twelve, and
both components accepted any int. They now refuse a count outside their
domain (``GRID_COLS``, ``PER_VIEW``); this gate pins the contract from
the OUTSIDE, by behaviour : a count is accepted if and only if every
class it renders, breakpoint prefixes included, is in the safelist.

Checked against the safelist ALONE, not the full source corpus : the
corpus holds prose, and a class written in a docstring would make the
gate pass for the wrong reason (cf. ``test_responsive_classes_are_safelisted``,
where ``md:hidden`` in a docstring hid a hole).
"""

from __future__ import annotations

import re

import pytest

from bretzel.components.base.attrs import ComponentUsageError
from bretzel.components.base.testing import render_isolated
from bretzel.components.layout.carousel import Carousel
from bretzel.components.layout.grid import Grid
from bretzel.components.primitives.text import Text
from bretzel.core.serialize import serialize
from bretzel.theme import Theme

#: ``(component, prop, prefix of the class the count renders)``.
_COUNT_PROPS = (
    (Grid, "cols", "grid-cols-"),
    (Carousel, "per_view", "basis-"),
)
_IDS = [f"{cls.__name__}.{prop}" for cls, prop, _ in _COUNT_PROPS]

#: Far beyond the safelist : a widened or narrowed domain is seen on
#: both sides.
_PROBED = range(0, 65)

#: The counts both props have always taken. Fewer accepted means the
#: refusal swallowed legitimate values — or the probe stopped building.
_MIN_ACCEPTED = 12

_INLINE = re.compile(r'@source inline\("([^"]*)"\)')
_CLASS = re.compile(r'(?<![\w:-])class="([^"]*)"')


@pytest.fixture(scope="module")
def safelisted() -> frozenset[str]:
    """The tokens of the generated ``@source inline(...)`` directive."""
    from bretzel.components import dynamic_responsive_classes

    css = Theme().generate_css(responsive_classes=dynamic_responsive_classes())
    return frozenset(
        token for block in _INLINE.findall(css) for token in block.split()
    )


def unlisted(classes: str, prefix: str, safelisted: frozenset[str]) -> list[str]:
    """The ``prefix*`` classes of ``classes`` the safelist does not hold."""
    return [
        token for token in classes.split()
        if token.split(":")[-1].startswith(prefix) and token not in safelisted
    ]


def verdict(
    cls: type, prop: str, value: object, prefix: str, safelisted: frozenset[str],
) -> list[str] | None:
    """``None`` if the component refuses ``prop=value``, else its unlisted
    classes. Built with one child : a carousel only sizes its slides."""
    try:
        with render_isolated():
            with cls(**{prop: value}) as node:
                Text("child")
            html = serialize(node.render())
    except ComponentUsageError:
        return None
    return unlisted(" ".join(_CLASS.findall(html)), prefix, safelisted)


def forms(n: int) -> tuple[object, ...]:
    """A count alone, and the same count at a breakpoint."""
    return (n, {"base": 1, "md": n})


@pytest.mark.parametrize(("cls", "prop", "prefix"), _COUNT_PROPS, ids=_IDS)
def test_the_sweep_is_not_vacuous(cls, prop, prefix, safelisted) -> None:
    accepted = [
        n for n in _PROBED
        if verdict(cls, prop, n, prefix, safelisted) is not None
    ]
    assert len(accepted) >= _MIN_ACCEPTED, (
        f"{cls.__name__}({prop}=…) accepts {len(accepted)} count(s) out of "
        f"{len(_PROBED)} probed, floor {_MIN_ACCEPTED} : either the refusal "
        f"swallows legitimate counts, or the probe no longer builds it."
    )


@pytest.mark.parametrize(("cls", "prop", "prefix"), _COUNT_PROPS, ids=_IDS)
def test_an_accepted_count_is_safelisted(cls, prop, prefix, safelisted) -> None:
    offenders = {
        repr(value): missing
        for n in _PROBED
        for value in forms(n)
        if (missing := verdict(cls, prop, value, prefix, safelisted))
    }
    assert not offenders, (
        f"{cls.__name__} accepts {prop}= values whose classes the production "
        f"safelist does not hold — right in dev, broken in production : "
        f"{dict(list(offenders.items())[:3])}. Refuse the count at "
        f"construction, or widen the domain the safelist is built from — "
        f"the two must stay one."
    )


def test_the_detector_still_bites(safelisted) -> None:
    """Both sides : an unlisted count is caught, a listed one is not."""
    assert unlisted("grid gap-4 grid-cols-37 md:grid-cols-37", "grid-cols-",
                    safelisted) == ["grid-cols-37", "md:grid-cols-37"]
    assert unlisted("grid gap-4 grid-cols-3 md:grid-cols-12", "grid-cols-",
                    safelisted) == []
    assert unlisted("shrink-0 basis-full md:basis-1/37", "basis-",
                    safelisted) == ["md:basis-1/37"]
