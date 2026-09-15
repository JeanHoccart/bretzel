/* 04_persistence.js — storage adapters per ClientState instance.
 *
 * Per envelope.client_state[<Class>.<key>].persist :
 *
 *   "memory"    → JS memory only, dropped on reload (no adapter). C'est
 *                 le DÉFAUT côté Python (``ClientState.__persist__``).
 *   "session"   → sessionStorage, key "$bz:<Class>.<key>"
 *   "local"     → localStorage, same key
 *
 * ⚠️ ``"volatile"`` et ``"cross_tab"`` étaient listés ici jusqu'au
 * 2026-08-01 : l'enum Python (``state/scopes/client.py::PERSISTS``) ne
 * peut émettre que les trois ci-dessus, donc ces deux modes sont
 * inatteignables — et "memory", le défaut, n'était pas documenté. Le
 * test ``mode === "volatile"`` du code ci-dessous ne matche donc jamais ;
 * il tombe dans le même no-op que "memory" (storageFor → null).
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
