"""The text emitter — two granularities, and that is the design's point.

A complete card × 104 components does not fit in context and does not
read. Hence:

- :func:`render_index` — **one line per symbol**, the whole surface. It
  is what stays loaded permanently: it answers "does ``justify`` exist on
  ``hstack``?", which is the question whose wrong answer produces a
  workaround (``classes="justify-between"``).
- :func:`render_detail` — ONE symbol's whole card, on demand.

The cheap index always present, the detail one command away.
"""

from __future__ import annotations

from bretzel.introspect.components import RESERVED_KWARGS, describe_components
from bretzel.introspect.model import (
    SOURCE_REACTIVE_PROP,
    AlgebraOp,
    ComponentInfo,
    HelperInfo,
    MethodInfo,
    ModuleSection,
    ParamInfo,
    StateInfo,
    SymbolDetail,
)

_INDENT = " " * 4

#: Beyond that, a doc line stops fitting on an index line.
_DOC_CLIP = 62


def _names(params: tuple[ParamInfo, ...]) -> str:
    return " ".join(p.name for p in params)


def render_index() -> str:
    """One line per ``ui.*`` symbol — plus a contracts line when the
    component carries any."""
    catalogue = describe_components()
    components = [i for i in catalogue if isinstance(i, ComponentInfo)]
    helpers = [i for i in catalogue if isinstance(i, HelperInfo)]

    width = max((len(i.ui_name) for i in catalogue), default=0) + 3

    out: list[str] = [
        f"# ui.* API — {len(components)} components, {len(helpers)} helpers",
        "",
        "Read directly from the live code, so this index cannot drift from the API.",
        "Generated on demand with `bretzel describe`.",
        "",
        "Every component ALSO accepts these universal keyword arguments, omitted",
        f"below for brevity: {', '.join(RESERVED_KWARGS)}.",
        "",
        "A `click` event is written as `on_click=`. Pass a slot by its name.",
        "Full details for one entry: `describe <name>`.",
        "",
    ]

    for info in components:
        head = f"ui.{info.ui_name}".ljust(width)
        props = _names(tuple(p for p in info.params if not p.name.startswith("on_")))
        out.append(f"{head}{info.family:<12} <{info.tag}>  {props}")
        contracts: list[str] = []
        if info.handler_kwargs:
            contracts.append(" ".join(info.handler_kwargs))
        if info.named_slots:
            contracts.append("slots: " + " ".join(info.named_slots))
        if info.imperative:
            contracts.append("imperative: " + " ".join(info.imperative))
        if contracts:
            out.append(f"{' ' * width}{' · '.join(contracts)}")

    if helpers:
        out.extend(["", "## Helpers (not components)", ""])
        for helper in helpers:
            head = f"ui.{helper.ui_name}".ljust(width)
            out.append(f"{head}{helper.kind:<18} {_names(helper.params)}")

    out.append(render_modules())
    out.append(render_kwarg_routing())
    out.append(render_bindable_matrix())
    return "\n".join(out)


def render_detail(info: ComponentInfo | HelperInfo) -> str:
    """A symbol's complete card."""
    if isinstance(info, HelperInfo):
        return _render_helper(info)
    return _render_component(info)


def _prologue(title: str, doc: str | None, params: tuple[ParamInfo, ...]) -> list[str]:
    """The card's head, common to components and helpers.

    The two halves diverged by a trailing blank line — an oversight, not
    a decision, and everything that followed in the component card
    assumed the line was there."""
    out = [title, ""]
    if doc:
        out.extend([doc, ""])
    if params:
        out.append("Parameters")
        out.extend(_param_lines(params))
        out.append("")
    return out


def _row(label: str, values: tuple[str, ...], suffix: str = "") -> str:
    """One contract line. The alignment lives HERE and not in four
    literals counted by eye — renaming "Imperative" can no longer shift
    the column silently."""
    return f"{label:<12}" + (", ".join(values) + suffix if values else "—")


