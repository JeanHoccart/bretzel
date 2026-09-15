"""Composed action round-trip — the safety net for the HMAC v2 rebuild.

``test_smoke.py`` already proves the HMAC *gate* (signed → runs, unsigned
/ tampered → 403, unknown → 404) and ``test_realtime.py`` proves the SSE
fan-out. What neither pins — and what HMAC v2 is about to move — lives here:

1. **The mutation round-trip body.** A signed action that mutates a
   ``@refreshable`` zone's dep must come back 200 with the zone
   *re-rendered at its new value* as an OOB swap. This exercises the
   whole spine (verify → dispatch → diff → refresh queue → envelope →
   serialize) and asserts the *bytes*, not just the status.

2. **Replay is currently possible (CHARACTERIZATION).** The exact same
   signed POST replayed twice runs the handler twice. This is the v1
   gap — no nonce, no timestamp. When HMAC v2 lands, the second POST
   must be rejected and ``test_replay_runs_handler_twice`` flips to
   ``test_replay_is_rejected``. Leaving this test RED-on-change is the
   whole point of the safety net.

3. **The body outside ``_args`` is unsigned (CHARACTERIZATION).** A
   valid signature covers ``action_id|_args`` only ; extra form fields
   reach the handler unsigned. HMAC v2's body_hash closes this — update
   the assertion then.

The app + zone + handlers live at MODULE level on purpose : the action
route resolves handlers via ``sys.modules`` (rejects ``<locals>``), so a
factory built inside a test function would 404. We reset the AppState in
the backend between tests via the autouse ``_reset_counter`` fixture.
"""

from __future__ import annotations

import asyncio
import re
import time

import pytest
from fastapi.testclient import TestClient

from bretzel import Bretzel, idempotent, page, refreshable, ui
from bretzel.server.handlers import encode_action_id, sign_action
from bretzel.state import AppState, field

_SECRET = "x" * 32


class AppCounter(AppState):
    n: int = field(default=0)


_app = Bretzel(secret_key=_SECRET, mode="dev")


@refreshable(deps=[AppCounter])
def counter_zone() -> None:
    # Distinctive marker so the body assertion can't false-match a stray
    # digit elsewhere in the document.
    ui.text(f"count={AppCounter().n}")


def counter_bump(step: str = "1") -> None:
    # ``step`` is bound from the raw form body by name. Non-state handler
    # kwargs are NOT type-coerced (only ServerState Fields are), so it
    # arrives as a string — we cast it here. Reassignment then goes
    # Field.__set__ → dirty → diff → counter_zone re-render.
    AppCounter().n += int(step)


@page("/")
def home() -> None:
    counter_zone()


_app.include(home)


_click_log: list[str] = []


def click_action() -> None:
    _click_log.append("clicked")


@page("/btn")
def button_page() -> None:
    ui.button("Go", on_click=click_action)


_app.include(button_page)


_idem_log: list[str] = []


@idempotent
def idem_action() -> None:
    _idem_log.append("x")


@page("/idem")
def idem_page() -> None:
    ui.button("Charge", on_click=idem_action)


_app.include(idem_page)


_tab_log: list[str] = []


def tab_change(value: str = "") -> None:
    _tab_log.append("tab-changed")


@page("/tabs")
def tabs_page() -> None:
    # A server ``on_change=`` callable → Tabs relocates the hx-* action
    # bundle (incl. data-bz-sig + data-bz-ts) onto a hidden <input>, the
    # element that actually fires ``change``. Regression surface for the
    # HMAC-v2 "ts left on the root" 403.
    with ui.tabs(value="a", on_change=tab_change):
        ui.tab("a", label="A")
        ui.tab("b", label="B")
        with ui.tab_panel("a"):
            ui.text("A")
        with ui.tab_panel("b"):
            ui.text("B")


_app.include(tabs_page)


_row_log: list[str] = []


def row_open(issue_id: str = "") -> None:
    _row_log.append(f"open:{issue_id}")


