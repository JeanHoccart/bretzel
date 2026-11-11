"""Introspection of the CLIENT RUNTIME — four surfaces read live.

The existing chapters introspect **Python** (a state class, a signature,
a ``ClientBinding``'s algebra). The runtime, for its part, is
**JavaScript**: ``bretzel/runtime/_src/*.js``. This module reads those
sources so the ``/runtime`` page copies nothing by hand.

Four surfaces:

- :func:`describe_directives` — the ``bz-*`` directives;
- :func:`describe_magics` — the variables injected into an expression;
- :func:`describe_runtime_api` — the global ``$bz`` object's surface;
- :func:`describe_runtime_modules` — the bundle's modules.

**What ``implemented`` says, and what it does not.** The directives'
vocabulary is declared on the Python side
(:mod:`bretzel.runtime.protocol`, one ``BZ_<NAME>_PREFIX`` per
directive) and rewired by hand on the JS side — the runtime cannot
import Python. Since the enumeration starts from the Python, only one
direction can be detected: **declared but never wired**. The reverse
(JS reading a token Python no longer emits) would require starting from
the JS and is not done here.

That direction is already gated at commit time by
``tests/consistency/test_python_js_mirror.py``, which discovers the same
constants by introspection and requires their presence in the bundle. So
the page is not the only net — it shows the same truth, one notch
stricter: comments stripped (the bundle contains the prose that
*documents* the directives, including those one would remove), and per
source module rather than on the concatenated bundle.

Known approximation: a token present as a marker rather than as wiring
(``createComment("bz-if")``) counts as wired. The mechanism sees
vocabulary, not semantics.

**Work note.** This module lives beside ``introspect.py`` rather than
inside it, for as long as the "API surface" work in progress stops
working there. Nothing justifies two modules in the end: when the two
branches meet, the content here folds back into ``introspect.py`` and
``runtime_blocks.py`` into ``blocks.py``.

⚠️ **The four surfaces are not yet registered** in
``tests/consistency/test_docs_coverage.py``'s ``SURFACES`` registry (the
same reason: the file is being edited in parallel). Until that is done, a
``CATEGORY_UNCLASSIFIED`` makes nobody blush and a regex that stopped
matching would empty its table in silence. The four dataclasses already
satisfy the ``Classified`` protocol — it is four entries to add, not code
to write.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import bretzel.runtime as _runtime
from bretzel.introspect import CATEGORY_UNCLASSIFIED
from bretzel.runtime import RUNTIME_MODULES as MODULES
from bretzel.runtime import RUNTIME_SOURCES as SOURCES

_RUNTIME_DIR = Path(_runtime.__file__).resolve().parent
_SRC = _RUNTIME_DIR / "_src"
_PROTOCOL = _RUNTIME_DIR / "protocol.py"

#: The kernel, ahead of the component engines in the declared order.
_CORE = {f"{name}.js" for name in MODULES[:MODULES.index("inputs/calendar/calendar")]}


# ── Reading the sources ────────────────────────────────────────────────

#: JS comments. The third copy in the repository: the canonical one is
#: ``tests/consistency/_discovery.py:strip_js_comments`` (promoted on
#: 2026-08-15). ``examples/`` never imports ``tests/`` — hence the copy,
#: aligned identically rather than rewritten. It carries the same
#: accepted approximation: a ``//`` in a literal (``"http://…"``) passes
#: for a comment; none of ``_src/``'s modules contains one. A real shared
#: home is still to be chosen.
_JS_LINE_COMMENT = re.compile(r"//.*$", re.MULTILINE)
_JS_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)


def strip_js_comments(source: str) -> str:
    """The JS stripped of its comments.

    Indispensable: ``directives.js``'s header *documents* the 13
    directives in prose. So sweeping the raw file would find the
    documentation, and a directive documented but never wired would pass
    for implemented — the exact false positive this page exists to make
    impossible.
    """
    return _JS_LINE_COMMENT.sub("", _JS_BLOCK_COMMENT.sub("", source))


@dataclass(frozen=True)
class _Source:
    name: str    # "directives.js"
    raw: str     # the file as it is (the header is a comment)
    code: str    # comments stripped


@lru_cache(maxsize=None)
def read_sources() -> tuple[_Source, ...]:
    """``_src/``'s modules, read ONCE, in bundle order.

    The glob lives here and nowhere else in the module: written twice, it
    becomes two ways of silently going empty the day ``_src/`` moves.
    (The repository already has its helper for that —
    ``_discovery.runtime_slabs`` — but it lives under ``tests/``, which
    ``examples/`` does not import.)
    """
    return tuple(
        _Source(name=path.name,
                raw=(text := path.read_text(encoding="utf-8")),
                code=strip_js_comments(text))
        for path in SOURCES
    )


def by_category(ops: list, order: dict[str, int]) -> tuple:
    """Sort by (category rank, name) — so the categories arrive
    contiguous, which the mirrors depend on to group with an
    ``itertools.groupby`` without re-sorting."""
    return tuple(sorted(ops, key=lambda o: (order.get(o.category, 9), o.name)))


# ── 1. Directives ──────────────────────────────────────────────────────

_DIRECTIVE_DISPLAY: dict[str, tuple[str, str, str]] = {
    # name → (category, syntax, what it guarantees)
    "bz-data": (
        'DOM structure',
        'bz-data="{ open: false }"',
        'Opens a local scope, keyed by bz-id — it SURVIVES the morph of a '
        'server refresh. Inside a scope method, write this.field.',
    ),
    "bz-if": (
        'DOM structure',
        'bz-if="expr"',
        'Really mounts / unmounts the subtree. Every mount starts from a '
        'fresh tree.',
    ),
    "bz-for": (
        'DOM structure',
        'bz-for="v in liste :key=v.id :flip"',
        'Keyed iteration over a single-root <template>. :key reuses the '
        'nodes; :flip animates the reflow of the rows that survive.',
    ),
    "bz-teleport": (
        'DOM structure',
        'bz-teleport="body"',
        'Projects the content elsewhere in the DOM; the scope stays '
        'resolved at the original place. Re-projects if the source '
        'changed.',
    ),
    "bz-text": (
        'reactive display',
        'bz-text="expr"',
        'textContent follows the value. Display only.',
    ),
    "bz-show": (
        'reactive display',
        'bz-show="expr"',
        'Toggles display. The element stays mounted (hence stays in the '
        'DOM for focus, measurement, tests).',
    ),
    "bz-class": (
        'reactive display',
        'bz-class="{ actif: open }"',
        'Adds / removes classes by truthiness. The static class= rendered '
        'by the server is a baseline that is never removable.',
    ),
    "bz-attr:": (
        'reactive display',
        'bz-attr:aria-expanded="open"',
        'A one-way reactive attribute. false/null/undefined remove the '
        'attribute; on a native form field, the property is updated too '
        '(otherwise a morph would empty the input).',
    ),
    "bz-model": (
        "two-way input",
        'bz-model="$bz.state.Form.default.email"',
        'Two-way binding, form controls only.',
    ),
    "bz-on:": (
        "user gesture",
        'bz-on:click="open = !open"',
        'Listens for an event. An element marked aria-disabled STARTS no '
        'interaction: activation events are ignored, the others pass '
        '(closing stays possible).',
    ),
    "bz-init": (
        "the node's lifecycle",
        'bz-init="setup()"',
        "Once only, at the node's first mount — and not replayed by a re-"
        'bind after a morph.',
    ),
    "bz-effect": (
        "the node's lifecycle",
        'bz-effect="void geom"',
        'A continuous reactive effect: replayed on every mutation of a '
        'signal it reads.',
    ),
    "bz-ref": (
        "the node's lifecycle",
        'bz-ref="track"',
        'Names the node in $refs. Registered across the whole tree BEFORE '
        'any binding, so a parent bz-init sees a child ref.',
    ),
}

_DIRECTIVE_ORDER = {
    'DOM structure': 0,
    'reactive display': 1,
    "two-way input": 2,
    "user gesture": 3,
    "the node's lifecycle": 4,
}


@dataclass(frozen=True)
class DirectiveOp:
    name: str            # "bz-show", "bz-on:"
    category: str
    syntax: str
    doc: str             # the guarantee, in French — editorial gloss
    constant: str        # the Python constant declaring it
    protocol_note: str   # the comment that constant carries
    implemented: bool    # a _src/ module wires it (comments stripped)


_PROTOCOL_COMMENT = re.compile(
    r'^(?:BZ_\w+_PREFIX)\s*:.*?=\s*"(?P<value>[^"]+)"\s*(?:#\s*(?P<note>.*))?$',
    re.MULTILINE,
)


@lru_cache(maxsize=None)
def protocol_notes() -> dict[str, str]:
    """``value → comment`` read from ``protocol.py``.

    The end-of-line comment IS the definition the base layer gives of its
    own directive. We show it as it is, beside the editorial gloss,
    rather than letting it be silently covered over by a second wording
    that might contradict it.
    """
    source = _PROTOCOL.read_text(encoding="utf-8")
    return {
        m.group("value"): (m.group("note") or "").strip()
        for m in _PROTOCOL_COMMENT.finditer(source)
    }


@lru_cache(maxsize=None)
def describe_directives() -> tuple[DirectiveOp, ...]:
    """The ``bz-*`` directives, enumerated from the base layer's public
    API.

    An entry absent from :data:`_DIRECTIVE_DISPLAY` comes out as
    ``CATEGORY_UNCLASSIFIED``: it still shows (nothing is lost) and, once
    the surface is registered in ``test_docs_coverage.py``'s registry, it
    will make the gate blush — so a human classifies it on purpose rather
    than by default.

    ``implemented`` is looked for in ALL of ``_src/``'s modules, not in
    the directives engine alone: ``bz-data`` is materialised by
    ``scope.js``, and moving another piece of wiring from one module
    to another is a legitimate refactor that must not trigger a false
    alarm.
    """
    notes = protocol_notes()
    sources = read_sources()
    ops: list[DirectiveOp] = []
    for const in dir(_runtime):
        if not (const.startswith("BZ_") and const.endswith("_PREFIX")):
            continue
        value = getattr(_runtime, const)
        category, syntax, doc = _DIRECTIVE_DISPLAY.get(
            value, (CATEGORY_UNCLASSIFIED, f'{value}="…"', "")
        )
        ops.append(DirectiveOp(
            name=value,
            category=category,
            syntax=syntax,
            doc=doc,
            constant=const,
            protocol_note=notes.get(value, ""),
            implemented=any(f'"{value}"' in s.code for s in sources),
        ))
    return by_category(ops, _DIRECTIVE_ORDER)


_ORDER_RE = re.compile(r'const ORDER = \[(?P<body>[^\]]*)\]')


@lru_cache(maxsize=None)
def binding_order() -> tuple[str, ...]:
    """The order in which the directives of the SAME element are wired,
    read from the engine. It is not cosmetic: ``ref`` first (a neighbour
    may read it), ``init`` last (the node is fully wired when it
    runs)."""
    for source in read_sources():
        match = _ORDER_RE.search(source.code)
        if match:
            return tuple(re.findall(r'"([^"]+)"', match.group("body")))
    return ()


# ── 2. Magics d'expression ─────────────────────────────────────────────

_MAGIC_DISPLAY: dict[str, tuple[str, str]] = {
    "$scope": ('scope', 'The current bz-data scope. It is on the scope '
                         'chain too, so a bare name reads it.'),
    "$el": ('the node', 'The element carrying the directive.'),
    "$refs": ('the node', 'The nodes named by bz-ref in this scope.'),
    "$event": ('the event', 'The DOM event — inside a bz-on: only.'),
    "$value": ('the event', 'The value written — inside a bz-model only.'),
    "$dispatch": ("act", '$dispatch(name, detail) — a CustomEvent '
                          'bubbling up from $el.'),
    "$nextTick": ("act", '$nextTick(fn) — after the signal flush, hence '
                          'after the DOM has been rewritten.'),
}

_MAGIC_ORDER = {'scope': 0, 'the node': 1, 'the event': 2, "act": 3}

_NEW_FUNCTION = re.compile(r"new Function\((?P<args>[^)]*)\)")


@dataclass(frozen=True)
class MagicOp:
    name: str
    category: str
    doc: str


@lru_cache(maxsize=None)
def describe_magics() -> tuple[MagicOp, ...]:
    """The variables injected into every ``bz-*`` expression.

    Read at their exact source: the argument list of the ``new Function``
    the expression compiler builds. Adding a magic to the engine adds it
    here — there is no other place where the list exists.
    """
    names: list[str] = []
    for source in read_sources():
        match = _NEW_FUNCTION.search(source.code)
        if match:
            names = re.findall(r'"(\$[A-Za-z]\w*)"', match.group("args"))
            break
    ops = [
        MagicOp(n, *_MAGIC_DISPLAY.get(n, (CATEGORY_UNCLASSIFIED, "")))
        for n in names
    ]
    return by_category(ops, _MAGIC_ORDER)


# ── 3. Surface $bz ─────────────────────────────────────────────────────

_API_DISPLAY: dict[str, tuple[str, str]] = {
    "signal": ('reactivity',
               'signal(init) → {get, set, peek, subscribe}. get() '
               'subscribes the current effect, peek() reads without '
               'subscribing, set() triggers nothing if the value is '
               'identical.'),
    "effect": ('reactivity',
               'effect(fn) → {dispose}. Runs straight away, runs again '
               'when a signal it read changes. The writes of a single tick'
               ' are merged into one re-execution.'),
    "computed": ('reactivity',
                 'computed(fn) → {get, peek, dispose}. A memoised '
                 'derivation, recomputed when a dependency moves.'),
    "state": ('state & transport',
              '$bz.state.<Class>.<key>.<field> — the signal of a client-'
              'state field, materialised at boot from the envelope.'),
    "notify": ('state & transport',
               'Pushes a toast onto the notification stack.'),
    "pending": ('state & transport',
                'pending(element|action_id, delay_ms) → the “an action is '
                'in flight” signal. An element walks up to the carrier of '
                'its hx-post; a string addresses the action from elsewhere'
                ' in the page. The delay is what avoids the flash on short'
                ' round trips. On the Python side: ``ui.pending()``.'),
    "version": ('state & transport',
                "The bundle's protocol version."),
    "helpers": ('shared helpers',
                'The bricks shared by the overlays and by the pointer-drag'
                ' family.'),
    "tip": ('shared helpers',
            "The page's one tooltip panel: ``open(anchor, opts)`` / "
            '``close()``. Every ``tooltip=`` shows it, and so do the '
            'collapsed sidebar rail and the charts.'),
    "num": ('shared helpers',
            'Pure numeric primitives: precision implied by a step.'),
    "parts": ('shared helpers',
              "The parts a page carries once — a calendar picker's header, "
              "a colour picker's palette: ``fill(host)`` clones the "
              '``<template data-bz-part>`` the host names into it.'),
    "fold": ('shared helpers',
             "The one form a search compares: lowercase, no accents, "
             "``ß`` as ``ss`` — twin of Python's ``bretzel.core.text.fold``, "
             'used by the combobox, ``filter_each`` and the datatable.'),
    "gesture": ("gesture engine",
                'The pointer gesture rules shared by drag-and-drop and the '
                "scheduler: when a press becomes a drag, the end-of-drag "
                'click swallowed, a dropped item that waits while the server '
                'asks.'),
    "dates": ('shared helpers',
              'The one date reader of the pickers: ``typed(text)`` reads a '
              'typed date in the page language\'s order (22/11/2026 is '
              'November 22nd in French), ``typedWeek``, and local-time '
              '``iso`` / ``addDays`` / ``addMonths`` / ``weekStartOf``.'),
    "times": ('shared helpers',
              'The one clock: ``shown(hhmm)`` writes an "HH:MM" as the '
              'page language does (« 14h30 » in French, « 2:30 PM » in '
              'American English), ``typed(text)`` reads it back, '
              '``pattern()`` is the empty field\'s hint, ``twelve()`` says '
              'whether the language counts its hours by twelve. Used by '
              'the time picker and the scheduler.'),
    "reportError": ('shared helpers',
                    'How the runtime reports an error it contains — a '
                    'directive or an effect that throws: ``console.error`` '
                    'naming what failed, then ``window.reportError``, so '
                    'whoever listens for uncaught errors still hears it. '
                    'The rest of the page goes on.'),
    "multiSelect": ('shared helpers',
                    'The membership algebra of a multiple selection, '
                    'shared by Select and Combobox.'),
    "dnd": ("gesture engine",
            'The Pointer Events drag-and-drop engine, shared by draggable '
            'and dropzone.'),
    "scheduler": ("gesture engine",
                  'Dragging a scheduler card to another time and pulling its '
                  'bottom edge; the card waits while a dialog asks.'),
    "verbs": ('shared helpers',
              'The client half of the VERBS (``bretzel.copy`` …): a '
              'browser action triggered from an ``on_*=``. Only ``copy`` '
              'lives there — ``print`` and ``fullscreen`` fit in an '
              'expression Python writes out in full. It carries the '
              'fallback outside a secure context, without which an '
              'internal tool served over ``http://`` on a local IP would '
              'copy nothing, in silence.'),
    "locale": ('shared helpers',
               'The month and day names, derived from ``<html lang>`` by '
               '``Intl``. Python cannot produce them: its ``locale`` '
               'module is process-global state.'),
}

_API_ORDER = {
    'reactivity': 0,
    'state & transport': 1,
    'shared helpers': 2,
    "gesture engine": 3,
    "component scope": 4,
    "internal": 5,
}

#: The keys that signal a "component scope factory" object. The
#: classification is MECHANICAL: one more component files itself, whereas
#: a really new API shape falls into unclassified. ``makeScope`` is
#: absorbed by ``\w+Scope`` — do not add it.
_SCOPE_KEYS = re.compile(r"\b(?:scope|single|multi|common|\w+Scope)\s*[:(]")

#: "Object-literal key" candidate: a name at the start of an indented
#: line, followed by ``:`` (a pair) or ``(`` (a shorthand method).
_MEMBER = re.compile(r"^(?P<indent> {2,8})(?P<name>\w+)\s*[:(]", re.MULTILINE)


def top_level_keys(body: str) -> tuple[str, ...]:
    """An object literal's FIRST-level keys.

    Filtered by the minimum indentation met, and not by a fixed bound: a
    bound let through the keywords in method bodies (``if (``,
    ``queueMicrotask(`` are indistinguishable from a shorthand method to
    a regex), and ``$bz.helpers`` came out with twelve members, two of
    them invented.
    """
    if not body.lstrip().startswith("{"):
        return ()   # a function or a scalar has no keys — without this
                    # guard, the body of a ``$bz.notify = function …``
                    # returned its first ``if`` as an API member
    candidates = [(m.group("indent"), m.group("name"))
                  for m in _MEMBER.finditer(body)]
    if not candidates:
        return ()
    top = min(len(indent) for indent, _ in candidates)
    return tuple(dict.fromkeys(
        name for indent, name in candidates if len(indent) == top
    ))

_ASSIGN = re.compile(r"(?:window\.)?\$bz\.(?P<name>[A-Za-z_]\w*)\s*=")


@dataclass(frozen=True)
class RuntimeApiOp:
    name: str
    category: str
    module: str
    doc: str
    members: tuple[str, ...]   # les clés de premier niveau, lues en direct

    @property
    def public(self) -> bool:
        return not self.name.startswith("_")


@lru_cache(maxsize=None)
def describe_runtime_api() -> tuple[RuntimeApiOp, ...]:
    """Everything the modules set on the global ``$bz`` object.

    The ``_`` prefix is authoritative: it classifies as "internal"
    without having to keep a list (the framework sets many, and it is not
    a decision to take every time). A PUBLIC name, on the other hand,
    must be classified — either by its shape (a scope factory is
    recognisable), or by hand in :data:`_API_DISPLAY`.

    ``members`` is read, never written by hand: an entry like
    ``$bz.helpers`` has ten keys, and listing them in prose made the
    eleventh a silent lie.
    """
    ops: list[RuntimeApiOp] = []
    seen: set[str] = set()
    for source in read_sources():
        matches = list(_ASSIGN.finditer(source.code))
        for index, match in enumerate(matches):
            name = match.group("name")
            if name in seen:
                continue
            seen.add(name)
            # The body stops at the NEXT assignment: a fixed-size window
            # overflowed onto the neighbour, and a future
            # ``$bz.router = makeRouter()`` set in a component module
            # inherited the ``scope:`` next door — classified "scope
            # factory" with affirmatively false documentation, instead of
            # stopping at unclassified.
            end = (matches[index + 1].start() if index + 1 < len(matches)
                   else len(source.code))
            body = source.code[match.end():end]
            members = top_level_keys(body)
            if name.startswith("_"):
                category, doc = "internal", ""
            elif name in _API_DISPLAY:
                category, doc = _API_DISPLAY[name]
            elif _SCOPE_KEYS.search(body):
                category = "component scope"
                doc = ("A scope factory, spread into the component's bz-"
                      'data.')
            else:
                category, doc = CATEGORY_UNCLASSIFIED, ""
            ops.append(RuntimeApiOp(
                name=name, category=category, module=source.name,
                doc=doc, members=members if not name.startswith("_") else (),
            ))
    return by_category(ops, _API_ORDER)


# ── 4. The bundle's modules ────────────────────────────────────────────

_HEADER = re.compile(r"^/\*\s*\S+\s+—\s*(?P<title>.*?)\s*$", re.MULTILINE)


@dataclass(frozen=True)
class RuntimeModuleOp:
    name: str
    category: str
    title: str
    lines: int


@lru_cache(maxsize=None)
def describe_runtime_modules() -> tuple[RuntimeModuleOp, ...]:
    """The modules concatenated into ``runtime.js``, in load order (the
    declared order is the topological one: signals before directives
    before scope).

    The title comes from the first header line, hence from the RAW text,
    the header being a comment. A module added appears here, classified,
    with no edit.
    """
    ops: list[RuntimeModuleOp] = []
    for source in read_sources():
        header = _HEADER.search(source.raw)
        title = header.group("title").rstrip("*/ ").strip() if header else ""
        ops.append(RuntimeModuleOp(
            name=source.name,
            category=("core" if source.name in _CORE else "component engine"),
            title=title,
            lines=len(source.raw.splitlines()),
        ))
    return tuple(ops)


@lru_cache(maxsize=None)
def bundle_facts() -> dict[str, int]:
    """The bundle's figures, measured — not announced. (The size budget
    the build's docstring promised was wrong by a factor of 2 before it
    was removed; so we show what we measure.)"""
    core = [m for m in describe_runtime_modules() if m.category == "core"]
    return {
        "modules": len(describe_runtime_modules()),
        "core_modules": len(core),
        "core_lines": sum(m.lines for m in core),
        "bundle_bytes": (_RUNTIME_DIR / "runtime.js").stat().st_size,
    }