def _render_helper(info: HelperInfo) -> str:
    return "\n".join(
        _prologue(f"ui.{info.ui_name}   ({info.kind})", info.doc, info.params)
    ).rstrip()


def _render_component(info: ComponentInfo) -> str:
    shape = "container" if info.is_container else "leaf"
    title = f"ui.{info.ui_name} → {info.class_name}   ({info.family}, <{info.tag}>, {shape})"
    out = _prologue(title, info.doc, info.params)

    audited = "" if info.bindable_audited else "   ⚠ not audited (BINDABLE_PROPS missing)"
    out.append(
        _row("Bindable", info.bindable, audited)
        if info.bindable
        else "Bindable    — (no property supports client-side binding)"
    )
    out.append(_row("Events", info.handler_kwargs))
    out.append(_row("Slots", info.named_slots))
    out.append(_row("Imperative", info.imperative))
    if info.autoname_from:
        out.append(_row("Autoname", (f"from {info.autoname_from}",)))
    out.extend(_theme_lines(info))

    out.extend(["", f"Accepted universal keyword arguments: {', '.join(RESERVED_KWARGS)}"])
    return "\n".join(out)


def render_symbol(detail: SymbolDetail) -> str:
    """The card of a symbol outside ``ui.*``.

    Same shape as the component card — title, docstring, parameters, then
    the contracts as ``label / values`` lines — so that a reader who has
    seen one knows how to read the other. What changes is what the
    symbol's nature allows one to say: a constant has only a value, a
    class has methods, ``ClientBinding`` has its algebra.
    """
    kind = detail.kind
    category = detail.category
    title = f"{detail.name} → {detail.module}   ({kind}, {category})"
    out = _prologue(title, detail.doc, detail.signature.params if detail.signature else ())

    if detail.value_repr is not None:
        out.append(_row("Value", (detail.value_repr,)))
    if detail.state is not None:
        out.append(_row("Scope", (detail.state.scope,)))
        out.extend(_state_url_lines(detail.state))
        out.extend(_state_field_lines(detail.state))
    if len(detail.exported_by) > 1:
        others = tuple(m for m in detail.exported_by if m != detail.module)
        out.append(_row("Also in", others, "   (the same object, re-exported)"))
    if detail.also_known_as:
        out.append(_row("Namesake", detail.also_known_as, "   (a DIFFERENT object)"))

    out.extend(_method_lines(detail.methods))
    out.extend(_algebra_lines(detail.algebra))
    return "\n".join(out).rstrip()


def _state_url_lines(state: StateInfo) -> list[str]:
    """What the state publishes in the ADDRESS, and under what name.

    The question no card could answer. A reader writing
    ``class Issues(DatatableState, addressable=True)`` cannot guess
    ``?sort=&dir=&p=``: the names are written on the PARENT's fields, a
    file they have no reason to open. Measured on 2026-09-06 — the
    question was asked, and the answer required reading
    ``state/datatable/state.py``.

    Three states, and distinguishing them IS the information:

    - published — the line names the parameters, and says the rest does
      not go out (that is the guarantee keeping ``filters`` out of the
      URL);
    - named but **off** — only ``addressable=True`` is missing, which no
      other reading would say;
    - nothing at all — the framework's default everywhere, where we write
      no line rather than an "Addressable —" that would read as a failed
      reading.
    """
    if state.url_error:
        return [_row("Addressable", (f"⚠ invalid declaration — {state.url_error}",))]
    if state.url_params:
        return [_row(
            "Addressable",
            tuple(f"{field}→{param}" for field, param in state.url_params),
            "   (a field omitted from this line is NEVER written to the URL)",
        )]
    if state.url_named:
        named = ", ".join(f"{field}→{param}" for field, param in state.url_named)
        return [_row(
            "Addressable",
            ("— disabled",),
            f"   (`addressable=True` would publish {named})",
        )]
    return []


