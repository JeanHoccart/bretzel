"""Event handler dispatch for components (V3 wire).

Three flavours of event handler are recognised, in this order :

- **Callable** (module-level function or bound classmethod) — the
  component registers it on the render context (HMAC-signed) and emits
  native HTMX attributes : ``hx-post="/_bretzel/action/<id>"`` +
  ``hx-trigger="<event>"`` targeting the permanent ``#bz-sink``, with
  the signature stamped in ``data-bz-sig`` (the runtime bridge forwards
  it as the ``X-Bz-Sig`` header) and partial-bound args riding as
  form-data via ``hx-vals``.
- **String** — a client-only JS expression, emitted as
  ``bz-on:<event>="<expression>"`` for the V3 runtime evaluator.
- **None** — silently dropped (the kwarg was passed but nil).

Handler addressability is the spec 07 ``module::qualname`` form.
Lambdas and closures are rejected up-front : the action route resolves
handlers via :func:`bretzel.server.handlers.resolve_handler`, which can
only walk ``sys.modules`` — anonymous callables would crash at first
click.

V3 constraint : HTMX hosts ONE ``hx-post`` per element, so a component
root can carry at most one server-handled event (any number of
client-only ``bz-on:`` handlers can coexist with it). Composite
components that need several server events route them onto distinct
child elements.
"""

from __future__ import annotations

import inspect
import json
from collections.abc import Callable, Mapping
from functools import partial
from typing import Any

from bretzel.components.base.attrs import (
    EVENT_PATTERN,
    ComponentDefinitionError,
    ComponentUsageError,
)
from bretzel.runtime.protocol import (
    BZ_ON_PREFIX,
    DATA_BZ_SIG,
    DATA_BZ_TS,
    ROUTE_ACTION,
    SINK_ELEMENT_ID,
    WIRE_ID_SEP,
)
from bretzel.state import ClientExpression

#: The rule of a server handler, in the words every reader gets: the
#: ``describe`` index states it before a first draft, the
#: ``lambda-handler`` lint rule after one. One sentence, so the two cannot
#: drift from each other nor from :func:`encode_handler_id`, which applies it.
SERVER_HANDLER_RULE = (
    "A server handler — a Python callable given to `on_<event>=` — is a "
    "module-level function, or `functools.partial(fn, value)` of one; never "
    "a lambda nor a closure: the framework signs it by its importable name."
)


class HandlerError(TypeError):
    """Raised when a component receives an event handler that the
    framework can't address (lambda, closure, non-callable / non-str)
    or can't emit (two server handlers on one element)."""


# ───────────────────────────────────────────────────────────────────────────
# Class-time validation : EVENTS ↔ ``on_<event>`` parameters
# ───────────────────────────────────────────────────────────────────────────


def cross_check_events(cls: type) -> None:
    """Verify that every event in ``cls.EVENTS`` has a matching
    ``on_<event>`` parameter in ``cls.__init__``.

    Raised at class definition time so a typo trips at import, not
    at first instantiation.
    """
    declared: tuple[str, ...] = getattr(cls, "EVENTS", ())
    if not declared:
        return

    init = cls.__init__
    if init is object.__init__:
        # No custom __init__ — nothing to cross-check.
        return

    sig = inspect.signature(init)
    on_params = {
        name
        for name in sig.parameters
        if EVENT_PATTERN.match(name)
    }

    missing = [f"on_{evt}" for evt in declared if f"on_{evt}" not in on_params]
    if missing:
        raise ComponentDefinitionError(
            f"{cls.__name__}.EVENTS declares events whose ``on_<event>`` "
            f"parameters are missing from __init__ : {missing!r}. "
            "Add them to the signature or remove from EVENTS."
        )


# ───────────────────────────────────────────────────────────────────────────
# Handler ID encoding (consistent with spec 07's module::qualname rule)
# ───────────────────────────────────────────────────────────────────────────


_ACTION_ID_SEPARATOR = WIRE_ID_SEP


