"""``POST /_bretzel/action/{action_id}`` — the event-dispatch endpoint.

HTMX POSTs here every time a component's ``hx-post`` fires (V3 wire —
no custom dispatcher). The flow :

1. Verify the HMAC signature (``X-Bz-Sig`` header, forwarded by the
   runtime bridge from the element's ``data-bz-sig`` stamp).
2. Decode bound args from the ``_args`` form field if present (baked
   into ``hx-vals`` at render time for ``functools.partial`` handlers).
3. Resolve the callable through ``sys.modules``.
4. Inject signature-typed args (any keyword that matches a key in the
   form data — client-state fields were already split off by the
   render-context middleware).
5. Run the handler ; if it returns an awaitable, ``await`` it.
6. Drain any refreshable handles the handler queued, render the
   partial response (OOB fragments + ``<bz-patch>`` delta).

State commit happens at end-of-request so the partial response
already shows the post-handler view.

"""

from __future__ import annotations

import functools
import inspect
import time
import typing
from collections.abc import Callable
from contextlib import nullcontext
from typing import TYPE_CHECKING, Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from starlette.background import BackgroundTasks
from starlette.requests import Request
from starlette.responses import HTMLResponse, Response

from bretzel.core import EventPayload, call_without_blocking
from bretzel.render.context import current_context
from bretzel.render.decorators.refreshable import broadcast_deps, enqueue_deps
from bretzel.render.partials import drain_refresh_queue
from bretzel.runtime.envelope import error_envelope
from bretzel.runtime.protocol import (
    HEADER_BZ_SIG,
    HEADER_BZ_TS,
    HEADER_PROTOCOL,
    PROTOCOL_VERSION,
    ROUTE_ACTION,
)
from bretzel.runtime.version import check_compat
from bretzel.server.decorators.background import bind_background_tasks
from bretzel.server.errors import AuthRequiredError, BretzelError
from bretzel.server.handlers import (
    HandlerResolutionError,
    decode_args,
    resolve_handler,
    verify_action,
)
from bretzel.server.idempotency import idempotency_key, idempotent_ttl
from bretzel.state.fields.validator import FormError
from bretzel.state.registry import use_registry
from bretzel.state.scopes.client import rendering_scope
from bretzel.state.scopes.server import ServerState

if TYPE_CHECKING:
    from fastapi import FastAPI

    from bretzel.render.types import BretzelApp


def register_action_route(fastapi: FastAPI, bretzel_app: BretzelApp) -> None:
    """Wire the single ``POST /_bretzel/action/{action_id:path}`` route."""

    @fastapi.post(
        ROUTE_ACTION + "/{action_id:path}",
        include_in_schema=False,
    )
    async def _invoke_action(action_id: str, request: Request) -> Response:
        return await _dispatch(bretzel_app, action_id, request)


# ───────────────────────────────────────────────────────────────────────────
# Internals
# ───────────────────────────────────────────────────────────────────────────


