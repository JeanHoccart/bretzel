"""The public surfaces of the framework's modules, classified by need.

**One reader, N tables — not N modules.** ``bretzel.state``,
``bretzel.server``, ``bretzel.render``, ``bretzel.runtime``,
``bretzel.core`` and ``bretzel.theme`` ask exactly the same question
("what exists here, and what is it for?"); writing a module each would
have produced six copies of a loop over ``__all__``. What differs from
one module to the next is not the reading, it is the **classification**.

**Classifying by NEED, and not by Python type, is the point.** Knowing
that ``refresh`` is a function helps nobody; knowing that it lives in
"act from a handler", next to ``abort`` and ``redirect``, answers the
real question — "I have a handler, what can I call?".

**The population is never copied**: it comes from the module's
``__all__``. Only the classification is written by hand, and that is
precisely what we want to force a decision on — a name added with no
entry here falls into :data:`CATEGORY_UNCLASSIFIED` and makes
``tests/consistency/test_module_surfaces_are_classified.py`` turn red. A
public surface is not widened without saying what it is for.
"""

from __future__ import annotations

import importlib
import inspect
import pkgutil
from functools import cache
from types import MappingProxyType

from bretzel.introspect.model import (
    CATEGORY_UNCLASSIFIED,
    ModuleSection,
    SurfaceSymbol,
)

#: A decorator is recognised by its use, not by its signature — the list
#: is short and stable, so naming it beats guessing it badly.
_DECORATORS = frozenset(
    {
        "page",
        "layout",
        "error_page",
        "refreshable",
        "background",
        "idempotent",
        "computed",
        "validator",
    }
)

_ERROR = "handle an error"

_TOPLEVEL: dict[str, str] = {
    "Bretzel": "mount the application",
    "BretzelConfig": "mount the application",
    "Feature": "mount the application",
    # The PWA is app CONFIGURATION, not a component: it is passed to
    # ``Bretzel(pwa=…)`` and describes the app to the system (name, icon,
    # clean window), not to the browser.
    "PWA": "mount the application",
    "PWAIcon": "mount the application",
    "page": "declare a route",
    "layout": "declare a route",
    "error_page": "declare a route",
    "refreshable": "declare a route",
    # A ``@download`` IS a routable — the only one that returns not a
    # page but a file. Its response cannot go through the action pipeline
    # (the bridge would swallow it as a ``<bz-patch>``).
    "download": "declare a route",
    # One entry point each, cf. test_handler_helpers_have_one_home.py
    "abort": "act from a handler",
    "redirect": "act from a handler",
    "push_url": "act from a handler",
    "background": "act from a handler",
    "idempotent": "act from a handler",
    "refresh": "act from a handler",
    # It makes the browser ASK FOR the page again — an action on the
    # response, not a zone re-render like ``refresh`` just above.
    "reload": "act from a handler",
    # The client VERBS (2026-09-01). A need of their own, and naming it
    # is what the gate requires: they act neither on the response nor on
    # the tree, they trigger a BROWSER action. Their place on ``bretzel``
    # rather than on ``ui`` is a user arbitration of the same day — what
    # DOES something is here, what IS something is on ``ui``.
    "copy": "act in the browser",
    "print_page": "act in the browser",
    "fullscreen": "act in the browser",
    "share": "act in the browser",
    "vibrate": "act in the browser",
    "ui": "render",
    "state": "declare state",
    # The resolved language of THIS request — read from a render body,
    # like ``Screen()`` just below.
    "Language": "render",
    "Screen": "render",
    # The third ambient read, with ``Screen`` and ``Language``: they all
    # answer "what do we know about THIS reader?". It lives in ``theme``
    # (base layer) and is re-exported here so the three import from the
    # same place — until 2026-08-29 one had to know ``bretzel.theme`` to
    # read the colour mode.
    "ColorScheme": "render",
    # The fourth and last ambient read. It lives in ``state`` because it
    # is a ``ClientState`` the runtime writes — but it reads like its
    # three sisters, and is therefore imported from here like them.
    "LiveConnection": "render",
    # The WHOLE identity fits in these two modules since 2026-08-29:
    # the imperative verbs and the two declarations (``@auth.source`` /
    # ``@auth.door``), which used to be at top level.
    "auth": "identify the current user",
    "oauth": "identify the current user",
    "BretzelError": _ERROR,
    "AuthRequiredError": _ERROR,
    "FeatureError": _ERROR,
    "__version__": "package metadata",
}

