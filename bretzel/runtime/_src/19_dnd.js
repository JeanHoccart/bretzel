/* 19_dnd.js — the node-DnD gesture shared by `dropzone` / `draggable`.
 *
 * ⚠️ **Distinct from the "drag" of the repository's two other
 * families**, and §6 of the roadmap insists because confusing them
 * costs:
 *   - `12_slider.js`      = pointer-drag (pointer → continuous value);
 *   - `08_file_upload.js` = native HTML5 DnD (OS files, DataTransfer).
 * This is the third: **moving a node** from one position to another.
 *
 * ── Why Pointer Events and not the HTML5 `draggable` API ─────────────
 * The HTML5 API simply does not fire `dragstart` on mobile. A framing
 * decision, settled: Pointer Events, like the slider.
 *
 * ── Why delegation to the document ───────────────────────────────────
 * One listener per zone would have to re-wire after every morph, and a
 * `bz-init` that runs again double-binds (the bridge's rescan disposes
 * and re-binds the directives). A single listener on the document,
 * which finds its target through `closest()`, is **insensitive to the
 * morph** and keeps no state on the nodes — the constraint traps.md
 * § "bz-class lost after a morph" made non-negotiable.
 *
 * ── Why we move the REAL node, with no clone ─────────────────────────
 * The reordering is applied to the DOM during the gesture. So:
 *   1. the preview is free — no ghost to position, no offset to compute
 *      for the neighbours, the browser reflows by itself;
 *   2. at the drop, **the DOM's order IS the result** — we read the
 *      indices instead of computing them, so the preview cannot lie
 *      about what leaves for the server;
 *   3. it is already the optimistic path. The server re-renders,
 *      idiomorph re-pairs by `bz-id` and the moved node is REUSED, not
 *      recreated — measured, and gated by
 *      `tests/runtime_js/test_morph_preserves_reordered_nodes.py`.
 *
 * ── A refusal's snap-back needs code, contrary to what was written
 *    here ──────────────────────────────────────────────────────────────
 * This line long said "a server refusal = no mutation = the morph puts
 * the item back. No dedicated code here." That was FALSE, and the gate
 * claiming to prove it was vacuous: the playground's handler increments
 * a refusal counter, so its state changed, so the zone re-rendered —
 * the snap-back did not come from the refusal but from the counter. A
 * handler that refuses by mutating NOTHING — the case `Move` documents
 * as THE way to refuse, and `examples/crm`'s — makes no zone re-render:
 * the server answers zero bytes and the card stays where the finger let
 * it go. Measured on 2026-09-09 on `examples/kanban`: a
 * work-in-progress limit refused on the server, and the screen showed
 * four cards in a column that accepts three.
 *
 * Hence the WITNESS below. It costs the normal case nothing and asks
 * nothing of the app's author: the attribute is set on the item at drop
 * time, the server never renders it, so idiomorph erases it as soon as
 * it re-pairs the node. If it is still there when the request comes
 * back, nobody answered for that item — and the gesture is undone.
 *
 * ── The geometry is READ, never configured ───────────────────────────
 * The axis (a vertical or horizontal list) is inferred from the real
 * position of two items, as the Carousel infers its stride. No
 * breakpoint, no `orientation=` prop to keep in sync with the CSS.
 *
 * DOM contract expected from Python (no new `bz-*` directive):
 *   zone : data-bz-dropzone="<name>"  data-bz-accepts="a,b"  [data-bz-locked]
 *          + a hidden carrier [data-bz-move-carrier] holding the hx-post
 *   item : data-bz-draggable  data-bz-key="…"  [data-bz-group] [data-bz-disabled]
 *          [data-bz-handle]  → when present, only [data-bz-drag-handle] grabs
 */
