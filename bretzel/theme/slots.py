"""Pure helpers for component-theme slot resolution and override merging.

Component themes are plain dicts of the shape ::

    {
        "slots":    {"root": "...", "icon": "..."},
        "variants": {"solid": "...", "outline": "..."},
        "sizes":    {"sm": "...", "md": "..."},
    }

The values are **complete** Tailwind class strings. They have been since
2026-08-30: until then they carried ``{bg_color}`` / ``{fg_color}``
holes, filled at render time against the component's ``color=``. That
mechanism was dropped with phase 5 of the colour-token project — themes
now read STEPS (``bg-(--bz-bg)``), and it is the bridge class set on the
root that says which colour it is (cf. :mod:`bretzel.theme.bridges`).

What the removal deleted, and why it was the right moment:
``resolve_slot``, ``resolve_slot_or_keyword``, ``PLACEHOLDER_NAMES`` and
``SHAPE_TOKEN_RE``. A hole is **not a class**: the compiler cannot see
it, so its CLOSURE had to be computed — every shape × every colour,
3 791 classes, 80 % of ``style.css``. A step is a complete class.

This module now exposes:

- :func:`merge_component_themes`: non-mutating deep merge of the user's
  overrides onto a base theme.
- :func:`validate_component_overrides`: the refusal of an unknown key.

Both are pure (no I/O, no contextvars), so they can be measured and
reasoned about in isolation.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from bretzel.theme.palette import Palette, ThemeError

#: The colour names that are NEITHER a semantic slot NOR a palette
#: entry, and which we accept anyway because they name a real CSS
#: colour. Today there is one: ``current`` → ``currentColor``.
#:
#: This set is read in TWO places that must agree — the BRIDGE generator
#: (``theme/bridges.py``, which decides which bridge classes exist in the
#: CSS) and the base layer's refusal
#: (``components/base/_wiring._refuse_unknown_color``, which decides
#: which names the render may emit). Making them read the SAME constant
#: is what forbids a colour from being emitted without a bridge: what
#: has no rule here is refused there.
#:
#: ⚠️ Only add a name here if it designates a valid CSS colour that the
#: twelve step formulas can start from. A BRAND colour goes in the
#: palette (``Theme(palette={...})``), not here — it gets its bridge
#: there on its own.
COLOR_KEYWORDS: frozenset[str] = frozenset({"current"})


def merge_component_themes(
    base: dict[str, Any],
    override: dict[str, Any],
) -> dict[str, Any]:
    """Deep-merge ``override`` on top of ``base`` — non-mutating.

    Recursion rule : at every depth, dicts are merged key-by-key ;
    anything else (string / list / int / None) is replaced wholesale
    by the override value.

    Inputs are never mutated — both ``base`` and ``override`` come
    out unchanged. The returned tree is a fresh structure so callers
    can mutate it freely.

    Example ::

        base = {
            "slots":    {"root": "...", "icon": "..."},
            "variants": {"solid": "...", "outline": "..."},
            "sizes":    {"sm": "...", "md": "..."},
        }
        override = {"slots": {"root": "rounded-full ..."}}

        merge_component_themes(base, override) == {
            "slots":    {"root": "rounded-full ...", "icon": "..."},
            "variants": {"solid": "...", "outline": "..."},
            "sizes":    {"sm": "...", "md": "..."},
        }
    """
    if not isinstance(base, dict) or not isinstance(override, dict):
        # Caller passed something weird — treat override as the winner.
        return _deep_copy(override) if override is not None else _deep_copy(base)

    out: dict[str, Any] = {}
    keys = list(base.keys())
    for k in override:
        if k not in keys:
            keys.append(k)

    for key in keys:
        if key in base and key in override:
            base_v = base[key]
            over_v = override[key]
            if isinstance(base_v, dict) and isinstance(over_v, dict):
                out[key] = merge_component_themes(base_v, over_v)
            else:
                out[key] = _deep_copy(over_v)
        elif key in override:
            out[key] = _deep_copy(override[key])
        else:
            out[key] = _deep_copy(base[key])
    return out


def _deep_copy(value: Any) -> Any:
    """Tiny recursive copy.

    We avoid :func:`copy.deepcopy` because the only mutable structures
    we expect (dict / list) are simple, and bringing in ``copy``
    adds an import for no value.
    """
    if isinstance(value, dict):
        return {k: _deep_copy(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_deep_copy(v) for v in value]
    # Primitives + tuples + frozensets are already immutable.
    return value


# ───────────────────────────────────────────────────────────────────────────
# Validation of component overrides
# ───────────────────────────────────────────────────────────────────────────


#: The only group whose KEYS are closed. Elsewhere — ``variants``,
#: ``sizes``, ``paddings``… — a new key EXTENDS the theme, and that is
#: the recommended path for deviating from the shipped theme: closing it
#: would condemn the only clean way out. A slot, by contrast, is composed
#: by the component's code (``compose_class("root")``): a name it does
#: not know is dead by construction, and nothing in the app can wake it.
CLOSED_GROUP: str = "slots"


def validate_component_overrides(
    components: Mapping[str, Any],
    vocabulary: Mapping[str, Mapping[str, frozenset[str]]],
) -> None:
    """Raise when an override names something nothing will read.

    ``vocabulary`` is **injected**: the ``theme`` layer may not import
    ``components`` (the ``base-independent-of-app`` contract in
    ``.importlinter``), so it cannot obtain it itself. Same arrangement
    as ``color_shapes`` in ``generate_theme_css_full``, and for the same
    reason.

    An accepted consequence, worth knowing:
    ``Theme(components={"crad": …})`` does **not** raise at construction
    — a ``Theme`` stays constructible without the components layer, which
    is what makes it testable on its own. The raise happens at **app
    startup**, called from ``server.lifecycle``, before anything else is
    mounted. ``Theme(semantic=…)``, on the other hand, raises
    immediately: its 11 slots live in the same layer.

    What is refused, in the order it is met:

    1. a **component key** no ``THEME_KEY`` carries;
    2. a **group** that component does not have;
    3. a ``slots`` key that component never composes.
    """
    for name, override in components.items():
        groups = vocabulary.get(name)
        if groups is None:
            raise ThemeError(
                f"Theme(components={{{name!r}: …}}): no component has "
                f"this theme key. The key is `THEME_KEY`, not always the "
                f"`ui.*` name — `sidebar_section` is written under "
                f"`'sidebar'`. `bretzel describe <name>` gives it."
            )
        if not isinstance(override, Mapping):
            continue
        for group, entries in override.items():
            if group not in groups:
                raise ThemeError(
                    f"Theme(components={{{name!r}: {{{group!r}: …}}}}) : "
                    f"`{name}` has no `{group}` group. Its groups: "
                    f"{', '.join(sorted(groups)) or '(aucun)'}."
                )
            if group != CLOSED_GROUP or not isinstance(entries, Mapping):
                continue
            unknown = sorted(set(entries) - set(groups[group]))
            if unknown:
                raise ThemeError(
                    f"Theme(components={{{name!r}: {{'slots': …}}}}) : "
                    f"`{name}` ne compose aucun slot {unknown}. Ses slots : "
                    f"{', '.join(sorted(groups[group])) or '(none)'}. A "
                    f"slot is composed by the component's code, so a name "
                    f"it does not know is dead: nothing in the app can "
                    f"wake it."
                )
