"""The size scale, and how a ``sizes`` table is read.

Why this module exists
----------------------

The ``xs|sm|md|lg|xl`` scale is the controls' grammar:
``bretzel describe`` announces it as a **closed enum** on Button, Input,
Select, Badge, Avatar, Icon, Spinner, Progress… And yet it was copied
**five times in ``tests/`` and zero times in ``bretzel/``** (measured on
2026-08-16) — ``test_size_enum_is_complete``,
``test_size_reaches_slots``, ``test_sizes_are_distinct``,
``test_playground_demos_the_api``, ``probes/bench_switch``. An enum
declared closed that exists nowhere in the code is not closed: it is a
convention, and a convention can refuse nothing.

⚠️ What the scale is NOT
------------------------

It is not "every value a component accepts". Three families go beyond
it, and that is **intended**:

- ``Text`` and ``Heading`` carry the **typographic** scale (``xs`` to
  ``8xl``, measured) — a heading is not a button's size, and
  ``bretzel describe`` says so: "do not confuse them";
- ``Avatar`` extends to ``2xl`` (portrait visual);
- ``Icon`` likewise.

:data:`SIZE_SCALE` is therefore **the common base**, and it serves two
roles: the minimal set a control's table must cover, and — this is the
second, less obvious use — the **marker** saying whether a table is
indexed by size or by slot.

The two ``sizes`` nestings, and why they must be told apart
-----------------------------------------------------------

Of the catalogue's 44 ``sizes`` tables, **33 are nested**, and two
OPPOSITE nestings coexist ::

    Checkbox    sizes = {"sm": {"root": …, "label": …}}     ← keys = SIZES
    DatePicker  sizes = {"input_field": {"sm": …, "md": …}} ← keys = SLOTS

Structurally indistinguishable: in both cases a dict of dicts. The only
signal available is the **content** of the keys, hence
:func:`size_vocabulary`, which looks at which tier the scale appears in.

Confusing the two is not theoretical: a first version of the
``value-outside-the-table`` lint rule reported
``ui.date_picker(size="sm")``, which is perfectly correct — the component
resolves its sizes itself in its ``render``.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Final

#: The five control steps. **Single source** — everything that needs to
#: know "is this a size name?" composes on it.
SIZE_SCALE: Final[tuple[str, ...]] = ("xs", "sm", "md", "lg", "xl")

_SCALE: Final[frozenset[str]] = frozenset(SIZE_SCALE)


def is_size_keyed(table: Mapping[str, Any]) -> bool:
    """Is the table indexed by SIZE (and not by slot)?

    The test is the intersection with :data:`SIZE_SCALE`, and not "are
    the values strings": ``Checkbox`` is indexed by size AND nested,
    ``Button`` is indexed by size and flat. The shape of the values
    therefore says nothing about the indexing.
    """
    return bool(_SCALE & set(table))


def size_vocabulary(theme: Mapping[str, Any] | None) -> frozenset[str]:
    """The values ``size=`` can take for this component theme.

    Absorbs both nestings:

    - a size-indexed table → its own keys, **whole** (so ``2xl``..``8xl``
      included for ``Text`` / ``Heading`` / ``Avatar``);
    - a slot-indexed table → the union of the second tier's keys that
      carry the scale.

    Returns an **empty** set when there is no table at all — the
    component then consumes ``size=`` otherwise (``radio_group``), and a
    consumer must on no account conclude "no value is valid". Empty means
    "I do not know", not "nothing".
    """
    table = (theme or {}).get("sizes")
    if not isinstance(table, Mapping) or not table:
        return frozenset()
    if is_size_keyed(table):
        return frozenset(table)
    found: set[str] = set()
    for row in table.values():
        if isinstance(row, Mapping) and is_size_keyed(row):
            found |= _SCALE & set(row)
    return frozenset(found)


#: The ``ui.icon`` size that goes with a label of a given size: **the
#: step just above**, on ``Icon``'s scale.
#:
#: Why one step, and not the same size
#: -----------------------------------
#:
#: ``<iconify-icon>`` sizes itself in ``1em`` — its size IS its
#: ``font-size``. At an equal size, a glyph therefore looks smaller than
#: the text: it has no ascender, no descender, nothing to catch the
#: baseline. ``Icon``'s theme already says so for its default
#: (``"md": "text-lg",  # slightly bigger than text for readability``) —
#: this table only generalises that intention to labels that are NOT
#: 16 px.
#:
#: ``Icon``'s default was calibrated against body text (18/16 = 1.125).
#: The items have labels of 12 to 14 px, and using it as-is gave up to
#: 1.50 there (``breadcrumb_item``, measured on 2026-08-18).
#:
#: ``Icon``'s scale has a hole (``sm`` = 14 px then ``md`` = 18 px,
#: nothing at 16): "the step above" is therefore read on ITS table, not
#: on Tailwind's. Five of the eight item components already respected it
#: before the rule was written.
#:
#: ⚠️ An icon size that is NOT one step above must be DECLARED with its
#: reason — ``bottom_bar_item`` goes up to 24 px because it is a touch
#: target, not a line-of-text ornament. Gated by
#: ``tests/consistency/test_icon_follows_its_label.py``.
ICON_SIZE_ABOVE: Final[Mapping[str, str]] = {
    "text-[10px]": "xs",   # 10 px → 12
    "text-xs": "sm",       # 12 px → 14
    "text-sm": "md",       # 14 px → 18
    "text-base": "md",     # 16 px → 18
    "text-lg": "lg",       # 18 px → 24
    "text-xl": "lg",       # 20 px → 24
}


def icon_size_for(label_class: str) -> str | None:
    """The icon size that goes with this label — ``None`` when its text
    class is not in :data:`ICON_SIZE_ABOVE`.

    ``label_class`` is the label's composed class string; we look in it
    for the SIZE ``text-*`` token. The other ``text-*`` (a colour,
    ``text-left``) are not in the table, so they are ignored — which is
    exactly why the table lists the sizes instead of matching a prefix.
    """
    for token in label_class.split():
        size = ICON_SIZE_ABOVE.get(token)
        if size is not None:
            return size
    return None


__all__ = (
    "ICON_SIZE_ABOVE",
    "SIZE_SCALE",
    "icon_size_for",
    "is_size_keyed",
    "size_vocabulary",
)
