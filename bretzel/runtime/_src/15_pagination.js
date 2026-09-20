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
