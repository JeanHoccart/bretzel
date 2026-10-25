"""Ship only the elements of a zone that changed.

Why
---
A ``@refreshable`` zone came back WHOLE on every change. On the
comparison helpdesk (``python-ui-shootout``, 2026-10-23), changing one
ticket's status sent four zones — the panel, the sidebar counters, the
toolbar and a 50-row table: 326 KB of HTML, 18.6 KB gzipped, where
React, FastHTML or Dash send 3.4 to 6.8 KB. Between two consecutive
status changes, only three elements actually differ: the panel, the
status counters and the row. Shipping those alone: 6.3 KB.

How
---
Every element carrying an ``id`` (outside a ``<template>``, an ``<svg>``
or a ``<math>``, where a lone patch would not parse or would find
nothing) gets two fingerprints:

- **whole** — its subtree, everything included;
- **own** — the same, but each ``id``-carrying descendant counted by its
  ``id`` only. Two renders with the same ``own`` have the same skeleton:
  only identified descendants can differ.

The zone's fingerprint is its root's ``whole``. Comparing the client's
copy with the fresh render, element by element from the root: same
``whole``, nothing to send; same ``own``, the difference is lower down,
look at the identified descendants; otherwise ship this element, which
the runtime morphs in place by its ``id``.

The server keeps the fingerprints of a zone version, keyed by the zone
fingerprint, in a bounded LRU (:class:`ZoneMaps`). The client still
carries the reference: it presents the fingerprint of what it holds, as
it already did to silence an unchanged zone. A fingerprint the cache no
longer knows — evicted, another worker, a restart — ships the zone whole,
the old behaviour. So does a zone whose root skeleton changed.

What a fingerprint ignores
--------------------------
``hx-swap-oob`` is transport: a zone shipped as a fragment carries it,
the same zone in its page does not. ``data-bz-sig`` is a function of the
action, its arguments and the timestamp: it says nothing the other
attributes do not. ``data-bz-ts`` is
the render second — counted, every clickable element looked changed one
second later, and a zone with a single button was never recognised as
unchanged (the zone-level silence had that defect since 2026-09-08). It
is ignored, with two exceptions that keep its meaning:

- an ``@idempotent`` action keeps it: its timestamp is the deduplication
  key, and a re-rendered button must get a fresh one, as before;
- with ``action_max_age`` set, it counts by half-windows, so an element
  is re-sent before its signature expires.

Crossed responses
-----------------
Two requests leaving with the same base (an action and an SSE refetch)
can each patch the zone against it. Their union may be a mix no
fingerprint describes. The response therefore names its base
(``X-Bretzel-Zone-Bases``); the runtime adopts the new fingerprint only
if it still holds that base, and forgets it otherwise — the next
exchange ships the zone whole. A silenced zone names its base too: it is
an empty patch against what the client said it held.

Every patch travels in a ``<template>``: alone at the top of a response,
the HTML parser drops a ``<tr>`` (measured 2026-10-23: the row patch
arrived, 369 bytes, and the table did not move), and htmx reads
out-of-band elements from a template.
"""

from __future__ import annotations

import hashlib
from collections import OrderedDict
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any

from bretzel.core.serialize import VOID_ELEMENTS
from bretzel.core.tree import Element, FragmentNode, HtmlNode, Node, TextNode
from bretzel.render.fusion import _flatten_fragments
from bretzel.runtime.protocol import (
    AT_TAG_NAME,
    DATA_BZ_SIG,
    DATA_BZ_TS,
    DATA_ZONE,
    DATA_ZONE_HASH,
    ROUTE_ACTION,
    SINK_ELEMENT_ID,
)

#: ``whole + own``, 8 bytes each.
Fingerprints = dict[str, bytes]

#: How many element fingerprints the cache keeps, all zone versions
#: together. A 50-row table zone holds ~1 700 addressed elements (by id or by position), about
#: 100 bytes each: 100 000 is ~60 such versions and ~10 MB. Beyond, the
#: oldest versions go, and a client still holding one gets its zone
#: whole — slower, never wrong.
MAX_CACHED_ELEMENTS = 100_000