(function () {
  "use strict";
  const $bz = (window.$bz = window.$bz || {});

  //: Mouse/stylus: the distance before the gesture becomes a drag. It is
  //: this threshold that PRESERVES THE CLICK — without it, every click
  //: on a card would start a move.
  const MOUSE_THRESHOLD_PX = 5;
  //: Touch: how long you press before grabbing.
  const TOUCH_HOLD_MS = 250;
  //: …and the distance beyond which we give up before the delay ends.
  //: It is what PRESERVES THE SCROLL: a finger running down a list must
  //: not carry off the card it brushed.
  const TOUCH_TOLERANCE_PX = 8;

  //: The witness of a drop awaiting an answer. Set on the item, erased
  //: by the morph — the server never renders this attribute, so
  //: idiomorph removes it when it re-pairs the node. It is the only
  //: measurement possible from the client of "did the answer touch this
  //: item", and it asks for no new protocol.
  const PENDING_ATTR = "data-bz-drop-pending";

  const ZONE_SEL = "[data-bz-dropzone]";
  const ITEM_SEL = "[data-bz-draggable]";
  const HANDLE_SEL = "[data-bz-drag-handle]";
  const CARRIER_SEL = "[data-bz-move-carrier]";
  //: Set on the ZONE while an overwrite is hovered. The theme hooks onto
  //: it; nothing else reads it.
  const REPLACE_ATTR = "data-bz-drop-replace";

  //: One gesture at a time — it is a physical truth of the pointer, not
  //: an implementation shortcut. `armed` = finger down, drag not decided
  //: yet; `active` = drag in progress.
  let armed = null;
  let active = null;

  // ── Reading the DOM contract ─────────────────────────────────────────

  function zoneOf(el) {
    return el ? el.closest(ZONE_SEL) : null;
  }

  function itemsOf(zone) {
    // The items of a NESTED zone are not ours.
    return Array.prototype.filter.call(
      zone.querySelectorAll(ITEM_SEL),
      function (it) { return zoneOf(it) === zone; }
    );
  }

  function indexOf(item) {
    const zone = zoneOf(item);
    return zone ? itemsOf(zone).indexOf(item) : -1;
  }

  /* Where to insert, when there is no item to aim at.
     ⚠️ **An item is NOT necessarily a direct child of its zone.** A
     dropzone arranges nothing — it receives — so the caller stacks its
     items with the container they already use (`ui.vstack`, `ui.grid`).
     Inserting into the ZONE would put the card beside that stack, and
     `insertBefore` flatly raises when the target is not its child.
     That is the bug the bench page revealed and that the gesture tests'
     synthetic DOM could not produce. */
  function itemsContainer(zone) {
    const first = itemsOf(zone)[0];
    if (first) return first.parentNode;
    /* An EMPTY zone. Falling back on the zone itself was a bug, and the
       comment that lived here said why it went unnoticed: "the next
       server render will put the card back in the stack". It does not.
       The moved node keeps its `bz-id`, which encodes its path in the
       tree; that path has changed, so idiomorph does not re-pair it and
       the card STAYS where it was dropped — that is to say a direct
       child of the zone, OUTSIDE the container the app rendered.

       Reproduced on 2026-09-13 on `/dnd`, by a drag that HESITATES: you
       take the item out of its zone, change your mind, come back. The
       original zone is then empty, the item is re-appended at its root,
       and it shows beside its box instead of inside it. A hesitant
       gesture is the ordinary gesture.

       What we do instead: the app rendered its items in a container of
       its own (a `vstack`, a grid) — it is still there, empty. We walk
       down the chain of SINGLE children to find it again. The hidden
       carrier of the `hx-post` does not count: it is always present and
       would skew the tally. */
    let node = zone;
    for (;;) {
      const kids = Array.prototype.filter.call(
        node.children,
        function (k) { return !k.matches(CARRIER_SEL); }
      );
      if (kids.length !== 1) return node;
      node = kids[0];
    }
  }

  /* A zone that holds only ONE element. The default, `many`, is not
     written: the absence of the attribute is enough. */
  function holdsOne(zone) {
    return zone.getAttribute("data-bz-holds") === "one";
  }

  /* Mark the target of an OVERWRITE, and mark only it. */
  function markReplace(zone) {
    if (active.replaceZone === zone) return;
    clearReplace();
    active.replaceZone = zone;
    if (zone) zone.setAttribute(REPLACE_ATTR, "true");
  }

  function clearReplace() {
    if (active && active.replaceZone) {
      active.replaceZone.removeAttribute(REPLACE_ATTR);
      active.replaceZone = null;
    }
  }

  function groupOf(item) {
    return item.getAttribute("data-bz-group") || "";
  }

  /* Does the zone accept this group?
     ⚠️ An absent `data-bz-accepts` does NOT mean "accepts anything". A
     zone with no declaration receives **only its own items**: two
     independent lists on the same page must not swap cards because
     nobody declared anything. It is Sortable.js's default (an anonymous
     group is unique per instance there), and the playground's bench
     proved it necessary — without it, grabbing a kanban card lit up the
     page's five unrelated zones.
     Receiving from elsewhere is therefore an OPT-IN, not a default. */
  function accepts(zone, group, originZone) {
    //: ⚠️ `accepts` governs ENTRY FROM ELSEWHERE, not internal
    //: reordering. Reordering within its own zone is not entering it:
    //: the item is already there, and nobody declared anything about
    //: that. Consulting `accepts` here froze a whole list as soon as the
    //: items' `group=` did not answer its `accepts=` — measured:
    //: `accepts=["card"]` on items with no group made the zone totally
    //: inert, in silence. Sortable.js separates `put` (receive) from
    //: `sort` (reorder) for the same reason.
    if (zone === originZone) return true;
    const raw = (zone.getAttribute("data-bz-accepts") || "").trim();
    //: Absent OR empty: the zone receives nothing from elsewhere. Both
    //: are equivalent now the internal case is out — so `accepts=[]`
    //: really seals what it announces, which was not the case when the
    //: empty list was confused with "not declared".
    if (!raw) return false;
    return raw.split(",").some(function (g) { return g.trim() === group; });
  }

  /* §6's two doors, kept SEPARATE: `accepts` decides entry, `locked`
     decides exit. A wastebasket is a zone that accepts a group and from
     which nothing comes out. */
  function canLeave(zone) {
    return !zone.hasAttribute("data-bz-locked");
  }

  function canEnter(zone, group, originZone) {
    if (!accepts(zone, group, originZone)) return false;
    if (zone !== originZone && !canLeave(originZone)) return false;
    return true;
  }

  // ── Measured geometry ────────────────────────────────────────────────

  /* The dominant axis, inferred from two real items. A list whose items
     mostly spread in X is horizontal — the CSS has already decided, we
     only read it. Fallback to the vertical axis (the common case) when
     there are not two items to compare. */
  function axisOf(zone) {
    //: The dragged item is NOT excluded, and that is the 2026-08-10
    //: correction: we move the real node, so it is still in the flow and
    //: its box is as valid as any other's. Excluding it left a list of
    //: TWO items with a single reference point, so a fallback to the
    //: vertical axis — measured: a horizontal row of two cards was
    //: impossible to reorder, the comparison being made on a Y both
    //: share.
    const items = itemsOf(zone);
    if (items.length >= 2) {
      const a = items[0].getBoundingClientRect();
      const b = items[1].getBoundingClientRect();
      if (a.left !== b.left || a.top !== b.top) {
        return Math.abs(b.left - a.left) > Math.abs(b.top - a.top) ? "x" : "y";
      }
    }
    //: A single item (or two overlapping): nothing left to measure
    //: between two boxes, so we ask the CSS what it decided. Always
    //: READ, never configured — no `orientation=` prop to keep in sync.
    const box = itemsContainer(zone);
    const dir = (getComputedStyle(box).flexDirection || "");
    return dir.indexOf("row") === 0 ? "x" : "y";
  }

  /* Should we insert AFTER the hovered item? We compare the pointer to
     the middle of its box, along the list's axis. */
  function isPastMiddle(rect, x, y, axis) {
    return axis === "x"
      ? x - rect.left > rect.width / 2
      : y - rect.top > rect.height / 2;
  }

  // ── Le geste ─────────────────────────────────────────────────────────

  function disarm() {
    if (armed && armed.timer) clearTimeout(armed.timer);
    armed = null;
  }

  function onPointerDown(e) {
    if (active || armed) return;
    //: The main button only: a right click opens a menu, it does not
    //: grab.
    if (e.pointerType === "mouse" && e.button !== 0) return;

    const item = e.target.closest ? e.target.closest(ITEM_SEL) : null;
    if (!item || item.hasAttribute("data-bz-disabled")) return;
    const zone = zoneOf(item);
    if (!zone) return;

    //: `handle=True`: the whole card stays inert, only the handle
    //: grabs. It is an opt-in RESTRICTION, not the default gesture.
    if (item.hasAttribute("data-bz-handle")) {
      const handle = e.target.closest(HANDLE_SEL);
      if (!handle || !item.contains(handle)) return;
    }

    armed = {
      item: item,
      zone: zone,
      pointerId: e.pointerId,
      touch: e.pointerType === "touch",
      x: e.clientX,
      y: e.clientY,
      timer: null,
    };

    if (armed.touch) {
      //: Touch: it is TIME that decides, not distance.
      armed.timer = setTimeout(function () {
        if (armed) begin();
      }, TOUCH_HOLD_MS);
    }
  }

  function begin() {
    if (!armed) return;
    const a = armed;
    if (a.timer) clearTimeout(a.timer);
    armed = null;

    active = {
      item: a.item,
      originZone: a.zone,
      originIndex: indexOf(a.item),
      //: Enough to undo the gesture exactly — `insertBefore(item, null)`
      //: is an append, so an item taken from the last position restores
      //: itself with no special case.
      originParent: a.item.parentNode,
      originNext: a.item.nextSibling,
      group: groupOf(a.item),
      pointerId: a.pointerId,
    };
    //: An attribute, not a class: the theme hooks onto it with
    //: `data-[bz-dragging]:…`, and a morph that rewrites `class=` cannot
    //: erase it by accident.
    active.item.setAttribute("data-bz-dragging", "true");
    /* ⚠️ THE AXIS — a HOOK for the theme, not a runtime setting.
       The shipped default does nothing with it: a card in flight keeps
       its size (cf. `draggable`'s `dragging` slot). It is published so
       that an app preferring a PLACEHOLDER can get one by overriding
       that slot, with no prop and without touching the gesture.

       Why the axis and not a boolean: "smaller" does not mean the same
       thing in both directions. A vertical list wants a full-width bar,
       a horizontal row wants a full-height column. CSS cannot measure a
       list; `axisOf` already infers it from the real position of two
       items.

       Why not on a `holds="one"` zone: it inserts nothing. Its card does
       not leave a space to fill, it leaves an EMPTY place — and a theme
       that reduced an occupant to a bar in its chair would tell
       something false. */
    if (!holdsOne(a.zone)) {
      active.item.setAttribute("data-bz-drag-axis", axisOf(a.zone));
    }
    makePreview(a.x, a.y);
    markValidZones();
  }

  /* The preview that follows the pointer.
     Without it, only the LIST moves: the neighbours part, but nothing is
     "in hand" and the gesture reads as a cursor wandering about. It is
     the clone that flies and the original that stays — Sortable.js's and
     dnd-kit's DragOverlay's shape — rather than translating the real
     node, which is already reordered in the flow and would therefore
     move twice.

     ⚠️ **The clone must be ANONYMOUS.** We remove its `id`, `bz-id` and
     `data-bz-draggable`, on it AND on all its descendants: a duplicate
     id would make idiomorph pair anything at the next morph, and a
     duplicate `data-bz-draggable` would skew the indices `itemsOf`
     reads. The rest of its look is a plain clone of what the user was
     already looking at. */
  function makePreview(x, y) {
    const src = active.item;
    const rect = src.getBoundingClientRect();
    const node = src.cloneNode(true);

    node.removeAttribute("data-bz-dragging");
    node.removeAttribute("data-bz-drag-axis");
    const strip = ["id", "bz-id", "data-bz-draggable", "data-bz-key",
                   "data-bz-drag-handle", "data-bz-move-carrier",
                   "data-bz-drag-axis"];
    const scrub = function (el) {
      for (let i = 0; i < strip.length; i++) el.removeAttribute(strip[i]);
    };
    scrub(node);
    Array.prototype.forEach.call(node.querySelectorAll("*"), scrub);

    node.classList.add("bz-drag-preview");
    //: A frozen width: out of the flow, a block no longer has a parent
    //: to inherit from, and the preview would collapse onto its
    //: content.
    node.style.width = rect.width + "px";
    node.style.height = rect.height + "px";
    node.style.left = rect.left + "px";
    node.style.top = rect.top + "px";

    //: The gap between the grabbed point and the card's corner. It is
    //: what stops the card "jumping" under the cursor at the moment you
    //: grab it — it stays held where you took it.
    active.grabDX = x - rect.left;
    active.grabDY = y - rect.top;
    active.preview = node;
    document.body.appendChild(node);
  }

  function movePreview(x, y) {
    if (!active.preview) return;
    active.preview.style.left = (x - active.grabDX) + "px";
    active.preview.style.top = (y - active.grabDY) + "px";
  }

  function dropPreview() {
    if (active && active.preview && active.preview.parentNode) {
      active.preview.parentNode.removeChild(active.preview);
    }
  }

  /* Requirement 1 of the framing: show WHERE the item can land, during
     the gesture. Gated on an attribute set by the gesture, never on
     `:hover` — a hover does not exist for a finger, and that is this
     project's reference pointer. */
  function markValidZones() {
    Array.prototype.forEach.call(
      document.querySelectorAll(ZONE_SEL),
      function (z) {
        if (canEnter(z, active.group, active.originZone)) {
          z.setAttribute("data-bz-drop-ok", "true");
        }
      }
    );
  }

  function clearValidZones() {
    Array.prototype.forEach.call(
      document.querySelectorAll("[data-bz-drop-ok]"),
      function (z) { z.removeAttribute("data-bz-drop-ok"); }
    );
  }

  function onPointerMove(e) {
    if (armed && e.pointerId === armed.pointerId) {
      const dx = Math.abs(e.clientX - armed.x);
      const dy = Math.abs(e.clientY - armed.y);
      if (armed.touch) {
        //: The finger ran off before the delay ended: it was a scroll.
        if (Math.max(dx, dy) > TOUCH_TOLERANCE_PX) disarm();
      } else if (Math.max(dx, dy) > MOUSE_THRESHOLD_PX) {
        begin();
      }
      return;
    }
    if (!active || e.pointerId !== active.pointerId) return;

    //: During a touch drag, the gesture is ours: without this the page
    //: scrolls under the card.
    if (e.cancelable) e.preventDefault();
    //: The preview first: it must follow the finger even when the
    //: pointer hovers a zone that refuses, otherwise the card freezes
    //: and the gesture looks broken when it is simply refused.
    movePreview(e.clientX, e.clientY);
    hoverTo(e.clientX, e.clientY);
  }

  /* The core: put the node where the pointer says it is going. */
  function hoverTo(x, y) {
    const under = document.elementFromPoint(x, y);
    if (!under) {
      if (active.preview) active.preview.style.visibility = "";
      return;
    }
    const overZone = zoneOf(under);
    if (!overZone) {
      if (active.preview) active.preview.style.visibility = "";
      return;
    }
    //: A trash zone is a terminal action, not a destination to inspect.
    //: The source card is still temporarily reparented there so `finish()`
    //: can report the target, but showing its floating clone over the bin
    //: makes it read as a second card.  Hide that clone while the pointer is
    //: above any locked zone; reveal it immediately when it leaves again.
    if (active.preview) {
      active.preview.style.visibility = overZone.hasAttribute("data-bz-locked")
        ? "hidden" : "";
    }
    if (!canEnter(overZone, active.group, active.originZone)) return;

    /* ⚠️ OVERWRITE. A zone that holds only one element and already
       carries one must receive NOTHING during the gesture: sliding the
       node in would make it contain two occupants — what the user sees
       as "the item takes up an enormous amount of room". We mark it, we
       do not fill it. The drop will go to the handler all the same, and
       the handler decides (swap, refuse): it is the server that
       arbitrates, here we only announce honestly what is going to
       happen. */
    if (holdsOne(overZone) && overZone !== zoneOf(active.item)
        && itemsOf(overZone).length > 0) {
      markReplace(overZone);
      return;
    }
    clearReplace();

    const overItem = under.closest(ITEM_SEL);
    if (overItem && overItem !== active.item && zoneOf(overItem) === overZone) {
      const rect = overItem.getBoundingClientRect();
      const axis = axisOf(overZone);
      const after = isPastMiddle(rect, x, y, axis);
      //: Relative to the TARGET'S PARENT, never to the zone — cf.
      //: `itemsContainer`. The items can live at any depth under the
      //: zone.
      overItem.parentNode.insertBefore(
        active.item, after ? overItem.nextSibling : overItem
      );
      return;
    }
    //: Hovering the zone outside any item — typically an empty column
    //: or the space below the last item. We only append if the item is
    //: not already here, otherwise every pointermove would throw it back
    //: to the end.
    if (!overItem && zoneOf(active.item) !== overZone) {
      itemsContainer(overZone).appendChild(active.item);
    }
  }

  function onPointerUp(e) {
    if (armed && e.pointerId === armed.pointerId) return disarm();
    if (!active || e.pointerId !== active.pointerId) return;
    finish();
  }

  function onPointerCancel(e) {
    if (armed && e.pointerId === armed.pointerId) return disarm();
    if (active && e.pointerId === active.pointerId) cancel();
  }

  function onKeyDown(e) {
    if (e.key === "Escape") {
      if (armed) disarm();
      else if (active) cancel();
    }
  }

  function cleanup() {
    dropPreview();
    if (active) {
      clearReplace();
      active.item.removeAttribute("data-bz-dragging");
      active.item.removeAttribute("data-bz-drag-axis");
    }
    clearValidZones();
    active = null;
  }

  /* Cancel = put the node back exactly where it came from. Used by
     Escape and by `pointercancel` — NEVER by a server refusal, which
     goes through the morph (cf. this file's header). */
  function cancel() {
    if (!active) return;
    active.originParent.insertBefore(active.item, active.originNext);
    cleanup();
  }

  /* Undo the drop if the answer did not confirm it.
     ⚠️ Two frames of waiting, not one: `htmx:afterRequest` is the only
     reliable disarm (htmx emits it on 4xx, network errors and aborts
     too), but the swap and the rescan around it land on the following
     frames. Checking straight away would read the witness before the
     morph had a chance to erase it, and EVERY drop would be undone. */
  function armSnapBack(item, parent, next, carrier) {
    const itemKey = item.getAttribute("data-bz-key") || "";
    const destination = zoneOf(item);
    const destinationName = destination
      ? destination.getAttribute("data-bz-dropzone") || ""
      : "";
    item.setAttribute(PENDING_ATTR, "");
    function settle(e) {
      if (e.detail && e.detail.elt && e.detail.elt !== carrier) return;
      document.body.removeEventListener("htmx:afterRequest", settle);
      requestAnimationFrame(function () {
        requestAnimationFrame(function () {
          if (!item.hasAttribute(PENDING_ATTR)) return;
          item.removeAttribute(PENDING_ATTR);
          //: The server may have removed the item (archiving): there
          //: is then nothing to put back, and its old parent may itself
          //: have disappeared.
          if (!item.isConnected || !parent.isConnected) return;
          parent.insertBefore(
            item, next && next.parentNode === parent ? next : null
          );
        });
        requestAnimationFrame(function () {
          restoreSequentialFocus(itemKey, destinationName);
        });
      });
    }
    document.body.addEventListener("htmx:afterRequest", settle);
  }

  /* Put the starting point of sequential navigation back after the
     morph. A move between zones changes the card's `bz-id`: idiomorph
     then recreates its node and Chromium puts the focus back on BODY. In
     that state, the first Tab is swallowed instead of reaching the next
     control. We focus the card the server rendered as a temporary
     anchor; it does not durably enter the tab order. */
  function restoreSequentialFocus(itemKey, zoneName) {
    if (!itemKey || !zoneName) return;
    const zones = document.querySelectorAll(ZONE_SEL);
    let item = null;
    for (let i = 0; i < zones.length && !item; i++) {
      if (zones[i].getAttribute("data-bz-dropzone") !== zoneName) continue;
      const candidates = itemsOf(zones[i]);
      for (let j = 0; j < candidates.length; j++) {
        if (candidates[j].getAttribute("data-bz-key") === itemKey) {
          item = candidates[j];
          break;
        }
      }
    }
    if (!item || !item.isConnected) return;
    const hadTabindex = item.hasAttribute("tabindex");
    if (!hadTabindex) item.setAttribute("tabindex", "-1");
    item.focus({preventScroll: true});
    if (!hadTabindex) {
      item.addEventListener("blur", function removeTemporaryTabindex() {
        item.removeAttribute("tabindex");
      }, {once: true});
    }
  }

  function finish() {
    const a = active;
    //: An overwrite did NOT move the node: the target zone is read from
    //: the mark, not from the position. Its index is 0 — a zone with one
    //: element has no other.
    const remplace = a.replaceZone;
    const toZone = remplace || zoneOf(a.item);
    const toIndex = remplace ? 0 : indexOf(a.item);
    const origin = {parent: a.originParent, next: a.originNext, item: a.item};
    cleanup();
    if (!toZone) return;

    //: Nothing moved → no server round trip. A drag that puts the item
    //: back where it was must not produce a `Move`.
    if (!remplace && toZone === a.originZone && toIndex === a.originIndex) {
      return;
    }

    //: It is the RECEIVING zone that decides — its `on_move` is the
    //: handler, and its carrier holds the hx-post.
    //: ⚠️ Filtered by `zoneOf`, like `itemsOf`: `querySelector` searches
    //: the WHOLE subtree, so a nested dropzone — whose carrier
    //: necessarily precedes the parent's, since it is rendered last —
    //: would capture the parent's drop and POST it to ITS handler.
    const carrier = Array.prototype.find.call(
      toZone.querySelectorAll(CARRIER_SEL),
      function (el) { return zoneOf(el) === toZone; }
    );
    if (!carrier) return;

    carrier.value = JSON.stringify({
      item_key: a.item.getAttribute("data-bz-key") || "",
      from_zone: a.originZone.getAttribute("data-bz-dropzone") || "",
      to_zone: toZone.getAttribute("data-bz-dropzone") || "",
      from_index: a.originIndex,
      to_index: toIndex,
    });
    //: The home-made transport — the JS writes, dispatches, and it is
    //: the carrier's hx-post that leaves. No `fetch` here: the transport
    //: boundary belongs to the bridge (charter, principle 2).
    armSnapBack(origin.item, origin.parent, origin.next, carrier);
    $bz.helpers.emitChange(carrier, "move");
  }

  //: Once the gesture is GRABBED, the finger is ours: it is this
  //: `preventDefault` on the `touchmove` that stops the browser
  //: scrolling under the card.
  //:
  //: It does NOT duplicate `onPointerMove`'s. A `preventDefault` on a
  //: `pointermove` does not cancel a touch scroll — only the
  //: `touchmove` can, and only in a NON-PASSIVE listener. As long as the
  //: CSS set `touch-action: none` the question did not arise: the
  //: browser never scrolled. Since the item leaves `pan-x pan-y`
  //: (finding [27]: without it the finger could no longer scroll a
  //: column of cards), the gesture has to be taken over at the moment
  //: the long press succeeds — and at that precise instant the finger
  //: has not moved, so no scroll is in progress and the takeover is
  //: clean.
  //:
  //: ⚠️ We prevent NOTHING as long as the drag is only `armed`: that is
  //: exactly the "a finger runs down the list and brushes a card" case,
  //: which the 8 px tolerance leaves to the scroll.
  function onTouchMove(e) {
    if (active && e.cancelable) e.preventDefault();
  }

  document.addEventListener("pointerdown", onPointerDown, true);
  //: `passive: false` — `onPointerMove` must be able to
  //: `preventDefault()` to hold the scroll during a MOUSE drag (text
  //: selection, native image drag).
  document.addEventListener("pointermove", onPointerMove, { passive: false });
  document.addEventListener("touchmove", onTouchMove, { passive: false });
  document.addEventListener("pointerup", onPointerUp, true);
  document.addEventListener("pointercancel", onPointerCancel, true);
  document.addEventListener("keydown", onKeyDown, true);

  //: Exposed for the tests and for a future component that would drive
  //: the gesture. The public contract stays the data attributes.
  $bz.dnd = {
    MOUSE_THRESHOLD_PX: MOUSE_THRESHOLD_PX,
    TOUCH_HOLD_MS: TOUCH_HOLD_MS,
    TOUCH_TOLERANCE_PX: TOUCH_TOLERANCE_PX,
    _state: function () { return { armed: armed, active: active }; },
    _axisOf: axisOf,
    _accepts: accepts,
    _canEnter: canEnter,
    _indexOf: indexOf,
  };
})();
