/* 00_index.js — bootstrap + window.$bz wiring.
 *
 * First in concatenation order but everything heavy runs at
 * DOMContentLoaded, after all modules have registered their pieces on
 * window.$bz. Bootstrap sequence (spec 03-runtime.md §00_index.js) :
 *
 *   1. Parse <bz-envelope> (one-shot bootstrap blob).
 *   2. Seed the global signal store from envelope.client_state.
 *   3. Register persistence adapters per instance (saved snapshots
 *      overlay envelope defaults).
 *   4. Wire the HTMX bridge listeners.
 *   5. Wire the OS color-scheme listener ($bz._osScheme signal).
 *   6. Scan the document : bz-data scopes + all bz-* directives.
 *      (Steps 5/6 were inverted in this comment until 2026-08-01 — the
 *      OS listener is wired BEFORE the scan.)
 *   7. Wire the SSE EventSource + data-bz-subscribe-* zones.
 *   8. Add .bz-ready on <html> (releases [bz-data]{visibility:hidden}),
 *      dispatch bz:ready.
 *
 * Public surface : window.$bz = { version, state, signal, effect,
 * computed, helpers, notify }.
 */
(function () {
  "use strict";
  const $bz = (window.$bz = window.$bz || {});
  $bz.version = "__PROTOCOL_VERSION__";

  // The transport-config vocabulary the CLIENT consumes, declared in
  // ONE place and copied in the loop below. It is a SYNTACTIC anchor,
  // not style: the gate
  // ``tests/consistency/test_client_state_transport_config.py`` reads
  // this literal to check the server really emits everything we read.
  // Without it, it had to guess the reads with a regex (``cfg.<x>``),
  // which picked up the calendar's ``cfg.mode`` / ``cfg.weekstart`` —
  // and compensated with a hand-written list of names, so did NOT cover
  // the next key. Same role as the ``kind === "…"`` the sibling gate for
  // error kinds anchors on.
  const CONFIG_KEYS = ["send_to_server"];

  // Adopt ONE instance's transport config. Two callers, a single body:
  // the boot (from the ``<bz-envelope>``) and the bridge (from a partial
  // nav's seed ``<bz-patch>``). Before 2026-08-15 this body only existed
  // inline in the boot, so a ``ClientState`` discovered during a partial
  // nav got its fields without its config: ``send_to_server`` ignored,
  // and ``persist`` with no adapter — so a saved value never read back.
  //
  // ⚠️ To be called AFTER seeding the instance's fields: ``register``
  // superimposes the already stored snapshot, which must beat the
  // server's defaults ("the user's browser knows better",
  // 04_persistence.js).
  function adoptConfig(path, entry) {
    const cfg = {};
    for (const key of CONFIG_KEYS) cfg[key] = entry[key];
    $bz._config[path] = cfg;
    $bz._persistence.register(path, entry.persist || "memory");
  }
  $bz._adoptConfig = adoptConfig;

  // ── Global typed store : "Class.key.field" → signal ────────────────
  const flat = new Map();
  $bz._store = {
    entries() {
      return flat.entries();
    },
    get(path) {
      // Auto-create on first read so effects subscribe even before the
      // first patch creates the field.
      if (!flat.has(path)) flat.set(path, $bz.signal(undefined));
      return flat.get(path).get();
    },
    peek(path) {
      return flat.has(path) ? flat.get(path).peek() : undefined;
    },
    set(path, value) {
      if (!flat.has(path)) flat.set(path, $bz.signal(value));
      else flat.get(path).set(value);
      if ($bz._persistence) $bz._persistence.notify(path, value);
    },
    // Set an INITIAL value: does nothing if the field already has one.
    //
    // It is what separates "seeding" from "pushing", and the difference
    // cost the user's colour mode: at every partial navigation, the
    // server re-emits ALL the page's instances
    // (`include_unchanged=True`) — with its own values, that is to say
    // the defaults, since it cannot know the browser's. A `set`
    // overwrote them, and since `set` notifies the persistence, the
    // default went into localStorage BEFORE `adoptConfig` went and read
    // the snapshot back from it. The user's choice was destroyed, not
    // merely hidden.
    //
    // `undefined` counts as absent: `get()` auto-creates an empty signal
    // so an effect can subscribe before the first patch, so the signal's
    // existence does not say it carries a value.
    seed(path, value) {
      if (flat.has(path) && flat.get(path).peek() !== undefined) return;
      this.set(path, value);
    },
    fieldsOf(instancePath) {
      const prefix = instancePath + ".";
      const out = {};
      for (const [path, sig] of flat.entries()) {
        if (path.startsWith(prefix)) out[path.slice(prefix.length)] = sig.peek();
      }
      return out;
    },
  };

  // $bz.state.Class.key.field — 3-level proxy over the flat store.
  function level(prefix, depth) {
    return new Proxy(
      {},
      {
        get(_t, key) {
          if (typeof key !== "string") return undefined;
          const path = prefix ? prefix + "." + key : key;
          if (depth === 2) return $bz._store.get(path);
          return level(path, depth + 1);
        },
        set(_t, key, value) {
          if (depth !== 2) {
            throw new Error("bz: only leaf fields of $bz.state are assignable");
          }
          $bz._store.set(prefix + "." + key, value);
          return true;
        },
      },
    );
  }
  $bz.state = level("", 0);

  // ── Notifications ───────────────────────────────────────────────────
  $bz.notify = function (payload) {
    document.dispatchEvent(new CustomEvent("bz:notify", { detail: payload }));
  };

  // ── Bootstrap ───────────────────────────────────────────────────────
  // SSE opens LAZILY : the EventSource is established the first time a
  // subscribe zone is present — at boot OR after a partial-nav swap that
  // brings one in (hx-boost into the outlet). Without this, landing on a
  // page with no subscribe zone (a list / hub) then boost-navigating to a
  // subscribed page (the stepper) would never open the stream — the
  // runtime only boots once, and the old ``if (!zones.length) return``
  // bailed out for good. ``$bz._ensureSse`` is re-called from the bridge's
  // afterSwap, so a zone arriving via partial nav wires up.
  let _sseUrl = null;
  let _sseSource = null;

  /* THIS tab's identity, drawn once per page load.
     It designates nothing on the server side, does not survive the tab
     closing, and serves one thing only: letting the server NOT
     re-broadcast to whoever has just written what it has just received.
     Without it, ticking a box on a shared table cost five requests
     instead of one — the action, then one re-read per subscribed zone,
     each returning exactly what the first had delivered (measured on
     `examples/kanban`: 354 kB for 177 kB of use).

     `crypto.randomUUID` is not guaranteed outside a secure context — a
     test `http://192.168.x.x` loses it — hence the fallback. The value
     has no cryptographic requirement: it only has to be unique among
     one person's open tabs. */
  $bz._tabId = (function () {
    try {
      if (window.crypto && window.crypto.randomUUID) {
        return window.crypto.randomUUID();
      }
    } catch (e) { /* insecure context */ }
    return (Date.now().toString(36) + Math.random().toString(36).slice(2, 10));
  })();

  // ── Refetching ONE subscribed zone ────────────────────────────────
  //
  // ⚠️ This was written, until 2026-09-04:
  //
  //     window.htmx.ajax("GET", url, { swap: "none" })
  //
  // With no ``source``, htmx attaches the request to ``document.body``
  // — so a page's N zones share ONE element, and its implicit
  // ``hx-sync`` makes them cancel each other. Measured on three zones
  // subscribed to the same state, on a client that receives ONLY the
  // stream (not the OOB swaps of its own action):
  //
  //     round 1   a=5    b=0    c=5     (expected 5 everywhere)
  //     round 2   a=5    b=0    c=10    (expected 10)
  //     round 3   a=10   b=0    c=15    (expected 15)
  //
  // The MIDDLE zone never refreshes, the first stays a round behind,
  // only the last is right. It is not slowness, it is WRONG data
  // displayed indefinitely — and nothing reports it, neither console
  // nor network: the lost requests were never emitted.
  //
  // ``source: zone`` gives each zone back its own request cycle.
  //
  // ── And the coalescing, which is the other half ────────────────────
  //
  // The same SSE event wakes every client on the same millisecond, and
  // two close signals are two requests, the first of which already
  // describes a stale state. Hence a window per zone (we keep the LAST
  // demand) and a random offset per client (we spread the herd).
  //
  // Both numbers are small on purpose: beyond that, a "real time" stops
  // being one. 40 ms of window holds a burst of signals, 60 ms of
  // spread is enough to desynchronise clients the same event wakes
  // together.
  const REFETCH_WINDOW_MS = 40;
  const REFETCH_SPREAD_MS = 60;

  // The offset is drawn ONCE per page: redrawing it at every event
  // would re-synchronise the clients on average, which is exactly what
  // we are trying to avoid.
  const _refetchJitter = Math.random() * REFETCH_SPREAD_MS;

  // Keyed by ELEMENT: a zone replaced by a morph loses its entry with
  // it, and does not inherit the old one's timer.
  const _refetchPending = new WeakMap();

  function refetchZone(zone, url) {
    let state = _refetchPending.get(zone);
    if (!state) {
      state = { timer: null };
      _refetchPending.set(zone, state);
    }
    // A more recent demand replaces the one that was waiting: they
    // describe the same final state, and only the last one knows it.
    if (state.timer) clearTimeout(state.timer);
    state.timer = setTimeout(function () {
      state.timer = null;
      window.htmx.ajax("GET", url, { source: zone, swap: "none" });
    }, REFETCH_WINDOW_MS + _refetchJitter);
  }
  $bz._refetchZone = refetchZone;

  function ensureSse() {
    if (_sseSource || !_sseUrl) return;
    if (!document.querySelector("[data-bz-subscribe-state]")) return;
    // Framework-owned ``LiveConnection`` builtin ClientState : mirror the
    // EventSource connection into a store cell apps can bind a live/offline
    // indicator to (``visible=LiveConnection().connected``). Seeded here (not at
    // boot) so only pages that actually open the stream carry it. Starts
    // false ; ``open`` flips it true, ``error`` (transient drop) false —
    // EventSource auto-reconnects and fires ``open`` again.
    $bz._persistence.register("LiveConnection.default", "memory");
    $bz._store.set("LiveConnection.default.connected", false);
    _sseSource = new EventSource(_sseUrl);
    _sseSource.addEventListener("open", function () {
      $bz._store.set("LiveConnection.default.connected", true);
    });
    _sseSource.addEventListener("error", function () {
      $bz._store.set("LiveConnection.default.connected", false);
    });
    _sseSource.addEventListener("state-dirty", function (event) {
      const qualname = event.data;
      for (const zone of document.querySelectorAll("[data-bz-subscribe-state]")) {
        // A broadcast zone lists ALL its deps (space-separated) ; refetch
        // when the dirtied state is one of them.
        const states = zone.getAttribute("data-bz-subscribe-state").split(" ");
        if (!states.includes(qualname)) continue;
        const url = zone.getAttribute("data-bz-subscribe-url");
        if (url && window.htmx) refetchZone(zone, url);
      }
    });
  }
  $bz._ensureSse = ensureSse;

  function boot() {
    let config = null;
    // "__ENVELOPE_TAG__" is substituted at build time from protocol.py.
    const envelope = document.querySelector("__ENVELOPE_TAG__");
    if (envelope) {
      try {
        config = JSON.parse(envelope.textContent);
      } catch (e) {
        console.error("bz: malformed <__ENVELOPE_TAG__>", e);
      }
    }
    $bz._config = {};
    if (config) {
      const clientState = config.client_state || {};
      for (const path of Object.keys(clientState)) {
        const entry = clientState[path];
        // The fields FIRST, the config AFTERWARDS: ``adoptConfig``
        // calls ``register``, which superimposes the stored snapshot —
        // it must overwrite the server's defaults, not the other way
        // round.
        const fields = entry.fields || {};
        for (const field of Object.keys(fields)) {
          $bz._store.set(path + "." + field, fields[field]);
        }
        adoptConfig(path, entry);
      }
      $bz._csrf = config.csrf || null;
      // The page identity, which the bridge sets as a header on every
      // action. Without it, the server forges a new one and the action
      // leaves with a BLANK ``page`` scope state. Until then it only
      // arrived through the page container's ``hx-headers``, which a
      // panel teleported into <body> left — hence a dropdown / dialog /
      // drawer handler that lost the state in silence.
      $bz._pageId = config.page_id || null;
      $bz._endpoints = config.endpoints || {};

      // ── The address, corrected ─────────────────────────────────────
      //
      // A ``session``-scoped state remembers a sort or a filter beyond
      // navigations: coming back to a bare ``/accounts`` renders a
      // sorted view under an address that says nothing about it, and the
      // copied link shows something else to whoever receives it. The
      // server knows both and sets the right address here.
      //
      // ``replaceState`` and NOT ``pushState``: correcting is not
      // navigating. Stacking an entry at every load would make the back
      // button unusable — it would take two clicks for one move.
      //
      // ``history.state`` is preserved: htmx files its own there, and
      // overwriting it would break its restoration on the entries it
      // created.
      if (config.address) {
        try {
          window.history.replaceState(
            window.history.state, "", config.address,
          );
        } catch (e) {
          // A refused address (a different origin) must not stop the
          // page booting: the address will stay silent, the view is
          // right. We degrade, we do not break.
          console.error("bz: adresse non corrigeable", config.address, e);
        }
      }
    }

    $bz._wireBridge();

    // OS color-scheme derived signal — bz-effects depending on both
    // ColorScheme.mode and the OS preference re-run on either change.
    const osDark = window.matchMedia("(prefers-color-scheme: dark)");
    $bz._osScheme = $bz.signal(osDark.matches ? "dark" : "light");
    osDark.addEventListener("change", function () {
      $bz._osScheme.set(osDark.matches ? "dark" : "light");
    });

    // Framework-owned color scheme. ColorScheme is a builtin ClientState,
    // not app state — so the app never has to instantiate it. Guarantee
    // its ``local`` persistence adapter + store cell exist even when the
    // envelope never carried it (no ``ColorScheme()`` in the app), then
    // drive ``<html>.dark`` LIVE. register() is idempotent : if the
    // envelope already registered the adapter above, this is a no-op ;
    // otherwise it overlays any saved snapshot from localStorage.
    // ⚠️ The mode→dark resolution MUST match the FOUC script in
    // ``render/shell.py`` (which runs pre-paint, before this loads).
    $bz._persistence.register("ColorScheme.default", "local");
    if ($bz._store.peek("ColorScheme.default.mode") === undefined) {
      $bz._store.set("ColorScheme.default.mode", "system");
    }
    // The mode -> dark resolution, in ONE place. The effect below sets
    // it on <html>; ``ColorScheme.toggle()`` (Python) calls it to flip
    // against WHAT IS SEEN and not against the stored token.
    //
    // Without that, starting from ``system`` on a dark OS made the FIRST
    // click invisible: it wrote ``dark``, already the resolved value.
    // Measured on both demo apps on 2026-09-04 — the user reported it as
    // "the button does not work", which is the right reading of a
    // control that does nothing one time in two.
    //
    // Reads two signals, so called INSIDE the effect it keeps tracking.
    $bz._isDark = function () {
      const m = $bz._store.get("ColorScheme.default.mode");
      return (
        m === "dark" ||
        ((m === "system" || m === "auto") && $bz._osScheme.get() === "dark")
      );
    };
    $bz.effect(function () {
      document.documentElement.classList.toggle("dark", $bz._isDark());
    });

    // Boot scan timing — exposed as a ``performance.measure`` so the
    // load-handler cost can be attributed (our directive binding vs the
    // debug-only in-browser Tailwind compiler). Negligible overhead, kept
    // permanently for diagnostics : read via
    // ``performance.getEntriesByName("bz:boot-scan")``.
    const _perf = window.performance && performance.mark ? performance : null;
    if (_perf) _perf.mark("bz:scan-start");
    $bz._scan(document.body);
    if (_perf) {
      _perf.mark("bz:scan-end");
      try {
        _perf.measure("bz:boot-scan", "bz:scan-start", "bz:scan-end");
      } catch (e) {
        /* marks evicted under buffer pressure — ignore */
      }
    }

    if ($bz._endpoints && $bz._endpoints.sse) {
      // The identity goes through the URL: `EventSource` has no way of
      // setting a header.
      _sseUrl = $bz._endpoints.sse
        + ($bz._endpoints.sse.indexOf("?") >= 0 ? "&" : "?")
        + "tab=" + encodeURIComponent($bz._tabId);
      ensureSse();
    }

    document.documentElement.classList.add("bz-ready");
    document.dispatchEvent(new CustomEvent("bz:ready"));
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    // Already-ready DOM : defer one microtask so the rest of the
    // bundle (01..06, concatenated after this module) is evaluated
    // before boot() touches $bz._scan / $bz._wireBridge.
    queueMicrotask(boot);
  }
})();