def encode_handler_id(handler: Callable[..., Any]) -> str:
    """Return the addressable id for ``handler``.

    Phase 1 form : ``<module>::<qualname>``. The server layer signs
    this with HMAC before emitting to the client and verifies on
    incoming POSTs ; render stays free of crypto concerns.

    ``functools.partial`` is unwrapped : the underlying function
    drives the id, the bound args ride separately via
    :func:`bretzel.server.handlers.encode_args` (component layer
    bakes the blob into the rendered attribute alongside this id).

    Lambdas and closures are rejected up-front — they cannot be
    resolved through ``sys.modules`` (cf. CR-1 from the spec review).
    """
    import functools

    if isinstance(handler, functools.partial):
        # Walk through nested partials defensively ; settle on the
        # innermost real callable for the id encoding.
        inner = handler
        while isinstance(inner, functools.partial):
            inner = inner.func
        return encode_handler_id(inner)
    if not callable(handler):
        raise HandlerError(
            f"Event handler must be callable, got {type(handler).__name__}."
        )
    qualname = getattr(handler, "__qualname__", "")
    module = getattr(handler, "__module__", "")
    if "<lambda>" in qualname:
        raise HandlerError(
            "Lambda handlers are forbidden — the framework resolves handlers "
            "via sys.modules at request time, which lambdas can't survive. "
            "Move the function to module level."
        )
    if "<locals>" in qualname:
        raise HandlerError(
            f"Closure handler {qualname!r} cannot be addressed via "
            "sys.modules. Move the function to module level (or use a "
            "@classmethod / @staticmethod) ; component-internal handlers "
            "are NOT supported in Mode A — see spec 06 § Mode A example."
        )
    if not module or not qualname:
        raise HandlerError(
            f"Handler {handler!r} has no resolvable __module__/__qualname__."
        )
    return f"{module}{_ACTION_ID_SEPARATOR}{qualname}"


# ───────────────────────────────────────────────────────────────────────────
# V3 attribute emission
# ───────────────────────────────────────────────────────────────────────────


def client_event_attr(event: str) -> str:
    """Attribute name for a client-only handler : ``bz-on:<event>``."""
    return f"{BZ_ON_PREFIX}{event}"


def auto_busy(owner: str, value: Any, *, declared: bool) -> bool:
    """Whether the runtime may show this component's triggers as busy
    (:data:`~bretzel.runtime.protocol.DATA_BZ_BUSY`, ``bridge.js``)
    while their request is unanswered — the default.

    ``loading=False`` turns it off. A component that declares ``loading``
    itself (a button, which draws its own spinner) keeps it only while
    ``loading`` is left at its default: ``True`` or a binding means the
    component shows the state on its own, and a second one would double it.
    """
    if declared or value is None:
        return value is None
    if value is False:
        return False
    raise ComponentUsageError(
        f"{owner}(loading={value!r}): only ``loading=False`` is accepted here — "
        "it turns off the busy state the runtime shows on its own while an "
        "action is unanswered. To show a loading state yourself, use "
        "``visible=ui.pending(...)`` on what should appear."
    )


