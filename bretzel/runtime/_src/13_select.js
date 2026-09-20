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
