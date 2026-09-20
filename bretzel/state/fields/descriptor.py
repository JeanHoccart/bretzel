"""``Field`` descriptor — the storage / access primitive for typed state.

Every typed attribute on a :class:`~bretzel.state.base.State` subclass is
backed by a :class:`Field` instance. The descriptor's two jobs :

1. Read / write the value on the host instance, with no extra ceremony at
   the call site (``cart.coupon`` reads, ``cart.coupon = "X"`` writes).
2. Hook the framework's :class:`~bretzel.core.tracking.DependencyTracker`
   into every read and write, so ``@computed`` / re-render observers see
   the right dependency graph.

The metaclass in :mod:`bretzel.state.base` is responsible for detecting
plain class-level annotations and wrapping them in ``Field`` automatically.
Users only need :func:`field` for non-trivial defaults (``default_factory``
mainly).
"""

from __future__ import annotations

import json
import types
from collections.abc import Callable
from typing import Any, Final, Union, get_args, get_origin

from bretzel.core.tracking import TRACKER
from bretzel.state.types import decode_value

# ───────────────────────────────────────────────────────────────────────────
# Sentinel — distinguishable from any real ``default`` (including ``None``)
# ───────────────────────────────────────────────────────────────────────────


class _Missing:
    __slots__ = ()

    def __repr__(self) -> str:
        return "MISSING"


MISSING: Final[Any] = _Missing()


# ───────────────────────────────────────────────────────────────────────────
# Form-data coercion
# ───────────────────────────────────────────────────────────────────────────

# Strings the dispatcher + plain HTML forms can plausibly send for a
# bool field. Anything outside this set raises so we don't silently
# turn "maybe" into True/False.
_TRUE_STRINGS = frozenset({"true", "1", "on", "yes"})
_FALSE_STRINGS = frozenset({"false", "0", "off", "no", ""})
_BOOL_STRINGS_HINT = repr(sorted(_TRUE_STRINGS | _FALSE_STRINGS))

_SCALAR_TYPES: Final[tuple[type, ...]] = (bool, int, float)

#: The declared types with NOTHING to decode — no business codec, no
#: enumeration. They cover nearly every field, hence the fast exit in
#: :meth:`Field.__set__`.
_NOTHING_TO_DECODE: Final[frozenset[Any]] = frozenset(
    {str, int, float, bool, None}
)

#: The containers a field may declare and a control serialises to JSON.
#: ``tuple`` is NOT there: ``json.loads`` never produces a tuple, so
#: announcing it would make everything coming from the form raise.
_COMPOSITE_TYPES: Final[tuple[type, ...]] = (list, dict)

#: The ways two concurrent writes combine. ``None`` — absent from here —
#: means "replace", and that is the default: for a CHOICE (a page, a
#: sort), the last writer is right.
MERGES: Final[tuple[str, ...]] = ("add",)


def _resolve_scalar_target(type_: Any) -> type | None:
    """Return the scalar type to coerce *into*, or ``None`` if N/A.

    Only two annotation shapes coerce :

    - Plain scalar : ``flag: bool`` → ``bool``.
    - Nullable scalar : ``flag: bool | None`` / ``Optional[bool]`` →
      ``bool``. We unwrap only when ``None`` is the *only* extra arg so
      ambiguous unions like ``int | str`` stay untouched (the form
      string is a legitimate value for the ``str`` branch).
    """
    if type_ in _SCALAR_TYPES:
        return type_  # type: ignore[no-any-return]
    origin = get_origin(type_)
    if origin is Union or origin is types.UnionType:
        args = get_args(type_)
        non_none = [a for a in args if a is not type(None)]
        if len(non_none) == 1 and non_none[0] in _SCALAR_TYPES:
            return non_none[0]  # type: ignore[no-any-return]
    return None


class _SkipAssignment:
    """Sentinel returned by :func:`_coerce_scalar` to tell
    :meth:`Field.__set__` to no-op on this write. Used when a form
    sends an empty string for a typed-non-str field — semantically,
    "the user didn't enter a value", which should leave the current
    state field untouched rather than blowing up with a coercion
    error or silently storing garbage."""


_SKIP_ASSIGNMENT: _SkipAssignment = _SkipAssignment()