def action_attrs(
    event: str,
    action_id: str,
    args_blob: str,
    sig: str,
    *,
    modifier: str | None = None,
    from_id: str | None = None,
    ts: str | None = None,
) -> dict[str, str]:
    """HTMX attribute set for one server-handled event (V3 wire).

    - ``hx-post`` → the action route. HTMX owns the POST ; the V3
      runtime only configures the request (signals snapshot, headers).
    - ``hx-trigger`` → explicit event name, predictable across tags
      (HTMX's per-tag defaults never surprise us). ``modifier`` (e.g.
      ``"delay:300ms"`` / ``"throttle:300ms"`` from ``debounce=`` /
      ``throttle=``) is appended after the event name when present.
      ``from_id`` appends HTMX's ``from:#<id>`` clause so a hidden
      *carrier* element can listen for an event dispatched on ANOTHER
      element (the overlay root) — this is how a single overlay wires a
      SECOND server handler when the root already hosts the first
      ``hx-post`` (cf. ``Component.ALLOW_MULTI_SERVER_EVENTS``).
    - ``hx-target``/``hx-swap`` → the permanent ``#bz-sink``, so the
      non-OOB response body (``<bz-patch>``, notifications) lands in
      the DOM instead of being discarded. OOB fragments swap their own
      targets regardless.
    - ``hx-vals`` → partial-bound args (``_args`` base64 blob) ride as
      form-data, alongside the client-state fields the bridge injects.
    - ``data-bz-sig`` → render-time HMAC ; the bridge forwards it as
      the ``X-Bz-Sig`` header, the action route verifies.
    - ``data-bz-ts`` → the render timestamp that was ALSO signed into
      ``sig`` (via ``register_action`` → ``sign_action(ts=ctx.render_ts)``).
      It **must** ride along or the server verifies the sig against an
      empty ts and 403s every call. Rather than make every call site
      re-thread ``ctx.render_ts`` (the "forgotten data-bz-ts" trap that broke
      table row-clicks + chart slices), ``ts`` defaults to the SAME active
      context's ``render_ts`` — so it's correct-by-construction and cannot
      be forgotten. Pass an explicit ``ts`` only to override (or ``""`` to
      force the pre-v2 no-ts wire). Outside a render scope (bare unit
      tests) it falls back to ``""``.
    """
    if ts is None:
        # Deferred import — breaks the components→render module cycle
        # (render.context imports events at call time too).
        from bretzel.render.context import maybe_current_context

        _ctx = maybe_current_context()
        ts = _ctx.render_ts if _ctx is not None else ""
    trigger_parts = [event]
    if modifier:
        trigger_parts.append(modifier)
    if from_id:
        trigger_parts.append(f"from:#{from_id}")
    trigger = " ".join(trigger_parts)
    if event == "input" and modifier and modifier.startswith("delay:"):
        # Leaving the field sends at once what the pause was holding.
        # ``delay:`` drops its request with its element: type, click a
        # tab that redraws the zone, and the last words would be lost.
        # htmx clears an element's pending delay when another of its
        # triggers fires, so this sends ONCE.
        trigger += ", change" + (f" from:#{from_id}" if from_id else "")
    attrs = {
        "hx-post": f"{ROUTE_ACTION}/{action_id}",
        "hx-trigger": trigger,
        "hx-target": f"#{SINK_ELEMENT_ID}",
        "hx-swap": "innerHTML",
    }
    if args_blob:
        attrs["hx-vals"] = json.dumps({"_args": args_blob})
    if sig:
        attrs[DATA_BZ_SIG] = sig
    if ts:
        attrs[DATA_BZ_TS] = ts
    return attrs


def posted_action(attrs: Mapping[str, Any]) -> str | None:
    """The action id these attributes post (:func:`action_attrs`'s
    ``hx-post``), or ``None``. Read here, next to where it is written."""
    post = attrs.get("hx-post")
    prefix = f"{ROUTE_ACTION}/"
    if isinstance(post, str) and post.startswith(prefix):
        return post[len(prefix):]
    return None