def _state_field_lines(state: StateInfo) -> list[str]:
    """A state class's fields.

    The five BASE classes have none, and that is expected — their card
    stops at the scope. Write nothing in that case rather than a
    "Fields —" that would read as a failed reading."""
    if not state.fields:
        return []
    out = ["Fields"]
    out.extend(
        _param_lines(
            tuple(
                ParamInfo(
                    name=f.name,
                    kind="keyword-only",
                    type_label=f.type_label,
                    default_label=f.default_label,
                )
                for f in state.fields
            )
        )
    )
    if state.computed:
        out.append(_row("Computed", state.computed))
    return out


def _method_lines(methods: tuple[MethodInfo, ...]) -> list[str]:
    """The public methods, one per line, with their signature.

    The name alone is not enough: ``Language.set`` and ``auth.login``
    read from their arguments, and that is precisely what no index line
    could carry."""
    if not methods:
        return []
    out = ["", "Methods"]
    width = max(len(m.name) for m in methods) + 2
    for method in methods:
        call = f"{method.name}({_names(method.params)})"
        out.append(f"{_INDENT}{call:<{width + 14}}-> {method.returns_label}")
        if method.doc:
            out.append(f"{_INDENT}{_INDENT}{method.doc.splitlines()[0]}")
    return out


def _algebra_lines(ops: tuple[AlgebraOp, ...]) -> list[str]:
    """The Python→JS algebra, grouped by category.

    The JS shown is **captured at runtime** by
    :mod:`~bretzel.introspect.algebra`'s probe, not copied: what is
    displayed is what the component will emit."""
    if not ops:
        return []
    out = ["", "Python → JS algebra (JavaScript captured at runtime)"]
    current = ""
    width = max(len(op.python) for op in ops) + 3
    for op in ops:
        if op.category != current:
            current = op.category
            out.append(f"  {current}")
        out.append(f"{_INDENT}{op.python:<{width}}{op.js or '—'}")
    return out


def _theme_lines(info: ComponentInfo) -> list[str]:
    """The theme vocabulary — one line per group.

    The VALUES are not shown: 70 855 characters of Tailwind classes
    across the whole catalogue, which the code already says better. What
    could be read nowhere is the list of names one is allowed to write in
    ``Theme(components=…)``.

    The key is repeated when it differs from the ``ui.*`` name: three
    components write under ANOTHER's theme (``sidebar_section`` →
    ``sidebar``), and nobody guesses that.
    """
    if not info.theme:
        return []
    head = "Theme"
    if info.theme_key and info.theme_key != info.ui_name:
        head = f"Theme (key: {info.theme_key})"
    out = ["", f"{head} — Theme(components={{{info.theme_key!r}: {{…}}}})"]
    for group, keys in info.theme:
        out.append(f"  {group:<14}" + (", ".join(keys) if keys else "— (single value)"))
    # The keys of ``sizes`` are NOT the values of ``size=``: on 33 of
    # the catalogue's 44 tables they name SLOTS (``date_picker`` shows
    # ``input_field, clear_button…``), and reading the raw line makes one
    # write ``size="input_field"``. That is the exact mistake a first
    # version of the ``value-outside-the-table`` rule made by reading it.
    # The resolved line cuts that short, and it also carries the extended
    # scales (``heading`` up to ``8xl``, ``avatar`` up to ``2xl``).
    if info.size_values and tuple(info.size_values) != tuple(dict(info.theme).get("sizes", ())):
        out.append(f"  {'size= values':<14}" + ", ".join(info.size_values))
    return out


def _param_lines(params: tuple[ParamInfo, ...]) -> list[str]:
    """The parameters, aligned. A reactive prop is marked: its absence
    from the ``__init__`` is an API decision, not an accident, and the
    reader must know it goes through ``**kwargs``."""
    if not params:
        return []
    name_w = max(len(p.name) for p in params) + 2
    type_w = max(len(p.type_label) for p in params) + 2
    return [
        f"{_INDENT}{p.name:<{name_w}}{p.type_label:<{type_w}}"
        f"{f'= {p.default_label}' if p.default_label else ''}"
        f"{'   (reactive property)' if p.source == SOURCE_REACTIVE_PROP else ''}"
        for p in params
    ]


