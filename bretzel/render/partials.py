"""Partial rendering — single ``@refreshable`` section + state delta.

Triggered by:

- A zone enqueued during an action — by a ``deps=`` state change or the
  free :func:`refresh` — the pipeline drains
  :attr:`RenderContext.refresh_queue` at end-of-action and emits each
  section as an out-of-band swap.
- An SSE-driven refetch (``GET /_bretzel/refetch/<state>/<zone>``) from
  the client (manual refresh or an SSE dep-change fan-out).

The output is **not** a full HTML5 document — just the inner content
of the swap target plus a ``<bz-patch>`` tag carrying the
post-action client-state patches. Layer 6 wraps it in a Starlette
``HTMLResponse``; we stop at the bytes.

"""

from __future__ import annotations

import json
import logging
import re
import time
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from typing import Any

from bretzel.core import call_without_blocking
from bretzel.core.serialize import serialize
from bretzel.core.tree import Element, Node
from bretzel.render.context import RenderContext, use_context
from bretzel.render.decorators.refreshable import (
    RefreshableHandle,
    drain_pending_async_zones,
    zone_attrs,
)
from bretzel.render.fusion import BZ_ID_ATTR, fuse_or_wrap
from bretzel.render.types import BretzelApp
from bretzel.render.zone_diff import (
    Fingerprinter,
    RowPatch,
    RowsOnly,
    ZonePrint,
    ZoneVersion,
    as_patch,
    at_position,
    changed_elements,
    removal,
    row_patch,
    stamp_zones,
    stamped,
)
from bretzel.runtime.envelope import serialize_patch
from bretzel.runtime.protocol import (
    HEADER_ZONE_BASES,
    HEADER_ZONE_HASHES,
    TITLE_EVENT,
)
from bretzel.state.persistence.client_bridge import instance_key
from bretzel.state.scopes.client import ClientState, rendering_scope

#: The ``<template>`` whose content the runtime projects under
#: ``<body>``. Written here rather than imported from ``components``:
#: ``render`` does not reach up the stack at load time (principle 5).
TELEPORT_ATTR = "bz-teleport"

# ───────────────────────────────────────────────────────────────────────────
# Result type
# ───────────────────────────────────────────────────────────────────────────


_log = logging.getLogger("bretzel.render.partials")


@dataclass(slots=True)
class RenderResult:
    """The output of a render call ready for Layer 6 to wrap.

    Carries everything the server needs to assemble a Starlette
    ``Response`` — the body, the response headers, the status code,
    and the cookie ops collected on the way.
    """

    body: str
    status_code: int = 200
    headers: dict[str, str] = field(default_factory=dict)
    new_cookies: dict[str, dict[str, Any]] = field(default_factory=dict)
    deleted_cookies: set[str] = field(default_factory=set)


# ───────────────────────────────────────────────────────────────────────────
# Public entry — render_partial
# ───────────────────────────────────────────────────────────────────────────


