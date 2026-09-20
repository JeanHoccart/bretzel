/* 14_combobox.js — shared scopes for the Combobox component.
 *
 * The biggest inline scope (~30 methods : normalise/filter/nav +
 * pick/multi-membership/bulk) lived in every instance's bz-data. It now
 * lives here ONCE, split into a shared ``common`` (filter + nav) plus a
 * mode-specific ``single`` / ``multi``. Each instance spreads both :
 *
 *   bz-data="{...$bz.combobox.common, ...$bz.combobox.single,
 *             value: 'a', _read(){return this.value},
 *             _write(v){this.value=v}, open: false, query: '',
 *             _highlight: -1, _options: [...]}"
 *
 * ``_options`` (option objects w/ haystack) stays per instance.
 *
 * ⚠️ There was also a ``_labels: {value: label}``, removed on
 * 2026-08-28: each ``_options`` entry ALREADY carries its ``label``, so
 * the map repeated half the list — 501 bytes of 22,586 for twenty
 * options. Its only reader (the label shown in the closed field, in
 * single mode) goes through ``_labelOf`` below. ``Select``, for its
 * part, KEEPS it: its ``_options`` carries only values, so the map is
 * not redundant there.
 *
 * Value access goes through ``this._read()`` / ``this._write(v)``
 * (local: a ``value`` field ; binding: ``$bz.state.<path>``, read raw +
 * null-guard baked into the per-instance ``_read``). No live
 * ``get value()`` (scope.absorb freezes getters — cf. traps.md).
 */
