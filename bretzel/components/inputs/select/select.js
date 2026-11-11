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