@page("/rowtable")
def rowtable_page() -> None:
    # A clickable Table stamps its per-row action DIRECTLY on the <tr>
    # (no relocation) via ``action_attrs()``. Distinct code path from the
    # relocated components below — the HMAC-v2 ts rollout missed it too.
    ui.table(
        columns=[ui.column("id", label="#"), ui.column("t", label="T")],
        rows=[{"id": 7, "t": "alpha"}, {"id": 9, "t": "beta"}],
        row_key="id",
        on_item_click=row_open,
    )


_app.include(rowtable_page)


def _scrape(html: str) -> tuple[str, str, str]:
    """Pull (sig, ts, action_id) out of a rendered action button."""
    sig = re.search(r'data-bz-sig="([^"]+)"', html)
    ts = re.search(r'data-bz-ts="([^"]+)"', html)
    aid = re.search(r'hx-post="/_bretzel/action/([^"]+)"', html)
    return sig.group(1), ts.group(1), aid.group(1)


@pytest.fixture(autouse=True)
def _reset_counter():
    """Reset AppCounter to 0 in the backend after each test so a mutation
    from one test doesn't leak into the next (the module-level app keeps
    one backend instance for the whole process)."""
    yield
    if _app.state_backend is not None:

        async def _wipe() -> None:
            await _app.state_backend.save(
                "app", "AppCounter:default", {"n": 0}, ttl=None
            )

        asyncio.new_event_loop().run_until_complete(_wipe())


def _sign(action, args_blob: str = ""):
    action_id = encode_action_id(action)
    return action_id, sign_action(_app.config._action_key, action_id, args_blob)


# ───────────────────────────────────────────────────────────────────────────
# 1. Mutation round-trip — the composed render path, asserted on the bytes
# ───────────────────────────────────────────────────────────────────────────


class TestMutationRoundTrip:
    def test_action_rerenders_zone_with_new_value(self) -> None:
        action_id, sig = _sign(counter_bump)
        with TestClient(_app) as client:
            client.get("/")  # render the zone → establish session + bz-id
            response = client.post(
                f"/_bretzel/action/{action_id}",
                headers={"X-Bz-Sig": sig},
                data={"_args": ""},
            )
        assert response.status_code == 200
        body = response.text
        # The zone came back re-rendered at its NEW value…
        assert "count=1" in body
        # …as an out-of-band swap the runtime applies by id.
        assert "hx-swap-oob" in body

    def test_no_mutation_returns_204(self) -> None:
        # A handler that touches no dep queues no refresh → empty envelope.
        action_id, sig = _sign(_noop)
        with TestClient(_app) as client:
            client.get("/")
            response = client.post(
                f"/_bretzel/action/{action_id}",
                headers={"X-Bz-Sig": sig},
                data={"_args": ""},
            )
        assert response.status_code == 204


def _noop() -> None:
    return None


# ───────────────────────────────────────────────────────────────────────────
# 2. Replay CHARACTERIZATION — v1 has no anti-replay. Flip on HMAC v2.
# ───────────────────────────────────────────────────────────────────────────


class TestReplayCharacterization:
    def test_replay_runs_handler_twice(self) -> None:
        # Identical signed request, sent twice. Today BOTH mutate : the
        # counter advances 0→1→2, proving the handler ran on the replay.
        #
        # HMAC v2 (B, timestamp window) does NOT stop an immediate replay
        # inside the window — by design. Double-submit protection is the job
        # of the opt-in ``@idempotent`` decorator (C), which dedups on the
        # signed (action_id|args|ts) key. counter_bump is not @idempotent, so
        # the replay still runs — hence 0→1→2.
        action_id, sig = _sign(counter_bump)
        payload = {
            "url": f"/_bretzel/action/{action_id}",
            "headers": {"X-Bz-Sig": sig},
            "data": {"_args": ""},
        }
        with TestClient(_app) as client:
            client.get("/")
            first = client.post(**payload)
            second = client.post(**payload)
        assert first.status_code == 200
        assert "count=1" in first.text
        # The replay was accepted and the handler ran again (v1 gap).
        assert second.status_code == 200
        assert "count=2" in second.text


