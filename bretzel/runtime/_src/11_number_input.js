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
