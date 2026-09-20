"""Abstract :class:`State` + the ``_StateMeta`` metaclass.

The metaclass is the magic that lets users write idiomatic Python ::

    class CartState(ServerState, scope="session"):
        items: list[Item] = field(default_factory=list)
        coupon: str = field(default="")

        @computed
        def total(self) -> float:
            return ...

        @validator("coupon")
        def normalize_coupon(self, v: str) -> str:
            return v.strip().upper()

…and have it transparently turned into a typed, tracked, serialisable
state class. The metaclass walks the class body, REFUSES any declaration
that does not go through
:func:`~bretzel.state.fields.descriptor.field` — one single form, decided
on 2026-09-05 — and collects the
:class:`~bretzel.state.fields.computed.ComputedProperty` and
:class:`~bretzel.state.fields.validator.Validator` into class registries
the descriptor and registry layers read back.

Concrete scopes (``ServerState`` / ``ClientState``) live in
``bretzel.state.scopes`` and add the persistence-side configuration on
top of this skeleton.
"""

from __future__ import annotations

import re
import typing
from collections.abc import Iterator
from typing import Any, ClassVar, Final

from bretzel.state.fields.computed import ComputedProperty
from bretzel.state.fields.descriptor import MISSING, Field
from bretzel.state.fields.validator import Validator
from bretzel.state.types import is_storable

# Sentinel returned by ``namespace.get`` so we can tell "no entry" apart
# from "entry is ``None``" (a valid default).
_NOT_PROVIDED: Final[Any] = object()

#: ``ClassVar[…]`` at the head of an annotation, with or without a module
#: prefix. Annotations arrive as TEXT, hence the textual recognition.
_CLASS_VAR_RE: Final[re.Pattern[str]] = re.compile(
    r"^\s*(?:\w+\.)?ClassVar\b"
)

#: The types a ``merge="add"`` field may carry. The store sums NUMBERS:
#: ``HINCRBY`` on a string returns "hash value is not an integer", so at
#: deployment time.
_ADDABLE_TYPES: Final[tuple[type, ...]] = (int, float)


# ───────────────────────────────────────────────────────────────────────────
# Metaclass
# ───────────────────────────────────────────────────────────────────────────


def _is_class_var(annotation: Any) -> bool:
    """Does the annotation say ``ClassVar``?

    It arrives as TEXT most of the time (the ``__future__``, or the
    format requested from PEP 649), so the recognition is textual — with
    the module prefix optional, ``typing.ClassVar`` being as common as
    ``ClassVar``. On 3.12/3.13 without the ``__future__`` it arrives as an
    object, hence the second test.
    """
    if isinstance(annotation, str):
        return _CLASS_VAR_RE.match(annotation) is not None
    return annotation is ClassVar or typing.get_origin(annotation) is ClassVar


def _refuse_a_bare_declaration(cls_name: str, attr_name: str, value: Any) -> None:
    """A field is declared with ``field(...)``, and with nothing else.

    **One single way to write one thing.** A field option has nowhere to
    land on the short form, so every new declaration had to invent a TYPE
    (``Counter``, ``Amount``…) and grow the public surface. With a call,
    they are added as parameters.

    The annotation stays mandatory: it is the only position where Python
    reads a type *expression*, so the only one able to say ``int | None``.
    """
    if isinstance(value, list | dict | set):
        # The trickiest case keeps its own message: a mutable literal
        # shared between instances is a fault in itself, not merely a
        # matter of spelling.
        raise TypeError(
            f"Mutable default for {attr_name!r} on {cls_name!r}: "
            "use 'field(default_factory=...)' instead of a "
            "literal list/dict/set."
        )
    if value is _NOT_PROVIDED:
        write_as = "field()"
        finding = "has no value"
    else:
        write_as = f"field(default={value!r})"
        finding = f"is {value!r}"
    raise TypeError(
        f"{cls_name}.{attr_name} {finding}: write "
        f"`{attr_name}: … = {write_as}`. "
        f"A field is declared by ONE call, and that is where "
        f"`default_factory`, `url` and `merge` live — there is no second "
        f"way to do it. The type annotation stays: it is what gives the "
        f"type."
    )


