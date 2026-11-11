"""Kwargs splitting + attribute-name normalisation.

Components accept a wild kwargs surface: reactive props, named slots,
event handlers, raw HTML attrs (including ``aria_*`` / ``data_*`` /
``role`` / …), raw pass-through attrs (**``hx-`` only** — ``:`` / ``@`` /
``x-`` RAISE, cf. ``reject_dead_alpine_attr``), and
a few reserved framework keywords (``classes``, ``slots``, ``key``…).

This module is the dispatcher: :func:`split_kwargs` carves a single
``**kwargs`` dict into five buckets that the :class:`Component`
constructor consumes one by one.

"""

from __future__ import annotations

import re
from functools import cache
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from bretzel.components.base.component import Component


# ``on_<event>`` matches any lowercase event with optional underscores.
EVENT_PATTERN: re.Pattern[str] = re.compile(r"^on_[a-z][a-z0-9_]*$")


# HTMX attrs that pass verbatim. A component has in principle no
# business writing one (cf. CLAUDE.md principle 2: the transport boundary
# is runtime-only), but a few drive the swap engine directly —
# sidebar/navbar for partial nav, notification for OOB toasts, form,
# radio, table.
_PASSTHROUGH_PREFIXES: tuple[str, ...] = ("hx-",)

# ── The dead Alpine prefixes ─────────────────────────────────────────────
# The directive engine only scans ``bz-attr:`` and ``bz-on:``
# (``directives.js``, ``startsWith``). A ``ui.card(**{"@click": "alert(1)",
# "x-show": "open"})`` would go out into the DOM, valid, and NOBODY would
# ever look at it: zero errors, zero warnings, zero effect.
#
# ⚠️ Keeping these prefixes off the pass-through list is NOT enough to close
# the failure mode: ``normalize_attr_name`` returns as-is any name
# containing ``-``/``:``/``@``, so a raw attribute would carry exactly the
# same name. It is the LOUD REFUSAL below that is the fix; the tuple is
# only vocabulary.
_DEAD_ALPINE_PREFIXES: tuple[str, ...] = (":", "@", "x-")

# ── The raw HTML escape hatch, DECLARED ──────────────────────────────────
#
# Bucket 5 refuses, like the other four: an unknown event raises, an
# unknown slot raises, an Alpine directive raises. As a mute catch-all it
# would send every unknown kwarg into the DOM as an inert attribute:
# ``ui.input(label=…)`` would render ``<input label="…">`` — no label
# displayed, no error, nothing to see in the HTML.
#
# ⚠️ **The refusal is NOT "refuse the unknown".** Most of what reaches this
# bucket is LEGITIMATE: ``aria_label``, ``class_``, ``bz-*`` directives,
# ``data_*``, ``role``. Refusing outright would break those correct uses.
# The escape hatch is therefore **explicit**: those families pass,
# everything else raises. An AST scan cannot establish the list — it
# misses ``class_`` and the ``bz-*``, which arrive through helpers.
_RAW_HTML_PREFIXES: tuple[str, ...] = (
    "aria_",
    "aria-",
    "data_",
    "data-",
    # The runtime's vocabulary: ``bz-on:click``, ``bz-attr:placeholder``,
    # ``bz-class``, ``bz-show``. It is the framework's idiom, not an
    # escape hatch — but it does arrive through here when written as a
    # kwarg.
    "bz-",
)

#: The anchor family: attributes that only mean something on an ``<a>``
#: (or an ``<area>``). Admitted as raw kwargs below, and REFUSED at render
#: when the element that carries them is not an anchor
#: (``component._refuse_stray_anchor_attrs``) — the one check that needs
#: the rendered tag, which this module never sees.
ANCHOR_ATTRS: frozenset[str] = frozenset({"href", "target", "rel", "download"})

#: The tags where :data:`ANCHOR_ATTRS` mean something.
ANCHOR_TAGS: frozenset[str] = frozenset({"a", "area"})

