"""Kwargs splitting + attribute-name normalisation.

Components accept a wild kwargs surface: reactive props, named slots,
event handlers, raw HTML attrs (including ``aria_*`` / ``data_*`` /
``role`` / …), raw pass-through attrs (**``hx-`` only** — ``:`` / ``@`` /
``x-`` RAISE since 2026-07-30, cf. ``reject_dead_alpine_attr``), and
a few reserved framework keywords (``classes``, ``slots``, ``key``…).

This module is the dispatcher: :func:`split_kwargs` carves a single
``**kwargs`` dict into five buckets that the :class:`Component`
constructor consumes one by one.

"""

from __future__ import annotations

import re
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

# ── The Alpine prefixes, dead since V3 ───────────────────────────────────
# This tuple used to be ``(":", "@", "x-", "hx-")``. Commit 10e34c2e
# (2026-07-03) renamed ``_RAW_ALPINE_PREFIXES`` → ``_PASSTHROUGH_PREFIXES``
# announcing "Pure behaviour-neutral rename […] no logic touched": the NAME
# was de-Alpined, the VALUE was not.
#
# Measured on 2026-07-29: the directive engine only scans ``bz-attr:`` and
# ``bz-on:`` (``02_directives.js``, ``startsWith`` — zero occurrences of
# ``x-`` / ``@`` / ``:`` as an attribute prefix). A ``ui.card(**{"@click":
# "alert(1)", "x-show": "open"})`` therefore went out into the DOM, valid,
# and NOBODY ever looked at it: zero errors, zero warnings, zero effect.
#
# ⚠️ Removing the prefix from the list is NOT enough to close the failure
# mode: ``normalize_attr_name`` returns as-is any name containing
# ``-``/``:``/``@``, so the ``raw_html`` catch-all would emit exactly the
# same attribute. It is the LOUD REFUSAL below that is the fix; the tuple
# is only vocabulary.
_DEAD_ALPINE_PREFIXES: tuple[str, ...] = (":", "@", "x-")

# ── The raw HTML escape hatch, now DECLARED ──────────────────────────────
#
# Until 2026-08-16, bucket 5 was a mute catch-all: **every** unknown kwarg
# went out into the DOM as an inert attribute. It was the only one of the
# five buckets to refuse nothing — an unknown event raises, an unknown slot
# raises, an Alpine directive raises. The guard existed, it had simply
# never been set here.
#
# What it cost: 44 dead kwargs measured over ``examples/`` on 2026-08-01,
# including ``ui.input(label=…)`` on 22 sites rendering
# ``<input label="…">`` — no label displayed, no error, nothing to see in
# the HTML.
#
# ⚠️ **The refusal is NOT "refuse the unknown".** Measured at runtime over
# the 14 685 tests (bucket 5 instrumented): 17 distinct kwargs went
# through it, and the overwhelming majority were LEGITIMATE —
#
#   34 ``aria_label``, 6 ``class_``, 6 ``bz-*`` directives, 4 ``data_*``,
#   1 ``role``… and five genuinely dead ones (``clearable``, ``options``,
#   ``href``, ``value``, ``foo``), all in ``tests/``.
#
# Refusing outright would have broken 51 correct uses to catch 5 faults.
# The fix is therefore to make the escape hatch **explicit**: those
# families pass, everything else raises. An AST scan would not have seen
# it — it missed ``class_`` and the ``bz-*``, which arrive through
# helpers.
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
        # ⚠️ That is this refusal's honest limit: an HTML attribute's
        # validity depends on the RENDERED TAG, which ``split_kwargs``
        # does not know — ``tag=`` is removed by the constructor before
        # reaching here. So ``ui.button(href=…)`` WITHOUT ``tag="a"``
        # still passes and stays inert. Closing it would require
        # validating attribute against tag, that is to say embedding an
        # HTML table: another project. `bretzel check` does see it, since
        # it reads the call site.
        "href",
        "target",
        "rel",
        "download",
    }
)


def is_declared_raw_attr(python_name: str) -> bool:
    """``True`` when the kwarg is a **declared** raw HTML escape hatch."""
    return python_name in _RAW_HTML_NAMES or python_name.startswith(_RAW_HTML_PREFIXES)


class ComponentDefinitionError(TypeError):
    """Raised at class creation time when a component is malformed
    (e.g. ``EVENTS`` lists an event with no matching ``on_<event>``
    parameter in ``__init__``)."""


class ComponentUsageError(TypeError):
    """Raised at instantiation time when the user mis-uses a component
    (unknown slot, event handler for an event that isn't supported)."""


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
    # generator cost 5 Python iterations per attribute: profiled on a
    # render of /tabs, 9 951 calls produced 49 755 iterations there.
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

    for key, value in kwargs.items():
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


def _looks_like_component(value: Any) -> bool:
    """``True`` if ``value`` quacks like a :class:`Component` instance.

    Avoiding a direct import of :class:`Component` keeps this module's
    dependency graph minimal — structural detection on a few telltale
    attributes is enough for the slot-misuse guard.
    """
    return all(hasattr(value, attr) for attr in ("render", "id", "_reactive_values"))
