/* time_picker.js — the TimePicker component's shared scope.
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
 * from the store cell, which nothing rewrites (cf. traps.md § "Une
 * valeur de scope calculée doit rester calculable").
 *
 * Why a shared scope rather than inline expressions: a panel with 24
 * hours and 4 minutes is 28 buttons. Writing the pick and the selection
 * test out in full on each would serialise the same algorithm 28 times
 * PER INSTANCE — exactly what Pagination's and Accordion's "config as
 * data" switches avoid.
 */
(function () {
  "use strict";
  const $bz = (window.$bz = window.$bz || {});

  //: The index of the two parts in the tuple ``_parts`` returns.
  const HOUR = 0;
  const MINUTE = 1;
  //: The half day's column — built here, only in twelve hours.
  const PERIOD = 2;

  /* The AM / PM column: a sibling of the minutes', same classes, its
   * own name (``data-bz-period-label``, a framework text). */
  function addPeriodColumn(el) {
    const minutes = el.querySelector('[data-bz-part="' + MINUTE + '"]');
    if (!minutes) return;
    const col = minutes.cloneNode(false);
    col.setAttribute("data-bz-part", String(PERIOD));
    col.setAttribute("data-bz-values", "AM,PM");
    col.setAttribute("data-bz-off", "");
    const name = el.getAttribute("data-bz-period-label") || "";
    col.setAttribute("aria-label", name);
    col.setAttribute("data-bz-cell-label", name);
    const head = minutes.firstElementChild && !minutes.firstElementChild.hasAttribute("data-bz-v")
      ? minutes.firstElementChild.cloneNode(false) : null;
    if (head) { head.innerHTML = "&nbsp;"; col.appendChild(head); }
    minutes.parentNode.appendChild(col);
  }

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
     * Why Python does not render the cells
     * -------------------------------------
     * Each would carry the theme's class string and two directives
     * (``bz-attr:data-selected`` + ``bz-on:click``), and at ``step=1``
     * there are 84 cells: nearly all of the component's weight would be
     * that one class and those directives, repeated identically.
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
      // ── Twelve hours, when the page's language counts so ─────────
      // The column counts as the field does (« 2:30 PM »). The VALUE
      // stays "HH:MM": only the cells change — the
      // hours become 12, 1…11, a third column carries the half day, and
      // a click is turned back into 24 hours before it is picked.
      const twelve = $bz.times.twelve();
      if (twelve && !el.querySelector('[data-bz-part="' + PERIOD + '"]')) {
        addPeriodColumn(el);
      }
      const cols = el.querySelectorAll("[data-bz-part]");
      const h24 = parts[HOUR] === "" ? null : Number(parts[HOUR]);
      const pm = h24 !== null && h24 >= 12;
      const pad = function (n) { return String(n).padStart(2, "0"); };
      // What a cell of the twelve-hour panel stands for, in 24 hours.
      const as24 = function (h12, isPm) { return pad((Number(h12) % 12) + (isPm ? 12 : 0)); };
      const chosen = function (part, v) {
        if (!twelve) return pick(part, v);
        if (part === HOUR) return pick(HOUR, as24(v, pm));
        if (part === PERIOD) {
          const toPm = v === "PM";
          return pick(HOUR, h24 === null ? (toPm ? "12" : "00") : as24(h24 % 12, toPm));
        }
        return pick(part, v);
      };

      for (let i = 0; i < cols.length; i++) {
        const col = cols[i];
        const part = Number(col.getAttribute("data-bz-part"));
        // Escaped: the label is the app's words (``hour_label=``, a
        // translation) and the cells are built as HTML.
        const esc = $bz.helpers.escapeHtml;
        const label = esc(col.getAttribute("data-bz-cell-label") || "");

        if (!col.querySelector("[data-bz-v]")) {
          const values = twelve && part === HOUR
            ? ["12", "1", "2", "3", "4", "5", "6", "7", "8", "9", "10", "11"]
            : (col.getAttribute("data-bz-values") || "").split(",").filter(Boolean);
          const shown = part === PERIOD ? $bz.times.halves() : null;
          const barred = (col.getAttribute("data-bz-off") || "")
            .split(",").filter(Boolean);
          let html = "";
          for (let j = 0; j < values.length; j++) {
            const v = values[j];
            const dead = off || barred.indexOf(v) !== -1;
            const said = esc(shown ? shown[j] : v);
            html +=
              '<button type="button" data-bz-v="' + esc(v) + '"' +
              ' class="' + esc(cellCls) + '"' +
              ' aria-label="' + label + " " + said + '"' +
              (dead ? " disabled" : "") + ">" + said + "</button>";
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
            col._bzTimePick(part, cell.getAttribute("data-bz-v"));
          });
        }
        // Re-pointed at every pass: the half day it converts with is
        // the CURRENT value's.
        col._bzTimePick = chosen;

        // The selection, at every pass of the effect.
        const courant = !twelve || part === MINUTE ? parts[part]
          : h24 === null ? "" : part === HOUR ? String(h24 % 12 || 12) : (pm ? "PM" : "AM");
        const barred = twelve && part === HOUR
          ? (col.getAttribute("data-bz-off") || "").split(",").filter(Boolean) : null;
        const cells = col.querySelectorAll("[data-bz-v]");
        for (let j = 0; j < cells.length; j++) {
          const c = cells[j];
          // min / max are in 24 hours: a twelve-hour cell is out of
          // range in the CURRENT half day, so it is judged at each pass.
          if (barred) c.disabled = off || barred.indexOf(as24(c.getAttribute("data-bz-v"), pm)) !== -1;
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