def item_action_attrs(
    handler: Any,
    *,
    event: str,
    owner_id: str,
    ctx: Any,
    payload: dict[str, Any] | None = None,
    bind: Callable[[Callable[..., Any]], Callable[..., Any]] | None = None,
    dom_event: str | None = None,
    guard: str | None = None,
    modifier: str | None = None,
) -> dict[str, Any]:
    """Route an ``on_*`` set on an INTERNAL ELEMENT, not on the root.

    The base layer already routes a declared event's handlers — but it
    sets them on the ROOT, because an element carries ONE ``hx-post``.
    Four components have a per-ELEMENT event: a ``ui.table`` row, a
    ``ui.bar_chart`` bar, a ``ui.pie_chart`` slice, a ``ui.diagram``
    node. Each must bind its own data into the call, so none can go
    through the base layer.

    A bare ``partial`` + ``register_action`` in each would make only a
    CALLABLE work: a client expression string — the second of the three
    shapes any framework ``on_*`` accepts — would raise a ``TypeError``
    surfaced bare from ``functools.partial``, naming neither the component
    nor the prop.

    ``bind`` receives the callable and returns the version bound to THIS
    element — it is the only piece that differs from one caller to the
    next (``partial(fn, label, value)`` for a bar, ``partial(fn, key)``
    for a row).

    ⚠️ ``dom_event`` exists because the DECLARED name and the browser's
    event can differ: ``ui.table`` declares ``item_click`` but what
    arrives in the DOM is a ``click``. Without it, the client part landed
    on ``bz-on:item_click`` — a listener for an event nobody dispatches,
    so a perfectly formed expression that never fires. The costliest
    defect of the series: silent in both directions.

    ``modifier`` is the ``delay:`` / ``throttle:`` that ``debounce=`` and
    ``throttle=`` set on the instance (``self._trigger_modifier``). The
    base layer applies it by itself to the ROOT's action; on a
    per-element action, only the caller can pass it on — and as long as
    none of the four did, the kwarg was accepted then lost.

    ``guard`` is a JS condition that wraps the client part, so it
    respects the same filter as the server part — a click on a button
    INSIDE a row must fire neither.

    ``payload`` is the element's data, NAMED — ``{"key": 12}`` for a
    row, ``{"label": "Jan", "value": 3}`` for a bar — and it serves both
    sides: its values, in order, are the server handler's arguments (the
    ``bind`` it replaces), and the whole dict is the ``detail`` of a real
    ``CustomEvent`` named after the declared event, which the client
    expression reads as ``$event.detail.key``. On the DOM's ``click``,
    ``$event.detail`` would be the browser's click count. A
    ``CustomEvent``'s ``detail`` is the DOM's own convention, the one
    Bretzel's commands use (``$event.detail.value``).

    Returns the attributes to merge onto the element: ``hx-post`` and its
    signature for the server part, ``bz-on:<event>`` for the client part.
    Both coexist — a ``[callable, "expr"]`` list wires them both, in the
    order written.
    """
    if bind is None:
        values = tuple((payload or {}).values())

        def bind(fn: Callable[..., Any]) -> Callable[..., Any]:
            return partial(fn, *values)
    handlers = list(handler) if isinstance(handler, (list, tuple)) else [handler]
    attrs: dict[str, Any] = {}
    client: list[str] = []
    for one in handlers:
        if one is None:
            continue
        if isinstance(one, str):
            client.append(one)
            continue
        if not callable(one):
            raise HandlerError(
                f"on_{event}= received {type(one).__name__}. Expected: a "
                f"module-level callable (server action), a string (client "
                f"expression), or a list of both."
            )
        if ctx is None:
            continue
        # ``dom_event`` applies to the SERVER part too: `hx-trigger` is
        # a BROWSER event. As long as the declared name and the DOM's
        # coincided, nobody saw it — `ui.table` was in fact fixing its
        # `hx-trigger` BY HAND right after this call, which was the
        # symptom. The first rename to `item_click` made the fault
        # visible: `hx-trigger="item_click"`, an event nothing
        # dispatches. The action's identity, for its part, keeps the
        # DECLARED name — it is what must match `EVENTS`.
        attrs.update(
            action_attrs(
                dom_event or event,
                *ctx.register_action(bind(one), owner_id, event),
                modifier=modifier,
            )
        )
        if guard:
            # The guard applies to BOTH parts.
            #
            # ⚠️ A caller overwriting `hx-trigger` after this call would
            # take the MODIFIER with it: `debounce=` on a per-element
            # action would be accepted then lost. The guard and the delay
            # coexist in HTMX's syntax — `click[filter] delay:300ms`.
            trigger = f"{dom_event or event}[{guard}]"
            attrs["hx-trigger"] = f"{trigger} {modifier}" if modifier else trigger
    if client:
        body = "; ".join(client)
        if payload is not None and dom_event and dom_event != event:
            # The browser's event (``click``) re-fires the DECLARED one as a
            # ``CustomEvent`` carrying the element's data; the expression
            # listens to that one. Not bubbling: a row inside a row, or a
            # node inside a group, would hand its parent an event it never
            # asked for.
            attrs["data-bz-detail"] = json.dumps(payload)
            fire = (f"$el.dispatchEvent(new CustomEvent('{event}', "
                    "{detail: JSON.parse($el.dataset.bzDetail)}))")
            attrs[client_event_attr(dom_event)] = f"if ({guard}) {{ {fire} }}" if guard else fire
            attrs[client_event_attr(event)] = body
            return attrs
        if guard:
            body = f"if ({guard}) {{ {body} }}"
        attrs[client_event_attr(dom_event or event)] = body
    return attrs


