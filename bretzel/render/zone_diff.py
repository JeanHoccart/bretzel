"""Ship only the elements of a zone that changed.

Why
---
A ``@refreshable`` zone shipped WHOLE repeats, on every change, all that
did not move: changing one row's status re-sends the panel, the counters,
the toolbar and the whole table, where only three elements actually
differ: the panel, the status counters and the row.

How
---
Every element carrying an ``id`` (outside a ``<template>`` — but for a
``bz-teleport`` one —, an ``<svg>`` or a ``<math>``, where a lone patch
would not parse or would find
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
attributes do not. ``data-bz-subscribe-url`` is signed for the session:
counted, two clients of one zone would hold two fingerprints of the same
content, and it never changes within a session. ``data-bz-ts`` is
the render second — counted, every clickable element would look changed
one second later, and a zone with a single button would never be
recognised as unchanged. It is ignored, with two exceptions that keep its
meaning:

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

A list that changed
-------------------
A parent whose list of children changed — one child more or less, a new
order — does not ship WHOLE. Every element has two
more fingerprints: its **frame** — its own markup and its children that
are not addressed, without the addressed ones — and its **loose** one,
``whole`` without ``id`` nor ``bz-id``. Same frame, different ``own``:
only the LIST of addressed children moved. The parent then receives a
list patch (:class:`ListPatch`):

- a child with an ``id`` IS that id: kept wherever it went (``#id``),
  then diffed like any element, or inserted when the client never held
  it under this parent;
- children addressed by position are matched on their *loose*
  fingerprint (``difflib``): without ``key=``, the ids inside a child
  follow its rank, and the child after a removed one would look new.
  Matched, a child is kept, or morphed when its ids slid.

Any configuration: keyed or not, inserted, removed, reordered. One list
mechanism, one way to ship (:class:`Patch`, :func:`ship`).

A teleported panel
------------------
An overlay's panel (popover, dropdown, tooltip) travels in a
``<template bz-teleport="body">``: the runtime projects a copy under
``<body>``, where it lives. Opaque like any other template, it would ship
the whole popover for a box ticked inside it, and the runtime would
rebuild the panel — a blink. Its ids are therefore targets:
``getElementById`` finds them in the live copy, and the morph lands there.
Its children are never found by position — they are not the template's
children in the DOM —
so a change with no id around it still ships the overlay, whose panel
the runtime then morphs in place (``directives.js``, ``bindTeleport``).

Every patch travels in a ``<template>``: alone at the top of a response,
the HTML parser drops a ``<tr>``, and htmx reads out-of-band elements
from a template.
"""

from __future__ import annotations

import difflib
import hashlib
import re
from collections import OrderedDict
from collections.abc import Callable, Sequence
from collections.abc import Set as AbstractSet
from dataclasses import dataclass, field
from typing import Any

from bretzel.core.serialize import VOID_ELEMENTS
from bretzel.core.tree import Element, FragmentNode, HtmlNode, Node, TextNode
from bretzel.render.fusion import _flatten_fragments
from bretzel.runtime.protocol import (
    ADDRESSABLE_ID,
    AT_TAG_NAME,
    DATA_BZ_SIG,
    DATA_BZ_TS,
    DATA_SUBSCRIBE_URL,
    DATA_ZONE,
    DATA_ZONE_HASH,
    ROUTE_ACTION,
    SINK_ELEMENT_ID,
)

#: ``whole + own + frame + loose``, 8 bytes each (``_WHOLE`` …).
Fingerprints = dict[str, bytes]

#: How many element fingerprints the cache keeps, all zone versions
#: together, at about 100 bytes each: ~10 MB. Beyond, the
#: oldest versions go, and a client still holding one gets its zone
#: whole — slower, never wrong.
MAX_CACHED_ELEMENTS = 100_000

_DIGEST = 8
#: Where each fingerprint sits in an element's bytes.
_WHOLE, _OWN, _FRAME, _LOOSE = (slice(i * _DIGEST, (i + 1) * _DIGEST) for i in range(4))
#: An ``id`` a patch can name (``protocol.ADDRESSABLE_ID``, read by the
#: runtime too): another is reached by its position.
_ADDRESSABLE = re.compile(ADDRESSABLE_ID)
#: Joins a parent's key and an index into a position key: a control
#: character no ``id`` carries.
_POSITION = "\x1f"
#: Not content: the signature (a function of the other attributes), the
#: stamp itself, the refetch URL signed for the session, and the swap
#: instruction a zone shipped as a fragment carries and the same zone
#: rendered in its page does not.
_IGNORED = frozenset({DATA_BZ_SIG, DATA_ZONE_HASH, DATA_SUBSCRIBE_URL, "hx-swap-oob"})
#: Left out of the *loose* fingerprint: where an element is, not what it is.
_IDS = frozenset({"id", "bz-id"})
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
    #: among the parent's elements (:func:`_address` walks it back up).
    place: dict[str, tuple[str, int]] = field(default_factory=dict)
    #: The elements whose children the browser can find one by one, every
    #: one addressed — their list can be patched (:func:`changes`).
    listable: set[str] = field(default_factory=set)