async def render_partial(
    app: BretzelApp,
    handle: RefreshableHandle,
    *,
    ctx: RenderContext,
    extra_handles: Iterable[RefreshableHandle] = (),
) -> RenderResult:
    """Render refreshable regions and the client-state delta."""
    ctx.is_partial = True

    # Every refreshable rides as an OOB fragment. The dispatcher
    # (there is NO custom dispatcher: ``05_bridge.js`` enriches the
    # headers of a native htmx POST) issues the action POST with
    # ``swap: 'none'`` — the response body is never swapped into the
    # trigger, only ``hx-swap-oob`` fragments find their target by id.
    # If we emitted the primary without ``hx-swap-oob``, it would be
    # silently dropped. (V1 made the same call: every refresh emits as
    # OOB, swap-by-id, no trigger-vs-target distinction.)
    # ── A nested zone ships only ONCE ─────────────────────────────
    # The parent renders its subtree, child included; if the child is
    # ALSO in the queue, its fragment goes out a second time and the
    # morph throws one away. Measured: two zones on the same state, 200
    # rows in the child → 19.7 KB of which half is useless; at three
    # levels, the inside goes out THREE times.
    #
    # Nesting cannot be known any earlier: ``enqueue_deps`` sees only
    # declarations, and "parent calls child" is a RENDER fact,
    # conditional at that. So it is discovered here, once the tree is
    # built, and it costs nothing more — the tree is already there.
    #
    # Both directions, because the queue's order is that of the
    # decorations: a zone already covered is not rendered AT ALL (we save
    # the server work too), and if the child came first, its fragment is
    # removed when the parent covers it.
    ordered: list[RefreshableHandle] = []
    seen: set[str] = set()
    for h in (handle, *extra_handles):
        if h.id not in seen:
            seen.add(h.id)
            ordered.append(h)

    emitted: dict[str, str] = {}
    covered: set[str] = set()
    #: What this response ships, by zone — sent back to the client, who
    #: will present it to us again on the next request.
    digests: dict[str, str] = {}
    #: The fingerprint each PATCHED zone was diffed against (cf.
    #: ``render/zone_diff.py``, "Crossed responses").
    bases: dict[str, str] = {}
    # Optional, so not in the ``BretzelApp`` protocol: an app without the
    # cache (a test rig) still silences unchanged zones, and ships the
    # others whole.
    maps = getattr(app, "zone_maps", None)
    fingerprinter = fingerprinter_for(app)
    #: ``debug`` only: what each zone cost to render, in ``Server-Timing``
    #: — the browser's DevTools show it next to the request. Measured
    #: blind on 2026-10-23: a status change spent 64 of its 110 ms
    #: re-rendering a 50-row table for one changed row, and nothing in
    #: the response said so.
    timings: list[str] = []
    debug = bool(getattr(app, "debug", False))
    for h in ordered:
        if h.id in covered:
            continue
        started = time.perf_counter()
        held = ctx.zone_hashes.get(h.id)
        # ── Rows only: ``refresh(zone, rows=[…])`` ───────────────────
        # The zone runs again but its keyed table renders those rows
        # alone; whatever cannot be done row by row falls through to the
        # whole render just below (``render/zone_diff.row_patch``).
        known = maps.get(held) if maps is not None and held else None
        rows = ctx.zone_rows.get(h.id)
        if rows and known:
            patched = await _rows_only(app, h, ctx, rows, known, held, fingerprinter)
            if patched is not None:
                if debug:
                    timings.append(_timing(h, time.perf_counter() - started))
                maps.put_version(patched.digest, patched.version)
                emitted[h.id] = _ship(patched.rows, patched.removed, fingerprinter, maps)
                digests[h.id], bases[h.id] = patched.digest, held
                continue
        try:
            root = await _render_one(app, h, ctx, oob=True)
        except Exception as exc:  # broad on purpose — see the docstring next door
            emitted[h.id] = _zone_failure_fragment(app, h, exc)
            continue
        if debug:
            timings.append(_timing(h, time.perf_counter() - started))
        for zone_id in _zone_ids_inside(root, among=seen):
            covered.add(zone_id)
            emitted.pop(zone_id, None)
            digests.pop(zone_id, None)
            bases.pop(zone_id, None)
        # ── Silent, patched or whole ──────────────────────────────────
        #
        # The render is already paid for here — it is the shipping, the
        # gzip and the morph that are saved. A zone whose render has not
        # moved does not go out (measured on ``examples/messagerie`` on
        # 2026-09-08: re-clicking an open thread, 9 461 bytes and 50 ms →
        # 300 bytes and 10 ms); one that moved sends only its changed
        # elements when the client presents a fingerprint the cache knows.
        # ``render/zone_diff.py`` holds the how and the guarantees: an
        # absent, stale or lying fingerprint can only cause a re-ship.
        printed = fingerprinter.zone(root) if isinstance(root, Element) else None
        if printed is None:
            emitted[h.id] = serialize(root)
            continue
        digests[h.id] = printed.digest
        if maps is not None:
            maps.put(printed)
        if held == printed.digest:
            bases[h.id] = held
            continue
        patch = changed_elements(printed, root, known.elements) if known else None
        if patch is not None:
            emitted[h.id] = _ship(
                [printed.nodes[k] for k in patch if k not in printed.place], (),
                fingerprinter, maps, zone_id=h.id, printed=printed,
                placed=[k for k in patch if k in printed.place])
            bases[h.id] = held
            continue
        inner = Element(root.tag, root.attrs, tuple(stamp_zones(root.children, fingerprinter, maps)))
        emitted[h.id] = serialize(stamped(inner, printed, maps))

    if digests:
        ctx.response_headers[HEADER_ZONE_HASHES] = _pairs(digests)
    if bases:
        ctx.response_headers[HEADER_ZONE_BASES] = _pairs(bases)
    if timings:
        ctx.response_headers["Server-Timing"] = ", ".join(timings)

    pieces: list[str] = list(emitted.values())

    # Append the delta script tag if any client state mutated.
    delta_html = _render_delta(ctx)
    if delta_html:
        pieces.append(delta_html)

    # Drain the toast queue: ``ui.notification(...)`` calls during the
    # action collected dicts on ``ctx.notifications``. They ride ONE
    # ``<bz-patch>`` under the reserved ``_notifications`` key; the
    # bridge forwards them to ``$bz.notify`` and the auto-mounted
    # toaster shows them. (There is no ``NotificationContainer`` — that
    # name, and the old inline ``<script>``, date from V2.)
    from bretzel.components.feedback.notification import serialise_pending

    notif_html = serialise_pending(ctx.notifications)
    if notif_html:
        pieces.append(notif_html)

    # A zone that rendered ``ui.title`` changes the tab too: a partial
    # response has no ``<head>``, so the title rides ``HX-Trigger``, the
    # same event a partial navigation uses. Only when a zone SET it —
    # otherwise every click would push the decorator's title back.
    if ctx.head_title:
        push_title(ctx, ctx.head_title)

    body = "\n".join(pieces)
    return RenderResult(
        body=body,
        status_code=200,
        headers=dict(ctx.response_headers),
        new_cookies=dict(ctx.new_cookies),
        deleted_cookies=set(ctx.deleted_cookies),
    )