(function () {
  "use strict";
  const $bz = (window.$bz = window.$bz || {});

  // No scope-level change dispatcher : ``change`` is fired by the
  // per-instance ``_change_emit_effect`` posted ON the hidden input
  // (combobox.py). That effect dispatches from the hidden input itself,
  // so the relocated htmx listener always sees it ; a scope method's
  // carrier resolved unreliably (root vs hidden, depending on bind
  // order) and, when it DID reach the input, fired a SECOND, redundant
  // ``change`` — a double server event. The value-setting methods below
  // just ``_write`` ; the effect observes the mutation and dispatches.

  $bz.combobox = {
    /* ── The options, painted by the PANEL ───────────────────────────
     *
     * Before 2026-09-02, each option carried five directives:
     * ``bz-class``, ``bz-attr:aria-selected``, ``bz-show`` and two
     * ``bz-on:``. Measured: 461 bytes per option, of which 177 for
     * those directives alone, repeated identically N times.
     *
     * Three of them become ONE effect and TWO delegated listeners, on
     * the panel. ``bz-show`` stays per option: it is the search filter,
     * and the runtime has its own hiding machinery.
     *
     * ⚠️ Why the options stay rendered by the SERVER — and why that is
     * not half a job. The repository's rule ("who writes the ``for``?",
     * gated by ``test_collection_owner_decides_the_api``) ties the place
     * of the render to the API's shape: a component that renders its
     * collection on the SERVER side is entitled to a ``render=``
     * callback, a component whose client creates the nodes is NOT — a
     * Python callback does not run in the browser. Painting the options
     * here would therefore lose the combobox its ``render=``, added on
     * 2026-08-18 precisely because the layout thesis had counted it
     * among the four collections with NO way out for the author. The
     * gain in bytes is not worth a content escape hatch in a framework
     * that has nine for 498 style slots.
     */
    optionOf(ev) {
      const o = ev.target.closest('[role="option"]');
      // A disabled button does not dispatch a click, but IT DOES
      // RECEIVE hovers — without that guard, moving the mouse over a
      // greyed option would highlight it as if it were pickable.
      return o && !o.disabled ? o : null;
    },

    /* Repaint every option's state: the highlight (keyboard and mouse)
     * and the selection.
     *
     * The two class strings travel ONCE, on the panel, instead of being
     * copied into each option's ``bz-class``.
     *
     * ⚠️ We manipulate ``classList`` directly rather than keeping
     * tracking on the node. It is deliberate and it is ``bz-class``'s
     * lesson (traps.md): a state kept on the element does not survive a
     * morph, so the active class was never re-added at the rescan. Here
     * the effect REPAINTS everything at every pass from the truth
     * (``_highlight`` and ``isPicked``), so a morph that would put the
     * SSR class back is caught at the next pass.
     */
    paintOptions(el, highlight, isPicked) {
      const actif = (el.getAttribute("data-bz-opt-active") || "").split(" ");
      const pris = (el.getAttribute("data-bz-opt-picked") || "").split(" ");
      const options = el.querySelectorAll('[role="option"]');
      for (let i = 0; i < options.length; i++) {
        const o = options[i];
        const choisi = !!isPicked(o.getAttribute("data-value"));
        o.setAttribute("aria-selected", choisi ? "true" : "false");
        for (const c of actif) {
          if (c) o.classList.toggle(c, i === highlight);
        }
        for (const c of pris) {
          if (c) o.classList.toggle(c, choisi);
        }
      }
    },

    common: {
      // JS mirror of the Python text normaliser (lowercase + strip
      // diacritics). Constant across instances.
      _norm: (s) => s.toLowerCase().normalize("NFD").replace(/\p{M}/gu, ""),
      _value() { return this._read(); },
      // A value's label, read in ``_options`` — which already carries
      // it. Replaces the ``_labels`` map each instance emitted in
      // addition (cf. the header). A single reader: the CLOSED field in
      // single mode, so a linear scan over an options list costs nothing
      // measurable, and it stays in step with ``_options`` when a server
      // refresh re-seeds it — which a map frozen in another field could
      // miss.
      _labelOf(v) {
        const s = String(v == null ? "" : v);
        if (!s) return "";
        const hit = this._options.find((o) => String(o.value) === s);
        return hit ? hit.label : "";
      },
      _tokens() {
        const q = this._norm(this.query || "");
        return q ? q.split(/\s+/).filter(Boolean) : [];
      },
      _matches(haystack) {
        const t = this._tokens();
        if (!t.length) return true;
        return t.every((tok) => haystack.includes(tok));
      },
      _visibleIndices() {
        const out = [];
        for (let i = 0; i < this._options.length; i++) {
          const o = this._options[i];
          if (o.disabled) continue;
          if (this._matches(o.haystack)) out.push(i);
        }
        return out;
      },
      _visibleCount() { return this._visibleIndices().length; },
      _moveHighlight(delta) {
        const vis = this._visibleIndices();
        if (!vis.length) { this._highlight = -1; return; }
        let pos = vis.indexOf(this._highlight);
        if (pos === -1) pos = delta > 0 ? -1 : vis.length;
        pos = Math.max(0, Math.min(vis.length - 1, pos + delta));
        this._highlight = vis[pos];
      },
    },
    single: {
      _pickHighlighted() {
        if (!this.open) { this.open = true; return; }
        const vis = this._visibleIndices();
        let idx = this._highlight;
        if (idx < 0 || !vis.includes(idx)) idx = vis[0];
        if (idx == null) return;
        this._pick(this._options[idx].value);
      },
      _picked() { const v = this._value(); return v == null || v === "" ? [] : [String(v)]; },
      _isPicked(v) { return String(this._value() || "") === String(v); },
      _hasPicked() { const v = this._value(); return v != null && v !== ""; },
      _pick(v) {
        this._write(String(v));
        this.query = ""; this.open = false; this._highlight = -1;
      },
      _togglePick(v) {
        if (this._isPicked(v)) {
          this._write(""); this.query = ""; this._highlight = -1;
        } else { this._pick(v); }
      },
      _setValue(raw) { this._pick(raw == null ? "" : raw); },
      _clearAll() { this._write(""); this.query = ""; this.open = false; },
      _selectAll() {},
      _removeLast() {},
      _removeOne(v) {
        if (this._isPicked(v)) { this._write(""); this.query = ""; }
      },
    },
    multi: {
      ...$bz.multiSelect,
      _pickHighlighted() {
        if (!this.open) { this.open = true; return; }
        const vis = this._visibleIndices();
        let idx = this._highlight;
        if (idx < 0 || !vis.includes(idx)) idx = vis[0];
        if (idx == null) return;
        this._togglePick(this._options[idx].value);
        this.query = ""; this._highlight = -1;
      },
      _removeLast() {
        const cur = this._picked();
        if (cur.length) { this._write(cur.slice(0, -1)); }
      },
      _selectAll() {
        const vis = this._visibleIndices();
        this._write(vis.map((i) => this._options[i].value));
      },
      // The mixin empties the selection without closing; Combobox ADDS
      // the query reset (Select has no search field).
      _clearAll() { $bz.multiSelect._clearAll.call(this); this.query = ""; },
    },
  };
})();
