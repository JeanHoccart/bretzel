"""Reactive props — the bridge between component kwargs and runtime attrs.

A *reactive prop* is a class attribute on a :class:`Component` subclass
declared like ::

    class Button(Component):
        color: str = reactive_prop(default="primary")
        disabled: bool = reactive_prop(default=False)

The descriptor itself is mostly a marker : the real work happens at
:py:meth:`Component.__init__` time, where the metaclass walks the
class body and the constructor inspects the kwargs to decide which
storage path each value takes:

- **Python literal** (``True``, ``"primary"``, ``42``) → static HTML
  attribute, baked at render time.
- **ClientBinding** (``state.X`` from a ``ClientState``) → emitted as
  ``bz-attr:X="<binding-path>"`` ; the runtime binds it reactively.
  (The old ``bz-prop:`` prefix was split into ``BZ_MODEL_PREFIX`` +
  ``BZ_ATTR_PREFIX`` — cf. ``runtime/protocol.py``.)
A ``str`` is always a literal, whatever it looks like. Client code is a
``ClientBinding`` / ``ClientExpression``, or a ``bz-attr:X`` the caller
writes by hand (``**{"bz-attr:placeholder": "a && b"}``).

⚠️ No heuristic sniffs a string — a call ``f(``, ``||``, ``==``, ``$el``
— to send it out as ``bz-attr:X``, compiled by the runtime with
``new Function``: a value comes from people. With such a guess,
``ui.avatar(name="0||alert(1)")`` would run its script in every browser
that shows that user.
"""

from __future__ import annotations

from collections.abc import Callable
from functools import cache
from typing import Any, Final

from bretzel.components.base.attrs import ComponentDefinitionError


class _Missing:
    """Sentinel for "no default" — kept distinct from ``None`` which
    is itself a perfectly valid default value."""

    __slots__ = ()

    def __repr__(self) -> str:
        return "MISSING"


MISSING: Final[Any] = _Missing()


# ───────────────────────────────────────────────────────────────────────────
# Descriptor
# ───────────────────────────────────────────────────────────────────────────