async def _dispatch(
    bretzel_app: BretzelApp,
    action_id: str,
    request: Request,
) -> Response:
    ctx = current_context()
    # V3 wire : the args blob rides as a regular form field (emitted
    # via ``hx-vals`` at render time) ; the signature rides as the
    # ``X-Bz-Sig`` header (forwarded by the bridge from the element's
    # ``data-bz-sig`` stamp).
    args_blob = str((ctx.form_data or {}).get("_args", ""))
    signature = request.headers.get(HEADER_BZ_SIG, "")
    ts = request.headers.get(HEADER_BZ_TS, "")

    # Protocol compatibility. The bridge has sent
    # ``X-Bretzel-Protocol`` on every action POST forever, and
    # ``check_compat`` existed with its tests — but NOBODY read the
    # header (measured 2026-08-01: zero callers outside the tests). The
    # real case: after a deployment, a tab left open keeps its cached
    # ``runtime.js`` and POSTs to a server of a different major. Without
    # this check, it broke with no message.
    #
    # We refuse ONLY on a present and different major: an absent header
    # (old client, forged request, test) falls into the HMAC path below,
    # which is the real security barrier. This check serves READABILITY,
    # not safety.
    client_protocol = request.headers.get(HEADER_PROTOCOL, "")
    if client_protocol and not check_compat(client_protocol):
        return HTMLResponse(
            content=error_envelope(
                "reload",
                f"Runtime protocol {client_protocol} incompatible with server "
                f"{PROTOCOL_VERSION} — reloading to pull a current runtime.js.",
            ),
            status_code=409,
        )

    action_key = bretzel_app.config._action_key  # type: ignore[attr-defined]
    if not verify_action(action_key, action_id, args_blob, signature, ts=ts):
        # 403 not 404 — explicit "we know you tried, you can't". Body is a
        # ``_error: reload`` envelope : a bad sig is almost always a stale /
        # rotated page token, and re-rendering mints a fresh one — so the
        # bridge reloads instead of dead-ending on a generic toast.
        return HTMLResponse(
            content=error_envelope("reload", "Invalid action signature."),
            status_code=403,
        )

    # B — captured-request validity window. Opt-in via ``action_max_age``
    # (seconds) ; ``None`` keeps the pre-v2 "valid forever" behaviour. The
    # ts is part of the signed payload (verified above), so a client can't
    # forge a fresh one.
    max_age = getattr(bretzel_app.config, "action_max_age", None)
    if max_age is not None and ts:
        try:
            stale = int(time.time()) - int(ts) > max_age
        except ValueError:
            stale = True  # unparseable ts → treat as stale
        if stale:
            # Same ``_error: reload`` envelope as a bad sig → the bridge
            # reloads the page, which re-renders every action with a fresh ts.
            return HTMLResponse(
                content=error_envelope("reload", "Action expired — reload."),
                status_code=403,
            )

    try:
        handler = resolve_handler(action_id)
    except HandlerResolutionError:
        # Don't leak the underlying message to the client — a 404 is
        # what the runtime expects for "this id doesn't exist".
        return HTMLResponse(content="Unknown action.", status_code=404)

    bound_args, bound_kwargs = decode_args(args_blob)

    # C — @idempotent : collapse a same-render double-submit. The key is
    # the signed (action_id|args|ts) + user, so a re-rendered button (fresh
    # ts) is a distinct op. A replay short-circuits to a no-op 204.
    ttl = idempotent_ttl(handler)
    store = getattr(bretzel_app, "idempotency_store", None)
    if ttl is not None and ts and store is not None:
        key = idempotency_key(ctx.user_id, action_id, args_blob, ts)
        if not await store.claim(key, ttl):
            return HTMLResponse(status_code=204)

    # Bind the per-request registry so ``MyState()`` inside handlers
    # hits the cache + sync hydrate path. The rendering scope flips
    # the flag that turns ClientState reads into ``ClientBinding``s
    # during the refresh re-render.
    registry_cm = (
        use_registry(ctx.state_registry)
        if ctx.state_registry is not None
        else nullcontext()
    )

    # Per-request background queue : handlers call ``task.schedule(...)``
    # which appends here ; attached to the response below so Starlette
    # drains it AFTER the body ships (fire-and-forget after-response).
    bg = BackgroundTasks()

    try:
        # An UNREADABLE form is not an empty form. Running the handler
        # here means making it write blank fields into the state: the
        # failure then does not read as a failure, but as input — and it
        # is irreversible.
        if ctx.form_error:
            raise BretzelError(
                f"The action was not executed: {ctx.form_error} Nothing "
                f"was written to the state — a handler running on an "
                f"unreadable form would erase the fields it believes it is "
                f"receiving."
            )
        with registry_cm, bind_background_tasks(bg):
            # Arg injection runs INSIDE the registry context so a
            # ``form: MyState`` parameter can resolve + hydrate the bound
            # state from the submission (registry-cached instance).
            args, kwargs = await _inject_signature_args(
                handler, request, bound_args, bound_kwargs
            )
            # Handler runs OUTSIDE ``rendering_scope`` — ClientState
            # field reads must return real values here so the body can
            # do ``state.count += 1`` arithmetic. The rendering scope
            # only kicks in during the refreshable re-render below
            # (where ``ClientState.count`` should yield a binding the
            # runtime can patch).
            # Offloaded when synchronous — the COMMON case here (cf.
            # ``core/invoke``): a ``def`` calling a blocking database
            # would freeze the worker's loop, and with it every other
            # user's requests.
            await call_without_blocking(handler, *args, **kwargs)

            # Detect state mutations — including in-place list/dict ops the
            # descriptor never sees — BEFORE the drain, then enqueue every
            # zone that declared a changed state in ``deps=`` (the
            # declarative auto-refresh). Also flips ``_dirty`` so ``commit``
            # persists in-place mutations. Runs outside ``rendering_scope``
            # (raw values) and before ``drain_refresh_queue``.
            if ctx.state_registry is not None:
                changed = ctx.state_registry.diff_and_notify()
                # The field NAMES, not only the classes: a component
                # can then skip re-emitting a region the change cannot
                # have touched. Empty elsewhere (full page, SSE refetch),
                # so the default is "re-render everything" — the safe
                # side.
                ctx.changed_fields = dict(ctx.state_registry.changed_fields)
                # A field declared ``URL = {…}`` has moved → the
                # displayed address must follow, otherwise the view stays
                # unreachable on return and on sharing. The content
                # arrives through the swap below: this header ONLY
                # renames.
                #
                # The test is narrow — "an ADDRESSABLE field", not "a
                # state changed". Paginating a table whose sort alone is
                # declared pushes nothing: otherwise every click would
                # stack an identical entry, and leaving the page would
                # take ten backs.
                _push_addressable_url(request, ctx)
                enqueue_deps(ctx, changed)
                # Cross-tab fan-out for broadcast=[State] zones : every other
                # tab (same session or another browser) gets an SSE signal
                # to refetch. The acting tab already has the local OOB swap
                # from enqueue_deps.
                broadcast_deps(ctx, changed)

            # ── Drain refreshable / client-state delta into the response ────
            with rendering_scope():
                render_result = await drain_refresh_queue(bretzel_app, ctx)

            # Persist any dirty server-state mutated by the handler.
            if ctx.state_registry is not None:
                await ctx.state_registry.commit()
    except AuthRequiredError:
        # Caught HERE rather than left to the app-level 401 handler
        # (``routing/errors.py``) on purpose : this response is swapped
        # into the DOM by the bridge, so it must be a bare body — the
        # rendered 401 *page* the handler produces would land inside the
        # button that triggered the action. Same status, different wire
        # shape ; the page path keeps the real error page.
        return HTMLResponse(content="Authentication required.", status_code=401)
    except BretzelError as exc:
        return HTMLResponse(content=str(exc), status_code=500)
    if render_result is None:
        # Nothing to refresh, no client-state changed → empty 204
        # so HTMX knows there's no swap to apply. Scheduled background
        # tasks (if any) still ride along on the response.
        return Response(status_code=204, background=bg)

    return HTMLResponse(
        content=render_result.body,
        status_code=render_result.status_code,
        background=bg,
    )


