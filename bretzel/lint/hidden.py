"""Note: branches a ``ClientState`` hides with ``visible=``, rendered anyway.

The silence it closes
---------------------

``visible=`` bound to a ``ClientState`` hides in the browser; it removes
nothing from the HTML. Every branch is rendered by the server, shipped,
and redrawn by the actions that touch it, seen or not. For a menu, a
tooltip, two small cards (the structural mutex), that is the right price:
the switch costs no round trip. For a whole screen it is not. Measured on
Orga: the shell rendered its five apps in the main card AND,
compact, in the side panel, one visible on each side, under a persisted
``ClientState`` — half of a 338 KB page was hidden, and the compact list
of threads was redrawn at every opened thread, panel closed.

What decides WHICH heavy content to render is the server's to know: an
addressable ``PageState`` (``field(url=...)``) or a ``UserState``
preference, and the page renders only what is seen
(``choisir-etat-et-composant.md``).

What is noted
-------------

A ``with`` block whose ``visible=`` reads a ``ClientState`` of the corpus
(a holder ``d = Disposition()``, a parameter ``d: Disposition``, or
``Disposition().field`` itself), when the block

- **draws a zone**: it calls a ``@refreshable`` function, or a function
  of the corpus that does (followed by name, through any depth) — a zone
  is rendered and redrawn whether it is seen or not;
- or **is one branch per value**: it sits in a ``for`` loop and its
  condition is the state compared to the loop's variable
  (``d.app == key``, ``.eq(row["id"])``) — N branches, one seen.

Spared: a leaf call (``ui.icon(visible=...)`` holds nothing to weigh); a
server state (it is the server's choice already); and the structural
mutex — the same condition negated in the same loop
(``visible=chosen`` / ``visible=chosen.not_()``): two branches written by
hand, not one per value.

A note, not a finding (validated by Jean): light branches
are legitimate, and the measure that decides is the probe's — the share
of the page under ``display: none`` (``livrer-une-app.md``).

A zone is followed through calls BY NAME to a function the module
defines or imports: what it does not see is a dynamic call
(``screens[key]()``) or a method (``self.zone()``). The loop form catches
the shell whatever its branches call.

Read from ``Module.nodes`` alone, scopes by source span — the walk a pass
pays once (``test_lint_derives_the_corpus_once``).
"""

from __future__ import annotations

import ast
import inspect
from collections.abc import Iterator, Sequence
from dataclasses import dataclass, field
from functools import cache

from bretzel.lint.corpus import Module
from bretzel.lint.report import Finding
from bretzel.lint.rules._app_calls import keyword

NOTE = "hidden-branch-rendered"

_HINT = (
    "If the branches are heavy (an app, a panel, the tab of a heavy screen), "
    "choose WHICH to render on the server: an addressable `PageState` "
    "(`field(url=...)`) or a `UserState` preference, and render only that one "
    "— choisir-etat-et-composant.md. Light branches (a menu, two small cards) "
    "stay as they are; `bretzel probe` measures the hidden share of the page."
)

#: ``(line, column, end line, end column)`` — where a node sits.
Span = tuple[int, int, int, int]
_Loop = ast.For | ast.AsyncFor
_With = ast.With | ast.AsyncWith


def _span(node: ast.AST) -> Span:
    line = getattr(node, "lineno", 0)
    return (line, getattr(node, "col_offset", 0),
            getattr(node, "end_lineno", None) or line,
            getattr(node, "end_col_offset", None) or 0)


def _inside(inner: Span, outer: Span) -> bool:
    return inner[:2] >= outer[:2] and inner[2:] <= outer[2:]


def _name(node: ast.expr) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    if isinstance(node, ast.Call):
        return _name(node.func)
    return None


def _visible(node: ast.AST) -> ast.expr | None:
    return keyword(node, "visible") if isinstance(node, ast.Call) else None


@cache
def _framework_client_states() -> frozenset[str]:
    """The public ``ClientState`` classes, derived and not copied — the
    seed of the corpus's own (``ColorScheme``, ``LiveConnection``…)."""
    import bretzel
    import bretzel.state as state_module
    from bretzel.state import ClientState

    return frozenset(
        name for module in (bretzel, state_module) for name in dir(module)
        if inspect.isclass(obj := getattr(module, name, None)) and issubclass(obj, ClientState)
    )


#: The node kinds :class:`_Facts` keeps as they are, by exact type — a
#: lookup per node, where a chain of ``isinstance`` cost most of the note.
_KEPT = {
    ast.ClassDef: "classes", ast.With: "withs", ast.AsyncWith: "withs",
    ast.For: "loops", ast.AsyncFor: "loops", ast.Assign: "assigns",
    ast.Attribute: "attributes", ast.Name: "names",
}