_STATE: dict[str, str] = {
    # The four server scopes — inheritance IS the duration hierarchy.
    "ServerState": "declare server state",
    "PageState": "declare server state",
    "SessionState": "declare server state",
    "UserState": "declare server state",
    "AppState": "declare server state",
    # The fifth scope, on the browser side.
    "ClientState": "declare client state",
    "LiveConnection": "declare client state",
    "field": "declare a field",
    "register_type": "declare a field",
    "computed": "declare a field",
    "validator": "declare a field",
    "form_value": "read state elsewhere",
    # The algebra: what one composes for a `bz-show` / a `visible=`.
    "ClientBinding": "compose on the client",
    "ClientExpression": "compose on the client",
    "FormError": _ERROR,
    "ReactivityError": _ERROR,
    "ScopeConfigError": _ERROR,
    "StateHydrationError": _ERROR,
    "AuthRequiredError": _ERROR,
    "LockTimeoutError": _ERROR,
}

_SERVER: dict[str, str] = {
    "Bretzel": "mount the application",
    "BretzelConfig": "mount the application",
    "Feature": "mount the application",
    # The PWA is app CONFIGURATION, not a component: it is passed to
    # ``Bretzel(pwa=…)`` and describes the app to the system (name, icon,
    # clean window), not to the browser.
    "PWA": "mount the application",
    "PWAIcon": "mount the application",
    # The app map: declared contract ↔ derived reality. Not a devtool —
    # it feeds the map component at runtime.
    "describe_app": "inspect the app map",
    "AppGraph": "inspect the app map",
    "abort": "act from a handler",
    "redirect": "act from a handler",
    "push_url": "act from a handler",
    "background": "act from a handler",
    "idempotent": "act from a handler",
    "reload": "act from a handler",
    "BretzelError": _ERROR,
    "AuthRequiredError": _ERROR,
    "ConfigError": _ERROR,
    "FeatureError": _ERROR,
}

_RENDER: dict[str, str] = {
    "page": "declare a route",
    "layout": "declare a route",
    "error_page": "declare a route",
    "refreshable": "declare a route",
    # A ``@download`` IS a routable — the only one that returns not a
    # page but a file. Its response cannot go through the action pipeline
    # (the bridge would swallow it as a ``<bz-patch>``).
    "download": "declare a route",
    "render_page": "render",
    "render_partial": "render",
    "default_shell": "render",
    "shell_sources": "render",
    "serialize_html": "render",
    "refresh": "refresh a region",
    "drain_refresh_queue": "refresh a region",
    "RefreshableHandle": "refresh a region",
    "zone_ids_watching": "refresh a region",
    "text": "say a framework word",
    "plural": "say a framework word",
    "template": "say a framework word",
    "DEFAULT_TEXTS": "say a framework word",
    "resolve_texts": "say a framework word",
    # The LANGUAGE, not the words: ``Language().code`` is what an app
    # translates ITS strings with, which the framework does not know;
    # ``Language.set`` is the selector.
    "Language": "choose the language",
    "negotiate_language": "choose the language",
    "resolve_language": "choose the language",
    "LanguageTables": "choose the language",
    "TextsError": _ERROR,
    "RenderContext": "read the render context",
    "current_context": "read the render context",
    "maybe_current_context": "read the render context",
    "use_context": "read the render context",
    "current_iteration_key": "read the render context",
    "PageMeta": "route metadata",
    "LayoutMeta": "route metadata",
    "ErrorMeta": "route metadata",
    "RenderResult": "route metadata",
    "BretzelApp": "route metadata",
    "state_qualname": "route metadata",
    "fuse_or_wrap": "compose attributes",
    "FusionConflict": "compose attributes",
    "DEFAULT_HTMX_URL": "constant",
    # The three third-party scripts vendored locally. Public because the
    # server layer serves them (it goes through `render`'s API, not
    # through the submodule) and because an auth guard must be able to
    # name them.
    "ROUTE_VENDOR": "serve third-party scripts locally",
    "ROUTE_ICONS": "serve third-party scripts locally",
    "VendoredAsset": "serve third-party scripts locally",
    "cached_name": "serve third-party scripts locally",
    "ensure_vendored": "serve third-party scripts locally",
    "downloadable_assets": "serve third-party scripts locally",
    "icon_payload": "serve third-party scripts locally",
    "vendored_assets": "serve third-party scripts locally",
    "vendored_is_available": "serve third-party scripts locally",
    "vendored_local_path": "serve third-party scripts locally",
}