def push_title(ctx: RenderContext, title: str) -> None:
    """Announce ``title`` to the runtime through ``HX-Trigger``.

    MERGED into a trigger already set (``ctx.set_header("HX-Trigger",
    …)`` in a handler) rather than written over it: a response carries a
    single ``HX-Trigger`` header, and the app's event and the title must
    both arrive. htmx accepts a JSON object or a comma-separated list of
    names; the second is read as names with no detail.
    """
    current = ctx.response_headers.get("HX-Trigger", "")
    events: dict[str, Any] = {}
    if current:
        try:
            parsed = json.loads(current)
        except ValueError:
            parsed = None
        if isinstance(parsed, dict):
            events = parsed
        else:
            events = {n.strip(): None for n in current.split(",") if n.strip()}
    events[TITLE_EVENT] = title
    ctx.response_headers["HX-Trigger"] = json.dumps(events)


# ───────────────────────────────────────────────────────────────────────────
# Internals
# ───────────────────────────────────────────────────────────────────────────


def _lower(ctx: RenderContext) -> list[Node]:
    """Flatten the root's children into Nodes, in a single pass.

    ``is_rendering=True`` for the walk: a Component built *during* a
    ``render()`` (a ``ui.badge`` built in a cell's ``render=``) is then
    treated as a subcomponent and skips root registration. Without that
    guard, they would leak as siblings of the section root and come back
    out as duplicates in the OOB swap.
    """
    produced: list[Node] = []
    previous_is_rendering = ctx.is_rendering
    ctx.is_rendering = True
    try:
        for child in ctx.root_children:
            rendered = child.render() if hasattr(child, "render") else child
            if isinstance(rendered, Node):
                produced.append(rendered)
    finally:
        ctx.is_rendering = previous_is_rendering
    return produced


def _zone_identity(handle: RefreshableHandle) -> dict[str, str]:
    """A zone's identity attributes, as its render sets them.

    Goes through
    :func:`~bretzel.render.decorators.refreshable.zone_attrs`, the single
    source — a fragment copying them would drift, and that has already
    happened (cf. ``_zone_failure_fragment``).

    The subscription attributes are recomputed from the handle rather
    than guessed: a ``broadcast=[State]`` zone that lost them while
    failing would also lose its ``EventSource``, hence its real-time
    behaviour, on top of its refresh.
    """
    states = handle._broadcast_qualnames()
    return zone_attrs(
        handle.id,
        subscribe_state_qualname=" ".join(states) if states else None,
        subscribe_url=handle._subscribe_url(states) if states else None,
    )