# ───────────────────────────────────────────────────────────────────────────
# 3. Unsigned-body CHARACTERIZATION — sig covers action_id|_args only.
# ───────────────────────────────────────────────────────────────────────────


class TestUnsignedBodyCharacterization:
    def test_body_field_outside_args_is_accepted_unsigned(self) -> None:
        # Sign with EMPTY args, then smuggle ``step=5`` in the form body.
        # The signature never covered it, yet it reaches the handler and
        # the counter jumps by 5 — proof the body is unsigned today.
        #
        # By design, v2 does NOT sign the body : the sig is baked at render
        # time (the client has no key), so it can't cover request-time form
        # fields — and needn't, since those are the user's own session values
        # (no privilege escalation). So this stays accepted.
        action_id, sig = _sign(counter_bump)  # signed over _args=""
        with TestClient(_app) as client:
            client.get("/")
            response = client.post(
                f"/_bretzel/action/{action_id}",
                headers={"X-Bz-Sig": sig},
                data={"_args": "", "step": "5"},
            )
        assert response.status_code == 200
        assert "count=5" in response.text


# ───────────────────────────────────────────────────────────────────────────
# 4. HMAC v2 — signed render timestamp (ts) wire + action_max_age window
# ───────────────────────────────────────────────────────────────────────────


class TestV2TimestampWire:
    def test_real_wire_ts_flows_render_to_dispatch(self) -> None:
        # The full v2 wire, no manual signing : the render bakes data-bz-sig
        # AND data-bz-ts, the client forwards both, dispatch verifies the sig
        # over (action_id|args|ts). Proves the ts round-trips end to end.
        _click_log.clear()
        with TestClient(_app) as client:
            sig, ts, aid = _scrape(client.get("/btn").text)
            assert aid.endswith("::click_action")
            resp = client.post(
                f"/_bretzel/action/{aid}",
                headers={"X-Bz-Sig": sig, "X-Bz-Ts": ts},
                data={"_args": ""},
            )
        assert resp.status_code in (200, 204)
        assert _click_log == ["clicked"]

    def test_tampered_ts_rejected(self) -> None:
        # ts is part of the signed payload — bump it by one second and the
        # sig no longer matches → 403.
        _click_log.clear()
        with TestClient(_app) as client:
            sig, ts, aid = _scrape(client.get("/btn").text)
            resp = client.post(
                f"/_bretzel/action/{aid}",
                headers={"X-Bz-Sig": sig, "X-Bz-Ts": str(int(ts) + 1)},
                data={"_args": ""},
            )
        assert resp.status_code == 403
        assert _click_log == []


class TestErrorReloadEnvelope:
    """A 403 (bad / expired signature, or CSRF) returns a ``_error: reload``
    envelope in its body instead of bare text. The bridge extracts it from
    the error response and reloads the page — minting a fresh sig / CSRF
    token — rather than dead-ending on a generic 'Request failed (403)'
    toast. (Before : the reload was documented in the bridge but wired on
    neither side ; user report 2026-07-13.)"""

    def test_bad_sig_403_body_is_reload_envelope(self) -> None:
        with TestClient(_app) as client:
            _s, ts, aid = _scrape(client.get("/btn").text)
            resp = client.post(
                f"/_bretzel/action/{aid}",
                headers={"X-Bz-Sig": "deadbeef" * 2, "X-Bz-Ts": ts},
                data={"_args": ""},
            )
        assert resp.status_code == 403
        # The bridge extracts <bz-patch> from the error body and dispatches
        # the reserved ``_error`` directive (kind "reload").
        assert "bz-patch" in resp.text
        assert "_error" in resp.text
        assert "reload" in resp.text


