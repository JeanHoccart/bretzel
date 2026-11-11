"""What an app's ``Feature`` contracts can answer when they are asked.

Read at startup and then forgotten, a contract answers nothing: who uses
what, what a change touches would be searched by hand, with ``grep``.
This module turns the contracts into answers, for the two commands
``bretzel features`` and ``bretzel impact``:

- **the map** — each feature, what it is, its routes, what it exposes,
  who uses it;
- **what to fix** — ``uses`` that lie, a public symbol no other feature
  uses (a dead surface), a symbol
  taken from a feature that does not expose it (a boundary crossed);
- **what a change touches** — the features that import, directly or not,
  the feature of a file, their pages, and the probes that visit them.

Everything is DERIVED from the code the app runs on: the real imports
(AST of the modules already loaded), the objects in ``provides`` compared
by identity — so a constant (``KIND``, a dict) is recognised under the
name it is imported by, though ``provides`` received its value.
"""

from __future__ import annotations

import ast
import sys
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from bretzel.server.feature import (
    Feature,
    _classify_provide,
    _feature_prefix,
    _imports_of,
    _render_parents,
    dependency_drift,
)

#: Provides nobody is expected to import: what the router mounts (a page,
#: a layout, an error page), and what a feature declares for the map of
#: its own contract (its states, its zones) — the convention of
#: ``Feature``'s own example, ``provides=[CartState, cart_page]``.
_NOT_IMPORTED = ("page", "layout", "error", "state", "view")


@dataclass(frozen=True)
class SymbolUse:
    """``importer`` takes ``name`` from ``provider``'s modules."""

    importer: str
    provider: str
    name: str
    obj: Any = field(default=None, compare=False, repr=False)


@dataclass(frozen=True)
class Surface:
    """Public symbols nobody else uses, and symbols taken without being public."""

    unused: tuple[tuple[str, str], ...] = ()                 # (feature, label)
    undeclared: tuple[tuple[str, str, tuple[str, ...]], ...] = ()  # (provider, name, importers)


@dataclass(frozen=True)
class Impact:
    """What a change to some files touches."""

    touched: tuple[str, ...] = ()        # the features owning the files
    affected: tuple[str, ...] = ()       # touched + every feature importing them, transitively
    routes: tuple[tuple[str, str], ...] = ()   # (route, feature) of the affected pages
    probes: tuple[tuple[str, tuple[str, ...]], ...] = ()  # (probe file, features it covers)
    unowned: tuple[str, ...] = ()        # files no feature owns


class _Owners:
    """Which feature owns a module: the longest feature prefix wins."""

    def __init__(self, feats: list[Feature]) -> None:
        self.prefix = {f.name: _feature_prefix(f.module or "") for f in feats}
        self._order = sorted(((p, n) for n, p in self.prefix.items() if p),
                             key=lambda t: -len(t[0]))

    def of(self, module: str) -> str:
        for prefix, name in self._order:
            if module == prefix or module.startswith(prefix + "."):
                return name
        return ""

    def modules(self, feature: str) -> list[tuple[str, Any]]:
        return [(n, m) for n, m in list(sys.modules.items())
                if m is not None and getattr(m, "__file__", None) and self.of(n) == feature]


#: Folders never read as the app's own code.
_SKIPPED = {".venv", "venv", "site-packages", "node_modules", "__pycache__", ".bretzel", ".git"}


def app_files(features: Iterable[Feature], root: Path) -> list[tuple[str, Path]]:
    """The app's Python files that belong to no feature — ``core/``,
    ``main.py``, the tests — as ``(label, path)``: what they use is used."""
    owners = _Owners(list(features))
    owned = {Path(m.__file__).resolve() for f in owners.prefix for _n, m in owners.modules(f)}
    out = []
    for path in sorted(root.rglob("*.py")):
        if _SKIPPED & set(path.relative_to(root).parts) or path.resolve() in owned:
            continue
        out.append((f"[{path.relative_to(root).as_posix()}]", path))
    return out