_RUNTIME: dict[str, str] = {
    # The client VERBS (2026-09-01). A need of their own, and naming it
    # is what the gate requires: they act neither on the response nor on
    # the tree, they trigger a BROWSER action. Their place on ``bretzel``
    # rather than on ``ui`` is a user arbitration of the same day — what
    # DOES something is here, what IS something is on ``ui``.
    "copy": "act in the browser",
    "print_page": "act in the browser",
    "fullscreen": "act in the browser",
    "share": "act in the browser",
    "vibrate": "act in the browser",
    # The `bz-*` vocabulary — the framework's client-side idiom. A
    # component composes with those; it writes neither `hx-` nor `fetch`.
    "BZ_ON_PREFIX": "bz-* directive vocabulary",
    "BZ_MODEL_PREFIX": "bz-* directive vocabulary",
    "BZ_ATTR_PREFIX": "bz-* directive vocabulary",
    "BZ_CLASS_PREFIX": "bz-* directive vocabulary",
    "BZ_TEXT_PREFIX": "bz-* directive vocabulary",
    "BZ_SHOW_PREFIX": "bz-* directive vocabulary",
    "BZ_IF_PREFIX": "bz-* directive vocabulary",
    "BZ_FOR_PREFIX": "bz-* directive vocabulary",
    "BZ_DATA_PREFIX": "bz-* directive vocabulary",
    "BZ_INIT_PREFIX": "bz-* directive vocabulary",
    "BZ_EFFECT_PREFIX": "bz-* directive vocabulary",
    "BZ_REF_PREFIX": "bz-* directive vocabulary",
    "BZ_TELEPORT_PREFIX": "bz-* directive vocabulary",
    "BZ_ID_ATTR": "transport attribute",
    "BZ_STATE_ATTR": "transport attribute",
    "DATA_BZ_SIG": "transport attribute",
    "DATA_BZ_TS": "transport attribute",
    "DATA_SUBSCRIBE_STATE": "transport attribute",
    "DATA_SUBSCRIBE_URL": "transport attribute",
    "SERVERSYNC_KEY": "transport attribute",
    "SINK_ELEMENT_ID": "transport attribute",
    "WIRE_ID_SEP": "transport attribute",
    "HEADER_PROTOCOL": "HTTP header",
    "HEADER_BZ_SIG": "HTTP header",
    "HEADER_BZ_TS": "HTTP header",
    "HEADER_PAGE_ID": "HTTP header",
    "HEADER_CSRF": "HTTP header",
    # The URLs live here and reach the client through the envelope — the
    # runtime.js hard-codes none of them (anti-rule 3).
    "ROUTE_PREFIX": "runtime route",
    "ROUTE_RUNTIME_JS": "runtime route",
    "ROUTE_THEME_CSS": "runtime route",
    "ROUTE_STYLE_CSS": "runtime route",
    "ROUTE_ICONS": "runtime route",
    "ROUTE_VENDOR": "runtime route",
    "is_public_asset_path": "runtime route",
    "ROUTE_ACTION": "runtime route",
    "ROUTE_SSE": "runtime route",
    "ROUTE_REFETCH": "runtime route",
    # The open/closed classification of those routes, for an app's auth
    # guard. Gated by test_framework_routes_are_classified.
    "PUBLIC_ASSET_ROUTES": "runtime route",
    "Envelope": "envelope and patch",
    "Patch": "envelope and patch",
    "build_envelope": "envelope and patch",
    "build_patch": "envelope and patch",
    "serialize_envelope": "envelope and patch",
    "serialize_patch": "envelope and patch",
    "parse_client_payload": "envelope and patch",
    "default_endpoints": "envelope and patch",
    "outlet_id_for": "envelope and patch",
    "ENVELOPE_TAG_NAME": "envelope and patch",
    "PATCH_TAG_NAME": "envelope and patch",
    "PROTOCOL_VERSION": "protocol version",
    "check_compat": "protocol version",
    "check_protocol_compat": "protocol version",
    "parse_major": "protocol version",
    # The ONLY SSE event: "state X is dirty". The server never pushes
    # HTML through that channel, it pushes a signal.
    "SSE_EVENT_STATE_DIRTY": "real time (SSE)",
}