class ReactivePropDescriptor:
    """Class-level descriptor for a reactive prop.

    Stores the default value at class build time ; the actual value
    lives in ``instance._reactive_values[name]`` after
    :py:meth:`Component.__init__` runs.

    Class-level access (``Button.color``) yields the descriptor itself
    so the metaclass / introspection code can read its config.
    Instance-level access (``my_btn.color``) yields the stored value.
    """

    __slots__ = (
        "declared_type",
        "default",
        "default_factory",
        "emit_attr",
        "name",
        "names_field",
        "scope_keys",
        "steps",
        "writes",
    )

    def __init__(
        self,
        *,
        default: Any = MISSING,
        default_factory: Callable[[], Any] | None = None,
        emit_attr: bool = True,
        writes: bool = False,
        scope_keys: tuple[str, ...] | None = None,
        steps: tuple[str, ...] | None = None,
        names_field: bool = False,
    ) -> None:
        if default is not MISSING and default_factory is not None:
            raise ComponentDefinitionError(
                "reactive_prop cannot specify both ``default`` and ``default_factory``."
            )
        if scope_keys is not None and len(scope_keys) < 2:
            # ⚠️ A SINGLE key is not declared: the default is the
            # prop's name, so ``scope_keys=("value",)`` is redundant and
            # ``scope_keys=("val",)`` is a SYNONYM. The repository
            # carried thirteen — ``val``, ``active``, ``current``,
            # ``sel``, ``expanded``, ``picked`` — that is eight
            # spellings for one notion, and it knows what they cost:
            # "it is the naming divergence (value/picked/active/sel)
            # that caused 5 of the 8 missed ``_serverSync``".
            #
            # What stays legitimate is the form the default CANNOT
            # express: a value living under SEVERAL keys
            # (``Calendar.month`` → ``year`` + ``month``,
            # ``DateRangePicker.value`` → ``vstart`` + ``vend``). Hence
            # the threshold at two — it does not measure a quantity, it
            # names the parameter's only reason to exist.
            #
            # Raised at CLASS CREATION, so at import: it is not a test
            # one can forget to run.
            raise ComponentDefinitionError(
                f"reactive_prop(scope_keys={scope_keys!r}): a SINGLE "
                f"scope key is not declared — it is the prop's name by "
                f"default. Remove the parameter and name the key like the "
                f"prop. ``scope_keys=`` only exists for a value living "
                f"under SEVERAL keys (year+month, vstart+vend)."
            )
        self.name: str = ""
        self.default = default
        self.default_factory = default_factory
        # When ``False``, the prop's value is consumed internally by
        # the component (typically to compose theme classes) but never
        # ends up as a raw HTML attribute. Use for purely-cosmetic
        # props like ``variant`` / ``size`` / ``color`` / ``weight``
        # that would otherwise pollute the DOM with framework noise.
        # Reactive bindings (ClientBinding / client expressions) are
        # still emitted as ``bz-attr:`` / ``bz-model`` because the
        # runtime has to track them.
        self.emit_attr = emit_attr
        # ``writes``: the CLIENT writes into this prop (value / checked
        # / open). The client path is the ASSIGNMENT TARGET in the JS
        # emitted → a ClientExpression is refused there, and
        # ``_serverSync`` is emitted in server-backed mode. The
        # metaclass derives the ``TWO_WAY_PROPS`` ClassVar from it
        # (co-located with the prop rather than declared 30 lines below —
        # it is Lit's ``reflect`` / Textual's ``bindings=``). This is NOT
        # ``AUTONAME_FROM`` ("where does my HTML name= come from"). Cf.
        # ``Component._value_server_backed``.
        self.writes = writes
        # ``scope_keys``: under which key(s) the value lives in the
        # component's ``bz-data``. **Default: the prop's name**, and that
        # is the case for 31 of the 33 writing props. The two that
        # declare are the ones the default cannot express:
        # ``Calendar.month`` → ``("year", "month")``,
        # ``DateRangePicker.value`` → ``("vstart", "vend")``.
        #
        # ⚠️ A SINGLE key is REFUSED (cf. ``__init__``). The parameter
        # carried thirteen synonyms — ``val``, ``active``, ``current``,
        # ``sel``, ``expanded``, ``picked`` — that is eight spellings for
        # "the chosen value". The cost is on record: "it is the naming
        # divergence (value/picked/active/sel) that caused 5 of the 8
        # missed ``_serverSync``". The key was moreover hard-coded in
        # every ``server_sync_marker(...)`` — two sources for one fact;
        # the emission now reads it through
        # ``Component._scope_keys(prop)``.
        self.scope_keys = scope_keys
        # ``steps``: this prop's LEGAL values, when the theme cannot
        # say them. Declaring them is all it takes: the socle refuses the
        # rest at render, with :class:`ComponentUsageError` (cf.
        # ``table_axes``). ``refuse_a_value_off_the_table`` normally reads the
        # ``sizes`` / ``variants`` table; some props escape it and would
        # otherwise render anything silently:
        #
        #   - ``bar_chart.variant`` / ``pie_chart.variant`` — their value
        #     names a PLOT MODE, not a theme step, so there is no table
        #     to read. ``variant="zzz"`` would render identically to the
        #     default;
        #   - ``radio.size`` — the table exists but its default is
        #     ``None`` ("inherit from the group"), and it is the default
        #     that anchors which of a nested table's two tiers carries
        #     the steps. With no readable anchor, the refusal abstains,
        #     and ``size="zzz"`` would render WITHOUT a size;
        #   - ``radio_group.size`` — the group has no table of its own,
        #     it passes down to the children.
        #
        # ⚠️ **Do NOT retype a list the theme already carries.** A prop
        # with a table reads it (``tuple(RADIO_THEME
        # ["sizes"])``): it is the same gesture as ``scope_keys``, a
        # declaration that NAMES a source rather than becoming a second
        # one. A copied set would drift from the table the day it gains a
        # step.
        self.steps = steps
        # ``names_field``: it is THIS prop that gives the component its
        # HTML ``name=``, hence the field the FormData will carry. The
        # metaclass derives the ``AUTONAME_FROM`` ClassVar from it.
        #
        # The third fact co-located on the prop, after ``writes`` and
        # ``scope_keys``. It answers a DIFFERENT question from ``writes``:
        # "where does my name= come from" against "what does the client
        # write". The two coincide on the form inputs but diverge — some
        # components write without naming (the overlays on ``open``,
        # ``FormField`` on ``error``). Confusing them couples server-sync
        # to form naming.
        #
        # ⚠️ ``names_field=True`` implies ``writes=True``: a form field
        # whose value the client does not write has no ``name=`` to
        # derive. The metaclass checks it.
        self.names_field = names_field
        # Populated by ``_ComponentMeta.__new__`` once it can read the
        # owner class's ``__annotations__``. ``None`` means "unannotated"
        # — discipline checks fall back to permissive behaviour.
        self.declared_type: Any = None

    def __set_name__(self, owner: type, name: str) -> None:
        self.name = name

    def __get__(self, instance: Any | None, owner: type | None = None) -> Any:
        if instance is None:
            return self
        # Stored values live on a per-instance dict populated by the
        # Component constructor. Falling back to the descriptor's own
        # default keeps simple instantiations working before the
        # storage dict is wired (helps tests and class introspection).
        values = getattr(instance, "_reactive_values", None)
        if values is None:
            return self.resolve_default()
        return values.get(self.name, self.resolve_default())

    def resolve_default(self) -> Any:
        if self.default_factory is not None:
            return self.default_factory()
        if self.default is not MISSING:
            return self.default
        return None

    def has_default(self) -> bool:
        return self.default is not MISSING or self.default_factory is not None

    def __repr__(self) -> str:
        parts = [f"name={self.name!r}"]
        if self.default is not MISSING:
            parts.append(f"default={self.default!r}")
        if self.default_factory is not None:
            parts.append(f"default_factory={self.default_factory!r}")
        return f"reactive_prop({', '.join(parts)})"


