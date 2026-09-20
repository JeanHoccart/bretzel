"""Render-context middleware — the central piece.

Builds a fresh :class:`RenderContext` per request, populates it from
what the upstream middleware (session / auth) parsed, binds it as the
active context-var, and applies the resolved cookies / headers on the
way out.

This is also the point where we run the registered cleanup callbacks
in LIFO order — anything that needs to happen after the response
went through the middleware stack but before the connection closes.

Form data (V3 wire): when the inbound request is form-typed, the
middleware buffers the body — **bounded and spilled to disk past a
threshold**, cf. ``_buffer_body`` —, parses it ONCE, and splits the
namespaced client-state fields (``Class.key.field=value``, injected by
the runtime bridge on every HTMX request) from the regular handler args
via :func:`bretzel.runtime.envelope.parse_client_payload`. The handler
args land on ``ctx.form_data``, the client-state slice feeds the
:class:`StateRegistry` hydration. Downstream consumers that still call
``request.body()`` / ``.form()`` get the buffered bytes via a replay
receive callable.
"""

from __future__ import annotations

import logging
import secrets
import tempfile
from dataclasses import dataclass
from typing import IO, TYPE_CHECKING, Any
from urllib.parse import parse_qsl

from starlette.datastructures import MutableHeaders
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from bretzel.render.context import RenderContext, use_context
from bretzel.render.lang import resolve_language
from bretzel.runtime.envelope import parse_client_payload
from bretzel.runtime.protocol import (
    HEADER_PAGE_ID,
    HEADER_TAB,
    HEADER_ZONES,
    LANG_COOKIE,
)
from bretzel.server.middleware._state import ensure_state, read_header
from bretzel.server.middleware.csrf import csrf_token_for
from bretzel.state.registry import StateRegistry

if TYPE_CHECKING:
    from bretzel.render.types import BretzelApp


_BODY_METHODS = frozenset({"POST", "PUT", "PATCH"})

_log = logging.getLogger("bretzel.server.request")

#: The ceiling on the whole BODY. There was none: ``_read_full_body``
#: concatenated whatever arrived until the client stopped, so a single
#: POST was enough to make the worker allocate as much RAM as the sender
#: wanted. ``_MAX_PART_BYTES`` did not protect against that — it applies
#: to a PART, and only after the whole body is already in memory.
#:
#: 32 MiB, the same value as a part's ceiling: a part cannot exceed the
#: body containing it anyway. Beyond that, the answer is a 413 — and it
#: is a clear improvement on what came before, where a body that was too
#: large passed the buffer then failed to parse, which the ``except``
#: turned into an empty form, silently.
_MAX_BODY_BYTES = 32 * 1024 * 1024

#: Past which the buffer goes to DISK.
#:
#: ``SpooledTemporaryFile`` keeps everything in memory below this
#: threshold and switches to a file at the first byte that exceeds it.
#: The hot path — an action, a few hundred bytes — therefore never
#: touches the disk, and a 30 MiB upload costs 1 MiB of RAM instead of
#: 30. Without it, the spilling Starlette already does for file parts was
#: cancelled in advance: we had materialised everything before it could
#: see it.
_SPOOL_THRESHOLD_BYTES = 1024 * 1024

#: The size of a chunk read back from the buffer. The body goes out in
#: SEVERAL ASGI messages when it is large — which is also more faithful
#: to the protocol than the single message we had before.
_REPLAY_CHUNK_BYTES = 64 * 1024

_TOO_LARGE = (
    f"the request body exceeds {_MAX_BODY_BYTES // (1024 * 1024)} MiB."
)


@dataclass(slots=True)
class _BufferedBody:
    """The request body, re-readable as many times as needed.

    ``too_large`` says the read stopped at the ceiling: the content is
    then truncated and must not be parsed. We do not drain the rest —
    answering 413 without finishing listening is the normal behaviour,
    and continuing to read would be precisely what we refuse.
    """

    spool: IO[bytes]
    size: int
    too_large: bool = False

    def read_all(self) -> bytes:
        self.spool.seek(0)
        return self.spool.read()

    def close(self) -> None:
        self.spool.close()