_CORE: dict[str, str] = {
    "Node": "render tree",
    "Element": "render tree",
    # Suffixed ``Node`` on 2026-08-29: ``Text``/``Html``/``Fragment``
    # were the three ONLY names of the whole public surface designating
    # two different objects (a tree node here, a component in
    # ``bretzel.components``). The suffix is not an invention: the five
    # files that already had to lift the ambiguity all aliased to those
    # very names.
    "TextNode": "render tree",
    "HtmlNode": "render tree",
    "FragmentNode": "render tree",
    "VOID_ELEMENTS": "render tree",
    "serialize": "render tree",
    "serialize_attrs": "render tree",
    "escape_html": "escape",
    "escape_attr": "escape",
    "escape_js": "escape",
    "IdGenerator": "node identity",
    "hash_segment": "node identity",
    # What makes "mutating state re-renders the subtree" possible.
    "DependencyTracker": "track dependencies",
    "Observer": "track dependencies",
    "TRACKER": "track dependencies",
    "EventPayload": "transport an event",
    "BretzelError": _ERROR,
    "CircularDependencyError": _ERROR,
    # The framework calls APP code from a coroutine — a ``def`` would
    # block the loop there, so it is offloaded onto the threadpool.
    "call_without_blocking": "call application code",
}

_THEME: dict[str, str] = {
    "Theme": "declare a theme",
    "ColorScheme": "declare a theme",
    "IconConfig": "declare a theme",
    "ScrollbarConfig": "declare a theme",
    "SEMANTIC_COLOR_NAMES": "constant",
    "DEFAULT_PALETTE_NAMES": "constant",
    "FONT_SLOT_NAMES": "constant",
    "SHAPE_SLOT_NAMES": "constant",
    "TEXT_SLOT_NAMES": "constant",
    "DEFAULT_SPACING_PX": "constant",
    "ThemeError": _ERROR,
}

#: What ``bretzel.components`` exports WITHOUT it being the catalogue.
#: Value objects one names in a signature (``Series``, ``Move``,
#: ``GraphNode``), a constant, and two functions. They travel with a
#: component without being one, so no component mechanism describes them
#: — and the exemption protecting the catalogue swallowed them with it.
#: The 102 component classes, by contrast, are NOT here: they are
#: filtered, not forgotten (cf. :func:`describe_module`).
_COMPONENTS: dict[str, str] = {
    "Column": "describe a table",
    "apply_query": "describe a table",
    "Series": "describe a chart",
    "Reference": "describe a chart",
    "GraphNode": "describe a diagram",
    "GraphEdge": "describe a diagram",
    "Track": "describe a media track",
    "Move": "handle drag and drop",
    # Re-exported — their card ALSO lives under
    # ``bretzel.state.datatable``, and ``SymbolDetail.exported_by`` says
    # so on each. The classification is the SAME on both sides: two needs
    # for one object would read as two objects.
    "DatatableState": "declare server state",
    "Query": "receive a reader query",
    "ui": "call a component",
    "dynamic_responsive_classes": "declare to the CSS compiler",
    "SANDBOX_BASELINE": "constant",
}

#: A table's two names. They come out through ``bretzel.components``,
#: whose surface IS the ``ui.*`` catalogue and which is exempted on that
#: ground (``test_module_surfaces_are_classified``) — but those two are
#: not part of it: they are a STATE and a MESSAGE, described by no
#: component mechanism. The exemption swallowed them, and
#: ``describe DatatableState`` therefore answered "is neither in the
#: components nor the modules" about the class every table subclasses.
#: We classify their module of origin, not their door: two entries, not
#: 115.
_DATATABLE: dict[str, str] = {
    "DatatableState": "declare server state",
    "Query": "receive a reader query",
}

