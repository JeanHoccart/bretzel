"""``ServerState`` — typed state living on the server.

Adds the ``scope=`` class kwarg on top of :class:`State` to declare which
of the four scopes (``page`` / ``session`` / ``user`` / ``app``) the
state lives in. The scope is what the registry consults to pick a
backend, an identity, and a TTL; this class itself is just the schema.

The actual identity resolution (session id, hashed user id, …) and TTL
defaults are owned by the registry layer (:mod:`bretzel.state.registry`).

Field-read autoname
-------------------

During a render scope, scalar field reads on a ``ServerState`` return a
str / int / float subclass that **also** carries the source field's
``field_name``. Components opted into ``AUTONAME_FROM`` use that stamp
to derive the form-data ``name=`` HTML attribute, so user code can stay
clean ::

    class Cart(ServerState, scope="session"):
        coupon: str = field(default="")

    ui.input(value=cart.coupon)
    # → renders ``<input name="coupon" value=""/>``; the submit handler
    #   receives ``coupon=…`` as a kwarg, no manual ``name="coupon"``.

The values ``_stamp`` handles carry their source field during the render,
including lists, tuples, dates and booleans. Dictionaries stay raw. An
operation that produces a new value (comparison, conversion, computation)
may lose that provenance: it then no longer guarantees the control is
bound to the server field.

Outside a render scope (action handlers, validators, computed bodies),
field reads return raw values. Only the render layer sees the stamped
form, so persistence and state mutations stay clean.
"""

from __future__ import annotations

import inspect
from datetime import date, datetime
from typing import Any, ClassVar, Final, Literal, Self

from bretzel.state.base import State
from bretzel.state.fields.descriptor import Field
from bretzel.state.scopes.client import _RENDERING

# Tuple form for runtime validation, Literal for static checking.
SCOPES: Final[tuple[str, ...]] = ("page", "session", "user", "app")
ServerScope = Literal["page", "session", "user", "app"]


# ───────────────────────────────────────────────────────────────────────────
# Stamped scalar wrappers
# ───────────────────────────────────────────────────────────────────────────


class _BoundStr(str):
    """``str`` subclass carrying its source field's name + owning instance.

    Created on the fly by :meth:`ServerState.__getattribute__` during a
    render scope so components can read the value, where it came from
    (``field_name``, for autoname) and the owning state instance
    (``owner``, so a ``form_field`` can resolve ``owner.errors[field]``).
    Indistinguishable from a plain ``str`` for any operation that doesn't
    explicitly look at ``type(...) is str``.
    """

    field_name: str
    owner: Any

    def __new__(cls, value: str, field_name: str, owner: Any = None) -> _BoundStr:
        instance = super().__new__(cls, value)
        instance.field_name = field_name
        instance.owner = owner
        return instance


class _BoundInt(int):
    """``int`` subclass carrying its source field's name.

    ``_stamp`` reserves this class for exact ``int``. Booleans go through
    :class:`_BoundBool`.
    """

    field_name: str
    owner: Any

    def __new__(cls, value: int, field_name: str, owner: Any = None) -> _BoundInt:
        instance = super().__new__(cls, value)
        instance.field_name = field_name
        instance.owner = owner
        return instance


class _BoundFloat(float):
    """``float`` subclass carrying its source field's name + owner."""

    field_name: str
    owner: Any

    def __new__(cls, value: float, field_name: str, owner: Any = None) -> _BoundFloat:
        instance = super().__new__(cls, value)
        instance.field_name = field_name
        instance.owner = owner
        return instance


class _BoundBool(int):
    """``int``-based wrapper for ``bool`` values that carries ``field_name``.

    ``bool`` itself cannot be subclassed (``TypeError``). This wrapper
    uses ``int`` (bool's parent) so the value is 0 or 1, and adds a
    marker attribute so ``emit_attrs`` can treat it as a boolean HTML
    attribute (present/absent) rather than as a numeric value.
    """

    field_name: str
    owner: Any
    _is_bound_bool: bool = True

    def __new__(cls, value: bool, field_name: str, owner: Any = None) -> _BoundBool:
        instance = super().__new__(cls, int(value))
        instance.field_name = field_name
        instance.owner = owner
        return instance

    def __bool__(self) -> bool:
        return int(self) != 0

    def __repr__(self) -> str:
        return repr(bool(self))


class _BoundList(list):  # type: ignore[type-arg]
    """``list`` subclass carrying its source field's name.

    Multi-value components (ToggleGroup / Select / Combobox in
    ``multiple`` mode) bind a LIST field (``value=state.tags``). Without
    a stamp the list looks identical to a literal ``["a", "b"]``, so the
    render layer can't tell server-backed from local — and a server-
    driven ``@refreshable`` swap can't re-adopt the value (the
    ``_serverSync`` opt-in is gated on ``field_name``). Subclassing
    ``list`` keeps every list operation working (iteration, ``len``,
    ``json.dumps``, ``isinstance(x, list)``) while adding the stamp.
    """

    field_name: str
    owner: Any

    def __init__(self, value: Any, field_name: str, owner: Any = None) -> None:
        super().__init__(value)
        self.field_name = field_name
        self.owner = owner


