"""Reactive props — the bridge between component kwargs and runtime attrs.

A *reactive prop* is a class attribute on a :class:`Component` subclass
declared like ::

    class Button(Component):
        color: str = reactive_prop(default="primary")
        disabled: bool = reactive_prop(default=False)

The descriptor itself is mostly a marker : the real work happens at
:py:meth:`Component.__init__` time, where the metaclass walks the
class body and the constructor inspects the kwargs to decide which
storage path each value takes (cf. ``.claude/bretzel/components.md`` § *How
emit_attrs handles the 3 cases*) :

- **Python literal** (``True``, ``"primary"``, ``42``) → static HTML
  attribute, baked at render time.
- **ClientBinding** (``state.X`` from a ``ClientState``) → emitted as
  ``bz-attr:X="<binding-path>"`` ; the runtime binds it reactively.
  (The old ``bz-prop:`` prefix was split into ``BZ_MODEL_PREFIX`` +
  ``BZ_ATTR_PREFIX`` — cf. ``runtime/protocol.py``.)
- **client expression string** (``"$bz.state.X.y"``, ``"a <= 1"``, …) →
  emitted as a raw ``bz-attr:X="..."`` directive too.

This module owns the descriptor + factory + the heuristic that tells
"is this string a client expression or a literal?".
"""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import Any, Final


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
        "never_code",
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
        never_code: bool = False,
    ) -> None:
        if default is not MISSING and default_factory is not None:
            raise ValueError(
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
            raise ValueError(
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
        # ``Component._value_server_backed`` + todo.md § A3.
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
        # say them. ``refuse_a_value_off_the_table`` normally reads the
        # ``sizes`` / ``variants`` table; four props in the catalogue
        # escaped it and therefore rendered anything silently (measured
        # on 2026-09-06, then on 2026-09-07):
        #
        #   - ``bar_chart.variant`` / ``pie_chart.variant`` — their value
        #     names a PLOT MODE, not a theme step, so there is no table
        #     to read. ``variant="zzz"`` rendered identically to the
        #     default;
        #   - ``radio.size`` — the table exists but its default is
        #     ``None`` ("inherit from the group"), and it is the default
        #     that anchors which of a nested table's two tiers carries
        #     the steps. With no readable anchor, the refusal abstained,
        #     and ``size="zzz"`` rendered WITHOUT a size;
        #   - ``radio_group.size`` — the group has no table of its own,
        #     it passes down to the children.
        #
        # ⚠️ **Do NOT retype a list the theme already carries.** Three of
        # the four read their own table (``tuple(RADIO_THEME
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
        # ``scope_keys`` — and the last of the three to migrate (the base
        # layer's 2026-07-29 audit classified it as "the last
        # pre-migration style declaration"). It answers a DIFFERENT
        # question from ``writes``: "where does my name= come from"
        # against "what does the client write". The two coincide on the
        # 15 form inputs but diverge — 6 components write without naming
        # (the 5 overlays on ``open``, ``FormField`` on ``error``).
        # Confusing them is precisely what had coupled server-sync to
        # form naming.
        #
        # ⚠️ ``names_field=True`` implies ``writes=True``: a form field
        # whose value the client does not write has no ``name=`` to
        # derive. The metaclass checks it.
        self.names_field = names_field
        # ``never_code``: this prop's value is DATA, never client code
        # — so ``looks_like_client_expr`` does not run on it. The fourth
        # fact co-located on the prop, same pattern as ``writes`` /
        # ``scope_keys`` / ``names_field``.
        #
        # The case that gave birth to it, and why it is a DECLARATION and
        # not one more marker in the heuristic: a prop carrying a URL
        # (``href`` / ``src`` / ``poster``) regularly receives base64,
        # whose padding is written ``=`` or ``==``. And ``==`` is a
        # strong marker. The value therefore went out as ``bz-attr:href``,
        # the runtime tried to compile ``/_bretzel/datatable.csv?q=…`` as
        # JS — ``/…/`` is a regex literal — and threw "Invalid regular
        # expression flags". Measured on 2026-08-26: the datatable's CSV
        # export lost its ``href`` after any search, depending on whether
        # the blob happened to land on the padding.
        #
        # It was the THIRD occurrence of this class (``--w: 200px``,
        # ``signature_pad``'s data URI, this one), and the first two had
        # been repaired by a SHAPE exclusion in the heuristic — including
        # ``value.startswith("data:")``, removed here: it targeted the
        # same props, guessing from the value what the prop can say. A
        # shape exclusion only ever closes the occurrence it saw; the
        # declaration closes the class.
        #
        # The escape hatch remains: ``**{"bz-attr:href": "…"}`` forces
        # the expression, as on any prop.
        self.never_code = never_code
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
    never_code: bool = False,
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

    Pass ``never_code=True`` when the value is DATA and never client code
    — a URL (``href`` / ``src`` / ``poster``), typically.
    :func:`looks_like_client_expr` then does not run on it at all, which
    puts it out of reach of its false positives: a base64 padding (``==``)
    in a URL was enough to send it out as ``bz-attr:``, and the runtime
    then threw a syntax error instead of setting the attribute. Cf.
    :class:`ReactivePropDescriptor`.

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
        never_code=never_code,
    )


# ───────────────────────────────────────────────────────────────────────────
# client-expression heuristic
# ───────────────────────────────────────────────────────────────────────────


# Conservative markers — every one of these is a *strong* signal that
# the string is JS code, not a value. We default to "literal" when in
# doubt so harmless strings like ``color="primary"`` never accidentally
# get evaluated as JS.
_CLIENT_EXPR_MARKERS: tuple[str, ...] = (
    "==", "!=", "===", "!==",
    "<=", ">=",
    "&&", "||",
    # NOTE: ``++`` / ``--`` removed in May 2026.
    # - ``--`` collides with EVERY CSS custom property name
    #   (``--w``, ``--bg-color``, ``--bz-overlay-z``) and is far
    #   more commonly typed as a value than as a JS decrement.
    #   Regression: a placeholder ``"--w: 200px"`` mistagged as
    #   the runtime emitted ``:placeholder="--w: 200px"`` → the runtime
    #   parse error → page crash.
    # - ``++`` shows up in prose too (``"C++ developer"``,
    #   ``"version 2++"``) and the JS decrement / increment forms
    #   always come WITH an identifier (``i++``, ``++count``)
    #   which is already caught by the function-call /
    #   member-access heuristics elsewhere.
    # A user who really wants to fire a JS ``i--`` expression as a
    # prop value forces it with ``attrs={"bz-attr:x": …}``. (The old
    # ``:attr`` was an inert Alpine prefix, and it RAISES since
    # 2026-07-30.)
    # The V3 runtime magics. ``$store`` was removed on 2026-08-01: it
    # was an Alpine magic, absent from ``runtime/_src`` (the real ones
    # are $bz / $dispatch / $el / $event / $refs / $root). An allowlist
    # entry that no longer excludes anything is the pathology the base
    # layer's audit named.
    "$dispatch", "$bz.", "$el", "$refs", "$event", "$root",
)  # fmt: skip


# Ternary requires ``<expr> ? <a> : <b>``; we look for ``\s\?\s`` plus
# a colon later in the string. This is intentionally strict — a bare
# ``?`` in human text (``"What needs to be done ?"`` placeholder) used
# to be classified as a client expr and the value got emitted as ``:placeholder``,
# making the runtime try to evaluate the sentence as JS at runtime.
_TERNARY_RE = re.compile(r"\s\?\s.*:")
# Arrow function : ``)`` immediately before ``=>`` (catches both
# ``() => x`` and ``(a, b) => a + b``). Naked ``=>`` is not enough —
# CSS selectors and other strings can include it.
_ARROW_FN_RE = re.compile(r"\)\s*=>")
# No ``\s*`` between the identifier and ``(`` : real function calls
# never have a space there (``foo()`` / ``state.toggle()``), but
# prose does (``Sign up (free)`` / ``Email (work)``). The trailing
# whitespace allowance used to misclassify text as JS.
_FUNCTION_CALL_RE = re.compile(r"\b[a-zA-Z_$][a-zA-Z0-9_$]*\(")


def reads_as_client_expr(value: Any, owner: type, name: str) -> bool:
    """The whole question: is ``value``, set on THIS prop, code?

    Two halves, and the order matters:

    1. the **declaration** — ``reactive_prop(never_code=True)`` says this
       prop carries data. We do not guess;
    2. the **heuristic** — for everything else,
       :func:`looks_like_client_expr` sniffs the value.

    It lives here rather than inline in ``Component.__init__`` because it
    is ONE question, not two: separating the declaration from the
    heuristic let a caller read the second without the first — which is
    exactly the state before 2026-08-26, where the datatable's CSV export
    lost its ``href``.

    It takes ``(owner, name)`` rather than the already-resolved
    descriptor so as to fit in ONE call at the caller:
    ``Component.__init__`` is under a line ceiling
    (``test_the_choke_point_only_shrinks``), and a question that moves
    must not leave its resolution behind.
    """
    if not isinstance(value, str):
        return False
    descriptor = getattr(owner, "__reactive_props__", {}).get(name)
    if descriptor is not None and descriptor.never_code:
        return False
    return looks_like_client_expr(value)


def looks_like_client_expr(value: str) -> bool:
    """Heuristic: does ``value`` look like a client / JS expression?

    Returns ``True`` if it carries one of:
    - A leading ``$`` (runtime magics: ``$bz``, ``$dispatch``, ``$el``…).
    - A standalone ``<`` or ``>`` (comparison) — but never ``<=``/``>=`` only,
      we check the wider list above.
    - One of the client / JS markers in :data:`_CLIENT_EXPR_MARKERS`.
    - A function call: ``foo()`` or ``method()``.

    Returns ``False`` for plain identifiers (``primary``), CSS class
    strings, etc.

    ⚠️ **It does NOT protect URLs**, contrary to what this line promised
    until 2026-08-26 ("Returns False for … URLs (``/users/42``)"). That
    is true of ``/users/42``, which carries no marker — and false as soon
    as a URL carries one: a base64 padding (``==``), an ``&&`` in a query
    string. The promise held by the chosen example, not by the code, and
    three regressions came through there.

    A prop carrying a URL declares ``reactive_prop(never_code=True)``:
    the heuristic then does not run on it at all. It is the only
    mechanism — the shape exclusions (``data:``…) were removed with it.

    **The escape hatch, when the heuristic is wrong** — in both
    directions:

    - *it sees code where you wanted text* (``placeholder="a && b"``)
      → go through ``attrs={"placeholder": "a && b"}``. The ``attrs=``
      bucket short-circuits the heuristic and wins precedence over the
      named kwarg.
    - *you want to force a client expression* → write the directive
      yourself: ``**{"bz-attr:placeholder": "a && b"}``.

    ⚠️ This docstring long announced "force client binding via the
    explicit ``:attr_name="expr"``" — and ``:`` is an **Alpine** prefix,
    dead since V3. The documented escape hatch therefore did nothing at
    all, and since 2026-07-29 it raises (``reject_dead_alpine_attr``).
    There was no functional documented opt-out left; the two above are
    it.
    """
    if not isinstance(value, str) or not value:
        return False

    # Leading ``$`` — only when followed by an JS identifier
    # (letter / underscore / dot). Lone ``$`` (currency prefix) and
    # ``$<digit>`` (regex backref-like, ``$1.50``) are text, not
    # the runtime. Regression : the playground's ``prefix="$"`` control
    # used to emit ``:prefix="$"`` and the runtime crashed with
    # ``$ is not defined``.
    if value.startswith("$"):
        if len(value) > 1 and (
            value[1].isalpha() or value[1] == "_" or value[1] == "."
        ):
            return True
        return False

    # Strong markers : comparisons, logical ops, ternary, arrow fn.
    for marker in _CLIENT_EXPR_MARKERS:
        if marker in value:
            return True

    # Bare ``<`` or ``>`` as comparison — but skip cases where they're
    # part of HTML / templates passed verbatim. Conservative : only
    # treat as expression when surrounded by spaces (``a > 1``).
    if " < " in value or " > " in value:
        return True

    # Ternary : strict pattern with surrounding spaces + a colon later.
    if _TERNARY_RE.search(value):
        return True

    # Arrow function : the ``=>`` must come right after a ``)``.
    if _ARROW_FN_RE.search(value):
        return True

    # Function call. Catches ``foo()``, ``$bz._resolveIcon(…)``,
    # ``state.toggle()``. **Tightened (mai 2026)** : the match must sit
    # at the start of the string, optionally preceded ONLY by
    # identifier-chain chars (letters / digits / underscore / dot /
    # dollar). Without this, text content containing a parenthesised
    # aside (``Sign up (free)``) or HTML embedded JS
    # (``<script>alert(1)</script>``) was misclassified as a client expr
    # and the runtime crashed trying to evaluate it. Regression
    # reported via the Input playground Edge cases card.
    match = _FUNCTION_CALL_RE.search(value)
    if not match:
        return False
    prefix = value[: match.start()]
    if not prefix:
        return True
    return all(c.isalnum() or c in "_.$" for c in prefix)
