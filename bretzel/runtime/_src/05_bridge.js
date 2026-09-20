/* 05_bridge.js — HTMX glue : signal snapshot out, <bz-patch> in.
 *
 * The ONLY module that wires HTMX events. No custom action dispatcher :
 * components emit native hx-post, HTMX owns the POST, we only configure
 * the request envelope and consume the response patches.
 *
 *   htmx:configRequest
 *     - snapshot the global signal store, group by instance,
 *     - filter per opt-outs (send_to_server=false) and sync mode
 *       (sync="delta" diffs against the last-sent snapshot),
 *     - inject namespaced form-data (Class.key.field=value),
 *     - inject X-Bretzel-Protocol / X-Bretzel-CSRF / X-Bretzel-Page-ID,
 *     - forward X-Bz-Sig / X-Bz-Ts from the triggering element's
 *       data-bz-sig / data-bz-ts stamps (HMAC v2).
 *
 *   htmx:afterSwap + htmx:oobAfterSwap
 *     - collect <bz-patch> tags, apply patches to the signal store,
 *       remove the consumed tags,
 *     - reserved keys : "_error" (dispatch table below),
 *       "_notifications" (forward to $bz.notify),
 *     - RESCAN the swapped subtree (rebind-after-morph — restores
 *       reactive writes idiomorph clobbered),
 *     - sweep orphaned bz-data scopes.
 *
 *   htmx:responseError
 *     - parse <bz-patch> out of the raw error body (4xx/5xx responses
 *       are not swapped by HTMX), dispatch a reserved ``_error`` directive
 *       via handleError(), else generic notification.
 *
 * ``_error`` dispatch (server emits the envelope via error_envelope()) :
 *   kind "reload"   → window.location.reload() — a stale / rotated HMAC
 *                     signature or CSRF token, which re-rendering the page
 *                     mints fresh (loop-guarded : a 2nd reload-error within
 *                     3s falls back to a toast, so a persistent failure
 *                     surfaces instead of looping).
 *   otherwise / un-enveloped 4xx → generic error toast
 *
 *   (There is NO "redirect" kind: a redirection goes through the
 *   HX-Redirect header, which htmx handles natively, and
 *   `bretzel.redirect()` sets it. The kind stayed here for six months
 *   with nothing emitting it on the Python side — and with nothing being
 *   ABLE to, error_envelope() not knowing how to carry a url. Gate:
 *   tests/consistency/test_bridge_error_kinds_are_emitted.py.)
 */
