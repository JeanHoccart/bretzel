"""Layer 7 — the framework describes itself, and cannot lie.

This module reads the **installed** code at the moment it is queried.
That is what distinguishes it from an API catalogue: there is nothing to
maintain, so nothing to let drift. It is also why it ships INSIDE the
framework and cannot live in a separate package — a version gap between
the describer and the described would make it lie, which is precisely the
illness it cures.

Three high-level entry points:

- :func:`index` — one line per ``ui.*`` symbol, the whole surface.
- :func:`describe` — a symbol's complete card, as text, on demand.
- :func:`resolve` — the SAME resolution, returned as a dataclass. It is
  the one a consumer calls: the CLI draws its ``--json`` from it, and the
  order of the tiers (module → component → symbol) is written only there.

⚠️ **The emitters' output is UTF-8**, arrows and quotation marks
included. A consumer writing it to a stream owns its encoding — on a
Windows console (cp1252) a bare ``print`` raises. The CLI does it for
them (``bretzel.cli.main``); a home-made script must do it too.

And the per-section readers, for a consumer composing their own:
:func:`describe_state`, :func:`describe_client_algebra`,
:func:`describe_toplevel_surface`, :func:`describe_method_surface`,
:func:`describe_callable`.

The contract for a third-party consumer (living documentation, generator,
MCP server) is :mod:`bretzel.introspect.model`: the dataclasses are
imported **in process**, the text output is not parsed.

The absence of a specialised section in the textual output does not mean
the symbol is absent from the general resolution.
"""

from __future__ import annotations

import contextlib
import importlib

from bretzel.introspect._signature import describe_callable
from bretzel.introspect.algebra import describe_client_algebra
from bretzel.introspect.capabilities import (
    CAPABILITIES,
    Capability,
    capability_names,
    render_capabilities,
)
from bretzel.introspect.components import (
    RESERVED_KWARGS,
    describe_component,
    describe_components,
    describe_ui_symbol,
    prop_vocabulary,
    theme_shapes,
    theme_vocabulary,
    ui_name_of_class,
    ui_symbol_names,
)
from bretzel.introspect.emit.text import (
    render_detail,
    render_index,
    render_module,
    render_symbol,
)
from bretzel.introspect.methods import describe_method_surface
from bretzel.introspect.model import (
    CATEGORY_UNCLASSIFIED,
    SCHEMA_VERSION,
    SOURCE_REACTIVE_PROP,
    SOURCE_SIGNATURE,
    AlgebraOp,
    CallableInfo,
    ComponentInfo,
    FieldInfo,
    HelperInfo,
    MethodInfo,
    ModuleSection,
    ParamInfo,
    StateInfo,
    SurfaceSymbol,
    SymbolDetail,
)
from bretzel.introspect.modules import (
    describe_module,
    describe_modules,
    describe_toplevel_surface,
    module_names,
    public_owners,
)
from bretzel.introspect.package_tree import (
    ModuleInfo,
    PackageNode,
    SymbolLine,
    describe_package,
    package_names,
    render_package,
    render_tree,
    walk,
)
from bretzel.introspect.state import describe_state
from bretzel.introspect.symbols import (
    describe_symbol,
    symbol_names,
    symbol_owners,
)
from bretzel.introspect.theme_sheet import theme_sheet

__all__ = (
    "CAPABILITIES",
    "CATEGORY_UNCLASSIFIED",
    "Capability",
    "capability_names",
    "render_capabilities",
    "RESERVED_KWARGS",
    "SCHEMA_VERSION",
    "SOURCE_REACTIVE_PROP",
    "SOURCE_SIGNATURE",
    "AlgebraOp",
    "CallableInfo",
    "ComponentInfo",
    "FieldInfo",
    "ModuleInfo",
    "ModuleSection",
    "PackageNode",
    "SymbolLine",
    "describe_package",
    "package_names",
    "render_package",
    "render_tree",
    "walk",
    "HelperInfo",
    "MethodInfo",
    "ParamInfo",
    "StateInfo",
    "SurfaceSymbol",
    "SymbolDetail",
    "describe",
    "describe_callable",
    "describe_client_algebra",
    "describe_component",
    "describe_components",
    "describe_method_surface",
    "describe_module",
    "describe_modules",
    "describe_state",
    "describe_symbol",
    "describe_toplevel_surface",
    "prop_vocabulary",
    "theme_sheet",
    "theme_shapes",
    "theme_vocabulary",
    "describe_ui_symbol",
    "index",
    "module_names",
    "render_detail",
    "render_index",
    "render_module",
    "render_symbol",
    "resolve",
    "symbol_names",
    "symbol_owners",
    "ui_symbol_names",
)


def index() -> str:
    """The whole ``ui.*`` surface, one line per symbol."""
    return render_index()


