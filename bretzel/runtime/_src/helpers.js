/* helpers.js — shared helpers for overlay-class components.
 *
 * Exposed via window.$bz.helpers, consumed by Dialog / Drawer /
 * Popover / Dropdown / Tooltip component code. Trimmed on purpose —
 * we inline the 6 placements we actually use instead of shipping a
 * floating-ui clone (V2's 09_floating.js was 257 LOC ; this is the
 * subset Bretzel components consume).
 *
 *   focusTrap(el)              trap Tab/Shift+Tab inside el ; returns
 *                              dispose (restores the previous focus)
 *   focusIn(id, sels)          focus a component's FOCUS_TARGET (.focus())
 *   blurIn(id)                 blur what has the focus inside it (.blur())
 *   autofocusMounted(els)      autofocus= on entering the page ($bz._scan)
 *   autofocusOpen(panel)       autofocus= when an anchored overlay opens
 *   escapeKey(handler, el?)    Escape, the deepest overlay first ; returns unsubscribe
 *   scrollLock()               body scroll lock w/ scrollbar compensation ;
 *                              returns unlock
 *   floating(anchor, el, opts) position el relative to anchor
 *                              (fixed-position, viewport-aware flip) ;
 *                              returns dispose (stops tracking)
 */
(function () {
  "use strict";
  const $bz = (window.$bz = window.$bz || {});

  // ``directives.js`` owns the list (it loads first).
  const FOCUSABLE = $bz._FOCUSABLE;

  /* A focusable that is not displayed takes no focus, in silence. */
  function shownFocusables(el) {
    return Array.from(el.querySelectorAll(FOCUSABLE)).filter(function (n) {
      return n.offsetParent !== null;
    });
  }

  function focusTrap(el) {
    const previous = document.activeElement;
    function onKeydown(e) {
      if (e.key !== "Tab") return;
      const focusable = shownFocusables(el);
      if (!focusable.length) return;
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (e.shiftKey && document.activeElement === first) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault();
        first.focus();
      }
    }
    el.addEventListener("keydown", onKeydown);
    /* The initial focus RETRIES frame by frame until it takes.
     *
     * It is not superstition: this effect installs itself in the
     * reactive flush that has just turned ``open`` true, so before the
     * computed style flips. Yet ``focus()`` on an element in
     * ``visibility: hidden`` is a **silent no-op** — no error, no
     * return, nothing.
     *
     * A FIXED delay is not enough: the boundary falls right inside the
     * hidden window, and it moves from one run to the next. So we do not
     * wait for a duration, we wait for the RESULT: we try, we check the
     * focus landed, and we retry otherwise.
     *
     * Without that, the trap is installed (``$el._bzTrap`` present) and
     * the focus stays on the trigger. The contract is written in
     * ``dialog.py``: "the first interactive child receives focus".
     *
     * The DOM is RE-QUERIED at every attempt: between the installation
     * and the frame that succeeds, a morph may have replaced the panel's
     * content, and a detached node focuses into the void. */
    let attempts = 0;
    function focusFirst() {
      if (!el.isConnected) return;
      // The field marked ``autofocus=`` first, then the first focusable.
      const first = autofocusIn(el) || shownFocusables(el)[0];
      if (first) {
        giveFocus(first);
        if (el.contains(document.activeElement)) return;
      }
      // ~20 frames (≈ 1/3 s): beyond that, the panel will not open.
      if (++attempts < 20) requestAnimationFrame(focusFirst);
    }
    requestAnimationFrame(focusFirst);
    return function dispose() {
      el.removeEventListener("keydown", onKeydown);
      if (previous && previous.focus) previous.focus();
    };
  }

  /* ── Focus targets: ``autofocus=``, ``.focus()``, ``.blur()`` ──────
   *
   * A component declares WHERE it takes the focus once
   * (``FOCUS_TARGET``, ``components/base/focus.py``): a list of
   * selectors tried in order, each on the element carrying the id then
   * inside it; an empty list is that element. The order is a priority
   * (the checked radio, else the first), which one selector list cannot
   * say. */
  const AUTOFOCUS = "data-bz-autofocus";

  function resolveTarget(el, sels) {
    if (!sels.length) return el;
    for (const s of sels) {
      if (el.matches(s)) return el;
      const hit = el.querySelector(s);
      if (hit) return hit;
    }
    return null;
  }

  function focusTarget(marked) {
    let sels = [];
    try {
      sels = JSON.parse(marked.getAttribute(AUTOFOCUS) || "[]");
    } catch (e) {
      /* a hand-written marker that is not JSON: the element itself */
    }
    return resolveTarget(marked, sels);
  }

  function focusIn(id, sels) {
    const el = document.getElementById(id);
    const target = el && resolveTarget(el, sels);
    if (target) target.focus();
  }

  function blurIn(id) {
    const el = document.getElementById(id);
    const active = document.activeElement;
    if (el && active && el.contains(active)) active.blur();
  }

  // ``focus()`` on an element that is not rendered, or in
  // ``visibility: hidden`` (a closed dialog), is a silent no-op.
  function shown(t) {
    return t.isConnected && t.getClientRects().length > 0 &&
      getComputedStyle(t).visibility !== "hidden";
  }

  /* A focus the PAGE gives (autofocus, a dialog opening), not the person.
   * A component whose focus has a side effect asks before acting: the
   * combobox opens its list when someone Tabs or clicks into it, not
   * when the page puts the cursor there (rule 5: autofocus never opens
   * a panel). ``focus`` fires synchronously inside ``.focus()``. */
  let giving = false;
  function giveFocus(t) {
    giving = true;
    try {
      t.focus();
    } finally {
      giving = false;
    }
  }
  function pageGivesFocus() {
    return giving;
  }

  // The first marked target inside ``box`` (an overlay's panel).
  function autofocusIn(box) {
    const marked = Array.from(box.querySelectorAll("[" + AUTOFOCUS + "]"));
    if (box.hasAttribute(AUTOFOCUS)) marked.unshift(box);
    for (const el of marked) {
      const t = focusTarget(el);
      if (t) return t;
    }
    return null;
  }

  // The user is typing somewhere: a field that just appeared does not
  // take the keyboard from them.
  function typing() {
    const a = document.activeElement;
    if (!a || a === document.body || !a.isConnected) return false;
    if (a.isContentEditable || a.tagName === "TEXTAREA" || a.tagName === "SELECT") return true;
    return a.tagName === "INPUT" &&
      !/^(button|submit|reset|checkbox|radio|range|color|file|image)$/i.test(a.type);
  }

  /* Rule 1 — a field takes the focus when its MARK APPEARS: it enters
   * the page marked, or a redraw marks it (``autofocus=`` False → True).
   * ``seen`` holds the nodes marked at the last scan: a morph keeps the
   * node of a field it merely redraws (paired by id), so a field that
   * STAYS marked is not focused again; one that loses the mark is
   * forgotten, and focused anew when it gets it back — ``autofocus=`` on
   * → off → on, or ``autofocus=(field in error)`` after each refused
   * submit.
   *
   * Every ``$bz._scan`` reports here, and the marks wait in ``pending``
   * for one frame: a ``bz-for`` scans its rows one by one, and the rule
   * "the first in the page wins" needs them all at once.
   *
   * Rule 3 — hidden at mount (closed overlay, inactive tab, folded
   * accordion): the frames retry while the page settles (an effect that
   * shows a panel lands a frame later), then give up. An overlay that
   * opens LATER focuses its own (``autofocusOpen``, ``focusTrap``); a tab
   * revealed later does not steal the focus. */
  const seen = new WeakSet();
  let pending = [];
  let tries = 0;
  let frame = 0;

  function autofocusMounted(els) {
    for (const el of els) {
      if (el.nodeType !== 1) continue;
      if (!el.hasAttribute(AUTOFOCUS)) {
        seen.delete(el);
        continue;
      }
      if (seen.has(el)) continue;
      seen.add(el);
      pending.push(el);
    }
    if (pending.length && !frame) {
      tries = 0;
      frame = requestAnimationFrame(settleAutofocus);
    }
  }

  function settleAutofocus() {
    frame = 0;
    pending = pending.filter(function (el) { return el.isConnected; });
    pending.sort(function (a, b) {
      return a.compareDocumentPosition(b) & Node.DOCUMENT_POSITION_FOLLOWING ? -1 : 1;
    });
    const targets = [];
    for (const el of pending) {
      const t = focusTarget(el);
      if (t && shown(t)) targets.push(t);
    }
    if (!targets.length) {
      if (pending.length && ++tries < 20) frame = requestAnimationFrame(settleAutofocus);
      else pending = [];
      return;
    }
    pending = [];
    if (targets.length > 1) {
      console.warn("bz: " + targets.length + " fields marked autofocus= entered the page " +
        "together; the first takes the focus.", targets);
    }
    const target = targets[0];
    // Rule 2 — never under the hands of someone typing elsewhere.
    if (typing() && document.activeElement !== target) return;
    giveFocus(target);
  }

  /* Rule 4 — an anchored overlay (popover, dropdown) that OPENS hands
   * the focus to the field marked inside it, if any; with none, the
   * focus stays on the trigger: a popover is not modal. Same retry as
   * the focus trap: the panel is shown by the very effect calling us. */
  function autofocusOpen(panel) {
    let attempts = 0;
    function attempt() {
      if (!panel.isConnected) return;
      const t = autofocusIn(panel);
      if (!t) return;
      giveFocus(t);
      if (document.activeElement === t) return;
      if (++attempts < 20) requestAnimationFrame(attempt);
    }
    requestAnimationFrame(attempt);
  }

  // A listener outside the caller's node: its unsubscribe goes to the
  // running ``bz-init`` (``$bz._own``, ``directives.js``), which gives
  // it back when its node leaves the document.
  function owned(release) {
    return $bz._own ? $bz._own(release) : release;
  }

  // Escape closes ONE layer: the deepest of the overlays that answer.
  // Every overlay registers at mount, open or not; its handler returns
  // ``true`` when it closed something. Handed its element, an overlay is
  // asked before the ones that contain it (then the later in the page
  // before the earlier), and the first ``true`` ends the round, so a
  // popover inside a drawer does not take the drawer with it on one
  // Escape. A handler without an element, or that returns nothing, never
  // stops the round.
  const escapes = [];

  function deeperFirst(a, b) {
    if (!a.el || !b.el) return (a.el ? 0 : 1) - (b.el ? 0 : 1);
    if (a.el.contains(b.el)) return 1;
    if (b.el.contains(a.el)) return -1;
    return a.el.compareDocumentPosition(b.el) & Node.DOCUMENT_POSITION_FOLLOWING ? 1 : -1;
  }

  function onEscape(e) {
    if (e.key !== "Escape") return;
    const round = escapes.slice().sort(deeperFirst);
    for (const entry of round) {
      if (entry.handler(e) === true && entry.el) return;
    }
  }

  function escapeKey(handler, el) {
    const entry = {handler: handler, el: el || null};
    if (!escapes.length) document.addEventListener("keydown", onEscape);
    escapes.push(entry);
    return owned(function () {
      const at = escapes.indexOf(entry);
      if (at >= 0) escapes.splice(at, 1);
      if (!escapes.length) document.removeEventListener("keydown", onEscape);
    });
  }

  /* Listen for a window-level event (V3 replacement for Alpine's
   * ``@<event>.window`` modifier — bz-on listens on the element, not
   * the window). Returns its unsubscribe. Typical consumers register
   * from ``bz-init`` for events that only ever fire on window :
   * ``popstate``, ``htmx:after-request``, ``htmx:before-request``. */
  function onWindow(eventName, handler) {
    window.addEventListener(eventName, handler);
    return owned(function () {
      window.removeEventListener(eventName, handler);
    });
  }

  function scrollLock() {
    const gap = window.innerWidth - document.documentElement.clientWidth;
    const prevOverflow = document.body.style.overflow;
    const prevPadding = document.body.style.paddingRight;
    document.body.style.overflow = "hidden";
    if (gap > 0) document.body.style.paddingRight = gap + "px";
    return function unlock() {
      document.body.style.overflow = prevOverflow;
      document.body.style.paddingRight = prevPadding;
    };
  }

  /* Close the overlay when a click lands outside `el`. Registered in
   * the capture phase so a stopPropagation inside the panel doesn't
   * smother it. Returns its unsubscribe.
   *
   * `alsoInsideFn` (optional) : a function returning an element ALSO
   * treated as "inside". Needed when the panel is teleported to <body>
   * (out of `el`'s subtree) : a click in the panel would count as
   * outside and close it immediately. Resolved on each click — the
   * teleported panel's ref registers AFTER this handler is wired, so it
   * can't be captured up front. */
  /* Is `node` inside `container`, teleportations counted: a panel
   * projected under <body> is still inside what it was projected FROM
   * (its `_bzScopeHost`, the origin <template>). A dropdown opened in a
   * popover's panel is in the popover — at any depth. Excepting only the
   * container's own panel would let a pick in a menu nested in a popover
   * close the popover with its menu. */
  function within(container, node) {
    while (node) {
      if (container.contains(node)) return true;
      let up = node;
      while (up && !up._bzScopeHost) up = up.parentElement;
      if (!up) return false;
      node = up._bzScopeHost;
    }
    return false;
  }

  function clickOutside(el, handler, alsoInsideFn) {
    function onClick(e) {
      if (within(el, e.target)) return;
      if (alsoInsideFn) {
        const extra = alsoInsideFn();
        if (extra && within(extra, e.target)) return;
      }
      handler(e);
    }
    document.addEventListener("click", onClick, true);
    return owned(function () {
      document.removeEventListener("click", onClick, true);
    });
  }

  /* Position `el` (fixed) relative to `anchor`. placement = "<side>"
   * or "<side>-<align>" with side ∈ {auto,top,bottom,left,right}, align
   * ∈ {start,center,end} (default center).
   *
   * ONE rule for every side : try the sides in an order, take the first
   * where the panel fits entirely ; if none fits, the side with the most
   * leftover room. side "auto" tries bottom → top → right → left ; an
   * explicit side tries itself, then its OPPOSITE, then the other two in
   * that same order. Predictable (an order, not raw "most room" which
   * would jump around) and never off-screen : both axes are clamped.
   *
   * An explicit side tries all four because, in a narrow window, the
   * panel can fit on neither that side nor its opposite.
   *
   * Either way the RESOLVED side is written to `el.dataset.side` so a
   * consumer (e.g. the tooltip arrow) can follow it — no more arrow
   * frozen at the SSR side while the panel flips at runtime.
   *
   * Tracks scroll + resize ; returns its dispose. */
  // Best-fit preference order — module constant so the scroll/resize
  // reposition path allocates nothing per tick.
  const SIDE_ORDER = ["bottom", "top", "right", "left"];
  const OPPOSITE = { bottom: "top", top: "bottom", right: "left", left: "right" };
  // The readability floor of an anchored panel, in px. `matchWidth`
  // never goes below that width, whatever the anchor: without it, a
  // `ui.select` placed in a sidebar collapsed to a rail (`w-16`) renders
  // a ~48 px panel where the labels wrap letter by letter, with a
  // horizontal scrollbar. 192 px = `12rem`
  // — the value the repository already gives an anchored panel:
  // `min-w-[12rem]` at `dropdown` and `popover`, `min-w-48` for
  // `combobox`'s `sm` `panel_free`.
  const MIN_MATCHED_WIDTH = 192;
  function floating(anchor, el, opts) {
    opts = opts || {};
    const parts = (opts.placement || "bottom").split("-");
    const wantSide = parts[0];
    const align = parts[1] || "center";
    const offset = opts.offset === undefined ? 6 : opts.offset;
    // matchWidth: pin the panel to the anchor's width (native <select>
    // behaviour). Both min AND max so wide content (a multi-combobox
    // header with many pills, a long option) WRAPS / truncates inside
    // the trigger width instead of growing the panel past the trigger
    // and getting shoved to the viewport edge. Set BEFORE measuring so
    // offsetWidth reflects it.
    const matchWidth = !!opts.matchWidth;

    function position() {
      // Pin to `fixed` BEFORE measuring. On the very first open the panel
      // was just un-hidden (display:none → ''), so without this it is still
      // in normal flow when we read offsetWidth/Height — its size (and thus
      // the computed placement) is constrained by the parent (e.g. a narrow
      // sidebar) and ends up wrong, only snapping right on the 2nd open when
      // a leftover `fixed` is still set. Measuring while fixed is consistent
      // on every open.
      el.style.position = "fixed";
      const a = anchor.getBoundingClientRect();
      if (matchWidth) {
        // The floor applies to the ANCHOR, not to the result: above
        // `MIN_MATCHED_WIDTH`, `mw === a.width` and the behaviour is
        // identical to the byte (that is what makes this fix safe for
        // `matchWidth`'s only two callers, Select and Combobox). The
        // floor itself is bounded to the viewport: on a screen narrower
        // than 192 px, a panel at the floor would overflow, and the edge
        // correction below (`Math.max(4, Math.min(...))`) only shifts
        // it, it does not shrink it.
        const mw = Math.max(
          a.width,
          Math.min(MIN_MATCHED_WIDTH, Math.max(0, window.innerWidth - 8))
        );
        el.style.minWidth = mw + "px";
        el.style.maxWidth = mw + "px";
      }
      const w = el.offsetWidth;
      const h = el.offsetHeight;
      const vw = window.innerWidth;
      const vh = window.innerHeight;

      // Room available on each side of the anchor (minus the offset),
      // and what the panel needs there (its height for top/bottom, its
      // width for left/right).
      const room = {
        bottom: vh - a.bottom - offset,
        top: a.top - offset,
        right: vw - a.right - offset,
        left: a.left - offset,
      };
      const need = { bottom: h, top: h, right: w, left: w };

      const order =
        wantSide in OPPOSITE
          ? [wantSide, OPPOSITE[wantSide]].concat(
              SIDE_ORDER.filter(function (s) {
                return s !== wantSide && s !== OPPOSITE[wantSide];
              })
            )
          : SIDE_ORDER;
      const side =
        order.find(function (s) {
          return room[s] >= need[s];
        }) ||
        order.reduce(function (best, s) {
          return room[s] - need[s] > room[best] - need[best] ? s : best;
        });

      let top, left;
      if (side === "top" || side === "bottom") {
        top = side === "bottom" ? a.bottom + offset : a.top - offset - h;
        if (align === "start") left = a.left;
        else if (align === "end") left = a.right - w;
        else left = a.left + (a.width - w) / 2;
      } else {
        left = side === "right" ? a.right + offset : a.left - offset - w;
        if (align === "start") top = a.top;
        else if (align === "end") top = a.bottom - h;
        else top = a.top + (a.height - h) / 2;
      }
      // Both axes : when no side fits, the panel covers part of its
      // anchor rather than leaving the screen.
      left = Math.max(4, Math.min(left, vw - w - 4));
      top = Math.max(4, Math.min(top, vh - h - 4));
      el.style.top = top + "px";
      el.style.left = left + "px";
      // Publish the resolved side so consumers (tooltip arrow) follow it
      // — only on change, so a stable overlay writes nothing while the
      // page scrolls under it.
      if (el.dataset.side !== side) el.dataset.side = side;

      /* …and WHERE the anchor is in the panel, so the arrow aims at it.
         The panel's middle and the trigger's middle coincide as long as
         nothing pushes the panel; the edge reframing just above
         (`Math.max(4, Math.min(...))`) separates them. An arrow set at
         `left-1/2` — so in the middle of the bubble — would point beside
         its button as soon as the panel approaches an edge. */
      const centre =
        side === "top" || side === "bottom"
          ? a.left + a.width / 2 - left
          : a.top + a.height / 2 - top;
      // Bounded inside the panel: an arrow set 2 px from the edge
      // sticks out of the corners' radius and floats beside the bubble.
      // 12 px covers the panel's radius plus the arrow's half width (an
      // 8 px square rotated 45°, ~11 px of diagonal).
      const etendue = side === "top" || side === "bottom" ? w : h;
      const vise = Math.max(12, Math.min(centre, etendue - 12));
      el.style.setProperty("--bz-arrow", vise + "px");
    }

    // Opened from inside a modal (a dialog, a drawer: ``aria-modal``), the
    // panel is painted above it. Anchored panels sit at ``z-40``, under
    // the house's ``z-50`` modals: without this, a popover in a drawer
    // opens BEHIND it, and its buttons are out of reach. At ``z-50`` the
    // tie goes to the panel, projected last in
    // ``<body>``. A virtual anchor (a chart's point: a bare
    // ``getBoundingClientRect``) is in no modal.
    const inModal = typeof anchor.closest === "function" && anchor.closest('[aria-modal="true"]');
    el.style.zIndex = inModal ? "50" : "";
    position();
    window.addEventListener("scroll", position, true);
    window.addEventListener("resize", position);
    return function dispose() {
      window.removeEventListener("scroll", position, true);
      window.removeEventListener("resize", position);
    };
  }

  // Shared "should we animate ?" gate — the toast leave dance
  // (notification.js) and the bz-for FLIP reflow (directives.js) both
  // honour it. The MediaQueryList is created once and memoised ; ``.matches``
  // stays live, so an OS setting change mid-session is respected without
  // re-parsing the query on every call.
  let reduceMotionMQL = null;
  function prefersReducedMotion() {
    if (typeof window.matchMedia !== "function") return false;
    if (!reduceMotionMQL) {
      reduceMotionMQL = window.matchMedia("(prefers-reduced-motion: reduce)");
    }
    return reduceMotionMQL.matches;
  }

  /* ── The address, on the client side ─────────────────────────────────
   *
   * The EXACT counterpart of ``push_url()`` on the server side
   * (server/navigation.py), for what makes no round trip: a tab flips in
   * the scope, the server knows nothing about it, so the ``HX-Push-Url``
   * header can do nothing for it.
   *
   * ``pushState`` and not ``replaceState``: a tab IS a view, so the back
   * button must return to it. A display preference (a density, a theme)
   * does not deserve a history entry and has no business here.
   *
   * We keep ``history.state`` intact: htmx files its own there, and
   * overwriting it would break its own restoration on the entries it
   * created.
   */
  function pushUrl(param, value) {
    const url = new URL(window.location.href);
    const next = value == null ? "" : String(value);
    if (next === "") url.searchParams.delete(param);
    else url.searchParams.set(param, next);
    if (url.href === window.location.href) return;
    window.history.pushState(window.history.state, "", url.href);
  }

  /* A parameter's CURRENT value, or ``null``. Read live rather than
   * remembered: after a back, ``location`` has already moved by the time
   * the ``popstate`` reaches us. */
  function urlParam(param) {
    return new URL(window.location.href).searchParams.get(param);
  }

  /* Text made inert for HTML a slab builds as a string (the calendar's
   * cells, the time picker's buttons): ``&``, ``<``, ``>`` and both
   * quotes. THE escaper of the runtime: a slab that writes HTML from data
   * goes through it, and a new HTML sink is declared in
   * ``tests/consistency/test_runtime_html_sinks_are_declared.py``. */
  function escapeHtml(value) {
    return String(value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  $bz.helpers = {
    escapeHtml: escapeHtml,
    focusTrap: focusTrap,
    focusIn: focusIn,
    blurIn: blurIn,
    autofocusMounted: autofocusMounted,
    autofocusOpen: autofocusOpen,
    pageGivesFocus: pageGivesFocus,
    escapeKey: escapeKey,
    onWindow: onWindow,
    pushUrl: pushUrl,
    urlParam: urlParam,
    scrollLock: scrollLock,
    clickOutside: clickOutside,
    floating: floating,
    prefersReducedMotion: prefersReducedMotion,

    // Fire ``eventName`` from the scope's form carrier, deferred to a
    // microtask so the DOM write that precedes it has landed before any
    // listener reads the value back.
    //
    // The event name is the ONLY thing that differs between the two
    // components and the difference is deliberate :
    // number_input emits ``bzchange`` (its own, so an ``on_change=``
    // wired by the user can't be confused with the native ``change`` the
    // inner input fires while typing) ; slider emits the native
    // ``change``. Passing it in keeps the microtask rationale in one
    // place. Distinct from ``base/field_wiring.change_emit_effect``, which is
    // the effect-context mechanism, not another variant of this.
    //
    // ``detail``: what the gesture tells, the object whose JSON the
    // carrier holds for the server (a scheduler's ``{event_id, start,
    // end}``, a dropzone's ``Move``) — the client expression reads it in
    // ``$event.detail``, as every ``item_click``.
    emitChange: function (carrier, eventName, detail) {
      if (!carrier) return;
      const name = eventName || "change";
      queueMicrotask(function () {
        carrier.dispatchEvent(detail === undefined
          ? new Event(name, { bubbles: true })
          : new CustomEvent(name, { bubbles: true, detail: detail }));
      });
    },

    // ── Pointer capture — the pointer-drag family ────────────────────
    // Capturing means telling the browser to send ALL the pointer's
    // events to that element until release, even when the cursor leaves
    // it. Without that, the gesture stops at the first pixel outside the
    // box — and a handle is a few points wide.
    //
    // The two guards are not superstition, and it is for them that this
    // lives here rather than being copied:
    //   - ``pointerId !== undefined``: a synthetic event (a test, a
    //     script) does not carry one, and the call would raise;
    //   - the ``try``: the browser refuses the capture if the pointer is
    //     no longer active (released in the meantime, gesture cancelled
    //     by the OS), and that exception must not break the gesture in
    //     progress.
    //
    // A pointer-drag component calls this, it does not copy it.
    capturePointer: function (el, e) {
      if (!el || !e || e.pointerId === undefined) return;
      try { el.setPointerCapture(e.pointerId); } catch (err) {}
    },
    releasePointer: function (el, e) {
      if (!el || !e || e.pointerId === undefined) return;
      try { el.releasePointerCapture(e.pointerId); } catch (err) {}
    },

  };

  /* Iconify name resolution — mirrors Python's Icon._resolve_name so a
   * reactive name=ClientBinding produces the same "set:name[-style]"
   * form the server emits at SSR time. Invoked from rendered HTML :
   *   bz-attr:icon="$bz._resolveIcon($bz.state.X.y.icon, 'lucide', null)"
   * defaultSet / defaultStyle are baked at SSR time from the theme. */
  $bz._resolveIcon = function (name, defaultSet, defaultStyle) {
    if (!name) return "";
    if (String(name).indexOf(":") !== -1) return name; // full form verbatim
    let full = (defaultSet || "lucide") + ":" + name;
    // Phosphor (``ph``, translated server-side) / Tabler take an
    // optional style suffix (-bold, -fill, …).
    if (defaultStyle && (defaultSet === "ph" || defaultSet === "tabler")) {
      full = full + "-" + defaultStyle;
    }
    return full;
  };

  /* Is ``href`` the active entry of its menu for ``path``? An entry
   * matches its own path and what lies below it (``/`` only itself),
   * and the MOST SPECIFIC matching entry of the menu wins: ``/tickets``
   * stays lit on ``/tickets/42``, not on ``/tickets/mine`` when a
   * ``/tickets/mine`` entry exists. The menu is the closest
   * aside / nav / [role=navigation]; its entries carry ``__NAV_ATTR__``.
   * Decided in the browser and not by the server: entries rendered by a
   * refreshable zone, or by another one, belong to the same menu. The
   * winner is computed once per menu and path, not once per entry. */
  const NAV_WINNERS = new WeakMap();
  function navMatches(path, href) {
    return href === "/" ? path === "/" : path === href || path.startsWith(href + "/");
  }
  $bz._navActive = function (path, href, el) {
    if (!navMatches(path, href)) return false;
    const root = (el && el.closest && el.closest("aside, nav, [role=navigation]")) || document;
    const entries = root.querySelectorAll("[__NAV_ATTR__]");
    let memo = NAV_WINNERS.get(root);
    if (!memo || memo.path !== path || memo.count !== entries.length) {
      let winner = null;
      entries.forEach(function (entry) {
        const h = entry.getAttribute("__NAV_ATTR__");
        if (navMatches(path, h) && (winner === null || h.length > winner.length)) winner = h;
      });
      memo = { path: path, count: entries.length, winner: winner };
      NAV_WINNERS.set(root, memo);
    }
    return memo.winner === null || memo.winner === href;
  };

  /* ui.interval — recurring client timer that fires a server action.
   * Driven reactively from a bz-effect : ``$bz._tick($el, active, ms)``.
   * When ``active`` is truthy we ensure a setInterval that dispatches a
   * ``tick`` CustomEvent on the element (htmx fires the hx-post on it) ;
   * when falsy we clear it. The interval is idempotent across morph
   * re-binds (the element keeps ``_bzTickId``), self-clears if the
   * element leaves the DOM, and ``ms`` changes restart it. This is the
   * stoppable replacement for a server background loop : flipping the
   * ``active`` binding (server- or client-side) stops it instantly —
   * no held connection, no orphan requests. */
  $bz._tick = function (el, active, ms) {
    if (active) {
      if (el._bzTickId && el._bzTickMs === ms) return; // already live, same rate
      if (el._bzTickId) clearInterval(el._bzTickId);   // rate changed → restart
      el._bzTickMs = ms;
      el._bzTickId = setInterval(function () {
        if (!el.isConnected) {                          // removed → self-clear
          clearInterval(el._bzTickId);
          el._bzTickId = null;
          return;
        }
        el.dispatchEvent(new CustomEvent("tick"));
      }, ms);
    } else if (el._bzTickId) {
      clearInterval(el._bzTickId);
      el._bzTickId = null;
    }
  };

  /* Multi-pick membership algebra, shared by the Select and Combobox
   * multi scopes. Both read/write through the scope's own ``_read`` /
   * ``_write``, so the mixin never knows where the value lives (a local
   * signal or ``$bz.state.X.Y``).
   *
   * Spread it into a scope : ``{ ...$bz.multiSelect, …overrides }``.
   *
   * Only the genuinely divergent methods stay per-scope — Combobox
   * filters ``_selectAll`` by what the query leaves visible, and has
   * ``_highlightFromValue`` on Select's side.
   * The ones below are common, so a set-semantics fix is made once and
   * the two components cannot silently diverge. ``_clearAll`` does not
   * close the panel: a panel must survive its own header commands, as
   * with ``_selectAll``. Combobox overrides it, but only to ADD its query
   * reset. */
  $bz.multiSelect = {
    _picked() { const v = this._value(); return Array.isArray(v) ? v.map(String) : []; },
    _isPicked(v) { return this._picked().indexOf(String(v)) >= 0; },
    _hasPicked() { return this._picked().length > 0; },
    _togglePick(v) {
      const cur = this._picked();
      const str = String(v);
      const i = cur.indexOf(str);
      this._write(i >= 0 ? cur.filter((_, j) => j !== i) : [...cur, str]);
    },
    _removeOne(v) {
      const cur = this._picked();
      const i = cur.indexOf(String(v));
      if (i >= 0) { this._write(cur.filter((_, j) => j !== i)); }
    },
    // Single-mode alias for keyboard Enter (an option click calls
    // _togglePick directly).
    _pick(v) { this._togglePick(v); },
    _setValue(raw) {
      this._write(
        Array.isArray(raw)
          ? raw.map(String)
          : raw == null || raw === "" ? [] : [String(raw)],
      );
    },
    // Empties the selection WITHOUT closing the panel: it is a command
    // OF the header bar, and a command does not dismiss what it
    // commands. With an ``on_close=`` wired, closing here POSTED the
    // empty selection to the server — cf. the datatable's column
    // filter.
    _clearAll() { this._write([]); },
  };

  /* The parts a page carries ONCE (``render/shared_parts.py``): one
   * ``<template data-bz-part="<key>">`` per distinct part, cloned into a
   * host that names it (``data-bz-part``) — a calendar picker's header,
   * a colour picker's palette — the first time it opens, and again after
   * a morph took it out (the server never renders it). The clones are
   * marked ``data-bz-row``: the runtime inserted them, a walk by position
   * skips them. A zone response appends the parts it rendered to <body>;
   * one per key is kept, the first — identical by construction. */
  function partTemplate(key) {
    return key ? document.querySelector('template[data-bz-part="' + key + '"]') : null;
  }

  // Clone the host's part in, after its leading hidden inputs; ``true``
  // when it did. Scanned after insertion: its directives read the host's
  // scope.
  function fillPart(host) {
    const key = host && host.getAttribute("data-bz-part");
    if (!key || host.querySelector(':scope > [data-bz-part-of]')) return false;
    const tpl = partTemplate(key);
    if (!tpl) {
      console.warn("bz: no shared part " + key + " on the page");
      return false;
    }
    let anchor = host.firstElementChild;
    while (anchor && anchor.matches('input[type="hidden"]')) anchor = anchor.nextElementSibling;
    const nodes = Array.from(tpl.content.children).map(function (n) {
      const copy = n.cloneNode(true);
      copy.setAttribute("data-bz-part-of", key);
      copy.setAttribute("data-bz-row", "");
      return copy;
    });
    for (const node of nodes) host.insertBefore(node, anchor);
    if ($bz._scan) for (const node of nodes) $bz._scan(node);
    return true;
  }

  function dropDuplicateParts() {
    const seen = {};
    document.querySelectorAll("template[data-bz-part]").forEach(function (t) {
      const key = t.getAttribute("data-bz-part");
      if (seen[key]) t.remove();
      else seen[key] = true;
    });
  }
  document.addEventListener("htmx:afterSwap", dropDuplicateParts);
  document.addEventListener("htmx:oobAfterSwap", dropDuplicateParts);

  $bz.parts = { template: partTemplate, fill: fillPart };

  /* The pointer gesture's rules, ONCE — for `dnd.js` (moving a node
   * between zones) and `scheduler.js` (moving a card in time): keep a
   * dropped card where it was while the server ASKS something (a modal
   * dialog, no redraw), and swallow the click a browser fires at the end
   * of a drag. Without them, an `on_move` that asks « move it to Done? »
   * puts the card back under the question, and a clickable card opens
   * when it is let go.
   *
   *   MOUSE_THRESHOLD_PX / TOUCH_HOLD_MS / TOUCH_TOLERANCE_PX   when a
   *       press becomes a drag (distance, or time then wander);
   *   distance(start, e)        how far the pointer went, the same way;
   *   swallowClick()            the click that ends a drag, for a MOMENT
   *       (`SWALLOW_MS`) — a browser may fire none, and the next click
   *       would be the dialog's button;
   *   whenAnswered(carrier, {untouched, undo, settled})   after the
   *       carrier's answer (two frames: the swap and the rescan land
   *       then), `undo()` if `untouched()` — unless a modal dialog is open
   *       or a request is in flight: then it waits for the dialog's
   *       `close` or the next answer. `settled()` runs once, after the
   *       first answer. */
  const MODAL_SEL = '[role="dialog"][aria-modal="true"][data-open="true"]';
  const SWALLOW_MS = 400;
  let swallowUntil = 0;
  //: Requests in flight, page-wide. From `htmx:beforeSend`, never
  //: `beforeRequest`: a request cancelled before it leaves fires no
  //: `afterRequest`, and the count would hold a card for ever.
  let inFlight = 0;
  document.addEventListener("htmx:beforeSend", function () { inFlight++; });
  document.addEventListener("htmx:afterRequest", function () {
    inFlight = Math.max(0, inFlight - 1);
  });
  document.addEventListener("click", function (e) {
    if (Date.now() > swallowUntil) return;
    swallowUntil = 0;
    e.stopPropagation();
    e.preventDefault();
  }, true);

  function afterTwoFrames(fn) {
    requestAnimationFrame(function () { requestAnimationFrame(fn); });
  }

  function whenAnswered(carrier, how) {
    let holding = false;
    function wake() { afterTwoFrames(decide); }
    function hold() {
      if (holding) return;
      holding = true;
      document.addEventListener("close", wake);
      document.addEventListener("htmx:afterRequest", wake);
    }
    function release() {
      if (!holding) return;
      holding = false;
      document.removeEventListener("close", wake);
      document.removeEventListener("htmx:afterRequest", wake);
    }
    function decide() {
      if (!how.untouched()) return release();
      //: A closed dialog stays MOUNTED (its leave animation needs it):
      //: `data-open` says whether it asks.
      if (document.querySelector(MODAL_SEL) !== null || inFlight > 0) return hold();
      release();
      how.undo();
    }
    function settle(e) {
      if (e.detail && e.detail.elt && e.detail.elt !== carrier) return;
      document.removeEventListener("htmx:afterRequest", settle);
      afterTwoFrames(function () {
        decide();
        if (how.settled) how.settled();
      });
    }
    document.addEventListener("htmx:afterRequest", settle);
  }

  $bz.gesture = {
    MOUSE_THRESHOLD_PX: 5,
    TOUCH_HOLD_MS: 250,
    TOUCH_TOLERANCE_PX: 8,
    SWALLOW_MS: SWALLOW_MS,
    distance: function (start, e) {
      return Math.hypot(e.clientX - start.x, e.clientY - start.y);
    },
    swallowClick: function () { swallowUntil = Date.now() + SWALLOW_MS; },
    afterTwoFrames: afterTwoFrames,
    whenAnswered: whenAnswered,
    _inFlight: function () { return inFlight; },
  };

  /* Numeric primitives — pure, widget-agnostic. Shared by the
   * number_input + slider slabs (each caches the result locally). */
  $bz.num = {
    // Decimal places implied by a numeric step : 0.01 → 2, 5 → 0.
    // Pure (number|string) → int, no ``this`` / no widget state.
    precisionFromStep: function (step) {
      const s = String(step);
      const dot = s.indexOf(".");
      return dot >= 0 ? s.length - dot - 1 : 0;
    },

    // The memo wrapper over ``precisionFromStep``, cached on the scope's
    // own ``_precCache`` field. Spread into a scope as ``_precision``.
    cachedPrecision: function () {
      if (this._precCache !== undefined) return this._precCache;
      this._precCache = $bz.num.precisionFromStep(this._step);
      return this._precCache;
    },

  };
})();
