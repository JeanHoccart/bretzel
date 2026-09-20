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


/* 01_signals.js — reactive primitives : signal / effect / computed.
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
 * Spec : spec/V3/03-runtime.md §"_src/01_signals.js".
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
      for (const eff of batch) eff._run();
    });
  }

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


/* 02_directives.js — the 13 bz-* directives + the binding engine.
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
 *   (bz-data is owned by 03_scope.js)
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
 * A CSP IS shipped since 2026-09-05 (`Bretzel(csp=True)`, cf.
 * `.claude/bretzel/security.md`) : it carries `'unsafe-eval'` for this
 * very `new Function`, but NOT `'unsafe-inline'`, so an injected
 * <script> stays inert. Only the `unsafe-eval`-FREE mode is still
 * deferred, and its cost is measured there — 29 % of the expressions
 * this engine receives fall outside any tractable subset.
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
   * Until 2026-08-13 each component got by on its own, and once
   * measured, two of the three ways used were broken:
   *   - MenuItem removed its wiring AT CONSTRUCTION — so never when
   *     `disabled` is driven by a binding, where the value at render is
   *     `false`. `ui.dropdown_item(disabled=<binding>)` stayed entirely
   *     clickable while looking active;
   *   - the three nav items set `pointer-events-none`, which does block
   *     the click but CANCELS the same element's `cursor-not-allowed`
   *     (no pointer event ⇒ no cursor painted).
   *
   * Inertness therefore became a property of the BASE LAYER, derived
   * from `aria-disabled="true"` alone — the attribute a11y requires
   * anyway, and that the server knows how to make reactive through
   * `bz-attr:`. Three guards, each at its boundary: the `bz-on:`
   * handlers here, native navigation just below, and the server action
   * in `05_bridge.js` (measured: `preventDefault` on
   * `htmx:configRequest` does cancel the request in htmx 2.0.4, cf.
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
   * Why they do not bubble (measured in the browser on 2026-08-19)
   * ---------------------------------------------------------------
   * ``on_open=`` / ``on_close=`` set their ``hx-trigger`` on the
   * component's ROOT. With ``bubbles: true``, that root therefore also
   * caught its descendants' ``open``/``close``:
   *
   *   - a ``ui.select`` in a ``ui.dialog(on_open=…)`` → opening the
   *     panel POSTed THE DIALOG's handler, and Escape POSTed TWO
   *     ``on_close``;
   *   - a ``ui.alert(dismissible=True)`` in a ``ui.dialog(on_close=…)``
   *     → dismissing the alert POSTed THE DIALOG's ``on_close``.
   *
   * Eight components expose these two events and eight emit them: any
   * emitter nested in any listener leaked. Repro:
   * ``tests/probes/probe_overlay_bubble.py``. */
  const SCOPED_EVENTS = new Set(["open", "close"]);

  /* The root of the component containing ``el``: the first ancestor
   * with a ``bz-data``, walking teleportations back through their
   * origin.
   *
   * The same walk as ``findScope`` (``03_scope.js``) — without the
   * ``_bzScopeHost`` jump, a panel projected under ``<body>`` (Tooltip,
   * Popover, Dropdown, SidebarFooter's popover) would look for its root
   * in the ``<body>`` and find none. No ``open``/``close`` leaves from
   * there today — measured, only ``bz-dropdown-pick`` lives there — but
   * a component to come should not have to rediscover this trap. */
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
  }

  function disposeTree(node) {
    if (node.nodeType !== 1) return;
    disposeEl(node);
    for (const child of node.querySelectorAll("*")) disposeEl(child);
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
      // direct property write (cf. traps.md § bz-attr value on a custom
      // element).
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
      // set lived on the element (`el._bzClassDyn`) it survived the morph,
      // so the re-bound effect saw prev===next and NEVER re-added the
      // stripped classes — the styling silently vanished until the next
      // interaction (reproduced: pagination active page loses its pill,
      // accordion body flashes back open on close). A fresh per-bind set
      // starts empty, so the first run after a morph re-adds every class
      // from the real (clobbered) DOM baseline. Within a single bind the
      // closure persists across signal-driven re-runs, so normal
      // add/remove diffing is unchanged. Cf. traps.md § "bz-class lost
      // after a morph (tracking on the node)".
      //
      // `managed` alone is NOT enough to keep that promise: it holds what
      // the EXPRESSION produced, not what was really added. Yet
      // `classList` is a set — a token already present in the SSR
      // `class=` makes the `add` a no-op, but the `remove` deletes it for
      // good. A theme that repeats a token between its static layer and
      // its dynamic layer therefore saw the static token DESTROYED at the
      // first toggle (measured: a Pagination button that stopped being an
      // ellipsis lost `w-10 text-sm flex items-center justify-center` and
      // collapsed from 40 px to 8 px, `h-10` intact). Hence `base`: the
      // baseline read at bind time, never removable. Cf. traps.md
      // § "bz-class destroys a token the theme shares with its static
      // layer".
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
      // Symptom measured on 2026-08-16 on a demo app since removed:
      // after a partial navigation from `/` to `/stats`, the "Tasks"
      // entry kept its `bg-primary` background although its
      // `data-active` had indeed gone back to `false` — an item HALF
      // active, background painted and text left grey. `bz-attr` has no
      // baseline, so it stayed right: the two channels of one state
      // diverged.
      //
      // Affects the 9 components that emit `bz-class`, not only the
      // sidebar. Cf. traps.md § "bz-class lost after a morph" — same
      // family, opposite direction: the class SURVIVES instead of
      // disappearing.
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
        el.style.display = evaluate(el, expr, scope) ? "" : "none";
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
      compile(expr, "run")(
        scope.proxy, el, scope.refs, null, null, makeDispatch(el), nextTick,
      );
    },
  };

  // Binding order : refs first (siblings may use them in init), init
  // last (element fully wired when it runs).
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
    bound.set(el, disposers);
    const scope = $bz._scopeFor(el);
    for (const [kind, expr, arg] of todo) HANDLERS[kind](el, expr, scope, disposers, arg);
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
        anchor.parentNode.insertBefore(mounted, anchor.nextSibling);
        scan(mounted);
      } else if (!v && mounted) {
        disposeTree(mounted);
        mounted.remove();
        mounted = null;
      }
    });
    bound.set(anchor, [
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
  // uses across its keyframes). Not slaved to any one component ; a toast's
  // leave dance happens to share the 200ms so its neighbour's slide reads as
  // one motion, but nothing here needs to track ``LEAVE_MS``.
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
    }
    const rows = (template._bzForRows = template._bzForRows || new Map());
    const scope = $bz._scopeFor(template.parentElement || document.body);
    // ``:flip`` opt-in (parsed above) makes surviving rows slide from their
    // old box to the new one when a sibling is inserted or removed, instead
    // of teleporting into the freed space. The notification stack uses it so
    // a dismissed toast's neighbours glide up rather than snap (cf. traps.md
    // § "Toast reflow jumps"). Reconciliation stays key-based (nodes are
    // reused, never remounted) — FLIP only animates the layout delta of nodes
    // present both BEFORE and AFTER the update.

    const eff = $bz.effect(function () {
      const items =
        compile(listExpr, "get")(
          scope.proxy, template, scope.refs, null, null, function () {}, nextTick,
        ) || [];
      // FLIP "First" : snapshot every connected row's box before we mutate.
      // Honour prefers-reduced-motion via the shared gate (06_helpers.js) —
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
    bound.set(template, [eff.dispose]);
  }

  // ── Structural : bz-teleport (on a <template>) ─────────────────────
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
      const node = child.cloneNode(true);
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
      // no-op here. cf. traps.md § "Teleported hx-post dead after refresh".
      if (window.htmx) window.htmx.process(node);
    }
    template._bzTeleportSig = sig;
    template._bzTeleported = moved;
    bound.set(template, [
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
    // for cleanup. (cf. traps.md § Slider click → 0 / bz-init descendant
    // refs.)
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
  }

  $bz._scan = scan;
  $bz._disposeTree = disposeTree;
  $bz._compile = compile;
  $bz._sweepTeleports = sweepTeleports;
})();