def _zone_failure_fragment(
    app: BretzelApp,
    handle: RefreshableHandle,
    exc: BaseException,
) -> str:
    """The fragment replacing a zone whose render raised.

    **Why isolate rather than let it surface.** A zone raising during the
    drain took the whole response down as a 500, and three things were
    lost at once: the other zones — valid, sometimes already rendered —
    never reached the browser; htmx does not swap on a non-2xx, so the
    user saw their page do nothing; and since ``commit()`` comes AFTER
    the drain, the handler's mutations were cancelled. Measured on
    2026-09-05: a DISPLAY bug in one zone cancelled the requested
    registration, without a word.

    Isolating fixes all three: the drain goes to the end, so the commit
    runs, so the user's action holds.

    **Why a VISIBLE error and not the zone left as-is.** A mute zone
    would show stale data in a page that looks correct — the silent lie,
    precisely what this repository refuses elsewhere. Better to say where
    it breaks.

    **The detail follows ``expose_errors``**, never ``debug``: that is
    already the framework's dividing line for error pages
    (``server/routing/errors.py``) — an exposure decision, not a
    verbosity one. One policy, not two.

    ⚠️ Concerns the drain ONLY (action response, SSE refetch, OOB swap).
    A zone raising while rendering a PAGE still lets the exception
    surface, where ``@error_page`` awaits it: there, no other valid
    content has to be saved.
    """
    _log.exception(
        "zone %s failed to render — isolated so the rest of the response "
        "survives", handle.id,
    )
    cfg = getattr(app, "config", None)
    if bool(getattr(cfg, "expose_errors", False)):
        message = f"{type(exc).__name__}: {exc}"
    else:
        message = "This zone could not be displayed."

    # We compose with ``ui.alert`` rather than writing the markup by
    # hand: it is the repository's component for saying that, and a
    # second version would drift from its theme at the first change.
    from bretzel.components.feedback.alert import Alert  # cycle : render → components

    try:
        node: Node = Alert(message=message, color="error").render()
    except Exception:  # le secours du secours
        # If even the alert breaks, we do not retry: we render bare
        # text. An exception here would do exactly what we are fixing.
        _log.exception("zone %s: the fallback alert raised too", handle.id)
        node = Element("span", {}, [message])

    # ⚠️ The SAME wrapping as the nominal render, not a hand-written
    # ``<div>``. The fragment was composed as an f-string for a day, and
    # it omitted ``DATA_ZONE``: after an error, the zone dropped out of
    # the browser's enumeration, the ``X-Bretzel-Zones`` header no longer
    # carried it, ``enqueue_deps`` filtered it out — it NEVER refreshed
    # again, until a full reload, and without a word. It also lost the
    # ``class="contents"`` of ``fuse_or_wrap``, so the failed zone got
    # back a layout box its healthy twin does not have.
    return serialize(
        fuse_or_wrap(
            [node],
            bz_id=handle.id,
            extra_attrs={**_zone_identity(handle), "hx-swap-oob": "morph"},
        )
    )


async def _rows_only(
    app: BretzelApp,
    handle: RefreshableHandle,
    ctx: RenderContext,
    rows: set[str],
    known: ZoneVersion,
    held: str,
    fingerprinter: Fingerprinter,
) -> RowPatch | None:
    """Render ``handle`` for ``rows`` only and build the row patch, or
    ``None`` to render it whole (a change that is not row by row). A
    render that raises is left to the whole render, which isolates it the
    usual way."""
    ctx.rows_only = scope = RowsOnly(frozenset(rows))
    try:
        await _render_one(app, handle, ctx, oob=True)
    except Exception:  # the whole render that follows reports it
        return None
    finally:
        ctx.rows_only = None
    return row_patch(scope.reports, known, held, fingerprinter)


