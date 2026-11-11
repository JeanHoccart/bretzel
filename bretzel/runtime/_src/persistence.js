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
