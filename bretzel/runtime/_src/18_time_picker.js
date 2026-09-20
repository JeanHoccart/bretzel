/* 18_time_picker.js — the TimePicker component's shared scope.
 *
 * The value is an ``"HH:MM"`` STRING — the same shape as the date
 * pickers' ISO: sortable, comparable, serialisable as is in a form data,
 * and readable by a human in the editable field.
 *
 *   bz-data="{...$bz.time.scope, open: false, value: "09:30",
 *             _read(){…}, _write(v){…}}"
 *
 * ⚠️ ``_read`` / ``_write`` are NOT an elegance: a bound expression must
 * live in a METHOD BODY. A ``bz-data`` field is evaluated ONCE, outside
 * any effect — ``absorb`` wraps its snapshot in a new signal decoupled
 * from the store cell, which nothing rewrites any more (a regression
 * measured on Pagination and Tooltip, cf. traps.md § "a bz-data field is
 * not reactive").
 *
 * Why a shared scope rather than inline expressions: a panel with 24
 * hours and 4 minutes is 28 buttons. Writing the pick and the selection
 * test out in full on each would serialise the same algorithm 28 times
 * PER INSTANCE — exactly what Pagination's and Accordion's "config as
 * data" switches removed.
 */
(function () {
  "use strict";
  const $bz = (window.$bz = window.$bz || {});

  //: The index of the two parts in the tuple ``_parts`` returns.
  const HOUR = 0;
  const MINUTE = 1;

  $bz.time = {
    scope: {
      // ── Reading ──────────────────────────────────────────────────
      // METHODS, never getters: ``scope.absorb`` invokes each key at
      // registration and would freeze a getter on its first value (cf.
      // traps.md).
      _parts() {
        const m = String(this._read() || "").match(/^(\d{1,2}):(\d{2})/);
        // Two empty strings rather than null: the callers compare, they
        // never have to test presence.
        return m ? [m[1].padStart(2, "0"), m[2]] : ["", ""];
      },
      _is(part, v) {
        return this._parts()[part] === v;
      },

      // ── Writing ──────────────────────────────────────────────────
      _pick(part, v) {
        const p = this._parts();
        p[part] = v;
        // An hour chosen while the minute is unknown is ``:00`` —
        // otherwise the field would stay EMPTY right after a click, and
        // the user would think the click did not take. Symmetrical for a
        // minute chosen first.
        this._write(
          (p[HOUR] || "00") + ":" + (p[MINUTE] || "00")
        );
      },
      // Clicking a MINUTE closes the panel, clicking an hour does not:
      // the reading order is hour then minute, so closing on the hour
      // would cut the user's hand off mid-gesture. ``_closeOnPick`` is
      // data (the component's prop).
      pick(part, v) {
        this._pick(part, v);
        if (this._closeOnPick && part === MINUTE) this.open = false;
      },
    },

    /* Paint the two columns' cells, then mark the selection.
     *
     * Why the cells are no longer rendered by Python
     * -----------------------------------------------
     * They each carried the theme's class string — 452 characters — and
     * two directives (``bz-attr:data-selected`` + ``bz-on:click``). At
     * ``step=1`` that is 84 cells: 49 kB of the 54 the component
     * weighed, 38 of them for the single class repeated identically.
     * Measured on 2026-09-01.
     *
     * It is the same remedy as ``<bz-calendar>``, which leaves its grid
     * EMPTY in SSR and fills it here — but WITHOUT a custom element: its
     * docstring says a second one would be the moment to make it a
     * runtime policy, and lightening a payload does not justify opening
     * that work. A ``bz-effect`` on the container is enough.
     *
     * The cells have NO directive left
     * ---------------------------------
     * A delegated click replaces 84 ``bz-on:click``, and this effect
     * replaces 84 ``bz-attr:data-selected``. It is what avoids having to
     * rescan the subtree after painting it — a ``$bz._scan`` called from
     * the body of an effect a scan has just installed would reinstall
     * itself.
     *
     * The effect runs again at every change of the value (it reads
     * ``_parts()``), so the selection is repainted without anything else
     * moving. The construction, for its part, only happens once: the
     * guard is a DOM MEASUREMENT ("do I already have cells?"),
     * legitimate here for the same reason as in
     * ``bz-calendar.rehydrate`` — it derives no display, it observes a
     * one-off fact at the only moment the question arises.
     */
    fill(el, parts, pick) {
      const cellCls = el.getAttribute("data-bz-cell-class") || "";
      const off = el.hasAttribute("data-bz-cells-disabled");
      const cols = el.querySelectorAll("[data-bz-part]");

      for (let i = 0; i < cols.length; i++) {
        const col = cols[i];
        const part = Number(col.getAttribute("data-bz-part"));
        const label = col.getAttribute("data-bz-cell-label") || "";

        if (!col.querySelector("[data-bz-v]")) {
          const values = (col.getAttribute("data-bz-values") || "")
            .split(",").filter(Boolean);
          const barred = (col.getAttribute("data-bz-off") || "")
            .split(",").filter(Boolean);
          let html = "";
          for (let j = 0; j < values.length; j++) {
            const v = values[j];
            const dead = off || barred.indexOf(v) !== -1;
            html +=
              '<button type="button" data-bz-v="' + v + '"' +
              ' class="' + cellCls + '"' +
              ' aria-label="' + label + " " + v + '"' +
              (dead ? " disabled" : "") + ">" + v + "</button>";
          }
          col.insertAdjacentHTML("beforeend", html);
        }

        // A single listener per column. The flag lives on the NODE, and
        // it is correct here: if idiomorph keeps the node, the listener
        // survives with it; if it replaces it, the new one has no flag
        // and re-wires. The flag and the listener always agree — which
        // is very exactly what ``bz-class``'s tracking was missing (cf.
        // traps.md).
        if (!col._bzTimeWired) {
          col._bzTimeWired = true;
          col.addEventListener("click", function (ev) {
            const cell = ev.target.closest("[data-bz-v]");
            if (!cell || cell.disabled) return;
            pick(part, cell.getAttribute("data-bz-v"));
          });
        }

        // The selection, at every pass of the effect.
        const courant = parts[part];
        const cells = col.querySelectorAll("[data-bz-v]");
        for (let j = 0; j < cells.length; j++) {
          const c = cells[j];
          if (c.getAttribute("data-bz-v") === courant) {
            c.setAttribute("data-selected", "true");
          } else {
            c.removeAttribute("data-selected");
          }
        }
      }
    },
  };
})();