def _refuse_an_unstorable_type(cls_name: str, attr_name: str, fld: Field) -> None:
    """A field must be able to REACH the store, and we say so early.

    Without this refusal, ``day: date`` was accepted, the memory store
    kept the Python object as-is, and the fault waited for Redis to be
    plugged in: it worked in dev and broke at deployment. Raising at
    import moves the failure to where it is seen — at startup, on the
    machine of whoever writes the field.

    Same gesture as the two neighbouring refusals: the ambiguous form is
    forbidden rather than left to bite later.
    """
    if is_storable(fld.type_):
        return
    # ⚠️ An unresolved FORWARD reference stays a string (cf. the
    # ``except (NameError, TypeError)`` in the metaclass, which leaves
    # ``type_`` as-is). We cannot judge what we could not resolve:
    # refusing here would break a pattern the framework tolerates on
    # purpose. It is then the store that will refuse at write time, and
    # name the field.
    if isinstance(fld.type_, str):
        return
    type_name = getattr(fld.type_, "__name__", None) or repr(fld.type_)
    raise TypeError(
        f"{cls_name}.{attr_name} is declared {type_name!r}, which the "
        f"store does not know how to write. State persists as JSON — "
        f"Bretzel does NOT fall back on pickle (code-execution risk).\n"
        f"  • if it is one of your classes: "
        f"`register_type({type_name}, encode=…, decode=…)` once, when the "
        f"app loads, and the annotation is enough afterwards;\n"
        f"  • if you know what you are doing: annotate `Any`, and it is "
        f"the store that will refuse at write time, naming the field.\n"
        f"Known out of the box: str, int, float, bool, list, dict, date, "
        f"datetime, time, Decimal, UUID and any enumeration."
    )


def _refuse_an_impossible_sum(cls_name: str, attr_name: str, fld: Field) -> None:
    """``merge="add"`` asks for a number, and a number starting at zero.

    Both refusals come from the store, not from taste:

    - ``HINCRBY`` on a non-numeric value returns "hash value is not an
      integer". Without this check, the fault would wait for the first
      write IN PRODUCTION — the dev runs in memory, where summing two
      strings raises elsewhere and differently;
    - ``HINCRBY`` on an ABSENT field counts from 0. A counter whose
      default were 10 would therefore see its first "add 1" write 1 where
      the app displays 11, and the gap would never be made up. Making it
      up at commit time would require the backend to know every state's
      defaults.

    A total that starts anywhere but zero is not a total anyway: it is a
    starting value, therefore a choice.
    """
    if fld.type_ is not None and fld.type_ not in _ADDABLE_TYPES:
        raise TypeError(
            f"{cls_name}.{attr_name} is declared `merge=\"add\"` but its "
            f"type is {getattr(fld.type_, '__name__', fld.type_)!r}. "
            f"The store SUMS: only `int` and `float` can be summed. For a "
            f"list there is no operation yet — you need your own lock."
        )
    start = fld.default if fld.default is not MISSING else 0
    if start:
        raise TypeError(
            f"{cls_name}.{attr_name} is declared `merge=\"add\"` and is "
            f"{start!r} by default. A total starts at zero: the store "
            f"counts from 0 when the row does not exist yet, so another "
            f"default would be lost on the first increment. Put 0, or drop "
            f"`merge` if this value is a starting point and not a total."
        )


def _body_annotations(namespace: dict[str, Any]) -> dict[str, Any]:
    """The class body's annotations, wherever Python stored them.

    Two places, depending on the version and on the module:

    - ``__annotations__`` in the namespace — on Python 3.12/3.13, and
      everywhere the module carries ``from __future__ import annotations``;
    - a FUNCTION, ``__annotate_func__`` — on Python 3.14 without that
      ``__future__``, where PEP 649 no longer materialises annotations
      when the class is created.

    Reading only the first did not raise: it returned an empty dict, so a
    state class **with no field at all**. Reads still worked (plain
    attributes), nothing was ever persisted, and no error anywhere — the
    action answered 204 and the screen did not move. That is what forced
    every app to write ``from __future__ import annotations`` at the head
    of each module declaring a state, on pain of a mute failure. This
    function removes the requirement.

    ``Format.STRING`` returns text, exactly like the ``__future__``: step
    5 of the metaclass resolves everything into real types, and a forward
    reference must on no account raise here.
    """
    annotations = namespace.get("__annotations__")
    if annotations is not None:
        return annotations
    annotate = namespace.get("__annotate_func__")
    if annotate is None:
        return {}
    # Local import: ``annotationlib`` only exists from 3.14 on, and we
    # only get here on 3.14 — ``__annotate_func__`` does not exist before.
    import annotationlib

    return annotationlib.call_annotate_function(
        annotate, annotationlib.Format.STRING
    )