@dataclass(slots=True, frozen=True)
class ZoneVersion:
    """What the cache keeps of a zone version: each identified element's
    fingerprints, and the ones that have identified descendants, with
    those (in order)."""

    elements: Fingerprints
    children: dict[str, tuple[str, ...]]

    @classmethod
    def of(cls, printed: ZonePrint) -> ZoneVersion:
        """The version a whole render describes (its ids must not repeat)."""
        assert printed.elements is not None
        return cls(printed.elements, {k: v for k, v in printed.children.items() if v})


@dataclass(slots=True)
class ListPatch:
    """A parent whose list of addressed children changed, nothing else.

    ``where`` finds the parent (:func:`_address`). ``ops`` describe the
    new children in order: ``#row-2`` keeps the child with that id,
    wherever the browser holds it (a drag and drop moves the cards before
    the server answers); ``k3`` keeps the child at rank 3 AMONG THOSE
    WITHOUT ID (the hour lines of a scheduler column stay put while its
    cards come and go), ``m3`` keeps it and morphs it into the next of
    ``nodes``; ``n`` inserts the next of ``nodes`` — or, when the browser
    holds an element with its id elsewhere, moves that one and morphs it.
    ``count`` is how many children without id the browser must hold when
    a rank is used: a walk that finds another number does not apply the
    patch, and asks for the zone again. Ops are separated by spaces — an
    id holds none."""

    where: dict[str, str]
    count: int
    ops: list[str]
    nodes: list[Element]