/* 03_scope.js — bz-data component-scoped state, keyed by bz-id.
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
 * Nested scopes : a child bz-data reads its parent's vars, cannot
 * write them (throws — settled at the Phase 0 spike, open question #7).
 * bz-for item scopes are different : they're the SAME component scope
 * plus loop vars, so writes fall through to the parent.
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
          // (The Phase-0 spike threw here ; real composite components
          // need the delegation, so the guard was lifted.)
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
      refs: refs,
      proxy: proxy,
      parentScope() {
        return parent;
      },
      /* Re-attach this scope to its CURRENT parent.
       *
       * A scope is indexed by its ``bz-id`` STRING and therefore
       * survives its node being replaced — that is intended. But its
       * parent was captured ONCE, at creation, and never looked at
       * again: a node reappearing under another parent kept the old one
       * for life.
       *
       * It bit on an ``hx-boost`` navigation, which does not reload the
       * runtime: a picker's ``<bz-calendar>`` carried a page-independent
       * id, so the new page found the old page's scope, whose parent was
       * the PREVIOUS page's picker. The ``on_change`` wrote its value
       * into a dead scope — highlighted grid, empty field, and an F5 to
       * get out of it.
       *
       * The ids are now unique per page (``panel_calendar``), so that
       * path is no longer reached by the pickers. This is the hardening:
       * it closes the CLASS, so that the next id collision — whatever it
       * may be — does not become a silent bug again.
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
          else if (!signals.has(key)) signals.set(key, $bz.signal(v));
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
   * But a server-bound input (NumberInput / Slider / Select / Combobox
   * in local mode) seeds its ``value`` signal from the server : when
   * its @refreshable zone re-renders with a NEW value, the fresh value
   * rides in the morphed bz-data attribute yet absorb keeps the stale
   * one. Such components opt the affected keys in via a ``_serverSync``
   * array ; the bridge calls this ONCE per swap (after the rescan) to
   * adopt exactly those keys from the freshly-morphed attribute. Keys
   * NOT listed (isOpen, _query, …) stay client-owned. Binding-mode
   * inputs need nothing here — their value lives in $bz._store, which
   * the patch envelope updates and which never rides a scope signal. */
  function resyncScopes(root) {
    if (!root || root.nodeType !== 1 || !scopes.size) return;
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
      const keys = decl && Array.isArray(decl._serverSync) ? decl._serverSync : null;
      if (!keys) continue;
      for (const key of keys) {
        const sig = scope.signals.get(key);
        if (sig) sig.set(decl[key]);
      }
    }
  }

  $bz._scopes = scopes;
  $bz._scopeFor = scopeFor;
  $bz._ensureScope = ensureScope;
  $bz._makeItemScope = makeItemScope;
  $bz._sweepScopes = sweepScopes;
  $bz._resyncScopes = resyncScopes;
})();


/* 04_persistence.js — storage adapters per ClientState instance.
 *
 * Per envelope.client_state[<Class>.<key>].persist :
 *
 *   "memory"    → JS memory only, dropped on reload (no adapter). It is
 *                 the DEFAULT on the Python side
 *                 (``ClientState.__persist__``).
 *   "session"   → sessionStorage, key "$bz:<Class>.<key>"
 *   "local"     → localStorage, same key
 *
 * ⚠️ ``"volatile"`` and ``"cross_tab"`` were listed here until
 * 2026-08-01: the Python enum (``state/scopes/client.py::PERSISTS``) can
 * only emit the three above, so those two modes are unreachable — and
 * "memory", the default, was not documented. The ``mode === "volatile"``
 * test in the code below therefore never matches; it falls into the same
 * no-op as "memory" (storageFor → null).
 *
 * Wiring : 00_index.js calls register(path, mode) for each instance
 * AFTER seeding the envelope defaults — register() then overlays any
 * saved snapshot. Every store write is funnelled through
 * $bz._persistence.notify(fullPath) by the store itself ; the adapter
 * saves the instance's full field map. cross_tab adapters additionally
 * publish the change and mirror remote ones into the store (with an
 * echo guard).
 *
 * "page" mode (V2) is gone — page identity is a server concept, not a
 * client persistence target. TTL plumbing is gone too (cf. .claude/bretzel/state.md).
 */
(function () {
  "use strict";
  const $bz = (window.$bz = window.$bz || {});

  const adapters = new Map(); // instancePath → adapter

  function storageFor(mode) {
    if (mode === "session") return window.sessionStorage;
    if (mode === "local" || mode === "cross_tab") return window.localStorage;
    return null;
  }

  function storageKey(path) {
    return "$bz:" + path;
  }

  function register(path, mode) {
    if (mode === "volatile" || adapters.has(path)) return;
    const storage = storageFor(mode);
    if (!storage) return;

    const adapter = { mode: mode, storage: storage, channel: null, muted: false };
    adapters.set(path, adapter);

    // Overlay the saved snapshot (it wins over envelope defaults —
    // the user's browser knows better than the server's defaults).
    try {
      const raw = storage.getItem(storageKey(path));
      if (raw) {
        const saved = JSON.parse(raw);
        for (const field of Object.keys(saved)) {
          $bz._store.set(path + "." + field, saved[field]);
        }
      }
    } catch (e) {
      console.error("bz: corrupt persisted state for", path, e);
      storage.removeItem(storageKey(path));
    }

    if (mode === "cross_tab" && "BroadcastChannel" in window) {
      adapter.channel = new BroadcastChannel(storageKey(path));
      adapter.channel.onmessage = function (msg) {
        adapter.muted = true; // don't re-publish what we just received
        try {
          $bz._store.set(path + "." + msg.data.field, msg.data.value);
        } finally {
          adapter.muted = false;
        }
      };
    }
  }

  /* Called by the store on every set whose path belongs to a
   * registered instance. */
  function notify(fullPath, value) {
    const cut = fullPath.lastIndexOf(".");
    const path = fullPath.slice(0, cut);
    const field = fullPath.slice(cut + 1);
    const adapter = adapters.get(path);
    if (!adapter) return;
    adapter.storage.setItem(
      storageKey(path),
      JSON.stringify($bz._store.fieldsOf(path)),
    );
    if (adapter.channel && !adapter.muted) {
      adapter.channel.postMessage({ field: field, value: value });
    }
  }

  $bz._persistence = { register: register, notify: notify };
})();


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
  const ACTION_PREFIX = "/_bretzel/action/";

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
        typeof window.$bzScreenSync === "function" &&
        !window.$bzScreenSync()
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


/* 06_helpers.js — shared helpers for overlay-class components.
 *
 * Exposed via window.$bz.helpers, consumed by Dialog / Drawer /
 * Popover / Dropdown / Tooltip component code. Trimmed on purpose —
 * we inline the 6 placements we actually use instead of shipping a
 * floating-ui clone (V2's 09_floating.js was 257 LOC ; this is the
 * subset Bretzel components consume).
 *
 *   focusTrap(el)              trap Tab/Shift+Tab inside el ; returns
 *                              dispose (restores the previous focus)
 *   escapeKey(handler)         global Escape listener ; returns unsubscribe
 *   scrollLock()               body scroll lock w/ scrollbar compensation ;
 *                              returns unlock
 *   floating(anchor, el, opts) position el relative to anchor
 *                              (fixed-position, viewport-aware flip) ;
 *                              returns dispose (stops tracking)
 */