def render_module(section: ModuleSection) -> str:
    """A module section, grouped by need.

    Every symbol fits on one line with the first line of its docstring,
    truncated: the index answers "what exists and what is it for", not
    "what is the exact signature".
    """
    out: list[str] = [f"## {section.name}", ""]
    if not section.covered:
        out.extend(["(section not covered — no category mapping defined)", ""])
        return "\n".join(out)

    current = ""
    width = max((len(s.name) for s in section.symbols), default=0) + 2
    for symbol in section.symbols:
        if symbol.category != current:
            current = symbol.category
            out.append(f"  {current}")
        doc = (symbol.summary or "").strip()
        if len(doc) > _DOC_CLIP:
            doc = doc[: _DOC_CLIP - 1].rstrip() + "…"
        kind = symbol.kind
        out.append(f"    {symbol.name:<{width}}{kind:<11} {doc}")
    out.append("")
    return "\n".join(out)


def render_modules() -> str:
    """Every module section, in reading order."""
    from bretzel.introspect.modules import describe_modules

    out = ["", "# Module API", ""]
    out.extend(render_module(section) for section in describe_modules())
    return "\n".join(out).rstrip()


def render_kwarg_routing() -> str:
    """Kwarg routing, DERIVED from the base layer's constants.

    This table was written by hand in ``kwarg-routing.md`` and carried
    three false claims there simultaneously. Generated, it can no longer
    carry any — it is the only remedy that survived the measurement
    (three prose gate candidates were set aside, cf.
    :mod:`bretzel.introspect.routing`).
    """
    from bretzel.introspect.routing import describe_kwarg_routing

    buckets = describe_kwarg_routing()
    width = max(len(b.name) for b in buckets) + 2
    out = [
        "",
        "# Keyword argument routing — `split_kwargs` buckets",
        "",
        "GENERATED from framework constants, so this table cannot drift from",
        "what the framework accepts or rejects.",
        "",
    ]
    for bucket in buckets:
        accepts = " ".join(bucket.accepts)
        if len(accepts) > 78:
            accepts = accepts[:77] + "…"
        out.append(f"{bucket.rank}. {bucket.name:<{width}} → {bucket.outcome}")
        out.append(f"{' ' * (width + 5)}{accepts}")
    return "\n".join(out)


def render_bindable_matrix() -> str:
    """Each component's bindable surface, DERIVED.

    This matrix was written by hand in ``kwarg-routing.md`` — 70 lines,
    one component per line, with the binding's direction noted ``⇄`` /
    ``→`` / ``∅``. ``test_bindable_surface`` guarded it indirectly: it
    turns red when the code changes, which **forces the funnel to be
    updated** — it does not check that the update was done correctly.

    Derived, the manual step disappears. ``⇄`` = the client writes
    (``TWO_WAY_PROPS``), ``→`` = read-only, absent = static.
    """
    from bretzel.introspect.components import describe_components
    from bretzel.introspect.model import ComponentInfo

    infos = [i for i in describe_components() if isinstance(i, ComponentInfo)]
    bindables = [i for i in infos if i.bindable]
    out = [
        "",
        f"# Bindable API — {len(bindables)} of {len(infos)} components",
        "",
        "GENERATED. `⇄` means the client WRITES the value (`TWO_WAY_PROPS`); `→`",
        "is read-only. A component omitted here has NO bindable properties; any",
        "binding raises `ComponentUsageError` by design.",
        "",
    ]
    width = max((len(i.ui_name) for i in bindables), default=0) + 3
    for info in sorted(bindables, key=lambda i: (i.family, i.ui_name)):
        props = " ".join(f"{p}{'⇄' if p in info.two_way else '→'}" for p in info.bindable)
        audited = "" if info.bindable_audited else "   ⚠ not audited"
        out.append(f"ui.{info.ui_name:<{width}}{info.family:<12} {props}{audited}")
    return "\n".join(out)