class _BoundTuple(tuple):  # type: ignore[type-arg]
    """``tuple`` subclass carrying its source field's name — the immutable
    twin of :class:`_BoundList`.

    Range components (DateRangePicker) bind a TUPLE field
    (``value=state.picked`` where ``picked = (d1, d2)``). Without a stamp a
    server-backed range is indistinguishable from a literal ``(d1, d2)``, so
    the render layer can't opt it into ``_serverSync`` (gated on
    ``field_name``) and a ``@refreshable`` swap won't re-adopt it. ``tuple``
    is immutable, so the stamp rides via ``__new__``. Every tuple operation
    (indexing, ``len``, ``json.dumps``, ``isinstance(x, tuple)``) still works.
    """

    field_name: str
    owner: Any

    def __new__(cls, value: Any, field_name: str, owner: Any = None) -> _BoundTuple:
        inst = super().__new__(cls, value)
        inst.field_name = field_name
        inst.owner = owner
        return inst


class _BoundDate(date):
    """``date`` subclass carrying its source field's name + owner.

    Date-valued inputs (Calendar / DatePicker) opt into
    ``AUTONAME_FROM = "value"`` just like the text inputs, but a plain
    ``datetime.date`` is none of ``str`` / ``int`` / ``float`` so the
    primitive stamps above never caught it — ``ui.date_picker(value=
    state.appointment)`` silently fell back to ``name="value"`` instead
    of ``name="appointment"``. Subclassing ``date`` keeps every date
    operation working (``isinstance(x, date)``, ``.isoformat()``,
    comparisons, arithmetic) while adding the stamp.
    """

    field_name: str
    owner: Any

    def __new__(
        cls, value: date, field_name: str, owner: Any = None
    ) -> _BoundDate:
        instance = super().__new__(
            cls, value.year, value.month, value.day
        )
        instance.field_name = field_name
        instance.owner = owner
        return instance

    def replace(self, *args: Any, **kwargs: Any) -> date:
        # ``date.replace`` reconstructs via ``type(self)(y, m, d)`` — but our
        # ``__new__`` takes ``(date, field_name)``, so the stock path passes
        # ints where a date is expected and crashes with
        # ``'int' object has no attribute 'year'``. A replaced date is a NEW
        # computed value, not the bound field, so drop the stamp and return a
        # plain ``date`` (e.g. Calendar's ``month.replace(day=1)`` on a
        # server-bound month used to 500 here).
        return date(self.year, self.month, self.day).replace(*args, **kwargs)


class _BoundDateTime(datetime):
    """``datetime`` subclass carrying its source field's name + owner.

    ``datetime`` is a subclass of ``date`` ; stamping it as a plain
    ``_BoundDate`` would drop the time component, so it gets its own
    wrapper. ``_stamp`` checks ``type(raw) is datetime`` (exact) before
    the ``date`` branch so neither catches the other.
    """

    field_name: str
    owner: Any

    def __new__(
        cls, value: datetime, field_name: str, owner: Any = None
    ) -> _BoundDateTime:
        instance = super().__new__(
            cls,
            value.year, value.month, value.day,
            value.hour, value.minute, value.second,
            value.microsecond, value.tzinfo, fold=value.fold,
        )
        instance.field_name = field_name
        instance.owner = owner
        return instance

    def replace(self, *args: Any, **kwargs: Any) -> datetime:
        # Same reconstruction trap as ``_BoundDate.replace`` — drop the
        # stamp, return a plain ``datetime``.
        return datetime(
            self.year, self.month, self.day, self.hour, self.minute,
            self.second, self.microsecond, self.tzinfo, fold=self.fold,
        ).replace(*args, **kwargs)


def _stamp(raw: Any, field_name: str, owner: Any = None) -> Any:
    """Wrap a supported value with a ``field_name`` + ``owner`` stamp, or
    return as-is.

    The render layer calls this for every field read. Dicts, custom
    objects, and ``None`` flow through unchanged so iteration and
    identity checks keep working. The plain primitives (``str`` /
    ``bool`` / ``int`` / ``float``), ``list`` / ``tuple`` (for multi-value
    components) and the date types (``datetime`` / ``date``, for the
    date inputs' autoname) get the stamp. ``owner`` is the source state
    instance, so a wrapping component (``form_field``) can resolve
    ``owner.errors``. All checks are exact (``type(raw) is …``) so an
    already-stamped value is never re-wrapped and ``datetime`` (a
    ``date`` subclass) doesn't fall into the ``date`` branch.
    """
    t = type(raw)
    if t is str:
        return _BoundStr(raw, field_name, owner)
    if t is bool:
        return _BoundBool(raw, field_name, owner)
    if t is int:
        return _BoundInt(raw, field_name, owner)
    if t is float:
        return _BoundFloat(raw, field_name, owner)
    if t is list:
        return _BoundList(raw, field_name, owner)
    if t is tuple:
        return _BoundTuple(raw, field_name, owner)
    if t is datetime:
        return _BoundDateTime(raw, field_name, owner)
    if t is date:
        return _BoundDate(raw, field_name, owner)
    return raw