def symbol_uses(features: Iterable[Feature], root: Path | None = None) -> list[SymbolUse]:
    """Every symbol a feature takes from another one: ``from x import a``,
    and ``import x as m`` / ``from pkg import x`` read as ``m.a``. With
    ``root``, the app's files outside the features too (``core/``, the
    tests), labelled by their path."""
    feats = list(features)
    owners = _Owners(feats)
    out: list[SymbolUse] = []
    sources = [(f.name, n, Path(m.__file__)) for f in feats for n, m in owners.modules(f.name)]
    if root is not None:
        sources += [(label, label, path) for label, path in app_files(feats, root)]
    for who, mod_name, file in sources:
        try:
            tree = ast.parse(file.read_text(encoding="utf-8"))
        except (OSError, SyntaxError, ValueError):
            continue
        aliases: dict[str, str] = {}   # local name -> module of another feature
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                base = _absolute(node, mod_name)
                for alias in node.names:
                    as_module = f"{base}.{alias.name}" if base else alias.name
                    if owners.of(as_module) not in ("", who) and as_module in sys.modules:
                        aliases[alias.asname or alias.name] = as_module
                        continue
                    provider = owners.of(base)
                    if provider and provider != who:
                        obj = getattr(sys.modules.get(base), alias.name, None)
                        out.append(SymbolUse(who, provider, alias.name, obj))
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if owners.of(alias.name) not in ("", who):
                        aliases[alias.asname or alias.name] = alias.name
        for node in ast.walk(tree):
            if (isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name)
                    and node.value.id in aliases):
                module = aliases[node.value.id]
                obj = getattr(sys.modules.get(module), node.attr, None)
                out.append(SymbolUse(who, owners.of(module), node.attr, obj))
    return out


def _absolute(node: ast.ImportFrom, module_name: str) -> str:
    if node.level:
        base = module_name.split(".")[: -node.level]
        return ".".join(base + ([node.module] if node.module else []))
    return node.module or ""


def _label(feature: Feature, obj: Any, owners: _Owners) -> str:
    """A provide's name: its own, or — a constant — the one its module
    gives it."""
    info = _classify_provide(obj)
    if info.kind != "value":
        return info.label
    for _n, mod in owners.modules(feature.name):
        for name, value in vars(mod).items():
            if value is obj and not name.startswith("_"):
                return name
    return info.label


def surface(features: Iterable[Feature], root: Path | None = None) -> Surface:
    feats = list(features)
    owners = _Owners(feats)
    uses = symbol_uses(feats, root)
    unused: list[tuple[str, str]] = []
    for f in feats:
        for obj in f.provides:
            if (_classify_provide(obj).kind in _NOT_IMPORTED
                    or getattr(obj, "_bz_download", None) is not None):
                continue
            if not any(u.provider == f.name and _same(u.obj, obj) for u in uses):
                unused.append((f.name, _label(f, obj, owners)))
    by_name = {f.name: f for f in feats}
    taken: dict[tuple[str, str], set[str]] = {}
    for u in uses:
        provider = by_name.get(u.provider)
        if provider is None or u.obj is None or isinstance(u.obj, type(sys)):
            continue
        # A test may look inside a feature: it counts as a use (above),
        # not as a boundary crossed.
        if u.importer.startswith("[") and "tests" in Path(u.importer.strip("[]")).parts:
            continue
        if not any(_same(u.obj, p) for p in provider.provides):
            taken.setdefault((u.provider, u.name), set()).add(u.importer)
    return Surface(tuple(sorted(unused)),
                   tuple((p, n, tuple(sorted(w))) for (p, n), w in sorted(taken.items())))


def _same(a: Any, b: Any) -> bool:
    """The same object — a ``@refreshable`` handle and its function too."""
    return a is b or getattr(a, "fn", a) is getattr(b, "fn", b)