def _resolve_container_target(type_: Any) -> type | None:
    """``list`` / ``dict``, including PARAMETERISED and nullable. Else ``None``.

    ``list[str]`` is not ``list``: ``type_ in (list, dict)`` is false, and
    yet it is the most common annotation — the one ``state.md`` gives as
    an example (``tags: list[str] = field(default_factory=list)``).
    Without this resolution, decoding only applied to bare annotations and
    let through the form everyone writes. Found while re-reading the fix,
    not while writing it.

    Same caution as :func:`_resolve_scalar_target` about unions: we only
    unwrap when ``None`` is the single other member.
    """
    if type_ in _COMPOSITE_TYPES:
        return type_  # type: ignore[no-any-return]
    origin = get_origin(type_)
    if origin in _COMPOSITE_TYPES:
        return origin  # type: ignore[no-any-return]
    if origin is Union or origin is types.UnionType:
        non_none = [a for a in get_args(type_) if a is not type(None)]
        if len(non_none) == 1:
            return _resolve_container_target(non_none[0])
    return None


def _coerce_composite(value: Any, type_: Any) -> Any:
    """Decode the JSON a COMPOSITE-valued control drops in the form.

    Six components carry a value that is not a scalar — a multiple
    selection (``toggle_group`` / ``select`` / ``combobox``), two bounds
    (``date_range_picker``, ``slider(range=True)``), a split
    (``resizable``). No `<input>` carries anything but a string, so they
    all serialise with ``JSON.stringify`` into a hidden field.

    Without this decoding, a ``list`` field received the STRING
    ``'["a","b"]'`` and stored it as-is. The next render did ``list(...)``
    on it and displayed fourteen characters; the mush was re-posted, and
    it **survived the reload**. No error anywhere — exactly the failure
    mode scalar coercion exists to remove on ``bool``/``int``, applied one
    notch higher.

    Measured on 2026-08-19 on the CRM's Settings screen.

    Rules:

    - empty string → empty container. "Nothing selected" is a value the
      user chose, not an absence of input — skipping it (as ``""`` does on
      an ``int``) would make a multi-select impossible to EMPTY, the exact
      twin of the unticked-checkbox bug;
    - a string that **looks like** a container (``[…]`` / ``{…}``) is
      decoded, and malformed JSON raises ``ValueError`` there — so a field
      message, not a silence;
    - **everything else passes THROUGH**, and this clause is the most
      important of the three. The ``ClientState`` store does not travel as
      JSON: htmx serialises an array **element by element**
      (``formDataFromObject``: ``obj[key].forEach(v => append(key, v))``),
      so a ``list`` field of a ``ClientState`` receives ``"change"``, not
      ``'["change"]'``. A first version of this decoding raised on that,
      and since ``State._apply_fields`` has no guard, **every action on a
      page carrying such a state returned 500**. Six playground states
      were affected, and the full suite was green: no gate posts a client
      store. Found by re-reading, not by a test.
    """
    container = _resolve_container_target(type_)
    if not isinstance(value, str) or container is None:
        return value
    type_ = container
    text = value.strip()
    if not text:
        return type_()
    if not text.startswith(("[", "{")):
        # Not a serialised container — cf. clause 3 of the docstring.
        return value
    try:
        decoded = json.loads(text)
    except ValueError as exc:
        raise ValueError(
            f"Cannot read {value!r} as JSON for a field "
            f"{type_.__name__} : {exc}."
        ) from exc
    if not isinstance(decoded, type_):
        raise ValueError(
            f"{value!r} decodes to {type(decoded).__name__}, not to "
            f"{type_.__name__}."
        )
    return decoded