# ───────────────────────────────────────────────────────────────────────────
# ServerState
# ───────────────────────────────────────────────────────────────────────────


class ServerState(State):
    """A typed state persisted on the server side.

    Subclasses declare their scope at class definition time ::

        class CartState(ServerState, scope="session"):
            items: list[Item] = field(default_factory=list)

    Defaults to ``scope="session"`` — the most common case.
    """

    __scope__: ClassVar[ServerScope] = "session"

    #: Does this state publish its named fields in the URL?
    #:
    #: ``class Issues(DatatableState, addressable=True)`` — a ONE-line
    #: opt-in, which lights up every field carrying a ``field(url=…)``.
    #:
    #: **Decision and naming are separate, and that is the heart of the
    #: design.** The name can be supplied by the framework
    #: (``DatatableState`` already names sort / direction / page /
    #: search); the decision to PUBLISH cannot. What is in a URL goes into
    #: the browser history, the server access logs and the ``Referer``
    #: header of every outgoing link — that is never obtained by default.
    __addressable__: ClassVar[bool] = False

    @classmethod
    async def load(cls, *, key: str = "default") -> Self:
        """Hydrate this state asynchronously from its configured backend."""
        # Deferred import: ``registry`` imports this module at load time,
        # the reverse at module level would make a cycle.
        from bretzel.state.registry import current_registry

        registry = current_registry()
        if registry is None:
            return cls(key=key)  # type: ignore[return-value]
        return await registry.resolve(cls, key=key)  # type: ignore[return-value]

    @classmethod
    def lock(
        cls,
        *,
        key: str = "default",
        ttl: int | None = None,
        timeout: float | None = None,
    ) -> Any:
        """Serialize a read-modify-write operation on this state."""
        from bretzel.state.registry import current_registry

        registry = current_registry()
        if registry is None:
            raise RuntimeError(
                f"{cls.__name__}.lock() needs a request registry: there "
                f"is none here (script, test outside a request). The lock "
                f"protects one store row, it is meaningless without it."
            )
        return registry.lock(cls, key, ttl=ttl, timeout=timeout)

    def __init_subclass__(
        cls,
        *,
        scope: ServerScope | None = None,
        addressable: bool | None = None,
        **kwargs: object,
    ) -> None:
        super().__init_subclass__(**kwargs)
        if addressable is not None:
            cls.__addressable__ = bool(addressable)
        if scope is None:
            return  # inherit from parent (initially "session")
        if scope not in SCOPES:
            raise ValueError(
                f"Invalid scope {scope!r} on {cls.__name__} : "
                f"expected one of {SCOPES}."
            )
        cls.__scope__ = scope

    # ── Render-flag-aware attribute access ─────────────────────────────
    #
    # Mirrors :meth:`ClientState.__getattribute__` : when rendering, scalar
    # field reads come back stamped with their ``field_name`` so
    # ``AUTONAME_FROM`` components can derive HTML ``name=`` automatically.
    # Outside a render scope, reads are raw. Internal / dunder / non-field
    # accesses always pass through untouched.

    def __getattribute__(self, name: str) -> Any:
        # Dunders / private attributes always raw — short-circuits the
        # internals (``_key``, ``_dirty``, ``__dict__``, …).
        if name.startswith("_"):
            return object.__getattribute__(self, name)

        # Outside render → raw values. Handlers, validators, computed
        # bodies all see plain Python.
        if not _RENDERING.get():
            return object.__getattribute__(self, name)

        # Inside render : only Field descriptor reads get wrapped.
        # Methods and computed properties stay normal.
        descriptor = inspect.getattr_static(type(self), name, None)
        if not isinstance(descriptor, Field):
            return object.__getattribute__(self, name)

        # Raw-value override : when a form submission was rejected for this
        # field (validator / coercion), the assignment rolled back to the
        # clean value — but the re-rendered input should keep what the user
        # actually typed (alongside the error). Render-only ; handlers
        # (outside render) still read the authoritative clean value.
        raw_overrides = object.__getattribute__(self, "__dict__").get("_bz_raw")
        if raw_overrides is not None and name in raw_overrides:
            return _stamp(raw_overrides[name], name, self)

        raw = object.__getattribute__(self, name)
        return _stamp(raw, name, self)