_DIGEST = 8
#: Not content: the signature (a function of the other attributes), the
#: stamp itself, and the swap instruction a zone shipped as a fragment
#: carries and the same zone rendered in its page does not.
_IGNORED = frozenset({DATA_BZ_SIG, DATA_ZONE_HASH, "hx-swap-oob"})
#: Subtrees whose ids cannot be patch targets (cf. the module docstring).
_OPAQUE = frozenset({"template", "svg", "math"})
_ACTION_PREFIX = f"{ROUTE_ACTION}/"


@dataclass(slots=True)
class ZonePrint:
    """A zone's fingerprints, as one render produced them.

    ``elements`` is ``None`` when an ``id`` repeats: a patch could not say
    which element it targets, so the zone can only ship whole — its
    ``digest`` still silences it when nothing moved.
    """

    digest: str
    elements: Fingerprints | None
    nodes: dict[str, Element] = field(default_factory=dict)
    #: Each identified element's nearest identified descendants.
    children: dict[str, tuple[str, ...]] = field(default_factory=dict)
    #: An element addressed by position: its parent's key and its index
    #: among the parent's elements (:func:`at_position` walks it back up).
    place: dict[str, tuple[str, int]] = field(default_factory=dict)


@dataclass(slots=True, frozen=True)
class ZoneVersion:
    """What the cache keeps of a zone version: each identified element's
    fingerprints, and the ones that have identified descendants, with
    those (in order) — what a rows-only refresh needs to know which rows
    the client holds, and where."""

    elements: Fingerprints
    children: dict[str, tuple[str, ...]]

    @classmethod
    def of(cls, printed: ZonePrint) -> ZoneVersion:
        """The version a whole render describes (its ids must not repeat)."""
        assert printed.elements is not None
        return cls(printed.elements, {k: v for k, v in printed.children.items() if v})


@dataclass(slots=True)
class RowReport:
    """What a keyed ``ui.table`` rendered during a rows-only refresh."""

    #: ``False`` when the table cannot work row by row (no row key).
    supported: bool
    #: The id every row id of this table starts with.
    prefix: str = ""
    #: The ids the requested rows carry (listed or not).
    wanted: set[str] = field(default_factory=set)
    #: The row ids of the fresh list, in order.
    order: list[str] = field(default_factory=list)
    #: Row id → the freshly rendered row, for the requested rows listed.
    rendered: dict[str, Element] = field(default_factory=dict)


@dataclass(slots=True)
class RowsOnly:
    """The render context's state while a zone renders for some rows:
    the keys asked for, and what each keyed table filed."""

    keys: frozenset[str]
    reports: list[RowReport] = field(default_factory=list)


@dataclass(slots=True)
class RowPatch:
    """A rows-only refresh, ready to ship: the rows to morph, the ids to
    remove, and the client's version afterwards with its fingerprint."""

    rows: list[Element]
    removed: list[str]
    version: ZoneVersion
    digest: str