@functools.cache
def _cached_signature(handler: Callable[..., Any]) -> inspect.Signature:
    """Memoised :func:`inspect.signature` for action handlers.

    ``inspect.signature`` walks ``__wrapped__`` / annotation strings on
    each call ; on the dispatch hot path that's wasted work because
    handlers don't mutate. Caching by handler identity (functions are
    hashable by ``id``) eliminates a measurable cold-path cost on the
    first action POST.
    """
    return inspect.signature(handler)


@functools.cache
def _state_params(handler: Callable[..., Any]) -> dict[str, type]:
    """Map each handler parameter annotated with a ``ServerState`` subclass
    to that class.

    Resolved once per handler — annotations may be PEP-563 strings under
    ``from __future__ import annotations``, so we go through
    :func:`typing.get_type_hints` rather than reading the raw signature.
    Returns an empty mapping when the hints can't be resolved : the handler
    then behaves exactly as before (plain form-field injection only).
    """
    try:
        hints = typing.get_type_hints(handler)
    except Exception:
        return {}
    return {
        name: ann
        for name, ann in hints.items()
        if name != "return"
        and isinstance(ann, type)
        and issubclass(ann, ServerState)
    }


@functools.cache
def _payload_params(handler: Callable[..., Any]) -> dict[str, type]:
    """Map each handler parameter annotated with an :class:`EventPayload`.

    The third injection shape, next to plain form fields and
    ``ServerState``. A payload is produced by the **runtime** — a drag
    reports which item moved and where — and rides as one JSON blob in the
    single hidden field named by the class's ``WIRE_FIELD``.

    Deliberately keyed on the base class, never on a concrete one : this
    dispatch path must not learn the vocabulary of any component. A future
    payload (a resize's dimensions, a canvas stroke) subclasses
    ``EventPayload`` and is injected without touching this file.
    """
    try:
        hints = typing.get_type_hints(handler)
    except Exception:
        return {}
    return {
        name: ann
        for name, ann in hints.items()
        if name != "return"
        and isinstance(ann, type)
        and issubclass(ann, EventPayload)
        and ann is not EventPayload
    }


