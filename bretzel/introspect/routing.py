"""Kwarg routing — derived from the base layer, never copied.

**Why this section exists, and why it is generated.**
``kwarg-routing.md`` carried a hand-written table describing
``split_kwargs``'s five buckets. On 2026-08-16, it contained **three
false claims**: the Alpine prefixes announced as "passthrough" (false
since 2026-07-30, so two and a half weeks), bucket 6 called "catch-all"
(closed that very day), and a warning claiming ``bz-*`` does not go
through it (measured: six do).

Three documentation gates already existed and none of them could see
those: they check paths, symbols, inventories — **decidable** things.
"Does this paragraph still describe the behaviour?" is not.

Three gate candidates were measured and then **set aside**:

- a gate on the constants cited with their value → a population of 3, and
  three false positives out of three (quotes, placeholders);
- extending the Alpine vocabulary gate to the funnel → ~60 exceptions to
  write, nearly all of them legitimate narrative (``traps.md`` TELLS
  stories);
- a freshness gate by git co-change → 9 docs out of 11 permanently
  "behind". A signal that is always on is not a signal.

What remains, and works: **not writing the decidable part**. A table
enumerating constants does not have to be copied — it reads itself. The
prose keeps what does not derive: the *why*.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Bucket:
    """One ``split_kwargs`` bucket, with what falls into it."""

    rank: int
    name: str
    accepts: tuple[str, ...]
    outcome: str


def describe_kwarg_routing() -> tuple[Bucket, ...]:
    """The buckets, read from the base layer's constants."""
    from bretzel.components.base.attrs import (
        _DEAD_ALPINE_PREFIXES,
        _PASSTHROUGH_PREFIXES,
        _RAW_HTML_NAMES,
        _RAW_HTML_PREFIXES,
    )
    from bretzel.components.base.component import RESERVED_KWARGS

    star = tuple(f"{p}*" for p in _PASSTHROUGH_PREFIXES)
    dead = tuple(f"{p}*" for p in _DEAD_ALPINE_PREFIXES)
    declared = tuple(f"{p}*" for p in _RAW_HTML_PREFIXES) + tuple(sorted(_RAW_HTML_NAMES))

    return (
        Bucket(0, "reserved (removed before split_kwargs)", RESERVED_KWARGS, "handled individually"),
        Bucket(1, "Alpine directive — unsupported since V3", dead, "ComponentUsageError"),
        Bucket(2, "passthrough verbatim", star, "passthrough"),
        Bucket(
            3,
            "reactive property declared on the class",
            ("<__reactive_props__>",),
            "_reactive_values",
        ),
        Bucket(4, "named slot", ("<NAMED_SLOTS>",), "_slot_components"),
        Bucket(5, "event handler", ("on_<EVENTS>",), "_event_attrs"),
        Bucket(6, "DECLARED raw HTML escape hatch", declared, "_raw_attrs (normalized name)"),
        Bucket(7, "everything else", ("*",), "ComponentUsageError"),
    )
