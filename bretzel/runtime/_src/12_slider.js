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