#: An event that does not bubble, and the one that does — for a carrier
#: listening FROM the root: a component whose focusable sits INSIDE its
#: root (a select's trigger) would never tell it.
_BUBBLING = {"focus": "focusin", "blur": "focusout"}

#: Roots whose children are not theirs to keep: void or text-only
#: elements, and ``<bz-calendar>``, which repaints its own content and
#: erased a carrier put inside it. Their carriers go right after them.
_NO_CHILD = frozenset({"input", "textarea", "img", "br", "hr", "select", "bz-calendar"})


def fields_of(root_id: str) -> str:
    """The ``hx-include`` that brings a component's fields — save a file
    input. Posted outside a multipart form, a file arrives as the text
    ``[object File]`` (the file itself travels by ``upload_url``). The
    root, whole, when it holds none (htmx takes an element AND its
    fields); its other fields one by one when it does. A flat list:
    htmx splits ``hx-include`` on its commas — ``:is(a, b)`` is cut."""
    return (f"#{root_id}:not(:has(input[type=file])), #{root_id} input:not([type=file]), "
            f"#{root_id} select, #{root_id} textarea")


def carrier_attrs(
    event: str, action_id: str, args_blob: str, sig: str, *,
    root_id: str, dom_event: str | None = None, modifier: str | None = None,
) -> dict[str, Any]:
    """A hidden carrier for a component's SECOND (third…) server handler.

    A root carries one ``hx-post``; each further ``on_<event>`` gets an
    element of its own that listens FROM the root (``from:#root``) — one
    server handler PER EVENT, on every component. ``dom_event`` is the name the DOM knows it by
    (``Component.DOM_EVENTS``); a stable id keeps idiomorph matching it
    across refreshes; ``hx-include`` brings the component's fields, as
    the root's own handler has them.
    """
    attrs = action_attrs(
        dom_event or _BUBBLING.get(event, event), action_id, args_blob, sig,
        modifier=modifier, from_id=root_id,
    )
    attrs["id"] = f"{root_id}__on{event}"
    attrs["hidden"] = True
    # The carrier first: a list that matches nothing is an htmx error in
    # the console (a file_upload holds no other field).
    attrs["hx-include"] = f"#{attrs['id']}, {fields_of(root_id)}"
    return attrs


def with_carriers(component: Any, node: Any) -> Any:
    """The rendered root with its carriers — placed here, once, for every
    component: inside the root, or right after it when the root keeps no
    child. A carrier the component placed itself (the overlays) is left."""
    from dataclasses import replace

    from bretzel.core.tree import Element, FragmentNode

    if not getattr(component, "_event_carriers", None) or not isinstance(node, Element):
        return node
    carriers = component._event_carrier_nodes()
    placed: set[str] = set()
    stack = [node]
    while stack:
        one = stack.pop()
        if getattr(one, "attrs", None) and "id" in one.attrs:
            placed.add(one.attrs["id"])
        stack.extend(getattr(one, "children", None) or ())
    missing = [c for c in carriers if c.attrs.get("id") not in placed]
    if not missing:
        return node
    if node.tag in _NO_CHILD:
        return FragmentNode(children=(node, *missing))
    return replace(node, children=(*node.children, *missing))


def pending(
    handler: Callable[..., Any] | None = None,
    *,
    after: int = 200,
) -> ClientExpression:
    """Return a client expression indicating whether an action is in flight."""
    target = "$el" if handler is None else json.dumps(encode_handler_id(handler))
    # ``ssr_value=False``: no request can be in flight when the server
    # renders. Without it, a ``visible=ui.pending(...)`` shows on EVERY
    # load until the runtime evaluates — a flicker, on the very
    # mechanism made to avoid them.
    return ClientExpression(f"$bz.pending({target}, {int(after)})", ssr_value=False)