class TestRelocatedActionWireTs:
    """Regression : a component that relocates its server action onto a
    hidden ``<input>`` (Tabs / Accordion / Pagination / ToggleGroup / Tree)
    must move ``data-bz-ts`` WITH ``data-bz-sig``. The bridge reads BOTH
    off ``closest("[data-bz-sig]")`` — the same element — and the sig is
    computed over ``action_id|args|ts``. Leaving the ts on the (now
    handler-less) root makes the client forward an empty ``X-Bz-Ts`` → the
    server recomputes over ``…|"" `` ≠ signature → 403. The HMAC-v2 rollout
    missed the shared ``CHANGE_HANDLER_KEYS`` tuple ; user report 2026-07
    (Tabs "Server events" bench). ``_scrape_carrier`` mimics the bridge :
    it reads sig+ts FROM the sig-bearing element, not from the document
    at large — so a ts stranded on the root does NOT rescue this test."""

    @staticmethod
    def _scrape_carrier(html: str) -> tuple[str, str, str]:
        # The hidden input bearing data-bz-sig — the bridge's carrier.
        m = re.search(r'<input\b[^>]*\bdata-bz-sig="[^"]*"[^>]*>', html)
        assert m is not None, "no hidden input carrying data-bz-sig"
        tag = m.group(0)
        sig = re.search(r'data-bz-sig="([^"]+)"', tag)
        ts = re.search(r'data-bz-ts="([^"]+)"', tag)
        aid = re.search(r'hx-post="/_bretzel/action/([^"]+)"', tag)
        return (
            sig.group(1) if sig else "",
            ts.group(1) if ts else "",
            aid.group(1) if aid else "",
        )

    def test_tabs_relocated_action_carries_ts_no_403(self) -> None:
        _tab_log.clear()
        with TestClient(_app) as client:
            sig, ts, aid = self._scrape_carrier(client.get("/tabs").text)
            assert aid.endswith("::tab_change")
            # The core of the bug : the ts must ride the SAME element as
            # the sig. Empty here == the 403 regression.
            assert ts, "data-bz-ts missing on the sig carrier (the 403 bug)"
            resp = client.post(
                f"/_bretzel/action/{aid}",
                headers={"X-Bz-Sig": sig, "X-Bz-Ts": ts},
                data={"_args": ""},
            )
        assert resp.status_code in (200, 204), resp.text
        assert _tab_log == ["tab-changed"]


class TestTableRowClickWireTs:
    """Regression : a clickable Table row stamps its action DIRECTLY on the
    ``<tr>`` (no relocation), calling ``action_attrs()`` without threading
    ``ts``. The HMAC-v2 rollout that fixed the RELOCATED path (Tabs, above)
    missed this direct path AND the chart slice / bar clicks → every
    row-click 403'd (user report 2026-07, Table "Server events" bench).
    Fixed at the ROOT : ``action_attrs`` defaults ``ts`` from the active
    render context, so no call site — relocated or direct — can drop it.
    ``_scrape_row`` mimics the bridge : it reads sig+ts off the SAME
    ``<tr>`` (``closest("[data-bz-sig]")``)."""

    @staticmethod
    def _scrape_row(html: str) -> tuple[str, str, str, str]:
        m = re.search(r'<tr\b[^>]*\bdata-bz-sig="[^"]*"[^>]*>', html)
        assert m is not None, "no <tr> carrying data-bz-sig"
        tag = m.group(0)
        sig = re.search(r'data-bz-sig="([^"]+)"', tag)
        ts = re.search(r'data-bz-ts="([^"]+)"', tag)
        aid = re.search(r'hx-post="/_bretzel/action/([^"]+)"', tag)
        # ``_args`` rides inside hx-vals JSON (quotes HTML-escaped as &quot;).
        args = re.search(
            r'_args(?:&quot;|")\s*:\s*(?:&quot;|")([A-Za-z0-9_=\-]*)', tag
        )
        return (
            sig.group(1) if sig else "",
            ts.group(1) if ts else "",
            aid.group(1) if aid else "",
            args.group(1) if args else "",
        )

    def test_item_click_carries_ts_no_403(self) -> None:
        _row_log.clear()
        with TestClient(_app) as client:
            sig, ts, aid, args_blob = self._scrape_row(
                client.get("/rowtable").text
            )
            assert aid.endswith("::row_open")
            # The core of the bug : the ts must ride the SAME <tr> as the
            # sig. Empty here == the 403 regression.
            assert ts, "data-bz-ts missing on the <tr> (the 403 bug)"
            resp = client.post(
                f"/_bretzel/action/{aid}",
                headers={"X-Bz-Sig": sig, "X-Bz-Ts": ts},
                data={"_args": args_blob},
            )
        assert resp.status_code in (200, 204), resp.text
        # The bound row_key (id=7 of the first row) reached the handler.
        assert _row_log == ["open:7"]


