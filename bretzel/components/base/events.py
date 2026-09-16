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
from collections.abc import Callable
from typing import Any

from bretzel.components.base.attrs import (
    EVENT_PATTERN,
    ComponentDefinitionError,
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
      re-thread ``ctx.render_ts`` (the "data-bz-ts oublié" trap that broke
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
    attrs = {
        "hx-post": f"{ROUTE_ACTION}/{action_id}",
        "hx-trigger": " ".join(trigger_parts),
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


def item_action_attrs(
    handler: Any,
    *,
    event: str,
    bind: Callable[[Callable[..., Any]], Callable[..., Any]],
    owner_id: str,
    ctx: Any,
    dom_event: str | None = None,
    guard: str | None = None,
    modifier: str | None = None,
) -> dict[str, Any]:
    """Router un ``on_*`` posé sur un ÉLÉMENT INTERNE, pas sur la racine.

    Le socle route déjà les handlers d'un event déclaré — mais il les
    pose sur la RACINE, parce qu'un élément porte UN ``hx-post``. Quatre
    composants ont un event par ÉLÉMENT : une ligne de ``ui.table``, une
    barre de ``ui.bar_chart``, une part de ``ui.pie_chart``, un nœud de
    ``ui.diagram``. Chacun doit lier sa propre donnée dans l'appel, donc
    aucun ne peut passer par le socle.

    Les quatre recopiaient le même ``partial`` + ``register_action``, et
    les quatre avaient le même trou : seul un CALLABLE marchait. Une
    chaîne d'expression cliente — la deuxième des trois formes que tout
    ``on_*`` du framework accepte — y levait un ``TypeError`` remonté nu
    de ``functools.partial``, sans nommer le composant ni la prop.
    Mesuré le 2026-09-06 sur les trois composants livrés
    (``.claude/work/audit-declaration-2026-09-06.md``).

    ``bind`` reçoit le callable et rend la version liée à CET élément —
    c'est le seul morceau qui diffère d'un appelant à l'autre
    (``partial(fn, label, value)`` pour une barre, ``partial(fn, key)``
    pour une ligne).

    ⚠️ ``dom_event`` existe parce que le nom DÉCLARÉ et l'event du
    navigateur peuvent différer : ``ui.table`` déclare ``item_click``
    mais ce qui arrive dans le DOM est un ``click``. Sans lui, la part
    cliente atterrissait sur ``bz-on:item_click`` — un listener pour un
    event que personne ne dispatche, donc une expression parfaitement
    formée qui ne tire jamais. Le défaut le plus cher de la série :
    silencieux dans les deux sens.

    ``modifier`` est le ``delay:`` / ``throttle:`` que ``debounce=`` et
    ``throttle=`` posent sur l'instance (``self._trigger_modifier``). Le
    socle l'applique tout seul à l'action de la RACINE ; sur une action
    par élément, seul l'appelant peut le transmettre — et tant qu'aucun
    des quatre ne le faisait, le kwarg était accepté puis perdu.

    ``guard`` est une condition JS qui enveloppe la part cliente, pour
    qu'elle respecte le même filtre que la part serveur — un clic sur un
    bouton DANS une ligne ne doit déclencher ni l'une ni l'autre.

    Rend les attributs à fusionner sur l'élément : ``hx-post`` et sa
    signature pour la part serveur, ``bz-on:<event>`` pour la part
    cliente. Les deux cohabitent — une liste ``[callable, "expr"]`` les
    câble tous les deux, dans l'ordre écrit.
    """
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
                f"on_{event}= a reçu {type(one).__name__}. Attendu : un "
                f"callable de niveau module (action serveur), une chaîne "
                f"(expression cliente), ou une liste des deux."
            )
        if ctx is None:
            continue
        # ``dom_event`` vaut aussi pour la part SERVEUR : `hx-trigger`
        # est un event du NAVIGATEUR. Tant que le nom déclaré et celui du
        # DOM coïncidaient, personne ne le voyait — `ui.table` corrigeait
        # d'ailleurs son `hx-trigger` À LA MAIN juste après cet appel, ce
        # qui était le symptôme. Le premier renommage vers `item_click` a
        # rendu la faute visible : `hx-trigger="item_click"`, un event que
        # rien ne dispatche. L'identité de l'action, elle, garde le nom
        # DÉCLARÉ — c'est elle qui doit correspondre à `EVENTS`.
        attrs.update(
            action_attrs(
                dom_event or event,
                *ctx.register_action(bind(one), owner_id, event),
                modifier=modifier,
            )
        )
        if guard:
            # La garde vaut pour les DEUX parts. `ui.table` la posait à
            # la main juste après cet appel, en écrasant `hx-trigger` —
            # une réparation locale d'un routeur qui savait déjà, dans
            # sa part cliente, ce qu'il ne faisait pas dans la sienne.
            #
            # ⚠️ Et l'écrasement emportait le MODIFICATEUR avec lui :
            # `debounce=` sur une action par élément était accepté puis
            # perdu. La garde et le délai cohabitent dans la syntaxe
            # HTMX — `click[filtre] delay:300ms` — il fallait juste les
            # écrire tous les deux (2026-09-07).
            trigger = f"{dom_event or event}[{guard}]"
            attrs["hx-trigger"] = f"{trigger} {modifier}" if modifier else trigger
    if client:
        body = "; ".join(client)
        if guard:
            body = f"if ({guard}) {{ {body} }}"
        attrs[client_event_attr(dom_event or event)] = body
    return attrs


def pending(
    handler: Callable[..., Any] | None = None,
    *,
    after: int = 200,
) -> ClientExpression:
    """Return a client expression indicating whether an action is in flight."""
    target = "$el" if handler is None else json.dumps(encode_handler_id(handler))
    # ``ssr_value=False`` : aucune requête ne peut être en vol quand le
    # serveur rend. Sans lui, un ``visible=ui.pending(...)`` s'affiche à
    # CHAQUE chargement jusqu'à ce que le runtime évalue — un
    # clignotement, sur le mécanisme fait pour les éviter.
    return ClientExpression(f"$bz.pending({target}, {int(after)})", ssr_value=False)