@dataclass
class _Facts:
    """What one module holds, sorted out of ``Module.nodes`` in one pass."""

    module: Module
    functions: list[ast.FunctionDef | ast.AsyncFunctionDef] = field(default_factory=list)
    classes: list[ast.ClassDef] = field(default_factory=list)
    #: The names a call here may reach a function of the corpus by: the
    #: module's own functions and what it imports by name. A method call
    #: (``row.get()``) is left out — matched by its attribute alone, it hit
    #: any function of the corpus with the same name.
    here: set[str] = field(default_factory=set)
    calls: list[tuple[Span, str]] = field(default_factory=list)
    withs: list[_With] = field(default_factory=list)
    loops: list[_Loop] = field(default_factory=list)
    visibles: list[tuple[Span, ast.expr]] = field(default_factory=list)
    assigns: list[ast.Assign] = field(default_factory=list)
    args: list[ast.arg] = field(default_factory=list)
    attributes: list[ast.Attribute] = field(default_factory=list)
    names: list[ast.Name] = field(default_factory=list)

    @classmethod
    def of(cls, module: Module) -> _Facts:
        facts = cls(module)
        for node in module.nodes:
            kind = type(node)
            if (kept := _KEPT.get(kind)) is not None:
                getattr(facts, kept).append(node)
            elif kind is ast.Call:
                if isinstance(node.func, ast.Name):
                    facts.calls.append((_span(node), node.func.id))
                if (value := _visible(node)) is not None:
                    facts.visibles.append((_span(node), value))
            elif kind is ast.arg and node.annotation is not None:
                facts.args.append(node)
            elif kind is ast.FunctionDef or kind is ast.AsyncFunctionDef:
                facts.functions.append(node)
                facts.here.add(node.name)
            elif kind is ast.ImportFrom:
                facts.here.update(a.asname or a.name for a in node.names)
        return facts

    def called_in(self, span: Span) -> Iterator[str]:
        """The names called inside ``span`` that may reach a corpus function."""
        return (name for at, name in self.calls if name in self.here and _inside(at, span))

    def names_in(self, span: Span) -> set[str]:
        return {n.id for n in self.names if _inside(_span(n), span)}


def _client_classes(all_facts: Sequence[_Facts]) -> set[str]:
    """The ``ClientState`` classes: the framework's, and the corpus's
    subclasses of them through any depth."""
    defs = [c for f in all_facts for c in f.classes]
    known = set(_framework_client_states())
    grew = True
    while grew:
        grew = False
        for cls in defs:
            if cls.name not in known and any(_name(b) in known for b in cls.bases):
                known.add(cls.name)
                grew = True
    return known


def _zone_drawers(all_facts: Sequence[_Facts]) -> dict[str, str]:
    """Function name → the zone it draws, directly or through calls."""
    calls = [(fn.name, sorted(set(f.called_in(_span(fn)))))
             for f in all_facts for fn in f.functions]
    drawers = {fn.name: fn.name for f in all_facts for fn in f.functions
               if any(_name(d) == "refreshable" for d in fn.decorator_list)}
    grew = True
    while grew:
        grew = False
        for name, called in calls:
            if name in drawers:
                continue
            zone = next((drawers[c] for c in called if c in drawers), None)
            if zone is not None:
                drawers[name] = zone
                grew = True
    return drawers


class _Reader:
    """What one module's ``visible=`` conditions read."""

    def __init__(self, facts: _Facts, classes: set[str]) -> None:
        holders: dict[str, str] = {}
        for node in facts.assigns:
            if (isinstance(node.value, ast.Call)
                    and (cls := _name(node.value.func)) in classes):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        holders[target.id] = cls
        for arg in facts.args:
            ann = arg.annotation
            ann_name = ann.value if isinstance(ann, ast.Constant) else _name(ann)  # type: ignore[arg-type]
            if isinstance(ann_name, str) and ann_name in classes:
                holders[arg.arg] = ann_name
        #: Each read of a ``ClientState`` field, and its class.
        self.reads: list[tuple[Span, str]] = []
        for node in facts.attributes:
            owner = node.value
            if isinstance(owner, ast.Name) and owner.id in holders:
                self.reads.append((_span(node), holders[owner.id]))
            elif isinstance(owner, ast.Call) and (cls := _name(owner.func)) in classes:
                self.reads.append((_span(node), cls))
        # A condition named once (``chosen = Pick().pupil.eq(pid)``), so
        # that ``visible=chosen`` and ``visible=chosen.not_()`` resolve.
        self.named: dict[str, ast.expr] = {
            node.targets[0].id: node.value for node in facts.assigns
            if len(node.targets) == 1 and isinstance(node.targets[0], ast.Name)
            and self.client_of(node.value)}

    def client_of(self, expr: ast.expr) -> str | None:
        """The ``ClientState`` class ``expr`` reads a field of, if any."""
        span = _span(expr)
        return next((cls for at, cls in self.reads if _inside(at, span)), None)

    def split(self, expr: ast.expr) -> tuple[ast.expr, bool]:
        """``(condition, negated)``, a named condition resolved."""
        negated = False
        if (isinstance(expr, ast.Call) and isinstance(expr.func, ast.Attribute)
                and expr.func.attr == "not_" and not expr.args):
            expr, negated = expr.func.value, True
        elif isinstance(expr, ast.UnaryOp) and isinstance(expr.op, ast.Invert):
            expr, negated = expr.operand, True
        if isinstance(expr, ast.Name) and expr.id in self.named:
            expr = self.named[expr.id]
        return expr, negated