def resolve(name: str) -> ModuleSection | ComponentInfo | HelperInfo | SymbolDetail:
    """The symbol designated by ``name``, in its dataclass form.

    **The order of the tiers lives HERE and nowhere else.** It was
    written three times — in ``describe``, in the CLI for ``--json``, and
    in the error message — and all three had already diverged:
    ``--json`` ignored the module tier, so ``describe bretzel.core
    --json`` raised and ``describe bretzel.state --json`` answered ANOTHER
    symbol's card (``state``, re-exported by ``bretzel``). That is exactly
    the divergence this project came to close, reintroduced by a copy.

    Three natures of name:

    - a covered module (``bretzel.state``) → its classified surface;
    - **any other PACKAGE** (``bretzel.components.inputs``) → its tree
      and the docstrings the folders already carry. Added on 2026-09-02:
      there are 117 packages under ``bretzel/`` and seven were described,
      because the table is written by hand. The tree, by contrast, reads
      itself;
    - a component (``button`` or ``ui.button`` — the real call site
      carries the prefix, requiring it would be needless friction);
    - **any other public symbol** (``page``, ``PageState``,
      ``ClientBinding``, ``ROUTE_ACTION``), bare or qualified.

    The ``ui.`` prefix forces the second family: it is the only way to
    ask for the component when a name is carried by both surfaces.
    """
    if name in module_names():
        return describe_module(name)

    # An UNCLASSIFIED package — tested after the table, which is more
    # precise when it exists (it groups by need, the tree does not).
    #
    # ⚠️ This test AFTER the table has an effect worth knowing:
    # ``describe bretzel`` returns the SURFACE (45 lines), not the tree
    # (117). Both exist, the table wins, and that is intended — one asks
    # for "bretzel" to know what to write, not how the folders are laid
    # out. ``render_module`` therefore adds a line saying where to find
    # the other, without which the tree would be silently hidden for the
    # seven classified modules.
    if name.startswith("bretzel.") or name == "bretzel":
        with contextlib.suppress(ValueError):
            return describe_package(name)

    symbol = name.removeprefix("ui.")
    if symbol in ui_symbol_names():
        return describe_ui_symbol(symbol)
    if not name.startswith("ui."):
        with contextlib.suppress(KeyError):
            return describe_symbol(name)
    raise KeyError(_unknown_message(name))


def describe(name: str) -> str:
    """A framework symbol's complete card, as text.

    A rendering of what :func:`resolve` found — the resolution is not
    redone here.

    ⚠️ **One single exception, and it is deliberate**: ``capabilities``
    does NOT go through :func:`resolve`, because it is not a symbol. It
    is the module's only answer that derives from no reading of the code
    — a capability crosses five folders, so neither the tree, nor the
    per-need table, nor the ``ui.*`` catalogue can form it. It is written
    by hand and ANCHORED: cf.
    :mod:`bretzel.introspect.capabilities`.
    """
    if name == "capabilities":
        return render_capabilities()
    found = resolve(name)
    if isinstance(found, ModuleSection):
        rendered = render_module(found)
        # The pointer to the tree — cf. ``resolve``'s warning.
        with contextlib.suppress(ValueError):
            node = describe_package(name)
            if node.children:
                rendered += (
                    f"\n  ({len(walk(node))} packages below — "
                    f"use ``describe {name}.<folder>`` to inspect the tree)\n"
                )
        return rendered
    if isinstance(found, SymbolDetail):
        return render_symbol(found)
    if isinstance(found, PackageNode):
        return render_package(found)
    return render_detail(found) + _homonym_note(found.ui_name)


def _homonym_note(ui_name: str) -> str:
    """Report that a component name ALSO designates a module symbol.

    One case today, and it is a trap: ``text`` is the ``ui.text``
    component **and** ``bretzel.render.text``, the framework's word
    rendered in the app's language. The bare name resolves to the
    component — that is the dominant use — but stopping there would make
    the other a symbol one can only find by already knowing it exists.

    The reverse direction is carried by
    :attr:`~bretzel.introspect.model.SymbolDetail.also_known_as`, so the
    symbol's card names the component without going through here.
    """
    owners = symbol_owners().get(ui_name, ())
    if not owners:
        return ""
    paths = ", ".join(f"{module}.{ui_name}" for module in owners)
    return f"\n\nNamesake   {paths}   (`describe {owners[0]}.{ui_name}`)"


def _unknown_message(name: str) -> str:
    """The message for a name not found — it must say WHERE we looked.

    The old one answered "``ui.page`` does not exist" for ``page``, which
    is true and misleading: the symbol exists, elsewhere. A reader
    concluded that the decorator did not exist.
    """
    forced_ui = name.startswith("ui.")
    symbol = name.removeprefix("ui.")
    known_ui = ui_symbol_names()
    scopes = "the `ui.*` components" if forced_ui else "the `ui.*` components or modules"
    pool = set(known_ui) if forced_ui else set(known_ui) | set(symbol_names())
    near = sorted(n for n in pool if (symbol in n or n in symbol) and n != symbol)[:6]
    hint = f" Similar names: {', '.join(near)}." if near else ""
    return (
        f"`{name}` was not found among {scopes} "
        f"({len(known_ui)} components, {len(symbol_names())} module symbols)."
        f"{_where_it_lives(symbol)}"
        f"{hint} `index()` lists them all, and `describe capabilities` "
        f"shows what the framework can do."
    )


def _where_it_lives(symbol: str) -> str:
    """Where the name lives, when it lives somewhere the table ignores.

    Two ways of existing without having a card, and both came up on
    2026-09-06:

    - the CATALOGUE — ``Button`` is ``ui.button``'s class, and
      ``AccordionItem`` ``ui.accordion_item``'s. Substring neighbourhood
      does not find them (it compares case-sensitively), so the message
      answered "does not exist" about a name one can import. The
      correspondence is read by IDENTITY on the ``ui`` namespace — not by
      spelling, which misses everything carrying an underscore;
    - the DOOR — ``DatatableState`` is exported by ``bretzel.components``,
      a package with no classification table.

    Saying "does not exist" about an importable name is the most
    expensive fault of the lot: it is CREDIBLE, and it makes people give
    up.
    """
    owner = public_owners().get(symbol)
    if owner is None:
        return ""
    value = getattr(importlib.import_module(owner), symbol, None)
    catalogue = ui_name_of_class().get(value) if isinstance(value, type) else None
    if catalogue is not None:
        return f" It is the class behind `ui.{catalogue}`: `describe {catalogue}`."
    return (
        f" It can still be imported with `from {owner} import {symbol}`, but "
        f"{owner} has no category table and therefore no detail page."
    )