#: The EXACT names admitted without a prefix. Two, each with its reason.
_RAW_HTML_NAMES: frozenset[str] = frozenset(
    {
        # The standard Python escape for the ``class`` attribute — the
        # base layer does not pop it (it is not a reserved kwarg), it
        # comes out as ``class=`` and coexists with ``classes=``. Tested
        # by ``test_attr_precedence_is_one_contract``.
        "class_",
        # An ARIA attribute with no ``aria-`` prefix. Refusing it would
        # force writing ``attrs={"role": …}`` for the most common
        # accessibility attribute after ``aria-label``.
        "role",
        # ── The anchor family ────────────────────────────────────────────
        # Unlocked by ``tag="a"``, the universal retag. The real case is
        # the datatable's export: a ``Button`` retagged as an anchor,
        # BECAUSE only an anchor can download, and which must stay
        # visually a button (it lives in a toolbar next to "Clear
        # filters"). Cf. ``datatable.py`` § CSV export.
        #
        # Their validity depends on the RENDERED TAG, which
        # ``split_kwargs`` does not know (``tag=`` is removed before) —
        # so the check lives at render, cf. :data:`ANCHOR_ATTRS`. Without
        # it, ``ui.icon_button(href=…)`` would render ``<button href=…>``,
        # which leads nowhere.
        *ANCHOR_ATTRS,
    }
)


def is_declared_raw_attr(python_name: str) -> bool:
    """``True`` when the kwarg is a **declared** raw HTML escape hatch."""
    return python_name in _RAW_HTML_NAMES or python_name.startswith(_RAW_HTML_PREFIXES)


class ComponentDefinitionError(TypeError):
    """Raised at class creation time when a component is malformed
    (e.g. ``EVENTS`` lists an event with no matching ``on_<event>``
    parameter in ``__init__``)."""


class ComponentUsageError(TypeError, ValueError):
    """The one exception for a component the CALLER mis-uses: a value off
    its table, an unknown slot, an event it does not support, a call it
    cannot honour. It says what to write.

    A ``TypeError`` and a ``ValueError`` both, because it covers both
    faults and an ``except`` written for either still catches it.
    :class:`ComponentDefinitionError` stays for a malformed class."""


# ───────────────────────────────────────────────────────────────────────────
# normalize_attr_name — Python kwargs → HTML attrs
# ───────────────────────────────────────────────────────────────────────────


def normalize_attr_name(python_name: str) -> str:
    """Convert a Python-friendly kwarg name to an HTML attribute name.

    Rules :

    - Names already containing ``-``, ``:``, ``@`` are returned as-is
      (raw pass-through / HTMX attrs that the developer typed deliberately).
    - Trailing underscores (``class_``, ``for_``) are stripped — these
      are the standard Python escapes for HTML keywords that clash
      with Python builtins.
    - Internal underscores convert to dashes (``aria_label`` →
      ``aria-label``, ``data_testid`` → ``data-testid``).
    """
    if not python_name:
        return python_name
    # Three C scans rather than one three-pass generator: 8 241 calls
    # per render of /tabs, so 32 964 Python iterations saved.
    if "-" in python_name or ":" in python_name or "@" in python_name:
        return python_name
    if python_name.endswith("_"):
        python_name = python_name.rstrip("_")
    # ``data_*`` and ``aria_*`` follow the dash convention.
    return python_name.replace("_", "-")


def is_passthrough_attr(python_name: str) -> bool:
    """``True`` when the kwarg is a raw HTMX attribute that should pass
    through to the rendered element verbatim."""
    # ``startswith`` accepts a tuple and loops in C. The equivalent
    # generator would run Python iterations for every attribute of every render.
    return python_name.startswith(_PASSTHROUGH_PREFIXES)