(function () {
  "use strict";
  const $bz = (window.$bz = window.$bz || {});

  // Wire-format tag name — substituted at build time from protocol.py
  // (single source of truth, even inside the JS).
  const PATCH_TAG = "__PATCH_TAG__";

  function handleError(err) {
    // Typed error directive from a 4xx body (reserved ``_error`` key).
    const kind = err && err.kind;
    if (kind === "reload") {
      // A reload re-renders the page with a fresh HMAC sig + CSRF token,
      // healing the stale-token 403 the user would otherwise dead-end on.
      // Loop-guard : if we already reloaded < 3s ago and hit ANOTHER
      // reload-error, the reload isn't fixing it — surface a toast instead
      // of looping forever.
      let last = 0;
      try { last = parseInt(sessionStorage.getItem("bzReloadAt") || "0", 10); } catch (e) {}
      const now = Date.now();
      if (now - last < 3000) {
        $bz.notify({ variant: "error", message: (err && err.message) || "Request failed — please reload." });
        return;
      }
      try { sessionStorage.setItem("bzReloadAt", String(now)); } catch (e) {}
      window.location.reload();
      return;
    }
    $bz.notify({ variant: "error", message: (err && err.message) || "Request failed." });
  }

  function applyPayload(payload) {
    if (!payload || !payload.patches) return;
    // SEED or PUSH — two paths, two intents.
    //
    //   seed   (partial nav): the server re-emits every instance of the
    //          page, with ITS values, which are the defaults. It cannot
    //          know the browser's. They must therefore only serve to
    //          create what is missing.
    //   push   (action response): the server deliberately mutated a
    //          field. It wins.
    //
    // `config` is the marker, and it is not approximate: on the Python
    // side, `build_patch` only emits it under `include_unchanged=True`,
    // that is to say exactly the seed path. The agreement is gated by
    // `tests/consistency/test_a_seed_patch_never_overwrites.py`, and the
    // result by
    // `tests/runtime_js/test_a_partial_nav_never_clobbers_client_state.py`.
    const isSeed = !!payload.config;
    for (const instancePath of Object.keys(payload.patches)) {
      const fields = payload.patches[instancePath];
      if (instancePath === "_error") {
        // A typed error directive supersedes any other patch — dispatch
        // (reload / toast) and stop applying this payload.
        handleError(fields);
        return;
      }
      if (instancePath === "_notifications") {
        for (const n of fields) $bz.notify(n);
        continue;
      }
      for (const field of Object.keys(fields)) {
        const path = instancePath + "." + field;
        if (isSeed) $bz._store.seed(path, fields[field]);
        else $bz._store.set(path, fields[field]);
      }
    }
    // The partial nav seed's transport config — AFTER the fields,
    // because ``adoptConfig`` registers the persistence and that
    // superimposes the stored snapshot, which must win. Absent from an
    // ordinary action response: the client already has those instances'
    // config.
    if (payload.config && $bz._adoptConfig) {
      for (const path of Object.keys(payload.config)) {
        $bz._adoptConfig(path, payload.config[path]);
      }
    }
  }

  function applyPatchTags() {
    for (const tag of document.querySelectorAll(PATCH_TAG)) {
      let payload = null;
      try {
        payload = JSON.parse(tag.textContent);
      } catch (e) {
        console.error("bz: malformed <bz-patch>", tag.textContent, e);
      }
      tag.remove();
      applyPayload(payload);
    }
  }

  // A COMPOSITE value leaves as JSON, not as is.
  //
  // A form body only carries strings, and htmx treats an array
  // separately: `formDataFromObject` does `obj[key].forEach(v =>
  // append(key, v))`. Two consequences, measured on 2026-08-19:
  //
  //   - `["a","b"]` leaves as TWO fields of the same name, and the
  //     server keeps the last — so `["a","b"]` arrives as `"b"`, and
  //     `["change"]` as `"change"`;
  //   - `[]` adds NOTHING, so the key is absent from the body. Since
  //     hydration only writes the fields that are present, **an emptied
  //     client list could never empty its server field again** — the
  //     exact twin of the unticked box that submits nothing, on the
  //     other transport.
  //
  // `JSON.stringify` puts the client store back on the same convention
  // as the catalogue's seven hidden carriers (`toggle_group`, `select`,
  // `combobox`, `date_range_picker`, `slider`, `resizable`,
  // `accordion`), and it is `_coerce_composite` that undoes it on the
  // Python side — a single wire contract for both paths, instead of two.
  //
  // Scalars are NOT touched: they already travel correctly, and encoding
  // them would make `'"text"'` arrive where the field expects `text`.
  function wireValue(value) {
    return value !== null && typeof value === "object"
      ? JSON.stringify(value)
      : value;
  }

  function injectParameters(detail) {
    const config = $bz._config || {};
    const grouped = new Map(); // instancePath → {field: value}
    for (const [fullPath, sig] of $bz._store.entries()) {
      const cut = fullPath.lastIndexOf(".");
      const path = fullPath.slice(0, cut);
      const field = fullPath.slice(cut + 1);
      if (!grouped.has(path)) grouped.set(path, {});
      grouped.get(path)[field] = sig.peek();
    }
    for (const [path, fields] of grouped.entries()) {
      // ``send_to_server: false`` (declared on the Python side on the
      // class) is the ONLY filter here, and it is all-or-nothing. A
      // "delta" mode lived in this place until 2026-08-14; it was wrong,
      // not merely useless — the full reason is in ``ClientState``'s
      // docstring (bretzel/state/scopes/client.py § "There is NO delta
      // mode"). Do not reintroduce it without reading that paragraph
      // first.
      const cfg = config[path] || {};
      if (cfg.send_to_server === false) continue;
      for (const field of Object.keys(fields)) {
        detail.parameters[path + "." + field] = wireValue(fields[field]);
      }
    }
  }

  /* ── ``$bz.pending`` — "is an action in flight?" ─────────────────────
   *
   * htmx KNOWS a request is in progress (it sets ``.htmx-request`` on
   * the triggering element), but that information was readable by
   * nobody: neither from a ``bz-*`` expression, nor from Python. A dev
   * who wanted a spinner during the round trip therefore had to hold the
   * boolean themselves — and they COULD not hold it on the server side,
   * since server state arrives WITH the response, that is to say when
   * the wait is already over.
   *
   * This module already owns the transport boundary, so it is here that
   * the information is published, as a signal: ``ui.pending()`` returns
   * the expression ``$bz.pending($el, 200)``, read by any ``bz-show`` /
   * ``bz-attr`` like any other source.
   *
   * TWO ADDRESSINGS, a single function. ``$el`` (the element carrying
   * the prop is the trigger) walks up to the ``hx-post``'s carrier
   * through ``closest``: indispensable, because the spinner's
   * ``bz-show`` is set on the SPINNER, not on the button (cf.
   * ``_cloak_show``). A string (the ``action_id``) addresses the same
   * action from elsewhere in the page — ``ui.pending(save)``.
   *
   * THE DELAY IS THE MECHANISM'S REASON TO BE. A spinner that appears
   * under ~200 ms produces a flash, and the interface is perceived as
   * SLOWER than showing nothing. Nobody writes it by hand; here it is
   * the default. The delay travels in the expression, so several delays
   * can coexist on one key — hence a ``Map`` of signals per delay rather
   * than a single signal.
   *
   * A counter, not a boolean: two buttons sharing the same
   * ``action_id`` can be in flight at the same time, and the first
   * return must not extinguish the second.
   */
  const PENDING_BY_ELT = new WeakMap();
  const PENDING_BY_ID = new Map();

  /* Two stores, and it is forced, not incidental: a ``WeakMap`` cannot
   * index a string, and a ``Map`` indexed by elements would hold every
   * trigger for the life of the page. */
  function pendingStore(key) {
    return typeof key === "string" ? PENDING_BY_ID : PENDING_BY_ELT;
  }

  /* The keys a request arms: the triggering element AND its
   * ``action_id``. The latter reads from ``hx-post``, whose format is
   * ``<ROUTE_ACTION>/<id>`` — and ``ROUTE_ACTION`` is SUBSTITUTED here
   * from ``protocol.py`` at build time, like the envelope and patch
   * tags. Without that the JS would become a stranger to the wire
   * format again: it would guess it by string splitting, and a route
   * change on the Python side would show up nowhere. */
  const ACTION_PREFIX = "__ROUTE_ACTION__/";

  /* The THIRD key, reserved: "a navigation is in flight". The shell's
   * bar (``render/shell.nav_progress_html``) is only a ``bz-show`` on
   * it, so it has no mechanism of its own — it is the same registry, the
   * same timing, the same disarm.
   *
   * Two shapes of navigation in this repository, and both are needed:
   * ``detail.boosted`` covers the links boosted by ``hx-boost`` (set at
   * the document level by the shell), and ``hx-push-url`` covers the
   * sidebar / navbar's partial nav, which is not boosted but an explicit
   * ``hx-get`` (``navigation/_wiring.py``). Testing one without the
   * other would leave half the menus with no bar. */
  const NAV_KEY = "__NAV_PENDING_KEY__";

  function pendingKeys(elt, detail) {
    if (!elt || elt.nodeType !== 1) return [];
    const keys = [elt];
    const post = elt.getAttribute("hx-post");
    if (post && post.startsWith(ACTION_PREFIX)) {
      keys.push(post.slice(ACTION_PREFIX.length));
    }
    if ((detail && detail.boosted) || elt.getAttribute("hx-push-url") === "true") {
      keys.push(NAV_KEY);
    }
    return keys;
  }

  function armPending(key) {
    // No entry = nobody reads this key. Nothing to arm: we do not
    // fabricate a signal for a button with no ``ui.pending()``.
    const entry = pendingStore(key).get(key);
    if (!entry || ++entry.count > 1) return;
    entry.byDelay.forEach(function (slot, delay) {
      if (delay <= 0) {
        slot.sig.set(true);
        return;
      }
      slot.timer = setTimeout(function () {
        slot.timer = 0;
        slot.sig.set(true);
      }, delay);
    });
  }

  function disarmPending(key) {
    const entry = pendingStore(key).get(key);
    if (!entry || entry.count === 0 || --entry.count > 0) return;
    entry.byDelay.forEach(function (slot) {
      clearTimeout(slot.timer);
      slot.timer = 0;
      slot.sig.set(false);
    });
  }

  /* Defined at the module's LOAD, not in ``_wireBridge``: a
   * ``bz-show`` can evaluate before the bridge is wired, and a missing
   * ``$bz.pending`` would crash the expression instead of returning
   * ``false``. */
  $bz.pending = function (key, delay) {
    if (key && key.nodeType === 1) key = key.closest("[hx-post]") || key;
    const store = pendingStore(key);
    let entry = store.get(key);
    if (!entry) {
      entry = { byDelay: new Map(), count: 0 };
      store.set(key, entry);
    }
    const ms = delay || 0;
    let slot = entry.byDelay.get(ms);
    if (!slot) {
      slot = { sig: $bz.signal(false), timer: 0 };
      entry.byDelay.set(ms, slot);
    }
    // Reading INSIDE an effect = subscribing. It is the only point of
    // contact with the reactive graph: the toggle then goes through the
    // ordinary microtask flush, like any other source.
    return slot.sig.get();
  };

  $bz._wireBridge = function () {
    document.body.addEventListener("htmx:configRequest", function (e) {
      // An inert control posts NOTHING. It is inertness's third guard
      // (the other two — `bz-on:` handlers and native navigation — live
      // in 02_directives.js, which owns the rule) and it is here because
      // this is the transport boundary: this module is "the ONLY module
      // that wires HTMX events".
      //
      // MEASURED before being written, not read in a doc: htmx 2.0.4
      // does emit `configRequest` then gives the request up on
      // `preventDefault` — the probe's unblocked witness, for its part,
      // leaves. Cf. `tests/audit/probe_configrequest_is_cancelable.py`.
      if ($bz._inert(e.detail.elt)) {
        e.preventDefault();
        return;
      }
      // A BOOSTED navigation that crosses the mobile threshold cannot
      // be a partial swap. `Screen().is_mobile` is a SERVER `if`, and
      // the layout carrying it lives OUTSIDE `[data-bz-outlet]`:
      // swapping the outlet would leave the desktop sidebar in place on
      // a phone viewport, indefinitely, until the next hard load. The
      // `<head>` script does not replay either, so the cookie stays
      // stale and even the server does not know.
      //
      // We resync the cookie and give the navigation back to the
      // browser: a full load re-renders the shell from the fresh cookie.
      // It is NOT a return of the live resize removed on 2026-07-13 —
      // nothing fires on a resize, only on a navigation the user asked
      // for, exactly like an F5.
      //
      // Restricted to `<a>`: the GET of `@refreshable` zones and of the
      // SSE refetch also come through here and must never become a
      // navigation. `$bzScreenSync` is defined by the `<head>` script
      // (`render/shell.py`) — absent from a custom shell, we do nothing.
      if (
        String(e.detail.verb).toLowerCase() === "get" &&
        e.detail.elt &&
        e.detail.elt.tagName === "A" &&
        typeof window.__SCREEN_SYNC_FN__ === "function" &&
        !window.__SCREEN_SYNC_FN__()
      ) {
        e.preventDefault();
        window.location.assign(
          e.detail.path || e.detail.elt.getAttribute("href"),
        );
        return;
      }
      // The client-state snapshot rides ONLY on action POSTs (it's
      // form-data for the handler). Nav GETs (hx-boost partial-nav) and
      // the SSE realtime refetch must NOT carry it — otherwise
      // hx-push-url leaks the entire client store into the address-bar
      // query string (?ColorScheme.default.mode=dark&HubFilter...).
      if (String(e.detail.verb).toLowerCase() === "post") {
        injectParameters(e.detail);
      }
      e.detail.headers["X-Bretzel-Protocol"] = $bz.version;
      if ($bz._csrf) e.detail.headers["X-Bretzel-CSRF"] = $bz._csrf;
      if ($bz._pageId) e.detail.headers["X-Bretzel-Page-ID"] = $bz._pageId;
      // Who writes. The server uses it so as NOT to re-broadcast to
      // this tab what it has just answered it — cf. `$bz._tabId`.
      if ($bz._tabId) e.detail.headers["X-Bretzel-Tab"] = $bz._tabId;
      // Tell the server which @refreshable zones this document
      // carries.
      //
      // Without it, it queues EVERY zone declared on a changed state
      // class — including those of other pages — renders them, sends
      // them, and we throw them away for want of a target. Measured on
      // examples/mad: 8.4 ms of server render wasted against 9.6 ms
      // useful, that is to say nearly half the drain.
      //
      // On action POSTs only: a GET nav (hx-boost) has no drain, and the
      // header would end up in the pushed URL.
      //
      // We read the DOM at the instant of the request, not a list the
      // server would have given us at render: an OOB swap may have
      // introduced a zone since, and a frozen list would condemn it
      // never to refresh again.
      if (String(e.detail.verb).toLowerCase() === "post") {
        const zones = document.querySelectorAll("[data-bz-zone]");
        if (zones.length) {
          const ids = [];
          for (const z of zones) {
            // ``id`` alone, or ``id:fingerprint`` when we know what
            // the zone carries: the server uses it to KEEP QUIET about a
            // zone whose fresh render would be identical. The
            // fingerprint comes from IT, it is never computed here — an
            // absent or stale fingerprint can therefore only make the
            // zone be re-sent, never wrongly suppressed.
            const zid = z.getAttribute("bz-id");
            const vu = $bz._zoneHashes && $bz._zoneHashes[zid];
            ids.push(vu ? zid + ":" + vu : zid);
          }
          e.detail.headers["X-Bretzel-Zones"] = ids.join(",");
        }
      }
      const carrier = e.detail.elt && e.detail.elt.closest("[data-bz-sig]");
      // An action POST WITH NO signature carrier does not leave.
      //
      // It is not about caution: the request is already lost. On the
      // Python side, `action_attrs` is the ONLY place that writes an
      // `hx-post`, and it sets `data-bz-sig` in the same dict — so every
      // htmx POST is an action, and every action is born signed. Not
      // finding a carrier at `configRequest` time means one thing only:
      // the element was DETACHED between the trigger and now, typically
      // by the morph of a `@refreshable` zone.
      //
      // Letting it leave costs, and it is measured. The server refuses
      // any invalid signature with an `_error: reload`, which
      // `handleError` executes — so an already obsolete request RELOADS
      // THE WHOLE PAGE. Reproduced on `/carousel` on 2026-08-27: an
      // autoplay ticks while a flip re-renders the panel, the node
      // disappears, the POST leaves bare, 403, reload. The audit saw
      // "Execution context was destroyed" and counted it as a
      // concurrency flake; it was deterministic.
      //
      // Restricted to POST: a boosted nav and an SSE zone's refetch are
      // GETs, they never have a signature and must pass.
      if (!carrier && String(e.detail.verb).toLowerCase() === "post") {
        e.preventDefault();
        return;
      }
      if (carrier) {
        e.detail.headers["X-Bz-Sig"] = carrier.getAttribute("data-bz-sig");
        const ts = carrier.getAttribute("data-bz-ts");
        if (ts) e.detail.headers["X-Bz-Ts"] = ts;
      }
    });

    function afterSwap(e) {
      applyPatchTags();
      let target = e.detail && e.detail.target ? e.detail.target : e.target;
      // An OOB swap that CHANGES a refreshable zone's ROOT TAG makes HTMX
      // REPLACE the node instead of morphing it in place — and the event
      // still reports the OLD, now-detached element. This happens whenever
      // a zone's single fused child changes element type across a refresh :
      // an empty-state ``ui.text`` (<span>) becoming a populated ``vstack``
      // (<div>), say. Scanning that stale node misses EVERY bz-* directive
      // in the freshly inserted subtree — the first tooltip's bz-teleport
      // never projects, a row's bz-model / bz-show never bind — and the
      // backlog only clears on the NEXT swap that happens to morph in place.
      // The replacement keeps the zone id, so re-resolve to the live node.
      if (target && target.id && !target.isConnected) {
        const live = document.getElementById(target.id);
        if (live) target = live;
      }
      if (target && target.nodeType === 1) {
        $bz._scan(target);
        // Adopt server-authoritative signals (``_serverSync`` keys) from
        // the freshly-morphed bz-data — runs AFTER the rescan so the
        // bz-attr effects are live when the value signal changes.
        $bz._resyncScopes(target);
      }
      $bz._sweepScopes();
      // Drop teleported panels (tooltip/overlay portals under <body>)
      // whose origin was removed by this swap — else they orphan.
      if ($bz._sweepTeleports) $bz._sweepTeleports();
      // A partial-nav swap (hx-boost) may have brought in a subscribe
      // zone on a page that had none at boot — open the SSE stream now.
      if ($bz._ensureSse) $bz._ensureSse();
    }
    for (const eventName of ["htmx:afterSwap", "htmx:oobAfterSwap"]) {
      document.body.addEventListener(eventName, afterSwap);
    }

    /* The witness's life cycle. ``htmx:afterRequest`` is the ONLY
     * disarm: htmx emits it in every exit case — success, 4xx/5xx,
     * network error, timeout, abort — so also listening to
     * ``sendError``/``timeout`` would decrement the counter twice and
     * would extinguish a second request still in flight on the same
     * key. */
    document.body.addEventListener("htmx:beforeRequest", function (e) {
      pendingKeys(e.detail.elt, e.detail).forEach(armPending);
    });
    document.body.addEventListener("htmx:afterRequest", function (e) {
      pendingKeys(e.detail.elt, e.detail).forEach(disarmPending);

      /* The fingerprints of the zones this response has just shipped.
       * We KEEP them to present them again at the next request: the
       * server can then keep quiet about a zone whose fresh render would
       * be identical to what we are already showing.
       *
       * Nothing is computed here, and that is what makes the mechanism
       * safe: the fingerprint is that of the HTML the server sent. If
       * the DOM has changed since for another reason, the fingerprint
       * becomes wrong in the HARMLESS direction — the server will find a
       * difference and re-ship. */
      const xhr = e.detail && e.detail.xhr;
      if (!xhr || !xhr.getResponseHeader) return;
      const brut = xhr.getResponseHeader("X-Bretzel-Zone-Hashes");
      if (!brut) return;
      $bz._zoneHashes = $bz._zoneHashes || {};
      for (const morceau of brut.split(",")) {
        const coupe = morceau.indexOf(":");
        if (coupe > 0) {
          $bz._zoneHashes[morceau.slice(0, coupe)] = morceau.slice(coupe + 1);
        }
      }
    });

    document.body.addEventListener("htmx:responseError", function (e) {
      const text = e.detail.xhr ? e.detail.xhr.responseText || "" : "";
      // 4xx/5xx bodies are not swapped by HTMX, so the patch tags never
      // reach the DOM — extract them from the raw response text.
      const re = new RegExp("<" + PATCH_TAG + ">([\\s\\S]*?)</" + PATCH_TAG + ">", "g");
      let handled = false;
      let m;
      while ((m = re.exec(text)) !== null) {
        try {
          applyPayload(JSON.parse(m[1]));
          handled = true;
        } catch (err) {
          console.error("bz: malformed error <" + PATCH_TAG + ">", err);
        }
      }
      if (!handled) {
        $bz.notify({
          variant: "error",
          message: "Request failed (" + (e.detail.xhr ? e.detail.xhr.status : "?") + ")",
        });
      }
    });
  };
})();