def _coerce_scalar(value: Any, type_: Any) -> Any:
    """Coerce string form-data values to a field's declared scalar type.

    Form submissions arrive as strings ; without this, handlers would
    need per-field ``if value in ("true", "false")`` ladders before
    ``setattr(state, key, value)``. Only ``str → bool|int|float`` is
    performed — non-string values and non-scalar fields pass through.

    Empty string for a typed (non-str) field returns the
    :data:`_SKIP_ASSIGNMENT` sentinel : an HTML form sends ``""`` for
    an unfilled ``type="number"`` input (or similar), which the
    handler should treat as "no value provided" rather than a
    coercion error. The descriptor catches the sentinel and skips
    the assignment, leaving the field at its current value.

    Raises :class:`ValueError` on malformed *non-empty* input so bad
    data still surfaces loudly instead of landing a nonsensical
    value in state.
    """
    if not isinstance(value, str) or type_ is None:
        return value
    target = _resolve_scalar_target(type_)
    # ``int`` / ``float`` fields : empty form value (typical HTML
    # ``type="number"`` input erased by the user) → tell the
    # descriptor to skip the assignment. Without this the dispatch
    # would 500 on ``float("")`` / ``int("")``. ``str`` and ``bool``
    # keep their existing handling : "" is a valid str, and bool's
    # legacy ``_FALSE_STRINGS`` includes "" → False.
    if value == "" and target in (int, float):
        return _SKIP_ASSIGNMENT
    if target is bool:
        v = value.strip().lower()
        if v in _TRUE_STRINGS:
            return True
        if v in _FALSE_STRINGS:
            return False
        raise ValueError(
            f"Cannot coerce {value!r} to bool — expected one of "
            f"{_BOOL_STRINGS_HINT}."
        )
    if target is int:
        return int(value)  # int() already strips whitespace ; ValueError on garbage
    if target is float:
        return float(value)
    return value


# ───────────────────────────────────────────────────────────────────────────
# Descriptor
# ───────────────────────────────────────────────────────────────────────────


class Field:
    """Per-attribute descriptor.

    Instances are configured with a default (value or factory) and an
    optional ``type_`` annotation captured at class-build time. The actual
    name is filled in by :py:meth:`__set_name__` when the descriptor is
    assigned to a class attribute.

    Storage layout : the value is kept on the host instance under the
    private key ``f"_field_{name}"``. We avoid name mangling and never
    shadow the public attribute (which is the descriptor itself).
    """

    __slots__ = (
        "_storage_key", "default", "default_factory", "merge", "name",
        "type_", "url",
    )

    def __init__(
        self,
        *,
        default: Any = MISSING,
        default_factory: Callable[[], Any] | None = None,
        type_: type | None = None,
        url: str | None = None,
        merge: str | None = None,
    ) -> None:
        if default is not MISSING and default_factory is not None:
            raise ValueError(
                "Field cannot have both a 'default' and a 'default_factory'."
            )
        self.default = default
        self.default_factory = default_factory
        self.type_: type | None = type_
        #: The name this field carries in the URL — ``field(url="sort")``.
        #: It DECLARES the name; it is not enough to make the field
        #: addressable (``addressable=True`` on the class is what lights
        #: it up), because what is in a URL is PUBLIC and must never be
        #: obtained by accident. Cf. :mod:`bretzel.state.url`.
        self.url: str | None = url
        #: How two concurrent writes combine. ``None`` replaces — the
        #: last writer wins. ``"add"`` sums: the commit sends the DELTA,
        #: and the store applies it without reading, so two concurrent
        #: requests both count.
        self.merge: str | None = merge
        self.name: str = ""  # populated by __set_name__
        self._storage_key: str = ""

    # ── Descriptor protocol ─────────────────────────────────────────────

    def __set_name__(self, owner: type, name: str) -> None:
        self.name = name
        self._storage_key = f"_field_{name}"

    def __get__(self, instance: object | None, owner: type | None = None) -> Any:
        if instance is None:
            return self  # class-level access returns the descriptor itself
        TRACKER.track_access(instance, self.name)
        try:
            return instance.__dict__[self._storage_key]
        except KeyError:
            return self._resolve_default(instance)

    def __set__(self, instance: object, value: Any) -> None:
        cls = type(instance)
        validators_map: dict[str | None, list[Any]] = getattr(cls, "__validators__", {})

        # Coerce form-data strings before anything else sees them, so
        # validators receive the declared type and handlers can write
        # ``setattr(state, key, value)`` for bool/int/float fields
        # without per-field ladders.
        value = _coerce_scalar(value, self.type_)
        # …then the containers: a multiple selection, a date range, a
        # panel split all arrive as JSON in a hidden field.
        value = _coerce_composite(value, self.type_)
        # …then the business types. One gesture for TWO paths: reading
        # back from the store (where a ``date`` came back as
        # ``"2026-03-04"``) and writing a form (where it arrives as a
        # string too). Handling them separately would have left the
        # second one silent — and it was: a field typed ``date`` kept the
        # ``str`` with nothing saying so.
        # Fast exit: 99 % of fields are ``str``/``int``/``bool``, and
        # ``decode_value`` cost them four calls to do nothing — measured
        # on 2026-09-06, +16 % on every field write. The declared type
        # never changes after the class is built, so this test is the
        # same on every write.
        if self.type_ not in _NOTHING_TO_DECODE:
            value = decode_value(self.type_, value)

        # ``_SKIP_ASSIGNMENT`` sentinel : the coercer detected an
        # empty form-data value targeting a typed-non-str field
        # (e.g. ``type="number"`` input erased by the user). Skip
        # the write entirely so the current value is preserved and
        # no validator runs on a placeholder. This is what every
        # form handler ``server_changed(**kwargs)`` expects when
        # a numeric input is emptied — without this, the dispatch
        # would 500 on a ``float("")`` ValueError.
        if isinstance(value, _SkipAssignment):
            return

        # 1. Single-field validators in declaration order. Each may transform
        #    or reject ; the chained return value is what gets stored.
        for v in validators_map.get(self.name, ()):
            value = v.fn(instance, value)

        # 2. Capture previous state for rollback if a whole-instance
        #    validator rejects after we've written.
        had_previous = self._storage_key in instance.__dict__
        previous: Any = instance.__dict__.get(self._storage_key)

        instance.__dict__[self._storage_key] = value
        if hasattr(instance, "_dirty"):
            instance._dirty = True  # type: ignore[attr-defined]

        # 3. Whole-instance validators (multi-field invariants).
        try:
            for v in validators_map.get(None, ()):
                v.fn(instance)
        except Exception:
            # Rollback — restore prior storage exactly as it was.
            if had_previous:
                instance.__dict__[self._storage_key] = previous
            else:
                instance.__dict__.pop(self._storage_key, None)
            raise

        # 4. Notify only after the mutation has been validated end-to-end.
        TRACKER.notify_change(instance, self.name)

    # ── Helpers ─────────────────────────────────────────────────────────

    def _resolve_default(self, instance: object) -> Any:
        """Return the field's default for ``instance``.

        With ``default_factory`` we materialise the value once and cache
        it on the instance, so each instance gets its own object — the
        mutable-default trap that plain Python defaults are subject to.
        """
        if self.default_factory is not None:
            value = self.default_factory()
            instance.__dict__[self._storage_key] = value
            return value
        if self.default is not MISSING:
            return self.default
        raise AttributeError(
            f"Field {self.name!r} has no value and no default."
        )

    def has_value(self, instance: object) -> bool:
        """``True`` iff ``instance`` has an explicitly stored value for this
        field (defaults aren't materialised by this check)."""
        return self._storage_key in instance.__dict__

    def __repr__(self) -> str:
        parts = [f"name={self.name!r}"]
        if self.default is not MISSING:
            parts.append(f"default={self.default!r}")
        if self.default_factory is not None:
            parts.append(f"default_factory={self.default_factory!r}")
        if self.type_ is not None:
            parts.append(f"type_={self.type_!r}")
        return f"Field({', '.join(parts)})"