@dataclass(slots=True)
class Patch:
    """What to ship so that the client's copy becomes the fresh render, as
    :func:`changes` found it. :func:`ship` sends it."""

    #: Elements with an ``id``, morphed by it.
    morphs: list[Element] = field(default_factory=list)
    #: Elements without, each with where the browser finds it.
    placed: list[tuple[dict[str, str], Element]] = field(default_factory=list)
    lists: list[ListPatch] = field(default_factory=list)
    #: Children with no key, kept for their content, whose ids slid with
    #: their rank (a neighbour came or went) — each with where its parent
    #: is. Shipping them is right; a client state the runtime keys by
    #: ``bz-id`` does not follow them (``partials`` warns in debug).
    slid: list[tuple[dict[str, str], Element]] = field(default_factory=list)


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
        whole, _own, _refs, _addressed, _loose = self._walk(root, printed, opaque=False)
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

    def _heads(self, element: Element) -> tuple[bytes, bytes]:
        """The tag and the attributes that count, as the bytes the element's
        digests start with — and the same without the ids, for its *loose*
        digest (:data:`_IDS`). One pass, each encoded once: this runs for
        every element of every zone rendered."""
        parts, loose = [element.tag], [element.tag]
        for key, value in element.attrs.items():
            if key in _IGNORED:
                continue
            if key == DATA_BZ_TS:
                value = self._ts(element, value)
            part = f"\0{key}={value}"
            parts.append(part)
            if key not in _IDS:
                loose.append(part)
        return "".join(parts).encode(), "".join(loose).encode()

    def _walk(
        self, node: Node, printed: ZonePrint, *, opaque: bool,
        place: tuple[str, int] | None = None,
    ) -> tuple[bytes, bytes, tuple[str, ...], bool, bytes]:
        """``(whole, contribution to the parent's own, addressed elements at
        this level, whether this node is itself addressed, its content
        without ids)``. An addressed
        child contributes its mark to the parent's ``own`` and NOTHING to
        its ``frame``.

        An element is addressed by its ``id``, else by ``place`` — its
        index under its parent — when the browser can find it there too
        (:func:`_by_position`). ``own`` is only hashed apart from
        ``whole`` when an addressed descendant makes them differ."""
        if isinstance(node, Element):
            head, loose_head = self._heads(node)
            ident = node.attrs.get("id")
            if ident and not opaque and _ADDRESSABLE.match(str(ident)):
                key, mark = str(ident), b"#" + str(ident).encode() + b"\0"
            elif place is not None:
                # The tag is part of the mark: a child that changes tag
                # changes its parent's shape, so the parent ships.
                key, mark = position_key(*place), b"@" + node.tag.encode() + b"\0"
            else:
                key = None
            inner = opaque or (node.tag in _OPAQUE and not _teleports(node))
            kids = () if node.tag in VOID_ELEMENTS else _flatten_fragments(node.children)
            by_position = key is not None and not inner and _by_position(node, kids)
            refs: list[str] = []
            wholes, owns, frames, looses = [head], [head], [head], [loose_head]
            # Its list can be patched when the browser finds every child
            # one by one: each addressed, none a template or a ``bz-if``.
            listable = by_position
            index = 0
            for child in kids:
                child_place = None
                if isinstance(child, Element) and "bz-if" not in child.attrs:
                    if by_position and child.tag != "template":
                        child_place = (key, index)
                    index += 1
                child_whole, child_own, child_refs, child_addressed, child_loose = self._walk(
                    child, printed, opaque=inner, place=child_place)
                if isinstance(child, Element) and (
                        child_place is None or not child_addressed):
                    listable = False
                wholes.append(child_whole)
                looses.append(child_loose)
                owns.append(child_own)
                if not child_addressed:
                    frames.append(child_own)
                refs.extend(child_refs)
            # One hash over the concatenation: the same digest as feeding
            # the parts one by one, for a fraction of the calls.
            whole_digest = hashlib.blake2s(b"".join(wholes), digest_size=_DIGEST).digest()
            loose_digest = hashlib.blake2s(b"".join(looses), digest_size=_DIGEST).digest()
            own_digest = (hashlib.blake2s(b"".join(owns), digest_size=_DIGEST).digest()
                          if refs else whole_digest)
            frame_digest = (hashlib.blake2s(b"".join(frames), digest_size=_DIGEST).digest()
                            if refs else whole_digest)
            if key is None:
                return whole_digest, own_digest, tuple(refs), False, loose_digest
            if printed.elements is not None:
                if key in printed.elements:
                    printed.elements = None
                else:
                    printed.elements[key] = (whole_digest + own_digest + frame_digest
                                             + loose_digest)
                    printed.nodes[key] = node
                    printed.children[key] = tuple(refs)
                    if mark[:1] == b"@":
                        printed.place[key] = place
                    if listable:
                        printed.listable.add(key)
            return whole_digest, mark, (key,), True, loose_digest
        if isinstance(node, TextNode):
            text = b"t" + node.content.encode()
            return text, text, (), False, text
        if isinstance(node, HtmlNode):
            raw = b"h" + node.html.encode()
            return raw, raw, (), False, raw
        raise TypeError(f"Cannot fingerprint unknown Node type: {type(node).__name__}")


def position_key(parent: str, index: int) -> str:
    """A unique key for the ``index``-th element under ``parent`` — a
    control character no ``id`` carries. Never parsed back: the place is
    kept in :attr:`ZonePrint.place`."""
    return f"{parent}{_POSITION}{index}"


def is_positional(key: str) -> bool:
    """Is ``key`` a position (:func:`position_key`), not an ``id``?"""
    return _POSITION in key


def _teleports(node: Element) -> bool:
    """A ``<template bz-teleport>``: its content lives in the document,
    projected elsewhere — its ids are found there (cf. the docstring)."""
    return node.tag == "template" and "bz-teleport" in node.attrs


def _by_position(node: Element, kids: Sequence[Node]) -> bool:
    """Can the browser find ``node``'s children by position? Not when raw
    markup may add elements, nor inside a custom element, which builds its
    own content. (What the runtime inserts — ``bz-for`` rows, ``bz-if``
    mounts — carries ``data-bz-row``, and the runtime skips it; the server
    does not count ``bz-if`` elements either.)"""
    return ("-" not in node.tag and node.tag != "template"
            and not any(isinstance(kid, HtmlNode) for kid in kids))


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


def holding(printed: ZonePrint, root: Element, names: AbstractSet[str]) -> set[str]:
    """The addressed elements nearest to a form control named in ``names``.

    An action that sets a submitted field to something else than what was
    typed leaves the browser showing the typed text — not the render whose
    fingerprint it presents. Those elements must ship even when the
    fingerprints agree (:func:`changes`, ``stale``). One walk, run only
    when an action overrode a field.
    """
    keys = {id(node): key for key, node in printed.nodes.items()}
    found: set[str] = set()
    stack: list[tuple[Node, str]] = [(root, str(root.attrs.get("id")))]
    while stack:
        node, near = stack.pop()
        if isinstance(node, Element):
            near = keys.get(id(node), near)
            if node.attrs.get("name") in names:
                found.add(near)
        stack.extend((child, near) for child in getattr(node, "children", ()) or ())
    return found