(function () {
  "use strict";
  const $bz = (window.$bz = window.$bz || {});

  const FOCUSABLE =
    'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), ' +
    'textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

  function focusTrap(el) {
    const previous = document.activeElement;
    function onKeydown(e) {
      if (e.key !== "Tab") return;
      const focusable = Array.from(el.querySelectorAll(FOCUSABLE)).filter(
        function (n) {
          return n.offsetParent !== null;
        },
      );
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
     * return, nothing. Observed on ``bench_dialog`` (2026-08-19), the
     * panel's three buttons: hidden at +1 ms, visible at +16 ms.
     *
     * A FIXED delay is not enough, and that is measured too: the
     * two-frame version passed about one time in three — the boundary
     * falls right inside the hidden window, and it moves from one run to
     * the next. So we do not wait for a duration, we wait for the
     * RESULT: we try, we check the focus landed, and we retry otherwise.
     *
     * Without that, the trap was indeed installed (``$el._bzTrap``
     * present) and the focus stayed on the trigger. The restored
     * contract is written in ``dialog.py``: "the first interactive child
     * receives focus".
     *
     * The DOM is RE-QUERIED at every attempt: between the installation
     * and the frame that succeeds, a morph may have replaced the panel's
     * content, and a detached node focuses into the void. */
    let attempts = 0;
    function focusFirst() {
      if (!el.isConnected) return;
      const first = el.querySelector(FOCUSABLE);
      if (first) {
        first.focus();
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

  function escapeKey(handler) {
    function onKeydown(e) {
      if (e.key === "Escape") handler(e);
    }
    document.addEventListener("keydown", onKeydown);
    return function () {
      document.removeEventListener("keydown", onKeydown);
    };
  }

  /* Listen for a window-level event (V3 replacement for Alpine's
   * ``@<event>.window`` modifier — bz-on listens on the element, not
   * the window). Returns its unsubscribe. Typical consumers register
   * from ``bz-init`` for events that only ever fire on window :
   * ``popstate``, ``htmx:after-request``, ``htmx:before-request``. */
  function onWindow(eventName, handler) {
    window.addEventListener(eventName, handler);
    return function () {
      window.removeEventListener(eventName, handler);
    };
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
  function clickOutside(el, handler, alsoInsideFn) {
    function onClick(e) {
      if (el.contains(e.target)) return;
      if (alsoInsideFn) {
        const extra = alsoInsideFn();
        if (extra && extra.contains(e.target)) return;
      }
      handler(e);
    }
    document.addEventListener("click", onClick, true);
    return function () {
      document.removeEventListener("click", onClick, true);
    };
  }

  /* Position `el` (fixed) relative to `anchor`. placement = "<side>"
   * or "<side>-<align>" with side ∈ {auto,top,bottom,left,right}, align
   * ∈ {start,center,end} (default center).
   *
   * side "auto" = BEST-FIT : pick the first side (preference order
   * bottom → top → right → left) where the panel fits entirely ; if
   * none fits, the side with the most leftover room. Predictable (a
   * preference order, not raw "most room" which would jump around) and
   * never off-screen (the cross axis is clamped).
   *
   * An explicit side keeps the old behaviour : flip to the OPPOSITE
   * side on the main axis when the preferred side lacks room.
   *
   * Either way the RESOLVED side is written to `el.dataset.side` so a
   * consumer (e.g. the tooltip arrow) can follow it — no more arrow
   * frozen at the SSR side while the panel flips at runtime.
   *
   * Tracks scroll + resize ; returns its dispose. */
  // Best-fit preference order — module constant so the scroll/resize
  // reposition path allocates nothing per tick.
  const SIDE_ORDER = ["bottom", "top", "right", "left"];
  // The readability floor of an anchored panel, in px. `matchWidth`
  // never goes below that width, whatever the anchor: a `ui.select`
  // placed in a sidebar collapsed to a rail (`w-16`) rendered a ~48 px
  // panel where the labels wrapped letter by letter, with a horizontal
  // scrollbar (seen on `examples/crm` on 2026-08-29). 192 px = `12rem`
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

      let side;
      if (wantSide === "auto") {
        // Best-fit : first side (in preference order) where the panel
        // fits ; else the side with the most leftover room.
        side = SIDE_ORDER.find(function (s) {
          return room[s] >= need[s];
        });
        if (!side) {
          side = SIDE_ORDER.reduce(function (best, s) {
            return room[s] - need[s] > room[best] - need[best] ? s : best;
          });
        }
      } else {
        // Explicit side : flip to the opposite on the main axis when the
        // preferred side lacks room (and the opposite has it).
        side = wantSide;
        if (side === "bottom" && room.bottom < h && room.top >= h) side = "top";
        else if (side === "top" && room.top < h && room.bottom >= h) side = "bottom";
        else if (side === "right" && room.right < w && room.left >= w) side = "left";
        else if (side === "left" && room.left < w && room.right >= w) side = "right";
      }

      let top, left;
      if (side === "top" || side === "bottom") {
        top = side === "bottom" ? a.bottom + offset : a.top - offset - h;
        if (align === "start") left = a.left;
        else if (align === "end") left = a.right - w;
        else left = a.left + (a.width - w) / 2;
        left = Math.max(4, Math.min(left, vw - w - 4));
      } else {
        left = side === "right" ? a.right + offset : a.left - offset - w;
        if (align === "start") top = a.top;
        else if (align === "end") top = a.bottom - h;
        else top = a.top + (a.height - h) / 2;
        top = Math.max(4, Math.min(top, vh - h - 4));
      }
      el.style.top = top + "px";
      el.style.left = left + "px";
      // Publish the resolved side so consumers (tooltip arrow) follow it
      // — only on change, so a stable overlay writes nothing while the
      // page scrolls under it.
      if (el.dataset.side !== side) el.dataset.side = side;

      /* …and WHERE the anchor is in the panel, so the arrow aims at it.
         The panel's middle and the trigger's middle coincide as long as
         nothing pushes the panel; the edge reframing just above
         (`Math.max(4, Math.min(...))`) separates them. The arrow was set
         at `left-1/2` — so in the middle of the bubble — and pointed
         beside its button as soon as you approached an edge. Measured on
         2026-09-09 on `examples/kanban`: trigger centred at 1468 px,
         arrow at 1443. */
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

    position();
    window.addEventListener("scroll", position, true);
    window.addEventListener("resize", position);
    return function dispose() {
      window.removeEventListener("scroll", position, true);
      window.removeEventListener("resize", position);
    };
  }

  // Shared "should we animate ?" gate — the toast leave dance
  // (09_notification.js) and the bz-for FLIP reflow (02_directives.js) both
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
   * ``pushState`` and not ``replaceState`` — the user's decision on
   * 2026-08-29: "pushState for views". A tab IS a view, so the back
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

  $bz.helpers = {
    focusTrap: focusTrap,
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
    // The event name is the ONLY thing that differed between the two
    // copies (audit F61) and the difference is deliberate :
    // number_input emits ``bzchange`` (its own, so an ``on_change=``
    // wired by the user can't be confused with the native ``change`` the
    // inner input fires while typing) ; slider emits the native
    // ``change``. Passing it in keeps the microtask rationale in one
    // place. Distinct from ``base/_wiring.change_emit_effect``, which is
    // the effect-context mechanism, not another variant of this.
    emitChange: function (carrier, eventName) {
      if (!carrier) return;
      const name = eventName || "change";
      queueMicrotask(function () {
        carrier.dispatchEvent(new Event(name, { bubbles: true }));
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
    // Extracted on 2026-08-13, at the 3rd and 4th site (slider ×2,
    // resizable ×2) — the threshold the repository set itself, "twice a
    // coincidence, three times a pattern". The pointer-drag family's
    // next component (``signature_pad``) calls this, it does not copy
    // it.
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
    // Phosphor / Tabler take an optional style suffix (-bold, -fill, …).
    if (defaultStyle && (defaultSet === "phosphor" || defaultSet === "tabler")) {
      full = full + "-" + defaultStyle;
    }
    return full;
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
   * The eight below were identical in both slabs (audit F19), so a
   * set-semantics fix had to be hand-mirrored or the two components
   * silently diverged. ``_clearAll`` JOINED them on 2026-08-06 : it was
   * excluded only because each scope also set ``this.open = false``,
   * and that closing is exactly what got removed (a panel must survive
   * its own header commands — ``_selectAll`` never closed). Combobox
   * still overrides it, but only to ADD its query reset. */
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
    // The primitive was already shared ; the memo around it was not, so
    // it existed twice (audit F60).
    cachedPrecision: function () {
      if (this._precCache !== undefined) return this._precCache;
      this._precCache = $bz.num.precisionFromStep(this._step);
      return this._precCache;
    },

  };
})();


/* 06_locale.js — month and weekday names, derived from the language.
 *
 * ⚠️ **The number 06 is an ORDERING CONSTRAINT, not an identity.** This
 * slab was called ``22_locale.js`` until 2026-08-27, so loaded FIFTEEN
 * slabs after its only consumer, ``07_calendar.js``. Yet that one calls
 * ``customElements.define('bz-calendar', …)``, which IMMEDIATELY
 * upgrades every calendar already in the DOM — their constructor then
 * reads ``$bz.locale.weekdayNames()`` on a ``$bz.locale`` that does not
 * exist yet.
 *
 * Measured: **one exception thrown per calendar**, that is 54 on the
 * playground's ``/calendar`` page, 44 on ``/date_picker``, 45 on
 * ``/date_range_picker``, 35 on ``/month_picker``. The screen recovered
 * — the ``bz-text`` directive comes back later — but the flood of errors
 * stopped ``networkidle`` arriving, and ``pytest -m audit`` HUNG on it.
 * An hour-long suite made unusable by a line of ordering.
 *
 * This file depends on nothing (it creates ``window.$bz`` if needed), so
 * it could live anywhere before 07. It is placed JUST before its
 * consumer so that a reader wondering "why here?" finds the answer on
 * the folder's next line.
 *
 * Guarded by ``tests/runtime_js/test_no_page_throws_on_load.py``, which
 * loads the 74 component pages and requires ZERO exception. A STATIC
 * gate (forbidding a read of a ``$bz.<ns>`` set later) was ruled out
 * after measurement: 9 cases in the repository, and all 9 are legitimate
 * — DEFERRED reads, in functions called well after load. What sets the
 * defect apart is the MOMENT of the read, and only a browser separates
 * them.
 *
 * Exposed as window.$bz.locale, read by 07_calendar.js and by the bz-*
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
 *   $bz.locale.weekdayNames()     7 short names, SUNDAY first
 *   $bz.locale.weekdayLongNames() the same in full, for a ``title=``
 *
 * ⚠️ Sunday first, always: it is ``Date.getDay()``'s order, and it is
 * the component that rotates the list according to ``weekstart``. A list
 * written Monday-first — the French reflex — shifts every column by a
 * day (trap [14] of the CRM work).
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

  // 2023-01-01 IS a Sunday, and 2023 has twelve months — the two
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
        weekday: "short",
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
      // The fallback has ONLY abbreviations. ``weekdaysLong`` is
      // therefore the same thing there: a ``title`` identical to the
      // visible text is useless but never wrong, where inventing a full
      // name would be.
      entry = {
        months: FALLBACK_MONTHS,
        weekdays: FALLBACK_WEEKDAYS,
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
})();


/* 07_calendar.js — <bz-calendar> custom element (stateful day grid). */
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

    // Derived from ``<html lang>`` by 22_locale.js, not written here: a
    // hard-coded table rendered "August / MON TUE WED" to every app,
    // whatever its language, and the only handle was to pass
    // ``month_names=`` AT EVERY MOUNT (three times on a single CRM
    // screen). The component's explicit lists always win — they arrive
    // as attributes and these defaults only serve their absence.
    function DEFAULT_WEEKDAYS() { return window.$bz.locale.weekdayNames(); }
    function DEFAULT_WEEKDAYS_LONG() {
        return window.$bz.locale.weekdayLongNames();
    }
    function DEFAULT_MONTHS() { return window.$bz.locale.monthNames(); }

    function iso(d) {
        return d.getFullYear() + '-' +
            String(d.getMonth() + 1).padStart(2, '0') + '-' +
            String(d.getDate()).padStart(2, '0');
    }

    /* The ISO day shifted by ``n`` days. Goes through a ``Date`` rather
     * than through string arithmetic: only it knows about month ends and
     * leap years. */
    function addDays(isoStr, n) {
        var p = isoStr.split('-');
        return iso(new Date(+p[0], +p[1] - 1, +p[2] + n));
    }

    /* The first day of the week that CONTAINS ``isoStr``, according to
     * ``weekstart`` (0 = Sunday, 1 = Monday…).
     *
     * It is the ``week`` mode's only rule: clicking any day picks its
     * week, and the returned value is that first day. The modulo is
     * doubled (``% 7 + 7) % 7``) because JS returns a NEGATIVE remainder
     * for a negative dividend — without it, any week whose clicked day
     * falls before ``weekstart`` would go back one week.
     */
    function weekStartOf(isoStr, weekstart) {
        var p = isoStr.split('-');
        var d = new Date(+p[0], +p[1] - 1, +p[2]);
        var back = (d.getDay() - weekstart + 7) % 7;
        return iso(new Date(+p[0], +p[1] - 1, +p[2] - back));
    }

    function parseJSON(value, fallback) {
        if (!value) return fallback;
        try { return JSON.parse(value); } catch (e) { return fallback; }
    }

    function escapeAttr(s) {
        return String(s)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;');
    }

    class BzCalendar extends HTMLElement {
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
         * The hole, measured on 2026-08-21: the SSR emits an EMPTY grid
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
         * ATTRIBUTES; it is not true of the CHILDREN, and that is the
         * counterpart the "custom element" choice had not honoured.
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
                    '[data-day-cell][data-selected="true"]'
                    + ':not([aria-disabled="true"])'
                ) ||
                this.querySelector(
                    '[data-day-cell][data-today="true"]'
                    + ':not([aria-disabled="true"])'
                ) ||
                this.querySelector(
                    '[data-day-cell]:not([aria-disabled="true"])'
                );
            if (target) target.focus();
        }

        blur() {
            var focused = this.querySelector('[data-day-cell]:focus');
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
                hidden.dispatchEvent(
                    new Event('change', { bubbles: true })
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
                theme: parseJSON(
                    this.getAttribute('data-bz-theme'), {}
                ),
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
                    '<button type="button" data-month-cell ' +
                    'class="' + cellCls + '" ' +
                    'data-value="' + ym + '" ' +
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
                        '<button type="button" data-day-cell ' +
                        'class="' + escapeAttr(theme.day_cell || '') + '" ' +
                        'data-date="' + s + '" ' +
                        'data-mark="' + mark + '"' + markLabel + ' ' +
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
            var cells = this.querySelectorAll('[data-day-cell]');
            cells.forEach(function (cell) {
                var s = cell.getAttribute('data-date');
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
            this.querySelectorAll('[data-month-cell]').forEach(function (c) {
                c.onclick = function () {
                    if (c.getAttribute('aria-disabled') === 'true') return;
                    var ym = c.getAttribute('data-value');
                    self.setAttribute('value', ym);
                    self._syncHiddenAndFireChange(ym, ym);
                };
            });
            // Prev / next buttons live in the Python-rendered header
            // (``data-bz-cal-header``). They're ``bz-on:click``
            // handlers that mutate the wrapper's ``year`` / ``month``
            // scope ; nothing to wire here.

            var cells = this.querySelectorAll('[data-day-cell]');
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
                        self._hoverDate = cell.getAttribute('data-date');
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
            var s = cell.getAttribute('data-date');
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


/* 08_file_upload.js — $bz.fileUpload.makeScope factory for ui.file_upload. */
// ════════════════════════════════════════════════════════════════════════
// 08 FILE UPLOAD — bz-data scope factory for <ui.file_upload>.
//
// Why a runtime slab
// ──────────────────
// The component carries enough JS for the inline-bz-data shape to bloat
// every instance by ~3 kB. Externalising into one factory means each
// instance just drops ``bz-data="$bz.fileUpload.makeScope({el: $el, …})"``
// (~250 chars). The factory owns :
//
// V3 notes : (a) the scope captures its root element (``opts.el``,
// available in the ``bz-data`` expression) — V3 scope methods get no
// ``$root`` / ``$refs`` / ``$dispatch`` magic. (b) V3 signals compare
// by identity, so array mutations REASSIGN (``files = [...]``) and
// per-file updates replace the entry object (keyed by id) so the
// ``bz-for`` rows re-render.
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

    function formatSize(bytes) {
        if (bytes >= 1048576) return (bytes / 1048576).toFixed(1) + ' MB';
        if (bytes >= 1024) return (bytes / 1024).toFixed(0) + ' KB';
        return bytes + ' B';
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

    function makeScope(opts) {
        const acceptList = opts.accept
            ? String(opts.accept).split(',').map((s) => s.trim()).filter(Boolean)
            : null;
        const maxSizeMB = opts.maxSizeMB || null;
        const maxFiles = opts.maxFiles || null;
        const multiple = !!opts.multiple;
        const showPreviews = opts.showPreviews !== false;  // default true
        const uploadUrl = opts.uploadUrl || null;

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
            // hook — the method that lived here came from the Alpine
            // era, where it was called automatically, and has never run
            // since (audit F22/F74). The previews' blob URLs are revoked
            // in the three places that remove a file (single-file
            // replacement, removeFile, clear); what stays unfreed are
            // the previews of a component removed from the DOM with
            // files still in it. A known debt, tracked in inventory.md:
            // reopening it asks for a real unmount hook on the runtime
            // side, not a method nobody calls.

            // ── Validation + add ───────────────────────────────────
            handleFiles(fileList) {
                this.errors = [];
                let incoming = Array.from(fileList);
                let sizeRejected = 0;
                let formatRejected = 0;
                let firstReject = '';

                if (!multiple && incoming.length > 1) {
                    this.errors = this.errors.concat(['Only one file allowed.']);
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
                            ['Maximum ' + maxFiles + ' files reached.']);
                        return;
                    }
                    if (incoming.length > room) {
                        this.errors = this.errors.concat([
                            (incoming.length - room) + ' files skipped — limit ' +
                            maxFiles + ' reached.'
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
                        const reason = sizeRejected
                            ? 'exceeds ' + maxSizeMB + ' MB'
                            : 'format not supported';
                        msg = firstReject + ' — ' + reason;
                    } else {
                        let reason = 'invalid';
                        if (sizeRejected && !formatRejected) reason = 'too large';
                        else if (formatRejected && !sizeRejected) reason = 'wrong format';
                        else reason = 'size or format';
                        msg = rejected + ' files skipped (' + reason + ').';
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
                    this._patchFile(id, { status: 'error', error: 'Network error' });
                    this.dispatch('upload-error', {
                        file: file,
                        error: 'Network error',
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
                // header as the bridge (05_bridge.js).
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

    window.$bz.fileUpload = { makeScope: makeScope, formatSize: formatSize };
})();


/* 09_notification.js — toast stack manager (bz-data scope factory). */
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
// leave is a two-phase dismiss (flip ``_leaving`` → wait ``LEAVE_MS`` →
// splice) so the ``bz-toast-leave`` keyframe can play before removal.
//
// Variant / icon / position normalisation reads the theme blob the
// shell injects on ``window.$bz_theme.notification``.
// ════════════════════════════════════════════════════════════════════════

(function () {
  "use strict";
  const $bz = window.$bz;
  if (!$bz) return;

  // Mirrors the ``bz-toast-out`` duration in the shell keyframes
  // (``_NOTIFICATION_ANIM_STYLE``). Keep them in sync.
  const LEAVE_MS = 200;

  // Shared with the bz-for FLIP reflow — see 06_helpers.js.
  const prefersReducedMotion = $bz.helpers.prefersReducedMotion;

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
        // No animation wanted : drop it now, skip the leave dance.
        if (prefersReducedMotion()) {
          this._remove(id);
          return;
        }
        // Phase 1 — mark the toast leaving so the ``bz-toast-leave``
        // keyframe plays (``bz-class`` reacts to ``_leaving``). Reassign a
        // fresh object under the same ``id`` so the keyed ``bz-for`` updates
        // the existing node in place instead of remounting it. Guard against
        // a double dismiss (manual click + auto-timeout) so we never restart
        // the animation or schedule a second removal.
        let found = false;
        const next = {};
        for (const p of Object.keys(this.stacks)) {
          next[p] = this.stacks[p].map(function (t) {
            if (t.id === id && !t._leaving) {
              found = true;
              return Object.assign({}, t, { _leaving: true });
            }
            return t;
          });
        }
        if (!found) return;
        this.stacks = next;
        // Phase 2 — actually splice once the leave animation has played.
        const self = this;
        setTimeout(function () {
          self._remove(id);
        }, LEAVE_MS);
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


/* 10_charts.js — shared chart tooltip + legend scope factories. */
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
// 1. Lazily mounts a single ``<div class="bz-chart-tooltip">`` on
//    ``<body>`` the first time a chart needs it (zero cost on a page
//    with no charts at all).
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
//   $bz.charts.hide()         → force-hide (e.g. on htmx swap)
// ════════════════════════════════════════════════════════════════════════

(function () {
    'use strict';

    var $bz = window.$bz;
    if (!$bz) return;

    var tip = null;
    var hideTimer = null;
    // Closure that recomputes the visible tooltip's viewport rect from
    // live geometry (returns null when it can't). Each show path installs
    // one capturing whatever it needs — a bar's ``.bz-bar-fill``, a
    // scatter dot, a pie centroid, a line column + fraction. Scroll /
    // resize replay it so a ``fixed`` panel positioned once stays glued
    // to its data point instead of drifting as the page scrolls.
    var activeReposition = null;

    // Tailwind classes carry the Bretzel theme tokens (``bg-text`` /
    // ``text-background`` resolve to the semantic palette set by the
    // user's ``Theme(...)``). The framework already ships these
    // classes (line_chart's tooltip slot uses the same recipe) so
    // they're guaranteed to be in the compiled CSS.
    var TOOLTIP_CLASSES = (
        'bz-chart-tooltip fixed z-50 pointer-events-none ' +
        'px-2.5 py-1.5 rounded-box bg-text/95 text-background ' +
        'text-xs font-medium leading-relaxed whitespace-pre-line ' +
        'shadow-md opacity-0 transition-opacity duration-150'
    );

    function ensureTooltip() {
        if (tip) return tip;
        tip = document.createElement('div');
        tip.className = TOOLTIP_CLASSES;
        tip.setAttribute('role', 'tooltip');
        document.body.appendChild(tip);
        return tip;
    }

    // Set the panel's left/top for a viewport-space ``rect`` — top-
    // anchored, flips below when the trigger hugs the top edge. Reads
    // the panel's own size first (textContent is already set).
    function placeAt(rect) {
        var t = ensureTooltip();
        var tw = t.offsetWidth;
        var th = t.offsetHeight;
        var cx = rect.left + rect.width / 2;
        var aboveY = rect.top - th - 8;
        var flipped = aboveY < 4;
        var y = flipped ? (rect.bottom + 8) : aboveY;
        var x = Math.max(4, Math.min(window.innerWidth - tw - 4, cx - tw / 2));
        t.style.left = x + 'px';
        t.style.top = y + 'px';
    }

    function position(rect) {
        var t = ensureTooltip();
        t.style.left = '0px';
        t.style.top = '0px';
        placeAt(rect);
        t.style.opacity = '1';
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

    // Keep the visible panel glued to its anchor across scroll / resize —
    // recompute geometry and move (no opacity toggle, so no re-fade).
    function reposition() {
        if (!tip || tip.style.opacity !== '1' || !activeReposition) return;
        var rect = activeReposition();
        if (rect) placeAt(rect);
    }
    // Capture phase so scrolls inside any nested scroll container (not
    // just the window) reach us — scroll events don't bubble.
    window.addEventListener('scroll', reposition, true);
    window.addEventListener('resize', reposition);

    function hideTooltip() {
        activeReposition = null;
        if (!tip) return;
        // Tiny grace period so a fast cursor leaving one bar and entering
        // the next doesn't flash the tooltip in/out — the next ``show``
        // cancels the pending hide.
        clearTimeout(hideTimer);
        hideTimer = setTimeout(function () {
            if (tip) tip.style.opacity = '0';
        }, 60);
    }

    // The ``show`` handshake every hover path repeats : resolve the
    // hovered element, read its pre-formatted label, cancel a pending
    // hide, make sure the tooltip node exists, and write the text ONLY
    // when it changed (writing the same string would invalidate layout
    // before ``offsetWidth`` is read, for nothing).
    //
    // Returns the hovered element when a label is on screen, or null
    // when there was nothing to show — each caller then does its own
    // anchoring, which is where they genuinely differ (bar-fill lookup,
    // dot rect, line-column band). Three copies before (audit F59).
    function showLabel(event) {
        var el = event && event.currentTarget;
        if (!el) return null;
        var label = el.getAttribute('data-bz-display');
        if (!label) return null;
        clearTimeout(hideTimer);
        var t = ensureTooltip();
        if (t.textContent !== label) t.textContent = label;
        return el;
    }

    function tooltipScope() {
        return {
            show: function (event) {
                var el = showLabel(event);
                if (!el) return;
                // Bar charts widen the hit target to the whole column via
                // a transparent ``.bz-bar-hit`` overlay that spans the
                // plot. Anchoring on the overlay itself would float the
                // tooltip at the top of the column ; anchor on the sibling
                // ``.bz-bar-fill`` instead so it lands on the data point.
                var anchor = el;
                if (el.classList && el.classList.contains('bz-bar-hit')) {
                    var fill = el.parentNode &&
                        el.parentNode.querySelector('.bz-bar-fill');
                    if (fill) anchor = fill;
                }
                // Anchor on the data point : a bar's ``.bz-bar-fill``, a
                // scatter/line dot, or a pie wedge's ``data-bz-ax/ay``
                // centroid (a ``<path>`` bbox would float the panel at the
                // pie's centre). ``rectForAnchor`` resolves all three ;
                // stash the element so scroll / resize can re-anchor.
                var rect = rectForAnchor(anchor);
                if (rect) {
                    activeReposition = function () {
                        return rectForAnchor(anchor);
                    };
                    position(rect);
                } else {
                    // Last-resort fallback (path with no centroid attrs) —
                    // pin to the cursor ; nothing to re-anchor on scroll.
                    activeReposition = null;
                    position({
                        left: event.clientX, right: event.clientX,
                        top: event.clientY, bottom: event.clientY,
                        width: 0, height: 0,
                    });
                }
            },
            hide: function () { hideTooltip(); },
        };
    }

    // Force-hide on htmx swap so a refresh that replaces the chart
    // doesn't leave the tooltip pointing at thin air.
    document.addEventListener('htmx:before-swap', function () {
        activeReposition = null;
        if (tip) tip.style.opacity = '0';
    });

    function parseJSON(attr, fallback) {
        if (!attr) return fallback;
        try { return JSON.parse(attr); } catch (e) { return fallback; }
    }

    // Legend visibility, shared by every multi-series chart scope.
    // ``visible[i]`` drives ``bz-show`` on the path / dots / markers the
    // server rendered with series index ``i``.
    //
    // Two load-bearing details lived in two copies (audit F18) : the
    // "never toggle the last one off" guard (an all-hidden chart reads
    // as broken — Vercel and Stripe ship the same rule), and the
    // REASSIGN in toggleSeries (V3 signals are identity-compared, so an
    // in-place ``visible[i] = …`` would not re-render).
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
        return {
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
                var el = showLabel(event);
                // Nothing to show (no target, or a column with no
                // label) → hide. The pre-shared version returned early
                // without hiding in the no-target case ; a dispatched
                // mouseenter always has a currentTarget, and hideTooltip
                // no-ops when no tooltip node exists yet.
                if (!el) { hideTooltip(); return; }
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
                activeReposition = lineRect;
                position(lineRect());
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
        };
    }

    function scatterScope(opts) {
        var vis = seriesVisibility((opts && opts.n_series) || 1);
        return {
            visible: vis.visible,
            isVisible: vis.isVisible,
            toggleSeries: vis.toggleSeries,
            // Floating tooltip on per-dot hover. Each ``<circle>``
            // dot carries ``data-bz-display`` ; the circle's
            // ``getBoundingClientRect()`` is tight (``r × 2`` box)
            // so anchoring above it lands cleanly on the dot.
            show: function (event) {
                var el = showLabel(event);
                if (!el) return;
                activeReposition = function () {
                    return el.getBoundingClientRect();
                };
                position(el.getBoundingClientRect());
            },
            hide: function () { hideTooltip(); },
        };
    }

    $bz.charts = {
        tooltipScope: tooltipScope,
        lineScope: lineScope,
        scatterScope: scatterScope,
        hide: hideTooltip,
    };
})();


/* 11_number_input.js — shared scope for the NumberInput component.
 *
 * The full client logic (precision, clamp, snap-to-step, draft-vs-value,
 * nudge, change emission) lived INLINE in every instance's bz-data
 * attribute (~1.5 KB of method bodies repeated per <ui.number_input>).
 * It now lives here ONCE ; each instance emits only its state +
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
      _displayValue() {
        const v = this._read();
        if (v == null || v === "") return "";
        return String(this._round(Number(v)));
      },
      _commitDraft(final) {
        const raw = String(this._draft || "").trim();
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
          this._draft = String(clamped);
          this._emitChange();
        } else {
          this._write(this._round(n));
        }
      },
      _nudge(delta) {
        const cur = this._read() == null ? 0 : Number(this._read());
        const next = this._snap(this._clamp(cur + delta));
        this._write(next);
        if (this._focused) this._draft = String(next);
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
        this._draft = String(next);
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


/* 12_slider.js — shared scope for the Slider component.
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


/* 13_select.js — shared scopes for the Select component.
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

  $bz.select = {
    single: {
      // A value's label. Select KEEPS its ``_labels`` map (its
      // ``_options`` carries only values, so it is not redundant
      // there); what disappeared on 2026-08-28 is the map RE-INLINED
      // in each pill template's ``bz-text`` — a third copy of the
      // same table. The shared template
      // (``_picker.build_pills_template``) now calls this method,
      // which Combobox defines its own way.
      _labelOf(v) { return this._labels[String(v)] || ""; },
      _pick(v) { this._write(v); this.open = false; },
      _isPicked(v) { return String(this._read() || "") === String(v); },
      _highlightFromValue() {
        this._highlight = Math.max(0, this._options.indexOf(String(this._read())));
      },
    },
    multi: {
      ...$bz.multiSelect,
      // A value's label. Select KEEPS its ``_labels`` map (its
      // ``_options`` carries only values, so it is not redundant
      // there); what disappeared on 2026-08-28 is the map RE-INLINED
      // in each pill template's ``bz-text`` — a third copy of the
      // same table. The shared template
      // (``_picker.build_pills_template``) now calls this method,
      // which Combobox defines its own way.
      _labelOf(v) { return this._labels[String(v)] || ""; },
      _value() { const v = this._read(); return v == null ? [] : v; },
      // Select-specific : every option is always visible (no query).
      // ``_clearAll`` is NOT redeclared — the mixin's does exactly that,
      // and repeating it here is how the two pickers diverged (audit
      // F19).
      _selectAll() { this._write(this._options.slice()); },
      _highlightFromValue() {
        const picks = this._picked();
        if (picks.length) this._highlight = Math.max(0, this._options.indexOf(picks[0]));
        else this._highlight = 0;
      },
    },
  };
})();


/* 14_combobox.js — shared scopes for the Combobox component.
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
 * ⚠️ There was also a ``_labels: {value: label}``, removed on
 * 2026-08-28: each ``_options`` entry ALREADY carries its ``label``, so
 * the map repeated half the list — 501 bytes of 22,586 for twenty
 * options. Its only reader (the label shown in the closed field, in
 * single mode) goes through ``_labelOf`` below. ``Select``, for its
 * part, KEEPS it: its ``_options`` carries only values, so the map is
 * not redundant there.
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
     * Before 2026-09-02, each option carried five directives:
     * ``bz-class``, ``bz-attr:aria-selected``, ``bz-show`` and two
     * ``bz-on:``. Measured: 461 bytes per option, of which 177 for
     * those directives alone, repeated identically N times.
     *
     * Three of them become ONE effect and TWO delegated listeners, on
     * the panel. ``bz-show`` stays per option: it is the search filter,
     * and the runtime has its own hiding machinery.
     *
     * ⚠️ Why the options stay rendered by the SERVER — and why that is
     * not half a job. The repository's rule ("who writes the ``for``?",
     * gated by ``test_collection_owner_decides_the_api``) ties the place
     * of the render to the API's shape: a component that renders its
     * collection on the SERVER side is entitled to a ``render=``
     * callback, a component whose client creates the nodes is NOT — a
     * Python callback does not run in the browser. Painting the options
     * here would therefore lose the combobox its ``render=``, added on
     * 2026-08-18 precisely because the layout thesis had counted it
     * among the four collections with NO way out for the author. The
     * gain in bytes is not worth a content escape hatch in a framework
     * that has nine for 498 style slots.
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
        const choisi = !!isPicked(o.getAttribute("data-value"));
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
      // JS mirror of the Python text normaliser (lowercase + strip
      // diacritics). Constant across instances.
      _norm: (s) => s.toLowerCase().normalize("NFD").replace(/\p{M}/gu, ""),
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
        return hit ? hit.label : "";
      },
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
      _moveHighlight(delta) {
        const vis = this._visibleIndices();
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
        const vis = this._visibleIndices();
        let idx = this._highlight;
        if (idx < 0 || !vis.includes(idx)) idx = vis[0];
        if (idx == null) return;
        this._pick(this._options[idx].value);
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
        const vis = this._visibleIndices();
        let idx = this._highlight;
        if (idx < 0 || !vis.includes(idx)) idx = vis[0];
        if (idx == null) return;
        this._togglePick(this._options[idx].value);
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


/* 15_pagination.js — the Pagination component's shared scope.
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
 * NumberInput had already applied (cf. 11_number_input.js):
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
      // the Slider's ``_disabledState`` (12_slider.js:28).
      //
      // ⚠️ It is NOT data. A ``_disabled: <store path>`` field in the
      // bz-data would be evaluated ONCE, outside any effect: ``absorb``
      // wraps the snapshot in a new signal decoupled from the cell, and
      // nothing rewrites it any more. The lock therefore stayed frozen
      // at its mount value (measured: the switch flips, the pagination
      // stays clickable). A bound expression must live in a METHOD BODY,
      // the only place re-read at every call hence tracked by the
      // calling effect. Cf. traps.md § "a bz-data field is not
      // reactive".
      isDisabled() {
        return false;
      },

      // A setter — it only mutates on a real change, so a click on the
      // current page is a no-op. It is the hidden input's ``bz-effect``
      // that turns the mutation into a bubbling ``change``.
      //
      // The lock and the bound live HERE, in the single mutator, because
      // the callers are no longer equivalent: the rail's buttons are
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


/* 16_accordion.js — the shared scopes of Accordion, Tree, Tabs, Stepper
 * and Tooltip. (The file's name dates from the first arrival.)
 *
 * Both components serialised all their method bodies into every
 * instance's ``bz-data`` — Accordion 622 bytes, Tree 293 — and Accordion
 * additionally baked its configuration INTO the code:
 *
 *     toggle(v) { … if (cur === target) { if (true) { … } } … }
 *                                            ^^^^ collapsible
 *     expandAll() { const ids = ["a","b","c"]; … }
 *
 * Two accordions with different configurations therefore produced two
 * different CODES, not two different states — that is what made
 * factoring impossible. The switch is "config as data", the same
 * prerequisite as NumberInput (11) and Pagination (15).
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
  // ``$bz.pagination.setActive``. Serialised per instance until
  // 2026-07-29.
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
      // Set by ``bz-init``, the route ``06_helpers.js`` documents for an
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

  // ── Tooltip ───────────────────────────────────────────────────────
  // The clearest case of "config baked into the code" after Pagination:
  // the serialised body contained ``if (!(true)) return;`` — the
  // activation flag hard-coded — and the opening delay as a literal. Two
  // tooltips with different delays produced two different CODES.
  //
  // ``_delay`` becomes data — it is a server-side literal, so REAL data.
  // ``_enabled`` does not: it accepts a ClientBinding or a live JS
  // expression, and a bz-data field is evaluated only once, outside any
  // effect (``absorb`` decouples its snapshot from the store). Switching
  // it to a field had therefore frozen it at mount although the
  // builder's docstring promised the opposite — "the condition is
  // evaluated at hover time". It becomes a METHOD again: a constant by
  // default here, overridden by the builder when the condition is
  // real.
  $bz.tooltip = {
    scope: {
      _enabled() {
        return true;
      },
      _show() {
        if (!this._enabled()) return;
        clearTimeout(this._t);
        this._t = setTimeout(() => {
          this.open = true;
        }, this._delay);
      },
      _hide() {
        clearTimeout(this._t);
        this.open = false;
      },
    },
  };
})();


/* 17_carousel.js — the Carousel component's shared scope.
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
        // time, with that instant's layout, and is never re-read. Paid
        // for real: hydrated before the Tailwind sheet applies, the
        // track is not yet ``flex``, so ``scrollWidth === clientWidth``,
        // so the bound is 0, so BOTH arrows are disabled — and
        // ``disabled:opacity-0`` erases them. No arrow at the first
        // visit, all of them on refresh. Cf. ``_observeGeom`` for what
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
        // signal at the first write — cf. ``03_scope.js``). A node
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


/* 18_time_picker.js — the TimePicker component's shared scope.
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
 * from the store cell, which nothing rewrites any more (a regression
 * measured on Pagination and Tooltip, cf. traps.md § "a bz-data field is
 * not reactive").
 *
 * Why a shared scope rather than inline expressions: a panel with 24
 * hours and 4 minutes is 28 buttons. Writing the pick and the selection
 * test out in full on each would serialise the same algorithm 28 times
 * PER INSTANCE — exactly what Pagination's and Accordion's "config as
 * data" switches removed.
 */
(function () {
  "use strict";
  const $bz = (window.$bz = window.$bz || {});

  //: The index of the two parts in the tuple ``_parts`` returns.
  const HOUR = 0;
  const MINUTE = 1;

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
     * Why the cells are no longer rendered by Python
     * -----------------------------------------------
     * They each carried the theme's class string — 452 characters — and
     * two directives (``bz-attr:data-selected`` + ``bz-on:click``). At
     * ``step=1`` that is 84 cells: 49 kB of the 54 the component
     * weighed, 38 of them for the single class repeated identically.
     * Measured on 2026-09-01.
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
      const cols = el.querySelectorAll("[data-bz-part]");

      for (let i = 0; i < cols.length; i++) {
        const col = cols[i];
        const part = Number(col.getAttribute("data-bz-part"));
        const label = col.getAttribute("data-bz-cell-label") || "";

        if (!col.querySelector("[data-bz-v]")) {
          const values = (col.getAttribute("data-bz-values") || "")
            .split(",").filter(Boolean);
          const barred = (col.getAttribute("data-bz-off") || "")
            .split(",").filter(Boolean);
          let html = "";
          for (let j = 0; j < values.length; j++) {
            const v = values[j];
            const dead = off || barred.indexOf(v) !== -1;
            html +=
              '<button type="button" data-bz-v="' + v + '"' +
              ' class="' + cellCls + '"' +
              ' aria-label="' + label + " " + v + '"' +
              (dead ? " disabled" : "") + ">" + v + "</button>";
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
            pick(part, cell.getAttribute("data-bz-v"));
          });
        }

        // The selection, at every pass of the effect.
        const courant = parts[part];
        const cells = col.querySelectorAll("[data-bz-v]");
        for (let j = 0; j < cells.length; j++) {
          const c = cells[j];
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


/* 19_dnd.js — the node-DnD gesture shared by `dropzone` / `draggable`.
 *
 * ⚠️ **Distinct from the "drag" of the repository's two other
 * families**, and §6 of the roadmap insists because confusing them
 * costs:
 *   - `12_slider.js`      = pointer-drag (pointer → continuous value);
 *   - `08_file_upload.js` = native HTML5 DnD (OS files, DataTransfer).
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
 * morph** and keeps no state on the nodes — the constraint traps.md
 * § "bz-class lost after a morph" made non-negotiable.
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
 *      recreated — measured, and gated by
 *      `tests/runtime_js/test_morph_preserves_reordered_nodes.py`.
 *
 * ── A refusal's snap-back needs code, contrary to what was written
 *    here ──────────────────────────────────────────────────────────────
 * This line long said "a server refusal = no mutation = the morph puts
 * the item back. No dedicated code here." That was FALSE, and the gate
 * claiming to prove it was vacuous: the playground's handler increments
 * a refusal counter, so its state changed, so the zone re-rendered —
 * the snap-back did not come from the refusal but from the counter. A
 * handler that refuses by mutating NOTHING — the case `Move` documents
 * as THE way to refuse, and `examples/crm`'s — makes no zone re-render:
 * the server answers zero bytes and the card stays where the finger let
 * it go. Measured on 2026-09-09 on `examples/kanban`: a
 * work-in-progress limit refused on the server, and the screen showed
 * four cards in a column that accepts three.
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
 *          + a hidden carrier [data-bz-move-carrier] holding the hx-post
 *   item : data-bz-draggable  data-bz-key="…"  [data-bz-group] [data-bz-disabled]
 *          [data-bz-handle]  → when present, only [data-bz-drag-handle] grabs
 */
(function () {
  "use strict";
  const $bz = (window.$bz = window.$bz || {});

  //: Mouse/stylus: the distance before the gesture becomes a drag. It is
  //: this threshold that PRESERVES THE CLICK — without it, every click
  //: on a card would start a move.
  const MOUSE_THRESHOLD_PX = 5;
  //: Touch: how long you press before grabbing.
  const TOUCH_HOLD_MS = 250;
  //: …and the distance beyond which we give up before the delay ends.
  //: It is what PRESERVES THE SCROLL: a finger running down a list must
  //: not carry off the card it brushed.
  const TOUCH_TOLERANCE_PX = 8;

  //: The witness of a drop awaiting an answer. Set on the item, erased
  //: by the morph — the server never renders this attribute, so
  //: idiomorph removes it when it re-pairs the node. It is the only
  //: measurement possible from the client of "did the answer touch this
  //: item", and it asks for no new protocol.
  const PENDING_ATTR = "data-bz-drop-pending";

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
    /* An EMPTY zone. Falling back on the zone itself was a bug, and the
       comment that lived here said why it went unnoticed: "the next
       server render will put the card back in the stack". It does not.
       The moved node keeps its `bz-id`, which encodes its path in the
       tree; that path has changed, so idiomorph does not re-pair it and
       the card STAYS where it was dropped — that is to say a direct
       child of the zone, OUTSIDE the container the app rendered.

       Reproduced on 2026-09-13 on `/dnd`, by a drag that HESITATES: you
       take the item out of its zone, change your mind, come back. The
       original zone is then empty, the item is re-appended at its root,
       and it shows beside its box instead of inside it. A hesitant
       gesture is the ordinary gesture.

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
     group is unique per instance there), and the playground's bench
     proved it necessary — without it, grabbing a kanban card lit up the
     page's five unrelated zones.
     Receiving from elsewhere is therefore an OPT-IN, not a default. */
  function accepts(zone, group, originZone) {
    //: ⚠️ `accepts` governs ENTRY FROM ELSEWHERE, not internal
    //: reordering. Reordering within its own zone is not entering it:
    //: the item is already there, and nobody declared anything about
    //: that. Consulting `accepts` here froze a whole list as soon as the
    //: items' `group=` did not answer its `accepts=` — measured:
    //: `accepts=["card"]` on items with no group made the zone totally
    //: inert, in silence. Sortable.js separates `put` (receive) from
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
    //: The dragged item is NOT excluded, and that is the 2026-08-10
    //: correction: we move the real node, so it is still in the flow and
    //: its box is as valid as any other's. Excluding it left a list of
    //: TWO items with a single reference point, so a fallback to the
    //: vertical axis — measured: a horizontal row of two cards was
    //: impossible to reorder, the comparison being made on a Y both
    //: share.
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
      const dx = Math.abs(e.clientX - armed.x);
      const dy = Math.abs(e.clientY - armed.y);
      if (armed.touch) {
        //: The finger ran off before the delay ended: it was a scroll.
        if (Math.max(dx, dy) > TOUCH_TOLERANCE_PX) disarm();
      } else if (Math.max(dx, dy) > MOUSE_THRESHOLD_PX) {
        begin();
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

  /* The core: put the node where the pointer says it is going. */
  function hoverTo(x, y) {
    const under = document.elementFromPoint(x, y);
    if (!under) {
      if (active.preview) active.preview.style.visibility = "";
      return;
    }
    const overZone = zoneOf(under);
    if (!overZone) {
      if (active.preview) active.preview.style.visibility = "";
      return;
    }
    //: A trash zone is a terminal action, not a destination to inspect.
    //: The source card is still temporarily reparented there so `finish()`
    //: can report the target, but showing its floating clone over the bin
    //: makes it read as a second card.  Hide that clone while the pointer is
    //: above any locked zone; reveal it immediately when it leaves again.
    if (active.preview) {
      active.preview.style.visibility = overZone.hasAttribute("data-bz-locked")
        ? "hidden" : "";
    }
    if (!canEnter(overZone, active.group, active.originZone)) return;

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

    const overItem = under.closest(ITEM_SEL);
    if (overItem && overItem !== active.item && zoneOf(overItem) === overZone) {
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
    active.originParent.insertBefore(active.item, active.originNext);
    cleanup();
  }

  /* Undo the drop if the answer did not confirm it.
     ⚠️ Two frames of waiting, not one: `htmx:afterRequest` is the only
     reliable disarm (htmx emits it on 4xx, network errors and aborts
     too), but the swap and the rescan around it land on the following
     frames. Checking straight away would read the witness before the
     morph had a chance to erase it, and EVERY drop would be undone. */
  function armSnapBack(item, parent, next, carrier) {
    const itemKey = item.getAttribute("data-bz-key") || "";
    const destination = zoneOf(item);
    const destinationName = destination
      ? destination.getAttribute("data-bz-dropzone") || ""
      : "";
    item.setAttribute(PENDING_ATTR, "");
    function settle(e) {
      if (e.detail && e.detail.elt && e.detail.elt !== carrier) return;
      document.body.removeEventListener("htmx:afterRequest", settle);
      requestAnimationFrame(function () {
        requestAnimationFrame(function () {
          if (!item.hasAttribute(PENDING_ATTR)) return;
          item.removeAttribute(PENDING_ATTR);
          //: The server may have removed the item (archiving): there
          //: is then nothing to put back, and its old parent may itself
          //: have disappeared.
          if (!item.isConnected || !parent.isConnected) return;
          parent.insertBefore(
            item, next && next.parentNode === parent ? next : null
          );
        });
        requestAnimationFrame(function () {
          restoreSequentialFocus(itemKey, destinationName);
        });
      });
    }
    document.body.addEventListener("htmx:afterRequest", settle);
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

  function finish() {
    const a = active;
    //: An overwrite did NOT move the node: the target zone is read from
    //: the mark, not from the position. Its index is 0 — a zone with one
    //: element has no other.
    const remplace = a.replaceZone;
    const toZone = remplace || zoneOf(a.item);
    const toIndex = remplace ? 0 : indexOf(a.item);
    const origin = {parent: a.originParent, next: a.originNext, item: a.item};
    cleanup();
    if (!toZone) return;

    //: Nothing moved → no server round trip. A drag that puts the item
    //: back where it was must not produce a `Move`.
    if (!remplace && toZone === a.originZone && toIndex === a.originIndex) {
      return;
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
    if (!carrier) return;

    carrier.value = JSON.stringify({
      item_key: a.item.getAttribute("data-bz-key") || "",
      from_zone: a.originZone.getAttribute("data-bz-dropzone") || "",
      to_zone: toZone.getAttribute("data-bz-dropzone") || "",
      from_index: a.originIndex,
      to_index: toIndex,
    });
    //: The home-made transport — the JS writes, dispatches, and it is
    //: the carrier's hx-post that leaves. No `fetch` here: the transport
    //: boundary belongs to the bridge (charter, principle 2).
    armSnapBack(origin.item, origin.parent, origin.next, carrier);
    $bz.helpers.emitChange(carrier, "move");
  }

  //: Once the gesture is GRABBED, the finger is ours: it is this
  //: `preventDefault` on the `touchmove` that stops the browser
  //: scrolling under the card.
  //:
  //: It does NOT duplicate `onPointerMove`'s. A `preventDefault` on a
  //: `pointermove` does not cancel a touch scroll — only the
  //: `touchmove` can, and only in a NON-PASSIVE listener. As long as the
  //: CSS set `touch-action: none` the question did not arise: the
  //: browser never scrolled. Since the item leaves `pan-x pan-y`
  //: (finding [27]: without it the finger could no longer scroll a
  //: column of cards), the gesture has to be taken over at the moment
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


/* 20_resizable.js — the shared scope of the Resizable component (split panes).
 *
 * ⚠️ **The repository's third "drag" family, and confusing it costs**:
 *   - `12_slider.js`      = pointer → a VALUE on a scale;
 *   - `19_dnd.js`         = moving a NODE from one position to another;
 *   - here                = pointer → a DIMENSION. Nothing moves,
 *                           nothing changes parent: two neighbours
 *                           re-share the room they already occupy.
 * It is the slider's family (pointer-drag, continuous delta), not the
 * node-DnD's — the roadmap has said so since framing #6, and this file
 * therefore has NO dependency on `19_dnd.js`.
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
      // ⚠️ **The normalisation is not cosmetic, and forgetting it here
      // made the component inert.** ``_mins`` travels in PERCENTAGE
      // POINTS; if the weights stay raw, the two scales no longer talk
      // to each other. Measured: ``sizes=[1, 3]`` (a documented writing
      // — it is the RATIO that counts) with ``min_size=15`` gives
      // ``pair = 4``, ``lo = 15``, so ``hi < lo`` at every frame, so a
      // handle that NEVER moves — with no error, nothing in the console.
      // In local mode the defect was invisible because the ``bz-data``
      // seeded by the server is already normalised; it only showed in
      // binding mode, the very one the component puts forward for
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
      // bounded. Added on 2026-08-23 — ``_min`` lived alone, which was
      // an asymmetry and not a decision.
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


/* 21_signature_pad.js — the SignaturePad component's shared scope.
 *
 * **The repository's first and only `<canvas>`** (checked: zero other
 * occurrence, the charts are SVG). Everything that follows comes from
 * two properties of the canvas the rest of the framework never had to
 * deal with: it has no intrinsic size, and **resizing it clears it**.
 *
 * ── The third member of the pointer-drag family ───────────────────────
 *   - `12_slider.js`      = pointer → a VALUE on a scale;
 *   - `20_resizable.js`   = pointer → a DIMENSION;
 *   - here                = pointer → a STROKE.
 * Nothing to do with `19_dnd.js`'s node-DnD. The pointer capture goes
 * through `$bz.helpers.capturePointer`, extracted on 2026-08-13 while
 * shipping `resizable` — this file is its first new caller.
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
  //: would add no power (memory `project_api_opinionation_thesis`).
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
        this._write(inked ? this._canvas.toDataURL("image/png") : "");
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


/* 22_verbs.js — the CLIENT half of `bretzel.runtime.verbs`.
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
     * ⚠️ `navigator.share` is **undefined** on desktop Chromium
     * (measured on 2026-09-02: `typeof navigator.share === "undefined"`).
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
      if (!charge.url) charge.url = window.location.href;
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

    /* Vibrate. `navigator.vibrate` EXISTS everywhere (measured:
     * `function` on desktop Chromium) and does nothing with no hardware
     * — so there is no absence to handle, unlike `share`.
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


/* 23_diagram.js — the highlighting of neighbours, in `ui.diagram`.
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
 * Same reason as 16_accordion: serialising these method bodies into
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
       * DERIVED from the selection, never stored. The first version kept
       * a `lit` array that `light()` filled — and that array did not
       * move when the selection changed from OUTSIDE (a `select` bound
       * to the same `ClientState`, a `state.node.set(...)`). The store
       * followed, the screen did not: measured at `dim = 0` where a
       * click gave 3.
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
