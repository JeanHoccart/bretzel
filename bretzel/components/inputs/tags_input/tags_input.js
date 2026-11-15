/* tags_input.js — the scope of ``ui.tags_input``.
 *
 * Free values typed as tags; the instance emits only data
 * (``value`` / ``query`` / ``open`` / ``_highlight`` / ``_selected`` /
 * ``_labels``, and the server config ``_options`` / ``_pattern`` /
 * ``_texts``). The value goes through ``_read`` / ``_write`` (a local
 * field or the store cell), so the membership algebra is
 * ``$bz.multiSelect``'s.
 *
 * The suggestions are server-rendered buttons; ``_shows(i)`` filters them
 * (``bz-show``) and ``$bz.combobox.paintOptions`` lights the highlighted
 * one — the same two tools as the combobox's list.
 */
(function () {
  "use strict";
  const $bz = (window.$bz = window.$bz || {});
  // What separates two values typed or pasted at once.
  const SEPARATORS = /[;,\n\r\t]+/;

  $bz.tagsInput = {
    scope: {
      ...$bz.multiSelect,
      _value() { return this._read(); },
      // A tag's label: the one it was picked with, the one the server
      // knows for the value it rendered (``_known``), an option's, or the
      // value itself. ``_labels`` is the browser's own memory: the options
      // change with each search, a tag keeps its name.
      _labelOf(v) {
        const s = String(v);
        if (this._labels[s]) return this._labels[s];
        if (this._known[s]) return this._known[s];
        const hit = this._options.find((o) => o.value === s);
        return hit ? hit.label : s;
      },
      _remember() { this._labels = { ...this._known, ...this._labels }; },
      _valid(v) {
        if (!this._pattern) return true;
        try { return new RegExp("^(?:" + this._pattern + ")$", "u").test(String(v)); }
        catch (e) { return true; }
      },
      // A tag's tooltip: its value, and why it is refused when it is.
      _tipOf(v) {
        return this._valid(v) ? String(v) : String(v) + " — " + this._texts.invalid;
      },
      _shows(i) {
        const o = this._options[i];
        if (!o || this._isPicked(o.value)) return false;
        const q = $bz.fold(String(this.query || "").trim());
        if (!q) return true;
        return q.split(/\s+/).every((t) => o.haystack.includes(t));
      },
      _shown() {
        const out = [];
        for (let i = 0; i < this._options.length; i++) if (this._shows(i)) out.push(i);
        return out;
      },
      // The suggestions show on focus and follow the typing, closed when
      // nothing is left to suggest.
      _typed() {
        this._selected = "";
        const shown = this._shown();
        this.open = shown.length > 0;
        this._highlight = shown.length ? shown[0] : -1;
      },
      _say(key, v) {
        this._said = this._texts[key].replace("{text}", this._labelOf(v));
      },
      // Each piece of ``raw`` becomes a tag, unless it already is one.
      _add(raw) {
        const cur = this._picked();
        const pieces = String(raw == null ? "" : raw).split(SEPARATORS)
          .map((s) => s.trim()).filter(Boolean);
        const fresh = pieces.filter((p, i) => cur.indexOf(p) < 0 && pieces.indexOf(p) === i);
        if (!fresh.length) return;
        this._write([...cur, ...fresh]);
        this._say("added", fresh[fresh.length - 1]);
      },
      _remove(v) {
        this._removeOne(v);
        this._selected = "";
        this._say("removed", v);
      },
      _choose(i) {
        const o = this._options[i];
        if (!o) return;
        if (o.label !== o.value) this._labels = { ...this._labels, [o.value]: o.label };
        this._add(o.value);
        this.query = ""; this.open = false; this._highlight = -1;
      },
      // What is typed becomes a tag: on a separator, on leaving the field.
      _commit() {
        if (String(this.query || "").trim()) this._add(this.query);
        this.query = ""; this.open = false; this._highlight = -1;
      },
      _move(delta) {
        const shown = this._shown();
        if (!shown.length) return;
        let pos = shown.indexOf(this._highlight) + delta;
        pos = Math.max(0, Math.min(shown.length - 1, pos));
        this._highlight = shown[pos];
      },
      _key(e) {
        const k = e.key;
        const typed = String(this.query || "").trim();
        if (k === "ArrowDown" || k === "ArrowUp") {
          if (!this.open) return;
          e.preventDefault();
          this._move(k === "ArrowDown" ? 1 : -1);
        } else if (k === "Enter" || (k === "Tab" && typed)) {
          // Tab with nothing typed goes on to the next field.
          e.preventDefault();
          // The highlight is an index into ``_options``, and a server
          // search REPLACES them: an index from the list before points at
          // nothing, or at another person. Taken only if it still shows.
          const shown = this._shown();
          const pick = shown.indexOf(this._highlight) >= 0 ? this._highlight : shown[0];
          if (this.open && pick != null && (typed || k === "Enter")) this._choose(pick);
          else this._commit();
        } else if (k === ";" || k === ",") {
          e.preventDefault();
          this._commit();
        } else if (k === "Backspace" && !this.query) {
          const cur = this._picked();
          if (!cur.length) return;
          e.preventDefault();
          if (this._selected && cur.indexOf(this._selected) >= 0) this._remove(this._selected);
          else this._selected = cur[cur.length - 1];
        } else if (k === "Escape") {
          this.open = false; this._selected = "";
        } else {
          this._selected = "";
        }
      },
      // Pasting several values makes several tags at once.
      _paste(e) {
        const pasted = (e.clipboardData || window.clipboardData).getData("text");
        if (!SEPARATORS.test(pasted)) return;
        e.preventDefault();
        this._add(String(this.query || "") + pasted);
        this.query = ""; this.open = false;
      },
      // A double click puts a tag back into text, to correct it.
      _edit(v) {
        this._commit();
        this._removeOne(v);
        this.query = String(v);
        this._typed();
      },
      // ``.clear()`` / ``.set()`` land here too.
      _setValue(raw) {
        $bz.multiSelect._setValue.call(this, raw);
        this._selected = "";
      },
    },
  };
})();