def import_graph(features: Iterable[Feature]) -> dict[str, set[str]]:
    """Feature → the features its modules really import (not its ``uses``)."""
    feats = list(features)
    owners = _Owners(feats)
    graph: dict[str, set[str]] = {f.name: set() for f in feats}
    for f in feats:
        for mod_name, mod in owners.modules(f.name):
            for target in _imports_of(mod.__file__, mod_name):
                owner = owners.of(target)
                if owner and owner != f.name:
                    graph[f.name].add(owner)
    return graph


def impact(features: Iterable[Feature], files: Iterable[Path],
           probes_dir: Path | None = None) -> Impact:
    """The features a change to ``files`` touches, and how to check them."""
    feats = list(features)
    owners = _Owners(feats)
    by_file: dict[Path, str] = {}
    for f in feats:
        for _n, mod in owners.modules(f.name):
            by_file[Path(mod.__file__).resolve()] = f.name
    touched, unowned = set(), []
    for file in files:
        name = by_file.get(Path(file).resolve())
        if name:
            touched.add(name)
        else:
            unowned.append(str(file))
    graph = import_graph(feats)
    affected = set(touched)
    grew = True
    while grew:
        grew = False
        for name, deps in graph.items():
            if name not in affected and deps & affected:
                affected.add(name)
                grew = True
    routes = []
    for f in feats:
        if f.name in affected:
            for obj in f.provides:
                info = _classify_provide(obj)
                if info.kind == "page" and info.detail:
                    routes.append((info.detail, f.name))
    probes = []
    if probes_dir is not None and probes_dir.is_dir():
        for probe in sorted(probes_dir.glob("*.py")):
            covered = _covered(probe, feats, owners, affected)
            if covered:
                probes.append((probe.name, tuple(sorted(covered))))
    return Impact(tuple(sorted(touched)), tuple(sorted(affected)), tuple(sorted(routes)),
                  tuple(probes), tuple(unowned))


def _covered(probe: Path, feats: list[Feature], owners: _Owners,
             affected: set[str]) -> set[str]:
    """The affected features a probe exercises: it imports one of their
    modules, or it names the fixed start of one of their routes
    (``/classes`` for ``/classes/{code}``). A heuristic, said as such:
    it looks for the route's text, it does not follow the clicks."""
    text = probe.read_text(encoding="utf-8")
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return set()
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            imported.add(owners.of(node.module))
            imported.update(owners.of(f"{node.module}.{a.name}") for a in node.names)
        elif isinstance(node, ast.Import):
            imported.update(owners.of(a.name) for a in node.names)
    out = {name for name in imported if name in affected}
    for f in feats:
        if f.name not in affected:
            continue
        for obj in f.provides:
            info = _classify_provide(obj)
            if info.kind != "page" or not info.detail:
                continue
            start = info.detail.split("{", 1)[0].rstrip("/")
            # The root names itself whole: "/" alone, or "/?" and a query.
            marks = ([f'"{start}', f"'{start}"] if start else
                     ['"/"', "'/'", '"/?', "'/?"])
            if any(mark in text for mark in marks):
                out.add(f.name)
    return out


def describe_features(features: Iterable[Feature]) -> list[dict[str, Any]]:
    """The map: per feature, what it is, its first docstring line, its
    routes, what it exposes, who imports it and what it imports."""
    feats = list(features)
    owners = _Owners(feats)
    graph = import_graph(feats)
    render = _render_parents(feats)
    rows = []
    for f in feats:
        mods = owners.modules(f.name)
        doc = ""
        file = ""
        for _n, mod in mods:
            file = file or mod.__file__
            if not doc and mod.__doc__:
                doc = mod.__doc__.strip().splitlines()[0]
        infos = [_classify_provide(o) for o in f.provides]
        rows.append({
            "name": f.name,
            "kind": f.kind,
            "summary": doc,
            "file": file,
            "routes": [i.detail for i in infos if i.kind == "page" and i.detail],
            "provides": [_label(f, o, owners) for o, i in zip(f.provides, infos, strict=True)
                         if i.kind != "page"],
            "imports": sorted(graph[f.name] - {render.get(f.name, (False, ""))[1]}),
            "used_by": sorted(n for n, deps in graph.items() if f.name in deps),
        })
    return rows


