/* scheduler.js — dragging a `ui.scheduler` card to another time,
 * pulling its bottom edge to change its end, and tracing a new event on
 * the empty grid (`on_create`).
 *
 * ── Why not `dnd.js` ───────────────────────────────────────────────
 * The node-DnD moves a node from one LIST to another and reports an
 * index. A scheduler drop is a POSITION in a grid — "Thursday at 8h05" —
 * and the length of an event is pulled, not reordered. What is shared is
 * the transport, kept identical on purpose: a hidden carrier holds the
 * `hx-post`, the gesture writes a JSON blob into it and fires its event,
 * and a WITNESS on the card says whether the answer touched it.
 *
 * ── The traps it carries once for all ─────────────────────────────────
 *   1. A ghost left by an earlier gesture never survives into the next:
 *      every ghost is removed when a gesture begins and when it ends.
 *   2. A refusal puts the card back — the server answered without
 *      redrawing it (zero bytes, an error status, an exception).
 *   3. A QUESTION keeps the card where it was dropped. The server that
 *      asks "this one or all of them?" opens a modal dialog and does not
 *      redraw the scheduler; snapping back at that moment would put the
 *      card back under the question. So while a modal dialog is open, the
 *      card waits; when none is open any more and no request is in flight,
 *      an untouched card goes back — cancelled.
 *   4. The click a browser fires at the end of a drag is swallowed for a
 *      MOMENT, not "until the next click": a browser may fire none, and
 *      the next one would be the dialog's button.
 *
 * ── Why delegation to the document ───────────────────────────────────
 * The scheduler is redrawn by morphs; a listener on a card would die
 * with it. One listener per event type, on the document, which finds its
 * target with `closest()` and keeps no state on the nodes.
 *
 * DOM contract expected from Python (`components/data/scheduler`):
 *   root    [data-bz-scheduler] data-bz-grid-start, data-bz-grid-end (minutes),
 *           data-bz-px (pixels per minute), data-bz-snap (minutes), data-bz-gap (px)
 *   column  [data-bz-day="YYYY-MM-DD"]
 *   card    [data-bz-event] data-bz-start, data-bz-duration (minutes),
 *           [data-bz-movable] when it can be dragged
 *   edge    [data-bz-resize] inside a card, when it can be pulled
 *   carrier [data-bz-scheduler-carrier="move"|"resize"|"create"], a root child
 *   tag     [data-bz-scheduler-tag], a root child — the label of the time
 *   draft   [data-bz-scheduler-draft], a root child — the theme's picture of
 *           a new event, copied under a trace
 *
 * ── The trace (`on_create`) ──────────────────────────────────────────
 * A press on a column, NOT on a card, that moves past the threshold
 * draws a draft (on the root, over the column) from the pressed minute
 * to the pointer, snapped. At the
 * release the draft STAYS until the answer — the app redraws with its
 * own provisional item, or answers nothing — then goes. A press that does
 * not move creates nothing: a click on the grid often closes a panel.
 */