async def _hydrate_state(
    state_cls: type[ServerState], form_data: dict[str, Any]
) -> Any:
    """Resolve ``state_cls`` through the registry and write back every
    declared field present in the submission.

    Each assignment goes through ``Field.__set__``, which coerces the form
    string to the field's declared type (``"12.5"`` → ``12.5``) and runs
    its validators — so the handler receives a typed, validated instance
    with no ``get()`` / ``setattr`` boilerplate. Fields absent from the
    submission keep their persisted / default value, so a partial form
    never wipes the rest of the state.

    Validation is **collected, not raised**: when a coercion or a
    validator rejects a value, the (already rolled-back) assignment leaves
    the field at its prior value and the message is stashed under
    ``instance._bz_errors[field]``, surfaced via the ``State.errors``
    property. The handler inspects ``form.errors`` and decides what to do
    (typically re-render the form zone so each ``form_field`` shows its
    message). Collecting — rather than stopping at the first bad field —
    lets the user see every error in one pass, the way real forms behave.

    ``await state_cls.load()`` and not ``state_cls()``: this path runs on
    the LOOP — the action route is a coroutine, and injection precedes
    the handler's offload — so the synchronous shortcut cannot hydrate
    there when the backend reads asynchronously. ``load()`` is exactly the
    door provided for it.
    """
    instance = await state_cls.load()
    errors: dict[str, str] = {}
    raw: dict[str, Any] = {}
    for field_name in state_cls._all_fields():
        if field_name in form_data:
            try:
                setattr(instance, field_name, form_data[field_name])
            except FormError as exc:
                # A whole-instance (cross-field) validator rejected — the
                # message belongs to the FORM, not one field. Route it to
                # the reserved ``"_"`` key (a form-level Alert reads it).
                errors["_"] = str(exc)
                raw[field_name] = form_data[field_name]
            except ValueError as exc:
                errors[field_name] = str(exc)
                # Keep the raw submission so the re-rendered input shows the
                # user's text instead of the rolled-back clean value.
                raw[field_name] = form_data[field_name]
    if errors:
        instance.__dict__["_bz_errors"] = errors
    if raw:
        instance.__dict__["_bz_raw"] = raw
    return instance