class Fingerprinter:
    """Computes the fingerprints of a tree under one render's rules."""

    def __init__(
        self,
        *,
        action_max_age: int | None = None,
        is_idempotent: Callable[[str], bool] = lambda _action_id: False,
    ) -> None:
        self._window = max(1, action_max_age // 2) if action_max_age else None
        self._is_idempotent = is_idempotent
        self._idempotent: dict[str, bool] = {}

    def zone(self, root: Element) -> ZonePrint:
        printed = ZonePrint(digest="", elements={})
        whole, _own, _refs = self._walk(root, printed, opaque=False)
        printed.digest = whole.hex()
        return printed

    def _ts(self, element: Element, value: Any) -> str:
        action = str(element.attrs.get("hx-post", ""))
        if action:
            action_id = action.removeprefix(_ACTION_PREFIX)
            if action_id not in self._idempotent:
                self._idempotent[action_id] = self._is_idempotent(action_id)
            if self._idempotent[action_id]:
                return str(value)
        if self._window is not None:
            try:
                return str(int(value) // self._window)
            except (TypeError, ValueError):
                return str(value)
        return ""

    def _head(self, element: Element) -> bytes:
        """The tag and the attributes that count, as the bytes the element's
        digests start with. One string, encoded once: this runs for every
        element of every zone rendered."""
        parts = [element.tag]
        for key, value in element.attrs.items():
            if key in _IGNORED:
                continue
            if key == DATA_BZ_TS:
                value = self._ts(element, value)
            parts.append(f"\0{key}={value}")
        return "".join(parts).encode()

    def _walk(
        self, node: Node, printed: ZonePrint, *, opaque: bool,
        place: tuple[str, int] | None = None,
    ) -> tuple[bytes, bytes, tuple[str, ...]]:
        """``(whole, contribution to the parent's own, addressed elements at
        this level)``.

        An element is addressed by its ``id``, else by ``place`` — its
        index under its parent — when the browser can find it there too
        (:func:`_by_position`). ``own`` is only hashed apart from
        ``whole`` when an addressed descendant makes them differ."""
        if isinstance(node, Element):
            head = self._head(node)
            ident = node.attrs.get("id")
            if ident and not opaque:
                key, mark = str(ident), b"#" + str(ident).encode() + b"\0"
            elif place is not None:
                # The tag is part of the mark: a child that changes tag
                # changes its parent's shape, so the parent ships.
                key, mark = position_key(*place), b"@" + node.tag.encode() + b"\0"
            else:
                key = None
            inner = opaque or node.tag in _OPAQUE
            kids = () if node.tag in VOID_ELEMENTS else _flatten_fragments(node.children)
            by_position = key is not None and not inner and _by_position(node, kids)
            refs: list[str] = []
            wholes, owns = [head], [head]
            index = 0
            for child in kids:
                child_place = None
                if isinstance(child, Element) and "bz-if" not in child.attrs:
                    if by_position and child.tag != "template":
                        child_place = (key, index)
                    index += 1
                child_whole, child_own, child_refs = self._walk(
                    child, printed, opaque=inner, place=child_place)
                wholes.append(child_whole)
                owns.append(child_own)
                refs.extend(child_refs)
            # One hash over the concatenation: the same digest as feeding
            # the parts one by one, for a fraction of the calls.
            whole_digest = hashlib.blake2s(b"".join(wholes), digest_size=_DIGEST).digest()
            own_digest = (hashlib.blake2s(b"".join(owns), digest_size=_DIGEST).digest()
                          if refs else whole_digest)
            if key is None:
                return whole_digest, own_digest, tuple(refs)
            if printed.elements is not None:
                if key in printed.elements:
                    printed.elements = None
                else:
                    printed.elements[key] = whole_digest + own_digest
                    printed.nodes[key] = node
                    printed.children[key] = tuple(refs)
                    if mark[:1] == b"@":
                        printed.place[key] = place
            return whole_digest, mark, (key,)
        if isinstance(node, TextNode):
            text = b"t" + node.content.encode()
            return text, text, ()
        if isinstance(node, HtmlNode):
            raw = b"h" + node.html.encode()
            return raw, raw, ()
        raise TypeError(f"Cannot fingerprint unknown Node type: {type(node).__name__}")


def position_key(parent: str, index: int) -> str:
    """A unique key for the ``index``-th element under ``parent`` — a
    control character no ``id`` carries. Never parsed back: the place is
    kept in :attr:`ZonePrint.place`."""
    return f"{parent}\x1f{index}"


def _by_position(node: Element, kids: Sequence[Node]) -> bool:
    """Can the browser find ``node``'s children by position? Not when raw
    markup may add elements, nor inside a custom element, which builds its
    own content. (What the runtime inserts — ``bz-for`` rows, ``bz-if``
    mounts — carries ``data-bz-row``, and the runtime skips it; the server
    does not count ``bz-if`` elements either.)"""
    return "-" not in node.tag and not any(isinstance(kid, HtmlNode) for kid in kids)


def shape_of(element: Element) -> str:
    """A short fingerprint of an element's children as the runtime sees
    them — djb2 over their tags joined by ``,``, ``bz-if`` ones left out.
    The runtime computes the same from the DOM (``localName``, skipping
    ``data-bz-row``) before each step of a walk: a tag alone does not tell
    two spans apart."""
    tags = [kid.tag for kid in _flatten_fragments(element.children)
            if isinstance(kid, Element) and "bz-if" not in kid.attrs]
    h = 5381
    for char in ",".join(tags):
        h = ((h << 5) + h + ord(char)) & 0xFFFFFFFF
    return format(h, "x")


def changed_elements(printed: ZonePrint, root: Element, held: Fingerprints) -> list[str] | None:
    """The addresses (ids or positions) of the elements to ship so that
    ``held`` becomes ``printed``; ``printed.nodes`` holds them.

    ``None`` when the zone must ship whole — its root skeleton changed, or
    its ids repeat.
    """
    fresh = printed.elements
    root_id = root.attrs.get("id")
    if fresh is None or root_id not in held or root_id not in fresh:
        return None
    out: list[str] = []

    def visit(key: str) -> None:
        was, now = held.get(key), fresh[key]
        if was == now:
            return
        if was is not None and was[_DIGEST:] == now[_DIGEST:]:
            for child in printed.children[key]:
                visit(child)
        else:
            out.append(key)

    visit(str(root_id))
    if out and out[0] == root_id:
        return None
    return out


def as_patch(element: Element) -> Element:
    """The element as an out-of-band morph of its namesake, in a template."""
    patch = Element(element.tag, {**element.attrs, "hx-swap-oob": "morph"}, element.children)
    return Element("template", {}, (patch,))


def at_position(zone_id: str, printed: ZonePrint, placed: Sequence[tuple[str, Element]]) -> Element:
    """The changes to elements with no ``id``, in one out-of-band block for
    the sink: each ``<bz-at>`` says where the element is — its nearest
    identified ancestor, the path from there, the shape of each level —
    and what it becomes. The runtime walks there (skipping what it
    inserted itself), checks each shape, and morphs it; a walk that does
    not land forgets the zone's fingerprint and asks for the zone again."""
    moves = []
    for key, element in placed:
        steps: list[int] = []
        parents: list[str] = []
        cursor = key
        while cursor in printed.place:
            cursor, index = printed.place[cursor]
            steps.append(index)
            parents.append(cursor)
        steps.reverse()
        parents.reverse()
        moves.append(Element(AT_TAG_NAME, {
            "zone": zone_id, "anchor": cursor, "path": ".".join(map(str, steps)),
            "shape": ".".join(shape_of(printed.nodes[p]) for p in parents),
        }, (Element("template", {}, (element,)),)))
    return Element("div", {"hx-swap-oob": f"beforeend:#{SINK_ELEMENT_ID}"}, tuple(moves))


def removal(ident: str) -> Element:
    """The out-of-band removal of a table row, in a template (htmx's
    ``delete`` swap takes the target by id, whatever the content)."""
    return Element("template", {}, (Element("tr", {"id": ident, "hx-swap-oob": "delete"}, ()),))


class ZoneMaps:
    """Zone fingerprint → its elements' fingerprints, most recent first.

    Owned by the application (``Bretzel.zone_maps``), never by the module
    (anti-rule 2). Bounded by the number of elements, not of versions: a
    small zone costs little, a large one counts for what it holds.
    """

    def __init__(self, max_elements: int = MAX_CACHED_ELEMENTS) -> None:
        self._maps: OrderedDict[str, ZoneVersion] = OrderedDict()
        self._elements = 0
        self._max = max_elements

    def get(self, digest: str) -> ZoneVersion | None:
        found = self._maps.get(digest)
        if found is not None:
            self._maps.move_to_end(digest)
        return found

    def put(self, printed: ZonePrint) -> None:
        if printed.elements is None:
            return
        self.put_version(printed.digest, ZoneVersion.of(printed))

    def put_version(self, digest: str, version: ZoneVersion) -> None:
        if digest in self._maps:
            self._maps.move_to_end(digest)
            return
        self._maps[digest] = version
        self._elements += len(version.elements)
        while self._elements > self._max and len(self._maps) > 1:
            _, dropped = self._maps.popitem(last=False)
            self._elements -= len(dropped.elements)


def stamp_zones(
    nodes: Sequence[Node], fingerprinter: Fingerprinter, maps: ZoneMaps | None
) -> list[Node]:
    """Set :data:`DATA_ZONE_HASH` on every zone among ``nodes``.

    Whatever ships a zone's root — a page, a partial navigation, a zone
    shipped whole, a patched element holding a nested zone — goes through
    here, so no zone ever arrives without the fingerprint of what it
    carries. Inner zones first; the stamp itself is not content.
    """
    return [_stamp(node, fingerprinter, maps) for node in nodes]


def _stamp(node: Node, fingerprinter: Fingerprinter, maps: ZoneMaps | None) -> Node:
    if not isinstance(node, (Element, FragmentNode)) or (
        isinstance(node, Element) and node.tag == "template"
    ):
        return node
    children = node.children
    for i, child in enumerate(node.children):
        new = _stamp(child, fingerprinter, maps)
        if new is not child:
            if children is node.children:
                children = list(node.children)
            children[i] = new
    if children is not node.children:
        node = (Element(node.tag, node.attrs, tuple(children))
                if isinstance(node, Element) else FragmentNode(tuple(children)))
    if isinstance(node, Element) and DATA_ZONE in node.attrs and node.attrs.get("id"):
        return stamped(node, fingerprinter.zone(node), maps)
    return node


def stamped(zone: Element, printed: ZonePrint, maps: ZoneMaps | None) -> Element:
    """The zone's root carrying its fingerprint, cached for the next patch."""
    if maps is not None:
        maps.put(printed)
    return Element(zone.tag, {**zone.attrs, DATA_ZONE_HASH: printed.digest}, zone.children)


def row_patch(
    reports: list[RowReport], held: ZoneVersion, held_digest: str, fingerprinter: Fingerprinter
) -> RowPatch | None:
    """The patch of a rows-only refresh — or ``None`` when it cannot be
    done row by row.

    Row by row means: every row the client holds is still listed, in the
    same order, except the requested rows that left the list. A new row,
    a new order, an empty list (its empty state) or a table without row
    keys ship the zone whole.

    The ancestors' fingerprints are not recomputed: a stale ``whole``
    only makes the next diff look one level deeper, never stop short. The
    new version's fingerprint is its base's plus what changed — a whole
    render never yields it, so an unchanged refresh after a row patch is
    diffed (to nothing) rather than silenced.
    """
    if not reports or not all(r.supported for r in reports):
        return None
    elements = dict(held.elements)
    children = dict(held.children)
    rows: list[Element] = []
    removed: list[str] = []
    changes = hashlib.blake2s(held_digest.encode(), digest_size=_DIGEST)
    for report in reports:
        listed = set(report.order)
        parent = next((p for rid in report.order[:1]
                       for p, kids in children.items() if rid in kids), None)
        if parent is None:
            return None
        held_rows = [rid for rid in children[parent] if rid.startswith(report.prefix)]
        gone = sorted(rid for rid in report.wanted - listed if rid in held_rows)
        if [rid for rid in held_rows if rid not in gone] != report.order:
            return None
        for rid in gone:
            _forget(rid, elements, children)
            children[parent] = tuple(c for c in children[parent] if c != rid)
            removed.append(rid)
            changes.update(b"-" + rid.encode())
        for rid, row in report.rendered.items():
            printed = fingerprinter.zone(row)
            if printed.elements is None:
                return None
            _forget(rid, elements, children)
            version = ZoneVersion.of(printed)
            elements.update(version.elements)
            children.update(version.children)
            rows.append(row)
            changes.update(rid.encode() + printed.elements[rid])
    return RowPatch(rows, removed, ZoneVersion(elements, children), changes.hexdigest())


def _forget(ident: str, elements: Fingerprints, children: dict[str, tuple[str, ...]]) -> None:
    """Drop an element and its identified descendants from a version."""
    for child in children.pop(ident, ()):
        _forget(child, elements, children)
    elements.pop(ident, None)