(function () {
  "use strict";
  const $bz = (window.$bz = window.$bz || {});

  //: The gesture's rules live ONCE, in `$bz.gesture` (`helpers.js`),
  //: shared with `dnd.js`: the threshold keeps the CLICK
  //: (`on_item_click=`), the touch hold and its tolerance keep the week
  //: SCROLLABLE, the end-of-drag click is swallowed for a moment, and a
  //: dropped card waits while a question is open.
  const G = $bz.gesture;
  const THRESHOLD_PX = G.MOUSE_THRESHOLD_PX;
  const TOUCH_HOLD_MS = G.TOUCH_HOLD_MS;
  const TOUCH_TOLERANCE_PX = G.TOUCH_TOLERANCE_PX;

  //: Set on a dropped card until an answer redraws it. The server never
  //: renders it, so the morph erases it; its survival says nobody did.
  const PENDING_ATTR = "data-bz-reschedule-pending";
  ($bz._witnesses = $bz._witnesses || new Set()).add(PENDING_ATTR);
  const ROOT_SEL = "[data-bz-scheduler]";
  const COLUMN_SEL = "[data-bz-day]";
  let armed = null;
  let active = null;

  // ── Reading the contract ─────────────────────────────────────────────

  function grid(root) {
    return {
      start: +root.getAttribute("data-bz-grid-start"),
      end: +root.getAttribute("data-bz-grid-end"),
      px: +root.getAttribute("data-bz-px"),
      snap: +root.getAttribute("data-bz-snap") || 5,
      gap: +root.getAttribute("data-bz-gap") || 0,
    };
  }

  function child(root, selector) {
    return root.querySelector(":scope > " + selector);
  }

  function carrierOf(root, mode) {
    return child(root, '[data-bz-scheduler-carrier="' + mode + '"]');
  }

  /* The geometry is read ONCE per gesture (and again on a scroll), not
     on every pointermove: a layout read right after the ghost's write
     forced a reflow per move. */
  function measure(a) {
    a.rootBox = a.root.getBoundingClientRect();
    a.columns = Array.prototype.filter.call(
      a.root.querySelectorAll(COLUMN_SEL),
      function (c) { return c.closest(ROOT_SEL) === a.root; }
    ).map(function (c) { return {el: c, box: c.getBoundingClientRect()}; });
    a.tagHeight = a.tag ? a.tag.offsetHeight : 0;
  }

  /* A day column spans the grid's height, so x alone finds it — even
     when the pointer strays above the grid. A month cell needs y too. */
  function columnAt(a, x, y) {
    const hit = a.columns.find(function (c) {
      return x >= c.box.left && x < c.box.right
        && (!a.month || (y >= c.box.top && y < c.box.bottom));
    });
    return hit || null;
  }

  function clamp(v, lo, hi) { return Math.max(lo, Math.min(hi, v)); }

  /* The hour beside a dragged card, by THE clock (``$bz.times.shown``):
   * « 8h05 » in French, « 8:05 AM » in American English. */
  function label(minutes) {
    const pad = function (n) { return String(n).padStart(2, "0"); };
    return $bz.times.shown(pad(Math.floor(minutes / 60)) + ":" + pad(minutes % 60));
  }

  /* "2026-11-10" + 485 → "2026-11-10T08:05", in the page's local time.
     Built on a Date so that 24:00 becomes the next day's 00:00. */
  function iso(day, minutes) {
    const d = new Date(day + "T00:00:00");
    d.setMinutes(minutes);
    const pad = function (n) { return String(n).padStart(2, "0"); };
    return d.getFullYear() + "-" + pad(d.getMonth() + 1) + "-" + pad(d.getDate())
      + "T" + pad(d.getHours()) + ":" + pad(d.getMinutes());
  }

  function listOf(cell) {
    return cell.querySelector("[data-bz-month-list]") || cell;
  }

  function removeGhosts() {
    document.querySelectorAll("[data-bz-ghost]").forEach(function (g) { g.remove(); });
  }

  function removeDrafts() {
    document.querySelectorAll("[data-bz-draft]").forEach(function (d) { d.remove(); });
  }

  // ── The gesture ──────────────────────────────────────────────────────

  function onPointerDown(e) {
    if (active || armed) return;
    if (e.pointerType === "mouse" && e.button !== 0) return;
    if (!e.target.closest) return;
    const edge = e.target.closest("[data-bz-resize]");
    const card = edge ? edge.closest("[data-bz-event]") : e.target.closest("[data-bz-movable]");
    if (!card && !e.target.closest("[data-bz-event]")) return armCreate(e);
    if (!card || card.hasAttribute(PENDING_ATTR)) return;
    const root = card.closest(ROOT_SEL);
    const column = card.closest(COLUMN_SEL);
    const mode = edge ? "resize" : "move";
    if (!root || !column || !carrierOf(root, mode)) return;
    armed = {
      card: card, root: root, column: column, mode: mode,
      pointerId: e.pointerId, touch: e.pointerType === "touch",
      x: e.clientX, y: e.clientY, timer: null,
    };
    if (armed.touch) {
      armed.timer = setTimeout(function () { if (armed) begin(armed.x, armed.y); },
                               TOUCH_HOLD_MS);
    }
  }

  /* A press on the empty grid of a scheduler that creates. */
  function armCreate(e) {
    const column = e.target.closest(COLUMN_SEL);
    const root = column && column.closest(ROOT_SEL);
    if (!root || root.getAttribute("data-bz-view") === "month" || !carrierOf(root, "create")) {
      return;
    }
    armed = {
      card: null, root: root, column: column, mode: "create",
      pointerId: e.pointerId, touch: e.pointerType === "touch",
      x: e.clientX, y: e.clientY, timer: null,
    };
    if (armed.touch) {
      armed.timer = setTimeout(function () { if (armed) begin(armed.x, armed.y); },
                               TOUCH_HOLD_MS);
    }
  }

  function disarm() {
    if (armed && armed.timer) clearTimeout(armed.timer);
    armed = null;
  }

  function begin(x, y) {
    const a = armed;
    disarm();
    removeGhosts();
    removeDrafts();
    if (a.mode === "create") return beginCreate(a, x, y);
    const card = a.card;
    const box = card.getBoundingClientRect();
    const ghost = card.cloneNode(true);
    //: The copy carries no identity and no wiring: it is a picture.
    [ghost].concat(Array.prototype.slice.call(ghost.querySelectorAll("*"))).forEach(function (el) {
      Array.prototype.slice.call(el.attributes).forEach(function (attr) {
        const n = attr.name;
        if (n === "id" || n === "tabindex" || n === "role" || n === "aria-label"
            || n.indexOf("hx-") === 0 || n.indexOf("bz-") === 0 || n === "data-bz-sig"
            || n === "data-bz-movable" || n === "data-bz-event") {
          el.removeAttribute(n);
        }
      });
    });
    ghost.setAttribute("data-bz-ghost", "");
    ghost.setAttribute("aria-hidden", "true");
    card.setAttribute("data-bz-dragging", "");
    const tag = child(a.root, "[data-bz-scheduler-tag]");
    if (tag) tag.hidden = false;
    active = {
      card: card, root: a.root, mode: a.mode, pointerId: a.pointerId,
      grid: grid(a.root), ghost: ghost, tag: tag,
      grab: a.y - box.top,
      origin: {
        column: a.column,
        parent: card.parentNode,
        next: card.nextSibling,
        style: card.getAttribute("style") || "",
        start: +card.getAttribute("data-bz-start"),
        duration: +card.getAttribute("data-bz-duration"),
      },
      column: a.column, start: 0, end: 0, x: x, y: y,
      //: A month has no hours: the chip changes day, keeps its time, and
      //: sits in the cell's list rather than at a height.
      month: a.root.getAttribute("data-bz-view") === "month",
    };
    if (active.month && tag) tag.hidden = true;
    measure(active);
    update(x, y);
  }

  function beginCreate(a, x, y) {
    const template = child(a.root, "[data-bz-scheduler-draft]");
    if (!template) return;
    const draft = template.cloneNode(true);
    draft.removeAttribute("data-bz-scheduler-draft");
    draft.removeAttribute("hidden");
    draft.setAttribute("data-bz-draft", "");
    //: ``data-bz-row``: what the runtime inserted itself, which the
    //: bridge's position patches skip when they check a level's shape
    //: (``bridge.js``, ``applyPositionPatches``). Without it the answer
    //: that redraws the scheduler is refused, and the new event never
    //: shows.
    draft.setAttribute("data-bz-row", "");
    const tag = child(a.root, "[data-bz-scheduler-tag]");
    if (tag) tag.hidden = false;
    active = {
      card: null, root: a.root, mode: "create", pointerId: a.pointerId,
      grid: grid(a.root), ghost: draft, tag: tag,
      column: a.column, start: 0, end: 0, x: x, y: y, month: false,
      origin: {column: a.column, start: 0, duration: 0},
    };
    measure(active);
    const g = active.grid;
    const here = active.columns.find(function (c) { return c.el === a.column; });
    //: The pressed minute, floored to the snap: the trace's anchor.
    active.origin.start = clamp(
      Math.floor((g.start + (a.y - here.box.top) / g.px) / g.snap) * g.snap,
      g.start, g.end - g.snap);
    //: On the root, over the column: the draft outlives the gesture, and
    //: the answer redraws the column under it.
    a.root.appendChild(draft);
    update(x, y);
  }

  function showTag(a, here, start, end) {
    if (!a.tag) return;
    const g = a.grid;
    //: Placed from the computed top, never read back from the ghost.
    a.tag.textContent = label(start) + " – " + label(end);
    a.tag.style.left = (here.box.left - a.rootBox.left + g.gap) + "px";
    a.tag.style.top = (here.box.top - a.rootBox.top + (start - g.start) * g.px
                       - a.tagHeight - 4) + "px";
  }

  function update(x, y) {
    const a = active;
    const g = a.grid;
    const snap = function (m) { return Math.round(m / g.snap) * g.snap; };
    a.x = x;
    a.y = y;
    if (a.mode === "create") {
      //: The trace stays in its column; it runs from the anchor to the
      //: pointer, downwards or upwards, one snap at least.
      const col = a.columns.find(function (c) { return c.el === a.column; });
      const at = clamp(g.start + (y - col.box.top) / g.px, g.start, g.end);
      const anchor = a.origin.start;
      let start = anchor;
      let end = Math.max(anchor + g.snap, Math.ceil(at / g.snap) * g.snap);
      if (at < anchor) {
        start = Math.floor(at / g.snap) * g.snap;
        end = anchor + g.snap;
      }
      a.start = clamp(start, g.start, g.end - g.snap);
      a.end = clamp(end, a.start + g.snap, g.end);
      const d = a.ghost.style;
      d.left = (col.box.left - a.rootBox.left + g.gap) + "px";
      d.width = (col.box.width - 2 * g.gap) + "px";
      d.top = Math.round(col.box.top - a.rootBox.top + (a.start - g.start) * g.px + g.gap / 2) + "px";
      d.height = Math.round((a.end - a.start) * g.px - g.gap) + "px";
      showTag(a, col, a.start, a.end);
      return;
    }
    const here = (a.mode === "move" && columnAt(a, x, y))
      || a.columns.find(function (c) { return c.el === a.column; });
    if (a.month) {
      a.column = here.el;
      a.start = a.origin.start;
      a.end = a.origin.start + a.origin.duration;
      const list = listOf(here.el);
      if (a.ghost.parentNode !== list) list.appendChild(a.ghost);
      return;
    }
    let start = a.origin.start;
    let end = start + a.origin.duration;
    if (a.mode === "move") {
      const top = y - here.box.top - a.grab;
      start = clamp(snap(g.start + top / g.px), g.start, g.end - a.origin.duration);
      end = start + a.origin.duration;
    } else {
      end = clamp(snap(g.start + (y - here.box.top) / g.px), start + g.snap, g.end);
    }
    a.column = here.el;
    a.start = start;
    a.end = end;
    if (a.ghost.parentNode !== here.el) here.el.appendChild(a.ghost);
    place(a.ghost, a, start, end, a.mode === "move");
    showTag(a, here, start, end);
  }

  /* Pose a card at [start, end). A moved card loses its lane: until the
     server places it, it takes the column's whole width. */
  function place(el, a, start, end, wholeWidth) {
    const g = a.grid;
    el.style.top = Math.round((start - g.start) * g.px + g.gap / 2) + "px";
    el.style.height = Math.round((end - start) * g.px - g.gap) + "px";
    if (wholeWidth) {
      el.style.insetInlineStart = g.gap + "px";
      el.style.width = "calc(100% - " + 2 * g.gap + "px)";
    }
  }

  function cleanup() {
    removeGhosts();
    if (active) {
      if (active.card) active.card.removeAttribute("data-bz-dragging");
      if (active.tag) active.tag.hidden = true;
    }
    active = null;
  }

  function finish() {
    const a = active;
    cleanup();
    G.swallowClick();
    if (a.mode === "create") return finishCreate(a);
    const day = a.column.getAttribute("data-bz-day");
    const unchanged = a.column === a.origin.column && a.start === a.origin.start
      && a.end === a.origin.start + a.origin.duration;
    if (unchanged) return;
    const carrier = carrierOf(a.root, a.mode);
    if (!carrier) return;

    //: Optimistic: the card goes where it was dropped, at once.
    const card = a.card;
    const host = a.month ? listOf(a.column) : a.column;
    if (card.parentNode !== host) host.appendChild(card);
    if (!a.month) place(card, a, a.start, a.end, a.mode === "move");
    card.setAttribute("data-bz-start", String(a.start));
    card.setAttribute("data-bz-duration", String(a.end - a.start));

    const told = {
      event_id: card.getAttribute("data-bz-event") || "",
      start: iso(day, a.start),
      end: iso(day, a.end),
    };
    carrier.value = JSON.stringify(told);
    //: A client expression only: no request, so no answer will ever place
    //: the card — it goes back once the expression has run.
    const server = carrier.hasAttribute("hx-post");
    if (server) armSnapBack(card, a.origin, carrier);
    //: The carrier's `hx-post` leaves — no `fetch` here: the transport
    //: belongs to the bridge (charter, principle 2).
    $bz.helpers.emitChange(carrier, a.mode, told);
    if (!server) afterTwoFrames(function () { restore(card, a.origin); });
  }

  /* The traced slot leaves; the draft waits for the answer, then goes —
     an app that keeps the slot has drawn its own item by then. */
  function finishCreate(a) {
    const draft = a.ghost;
    const carrier = carrierOf(a.root, "create");
    if (!carrier) { draft.remove(); return; }
    const day = a.column.getAttribute("data-bz-day");
    const told = {event_id: "", start: iso(day, a.start), end: iso(day, a.end)};
    carrier.value = JSON.stringify(told);
    const server = carrier.hasAttribute("hx-post");
    function settle(e) {
      if (e.detail && e.detail.elt && e.detail.elt !== carrier) return;
      document.removeEventListener("htmx:afterRequest", settle);
      afterTwoFrames(function () { draft.remove(); });
    }
    if (server) document.addEventListener("htmx:afterRequest", settle);
    $bz.helpers.emitChange(carrier, "create", told);
    if (!server) afterTwoFrames(function () { draft.remove(); });
  }

  // ── The answer ───────────────────────────────────────────────────────

  function restore(card, origin) {
    card.removeAttribute(PENDING_ATTR);
    if (!card.isConnected || !origin.parent.isConnected) return;
    origin.parent.insertBefore(
      card, origin.next && origin.next.parentNode === origin.parent ? origin.next : null
    );
    card.setAttribute("style", origin.style);
    card.setAttribute("data-bz-start", String(origin.start));
    card.setAttribute("data-bz-duration", String(origin.duration));
  }

  //: Two frames after an answer: the swap and the rescan land on the
  //: frames that follow `htmx:afterRequest`.
  const afterTwoFrames = G.afterTwoFrames;

  //: While a question is open the card waits for what can end it: the
  //: dialog's own `close` (bubbled from `show_attrs`' `$dispatch`), or an
  //: answer that may redraw the scheduler (`$bz.gesture.whenAnswered`).
  function armSnapBack(card, origin, carrier) {
    card.setAttribute(PENDING_ATTR, "");
    G.whenAnswered(carrier, {
      untouched: function () {
        return card.hasAttribute(PENDING_ATTR) && card.isConnected;
      },
      undo: function () { restore(card, origin); },
    });
  }

  // ── Listeners ────────────────────────────────────────────────────────

  function onPointerMove(e) {
    if (armed && e.pointerId === armed.pointerId) {
      const far = G.distance(armed, e);
      if (armed.touch) {
        if (far > TOUCH_TOLERANCE_PX) disarm();
      } else if (far >= THRESHOLD_PX) {
        begin(e.clientX, e.clientY);
      }
      return;
    }
    if (!active || e.pointerId !== active.pointerId) return;
    e.preventDefault();
    update(e.clientX, e.clientY);
  }

  function onPointerUp(e) {
    if (armed && e.pointerId === armed.pointerId) return disarm();
    if (active && e.pointerId === active.pointerId) finish();
  }

  function onPointerCancel(e) {
    if (armed && e.pointerId === armed.pointerId) return disarm();
    if (active && e.pointerId === active.pointerId) cleanup();
  }

  function onKeyDown(e) {
    if (e.key !== "Escape") return;
    if (armed) disarm();
    else if (active) cleanup();
  }

  //: A wheel scroll during a drag moves the columns under the pointer.
  function onScroll() {
    if (!active) return;
    measure(active);
    update(active.x, active.y);
  }

  //: Once grabbed, the finger is ours: only a non-passive `touchmove`
  //: can stop the browser scrolling under the card.
  function onTouchMove(e) {
    if (active && e.cancelable) e.preventDefault();
  }

  document.addEventListener("pointerdown", onPointerDown, true);
  document.addEventListener("pointermove", onPointerMove, { passive: false });
  document.addEventListener("touchmove", onTouchMove, { passive: false });
  document.addEventListener("pointerup", onPointerUp, true);
  document.addEventListener("pointercancel", onPointerCancel, true);
  document.addEventListener("keydown", onKeyDown, true);
  document.addEventListener("scroll", onScroll, true);

  //: Exposed for the tests. The public contract stays the data attributes.
  $bz.scheduler = {
    THRESHOLD_PX: THRESHOLD_PX,
    SWALLOW_MS: G.SWALLOW_MS,
    _state: function () { return { armed: armed, active: active, inFlight: G._inFlight() }; },
    _iso: iso,
  };
})();