#: The kinds that draw the interface. Nothing below them imports them —
#: a ``data`` feature never imports a page: it would bring the page's
#: imports, its layout and its states into every caller of the data.
UI_KINDS = frozenset({"shell", "layout", "page", "error"})

#: The kinds that never import the interface. ``facade`` is not one: it
#: fronts a sub-tree, and may front pages.
BELOW_UI = frozenset({"state", "data", "logic", "infra", "job"})

#: What a provide of each mounted sort requires as the feature's kind.
_KIND_OF = {"page": ("page",), "layout": ("shell", "layout"), "error": ("error",)}


def kind_errors(features: Iterable[Feature]) -> list[str]:
    """What makes a ``kind`` lie, one line each:

    - **layers** — a feature below the interface (``data``, ``logic``,
      ``state``, ``infra``, ``job``) imports one that draws it;
    - **what it provides** — a page from a feature that is not a
      ``page``, a layout from neither a ``shell`` nor a ``layout``, an
      error page from no ``error``; and a ``page`` that mounts no page."""
    feats = list(features)
    kind = {f.name: f.kind for f in feats}
    out = []
    for name, deps in import_graph(feats).items():
        if kind[name] in BELOW_UI:
            for dep in sorted(d for d in deps if kind.get(d) in UI_KINDS):
                out.append(f"{name} ({kind[name]}) imports {dep} ({kind[dep]}): below the "
                           f"interface, a feature never imports what draws it")
    for f in feats:
        mounted = {_classify_provide(o).kind for o in f.provides} & set(_KIND_OF)
        for sort in sorted(mounted):
            if f.kind not in _KIND_OF[sort] and f.kind != "facade":
                out.append(f"{f.name} is a `{f.kind}` and provides a {sort}: its kind is "
                           f"{' or '.join(f'`{k}`' for k in _KIND_OF[sort])}")
        if f.kind == "page" and "page" not in mounted:
            out.append(f"{f.name} is a `page` and provides no page")
    return out


def contract_errors(features: Iterable[Feature], root: Path | None = None) -> list[str]:
    """What makes a contract lie, one line each: a ``uses`` that differs
    from the real imports, a symbol taken from a feature whose
    ``provides`` does not hold it, a ``kind`` that lies
    (:func:`kind_errors`). What ``Bretzel`` refuses to start on in
    ``mode="dev"``."""
    feats = list(features)
    out = []
    for d in dependency_drift(feats):
        if d.missing:
            out.append(f"{d.feature} imports {', '.join(d.missing)} without declaring it "
                       f"in `uses`")
        if d.stale:
            out.append(f"{d.feature} declares {', '.join(d.stale)} in `uses` and never "
                       f"imports it")
    for provider, name, importers in surface(feats, root).undeclared:
        out.append(f"{provider}.{name} is taken by {', '.join(importers)} and is not in "
                   f"its `provides`")
    return out + kind_errors(feats)


def findings(features: Iterable[Feature], root: Path | None = None) -> list[str]:
    """What to fix, one line each: :func:`contract_errors`, then a public
    symbol nothing uses — advice, not an error: a function kept for the
    chatbot or an API may wait for its first caller. ``root``: the app's
    folder, so that what ``core/`` or the tests use counts as used."""
    feats = list(features)
    out = contract_errors(feats, root)
    for feature, label in surface(feats, root).unused:
        out.append(f"{feature}.{label} is in `provides` and nothing outside it uses it "
                   f"— private, or dead")
    return out
