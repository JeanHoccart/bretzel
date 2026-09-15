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
      // Le libellé d'une valeur. Select GARDE sa carte ``_labels``
      // (son ``_options`` ne porte que des valeurs, donc elle n'y
      // est pas redondante) ; ce qui a disparu le 2026-08-28, c'est
      // la carte RÉ-INLINÉE dans le ``bz-text`` de chaque gabarit de
      // pastille — un troisième exemplaire de la même table. Le
      // gabarit partagé (``_picker.build_pills_template``) appelle
      // désormais cette méthode, que Combobox définit à sa façon.
      _labelOf(v) { return this._labels[String(v)] || ""; },
      _pick(v) { this._write(v); this.open = false; },
      _isPicked(v) { return String(this._read() || "") === String(v); },
      _highlightFromValue() {
        this._highlight = Math.max(0, this._options.indexOf(String(this._read())));
      },
    },
    multi: {
      ...$bz.multiSelect,
      // Le libellé d'une valeur. Select GARDE sa carte ``_labels``
      // (son ``_options`` ne porte que des valeurs, donc elle n'y
      // est pas redondante) ; ce qui a disparu le 2026-08-28, c'est
      // la carte RÉ-INLINÉE dans le ``bz-text`` de chaque gabarit de
      // pastille — un troisième exemplaire de la même table. Le
      // gabarit partagé (``_picker.build_pills_template``) appelle
      // désormais cette méthode, que Combobox définit à sa façon.
      _labelOf(v) { return this._labels[String(v)] || ""; },
      _value() { const v = this._read(); return v == null ? [] : v; },
      // Select-specific : every option is always visible (no query).
      // ``_clearAll`` n'est PAS redéclaré — celui du mixin fait
      // exactement ça, et le redire ici est comment les deux pickers
      // divergeaient (audit F19).
      _selectAll() { this._write(this._options.slice()); },
      _highlightFromValue() {
        const picks = this._picked();
        if (picks.length) this._highlight = Math.max(0, this._options.indexOf(picks[0]));
        else this._highlight = 0;
      },
    },
  };
})();
