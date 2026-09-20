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