class _StateMeta(type):
    """Metaclass for :class:`State`.

    Responsibilities:

    1. **Refuse a bare declaration.** ``count: int = 0`` raises, with the
       sentence that says to write ``field(default=0)``. One single form:
       it is the only place a field option can land.
    2. **Let through what is not a field**: a name prefixed with ``_``,
       and a ``ClassVar`` annotation — which is precisely the standard way
       of saying "this is not an instance field".
    3. **Aggregate validators and computed declarations.** Class-body
       declarations are merged with what the parents already exposed, so
       inheritance composes correctly.
    4. **Drop class-level kwargs.** ``class X(Base, scope="session")``
       passes ``scope="session"`` to the metaclass — we keep them out of
       :py:meth:`type.__new__` (which doesn't accept kwargs) and let
       ``__init_subclass__`` on concrete scopes consume them.
    """

    def __new__(
        mcs,
        name: str,
        bases: tuple[type, ...],
        namespace: dict[str, Any],
        **kwargs: Any,
    ) -> _StateMeta:
        annotations: dict[str, Any] = _body_annotations(namespace)

        # ── 1. Pre-scan the body for already-declared decorators ────────
        body_validators: dict[str | None, list[Validator]] = {}
        body_computed: dict[str, ComputedProperty] = {}

        for attr_name, value in namespace.items():
            if isinstance(value, Validator):
                body_validators.setdefault(value.target, []).append(value)
            elif isinstance(value, ComputedProperty):
                body_computed[attr_name] = value

        # ── 2. Wrap plain defaults as Fields ───────────────────────────
        for attr_name, ann_type in annotations.items():
            if attr_name.startswith("_"):
                continue  # private — leave alone

            existing = namespace.get(attr_name, _NOT_PROVIDED)

            if isinstance(existing, Field):
                # Capture the annotation but don't replace the descriptor.
                if existing.type_ is None:
                    existing.type_ = ann_type
                # ── What the PARENT field said about itself ─────────
                #
                # Redeclaring a field to change its DEFAULT must not make
                # it lose what it otherwise is. The measured case
                # (2026-08-29): ``DatatableState.sort_key`` carries
                # ``url="sort"``, an app redeclares it to sort by name
                # initially — and its URL silently stopped carrying the
                # sort. Overriding a value is not a renunciation of the
                # vocabulary.
                if existing.url is None:
                    for base in bases:
                        parent = getattr(base, attr_name, None)
                        if isinstance(parent, Field) and parent.url:
                            existing.url = parent.url
                            break
                continue
            if isinstance(existing, ComputedProperty | Validator):
                # Decorated declarations are already first-class descriptors.
                continue

            if _is_class_var(ann_type):
                # A class constant is NOT a field, and saying so is
                # ``ClassVar``'s job. Before this test it was promoted
                # like the others: persisted, diffed, and sent to the
                # browser on a ``ClientState``.
                continue

            _refuse_a_bare_declaration(name, attr_name, existing)

        # ── 3. Build the class. Forward kwargs to ``type.__new__`` so
        # they propagate to ``__init_subclass__`` of the parent chain
        # (PEP 487). ``type.__new__`` itself ignores unknown kwargs.
        cls = super().__new__(mcs, name, bases, namespace, **kwargs)

        # ── 4. Merge inherited registries with what the body added ─────
        merged_validators: dict[str | None, list[Validator]] = {}
        merged_computed: dict[str, ComputedProperty] = {}

        # Walk MRO in reverse so deeper bases lose to shallower overrides.
        for base in reversed(cls.__mro__[1:]):  # skip cls itself
            for target, vlist in getattr(base, "__validators__", {}).items():
                merged_validators.setdefault(target, []).extend(vlist)
            merged_computed.update(getattr(base, "__computed__", {}))

        for target, vlist in body_validators.items():
            merged_validators.setdefault(target, []).extend(vlist)
        merged_computed.update(body_computed)

        cls.__validators__ = merged_validators
        cls.__computed__ = merged_computed

        # ── 5. Resolve string annotations into real types ──────────────
        # ``from __future__ import annotations`` (PEP 563) and PEP 649
        # both make annotations show up as strings on the class. Resolve
        # them once so descriptors carry the actual ``type`` object.
        try:
            resolved = typing.get_type_hints(cls)
        except (NameError, TypeError):
            # Forward references that can't be resolved at definition time
            # leave the descriptor's ``type_`` as the unresolved string.
            resolved = {}

        for attr_name, attr in vars(cls).items():
            if not isinstance(attr, Field):
                continue
            if attr_name in resolved:
                attr.type_ = resolved[attr_name]
            if attr.merge == "add":
                _refuse_an_impossible_sum(name, attr_name, attr)
            # OUTSIDE the `if`: every field must be able to reach the
            # store, additive or not. This check lived inside it for the
            # time of one commit, where it only saw counters — that is to
            # say the only fields whose type was ALREADY guaranteed
            # numeric.
            _refuse_an_unstorable_type(name, attr_name, attr)

        return cls

    def __init__(
        cls,
        name: str,
        bases: tuple[type, ...],
        namespace: dict[str, Any],
        **kwargs: Any,
    ) -> None:
        # Forward kwargs to ``type.__init__`` so they reach
        # ``__init_subclass__`` of the parent chain. ``type.__init__`` in
        # CPython 3.6+ tolerates extra keyword arguments (PEP 487) and
        # routes them to ``__init_subclass__``.
        super().__init__(name, bases, namespace, **kwargs)

    def __call__(cls, *args: Any, **kwargs: Any) -> Any:
        """Intercept ``MyState(...)`` to consult the active registry.

        Inside a request scope, the registry caches one instance per
        ``(class, key)`` pair so multiple ``MyState()`` calls return the
        same object. Outside a registry scope (tests, scripts), this
        falls through to a vanilla constructor.

        We import :func:`current_registry` lazily — ``registry.py``
        imports from this module too, and the cycle would otherwise
        explode at module load.
        """
        from bretzel.state.registry import current_registry

        registry = current_registry()
        if registry is None:
            return super().__call__(*args, **kwargs)

        key = kwargs.get("key", "default")
        cached = registry.get_cached(cls, key)
        if cached is not None:
            return cached

        # ServerState: hydrate from the backend, whatever it is. The
        # memory backend reads directly (``load_sync``); a backend that
        # only reads with ``await`` (Redis) is reached through the
        # registry's thread → loop bridge. ``None`` here therefore means
        # "nothing stored", no longer "not hydratable": we then fall back
        # on the default values, which is the right answer.
        #
        # ⚠️ From an ``async def`` app body — so on the loop, where the
        # bridge cannot wait — ``try_sync_resolve`` RAISES instead of
        # returning defaults the commit would then overwrite. The gesture
        # to write there is ``await MyState.load()``.
        from bretzel.state.scopes.client import ClientState
        from bretzel.state.scopes.server import ServerState

        if issubclass(cls, ServerState):
            hydrated = registry.try_sync_resolve(cls, key)
            if hydrated is not None:
                return hydrated

        instance = super().__call__(*args, **kwargs)
        registry.register(instance, key)

        # ClientState picks up inbound client-side values automatically
        # so handlers see what the browser most-recently sent.
        if isinstance(instance, ClientState):
            registry.hydrate_client(instance)

        return instance