def _ship(
    changed: Sequence[Element],
    removed: Sequence[str],
    fingerprinter: Fingerprinter,
    maps: Any,
    *,
    zone_id: str = "",
    printed: ZonePrint | None = None,
    placed: Sequence[str] = (),
) -> str:
    """A zone's patch: its changed elements morphed in place (nested zones
    stamped), its removed rows deleted, and its changed elements with no
    ``id`` found by position (``zone_diff.at_position``). Those ride in
    the sink, appended out of band: an action's body lands there, a
    refetch's is not swapped at all."""
    pieces = [*(serialize(as_patch(e)) for e in stamp_zones(changed, fingerprinter, maps)),
              *(serialize(removal(ident)) for ident in removed)]
    if placed and printed is not None:
        fresh = stamp_zones([printed.nodes[k] for k in placed], fingerprinter, maps)
        pieces.append(serialize(at_position(zone_id, printed, list(zip(placed, fresh, strict=True)))))
    return "".join(pieces)


def _timing(handle: RefreshableHandle, seconds: float) -> str:
    """One ``Server-Timing`` entry: the zone's function name as metric
    (a token: letters, digits, ``_``), its qualified name as description."""
    name = re.sub(r"\W", "_", handle.zone_qualname.rsplit("::", 1)[-1].rsplit(".", 1)[-1])
    return f'zone_{name};dur={seconds * 1000:.1f};desc="{handle.zone_qualname}"'


def _pairs(values: dict[str, str]) -> str:
    """``id:value`` pairs, comma-separated — the shape
    ``render_context._zone_hashes_of`` reads back."""
    return ",".join(f"{key}:{value}" for key, value in values.items())


def fingerprinter_for(app: BretzelApp) -> Fingerprinter:
    """The fingerprint rules of this app: its anti-replay window, and which
    actions are ``@idempotent`` — decided as the action route decides,
    from the handler the action id resolves to (cf. ``render/zone_diff.py``,
    "What a fingerprint ignores")."""
    # render → server, at call time: the route's own resolution, not a copy.
    from bretzel.server.handlers import HandlerResolutionError, resolve_handler
    from bretzel.server.idempotency import idempotent_ttl

    def is_idempotent(action_id: str) -> bool:
        try:
            return idempotent_ttl(resolve_handler(action_id)) is not None
        except HandlerResolutionError:
            return False

    config = getattr(app, "config", None)
    return Fingerprinter(
        action_max_age=getattr(config, "action_max_age", None),
        is_idempotent=is_idempotent,
    )