def _zones_declared_by(request: Any) -> frozenset[str] | None:
    """The zones the browser says it carries, or ``None`` when it is silent.

    ``None`` and the empty set do NOT mean the same thing: the first is
    "I do not know" and lets the drain behave as before, the second would
    be "no zone" and would silence them all. The runtime never sends the
    header empty, so an empty or blank value is treated as silence.

    Cf. :data:`~bretzel.runtime.protocol.HEADER_ZONES` for the
    measurement justifying the header.
    """
    raw = request.headers.get(HEADER_ZONES)
    if not raw:
        return None
    # Each entry is ``id`` or ``id:fingerprint`` — the fingerprint is
    # read by :func:`_zone_hashes_of`, here we keep only the identity.
    ids = frozenset(
        p.split(":", 1)[0]
        for p in (m.strip() for m in raw.split(",")) if p
    )
    return ids or None


def _zone_hashes_of(request: Any) -> dict[str, str]:
    """``{id: fingerprint}`` of what the browser is ALREADY displaying.

    Empty when the client is silent or sends only identities — an older
    runtime, or the very first POST after a full load, which has not yet
    received any fingerprint.
    """
    raw = request.headers.get(HEADER_ZONES)
    if not raw:
        return {}
    known: dict[str, str] = {}
    for piece in (m.strip() for m in raw.split(",")):
        if ":" in piece:
            zone_id, digest = piece.split(":", 1)
            if zone_id and digest:
                known[zone_id] = digest
    return known


class RenderContextMiddleware:
    """Construct a per-request :class:`RenderContext` and apply its
    accumulated cookies / headers to the outgoing response."""

    def __init__(self, app: ASGIApp, *, bretzel_app: BretzelApp) -> None:
        self.app = app
        self._bretzel_app = bretzel_app

    async def __call__(
        self,
        scope: Scope,
        receive: Receive,
        send: Send,
    ) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        state = ensure_state(scope)
        session_id = getattr(state, "session_id", None) or secrets.token_hex(16)
        user_id = getattr(state, "user_id", None)

        raw_form, replay_receive, form_error, buffered = await _collect_form(
            scope, receive
        )
        if buffered is not None and buffered.too_large:
            # Refusal BEFORE building anything: no context, no
            # registry, no route. The body is truncated, there is nothing
            # to be drawn from it, and 413 is the answer the client
            # expects.
            buffered.close()
            await Response(_TOO_LARGE, status_code=413)(scope, receive, send)
            return
        # V3 wire : split the bridge-injected client-state fields from
        # the regular handler args. The registry hydrates from the
        # former ; the action route / handlers only ever see the latter.
        by_instance, form_data = parse_client_payload(raw_form)
        client_state_payload = {
            f"{cls}.{key}": fields for (cls, key), fields in by_instance.items()
        }

        request = Request(scope, replay_receive)

        # CSRF token is deterministic on (session_id, csrf_key) — same
        # value every render of the same session, picked up by the
        # runtime envelope and echoed in the ``X-Bretzel-CSRF`` header
        # on non-safe-method requests (the :class:`CSRFMiddleware`
        # validates it on the way in).
        csrf_key = getattr(self._bretzel_app.config, "_csrf_key", b"")
        csrf_token = csrf_token_for(session_id, csrf_key) if csrf_key else ""

        cfg = self._bretzel_app.config
        resolved_lang = resolve_language(
            cookie=request.cookies.get(LANG_COOKIE),
            header=request.headers.get("accept-language"),
            available=cfg.languages,
            default=cfg.lang,
        )
        ctx = RenderContext(
            app=self._bretzel_app,
            request=request,
            state_registry=None,
            client_state_payload=client_state_payload,
            form_data=form_data,
            form_error=form_error,
            user_id=user_id,
            session_id=session_id,
            csrf_token=csrf_token,
            live_zones=_zones_declared_by(request),
            zone_hashes=_zone_hashes_of(request),
            tab_id=(request.headers.get(HEADER_TAB) or "").strip()[:64],
            # The language and the framework's words travel BY VALUE
            # to here: a component in layer 5 cannot reach up to read the
            # config in layer 7, and ``ui.text()`` must work without a
            # complete app (the whole unit suite).
            lang=resolved_lang,
            texts=cfg.text_tables.for_language(resolved_lang),
        )

        page_id = read_header(scope, HEADER_PAGE_ID) or ctx.page_uuid
        url_params = _addressable_params(scope)

        backend = getattr(self._bretzel_app, "_state_backend", None)
        if backend is not None:
            ctx.state_registry = StateRegistry(
                backend=backend,
                client_payload=client_state_payload,
                form_data=form_data,
                session_id=session_id,
                user_id=user_id,
                page_id=page_id,
                url_params=url_params,
            )

        async def wrapped_send(message: Message) -> None:
            if message["type"] == "http.response.start":
                _apply_ctx_cookies_and_headers(ctx, message)
            await send(message)

        with use_context(ctx):
            try:
                await self.app(scope, replay_receive, wrapped_send)
            finally:
                ctx.run_cleanups()
                # The buffer may be a FILE: not closing it would leave
                # one temporary per slightly large upload, and the
                # garbage collector gets to it in its own time.
                if buffered is not None:
                    buffered.close()