# ───────────────────────────────────────────────────────────────────────────
# Abstract State
# ───────────────────────────────────────────────────────────────────────────


class State(metaclass=_StateMeta):
    """Abstract parent of all typed-state classes.

    Concrete scopes live in :mod:`bretzel.state.scopes`. Direct
    instantiation of :class:`State` is allowed for tests but yields no
    persistence behaviour — registry resolution and backend save / load
    are scope-specific.
    """

    # Class-level registries populated by the metaclass. Declared here so
    # both static checkers and runtime introspection see them on every
    # subclass even if it has no validators / computed of its own.
    __validators__: ClassVar[dict[str | None, list[Validator]]] = {}
    __computed__: ClassVar[dict[str, ComputedProperty]] = {}

    def __init__(self, *, key: str = "default") -> None:
        self._key: str = key
        self._dirty: bool = False

    # ── Introspection helpers ────────────────────────────────────────────

    @classmethod
    def _all_fields(cls) -> dict[str, Field]:
        """Walk the MRO and collect every :class:`Field` descriptor.

        Cached on the class on first call. Layers above (registry,
        client_bridge) iterate over this to drive serialization.
        """
        cached = cls.__dict__.get("__bz_field_cache__")
        if cached is not None:
            return cached  # type: ignore[no-any-return]

        result: dict[str, Field] = {}
        for klass in reversed(cls.__mro__):
            for attr_name, attr in klass.__dict__.items():
                if isinstance(attr, Field):
                    result[attr_name] = attr

        # Stash on the class itself (not on a parent's dict).
        type.__setattr__(cls, "__bz_field_cache__", result)
        return result

    def _iter_field_names(self) -> Iterator[str]:
        """Yield every field name declared on this instance's class."""
        yield from type(self)._all_fields().keys()

    def _field_values(self) -> dict[str, Any]:
        """Effective value of every declared field — its default when unset —
        read straight from storage WITHOUT materialising ``default_factory``
        into ``__dict__``.

        This is the snapshot surface the registry diffs to detect mutations,
        including in-place ones (``state.items.append(...)``) that never go
        through :meth:`~bretzel.state.fields.descriptor.Field.__set__`.
        Reading from storage (not ``getattr``) keeps it side-effect-free ;
        falling back to the field default means a lazily-read default never
        looks like a change. Required fields with no value and no default are
        omitted (they appear in the map iff explicitly set).
        """
        out: dict[str, Any] = {}
        for name, fld in type(self)._all_fields().items():
            storage_key = fld._storage_key
            if storage_key in self.__dict__:
                out[name] = self.__dict__[storage_key]
            elif fld.default_factory is not None:
                out[name] = fld.default_factory()
            elif fld.default is not MISSING:
                out[name] = fld.default
        return out

    # ── Form-validation errors ───────────────────────────────────────────

    @property
    def errors(self) -> dict[str, str]:
        """Field-name → message map of validation errors.

        Populated when this state is hydrated from a form submission by
        the action dispatcher's ``def handler(form: MyState)`` path : each
        validator that rejects a submitted value lands its message here
        (the assignment itself is rolled back, so the field keeps its
        prior value). Empty when the submission was valid or the state
        wasn't form-hydrated.

        The handler checks it and decides what to do ; the form zone
        declares ``deps=[MyForm]`` so it re-renders automatically once a
        validator writes here — no manual call ::

            def save(form: MyForm) -> None:
                if form.errors:
                    return               # zone re-renders : form_fields show messages
                ...                      # valid : proceed

        A ``form_field`` displays a field's message via
        ``error=form.errors.get("<field>")``. ``"_"``-prefixed key holds
        whole-form (cross-field) errors.
        """
        return self.__dict__.get("_bz_errors", {})

    # ── Serialisation ────────────────────────────────────────────────────

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-friendly snapshot of the instance.

        Only fields with **explicitly stored** values are included — the
        defaults are recoverable by the receiving end via
        le registre. Computed properties are excluded ; they are
        derived, not state.
        """
        result: dict[str, Any] = {}
        for name, field in type(self)._all_fields().items():
            if field.has_value(self):
                value = self.__dict__.get(field._storage_key, MISSING)
                if value is MISSING:
                    continue
                result[name] = value
        return result

    def _apply_fields(self, data: dict[str, Any]) -> None:
        """Overwrite every declared field present in ``data`` on this instance.

        Unknown keys are silently ignored — letting an old persisted payload
        survive a removed field. Each assignment goes through
        ``Field.__set__`` (coercion + validators). The single source for the
        "hydrate from a dict" loop, shared by the registry's resolution
        paths and the client store's; the caller then does its own
        ``_dirty`` reset and its registration.

        It is the single internal entry point for hydrating an existing
        instance from a dictionary.
        """
        fields = type(self)._all_fields()
        for name, value in data.items():
            if name in fields:
                setattr(self, name, value)

    # ── Equality / repr ──────────────────────────────────────────────────

    def __repr__(self) -> str:
        body = ", ".join(f"{n}={getattr(self, n)!r}" for n in self._iter_field_names())
        return f"{type(self).__name__}(key={self._key!r}, {body})"