def _compared_to(facts: _Facts, cond: ast.expr, loop_names: set[str]) -> bool:
    """``cond`` is ``<state> == <loop variable>`` (or ``.eq(...)``) — the
    variable, or a value taken from it (``row["id"]``)."""
    sides: list[ast.expr] = []
    if (isinstance(cond, ast.Compare) and len(cond.ops) == 1
            and isinstance(cond.ops[0], ast.Eq)):
        sides = [cond.left, cond.comparators[0]]
    elif (isinstance(cond, ast.Call) and isinstance(cond.func, ast.Attribute)
            and cond.func.attr == "eq" and len(cond.args) == 1):
        sides = [cond.func.value, cond.args[0]]
    return any(facts.names_in(_span(side)) & loop_names for side in sides)


def _loops_around(facts: _Facts, block: _With) -> list[_Loop]:
    """The loops around ``block`` in its own function, innermost first."""
    at = _span(block)
    scopes = [_span(fn)[:2] for fn in facts.functions if _inside(at, _span(fn))]
    floor = max(scopes) if scopes else (0, 0)
    loops = [lp for lp in facts.loops if _inside(at, _span(lp)) and _span(lp)[:2] > floor]
    return sorted(loops, key=_span, reverse=True)


def _mutex(facts: _Facts, loop: _Loop, cond: ast.expr, reader: _Reader) -> bool:
    """The same condition, negated, on another branch of the same loop."""
    shape, span = ast.dump(cond), _span(loop)
    return any(negated and ast.dump(other) == shape
               for at, value in facts.visibles if _inside(at, span)
               for other, negated in [reader.split(value)])


def _hidden_blocks(facts: _Facts, reader: _Reader
                   ) -> Iterator[tuple[_With, ast.expr, str, bool]]:
    """``(block, condition, class, negated)`` for each ``with`` whose
    ``visible=`` reads a ``ClientState``."""
    for block in facts.withs:
        for item in block.items:
            value = _visible(item.context_expr)
            if value is None:
                continue
            cond, negated = reader.split(value)
            if (cls := reader.client_of(cond)) is not None:
                yield block, cond, cls, negated


def _module_notes(facts: _Facts, reader: _Reader,
                  drawers: dict[str, str]) -> Iterator[Finding]:
    for block, cond, cls, negated in _hidden_blocks(facts, reader):
        body = (*_span(block.body[0])[:2], *_span(block)[2:])
        zone = next((drawers[n] for n in facts.called_in(body) if n in drawers), None)
        if zone is not None:
            message = (f"`visible=` bound to the ClientState `{cls}` hides a block "
                       f"that draws the zone `{zone}`: the server renders it, and "
                       "redraws it, while it is hidden.")
        else:
            if negated:
                continue
            loop = next((lp for lp in _loops_around(facts, block)
                         if _compared_to(facts, cond, facts.names_in(_span(lp.target)))),
                        None)
            if loop is None or _mutex(facts, loop, cond, reader):
                continue
            message = (f"`visible=` bound to the ClientState `{cls}` draws one branch "
                       "per value of the loop: all are rendered, and redrawn, for "
                       "one seen.")
        yield Finding(rule=NOTE, path=facts.module.path, line=block.lineno,
                      message=message, hint=_HINT)


def notes(found: Sequence[Module]) -> list[Finding]:
    """One note per ``with`` block hiding heavy content under a ``ClientState``."""
    all_facts = [_Facts.of(m) for m in found]
    classes = _client_classes(all_facts)
    if not classes:
        return []
    drawers = _zone_drawers(all_facts)
    out = [n for f in all_facts for n in _module_notes(f, _Reader(f, classes), drawers)]
    out.sort(key=lambda f: (f.path.as_posix(), f.line))
    return out


def watched(found: Sequence[Module]) -> int:
    """How many ``with`` blocks carry a ``visible=`` bound to a ``ClientState``
    — the population the note judges, for a gate's floor."""
    all_facts = [_Facts.of(m) for m in found]
    classes = _client_classes(all_facts)
    return sum(1 for f in all_facts for _ in _hidden_blocks(f, _Reader(f, classes)))