async def _inject_signature_args(
    handler: Callable[..., Any],
    request: Request,
    bound_args: list[Any],
    bound_kwargs: dict[str, Any],
) -> tuple[list[Any], dict[str, Any]]:
    """Build the final ``(args, kwargs)`` tuple for ``handler``.

    Phase 1 wiring :

    - Bound args from a ``functools.partial`` are passed positionally.
    - Bound kwargs are passed as kwargs.
    - For every ``handler`` parameter that has a name match in the
      request's form data and isn't already in ``bound_kwargs``, the
      form value is forwarded.

    A parameter annotated with a ``ServerState`` subclass
    (``def save(form: CartForm)``) is resolved through the registry and
    **hydrated from the submission** : every declared field present in the
    form data is written back (coerced + validated via ``Field.__set__``).
    Handlers can still call ``CartState()`` directly for state they don't
    want bound to the form, and ``state.form_value()`` stays the escape hatch for
    one-off unbound fields.
    """
    sig = _cached_signature(handler)
    state_params = _state_params(handler)
    payload_params = _payload_params(handler)
    # Form data lives on the active RenderContext — the render-context
    # middleware parses the body once at the top of the request and
    # stashes it there.
    ctx = current_context()
    form_data: dict[str, Any] = ctx.form_data or {}

    kwargs = dict(bound_kwargs)
    named_params: set[str] = set()
    has_var_keyword = False
    for name, param in sig.parameters.items():
        if param.kind is inspect.Parameter.VAR_KEYWORD:
            has_var_keyword = True
            continue
        if param.kind is inspect.Parameter.VAR_POSITIONAL:
            continue
        named_params.add(name)
        if name in kwargs:
            continue
        if name in state_params:
            kwargs[name] = await _hydrate_state(state_params[name], form_data)
            continue
        if name in payload_params:
            payload_cls = payload_params[name]
            raw = form_data.get(payload_cls.WIRE_FIELD)
            if raw is None:
                # Loud, because the alternative is a handler that runs with
                # a default-constructed payload and mutates the wrong row.
                raise BretzelError(
                    f"{getattr(handler, '__name__', handler)!r} declares "
                    f"{name}: {payload_cls.__name__}, but the submission "
                    f"carries no {payload_cls.WIRE_FIELD!r} field. The "
                    f"component that fires this action is not emitting its "
                    f"payload carrier."
                )
            kwargs[name] = payload_cls.from_wire(raw)
            continue
        if name in form_data:
            kwargs[name] = form_data[name]

    # A handler declared with ``**kwargs`` wants to receive every form
    # field that wasn't already bound — typical for generic mutators
    # (``def server_changed(**kwargs): for k, v in kwargs.items(): …``).
    # Underscore-prefixed fields are wire plumbing (``_args``), never
    # handler input.
    if has_var_keyword:
        for name, value in form_data.items():
            if name in kwargs or name in named_params or name.startswith("_"):
                continue
            kwargs[name] = value

    return list(bound_args), kwargs


def _push_addressable_url(request: Any, ctx: Any) -> None:
    """Recompose the address from the addressable states, and push it.

    The PATH comes from ``HX-Current-URL``: an action POSTs to
    ``/_bretzel/action/<id>``, so its own URL says nothing about the page
    being looked at. Without that header (a client that is not htmx), we
    push nothing rather than guess — a wrong address is worse than an
    absent one.

    The UNDECLARED parameters of the current URL are preserved: an app
    can carry its own (``?utm_source=…``, a campaign id), and
    overwriting them on the first sort would be a silent regression.
    """
    registry = ctx.state_registry
    if registry is None or not registry.addressable_changed(ctx.changed_fields):
        return
    current = request.headers.get("HX-Current-URL")
    if not current:
        return

    split = urlsplit(current)
    params = dict(parse_qsl(split.query, keep_blank_values=True))
    # The DECLARED parameters are recomposed IN FULL, not merged. A
    # field back at its default leaves ``addressable_params()``; merging
    # it would therefore leave the old value in place — and since the URL
    # is authoritative on the next action, it would re-seed what the user
    # has just left. Measured: sorting by "Sector" then "Account" kept
    # ``?sort=sector``, and every subsequent click fell back on it.
    #
    # What the app carried itself (``?utm_source=``, a campaign id) is
    # not declared, so it survives.
    for stale in registry.addressable_param_names():
        params.pop(stale, None)
    params.update(registry.addressable_params())
    ctx.set_header(
        "HX-Push-Url",
        urlunsplit(("", "", split.path, urlencode(params), split.fragment)),
    )