def changes(printed: ZonePrint, root: Element, held: ZoneVersion,
            stale: AbstractSet[str] = frozenset()) -> Patch | None:
    """What to ship so that ``held`` becomes ``printed``.

    ``stale``: elements the browser no longer shows as ``held`` says
    (:func:`holding`) — shipped whatever their fingerprints, the walk
    going down to them.

    ``None`` when the zone must ship whole — its root changed beyond its
    list of children, or its ids repeat.
    """
    fresh = printed.elements
    old = held.elements
    root_id = root.attrs.get("id")
    if fresh is None or root_id not in old or root_id not in fresh:
        return None
    patch = Patch()
    shipped: list[str] = []
    parents = {child: key for key, kids in printed.children.items() for child in kids} \
        if stale else {}
    forced: set[str] = set()
    for key in stale:
        while key is not None and key not in forced:
            forced.add(key)
            key = parents.get(key)
    # Each parent's shape, computed once: every element sent under the
    # same parent walks the same levels.
    shapes: dict[str, str] = {}

    def visit(key: str) -> None:
        was, now = old.get(key), fresh[key]
        if was == now and key not in forced:
            return
        if key in stale:
            shipped.append(key)
        elif was is not None and was[_OWN] == now[_OWN]:
            for child in printed.children[key]:
                visit(child)
        elif was is not None and was[_FRAME] == now[_FRAME] and key in printed.listable:
            before, after = held.children.get(key, ()), printed.children[key]
            where, matched = _address(printed, key, shapes), _match(before, after, old, fresh)
            patch.lists.append(list_patch(where, before, after, printed.nodes, matched))
            # Same content without ids, not the same ids: they slid.
            patch.slid.extend((where, printed.nodes[new]) for new, (was, same) in matched.items()
                              if not same and old[was][_LOOSE] == fresh[new][_LOOSE])
            kept = set(before)
            for child in after:
                if child in kept and not is_positional(child):
                    visit(child)          # the same id: diffed like any element
        else:
            shipped.append(key)

    visit(str(root_id))
    if shipped[:1] == [root_id]:
        return None
    for key in shipped:
        if key in printed.place:
            patch.placed.append((_address(printed, key, shapes), printed.nodes[key]))
        else:
            patch.morphs.append(printed.nodes[key])
    return patch


def _match(before: Sequence[str], after: Sequence[str], old: Fingerprints,
           fresh: Fingerprints) -> dict[str, tuple[str, bool]]:
    """The children addressed by position that stay: new key → (old key,
    unchanged). Matched on their content without ids, like two texts; a
    run replaced by as many children stays in place, morphed."""
    olds = [k for k in before if is_positional(k)]
    news = [k for k in after if is_positional(k)]
    matcher = difflib.SequenceMatcher(
        None, [old[k][_LOOSE] for k in olds], [fresh[k][_LOOSE] for k in news], autojunk=False)
    matched: dict[str, tuple[str, bool]] = {}
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal" or (tag == "replace" and i2 - i1 == j2 - j1):
            for was, new in zip(olds[i1:i2], news[j1:j2], strict=True):
                matched[new] = (was, tag == "equal" and old[was][_WHOLE] == fresh[new][_WHOLE])
    return matched


def list_patch(where: dict[str, str], before: Sequence[str], after: Sequence[str],
               nodes: dict[str, Element], matched: dict[str, tuple[str, bool]]) -> ListPatch:
    """The ops turning the list ``before`` into ``after`` (cf.
    :class:`ListPatch`); ``nodes`` holds the fresh children, ``matched``
    the children by position that stay (:func:`_match`)."""
    held = set(before)
    rank = {k: r for r, k in enumerate(k for k in before if is_positional(k))}
    ops: list[str] = []
    sent: list[Element] = []
    for key in after:
        if key in matched:
            was, same = matched[key]
            ops.append(f"{'k' if same else 'm'}{rank[was]}")
            if same:
                continue
        elif key in held and not is_positional(key):
            ops.append(f"#{key}")
            continue
        else:
            ops.append("n")
        sent.append(nodes[key])
    return ListPatch(where, len(rank), ops, sent)


