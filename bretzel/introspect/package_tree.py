"""The folder TREE — the framework describes its own layout.

⚠️ **Not to be confused with ``packages.py``, its folder neighbour**,
which deals with an entirely different subject: the components published
by installed THIRD-PARTY packages. Here it is Bretzel's own tree. The two
names look alike enough that one overwrites one believing one is creating
the other — that happened on 2026-09-02, and it was the suite's 216 reds
that said so, not the re-reading.

``describe_module`` reads a hand-written table: seven modules classified
symbol by symbol. That is precise, and it is **blind to the rest** —
``bretzel.components.inputs`` is a real package, with a real docstring,
and introspection answered "does not exist".

Measured on 2026-09-02: **117 folders under ``bretzel/``, 117 have a
package docstring, none missing.** The material to describe itself
therefore already exists in full — nobody was reading it.

This module reads it. It classifies nothing and invents nothing: it walks
the tree, takes the docstring the folder already carries, and returns the
hierarchy. ``modules.py``'s per-need classification stays laid ON TOP, on
the seven modules that have it — the two complement each other, they do
not replace each other.

Why it cannot rot
-----------------
Because the source is the folder itself. A hand-written list drifts as
soon as one adds a package without thinking about it; here, a new package
appears on its own, and its docstring is what its author wrote when
creating it. The only thing to keep is that it has one —
``test_every_package_describes_itself`` takes care of that.

It is the same lesson as the ``bretzel-api`` skill deleted on 2026-08-01:
a hand-copied catalogue drifts faster than it serves. The difference
between the two is knowing WHO the source is.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass, field
from functools import cache
from pathlib import Path

#: The installed package's root. Read from this file rather than through
#: ``importlib``: we want the FILE TREE, not what Python was willing to
#: import — a broken package must appear, not disappear.
_ROOT = Path(__file__).resolve().parent.parent


@dataclass(frozen=True, slots=True)
class SymbolLine:
    """A module's public symbol, and its first line.

    Not a card: a component's full detail lives in
    ``describe_ui_symbol``, which reads the REAL class (params, slots,
    events). Here we only want "what is there, and what it is for", read
    from the AST — so without importing anything.
    """

    name: str
    kind: str          # "function" | "class"
    summary: str


@dataclass(frozen=True, slots=True)
class ModuleInfo:
    """A ``.py`` module, its reason to exist, and what it exposes."""

    name: str
    summary: str
    symbols: tuple[SymbolLine, ...] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class PackageNode:
    """A package, its reason to exist, and what it contains."""

    #: The dotted path, ``bretzel.components.inputs``.
    name: str
    #: The FIRST line of its docstring — what it does, in one sentence.
    summary: str
    #: Its whole docstring, for whoever wants the detail.
    doc: str
    #: Its subpackages, sorted.
    children: tuple[PackageNode, ...] = field(default_factory=tuple)
    #: The ``.py`` modules it carries in its own right (excluding
    #: ``__init__``), with their first line AND their public symbols. A
    #: private module (``_x.py``) is one of them: it counts in the layout
    #: even if it is not part of the API.
    modules: tuple[ModuleInfo, ...] = field(default_factory=tuple)

    @property
    def depth(self) -> int:
        return self.name.count(".")


def _docstring_of(path: Path) -> str:
    """A file's docstring, or ``""``.

    ⚠️ ``utf-8-sig`` and not ``utf-8``: ``bretzel/render/__init__.py``
    carried a BOM that the latter leaves at the head of the string and
    that ``ast`` refuses — one file out of 344 thus dropped out of seven
    gates' sweep, for months. The shared reader in ``tests/consistency``
    carries the same fix, for the same reason.
    """
    try:
        tree = ast.parse(path.read_text(encoding="utf-8-sig"))
    except (SyntaxError, UnicodeDecodeError, OSError):
        return ""
    return ast.get_docstring(tree) or ""


def _first_line(doc: str) -> str:
    """The first PARAGRAPH, lines re-joined — not the first line.

    ⚠️ **The difference is not cosmetic, it is measured.** Taking the
    first *line* cut **68 summaries out of 592 (11 %)** in the middle of
    a sentence, because the author had wrapped their sentence at 79
    columns:

        Stable 8-char hex digest used to compress IDs (and other stable

    The reader did not see a short sentence, they saw a false one — and
    nothing on screen said half of it was missing.

    The paragraph repairs **all 68, at no cost**: the median length is
    the same (59 characters), because the vast majority of summaries
    already fit on one line. Only 9 exceed 200 characters.

    We stop at the first EMPTY line: the rest of a docstring is the
    detail, and a summary must stay a summary.
    """
    block: list[str] = []
    for line in doc.strip().splitlines():
        if not line.strip():
            break
        block.append(line.strip())
    return " ".join(block)


def _is_package(path: Path) -> bool:
    return path.is_dir() and (path / "__init__.py").exists()


def _module_info(path: Path) -> ModuleInfo:
    """The module, its sentence, and its top-level public symbols.

    Why we descend that far (2026-09-02)
    ------------------------------------
    Because the level above is often EMPTY. Measured: **73 of the 117
    package docstrings are stubs** of the form "icon_button component.",
    while the module just below says "IconButton — square button whose
    only content is an icon".

    The content exists, it is one notch lower: **608 public symbols, 592
    documented — 97 %**. Descending therefore costs less than rewriting
    73 folder docstrings — and gives text somebody wrote thinking about
    what they were doing, not to fill a box.

    ⚠️ Read from the AST, so WITHOUT importing. A module that breaks on
    import stays described — and that is intended: a repository's
    documentation must survive a file under construction.
    """
    doc_module = _docstring_of(path)
    symbol_lines: list[SymbolLine] = []
    try:
        tree = ast.parse(path.read_text(encoding="utf-8-sig"))
    except (SyntaxError, UnicodeDecodeError, OSError):
        tree = None
    if tree is not None:
        for n in tree.body:
            if isinstance(n, ast.ClassDef):
                kind = "class"
            elif isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
                kind = "function"
            else:
                continue
            if n.name.startswith("_"):
                continue
            symbol_lines.append(SymbolLine(
                name=n.name, kind=kind,
                summary=_first_line(ast.get_docstring(n) or ""),
            ))
    return ModuleInfo(
        name=path.stem, summary=_first_line(doc_module),
        symbols=tuple(symbol_lines),
    )


@cache
def describe_package(name: str = "bretzel") -> PackageNode:
    """The tree starting from ``name``, docstrings included.

    ``name`` is a dotted path (``bretzel.components.inputs``). Raises
    ``ValueError`` when it does not designate a package — and the message
    says what EXISTS at the requested level, because a typo in a folder
    name is the common case.

    Memoised, and it took measuring to see it
    -----------------------------------------
    Walking the tree parses **344 files at the AST level**, which cost
    **740 ms ON EVERY CALL**. The package's eight other readers have
    carried a ``@cache`` forever; this one did not, and it was the most
    expensive of all — 150 times ``index()``, which takes 4.7 ms.

    ``examples/docs``'s ``/tree`` page called it TWICE per request (here,
    then through :func:`package_names`): **1 340 ms** for one page,
    against 132 ms for ``/components``.

    Safe because the result is immutable: ``PackageNode`` is a ``frozen``
    whose every field is a string or a tuple of ``frozen``. No caller can
    therefore corrupt the cached entry.

    ⚠️ The source is the FILE SYSTEM, not a Python object: a folder added
    during the process's life does not appear. In dev it does not show —
    ``mode="dev"`` restarts the process at the slightest file touched —
    and a script fabricating packages on the fly calls
    ``describe_package.cache_clear()``, as ``third_party_components``
    does.
    """
    parts = name.split(".")
    if parts[0] != "bretzel":
        raise ValueError(
            f"describe_package({name!r}): the packages described here "
            f"live under ``bretzel``. For a symbol, it is "
            f"``describe_ui_symbol``."
        )
    path = _ROOT.joinpath(*parts[1:])
    if not _is_package(path):
        siblings = sorted(
            p.name for p in path.parent.iterdir() if _is_package(p)
        ) if path.parent.is_dir() else []
        raise ValueError(
            f"``{name}`` is not a package. At the same level: "
            f"{', '.join(siblings) or '(none)'}."
        )
    return _build(name, path)


def _build(name: str, path: Path) -> PackageNode:
    doc = _docstring_of(path / "__init__.py")
    enfants = tuple(
        _build(f"{name}.{p.name}", p)
        for p in sorted(path.iterdir())
        if _is_package(p) and p.name != "__pycache__"
    )
    modules = tuple(
        _module_info(p)
        for p in sorted(path.glob("*.py"))
        if p.name != "__init__.py"
    )
    return PackageNode(
        name=name, summary=_first_line(doc), doc=doc,
        children=enfants, modules=modules,
    )


def walk(node: PackageNode) -> list[PackageNode]:
    """The node and all its descendants, depth first."""
    out = [node]
    for child in node.children:
        out.extend(walk(child))
    return out


def package_names(root: str = "bretzel") -> tuple[str, ...]:
    """Every package under ``root``, dotted paths, sorted."""
    return tuple(n.name for n in walk(describe_package(root)))


def render_tree(node: PackageNode, *, max_depth: int | None = None) -> str:
    """The tree as text — what ``bretzel describe <package>`` shows.

    ``max_depth`` counts FROM the requested node, not from the root:
    ``describe bretzel --depth 1`` shows the big blocks,
    ``describe bretzel.components --depth 1`` shows its groups.
    """
    lines: list[str] = []
    base = node.depth

    def _write(n: PackageNode) -> None:
        relative = n.depth - base
        if max_depth is not None and relative > max_depth:
            return
        indent = "  " * relative
        summary = f"  — {n.summary}" if n.summary else ""
        lines.append(f"{indent}{n.name.split('.')[-1]}/{summary}")
        for child in n.children:
            _write(child)

    _write(node)
    return "\n".join(lines)


def render_package(node: PackageNode) -> str:
    """A package's card — its reason to exist, its tree, its modules.

    Deliberately SHORTER than a symbol's card: one comes here to know
    "what is in there", not to read a signature. A symbol's detail stays
    ``describe <name>``.
    """
    lines = [f"## {node.name}", ""]
    if node.doc:
        # The whole docstring, indented — it is what the package's
        # author wrote, and rephrasing it would make the two diverge.
        for line in node.doc.strip().splitlines():
            lines.append(f"  {line}" if line.strip() else "")
        lines.append("")

    if node.children:
        lines.append(f"  Subpackages ({len(node.children)})")
        for child in node.children:
            short = child.name.split(".")[-1]
            summary = f"  — {child.summary}" if child.summary else ""
            lines.append(f"    {short}/{summary}")
        lines.append("")

    if node.modules:
        lines.append(f"  Modules ({len(node.modules)})")
        for mod in node.modules:
            lines.append(f"    {mod.name:<24}{mod.summary}")
            for sym in mod.symbols:
                lines.append(f"      {sym.name:<22}{sym.summary}")
        lines.append("")

    total = len(walk(node))
    if total > 1:
        lines.append(f"  {total} packages in total under this node.")
    return "\n".join(lines)