# ───────────────────────────────────────────────────────────────────────────
# Public sugar
# ───────────────────────────────────────────────────────────────────────────


def field(
    *,
    default: Any = MISSING,
    default_factory: Callable[[], Any] | None = None,
    url: str | None = None,
    merge: str | None = None,
) -> Any:
    """Declare a typed state field."""
    if isinstance(default, list | dict | set):
        # The guard MOVED here on 2026-09-05, together with the
        # obligation to go through ``field()``: it used to live in the
        # metaclass, on the bare-default path, which no longer exists.
        # Without that move ``field(default=[])`` passed — the literal is
        # then SHARED by every instance, and mutating one mutates the
        # others.
        raise ValueError(
            f"field(default={default!r}): a mutable literal would be "
            f"shared by every instance of the state. Write "
            f"`field(default_factory={type(default).__name__})`, which "
            f"builds one per instance."
        )
    if default is not MISSING and default_factory is not None:
        raise ValueError(
            "field() takes `default` OR `default_factory`, not both."
        )
    if merge is not None and merge not in MERGES:
        raise ValueError(
            f"field(merge={merge!r}): accepted values {MERGES}, or "
            f"``None`` to replace (the default)."
        )
    return Field(
        default=default,
        default_factory=default_factory,
        url=url,
        merge=merge,
    )