#: ``bretzel.probe`` — the layer-7 one that DRIVES the running app.
#:
#: ⚠️ **Absent until 2026-09-12, and it is a hole paid for in greps.**
#: ``describe probe`` answered "is neither in the ``ui.*`` components nor
#: the modules", honestly adding "it does import, though". The measured
#: result while mounting ``examples/ecole``: writing a probe required
#: opening ``_probe.py`` — ``probe()``'s signature (is there a
#: ``strict=``? no; a ``size=``? yes) and ``Probe.requests``'s.
#:
#: The tooling exclusion's rationale — *"``describe`` is for writing an
#: app, not for reading itself"* — does not cover this package. One does
#: not write a probe to read the framework: one writes it to judge ONE'S
#: app, exactly as one writes a page. It is in fact the moment when one
#: least wants to open a framework file.
#:
#: ``cli``, ``introspect`` and ``lint`` stay out: one does not call them
#: from an app's code.
_PROBE: dict[str, str] = {
    "probe": "drive the running app",
    "Probe": "drive the running app",
    "Window": "drive the running app",
    "Net": "drive the running app",
    "Box": "drive the running app",
    "ProbeFailedError": _ERROR,
    "ElementNotFoundError": _ERROR,
    "DropMissedError": _ERROR,
    "ScopeNotReadableError": _ERROR,
}

#: module → classification table. The order is the reading order: one
#: mounts the app, declares its state, renders, then descends towards the
#: transport.
SECTIONS: dict[str, dict[str, str]] = {
    "bretzel": _TOPLEVEL,
    "bretzel.state": _STATE,
    "bretzel.state.datatable": _DATATABLE,
    "bretzel.components": _COMPONENTS,
    "bretzel.server": _SERVER,
    "bretzel.render": _RENDER,
    "bretzel.theme": _THEME,
    "bretzel.runtime": _RUNTIME,
    "bretzel.core": _CORE,
    "bretzel.probe": _PROBE,
}


def module_names() -> tuple[str, ...]:
    """The modules that have a classification table."""
    return tuple(SECTIONS)


#: The TOOLING packages, outside the sweep below. ``describe`` is for
#: writing an app, not for reading itself; and importing ``bretzel.lint``
#: from here would remove the guarantee that makes it extractable (the
#: ``lint-stays-extractable`` contract in ``.importlinter``).
_TOOLING = frozenset({"cli", "introspect", "lint"})


@cache
def public_owners() -> MappingProxyType[str, str]:
    """Public name → the package exporting it, over the whole app surface.

    **Unfiltered**: the catalogue's 102 classes are part of it, even
    though no section lists them. It is the only reading that answers
    "does this name import?", and that is the question the not-found
    message must settle — ``Button`` imports, whatever the table says.

    ⚠️ Filtering it on ``SECTIONS`` cost a regression the same day:
    covering ``bretzel.components`` took its 102 classes out of this
    sweep, and ``describe Button`` stopped pointing at
    ``describe button``. A "what is left" reading empties itself as soon
    as one repairs what was missing.

    Discovered, not written: a new facade enters it with no edit here,
    and ``test_a_public_name_is_never_reported_missing`` turns red if it
    leaves.
    """
    import bretzel

    out: dict[str, str] = {}
    for found in pkgutil.iter_modules(bretzel.__path__):
        if found.name in _TOOLING:
            continue
        module = importlib.import_module(f"bretzel.{found.name}")
        for symbol in getattr(module, "__all__", ()):
            out.setdefault(symbol, module.__name__)
    return MappingProxyType(out)


def uncovered_owners() -> MappingProxyType[str, str]:
    """Those of :func:`public_owners` that no section classifies.

    What the not-found message must say differently: no card, so we name
    the import door. Empty today — ``bretzel.components``'s thirteen
    non-catalogue names have been classified since 2026-09-06 — and kept
    for the next facade, which will arrive without a table.
    """
    return MappingProxyType({
        symbol: owner
        for symbol, owner in public_owners().items()
        if owner not in SECTIONS
    })


def describe_module(name: str) -> ModuleSection:
    """Read a module's ``__all__`` and classify every name by need.

    **A CATALOGUE class is removed from the population**, and never
    silently: ``Button``'s card is ``ui.button``'s, with its props, its
    events, its slots and its imperative surface. Making it a module
    symbol as well would produce a second, poorer card, under a name one
    can type.

    That is the reason that exempted ``bretzel.components`` from any
    classification, and it was true — for its 102 classes. It swallowed
    with them the thirteen names that are NOT catalogue: value objects
    one names in a signature, a constant, two functions. The filter keeps
    the reason and returns the thirteen.

    ⚠️ A re-exported name is NOT filtered: ``page`` comes out of
    ``bretzel`` and of ``bretzel.render``, and both sections list it —
    it is ``SymbolDetail.exported_by`` that carries the information
    ("Also in"). The version that filtered re-exports lived two minutes
    and removed 22 cards, including ``page``'s: the two halves filtered
    each other.

    The filter is DERIVED — identity on the ``ui`` namespace — so it
    cannot rot like a hand-written list.
    """
    module = importlib.import_module(name)
    categories = SECTIONS.get(name, {})
    exported = tuple(
        symbol
        for symbol in getattr(module, "__all__", ())
        if symbol not in _catalogue_names(name)
    )

    symbols = tuple(
        SurfaceSymbol(
            name=symbol,
            category=categories.get(symbol, CATEGORY_UNCLASSIFIED),
            kind=kind_of(value, symbol),
            summary=summarize(value),
        )
        for symbol in exported
        for value in [getattr(module, symbol, None)]
    )
    return ModuleSection(
        name=name,
        doc=first_doc_line(module),
        symbols=tuple(sorted(symbols, key=_reading_order(categories))),
        covered=bool(categories),
    )


