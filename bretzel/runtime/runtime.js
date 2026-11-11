/* index.js — bootstrap + window.$bz wiring.
 *
 * First in concatenation order but everything heavy runs at
 * DOMContentLoaded, after all modules have registered their pieces on
 * window.$bz. Bootstrap sequence (spec 03-runtime.md §index.js) :
 *
 *   1. Parse <bz-envelope> (one-shot bootstrap blob).
 *   2. Seed the global signal store from envelope.client_state.
 *   3. Register persistence adapters per instance (saved snapshots
 *      overlay envelope defaults).
 *   4. Wire the HTMX bridge listeners.
 *   5. Wire the OS color-scheme listener ($bz._osScheme signal).
 *   6. Scan the document : bz-data scopes + all bz-* directives.
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
  $bz.version = "v1.0";

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
  // nav's seed ``<bz-patch>``). A ``ClientState`` discovered during a
  // partial nav needs its config as well as its fields: without it,
  // ``send_to_server`` is ignored and ``persist`` has no adapter — so a
  // saved value never reads back.
  //
  // ⚠️ To be called AFTER seeding the instance's fields: ``register``
  // superimposes the already stored snapshot, which must beat the
  // server's defaults ("the user's browser knows better",
  // persistence.js).
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
     Without it, an action on a shared table costs one more request per
     subscribed zone, each returning exactly what the action has just
     delivered.

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
  // ⚠️ ``htmx.ajax`` needs a ``source`` here. With none, htmx attaches
  // the request to ``document.body`` — so a page's N zones share ONE
  // element, and its implicit ``hx-sync`` makes them cancel each other.
  // Some zones then never refresh and others stay a round behind. It is
  // not slowness, it is WRONG data displayed indefinitely — and nothing
  // reports it, neither console nor network: the lost requests are never
  // emitted.
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
    // A more recent demand replaces the one that was waiting: they
    // describe the same final state, and only the last one knows it.
    clearTimeout(_refetchPending.get(zone));
    _refetchPending.set(zone, setTimeout(function () {
      // The zone's fingerprint rides along, as on an action POST: the
      // server can then patch the zone instead of shipping it whole.
      const headers = { "X-Bretzel-Zones": $bz._zoneEntry(zone) };
      window.htmx.ajax("GET", url, { source: zone, swap: "none", headers: headers });
    }, REFETCH_WINDOW_MS + _refetchJitter));
  }
  $bz._refetchZone = refetchZone;

  /* When EventSource GIVES UP. It retries a dropped stream by itself,
   * but a retry answered with anything other than a 200
   * ``text/event-stream`` — the 502 a proxy returns while the app
   * restarts — closes it for good (``readyState === CLOSED``, per the
   * spec). Left alone, such a restart leaves every open tab deaf to
   * realtime until a reload. So we reopen it ourselves, doubling the
   * delay from 1 s to 30 s; a successful ``open`` resets it.
   *
   * ``_sseWasDown``: whatever was broadcast during the gap is lost — the
   * broker does not replay. On the ``open`` that ends a gap, every
   * subscribed zone refetches once, through the same coalescing window
   * as a ``state-dirty``. */
  const SSE_RETRY_MIN_MS = 1000;
  const SSE_RETRY_MAX_MS = 30000;
  let _sseRetryMs = SSE_RETRY_MIN_MS;
  let _sseWasDown = false;

  function refetchSubscribedZones(qualname) {
    for (const zone of document.querySelectorAll("[data-bz-subscribe-state]")) {
      // A zone lists the shared states it read (space-separated);
      // refetch when the dirtied state is one of them.
      if (qualname !== undefined) {
        const states = zone.getAttribute("data-bz-subscribe-state").split(" ");
        if (!states.includes(qualname)) continue;
      }
      const url = zone.getAttribute("data-bz-subscribe-url");
      if (url && window.htmx) refetchZone(zone, url);
    }
  }

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
    const source = new EventSource(_sseUrl);
    _sseSource = source;
    source.addEventListener("open", function () {
      $bz._store.set("LiveConnection.default.connected", true);
      _sseRetryMs = SSE_RETRY_MIN_MS;
      if (_sseWasDown) {
        _sseWasDown = false;
        refetchSubscribedZones();
      }
    });
    source.addEventListener("error", function () {
      $bz._store.set("LiveConnection.default.connected", false);
      _sseWasDown = true;
      if (source.readyState !== EventSource.CLOSED) return;
      source.close();
      if (_sseSource === source) _sseSource = null;
      setTimeout(ensureSse, _sseRetryMs);
      _sseRetryMs = Math.min(_sseRetryMs * 2, SSE_RETRY_MAX_MS);
    });
    source.addEventListener("state-dirty", function (event) {
      refetchSubscribedZones(event.data);
    });
  }
  $bz._ensureSse = ensureSse;

  function boot() {
    let config = null;
    // "bz-envelope" is substituted at build time from protocol.py.
    const envelope = document.querySelector("bz-envelope");
    if (envelope) {
      try {
        config = JSON.parse(envelope.textContent);
      } catch (e) {
        console.error("bz: malformed <bz-envelope>", e);
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
      // leaves with a BLANK ``page`` scope state. The page container's
      // ``hx-headers`` alone is not enough: a panel teleported into <body>
      // leaves that container, and a dropdown / dialog / drawer handler
      // would lose the state in silence.
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
    // Without that, starting from ``system`` on a dark OS makes the FIRST
    // click invisible: it writes ``dark``, already the resolved value.
    //
    // Reads two signals, so called INSIDE the effect it keeps tracking.
    $bz._isDark = function () {
      const m = $bz._store.get("ColorScheme.default.mode");
      return (
        m === "dark" ||
        ((m === "system" || m === "auto") && $bz._osScheme.get() === "dark")
      );
    };
    // The switch is INSTANT, like every other framework's: many
    // components carry ``transition-colors`` for their hover, and those
    // transitions would also run on the scheme change, so the page would
    // repaint in a staggered wave. Transitions are suspended for the one
    // frame of the switch — the mechanism next-themes calls
    // ``disableTransitionOnChange``.
    $bz.effect(function () {
      const root = document.documentElement;
      const dark = $bz._isDark();
      if (root.classList.contains("dark") === dark) return;
      const pause = document.createElement("style");
      pause.textContent =
        "*,*::before,*::after{transition:none!important}";
      document.head.appendChild(pause);
      root.classList.toggle("dark", $bz._isDark());
      // Force the new styles to apply while transitions are off, then
      // give transitions back on the next frame.
      window.getComputedStyle(document.body).backgroundColor;
      requestAnimationFrame(function () {
        requestAnimationFrame(function () { pause.remove(); });
      });
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


/* signals.js — reactive primitives : signal / effect / computed.
 *
 * The signal store is the one thing HTMX does not do at all. Design
 * references : Solid.js fine-grained reactivity, Vue 3 ref/computed.
 * We use the simplest viable model — no proxies on arrays, no
 * auto-tracking of nested object mutations (`signal({a:1})` then
 * mutating `.a` does NOT trigger ; `.set({a:2})` with a fresh object
 * does). Predictable, debuggable.
 *
 *   signal(initial) → { get, set, peek, subscribe }
 *     get()        reads + registers the running effect as dependent
 *     peek()       reads without registering
 *     set(v)       triggers dependents unless Object.is(v, current)
 *     subscribe(fn) plain observer (fires on change), returns unsubscribe
 *
 *   effect(fn) → { dispose }
 *     runs now, re-runs whenever any signal it read changes. A per-tick
 *     dirty queue + microtask flush coalesce multiple writes into one
 *     re-run. Re-entering a running effect throws (cycle detection).
 *
 *   computed(fn) → { get, peek, dispose }
 *     memoized derivation, recomputed when a dependency changes.
 *
 * Spec : spec/V3/03-runtime.md §"_src/signals.js".
 */
(function () {
  "use strict";
  const $bz = (window.$bz = window.$bz || {});

  let activeEffect = null;
  const pending = new Set();
  let flushScheduled = false;

  function scheduleFlush() {
    if (flushScheduled) return;
    flushScheduled = true;
    queueMicrotask(function () {
      flushScheduled = false;
      const batch = Array.from(pending);
      pending.clear();
      // One effect that throws reports itself and spares the rest of
      // the batch: without this, a typo in one expression stops every
      // effect waiting in the same flush.
      for (const eff of batch) {
        try {
          eff._run();
        } catch (err) {
          $bz.reportError("an effect", err);
        }
      }
    });
  }

  /* An error the runtime contains is still REPORTED as uncaught
   * (``reportError``): the page goes on, and whoever listens for page
   * errors — Playwright's ``pageerror``, ``bretzel.probe``, the load
   * gates — still hears it. A bare ``console.error`` would have blinded
   * them. */
  $bz.reportError = function (what, err) {
    console.error("bz: " + what + " failed —", err);
    if (typeof window.reportError === "function") window.reportError(err);
    else setTimeout(function () { throw err; });
  };

  function signal(initial) {
    let value = initial;
    const subs = new Set();      // dependent effects
    const observers = new Set(); // plain subscribe() callbacks
    return {
      get() {
        if (activeEffect) {
          subs.add(activeEffect);
          activeEffect._deps.add(subs);
        }
        return value;
      },
      peek() {
        return value;
      },
      set(v) {
        if (Object.is(v, value)) return;
        value = v;
        for (const eff of subs) pending.add(eff);
        scheduleFlush();
        for (const fn of observers) fn(v);
      },
      subscribe(fn) {
        observers.add(fn);
        return function () {
          observers.delete(fn);
        };
      },
    };
  }

  function effect(fn) {
    const eff = {
      _deps: new Set(),
      _disposed: false,
      _running: false,
      _run() {
        if (eff._disposed) return;
        if (eff._running) throw new Error("bz: effect cycle detected");
        for (const subs of eff._deps) subs.delete(eff);
        eff._deps.clear();
        const prev = activeEffect;
        activeEffect = eff;
        eff._running = true;
        try {
          fn();
        } finally {
          activeEffect = prev;
          eff._running = false;
        }
      },
      dispose() {
        eff._disposed = true;
        for (const subs of eff._deps) subs.delete(eff);
        eff._deps.clear();
      },
    };
    eff._run();
    return eff;
  }

  function computed(fn) {
    const out = signal(undefined);
    const eff = effect(function () {
      out.set(fn());
    });
    return { get: out.get, peek: out.peek, dispose: eff.dispose };
  }

  $bz.signal = signal;
  $bz.effect = effect;
  $bz.computed = computed;
})();


/* directives.js — the 13 bz-* directives + the binding engine.
 *
 *   bz-on:<event>="<expr>"   addEventListener, runs expr in scope
 *   bz-model="<path>"        two-way binding on form inputs only
 *   bz-attr:<name>="<expr>"  one-way attribute bind (false/null/undefined
 *                            → removeAttribute, true → empty attr)
 *   bz-class="<obj|array>"   classList add/remove per truthiness ;
 *                            statically-emitted class="" preserved
 *   bz-text="<expr>"         textContent (display-only)
 *   bz-show="<expr>"         style.display toggle, element stays mounted
 *   bz-if="<expr>"           mount/unmount (fresh subtree each mount)
 *   bz-for="v in expr [:key=expr] [:flip]"  keyed iteration — lives on a
 *                            <template> with a single root child. ``:flip``
 *                            FLIP-animates surviving rows on insert/remove.
 *   bz-init="<expr>"         one-shot on first mount of the node
 *   bz-effect="<expr>"       continuous reactive effect
 *   bz-ref="<name>"          register el in scope refs
 *   bz-teleport="<selector>" move <template> content to target, scope
 *                            stays bound to the origin location
 *   (bz-data is owned by scope.js)
 *
 * Engine contract (validated by the Phase 0 spike) :
 *   - scan(root) binds the whole subtree, document order (parents
 *     first, so bz-data scopes exist before descendants resolve them).
 *   - REBIND-AFTER-MORPH : the bridge re-scans every swapped subtree ;
 *     existing bindings are disposed and re-bound, effects re-run and
 *     restore any reactive write idiomorph clobbered (textContent,
 *     display, value). This single rule replaces V2's whole
 *     morph-guard machinery (02_morph_hook.js).
 *
 * Expression sandbox : `new Function` compiled once per (mode, expr),
 * cached. `with($scope)` puts the bz-data scope proxy on the scope
 * chain — bare names read/write scope signals, `$bz.state.X.Y.Z`
 * reaches the global typed store.
 *
 * A CSP is shipped (`Bretzel(csp=True)`): it carries `'unsafe-eval'` for this
 * very `new Function`, but NOT `'unsafe-inline'`, so an injected
 * <script> stays inert. Only the `unsafe-eval`-FREE mode is deferred;
 * that document says why.
 */
(function () {
  "use strict";
  const $bz = (window.$bz = window.$bz || {});

  /* ── The inertness of a disabled control ────────────────────────────
   *
   * A native SUPPORT (`<button disabled>`, `<input disabled>`) is made
   * inert by the browser, for free. An `<a>`, a `<div>`, a
   * `role="menuitem"` NEVER are: the `disabled` attribute does not exist
   * on them, it is simply ignored.
   *
   * Left to each component, it breaks in two ways:
   *   - removing the wiring AT CONSTRUCTION misses a `disabled` driven by
   *     a binding, where the value at render is `false`: the control
   *     stays entirely clickable;
   *   - `pointer-events-none` does block the click but CANCELS the same
   *     element's `cursor-not-allowed` (no pointer event ⇒ no cursor
   *     painted).
   *
   * Inertness is therefore a property of the BASE LAYER, derived
   * from `aria-disabled="true"` alone — the attribute a11y requires
   * anyway, and that the server knows how to make reactive through
   * `bz-attr:`. Three guards, each at its boundary: the `bz-on:`
   * handlers here, native navigation just below, and the server action
   * in `bridge.js` (`preventDefault` on `htmx:configRequest` cancels the
   * request in htmx 2.0.4, cf.
   * `tests/audit/probe_configrequest_is_cancelable.py`).
   *
   * `closest()` and not a direct read: a click lands on the child (the
   * icon, the label), not on the control carrying the state.
   */
  const INERT_SELECTOR = '[aria-disabled="true"]';

  // The events that START an interaction. The list is closed on
  // purpose: blocking every event would make a closing
  // `bz-on:mouseleave` inoperative on a disabled control, so would leave
  // an open state stuck. What we refuse is to act — not to observe.
  const ACTIVATION_EVENTS = new Set([
    "click", "dblclick", "mousedown", "pointerdown", "touchstart",
    "keydown", "keypress", "keyup", "submit",
  ]);

  $bz._inert = function (el) {
    return !!(el && el.closest && el.closest(INERT_SELECTOR));
  };

  // The native navigation of an inert `<a href>`. It has no `bz-on:` to
  // intercept and is not always boosted by HTMX, so it needs its own
  // guard. `preventDefault` ALONE, never `stopPropagation`: cutting
  // propagation here would kill the click-outside of overlays open
  // elsewhere in the page — a dropdown would stay open because you
  // clicked a disabled button at the other end of the screen.
  document.addEventListener("click", function (event) {
    const target = event.target;
    if (target && target.closest && target.closest("a" + INERT_SELECTOR)) {
      event.preventDefault();
    }
  }, true);

  // URLs the browser follows or loads, and the script schemes it must not
  // be given there: the mirror of ``URL_ATTRS`` / ``is_script_url`` in
  // core/escape.py (a link a user typed would otherwise run on click).
  const URL_ATTRS = new Set(["href", "src", "action", "formaction",
    "xlink:href", "poster", "data", "background", "cite"]);
  function scriptUrl(value) {
    return /^(?:javascript|vbscript):/i.test(String(value).replace(/[\u0000- ]/g, ""));
  }

  // ── Expression compiler ────────────────────────────────────────────
  const exprCache = new Map();
  function compile(expr, mode) {
    // mode: "get" (return expr) | "run" (statements) | "set" (expr = $value)
    const key = mode + " " + expr;
    let fn = exprCache.get(key);
    if (!fn) {
      let body;
      if (mode === "get") body = "with($scope){ return (" + expr + ") }";
      else if (mode === "run") body = "with($scope){ " + expr + " }";
      else body = "with($scope){ " + expr + " = $value }";
      fn = new Function(
        "$scope", "$el", "$refs", "$event", "$value", "$dispatch", "$nextTick",
        body,
      );
      exprCache.set(key, fn);
    }
    return fn;
  }

  /* A component's LIFE-CYCLE events. They belong to their root and have
   * nothing to say to an ancestor — unlike ``bz-dropdown-pick`` /
   * ``menu-pick``, which bubble ON PURPOSE.
   *
   * A mirror of ``_wiring.ROOT_DISPATCHED_EVENTS`` on the Python side,
   * guarded by
   * ``tests/consistency/test_scoped_events_mirror_python.py``.
   *
   * Why they do not bubble
   * ----------------------
   * ``on_open=`` / ``on_close=`` set their ``hx-trigger`` on the
   * component's ROOT. With ``bubbles: true``, that root would therefore
   * also catch its descendants' ``open``/``close``:
   *
   *   - a ``ui.select`` in a ``ui.dialog(on_open=…)`` → opening the
   *     panel would POST THE DIALOG's handler, and Escape would POST TWO
   *     ``on_close``;
   *   - a ``ui.alert(dismissible=True)`` in a ``ui.dialog(on_close=…)``
   *     → dismissing the alert would POST THE DIALOG's ``on_close``.
   *
   * Any emitter nested in any listener would leak. Repro:
   * ``tests/probes/probe_overlay_bubble.py``. */
  const SCOPED_EVENTS = new Set(["open", "close"]);

  /* The root of the component containing ``el``: the first ancestor
   * with a ``bz-data``, walking teleportations back through their
   * origin.
   *
   * The same walk as ``findScope`` (``scope.js``) — without the
   * ``_bzScopeHost`` jump, a panel projected under ``<body>`` (Tooltip,
   * Popover, Dropdown, SidebarFooter's popover) would look for its root
   * in the ``<body>`` and find none. */
  function componentRootOf(el) {
    let node = el;
    while (node) {
      if (node._bzScopeHost) {
        node = node._bzScopeHost;
        continue;
      }
      if (node.hasAttribute && node.hasAttribute("bz-data")) return node;
      node = node.parentElement;
    }
    return null;
  }

  function makeDispatch(el) {
    // Memoized per node — handlers on the same element share one closure.
    if (!el._bzDispatch) {
      el._bzDispatch = function (name, detail) {
        // The TARGET is the emitting component's root, not the node
        // that calls: an Alert's ``×`` is a descendant, and its
        // ``close`` must still reach the root's listener. Bubbling did
        // it; with bubbling cut, the root has to be aimed at directly.
        // Fallback on ``el`` if the component has no scope — one
        // dispatch fewer is better than a dispatch elsewhere.
        const scoped = SCOPED_EVENTS.has(name);
        const target = (scoped && componentRootOf(el)) || el;
        target.dispatchEvent(
          new CustomEvent(name, { detail: detail, bubbles: !scoped }),
        );
      };
    }
    return el._bzDispatch;
  }

  function nextTick(fn) {
    queueMicrotask(function () {
      queueMicrotask(fn); // after the signal flush microtask
    });
  }

  function evaluate(el, expr, scope) {
    return compile(expr, "get")(
      scope.proxy, el, scope.refs, null, null, makeDispatch(el), nextTick,
    );
  }

  // ── Binding registry ───────────────────────────────────────────────
  const bound = new WeakMap(); // node → array of dispose fns
  // The same nodes, iterable: a swap that drops a node never disposes it
  // (idiomorph and htmx remove, they do not tell us), so ``sweepDetached``
  // walks them after each swap. Otherwise an effect that read the client
  // state (``$bz.state``, a page-long signal) would stay in that signal's
  // subscribers with its node — the whole previous page would survive
  // every boosted navigation. Strong, but swept.
  const live = new Set();

  function track(node, disposers) {
    bound.set(node, disposers);
    live.add(node);
  }
  // Teleported nodes (panels moved to <body> by bz-teleport) — tracked
  // so a swap that removes the ORIGIN template can sweep the orphan
  // (idiomorph only touches the swapped subtree, never the panel in
  // <body>). cf. ``sweepTeleports`` + the bridge afterSwap.
  const teleported = new Set();

  function disposeEl(el) {
    const disposers = bound.get(el);
    if (!disposers) return;
    for (const d of disposers) d();
    bound.delete(el);
    live.delete(el);
  }

  function disposeTree(node) {
    if (node.nodeType !== 1) return;
    disposeEl(node);
    for (const child of node.querySelectorAll("*")) disposeEl(child);
    if (owned.size) {
      for (const el of Array.from(owned.keys())) {
        if (node === el || node.contains(el)) releaseOwned(el);
      }
    }
  }

  /* What a ``bz-init`` took OUTSIDE its node — a listener on
   * ``document`` or ``window`` (``$bz.helpers.escapeKey``,
   * ``clickOutside``, ``onWindow``). Not given back, each overlay of a
   * page would leave its listeners on ``document`` at every boosted
   * navigation, each closure holding the old page's DOM. The
   * ``isConnected`` guards keep them quiet, not gone.
   *
   * The helpers hand their unsubscribe to ``$bz._own``; while a
   * ``bz-init`` runs, it files it under that node. The node gives it
   * back when it is disposed (``bz-for`` / ``bz-if`` / teleport) or when
   * a swap left it out of the document (``sweepDetached``, from the
   * bridge). Kept OUT of ``bound``: a rebind disposes ``bound`` and a
   * ``bz-init`` does not run twice, so its listeners must outlive it. A
   * released node forgets its init: scanned again, it re-subscribes. */
  const owned = new Map(); // node → [release fns] ; swept, so strong is fine
  let owner = null; // the node whose bz-init is running

  function own(release) {
    if (owner && typeof release === "function") {
      const list = owned.get(owner);
      if (list) list.push(release);
      else owned.set(owner, [release]);
    }
    return release;
  }

  function releaseOwned(el) {
    const list = owned.get(el);
    if (!list) return;
    owned.delete(el);
    delete el._bzInitDone;
    for (const release of list) release();
  }

  // After a swap: every node it left out of the document gives back its
  // effects and listeners, and what its bz-init took outside it.
  function sweepDetached() {
    for (const node of Array.from(live)) {
      if (!node.isConnected) disposeEl(node);
    }
    for (const el of Array.from(owned.keys())) {
      if (!el.isConnected) releaseOwned(el);
    }
  }

  function elEffect(el, fn, disposers) {
    const eff = $bz.effect(fn);
    disposers.push(eff.dispose);
  }

  // ── Simple (non-structural) directives ─────────────────────────────
  const HANDLERS = {
    ref(el, expr, scope, disposers) {
      scope.refs[expr] = el;
      disposers.push(function () {
        if (scope.refs[expr] === el) delete scope.refs[expr];
      });
    },

    model(el, expr, scope, disposers) {
      const getter = compile(expr, "get");
      const setter = compile(expr, "set");
      const dispatch = makeDispatch(el);
      const isCheckbox = el.type === "checkbox";
      const isRadio = el.type === "radio";
      elEffect(el, function () {
        const v = getter(scope.proxy, el, scope.refs, null, null, dispatch, nextTick);
        if (isCheckbox) el.checked = !!v;
        else if (isRadio) el.checked = String(v) === el.value;
        else {
          const s = v === undefined || v === null ? "" : String(v);
          if (el.value !== s) el.value = s;
        }
      }, disposers);
      const eventName =
        isCheckbox || isRadio || el.tagName === "SELECT" ? "change" : "input";
      const listener = function (event) {
        const value = isCheckbox ? el.checked : el.value;
        if (isRadio && !el.checked) return;
        setter(scope.proxy, el, scope.refs, event, value, dispatch, nextTick);
      };
      el.addEventListener(eventName, listener);
      disposers.push(function () {
        el.removeEventListener(eventName, listener);
      });
    },

    attr(el, expr, scope, disposers, name) {
      // ``value`` / ``checked`` are IDL properties whose LIVE state
      // diverges from the attribute on form controls : a dirty input
      // displays ``el.value`` (the property), not the ``value``
      // attribute, and idiomorph clobbers the property on morph — so a
      // bz-attr:value that only set the attribute would empty the input
      // after a refresh (same attribute-vs-property trap as bz-text vs
      // textContent). Mirror onto the property too. The ``el.value !==
      // str`` guard avoids resetting the caret while the user types.
      // Scoped to native form controls : custom elements (e.g.
      // <bz-calendar>) reflect ``value`` through their own
      // attributeChangedCallback and must NOT be short-circuited by a
      // direct property write.
      const tag = el.tagName;
      const formControl = tag === "INPUT" || tag === "SELECT" || tag === "TEXTAREA";
      const idlValue = name === "value" && formControl;
      const idlChecked = name === "checked" && tag === "INPUT";
      elEffect(el, function () {
        const v = evaluate(el, expr, scope);
        if (v === false || v === null || v === undefined) {
          el.removeAttribute(name);
          if (idlValue) { if (el.value !== "") el.value = ""; }
          else if (idlChecked) el.checked = false;
        } else {
          const str = v === true ? "" : String(v);
          // A script URL is not set where the browser follows or
          // loads one: the server leaves it out the same way.
          if (URL_ATTRS.has(name) && scriptUrl(str)) { el.removeAttribute(name); return; }
          el.setAttribute(name, str);
          if (idlValue) { if (el.value !== str) el.value = str; }
          else if (idlChecked) el.checked = !!v;
        }
      }, disposers);
    },

    class(el, expr, scope, disposers) {
      // Dynamic classes are tracked so the static class="" set by the
      // server is never touched. The tracking set is per-BIND (this
      // closure), NOT a property persisted on the element.
      //
      // Why it MUST be per-bind : a @refreshable morph rewrites the
      // element's class="" back to the freshly-rendered SSR baseline,
      // which STRIPS the classes this directive had added (the active
      // pill on a Pagination page, the grid-rows-[1fr] on an open
      // Accordion body, a Sidebar's active item…). The bridge then
      // re-scans the swapped subtree, disposing and RE-BINDING us. If the
      // set lived on the element (`el._bzClassDyn`) it would survive the morph,
      // so the re-bound effect would see prev===next and NEVER re-add the
      // stripped classes — the styling would silently vanish until the next
      // interaction. A fresh per-bind set
      // starts empty, so the first run after a morph re-adds every class
      // from the real (clobbered) DOM baseline. Within a single bind the
      // closure persists across signal-driven re-runs, so normal
      // add/remove diffing is unchanged.
      //
      // `managed` alone is NOT enough to keep that promise: it holds what
      // the EXPRESSION produced, not what was really added. Yet
      // `classList` is a set — a token already present in the SSR
      // `class=` makes the `add` a no-op, but the `remove` deletes it for
      // good. A theme that repeats a token between its static layer and
      // its dynamic layer would therefore see the static token DESTROYED
      // at the first toggle. Hence `base`: the baseline read at bind time,
      // never removable.
      let managed = new Set();
      const base = new Set(el.classList);
      elEffect(el, function () {
        const v = evaluate(el, expr, scope);
        const next = new Set();
        if (Array.isArray(v)) {
          for (const entry of v) {
            if (!entry) continue;
            for (const cls of String(entry).split(/\s+/)) if (cls) next.add(cls);
          }
        } else if (v && typeof v === "object") {
          for (const key of Object.keys(v)) {
            if (!v[key]) continue;
            for (const cls of key.split(/\s+/)) if (cls) next.add(cls);
          }
        } else if (typeof v === "string") {
          for (const cls of v.split(/\s+/)) if (cls) next.add(cls);
        }
        for (const cls of managed)
          if (!next.has(cls) && !base.has(cls)) el.classList.remove(cls);
        for (const cls of next) if (!managed.has(cls)) el.classList.add(cls);
        managed = next;
      }, disposers);
      // An effect that ADDS classes REMOVES them on its disposal.
      //
      // Without that symmetry, `base` ends up protecting what the
      // RUNTIME added instead of what the SERVER wrote. `bindEl` starts
      // with `disposeEl`, so every re-bind (the bridge re-binds after
      // EVERY htmx swap) recaptures `base = new Set(el.classList)` — and
      // if the old effect left its classes in place, they enter the new
      // baseline and become PERMANENTLY unremovable.
      //
      // Without it, after a partial navigation a sidebar entry keeps its
      // `bg-primary` background although its `data-active` has gone back
      // to `false` — an item HALF active, background painted and text
      // left grey. `bz-attr` has no baseline, so it stays right: the two
      // channels of one state diverge.
      //
      // Affects every component that emits `bz-class`, not only the
      // sidebar. Same family as a class lost after a morph, opposite
      // direction: the class SURVIVES instead of disappearing.
      disposers.push(function () {
        for (const cls of managed)
          if (!base.has(cls)) el.classList.remove(cls);
      });
    },

    text(el, expr, scope, disposers) {
      elEffect(el, function () {
        const v = evaluate(el, expr, scope);
        el.textContent = v === undefined || v === null ? "" : String(v);
      }, disposers);
    },

    show(el, expr, scope, disposers) {
      elEffect(el, function () {
        const on = evaluate(el, expr, scope);
        const held = !on && el.contains(document.activeElement);
        el.style.display = on ? "" : "none";
        if (held) handFocusOn(el);
      }, disposers);
    },

    on(el, expr, scope, disposers, eventName) {
      const runner = compile(expr, "run");
      const dispatch = makeDispatch(el);
      const guarded = ACTIVATION_EVENTS.has(eventName);
      const listener = function (event) {
        // An inert control does not START an interaction. The guard
        // lives here because it is the runtime's only place that
        // installs a ``bz-on:`` — so the rule holds for the 76
        // components without any of them rewriting it.
        if (guarded && $bz._inert(el)) return;
        runner(scope.proxy, el, scope.refs, event, null, dispatch, nextTick);
      };
      el.addEventListener(eventName, listener);
      disposers.push(function () {
        el.removeEventListener(eventName, listener);
      });
    },

    effect(el, expr, scope, disposers) {
      const runner = compile(expr, "run");
      const dispatch = makeDispatch(el);
      elEffect(el, function () {
        runner(scope.proxy, el, scope.refs, null, null, dispatch, nextTick);
      }, disposers);
    },

    init(el, expr, scope) {
      if (el._bzInitDone) return; // one-shot per NODE (survives rebind)
      el._bzInitDone = true;
      const outer = owner;
      owner = el;
      try {
        compile(expr, "run")(
          scope.proxy, el, scope.refs, null, null, makeDispatch(el), nextTick,
        );
      } finally {
        owner = outer;
      }
    },
  };

  // Binding order : refs first (siblings may use them in init), init
  // last (element fully wired when it runs).
  /* The element that had the focus is hidden by its ``bz-show``: hand
   * the focus to the nearest visible focusable element around it, once
   * the whole batch is applied (a task, not a microtask): the control
   * that takes its place is shown in the same flush. Left on the hidden
   * element, the next Tab would start over from the end of the document. */
  const FOCUSABLE = 'a[href], button:not([disabled]), input:not([disabled]):not([type=hidden]), '
    + 'select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';
  // The ONE list of what takes the focus: ``helpers.js`` reads it
  // (focus trap, autofocus), so a picker's hidden carrier is left out
  // there too.
  $bz._FOCUSABLE = FOCUSABLE;
  function handFocusOn(hidden) {
    setTimeout(function () {
      const now = document.activeElement;
      if (now && now !== document.body && !hidden.contains(now)) return;
      const shown = function (c) {
        return !hidden.contains(c) && c.getClientRects().length > 0;
      };
      for (let box = hidden.parentElement; box; box = box.parentElement) {
        const all = Array.from(box.querySelectorAll(FOCUSABLE)).filter(shown);
        if (!all.length) continue;
        const after = all.find(function (c) {
          return hidden.compareDocumentPosition(c) & Node.DOCUMENT_POSITION_FOLLOWING;
        });
        (after || all[all.length - 1]).focus({ preventScroll: true });
        return;
      }
    }, 0);
  }

  const ORDER = ["ref", "model", "attr", "class", "text", "show", "on", "effect", "init"];

  function bindEl(el) {
    disposeEl(el);
    const todo = [];
    for (const attr of Array.from(el.attributes)) {
      const name = attr.name;
      if (name.startsWith("bz-on:")) todo.push(["on", attr.value, name.slice(6)]);
      else if (name.startsWith("bz-attr:")) todo.push(["attr", attr.value, name.slice(8)]);
      else if (name === "bz-model") todo.push(["model", attr.value, null]);
      else if (name === "bz-class") todo.push(["class", attr.value, null]);
      else if (name === "bz-text") todo.push(["text", attr.value, null]);
      else if (name === "bz-show") todo.push(["show", attr.value, null]);
      else if (name === "bz-ref") todo.push(["ref", attr.value, null]);
      else if (name === "bz-effect") todo.push(["effect", attr.value, null]);
      else if (name === "bz-init") todo.push(["init", attr.value, null]);
    }
    if (!todo.length) return;
    todo.sort(function (a, b) {
      return ORDER.indexOf(a[0]) - ORDER.indexOf(b[0]);
    });
    const disposers = [];
    track(el, disposers);
    const scope = $bz._scopeFor(el);
    // One directive that throws reports itself — element and expression
    // named — and spares the element's other directives, the subtree and
    // the page.
    for (const [kind, expr, arg] of todo) {
      try {
        HANDLERS[kind](el, expr, scope, disposers, arg);
      } catch (err) {
        $bz.reportError(kind + (arg ? ":" + arg : "") + '="' + expr + '" on <'
          + el.tagName.toLowerCase() + (el.id ? "#" + el.id : "") + ">", err);
      }
    }
  }

  // ── Structural : bz-if ─────────────────────────────────────────────
  function bindIf(el) {
    const expr = el.getAttribute("bz-if");
    const anchor = document.createComment("bz-if");
    el.parentNode.insertBefore(anchor, el);
    const template = el;
    template.remove();
    const scope = $bz._scopeFor(anchor.parentElement || document.body);
    let mounted = null;
    const eff = $bz.effect(function () {
      const v = compile(expr, "get")(
        scope.proxy, anchor, scope.refs, null, null, function () {}, nextTick,
      );
      if (v && !mounted) {
        mounted = template.cloneNode(true);
        mounted.removeAttribute("bz-if");
        // Inserted by the runtime, like a bz-for row: a walk by position
        // (``bridge.js``, ``applyPositionPatches``) skips it.
        mounted.setAttribute(ROW_MARK, "");
        anchor.parentNode.insertBefore(mounted, anchor.nextSibling);
        scan(mounted);
      } else if (!v && mounted) {
        disposeTree(mounted);
        mounted.remove();
        mounted = null;
      }
    });
    track(anchor, [
      eff.dispose,
      function () {
        if (mounted) {
          disposeTree(mounted);
          mounted.remove();
          mounted = null;
        }
      },
    ]);
  }

  // Generic reflow-motion tokens for the ``:flip`` list option — the
  // framework's standard short duration + easing (the same easing the shell
  // uses across its keyframes). Not slaved to any one component: a
  // dismissed toast goes at once, its neighbours glide into the slot.
  const FLIP_MS = 200;
  const FLIP_EASING = "cubic-bezier(.4,0,.2,1)";

  // FLIP "Play" — slide each surviving row from its recorded box to its new
  // one. Shared by ``bindFor`` when the loop opts in with ``:flip``. Skips
  // rows that did not move and rows with no "First" rect (they are new —
  // their own enter animation owns the entrance).
  //
  // Driven by the Web Animations API rather than a transition + inverse
  // transform : the manual invert/release pattern needs the inverted frame
  // to PAINT before the release, but rAF callbacks run before the paint
  // step (HTML rendering order : rAF → layout → paint), so releasing in the
  // next rAF cancels the invert and nothing animates. ``element.animate``
  // interpolates from → to with no timing dance and auto-clears its effect
  // (default ``fill: none``) — no inline style residue, no ``transitionend``
  // bookkeeping.
  function flipPlay(rows, firstRects) {
    if (typeof Element.prototype.animate !== "function") return;
    for (const [key, row] of rows) {
      const first = firstRects.get(key);
      if (!first) continue;
      const node = row.node;
      const last = node.getBoundingClientRect();
      const dx = first.left - last.left;
      const dy = first.top - last.top;
      if (Math.abs(dx) < 0.5 && Math.abs(dy) < 0.5) continue;
      // Cancel a FLIP still in flight (rapid successive removals) so the new
      // delta starts from the current visual position, not a stale one.
      if (node._bzFlip) node._bzFlip.cancel();
      node._bzFlip = node.animate(
        [
          { transform: "translate(" + dx + "px," + dy + "px)" },
          { transform: "translate(0px,0px)" },
        ],
        { duration: FLIP_MS, easing: FLIP_EASING },
      );
    }
  }

  // ── Structural : bz-for (on a <template>, single root child) ──────
  //: Set on every row a bz-for clones (and on a bz-if mount). The server's HTML never has it, so
  //: a morph that recycles a row into a server node strips it — which is
  //: how a rebind tells a row from a node that only sits where one was.
  const ROW_MARK = "data-bz-row";

  function bindFor(template) {
    let raw = template.getAttribute("bz-for");
    // ``:flip`` — optional trailing flag that opts the loop into FLIP reflow
    // animation (surviving rows glide to their new box instead of teleporting
    // when a sibling is inserted/removed). Stripped BEFORE the main parse so
    // the greedy ``:key=`` group never swallows it ; other loop options thus
    // stay on one surface (the bz-for expression), next to ``:key=``.
    const flipEnabled = /\s+:flip\s*$/.test(raw);
    if (flipEnabled) raw = raw.replace(/\s+:flip\s*$/, "");
    const match = raw.match(/^\s*(\w+)\s+in\s+(.+?)(?:\s+:key=(.+))?\s*$/);
    if (!match) {
      console.error("bz: invalid bz-for expression:", raw);
      return;
    }
    const varName = match[1];
    const listExpr = match[2];
    const keyExpr = match[3] || null;
    const content = template.content.firstElementChild;
    if (!content) {
      console.error("bz: <template bz-for> needs a single root child");
      return;
    }
    if (template._bzForRows) {
      // Rebind after morph : rows are keyed in the Map, effect below
      // reconciles against it — dispose the old effect first.
      disposeEl(template);
      // The server's HTML never carries the rows, so idiomorph matches
      // them by POSITION against what follows the template — and may
      // RECYCLE a row's node into a server sibling (a multi-select's
      // first pill can become its placeholder: same node, row marker
      // gone, hidden by its bz-show). The Map would then hold a connected
      // node that is no longer a row, and the pill would never come
      // back. A row that lost its marker, or left the template's
      // parent, belongs to the server's HTML: drop its stale
      // bindings (the scan rebinds it as what it has become) and let the
      // effect clone a fresh row.
      for (const [key, row] of Array.from(template._bzForRows.entries())) {
        const kept = row.node.isConnected
          && row.node.hasAttribute(ROW_MARK)
          && row.node.parentNode === template.parentNode;
        if (!kept) {
          disposeTree(row.node);
          template._bzForRows.delete(key);
        }
      }
    }
    const rows = (template._bzForRows = template._bzForRows || new Map());
    const scope = $bz._scopeFor(template.parentElement || document.body);
    // ``:flip`` opt-in (parsed above) makes surviving rows slide from their
    // old box to the new one when a sibling is inserted or removed, instead
    // of teleporting into the freed space. The notification stack uses it so
    // a dismissed toast's neighbours glide up rather than snap.
    // Reconciliation stays key-based (nodes are
    // reused, never remounted) — FLIP only animates the layout delta of nodes
    // present both BEFORE and AFTER the update.

    const eff = $bz.effect(function () {
      const items =
        compile(listExpr, "get")(
          scope.proxy, template, scope.refs, null, null, function () {}, nextTick,
        ) || [];
      // FLIP "First" : snapshot every connected row's box before we mutate.
      // Honour prefers-reduced-motion via the shared gate (helpers.js) —
      // read live so an OS toggle mid-session is respected.
      const flip = flipEnabled && !$bz.helpers.prefersReducedMotion();
      const firstRects = flip ? new Map() : null;
      if (flip) {
        for (const [k, r] of rows) {
          if (r.node.isConnected) firstRects.set(k, r.node.getBoundingClientRect());
        }
      }
      const seen = new Set();
      let cursor = template;
      items.forEach(function (item, index) {
        let key;
        if (keyExpr) {
          const probe = $bz._makeItemScope(scope, { [varName]: item, $index: index });
          key = compile(keyExpr, "get")(
            probe.proxy, template, scope.refs, null, null, function () {}, nextTick,
          );
        } else {
          key = index;
        }
        key = String(key);
        seen.add(key);
        let row = rows.get(key);
        if (!row) {
          const node = content.cloneNode(true);
          node.setAttribute(ROW_MARK, "");
          const itemScope = $bz._makeItemScope(scope, { [varName]: item, $index: index });
          node._bzItemScope = itemScope;
          row = { node: node, scope: itemScope };
          rows.set(key, row);
          cursor.parentNode.insertBefore(node, cursor.nextSibling);
          scan(node);
        } else {
          row.scope.vars[varName].set(item);
          row.scope.vars.$index.set(index);
          if (cursor.nextSibling !== row.node) {
            cursor.parentNode.insertBefore(row.node, cursor.nextSibling);
          }
        }
        cursor = row.node;
      });
      for (const [key, row] of Array.from(rows.entries())) {
        if (seen.has(key)) continue;
        disposeTree(row.node);
        row.node.remove();
        rows.delete(key);
      }
      // FLIP "Last / Invert / Play" : now the DOM is final, measure each
      // surviving row's new box, jump it back to where it was with an
      // instant inverse transform, then release it on the next frame so it
      // transitions to its resting place. Rows absent from ``firstRects``
      // are freshly inserted — they run their own enter animation, not FLIP.
      if (flip) flipPlay(rows, firstRects);
    });
    track(template, [eff.dispose]);
  }

  // ── Structural : bz-teleport (on a <template>) ─────────────────────
  /* What the runtime writes on a projected panel's root, and a morph
   * from the server's copy must leave alone: ``style`` (``display``, the
   * floating position) and ``data-side``. */
  const RUNTIME_OWNED = new Set(["style", "data-side"]);

  /* A refresh rewrote the source of a LIVE panel: morph each copy in
   * place instead of dropping and re-projecting it. Re-projected, an open
   * popover would be rebuilt and replay its entrance at every box ticked
   * inside it. Morphed, the node stays: its position, its open state, its
   * focus. The same children, tag for tag, or ``false``: the caller then
   * re-projects. */
  /* What htmx reads on an ANCESTOR (``hx-boost``, ``hx-target``,
   * ``hx-swap``, ``hx-headers``...): the page container carries them, and
   * a panel projected under ``<body>`` has left it. A link in an open
   * popover would then navigate the whole document instead of swapping
   * the page. The clone takes, from the
   * origin's nearest ancestor, each one it does not set itself: htmx's own
   * inheritance, frozen at projection. */
  const HTMX_INHERITED = [
    "hx-boost", "hx-target", "hx-swap", "hx-headers", "hx-vals",
    "hx-include", "hx-indicator", "hx-sync", "hx-push-url", "hx-select",
    "hx-params", "hx-encoding", "hx-ext", "hx-disabled-elt",
  ];
  function inheritHtmx(template, node) {
    for (const name of HTMX_INHERITED) {
      if (node.hasAttribute(name)) continue;
      const from = template.closest("[" + name + "]");
      if (from) node.setAttribute(name, from.getAttribute(name));
    }
    return node;
  }

  function morphTeleported(template) {
    const copies = template._bzTeleported;
    const fresh = Array.from(template.content.children);
    if (!window.Idiomorph || copies.length !== fresh.length) return false;
    for (let i = 0; i < copies.length; i++) {
      if (!copies[i].isConnected || copies[i].tagName !== fresh[i].tagName) return false;
    }
    copies.forEach(function (copy, i) {
      window.Idiomorph.morph(copy, inheritHtmx(template, fresh[i].cloneNode(true)), {
        morphStyle: "outerHTML",
        callbacks: {
          beforeAttributeUpdated: function (name, node) {
            return !(node === copy && RUNTIME_OWNED.has(name));
          },
        },
      });
      scan(copy); // rebinds: ``bindEl`` disposes before it binds
      // The server's new values reach the copy's scopes (a box ticked
      // elsewhere): ``absorb`` alone keeps the client's.
      if ($bz._resyncScopes) $bz._resyncScopes(copy);
      if (window.htmx) window.htmx.process(copy);
    });
    return true;
  }

  function bindTeleport(template) {
    // ``<template>.innerHTML`` serialises the content fragment. idiomorph
    // DOES morph into template content (verified), and the runtime never
    // mutates it (directives run on the teleported CLONE under the target,
    // not here) — so it is a reliable signature of the SOURCE. When it
    // changes, a refresh rewrote the panel and the live <body> copy is
    // stale and must be re-projected (else e.g. a tooltip's text / color /
    // arrow stays frozen on its first render inside a refreshable).
    const sig = template.innerHTML;
    const live =
      template._bzTeleported &&
      template._bzTeleported.some(function (n) {
        return n.isConnected;
      });
    if (live && template._bzTeleportSig === sig) {
      return; // already live AND source unchanged : keep the clone (no
      // flicker, preserves the panel's floating position / open state)
    }
    if (live && morphTeleported(template)) {
      template._bzTeleportSig = sig;
      return;
    }
    const target = document.querySelector(template.getAttribute("bz-teleport"));
    if (!target) {
      console.error("bz: bz-teleport target not found:", template.getAttribute("bz-teleport"));
      return;
    }
    // A morph rewrote the source : drop the stale clones before
    // re-projecting so the target reflects the new content.
    if (template._bzTeleported) {
      for (const stale of template._bzTeleported) {
        disposeTree(stale);
        stale.remove();
        teleported.delete(stale);
      }
      template._bzTeleported = null;
    }
    const moved = [];
    for (const child of Array.from(template.content.children)) {
      const node = inheritHtmx(template, child.cloneNode(true));
      node._bzScopeHost = template; // scope resolves at the ORIGIN location
      target.appendChild(node);
      moved.push(node);
      teleported.add(node);
      scan(node); // bz-* directives on the clone
      // htmx wiring on the clone. A teleported panel can carry ``hx-post``
      // action buttons (Dropdown items, a Popover's server buttons). The
      // ORIGIN lives inside an inert ``<template>`` (htmx never processes
      // template content), and a re-projection after a refresh appends the
      // clone OUTSIDE htmx's swap path — so htmx never wires the action and
      // the click fires only the client ``bz-dropdown-pick`` (menu closes),
      // never the POST. We own projecting the clone, so we own processing
      // it — mirror of ``scan``. Idempotent : htmx skips already-initialised
      // nodes, so the first projection (caught by htmx's observer) is a
      // no-op here.
      if (window.htmx) window.htmx.process(node);
    }
    template._bzTeleportSig = sig;
    template._bzTeleported = moved;
    track(template, [
      function () {
        for (const node of moved) {
          disposeTree(node);
          node.remove();
          teleported.delete(node);
        }
        template._bzTeleported = null;
      },
    ]);
  }

  // Remove teleported panels whose ORIGIN template left the DOM (a morph
  // dropped the owning tooltip/overlay). Without this they linger under
  // <body> — a tooltip that re-renders away mid-hover stays visible
  // forever. Called from the bridge afterSwap.
  function sweepTeleports() {
    if (!teleported.size) return;
    for (const node of Array.from(teleported)) {
      const host = node._bzScopeHost;
      if (!host || !host.isConnected) {
        disposeTree(node);
        node.remove();
        teleported.delete(node);
      }
    }
  }

  /* The fields a form lost to ``bz-teleport``. A popover INSIDE a
   * ``ui.form`` projects its inputs under ``<body>``: they leave the
   * form's ``elements``, and htmx — which reads them — submitted the form
   * without them, in silence. The bridge adds these back (configRequest).
   * A field of a form the panel carries itself (``el.form``) stays its. */
  function teleportedFieldsOf(form) {
    const out = [];
    for (const node of teleported) {
      const host = node._bzScopeHost;
      if (!host || !node.isConnected || !form.contains(host)) continue;
      const fields = Array.from(node.querySelectorAll("input, select, textarea"));
      if (node.matches("input, select, textarea")) fields.unshift(node);
      for (const el of fields) if (el.name && !el.disabled && !el.form) out.push(el);
    }
    return out;
  }

  // ── Scan ───────────────────────────────────────────────────────────
  function scan(root) {
    if (!root || root.nodeType !== 1) return;
    const els = [root].concat(Array.from(root.querySelectorAll("*")));
    // Pass 1 : materialise bz-data scopes (parents before children).
    for (const el of els) {
      if (el.hasAttribute("bz-data")) $bz._ensureScope(el);
    }
    // Pass 1.5 : register bz-ref tree-wide BEFORE any binding runs, so a
    // parent's bz-init can read a DESCENDANT ref. bindEl's per-element
    // ORDER only guarantees ref-before-init on the SAME element ; a root
    // bz-init that reads $refs of a child (Slider capturing its track /
    // change carrier) would otherwise see undefined — the child binds
    // later in document order, so the click→snap-to-min path lost its
    // track. Idempotent with HANDLERS.ref, which still owns the disposer
    // for cleanup.
    for (const el of els) {
      const refName = el.getAttribute("bz-ref");
      if (refName) $bz._scopeFor(el).refs[refName] = el;
    }
    // Pass 2 : structural + simple bindings.
    for (const el of els) {
      if (!el.isConnected && el !== root) continue; // removed by a structural directive
      if (el.tagName === "TEMPLATE") {
        if (el.hasAttribute("bz-for")) bindFor(el);
        else if (el.hasAttribute("bz-teleport")) bindTeleport(el);
        continue;
      }
      if (el.hasAttribute("bz-if")) {
        bindIf(el);
        continue;
      }
      bindEl(el);
    }
    // ``autofocus=``: what just ENTERED the page, by whichever road —
    // load, boosted navigation, morph, position patch, ``bz-for`` row,
    // ``bz-if`` mount, teleport. Every one of them ends here.
    if ($bz.helpers && $bz.helpers.autofocusMounted) $bz.helpers.autofocusMounted(els);
  }

  $bz._scan = scan;
  $bz._disposeTree = disposeTree;
  $bz._own = own;
  $bz._sweepDetached = sweepDetached;
  $bz._compile = compile;
  // Evaluate an expression the way a directive would, on demand: the
  // shared tooltip (``tip.js``) reads a trigger's ``disabled`` at
  // HOVER time, with ``$el`` = the trigger and its nearest scope.
  $bz._evaluate = function (el, expr) {
    return evaluate(el, expr, $bz._scopeFor(el));
  };
  $bz._sweepTeleports = sweepTeleports;
  $bz._teleportedFieldsOf = teleportedFieldsOf;
})();


/* scope.js — bz-data component-scoped state, keyed by bz-id.
 *
 * The piece Datastar lacked and Alpine implemented in the wrong place
 * (the DOM). Scope state lives in a runtime-side Map keyed by the
 * bz-id STRING — not in the DOM, not keyed by element : the node may
 * be replaced by idiomorph, the bz-id attribute is what survives.
 * Confirmed by the Phase 0 spike : a morph that re-emits
 * bz-data="{clicks: 0}" does NOT reset an existing scope.
 *
 * On first encounter of <div bz-data="{open: false, helper() {...}}">:
 *   1. evaluate the object literal ($el / $bz are in scope),
 *   2. wrap non-function fields in signals ; functions become helpers
 *      bound to the scope proxy (so `this.open = ...` writes the scope),
 *   3. stamp bz-id if absent (monotonic counter),
 *   4. store the scope in the Map.
 *
 * On re-encounter (same bz-id — typically after a morph) : reuse
 * existing signals, absorb new fields only, refresh helpers, NEVER
 * reset existing values.
 *
 * Nested scopes : a child bz-data reads its parent's vars, and a write
 * to a var an ancestor owns lands in that ancestor.
 * bz-for item scopes are the SAME component scope plus loop vars, so
 * their writes fall through to the parent.
 *
 * Eviction : _sweepScopes() drops scopes whose bz-id no longer exists
 * in the document — called by the bridge after swaps.
 */
(function () {
  "use strict";
  const $bz = (window.$bz = window.$bz || {});

  const scopes = new Map(); // bz-id → scope record
  let idCounter = 0;

  function evalDataLiteral(src, el) {
    return new Function("$el", "$bz", "return (" + src + ")")(el, $bz);
  }

  function makeScope(initialParent) {
    // MUTABLE: the parent is RE-RESOLVED (cf. ``reparent``). The traps
    // read it through the variable, never through a captured copy.
    let parent = initialParent;
    const signals = new Map();
    const helpers = new Map();
    // The last value the SERVER rendered for each signal, as JSON — what
    // ``resyncScopes`` compares a fresh render against.
    const seeds = new Map();
    const refs = parent && parent.refs ? Object.create(parent.refs) : {};

    const proxy = new Proxy(
      {},
      {
        has(_t, key) {
          if (typeof key !== "string") return false;
          if (signals.has(key) || helpers.has(key)) return true;
          return parent ? key in parent.proxy : false;
        },
        get(_t, key) {
          if (key === Symbol.unscopables) return undefined;
          if (signals.has(key)) return signals.get(key).get();
          if (helpers.has(key)) return helpers.get(key).bind(proxy);
          if (parent) return parent.proxy[key];
          return undefined;
        },
        set(_t, key, value) {
          if (signals.has(key)) {
            signals.get(key).set(value);
            return true;
          }
          // A var owned by an ancestor scope is written THERE (walk up
          // via the parent proxy), matching Alpine's nested-x-data
          // semantics — e.g. a nested <bz-calendar>{year,month} whose
          // change handler writes the date picker's parent {open,val}.
          if (parent && key in parent.proxy) {
            parent.proxy[key] = value;
            return true;
          }
          signals.set(key, $bz.signal(value));
          return true;
        },
      },
    );

    return {
      signals: signals,
      helpers: helpers,
      seeds: seeds,
      refs: refs,
      proxy: proxy,
      parentScope() {
        return parent;
      },
      /* Re-attach this scope to its CURRENT parent.
       *
       * A scope is indexed by its ``bz-id`` STRING and therefore
       * survives its node being replaced — that is intended. But its
       * parent is captured ONCE, at creation: without this call, a node
       * reappearing under another parent would keep the old one for life.
       *
       * An ``hx-boost`` navigation does not reload the runtime: on an id
       * shared between pages, the new page would find the old page's
       * scope, whose parent is a node of the PREVIOUS page, and a write
       * would land in a dead scope, in silence. The pickers' ids are
       * unique per page (``panel_calendar``); this call closes the CLASS,
       * whatever the id collision may be.
       *
       * ``refs`` inherits by PROTOTYPE, so re-attaching means moving the
       * prototype too, otherwise the ``$refs`` would go on resolving at
       * the old parent's. */
      reparent(next) {
        if (next === parent) return;
        parent = next;
        Object.setPrototypeOf(
          refs, next && next.refs ? next.refs : Object.prototype,
        );
      },
      absorb(decl) {
        for (const key of Object.keys(decl)) {
          if (key === "_serverSync") continue; // swap-resync marker, not a signal
          const v = decl[key];
          if (typeof v === "function") helpers.set(key, v);
          else if (!signals.has(key)) {
            signals.set(key, $bz.signal(v));
            seeds.set(key, seedOf(v));
          }
        }
      },
    };
  }

  // Root scope : empty, every name falls through to JS globals.
  const rootScope = makeScope(null);

  /* Item scope for bz-for rows : loop vars shadow, everything else
   * (reads AND writes) falls through to the host component scope. */
  function makeItemScope(parent, initialVars) {
    const vars = {};
    for (const key of Object.keys(initialVars)) {
      vars[key] = $bz.signal(initialVars[key]);
    }
    const proxy = new Proxy(
      {},
      {
        has(_t, key) {
          if (typeof key !== "string") return false;
          return key in vars || key in parent.proxy;
        },
        get(_t, key) {
          if (key === Symbol.unscopables) return undefined;
          if (key in vars) return vars[key].get();
          return parent.proxy[key];
        },
        set(_t, key, value) {
          if (key in vars) {
            vars[key].set(value);
            return true;
          }
          parent.proxy[key] = value; // delegate — same component scope
          return true;
        },
      },
    );
    return { vars: vars, proxy: proxy, refs: parent.refs };
  }

  function ensureScope(el) {
    let id = el.getAttribute("bz-id");
    if (!id) {
      id = "bz-" + ++idCounter;
      el.setAttribute("bz-id", id);
    }
    let scope = scopes.get(id);
    if (!scope) {
      scope = makeScope(parentScopeOf(el));
      scopes.set(id, scope);
    } else {
      // Found again, so potentially under ANOTHER parent than at its
      // creation (cf. ``reparent``). On the same page it is the same
      // object and the call does nothing.
      scope.reparent(parentScopeOf(el));
    }
    scope.absorb(evalDataLiteral(el.getAttribute("bz-data"), el));
    return scope;
  }

  /* Single upward walk shared by scopeFor / parentScopeOf : item scopes
   * (bz-for rows) win first, teleported subtrees resolve at their
   * origin template, bz-data hosts materialise their scope. */
  function findScope(node) {
    while (node) {
      if (node._bzItemScope) return node._bzItemScope;
      if (node._bzScopeHost) {
        node = node._bzScopeHost; // teleported subtree → resolve at origin
        continue;
      }
      if (node.hasAttribute && node.hasAttribute("bz-data")) return ensureScope(node);
      node = node.parentElement;
    }
    return rootScope;
  }

  function parentScopeOf(el) {
    return findScope(el.parentElement);
  }

  /* Nearest scope for any element, self included. */
  function scopeFor(el) {
    return findScope(el);
  }

  function sweepScopes() {
    if (!scopes.size) return;
    const live = new Set();
    for (const el of document.querySelectorAll("[bz-id]")) {
      live.add(el.getAttribute("bz-id"));
    }
    for (const id of Array.from(scopes.keys())) {
      if (!live.has(id)) scopes.delete(id);
    }
  }

  /* Swap-boundary value adoption. ``absorb`` deliberately SKIPS keys
   * whose signal already exists, so a morph that re-emits bz-data never
   * resets live client state (an open dropdown, a half-typed query).
   *
   * The rule, once per swap (after the rescan): **the server wins when
   * the value it renders has CHANGED since its last render.** A key the
   * server keeps rendering the same (``isOpen: false``, ``_query: ''``)
   * leaves the client's value alone; a key it renders differently is
   * adopted — the server changed it on purpose. One exception: inside a
   * component whose text field has the focus, nothing moves under the
   * user's fingers. ``_serverSync`` keys are adopted on every swap,
   * whatever the comparison says.
   *
   * Adopting only ``_serverSync`` keys would not do: only a value stamped
   * as a state field earns the marker, so a value the app COMPUTES
   * (filters read from the URL, a selection from a list) would stay
   * client-owned for good. "Clear filters" would leave the status toggles
   * pressed, "Clear selection" the boxes ticked. Binding-mode
   * inputs need nothing here — their value lives in $bz._store, which
   * the patch envelope updates and which never rides a scope signal.
   *
   * A value adopted here is the SERVER's, not a choice: ``_serverWriting``
   * stays up until the effects it wakes have run (they flush in the
   * microtask queued by the first ``set``; clearing in the next one comes
   * after), and ``change_emit_effect`` takes it as a new baseline rather
   * than a ``change``. Without it a select that a morph turns into
   * another one posts the server's value back, to the old action — a
   * 403. */
  function resyncScopes(root) {
    if (!root || root.nodeType !== 1 || !scopes.size) return;
    const typingIn = textEntryWithFocus();
    const hosts = [];
    if (root.hasAttribute("bz-data")) hosts.push(root);
    for (const el of root.querySelectorAll("[bz-data]")) hosts.push(el);
    for (const el of hosts) {
      const id = el.getAttribute("bz-id");
      if (!id) continue;
      const scope = scopes.get(id);
      if (!scope) continue;
      let decl;
      try {
        decl = evalDataLiteral(el.getAttribute("bz-data"), el);
      } catch (e) {
        continue;
      }
      if (!decl) continue;
      const forced = Array.isArray(decl._serverSync) ? decl._serverSync : [];
      const typing = typingIn && el.contains(typingIn);
      for (const key of Object.keys(decl)) {
        const v = decl[key];
        if (key === "_serverSync" || typeof v === "function") continue;
        const sig = scope.signals.get(key);
        if (!sig) continue;
        const fresh = seedOf(v);
        const moved = scope.seeds.get(key) !== fresh;
        scope.seeds.set(key, fresh);
        if (forced.includes(key) || (moved && !typing)) {
          if (!$bz._serverWriting) {
            $bz._serverWriting = true;
            queueMicrotask(() => queueMicrotask(() => { $bz._serverWriting = false; }));
          }
          sig.set(v);
        }
      }
    }
  }

  /* A server value, comparable across renders. */
  function seedOf(v) {
    try {
      return JSON.stringify(v);
    } catch (e) {
      return String(v);
    }
  }

  /* The text field being typed in, if any: its component keeps what the
   * user is typing even when the server's value moved meanwhile. */
  function textEntryWithFocus() {
    const el = document.activeElement;
    if (!el || el === document.body) return null;
    if (el.isContentEditable || el.tagName === "TEXTAREA") return el;
    if (el.tagName !== "INPUT") return null;
    return /^(text|search|email|url|tel|password|number|)$/i.test(el.type || "") ? el : null;
  }

  $bz._scopes = scopes;
  $bz._scopeFor = scopeFor;
  $bz._ensureScope = ensureScope;
  $bz._makeItemScope = makeItemScope;
  $bz._sweepScopes = sweepScopes;
  $bz._resyncScopes = resyncScopes;
})();


/* persistence.js — keeps a ClientState's fields in browser storage.
 *
 * ``persist`` (``state/scopes/client.py::PERSISTS``) says how long a value
 * lasts:
 *
 *   "memory"    → no storage, lost on reload. The default.
 *   "session"   → sessionStorage, key "$bz:<Class>.<key>"
 *   "local"     → localStorage, same key
 *
 * Wiring: index.js calls register(path, mode) for each instance AFTER
 * seeding the envelope defaults — register() then overlays any saved
 * snapshot. Every store write goes through notify(fullPath, value), which
 * saves that one field: tabs sharing localStorage each write only what
 * they changed, so none erases another's field. A tab sees what another
 * wrote at its next load.
 */
(function () {
  "use strict";
  const $bz = (window.$bz = window.$bz || {});

  const storages = new Map(); // instancePath → Storage

  function storageFor(mode) {
    if (mode === "session") return window.sessionStorage;
    if (mode === "local") return window.localStorage;
    return null;
  }

  function storageKey(path) {
    return "$bz:" + path;
  }

  function readSnapshot(storage, path) {
    try {
      const saved = JSON.parse(storage.getItem(storageKey(path)) || "{}");
      if (saved && typeof saved === "object") return saved;
      throw new TypeError("not a field map");
    } catch (e) {
      console.error("bz: corrupt persisted state for", path, e);
      storage.removeItem(storageKey(path));
      return {};
    }
  }

  function register(path, mode) {
    if (storages.has(path)) return;
    const storage = storageFor(mode);
    if (!storage) return;
    storages.set(path, storage);

    // The saved snapshot wins over envelope defaults — the user's browser
    // knows better than the server's defaults.
    const saved = readSnapshot(storage, path);
    for (const field of Object.keys(saved)) {
      $bz._store.set(path + "." + field, saved[field]);
    }
  }

  /* Called by the store on every set. */
  function notify(fullPath, value) {
    const cut = fullPath.lastIndexOf(".");
    const path = fullPath.slice(0, cut);
    const storage = storages.get(path);
    if (!storage) return;
    const saved = readSnapshot(storage, path);
    saved[fullPath.slice(cut + 1)] = value;
    storage.setItem(storageKey(path), JSON.stringify(saved));
  }

  $bz._persistence = { register: register, notify: notify };
})();


/* bridge.js — HTMX glue : signal snapshot out, <bz-patch> in.
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
  const PATCH_TAG = "bz-patch";

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
  // append(key, v))`. Two consequences:
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
  // as the catalogue's hidden carriers (`toggle_group`, `select`,
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
      // "delta" mode would be wrong, not merely useless — the full reason
      // is in ``ClientState``'s docstring (bretzel/state/scopes/client.py
      // § "There is NO delta mode"). Do not introduce one without reading
      // that paragraph first.
      const cfg = config[path] || {};
      if (cfg.send_to_server === false) continue;
      for (const field of Object.keys(fields)) {
        // A field with no value says nothing — its signal was created
        // by a read (`get` auto-creates) and never seeded. Sent, it
        // would put the WORD "undefined" in the body: stored as is in a
        // text field, refused by a bool one. Left out, the server keeps
        // its own value, as hydration only writes the fields present.
        if (fields[field] === undefined) continue;
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
  /* An app under a ``base_path`` (``core/base_path.py``) says so on
   * ``<html>``; for one at the root, ``BASE`` is empty and all this is
   * inert. */
  const BASE = document.documentElement.getAttribute("data-bz-base") || "";
  const ACTION_PREFIX = BASE + "/_bretzel/action/";

  /* The address bar's path as the app knows it: what ``current_path`` holds
   * and what the menu entries are compared with. */
  $bz._localPath = function () {
    const p = window.location.pathname;
    return BASE && (p === BASE || p.startsWith(BASE + "/")) ? p.slice(BASE.length) || "/" : p;
  };

  /* The THIRD key, reserved: "a navigation is in flight". The shell's
   * bar (``render/shell.nav_progress_html``) is only a ``bz-show`` on
   * it, so it has no mechanism of its own — it is the same registry, the
   * same timing, the same disarm.
   *
   * ``detail.boosted`` covers the links boosted by ``hx-boost`` (set at
   * the document level by the shell), menus included; ``hx-push-url`` an
   * author's own explicit ``hx-get``. */
  const NAV_KEY = "@nav";

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

  /* Whether a link is boosted: the link's own ``hx-boost``, else the
   * page's. htmx reads ``hx-boost`` by INHERITANCE, so any ancestor that
   * sets one speaks for the links it holds — and ``ui.form`` sets
   * ``hx-boost="false"`` for its OWN submit (``Form.render``): its
   * cancel link and its breadcrumb would reload the whole document,
   * sidebar included. A link with no
   * ``hx-boost`` of its own under a page that boosts (``render/shell.py``,
   * or a teleported panel that ``inheritHtmx`` gave the page's) gets its
   * own ``hx-boost="true"``, written before htmx reads it
   * (``beforeProcessNode``). An opt-out stays on the link itself: a
   * ``<a download>`` gets ``hx-boost="false"`` here. Where the boosted link
   * goes is ``boostedTarget``'s, below — same rule, the page's.
   * Registered at the module's LOAD: htmx processes the document at
   * ``DOMContentLoaded``, before ``boot()`` wires the bridge. Gate:
   * ``tests/runtime_js/test_a_link_is_boosted_wherever_it_sits.py``. */
  document.addEventListener("htmx:beforeProcessNode", function (e) {
    const a = e.target;
    if (a.tagName !== "A" || a.hasAttribute("hx-boost")) return;
    // A link to ANOTHER origin — another site, or another port of the same
    // host — is a document load, never boosted: htmx refuses a request off
    // its origin (``selfRequestsOnly``) and the click would do NOTHING, in
    // silence. Gate: same test file, ``test_a_link_to_another_origin``.
    //
    // Same thing for a page of this origin OUTSIDE this app's ``base_path``:
    // a sibling app, whose document cannot go in this app's outlet.
    //
    // And a ``<a download>``: htmx would swap the file into the page. A
    // ``@download`` route needs no attribute, it redirects htmx itself
    // (``server/routing/downloads.py``); this is for any other file route.
    const outside = BASE && a.pathname !== BASE && !a.pathname.startsWith(BASE + "/");
    const leaves = a.getAttribute("href") && (a.origin !== window.location.origin || outside);
    if (leaves || a.hasAttribute("download")) {
      a.setAttribute("hx-boost", "false");
      return;
    }
    if (a.closest('[hx-boost="true"]')) a.setAttribute("hx-boost", "true");
  });

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

  /* The automatic busy state (``loading=`` on the Python side): a
   * trigger whose request is still unanswered after ``BUSY_AFTER_MS``
   * shows it on its own — the ``bz-busy`` class for the theme's CSS
   * (``theme/css.py``, ``_BUSY``) and ``aria-busy`` for assistive tech.
   * Under the delay, nothing: a fast answer does not flash.
   *
   * A zone the runtime asks again (``refetchZone``: another tab's change,
   * a row refresh) is the source of its own request, so it gets the same
   * state. Not for a navigation — the shell's bar shows it —, nor for
   * polling, nor a hidden carrier, nor under ``loading=False``
   * (``data-bz-busy="off"`` on the element or an ancestor). A counter,
   * like the witness above: two requests from one element, and the first
   * answer must not clear the second. */
  const BUSY_AFTER_MS = 200;
  const BUSY = new WeakMap();

  function busyTarget(elt, detail) {
    if (!elt || elt.nodeType !== 1 || elt.hidden) return null;
    if ((detail && detail.boosted) || elt.getAttribute("hx-push-url") === "true") return null;
    if (/\bevery\b/.test(elt.getAttribute("hx-trigger") || "")) return null;
    if (elt.closest('[data-bz-busy="off"]')) return null;
    return elt;
  }

  function armBusy(elt) {
    let state = BUSY.get(elt);
    if (!state) {
      state = { count: 0, timer: 0, shown: false };
      BUSY.set(elt, state);
    }
    if (++state.count > 1) return;
    state.timer = setTimeout(function () {
      state.timer = 0;
      if (!elt.isConnected) return;
      elt.classList.add("bz-busy");
      elt.setAttribute("aria-busy", "true");
      state.shown = true;
    }, BUSY_AFTER_MS);
  }

  function disarmBusy(elt) {
    const state = BUSY.get(elt);
    if (!state || state.count === 0 || --state.count > 0) return;
    clearTimeout(state.timer);
    // A morph may already have dropped both (the server never renders
    // them): only what this state set is taken back.
    if (state.shown && elt.classList.contains("bz-busy")) {
      elt.classList.remove("bz-busy");
      elt.removeAttribute("aria-busy");
    }
    BUSY.delete(elt);
  }

  //: Attributes the client sets on an element until an answer redraws it
  //: (``dnd.js``, ``scheduler.js``): the server never renders them,
  //: so a morph erases them, and their survival says nobody answered. A
  //: list patch keeps an element WITHOUT morphing it — but it does answer
  //: for every child it places, so it erases them too (``applyList``).
  $bz._witnesses = $bz._witnesses || new Set();

  /* ── Where the page is scrolled, across navigations ──────────────────
   *
   * The browser's rule, Next.js's and SvelteKit's: a link followed opens
   * the page at the TOP (at its anchor for ``/page#section``); the
   * browser's back / forward gives a page back WHERE IT WAS LEFT;
   * anything that is not a navigation (an action redrawing a zone, a
   * tab, the sidebar's own scroll) leaves the scroll alone.
   *
   * htmx only knows the window, and most apps do not scroll it: the
   * document is frozen and a ``ui.pane`` scrolls around the outlet
   * (``ui.viewport``). That pane SURVIVES a navigation — only the outlet
   * is swapped — so left alone it keeps the page left's ``scrollTop``: a
   * link followed from the bottom of a page lands at the bottom of the
   * next, and Back gives the page back at an arbitrary height.
   *
   * What scrolls « the page »: the window, and every scroll container
   * that holds the outlet (``scrollersOf``) — both models, no flag.
   * Elements INSIDE the page keep their own (a list, a pane of the page).
   *
   * Each history entry carries a key in ``history.state``; its positions
   * live in memory under that key, taken when the entry is LEFT. htmx
   * rewrites the state to ``{htmx: true}`` before a push
   * (``saveCurrentPageToHistory``), so the key is written back right
   * after.
   *
   * Back / forward come back LIKE A LINK: the outlet is fetched and
   * swapped, the shell stays — its sidebar, its scroll — and the
   * positions are set back once the swap is in. htmx's own restore
   * would render the whole ``<body>`` again (``historyCacheSize: 0``,
   * ``render/shell.py``), its ``<script>`` tags included: htmx and this
   * runtime would boot a SECOND time in the same window at each Back,
   * every listener doubled. A page with no outlet is reloaded: one boot,
   * always.
   *
   * ``scrollIntoViewOnBoost`` is turned off: htmx scrolls a boosted
   * link's target into view — the outlet's top, under the pane's
   * padding, and down a scrolling document — instead of the
   * page's top. Gate:
   * ``tests/runtime_js/test_a_navigation_lands_at_the_top.py``. */
  const SCROLL_KEY = "bzScroll";
  const SCROLL_KEPT = 50;
  const scrollPositions = new Map();
  let scrollEntry = null;
  //: The navigation swap awaited: its target, and the positions to set
  //: back (``null``: the top, or the anchor).
  let scrollPending = null;

  function newScrollKey() {
    return Date.now().toString(36) + Math.random().toString(36).slice(2, 8);
  }

  function stampScrollEntry(key) {
    scrollEntry = key;
    const state = Object.assign({}, window.history.state);
    state[SCROLL_KEY] = key;
    try {
      window.history.replaceState(state, "");
    } catch (e) {
      // A refused state write must not stop a navigation: the page just
      // will not come back to its position.
    }
  }

  /* ``from`` and its ancestors that scroll vertically, outermost first. */
  function scrollersOf(from) {
    const out = [];
    for (let el = from; el && el !== document.body; el = el.parentElement) {
      if (/(auto|scroll)/.test(getComputedStyle(el).overflowY)) out.unshift(el);
    }
    return out;
  }

  /* The page's scrollers: those of the DEEPEST outlet, which hold the
   * outer ones' too (nested layouts). */
  function pageScrollers() {
    const outlets = document.querySelectorAll("[data-bz-outlet]");
    return scrollersOf(outlets[outlets.length - 1]);
  }

  function rememberScroll() {
    if (!scrollEntry) return;
    scrollPositions.delete(scrollEntry);
    scrollPositions.set(scrollEntry, {
      win: window.scrollY,
      panes: pageScrollers().map(function (el) { return el.scrollTop; }),
    });
    if (scrollPositions.size > SCROLL_KEPT) {
      scrollPositions.delete(scrollPositions.keys().next().value);
    }
  }

  /* Positions given back. The page just swapped may not have its full
   * height yet (its icons draw a moment later): a position past the end
   * is cut short — 5 530 px for 5 551 on the playground's /dropdown. So
   * it is set again at each frame, for half a second at most, until it
   * holds — and not once the user moves (wheel, touch, key, pointer):
   * the page is theirs again. */
  const SCROLL_TRIES = 30;
  const USER_MOVES = ["wheel", "touchstart", "keydown", "pointerdown"];

  function setScrollBack(pos) {
    const panes = pageScrollers();
    let tries = SCROLL_TRIES;
    let moved = false;
    function stop() { moved = true; }
    USER_MOVES.forEach(function (name) {
      window.addEventListener(name, stop, { capture: true, passive: true, once: true });
    });
    function done() {
      USER_MOVES.forEach(function (name) {
        window.removeEventListener(name, stop, { capture: true });
      });
    }
    (function apply() {
      if (moved) return done();
      window.scrollTo(0, pos.win);
      let held = Math.abs(window.scrollY - pos.win) < 1;
      panes.forEach(function (el, i) {
        el.scrollTop = pos.panes[i] || 0;
        held = held && Math.abs(el.scrollTop - (pos.panes[i] || 0)) < 1;
      });
      if (held || --tries <= 0) return done();
      requestAnimationFrame(apply);
    })();
  }

  /* The outlet a navigation swaps, and how: the target and the swap
   * declared next to ``hx-boost="true"`` on the page's envelope
   * (``render/shell.py``) — the only place the framework boosts. */
  function pageOutlet() {
    const decl = document.querySelector('[data-bz-page-id][hx-boost="true"]');
    const sel = decl && decl.getAttribute("hx-target");
    const target = sel && document.querySelector(sel);
    return target ? { target: target, swap: decl.getAttribute("hx-swap") } : null;
  }

  function wireScroll() {
    if (window.htmx) window.htmx.config.scrollIntoViewOnBoost = false;
    const state = window.history.state;
    stampScrollEntry((state && state[SCROLL_KEY]) || newScrollKey());

    // A push: the page left keeps its positions, then its key (htmx has
    // just rewritten its state). Only a swap INTO an outlet is a
    // navigation; a zone that pushes its address (a filter) is not.
    document.body.addEventListener("htmx:beforeHistoryUpdate", function (e) {
      const history = e.detail && e.detail.history;
      if (!history || history.type !== "push") return;
      rememberScroll();
      stampScrollEntry(scrollEntry);
      const t = e.detail.target;
      if (t && t.nodeType === 1 && (t.matches("[data-bz-outlet]")
          || t.querySelector("[data-bz-outlet]"))) {
        scrollPending = { target: t, pos: null };
      }
    });
    document.body.addEventListener("htmx:pushedIntoHistory", function () {
      stampScrollEntry(newScrollKey());
    });

    // The navigation's swap is in: the positions left there, else the
    // top — or the anchor (htmx scrolls to it again at settle: same
    // place).
    document.body.addEventListener("htmx:afterSwap", function (e) {
      const pending = scrollPending;
      if (!pending || e.detail.target !== pending.target) return;
      scrollPending = null;
      if (pending.pos) return setScrollBack(pending.pos);
      window.scrollTo(0, 0);
      scrollersOf(pending.target).forEach(function (el) { el.scrollTop = 0; });
      const id = decodeURIComponent(window.location.hash.slice(1));
      const anchor = id && document.getElementById(id);
      if (anchor) anchor.scrollIntoView({ block: "start" });
    });

    // Back / forward. The DOM is still the page left, so its positions
    // are read here. htmx keeps the entries that are not its own
    // (``#anchor`` jumps, handled by the browser). htmx sets
    // ``onpopstate`` at ``DOMContentLoaded`` — AFTER this boot, which
    // runs as soon as the deferred runtime is evaluated (``index.js``):
    // taken then (or at ``load``, if this boot came later), never before.
    let htmxPopstate = null;
    function takePopstate() {
      if (window.onpopstate === onPopstate) return;
      htmxPopstate = window.onpopstate;
      window.onpopstate = onPopstate;
    }
    if (document.readyState === "complete") takePopstate();
    else {
      document.addEventListener("DOMContentLoaded", takePopstate);
      window.addEventListener("load", takePopstate);
    }
    function onPopstate(e) {
      rememberScroll();
      const key = e.state && e.state[SCROLL_KEY];
      if (key) scrollEntry = key;
      else stampScrollEntry(newScrollKey());
      if (!(e.state && e.state.htmx)) {
        if (htmxPopstate) htmxPopstate.call(window, e);
        return;
      }
      const outlet = pageOutlet();
      if (!outlet || !window.htmx) {
        window.location.reload();
        return;
      }
      scrollPending = { target: outlet.target, pos: scrollPositions.get(scrollEntry) || null };
      window.htmx.ajax("GET", window.location.pathname + window.location.search, {
        source: outlet.target,
        target: outlet.target,
        swap: outlet.swap || "innerHTML",
      });
    }
  }

  $bz._wireBridge = function () {
    wireScroll();

    /* One field into a request body, as a form submit would write it. */
    function appendField(data, el) {
      const type = (el.type || "").toLowerCase();
      if (/^(submit|button|reset|image)$/.test(type)) return;
      if ((type === "checkbox" || type === "radio") && !el.checked) return;
      if (type === "file") {
        for (const f of el.files) data.append(el.name, f);
      } else if (el.tagName === "SELECT" && el.multiple) {
        for (const o of el.selectedOptions) data.append(el.name, o.value);
      } else {
        data.append(el.name, el.value);
      }
    }

    /* Where a boosted link goes: the page's outlet (``pageOutlet``),
     * whatever the link's ancestors say. htmx resolves a link's target
     * by INHERITANCE, and a component carrying an action sets
     * ``hx-target="#bz-sink"`` on its element (``events.py``): a link
     * inside it — a card ``on_click``, a dialog's ``on_close`` — would go
     * to the hidden sink, the address changing and the page not.
     * ``configRequest`` names the outlet to
     * the server, ``beforeSwap`` swaps it there: htmx reads the target
     * back from neither earlier. Gate:
     * ``tests/runtime_js/test_a_link_is_boosted_wherever_it_sits.py``. */
    function boostedTarget(detail) {
      if (!detail.boosted) return null;
      const outlet = pageOutlet();
      return outlet && outlet.target !== detail.target ? outlet : null;
    }

    document.body.addEventListener("htmx:beforeSwap", function (e) {
      const config = e.detail.requestConfig;
      const to = config && config._bzBoosted;
      if (!to || !to.target.isConnected) return;
      e.detail.target = to.target;
      if (to.swap) e.detail.swapOverride = to.swap;
    });

    document.body.addEventListener("htmx:configRequest", function (e) {
      // An inert control posts NOTHING. It is inertness's third guard
      // (the other two — `bz-on:` handlers and native navigation — live
      // in directives.js, which owns the rule) and it is here because
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
      // Nothing fires on a resize, only on a navigation the user asked
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
        typeof window.$bzScreenSync === "function" &&
        !window.$bzScreenSync()
      ) {
        e.preventDefault();
        window.location.assign(
          e.detail.path || e.detail.elt.getAttribute("href"),
        );
        return;
      }
      const boosted = boostedTarget(e.detail);
      if (boosted) {
        e.detail._bzBoosted = boosted;
        e.detail.headers["HX-Target"] = boosted.target.id;
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
      // them, and we throw them away for want of a target.
      //
      // On action POSTs, and on a navigation into an outlet: there, the
      // zones OUTSIDE it — the shell's — that read a page state are
      // redrawn for the page arrived at (``_shell_zones`` in
      // ``render/pipeline.py``). The zones inside the outlet are not listed:
      // the page brings them. Any other GET — a zone's own refetch, the
      // SSE one — sends nothing.
      //
      // We read the DOM at the instant of the request, not a list the
      // server would have given us at render: an OOB swap may have
      // introduced a zone since, and a frozen list would condemn it
      // never to refresh again.
      const verb = String(e.detail.verb).toLowerCase();
      const into = boosted ? boosted.target : e.detail.target;
      const outlet =
        verb === "get" && into && into.nodeType === 1 && into.hasAttribute("data-bz-outlet")
          ? into
          : null;
      if (verb === "post" || outlet) {
        const zones = document.querySelectorAll("[data-bz-zone]");
        if (zones.length) {
          const ids = [];
          for (const z of zones) {
            if (outlet && outlet.contains(z)) continue;
            // ``id`` alone, or ``id:fingerprint`` when we know what
            // the zone carries: the server uses it to KEEP QUIET about a
            // zone whose fresh render would be identical. The
            // fingerprint comes from IT, it is never computed here — an
            // absent or stale fingerprint can therefore only make the
            // zone be re-sent, never wrongly suppressed.
            ids.push($bz._zoneEntry(z));
          }
          if (ids.length) e.detail.headers["X-Bretzel-Zones"] = ids.join(",");
        }
      }
      // A form's fields that ``bz-teleport`` carried out of it (cf.
      // ``teleportedFieldsOf``): htmx built the body from
      // ``form.elements`` and never saw them. ``parameters`` is a view
      // over ``formData``, which htmx reads back after this event.
      const elt = e.detail.elt;
      const form =
        elt && elt.nodeType === 1 &&
        (elt.tagName === "FORM"
          ? elt
          : String(e.detail.verb).toLowerCase() !== "get" && elt.closest("form"));
      if (form && e.detail.formData && $bz._teleportedFieldsOf) {
        for (const el of $bz._teleportedFieldsOf(form)) appendField(e.detail.formData, el);
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
      // Letting it leave costs. The server refuses
      // any invalid signature with an `_error: reload`, which
      // `handleError` executes — so an already obsolete request RELOADS
      // THE WHOLE PAGE: an autoplay ticks while a flip re-renders the
      // panel, the node disappears, the POST leaves bare, 403, reload.
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

    /* Changes to elements with no ``id`` (``render/zone_diff.at_position``):
     * ``<bz-at zone anchor path shape>`` holds the new element in a
     * template. Walk from the anchor by element position, skipping what
     * the runtime inserted itself (``data-bz-row``: ``bz-for`` rows,
     * ``bz-if`` mounts), check each level's shape, morph. A walk that
     * does not land — the DOM moved under us — forgets the zone's
     * fingerprint (the base check of ``_adoptZoneHashes`` then keeps it
     * forgotten) and asks a subscribed zone again at once; any other zone
     * ships whole at the next exchange. */
    // Mirror of ``zone_diff.shape_of``: djb2 over the children's tags.
    function shapeOf(kids) {
      let h = 5381;
      const text = kids.map((k) => k.localName).join(",");
      for (let i = 0; i < text.length; i++) h = (((h << 5) + h) + text.charCodeAt(i)) >>> 0;
      return h.toString(16);
    }
    function settle(node) {
      if (window.htmx) window.htmx.process(node);
      $bz._scan(node);
      // Adopt server-authoritative signals (``_serverSync`` keys) from
      // the freshly-morphed bz-data — runs AFTER the rescan so the
      // bz-attr effects are live when the value signal changes.
      $bz._resyncScopes(node);
    }
    /* A walk that did not land: forget the zone's fingerprint and ask a
     * subscribed zone again; any other zone ships whole next time. */
    function lost(tag) {
      // Said out loud: a patch refused for a node inserted by hand
      // without ``data-bz-row`` would otherwise fail in silence. The zone
      // is still redrawn whole.
      console.warn("bz: a patch of zone " + tag.getAttribute("zone") + " found the page "
        + "changed under it (a node added outside the server's render? mark it "
        + "data-bz-row) — redrawing the zone whole");
      const host = document.querySelector('[data-bz-zone][bz-id="' + tag.getAttribute("zone") + '"]');
      if (!host) return;
      host.removeAttribute("data-bz-h");
      const url = host.getAttribute("data-bz-subscribe-url");
      if (url && $bz._refetchZone) $bz._refetchZone(host, url);
    }
    /* A parent whose list of children changed, nothing else
     * (``zone_diff.ListPatch``): ``#row-2`` keeps the child with that
     * id, wherever it is now (a drag and drop moved it already), ``k3``
     * keeps the old child 3, ``m3`` keeps it and morphs it into the next
     * template, ``n`` inserts the next template. A rank counts the
     * children without id only. An id the parent does not hold is taken
     * where the browser holds it — another list of the zone, or one this
     * run just removed (``orphans``) — moved here and morphed: a card
     * dragged to another column keeps its element. The old children not
     * kept go; the kept ones are MOVED, never rebuilt — their state and
     * their listeners stay. A rank needs the parent to hold ``count``
     * children without id first, or nothing is touched. */
    /* An id a patch may name — the server's rule exactly
     * (``protocol.ADDRESSABLE_ID``). Any other element, ``id="137"``
     * included, is ranked by position: counted otherwise, a list holding
     * one would never match the count the server sent. */
    const ADDRESSABLE = /^-?[A-Za-z_\u00a0-\uffff][\w\u00a0-\uffff-]*$/;
    const named = (el) => !!el.id && ADDRESSABLE.test(el.id);
    function applyList(parent, tag, fresh, orphans) {
      const kids = counted(parent);
      const ranked = kids.filter((c) => !named(c));
      const text = tag.getAttribute("list");
      const ops = text ? text.split(" ") : [];
      if (ops.some((op) => op[0] === "k" || op[0] === "m")
          && ranked.length !== Number(tag.getAttribute("count"))) return false;
      const byId = (id) => {
        const el = kids.find((kid) => kid.id === id) || orphans.get(id) || document.getElementById(id);
        return el && !el.contains(parent) ? el : null;
      };
      const next = [];
      const morphs = [];
      const added = [];
      let f = 0;
      for (const op of ops) {
        if (op === "n") {
          const tpl = fresh[f++];
          const moved = named(tpl) ? byId(tpl.id) : null;
          if (moved) {
            morphs.push([moved, tpl]);
            next.push(moved);
          } else {
            const node = document.importNode(tpl, true);
            next.push(node);
            added.push(node);
          }
          continue;
        }
        const old = op[0] === "#" ? byId(op.slice(1)) : ranked[Number(op.slice(1))];
        if (!old) return false;
        if (op[0] === "m") morphs.push([old, fresh[f++]]);
        next.push(old);
      }
      const keep = new Set(next);
      for (const node of next) for (const name of $bz._witnesses) node.removeAttribute(name);
      for (const kid of kids) {
        if (keep.has(kid)) continue;
        kid.remove();
        if (kid.id) orphans.set(kid.id, kid);
      }
      let prev = null;
      for (const node of next) {
        const want = prev ? prev.nextSibling : parent.firstChild;
        if (node !== want) parent.insertBefore(node, want);
        prev = node;
      }
      for (const [old, tpl] of morphs) morphInto(old, tpl);
      for (const node of added) settle(node);
      return true;
    }
    /* The children the server counts: not what the runtime inserted
     * itself (``bz-for`` rows, ``bz-if`` mounts carry ``data-bz-row``). */
    function counted(el) {
      return Array.from(el.children).filter((c) => !c.hasAttribute("data-bz-row"));
    }
    function morphInto(el, tpl) {
      const live = window.Idiomorph.morph(el, tpl, { morphStyle: "outerHTML" })
        .find((n) => n.nodeType === 1);
      if (live) settle(live);
    }
    /* Where a ``<bz-at>`` points: its anchor, then each step of its path,
     * as long as every level has the shape the server saw. An empty path
     * is the anchor itself (``"".split(".")`` would be one step). */
    function target(tag) {
      let el = document.getElementById(tag.getAttribute("anchor"));
      const shapes = (tag.getAttribute("shape") || "").split(".");
      const path = tag.getAttribute("path") || "";
      const steps = path ? path.split(".") : [];
      for (let i = 0; i < steps.length && el; i++) {
        const kids = counted(el);
        el = shapeOf(kids) === shapes[i] ? kids[Number(steps[i])] : null;
      }
      return el;
    }
    /* Each ``<bz-at>`` of the sink (``zone_diff.ship``): a list patch, or
     * one element morphed where it is. */
    function applyPositionPatches() {
      const sink = document.getElementById("bz-sink");
      if (!sink) return;
      const orphans = new Map();   // removed by a list this run: another may take them
      for (const tag of sink.querySelectorAll("bz-at")) {
        tag.remove();
        const el = target(tag);
        const fresh = Array.from(tag.children)
          .filter((c) => c.tagName === "TEMPLATE")
          .map((c) => c.content.firstElementChild);
        if (!el || !window.Idiomorph) lost(tag);
        else if (tag.hasAttribute("list")) {
          if (!applyList(el, tag, fresh, orphans)) lost(tag);
        } else if (fresh[0] && el.tagName === fresh[0].tagName) morphInto(el, fresh[0]);
        else lost(tag);
      }
    }

    /* Replace, do not morph, an element marked data-bz-replace.
     * idiomorph pairs the children of a node one by one, looking for the
     * best match among siblings that carry no id — quadratic on a large
     * blob. A highlighted ``ui.code`` is thousands of ``<span>``: the morph
     * would freeze the page for seconds. Such a blob holds no client
     * state, so its content is swapped whole and its attributes synced;
     * returning ``false`` tells idiomorph to leave the node alone after
     * that. Hooked on the DEFAULTS, so both paths reach
     * it: htmx's morph extension and ``applyPositionPatches`` above. */
    /* A node RECYCLED into an identified element is a new node: no
     * transition. idiomorph's soft match takes an old element WITHOUT
     * id for any new element of the same tag, identified or not — a
     * painted ``hstack`` can become a closed dialog's backdrop, and its
     * opacity animate from 1 to 0: a black veil over the screen. A node
     * CREATED has no value before, so it never transitions; one recycled
     * must not either.
     * The node and its subtree take their values with ``transition:
     * none``, then get their transitions back in a microtask, once the
     * new values are computed. A node morphed into ITSELF (same id) keeps
     * its transitions: that is how a panel closes, animated.
     * Gate: tests/runtime_js/test_a_recycled_node_does_not_animate.py. */
    const rebirths = new WeakSet();
    const reborn = [];
    function settleReborn() {
      // Computing the style now fixes the new values without transition.
      document.documentElement.getBoundingClientRect();
      for (const [el, was] of reborn.splice(0)) {
        if (was) el.style.transition = was;
        else el.style.removeProperty("transition");
        if (el.getAttribute("style") === "") el.removeAttribute("style");
      }
    }

    if (window.Idiomorph && window.Idiomorph.defaults) {
      const callbacks = window.Idiomorph.defaults.callbacks;
      const priorAfter = callbacks.afterNodeMorphed;
      callbacks.afterNodeMorphed = function (node) {
        if (rebirths.has(node)) {
          rebirths.delete(node);
          if (!reborn.length) queueMicrotask(settleReborn);
          for (const el of [node, ...node.querySelectorAll("*")]) {
            if (!el.style) continue;
            reborn.push([el, el.style.transition]);
            el.style.transition = "none";
          }
        }
        return priorAfter.apply(this, arguments);
      };
      const prior = callbacks.beforeNodeMorphed;
      callbacks.beforeNodeMorphed = function (old, fresh) {
        if (old.nodeType === 1 && fresh.nodeType === 1 && fresh.id && !old.id) {
          rebirths.add(old);
        }
        if (old.nodeType === 1 && fresh.nodeType === 1
            && old.hasAttribute("data-bz-replace")) {
          if (old.outerHTML !== fresh.outerHTML) {
            Array.from(old.attributes).forEach(function (a) {
              if (!fresh.hasAttribute(a.name)) old.removeAttribute(a.name);
            });
            Array.from(fresh.attributes).forEach(function (a) {
              if (old.getAttribute(a.name) !== a.value) old.setAttribute(a.name, a.value);
            });
            old.innerHTML = fresh.innerHTML;
          }
          return false;
        }
        return prior.apply(this, arguments);
      };
    }

    function afterSwap(e) {
      applyPatchTags();
      applyPositionPatches();
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
        $bz._resyncScopes(target);
      }
      $bz._sweepScopes();
      // The nodes this swap removed give back their effects, and what
      // their bz-init took outside them (document / window listeners).
      if ($bz._sweepDetached) $bz._sweepDetached();
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

    /* A ``redirect()`` that keeps the layout answers ``HX-Location``:
     * htmx fetches the new page into the outlet and returns BEFORE
     * swapping this response. Its out-of-band zones include the
     * layout's, which that navigation never redraws — left alone, they
     * keep their old version while ``_adoptZoneHashes`` takes the
     * fingerprint of the new one, and the next patch misses. Land them
     * first (``swapStyle: "none"`` keeps only the out-of-band parts);
     * the outlet's are replaced by the navigation anyway. */
    document.body.addEventListener("htmx:beforeOnLoad", function (e) {
      const xhr = e.detail && e.detail.xhr;
      if (!xhr || !xhr.getResponseHeader || !xhr.getResponseHeader("HX-Location")) return;
      if (xhr.responseText && window.htmx) {
        window.htmx.swap(document.body, xhr.responseText, { swapStyle: "none" });
      }
    });

    /* The witness's life cycle. ``htmx:afterRequest`` is the ONLY
     * disarm: htmx emits it in every exit case — success, 4xx/5xx,
     * network error, timeout, abort — so also listening to
     * ``sendError``/``timeout`` would decrement the counter twice and
     * would extinguish a second request still in flight on the same
     * key. */
    document.body.addEventListener("htmx:beforeRequest", function (e) {
      pendingKeys(e.detail.elt, e.detail).forEach(armPending);
      const busy = busyTarget(e.detail.elt, e.detail);
      if (busy) armBusy(busy);
    });

    /* The fingerprint of a zone lives ON its element (``data-bz-h``),
     * stamped by the server whenever it renders the zone whole; a
     * response that only patched or silenced the zone sends it in
     * ``X-Bretzel-Zone-Hashes``, with its base in ``X-Bretzel-Zone-Bases``.
     * Holding another base, we forget the fingerprint: the next exchange
     * ships the zone whole. Why: ``render/zone_diff.py``, "Crossed
     * responses".
     *
     * What that version READ (``data-bz-r``) rides along as a third part
     * — ``id:fingerprint:reads`` — so the server redraws the zone only
     * when a field THIS version read has changed. Absent, the server
     * falls back on what it learned itself: never wrongly silenced. */
    $bz._zoneEntry = function (zone) {
      const zid = zone.getAttribute("bz-id");
      const vu = zone.getAttribute("data-bz-h") || "";
      const lu = zone.getAttribute("data-bz-r");
      if (lu !== null) return zid + ":" + vu + ":" + lu;
      return vu ? zid + ":" + vu : zid;
    };
    function pairsOf(header) {
      const out = {};
      if (!header) return out;
      for (const morceau of header.split(",")) {
        const coupe = morceau.indexOf(":");
        if (coupe > 0) out[morceau.slice(0, coupe)] = morceau.slice(coupe + 1);
      }
      return out;
    }
    $bz._adoptZoneHashes = function (xhr) {
      const hashes = pairsOf(xhr.getResponseHeader("X-Bretzel-Zone-Hashes"));
      const bases = pairsOf(xhr.getResponseHeader("X-Bretzel-Zone-Bases"));
      for (const zid of Object.keys(hashes)) {
        const zone = document.querySelector('[data-bz-zone][bz-id="' + zid + '"]');
        if (!zone) continue;
        if (zid in bases && zone.getAttribute("data-bz-h") !== bases[zid]) {
          zone.removeAttribute("data-bz-h");
        } else {
          zone.setAttribute("data-bz-h", hashes[zid]);
        }
      }
    };
    document.body.addEventListener("htmx:afterRequest", function (e) {
      pendingKeys(e.detail.elt, e.detail).forEach(disarmPending);
      if (e.detail.elt && e.detail.elt.nodeType === 1) disarmBusy(e.detail.elt);

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

      /* A navigation starts a new page, with a fresh page state and its
       * own id (``render_context.py``). Adopt it: the actions that follow
       * must speak for the page SHOWN, not the one left — otherwise they
       * would find the old page's state again, the very defect the new
       * id closes. */
      const pageId = xhr.getResponseHeader("X-Bretzel-Page-ID");
      if (pageId) $bz._pageId = pageId;

      $bz._adoptZoneHashes(xhr);
    });

    /* A partial response has no <head>: its page title arrives in
     * ``HX-Trigger`` (``render/pipeline.py``), after every partial
     * navigation — a boosted link, a sidebar item, a ``redirect()``.
     * htmx dispatches a string value as ``detail.value``. */
    document.body.addEventListener("bretzel:title", function (e) {
      const title = e.detail && e.detail.value;
      if (typeof title === "string") document.title = title;
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


/* helpers.js — shared helpers for overlay-class components.
 *
 * Exposed via window.$bz.helpers, consumed by Dialog / Drawer /
 * Popover / Dropdown / Tooltip component code. Trimmed on purpose —
 * we inline the 6 placements we actually use instead of shipping a
 * floating-ui clone (V2's 09_floating.js was 257 LOC ; this is the
 * subset Bretzel components consume).
 *
 *   focusTrap(el)              trap Tab/Shift+Tab inside el ; returns
 *                              dispose (restores the previous focus)
 *   focusIn(id, sels)          focus a component's FOCUS_TARGET (.focus())
 *   blurIn(id)                 blur what has the focus inside it (.blur())
 *   autofocusMounted(els)      autofocus= on entering the page ($bz._scan)
 *   autofocusOpen(panel)       autofocus= when an anchored overlay opens
 *   escapeKey(handler, el?)    Escape, the deepest overlay first ; returns unsubscribe
 *   scrollLock()               body scroll lock w/ scrollbar compensation ;
 *                              returns unlock
 *   floating(anchor, el, opts) position el relative to anchor
 *                              (fixed-position, viewport-aware flip) ;
 *                              returns dispose (stops tracking)
 */
(function () {
  "use strict";
  const $bz = (window.$bz = window.$bz || {});

  // ``directives.js`` owns the list (it loads first).
  const FOCUSABLE = $bz._FOCUSABLE;

  /* A focusable that is not displayed takes no focus, in silence. */
  function shownFocusables(el) {
    return Array.from(el.querySelectorAll(FOCUSABLE)).filter(function (n) {
      return n.offsetParent !== null;
    });
  }

  function focusTrap(el) {
    const previous = document.activeElement;
    function onKeydown(e) {
      if (e.key !== "Tab") return;
      const focusable = shownFocusables(el);
      if (!focusable.length) return;
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (e.shiftKey && document.activeElement === first) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault();
        first.focus();
      }
    }
    el.addEventListener("keydown", onKeydown);
    /* The initial focus RETRIES frame by frame until it takes.
     *
     * It is not superstition: this effect installs itself in the
     * reactive flush that has just turned ``open`` true, so before the
     * computed style flips. Yet ``focus()`` on an element in
     * ``visibility: hidden`` is a **silent no-op** — no error, no
     * return, nothing.
     *
     * A FIXED delay is not enough: the boundary falls right inside the
     * hidden window, and it moves from one run to the next. So we do not
     * wait for a duration, we wait for the RESULT: we try, we check the
     * focus landed, and we retry otherwise.
     *
     * Without that, the trap is installed (``$el._bzTrap`` present) and
     * the focus stays on the trigger. The contract is written in
     * ``dialog.py``: "the first interactive child receives focus".
     *
     * The DOM is RE-QUERIED at every attempt: between the installation
     * and the frame that succeeds, a morph may have replaced the panel's
     * content, and a detached node focuses into the void. */
    let attempts = 0;
    function focusFirst() {
      if (!el.isConnected) return;
      // The field marked ``autofocus=`` first, then the first focusable.
      const first = autofocusIn(el) || shownFocusables(el)[0];
      if (first) {
        giveFocus(first);
        if (el.contains(document.activeElement)) return;
      }
      // ~20 frames (≈ 1/3 s): beyond that, the panel will not open.
      if (++attempts < 20) requestAnimationFrame(focusFirst);
    }
    requestAnimationFrame(focusFirst);
    return function dispose() {
      el.removeEventListener("keydown", onKeydown);
      if (previous && previous.focus) previous.focus();
    };
  }

  /* ── Focus targets: ``autofocus=``, ``.focus()``, ``.blur()`` ──────
   *
   * A component declares WHERE it takes the focus once
   * (``FOCUS_TARGET``, ``components/base/focus.py``): a list of
   * selectors tried in order, each on the element carrying the id then
   * inside it; an empty list is that element. The order is a priority
   * (the checked radio, else the first), which one selector list cannot
   * say. */
  const AUTOFOCUS = "data-bz-autofocus";

  function resolveTarget(el, sels) {
    if (!sels.length) return el;
    for (const s of sels) {
      if (el.matches(s)) return el;
      const hit = el.querySelector(s);
      if (hit) return hit;
    }
    return null;
  }

  function focusTarget(marked) {
    let sels = [];
    try {
      sels = JSON.parse(marked.getAttribute(AUTOFOCUS) || "[]");
    } catch (e) {
      /* a hand-written marker that is not JSON: the element itself */
    }
    return resolveTarget(marked, sels);
  }

  function focusIn(id, sels) {
    const el = document.getElementById(id);
    const target = el && resolveTarget(el, sels);
    if (target) target.focus();
  }

  function blurIn(id) {
    const el = document.getElementById(id);
    const active = document.activeElement;
    if (el && active && el.contains(active)) active.blur();
  }

  // ``focus()`` on an element that is not rendered, or in
  // ``visibility: hidden`` (a closed dialog), is a silent no-op.
  function shown(t) {
    return t.isConnected && t.getClientRects().length > 0 &&
      getComputedStyle(t).visibility !== "hidden";
  }

  /* A focus the PAGE gives (autofocus, a dialog opening), not the person.
   * A component whose focus has a side effect asks before acting: the
   * combobox opens its list when someone Tabs or clicks into it, not
   * when the page puts the cursor there (rule 5: autofocus never opens
   * a panel). ``focus`` fires synchronously inside ``.focus()``. */
  let giving = false;
  function giveFocus(t) {
    giving = true;
    try {
      t.focus();
    } finally {
      giving = false;
    }
  }
  function pageGivesFocus() {
    return giving;
  }

  // The first marked target inside ``box`` (an overlay's panel).
  function autofocusIn(box) {
    const marked = Array.from(box.querySelectorAll("[" + AUTOFOCUS + "]"));
    if (box.hasAttribute(AUTOFOCUS)) marked.unshift(box);
    for (const el of marked) {
      const t = focusTarget(el);
      if (t) return t;
    }
    return null;
  }

  // The user is typing somewhere: a field that just appeared does not
  // take the keyboard from them.
  function typing() {
    const a = document.activeElement;
    if (!a || a === document.body || !a.isConnected) return false;
    if (a.isContentEditable || a.tagName === "TEXTAREA" || a.tagName === "SELECT") return true;
    return a.tagName === "INPUT" &&
      !/^(button|submit|reset|checkbox|radio|range|color|file|image)$/i.test(a.type);
  }

  /* Rule 1 — a field takes the focus when its MARK APPEARS: it enters
   * the page marked, or a redraw marks it (``autofocus=`` False → True).
   * ``seen`` holds the nodes marked at the last scan: a morph keeps the
   * node of a field it merely redraws (paired by id), so a field that
   * STAYS marked is not focused again; one that loses the mark is
   * forgotten, and focused anew when it gets it back — ``autofocus=`` on
   * → off → on, or ``autofocus=(field in error)`` after each refused
   * submit.
   *
   * Every ``$bz._scan`` reports here, and the marks wait in ``pending``
   * for one frame: a ``bz-for`` scans its rows one by one, and the rule
   * "the first in the page wins" needs them all at once.
   *
   * Rule 3 — hidden at mount (closed overlay, inactive tab, folded
   * accordion): the frames retry while the page settles (an effect that
   * shows a panel lands a frame later), then give up. An overlay that
   * opens LATER focuses its own (``autofocusOpen``, ``focusTrap``); a tab
   * revealed later does not steal the focus. */
  const seen = new WeakSet();
  let pending = [];
  let tries = 0;
  let frame = 0;

  function autofocusMounted(els) {
    for (const el of els) {
      if (el.nodeType !== 1) continue;
      if (!el.hasAttribute(AUTOFOCUS)) {
        seen.delete(el);
        continue;
      }
      if (seen.has(el)) continue;
      seen.add(el);
      pending.push(el);
    }
    if (pending.length && !frame) {
      tries = 0;
      frame = requestAnimationFrame(settleAutofocus);
    }
  }

  function settleAutofocus() {
    frame = 0;
    pending = pending.filter(function (el) { return el.isConnected; });
    pending.sort(function (a, b) {
      return a.compareDocumentPosition(b) & Node.DOCUMENT_POSITION_FOLLOWING ? -1 : 1;
    });
    const targets = [];
    for (const el of pending) {
      const t = focusTarget(el);
      if (t && shown(t)) targets.push(t);
    }
    if (!targets.length) {
      if (pending.length && ++tries < 20) frame = requestAnimationFrame(settleAutofocus);
      else pending = [];
      return;
    }
    pending = [];
    if (targets.length > 1) {
      console.warn("bz: " + targets.length + " fields marked autofocus= entered the page " +
        "together; the first takes the focus.", targets);
    }
    const target = targets[0];
    // Rule 2 — never under the hands of someone typing elsewhere.
    if (typing() && document.activeElement !== target) return;
    giveFocus(target);
  }

  /* Rule 4 — an anchored overlay (popover, dropdown) that OPENS hands
   * the focus to the field marked inside it, if any; with none, the
   * focus stays on the trigger: a popover is not modal. Same retry as
   * the focus trap: the panel is shown by the very effect calling us. */
  function autofocusOpen(panel) {
    let attempts = 0;
    function attempt() {
      if (!panel.isConnected) return;
      const t = autofocusIn(panel);
      if (!t) return;
      giveFocus(t);
      if (document.activeElement === t) return;
      if (++attempts < 20) requestAnimationFrame(attempt);
    }
    requestAnimationFrame(attempt);
  }

  // A listener outside the caller's node: its unsubscribe goes to the
  // running ``bz-init`` (``$bz._own``, ``directives.js``), which gives
  // it back when its node leaves the document.
  function owned(release) {
    return $bz._own ? $bz._own(release) : release;
  }

  // Escape closes ONE layer: the deepest of the overlays that answer.
  // Every overlay registers at mount, open or not; its handler returns
  // ``true`` when it closed something. Handed its element, an overlay is
  // asked before the ones that contain it (then the later in the page
  // before the earlier), and the first ``true`` ends the round, so a
  // popover inside a drawer does not take the drawer with it on one
  // Escape. A handler without an element, or that returns nothing, never
  // stops the round.
  const escapes = [];

  function deeperFirst(a, b) {
    if (!a.el || !b.el) return (a.el ? 0 : 1) - (b.el ? 0 : 1);
    if (a.el.contains(b.el)) return 1;
    if (b.el.contains(a.el)) return -1;
    return a.el.compareDocumentPosition(b.el) & Node.DOCUMENT_POSITION_FOLLOWING ? 1 : -1;
  }

  function onEscape(e) {
    if (e.key !== "Escape") return;
    const round = escapes.slice().sort(deeperFirst);
    for (const entry of round) {
      if (entry.handler(e) === true && entry.el) return;
    }
  }

  function escapeKey(handler, el) {
    const entry = {handler: handler, el: el || null};
    if (!escapes.length) document.addEventListener("keydown", onEscape);
    escapes.push(entry);
    return owned(function () {
      const at = escapes.indexOf(entry);
      if (at >= 0) escapes.splice(at, 1);
      if (!escapes.length) document.removeEventListener("keydown", onEscape);
    });
  }

  /* Listen for a window-level event (V3 replacement for Alpine's
   * ``@<event>.window`` modifier — bz-on listens on the element, not
   * the window). Returns its unsubscribe. Typical consumers register
   * from ``bz-init`` for events that only ever fire on window :
   * ``popstate``, ``htmx:after-request``, ``htmx:before-request``. */
  function onWindow(eventName, handler) {
    window.addEventListener(eventName, handler);
    return owned(function () {
      window.removeEventListener(eventName, handler);
    });
  }

  function scrollLock() {
    const gap = window.innerWidth - document.documentElement.clientWidth;
    const prevOverflow = document.body.style.overflow;
    const prevPadding = document.body.style.paddingRight;
    document.body.style.overflow = "hidden";
    if (gap > 0) document.body.style.paddingRight = gap + "px";
    return function unlock() {
      document.body.style.overflow = prevOverflow;
      document.body.style.paddingRight = prevPadding;
    };
  }

  /* Close the overlay when a click lands outside `el`. Registered in
   * the capture phase so a stopPropagation inside the panel doesn't
   * smother it. Returns its unsubscribe.
   *
   * `alsoInsideFn` (optional) : a function returning an element ALSO
   * treated as "inside". Needed when the panel is teleported to <body>
   * (out of `el`'s subtree) : a click in the panel would count as
   * outside and close it immediately. Resolved on each click — the
   * teleported panel's ref registers AFTER this handler is wired, so it
   * can't be captured up front. */
  /* Is `node` inside `container`, teleportations counted: a panel
   * projected under <body> is still inside what it was projected FROM
   * (its `_bzScopeHost`, the origin <template>). A dropdown opened in a
   * popover's panel is in the popover — at any depth. Excepting only the
   * container's own panel would let a pick in a menu nested in a popover
   * close the popover with its menu. */
  function within(container, node) {
    while (node) {
      if (container.contains(node)) return true;
      let up = node;
      while (up && !up._bzScopeHost) up = up.parentElement;
      if (!up) return false;
      node = up._bzScopeHost;
    }
    return false;
  }

  function clickOutside(el, handler, alsoInsideFn) {
    function onClick(e) {
      if (within(el, e.target)) return;
      if (alsoInsideFn) {
        const extra = alsoInsideFn();
        if (extra && within(extra, e.target)) return;
      }
      handler(e);
    }
    document.addEventListener("click", onClick, true);
    return owned(function () {
      document.removeEventListener("click", onClick, true);
    });
  }

  /* Position `el` (fixed) relative to `anchor`. placement = "<side>"
   * or "<side>-<align>" with side ∈ {auto,top,bottom,left,right}, align
   * ∈ {start,center,end} (default center).
   *
   * ONE rule for every side : try the sides in an order, take the first
   * where the panel fits entirely ; if none fits, the side with the most
   * leftover room. side "auto" tries bottom → top → right → left ; an
   * explicit side tries itself, then its OPPOSITE, then the other two in
   * that same order. Predictable (an order, not raw "most room" which
   * would jump around) and never off-screen : both axes are clamped.
   *
   * An explicit side tries all four because, in a narrow window, the
   * panel can fit on neither that side nor its opposite.
   *
   * Either way the RESOLVED side is written to `el.dataset.side` so a
   * consumer (e.g. the tooltip arrow) can follow it — no more arrow
   * frozen at the SSR side while the panel flips at runtime.
   *
   * Tracks scroll + resize ; returns its dispose. */
  // Best-fit preference order — module constant so the scroll/resize
  // reposition path allocates nothing per tick.
  const SIDE_ORDER = ["bottom", "top", "right", "left"];
  const OPPOSITE = { bottom: "top", top: "bottom", right: "left", left: "right" };
  // The readability floor of an anchored panel, in px. `matchWidth`
  // never goes below that width, whatever the anchor: without it, a
  // `ui.select` placed in a sidebar collapsed to a rail (`w-16`) renders
  // a ~48 px panel where the labels wrap letter by letter, with a
  // horizontal scrollbar. 192 px = `12rem`
  // — the value the repository already gives an anchored panel:
  // `min-w-[12rem]` at `dropdown` and `popover`, `min-w-48` for
  // `combobox`'s `sm` `panel_free`.
  const MIN_MATCHED_WIDTH = 192;
  function floating(anchor, el, opts) {
    opts = opts || {};
    const parts = (opts.placement || "bottom").split("-");
    const wantSide = parts[0];
    const align = parts[1] || "center";
    const offset = opts.offset === undefined ? 6 : opts.offset;
    // matchWidth: pin the panel to the anchor's width (native <select>
    // behaviour). Both min AND max so wide content (a multi-combobox
    // header with many pills, a long option) WRAPS / truncates inside
    // the trigger width instead of growing the panel past the trigger
    // and getting shoved to the viewport edge. Set BEFORE measuring so
    // offsetWidth reflects it.
    const matchWidth = !!opts.matchWidth;

    function position() {
      // Pin to `fixed` BEFORE measuring. On the very first open the panel
      // was just un-hidden (display:none → ''), so without this it is still
      // in normal flow when we read offsetWidth/Height — its size (and thus
      // the computed placement) is constrained by the parent (e.g. a narrow
      // sidebar) and ends up wrong, only snapping right on the 2nd open when
      // a leftover `fixed` is still set. Measuring while fixed is consistent
      // on every open.
      el.style.position = "fixed";
      const a = anchor.getBoundingClientRect();
      if (matchWidth) {
        // The floor applies to the ANCHOR, not to the result: above
        // `MIN_MATCHED_WIDTH`, `mw === a.width` and the behaviour is
        // identical to the byte (that is what makes this fix safe for
        // `matchWidth`'s only two callers, Select and Combobox). The
        // floor itself is bounded to the viewport: on a screen narrower
        // than 192 px, a panel at the floor would overflow, and the edge
        // correction below (`Math.max(4, Math.min(...))`) only shifts
        // it, it does not shrink it.
        const mw = Math.max(
          a.width,
          Math.min(MIN_MATCHED_WIDTH, Math.max(0, window.innerWidth - 8))
        );
        el.style.minWidth = mw + "px";
        el.style.maxWidth = mw + "px";
      }
      const w = el.offsetWidth;
      const h = el.offsetHeight;
      const vw = window.innerWidth;
      const vh = window.innerHeight;

      // Room available on each side of the anchor (minus the offset),
      // and what the panel needs there (its height for top/bottom, its
      // width for left/right).
      const room = {
        bottom: vh - a.bottom - offset,
        top: a.top - offset,
        right: vw - a.right - offset,
        left: a.left - offset,
      };
      const need = { bottom: h, top: h, right: w, left: w };

      const order =
        wantSide in OPPOSITE
          ? [wantSide, OPPOSITE[wantSide]].concat(
              SIDE_ORDER.filter(function (s) {
                return s !== wantSide && s !== OPPOSITE[wantSide];
              })
            )
          : SIDE_ORDER;
      const side =
        order.find(function (s) {
          return room[s] >= need[s];
        }) ||
        order.reduce(function (best, s) {
          return room[s] - need[s] > room[best] - need[best] ? s : best;
        });

      let top, left;
      if (side === "top" || side === "bottom") {
        top = side === "bottom" ? a.bottom + offset : a.top - offset - h;
        if (align === "start") left = a.left;
        else if (align === "end") left = a.right - w;
        else left = a.left + (a.width - w) / 2;
      } else {
        left = side === "right" ? a.right + offset : a.left - offset - w;
        if (align === "start") top = a.top;
        else if (align === "end") top = a.bottom - h;
        else top = a.top + (a.height - h) / 2;
      }
      // Both axes : when no side fits, the panel covers part of its
      // anchor rather than leaving the screen.
      left = Math.max(4, Math.min(left, vw - w - 4));
      top = Math.max(4, Math.min(top, vh - h - 4));
      el.style.top = top + "px";
      el.style.left = left + "px";
      // Publish the resolved side so consumers (tooltip arrow) follow it
      // — only on change, so a stable overlay writes nothing while the
      // page scrolls under it.
      if (el.dataset.side !== side) el.dataset.side = side;

      /* …and WHERE the anchor is in the panel, so the arrow aims at it.
         The panel's middle and the trigger's middle coincide as long as
         nothing pushes the panel; the edge reframing just above
         (`Math.max(4, Math.min(...))`) separates them. An arrow set at
         `left-1/2` — so in the middle of the bubble — would point beside
         its button as soon as the panel approaches an edge. */
      const centre =
        side === "top" || side === "bottom"
          ? a.left + a.width / 2 - left
          : a.top + a.height / 2 - top;
      // Bounded inside the panel: an arrow set 2 px from the edge
      // sticks out of the corners' radius and floats beside the bubble.
      // 12 px covers the panel's radius plus the arrow's half width (an
      // 8 px square rotated 45°, ~11 px of diagonal).
      const etendue = side === "top" || side === "bottom" ? w : h;
      const vise = Math.max(12, Math.min(centre, etendue - 12));
      el.style.setProperty("--bz-arrow", vise + "px");
    }

    // Opened from inside a modal (a dialog, a drawer: ``aria-modal``), the
    // panel is painted above it. Anchored panels sit at ``z-40``, under
    // the house's ``z-50`` modals: without this, a popover in a drawer
    // opens BEHIND it, and its buttons are out of reach. At ``z-50`` the
    // tie goes to the panel, projected last in
    // ``<body>``. A virtual anchor (a chart's point: a bare
    // ``getBoundingClientRect``) is in no modal.
    const inModal = typeof anchor.closest === "function" && anchor.closest('[aria-modal="true"]');
    el.style.zIndex = inModal ? "50" : "";
    position();
    window.addEventListener("scroll", position, true);
    window.addEventListener("resize", position);
    return function dispose() {
      window.removeEventListener("scroll", position, true);
      window.removeEventListener("resize", position);
    };
  }

  // Shared "should we animate ?" gate — the toast leave dance
  // (notification.js) and the bz-for FLIP reflow (directives.js) both
  // honour it. The MediaQueryList is created once and memoised ; ``.matches``
  // stays live, so an OS setting change mid-session is respected without
  // re-parsing the query on every call.
  let reduceMotionMQL = null;
  function prefersReducedMotion() {
    if (typeof window.matchMedia !== "function") return false;
    if (!reduceMotionMQL) {
      reduceMotionMQL = window.matchMedia("(prefers-reduced-motion: reduce)");
    }
    return reduceMotionMQL.matches;
  }

  /* ── The address, on the client side ─────────────────────────────────
   *
   * The EXACT counterpart of ``push_url()`` on the server side
   * (server/navigation.py), for what makes no round trip: a tab flips in
   * the scope, the server knows nothing about it, so the ``HX-Push-Url``
   * header can do nothing for it.
   *
   * ``pushState`` and not ``replaceState``: a tab IS a view, so the back
   * button must return to it. A display preference (a density, a theme)
   * does not deserve a history entry and has no business here.
   *
   * We keep ``history.state`` intact: htmx files its own there, and
   * overwriting it would break its own restoration on the entries it
   * created.
   */
  function pushUrl(param, value) {
    const url = new URL(window.location.href);
    const next = value == null ? "" : String(value);
    if (next === "") url.searchParams.delete(param);
    else url.searchParams.set(param, next);
    if (url.href === window.location.href) return;
    window.history.pushState(window.history.state, "", url.href);
  }

  /* A parameter's CURRENT value, or ``null``. Read live rather than
   * remembered: after a back, ``location`` has already moved by the time
   * the ``popstate`` reaches us. */
  function urlParam(param) {
    return new URL(window.location.href).searchParams.get(param);
  }

  /* Text made inert for HTML a slab builds as a string (the calendar's
   * cells, the time picker's buttons): ``&``, ``<``, ``>`` and both
   * quotes. THE escaper of the runtime: a slab that writes HTML from data
   * goes through it, and a new HTML sink is declared in
   * ``tests/consistency/test_runtime_html_sinks_are_declared.py``. */
  function escapeHtml(value) {
    return String(value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  $bz.helpers = {
    escapeHtml: escapeHtml,
    focusTrap: focusTrap,
    focusIn: focusIn,
    blurIn: blurIn,
    autofocusMounted: autofocusMounted,
    autofocusOpen: autofocusOpen,
    pageGivesFocus: pageGivesFocus,
    escapeKey: escapeKey,
    onWindow: onWindow,
    pushUrl: pushUrl,
    urlParam: urlParam,
    scrollLock: scrollLock,
    clickOutside: clickOutside,
    floating: floating,
    prefersReducedMotion: prefersReducedMotion,

    // Fire ``eventName`` from the scope's form carrier, deferred to a
    // microtask so the DOM write that precedes it has landed before any
    // listener reads the value back.
    //
    // The event name is the ONLY thing that differs between the two
    // components and the difference is deliberate :
    // number_input emits ``bzchange`` (its own, so an ``on_change=``
    // wired by the user can't be confused with the native ``change`` the
    // inner input fires while typing) ; slider emits the native
    // ``change``. Passing it in keeps the microtask rationale in one
    // place. Distinct from ``base/field_wiring.change_emit_effect``, which is
    // the effect-context mechanism, not another variant of this.
    //
    // ``detail``: what the gesture tells, the object whose JSON the
    // carrier holds for the server (a scheduler's ``{event_id, start,
    // end}``, a dropzone's ``Move``) — the client expression reads it in
    // ``$event.detail``, as every ``item_click``.
    emitChange: function (carrier, eventName, detail) {
      if (!carrier) return;
      const name = eventName || "change";
      queueMicrotask(function () {
        carrier.dispatchEvent(detail === undefined
          ? new Event(name, { bubbles: true })
          : new CustomEvent(name, { bubbles: true, detail: detail }));
      });
    },

    // ── Pointer capture — the pointer-drag family ────────────────────
    // Capturing means telling the browser to send ALL the pointer's
    // events to that element until release, even when the cursor leaves
    // it. Without that, the gesture stops at the first pixel outside the
    // box — and a handle is a few points wide.
    //
    // The two guards are not superstition, and it is for them that this
    // lives here rather than being copied:
    //   - ``pointerId !== undefined``: a synthetic event (a test, a
    //     script) does not carry one, and the call would raise;
    //   - the ``try``: the browser refuses the capture if the pointer is
    //     no longer active (released in the meantime, gesture cancelled
    //     by the OS), and that exception must not break the gesture in
    //     progress.
    //
    // A pointer-drag component calls this, it does not copy it.
    capturePointer: function (el, e) {
      if (!el || !e || e.pointerId === undefined) return;
      try { el.setPointerCapture(e.pointerId); } catch (err) {}
    },
    releasePointer: function (el, e) {
      if (!el || !e || e.pointerId === undefined) return;
      try { el.releasePointerCapture(e.pointerId); } catch (err) {}
    },

  };

  /* Iconify name resolution — mirrors Python's Icon._resolve_name so a
   * reactive name=ClientBinding produces the same "set:name[-style]"
   * form the server emits at SSR time. Invoked from rendered HTML :
   *   bz-attr:icon="$bz._resolveIcon($bz.state.X.y.icon, 'lucide', null)"
   * defaultSet / defaultStyle are baked at SSR time from the theme. */
  $bz._resolveIcon = function (name, defaultSet, defaultStyle) {
    if (!name) return "";
    if (String(name).indexOf(":") !== -1) return name; // full form verbatim
    let full = (defaultSet || "lucide") + ":" + name;
    // Phosphor (``ph``, translated server-side) / Tabler take an
    // optional style suffix (-bold, -fill, …).
    if (defaultStyle && (defaultSet === "ph" || defaultSet === "tabler")) {
      full = full + "-" + defaultStyle;
    }
    return full;
  };

  /* Is ``href`` the active entry of its menu for ``path``? An entry
   * matches its own path and what lies below it (``/`` only itself),
   * and the MOST SPECIFIC matching entry of the menu wins: ``/tickets``
   * stays lit on ``/tickets/42``, not on ``/tickets/mine`` when a
   * ``/tickets/mine`` entry exists. The menu is the closest
   * aside / nav / [role=navigation]; its entries carry ``data-bz-nav``.
   * Decided in the browser and not by the server: entries rendered by a
   * refreshable zone, or by another one, belong to the same menu. The
   * winner is computed once per menu and path, not once per entry. */
  const NAV_WINNERS = new WeakMap();
  function navMatches(path, href) {
    return href === "/" ? path === "/" : path === href || path.startsWith(href + "/");
  }
  $bz._navActive = function (path, href, el) {
    if (!navMatches(path, href)) return false;
    const root = (el && el.closest && el.closest("aside, nav, [role=navigation]")) || document;
    const entries = root.querySelectorAll("[data-bz-nav]");
    let memo = NAV_WINNERS.get(root);
    if (!memo || memo.path !== path || memo.count !== entries.length) {
      let winner = null;
      entries.forEach(function (entry) {
        const h = entry.getAttribute("data-bz-nav");
        if (navMatches(path, h) && (winner === null || h.length > winner.length)) winner = h;
      });
      memo = { path: path, count: entries.length, winner: winner };
      NAV_WINNERS.set(root, memo);
    }
    return memo.winner === null || memo.winner === href;
  };

  /* ui.interval — recurring client timer that fires a server action.
   * Driven reactively from a bz-effect : ``$bz._tick($el, active, ms)``.
   * When ``active`` is truthy we ensure a setInterval that dispatches a
   * ``tick`` CustomEvent on the element (htmx fires the hx-post on it) ;
   * when falsy we clear it. The interval is idempotent across morph
   * re-binds (the element keeps ``_bzTickId``), self-clears if the
   * element leaves the DOM, and ``ms`` changes restart it. This is the
   * stoppable replacement for a server background loop : flipping the
   * ``active`` binding (server- or client-side) stops it instantly —
   * no held connection, no orphan requests. */
  $bz._tick = function (el, active, ms) {
    if (active) {
      if (el._bzTickId && el._bzTickMs === ms) return; // already live, same rate
      if (el._bzTickId) clearInterval(el._bzTickId);   // rate changed → restart
      el._bzTickMs = ms;
      el._bzTickId = setInterval(function () {
        if (!el.isConnected) {                          // removed → self-clear
          clearInterval(el._bzTickId);
          el._bzTickId = null;
          return;
        }
        el.dispatchEvent(new CustomEvent("tick"));
      }, ms);
    } else if (el._bzTickId) {
      clearInterval(el._bzTickId);
      el._bzTickId = null;
    }
  };

  /* Multi-pick membership algebra, shared by the Select and Combobox
   * multi scopes. Both read/write through the scope's own ``_read`` /
   * ``_write``, so the mixin never knows where the value lives (a local
   * signal or ``$bz.state.X.Y``).
   *
   * Spread it into a scope : ``{ ...$bz.multiSelect, …overrides }``.
   *
   * Only the genuinely divergent methods stay per-scope — Combobox
   * filters ``_selectAll`` by what the query leaves visible, and has
   * ``_highlightFromValue`` on Select's side.
   * The ones below are common, so a set-semantics fix is made once and
   * the two components cannot silently diverge. ``_clearAll`` does not
   * close the panel: a panel must survive its own header commands, as
   * with ``_selectAll``. Combobox overrides it, but only to ADD its query
   * reset. */
  $bz.multiSelect = {
    _picked() { const v = this._value(); return Array.isArray(v) ? v.map(String) : []; },
    _isPicked(v) { return this._picked().indexOf(String(v)) >= 0; },
    _hasPicked() { return this._picked().length > 0; },
    _togglePick(v) {
      const cur = this._picked();
      const str = String(v);
      const i = cur.indexOf(str);
      this._write(i >= 0 ? cur.filter((_, j) => j !== i) : [...cur, str]);
    },
    _removeOne(v) {
      const cur = this._picked();
      const i = cur.indexOf(String(v));
      if (i >= 0) { this._write(cur.filter((_, j) => j !== i)); }
    },
    // Single-mode alias for keyboard Enter (an option click calls
    // _togglePick directly).
    _pick(v) { this._togglePick(v); },
    _setValue(raw) {
      this._write(
        Array.isArray(raw)
          ? raw.map(String)
          : raw == null || raw === "" ? [] : [String(raw)],
      );
    },
    // Empties the selection WITHOUT closing the panel: it is a command
    // OF the header bar, and a command does not dismiss what it
    // commands. With an ``on_close=`` wired, closing here POSTED the
    // empty selection to the server — cf. the datatable's column
    // filter.
    _clearAll() { this._write([]); },
  };

  /* The parts a page carries ONCE (``render/shared_parts.py``): one
   * ``<template data-bz-part="<key>">`` per distinct part, cloned into a
   * host that names it (``data-bz-part``) — a calendar picker's header,
   * a colour picker's palette — the first time it opens, and again after
   * a morph took it out (the server never renders it). The clones are
   * marked ``data-bz-row``: the runtime inserted them, a walk by position
   * skips them. A zone response appends the parts it rendered to <body>;
   * one per key is kept, the first — identical by construction. */
  function partTemplate(key) {
    return key ? document.querySelector('template[data-bz-part="' + key + '"]') : null;
  }

  // Clone the host's part in, after its leading hidden inputs; ``true``
  // when it did. Scanned after insertion: its directives read the host's
  // scope.
  function fillPart(host) {
    const key = host && host.getAttribute("data-bz-part");
    if (!key || host.querySelector(':scope > [data-bz-part-of]')) return false;
    const tpl = partTemplate(key);
    if (!tpl) {
      console.warn("bz: no shared part " + key + " on the page");
      return false;
    }
    let anchor = host.firstElementChild;
    while (anchor && anchor.matches('input[type="hidden"]')) anchor = anchor.nextElementSibling;
    const nodes = Array.from(tpl.content.children).map(function (n) {
      const copy = n.cloneNode(true);
      copy.setAttribute("data-bz-part-of", key);
      copy.setAttribute("data-bz-row", "");
      return copy;
    });
    for (const node of nodes) host.insertBefore(node, anchor);
    if ($bz._scan) for (const node of nodes) $bz._scan(node);
    return true;
  }

  function dropDuplicateParts() {
    const seen = {};
    document.querySelectorAll("template[data-bz-part]").forEach(function (t) {
      const key = t.getAttribute("data-bz-part");
      if (seen[key]) t.remove();
      else seen[key] = true;
    });
  }
  document.addEventListener("htmx:afterSwap", dropDuplicateParts);
  document.addEventListener("htmx:oobAfterSwap", dropDuplicateParts);

  $bz.parts = { template: partTemplate, fill: fillPart };

  /* The pointer gesture's rules, ONCE — for `dnd.js` (moving a node
   * between zones) and `scheduler.js` (moving a card in time): keep a
   * dropped card where it was while the server ASKS something (a modal
   * dialog, no redraw), and swallow the click a browser fires at the end
   * of a drag. Without them, an `on_move` that asks « move it to Done? »
   * puts the card back under the question, and a clickable card opens
   * when it is let go.
   *
   *   MOUSE_THRESHOLD_PX / TOUCH_HOLD_MS / TOUCH_TOLERANCE_PX   when a
   *       press becomes a drag (distance, or time then wander);
   *   distance(start, e)        how far the pointer went, the same way;
   *   swallowClick()            the click that ends a drag, for a MOMENT
   *       (`SWALLOW_MS`) — a browser may fire none, and the next click
   *       would be the dialog's button;
   *   whenAnswered(carrier, {untouched, undo, settled})   after the
   *       carrier's answer (two frames: the swap and the rescan land
   *       then), `undo()` if `untouched()` — unless a modal dialog is open
   *       or a request is in flight: then it waits for the dialog's
   *       `close` or the next answer. `settled()` runs once, after the
   *       first answer. */
  const MODAL_SEL = '[role="dialog"][aria-modal="true"][data-open="true"]';
  const SWALLOW_MS = 400;
  let swallowUntil = 0;
  //: Requests in flight, page-wide. From `htmx:beforeSend`, never
  //: `beforeRequest`: a request cancelled before it leaves fires no
  //: `afterRequest`, and the count would hold a card for ever.
  let inFlight = 0;
  document.addEventListener("htmx:beforeSend", function () { inFlight++; });
  document.addEventListener("htmx:afterRequest", function () {
    inFlight = Math.max(0, inFlight - 1);
  });
  document.addEventListener("click", function (e) {
    if (Date.now() > swallowUntil) return;
    swallowUntil = 0;
    e.stopPropagation();
    e.preventDefault();
  }, true);

  function afterTwoFrames(fn) {
    requestAnimationFrame(function () { requestAnimationFrame(fn); });
  }

  function whenAnswered(carrier, how) {
    let holding = false;
    function wake() { afterTwoFrames(decide); }
    function hold() {
      if (holding) return;
      holding = true;
      document.addEventListener("close", wake);
      document.addEventListener("htmx:afterRequest", wake);
    }
    function release() {
      if (!holding) return;
      holding = false;
      document.removeEventListener("close", wake);
      document.removeEventListener("htmx:afterRequest", wake);
    }
    function decide() {
      if (!how.untouched()) return release();
      //: A closed dialog stays MOUNTED (its leave animation needs it):
      //: `data-open` says whether it asks.
      if (document.querySelector(MODAL_SEL) !== null || inFlight > 0) return hold();
      release();
      how.undo();
    }
    function settle(e) {
      if (e.detail && e.detail.elt && e.detail.elt !== carrier) return;
      document.removeEventListener("htmx:afterRequest", settle);
      afterTwoFrames(function () {
        decide();
        if (how.settled) how.settled();
      });
    }
    document.addEventListener("htmx:afterRequest", settle);
  }

  $bz.gesture = {
    MOUSE_THRESHOLD_PX: 5,
    TOUCH_HOLD_MS: 250,
    TOUCH_TOLERANCE_PX: 8,
    SWALLOW_MS: SWALLOW_MS,
    distance: function (start, e) {
      return Math.hypot(e.clientX - start.x, e.clientY - start.y);
    },
    swallowClick: function () { swallowUntil = Date.now() + SWALLOW_MS; },
    afterTwoFrames: afterTwoFrames,
    whenAnswered: whenAnswered,
    _inFlight: function () { return inFlight; },
  };

  /* Numeric primitives — pure, widget-agnostic. Shared by the
   * number_input + slider slabs (each caches the result locally). */
  $bz.num = {
    // Decimal places implied by a numeric step : 0.01 → 2, 5 → 0.
    // Pure (number|string) → int, no ``this`` / no widget state.
    precisionFromStep: function (step) {
      const s = String(step);
      const dot = s.indexOf(".");
      return dot >= 0 ? s.length - dot - 1 : 0;
    },

    // The memo wrapper over ``precisionFromStep``, cached on the scope's
    // own ``_precCache`` field. Spread into a scope as ``_precision``.
    cachedPrecision: function () {
      if (this._precCache !== undefined) return this._precCache;
      this._precCache = $bz.num.precisionFromStep(this._step);
      return this._precCache;
    },

  };
})();


/* locale.js — month and weekday names, derived from the language.
 *
 * ⚠️ **This slab's place in ``runtime/sources.py`` is an ORDERING
 * CONSTRAINT.** It must load before ``calendar.js``, which calls
 * ``customElements.define('bz-calendar', …)``: that IMMEDIATELY upgrades
 * every calendar already in the DOM, and their constructor then reads
 * ``$bz.locale.weekdayNames()``.
 *
 * Loaded later, it costs **one exception thrown per calendar**. The
 * screen recovers — the ``bz-text`` directive comes back later — but the
 * flood of errors stops ``networkidle`` arriving, and a suite waiting
 * for it hangs.
 *
 * This file depends on nothing (it creates ``window.$bz`` if needed), so
 * it could live anywhere before that consumer. It is placed JUST before
 * it so that a reader wondering "why here?" finds the answer on the
 * list's next line.
 *
 * Guarded by ``tests/runtime_js/test_no_page_throws_on_load.py``, which
 * loads the component pages and requires ZERO exception. A STATIC
 * gate (forbidding a read of a ``$bz.<ns>`` set later) would flag
 * legitimate cases: DEFERRED reads, in functions called well after load.
 * What sets the defect apart is the MOMENT of the read, and only a
 * browser separates them.
 *
 * Exposed as window.$bz.locale, read by calendar.js and by the bz-*
 * expressions (``bz-text="$bz.locale.monthName(month)"``).
 *
 * Why here rather than on the server side
 * ----------------------------------------
 * Python has no safe way of naming a month in a given language: the
 * stdlib's ``locale`` module is process-GLOBAL state (and depends on the
 * locales installed on the machine), and Babel would be a dependency —
 * which the charter excludes. The browser, for its part, already ships
 * the complete table: ``Intl.DateTimeFormat`` gives it for any BCP-47
 * tag, without one extra byte.
 *
 * The language comes from ``<html lang>``, which ``Bretzel(lang=...)``
 * sets — not from an ad hoc attribute. It is the standard place, the one
 * a screen reader already reads to choose its voice, and the only one
 * that stays right if the app changes it by hand.
 *
 *   $bz.locale.tag()            the current tag ("fr", "en"…)
 *   $bz.locale.monthNames()     12 long names, January first
 *   $bz.locale.monthName(i)     a single one, 0-indexed
 *   $bz.locale.weekdayNames()     7 NARROW names ("M", "T"…), SUNDAY first
 *   $bz.locale.weekdayLongNames() the same in full, for a ``title=``
 *
 * ⚠️ NARROW, not short: the calendar's column is written in density
 * steps and its text in text steps, and only the first follows
 * ``--spacing``. "Wed" / "mer." overflow their column, even at the
 * DEFAULT density. One letter fits any step; the full name rides the
 * column's ``title=``.
 *
 * ⚠️ Sunday first, always: it is ``Date.getDay()``'s order, and it is
 * the component that rotates the list according to ``weekstart``. A list
 * written Monday-first — the French reflex — shifts every column by a
 * day.
 */
(function () {
  "use strict";
  const $bz = (window.$bz = window.$bz || {});

  // A fallback if the engine has no usable Intl, or if the tag is
  // invalid (Intl RAISES on "français"). It is exactly what the
  // framework returned before, so a fallback changes nothing for
  // anybody.
  const FALLBACK_MONTHS = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
  ];
  const FALLBACK_WEEKDAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
  const FALLBACK_NARROW = FALLBACK_WEEKDAYS.map(function (d) { return d[0]; });

  // ``2023-01-01`` IS a Sunday, and 2023 has twelve months — the two
  // anchors we need. Everything is computed in UTC: building these dates
  // in local time would shift by a day west of Greenwich, so the day's
  // name too.
  const SUNDAY = Date.UTC(2023, 0, 1);
  const DAY_MS = 86400000;

  const memo = Object.create(null);

  function names(tag) {
    let entry = memo[tag];
    if (entry) return entry;
    try {
      const month = new Intl.DateTimeFormat(tag, {
        month: "long",
        timeZone: "UTC",
      });
      const weekday = new Intl.DateTimeFormat(tag, {
        weekday: "narrow",
        timeZone: "UTC",
      });
      // The FULL name, for the column headers' ``title=``. Same memo,
      // same construction: seven more calls, once per language tag,
      // never per calendar.
      const weekdayLong = new Intl.DateTimeFormat(tag, {
        weekday: "long",
        timeZone: "UTC",
      });
      entry = {
        months: FALLBACK_MONTHS.map(function (_, i) {
          return month.format(new Date(Date.UTC(2023, i, 15)));
        }),
        weekdays: FALLBACK_WEEKDAYS.map(function (_, i) {
          return weekday.format(new Date(SUNDAY + i * DAY_MS));
        }),
        weekdaysLong: FALLBACK_WEEKDAYS.map(function (_, i) {
          return weekdayLong.format(new Date(SUNDAY + i * DAY_MS));
        }),
      };
    } catch (e) {
      // The fallback has no full names: the abbreviation is the
      // longest thing it knows, so it is what the ``title`` carries.
      entry = {
        months: FALLBACK_MONTHS,
        weekdays: FALLBACK_NARROW,
        weekdaysLong: FALLBACK_WEEKDAYS,
      };
    }
    memo[tag] = entry;
    return entry;
  }

  $bz.locale = {
    tag: function () {
      return (document.documentElement.getAttribute("lang") || "en").trim() || "en";
    },
    monthNames: function () {
      return names(this.tag()).months;
    },
    monthName: function (index) {
      return this.monthNames()[index] || "";
    },
    weekdayNames: function () {
      return names(this.tag()).weekdays;
    },
    weekdayLongNames: function () {
      return names(this.tag()).weekdaysLong;
    },
  };

  /* ── $bz.dates — THE date arithmetic and the ONE reader of a typed date ──
   *
   * One place, because copies drift. ``new Date("2026-08-01")`` is UTC
   * midnight — west of Greenwich, July 31 — so a month computed from it
   * can land a month off. Every date here is LOCAL and every string ISO.
   */
  function iso(d) {
    return d.getFullYear() + "-" +
      String(d.getMonth() + 1).padStart(2, "0") + "-" +
      String(d.getDate()).padStart(2, "0");
  }

  /* An ISO day as a LOCAL Date (never `new Date(isoStr)`, which is UTC),
   * or null when it is not one. */
  function fromIso(isoStr) {
    const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(String(isoStr || ""));
    return m ? new Date(+m[1], +m[2] - 1, +m[3]) : null;
  }

  function addDays(isoStr, n) {
    const p = isoStr.split("-");
    return iso(new Date(+p[0], +p[1] - 1, +p[2] + n));
  }

  /* The first day of the month `n` months after the one of `isoStr`. */
  function addMonths(isoStr, n) {
    const d = fromIso(isoStr) || new Date();
    return iso(new Date(d.getFullYear(), d.getMonth() + n, 1));
  }

  /* The first day of the week that CONTAINS `isoStr`, according to
   * `weekstart` (0 = Sunday, 1 = Monday…). The modulo is doubled
   * (`% 7 + 7) % 7`) because JS returns a NEGATIVE remainder for a
   * negative dividend — without it, any day before `weekstart` in its
   * week would go back one week. */
  function weekStartOf(isoStr, weekstart) {
    const p = isoStr.split("-");
    const d = new Date(+p[0], +p[1] - 1, +p[2]);
    const back = (d.getDay() - weekstart + 7) % 7;
    return iso(new Date(+p[0], +p[1] - 1, +p[2] - back));
  }

  /* What the person TYPED, as an ISO day — or `""` when it is empty or
   * names no day (the field then clears). A clean ISO day passes. A
   * numeric date (`02/07/2027`, `2.7.27`, `2-7-2027`) is read in the order
   * of `<html lang>`: `new Date()` reads `MM/DD/YYYY` whatever the
   * language, so in French « 02/07/2027 » would become 7 February. The
   * order is asked of `Intl.DateTimeFormat` —
   * the day's place before or after the month's in that language's own
   * short date — so no table of locales; a day that does not exist
   * (`31/02/2027`) is refused, not rolled over. Anything else is free-form
   * (`July 19 2018`) and goes to `new Date()`. */
  function typed(text) {
    const s = String(text || "").trim();
    if (!s) return "";
    if (/^\d{4}-\d{2}-\d{2}$/.test(s)) return fromIso(s) ? s : "";
    const n = s.match(/^(\d{1,2})[\/.\- ](\d{1,2})[\/.\- ](\d{4}|\d{2})$/);
    if (n) {
      const parts = new Intl.DateTimeFormat(document.documentElement.lang || undefined)
        .formatToParts(new Date(2000, 10, 22));
      const at = function (k) { return parts.findIndex(function (p) { return p.type === k; }); };
      const dayFirst = at("day") < at("month");
      const d = +n[dayFirst ? 1 : 2];
      const mo = +n[dayFirst ? 2 : 1];
      let y = +n[3];
      if (y < 100) y += 2000;
      const c = new Date(y, mo - 1, d);
      if (c.getFullYear() !== y || c.getMonth() !== mo - 1 || c.getDate() !== d) return "";
      return iso(c);
    }
    const named = byName(s);
    if (named) return named.day ? iso(named.date) : "";
    const c = new Date(s);
    return isNaN(c.getTime()) ? "" : iso(c);
  }

  /* A month named in the page's language — « 4 nov. 2026 », « novembre
   * 2026 », « Nov 4, 2026 », « mer. 4 nov. 2026 » —: the words are
   * compared, accents and dots aside, to the month names `Intl` gives for
   * `<html lang>`, short and long; a weekday name matches none (« mar. »
   * is Tuesday, « mars » March). `null` when no word names a month;
   * `{date, day}` else, `day` false when no day was written. */
  /* The ONE form a search compares, twin of Python's ``fold``
   * (``bretzel/core/text.py``) — the two must give the same string: the
   * server bakes folded options, the browser folds what is typed. The
   * twin is held by ``tests/runtime_js/test_one_fold_on_both_sides.py``. */
  function fold(text) {
    return String(text == null ? "" : text).toLowerCase().normalize("NFKD")
      .replace(/\p{M}/gu, "").toLowerCase()
      .replace(/ß/g, "ss").replace(/ς/g, "σ");
  }
  $bz.fold = fold;

  const monthWords = {};
  function plain(word) {
    return fold(word).replace(/\./g, "");
  }
  function months() {
    const tag = document.documentElement.lang || "";
    if (!monthWords[tag]) {
      const found = {};
      ["short", "long"].forEach(function (width) {
        const f = new Intl.DateTimeFormat(tag || undefined, { month: width });
        for (let m = 0; m < 12; m++) found[plain(f.format(new Date(2000, m, 1)))] = m;
      });
      monthWords[tag] = found;
    }
    return monthWords[tag];
  }
  function byName(text) {
    const words = months();
    let month = -1, year = 0, day = 0;
    String(text).split(/[\s,\u2013\u2014\-]+/).forEach(function (token) {
      if (!token) return;
      if (/^\d{4}$/.test(token)) { year = +token; return; }
      if (/^\d{1,2}$/.test(token)) { if (!day) day = +token; return; }
      const m = words[plain(token)];
      if (m !== undefined && month < 0) month = m;
    });
    if (month < 0 || !year) return null;
    const date = new Date(year, month, day || 1);
    if (day && date.getDate() !== day) return { date: date, day: false };
    return { date: date, day: !!day };
  }

  /* A typed month, as ``YYYY-MM`` — or `""`. Digits (`2026-08`,
   * `08/2026`), or the month's name (« novembre 2026 »). */
  function typedMonth(text) {
    const s = String(text || "").trim();
    if (!s) return "";
    const m = s.match(/^(\d{1,4})[^\d](\d{1,4})$/);
    if (m) {
      const y = m[1].length === 4 ? +m[1] : +m[2];
      const mo = m[1].length === 4 ? +m[2] : +m[1];
      if (mo < 1 || mo > 12 || y < 1) return "";
      return String(y).padStart(4, "0") + "-" + String(mo).padStart(2, "0");
    }
    const named = byName(s);
    return named ? iso(named.date).slice(0, 7) : "";
  }

  /* What a field SHOWS of its value, in the page's language — the value
   * itself stays ISO, it is what is posted. A day is shown in the
   * language's short NUMERIC form — « 16/10/2026 », « 10/16/2026 » in
   * American English —, the one people write, so what is shown is what
   * one types. A value that is not one (half typed) is shown as it is. */
  const formats = {};
  const NUMERIC = { day: "2-digit", month: "2-digit", year: "numeric" };
  function format(options) {
    const tag = document.documentElement.lang || "";
    const key = tag + JSON.stringify(options);
    if (!formats[key]) formats[key] = new Intl.DateTimeFormat(tag || undefined, options);
    return formats[key];
  }
  function shown(isoStr) {
    const d = fromIso(isoStr);
    return d ? format(NUMERIC).format(d) : String(isoStr || "");
  }
  /* A chart's date tick, in the page's language: « 14h30 » / « 2:30 PM »
   * (`time`), « 02 févr. » / « Feb 02 » (`day`), « févr. 2026 » (`month`),
   * « 2026 » (`year`). The server wrote it with `strftime`, in English. */
  const AXIS = {
    day: { day: "2-digit", month: "short" },
    month: { month: "short", year: "numeric" },
    year: { year: "numeric" },
  };
  function axis(stamp, style) {
    const m = /^(\d{4})-(\d{2})-(\d{2})(?:T(\d{2}):(\d{2}))?/.exec(String(stamp || ""));
    if (!m) return String(stamp || "");
    if (style === "time") return shownTime((m[4] || "00") + ":" + (m[5] || "00"));
    const d = new Date(+m[1], +m[2] - 1, +m[3], +(m[4] || 0), +(m[5] || 0));
    return format(AXIS[style] || AXIS.day).format(d);
  }
  /* A day in words, « mardi 3 novembre 2026 » — what a screen reader
   * says of an event's day (the scheduler's cards). */
  function shownLong(isoStr) {
    const d = fromIso(isoStr);
    return d ? format({ weekday: "long", day: "numeric", month: "long", year: "numeric" }).format(d)
      : String(isoStr || "");
  }
  function shownMonth(ym) {
    const m = /^(\d{4})-(\d{2})$/.exec(String(ym || ""));
    return m ? format({ month: "long", year: "numeric" }).format(new Date(+m[1], +m[2] - 1, 1))
      : String(ym || "");
  }
  /* A week by its seven days, from the first one (`weekstart`: 0 =
   * Sunday, 1 = Monday…), whatever day of it the value names: « 02/11/2026
   * – 08/11/2026 ». */
  function shownWeek(isoStr, weekstart) {
    if (!fromIso(isoStr)) return String(isoStr || "");
    const d = fromIso(weekStartOf(isoStr, weekstart || 0));
    const end = new Date(d.getFullYear(), d.getMonth(), d.getDate() + 6);
    const f = format(NUMERIC);
    return f.formatRange ? f.formatRange(d, end) : f.format(d) + " – " + f.format(end);
  }

  /* What a field ASKS for when it is empty: the numeric form one types,
   * in the page's order and separators — « JJ/MM/AAAA » in French,
   * « MM/DD/YYYY » in American English, « DD.MM.YYYY » in German —, as the
   * browser's own date field does. The order comes from the formatter
   * `shown` uses, so the hint, what is shown and what `typed` reads agree;
   * the letters are the framework's texts (`date.typed_day`…), baked by
   * the server. */
  function letters(options, map) {
    return format(options).formatToParts(new Date(2000, 10, 22))
      .map(function (p) { return p.type in map ? map[p.type] : p.value; }).join("");
  }
  function pattern(day, month, year) {
    return letters(NUMERIC, { day: day, month: month, year: year });
  }
  function patternMonth(month, year) {
    return letters({ month: "2-digit", year: "numeric" }, { month: month, year: year });
  }

  /* ── $bz.times — THE clock: an "HH:MM" as the page's language writes it ──
   * One rule for every hour the framework shows (the time picker's field,
   * the scheduler's axis, the hour beside a dragged card): « 14h30 »,
   * « 8h » in French — the form a French reader writes, which `Intl` does
   * not give (« 14:30 ») —, otherwise `Intl`'s, « 2:30 PM » in American
   * English, « 14:30 » in British. The value stays "HH:MM". */
  function french() {
    return (document.documentElement.lang || "").split("-")[0].toLowerCase() === "fr";
  }
  const CLOCK = { hour: "numeric", minute: "2-digit" };
  /* `compact`: a whole hour without its minutes, « 9 AM » — the
   * scheduler's axis, where « 9:00 AM » broke on two lines. French is
   * already compact (« 9h »). */
  function shownTime(hhmm, compact) {
    const m = /^(\d{2}):(\d{2})$/.exec(String(hhmm || ""));
    if (!m) return String(hhmm || "");
    const h = +m[1], mi = +m[2];
    if (french()) return h + "h" + (mi ? m[2] : "");
    const when = new Date(2000, 0, 1, h, mi);
    if (compact && !mi) return format({ hour: "numeric" }).format(when);
    return format(CLOCK).format(when);
  }
  /* What is typed, as "HH:MM" — or "". « 14h30 », « 14:30 », « 14.30 »,
   * « 1430 », « 9 », and a half day in English or in the page's language
   * (« 2:30 PM », « 2 pm », « 2.30p.m. »). */
  function periods() {
    const parts = format(CLOCK).formatToParts(new Date(2000, 0, 1, 15, 0));
    const pm = parts.find(function (p) { return p.type === "dayPeriod"; });
    const am = format(CLOCK).formatToParts(new Date(2000, 0, 1, 3, 0))
      .find(function (p) { return p.type === "dayPeriod"; });
    return { am: am ? foldPeriod(am.value) : "", pm: pm ? foldPeriod(pm.value) : "" };
  }
  function foldPeriod(text) { return String(text).toLowerCase().replace(/[\s.]/g, ""); }
  function typedTime(text) {
    let s = foldPeriod(text);
    if (!s) return "";
    let half = null;
    const local = periods();
    const tail = /(am|pm|a|p)$/.exec(s);
    if (local.pm && s.endsWith(local.pm)) { half = "pm"; s = s.slice(0, -local.pm.length); }
    else if (local.am && s.endsWith(local.am)) { half = "am"; s = s.slice(0, -local.am.length); }
    else if (tail) { half = tail[1][0] === "p" ? "pm" : "am"; s = s.slice(0, -tail[1].length); }
    const m = s.match(/^(\d{1,2})(?:[^\d]?(\d{2}))?[^\d]?$/);
    if (!m) return "";
    let h = +m[1];
    const mi = +(m[2] || 0);
    if (half) {
      if (h < 1 || h > 12) return "";
      h = (h % 12) + (half === "pm" ? 12 : 0);
    }
    if (h > 23 || mi > 59) return "";
    return String(h).padStart(2, "0") + ":" + String(mi).padStart(2, "0");
  }
  /* The empty field's hint, as the browser's own time field writes it:
   * « --h-- » in French, « --:-- -- » in American English. */
  function patternTime() {
    if (french()) return "--h--";
    return format(CLOCK).formatToParts(new Date(2000, 0, 1, 15, 30))
      .map(function (p) { return p.type === "literal" ? p.value : "--"; }).join("");
  }
  /* Does the page's language count its hours by twelve? Never French
   * (the clock above); otherwise `Intl`'s hour cycle — American English
   * yes, British no. The time picker's panel follows it. */
  function twelve() {
    if (french()) return false;
    const cycle = format(CLOCK).resolvedOptions().hourCycle;
    return cycle === "h11" || cycle === "h12";
  }
  /* The two half days as the language names them, « AM » / « PM ». */
  function halves() {
    return [3, 15].map(function (h) {
      const p = format(CLOCK).formatToParts(new Date(2000, 0, 1, h, 0))
        .find(function (x) { return x.type === "dayPeriod"; });
      return p ? p.value : (h < 12 ? "AM" : "PM");
    });
  }
  $bz.times = { shown: shownTime, typed: typedTime, pattern: patternTime,
                twelve: twelve, halves: halves };

  $bz.dates = {
    iso: iso,
    fromIso: fromIso,
    addDays: addDays,
    addMonths: addMonths,
    weekStartOf: weekStartOf,
    typed: typed,
    typedMonth: typedMonth,
    shown: shown,
    shownMonth: shownMonth,
    shownWeek: shownWeek,
    shownLong: shownLong,
    axis: axis,
    pattern: pattern,
    patternMonth: patternMonth,
    /* A typed date, as the first day of its week — the week picker. The
     * field shows the week as a range (« 02/11/2026 – 08/11/2026 »): its
     * first day is what is read. */
    typedWeek: function (text, weekstart) {
      const day = typed(String(text || "").split(/\s[\u2013\u2014-]\s/)[0]);
      return day ? weekStartOf(day, weekstart) : "";
    },
  };
})();


/* calendar.js — <bz-calendar> custom element (stateful day grid). */
// ════════════════════════════════════════════════════════════════════════
// 07 CALENDAR — <bz-calendar> custom element.
//
// A stateful widget as a custom element : the day-grid logic (month
// math, range preview, keyboard grid nav) is genuinely complex and a
// custom element with its own state + attribute observers is the right
// tool — framework-agnostic, survives idiomorph for free (the element
// node persists by id, only observed attributes morph).
//
// The custom element owns its internal state ; configuration lives in
// observed HTML attributes that idiomorph can morph freely. Each
// attribute change triggers ``attributeChangedCallback`` which schedules
// a re-render. Form participation rides a child ``<input type="hidden">``
// onto which the V3 server-action attrs (hx-post / bz-on:change) are
// relocated by Python — the element fires a synthetic ``change`` on it
// whenever the value mutates.
//
// Public DOM API (callable from imperative handlers) :
//   .set(value), .clear(), .focus(), .blur(),
//   .prevMonth(), .nextMonth()
//
// Custom events dispatched :
//   change       — { value: string | [start, end] }
//   month-change — { year: int, month: 1..12 }
//
// Theme classes arrive via a JSON blob in the ``data-bz-theme`` attr ;
// Python's ``Calendar.render()`` composes the slot strings once and
// hands them over.
// ════════════════════════════════════════════════════════════════════════

(function () {
    'use strict';

    if (typeof customElements === 'undefined') return;
    if (customElements.get('bz-calendar')) return;

    // Derived from ``<html lang>`` by locale.js, not written here: a
    // hard-coded table would render "August / MON TUE WED" to every app,
    // whatever its language, and the only handle would be to pass
    // ``month_names=`` AT EVERY MOUNT. The component's explicit lists
    // always win — they arrive as attributes and these defaults only
    // serve their absence.
    function DEFAULT_WEEKDAYS() { return window.$bz.locale.weekdayNames(); }
    function DEFAULT_WEEKDAYS_LONG() {
        return window.$bz.locale.weekdayLongNames();
    }
    function DEFAULT_MONTHS() { return window.$bz.locale.monthNames(); }

    // The date arithmetic lives ONCE, in ``$bz.dates`` (``locale.js``):
    // the pickers' templates and ``calendar.next_month()`` use the same
    // functions.
    var iso = window.$bz.dates.iso;
    var addDays = window.$bz.dates.addDays;
    var weekStartOf = window.$bz.dates.weekStartOf;

    // The header a picker's calendar SHARES with the page is one of the
    // page's parts (``$bz.parts``, ``helpers.js``): its template
    // carries the theme too.

    function parseJSON(value, fallback) {
        if (!value) return fallback;
        try { return JSON.parse(value); } catch (e) { return fallback; }
    }

    // The runtime's one escaper (helpers.js), read when a cell is built.
    function escapeAttr(s) {
        return $bz.helpers.escapeHtml(s);
    }

    class BzCalendar extends HTMLElement {
        // ``$event.target.value`` reads the pick, as on every field: the
        // serialized value the hidden input carries to the form. No
        // setter: writing the observed ``value`` is a pick, and a pick
        // goes through ``set()`` (``_syncHiddenAndFireChange``).
        get value() { return this.getAttribute('value') || ''; }

        static get observedAttributes() {
            return [
                'mode', 'value', 'month', 'weekstart',
                'min', 'max', 'disabled',
                'disabled-dates', 'marks', 'weekday-names', 'month-names',
                'data-bz-theme',
                // ``data-bz-value-path`` / ``data-bz-month-path`` carry the
                // ``$bz.state.X.y`` dotted path the framework wants the
                // custom element to write into when the user picks a
                // value or navigates a month. Without these the binding
                // is one-way only (state → attribute) and the Client
                // playground / Client events cards stay silent.
                'data-bz-value-path',
                'data-bz-month-path',
            ];
        }

        constructor() {
            super();
            this._displayedYear = null;
            this._displayedMonth = null;
            this._hoverDate = null;
            // The start of a range BEING selected, ``range`` mode only.
            // It lives here and NOT in the ``value`` attribute — that is
            // the whole point.
            //
            // A range's first click emits no ``change`` (there is no
            // value to announce yet), so the picker's scope cannot
            // represent that state: it has only ``vstart`` / ``vend``,
            // both empty. Yet the wrapper's mirror ``bz-effect`` treats
            // that scope as the source of truth and pushes ``''`` into
            // the attribute as soon as it runs again — which happens at
            // EVERY HTMX swap, the bridge rescanning the target. As long
            // as the pending start lived in the attribute, that mirror
            // erased it and the second click reopened a range instead of
            // closing it: the field stayed empty and the user clicked
            // endlessly.
            //
            // Here the mirror has nothing left to overwrite — it
            // rewrites ``''`` over ``''``, so no
            // ``attributeChangedCallback``, so the pending state
            // survives. The attribute now carries only what is
            // COMMITTED; it is the sync surface with the outside, not a
            // buffer of transient state. ``_hoverDate`` already had
            // exactly that status, hence the neighbourhood.
            this._pendingStart = null;
            this._initialized = false;
            this._renderScheduled = false;
        }

        connectedCallback() {
            if (this._initialized) return;
            this._initialized = true;

            // Seed the displayed month from the ``month`` attribute or
            // today. We never re-read this from the attribute after
            // init — prev/next clicks mutate it internally and write
            // back to the attribute so external observers see the
            // current displayed month.
            var monthAttr = this.getAttribute('month');
            if (monthAttr) {
                var parts = monthAttr.split('-');
                this._displayedYear = parseInt(parts[0], 10);
                this._displayedMonth = parseInt(parts[1], 10) - 1;
            }
            if (this._displayedYear == null || isNaN(this._displayedYear)) {
                var t = new Date();
                this._displayedYear = t.getFullYear();
                this._displayedMonth = t.getMonth();
            }

            // Bretzel SSR emits the header + weekday row + an EMPTY
            // grid container (``data-bz-cal-grid`` with no children).
            // Fill the grid here on first connect ; subsequent attr
            // changes go through ``attributeChangedCallback`` →
            // ``_render`` which replaces all rendered children.
            this._render();
        }

        attributeChangedCallback(name, oldVal, newVal) {
            if (!this._initialized) return;     // initial attr setting
            if (oldVal === newVal) return;

            // A write of ``value`` that GETS THROUGH is authoritative:
            // it comes either from our own commit, or from outside (the
            // wrapper's mirror, a ``.set()``). In both cases the
            // selection in progress is void. The mirror pushing the same
            // value back does NOT come through here (the ``oldVal ===
            // newVal`` guard above), so a pending state never dies of a
            // mere rescan — which is exactly the invariant sought.
            if (name === 'value') this._pendingStart = null;

            // Sync the displayed month if the external observer (e.g.
            // a ClientBinding) wrote back through ``month=``.
            if (name === 'month' && newVal) {
                var parts = newVal.split('-');
                var y = parseInt(parts[0], 10);
                var m = parseInt(parts[1], 10) - 1;
                if (!isNaN(y) && !isNaN(m) &&
                    (y !== this._displayedYear ||
                     m !== this._displayedMonth)) {
                    this._displayedYear = y;
                    this._displayedMonth = m;
                }
            }

            this._scheduleRender();
        }

        _scheduleRender() {
            // Batch multiple attribute changes (typical when idiomorph
            // morphs several attrs in one tick) into a single render.
            if (this._renderScheduled) return;
            this._renderScheduled = true;
            queueMicrotask(() => {
                this._renderScheduled = false;
                this._render();
            });
        }

        // ── Public DOM API ───────────────────────────────────────────

        set(value) {
            var mode = this.getAttribute('mode') || 'picker';
            var serialized;
            if (mode === 'range' && Array.isArray(value)) {
                serialized = JSON.stringify(value);
            } else if (value == null) {
                serialized = '';
            } else {
                serialized = String(value);
            }
            // Explicit, and not only through
            // ``attributeChangedCallback``: a ``.clear()`` on a calendar
            // whose attribute is already ``''`` triggers no callback, and
            // would otherwise let a pending selection survive a
            // requested clear.
            this._pendingStart = null;
            this.setAttribute('value', serialized);
            this._syncHiddenAndFireChange(serialized, value);
        }

        clear() {
            this.set(null);
        }

        /* Repaint AFTER a morph that erased the body rendered here.
         *
         * The hole: the SSR emits an EMPTY grid
         * container that ``connectedCallback`` fills. When idiomorph
         * morphs the calendar IN PLACE — the refresh of a
         * ``@refreshable`` zone containing it — the children go back to
         * the server version, so empty. ``connectedCallback`` does not
         * run again (the node SURVIVED), nor does
         * ``attributeChangedCallback`` (no attribute changed): nobody
         * refills, and the calendar stays amputated FOR GOOD.
         *
         * The file's header says the configuration lives in attributes
         * "that idiomorph can morph freely". That is true of the
         * ATTRIBUTES; it is not true of the CHILDREN.
         *
         * Called by the ``bz-effect`` the Python sets on the root, and it
         * is indeed ``bz-effect`` and NOT ``bz-init``: the latter is
         * one-shot per NODE (``el._bzInitDone``, which explicitly
         * survives a rebind), yet idiomorph morphs IN PLACE — the node
         * survives, so a ``bz-init`` would never run again. A
         * ``bz-effect`` is disposed then redone by ``bindEl`` at every
         * rescan, and the bridge rescans its target at every swap. Same
         * choice and same reason as SignaturePad's ``_observe()``, which
         * writes in black and white "at every rescan rather than at the
         * bz-init".
         *
         * No new vocabulary, then: no ``hx-preserve``, no home-made morph
         * hook. The day a SECOND custom element exists, that will be the
         * moment to make it a runtime policy — not before.
         *
         * The guard is a DOM measurement, and it is legitimate here: it
         * DERIVES nothing (no display depends on it), it observes a
         * one-off fact — have my children been erased — at the only
         * moment the question arises. Without it, every unrelated swap
         * would repaint the grid and kill the range preview being
         * hovered.
         */
        // Own theme (an inline calendar) or the shared header's.
        _themeJSON() {
            var own = this.getAttribute('data-bz-theme');
            if (own) return own;
            var tpl = window.$bz.parts.template(this.getAttribute('data-bz-part'));
            return tpl ? tpl.getAttribute('data-bz-theme') : null;
        }

        /* Clone the shared header in, the first time the picker opens —
         * and again after a morph took it out (``$bz.parts.fill``).
         * Re-rendered after: a calendar that connected before its
         * template arrived (a zone response with a new header) drew its
         * grid without the theme. */
        ensureChrome() {
            if (window.$bz.parts.fill(this) && this._initialized) this._render();
        }

        rehydrate() {
            if (!this._initialized) return;   // connectedCallback rendra
            var body = this.querySelector('[data-bz-cal-grid]') ||
                       this.querySelector('[data-bz-cal-months]');
            if (!body || body.firstElementChild) return;
            this._render();
        }

        // The picker's selected date (single) or range start, as an ISO
        // string — or null when nothing is picked. Used by ``focus()`` to
        // know where to navigate.
        _selectedDate() {
            var mode = this.getAttribute('mode') || 'picker';
            // ``week`` returns a scalar DATE like ``picker`` (the
            // week's first day), not a pair — so the same reading.
            if (mode === 'picker' || mode === 'week') {
                var v = this.getAttribute('value');
                return (v && /^\d{4}-\d{2}-\d{2}$/.test(v)) ? v : null;
            }
            // A range being selected HAS a start, even if it is not in
            // the attribute yet: ``.focus()`` must navigate to IT, not to
            // the old committed range.
            if (this._pendingStart) return this._pendingStart;
            var arr = parseJSON(this.getAttribute('value') || '', []);
            return (Array.isArray(arr) && arr[0]
                && /^\d{4}-\d{2}-\d{2}$/.test(arr[0])) ? arr[0] : null;
        }

        focus() {
            // If a date is SELECTED but sits outside the displayed month,
            // navigate the grid to it FIRST — otherwise its cell doesn't
            // exist in the DOM and ``.focus()`` silently lands on the
            // current view's first cell (no visible movement). This is
            // what makes ``.focus()`` truly "focus the selected date".
            var self = this;
            var sel = this._selectedDate();
            if (sel) {
                var y = +sel.slice(0, 4);
                var m = +sel.slice(5, 7) - 1;
                if (y !== this._displayedYear || m !== this._displayedMonth) {
                    this._displayedYear = y;
                    this._displayedMonth = m;
                    // Sync the Python header scope + any ``month`` binding.
                    // ``_dispatchMonthChange`` sets the ``month`` attr, which
                    // schedules a microtask ``_render`` — so DON'T render
                    // synchronously here (that cell would be blown away and
                    // focus stolen). Defer the focus one microtask so it runs
                    // AFTER that render rebuilds the grid.
                    this._dispatchMonthChange();
                    queueMicrotask(function () { self._focusBestCell(); });
                    return;
                }
            }
            this._focusBestCell();
        }

        // Focus the SELECTED date, then TODAY, then the first focusable
        // cell in the CURRENT view. ``data-selected`` / ``data-today`` are
        // stamped per cell in ``_render`` ; each falls through gracefully
        // (querySelector → null) to the next candidate.
        _focusBestCell() {
            var target =
                this.querySelector(
                    '[data-bz-day-cell][data-selected="true"]'
                    + ':not([aria-disabled="true"])'
                ) ||
                this.querySelector(
                    '[data-bz-day-cell][data-today="true"]'
                    + ':not([aria-disabled="true"])'
                ) ||
                this.querySelector(
                    '[data-bz-day-cell]:not([aria-disabled="true"])'
                );
            if (target) target.focus();
        }

        blur() {
            var focused = this.querySelector('[data-bz-day-cell]:focus');
            if (focused) focused.blur();
        }

        prevMonth() {
            if (this._displayedMonth === 0) {
                this._displayedMonth = 11;
                this._displayedYear -= 1;
            } else {
                this._displayedMonth -= 1;
            }
            this._dispatchMonthChange();
            this._scheduleRender();
        }

        nextMonth() {
            if (this._displayedMonth === 11) {
                this._displayedMonth = 0;
                this._displayedYear += 1;
            } else {
                this._displayedMonth += 1;
            }
            this._dispatchMonthChange();
            this._scheduleRender();
        }

        // ── Internals ────────────────────────────────────────────────

        _dispatchMonthChange() {
            this.dispatchEvent(new CustomEvent('month-change', {
                detail: {
                    year: this._displayedYear,
                    month: this._displayedMonth + 1,
                },
                bubbles: true,
            }));
            var newIso = this._displayedYear + '-' +
                String(this._displayedMonth + 1).padStart(2, '0') + '-01';
            this._suppressMonthSync = true;
            this.setAttribute('month', newIso);
            this._suppressMonthSync = false;
            // Write back to bound ClientState (``month=binding`` at the
            // Python call site). Without this the Client playground
            // ``ui.text(client.displayed_month)`` echo stays empty.
            this._writeBinding(
                this.getAttribute('data-bz-month-path'), newIso
            );
        }

        _syncHiddenAndFireChange(serializedAttr, detailValue) {
            var hidden = this.querySelector('input[type="hidden"]');
            if (hidden) {
                hidden.value = serializedAttr;
                // ``bubbles: false``: the element's own ``change`` below is
                // THE change. If both bubbled, an ``on_change`` expression
                // would run twice per pick.
                hidden.dispatchEvent(
                    new Event('change', { bubbles: false })
                );
            }
            // Write back to bound ClientState (``value=binding`` at the
            // Python call site). Without this the Client playground
            // ``ui.text(client.picked)`` echo stays empty.
            this._writeBinding(
                this.getAttribute('data-bz-value-path'), detailValue
            );
            this.dispatchEvent(new CustomEvent('change', {
                detail: { value: detailValue },
                bubbles: true,
            }));
        }

        _writeBinding(path, value) {
            // Walk a ``$bz.state.X.y.field`` dotted path and assign
            // ``value`` to the leaf. Bails silently if the runtime
            // store hasn't booted yet (defensive — connectedCallback
            // can race with bootstrap in pathological cases).
            if (!path) return;
            var bz = window.$bz;
            if (!bz || !bz.state) return;
            var parts = path.split('.');
            if (parts[0] === '$bz') parts.shift();
            if (parts[0] === 'state') parts.shift();
            if (parts.length === 0) return;
            var obj = bz.state;
            for (var i = 0; i < parts.length - 1; i++) {
                if (obj[parts[i]] == null) return;
                obj = obj[parts[i]];
            }
            obj[parts[parts.length - 1]] = value;
        }

        _parseConfig() {
            var thisYear = new Date().getFullYear();
            return {
                mode: this.getAttribute('mode') || 'picker',
                value: this.getAttribute('value') || '',
                weekstart:
                    (parseInt(this.getAttribute('weekstart') || '1', 10)
                        % 7 + 7) % 7,
                min: this.getAttribute('min') || '',
                max: this.getAttribute('max') || '',
                disabled: this.hasAttribute('disabled'),
                disabledSet: new Set(
                    parseJSON(this.getAttribute('disabled-dates'), [])
                ),
                // ``marks``: {iso: count}. The accessible name's
                // template arrives RESOLVED from the server — the
                // framework's word table is in Python, and this grid is
                // built here.
                marks: parseJSON(this.getAttribute('marks'), {}),
                markLabel: this.getAttribute('data-bz-mark-label')
                    || '{day}, {n} events',
                weekdayNames: parseJSON(
                    this.getAttribute('weekday-names'), DEFAULT_WEEKDAYS()
                ),
                // The FULL names, for the headers' ``title=``.
                //
                // Empty as soon as the app supplies its own
                // abbreviations: guessing "mer." → "mercredi" would work
                // in French and nowhere else, and a WRONG title is worse
                // than no title. An app that wants its own declares its
                // language and lets the locale do the work.
                weekdayLongNames: this.getAttribute('weekday-names')
                    ? []
                    : DEFAULT_WEEKDAYS_LONG(),
                monthNames: parseJSON(
                    this.getAttribute('month-names'), DEFAULT_MONTHS()
                ),
                theme: parseJSON(this._themeJSON(), {}),
                yearMin: parseInt(
                    this.getAttribute('data-bz-year-min') || (thisYear - 10),
                    10,
                ),
                yearMax: parseInt(
                    this.getAttribute('data-bz-year-max') || (thisYear + 10),
                    10,
                ),
            };
        }

        /* The YEAR grid of ``month`` mode — 12 cells instead of the
         * weekday-row + day-grid pair.
         *
         * It is the component's SECOND kind of grid, and the only place
         * where it does not render days. Everything else (Python header,
         * hidden input, change dispatch, imperative listeners) is shared
         * — hence the early return in ``_render`` rather than a separate
         * class.
         *
         * The bounds compare in ``"YYYY-MM"``, never as dates: the format
         * is zero-padded, so it sorts lexicographically as it sorts
         * chronologically. ``min`` / ``max`` arrive as ``YYYY-MM-DD`` —
         * we truncate them, which makes a PARTIALLY allowed month
         * clickable, and it is intended: a ``min`` on 15 March does not
         * forbid "March".
         */
        _renderMonthGrid(cfg) {
            var theme = cfg.theme || {};
            var cellCls = escapeAttr(theme.month_cell || '');
            var selected = /^\d{4}-\d{2}$/.test(cfg.value) ? cfg.value : '';
            var now = new Date();
            var currentYm = now.getFullYear() + '-' +
                String(now.getMonth() + 1).padStart(2, '0');
            var lo = cfg.min ? cfg.min.slice(0, 7) : '';
            var hi = cfg.max ? cfg.max.slice(0, 7) : '';
            var html = '';
            for (var m = 0; m < 12; m++) {
                var ym = this._displayedYear + '-' +
                    String(m + 1).padStart(2, '0');
                var dis = (lo && ym < lo) || (hi && ym > hi);
                html +=
                    '<button type="button" data-bz-month-cell ' +
                    'class="' + cellCls + '" ' +
                    'data-bz-value="' + ym + '" ' +
                    'data-selected="' + (ym === selected) + '" ' +
                    'data-current="' + (ym === currentYm) + '" ' +
                    'aria-disabled="' + dis + '" ' +
                    'tabindex="' + (dis ? -1 : 0) + '"' +
                    (cfg.disabled ? ' disabled' : '') +
                    '><span>' + escapeAttr(cfg.monthNames[m]) + '</span>' +
                    '</button>';
            }
            return '<div data-bz-cal-months class="' +
                escapeAttr(theme.month_grid || '') + '">' + html + '</div>';
        }

        _render() {
            var cfg = this._parseConfig();
            if (cfg.mode === 'month') {
                this._replaceBody(this._renderMonthGrid(cfg));
                return;
            }
            var label = cfg.monthNames[this._displayedMonth] + ' ' +
                this._displayedYear;
            var rotatedWeekdays = cfg.weekdayNames
                .slice(cfg.weekstart)
                .concat(cfg.weekdayNames.slice(0, cfg.weekstart));
            // Rotated by the SAME number of steps, otherwise a
            // column's title would name the day next to it — worse than
            // nothing.
            var longs = cfg.weekdayLongNames || [];
            var rotatedLong = longs.length === 7
                ? longs.slice(cfg.weekstart).concat(longs.slice(0, cfg.weekstart))
                : [];

            // Range bounds for highlighting
            var rangeStart = '', rangeEnd = '';
            if (cfg.mode === 'range') {
                // The mode guard is load-bearing and stays a SINGLE
                // condition: a ``mode`` attribute that flips while a
                // pending state is alive does not clean it.
                if (this._pendingStart) {
                    // A selection in progress: the pending start beats
                    // the committed value, still the OLD range.
                    rangeStart = this._pendingStart;
                } else if (cfg.value) {
                    var arr = parseJSON(cfg.value, []);
                    if (Array.isArray(arr) && arr.length >= 1) {
                        rangeStart = arr[0] || '';
                        rangeEnd = arr[1] || '';
                    }
                }
            } else if (cfg.mode === 'week' && cfg.value) {
                // A week IS a closed range of 7 days. Rendering it as
                // such reuses ALL of the range mode's band rendering —
                // flat ends on the inner side, tinted middle — instead
                // of inventing a second visual vocabulary for the same
                // idea.
                rangeStart = weekStartOf(cfg.value, cfg.weekstart);
                rangeEnd = addDays(rangeStart, 6);
            }
            var picked = cfg.mode === 'picker' ? cfg.value : '';

            var self = this;
            function isSelected(s) {
                if (cfg.mode === 'picker') return s === picked;
                return s === rangeStart || s === rangeEnd;
            }
            function rangeBounds() {
                if (cfg.mode === 'week') {
                    // No progressive hover here: a week is chosen in a
                    // single click, so its bounds are always known and
                    // complete.
                    return rangeStart
                        ? { lo: rangeStart, hi: rangeEnd }
                        : { lo: null, hi: null };
                }
                if (cfg.mode !== 'range' || !rangeStart) {
                    return { lo: null, hi: null };
                }
                var effEnd = rangeEnd || self._hoverDate;
                if (!effEnd) {
                    return { lo: rangeStart, hi: rangeStart };
                }
                var lo = rangeStart < effEnd ? rangeStart : effEnd;
                var hi = rangeStart < effEnd ? effEnd : rangeStart;
                return { lo: lo, hi: hi };
            }
            function isInRange(s) {
                var b = rangeBounds();
                return b.lo !== null && s > b.lo && s < b.hi;
            }
            function isRangeStart(s) {
                var b = rangeBounds();
                return b.lo !== null && s === b.lo && b.lo !== b.hi;
            }
            function isRangeEnd(s) {
                var b = rangeBounds();
                return b.hi !== null && s === b.hi && b.lo !== b.hi;
            }
            function isCellDisabled(s) {
                if (cfg.disabledSet.has(s)) return true;
                if (cfg.min && s < cfg.min) return true;
                if (cfg.max && s > cfg.max) return true;
                return false;
            }

            // Compute the 6 × 7 grid
            var first = new Date(
                this._displayedYear, this._displayedMonth, 1
            );
            var offset = (first.getDay() - cfg.weekstart + 7) % 7;
            var todayStr = iso(new Date());
            var theme = cfg.theme || {};
            var cellsHTML = '';
            for (var w = 0; w < 6; w++) {
                for (var c = 0; c < 7; c++) {
                    var d = new Date(
                        this._displayedYear, this._displayedMonth,
                        1 + w * 7 + c - offset
                    );
                    var s = iso(d);
                    var day = d.getDate();
                    var inMonth = d.getMonth() === this._displayedMonth;
                    var isDis = isCellDisabled(s);
                    // A mark only lives in the DISPLAYED month: the
                    // grid overflows by six days on either side, and
                    // dotting a 31 July visible from August would make
                    // one read a load that is not that of the month
                    // being looked at.
                    var mark = inMonth ? (cfg.marks[s] | 0) : 0;
                    var markHTML = mark > 0
                        ? '<span class="' + escapeAttr(theme.day_mark || '') +
                          '" aria-hidden="true"></span>'
                        : '';
                    var markLabel = mark > 0
                        ? ' aria-label="' + escapeAttr(
                              cfg.markLabel
                                  .replace('{day}', day)
                                  .replace('{n}', mark)
                          ) + '"'
                        : '';
                    cellsHTML +=
                        '<button type="button" data-bz-day-cell ' +
                        'class="' + escapeAttr(theme.day_cell || '') + '" ' +
                        'data-bz-date="' + s + '" ' +
                        'data-bz-mark="' + mark + '"' + markLabel + ' ' +
                        'data-outside="' + (!inMonth) + '" ' +
                        'data-today="' + (s === todayStr) + '" ' +
                        'data-selected="' + isSelected(s) + '" ' +
                        'data-in-range="' + isInRange(s) + '" ' +
                        'data-range-start="' + isRangeStart(s) + '" ' +
                        'data-range-end="' + isRangeEnd(s) + '" ' +
                        'aria-disabled="' + isDis + '" ' +
                        'tabindex="' + (isDis ? -1 : 0) + '"' +
                        (cfg.disabled ? ' disabled' : '') +
                        '><span>' + day + '</span>' + markHTML + '</button>';
                }
            }

            var chevronCls = escapeAttr(theme.chevron_class || '');
            var navCls = escapeAttr(theme.nav_button || '');
            var labelCls = escapeAttr(theme.month_label || '');
            var weekdayRowCls = escapeAttr(theme.weekday_row || '');
            var weekdayCls = escapeAttr(theme.weekday || '');
            var weekRowCls = escapeAttr(theme.week_row || '');
            var headerCls = escapeAttr(theme.header || '');
            var disabledAttr = cfg.disabled ? ' disabled' : '';

            var weekdaysHTML = '';
            for (var i = 0; i < rotatedWeekdays.length; i++) {
                // ``title`` only if it BRINGS something: the fallback
                // with no Intl renders the same abbreviations on both
                // sides, and a title identical to the visible text is
                // noise for a screen reader.
                var entier = rotatedLong[i];
                var titre = (entier && entier !== rotatedWeekdays[i])
                    ? ' title="' + escapeAttr(entier) + '"'
                    : '';
                weekdaysHTML +=
                    '<div class="' + weekdayCls + '"' + titre + '>' +
                    escapeAttr(rotatedWeekdays[i]) + '</div>';
            }

            // The header (prev/next + month/year selectors) is now
            // rendered by Python using ``ui.dropdown`` + ``ui.icon_button``
            // so it inherits the framework theme. We preserve any
            // ``data-bz-cal-header`` child the Python side emitted and
            // never generate one here.
            var html =
                '<div data-bz-cal-weekdays class="' + weekdayRowCls + '">' +
                  weekdaysHTML +
                '</div>' +
                '<div data-bz-cal-grid class="' + weekRowCls + '">' +
                  cellsHTML +
                '</div>';

            this._replaceBody(html);
        }

        /* Replace the calendar's BODY while preserving the two children
         * that do not come from here: the hidden input (the form-data
         * carrier) and the header rendered by Python
         * (``data-bz-cal-header``, which contains the theme's IconButton
         * and dropdowns).
         *
         * Extracted from ``_render`` when ``month`` mode arrived: it
         * renders a TOTALLY different grid but must preserve exactly the
         * same two children. Copying the loop would have guaranteed that
         * one of the two modes forgets one of them one day.
         */
        _replaceBody(html) {
            var hidden = this.querySelector('input[type="hidden"]');
            var pyHeader = this.querySelector('[data-bz-cal-header]');
            var children = Array.from(this.childNodes);
            for (var i = 0; i < children.length; i++) {
                var child = children[i];
                if (child === hidden) continue;
                if (child === pyHeader) continue;
                this.removeChild(child);
            }
            this.insertAdjacentHTML('beforeend', html);
            this._wireListeners();
        }

        _paintHoverPreview() {
            // Patch only the ``data-in-range`` / ``data-range-start`` /
            // ``data-range-end`` attributes on EXISTING cells. No
            // children removal, no listener re-bind. Used during
            // mouse hover preview to avoid the "cell vanishes under
            // the cursor" bug.
            // This path exists ONLY during a selection in progress: its
            // two callers are behind ``_pendingStart`` (the
            // ``mouseenter`` directly, the ``mouseleave`` through
            // ``_hoverDate`` which is only set there). So it never has
            // to read the attribute — which, since the fix, cannot carry
            // a half-open pair anyway. Testing it here would contradict
            // the rest of the file.
            //
            // The mode guard is implicit: ``_pendingStart`` is only set
            // in ``_handleCellClick``'s ``range`` branch.
            var rangeStart = this._pendingStart;
            if (!rangeStart) return;
            var effEnd = this._hoverDate || '';
            var lo = '', hi = '';
            if (effEnd && effEnd !== rangeStart) {
                lo = rangeStart < effEnd ? rangeStart : effEnd;
                hi = rangeStart < effEnd ? effEnd : rangeStart;
            }
            var cells = this.querySelectorAll('[data-bz-day-cell]');
            cells.forEach(function (cell) {
                var s = cell.getAttribute('data-bz-date');
                var inRange = !!(lo && s > lo && s < hi);
                var isStart = !!(lo && s === lo);
                var isEnd = !!(hi && s === hi && lo !== hi);
                cell.setAttribute('data-in-range', inRange.toString());
                cell.setAttribute('data-range-start', isStart.toString());
                cell.setAttribute('data-range-end', isEnd.toString());
            });
        }

        _wireListeners() {
            var self = this;
            // ``month`` mode: cells of another kind, a click of
            // another nature. Wired BEFORE the day loop because in month
            // mode there is no day cell at all — the loop below runs
            // empty.
            this.querySelectorAll('[data-bz-month-cell]').forEach(function (c) {
                c.onclick = function () {
                    if (c.getAttribute('aria-disabled') === 'true') return;
                    var ym = c.getAttribute('data-bz-value');
                    self.setAttribute('value', ym);
                    self._syncHiddenAndFireChange(ym, ym);
                };
            });
            // Prev / next buttons live in the Python-rendered header
            // (``data-bz-cal-header``). They're ``bz-on:click``
            // handlers that mutate the wrapper's ``year`` / ``month``
            // scope ; nothing to wire here.

            var cells = this.querySelectorAll('[data-bz-day-cell]');
            var mode = this.getAttribute('mode') || 'picker';
            cells.forEach(function (cell) {
                cell.onclick = function () { self._handleCellClick(cell); };
                if (mode === 'range') {
                    // CRITICAL : mouse events must NOT trigger a full
                    // re-render. Each ``_render`` removes + re-inserts
                    // every cell, which means the cell currently under
                    // the cursor is replaced with a fresh DOM node — but
                    // that node never receives a ``mouseenter`` (the
                    // cursor was already over the position when it
                    // appeared), so ``_hoverDate`` freezes at the last
                    // value AND the new cell's ``onclick`` may not have
                    // settled by the time the user clicks. Bug visible
                    // on every range pick : the hover bar gets stuck
                    // mid-flight and the second click vanishes.
                    //
                    // Fix : ``_paintHoverPreview`` patches the data-*
                    // attrs IN PLACE on the existing cells. No DOM
                    // mutation beyond the affected attributes, so the
                    // cursor stays over the SAME node from start to
                    // finish, listeners stay live.
                    cell.onmouseenter = function () {
                        // "Are we between the two clicks?" now reads on
                        // ``_pendingStart`` — the attribute never carries
                        // a half-open pair any more.
                        if (!self._pendingStart) return;
                        self._hoverDate = cell.getAttribute('data-bz-date');
                        self._paintHoverPreview();
                    };
                    cell.onmouseleave = function () {
                        if (self._hoverDate) {
                            self._hoverDate = null;
                            self._paintHoverPreview();
                        }
                    };
                }
            });

            // Listen for the imperative ``bz-set`` / ``bz-prev-month`` /
            // ``bz-next-month`` events dispatched by Python's
            // ``.set()`` / ``.prev_month()`` / ``.next_month()`` methods.
            // Also relay ``focusin``/``focusout`` (which DO bubble from
            // the cells) as ``focus``/``blur`` CustomEvents on the root —
            // this is what makes ``on_focus`` / ``on_blur`` Python
            // kwargs fire when a cell receives keyboard focus, since
            // native focus / blur don't bubble.
            if (!this._wiredImperativeListeners) {
                this._wiredImperativeListeners = true;
                this.addEventListener('bz-set', function (e) {
                    self.set(e.detail && e.detail.value);
                });
                this.addEventListener('bz-prev-month', function () {
                    self.prevMonth();
                });
                this.addEventListener('bz-next-month', function () {
                    self.nextMonth();
                });
                this.addEventListener('focusin', function (e) {
                    // Only relay child focus, not focus on the root
                    // itself (which would be ambiguous and rare).
                    if (e.target !== self) {
                        self.dispatchEvent(new CustomEvent('focus', {
                            detail: { target: e.target },
                            bubbles: true,
                        }));
                    }
                });
                this.addEventListener('focusout', function (e) {
                    if (e.target !== self) {
                        self.dispatchEvent(new CustomEvent('blur', {
                            detail: { target: e.target },
                            bubbles: true,
                        }));
                    }
                });
            }
        }

        _handleCellClick(cell) {
            if (cell.getAttribute('aria-disabled') === 'true') return;
            var s = cell.getAttribute('data-bz-date');
            var mode = this.getAttribute('mode') || 'picker';

            if (mode === 'picker') {
                this.setAttribute('value', s);
                this._syncHiddenAndFireChange(s, s);
                return;
            }

            if (mode === 'week') {
                // Clicking ANY day picks its week, and what comes out
                // is that week's FIRST day — never the clicked day.
                // Without that snapping, two clicks in the same week
                // would produce two different values for the same
                // selection.
                var ws = (parseInt(
                    this.getAttribute('weekstart') || '1', 10
                ) % 7 + 7) % 7;
                var start = weekStartOf(s, ws);
                this.setAttribute('value', start);
                this._syncHiddenAndFireChange(start, start);
                return;
            }

            // range mode — two steps: we open on a PENDING start, we
            // close on the second click. Only the closing touches the
            // ``value`` attribute (cf. ``_pendingStart``).
            var rangeStart = this._pendingStart;

            if (!rangeStart) {
                this._hoverDate = null;
                this._pendingStart = s;
                // Repaint: with no attribute write there is no
                // ``attributeChangedCallback`` left to do it. We go
                // through ``_scheduleRender`` and not ``_render`` to keep
                // the render ASYNCHRONOUS as before — the attribute path
                // already batched in a microtask.
                this._scheduleRender();
                return;
            }

            // Close the range
            var newStart = rangeStart, newEnd = s;
            if (s < rangeStart) {
                newStart = s;
                newEnd = rangeStart;
            }
            this._hoverDate = null;
            this._pendingStart = null;
            var newVal = JSON.stringify([newStart, newEnd]);
            this.setAttribute('value', newVal);
            this._syncHiddenAndFireChange(newVal, [newStart, newEnd]);
        }
    }

    customElements.define('bz-calendar', BzCalendar);
})();


/* file_upload.js — $bz.fileUpload.makeScope factory for ui.file_upload. */
// ════════════════════════════════════════════════════════════════════════
// 08 FILE UPLOAD — bz-data scope factory for <ui.file_upload>.
//
// Why a runtime slab
// ──────────────────
// The component carries enough JS for the inline-bz-data shape to bloat
// every instance. Externalising into one factory means each instance
// just drops ``bz-data="$bz.fileUpload.makeScope({el: $el, …})"``.
//
// Notes : (a) the scope captures its root element (``opts.el``,
// available in the ``bz-data`` expression) — scope methods get no
// ``$root`` / ``$refs`` / ``$dispatch`` magic. (b) signals compare
// by identity, so array mutations REASSIGN (``files = [...]``) and
// per-file updates replace the entry object (keyed by id) so the
// ``bz-for`` rows re-render.
//
// The factory owns :
//
//   1. Drag state (``isDragging``).
//   2. The file list (each entry carries the raw ``File`` + UI status :
//      progress / done / error).
//   3. Client-side validation : ``accept`` filter, ``max_size_mb``,
//      ``max_files``, single vs multi.
//   4. DataTransfer sync with the hidden native ``<input type="file">``
//      so a parent ``<form>`` submit ships exactly what's displayed.
//   5. Image-preview thumbnails via ``URL.createObjectURL`` (revoked on
//      remove to free memory).
//   6. Optional async upload mode (``uploadUrl`` opt-in) via per-file
//      XMLHttpRequest with progress events. ``upload_*`` Alpine events
//      dispatch with the raw ``File`` so a ClientBinding push or a
//      server callable receives identity.
//
// Public DOM event shape (what the framework hooks onto) :
//   change            — files added / removed
//   upload-start      — async POST started for one file
//   upload-progress   — per-file progress %, NOT bridged to the server
//                       (every-tick round-trip would melt the wire)
//   upload-complete   — async POST returned 2xx
//   upload-error      — async POST returned 4xx/5xx or threw
//
// Validation errors live in ``errors`` (array of strings) — rendered
// inline by the component. We don't dispatch them as events ; the panel
// is reactive on the array.
// ════════════════════════════════════════════════════════════════════════

(function () {
    'use strict';

    if (typeof window === 'undefined') return;
    if (!window.$bz) window.$bz = {};
    if (window.$bz.fileUpload) return;

    // A size in the page's language: « 1,5 Mo » in French, « 1.5 MB » in
    // English — ``Intl``'s units.
    function formatSize(bytes) {
        const lang = document.documentElement.lang || undefined;
        const unit = bytes >= 1048576 ? ['megabyte', bytes / 1048576, 1]
            : bytes >= 1024 ? ['kilobyte', bytes / 1024, 0] : ['byte', bytes, 0];
        return new Intl.NumberFormat(lang, {
            style: 'unit', unit: unit[0], unitDisplay: 'short',
            maximumFractionDigits: unit[2],
        }).format(unit[1]);
    }

    // Compare ``file`` against ``accept`` token (mirror of the HTML
    // accept-attribute matching, simplified) :
    //   ".pdf"      → extension match
    //   "image/*"   → MIME family match
    //   "image/png" → exact MIME match
    function matchesToken(file, token) {
        token = token.trim().toLowerCase();
        if (!token) return true;
        if (token.charAt(0) === '.') {
            const idx = file.name.lastIndexOf('.');
            if (idx < 0) return false;
            return file.name.slice(idx).toLowerCase() === token;
        }
        const type = (file.type || '').toLowerCase();
        if (token.endsWith('/*')) {
            return type.startsWith(token.slice(0, -1));
        }
        return type === token;
    }

    function matchesAccept(file, acceptList) {
        if (!acceptList || acceptList.length === 0) return true;
        for (let i = 0; i < acceptList.length; i++) {
            if (matchesToken(file, acceptList[i])) return true;
        }
        return false;
    }

    // Stable id per file entry so ``bz-for`` :key= stays consistent
    // through removals (browsers don't expose a native handle).
    let _uid = 0;
    function nextId() { _uid += 1; return _uid; }

    function isImage(file) {
        return (file.type || '').startsWith('image/');
    }

    // A pasted screenshot reaches the page as ``image.png`` — every one
    // of them: three captures pasted would be three files of the same
    // name. It is renamed after the moment it was pasted; a real file
    // copied from the file manager keeps its own name.
    const GENERIC_PASTE_NAME = /^image\.(\w+)$/i;

    function pad(n) { return String(n).padStart(2, '0'); }

    function pastedName(file, stamp, index) {
        const found = GENERIC_PASTE_NAME.exec(file.name || 'image.png');
        if (!found) return file.name;
        return 'pasted-' + stamp + (index ? '-' + (index + 1) : '') +
            '.' + found[1].toLowerCase();
    }

    // The files a paste carries, or none. ``text/plain`` among the types
    // means the paste is TEXT that happens to come with a picture — Excel
    // cells and Word paragraphs both put a rendering of themselves on the
    // clipboard: the text must land in the field, and nothing be joined.
    function filesOfPaste(data) {
        if (!data || !data.files || data.files.length === 0) return [];
        const types = Array.from(data.types || []);
        if (types.indexOf('text/plain') !== -1) return [];
        const now = new Date();
        const stamp = now.getFullYear() + pad(now.getMonth() + 1) +
            pad(now.getDate()) + '-' + pad(now.getHours()) +
            pad(now.getMinutes()) + pad(now.getSeconds());
        return Array.from(data.files).map((file, i) => {
            const name = pastedName(file, stamp, i);
            return name === file.name ? file : new File([file], name, {
                type: file.type, lastModified: file.lastModified,
            });
        });
    }

    function makeScope(opts) {
        const acceptList = opts.accept
            ? String(opts.accept).split(',').map((s) => s.trim()).filter(Boolean)
            : null;
        const maxSizeMB = opts.maxSizeMB || null;
        const maxFiles = opts.maxFiles || null;
        const multiple = !!opts.multiple;
        const showPreviews = opts.showPreviews !== false;  // default true
        const uploadUrl = opts.uploadUrl || null;
        // The app's texts (``render/texts.py``), English if absent.
        const texts = opts.texts || {};
        const say = (key, english, holes) => String(texts[key] || english)
            .replace(/\{(\w+)\}/g, (m, k) => (holes && k in holes ? holes[k] : m));

        return {
            // Root element captured from the bz-data expression — the
            // V3 replacement for Alpine's $root / $refs.
            _el: opts.el || null,
            // ── State ──────────────────────────────────────────────
            isDragging: false,
            // ``isGlobalDragActive`` flips true when the user is
            // dragging a file ANYWHERE on the page (from the OS).
            // Every dropzone subscribes via ``@dragenter.window`` so
            // the user can see the drop target highlight from any
            // scroll position. Tracked with a counter because
            // ``dragenter`` / ``dragleave`` fire one per element
            // boundary crossed ; the counter reaches 0 only when the
            // drag truly leaves the window.
            isGlobalDragActive: false,
            _globalDragCounter: 0,
            files: [],
            errors: [],

            // ⚠️ No ``destroy()``: the V3 scope engine has NO unmount
            // hook, so such a method would never run. The previews' blob
            // URLs are revoked in the three places that remove a file
            // (single-file replacement, removeFile, clear). Not handled:
            // the previews of a component removed from the DOM with
            // files still in it, which would take a real unmount hook on
            // the runtime side.

            // ── Validation + add ───────────────────────────────────
            handleFiles(fileList) {
                this.errors = [];
                let incoming = Array.from(fileList);
                let sizeRejected = 0;
                let formatRejected = 0;
                let firstReject = '';

                if (!multiple && incoming.length > 1) {
                    this.errors = this.errors.concat([say('only_one', 'Only one file allowed.')]);
                    incoming = [incoming[0]];
                }
                if (!multiple && this.files.length > 0) {
                    // Replace mode — drop the previous one (and its preview).
                    this.files.forEach((f) => {
                        if (f._preview) URL.revokeObjectURL(f._preview);
                    });
                    this.files = [];
                }
                if (multiple && maxFiles) {
                    const room = maxFiles - this.files.length;
                    if (room <= 0) {
                        this.errors = this.errors.concat(
                            [say('max_reached', 'Maximum {max} files reached.', { max: maxFiles })]);
                        return;
                    }
                    if (incoming.length > room) {
                        this.errors = this.errors.concat([
                            say('over_limit', '{count} files skipped — limit {max} reached.',
                                { count: incoming.length - room, max: maxFiles })
                        ]);
                        incoming = incoming.slice(0, room);
                    }
                }

                const accepted = [];
                for (let i = 0; i < incoming.length; i++) {
                    const f = incoming[i];
                    if (maxSizeMB && f.size > maxSizeMB * 1048576) {
                        sizeRejected += 1;
                        if (!firstReject) firstReject = f.name;
                        continue;
                    }
                    if (!matchesAccept(f, acceptList)) {
                        formatRejected += 1;
                        if (!firstReject) firstReject = f.name;
                        continue;
                    }
                    accepted.push(f);
                }

                if ((sizeRejected || formatRejected) && this.errors.length === 0) {
                    const rejected = sizeRejected + formatRejected;
                    let msg;
                    if (rejected === 1) {
                        msg = sizeRejected
                            ? say('too_large', '{name} — exceeds {size}',
                                  { name: firstReject, size: formatSize(maxSizeMB * 1048576) })
                            : say('wrong_format', '{name} — format not supported', { name: firstReject });
                    } else {
                        let reason;
                        if (sizeRejected && !formatRejected) reason = say('reason_too_large', 'too large');
                        else if (formatRejected && !sizeRejected) reason = say('reason_wrong_format', 'wrong format');
                        else reason = say('reason_size_or_format', 'size or format');
                        msg = say('skipped', '{count} files skipped ({reason}).',
                                  { count: rejected, reason: reason });
                    }
                    this.errors = this.errors.concat([msg]);
                }

                // Build the new entries then reassign ``files`` once (V3
                // signals are identity-compared — an in-place push won't
                // re-render the bz-for list).
                const newEntries = [];
                for (let i = 0; i < accepted.length; i++) {
                    const f = accepted[i];
                    newEntries.push({
                        id: nextId(),
                        file: f,
                        name: f.name,
                        size: f.size,
                        sizeLabel: formatSize(f.size),
                        type: f.type,
                        isImage: isImage(f),
                        _preview: (showPreviews && isImage(f))
                            ? URL.createObjectURL(f)
                            : null,
                        progress: 0,
                        status: 'idle',  // idle | uploading | done | error
                        error: '',
                    });
                }
                this.files = this.files.concat(newEntries);

                this.syncInput();
                this.dispatch('change', {
                    files: this.files.map((e) => e.file),
                    count: this.files.length,
                });

                if (uploadUrl) {
                    for (let i = 0; i < accepted.length; i++) {
                        // Find the entry we just pushed for this file.
                        const entry = this.files.find((e) => e.file === accepted[i]);
                        if (entry) this.uploadOne(entry.id);
                    }
                }
            },

            // Replace one entry (keyed by id) with a patched copy so the
            // keyed bz-for row re-renders (V3 entries aren't deep-reactive).
            _patchFile(id, patch) {
                this.files = this.files.map(
                    (e) => (e.id === id ? Object.assign({}, e, patch) : e),
                );
            },

            // ── Remove ─────────────────────────────────────────────
            removeFile(entry, evt) {
                if (evt) evt.preventDefault();
                if (entry._preview) URL.revokeObjectURL(entry._preview);
                if (entry._xhr) {
                    try { entry._xhr.abort(); } catch (e) {}
                }
                this.files = this.files.filter((e) => e.id !== entry.id);
                this.errors = [];
                this.syncInput();
                this.dispatch('change', {
                    files: this.files.map((e) => e.file),
                    count: this.files.length,
                });
            },

            // Every file out at once — ``ui.message_input`` empties its
            // box once the message has left (message_input.js).
            clear() {
                this.files.forEach((e) => {
                    if (e._preview) URL.revokeObjectURL(e._preview);
                });
                this.files = [];
                this.errors = [];
                this.syncInput();
                this.dispatch('change', { files: [], count: 0 });
            },

            // ── DataTransfer → native input ────────────────────────
            syncInput() {
                if (typeof DataTransfer === 'undefined') return;  // very old browsers
                const dt = new DataTransfer();
                this.files.forEach((entry) => dt.items.add(entry.file));
                const native = this._el && this._el.querySelector('input[type=file]');
                if (native) native.files = dt.files;
            },

            // ── Native input change passthrough ────────────────────
            onNativeChange(evt) {
                if (!evt.isTrusted) return;  // we set .files programmatically too
                if (evt.target.files && evt.target.files.length > 0) {
                    this.handleFiles(evt.target.files);
                }
            },

            // ── Drag-drop (instance-level) ─────────────────────────
            onDragEnter(evt) { evt.preventDefault(); this.isDragging = true; },
            onDragOver(evt)  { evt.preventDefault(); this.isDragging = true; },
            onDragLeave(evt) { evt.preventDefault(); this.isDragging = false; },
            onDrop(evt) {
                evt.preventDefault();
                this.isDragging = false;
                // Drop also tears down the global highlight on every
                // dropzone — the drag is over.
                this._globalDragCounter = 0;
                this.isGlobalDragActive = false;
                if (evt.dataTransfer && evt.dataTransfer.files) {
                    this.handleFiles(evt.dataTransfer.files);
                }
            },

            // ── Drag-drop (window-level, "page is the target") ─────
            // The handlers below subscribe to ``dragenter`` /
            // ``dragleave`` / ``drop`` on the window, so a drag from
            // the OS — anywhere on the page — surfaces this dropzone
            // as a candidate target. ``isGlobalDragActive`` flips
            // true while the drag is in flight ; the wrapper's
            // ``:class`` adds ``dropzone_global_drag`` (ring + glow)
            // so the user can see where to drop.
            //
            // ``dragenter`` / ``dragleave`` fire one PER element
            // boundary crossed (drag over a button → dragenter,
            // drag off it → dragleave). We use a counter to know
            // when the drag truly entered or left the window.
            onWindowDragEnter(evt) {
                if (!this._dragCarriesFiles(evt)) return;
                this._globalDragCounter += 1;
                this.isGlobalDragActive = true;
            },
            onWindowDragLeave(evt) {
                if (!this._dragCarriesFiles(evt)) return;
                this._globalDragCounter -= 1;
                if (this._globalDragCounter <= 0) {
                    this._globalDragCounter = 0;
                    this.isGlobalDragActive = false;
                }
            },
            onWindowDrop() {
                this._globalDragCounter = 0;
                this.isGlobalDragActive = false;
            },

            _dragCarriesFiles(evt) {
                // ``dataTransfer.types`` is a DOMStringList containing
                // 'Files' for OS-originated drags ; for in-page drags
                // it'll be 'text/plain' or similar. Filter so we don't
                // highlight on a Notion-style block drag.
                const types = evt.dataTransfer && evt.dataTransfer.types;
                if (!types) return false;
                for (let i = 0; i < types.length; i++) {
                    if (types[i] === 'Files') return true;
                }
                return false;
            },

            // ── Paste (``paste=True``) ─────────────────────────────
            // Called from the root's ``bz-init``, so ``this`` is the
            // reactive scope. The listener sits on the enclosing
            // ``<form>`` — a paste fires on the FOCUSED element, and the
            // one focused is the field the person writes in, not the
            // picker — or on the root when there is no form. A paste
            // that carries files adds them as a pick would; one that
            // carries text is left to the field (``filesOfPaste``).
            // No unmount hook in V3 (cf. above): a root that has left
            // the DOM — a zone redrawn — unsubscribes at its next paste.
            // The form around the field has sent its files: the list
            // empties. Otherwise a sent file would keep its pill under the
            // button, and a second send would ship it again. Only a
            // SUCCESSFUL send of that form: a refusal
            // (4xx, 5xx) keeps what was picked. Same unsubscribe as the
            // paste below, at the next send after the root has left.
            watchForm() {
                const self = this;
                const root = self._el;
                const form = root && root.closest('form');
                if (!form) return;
                function onSent(evt) {
                    if (!root.isConnected) {
                        form.removeEventListener('htmx:afterRequest', onSent);
                        return;
                    }
                    const d = evt.detail || {};
                    if (d.elt === form && d.successful && self.files.length) self.clear();
                }
                form.addEventListener('htmx:afterRequest', onSent);
            },

            watchPaste() {
                const self = this;
                const root = self._el;
                if (!root) return;
                const host = root.closest('form') || root;
                function onPaste(evt) {
                    if (!root.isConnected) {
                        host.removeEventListener('paste', onPaste);
                        return;
                    }
                    const native = root.querySelector('input[type=file]');
                    if (native && native.disabled) return;
                    const pasted = filesOfPaste(evt.clipboardData);
                    if (pasted.length === 0) return;
                    evt.preventDefault();
                    self.handleFiles(pasted);
                }
                host.addEventListener('paste', onPaste);
            },

            // ── Browse-trigger click (delegated to native input) ──
            openPicker() {
                const native = this._el && this._el.querySelector('input[type=file]');
                if (native) native.click();
            },

            // ── Async upload (one file, keyed by id) ───────────────
            uploadOne(id) {
                const entry0 = this.files.find((e) => e.id === id);
                if (!entry0) return;
                const file = entry0.file;
                this._patchFile(id, { status: 'uploading', progress: 0, error: '' });
                this.dispatch('upload-start', { file: file });

                const xhr = new XMLHttpRequest();
                this._patchFile(id, { _xhr: xhr });
                xhr.upload.addEventListener('progress', (e) => {
                    if (e.lengthComputable) {
                        const pct = Math.round((e.loaded / e.total) * 100);
                        this._patchFile(id, { progress: pct });
                        this.dispatch('upload-progress', { file: file, progress: pct });
                    }
                });
                xhr.addEventListener('load', () => {
                    if (xhr.status >= 200 && xhr.status < 300) {
                        this._patchFile(id, { status: 'done', progress: 100 });
                        this.dispatch('upload-complete', {
                            file: file,
                            response: xhr.responseText,
                            status: xhr.status,
                        });
                    } else {
                        this._patchFile(id, { status: 'error', error: 'HTTP ' + xhr.status });
                        this.dispatch('upload-error', {
                            file: file,
                            error: 'HTTP ' + xhr.status,
                            status: xhr.status,
                        });
                    }
                });
                xhr.addEventListener('error', () => {
                    this._patchFile(id, { status: 'error', error: say('network_error', 'Network error') });
                    this.dispatch('upload-error', {
                        file: file,
                        error: say('network_error', 'Network error'),
                        status: 0,
                    });
                });
                const form = new FormData();
                form.append('file', file, entry0.name);
                xhr.open('POST', uploadUrl);
                // Bretzel's CSRF middleware is ALWAYS active and
                // protects every POST outside ``/_bretzel/action/*``.
                // Without this header, the async upload takes a 403 — so
                // ``upload_url=`` could work in NO app, the framework
                // rejecting its own component. Same source and same
                // header as the bridge (bridge.js).
                if ($bz._csrf) {
                    xhr.setRequestHeader('X-Bretzel-CSRF', $bz._csrf);
                }
                xhr.send(form);
            },

            // ── Dispatch helper — kebab DOM events on the root ─────
            dispatch(name, detail) {
                if (!this._el) return;
                this._el.dispatchEvent(new CustomEvent(name, {
                    detail: detail,
                    bubbles: true,
                }));
            },
        };
    }

    window.$bz.fileUpload = {
        makeScope: makeScope, formatSize: formatSize, filesOfPaste: filesOfPaste,
    };
})();


/* notification.js — toast stack manager (bz-data scope factory). */
// ════════════════════════════════════════════════════════════════════════
// 09 NOTIFICATION — toast stack data manager.
//
// The user calls ``ui.notification("Saved!")`` from a handler ; the
// server rides the payload back in a ``<bz-patch>{"patches":
// {"_notifications":[…]}}`` block, the bridge forwards each to
// ``$bz.notify`` (→ a ``bz:notify`` DOM event), and the toaster
// container (pre-rendered in the shell) catches it and pushes the
// toast into its own ``bz-data`` scope.
//
// V3 vs V2 : no ``Alpine.store`` — the toaster owns its state in a
// bz-data scope (``stacks``, one bucket per position). The factory
// here builds that scope. Reassignment (not in-place push/splice) so
// the ``bz-for`` over each bucket re-renders (V3 signals are
// identity-compared). Enter animation is a CSS keyframe fired on mount ;
// leave is IMMEDIATE — what disappears does not linger. The neighbours
// still glide into the freed slot (``:flip``).
//
// Variant / icon / position normalisation reads the theme blob the
// shell injects on ``window.$bz_theme.notification``.
// ════════════════════════════════════════════════════════════════════════

(function () {
  "use strict";
  const $bz = window.$bz;
  if (!$bz) return;


  function genId() {
    return "bz-toast-" + Date.now() + "-" + Math.random().toString(36).slice(2, 8);
  }

  function makeScope() {
    const THEME = (window.$bz_theme && window.$bz_theme.notification) || {};
    const positions = Object.keys(THEME.positions || { "top-right": 1 });
    const variants = Object.keys(THEME.variants || { info: 1 });
    const icons = THEME.icons || {};

    function emptyStacks() {
      const out = {};
      for (const p of positions) out[p] = [];
      return out;
    }

    function normalise(opts) {
      opts = opts || {};
      const variant = variants.indexOf(opts.variant) >= 0 ? opts.variant : "info";
      let icon;
      if (opts.icon === "" || opts.icon === false) icon = null;
      else if (typeof opts.icon === "string" && opts.icon) icon = opts.icon;
      else icon = icons[variant] || null;
      return {
        id: opts.id || genId(),
        message: String(opts.message || ""),
        title: opts.title || null,
        variant: variant,
        position: positions.indexOf(opts.position) >= 0 ? opts.position : "top-right",
        duration_ms: typeof opts.duration_ms === "number" ? opts.duration_ms : 4000,
        dismissible: opts.dismissible !== false,
        icon: icon,
      };
    }

    return {
      stacks: emptyStacks(),

      show(opts) {
        const toast = normalise(opts);
        const pos = toast.position;
        const next = Object.assign({}, this.stacks);
        next[pos] = next[pos].concat([toast]);
        this.stacks = next;
        if (toast.duration_ms > 0) {
          const self = this;
          setTimeout(function () {
            self.dismiss(toast.id);
          }, toast.duration_ms);
        }
        return toast.id;
      },

      dismiss(id) {
        // At once: a toast that leaves does not linger. A
        // double dismiss (click + auto-timeout) finds nothing the second
        // time — ``_remove`` is a no-op on an unknown id.
        this._remove(id);
      },

      _remove(id) {
        const next = {};
        let changed = false;
        for (const p of Object.keys(this.stacks)) {
          const before = this.stacks[p];
          next[p] = before.filter(function (t) {
            return t.id !== id;
          });
          if (next[p].length !== before.length) changed = true;
        }
        if (changed) this.stacks = next;
      },
    };
  }

  $bz.notification = { makeScope: makeScope };
})();


/* charts.js — shared chart tooltip + legend scope factories. */
// ════════════════════════════════════════════════════════════════════════
// 10 CHARTS — shared tooltip for bar / line / pie / sparkline.
//
// Why a runtime slab at all
// ─────────────────────────
// The charts are server-rendered SVG ; the framework already paints the
// silhouette on first paint with zero JS. What we DON'T render server-
// side is the floating tooltip — its position depends on the cursor
// (mouse) or the trigger rect (keyboard focus), neither of which Python
// can know. So this slab :
//
// 1. Shows the PAGE's one tooltip panel (``tip.js``, ``#bz-tip``) on
//    the hovered data point. A panel of its own, with the tooltip's look
//    copied as classes, would ignore the app's
//    ``Theme(components={"tooltip": …})``.
// 2. Exposes ``$bz.charts.tooltipScope()`` — a bz-data scope factory
//    every chart wrapper drops on its root. Bars / segments / points
//    handle ``bz-on:mouseenter="show($event)"`` / ``bz-on:mouseleave="hide()"``.
//    The factory reads ``data-bz-display`` off ``event.currentTarget``,
//    formats it server-side (so there's nothing for the JS to know about
//    locale / units), and positions the panel above the trigger.
//
// V3 : ``toggleSeries`` REASSIGNS the ``visible`` array (V3 signals are
// identity-compared — an in-place ``visible[i] = …`` wouldn't re-render
// the ``bz-show``'d paths/dots/legend slots).
//
// Public DOM API
// ──────────────
//   $bz.charts.tooltipScope() → bz-data scope object (bar / pie / sparkline)
//   $bz.charts.lineScope()    → bz-data scope tracking ``active`` for the
//                               line-chart hover state + per-series
//                               ``visible`` toggles.
//   $bz.charts.scatterScope() → bz-data scope (per-dot tooltip + legend)
//   $bz.charts.barScope()     → bz-data scope (per-bar tooltip + legend,
//                               grouped bars only — a stack with a hole lies)
//
// Every scope also carries ``key`` / ``unkey``: the chart is ONE tab
// stop, the arrows walk its points, Enter clicks one, Escape leaves.
//   $bz.charts.hide()         → force-hide (e.g. on htmx swap)
// ════════════════════════════════════════════════════════════════════════

(function () {
    'use strict';

    var $bz = window.$bz;
    if (!$bz) return;

    var hideTimer = null;
    // Whether the shared panel is showing a CHART's label — the swap
    // guard and the hide must not close a tooltip someone else opened.
    var owns = false;
    var ZERO = { left: 0, right: 0, top: 0, bottom: 0, width: 0, height: 0 };

    // Open the page's panel on a data point. ``rectFn`` is re-read by
    // ``floating`` on every scroll / resize, so the panel stays glued to
    // its point — the job an ``activeReposition`` closure did here by
    // hand. Above the point, flipped below when it hugs the top edge:
    // ``floating``'s ``top`` placement. ``whitespace-pre-line``: a label
    // is pre-formatted server-side, on several lines.
    function openAt(rectFn, label) {
        clearTimeout(hideTimer);
        if (!$bz.tip) return;
        owns = true;
        $bz.tip.open(
            { getBoundingClientRect: function () { return rectFn() || ZERO; } },
            { text: label, position: 'top', extraClass: 'whitespace-pre-line' }
        );
    }

    // Viewport rect for an anchor element — a pie wedge's ``data-bz-ax/ay``
    // centroid (SVG-space → screen via the CTM) when present, else the
    // ``rect`` / ``circle`` bounding box. ``null`` when the element can't
    // be resolved (e.g. a path with no centroid attrs) so callers fall
    // back to the cursor.
    function rectForAnchor(anchor) {
        if (!anchor) return null;
        var ax = anchor.getAttribute('data-bz-ax');
        var ay = anchor.getAttribute('data-bz-ay');
        var svg = anchor.ownerSVGElement;
        var ctm = svg && svg.getScreenCTM && svg.getScreenCTM();
        if (ax !== null && ay !== null && ctm) {
            var pt = svg.createSVGPoint();
            pt.x = parseFloat(ax);
            pt.y = parseFloat(ay);
            var screen = pt.matrixTransform(ctm);
            return {
                left: screen.x, right: screen.x,
                top: screen.y, bottom: screen.y,
                width: 0, height: 0,
            };
        }
        var tag = anchor.tagName && anchor.tagName.toLowerCase();
        if (tag === 'rect' || tag === 'circle') {
            return anchor.getBoundingClientRect();
        }
        return null;
    }

    function hideTooltip() {
        if (!owns) return;
        // Tiny grace period so a fast cursor leaving one bar and entering
        // the next doesn't flash the tooltip in/out — the next ``show``
        // cancels the pending hide.
        clearTimeout(hideTimer);
        hideTimer = setTimeout(function () {
            owns = false;
            if ($bz.tip) $bz.tip.close();
        }, 60);
    }

    // The hovered element and its pre-formatted label, or null when there
    // is nothing to show — each caller then anchors where it genuinely
    // differs (bar-fill lookup, dot rect, line-column band).
    function labelled(event) {
        var el = event && event.currentTarget;
        if (!el) return null;
        var label = el.getAttribute('data-bz-display');
        return label ? { el: el, label: label } : null;
    }

    function tooltipScope() {
        return scope({
            show: function (event) {
                var hit = labelled(event);
                if (!hit) return;
                // Bar charts widen the hit target to the whole column via
                // a transparent ``.bz-bar-hit`` overlay that spans the
                // plot. Anchoring on the overlay itself would float the
                // tooltip at the top of the column ; anchor on the sibling
                // ``.bz-bar-fill`` instead so it lands on the data point.
                var anchor = hit.el;
                if (anchor.classList && anchor.classList.contains('bz-bar-hit')) {
                    var fill = anchor.parentNode &&
                        anchor.parentNode.querySelector('.bz-bar-fill');
                    if (fill) anchor = fill;
                }
                // Anchor on the data point : a bar's ``.bz-bar-fill``, a
                // scatter/line dot, or a pie wedge's ``data-bz-ax/ay``
                // centroid (a ``<path>`` bbox would float the panel at the
                // pie's centre). ``rectForAnchor`` resolves all three.
                if (rectForAnchor(anchor)) {
                    openAt(function () { return rectForAnchor(anchor); }, hit.label);
                } else {
                    // Last-resort fallback (path with no centroid attrs) —
                    // pin to the cursor.
                    var cursor = {
                        left: event.clientX, right: event.clientX,
                        top: event.clientY, bottom: event.clientY,
                        width: 0, height: 0,
                    };
                    openAt(function () { return cursor; }, hit.label);
                }
            },
            hide: function () { hideTooltip(); },
        });
    }

    // Force-hide on htmx swap so a refresh that replaces the chart
    // doesn't leave the tooltip pointing at thin air.
    document.addEventListener('htmx:before-swap', function () {
        if (!owns) return;
        owns = false;
        clearTimeout(hideTimer);
        if ($bz.tip) $bz.tip.close();
    });

    // The keyboard, shared by every chart scope. The chart is ONE tab stop
    // (21 bars are not 21 tabs, as Highcharts' module does it); the arrows
    // walk the points that carry a tooltip — those of a hidden series have
    // no box and are skipped — and each step REPLAYS the hover, so the
    // tooltip, the line's crosshair and the bar's spotlight follow with no
    // second code path. Enter replays the click (``on_item_click``),
    // Escape and leaving the chart close.
    function keyboard() {
        return {
            kbd: -1,
            key: function (event) {
                // A legend button inside the chart keeps its own keys.
                if (event.target !== event.currentTarget) return;
                var points = Array.prototype.filter.call(
                    event.currentTarget.querySelectorAll('[data-bz-display]'),
                    function (el) { return el.getClientRects().length > 0; });
                if (!points.length) return;
                var k = event.key, at = this.kbd;
                if (k === 'ArrowRight' || k === 'ArrowDown') at = Math.min(at + 1, points.length - 1);
                else if (k === 'ArrowLeft' || k === 'ArrowUp') at = Math.max(at - 1, 0);
                else if (k === 'Home') at = 0;
                else if (k === 'End') at = points.length - 1;
                else if (k === 'Enter' || k === ' ') {
                    if (points[at]) points[at].dispatchEvent(new MouseEvent('click', { bubbles: true }));
                    if (k === ' ') event.preventDefault();
                    return;
                } else if (k === 'Escape') { this.unkey(event); return; }
                else return;
                event.preventDefault();
                if (points[this.kbd]) points[this.kbd].dispatchEvent(new MouseEvent('mouseleave'));
                this.kbd = at;
                points[at].dispatchEvent(new MouseEvent('mouseenter'));
            },
            unkey: function (event) {
                var root = event && event.currentTarget;
                var points = root ? root.querySelectorAll('[data-bz-display]') : [];
                Array.prototype.forEach.call(points, function (el) {
                    el.dispatchEvent(new MouseEvent('mouseleave'));
                });
                this.kbd = -1;
                hideTooltip();
            },
        };
    }

    // One scope object out of the pieces: the keyboard is in every one.
    function scope() {
        var out = keyboard();
        for (var i = 0; i < arguments.length; i++) {
            var part = arguments[i];
            for (var name in part) {
                if (Object.prototype.hasOwnProperty.call(part, name)) out[name] = part[name];
            }
        }
        return out;
    }

    function parseJSON(attr, fallback) {
        if (!attr) return fallback;
        try { return JSON.parse(attr); } catch (e) { return fallback; }
    }

    // Legend visibility, shared by every multi-series chart scope.
    // ``visible[i]`` drives ``bz-show`` on the path / dots / markers the
    // server rendered with series index ``i``.
    //
    // Two load-bearing details live here : the "never toggle the last
    // one off" guard (an all-hidden chart reads as broken — Vercel and
    // Stripe ship the same rule), and the REASSIGN in toggleSeries (V3
    // signals are identity-compared, so an in-place ``visible[i] = …``
    // would not re-render).
    function seriesVisibility(nSeries) {
        var visible = [];
        for (var i = 0; i < nSeries; i++) visible.push(true);
        return {
            visible: visible,
            isVisible: function (i) { return !!this.visible[i]; },
            toggleSeries: function (i) {
                if (i < 0 || i >= this.visible.length) return;
                var on = this.visible.filter(Boolean).length;
                if (this.visible[i] && on <= 1) return;
                this.visible = this.visible.map(function (v, j) {
                    return j === i ? !v : v;
                });
            },
        };
    }

    function lineScope(opts) {
        var nSeries = (opts && opts.n_series) || 1;
        var vis = seriesVisibility(nSeries);
        return scope({
            active: -1,
            visible: vis.visible,
            isVisible: vis.isVisible,
            // Full-column hover (single + multi). Sets the ``active``
            // index (drives the crosshair + per-series active dots via
            // bz-attr) AND positions the shared floating tooltip above
            // the active column. The hit rect (``event.currentTarget``)
            // spans the plot vertically, so its screen bbox gives us
            // both the column's screen-x band and the plot top —
            // scale-robust, no SVG CTM. ``data-bz-anchor-x`` is the
            // data-x's fraction within the rect, mapped onto that band.
            onHover: function (event, idx) {
                this.active = idx;
                var hit = labelled(event);
                // Nothing to show (no target, or a column with no
                // label) → hide.
                if (!hit) { hideTooltip(); return; }
                var el = hit.el;
                // Zero-size anchor at (column-x, plot-top) → the tooltip
                // floats above the plot, never over the curve. ``bottom
                // = r.top`` so the near-top flip lands just inside the
                // plot instead of at the far plot bottom. Recomputed from
                // the live hit rect so scroll / resize keep it glued.
                var lineRect = function () {
                    var r = el.getBoundingClientRect();
                    var frac = parseFloat(el.getAttribute('data-bz-anchor-x'));
                    if (isNaN(frac)) frac = 0.5;
                    var ax = r.left + frac * r.width;
                    return {
                        left: ax, right: ax, top: r.top, bottom: r.top,
                        width: 0, height: 0,
                    };
                };
                openAt(lineRect, hit.label);
            },
            onLeave: function () { this.active = -1; hideTooltip(); },
            // The shared toggle, plus line's own extra : drop the hover
            // index when the series it points at goes hidden. Wrapped
            // rather than re-copied, so the guard and the reassign stay
            // in one place.
            toggleSeries: function (i) {
                vis.toggleSeries.call(this, i);
                if (!this.visible[i]) this.active = -1;
            },
        });
    }

    function scatterScope(opts) {
        var vis = seriesVisibility((opts && opts.n_series) || 1);
        return scope({
            visible: vis.visible,
            isVisible: vis.isVisible,
            toggleSeries: vis.toggleSeries,
            // Floating tooltip on per-dot hover. Each ``<circle>``
            // dot carries ``data-bz-display`` ; the circle's
            // ``getBoundingClientRect()`` is tight (``r × 2`` box)
            // so anchoring above it lands cleanly on the dot.
            show: function (event) {
                var hit = labelled(event);
                if (!hit) return;
                openAt(function () { return hit.el.getBoundingClientRect(); }, hit.label);
            },
            hide: function () { hideTooltip(); },
        });
    }

    // Grouped bars with a clickable legend: the bar tooltip, plus the
    // series' visibility (a hidden series leaves its slot empty in each
    // group — the others keep their place and their height).
    function barScope(opts) {
        var vis = seriesVisibility((opts && opts.n_series) || 1);
        var bars = tooltipScope();
        return scope(bars, {
            visible: vis.visible,
            isVisible: vis.isVisible,
            toggleSeries: vis.toggleSeries,
        });
    }

    $bz.charts = {
        tooltipScope: tooltipScope,
        lineScope: lineScope,
        scatterScope: scatterScope,
        barScope: barScope,
        hide: hideTooltip,
    };
})();


/* number_input.js — shared scope for the NumberInput component.
 *
 * The full client logic (precision, clamp, snap-to-step, draft-vs-value,
 * nudge, change emission) lives here ONCE rather than INLINE in every
 * instance's bz-data attribute ; each instance emits only its state +
 * ``_read``/``_write`` so the same methods serve both modes :
 *
 *   bz-data="{...$bz.numberInput.scope, value: 42,
 *             _read(){return this.value}, _write(v){this.value=v},
 *             _min: null, _max: null, _step: 1, _draft: "42",
 *             _focused: false, _carrier: null, _precCache: undefined}"
 *
 * Value access goes through ``this._read()`` / ``this._write(v)`` so the
 * SAME methods cover local mode (a ``value`` signal field) and binding
 * mode (a ``$bz.state.<path>`` store cell) — the per-instance scope
 * supplies the right pair. (We can't bake a live ``get value()`` into
 * the literal : ``scope.absorb`` reads every key once, freezing getters —
 * cf. traps.md.)
 */
(function () {
  "use strict";
  const $bz = (window.$bz = window.$bz || {});

  /* The decimal mark of the page's language — « 2,5 » in French. The
   * field SHOWS its number with it and reads it back; the value carried
   * in the form stays « 2.5 ». */
  const marks = {};
  function decimalMark() {
    const tag = document.documentElement.lang || "";
    if (!(tag in marks)) {
      const part = new Intl.NumberFormat(tag || undefined).formatToParts(1.5)
        .find(function (p) { return p.type === "decimal"; });
      marks[tag] = part ? part.value : ".";
    }
    return marks[tag];
  }

  $bz.numberInput = {
    scope: {
      // Decimal precision implied by the step (step=0.01 → 2), memoised
      // on ``_precCache``. Guards float drift in the displayed value.
      _precision: $bz.num.cachedPrecision,
      _round(v) {
        const p = this._precision();
        return p > 0 ? Number(v.toFixed(p)) : v;
      },
      _clamp(v) {
        let out = v;
        if (this._min !== null) out = Math.max(this._min, out);
        if (this._max !== null) out = Math.min(this._max, out);
        return this._round(out);
      },
      _snap(v) {
        const base = this._min !== null ? this._min : 0;
        return this._round(Math.round((v - base) / this._step) * this._step + base);
      },
      _atMin() {
        const v = this._read();
        return this._min !== null && v != null && Number(v) <= this._min;
      },
      _atMax() {
        const v = this._read();
        return this._max !== null && v != null && Number(v) >= this._max;
      },
      // A number as the field shows it: the language's decimal mark.
      _shown(n) {
        return String(n).replace(".", decimalMark());
      },
      _displayValue() {
        const v = this._read();
        if (v == null || v === "") return "";
        return this._shown(this._round(Number(v)));
      },
      // The value the form carries, whatever the language: « 2.5 ».
      _canonical() {
        const v = this._read();
        if (v == null || v === "") return "";
        return String(this._round(Number(v)));
      },
      // What was typed, as a number's text: the language's mark read as
      // the point — a comma elsewhere is a thousands mark, dropped.
      _typed(text) {
        const s = String(text || "").trim().replace(/\s/g, "");
        return decimalMark() === "," ? s.replace(/,/g, ".") : s.replace(/,/g, "");
      },
      _commitDraft(final) {
        const raw = this._typed(this._draft);
        if (raw === "" || raw === "-" || raw === ".") {
          if (final) { this._write(null); this._emitChange(); }
          return;
        }
        const n = Number(raw);
        if (isNaN(n)) {
          if (final) this._draft = this._displayValue();
          return;
        }
        if (final) {
          const clamped = this._snap(this._clamp(n));
          this._write(clamped);
          this._draft = this._shown(clamped);
          this._emitChange();
        } else {
          this._write(this._round(n));
        }
      },
      _nudge(delta) {
        const cur = this._read() == null ? 0 : Number(this._read());
        const next = this._snap(this._clamp(cur + delta));
        this._write(next);
        if (this._focused) this._draft = this._shown(next);
        this._emitChange();
      },
      _setValue(raw) {
        const n = Number(raw);
        if (raw == null || raw === "" || isNaN(n)) {
          this._write(null);
          this._draft = "";
          this._emitChange();
          return;
        }
        const next = this._snap(this._clamp(n));
        this._write(next);
        this._draft = this._shown(next);
        this._emitChange();
      },
      // Dispatch a synthetic ``bzchange`` from the captured <input> so a
      // relocated ``on_change`` (bz-on:bzchange / hx-trigger="bzchange")
      // observes the COMMITTED value. We deliberately do NOT reuse the
      // native ``change`` event : the browser fires its own ``change`` on
      // blur, BEFORE we reformat the draft, carrying the raw typed text —
      // routing observers onto our private event sidesteps that dirty
      // dispatch (and the resulting double-fire). Deferred a microtask so
      // the signal flush (which also rides queueMicrotask, FIFO-ordered
      // before this one) lands the canonical value on the DOM input first.
      // ``bzchange``, not the native ``change`` : the inner input fires
      // ``change`` on its own while the user types, so a user
      // ``on_change=`` must not see it.
      _emitChange() { $bz.helpers.emitChange(this._carrier, "bzchange"); },
    },
  };
})();


/* slider.js — shared scope for the Slider component.
 *
 * The drag / keyboard / pointer / clamp / snap logic (~15 methods)
 * lived INLINE in every instance's bz-data. It now lives here ONCE ;
 * each instance emits only its state + ``_read``/``_write`` (value
 * access) and a ``_range`` flag (single scalar vs ``[start, end]``).
 *
 *   bz-data="{...$bz.slider.scope, value: 50,
 *             _read(){return this.value}, _write(v){this.value=v},
 *             _range: false, _min: 0, _max: 100, _step: 1,
 *             _dragging: null, _hovered: null, _focused: null,
 *             _track: null, _carrier: null, _precCache: undefined}"
 *
 * Value access goes through ``this._read()`` / ``this._write(v)`` so the
 * same methods serve local mode (a ``value`` field) and binding mode
 * (a ``$bz.state.<path>`` cell). The mode-specific bits (``_picked`` /
 * ``_setHandle`` / ``_setValue`` / ``_jumpToPointer``) branch on
 * ``this._range`` instead of being baked per instance.
 */
(function () {
  "use strict";
  const $bz = (window.$bz = window.$bz || {});

  $bz.slider = {
    scope: {
      // Static disabled (aria-disabled + tabindex) is applied at render
      // time ; the scalar guard stays a constant here.
      _disabledState() { return false; },
      _pct(v) {
        const range = this._max - this._min;
        if (range === 0) return 0;
        return ((v - this._min) / range) * 100;
      },
      _precision: $bz.num.cachedPrecision,
      _clamp(v) {
        const stepped = Math.round((v - this._min) / this._step) * this._step + this._min;
        const clamped = Math.max(this._min, Math.min(this._max, stepped));
        const p = this._precision();
        return p > 0 ? Number(clamped.toFixed(p)) : clamped;
      },
      _emitChange() { $bz.helpers.emitChange(this._carrier); },
      _pointerToValue(e) {
        const t = this._track;
        if (!t) return this._min;
        const rect = t.getBoundingClientRect();
        if (!rect.width) return this._min;
        const pct = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width));
        return this._clamp(this._min + pct * (this._max - this._min));
      },
      _startDrag(target, e) {
        if (this._disabledState()) return;
        this._dragging = target;
        $bz.helpers.capturePointer(this._track, e);
        this._setHandle(target, this._pointerToValue(e));
      },
      _drag(e) {
        if (this._dragging) this._setHandle(this._dragging, this._pointerToValue(e));
      },
      _endDrag(e) {
        $bz.helpers.releasePointer(this._track, e);
        this._dragging = null;
        this._emitChange();
      },
      _nudge(target, delta) {
        if (this._disabledState()) return;
        const cur = target === "value"
          ? this._picked()
          : this._picked()[target === "start" ? 0 : 1];
        this._setHandle(target, cur + delta);
        this._emitChange();
      },
      // ── Mode-aware (branch on this._range) ───────────────────────
      _picked() {
        const v = this._read();
        if (this._range) {
          return Array.isArray(v) && v.length >= 2
            ? [Number(v[0]), Number(v[1])]
            : [this._min, this._max];
        }
        if (v == null || isNaN(Number(v))) return this._min;
        return Number(v);
      },
      _setHandle(target, raw) {
        if (this._range) {
          const cur = this._picked();
          const v = this._clamp(raw);
          let next;
          if (target === "start") next = [Math.min(v, cur[1]), cur[1]];
          else next = [cur[0], Math.max(v, cur[0])];
          this._write(next);
        } else {
          this._write(this._clamp(raw));
        }
      },
      _setValue(raw) {
        if (this._range) {
          if (Array.isArray(raw) && raw.length >= 2) {
            this._write(
              [this._clamp(Number(raw[0])), this._clamp(Number(raw[1]))]
                .sort(function (a, b) { return a - b; }),
            );
            this._emitChange();
          }
        } else {
          const n = Number(raw);
          if (!isNaN(n)) { this._write(this._clamp(n)); this._emitChange(); }
        }
      },
      _jumpToPointer(e) {
        if (this._disabledState()) return;
        if (this._range) {
          const v = this._pointerToValue(e);
          const cur = this._picked();
          const target = Math.abs(v - cur[0]) < Math.abs(v - cur[1]) ? "start" : "end";
          this._startDrag(target, e);
        } else {
          this._startDrag("value", e);
        }
      },
    },
  };
})();


/* select.js — shared scopes for the Select component.
 *
 * The pick / highlight / multi-membership / bulk-action methods lived
 * INLINE in every instance's bz-data. They live here ONCE, split into
 * two scopes (single vs multi — the modes diverge too much for one
 * branching set). Each instance emits only its data + ``_read``/
 * ``_write`` :
 *
 *   bz-data="{...$bz.select.single, value: 'a',
 *             _read(){return this.value}, _write(v){this.value=v},
 *             open: false, _highlight: -1, _options: [...]}"
 *
 * ``_options`` (option values) and ``_labels`` (value→label map) stay
 * per instance — they differ per Select. Value access goes through
 * ``this._read()`` / ``this._write(v)`` (local: a ``value`` field ;
 * binding: a ``$bz.state.<path>`` cell). No live ``get value()`` —
 * ``scope.absorb`` freezes getters (cf. traps.md) ; the label / hidden
 * input read ``value_expr`` directly.
 */
(function () {
  "use strict";
  const $bz = (window.$bz = window.$bz || {});

  // No scope-level change dispatcher : ``change`` is fired by the
  // per-instance ``_change_emit_effect`` posted ON the hidden input
  // (select.py). That effect dispatches from the hidden input itself, so
  // the relocated htmx listener always sees it ; a scope method's carrier
  // resolved unreliably (root vs hidden, depending on bind order) — for
  // Select it landed on the root and never reached the input at all. The
  // value-setting methods below just ``_write`` ; the effect observes the
  // mutation and dispatches (mirror of Combobox).

  // The options the keyboard and « select all » may land on. The
  // server lists the disabled ones as DATA (``_disabled``); the mouse
  // cannot pick them — a disabled button dispatches no click — but the
  // arrows would walk ``_options`` whole, Enter would pick whatever is
  // highlighted and « select all » would copy the list.
  const usable = {
    _usable(v) { return !(this._disabled || []).includes(String(v)); },
    _firstUsable() {
      const i = this._options.findIndex((v) => this._usable(v));
      return i < 0 ? 0 : i;
    },
    // Move the highlight to the next usable option in ``dir`` (±1); it
    // stays put at the end of the list.
    _step(dir) {
      for (let i = this._highlight + dir; i >= 0 && i < this._options.length; i += dir) {
        if (this._usable(this._options[i])) { this._highlight = i; return; }
      }
    },
  };

  $bz.select = {
    single: {
      ...usable,
      // A value's label. Select KEEPS its ``_labels`` map (its
      // ``_options`` carries only values, so it is not redundant
      // there). The shared pill template
      // (``_picker.build_pills_template``) calls this method rather
      // than inline the map, and Combobox defines it its own way.
      _labelOf(v) { return this._labels[String(v)] || ""; },
      _pick(v) { this._write(v); this.open = false; },
      _enterPick() {
        const v = this._options[this._highlight];
        if (v !== undefined && this._usable(v)) this._pick(v);
      },
      _isPicked(v) { return String(this._read() || "") === String(v); },
      _highlightFromValue() {
        const i = this._options.indexOf(String(this._read()));
        this._highlight = i >= 0 && this._usable(this._options[i]) ? i : this._firstUsable();
      },
    },
    multi: {
      ...$bz.multiSelect,
      ...usable,
      _enterPick() {
        const v = this._options[this._highlight];
        if (v !== undefined && this._usable(v)) this._togglePick(v);
      },
      // A value's label. Select KEEPS its ``_labels`` map (its
      // ``_options`` carries only values, so it is not redundant
      // there). The shared pill template
      // (``_picker.build_pills_template``) calls this method rather
      // than inline the map, and Combobox defines it its own way.
      _labelOf(v) { return this._labels[String(v)] || ""; },
      _value() { const v = this._read(); return v == null ? [] : v; },
      // Select-specific : every option is always visible (no query).
      // ``_clearAll`` is NOT redeclared — the mixin's does exactly that.
      // Every USABLE option — a disabled one already picked (by the
      // server) stays picked, it is not added otherwise.
      _selectAll() {
        this._write(this._options.filter((v) => this._usable(v) || this._isPicked(v)));
      },
      _highlightFromValue() {
        const picks = this._picked().filter((v) => this._usable(v));
        const i = picks.length ? this._options.indexOf(picks[0]) : -1;
        this._highlight = i >= 0 ? i : this._firstUsable();
      },
    },
  };
})();


/* combobox.js — shared scopes for the Combobox component.
 *
 * The biggest inline scope (~30 methods : normalise/filter/nav +
 * pick/multi-membership/bulk) lived in every instance's bz-data. It now
 * lives here ONCE, split into a shared ``common`` (filter + nav) plus a
 * mode-specific ``single`` / ``multi``. Each instance spreads both :
 *
 *   bz-data="{...$bz.combobox.common, ...$bz.combobox.single,
 *             value: 'a', _read(){return this.value},
 *             _write(v){this.value=v}, open: false, query: '',
 *             _highlight: -1, _options: [...]}"
 *
 * ``_options`` (option objects w/ haystack) stays per instance.
 *
 * ⚠️ No ``_labels: {value: label}`` map here: each ``_options`` entry
 * ALREADY carries its ``label``, so the map would repeat half the list.
 * The label shown in the closed field, in single mode, goes through
 * ``_labelOf`` below. ``Select``, for its part, KEEPS the map: its
 * ``_options`` carries only values, so the map is not redundant there.
 *
 * Value access goes through ``this._read()`` / ``this._write(v)``
 * (local: a ``value`` field ; binding: ``$bz.state.<path>``, read raw +
 * null-guard baked into the per-instance ``_read``). No live
 * ``get value()`` (scope.absorb freezes getters — cf. traps.md).
 */
(function () {
  "use strict";
  const $bz = (window.$bz = window.$bz || {});

  // No scope-level change dispatcher : ``change`` is fired by the
  // per-instance ``_change_emit_effect`` posted ON the hidden input
  // (combobox.py). That effect dispatches from the hidden input itself,
  // so the relocated htmx listener always sees it ; a scope method's
  // carrier resolved unreliably (root vs hidden, depending on bind
  // order) and, when it DID reach the input, fired a SECOND, redundant
  // ``change`` — a double server event. The value-setting methods below
  // just ``_write`` ; the effect observes the mutation and dispatches.

  $bz.combobox = {
    /* ── The options, painted by the PANEL ───────────────────────────
     *
     * ``bz-class``, ``bz-attr:aria-selected`` and the two ``bz-on:`` would
     * be repeated identically on every option, so they live ONCE on the
     * panel, as ONE effect and TWO delegated listeners. ``bz-show`` stays
     * per option: it is the search filter, and the runtime has its own
     * hiding machinery.
     *
     * ⚠️ Why the options stay rendered by the SERVER — and why that is
     * not half a job. The repository's rule ("who writes the ``for``?",
     * gated by ``test_collection_owner_decides_the_api``) ties the place
     * of the render to the API's shape: a component that renders its
     * collection on the SERVER side is entitled to a ``render=``
     * callback, a component whose client creates the nodes is NOT — a
     * Python callback does not run in the browser. Painting the options
     * here would therefore lose the combobox its ``render=``, the author's
     * only way into an option's markup. The gain in bytes is not worth a
     * content escape hatch.
     */
    optionOf(ev) {
      const o = ev.target.closest('[role="option"]');
      // A disabled button does not dispatch a click, but IT DOES
      // RECEIVE hovers — without that guard, moving the mouse over a
      // greyed option would highlight it as if it were pickable.
      return o && !o.disabled ? o : null;
    },

    /* Repaint every option's state: the highlight (keyboard and mouse)
     * and the selection.
     *
     * The two class strings travel ONCE, on the panel, instead of being
     * copied into each option's ``bz-class``.
     *
     * ⚠️ We manipulate ``classList`` directly rather than keeping
     * tracking on the node. It is deliberate and it is ``bz-class``'s
     * lesson (traps.md): a state kept on the element does not survive a
     * morph, so the active class was never re-added at the rescan. Here
     * the effect REPAINTS everything at every pass from the truth
     * (``_highlight`` and ``isPicked``), so a morph that would put the
     * SSR class back is caught at the next pass.
     */
    paintOptions(el, highlight, isPicked) {
      const actif = (el.getAttribute("data-bz-opt-active") || "").split(" ");
      const pris = (el.getAttribute("data-bz-opt-picked") || "").split(" ");
      const options = el.querySelectorAll('[role="option"]');
      for (let i = 0; i < options.length; i++) {
        const o = options[i];
        const choisi = !!isPicked(o.getAttribute("data-bz-value"));
        o.setAttribute("aria-selected", choisi ? "true" : "false");
        for (const c of actif) {
          if (c) o.classList.toggle(c, i === highlight);
        }
        for (const c of pris) {
          if (c) o.classList.toggle(c, choisi);
        }
      }
    },

    common: {
      // The search form, ``$bz.fold`` — twin of the Python ``fold`` that
      // baked the options' haystacks.
      _norm: (s) => $bz.fold(s),
      _value() { return this._read(); },
      // A value's label, read in ``_options`` — which already carries
      // it. Replaces the ``_labels`` map each instance emitted in
      // addition (cf. the header). A single reader: the CLOSED field in
      // single mode, so a linear scan over an options list costs nothing
      // measurable, and it stays in step with ``_options`` when a server
      // refresh re-seeds it — which a map frozen in another field could
      // miss.
      _labelOf(v) {
        const s = String(v == null ? "" : v);
        if (!s) return "";
        const hit = this._options.find((o) => String(o.value) === s);
        // ``creatable``: a value typed by the reader is in no option —
        // it shows as itself. Not otherwise: an unknown id is not a
        // label (``42`` must not show up in the field).
        return hit ? hit.label : (this._creatable ? s : "");
      },
      /* ``creatable=True`` — what « Create « … » » would create: the
       * typed text, trimmed; ``""`` when nothing would be created —
       * nothing typed, or an option already says it (label or value,
       * folded: « musee » does not create a second « Musée »), or, in
       * multi mode, it is already picked. */
      _createText() {
        if (!this._creatable) return "";
        const raw = String(this.query || "").trim();
        if (!raw) return "";
        const q = this._norm(raw);
        for (const o of this._options) {
          if (this._norm(o.label) === q || this._norm(o.value) === q) return "";
        }
        for (const v of this._picked()) if (this._norm(v) === q) return "";
        return raw;
      },
      // The « Create » row's place in the keyboard path: after the
      // options, at index ``_options.length`` (the row is the last
      // ``[role=option]`` of the panel, so ``paintOptions`` lights it).
      _createIndex() { return this._createText() ? this._options.length : -1; },
      _tokens() {
        const q = this._norm(this.query || "");
        return q ? q.split(/\s+/).filter(Boolean) : [];
      },
      _matches(haystack) {
        const t = this._tokens();
        if (!t.length) return true;
        return t.every((tok) => haystack.includes(tok));
      },
      _visibleIndices() {
        const out = [];
        for (let i = 0; i < this._options.length; i++) {
          const o = this._options[i];
          if (o.disabled) continue;
          if (this._matches(o.haystack)) out.push(i);
        }
        return out;
      },
      _visibleCount() { return this._visibleIndices().length; },
      _navIndices() {
        const vis = this._visibleIndices();
        const c = this._createIndex();
        return c < 0 ? vis : vis.concat([c]);
      },
      _moveHighlight(delta) {
        const vis = this._navIndices();
        if (!vis.length) { this._highlight = -1; return; }
        let pos = vis.indexOf(this._highlight);
        if (pos === -1) pos = delta > 0 ? -1 : vis.length;
        pos = Math.max(0, Math.min(vis.length - 1, pos + delta));
        this._highlight = vis[pos];
      },
    },
    single: {
      _pickHighlighted() {
        if (!this.open) { this.open = true; return; }
        const nav = this._navIndices();
        let idx = this._highlight;
        // No highlight: the first visible option — or « Create » when
        // none is left.
        if (idx < 0 || !nav.includes(idx)) idx = nav[0];
        if (idx == null) return;
        if (idx === this._createIndex()) { this._create(); return; }
        this._pick(this._options[idx].value);
      },
      _create() {
        const v = this._createText();
        if (v) this._pick(v);
      },
      _picked() { const v = this._value(); return v == null || v === "" ? [] : [String(v)]; },
      _isPicked(v) { return String(this._value() || "") === String(v); },
      _hasPicked() { const v = this._value(); return v != null && v !== ""; },
      _pick(v) {
        this._write(String(v));
        this.query = ""; this.open = false; this._highlight = -1;
      },
      _togglePick(v) {
        if (this._isPicked(v)) {
          this._write(""); this.query = ""; this._highlight = -1;
        } else { this._pick(v); }
      },
      _setValue(raw) { this._pick(raw == null ? "" : raw); },
      _clearAll() { this._write(""); this.query = ""; this.open = false; },
      _selectAll() {},
      _removeLast() {},
      _removeOne(v) {
        if (this._isPicked(v)) { this._write(""); this.query = ""; }
      },
    },
    multi: {
      ...$bz.multiSelect,
      _pickHighlighted() {
        if (!this.open) { this.open = true; return; }
        const nav = this._navIndices();
        let idx = this._highlight;
        if (idx < 0 || !nav.includes(idx)) idx = nav[0];
        if (idx == null) return;
        if (idx === this._createIndex()) { this._create(); return; }
        this._togglePick(this._options[idx].value);
        this.query = ""; this._highlight = -1;
      },
      // A created value joins the picks as a pill; the field empties so
      // the next one can be typed.
      _create() {
        const v = this._createText();
        if (!v) return;
        this._togglePick(v);
        this.query = ""; this._highlight = -1;
      },
      _removeLast() {
        const cur = this._picked();
        if (cur.length) { this._write(cur.slice(0, -1)); }
      },
      _selectAll() {
        const vis = this._visibleIndices();
        this._write(vis.map((i) => this._options[i].value));
      },
      // The mixin empties the selection without closing; Combobox ADDS
      // the query reset (Select has no search field).
      _clearAll() { $bz.multiSelect._clearAll.call(this); this.query = ""; },
    },
  };
})();


/* pagination.js — the Pagination component's shared scope.
 *
 * The whole ``range()`` algorithm — computing the visible page numbers
 * with their ellipses — lived INLINE in every instance's ``bz-data``:
 * 957 bytes per ``<ui.pagination>``, the repository's biggest. Worse,
 * its configuration was baked INTO the method bodies:
 *
 *     totalPages() { return Math.max(1, +(10) || 1); }
 *     maxVisible() { return +(7) || 7; }
 *     isDisabled() { return !!(false); }
 *
 * — three literal constants where three pieces of data were needed. It
 * is what made factoring impossible: two instances with different
 * ``total_pages`` produced two different CODES, not two different
 * states.
 *
 * The switch is therefore "config as data", the prerequisite
 * NumberInput had already applied (cf. number_input.js):
 *
 *   bz-data="{...$bz.pagination.scope, value: 1, _total: 10,
 *             _maxVisible: 7, _disabled: false,
 *             _read(){return this.value}, _write(v){this.value = v}}"
 *
 * ``_read`` / ``_write`` cover BOTH modes with the same methods — a
 * local field (``value``) or a store cell (``$bz.state.<path>``). One
 * cannot put a ``get value()`` there: ``scope.absorb`` reads each key
 * once at registration and would freeze the getter (cf. traps.md).
 *
 * ``range()`` is the JS port of ``compute_range`` (Python). The two must
 * agree — that is what ``test_python_js_mirror`` checks.
 */
(function () {
  "use strict";
  const $bz = (window.$bz = window.$bz || {});

  $bz.pagination = {
    scope: {
      // ── Normalised reads ─────────────────────────────────────────
      // METHODS, not getters: the scope invokes them at registration,
      // which would freeze a getter on its first value.
      current() {
        return +this._read() || 1;
      },
      totalPages() {
        return Math.max(1, +this._total || 1);
      },
      maxVisible() {
        return +this._maxVisible || 7;
      },
      // A constant by default, overridden from the builder when the
      // lock is real (a literal or a binding) — the same mechanics as
      // the Slider's ``_disabledState`` (slider.js:28).
      //
      // ⚠️ It is NOT data. A ``_disabled: <store path>`` field in the
      // bz-data would be evaluated ONCE, outside any effect: ``absorb``
      // wraps the snapshot in a new signal decoupled from the cell, and
      // nothing rewrites it. The lock would therefore stay frozen at its
      // mount value: the switch flips, the pagination stays clickable.
      // A bound expression must live in a METHOD BODY,
      // the only place re-read at every call hence tracked by the
      // calling effect. Cf. traps.md § "Une valeur de scope calculée
      // doit rester calculable".
      isDisabled() {
        return false;
      },

      // A setter — it only mutates on a real change, so a click on the
      // current page is a no-op. It is the hidden input's ``bz-effect``
      // that turns the mutation into a bubbling ``change``.
      //
      // The lock and the bound live HERE, in the single mutator, because
      // the callers are not equivalent: the rail's buttons are
      // already guarded by their ``bz-attr:disabled`` and only pass
      // values coming from ``range()``, but the imperative API
      // (``p.next()`` on a button elsewhere in the page) has neither of
      // those two guard rails. A single guarded mutator rather than two
      // paths to guard separately (charter principle 4).
      setActive(v) {
        if (this.isDisabled()) return;
        const n = Math.max(1, Math.min(this.totalPages(), +v || 1));
        if (this.current() === n) return;
        this._write(n);
      },

      // Both directions are DERIVED from the mutator: the bound is
      // already there, so ``next()`` on the last page clamps to
      // ``totalPages()``, falls back on ``current()`` and exits — the
      // no-op at the edge is free, not one more branch.
      next() {
        this.setActive(this.current() + 1);
      },
      prev() {
        this.setActive(this.current() - 1);
      },

      // ── Computing the visible pages ──────────────────────────────
      // A direct port of ``compute_range``. Recomputes as soon as
      // current() / totalPages() / maxVisible() read a changed signal —
      // the runtime's effect tracks the reads.
      //
      // In a method body, a bare identifier does NOT see the scope:
      // everything goes through ``this.<name>()``.
      range() {
        const tp = this.totalPages();
        const slots = Math.max(5, this.maxVisible());
        const ap = this.current();
        if (tp <= slots) {
          return Array.from({ length: tp }, (_, i) => i + 1);
        }
        const side = Math.floor(slots / 2);
        const showLeft = ap > side + 1;
        const showRight = ap < tp - side;
        if (!showLeft) {
          const r = [];
          for (let i = 1; i < slots - 1; i++) r.push(i);
          r.push("ellipsis");
          r.push(tp);
          return r;
        }
        if (!showRight) {
          const r = [1, "ellipsis"];
          for (let i = tp - (slots - 3); i <= tp; i++) r.push(i);
          return r;
        }
        const r = [1, "ellipsis"];
        const middle = slots - 4;
        const start = ap - Math.floor(middle / 2);
        for (let i = 0; i < middle; i++) r.push(start + i);
        r.push("ellipsis");
        r.push(tp);
        return r;
      },
    },
  };
})();


/* accordion.js — the shared scopes of Accordion, Tree, Tabs and
 * Stepper.
 *
 * The method bodies live here rather than in every instance's
 * ``bz-data``, and an accordion's configuration is DATA. Baked into the
 * code, as in
 *
 *     toggle(v) { … if (cur === target) { if (true) { … } } … }
 *                                            ^^^^ collapsible
 *     expandAll() { const ids = ["a","b","c"]; … }
 *
 * two accordions with different configurations would be two different
 * CODES, not two different states, and nothing could be factored.
 * "Config as data" is the same prerequisite as NumberInput and
 * Pagination.
 *
 *   bz-data="{...$bz.accordion.single, value: "a", _read(){…}, _write(v){…},
 *             _collapsible: true, _allIds: ["a","b"]}"
 *   bz-data="{...$bz.accordion.multi,  value: ["a"],
 *             _allIds: ["a","b"]}"
 *
 * Two variants rather than a single parameterised one: single mode
 * carries a STRING, multi mode an ARRAY. Merging them would force every
 * method to re-test the type at runtime — the same reason that gave
 * ``$bz.select.single`` and ``$bz.select.multi``.
 *
 * ⚠️ METHODS, never getters: ``scope.absorb`` invokes each key at
 * registration and would freeze a getter on its first value (cf.
 * traps.md).
 */
(function () {
  "use strict";
  const $bz = (window.$bz = window.$bz || {});

  $bz.accordion = {
    // ── One panel open at a time ────────────────────────────────────
    single: {
      isOpen(v) {
        return String(this._read() || "") === String(v);
      },
      toggle(v) {
        const cur = String(this._read() || "");
        const target = String(v);
        if (cur === target) {
          // ``_collapsible``: is closing the current panel allowed?
          if (this._collapsible) this._write("");
        } else {
          this._write(target);
        }
      },
      expand(v) {
        const target = String(v);
        if (String(this._read() || "") !== target) this._write(target);
      },
      collapse(v) {
        const target = String(v);
        if (String(this._read() || "") === target && this._collapsible) {
          this._write("");
        }
      },
      // In single mode, "open everything" can only open the first.
      expandAll() {
        const ids = this._allIds || [];
        if (ids.length) this._write(String(ids[0]));
      },
      collapseAll() {
        if (this._collapsible) this._write("");
      },
    },

    // ── Plusieurs panneaux ouverts ──────────────────────────────────
    multi: {
      isOpen(v) {
        return (this._read() || []).indexOf(v) >= 0;
      },
      toggle(v) {
        const cur = this._read() || [];
        const i = cur.indexOf(v);
        this._write(i >= 0 ? cur.filter((_, j) => j !== i) : [...cur, v]);
      },
      expand(v) {
        const cur = this._read() || [];
        if (cur.indexOf(v) < 0) this._write([...cur, v]);
      },
      collapse(v) {
        const cur = this._read() || [];
        const i = cur.indexOf(v);
        if (i >= 0) this._write(cur.filter((_, j) => j !== i));
      },
      expandAll() {
        this._write((this._allIds || []).slice());
      },
      collapseAll() {
        this._write([]);
      },
    },
  };

  // ── Tree ──────────────────────────────────────────────────────────
  // The same family: multiple opening (the expanded nodes) + an optional
  // single selection. ``sel`` / ``isSel`` / ``select`` only serve when
  // ``selectable=True``; leaving them in the shared scope costs nothing
  // (the HTML does not call them) and avoids a second variant.
  $bz.tree = {
    scope: {
      isOpen(id) {
        return (this._read() || []).indexOf(id) >= 0;
      },
      toggle(id) {
        const cur = this._read() || [];
        const i = cur.indexOf(id);
        this._write(i >= 0 ? cur.filter((_, j) => j !== i) : [...cur, id]);
      },
      isSel(id) {
        return String(this._readSel() || "") === String(id);
      },
      select(id) {
        this._writeSel(String(id));
      },
      // Defaults for the NON-selectable case: the component only
      // replaces them when ``selectable=True``. Without them, ``isSel``
      // would raise if a theme called the method.
      _readSel() {
        return "";
      },
      _writeSel(_v) {},
    },
  };

  // ── Tabs ──────────────────────────────────────────────────────────
  // A setter with a change guard — the same shape as
  // ``$bz.pagination.setActive``.
  //
  // ``_url`` — the URL parameter's name, when the caller wrote
  // ``ui.tabs(url="tab")``. Absent by default, so everything that
  // follows is inert: a tab only has an address if you ask for one.
  //
  // It is the CLIENT counterpart of ``URL = {…}`` on a server state.
  // Both exist because both paths exist: a sort goes through the server,
  // which can set a header; a tab flips in the scope, with no request —
  // nobody on the server side learns anything, so it is up to the
  // runtime to keep the address bar in step.
  $bz.tabs = {
    scope: {
      setTab(v) {
        const s = String(v == null ? "" : v);
        if (String(this._read()) === s) return;
        this._write(s);
        if (this._url) $bz.helpers.pushUrl(this._url, s);
      },

      // The KEYBOARD, on the tablist (WAI-ARIA tabs pattern, automatic
      // activation). The tabindex is roving — only the active tab is in
      // the Tab order — so without this a keyboard user reached the
      // active tab and nothing else. Arrows move to the neighbour (and
      // wrap), Home/End to the ends; disabled tabs are skipped. The tab
      // reached is focused AND activated.
      tabKey(e, list) {
        const step = { ArrowRight: 1, ArrowLeft: -1, Home: 0, End: 0 }[e.key];
        if (step === undefined) return;
        const tabs = Array.from(
          list.querySelectorAll('[role="tab"]:not([disabled])'),
        );
        if (!tabs.length) return;
        const from = tabs.indexOf(e.target.closest('[role="tab"]'));
        let to;
        if (e.key === "Home") to = 0;
        else if (e.key === "End") to = tabs.length - 1;
        else to = (Math.max(from, 0) + step + tabs.length) % tabs.length;
        e.preventDefault();
        tabs[to].focus();
        this.setTab(tabs[to].dataset.bzTab);
      },

      // The BACK button. Without it, the browser's arrow would change
      // the address and leave the tab where it is — worse than no
      // address at all, because the displayed URL would then lie about
      // what is on screen.
      //
      // We cannot leave it to htmx: it only restores the entries it
      // created itself (it tests its own mark in ``history.state``), and
      // this one comes from here. And doing it ourselves is better
      // anyway — it is a signal toggle, instant, where htmx would redo
      // the whole page to change tab.
      //
      // Set by ``bz-init``, the route ``helpers.js`` documents for an
      // event that only exists on ``window``.
      _urlInit() {
        if (!this._url) return;
        const param = this._url;
        const self = this;
        // What the SERVER rendered — the tab when the address says
        // nothing. Captured here, at mount, because the signal will have
        // moved by the time the first ``popstate`` arrives.
        const initial = String(self._read());
        $bz.helpers.onWindow("popstate", function () {
          const raw = $bz.helpers.urlParam(param);
          // **Absent = the default.** Not "do nothing": coming back to
          // ``/contacts/5`` after ``?tab=activity`` must REOPEN the
          // initial tab. The first writing gated on ``if (next)`` and
          // therefore left the previous tab displayed under an address
          // that said something else — caught by ``probe_tabs_url``,
          // invisible to every SSR test.
          //
          // It is also the rule the server already applies on both sides
          // (``state/url.py``: absent → we keep the default, at its
          // default → does not appear). All three agree, so a round trip
          // is faithful.
          const next = raw == null || raw === "" ? initial : String(raw);
          if (String(self._read()) !== next) self._write(next);
        });
      },
    },
  };

  // ── Stepper ───────────────────────────────────────────────────────
  // The current index is an INTEGER, and that is what makes the scope so
  // small: "is this step done?" is answered by a comparison, where an id
  // would require an indexOf in a baked list.
  //
  //   bz-data="{...$bz.stepper.scope, current: 1, _read(){…}, _write(v){…},
  //             _max: 3}"
  //
  // ``_max`` = the greatest reachable index — the number of STEPS, or of
  // PANELS if there is one more (the "done" screen). Without it,
  // ``next()`` would not know where to stop, and baking the bound into
  // the method's body would make two different CODES for two steppers of
  // different lengths — the drift this file exists to kill.
  $bz.stepper = {
    scope: {
      // The only state the theme reads (``data-[status=done]/step:``).
      // A step in ERROR does not come through here: its attribute is
      // static on the server side, so never recomputed.
      _status(i) {
        const cur = Number(this._read()) || 0;
        return i < cur ? "done" : i === cur ? "current" : "upcoming";
      },
      goTo(i) {
        const n = Number(i);
        if ((Number(this._read()) || 0) === n) return;
        this._write(n);
      },
      next() {
        const cur = Number(this._read()) || 0;
        if (cur < this._max) this._write(cur + 1);
      },
      prev() {
        const cur = Number(this._read()) || 0;
        if (cur > 0) this._write(cur - 1);
      },
    },
  };
})();


/* carousel.js — the Carousel component's shared scope.
 *
 * The scrolling is **CSS scroll-snap**, not a translateX driven from
 * here: the track is an `overflow-x-auto snap-x snap-mandatory`
 * container and each slide carries `snap-start`. That choice decides
 * this whole file.
 *
 * What the browser does, and what we therefore do not write: the touch
 * swipe with its inertia and its rubber-banding, the wheel scroll, the
 * keyboard, and the snapping itself. Two things are left here — going
 * to an index, and reading the index from the scroll position.
 *
 *   bz-data="{...$bz.carousel.scope, current: 0, _track: null,
 *             _read(){…}, _write(v){…}}"
 *
 * ``_track`` is captured at the root's ``bz-init``
 * (`_track = $refs.bztrack`): a scope method has **no** access to
 * ``$refs``, only directives do (same constraint as Slider, cf. its
 * docstring).
 *
 * ⚠️ **All the geometry is READ from the DOM, never computed.** The
 * stride comes from the real gap between two slides, the bound from
 * ``scrollWidth - clientWidth``. That is what makes a responsive
 * ``per_view`` (`{"base": 1, "md": 3}`) free: the JS has no breakpoint
 * to know, it measures what CSS decided.
 */
(function () {
  "use strict";
  const $bz = (window.$bz = window.$bz || {});

  //: The silence after the last scroll event before considering the
  //: position settled. Without that delay, a smooth scroll from 0 to 3
  //: would publish 1 then 2 on the way — and on a server-bound
  //: ``value``, every intermediate value would leave as a ``change``.
  const SETTLE_MS = 120;

  $bz.carousel = {
    scope: {
      // ── Geometry ─────────────────────────────────────────────────
      // METHODS, never getters: ``scope.absorb`` invokes each key at
      // registration and would freeze a getter on its first value (cf.
      // traps.md).
      _step() {
        const t = this._track;
        if (!t || !t.children.length) return 0;
        const a = t.children[0];
        // The gap between TWO slides, not the width of one: it
        // includes the gap, so it stays right whatever the theme's
        // spacing.
        if (t.children.length > 1) {
          return (
            t.children[1].getBoundingClientRect().left -
            a.getBoundingClientRect().left
          );
        }
        return a.getBoundingClientRect().width;
      },
      _maxIndex() {
        // ``void this._geom`` is NOT dead: it is the read that
        // REGISTERS the reactive dependency of everything that
        // measures. A DOM measurement is not a signal — without that
        // link, a ``bz-attr:disabled="_atEnd()"`` evaluates once at scan
        // time, with that instant's layout, and is never re-read.
        // Hydrated before the Tailwind sheet applies, the track is not
        // yet ``flex``, so ``scrollWidth === clientWidth``, so the bound
        // is 0, so BOTH arrows are disabled — and ``disabled:opacity-0``
        // erases them: no arrow at the first visit, all of them on
        // refresh. Cf. ``_observeGeom`` for what
        // moves this signal.
        void this._geom;
        // ``_step()`` already returns 0 with no track, so this test
        // covers both cases — and ``_geomIndex`` just below leans on the
        // same property. Doubling the guard here would suggest the two
        // neighbours disagree.
        const step = this._step();
        if (!step) return 0;
        const t = this._track;
        return Math.max(0, Math.round((t.scrollWidth - t.clientWidth) / step));
      },
      _geomIndex() {
        const step = this._step();
        return step ? Math.round(this._track.scrollLeft / step) : 0;
      },

      // ── What makes the measurement re-evaluable ──────────────────
      // Called from a ``bz-effect`` carried by the TRACK, and most
      // certainly not from the root's ``bz-init``: ``bz-init`` is
      // one-shot per NODE (``el._bzInitDone``), yet idiomorph morphs IN
      // PLACE — the root's node survives, so the hook does not run
      // again, so the slides added by a morph would never be observed. A
      // ``bz-effect`` is thrown away and redone at every rescan, which
      // re-observes the current set with nothing more to write.
      // (``ui.carousel`` + ``ui.each`` inside a refreshed zone is the
      // component's number-one use case: that path is not a corner.)
      //
      // It must NOT join the root's effect, which already depends on
      // ``_geom`` through ``_syncFromValue`` → ``_maxIndex``: the bump
      // of the observer's first report would relaunch it, which would
      // re-wire the observer, which would report again — a loop.
      //
      // Why a ResizeObserver and not a ``window.resize``: the bound
      // moves without the window moving. A responsive ``per_view``
      // changes the SLIDES' width at a breakpoint; a carousel hydrated
      // in a collapsed panel measures zero until it opens; a stylesheet
      // arriving after the scan turns the track from ``block`` to
      // ``flex``. All three show on an observed box, none goes through a
      // window event.
      //
      // ONE slide is observed in addition to the track, and one is
      // enough: they all carry the SAME class string (``slide_class`` is
      // composed once on the Python side then applied to each), so they
      // change size together. The first is a faithful witness of the
      // group; observing the other eighty would bring no extra
      // information.
      _observeGeom() {
        const t = this._track;
        if (!t) return;
        // The observer is filed on the OBSERVED node, not on the scope
        // — the same choice as ``$bz._tick`` with ``el._bzTickId``, and
        // for the same reason: its lifetime is the track's, so a
        // detached track takes its observer with it. On the scope, it
        // would outlive its subject.
        //
        // Filing it there ALSO avoids a loop: this method runs in an
        // effect, and a scope field written from an effect that reads it
        // would call itself endlessly (an undeclared field becomes a
        // signal at the first write — cf. ``scope.js``). A node
        // property is not reactive, so nothing relaunches.
        if (t._bzGeomRo) t._bzGeomRo.disconnect();
        const self = this;
        // Bumping a counter rather than publishing the measurement:
        // the measurement stays read at the moment it is needed (a
        // single source), the signal only says "read again". No loop
        // possible — what the effect writes behind it (``disabled``, so
        // an opacity) changes no box.
        const ro = new ResizeObserver(function () {
          self._geom = self._geom + 1;
        });
        ro.observe(t);
        if (t.children[0]) ro.observe(t.children[0]);
        t._bzGeomRo = ro;
      },

      // ── Bounds — the arrows' disabled state ──────────────────────
      // Reading ``_read()`` registers the reactive dependency (it is
      // what moves); the BOUND, for its part, comes from the geometry —
      // so no per_view or breakpoint computation.
      _atStart() {
        return Number(this._read()) <= 0;
      },
      _atEnd() {
        return Number(this._read()) >= this._maxIndex();
      },

      // ── Navigation ───────────────────────────────────────────────
      goTo(i) {
        const t = this._track;
        if (!t) return;
        const n = Math.max(0, Math.min(this._maxIndex(), Number(i) || 0));
        t.scrollTo({ left: n * this._step(), behavior: "smooth" });
        // We do NOT write the state here: ``_onScroll`` is the index's
        // single source, and it will publish it when the position has
        // settled. Writing on both sides would make the signal diverge
        // from what the user sees as soon as they interrupt the
        // animation with a finger.
      },
      // ``next`` / ``prev`` LOOP, and it does not contradict arrows
      // that stop: the arrows are disabled at the edges, so they never
      // arrive here at the end. What arrives here at the end is the
      // autoplay — and a rotation that stops is no longer a rotation.
      next() {
        const max = this._maxIndex();
        const cur = Number(this._read()) || 0;
        this.goTo(cur >= max ? 0 : cur + 1);
      },
      prev() {
        const cur = Number(this._read()) || 0;
        this.goTo(cur <= 0 ? this._maxIndex() : cur - 1);
      },

      // ── The position → state bridge ──────────────────────────────
      _onScroll() {
        clearTimeout(this._settleId);
        this._settleId = setTimeout(() => {
          const i = this._geomIndex();
          if (Number(this._read()) !== i) this._write(i);
        }, SETTLE_MS);
      },

      // ── The state → position bridge ──────────────────────────────
      // Called from the root's ``bz-effect``: reading ``_read()``
      // registers the dependency, so an EXTERNAL writer (a binding
      // driven elsewhere, a `.set(i)`) scrolls the track.
      //
      // The ``!==`` guard is what stops the loop with ``_onScroll``, and
      // it is enough: during a smooth scroll, the published position
      // ends up equalling the target, the effect relaunches, finds no
      // gap any more, and does not call ``scrollTo`` a second time.
      _syncFromValue() {
        const t = this._track;
        if (!t) return;
        const target = Math.max(
          0,
          Math.min(this._maxIndex(), Number(this._read()) || 0)
        );
        if (this._geomIndex() === target) return;
        // The very first snap is INSTANT: a carousel rendered at
        // value=2 must show on slide 2, not scroll from 0 under the
        // user's eyes on load.
        const behavior = this._booted ? "smooth" : "auto";
        this._booted = true;
        t.scrollTo({ left: target * this._step(), behavior: behavior });
      },

      // ── Autoplay ─────────────────────────────────────────────────
      // A single gesture from the user and the rotation stops, for
      // good. No resumption after a delay: a content that starts moving
      // again while you are reading it is the number-one accessibility
      // complaint about carousels. No pause on hover either — it does
      // not exist on a coarse pointer.
      //
      // ``still`` is a SIGNAL declared in the ``bz-data`` (not a field
      // set on the fly): it is the root's effect that reads it, as
      // ``$bz._tick($el, !still, ms)``, and an undeclared field would
      // never relaunch that effect — the autoplay would run forever.
      _touch() {
        if (!this.still) this.still = true;
      },
    },
  };
})();


/* time_picker.js — the TimePicker component's shared scope.
 *
 * The value is an ``"HH:MM"`` STRING — the same shape as the date
 * pickers' ISO: sortable, comparable, serialisable as is in a form data,
 * and readable by a human in the editable field.
 *
 *   bz-data="{...$bz.time.scope, open: false, value: "09:30",
 *             _read(){…}, _write(v){…}}"
 *
 * ⚠️ ``_read`` / ``_write`` are NOT an elegance: a bound expression must
 * live in a METHOD BODY. A ``bz-data`` field is evaluated ONCE, outside
 * any effect — ``absorb`` wraps its snapshot in a new signal decoupled
 * from the store cell, which nothing rewrites (cf. traps.md § "Une
 * valeur de scope calculée doit rester calculable").
 *
 * Why a shared scope rather than inline expressions: a panel with 24
 * hours and 4 minutes is 28 buttons. Writing the pick and the selection
 * test out in full on each would serialise the same algorithm 28 times
 * PER INSTANCE — exactly what Pagination's and Accordion's "config as
 * data" switches avoid.
 */
(function () {
  "use strict";
  const $bz = (window.$bz = window.$bz || {});

  //: The index of the two parts in the tuple ``_parts`` returns.
  const HOUR = 0;
  const MINUTE = 1;
  //: The half day's column — built here, only in twelve hours.
  const PERIOD = 2;

  /* The AM / PM column: a sibling of the minutes', same classes, its
   * own name (``data-bz-period-label``, a framework text). */
  function addPeriodColumn(el) {
    const minutes = el.querySelector('[data-bz-part="' + MINUTE + '"]');
    if (!minutes) return;
    const col = minutes.cloneNode(false);
    col.setAttribute("data-bz-part", String(PERIOD));
    col.setAttribute("data-bz-values", "AM,PM");
    col.setAttribute("data-bz-off", "");
    const name = el.getAttribute("data-bz-period-label") || "";
    col.setAttribute("aria-label", name);
    col.setAttribute("data-bz-cell-label", name);
    const head = minutes.firstElementChild && !minutes.firstElementChild.hasAttribute("data-bz-v")
      ? minutes.firstElementChild.cloneNode(false) : null;
    if (head) { head.innerHTML = "&nbsp;"; col.appendChild(head); }
    minutes.parentNode.appendChild(col);
  }

  $bz.time = {
    scope: {
      // ── Reading ──────────────────────────────────────────────────
      // METHODS, never getters: ``scope.absorb`` invokes each key at
      // registration and would freeze a getter on its first value (cf.
      // traps.md).
      _parts() {
        const m = String(this._read() || "").match(/^(\d{1,2}):(\d{2})/);
        // Two empty strings rather than null: the callers compare, they
        // never have to test presence.
        return m ? [m[1].padStart(2, "0"), m[2]] : ["", ""];
      },
      _is(part, v) {
        return this._parts()[part] === v;
      },

      // ── Writing ──────────────────────────────────────────────────
      _pick(part, v) {
        const p = this._parts();
        p[part] = v;
        // An hour chosen while the minute is unknown is ``:00`` —
        // otherwise the field would stay EMPTY right after a click, and
        // the user would think the click did not take. Symmetrical for a
        // minute chosen first.
        this._write(
          (p[HOUR] || "00") + ":" + (p[MINUTE] || "00")
        );
      },
      // Clicking a MINUTE closes the panel, clicking an hour does not:
      // the reading order is hour then minute, so closing on the hour
      // would cut the user's hand off mid-gesture. ``_closeOnPick`` is
      // data (the component's prop).
      pick(part, v) {
        this._pick(part, v);
        if (this._closeOnPick && part === MINUTE) this.open = false;
      },
    },

    /* Paint the two columns' cells, then mark the selection.
     *
     * Why Python does not render the cells
     * -------------------------------------
     * Each would carry the theme's class string and two directives
     * (``bz-attr:data-selected`` + ``bz-on:click``), and at ``step=1``
     * there are 84 cells: nearly all of the component's weight would be
     * that one class and those directives, repeated identically.
     *
     * It is the same remedy as ``<bz-calendar>``, which leaves its grid
     * EMPTY in SSR and fills it here — but WITHOUT a custom element: its
     * docstring says a second one would be the moment to make it a
     * runtime policy, and lightening a payload does not justify opening
     * that work. A ``bz-effect`` on the container is enough.
     *
     * The cells have NO directive left
     * ---------------------------------
     * A delegated click replaces 84 ``bz-on:click``, and this effect
     * replaces 84 ``bz-attr:data-selected``. It is what avoids having to
     * rescan the subtree after painting it — a ``$bz._scan`` called from
     * the body of an effect a scan has just installed would reinstall
     * itself.
     *
     * The effect runs again at every change of the value (it reads
     * ``_parts()``), so the selection is repainted without anything else
     * moving. The construction, for its part, only happens once: the
     * guard is a DOM MEASUREMENT ("do I already have cells?"),
     * legitimate here for the same reason as in
     * ``bz-calendar.rehydrate`` — it derives no display, it observes a
     * one-off fact at the only moment the question arises.
     */
    fill(el, parts, pick) {
      const cellCls = el.getAttribute("data-bz-cell-class") || "";
      const off = el.hasAttribute("data-bz-cells-disabled");
      // ── Twelve hours, when the page's language counts so ─────────
      // The column counts as the field does (« 2:30 PM »). The VALUE
      // stays "HH:MM": only the cells change — the
      // hours become 12, 1…11, a third column carries the half day, and
      // a click is turned back into 24 hours before it is picked.
      const twelve = $bz.times.twelve();
      if (twelve && !el.querySelector('[data-bz-part="' + PERIOD + '"]')) {
        addPeriodColumn(el);
      }
      const cols = el.querySelectorAll("[data-bz-part]");
      const h24 = parts[HOUR] === "" ? null : Number(parts[HOUR]);
      const pm = h24 !== null && h24 >= 12;
      const pad = function (n) { return String(n).padStart(2, "0"); };
      // What a cell of the twelve-hour panel stands for, in 24 hours.
      const as24 = function (h12, isPm) { return pad((Number(h12) % 12) + (isPm ? 12 : 0)); };
      const chosen = function (part, v) {
        if (!twelve) return pick(part, v);
        if (part === HOUR) return pick(HOUR, as24(v, pm));
        if (part === PERIOD) {
          const toPm = v === "PM";
          return pick(HOUR, h24 === null ? (toPm ? "12" : "00") : as24(h24 % 12, toPm));
        }
        return pick(part, v);
      };

      for (let i = 0; i < cols.length; i++) {
        const col = cols[i];
        const part = Number(col.getAttribute("data-bz-part"));
        // Escaped: the label is the app's words (``hour_label=``, a
        // translation) and the cells are built as HTML.
        const esc = $bz.helpers.escapeHtml;
        const label = esc(col.getAttribute("data-bz-cell-label") || "");

        if (!col.querySelector("[data-bz-v]")) {
          const values = twelve && part === HOUR
            ? ["12", "1", "2", "3", "4", "5", "6", "7", "8", "9", "10", "11"]
            : (col.getAttribute("data-bz-values") || "").split(",").filter(Boolean);
          const shown = part === PERIOD ? $bz.times.halves() : null;
          const barred = (col.getAttribute("data-bz-off") || "")
            .split(",").filter(Boolean);
          let html = "";
          for (let j = 0; j < values.length; j++) {
            const v = values[j];
            const dead = off || barred.indexOf(v) !== -1;
            const said = esc(shown ? shown[j] : v);
            html +=
              '<button type="button" data-bz-v="' + esc(v) + '"' +
              ' class="' + esc(cellCls) + '"' +
              ' aria-label="' + label + " " + said + '"' +
              (dead ? " disabled" : "") + ">" + said + "</button>";
          }
          col.insertAdjacentHTML("beforeend", html);
        }

        // A single listener per column. The flag lives on the NODE, and
        // it is correct here: if idiomorph keeps the node, the listener
        // survives with it; if it replaces it, the new one has no flag
        // and re-wires. The flag and the listener always agree — which
        // is very exactly what ``bz-class``'s tracking was missing (cf.
        // traps.md).
        if (!col._bzTimeWired) {
          col._bzTimeWired = true;
          col.addEventListener("click", function (ev) {
            const cell = ev.target.closest("[data-bz-v]");
            if (!cell || cell.disabled) return;
            col._bzTimePick(part, cell.getAttribute("data-bz-v"));
          });
        }
        // Re-pointed at every pass: the half day it converts with is
        // the CURRENT value's.
        col._bzTimePick = chosen;

        // The selection, at every pass of the effect.
        const courant = !twelve || part === MINUTE ? parts[part]
          : h24 === null ? "" : part === HOUR ? String(h24 % 12 || 12) : (pm ? "PM" : "AM");
        const barred = twelve && part === HOUR
          ? (col.getAttribute("data-bz-off") || "").split(",").filter(Boolean) : null;
        const cells = col.querySelectorAll("[data-bz-v]");
        for (let j = 0; j < cells.length; j++) {
          const c = cells[j];
          // min / max are in 24 hours: a twelve-hour cell is out of
          // range in the CURRENT half day, so it is judged at each pass.
          if (barred) c.disabled = off || barred.indexOf(as24(c.getAttribute("data-bz-v"), pm)) !== -1;
          if (c.getAttribute("data-bz-v") === courant) {
            c.setAttribute("data-selected", "true");
          } else {
            c.removeAttribute("data-selected");
          }
        }
      }
    },
  };
})();


/* dnd.js — the node-DnD gesture shared by `dropzone` / `draggable`.
 *
 * ⚠️ **Distinct from the "drag" of the repository's two other
 * families**, and §6 of the roadmap insists because confusing them
 * costs:
 *   - `slider.js`      = pointer-drag (pointer → continuous value);
 *   - `file_upload.js` = native HTML5 DnD (OS files, DataTransfer).
 * This is the third: **moving a node** from one position to another.
 *
 * ── Why Pointer Events and not the HTML5 `draggable` API ─────────────
 * The HTML5 API simply does not fire `dragstart` on mobile. A framing
 * decision, settled: Pointer Events, like the slider.
 *
 * ── Why delegation to the document ───────────────────────────────────
 * One listener per zone would have to re-wire after every morph, and a
 * `bz-init` that runs again double-binds (the bridge's rescan disposes
 * and re-binds the directives). A single listener on the document,
 * which finds its target through `closest()`, is **insensitive to the
 * morph** and keeps no state on the nodes.
 *
 * ── Why we move the REAL node, with no clone ─────────────────────────
 * The reordering is applied to the DOM during the gesture. So:
 *   1. the preview is free — no ghost to position, no offset to compute
 *      for the neighbours, the browser reflows by itself;
 *   2. at the drop, **the DOM's order IS the result** — we read the
 *      indices instead of computing them, so the preview cannot lie
 *      about what leaves for the server;
 *   3. it is already the optimistic path. The server re-renders,
 *      idiomorph re-pairs by `bz-id` and the moved node is REUSED, not
 *      recreated — gated by
 *      `tests/runtime_js/test_morph_preserves_reordered_nodes.py`.
 *
 * ── A refusal's snap-back needs code ──────────────────────────────────
 * A handler that refuses by mutating NOTHING — the case `Move` documents
 * as THE way to refuse — makes no zone re-render: the server answers
 * zero bytes and the card would stay where the finger let it go, so the
 * morph cannot be what puts it back.
 *
 * Hence the WITNESS below. It costs the normal case nothing and asks
 * nothing of the app's author: the attribute is set on the item at drop
 * time, the server never renders it, so idiomorph erases it as soon as
 * it re-pairs the node. If it is still there when the request comes
 * back, nobody answered for that item — and the gesture is undone.
 *
 * ── The geometry is READ, never configured ───────────────────────────
 * The axis (a vertical or horizontal list) is inferred from the real
 * position of two items, as the Carousel infers its stride. No
 * breakpoint, no `orientation=` prop to keep in sync with the CSS.
 *
 * DOM contract expected from Python (no new `bz-*` directive):
 *   zone : data-bz-dropzone="<name>"  data-bz-accepts="a,b"  [data-bz-locked]
 *          [data-bz-terminal] (action target, never an in-flow destination)
 *          + a hidden carrier [data-bz-move-carrier] holding the hx-post
 *   item : data-bz-draggable  data-bz-key="…"  [data-bz-group] [data-bz-disabled]
 *          [data-bz-handle]  → when present, only [data-bz-drag-handle] grabs
 */
(function () {
  "use strict";
  const $bz = (window.$bz = window.$bz || {});

  //: The gesture's rules live ONCE, in `$bz.gesture` (`helpers.js`),
  //: shared with the scheduler. The mouse threshold PRESERVES THE CLICK
  //: (without it every click on a card would start a move); the touch
  //: hold and its tolerance PRESERVE THE SCROLL (a finger running down a
  //: list must not carry off the card it brushed).
  const G = $bz.gesture;
  const MOUSE_THRESHOLD_PX = G.MOUSE_THRESHOLD_PX;
  const TOUCH_HOLD_MS = G.TOUCH_HOLD_MS;
  const TOUCH_TOLERANCE_PX = G.TOUCH_TOLERANCE_PX;

  //: The witness of a drop awaiting an answer. Set on the item, erased
  //: by the morph — the server never renders this attribute, so
  //: idiomorph removes it when it re-pairs the node. It is the only
  //: measurement possible from the client of "did the answer touch this
  //: item", and it asks for no new protocol.
  const PENDING_ATTR = "data-bz-drop-pending";
  ($bz._witnesses = $bz._witnesses || new Set()).add(PENDING_ATTR);

  const ZONE_SEL = "[data-bz-dropzone]";
  const ITEM_SEL = "[data-bz-draggable]";
  const HANDLE_SEL = "[data-bz-drag-handle]";
  const CARRIER_SEL = "[data-bz-move-carrier]";
  //: Set on the ZONE while an overwrite is hovered. The theme hooks onto
  //: it; nothing else reads it.
  const REPLACE_ATTR = "data-bz-drop-replace";

  //: One gesture at a time — it is a physical truth of the pointer, not
  //: an implementation shortcut. `armed` = finger down, drag not decided
  //: yet; `active` = drag in progress.
  let armed = null;
  let active = null;

  // ── Reading the DOM contract ─────────────────────────────────────────

  function zoneOf(el) {
    return el ? el.closest(ZONE_SEL) : null;
  }

  function itemsOf(zone) {
    // The items of a NESTED zone are not ours.
    return Array.prototype.filter.call(
      zone.querySelectorAll(ITEM_SEL),
      function (it) { return zoneOf(it) === zone; }
    );
  }

  function indexOf(item) {
    const zone = zoneOf(item);
    return zone ? itemsOf(zone).indexOf(item) : -1;
  }

  /* Where to insert, when there is no item to aim at.
     ⚠️ **An item is NOT necessarily a direct child of its zone.** A
     dropzone arranges nothing — it receives — so the caller stacks its
     items with the container they already use (`ui.vstack`, `ui.grid`).
     Inserting into the ZONE would put the card beside that stack, and
     `insertBefore` flatly raises when the target is not its child.
     That is the bug the bench page revealed and that the gesture tests'
     synthetic DOM could not produce. */
  function itemsContainer(zone) {
    const first = itemsOf(zone)[0];
    if (first) return first.parentNode;
    /* An EMPTY zone. The zone itself is not a valid fallback: the next
       server render does not put the card back in the stack.
       The moved node keeps its `bz-id`, which encodes its path in the
       tree; that path has changed, so idiomorph does not re-pair it and
       the card STAYS where it was dropped — that is to say a direct
       child of the zone, OUTSIDE the container the app rendered.

       It happens on a drag that HESITATES: you take the item out of its
       zone, change your mind, come back. The original zone is then empty,
       the item would be re-appended at its root, and it would show beside
       its box instead of inside it. A hesitant gesture is the ordinary
       gesture.

       What we do instead: the app rendered its items in a container of
       its own (a `vstack`, a grid) — it is still there, empty. We walk
       down the chain of SINGLE children to find it again. The hidden
       carrier of the `hx-post` does not count: it is always present and
       would skew the tally. */
    let node = zone;
    for (;;) {
      const kids = Array.prototype.filter.call(
        node.children,
        function (k) { return !k.matches(CARRIER_SEL); }
      );
      if (kids.length !== 1) return node;
      node = kids[0];
    }
  }

  /* A zone that holds only ONE element. The default, `many`, is not
     written: the absence of the attribute is enough. */
  function holdsOne(zone) {
    return zone.getAttribute("data-bz-holds") === "one";
  }

  /* Mark the target of an OVERWRITE, and mark only it. */
  function markReplace(zone) {
    if (active.replaceZone === zone) return;
    clearReplace();
    active.replaceZone = zone;
    if (zone) zone.setAttribute(REPLACE_ATTR, "true");
  }

  function clearReplace() {
    if (active && active.replaceZone) {
      active.replaceZone.removeAttribute(REPLACE_ATTR);
      active.replaceZone = null;
    }
  }

  function groupOf(item) {
    return item.getAttribute("data-bz-group") || "";
  }

  /* Does the zone accept this group?
     ⚠️ An absent `data-bz-accepts` does NOT mean "accepts anything". A
     zone with no declaration receives **only its own items**: two
     independent lists on the same page must not swap cards because
     nobody declared anything. It is Sortable.js's default (an anonymous
     group is unique per instance there): without it, grabbing a card
     lights up every unrelated zone on the page.
     Receiving from elsewhere is therefore an OPT-IN, not a default. */
  function accepts(zone, group, originZone) {
    //: ⚠️ `accepts` governs ENTRY FROM ELSEWHERE, not internal
    //: reordering. Reordering within its own zone is not entering it:
    //: the item is already there, and nobody declared anything about
    //: that. Consulting `accepts` here would freeze a whole list as soon
    //: as the items' `group=` does not answer its `accepts=`:
    //: `accepts=["card"]` on items with no group would make the zone
    //: totally inert, in silence. Sortable.js separates `put` (receive) from
    //: `sort` (reorder) for the same reason.
    if (zone === originZone) return true;
    const raw = (zone.getAttribute("data-bz-accepts") || "").trim();
    //: Absent OR empty: the zone receives nothing from elsewhere. Both
    //: are equivalent now the internal case is out — so `accepts=[]`
    //: really seals what it announces, which was not the case when the
    //: empty list was confused with "not declared".
    if (!raw) return false;
    return raw.split(",").some(function (g) { return g.trim() === group; });
  }

  /* §6's two doors, kept SEPARATE: `accepts` decides entry, `locked`
     decides exit. A wastebasket is a zone that accepts a group and from
     which nothing comes out. */
  function canLeave(zone) {
    return !zone.hasAttribute("data-bz-locked");
  }

  function canEnter(zone, group, originZone) {
    if (!accepts(zone, group, originZone)) return false;
    if (zone !== originZone && !canLeave(originZone)) return false;
    return true;
  }

  // ── Measured geometry ────────────────────────────────────────────────

  /* The dominant axis, inferred from two real items. A list whose items
     mostly spread in X is horizontal — the CSS has already decided, we
     only read it. Fallback to the vertical axis (the common case) when
     there are not two items to compare. */
  function axisOf(zone) {
    //: The dragged item is NOT excluded: we move the real node, so it is
    //: still in the flow and its box is as valid as any other's. Excluding
    //: it would leave a list of TWO items with a single reference point,
    //: so a fallback to the vertical axis: a horizontal row of two cards
    //: would be impossible to reorder, the comparison being made on a Y
    //: both share.
    const items = itemsOf(zone);
    if (items.length >= 2) {
      const a = items[0].getBoundingClientRect();
      const b = items[1].getBoundingClientRect();
      if (a.left !== b.left || a.top !== b.top) {
        return Math.abs(b.left - a.left) > Math.abs(b.top - a.top) ? "x" : "y";
      }
    }
    //: A single item (or two overlapping): nothing left to measure
    //: between two boxes, so we ask the CSS what it decided. Always
    //: READ, never configured — no `orientation=` prop to keep in sync.
    const box = itemsContainer(zone);
    const dir = (getComputedStyle(box).flexDirection || "");
    return dir.indexOf("row") === 0 ? "x" : "y";
  }

  /* Should we insert AFTER the hovered item? We compare the pointer to
     the middle of its box, along the list's axis. */
  function isPastMiddle(rect, x, y, axis) {
    return axis === "x"
      ? x - rect.left > rect.width / 2
      : y - rect.top > rect.height / 2;
  }

  // ── Le geste ─────────────────────────────────────────────────────────

  function disarm() {
    if (armed && armed.timer) clearTimeout(armed.timer);
    armed = null;
  }

  function onPointerDown(e) {
    if (active || armed) return;
    //: The main button only: a right click opens a menu, it does not
    //: grab.
    if (e.pointerType === "mouse" && e.button !== 0) return;

    const item = e.target.closest ? e.target.closest(ITEM_SEL) : null;
    if (!item || item.hasAttribute("data-bz-disabled")) return;
    const zone = zoneOf(item);
    if (!zone) return;

    //: `handle=True`: the whole card stays inert, only the handle
    //: grabs. It is an opt-in RESTRICTION, not the default gesture.
    if (item.hasAttribute("data-bz-handle")) {
      const handle = e.target.closest(HANDLE_SEL);
      if (!handle || !item.contains(handle)) return;
    }

    armed = {
      item: item,
      zone: zone,
      pointerId: e.pointerId,
      touch: e.pointerType === "touch",
      x: e.clientX,
      y: e.clientY,
      timer: null,
    };

    if (armed.touch) {
      //: Touch: it is TIME that decides, not distance.
      armed.timer = setTimeout(function () {
        if (armed) begin();
      }, TOUCH_HOLD_MS);
    }
  }

  function begin() {
    if (!armed) return;
    const a = armed;
    if (a.timer) clearTimeout(a.timer);
    armed = null;

    active = {
      item: a.item,
      originZone: a.zone,
      originIndex: indexOf(a.item),
      //: Enough to undo the gesture exactly — `insertBefore(item, null)`
      //: is an append, so an item taken from the last position restores
      //: itself with no special case.
      originParent: a.item.parentNode,
      originNext: a.item.nextSibling,
      group: groupOf(a.item),
      pointerId: a.pointerId,
    };
    //: An attribute, not a class: the theme hooks onto it with
    //: `data-[bz-dragging]:…`, and a morph that rewrites `class=` cannot
    //: erase it by accident.
    active.item.setAttribute("data-bz-dragging", "true");
    /* ⚠️ THE AXIS — a HOOK for the theme, not a runtime setting.
       The shipped default does nothing with it: a card in flight keeps
       its size (cf. `draggable`'s `dragging` slot). It is published so
       that an app preferring a PLACEHOLDER can get one by overriding
       that slot, with no prop and without touching the gesture.

       Why the axis and not a boolean: "smaller" does not mean the same
       thing in both directions. A vertical list wants a full-width bar,
       a horizontal row wants a full-height column. CSS cannot measure a
       list; `axisOf` already infers it from the real position of two
       items.

       Why not on a `holds="one"` zone: it inserts nothing. Its card does
       not leave a space to fill, it leaves an EMPTY place — and a theme
       that reduced an occupant to a bar in its chair would tell
       something false. */
    if (!holdsOne(a.zone)) {
      active.item.setAttribute("data-bz-drag-axis", axisOf(a.zone));
    }
    makePreview(a.x, a.y);
    markValidZones();
  }

  /* The preview that follows the pointer.
     Without it, only the LIST moves: the neighbours part, but nothing is
     "in hand" and the gesture reads as a cursor wandering about. It is
     the clone that flies and the original that stays — Sortable.js's and
     dnd-kit's DragOverlay's shape — rather than translating the real
     node, which is already reordered in the flow and would therefore
     move twice.

     ⚠️ **The clone must be ANONYMOUS.** We remove its `id`, `bz-id` and
     `data-bz-draggable`, on it AND on all its descendants: a duplicate
     id would make idiomorph pair anything at the next morph, and a
     duplicate `data-bz-draggable` would skew the indices `itemsOf`
     reads. The rest of its look is a plain clone of what the user was
     already looking at. */
  function makePreview(x, y) {
    const src = active.item;
    const rect = src.getBoundingClientRect();
    const node = src.cloneNode(true);

    node.removeAttribute("data-bz-dragging");
    node.removeAttribute("data-bz-drag-axis");
    const strip = ["id", "bz-id", "data-bz-draggable", "data-bz-key",
                   "data-bz-drag-handle", "data-bz-move-carrier",
                   "data-bz-drag-axis"];
    const scrub = function (el) {
      for (let i = 0; i < strip.length; i++) el.removeAttribute(strip[i]);
    };
    scrub(node);
    Array.prototype.forEach.call(node.querySelectorAll("*"), scrub);

    node.classList.add("bz-drag-preview");
    //: A frozen width: out of the flow, a block no longer has a parent
    //: to inherit from, and the preview would collapse onto its
    //: content.
    node.style.width = rect.width + "px";
    node.style.height = rect.height + "px";
    node.style.left = rect.left + "px";
    node.style.top = rect.top + "px";

    //: The gap between the grabbed point and the card's corner. It is
    //: what stops the card "jumping" under the cursor at the moment you
    //: grab it — it stays held where you took it.
    active.grabDX = x - rect.left;
    active.grabDY = y - rect.top;
    active.preview = node;
    document.body.appendChild(node);
  }

  function movePreview(x, y) {
    if (!active.preview) return;
    active.preview.style.left = (x - active.grabDX) + "px";
    active.preview.style.top = (y - active.grabDY) + "px";
  }

  function dropPreview() {
    if (active && active.preview && active.preview.parentNode) {
      active.preview.parentNode.removeChild(active.preview);
    }
  }

  /* Requirement 1 of the framing: show WHERE the item can land, during
     the gesture. Gated on an attribute set by the gesture, never on
     `:hover` — a hover does not exist for a finger, and that is this
     project's reference pointer. */
  function markValidZones() {
    Array.prototype.forEach.call(
      document.querySelectorAll(ZONE_SEL),
      function (z) {
        if (canEnter(z, active.group, active.originZone)) {
          z.setAttribute("data-bz-drop-ok", "true");
        }
      }
    );
  }

  function clearValidZones() {
    Array.prototype.forEach.call(
      document.querySelectorAll("[data-bz-drop-ok]"),
      function (z) { z.removeAttribute("data-bz-drop-ok"); }
    );
  }

  function onPointerMove(e) {
    if (armed && e.pointerId === armed.pointerId) {
      const far = G.distance(armed, e);
      if (armed.touch) {
        //: The finger ran off before the delay ended: it was a scroll.
        if (far > TOUCH_TOLERANCE_PX) disarm();
      } else if (far >= MOUSE_THRESHOLD_PX) {
        begin();
        //: Follow THIS move too: otherwise a quick flick (or an automation
        //: tool's single move) would start the drag here and drop it in
        //: the origin zone on the next `pointerup`, saving nothing.
        if (active && e.pointerId === active.pointerId) {
          movePreview(e.clientX, e.clientY);
          hoverTo(e.clientX, e.clientY);
        }
      }
      return;
    }
    if (!active || e.pointerId !== active.pointerId) return;

    //: During a touch drag, the gesture is ours: without this the page
    //: scrolls under the card.
    if (e.cancelable) e.preventDefault();
    //: The preview first: it must follow the finger even when the
    //: pointer hovers a zone that refuses, otherwise the card freezes
    //: and the gesture looks broken when it is simply refused.
    movePreview(e.clientX, e.clientY);
    hoverTo(e.clientX, e.clientY);
  }

  //: Hide the node while it is leaving the board (a terminal zone
  //: hovered), and show it again — inline style, put back as it was. A
  //: morph that redraws the node drops the inline style by itself.
  function leave(a) {
    if (a.leaving) return;
    a.leaving = true;
    a.shownDisplay = a.item.style.display;
    a.item.style.display = "none";
  }

  function stay(a) {
    if (!a.leaving) return;
    a.leaving = false;
    a.item.style.display = a.shownDisplay;
  }

  function notTerminal() {
    active.terminalZone = null;
    stay(active);
  }

  /* The core: put the node where the pointer says it is going. */
  function hoverTo(x, y) {
    const under = document.elementFromPoint(x, y);
    if (!under) {
      notTerminal();
      clearReplace();
      return;
    }
    const overZone = zoneOf(under);
    if (!overZone) {
      notTerminal();
      clearReplace();
      return;
    }
    if (!canEnter(overZone, active.group, active.originZone)) {
      notTerminal();
      clearReplace();
      return;
    }

    //: Archive/delete targets receive a Move, but never the real node:
    //: inserting into a clipped, fixed-height target made the card vanish
    //: while its box still occupied space. Over such a zone the card
    //: LEAVES the board instead — back to where it came from (dropped in
    //: the last column crossed, the zone diff never touched it, cf.
    //: `finish`) and hidden there: only the floating preview remains,
    //: what a drop will do.
    if (overZone.hasAttribute("data-bz-terminal")) {
      clearReplace();
      active.terminalZone = overZone;
      backToOrigin(active);
      leave(active);
      return;
    }
    notTerminal();

    /* ⚠️ OVERWRITE. A zone that holds only one element and already
       carries one must receive NOTHING during the gesture: sliding the
       node in would make it contain two occupants — what the user sees
       as "the item takes up an enormous amount of room". We mark it, we
       do not fill it. The drop will go to the handler all the same, and
       the handler decides (swap, refuse): it is the server that
       arbitrates, here we only announce honestly what is going to
       happen. */
    if (holdsOne(overZone) && overZone !== zoneOf(active.item)
        && itemsOf(overZone).length > 0) {
      markReplace(overZone);
      return;
    }
    clearReplace();

    //: Only an item OF the zone hovered is aimed at. Over a zone nested
    //: in an item — a chapter holding its lessons — `closest` finds the
    //: enclosing item first, which belongs to the outer zone: taken for
    //: the target, it stopped the append below, and an empty inner zone
    //: could never be filled.
    let overItem = under.closest(ITEM_SEL);
    if (overItem && zoneOf(overItem) !== overZone) overItem = null;
    if (overItem && overItem !== active.item) {
      const rect = overItem.getBoundingClientRect();
      const axis = axisOf(overZone);
      const after = isPastMiddle(rect, x, y, axis);
      //: Relative to the TARGET'S PARENT, never to the zone — cf.
      //: `itemsContainer`. The items can live at any depth under the
      //: zone.
      overItem.parentNode.insertBefore(
        active.item, after ? overItem.nextSibling : overItem
      );
      return;
    }
    //: Hovering the zone outside any item — typically an empty column
    //: or the space below the last item. We only append if the item is
    //: not already here, otherwise every pointermove would throw it back
    //: to the end.
    if (!overItem && zoneOf(active.item) !== overZone) {
      itemsContainer(overZone).appendChild(active.item);
    }
  }

  function onPointerUp(e) {
    if (armed && e.pointerId === armed.pointerId) return disarm();
    if (!active || e.pointerId !== active.pointerId) return;
    finish();
  }

  function onPointerCancel(e) {
    if (armed && e.pointerId === armed.pointerId) return disarm();
    if (active && e.pointerId === active.pointerId) cancel();
  }

  function onKeyDown(e) {
    if (e.key === "Escape") {
      if (armed) disarm();
      else if (active) cancel();
    }
  }

  function cleanup() {
    dropPreview();
    if (active) {
      clearReplace();
      active.item.removeAttribute("data-bz-dragging");
      active.item.removeAttribute("data-bz-drag-axis");
    }
    clearValidZones();
    active = null;
  }

  /* Cancel = put the node back exactly where it came from. Used by
     Escape and by `pointercancel` — NEVER by a server refusal, which
     goes through the morph (cf. this file's header). */
  function cancel() {
    if (!active) return;
    stay(active);
    active.originParent.insertBefore(active.item, active.originNext);
    cleanup();
  }

  /* Undo the drop if the answer did not confirm it — after the answer's
     swap and rescan (`whenAnswered` waits two frames: checking straight
     away would read the witness before the morph erased it, and EVERY
     drop would be undone). While the server ASKS — a modal dialog open,
     the board not redrawn — the item stays where it was dropped, and
     goes back only if the question ends without an answer that touched
     it. */
  function armSnapBack(item, parent, next, carrier, show) {
    const itemKey = item.getAttribute("data-bz-key") || "";
    const destination = zoneOf(item);
    const destinationName = destination
      ? destination.getAttribute("data-bz-dropzone") || ""
      : "";
    item.setAttribute(PENDING_ATTR, "");
    G.whenAnswered(carrier, {
      untouched: function () { return item.hasAttribute(PENDING_ATTR); },
      undo: function () {
        item.removeAttribute(PENDING_ATTR);
        //: A card that left the board for a terminal zone comes back.
        if (show) show();
        //: The server may have removed the item (archiving): there is
        //: then nothing to put back, and its old parent may itself have
        //: disappeared.
        if (!item.isConnected || !parent.isConnected) return;
        parent.insertBefore(item, next && next.parentNode === parent ? next : null);
      },
      settled: function () { restoreSequentialFocus(itemKey, destinationName); },
    });
  }

  /* Put the starting point of sequential navigation back after the
     morph. A move between zones changes the card's `bz-id`: idiomorph
     then recreates its node and Chromium puts the focus back on BODY. In
     that state, the first Tab is swallowed instead of reaching the next
     control. We focus the card the server rendered as a temporary
     anchor; it does not durably enter the tab order. */
  function restoreSequentialFocus(itemKey, zoneName) {
    if (!itemKey || !zoneName) return;
    const zones = document.querySelectorAll(ZONE_SEL);
    let item = null;
    for (let i = 0; i < zones.length && !item; i++) {
      if (zones[i].getAttribute("data-bz-dropzone") !== zoneName) continue;
      const candidates = itemsOf(zones[i]);
      for (let j = 0; j < candidates.length; j++) {
        if (candidates[j].getAttribute("data-bz-key") === itemKey) {
          item = candidates[j];
          break;
        }
      }
    }
    if (!item || !item.isConnected) return;
    const hadTabindex = item.hasAttribute("tabindex");
    if (!hadTabindex) item.setAttribute("tabindex", "-1");
    item.focus({preventScroll: true});
    if (!hadTabindex) {
      item.addEventListener("blur", function removeTemporaryTabindex() {
        item.removeAttribute("tabindex");
      }, {once: true});
    }
  }

  //: The node where the gesture took it from — for a drop that will not
  //: place it (a terminal zone, an overwrite). A no-op when it is there.
  function backToOrigin(a) {
    const next = a.originNext && a.originNext.parentNode === a.originParent
      ? a.originNext : null;
    if (a.item.parentNode === a.originParent && a.item.nextSibling === next) return;
    a.originParent.insertBefore(a.item, next);
  }

  function finish() {
    const a = active;
    //: An overwrite did NOT move the node: the target zone is read from
    //: the mark, not from the position. Its index is 0 — a zone with one
    //: element has no other.
    const remplace = a.replaceZone;
    const terminal = a.terminalZone;
    const toZone = terminal || remplace || zoneOf(a.item);
    const toIndex = terminal || remplace ? 0 : indexOf(a.item);
    const origin = {parent: a.originParent, next: a.originNext, item: a.item};
    cleanup();
    //: The click the browser fires on the card it just let go would
    //: open it (a card with `on_click`).
    G.swallowClick();
    //: A terminal or an overwrite drop never PLACED the node: it stayed
    //: where the pointer last crossed an in-flow zone. Put it back where
    //: it came from, so the page matches the server's last render — the
    //: answer then removes or moves it like any other change. Left
    //: behind, it would sit in a column the server never changed: the zone
    //: diff (which ships only what the server changed) would never touch
    //: it, its witness would survive, and the drop would be "undone".
    if (terminal || remplace) backToOrigin(a);
    //: Dropped on a terminal zone, the card stays hidden until the answer
    //: removes it — or shows it again if nothing leaves.
    const show = function () { stay(a); };
    if (!toZone) return show();

    //: Nothing moved → no server round trip. A drag that puts the item
    //: back where it was must not produce a `Move`.
    if (!remplace && toZone === a.originZone && toIndex === a.originIndex) {
      return show();
    }

    //: It is the RECEIVING zone that decides — its `on_move` is the
    //: handler, and its carrier holds the hx-post.
    //: ⚠️ Filtered by `zoneOf`, like `itemsOf`: `querySelector` searches
    //: the WHOLE subtree, so a nested dropzone — whose carrier
    //: necessarily precedes the parent's, since it is rendered last —
    //: would capture the parent's drop and POST it to ITS handler.
    const carrier = Array.prototype.find.call(
      toZone.querySelectorAll(CARRIER_SEL),
      function (el) { return zoneOf(el) === toZone; }
    );
    if (!carrier) return show();

    const told = {
      item_key: a.item.getAttribute("data-bz-key") || "",
      from_zone: a.originZone.getAttribute("data-bz-dropzone") || "",
      to_zone: toZone.getAttribute("data-bz-dropzone") || "",
      from_index: a.originIndex,
      to_index: toIndex,
    };
    carrier.value = JSON.stringify(told);
    //: The home-made transport — the JS writes, dispatches, and it is
    //: the carrier's hx-post that leaves. No `fetch` here: the transport
    //: boundary belongs to the bridge (charter, principle 2).
    armSnapBack(origin.item, origin.parent, origin.next, carrier, show);
    $bz.helpers.emitChange(carrier, "move", told);
  }

  //: Once the gesture is GRABBED, the finger is ours: it is this
  //: `preventDefault` on the `touchmove` that stops the browser
  //: scrolling under the card.
  //:
  //: It does NOT duplicate `onPointerMove`'s. A `preventDefault` on a
  //: `pointermove` does not cancel a touch scroll — only the
  //: `touchmove` can, and only in a NON-PASSIVE listener. The item
  //: leaves `pan-x pan-y` (without it the finger could not scroll a
  //: column of cards), so the gesture has to be taken over at the moment
  //: the long press succeeds — and at that precise instant the finger
  //: has not moved, so no scroll is in progress and the takeover is
  //: clean.
  //:
  //: ⚠️ We prevent NOTHING as long as the drag is only `armed`: that is
  //: exactly the "a finger runs down the list and brushes a card" case,
  //: which the 8 px tolerance leaves to the scroll.
  function onTouchMove(e) {
    if (active && e.cancelable) e.preventDefault();
  }

  document.addEventListener("pointerdown", onPointerDown, true);
  //: `passive: false` — `onPointerMove` must be able to
  //: `preventDefault()` to hold the scroll during a MOUSE drag (text
  //: selection, native image drag).
  document.addEventListener("pointermove", onPointerMove, { passive: false });
  document.addEventListener("touchmove", onTouchMove, { passive: false });
  document.addEventListener("pointerup", onPointerUp, true);
  document.addEventListener("pointercancel", onPointerCancel, true);
  document.addEventListener("keydown", onKeyDown, true);

  //: Exposed for the tests and for a future component that would drive
  //: the gesture. The public contract stays the data attributes.
  $bz.dnd = {
    MOUSE_THRESHOLD_PX: MOUSE_THRESHOLD_PX,
    TOUCH_HOLD_MS: TOUCH_HOLD_MS,
    TOUCH_TOLERANCE_PX: TOUCH_TOLERANCE_PX,
    _state: function () { return { armed: armed, active: active }; },
    _axisOf: axisOf,
    _accepts: accepts,
    _canEnter: canEnter,
    _indexOf: indexOf,
  };
})();


/* resizable.js — the shared scope of the Resizable component (split panes).
 *
 * ⚠️ **The repository's third "drag" family, and confusing it costs**:
 *   - `slider.js`      = pointer → a VALUE on a scale;
 *   - `dnd.js`         = moving a NODE from one position to another;
 *   - here                = pointer → a DIMENSION. Nothing moves,
 *                           nothing changes parent: two neighbours
 *                           re-share the room they already occupy.
 * It is the slider's family (pointer-drag, continuous delta), not the
 * node-DnD's — the roadmap has said so since framing #6, and this file
 * therefore has NO dependency on `dnd.js`.
 *
 *   bz-data="{...$bz.resizable.scope, sizes: [30,70], _mins: [10,10],
 *             _vertical: false, _group: null,
 *             _read(){…}, _write(v){…}}"
 *
 * ``_group`` is captured at the root's ``bz-init`` (`_group = $el`): a
 * scope method has no access to ``$el``, only directives do (same
 * constraint and same remedy as Slider and Carousel).
 *
 * ── The split is in WEIGHTS, never in pixels ──────────────────────────
 * Each panel is a ``flex-grow: w`` on a zero basis, so the browser
 * shares the remaining room pro rata to the weights — the handles'
 * width is deducted BEFORE the split, without our knowing it, and a
 * group that shrinks keeps its proportions without our listening to any
 * ``resize``. Pixels enter here in a single place: the conversion of the
 * pointer's delta, measured at every gesture.
 *
 * ── Two neighbours, never more ────────────────────────────────────────
 * Dragging a handle redistributes ONLY the pair it separates: their sum
 * is invariant during the gesture, so the other panels do not move a
 * pixel. It is the behaviour of every real splitter, and it is what
 * makes the gesture predictable — a user widening their left column does
 * not want to see the right one reorganise itself.
 *
 * ── Why nothing is published DURING the gesture ───────────────────────
 * The drag writes the styles live (the fast path, no signal tick); the
 * state is only published on release. Publishing every frame would send
 * one ``change`` per pixel to the server, and would write localStorage a
 * hundred times a second when the ClientState is ``persist="local"``.
 * Same reason as the Carousel's ``SETTLE_MS``.
 */
(function () {
  "use strict";
  const $bz = (window.$bz = window.$bz || {});

  //: The step of a keyboard arrow, in percentage points. The ARIA
  //: "window splitter" pattern requires the handle to be drivable
  //: without a pointer — it is the only way to resize from the
  //: keyboard, and it is also the only one that works with no mouse AND
  //: no touch screen.
  const KEY_STEP = 2;

  $bz.resizable = {
    scope: {
      // ── Reading the DOM ──────────────────────────────────────────
      // ``:scope >`` and not a bare querySelectorAll: a Resizable NESTED
      // in a panel (the "editor + preview inside a resizable column" use
      // case) would otherwise see its child's panels as its own.
      _panels() {
        if (!this._group) return [];
        return Array.prototype.slice.call(
          this._group.querySelectorAll(":scope > [data-bz-rz-panel]")
        );
      },
      _px(el) {
        const r = el.getBoundingClientRect();
        return this._vertical ? r.height : r.width;
      },

      // ── State → layout ───────────────────────────────────────────
      // Called from the root's ``bz-effect``: reading ``_read()``
      // registers the dependency, so an EXTERNAL writer (a binding
      // driven elsewhere, a `.set([…])`, a restore from localStorage at
      // boot) re-lays the panels by itself.
      //
      // It is also what makes the anti-FOUC free: the root carries a
      // ``bz-data``, so it stays ``visibility:hidden`` until
      // ``html.bz-ready`` (cf. ``render/shell.py`` § _ANTI_FLASH_STYLE),
      // and the boot hydrates the store from localStorage BEFORE the
      // scan that runs this effect. The remembered sizes are therefore
      // in place at the first painted pixel — no pre-paint script to
      // write.
      _apply() {
        // The panels first, their COUNT then passed to ``_weights``:
        // without that both methods each launch the same
        // ``querySelectorAll``, at every tick of the effect.
        const panels = this._panels();
        const sizes = this._weights(panels.length);
        for (let i = 0; i < panels.length; i++) {
          const w = sizes[i];
          if (w === undefined) continue;
          // An INLINE style and not a class: the value is continuous
          // (a user stops where they want), so no Tailwind class can
          // express it — and an assembled class would not exist in
          // production's compiled CSS.
          panels[i].style.flexGrow = String(w);
        }
        // ``aria-valuenow`` is set back HERE, in the single reactive
        // pass, and not only in the gestures. It is what makes the FOUR
        // write paths correct by construction: pointer, keyboard,
        // `.set()` / `.reset()`, and a binding driven elsewhere. Copied
        // into each gesture, it only covered the first two —
        // `.set([20, 80])` left a screen reader on the first render's
        // value.
        if (this._group) {
          const handles = this._group.querySelectorAll(
            ":scope > [data-bz-rz-handle]"
          );
          for (let i = 0; i < handles.length; i++) {
            this._announce(handles[i], sizes[i]);
          }
        }
      },

      // The weight array **normalised to 100**. A panel added by a
      // morph without ``sizes`` following (a list of panels coming from
      // data) would otherwise get ``undefined``: it falls back to an
      // equal share rather than disappearing.
      //
      // ⚠️ **The normalisation is not cosmetic: without it the component
      // is inert.** ``_mins`` travels in PERCENTAGE POINTS; if the weights
      // stay raw, the two scales do not talk to each other:
      // ``sizes=[1, 3]`` (a documented writing — it is the RATIO that
      // counts) with ``min_size=15`` gives ``pair = 4``, ``lo = 15``, so
      // ``hi < lo`` at every frame, so a handle that NEVER moves — with no
      // error, nothing in the console. In local mode the ``bz-data``
      // seeded by the server is already normalised; only binding mode
      // shows the defect, the very one the component puts forward for
      // ``persist="local"``.
      //
      // An EXACT MIRROR of ``normalize_weights`` (``resizable.py``),
      // gated by ``tests/runtime_js/test_resizable_mirrors_python.py``,
      // which runs both halves over the same table.
      //
      // ``count`` is optional: a caller that has ALREADY counted the
      // panels passes it (``_apply``), the others let it be derived.
      // ⚠️ The ``_read()`` call stays the FIRST line: it is what
      // registers the effect's reactive dependency, and moving it after
      // an early return would lose it in silence.
      _weights(count) {
        const raw = this._read();
        const n = count === undefined ? this._panels().length : count;
        if (n <= 0) return [];
        const share = 100 / n;
        const out = [];
        let total = 0;
        for (let i = 0; i < n; i++) {
          const v = Array.isArray(raw) ? Number(raw[i]) : NaN;
          const w = isFinite(v) && v >= 0 ? v : share;
          out.push(w);
          total += w;
        }
        if (total <= 0) return out.map(() => Math.round(share * 100) / 100);
        return out.map((w) => Math.round((w * 100) / total * 100) / 100);
      },

      _min(i) {
        const m = Array.isArray(this._mins) ? Number(this._mins[i]) : 0;
        return isFinite(m) && m > 0 ? m : 0;
      },

      // The CEILING, in percentage points. ``100`` is the neutral value
      // and not a sentinel: a panel that can take all the room is not
      // bounded.
      _max(i) {
        const m = Array.isArray(this._maxs) ? Number(this._maxs[i]) : 100;
        return isFinite(m) && m > 0 && m <= 100 ? m : 100;
      },

      // ── The gesture ──────────────────────────────────────────────
      // No activation threshold, unlike the node-DnD: a splitter's
      // handle has no competing "click" to preserve (it does nothing
      // else), and it is already a dedicated target. The DnD's threshold
      // exists so that clicking a CARD stays a click; here it would
      // protect nothing and would add latency to the first pixel.
      _start(e, i) {
        const panels = this._panels();
        const a = panels[i];
        const b = panels[i + 1];
        if (!a || !b) return;
        const totalPx = panels.reduce((s, p) => s + this._px(p), 0);
        if (!totalPx) return;
        const weights = this._weights(panels.length);
        this._drag = {
          i: i,
          from: this._vertical ? e.clientY : e.clientX,
          // The px → weight factor is frozen at the START of the
          // gesture, and it is deliberate: the sum of the weights does
          // not move while you drag (we only redistribute it), so the
          // ratio stays right until release.
          factor: weights.reduce((s, w) => s + w, 0) / totalPx,
          // The left panel's weight at the START of the gesture: it is
          // the base the delta adds to, so it must not follow the
          // intermediate values (otherwise the movement accumulates and
          // the pointer "slides" under the handle). The right weight is
          // derived from the pair — no need to remember it.
          a: weights[i],
          sizes: weights,
          // Both panels and the handle are HELD here, not re-searched
          // at every frame: ``_move`` runs at the pointer's cadence, and
          // none of this can change during a gesture. Without that
          // capture, each frame relaunched TWO ``querySelectorAll`` (the
          // panels, then the handles for ``aria-valuenow``) to reach
          // three known nodes.
          aEl: a,
          bEl: b,
          handle: e.currentTarget,
        };
        // Capture on the HANDLE: the cursor leaves its box at the very
        // first pixel (it is a few points wide), and with no capture the
        // gesture would stop there.
        $bz.helpers.capturePointer(e.currentTarget, e);
      },

      // Distribute ``want`` over the pair ``i`` / ``i+1``, in place,
      // respecting both minimums. Returns ``false`` when the pair is
      // FROZEN — the case where the two minimums do not fit inside it
      // (60 + 60 in 100): we prefer to move nothing rather than violate
      // one of them on the grounds that the other requires it too.
      //
      // A single copy for the pointer AND the keyboard: it is the same
      // arithmetic, only ``want``'s origin differs (a pointer delta, or
      // an arrow step). Written twice, it would have been fixed one time
      // in two.
      _pair(sizes, i, want) {
        const pair = sizes[i] + sizes[i + 1];
        // The four constraints cross: the LEFT floor and the RIGHT
        // ceiling push the handle the same way (to the right), the other
        // two the other way. Hence the ``max`` on the floors and the
        // ``min`` on the ceilings, expressed in the same unit — the left
        // panel's size.
        const lo = Math.max(this._min(i), pair - this._max(i + 1));
        const hi = Math.min(pair - this._min(i + 1), this._max(i));
        // A FROZEN pair: the constraints do not hold together (60 + 60
        // in 100, or a ceiling under a floor). We prefer to move nothing
        // rather than violate one on the grounds that another requires
        // it.
        if (hi < lo) return false;
        sizes[i] = Math.max(lo, Math.min(hi, want));
        sizes[i + 1] = pair - sizes[i];
        return true;
      },

      // Publish: it is here, and only here, that the state leaves the
      // gesture. Rounding to two decimals avoids persisting
      // seventeen-digit floats in localStorage.
      _publish(sizes) {
        this._write(sizes.map((w) => Math.round(w * 100) / 100));
      },

      _move(e) {
        const d = this._drag;
        if (!d) return;
        const delta =
          ((this._vertical ? e.clientY : e.clientX) - d.from) * d.factor;
        if (!this._pair(d.sizes, d.i, d.a + delta)) return;
        // A DIRECT write, not going through the state: see the file's
        // header. Publication happens once, on release.
        d.aEl.style.flexGrow = String(d.sizes[d.i]);
        d.bEl.style.flexGrow = String(d.sizes[d.i + 1]);
        this._announce(d.handle, d.sizes[d.i]);
      },

      _end(e) {
        const d = this._drag;
        this._drag = null;
        if (!d) return;
        $bz.helpers.releasePointer(d.handle, e);
        this._publish(d.sizes);
      },

      // ── a11y ─────────────────────────────────────────────────────
      // ``aria-valuenow`` says "the panel before me occupies N %". The
      // server renders it only once, statically — the handle is not a
      // component, it has no reactive prop to bind — so it is the JS
      // that keeps it up to date.
      //
      // **A single author for the published state**: ``_apply``, the
      // reactive pass. Everything that writes the state goes back
      // through it, so the four paths are covered without any of them
      // having to think about it. ``_move`` calls it IN ADDITION, and
      // only because it is the only one that publishes nothing before
      // release — without that a screen reader would announce the
      // previous value for the whole duration of the drag.
      _announce(handle, value) {
        if (handle && value !== undefined) {
          handle.setAttribute("aria-valuenow", String(Math.round(value)));
        }
      },

      // ── Collapsing ───────────────────────────────────────────────
      // Put panel ``i`` away by giving its place to ``j``, its opposite
      // neighbour. Replaying the gesture restores it.
      //
      // ⚠️ **Collapsing OVERRIDES ``min_size``, and that is the point.**
      // It therefore does NOT go through ``_pair``, which exists to stop
      // a minimum being crossed by DRAGGING. The minimum says "do not
      // shrink me by accident"; collapsing is an explicit gesture that
      // says "put it away". Without that way out, ``min_size=20`` would
      // make a collapsible panel non-collapsible, and a second
      // vocabulary would be needed to say the same thing. VS Code and
      // shadcn do the same.
      //
      // ``_folded`` remembers the previous size, by index. It lives in
      // the scope — so it survives a morph, like the rest of the
      // component's state — and not on the server, which has no idea
      // what somebody put away three seconds ago.
      _fold(i, j) {
        const sizes = this._weights();
        if (sizes[i] === undefined || sizes[j] === undefined) return;
        const memo = this._folded || (this._folded = {});
        const back = memo[i];
        const pair = sizes[i] + sizes[j];

        if (back !== undefined) {
          // Restore. The neighbour keeps its own floor: giving the
          // stored panel back more than the pair contains would crush
          // it.
          const want = Math.min(back, Math.max(0, pair - this._min(j)));
          sizes[i] = want;
          sizes[j] = pair - want;
          delete memo[i];
        } else if (sizes[i] <= 0.01) {
          // Collapsed WITH NO memory: the case of a split restored
          // from localStorage, where a panel was at zero before the F5.
          // Without that branch, double-clicking would do nothing at all
          // — the panel would stay put away forever. It comes back to
          // its floor, or to an equal share if it has none.
          const want = Math.min(
            this._min(i) || 100 / Math.max(1, this._panels().length),
            Math.max(0, pair - this._min(j))
          );
          sizes[i] = want;
          sizes[j] = pair - want;
        } else {
          memo[i] = sizes[i];
          sizes[j] = pair;
          sizes[i] = 0;
        }
        this._publish(sizes);
      },

      // ── Keyboard ─────────────────────────────────────────────────
      // The handle is a focusable ``role="separator"``: the arrows move
      // it, like a slider. The step is in percentage points, so
      // independent of the group's width.
      _key(e, i, fold) {
        const key = e.key;
        // ``Enter`` collapses, when the handle touches a collapsible
        // panel. It is the double-click's keyboard twin, and the ARIA
        // "window splitter" pattern prescribes it: a focusable handle
        // whose only collapse command were a mouse gesture has no
        // collapse at all for whoever has no mouse.
        if (key === "Enter" && Array.isArray(fold)) {
          e.preventDefault();
          this._fold(fold[0], fold[1]);
          return;
        }
        const back = this._vertical ? "ArrowUp" : "ArrowLeft";
        const fwd = this._vertical ? "ArrowDown" : "ArrowRight";
        if (key !== back && key !== fwd) return;
        e.preventDefault();
        const sizes = this._weights();
        const step = key === back ? -KEY_STEP : KEY_STEP;
        // No ``_announce`` here: ``_publish`` relaunches ``_apply``,
        // which sets every ``aria-valuenow`` back. Calling it IN
        // ADDITION would give the same value two authors.
        if (this._pair(sizes, i, sizes[i] + step)) this._publish(sizes);
      },

      // ── Imperative ───────────────────────────────────────────────
      set(v) {
        if (Array.isArray(v)) this._write(v);
      },
      // Back to the equal split. A method and not a "re-set of the
      // initial sizes": the server renders the component only once, so
      // "initial" has no stable meaning once the user has dragged a
      // handle — whereas "in equal shares" is true at any moment.
      reset() {
        const n = this._panels().length;
        if (!n) return;
        this._write(new Array(n).fill(Math.round((100 / n) * 100) / 100));
      },
    },
  };
})();


/* signature_pad.js — the SignaturePad component's shared scope.
 *
 * **The framework's only `<canvas>`** (the charts are SVG). Everything
 * that follows comes from two properties of the canvas the rest of the
 * framework never had to deal with: it has no intrinsic size, and
 * **resizing it clears it**.
 *
 * ── The third member of the pointer-drag family ───────────────────────
 *   - `slider.js`      = pointer → a VALUE on a scale;
 *   - `resizable.js`   = pointer → a DIMENSION;
 *   - here                = pointer → a STROKE.
 * Nothing to do with `dnd.js`'s node-DnD. The pointer capture goes
 * through `$bz.helpers.capturePointer`.
 *
 *   bz-data="{...$bz.signaturePad.scope, value: '', _canvas: null,
 *             _strokes: [], _drawing: null, _base: null,
 *             _read(){…}, _write(v){…}}"
 *
 * ── Why we keep the POINTS, when there is no undo ─────────────────────
 * It is not to undo — the API only exposes `.clear()`, a signature is
 * redone and not touched up. It is because a canvas **loses its content
 * at every size change**, and a pad in a responsive form really does
 * change: a phone you turn, a panel you open, a `resizable` you drag.
 * Without the points, the signature disappears on rotation. The
 * alternative — reading the bitmap back and redrawing it to scale —
 * degrades at every pass.
 *
 * ── The value is EMPTY as long as nothing is drawn ────────────────────
 * A fresh canvas returns a perfectly valid PNG: a white rectangle.
 * Publishing it would pass "not signed yet" off as "signed", on the
 * server side, with nothing looking wrong. Zero strokes ⇒ empty string.
 */
(function () {
  "use strict";
  const $bz = (window.$bz = window.$bz || {});

  //: The stroke's thickness, in CSS pixels. A constant and not a prop:
  //: a signature has only one weight that works, and making it settable
  //: would add no power.
  const LINE_WIDTH = 2;

  $bz.signaturePad = {
    scope: {
      // ── The canvas and its size ──────────────────────────────────
      // ⚠️ Resizing a canvas CLEARS it, and giving it a size in CSS
      // pixels is not enough: without the density factor, the stroke is
      // blurry on every retina screen — that is to say on every phone,
      // this repository's test environment.
      _resize() {
        const c = this._canvas;
        if (!c) return;
        const box = c.getBoundingClientRect();
        if (!box.width || !box.height) return;
        const dpr = window.devicePixelRatio || 1;
        const w = Math.round(box.width * dpr);
        const h = Math.round(box.height * dpr);
        // Do nothing when nothing has moved: a write to
        // ``canvas.width`` clears the content EVEN if the value is
        // identical. The observer reports at the first wiring, so
        // without that guard the pad would clear at every rescan.
        if (c.width === w && c.height === h) return;
        c.width = w;
        c.height = h;
        const ctx = c.getContext("2d");
        ctx.scale(dpr, dpr);
        this._redraw();
      },

      // Re-wire the observer at every rescan rather than at the
      // ``bz-init``, and file it on the NODE: ``bz-init`` is one-shot
      // per node and idiomorph morphs in place, so an observer installed
      // there would never see a replaced canvas again. Same choice, same
      // reason as the Carousel's ``_observeGeom``.
      _observe() {
        const c = this._canvas;
        if (!c) return;
        if (c._bzPadRo) c._bzPadRo.disconnect();
        const self = this;
        const ro = new ResizeObserver(function () {
          self._resize();
        });
        ro.observe(c);
        c._bzPadRo = ro;
        this._resize();
        this._hydrate();
      },

      // ── The signature ALREADY THERE ──────────────────────────────
      // A reopened record returns its data URL at SSR. Without that
      // load, the frame showed EMPTY — and with no prompt, since the
      // server had already set ``data-empty="false"``. The component
      // therefore announced "there is a signature" while showing none.
      //
      // The loaded image becomes a BACKGROUND LAYER, distinct from the
      // points: ``_redraw`` paints it first, the strokes over it. It is
      // what makes it survive a resize like the rest — without that it
      // would disappear at the first size change, along with the canvas
      // we clear in order to resize it.
      //
      // Once per NODE only (``_bzHydrated``), and not in a reactive
      // effect: ``_publish`` writes into the same state, so an effect
      // that reads it would reload itself at every stroke. After the
      // boot, it is the canvas that is authoritative. A node property
      // and not a scope field, for the same reason as ``_bzPadRo`` — a
      // lifetime that is the canvas's.
      _hydrate() {
        const c = this._canvas;
        if (!c || c._bzHydrated) return;
        c._bzHydrated = true;
        const src = this._read();
        c._bzShown = src || "";
        if (!src) return;
        const img = new Image();
        const self = this;
        img.onload = function () {
          self._base = img;
          self._redraw();
          self._empty(false);
        };
        img.src = src;
      },

      // ── The stroke ───────────────────────────────────────────────
      // The ink is READ on the element (the computed ``color``), never
      // configured: the theme decides, and the value follows dark mode
      // by itself. A ``pen_color`` prop would have frozen a colour that
      // becomes invisible on the other background.
      _ink() {
        return getComputedStyle(this._canvas).color || "#000";
      },
      _redraw() {
        const c = this._canvas;
        if (!c) return;
        const ctx = c.getContext("2d");
        const dpr = window.devicePixelRatio || 1;
        const w = c.width / dpr;
        const h = c.height / dpr;
        ctx.clearRect(0, 0, w, h);
        // The signature already there, under the new strokes. Stretched
        // to the current box: a raster image has no other option, and
        // the original frame is not known — it is the same compromise
        // as any resized raster render.
        if (this._base) {
          try {
            ctx.drawImage(this._base, 0, 0, w, h);
          } catch (err) {
            /* a broken / cross-origin image: we keep the strokes */
          }
        }
        ctx.lineWidth = LINE_WIDTH;
        ctx.lineCap = "round";
        ctx.lineJoin = "round";
        ctx.strokeStyle = this._ink();
        for (const stroke of this._strokes) {
          if (stroke.length < 2) {
            // A lone point: a tap with no movement must leave a mark,
            // otherwise signing with a dot produces nothing.
            if (stroke.length === 1) {
              ctx.beginPath();
              ctx.arc(
                stroke[0][0], stroke[0][1], LINE_WIDTH / 2, 0, Math.PI * 2
              );
              ctx.fillStyle = this._ink();
              ctx.fill();
            }
            continue;
          }
          ctx.beginPath();
          ctx.moveTo(stroke[0][0], stroke[0][1]);
          for (let i = 1; i < stroke.length; i++) {
            ctx.lineTo(stroke[i][0], stroke[i][1]);
          }
          ctx.stroke();
        }
      },

      _at(e) {
        const r = this._canvas.getBoundingClientRect();
        return [e.clientX - r.left, e.clientY - r.top];
      },

      _start(e) {
        if (this._locked()) return;
        // Stops the browser reading the gesture as a text selection or
        // a scroll. ``touch-none`` on the canvas covers the scroll; this
        // covers the rest.
        e.preventDefault();
        $bz.helpers.capturePointer(this._canvas, e);
        this._drawing = [this._at(e)];
        this._strokes.push(this._drawing);
        this._redraw();
        this._empty(false);
      },

      _draw(e) {
        if (!this._drawing) return;
        this._drawing.push(this._at(e));
        this._redraw();
      },

      _end(e) {
        if (!this._drawing) return;
        $bz.helpers.releasePointer(this._canvas, e);
        this._drawing = null;
        // Publish when the pen LIFTS, not at every point: a PNG is
        // tens of kilobytes, and emitting it per frame would send as
        // many POSTs if an ``on_change`` is wired. Same rule as the
        // Resizable's handle release.
        this._publish();
      },

      // ── The value ────────────────────────────────────────────────
      // Written into the STATE (``_write``), not onto the carrier: it is
      // the carrier's ``bz-attr:value`` that reports it into the DOM,
      // and its ``bz-effect`` that draws the ``change`` from it. A
      // single author, the same mechanics as Slider / Carousel /
      // Resizable — writing both would make the form field diverge from
      // the state as soon as an external writer goes through the
      // second.
      _publish() {
        // ``_base`` counts as much as the strokes: a reopened record
        // then submitted without being touched must not ERASE the
        // signature it carried.
        const inked = this._strokes.length || this._base;
        const value = inked ? this._canvas.toDataURL("image/png") : "";
        // What the canvas shows is what it wrote: ``_follow`` must not
        // read its own publication back as an outside change.
        this._canvas._bzShown = value;
        this._write(value);
      },

      // ── A value written from OUTSIDE ─────────────────────────────
      // ``value`` is two-way after the boot too: a server action
      // resetting ``doc.signature`` to "" (a morph keeps the hydrated
      // canvas), or a ``ClientState`` written by another control, must
      // not leave the old ink on screen. A
      // reactive effect re-reading the value would reload at every
      // stroke (``_publish`` writes the same state) — so the canvas
      // remembers what it last SHOWED or PUBLISHED (``_bzShown``), and
      // only a different value repaints: an empty frame for "", the
      // image as the background layer otherwise.
      _follow() {
        const value = this._read() || "";
        const c = this._canvas;
        if (!c || !c._bzHydrated || value === c._bzShown) return;
        c._bzShown = value;
        this._strokes.length = 0;
        this._drawing = null;
        this._base = null;
        if (!value) {
          this._redraw();
          this._empty(true);
          return;
        }
        const img = new Image();
        const self = this;
        img.onload = function () {
          if (c._bzShown !== value) return;
          self._base = img;
          self._redraw();
          self._empty(false);
        };
        img.src = value;
      },

      // The marker the theme reads to show / hide the prompt. An
      // attribute and not a class: ``data-[empty=true]:`` is the
      // Tailwind variant the rest of the repository uses for JS-driven
      // states.
      _empty(value) {
        if (this._canvas && this._canvas.parentElement) {
          this._canvas.parentElement.setAttribute(
            "data-empty", value ? "true" : "false"
          );
        }
      },

      _locked() {
        return !!(
          this._canvas && this._canvas.hasAttribute("data-bz-pad-locked")
        );
      },

      // ── Imperative ───────────────────────────────────────────────
      // ``.clear()`` and nothing else: a signature is redone, it is not
      // touched up. The points kept in memory serve the resize (cf. the
      // header), not an undo.
      clear() {
        this._strokes.length = 0;
        // The background layer goes WITH the strokes: "clear" means an
        // empty frame, not "go back to the previous signature".
        this._base = null;
        this._drawing = null;
        this._redraw();
        this._empty(true);
        this._publish();
      },
    },
  };
})();


/* verbs.js — the CLIENT half of `bretzel.runtime.verbs`.
 *
 * A verb is a BROWSER action triggered from an `on_*=`:
 *
 *     ui.button("Copy", on_click=bretzel.copy(state.api_key))
 *
 * It plugs into the slot that already accepts a client-source STRING —
 * the same as `dialog.open()` — so it adds no plumbing: no request, no
 * directive, no scope.
 *
 * Only `copy` needs this file. `print` and `fullscreen` fit in an
 * expression Python writes out in full; putting them here would have
 * added an indirection with nothing common kept.
 *
 * ⚠️ Why `copy` is NOT a bare `navigator.clipboard.writeText`
 * ---------------------------------------------------------------------
 * The Clipboard API requires a **secure context**. `https://` and
 * `http://localhost` are; `http://192.168.1.20:8000` is NOT. Yet that is
 * very exactly how an internal tool is used — the audience Bretzel aims
 * at. On that path `navigator.clipboard` is `undefined`, and a bare call
 * would raise a TypeError: the button would do nothing, without a word.
 *
 * Hence the fallback on `document.execCommand('copy')`. It is deprecated
 * and it works everywhere, including outside a secure context — it is
 * the only path that exists over there, so "deprecated" is not an
 * argument against it, it is an argument for not using it first.
 */
(function () {
  "use strict";
  const $bz = (window.$bz = window.$bz || {});

  /* The fallback outside a secure context.
   *
   * The `<textarea>` is placed off screen rather than `display:none`: an
   * unrendered element is not selectable, so the copy would fail
   * silently. `readOnly` stops the virtual keyboard opening on mobile,
   * and `position:fixed` avoids scrolling the page to a field nobody
   * should see.
   */
  function viaTextarea(text) {
    const ta = document.createElement("textarea");
    ta.value = text;
    ta.setAttribute("readonly", "");
    ta.style.cssText = "position:fixed;top:0;left:-9999px;opacity:0";
    document.body.appendChild(ta);
    const selection = document.getSelection();
    const previous = selection && selection.rangeCount > 0
      ? selection.getRangeAt(0) : null;
    ta.select();
    let ok = false;
    try {
      ok = document.execCommand("copy");
    } catch (e) {
      ok = false;
    }
    document.body.removeChild(ta);
    // Give the user's selection back: `select()` overwrote it, and
    // losing your highlight because something else was copied shows.
    if (previous && selection) {
      selection.removeAllRanges();
      selection.addRange(previous);
    }
    return ok;
  }

  $bz.verbs = {
    /* Share — the native sheet, or the clipboard.
     *
     * ⚠️ `navigator.share` is **undefined** on desktop Chromium.
     * Its absence is therefore not an edge case, it is the NORMAL case
     * on the machine where Bretzel's users develop.
     *
     * Doing nothing in there would give an inert "Share" button to the
     * majority — exactly what this repository refuses elsewhere (cf. the
     * refusal of `tracks=` on `ui.audio`, which would have promised
     * subtitles and delivered an attribute). The fallback therefore
     * COPIES the URL: the button always does something useful, and it is
     * a contract, not an accident.
     */
    share(data) {
      const charge = data || {};
      // A RELATIVE address (« /partage/x ») is resolved against the
      // page: copied as is, it would be a dead link for whoever receives
      // it, and a page has no public way to know its own origin.
      charge.url = charge.url ? new URL(String(charge.url), window.location.href).href
        : window.location.href;
      if (navigator.share) {
        // A refusal by the user (they close the sheet) rejects the
        // promise. It is not an app error: we do NOT fall back on the
        // copy, otherwise cancelling a share would copy behind their
        // back.
        return navigator.share(charge).then(
          function () { return "shared"; },
          function () { return "cancelled"; }
        );
      }
      return $bz.verbs.copy(charge.url).then(function (ok) {
        return ok ? "copied" : "failed";
      });
    },

    /* Vibrate. `navigator.vibrate` does nothing with no hardware, and a
     * browser without it gives `false` — so there is nothing to fall back
     * on, unlike `share`.
     */
    vibrate(motif) {
      return navigator.vibrate ? navigator.vibrate(motif) : false;
    },

    /* Copy `value` to the clipboard. Returns a promise of a boolean —
     * never an exception: a verb is called from an `on_*=`, where nobody
     * catches anything, so a rejection would surface as an
     * `unhandledrejection` in the app's console.
     */
    copy(value) {
      const text = value === null || value === undefined ? "" : String(value);
      if (window.isSecureContext && navigator.clipboard) {
        return navigator.clipboard.writeText(text).then(
          function () { return true; },
          // A refusal stays possible IN a secure context (permission
          // revoked, document without focus). The fallback is then the
          // last chance, not a dead path.
          function () { return viaTextarea(text); }
        );
      }
      return Promise.resolve(viaTextarea(text));
    },
  };
})();


/* diagram.js — the highlighting of neighbours, in `ui.diagram`.
 *
 * The graph is LAID OUT on the server: positions, layers, paths, it all
 * arrives computed. This file lays out nothing. It does one thing, and
 * it is purely local: when you designate a node, everything that is not
 * connected dims.
 *
 * Why it cannot be a round trip
 * ------------------------------
 * Lighting up does not change WHICH nodes exist, only which are in the
 * foreground. Going through the server for that would cost a request and
 * a morph per designation, for a result the browser already knows: the
 * adjacency is baked into the DOM at render.
 *
 * What the server does keep is the NARROWING (`focus=`) — there the
 * drawn nodes change, so the layout changes, so it has to re-render. The
 * two gestures look alike on screen and do not have the same cost; that
 * is the only reason they are separate.
 *
 * Why a slab rather than an expression per node
 * ----------------------------------------------
 * Same reason as accordion: serialising these method bodies into
 * every node's `bz-data` would be 120 bytes × N. Here only the ADJACENCY
 * travels — an array of keys per node, the only thing that really
 * differs from one node to the next.
 *
 * ⚠️ METHODS, never getters: `scope.absorb` invokes each key at
 * registration and would freeze a getter on its first value (cf.
 * traps.md).
 */
(function () {
  "use strict";
  const $bz = (window.$bz = window.$bz || {});

  $bz.diagram = {
    scope: {
      /* The selection — READ AND WRITTEN by `_read` / `_write`.
       *
       * These two carry the indirection: the same methods serve the
       * local `value` field (no binding) and the store cell (a `value=`
       * bound to a `ClientState`). It is `tree`'s and `toggle_group`'s
       * idiom — without it, every method would have to test which mode
       * it is running in.
       *
       * No getter: `scope.absorb` invokes each key once at registration
       * and would freeze it on its first value.
       */
      _read() {
        return this.value;
      },
      _write(v) {
        this.value = v;
      },

      /* Designate `key`, whose neighbours `adj` lists (itself
       * included).
       *
       * Re-clicking the already designated node switches off. It is the
       * only way out from the keyboard and the finger — without it you
       * stay lit with no way of knowing how to come back, and there is
       * no hover to get out of it on a touch screen. */
      light(key) {
        this._write(
          String(this._read() || "") === String(key) ? "" : String(key)
        );
      },

      /* Must this node stay in the foreground?
       *
       * DERIVED from the selection, never stored. A `lit` array filled by
       * `light()` would not move when the selection changes from OUTSIDE
       * (a `select` bound to the same `ClientState`, a
       * `state.node.set(...)`): the store would follow, the screen would
       * not.
       *
       * `adj` is the node's adjacency, baked by the server into its
       * `bz-class`. So we test "is the selected one MY neighbour" rather
       * than the other way round — it is the same predicate, and it
       * requires no state.
       */
      isLit(key, adj) {
        const sel = String(this._read() || "");
        if (!sel) return true;
        if (sel === String(key)) return true;
        return (adj || []).indexOf(sel) !== -1;
      },

      /* Tout rallumer. */
      reset() {
        this._write("");
      },

      /* Arm the click-outside-the-diagram, once only.
       *
       * Designating a node is a reading gesture: you must be able to get
       * out of it by clicking anywhere, not only by finding the node you
       * had designated. Without that you stay lit, and on a touch screen
       * there is not even a hover to suspect it.
       *
       * `$bz.helpers.clickOutside` rather than a home-made listener: it
       * is the one the overlays use, it is in the CAPTURE phase (so an
       * inner `stopPropagation` does not smother it) and it returns its
       * unsubscribe.
       *
       * Idempotent: `bz-effect` is re-evaluated after every morph, and
       * without the flag we would stack one listener per refresh.
       */
      arm(el) {
        if (!el || el._bzDiagramOff) return;
        const scope = this;
        el._bzDiagramOff = $bz.helpers.clickOutside(el, function () {
          scope.reset();
        });
      },

      /* An edge stays in the foreground if it TOUCHES the designated
       * node.
       *
       * "Incident", and not "both its ends are lit": two neighbours of
       * one node are both in the foreground, but the edge linking them
       * to each other says nothing about what was designated. Keeping it
       * lit filled the screen with what we were precisely trying to
       * remove. */
      isEdgeLit(a, b) {
        const sel = String(this._read() || "");
        return !sel || sel === a || sel === b;
      },
    },
  };
})();


/* scheduler.js — dragging a `ui.scheduler` card to another time,
 * pulling its bottom edge to change its end, and tracing a new event on
 * the empty grid (`on_create`).
 *
 * ── Why not `dnd.js` ───────────────────────────────────────────────
 * The node-DnD moves a node from one LIST to another and reports an
 * index. A scheduler drop is a POSITION in a grid — "Thursday at 8h05" —
 * and the length of an event is pulled, not reordered. What is shared is
 * the transport, kept identical on purpose: a hidden carrier holds the
 * `hx-post`, the gesture writes a JSON blob into it and fires its event,
 * and a WITNESS on the card says whether the answer touched it.
 *
 * ── The traps it carries once for all ─────────────────────────────────
 *   1. A ghost left by an earlier gesture never survives into the next:
 *      every ghost is removed when a gesture begins and when it ends.
 *   2. A refusal puts the card back — the server answered without
 *      redrawing it (zero bytes, an error status, an exception).
 *   3. A QUESTION keeps the card where it was dropped. The server that
 *      asks "this one or all of them?" opens a modal dialog and does not
 *      redraw the scheduler; snapping back at that moment would put the
 *      card back under the question. So while a modal dialog is open, the
 *      card waits; when none is open any more and no request is in flight,
 *      an untouched card goes back — cancelled.
 *   4. The click a browser fires at the end of a drag is swallowed for a
 *      MOMENT, not "until the next click": a browser may fire none, and
 *      the next one would be the dialog's button.
 *
 * ── Why delegation to the document ───────────────────────────────────
 * The scheduler is redrawn by morphs; a listener on a card would die
 * with it. One listener per event type, on the document, which finds its
 * target with `closest()` and keeps no state on the nodes.
 *
 * DOM contract expected from Python (`components/data/scheduler`):
 *   root    [data-bz-scheduler] data-bz-grid-start, data-bz-grid-end (minutes),
 *           data-bz-px (pixels per minute), data-bz-snap (minutes), data-bz-gap (px)
 *   column  [data-bz-day="YYYY-MM-DD"]
 *   card    [data-bz-event] data-bz-start, data-bz-duration (minutes),
 *           [data-bz-movable] when it can be dragged
 *   edge    [data-bz-resize] inside a card, when it can be pulled
 *   carrier [data-bz-scheduler-carrier="move"|"resize"|"create"], a root child
 *   tag     [data-bz-scheduler-tag], a root child — the label of the time
 *   draft   [data-bz-scheduler-draft], a root child — the theme's picture of
 *           a new event, copied under a trace
 *
 * ── The trace (`on_create`) ──────────────────────────────────────────
 * A press on a column, NOT on a card, that moves past the threshold
 * draws a draft (on the root, over the column) from the pressed minute
 * to the pointer, snapped. At the
 * release the draft STAYS until the answer — the app redraws with its
 * own provisional item, or answers nothing — then goes. A press that does
 * not move creates nothing: a click on the grid often closes a panel.
 */
(function () {
  "use strict";
  const $bz = (window.$bz = window.$bz || {});

  //: The gesture's rules live ONCE, in `$bz.gesture` (`helpers.js`),
  //: shared with `dnd.js`: the threshold keeps the CLICK
  //: (`on_item_click=`), the touch hold and its tolerance keep the week
  //: SCROLLABLE, the end-of-drag click is swallowed for a moment, and a
  //: dropped card waits while a question is open.
  const G = $bz.gesture;
  const THRESHOLD_PX = G.MOUSE_THRESHOLD_PX;
  const TOUCH_HOLD_MS = G.TOUCH_HOLD_MS;
  const TOUCH_TOLERANCE_PX = G.TOUCH_TOLERANCE_PX;

  //: Set on a dropped card until an answer redraws it. The server never
  //: renders it, so the morph erases it; its survival says nobody did.
  const PENDING_ATTR = "data-bz-reschedule-pending";
  ($bz._witnesses = $bz._witnesses || new Set()).add(PENDING_ATTR);
  const ROOT_SEL = "[data-bz-scheduler]";
  const COLUMN_SEL = "[data-bz-day]";
  let armed = null;
  let active = null;

  // ── Reading the contract ─────────────────────────────────────────────

  function grid(root) {
    return {
      start: +root.getAttribute("data-bz-grid-start"),
      end: +root.getAttribute("data-bz-grid-end"),
      px: +root.getAttribute("data-bz-px"),
      snap: +root.getAttribute("data-bz-snap") || 5,
      gap: +root.getAttribute("data-bz-gap") || 0,
    };
  }

  function child(root, selector) {
    return root.querySelector(":scope > " + selector);
  }

  function carrierOf(root, mode) {
    return child(root, '[data-bz-scheduler-carrier="' + mode + '"]');
  }

  /* The geometry is read ONCE per gesture (and again on a scroll), not
     on every pointermove: a layout read right after the ghost's write
     forced a reflow per move. */
  function measure(a) {
    a.rootBox = a.root.getBoundingClientRect();
    a.columns = Array.prototype.filter.call(
      a.root.querySelectorAll(COLUMN_SEL),
      function (c) { return c.closest(ROOT_SEL) === a.root; }
    ).map(function (c) { return {el: c, box: c.getBoundingClientRect()}; });
    a.tagHeight = a.tag ? a.tag.offsetHeight : 0;
  }

  /* A day column spans the grid's height, so x alone finds it — even
     when the pointer strays above the grid. A month cell needs y too. */
  function columnAt(a, x, y) {
    const hit = a.columns.find(function (c) {
      return x >= c.box.left && x < c.box.right
        && (!a.month || (y >= c.box.top && y < c.box.bottom));
    });
    return hit || null;
  }

  function clamp(v, lo, hi) { return Math.max(lo, Math.min(hi, v)); }

  /* The hour beside a dragged card, by THE clock (``$bz.times.shown``):
   * « 8h05 » in French, « 8:05 AM » in American English. */
  function label(minutes) {
    const pad = function (n) { return String(n).padStart(2, "0"); };
    return $bz.times.shown(pad(Math.floor(minutes / 60)) + ":" + pad(minutes % 60));
  }

  /* "2026-11-10" + 485 → "2026-11-10T08:05", in the page's local time.
     Built on a Date so that 24:00 becomes the next day's 00:00. */
  function iso(day, minutes) {
    const d = new Date(day + "T00:00:00");
    d.setMinutes(minutes);
    const pad = function (n) { return String(n).padStart(2, "0"); };
    return d.getFullYear() + "-" + pad(d.getMonth() + 1) + "-" + pad(d.getDate())
      + "T" + pad(d.getHours()) + ":" + pad(d.getMinutes());
  }

  function listOf(cell) {
    return cell.querySelector("[data-bz-month-list]") || cell;
  }

  function removeGhosts() {
    document.querySelectorAll("[data-bz-ghost]").forEach(function (g) { g.remove(); });
  }

  function removeDrafts() {
    document.querySelectorAll("[data-bz-draft]").forEach(function (d) { d.remove(); });
  }

  // ── The gesture ──────────────────────────────────────────────────────

  function onPointerDown(e) {
    if (active || armed) return;
    if (e.pointerType === "mouse" && e.button !== 0) return;
    if (!e.target.closest) return;
    const edge = e.target.closest("[data-bz-resize]");
    const card = edge ? edge.closest("[data-bz-event]") : e.target.closest("[data-bz-movable]");
    if (!card && !e.target.closest("[data-bz-event]")) return armCreate(e);
    if (!card || card.hasAttribute(PENDING_ATTR)) return;
    const root = card.closest(ROOT_SEL);
    const column = card.closest(COLUMN_SEL);
    const mode = edge ? "resize" : "move";
    if (!root || !column || !carrierOf(root, mode)) return;
    armed = {
      card: card, root: root, column: column, mode: mode,
      pointerId: e.pointerId, touch: e.pointerType === "touch",
      x: e.clientX, y: e.clientY, timer: null,
    };
    if (armed.touch) {
      armed.timer = setTimeout(function () { if (armed) begin(armed.x, armed.y); },
                               TOUCH_HOLD_MS);
    }
  }

  /* A press on the empty grid of a scheduler that creates. */
  function armCreate(e) {
    const column = e.target.closest(COLUMN_SEL);
    const root = column && column.closest(ROOT_SEL);
    if (!root || root.getAttribute("data-bz-view") === "month" || !carrierOf(root, "create")) {
      return;
    }
    armed = {
      card: null, root: root, column: column, mode: "create",
      pointerId: e.pointerId, touch: e.pointerType === "touch",
      x: e.clientX, y: e.clientY, timer: null,
    };
    if (armed.touch) {
      armed.timer = setTimeout(function () { if (armed) begin(armed.x, armed.y); },
                               TOUCH_HOLD_MS);
    }
  }

  function disarm() {
    if (armed && armed.timer) clearTimeout(armed.timer);
    armed = null;
  }

  function begin(x, y) {
    const a = armed;
    disarm();
    removeGhosts();
    removeDrafts();
    if (a.mode === "create") return beginCreate(a, x, y);
    const card = a.card;
    const box = card.getBoundingClientRect();
    const ghost = card.cloneNode(true);
    //: The copy carries no identity and no wiring: it is a picture.
    [ghost].concat(Array.prototype.slice.call(ghost.querySelectorAll("*"))).forEach(function (el) {
      Array.prototype.slice.call(el.attributes).forEach(function (attr) {
        const n = attr.name;
        if (n === "id" || n === "tabindex" || n === "role" || n === "aria-label"
            || n.indexOf("hx-") === 0 || n.indexOf("bz-") === 0 || n === "data-bz-sig"
            || n === "data-bz-movable" || n === "data-bz-event") {
          el.removeAttribute(n);
        }
      });
    });
    ghost.setAttribute("data-bz-ghost", "");
    ghost.setAttribute("aria-hidden", "true");
    card.setAttribute("data-bz-dragging", "");
    const tag = child(a.root, "[data-bz-scheduler-tag]");
    if (tag) tag.hidden = false;
    active = {
      card: card, root: a.root, mode: a.mode, pointerId: a.pointerId,
      grid: grid(a.root), ghost: ghost, tag: tag,
      grab: a.y - box.top,
      origin: {
        column: a.column,
        parent: card.parentNode,
        next: card.nextSibling,
        style: card.getAttribute("style") || "",
        start: +card.getAttribute("data-bz-start"),
        duration: +card.getAttribute("data-bz-duration"),
      },
      column: a.column, start: 0, end: 0, x: x, y: y,
      //: A month has no hours: the chip changes day, keeps its time, and
      //: sits in the cell's list rather than at a height.
      month: a.root.getAttribute("data-bz-view") === "month",
    };
    if (active.month && tag) tag.hidden = true;
    measure(active);
    update(x, y);
  }

  function beginCreate(a, x, y) {
    const template = child(a.root, "[data-bz-scheduler-draft]");
    if (!template) return;
    const draft = template.cloneNode(true);
    draft.removeAttribute("data-bz-scheduler-draft");
    draft.removeAttribute("hidden");
    draft.setAttribute("data-bz-draft", "");
    //: ``data-bz-row``: what the runtime inserted itself, which the
    //: bridge's position patches skip when they check a level's shape
    //: (``bridge.js``, ``applyPositionPatches``). Without it the answer
    //: that redraws the scheduler is refused, and the new event never
    //: shows.
    draft.setAttribute("data-bz-row", "");
    const tag = child(a.root, "[data-bz-scheduler-tag]");
    if (tag) tag.hidden = false;
    active = {
      card: null, root: a.root, mode: "create", pointerId: a.pointerId,
      grid: grid(a.root), ghost: draft, tag: tag,
      column: a.column, start: 0, end: 0, x: x, y: y, month: false,
      origin: {column: a.column, start: 0, duration: 0},
    };
    measure(active);
    const g = active.grid;
    const here = active.columns.find(function (c) { return c.el === a.column; });
    //: The pressed minute, floored to the snap: the trace's anchor.
    active.origin.start = clamp(
      Math.floor((g.start + (a.y - here.box.top) / g.px) / g.snap) * g.snap,
      g.start, g.end - g.snap);
    //: On the root, over the column: the draft outlives the gesture, and
    //: the answer redraws the column under it.
    a.root.appendChild(draft);
    update(x, y);
  }

  function showTag(a, here, start, end) {
    if (!a.tag) return;
    const g = a.grid;
    //: Placed from the computed top, never read back from the ghost.
    a.tag.textContent = label(start) + " – " + label(end);
    a.tag.style.left = (here.box.left - a.rootBox.left + g.gap) + "px";
    a.tag.style.top = (here.box.top - a.rootBox.top + (start - g.start) * g.px
                       - a.tagHeight - 4) + "px";
  }

  function update(x, y) {
    const a = active;
    const g = a.grid;
    const snap = function (m) { return Math.round(m / g.snap) * g.snap; };
    a.x = x;
    a.y = y;
    if (a.mode === "create") {
      //: The trace stays in its column; it runs from the anchor to the
      //: pointer, downwards or upwards, one snap at least.
      const col = a.columns.find(function (c) { return c.el === a.column; });
      const at = clamp(g.start + (y - col.box.top) / g.px, g.start, g.end);
      const anchor = a.origin.start;
      let start = anchor;
      let end = Math.max(anchor + g.snap, Math.ceil(at / g.snap) * g.snap);
      if (at < anchor) {
        start = Math.floor(at / g.snap) * g.snap;
        end = anchor + g.snap;
      }
      a.start = clamp(start, g.start, g.end - g.snap);
      a.end = clamp(end, a.start + g.snap, g.end);
      const d = a.ghost.style;
      d.left = (col.box.left - a.rootBox.left + g.gap) + "px";
      d.width = (col.box.width - 2 * g.gap) + "px";
      d.top = Math.round(col.box.top - a.rootBox.top + (a.start - g.start) * g.px + g.gap / 2) + "px";
      d.height = Math.round((a.end - a.start) * g.px - g.gap) + "px";
      showTag(a, col, a.start, a.end);
      return;
    }
    const here = (a.mode === "move" && columnAt(a, x, y))
      || a.columns.find(function (c) { return c.el === a.column; });
    if (a.month) {
      a.column = here.el;
      a.start = a.origin.start;
      a.end = a.origin.start + a.origin.duration;
      const list = listOf(here.el);
      if (a.ghost.parentNode !== list) list.appendChild(a.ghost);
      return;
    }
    let start = a.origin.start;
    let end = start + a.origin.duration;
    if (a.mode === "move") {
      const top = y - here.box.top - a.grab;
      start = clamp(snap(g.start + top / g.px), g.start, g.end - a.origin.duration);
      end = start + a.origin.duration;
    } else {
      end = clamp(snap(g.start + (y - here.box.top) / g.px), start + g.snap, g.end);
    }
    a.column = here.el;
    a.start = start;
    a.end = end;
    if (a.ghost.parentNode !== here.el) here.el.appendChild(a.ghost);
    place(a.ghost, a, start, end, a.mode === "move");
    showTag(a, here, start, end);
  }

  /* Pose a card at [start, end). A moved card loses its lane: until the
     server places it, it takes the column's whole width. */
  function place(el, a, start, end, wholeWidth) {
    const g = a.grid;
    el.style.top = Math.round((start - g.start) * g.px + g.gap / 2) + "px";
    el.style.height = Math.round((end - start) * g.px - g.gap) + "px";
    if (wholeWidth) {
      el.style.insetInlineStart = g.gap + "px";
      el.style.width = "calc(100% - " + 2 * g.gap + "px)";
    }
  }

  function cleanup() {
    removeGhosts();
    if (active) {
      if (active.card) active.card.removeAttribute("data-bz-dragging");
      if (active.tag) active.tag.hidden = true;
    }
    active = null;
  }

  function finish() {
    const a = active;
    cleanup();
    G.swallowClick();
    if (a.mode === "create") return finishCreate(a);
    const day = a.column.getAttribute("data-bz-day");
    const unchanged = a.column === a.origin.column && a.start === a.origin.start
      && a.end === a.origin.start + a.origin.duration;
    if (unchanged) return;
    const carrier = carrierOf(a.root, a.mode);
    if (!carrier) return;

    //: Optimistic: the card goes where it was dropped, at once.
    const card = a.card;
    const host = a.month ? listOf(a.column) : a.column;
    if (card.parentNode !== host) host.appendChild(card);
    if (!a.month) place(card, a, a.start, a.end, a.mode === "move");
    card.setAttribute("data-bz-start", String(a.start));
    card.setAttribute("data-bz-duration", String(a.end - a.start));

    const told = {
      event_id: card.getAttribute("data-bz-event") || "",
      start: iso(day, a.start),
      end: iso(day, a.end),
    };
    carrier.value = JSON.stringify(told);
    //: A client expression only: no request, so no answer will ever place
    //: the card — it goes back once the expression has run.
    const server = carrier.hasAttribute("hx-post");
    if (server) armSnapBack(card, a.origin, carrier);
    //: The carrier's `hx-post` leaves — no `fetch` here: the transport
    //: belongs to the bridge (charter, principle 2).
    $bz.helpers.emitChange(carrier, a.mode, told);
    if (!server) afterTwoFrames(function () { restore(card, a.origin); });
  }

  /* The traced slot leaves; the draft waits for the answer, then goes —
     an app that keeps the slot has drawn its own item by then. */
  function finishCreate(a) {
    const draft = a.ghost;
    const carrier = carrierOf(a.root, "create");
    if (!carrier) { draft.remove(); return; }
    const day = a.column.getAttribute("data-bz-day");
    const told = {event_id: "", start: iso(day, a.start), end: iso(day, a.end)};
    carrier.value = JSON.stringify(told);
    const server = carrier.hasAttribute("hx-post");
    function settle(e) {
      if (e.detail && e.detail.elt && e.detail.elt !== carrier) return;
      document.removeEventListener("htmx:afterRequest", settle);
      afterTwoFrames(function () { draft.remove(); });
    }
    if (server) document.addEventListener("htmx:afterRequest", settle);
    $bz.helpers.emitChange(carrier, "create", told);
    if (!server) afterTwoFrames(function () { draft.remove(); });
  }

  // ── The answer ───────────────────────────────────────────────────────

  function restore(card, origin) {
    card.removeAttribute(PENDING_ATTR);
    if (!card.isConnected || !origin.parent.isConnected) return;
    origin.parent.insertBefore(
      card, origin.next && origin.next.parentNode === origin.parent ? origin.next : null
    );
    card.setAttribute("style", origin.style);
    card.setAttribute("data-bz-start", String(origin.start));
    card.setAttribute("data-bz-duration", String(origin.duration));
  }

  //: Two frames after an answer: the swap and the rescan land on the
  //: frames that follow `htmx:afterRequest`.
  const afterTwoFrames = G.afterTwoFrames;

  //: While a question is open the card waits for what can end it: the
  //: dialog's own `close` (bubbled from `show_attrs`' `$dispatch`), or an
  //: answer that may redraw the scheduler (`$bz.gesture.whenAnswered`).
  function armSnapBack(card, origin, carrier) {
    card.setAttribute(PENDING_ATTR, "");
    G.whenAnswered(carrier, {
      untouched: function () {
        return card.hasAttribute(PENDING_ATTR) && card.isConnected;
      },
      undo: function () { restore(card, origin); },
    });
  }

  // ── Listeners ────────────────────────────────────────────────────────

  function onPointerMove(e) {
    if (armed && e.pointerId === armed.pointerId) {
      const far = G.distance(armed, e);
      if (armed.touch) {
        if (far > TOUCH_TOLERANCE_PX) disarm();
      } else if (far >= THRESHOLD_PX) {
        begin(e.clientX, e.clientY);
      }
      return;
    }
    if (!active || e.pointerId !== active.pointerId) return;
    e.preventDefault();
    update(e.clientX, e.clientY);
  }

  function onPointerUp(e) {
    if (armed && e.pointerId === armed.pointerId) return disarm();
    if (active && e.pointerId === active.pointerId) finish();
  }

  function onPointerCancel(e) {
    if (armed && e.pointerId === armed.pointerId) return disarm();
    if (active && e.pointerId === active.pointerId) cleanup();
  }

  function onKeyDown(e) {
    if (e.key !== "Escape") return;
    if (armed) disarm();
    else if (active) cleanup();
  }

  //: A wheel scroll during a drag moves the columns under the pointer.
  function onScroll() {
    if (!active) return;
    measure(active);
    update(active.x, active.y);
  }

  //: Once grabbed, the finger is ours: only a non-passive `touchmove`
  //: can stop the browser scrolling under the card.
  function onTouchMove(e) {
    if (active && e.cancelable) e.preventDefault();
  }

  document.addEventListener("pointerdown", onPointerDown, true);
  document.addEventListener("pointermove", onPointerMove, { passive: false });
  document.addEventListener("touchmove", onTouchMove, { passive: false });
  document.addEventListener("pointerup", onPointerUp, true);
  document.addEventListener("pointercancel", onPointerCancel, true);
  document.addEventListener("keydown", onKeyDown, true);
  document.addEventListener("scroll", onScroll, true);

  //: Exposed for the tests. The public contract stays the data attributes.
  $bz.scheduler = {
    THRESHOLD_PX: THRESHOLD_PX,
    SWALLOW_MS: G.SWALLOW_MS,
    _state: function () { return { armed: armed, active: active, inFlight: G._inFlight() }; },
    _iso: iso,
  };
})();


/* tip.js — the ONE tooltip panel of the page, and the service that shows it.
 *
 * A client scope, four listeners and a teleported panel with its arrow
 * for every `ui.tooltip` — and every universal `tooltip="…"`, which builds
 * one — would weigh far more than what the tooltip says. So the server
 * renders ONE panel per page (`#bz-tip`, with the app's merged tooltip
 * theme — `bretzel/components/overlay/tooltip`), and a trigger only
 * carries what it says:
 *
 *   data-bz-tip-root           the wrapper the pointer and the focus enter
 *   data-bz-tip="…"            its text (`bz-attr:` keeps a binding live)
 *   <template data-bz-tip-content>   rich content, cloned in at show time
 *   data-bz-tip-position / -color / -delay / -class   when not the default
 *   data-bz-tip-off="expr"     `disabled=`, evaluated at HOVER time with
 *                              `$el` = the trigger (never frozen at mount)
 *   data-bz-tip-beside="sel"   place the panel beside that ANCESTOR's edge,
 *                              centred on the trigger (the sidebar rail: a
 *                              collapsed entry is a square inside the rail)
 *
 * The rules are the ones the per-instance scope applied: the reveal delay;
 * no tooltip over a popup its trigger opened (`aria-expanded="true"`,
 * checked again after the delay); hidden on click and when an anchored
 * descendant dispatches `open`. Two are new: the focusable control is
 * described by the panel while it shows (`aria-describedby`) — unless its
 * accessible name already says the same words, as an icon-only button
 * named after its tooltip does — and a swap that removes the trigger hides
 * the panel instead of leaving it pointing at nothing.
 *
 * `$bz.tip.open(anchor, opts)` / `$bz.tip.close()` are the same panel for
 * code that positions it itself — the sidebar rail, the charts.
 */
(function () {
  "use strict";
  const $bz = (window.$bz = window.$bz || {});
  const ROOT = "[data-bz-tip-root]";
  const BRIDGE = "bz-c-";

  let current = null; // the root shown, or waiting for its delay
  let timer = null;
  let detach = null; // floating's cleanup
  let watcher = null; // follows a live text while shown
  let described = null; // [element, previous aria-describedby]
  let extra = []; // per-instance panel classes applied on this show

  function panel() {
    return document.getElementById("bz-tip");
  }

  function bodyOf(p) {
    return p.querySelector("[data-bz-tip-body]");
  }

  function popupOpen(root) {
    return !!root.querySelector('[aria-expanded="true"]');
  }

  function switchedOff(root) {
    const expr = root.getAttribute("data-bz-tip-off");
    if (!expr) return false;
    try {
      return !!$bz._evaluate(root, expr);
    } catch (err) {
      return false;
    }
  }

  function anchorOf(root) {
    // Same probe as the anchored panels: a `display:contents` wrapper has
    // no box, its first child is the trigger's.
    return getComputedStyle(root).display === "contents"
      ? root.firstElementChild || root
      : root;
  }

  const FOCUSABLE = "a[href],button,input,select,textarea,[tabindex]";

  function controlOf(root) {
    return root.matches(FOCUSABLE) ? root : root.querySelector(FOCUSABLE) || root;
  }

  function nameOf(el) {
    return (el.getAttribute("aria-label") || el.textContent || "").trim();
  }

  // The extra gap that puts the panel beside an ancestor's edge rather
  // than the anchor's own.
  function besideGap(anchor, ancestor, placement) {
    const a = anchor.getBoundingClientRect();
    const b = ancestor.getBoundingClientRect();
    const side = placement.split("-")[0];
    if (side === "right") return b.right - a.right;
    if (side === "left") return a.left - b.left;
    if (side === "bottom") return b.bottom - a.bottom;
    if (side === "top") return a.top - b.top;
    return 0;
  }

  function delayOf(root) {
    const own = root.getAttribute("data-bz-tip-delay");
    const p = panel();
    return Number(own || (p && p.getAttribute("data-bz-tip-delay")) || 0);
  }

  function clearBody(p) {
    const body = bodyOf(p);
    if (!body) return null;
    for (const child of Array.from(body.children)) {
      if ($bz._disposeTree) $bz._disposeTree(child);
    }
    body.textContent = "";
    return body;
  }

  function paint(p, opts) {
    // The colour bridge: the panel carries exactly one.
    for (const cls of Array.from(p.classList)) {
      if (cls.indexOf(BRIDGE) === 0) p.classList.remove(cls);
    }
    p.classList.add(BRIDGE + (opts.color || "text"));
    for (const cls of extra) p.classList.remove(cls);
    extra = (opts.extraClass || "").split(/\s+/).filter(Boolean);
    for (const cls of extra) p.classList.add(cls);
  }

  function open(anchor, opts) {
    const p = panel();
    if (!p || !anchor) return;
    opts = opts || {};
    const body = clearBody(p);
    if (body) {
      if (opts.content) {
        body.appendChild(opts.content);
        if ($bz._scan) $bz._scan(body);
      } else {
        body.textContent = opts.text || "";
      }
    }
    paint(p, opts);
    const placement = opts.position || "auto";
    p.setAttribute("data-side", placement === "auto" ? "bottom" : placement);
    if (detach) detach();
    // Last in <body>: at the top rung (``z-50``) the tie goes to the last
    // painted, so the panel shows above an open dialog or picker.
    if (p.parentNode !== document.body || p.nextElementSibling) {
      document.body.appendChild(p);
    }
    p.style.display = "";
    const floatOpts = { placement: placement };
    if (opts.beside) floatOpts.offset = 6 + besideGap(anchor, opts.beside, placement);
    detach = $bz.helpers.floating(anchor, p, floatOpts);
    const control = opts.describes;
    if (control && nameOf(control) !== (opts.text || "").trim()) {
      described = [control, control.getAttribute("aria-describedby")];
      control.setAttribute("aria-describedby", "bz-tip");
    }
  }

  function close() {
    clearTimeout(timer);
    timer = null;
    if (watcher) watcher.disconnect();
    watcher = null;
    if (described) {
      const [el, previous] = described;
      if (previous === null) el.removeAttribute("aria-describedby");
      else el.setAttribute("aria-describedby", previous);
      described = null;
    }
    // The body is NOT emptied here. Emptying buys nothing; the next
    // `open` clears it.
    const p = panel();
    if (p) p.style.display = "none";
    if (detach) detach();
    detach = null;
    current = null;
  }

  function optionsOf(root) {
    const tpl = root.querySelector(":scope > template[data-bz-tip-content]");
    const beside = root.getAttribute("data-bz-tip-beside");
    return {
      beside: beside ? root.closest(beside) : null,
      describes: controlOf(root),
      text: root.getAttribute("data-bz-tip") || "",
      content: tpl ? tpl.content.cloneNode(true) : null,
      position: root.getAttribute("data-bz-tip-position") || "auto",
      color: root.getAttribute("data-bz-tip-color") || "text",
      extraClass: root.getAttribute("data-bz-tip-class") || "",
    };
  }

  function showRoot(root) {
    if (current !== root || !root.isConnected) return;
    if (popupOpen(root) || switchedOff(root)) return;
    open(anchorOf(root), optionsOf(root));
    // A bound text keeps changing while the panel shows.
    watcher = new MutationObserver(function () {
      const p = panel();
      const body = p && bodyOf(p);
      if (body && !root.querySelector(":scope > template[data-bz-tip-content]")) {
        body.textContent = root.getAttribute("data-bz-tip") || "";
      }
    });
    watcher.observe(root, { attributes: true, attributeFilter: ["data-bz-tip"] });
  }

  function enter(root) {
    if (root === current) return;
    close();
    if (popupOpen(root) || switchedOff(root)) return;
    current = root;
    timer = setTimeout(function () {
      showRoot(root);
    }, delayOf(root));
  }

  function rootOf(node) {
    return node && node.closest ? node.closest(ROOT) : null;
  }

  // A click hides the panel until the pointer MOVES. A click often redraws
  // what is under a pointer that has not moved — a button swapped for its
  // pressed twin, a row morphed — and the browser then sends `mouseover`
  // for the new element: the tooltip came back over what was just clicked.
  let clickedAt = null; // [x, y] of the click that closed the panel

  document.addEventListener("mouseover", function (e) {
    const root = rootOf(e.target);
    if (!root || root === current) return;
    if (e.relatedTarget && root.contains(e.relatedTarget)) return;
    if (clickedAt && e.clientX === clickedAt[0] && e.clientY === clickedAt[1]) return;
    clickedAt = null;
    enter(root);
  });
  document.addEventListener("mousemove", function (e) {
    if (!clickedAt || (e.clientX === clickedAt[0] && e.clientY === clickedAt[1])) return;
    clickedAt = null;
    const root = rootOf(e.target);
    if (root) enter(root);
  });
  document.addEventListener("mouseout", function (e) {
    if (!current || rootOf(e.target) !== current) return;
    if (e.relatedTarget && current.contains(e.relatedTarget)) return;
    close();
  });
  document.addEventListener("focusin", function (e) {
    const root = rootOf(e.target);
    // After a click, until the pointer moves, a focus that is not
    // ``:focus-visible`` was put there by a script — the clicked button
    // disappears and the runtime hands its focus to the neighbour, its
    // pressed twin, and the tooltip would come back over it. A Tab IS
    // focus-visible: the keyboard still opens it.
    if (clickedAt && !e.target.matches(":focus-visible")) return;
    if (root) enter(root);
  });
  document.addEventListener("focusout", function (e) {
    if (!current || !current.contains(e.target)) return;
    if (e.relatedTarget && current.contains(e.relatedTarget)) return;
    close();
  });
  document.addEventListener(
    "click",
    function (e) {
      if (!current || !current.contains(e.target)) return;
      close();
      clickedAt = [e.clientX, e.clientY];
    },
    true,
  );
  // An anchored descendant (a dropdown in the trigger) announces its panel.
  document.addEventListener(
    "open",
    function (e) {
      if (current && current.contains(e.target)) close();
    },
    true,
  );
  // A swap that removed the trigger must not leave the panel behind.
  for (const name of ["htmx:afterSwap", "htmx:oobAfterSwap"]) {
    document.addEventListener(name, function () {
      if (current && !current.isConnected) close();
    });
  }

  $bz.tip = { open: open, close: close };
})();


/* message_input.js — what ``ui.message_input`` does in the browser.
 *
 * Document-level listeners, not a scope per box: a box swapped in by a
 * morph needs nothing re-wired. Every listener looks for the box it
 * concerns (``[data-bz-message-input]``, a ``<form>``) and does nothing
 * elsewhere. The behaviours follow those of chat libraries and their
 * tests (assistant-ui, Vercel AI Elements, Ant Design X, Streamlit,
 * Gradio, chatscope, Stream):
 *
 * - **Enter sends, Shift+Enter breaks the line** — never during an IME
 *   composition, nor on the Enter that ends one (Safari fires it after
 *   ``compositionend``, as keyCode 229). On a touch screen Enter breaks the
 *   line (the round button sends), as assistant-ui does. Sending is the
 *   form's own ``requestSubmit``: no request is built here.
 * - **Never empty, never twice.** A submit with neither text nor file, one
 *   while an answer is written (the round button hidden or absent), or one
 *   while the box's request is still in flight, is stopped before htmx
 *   sees it (capture phase). A box with no server action never leaves
 *   natively either — the browser would reload the page.
 * - **Emptied at once, given back on failure.** As the request leaves
 *   (``htmx:beforeSend``: the values are already taken), the text and the
 *   files go — what is typed while the server answers is kept — and come
 *   back if the request fails, unless something new was typed meanwhile.
 * - **Focus** returns to the text after a send by the round button.
 * - **Escape stops** the answer being written (the « Arrêter » button).
 * - **Backspace on an empty text** removes the last file joined.
 * - **The counter** of ``max_length`` follows what is typed.
 * - **The microphone** — the browser's dictation (Web Speech API), in the
 *   page's language, appended to what is written; ``data-listening`` while
 *   it listens. The page says the browser can dictate
 *   (``html[data-bz-can-dictate]``), so a morph re-rendering it changes
 *   nothing.
 * - **Files dropped on the box** join, as the clip's picker would; a box
 *   switched off, or taking no file, lets nothing through — and never lets
 *   the browser open the dropped file instead of the page.
 */
(function () {
  "use strict";
  const $bz = (window.$bz = window.$bz || {});
  const BOX = "[data-bz-message-input]";
  const Recognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  const touch = window.matchMedia("(pointer: coarse)");
  const drafts = new WeakMap(); // form → {text, files} while its request is out
  let listening = null; // {rec, button}

  if (Recognition) document.documentElement.setAttribute("data-bz-can-dictate", "");

  function field(form) { return form.querySelector("[data-bz-message-field]"); }
  // The file picker's scope — its ``clear()``, ``handleFiles()``, ``files``.
  function uploader(form) {
    const el = form.querySelector(".bz-file-upload");
    return el && $bz._scopeFor ? $bz._scopeFor(el).proxy : null;
  }
  function off(form) { return form.matches("[data-disabled]"); }

  function busy(form) {
    const send = form.querySelector("[data-bz-message-send]");
    return !send || send.disabled || send.offsetParent === null;
  }

  function empty(form) {
    const text = field(form);
    const files = form.querySelector("input[type=file]");
    return !(text && text.value.trim()) && !(files && files.files && files.files.length);
  }

  function write(text, value) {
    text.value = value;
    text.dispatchEvent(new Event("input", { bubbles: true }));
  }

  function count(form) {
    const text = field(form);
    const counter = form.querySelector("[data-bz-message-count]");
    if (text && counter) counter.textContent = text.value.length + " / " + text.maxLength;
  }

  function stopListening() {
    if (listening) listening.rec.stop();
  }

  document.addEventListener("keydown", function (e) {
    const text = e.target;
    if (!text.matches || !text.matches("[data-bz-message-field]")) return;
    const form = text.closest(BOX);
    if (!form) return;
    if (e.key === "Escape") {
      const stop = form.querySelector("[data-bz-message-stop]");
      if (stop && stop.offsetParent !== null && !e.isComposing) { e.preventDefault(); stop.click(); }
      return;
    }
    if (e.key === "Backspace" && !text.value) {
      const files = uploader(form);
      if (files && files.files && files.files.length) {
        e.preventDefault();
        files.removeFile(files.files[files.files.length - 1]);
      }
      return;
    }
    if (e.key !== "Enter" || e.shiftKey || e.isComposing || e.keyCode === 229) return;
    if (touch.matches) return; // the line breaks; the round button sends
    e.preventDefault();
    if (!busy(form) && !empty(form)) {
      form.requestSubmit(form.querySelector("[data-bz-message-send]"));
    }
  });

  document.addEventListener("input", function (e) {
    const form = e.target.closest && e.target.closest(BOX);
    if (form && e.target.matches("[data-bz-message-field]")) count(form);
  });

  document.addEventListener("submit", function (e) {
    const form = e.target;
    if (!form.matches || !form.matches(BOX)) return;
    if (busy(form) || empty(form) || drafts.has(form) || form.classList.contains("htmx-request")) {
      e.preventDefault();
      e.stopImmediatePropagation();
      return;
    }
    if (!form.hasAttribute("hx-post")) e.preventDefault();
  }, true);

  document.addEventListener("htmx:beforeSend", function (e) {
    const form = e.detail && e.detail.elt;
    if (!form || !form.matches || !form.matches(BOX)) return;
    stopListening();
    const text = field(form);
    const files = uploader(form);
    drafts.set(form, { text: text ? text.value : "",
                       files: files && files.files ? files.files.map(function (f) { return f.file; }) : [] });
    if (text) write(text, "");
    if (files && files.clear) files.clear();
    if (text && document.activeElement && form.contains(document.activeElement)) text.focus();
  });

  document.addEventListener("htmx:afterRequest", function (e) {
    const form = e.detail && e.detail.elt;
    if (!form || !form.matches || !form.matches(BOX)) return;
    const draft = drafts.get(form);
    drafts.delete(form);
    if (!draft || e.detail.successful) return;
    const text = field(form);
    if (text && !text.value) write(text, draft.text);
    const files = uploader(form);
    if (files && draft.files.length && !(files.files && files.files.length)) {
      files.handleFiles(draft.files);
    }
  });

  document.addEventListener("click", function (e) {
    const button = e.target.closest && e.target.closest("[data-bz-voice]");
    if (!button || !Recognition) return;
    const form = button.closest(BOX);
    const text = form && field(form);
    if (!text) return;
    if (listening) { stopListening(); return; }
    const rec = new Recognition();
    rec.lang = document.documentElement.lang || navigator.language;
    rec.continuous = true;
    rec.interimResults = true;
    const before = text.value.replace(/\s+$/, "");
    rec.onresult = function (event) {
      let heard = "";
      for (let i = 0; i < event.results.length; i++) heard += event.results[i][0].transcript;
      heard = heard.trim();
      write(text, before && heard ? before + " " + heard : before || heard);
    };
    rec.onend = function () {
      button.removeAttribute("data-listening");
      button.setAttribute("aria-pressed", "false");
      listening = null;
    };
    listening = { rec: rec, button: button };
    button.setAttribute("data-listening", "true");
    button.setAttribute("aria-pressed", "true");
    rec.start();
  });

  document.addEventListener("dragover", function (e) {
    const form = e.target.closest && e.target.closest(BOX);
    if (form) e.preventDefault(); // a file dropped here never replaces the page
  });

  document.addEventListener("drop", function (e) {
    const form = e.target.closest && e.target.closest(BOX);
    if (!form) return;
    e.preventDefault();
    const files = uploader(form);
    if (!files || off(form) || !e.dataTransfer || !e.dataTransfer.files.length) return;
    files.handleFiles(e.dataTransfer.files);
  });
})();


/* message_list.js — ``ui.message_list`` follows its newest message.
 *
 * The behaviour that chat libraries (assistant-ui, Vercel AI Elements,
 * Ant Design X, Gradio, chatscope) share, and test:
 *
 * - **at the bottom, it stays there** — a new message, an answer that
 *   grows word by word, a refresh of the thread: the list scrolls with it;
 * - **scrolled up, it stops following** — the reader is reading; nothing
 *   pulls them down, and « back to the latest message » appears
 *   (``data-away`` on the list, which its theme reads);
 * - **back at the bottom** — by hand or by that button — it follows again.
 *
 * What grows is watched by a ResizeObserver on the thread (a new node, a
 * longer text, an image that loads: all change its height). The state is
 * kept by the list's id (it always has one): a refresh that morphs it
 * strips ``data-away`` — the server never renders it —, one that replaces
 * the element loses its scroll; both are put back after each settle,
 * where the reader was. A list met for the first time starts at its
 * bottom.
 */
(function () {
  "use strict";
  const LIST = "[data-bz-message-list]";
  const NEAR = 48; // px from the bottom that still count as « at the bottom »
  // By the list's id, not its element: a refresh may replace the element,
  // and what the reader did (scrolled up, to where) must survive it.
  const states = new Map(); // id → {stuck, top}
  const watched = new WeakSet(); // elements already observed

  function smooth() {
    return !window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  }

  function toBottom(list, animated) {
    list.scrollTo({ top: list.scrollHeight, behavior: animated && smooth() ? "smooth" : "auto" });
  }

  function stateOf(list) {
    let state = states.get(list.id);
    if (!state) { state = { stuck: true, top: 0 }; states.set(list.id, state); }
    return state;
  }

  function mark(list) {
    list.toggleAttribute("data-away", !stateOf(list).stuck);
  }

  function adopt(list) {
    const known = states.has(list.id);
    const state = stateOf(list);
    if (!watched.has(list)) {
      watched.add(list);
      const thread = list.firstElementChild;
      if (thread && window.ResizeObserver) {
        new ResizeObserver(function () {
          if (stateOf(list).stuck) toBottom(list, false);
        }).observe(thread);
      }
      list.addEventListener("scroll", function () {
        const s = stateOf(list);
        s.stuck = list.scrollHeight - list.scrollTop - list.clientHeight < NEAR;
        s.top = list.scrollTop;
        mark(list);
      }, { passive: true });
      // A new element of a list met before: back where the reader was.
      if (known && !state.stuck) list.scrollTop = state.top;
    }
    if (state.stuck) toBottom(list, false);
    mark(list);
  }

  function scan(root) {
    (root && root.querySelectorAll ? root : document).querySelectorAll(LIST).forEach(adopt);
    if (root && root.matches && root.matches(LIST)) adopt(root);
  }

  document.addEventListener("DOMContentLoaded", function () { scan(document); });
  document.addEventListener("htmx:load", function (e) { scan(e.target); });
  document.addEventListener("htmx:afterSettle", function () {
    document.querySelectorAll(LIST).forEach(adopt);
  });

  document.addEventListener("click", function (e) {
    const button = e.target.closest && e.target.closest("[data-bz-message-list-bottom]");
    const list = button && button.closest(LIST);
    if (!list) return;
    stateOf(list).stuck = true;
    toBottom(list, true);
    mark(list);
  });
})();