class TestActionMaxAgeWindow:
    def test_stale_rejected_fresh_accepted(self) -> None:
        # action_max_age=1s. A correctly-signed but 1h-old ts is rejected ;
        # a fresh one passes. Separate app — the knob is per-app.
        app = Bretzel(secret_key=_SECRET, mode="dev", action_max_age=1)
        app.include(button_page)
        aid = encode_action_id(click_action)
        key = app.config._action_key
        old_ts = str(int(time.time()) - 3600)
        fresh_ts = str(int(time.time()))
        old_sig = sign_action(key, aid, "", ts=old_ts)
        fresh_sig = sign_action(key, aid, "", ts=fresh_ts)
        _click_log.clear()
        with TestClient(app) as client:
            stale = client.post(
                f"/_bretzel/action/{aid}",
                headers={"X-Bz-Sig": old_sig, "X-Bz-Ts": old_ts},
                data={"_args": ""},
            )
            assert stale.status_code == 403
            assert _click_log == []
            fresh = client.post(
                f"/_bretzel/action/{aid}",
                headers={"X-Bz-Sig": fresh_sig, "X-Bz-Ts": fresh_ts},
                data={"_args": ""},
            )
        assert fresh.status_code in (200, 204)
        assert _click_log == ["clicked"]


# ───────────────────────────────────────────────────────────────────────────
# 5. HMAC v2 (C) — @idempotent dedups a same-render double-submit
# ───────────────────────────────────────────────────────────────────────────


class TestIdempotent:
    def test_same_render_double_submit_runs_once(self) -> None:
        _idem_log.clear()
        with TestClient(_app) as client:
            sig, ts, aid = _scrape(client.get("/idem").text)
            hdr = {"X-Bz-Sig": sig, "X-Bz-Ts": ts}
            first = client.post(f"/_bretzel/action/{aid}", headers=hdr, data={"_args": ""})
            second = client.post(f"/_bretzel/action/{aid}", headers=hdr, data={"_args": ""})
        assert first.status_code in (200, 204)
        # Same signed request replayed → deduped to a no-op 204, handler ran once.
        assert second.status_code == 204
        assert _idem_log == ["x"]

    def test_fresh_ts_is_a_distinct_op(self) -> None:
        # A different (fresh-render) ts → different key → runs again. Signed
        # manually with ts+5 to avoid same-second flakiness between two GETs.
        _idem_log.clear()
        with TestClient(_app) as client:
            sig, ts, aid = _scrape(client.get("/idem").text)
            client.post(f"/_bretzel/action/{aid}",
                        headers={"X-Bz-Sig": sig, "X-Bz-Ts": ts}, data={"_args": ""})
            ts2 = str(int(ts) + 5)
            sig2 = sign_action(_app.config._action_key, aid, "", ts=ts2)
            client.post(f"/_bretzel/action/{aid}",
                        headers={"X-Bz-Sig": sig2, "X-Bz-Ts": ts2}, data={"_args": ""})
        assert _idem_log == ["x", "x"]  # both ran — distinct render timestamps