@cache
def _catalogue_names(name: str) -> frozenset[str]:
    """The names of ``name`` that ARE a ``ui.*`` catalogue class.

    By identity, never by spelling: ``AccordionItem`` is
    ``ui.accordion_item``, and a string comparison misses everything
    carrying an underscore — 37 names out of 48, measured.
    """
    from bretzel.introspect.components import ui_name_of_class

    module = importlib.import_module(name)
    catalogue = ui_name_of_class()
    return frozenset(
        symbol
        for symbol in getattr(module, "__all__", ())
        for value in [getattr(module, symbol, None)]
        if isinstance(value, type) and value in catalogue
    )


def _reading_order(categories: dict[str, str]):
    """Sort by READING ORDER, not alphabetically.

    The tables above are written in the order one meets the needs — one
    mounts the app, declares its state, acts, renders, then descends
    towards the transport. That order is information, and losing it to
    the alphabet would open ``bretzel.state`` on "compose on the client"
    rather than on the four server scopes.

    A category's rank is therefore its rank of **first appearance** in
    the table: the order does not have to be maintained separately, it is
    already in the way the table is written.
    """
    ranks: dict[str, int] = {}
    for category in categories.values():
        ranks.setdefault(category, len(ranks))
    unclassified = len(ranks) + 1
    return lambda s: (ranks.get(s.category, unclassified), s.name)


def describe_modules() -> tuple[ModuleSection, ...]:
    """Every covered section, in reading order."""
    return tuple(describe_module(name) for name in SECTIONS)


def describe_toplevel_surface() -> tuple[SurfaceSymbol, ...]:
    """``bretzel.__all__`` classified — the surface one meets first.

    Kept as a named entry point because it is the surface the living
    documentation displays in its own right; it is a special case of
    :func:`describe_module`, not a second engine.
    """
    return describe_module("bretzel").symbols


def kind_of(value: object, name: str) -> str:
    if inspect.ismodule(value):
        return "module"
    if isinstance(value, type):
        return "class"
    if callable(value):
        return "decorator" if name in _DECORATORS else "function"
    return "value"


def first_doc_line(value: object) -> str | None:
    doc = inspect.getdoc(value)
    return doc.strip().splitlines()[0] if doc else None


def value_summary(value: object) -> str | None:
    """A constant's value — **its** summary, not its type's.

    ``inspect.getdoc`` on a constant returns its CLASS's docstring: the
    framework's 42 ``str`` constants all displayed
    ``str(object='') -> str``, and ``DEFAULT_TEXTS`` "dict() -> new empty
    dictionary". 46 index lines saying nothing, where the only thing one
    wants to know about a ``ROUTE_ACTION`` is its value.

    Sets are **sorted** before being returned: a ``frozenset`` of
    strings' iteration order depends on ``PYTHONHASHSEED``, so letting it
    through would make ``bretzel describe`` move from one process to the
    next and its freshness gate flicker.

    ``None`` for an arbitrary object (``TRACKER``, ``ui``): there, its
    class's docstring **is** the right summary, and its ``repr`` carries
    a memory address.
    """
    if isinstance(value, frozenset | set):
        body = ", ".join(repr(v) for v in sorted(value, key=repr))
        return f"{type(value).__name__}({{{body}}})" if body else f"{type(value).__name__}()"
    if value is None or isinstance(value, str | bytes | int | float | tuple | list | dict):
        return repr(value)
    return None


def summarize(value: object) -> str | None:
    """A symbol's index line: its value when it is one, otherwise the
    first line of its docstring."""
    return value_summary(value) or first_doc_line(value)