async def _render_one(
    app: BretzelApp,
    handle: RefreshableHandle,
    ctx: RenderContext,
    *,
    oob: bool,
) -> Node:
    """Run ``handle.fn`` and return the zone's root node.

    The caller serialises it: it first needs to know what this fragment
    CONTAINS (a nested zone it need not re-ship) and what changed in it
    (``render/zone_diff.py``). Reading either from the HTML would be a
    guess where the tree is an answer.

    Drains ``ctx.root_children`` written by the function (the
    component-tree path), or accepts a directly-returned :class:`Node`
    as a convenience for tests / handler-level code that doesn't
    construct components.
    """
    # Snapshot the existing root children so we can isolate this
    # call's contribution and restore the outer scope after.
    saved_root = ctx.root_children
    ctx.root_children = []
    saved_parent_stack = ctx.parent_stack
    ctx.parent_stack = []

    # Render under the registry / context already set up by the caller.
    #
    # Go through ``handle()`` (not ``handle.fn()``) so the
    # :class:`RefreshableHandle.__call__` path runs : it creates a
    # ``_RefreshableSection``, pushes it onto ``parent_stack`` via
    # ``with section:``, and the user function's components register
    # as the section's children. Without this, the partial branch
    # bypassed the section, ``parent_stack`` stayed empty, and every
    # child's ``Component.__init__`` fell back to the literal "root"
    # ID prefix — producing IDs incompatible with what the initial
    # full-page render emitted under ``refresh_<hash>_*``. Idiomorph
    # keys morphs by id ; the mismatch silently downgraded to subtree
    # REPLACEMENT, destroying every ``bz-data`` scope on the swapped
    # subtree (Select / Switch / Checkbox / Input ``bz-model`` /
    # ``bz-attr`` bindings re-installed against fresh DOM nodes,
    # leaving any external scope reference dangling).
    #
    # Cf. probe ``probe_variant_roundtrip_consistent`` for the original
    # repro.
    with use_context(ctx), rendering_scope():
        # ``handle()`` runs through ``RefreshableHandle.__call__`` which
        # creates a ``_RefreshableSection``, pushes it on parent_stack,
        # and runs the user fn. Any value the fn returns directly is
        # attached to the section's children by __call__; nothing for
        # us to capture here.
        # The SYNCHRONOUS body of a zone rendered on its own — SSE or OOB
        # — goes to the threadpool: without that, a real-time zone
        # reading a blocking database would freeze the loop once per
        # signal AND per subscribed client.
        #
        # ``is_async`` first, because ``__call__`` is synchronous in BOTH
        # cases: for an ``async`` body it merely sets the section down and
        # stores the coroutine (framework bookkeeping, nothing that can
        # block), and the drain just below awaits it on the loop.
        # Delegating it would cost a thread hop for nothing.
        if handle.is_async:
            handle()
        else:
            await call_without_blocking(handle)
        # An ``async`` zone has only set its section down; its body
        # waits in ``ctx.pending_async_zones``. This path is the refresh
        # one (OOB or SSE refetch): not draining here would render the
        # zone full on first display and EMPTY on every refresh — the
        # half that is hardest to see.
        await drain_pending_async_zones(ctx)

    # Drain the section (now the single root child) — its ``render``
    # produces an Element whose ``bz-id`` already matches handle.id,
    # so we don't need to ``fuse_or_wrap`` here; doing so would
    # double-wrap. We just merge the ``hx-swap-oob`` extra attr when
    # appropriate.
    #
    #
    # The flattening is OFFLOADED, like the body: ``render()`` calls app
    # code back (a ``ui.datatable``'s ``rows=``, a column's ``render=``),
    # and the framework REQUIRES that ``rows=`` to be a ``def`` — it
    # refuses a coroutine. Leaving it here would run it on the loop, once
    # per SSE signal and per subscribed client.
    produced = await call_without_blocking(_lower, ctx)

    # Restore caller's scope.
    ctx.root_children = saved_root
    ctx.parent_stack = saved_parent_stack

    extra: dict[str, Any] | None = None
    if oob:
        # Morph OOB swap via Idiomorph (loaded as an htmx-2 extension —
        # ``hx-ext="morph"`` is wired on ``<body>`` in the shell so
        # every swap goes through it). The morph matches by ``id``,
        # preserves the existing wrapper element + its descendants
        # whose ids match, and only updates attributes / content
        # where they differ. Critical consequence : ``bz-data``
        # scopes on the swapped subtree (accordion, popover, tabs,
        # drawer, …) survive intact — the user's locally-collapsed
        # buckets, open popovers, selected tab indicator, etc. don't
        # reset on every refresh the way a plain outerHTML swap did.
        extra = {"hx-swap-oob": "morph"}

    # Common case after the ``handle()`` fix : ``produced`` is a single
    # Element whose ``bz-id`` is already ``handle.id`` (the
    # ``_RefreshableSection`` rendered correctly). Just merge the
    # extra OOB attr — no fuse_or_wrap pass needed.
    if (
        len(produced) == 1
        and isinstance(produced[0], Element)
        and produced[0].attrs.get(BZ_ID_ATTR) == handle.id
    ):
        section_el = produced[0]
        if extra:
            merged = {**section_el.attrs, **extra}
            section_el = Element(
                tag=section_el.tag,
                attrs=merged,
                children=section_el.children,
            )
        return section_el

    # Fallback (defensive — shouldn't fire after the ``handle()`` fix
    # unless the user did something unusual). Stamp via fuse_or_wrap
    # like before.
    return fuse_or_wrap(
        produced,
        bz_id=handle.id,
        extra_attrs=extra,
    )