# ───────────────────────────────────────────────────────────────────────────
# Form body buffering + parsing
# ───────────────────────────────────────────────────────────────────────────


async def _collect_form(
    scope: Scope, receive: Receive
) -> tuple[dict[str, Any], Receive, str | None, _BufferedBody | None]:
    """``(form_data, downstream receive, possible error, buffer to close)``.

    Non-form-typed methods pass through with an empty form and the
    original ``receive``. Form-typed POSTs buffer the body so we can
    parse once here and replay it for any consumer that re-reads.

    The third element is the REASON for an empty form when there is one.
    It surfaces as far as the action dispatcher, which refuses rather
    than running a handler on nothing — an unreadable form was otherwise
    worth an input of blank fields, written to the state.

    The fourth is the buffer: the caller MUST close it, otherwise a
    slightly large upload leaves a temporary file behind.
    """
    method = scope.get("method", "").upper()
    if method not in _BODY_METHODS:
        return {}, receive, None, None

    ct = read_header(scope, "content-type") or ""
    is_urlencoded = "application/x-www-form-urlencoded" in ct
    is_multipart = "multipart/form-data" in ct
    if not (is_urlencoded or is_multipart):
        return {}, receive, None, None

    buffered = await _buffer_body(receive)
    if buffered.too_large:
        # The body is truncated: nothing to parse, and the caller
        # answers 413.
        return {}, _replay_receive(buffered), _TOO_LARGE, buffered
    replay = _replay_receive(buffered)
    if not buffered.size:
        return {}, replay, None, buffered
    if is_urlencoded:
        # parse_qsl is ~10× faster than spinning up a Starlette
        # MultiPartParser for the common case (every action POST).
        body = buffered.read_all()
        try:
            decoded = body.decode("utf-8")
        except UnicodeDecodeError:
            return (
                {},
                replay,
                "the form body is not valid UTF-8.",
                buffered,
            )
        return (
            dict(parse_qsl(decoded, keep_blank_values=True)),
            replay,
            None,
            buffered,
        )
    # multipart: delegate to Starlette so we inherit every quirk
    # (boundary handling, file uploads, charset detection).
    #
    # ``max_part_size`` raised: Starlette's default (1 MB) applies to
    # EACH part, including those that are not files, and a part that is
    # too large raises — which the ``except`` below turns into an EMPTY
    # form, silently. A form only arrives here since August 2026, when it
    # contains a file (``ui.form`` then derives its ``hx-encoding``);
    # before that, those bodies went through ``parse_qsl``, which has no
    # field limit. Without this raise, fixing file upload would have
    # introduced a 1 MB cliff on the neighbouring TEXT FIELD — a
    # ``ui.signature_pad`` (base64 data URL) or a long textarea is enough
    # to cross it, and the handler would receive an empty form without a
    # word.
    request = Request(scope, _replay_receive(buffered))
    try:
        raw_form = await request.form(max_part_size=_MAX_PART_BYTES)
        return {k: raw_form[k] for k in raw_form}, replay, None, buffered
    except Exception as exc:
        # ⚠️ This ``except`` returned an EMPTY form and said nothing.
        # The handler then ran on blank fields and wrote them to the
        # state: the failure read as input, which is the worse of the
        # two. We keep the pass-through — a ``raise`` here would also
        # break third-party routes that read the body themselves — but
        # the reason surfaces, and the dispatcher refuses.
        _log.exception("Formulaire multipart illisible")
        return (
            {},
            replay,
            f"the multipart form could not be read: {exc}",
            buffered,
        )


#: The ceiling on one multipart part. 32 MB: high enough that a text
#: field never meets it, and low enough to stay a bound. Starlette's
#: default (1 MB) is right for a field; it is too low as soon as a form
#: carries a file, which is the only case we get here.
_MAX_PART_BYTES = 32 * 1024 * 1024