def reject_dead_alpine_attr(owner: str, name: str) -> None:
    """Raise when ``name`` carries an Alpine directive prefix.

    Called on BOTH entry paths of a raw attribute — ``**kwargs`` (through
    :func:`split_kwargs`) and ``attrs={...}`` — because the attribute is
    as inert in one case as in the other. Letting one of the two through
    would make the refusal inconsistent, and that is exactly the kind of
    asymmetry that stops a mechanism being adopted.

    The message points at the ``bz-`` equivalent: that is what turns the
    refusal into help rather than a wall.
    """
    if not name.startswith(_DEAD_ALPINE_PREFIXES):
        return
    if name.startswith("@"):
        suggestion = f"``bz-on:{name[1:]}``"
    elif name.startswith(":"):
        suggestion = f"``bz-attr:{name[1:]}``"
    else:  # ``x-``
        suggestion = f"``bz-{name[2:]}``"
    raise ComponentUsageError(
        f"{owner}({name}=…): ``{name}`` is an Alpine directive, and "
        f"Alpine has not been in Bretzel since V3. The runtime only scans "
        f"``bz-attr:`` and ``bz-on:`` — this attribute would go out into "
        f"the DOM with nothing ever reading it.\n"
        f"  Write {suggestion} instead. To wire the SERVER, pass no "
        f"attribute at all: declare an ``on_<event>=`` handler and the "
        f"base layer emits the signed POST."
    )


# ───────────────────────────────────────────────────────────────────────────
# split_kwargs — the bucket dispatcher
# ───────────────────────────────────────────────────────────────────────────


