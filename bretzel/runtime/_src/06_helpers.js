/* 06_helpers.js — shared helpers for overlay-class components.
 *
 * Exposed via window.$bz.helpers, consumed by Dialog / Drawer /
 * Popover / Dropdown / Tooltip component code. Trimmed on purpose —
 * we inline the 6 placements we actually use instead of shipping a
 * floating-ui clone (V2's 09_floating.js was 257 LOC ; this is the
 * subset Bretzel components consume).
 *
 *   focusTrap(el)              trap Tab/Shift+Tab inside el ; returns
 *                              dispose (restores the previous focus)
 *   escapeKey(handler)         global Escape listener ; returns unsubscribe
 *   scrollLock()               body scroll lock w/ scrollbar compensation ;
 *                              returns unlock
 *   floating(anchor, el, opts) position el relative to anchor
 *                              (fixed-position, viewport-aware flip) ;
 *                              returns dispose (stops tracking)
 */
(function () {
  "use strict";
  const $bz = (window.$bz = window.$bz || {});

  const FOCUSABLE =
    'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), ' +
    'textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

  function focusTrap(el) {
    const previous = document.activeElement;
    function onKeydown(e) {
      if (e.key !== "Tab") return;
      const focusable = Array.from(el.querySelectorAll(FOCUSABLE)).filter(
        function (n) {
          return n.offsetParent !== null;
        },
      );
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
     * return, nothing. Observed on ``bench_dialog`` (2026-08-19), the
     * panel's three buttons: hidden at +1 ms, visible at +16 ms.
     *
     * A FIXED delay is not enough, and that is measured too: the
     * two-frame version passed about one time in three — the boundary
     * falls right inside the hidden window, and it moves from one run to
     * the next. So we do not wait for a duration, we wait for the
     * RESULT: we try, we check the focus landed, and we retry otherwise.
     *
     * Without that, the trap was indeed installed (``$el._bzTrap``
     * present) and the focus stayed on the trigger. The restored
     * contract is written in ``dialog.py``: "the first interactive child
     * receives focus".
     *
     * The DOM is RE-QUERIED at every attempt: between the installation
     * and the frame that succeeds, a morph may have replaced the panel's
     * content, and a detached node focuses into the void. */
    let attempts = 0;
    function focusFirst() {
      if (!el.isConnected) return;
      const first = el.querySelector(FOCUSABLE);
      if (first) {
        first.focus();
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

  function escapeKey(handler) {
    function onKeydown(e) {
      if (e.key === "Escape") handler(e);
    }
    document.addEventListener("keydown", onKeydown);
    return function () {
      document.removeEventListener("keydown", onKeydown);
    };
  }

  /* Listen for a window-level event (V3 replacement for Alpine's
   * ``@<event>.window`` modifier — bz-on listens on the element, not
   * the window). Returns its unsubscribe. Typical consumers register
   * from ``bz-init`` for events that only ever fire on window :
   * ``popstate``, ``htmx:after-request``, ``htmx:before-request``. */
  function onWindow(eventName, handler) {
    window.addEventListener(eventName, handler);
    return function () {
      window.removeEventListener(eventName, handler);
    };
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
  function clickOutside(el, handler, alsoInsideFn) {
    function onClick(e) {
      if (el.contains(e.target)) return;
      if (alsoInsideFn) {
        const extra = alsoInsideFn();
        if (extra && extra.contains(e.target)) return;
      }
      handler(e);
    }
    document.addEventListener("click", onClick, true);
    return function () {
      document.removeEventListener("click", onClick, true);
    };
  }

  /* Position `el` (fixed) relative to `anchor`. placement = "<side>"
   * or "<side>-<align>" with side ∈ {auto,top,bottom,left,right}, align
   * ∈ {start,center,end} (default center).
   *
   * side "auto" = BEST-FIT : pick the first side (preference order
   * bottom → top → right → left) where the panel fits entirely ; if
   * none fits, the side with the most leftover room. Predictable (a
   * preference order, not raw "most room" which would jump around) and
   * never off-screen (the cross axis is clamped).
   *
   * An explicit side keeps the old behaviour : flip to the OPPOSITE
   * side on the main axis when the preferred side lacks room.
   *
   * Either way the RESOLVED side is written to `el.dataset.side` so a
   * consumer (e.g. the tooltip arrow) can follow it — no more arrow
   * frozen at the SSR side while the panel flips at runtime.
   *
   * Tracks scroll + resize ; returns its dispose. */
  // Best-fit preference order — module constant so the scroll/resize
  // reposition path allocates nothing per tick.
  const SIDE_ORDER = ["bottom", "top", "right", "left"];
  // The readability floor of an anchored panel, in px. `matchWidth`
  // never goes below that width, whatever the anchor: a `ui.select`
  // placed in a sidebar collapsed to a rail (`w-16`) rendered a ~48 px
  // panel where the labels wrapped letter by letter, with a horizontal
  // scrollbar (seen on `examples/crm` on 2026-08-29). 192 px = `12rem`
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

      let side;
      if (wantSide === "auto") {
        // Best-fit : first side (in preference order) where the panel
        // fits ; else the side with the most leftover room.
        side = SIDE_ORDER.find(function (s) {
          return room[s] >= need[s];
        });
        if (!side) {
          side = SIDE_ORDER.reduce(function (best, s) {
            return room[s] - need[s] > room[best] - need[best] ? s : best;
          });
        }
      } else {
        // Explicit side : flip to the opposite on the main axis when the
        // preferred side lacks room (and the opposite has it).
        side = wantSide;
        if (side === "bottom" && room.bottom < h && room.top >= h) side = "top";
        else if (side === "top" && room.top < h && room.bottom >= h) side = "bottom";
        else if (side === "right" && room.right < w && room.left >= w) side = "left";
        else if (side === "left" && room.left < w && room.right >= w) side = "right";
      }

      let top, left;
      if (side === "top" || side === "bottom") {
        top = side === "bottom" ? a.bottom + offset : a.top - offset - h;
        if (align === "start") left = a.left;
        else if (align === "end") left = a.right - w;
        else left = a.left + (a.width - w) / 2;
        left = Math.max(4, Math.min(left, vw - w - 4));
      } else {
        left = side === "right" ? a.right + offset : a.left - offset - w;
        if (align === "start") top = a.top;
        else if (align === "end") top = a.bottom - h;
        else top = a.top + (a.height - h) / 2;
        top = Math.max(4, Math.min(top, vh - h - 4));
      }
      el.style.top = top + "px";
      el.style.left = left + "px";
      // Publish the resolved side so consumers (tooltip arrow) follow it
      // — only on change, so a stable overlay writes nothing while the
      // page scrolls under it.
      if (el.dataset.side !== side) el.dataset.side = side;

      /* …and WHERE the anchor is in the panel, so the arrow aims at it.
         The panel's middle and the trigger's middle coincide as long as
         nothing pushes the panel; the edge reframing just above
         (`Math.max(4, Math.min(...))`) separates them. The arrow was set
         at `left-1/2` — so in the middle of the bubble — and pointed
         beside its button as soon as you approached an edge. Measured on
         2026-09-09 on `examples/kanban`: trigger centred at 1468 px,
         arrow at 1443. */
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

    position();
    window.addEventListener("scroll", position, true);
    window.addEventListener("resize", position);
    return function dispose() {
      window.removeEventListener("scroll", position, true);
      window.removeEventListener("resize", position);
    };
  }

  // Shared "should we animate ?" gate — the toast leave dance
  // (09_notification.js) and the bz-for FLIP reflow (02_directives.js) both
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
   * ``pushState`` and not ``replaceState`` — the user's decision on
   * 2026-08-29: "pushState for views". A tab IS a view, so the back
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

  $bz.helpers = {
    focusTrap: focusTrap,
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
    // The event name is the ONLY thing that differed between the two
    // copies (audit F61) and the difference is deliberate :
    // number_input emits ``bzchange`` (its own, so an ``on_change=``
    // wired by the user can't be confused with the native ``change`` the
    // inner input fires while typing) ; slider emits the native
    // ``change``. Passing it in keeps the microtask rationale in one
    // place. Distinct from ``base/_wiring.change_emit_effect``, which is
    // the effect-context mechanism, not another variant of this.
    emitChange: function (carrier, eventName) {
      if (!carrier) return;
      const name = eventName || "change";
      queueMicrotask(function () {
        carrier.dispatchEvent(new Event(name, { bubbles: true }));
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
    // Extracted on 2026-08-13, at the 3rd and 4th site (slider ×2,
    // resizable ×2) — the threshold the repository set itself, "twice a
    // coincidence, three times a pattern". The pointer-drag family's
    // next component (``signature_pad``) calls this, it does not copy
    // it.
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
    // Phosphor / Tabler take an optional style suffix (-bold, -fill, …).
    if (defaultStyle && (defaultSet === "phosphor" || defaultSet === "tabler")) {
      full = full + "-" + defaultStyle;
    }
    return full;
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
   * The eight below were identical in both slabs (audit F19), so a
   * set-semantics fix had to be hand-mirrored or the two components
   * silently diverged. ``_clearAll`` JOINED them on 2026-08-06 : it was
   * excluded only because each scope also set ``this.open = false``,
   * and that closing is exactly what got removed (a panel must survive
   * its own header commands — ``_selectAll`` never closed). Combobox
   * still overrides it, but only to ADD its query reset. */
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
    // The primitive was already shared ; the memo around it was not, so
    // it existed twice (audit F60).
    cachedPrecision: function () {
      if (this._precCache !== undefined) return this._precCache;
      this._precCache = $bz.num.precisionFromStep(this._step);
      return this._precCache;
    },

  };
})();