# ───────────────────────────────────────────────────────────────────────────
# Public sugar
# ───────────────────────────────────────────────────────────────────────────


def reactive_prop(
    *,
    default: Any = MISSING,
    default_factory: Callable[[], Any] | None = None,
    emit_attr: bool = True,
    writes: bool = False,
    scope_keys: tuple[str, ...] | None = None,
    steps: tuple[str, ...] | None = None,
    names_field: bool = False,
) -> Any:
    """Declare a reactive prop on a :class:`Component` subclass.

    Pass ``emit_attr=False`` for cosmetic props consumed only by the
    component's class composition (variant / size / color / weight …)
    so they don't leak into the DOM as raw attributes. Reactive
    bindings still flow through (``bz-attr:`` / ``bz-model`` directives) —
    the runtime needs them.

    Pass ``writes=True`` when the CLIENT writes into this prop (a
    value-holding input: ``value`` / ``checked`` / ``open``). The
    metaclass derives ``TWO_WAY_PROPS`` from these — no separate ClassVar
    to keep in sync. The scope key is then the PROP'S NAME, and
    ``scope_keys=(...)`` is only set for a value living under SEVERAL
    keys (``Calendar.month`` → ``("year", "month")``,
    ``DateRangePicker.value`` → ``("vstart", "vend")``) — a single key is
    refused at class creation. Cf. :class:`ReactivePropDescriptor`.

    Pass ``names_field=True`` on the prop that gives the component its
    HTML ``name=`` — the metaclass derives ``AUTONAME_FROM`` from it. It
    implies ``writes=True`` (checked): a form field whose value the
    client does not write has no ``name=`` to derive.

    Return type is ``Any`` so static checkers see the field's
    annotated type on the class (``color: str = reactive_prop(...)``
    type-checks as ``str``).
    """
    return ReactivePropDescriptor(
        default=default,
        default_factory=default_factory,
        emit_attr=emit_attr,
        writes=writes,
        scope_keys=scope_keys,
        steps=steps,
        names_field=names_field,
    )


@cache
def _defaults_of(cls: type) -> tuple[tuple[str, Any, Callable[[], Any] | None], ...]:
    """``(name, default, factory)`` for each reactive prop of ``cls``, in
    declaration order — read once per class, not once per instance."""
    return tuple(
        (name, None if d.default is MISSING else d.default, d.default_factory)
        for name, d in (getattr(cls, "__reactive_props__", {}) or {}).items()
    )


def fill_defaults(values: dict[str, Any], cls: type) -> None:
    """Give every reactive prop not set by the caller its default, in
    declaration order (a factory runs per instance)."""
    for name, default, factory in _defaults_of(cls):
        if name not in values:
            values[name] = factory() if factory is not None else default