def split_kwargs(
    cls: type[Component],
    kwargs: dict[str, Any],
) -> tuple[
    dict[str, Any],  # reactive props
    dict[str, Any],  # named slots
    dict[str, Any],  # event handlers (keys keep ``on_`` prefix)
    dict[str, Any],  # raw pass-through / htmx attrs (keys kept verbatim)
    dict[str, Any],  # raw HTML attrs (keys normalised to dash form)
]:
    """Carve ``kwargs`` into the five buckets the :class:`Component`
    constructor consumes.

    Reserved keywords (``classes``, ``style``, ``slots``, ``key``,
    ``id``, ``tag``, ``attrs``, ``visible``, ``tooltip``, ``debounce``,
    ``throttle``) are NOT touched here — the constructor pops them out
    before calling :func:`split_kwargs`.

    Validation :

    - An ``on_<event>`` key whose ``<event>`` is not in ``cls.EVENTS``
      raises :class:`ComponentUsageError`.
    - A slot name not in ``cls.NAMED_SLOTS`` raises
      :class:`ComponentUsageError`.

    The function never mutates ``kwargs`` — callers can iterate over
    the input again if needed.
    """
    reactive_props = getattr(cls, "__reactive_props__", {}) or {}
    declared_events: tuple[str, ...] = getattr(cls, "EVENTS", ())
    named_slots: tuple[str, ...] = getattr(cls, "NAMED_SLOTS", ())

    reactive: dict[str, Any] = {}
    slots: dict[str, Any] = {}
    events: dict[str, Any] = {}
    passthrough: dict[str, Any] = {}
    raw_html: dict[str, Any] = {}

    buckets = {"p": passthrough, "r": reactive, "s": slots, "e": events}
    renamed: dict[str, str] = getattr(cls, "RENAMED_PROPS", {}) or {}
    refused: dict[str, str] = getattr(cls, "REFUSED_PROPS", {}) or {}
    for key, value in kwargs.items():
        # A name the API RULES retired (``components.md`` § *Les six
        # règles*, R6): the refusal gives the new one. Checked first, so
        # an old event name (``on_select``) is caught before the event
        # check speaks of an undeclared event.
        if key in renamed:
            raise ComponentUsageError(
                f"{cls.__name__}({key}=…) was renamed: {renamed[key]}"
            )
        # A name this component deliberately does not take. Without the
        # refusal it would fall through to the raw attrs and render as a
        # dead HTML attribute, in silence.
        if key in refused:
            raise ComponentUsageError(f"{cls.__name__} has no `{key}=`: {refused[key]}")
        known = _known_bucket(cls, key)
        if known is not None:
            buckets[known][key] = value
            continue
        # 0. An Alpine directive — dead since V3, loud refusal.
        reject_dead_alpine_attr(cls.__name__, key)

        # 1. Raw HTMX — verbatim, no kwargs decoding.
        if is_passthrough_attr(key):
            passthrough[key] = value
            continue

        # 2. Reactive prop declared on the class.
        if key in reactive_props:
            reactive[key] = value
            continue

        # 3. Named slot declared by the component author.
        if key in named_slots:
            slots[key] = value
            continue

        # 4. Event handler — must match the declared event list.
        match = EVENT_PATTERN.match(key)
        if match:
            event = key[3:]  # drop ``on_``
            if event not in declared_events:
                raise ComponentUsageError(
                    f"{cls.__name__} does not declare an ``on_{event}`` event "
                    f"(EVENTS = {declared_events!r}). Either add it to the "
                    "class, or go through ``attrs={'bz-on:x': …}`` — an "
                    "``@…`` kwarg now RAISES."
                )
            events[key] = value
            continue

        # 5. Anything else — raw HTML attr. Normalise the name to the
        # dashed form HTML expects.
        #
        # Special guard : a :class:`Component` instance can never be a
        # raw HTML attribute value. If we land here with one, the user
        # almost certainly mistyped a named-slot kwarg (``trailing=icon``
        # vs the declared ``icon_right``). Raise loudly so the typo
        # doesn't silently drop into ``raw_html``.
        if _looks_like_component(value):
            raise ComponentUsageError(
                f"{cls.__name__}({key}=…) received a component instance "
                "but no such named slot is declared "
                f"(NAMED_SLOTS = {named_slots!r}). Either register the slot "
                "on the class or rename the kwarg."
            )
        if not is_declared_raw_attr(key):
            raise ComponentUsageError(
                f"{cls.__name__}({key}=…): this component does not read "
                f"``{key}``, and it is not a declared HTML escape hatch. "
                f"The attribute would have gone out into the DOM with "
                f"nothing reading it — no error, no effect, nothing to see "
                f"in the HTML.\n"
                f"  ``bretzel describe {cls.__name__.lower()}`` lists what "
                f"it accepts.\n"
                f"  If you really want that HTML attribute: "
                f"``attrs={{'{normalize_attr_name(key)}': …}}``. The "
                f"families admitted directly as a kwarg are "
                f"{', '.join(_RAW_HTML_PREFIXES)}* "
                f"et {', '.join(sorted(_RAW_HTML_NAMES))}."
            )
        raw_html[normalize_attr_name(key)] = value

    return reactive, slots, events, passthrough, raw_html


@cache
def _known_bucket(cls: type[Component], key: str) -> str | None:
    """The bucket of a kwarg that needs no look at its value — a
    pass-through, a reactive prop, a slot, a declared event — or ``None``
    for the rest (raw attributes and errors), which take the full path.

    It depends on the class and the name only, both fixed after import,
    and a page builds many components with the same few dozen names, so
    the per-key checks are cached.
    """
    if key.startswith(_DEAD_ALPINE_PREFIXES):
        return None
    if is_passthrough_attr(key):
        return "p"
    if key in (getattr(cls, "__reactive_props__", {}) or {}):
        return "r"
    if key in getattr(cls, "NAMED_SLOTS", ()):
        return "s"
    if EVENT_PATTERN.match(key) and key[3:] in getattr(cls, "EVENTS", ()):
        return "e"
    return None


def _looks_like_component(value: Any) -> bool:
    """``True`` if ``value`` quacks like a :class:`Component` instance.

    Avoiding a direct import of :class:`Component` keeps this module's
    dependency graph minimal — structural detection on a few telltale
    attributes is enough for the slot-misuse guard.
    """
    return all(hasattr(value, attr) for attr in ("render", "id", "_reactive_values"))