def _address(printed: ZonePrint, key: str,
             shapes: dict[str, str] | None = None) -> dict[str, str]:
    """Where the browser finds an element: its nearest identified ancestor,
    the path from there, and the shape of each level on the way — for an
    element with an ``id``, itself and an empty path. ``shapes`` keeps
    the parents' shapes across the calls of one :func:`changes`."""
    steps: list[int] = []
    parents: list[str] = []
    cursor = key
    while cursor in printed.place:
        cursor, index = printed.place[cursor]
        steps.append(index)
        parents.append(cursor)
    steps.reverse()
    parents.reverse()
    shapes = {} if shapes is None else shapes
    for p in parents:
        if p not in shapes:
            shapes[p] = shape_of(printed.nodes[p])
    return {"anchor": cursor, "path": ".".join(map(str, steps)),
            "shape": ".".join(shapes[p] for p in parents)}


def ship(zone_id: str, patch: Patch, fingerprinter: Fingerprinter,
         maps: ZoneMaps | SessionZoneMaps | None) -> list[Element]:
    """A patch as the response carries it, nested zones stamped.

    Each element with an ``id`` in a ``<template>``, morphed out of band
    by its namesake. The lists, then the elements without, in one block
    appended to the sink (``#bz-sink``): each ``<bz-at>`` says where — its
    nearest identified ancestor, the path from there, the shape of each
    level — and carries its elements in templates. The runtime walks there
    (skipping what it inserted itself), checks each shape, and applies
    it; a walk that does not land forgets the zone's fingerprint and asks
    for the zone again. The lists first: the other paths are the new ones.
    """
    def at(where: dict[str, str], nodes: Sequence[Node], **extra: str) -> Element:
        return Element(AT_TAG_NAME, {"zone": zone_id, **where, **extra}, tuple(
            Element("template", {}, (node,)) for node in stamp_zones(nodes, fingerprinter, maps)))

    out = [Element("template", {}, (Element(e.tag, {**e.attrs, "hx-swap-oob": "morph"}, e.children),))
           for e in stamp_zones(patch.morphs, fingerprinter, maps)
           if isinstance(e, Element)]
    moves = [at(lst.where, lst.nodes, list=" ".join(lst.ops), count=str(lst.count))
             for lst in patch.lists]
    moves += [at(where, [element]) for where, element in patch.placed]
    if moves:
        out.append(Element("div", {"hx-swap-oob": f"beforeend:#{SINK_ELEMENT_ID}"}, tuple(moves)))
    return out


class ZoneMaps:
    """Zone fingerprint → its elements' fingerprints, most recent first.

    Owned by the application (``Bretzel.zone_maps``), never by the module.
    Bounded by the number of elements, not of versions: a
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

    def scoped(self, session_id: str | None) -> SessionZoneMaps:
        """This cache as one session sees it: only the versions served to
        that session.

        ⚠️ A fingerprint is computable offline (the code is public), and
        the client presents it as « what I hold ». Shared by the whole
        app, the cache would answer a patch when ANY session had been
        served that version, the whole zone otherwise: an attacker would
        learn whether another session's zone held a guessed value — a
        mark, a status, a yes/no. A client only ever holds what it was
        served, so nothing is lost by asking per session.
        """
        return SessionZoneMaps(self, f"{session_id or ''}|")


class SessionZoneMaps:
    """:class:`ZoneMaps` under one session's prefix — same three methods."""

    def __init__(self, maps: ZoneMaps, prefix: str) -> None:
        self._maps = maps
        self._prefix = prefix

    def get(self, digest: str) -> ZoneVersion | None:
        return self._maps.get(self._prefix + digest)

    def put(self, printed: ZonePrint) -> None:
        if printed.elements is None:
            return
        self.put_version(printed.digest, ZoneVersion.of(printed))

    def put_version(self, digest: str, version: ZoneVersion) -> None:
        self._maps.put_version(self._prefix + digest, version)


def stamp_zones(
    nodes: Sequence[Node], fingerprinter: Fingerprinter, maps: ZoneMaps | SessionZoneMaps | None
) -> list[Node]:
    """Set :data:`DATA_ZONE_HASH` on every zone among ``nodes``.

    Whatever ships a zone's root — a page, a partial navigation, a zone
    shipped whole, a patched element holding a nested zone — goes through
    here, so no zone ever arrives without the fingerprint of what it
    carries. Inner zones first; the stamp itself is not content.
    """
    return [_stamp(node, fingerprinter, maps) for node in nodes]


def _stamp(node: Node, fingerprinter: Fingerprinter, maps: ZoneMaps | SessionZoneMaps | None) -> Node:
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


def stamped(zone: Element, printed: ZonePrint, maps: ZoneMaps | SessionZoneMaps | None) -> Element:
    """The zone's root carrying its fingerprint, cached for the next patch."""
    if maps is not None:
        maps.put(printed)
    return Element(zone.tag, {**zone.attrs, DATA_ZONE_HASH: printed.digest}, zone.children)