async def _buffer_body(receive: Receive) -> _BufferedBody:
    """Drain ``receive`` into a BOUNDED buffer that can spill to disk.

    Two differences from the previous version, and the first is a closed
    hole: we stop at the ceiling instead of allocating whatever the
    sender wants, and we write into a ``SpooledTemporaryFile`` instead of
    a list of bytes — so below the threshold it is still memory, and
    above, it is a file.

    We stop reading as soon as the ceiling is crossed: finishing
    listening to a body we are going to refuse would amount to letting it
    cost whatever it wanted.
    """
    # No context manager (SIM115): the buffer outlives this function —
    # it has to survive the parse AND the request's passage through the
    # whole stack. Its closing is in the middleware's ``finally``, and
    # ``test_the_buffer_is_closed_after_the_request`` guards it.
    spool: IO[bytes] = tempfile.SpooledTemporaryFile(  # noqa: SIM115
        max_size=_SPOOL_THRESHOLD_BYTES
    )
    size = 0
    while True:
        msg = await receive()
        if msg["type"] != "http.request":
            break
        chunk = msg.get("body", b"")
        if size + len(chunk) > _MAX_BODY_BYTES:
            _log.warning(
                "Request body refused: more than %d bytes.", _MAX_BODY_BYTES
            )
            return _BufferedBody(spool=spool, size=size, too_large=True)
        spool.write(chunk)
        size += len(chunk)
        if not msg.get("more_body", False):
            break
    return _BufferedBody(spool=spool, size=size)


def _replay_receive(buffered: _BufferedBody) -> Receive:
    """Replay the body from the buffer, in chunks.

    Each call returns an INDEPENDENT ``Receive``: it carries its own
    position and repositions the buffer before every read, so two
    consumers (the parse here, then the downstream route) both read it
    from the start. A shared cursor would give the second an empty body,
    which is exactly the bug a buffer exists to avoid.
    """
    position = 0
    done = False

    async def replay() -> Message:
        nonlocal position, done
        if done:
            return {"type": "http.disconnect"}
        buffered.spool.seek(position)
        chunk = buffered.spool.read(_REPLAY_CHUNK_BYTES)
        position = buffered.spool.tell()
        more = position < buffered.size
        done = not more
        return {"type": "http.request", "body": chunk, "more_body": more}

    return replay


# ───────────────────────────────────────────────────────────────────────────
# Response splicing — cookies + headers from RenderContext
# ───────────────────────────────────────────────────────────────────────────


def _apply_ctx_cookies_and_headers(ctx: RenderContext, message: Message) -> None:
    """Splice ``ctx`` cookies + headers onto an ``http.response.start`` message.

    Cookie formatting is delegated to a throwaway Starlette Response
    so every option (``samesite``, ``domain``, ``expires``,
    ``max_age``, …) matches what ``Response.set_cookie`` /
    ``.delete_cookie`` would have written — same formatter as
    ``session.py`` uses, no drift between the two paths.
    """
    headers = MutableHeaders(scope=message)

    for name, value in ctx.response_headers.items():
        headers[name] = value

    if ctx.new_cookies or ctx.deleted_cookies:
        dummy = Response()
        for name, opts in ctx.new_cookies.items():
            opts_copy = dict(opts)
            value = opts_copy.pop("value")
            dummy.set_cookie(name, value, **opts_copy)
        for name in ctx.deleted_cookies:
            dummy.delete_cookie(name)
        for k, v in dummy.raw_headers:
            if k == b"set-cookie":
                headers.append("set-cookie", v.decode("latin-1"))


def _addressable_params(scope: Scope) -> dict[str, str]:
    """The parameters of the URL the BROWSER is displaying.

    Two sources, and confusing them breaks one of the two paths:

    - **a navigation** (GET, boosted or not) carries its query in its own
      URL. ``HX-Current-URL`` there designates the page being LEFT —
      using it would seed the previous page's state;
    - **an action** POSTs to ``/_bretzel/action/<id>``, which has no
      query. There, ``HX-Current-URL`` is the only source, and that is
      precisely what makes the URL authoritative: even if the ``page_id``
      is lost, the state is rebuilt from the displayed address.
    """
    if scope.get("method", "GET").upper() == "GET":
        raw = scope.get("query_string", b"").decode("latin-1")
    else:
        current = read_header(scope, "HX-Current-URL") or ""
        raw = current.partition("?")[2]
    return dict(parse_qsl(raw, keep_blank_values=True)) if raw else {}
