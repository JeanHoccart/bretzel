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