def _zone_ids_inside(root: Node, *, among: set[str]) -> set[str]:
    """The zones of ``among`` this fragment ALREADY carries, root excluded.

    ``among`` is the refresh queue: we are not looking for "the zones"
    but for "the ones we were also about to ship". That is what makes the
    filter safe despite a ``bz-id`` that does not belong to zones alone —
    every component the runtime must find again carries one
    (``Component.emit_attrs``). A component id cannot be in the queue, so
    the intersection settles it.

    The walk STOPS under a ``bz-teleport``: the runtime moves that
    ``<template>``'s content under ``<body>`` (the anchored overlay
    panels — Tooltip, Popover, Dropdown). A zone living in there is no
    longer, in the live DOM, a descendant of the ancestor carrying it in
    the SSR: morphing the ancestor would not reach it, and removing its
    fragment would freeze it. It is a DECLARATION read from the tree, not
    a guess about layout.

    ⚠️ A descendant hidden in an :class:`Html` node (raw markup) would
    not be seen. No path produces that today — a zone renders an
    :class:`Element` — and the gate's abstention table declares it rather
    than pretending to cover it.
    """
    found: set[str] = set()
    stack: list[Node] = list(getattr(root, "children", ()) or ())
    while stack:
        node = stack.pop()
        if isinstance(node, Element):
            if TELEPORT_ATTR in node.attrs:
                continue
            zone_id = node.attrs.get(BZ_ID_ATTR)
            if zone_id in among:
                found.add(zone_id)
        stack.extend(getattr(node, "children", ()) or ())
    return found


def _render_delta(ctx: RenderContext, *, include_unchanged: bool = False) -> str:
    """Build the ``<bz-patch>`` tag for the response (V3 wire format).

    Default mode is the action-response flow: the *dirty*
    :class:`ClientState` instances are PUSHED — the server mutated them
    on purpose, it wins —, and the instances the browser did not send
    are SEEDED. A refreshed zone can reference an instance the page never
    rendered before (a panel that appears with the first message), and
    the runtime then has nothing for it: its bindings read ``undefined``,
    its persistence is never registered, and the next action sends the
    word ``"undefined"`` back. A seed only creates what is missing
    (``$bz._store.seed``), so seeding an instance the browser does hold —
    a ``send_to_server=False`` one, which is never sent — costs bytes,
    not its value.

    ``include_unchanged=True`` switches to the partial-nav flow : every
    instance the registry knows about is seeded, dirty or not. Used
    when a partial response lands on the runtime for the first time
    (htmx swap of the outlet) and the new page references ClientStates
    the runtime has never seen.

    Returns an empty string when nothing needs sending (callers can
    decide not to append anything).
    """
    registry = ctx.state_registry
    if registry is None:
        return ""
    clients = [
        inst for inst in registry._instances.values() if isinstance(inst, ClientState)
    ]
    if include_unchanged:
        return serialize_patch(clients, include_unchanged=True) if clients else ""
    pushed = [inst for inst in clients if inst._dirty]
    unseen = [
        inst
        for inst in clients
        if not inst._dirty and instance_key(inst) not in registry._client_payload
    ]
    return (serialize_patch(unseen, include_unchanged=True) if unseen else "") + (
        serialize_patch(pushed) if pushed else ""
    )


# ───────────────────────────────────────────────────────────────────────────
# Convenience for tests / Layer 6
# ───────────────────────────────────────────────────────────────────────────


async def drain_refresh_queue(
    app: BretzelApp,
    ctx: RenderContext,
) -> RenderResult | None:
    """Render every queued refreshable in one OOB-batched response.

    Returns ``None`` when there's nothing to send back at all : no
    refreshables, no client-state delta, no pending toasts. Layer 6
    can then send an empty 204 / no-op response without burning bytes.
    """
    if not ctx.refresh_queue:
        # No refreshable to render — but the response may still need
        # to carry a client-state delta and / or pending toasts. Build
        # the body from those alone.
        from bretzel.components.feedback.notification import serialise_pending

        pieces: list[str] = []
        delta_html = _render_delta(ctx)
        if delta_html:
            pieces.append(delta_html)
        notif_html = serialise_pending(ctx.notifications)
        if notif_html:
            pieces.append(notif_html)
        if not pieces:
            return None
        return RenderResult(
            body="\n".join(pieces),
            status_code=200,
            headers=dict(ctx.response_headers),
            new_cookies=dict(ctx.new_cookies),
            deleted_cookies=set(ctx.deleted_cookies),
        )

    primary = ctx.refresh_queue[0]
    extras = ctx.refresh_queue[1:]
    return await render_partial(app, primary, ctx=ctx, extra_handles=extras)
