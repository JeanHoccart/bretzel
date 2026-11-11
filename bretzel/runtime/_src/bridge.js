/* bridge.js — HTMX glue : signal snapshot out, <bz-patch> in.
 *
 * The ONLY module that wires HTMX events. No custom action dispatcher :
 * components emit native hx-post, HTMX owns the POST, we only configure
 * the request envelope and consume the response patches.
 *
 *   htmx:configRequest
 *     - snapshot the global signal store, group by instance,
 *     - filter per opt-outs (send_to_server=false) and sync mode
 *       (sync="delta" diffs against the last-sent snapshot),
 *     - inject namespaced form-data (Class.key.field=value),
 *     - inject X-Bretzel-Protocol / X-Bretzel-CSRF / X-Bretzel-Page-ID,
 *     - forward X-Bz-Sig / X-Bz-Ts from the triggering element's
 *       data-bz-sig / data-bz-ts stamps (HMAC v2).
 *
 *   htmx:afterSwap + htmx:oobAfterSwap
 *     - collect <bz-patch> tags, apply patches to the signal store,
 *       remove the consumed tags,
 *     - reserved keys : "_error" (dispatch table below),
 *       "_notifications" (forward to $bz.notify),
 *     - RESCAN the swapped subtree (rebind-after-morph — restores
 *       reactive writes idiomorph clobbered),
 *     - sweep orphaned bz-data scopes.
 *
 *   htmx:responseError
 *     - parse <bz-patch> out of the raw error body (4xx/5xx responses
 *       are not swapped by HTMX), dispatch a reserved ``_error`` directive
 *       via handleError(), else generic notification.
 *
 * ``_error`` dispatch (server emits the envelope via error_envelope()) :
 *   kind "reload"   → window.location.reload() — a stale / rotated HMAC
 *                     signature or CSRF token, which re-rendering the page
 *                     mints fresh (loop-guarded : a 2nd reload-error within
 *                     3s falls back to a toast, so a persistent failure
 *                     surfaces instead of looping).
 *   otherwise / un-enveloped 4xx → generic error toast
 *
 *   (There is NO "redirect" kind: a redirection goes through the
 *   HX-Redirect header, which htmx handles natively, and
 *   `bretzel.redirect()` sets it. The kind stayed here for six months
 *   with nothing emitting it on the Python side — and with nothing being
 *   ABLE to, error_envelope() not knowing how to carry a url. Gate:
 *   tests/consistency/test_bridge_error_kinds_are_emitted.py.)
 */
(function () {
  "use strict";
  const $bz = (window.$bz = window.$bz || {});

  // Wire-format tag name — substituted at build time from protocol.py
  // (single source of truth, even inside the JS).
  const PATCH_TAG = "__PATCH_TAG__";

  function handleError(err) {
    // Typed error directive from a 4xx body (reserved ``_error`` key).
    const kind = err && err.kind;
    if (kind === "reload") {
      // A reload re-renders the page with a fresh HMAC sig + CSRF token,
      // healing the stale-token 403 the user would otherwise dead-end on.
      // Loop-guard : if we already reloaded < 3s ago and hit ANOTHER
      // reload-error, the reload isn't fixing it — surface a toast instead
      // of looping forever.
      let last = 0;
      try { last = parseInt(sessionStorage.getItem("bzReloadAt") || "0", 10); } catch (e) {}
      const now = Date.now();
      if (now - last < 3000) {
        $bz.notify({ variant: "error", message: (err && err.message) || "Request failed — please reload." });
        return;
      }
      try { sessionStorage.setItem("bzReloadAt", String(now)); } catch (e) {}
      window.location.reload();
      return;
    }
    $bz.notify({ variant: "error", message: (err && err.message) || "Request failed." });
  }

  function applyPayload(payload) {
    if (!payload || !payload.patches) return;
    // SEED or PUSH — two paths, two intents.
    //
    //   seed   (partial nav): the server re-emits every instance of the
    //          page, with ITS values, which are the defaults. It cannot
    //          know the browser's. They must therefore only serve to
    //          create what is missing.
    //   push   (action response): the server deliberately mutated a
    //          field. It wins.
    //
    // `config` is the marker, and it is not approximate: on the Python
    // side, `build_patch` only emits it under `include_unchanged=True`,
    // that is to say exactly the seed path. The agreement is gated by
    // `tests/consistency/test_a_seed_patch_never_overwrites.py`, and the
    // result by
    // `tests/runtime_js/test_a_partial_nav_never_clobbers_client_state.py`.
    const isSeed = !!payload.config;
    for (const instancePath of Object.keys(payload.patches)) {
      const fields = payload.patches[instancePath];
      if (instancePath === "_error") {
        // A typed error directive supersedes any other patch — dispatch
        // (reload / toast) and stop applying this payload.
        handleError(fields);
        return;
      }
      if (instancePath === "_notifications") {
        for (const n of fields) $bz.notify(n);
        continue;
      }
      for (const field of Object.keys(fields)) {
        const path = instancePath + "." + field;
        if (isSeed) $bz._store.seed(path, fields[field]);
        else $bz._store.set(path, fields[field]);
      }
    }
    // The partial nav seed's transport config — AFTER the fields,
    // because ``adoptConfig`` registers the persistence and that
    // superimposes the stored snapshot, which must win. Absent from an
    // ordinary action response: the client already has those instances'
    // config.
    if (payload.config && $bz._adoptConfig) {
      for (const path of Object.keys(payload.config)) {
        $bz._adoptConfig(path, payload.config[path]);
      }
    }
  }

  function applyPatchTags() {
    for (const tag of document.querySelectorAll(PATCH_TAG)) {
      let payload = null;
      try {
        payload = JSON.parse(tag.textContent);
      } catch (e) {
        console.error("bz: malformed <bz-patch>", tag.textContent, e);
      }
      tag.remove();
      applyPayload(payload);
    }
  }

  // A COMPOSITE value leaves as JSON, not as is.
  //
  // A form body only carries strings, and htmx treats an array
  // separately: `formDataFromObject` does `obj[key].forEach(v =>
  // append(key, v))`. Two consequences:
  //
  //   - `["a","b"]` leaves as TWO fields of the same name, and the
  //     server keeps the last — so `["a","b"]` arrives as `"b"`, and
  //     `["change"]` as `"change"`;
  //   - `[]` adds NOTHING, so the key is absent from the body. Since
  //     hydration only writes the fields that are present, **an emptied
  //     client list could never empty its server field again** — the
  //     exact twin of the unticked box that submits nothing, on the
  //     other transport.
  //
  // `JSON.stringify` puts the client store back on the same convention
  // as the catalogue's hidden carriers (`toggle_group`, `select`,
  // `combobox`, `date_range_picker`, `slider`, `resizable`,
  // `accordion`), and it is `_coerce_composite` that undoes it on the
  // Python side — a single wire contract for both paths, instead of two.
  //
  // Scalars are NOT touched: they already travel correctly, and encoding
  // them would make `'"text"'` arrive where the field expects `text`.
  function wireValue(value) {
    return value !== null && typeof value === "object"
      ? JSON.stringify(value)
      : value;
  }

  function injectParameters(detail) {
    const config = $bz._config || {};
    const grouped = new Map(); // instancePath → {field: value}
    for (const [fullPath, sig] of $bz._store.entries()) {
      const cut = fullPath.lastIndexOf(".");
      const path = fullPath.slice(0, cut);
      const field = fullPath.slice(cut + 1);
      if (!grouped.has(path)) grouped.set(path, {});
      grouped.get(path)[field] = sig.peek();
    }
    for (const [path, fields] of grouped.entries()) {
      // ``send_to_server: false`` (declared on the Python side on the
      // class) is the ONLY filter here, and it is all-or-nothing. A
      // "delta" mode would be wrong, not merely useless — the full reason
      // is in ``ClientState``'s docstring (bretzel/state/scopes/client.py
      // § "There is NO delta mode"). Do not introduce one without reading
      // that paragraph first.
      const cfg = config[path] || {};
      if (cfg.send_to_server === false) continue;
      for (const field of Object.keys(fields)) {
        // A field with no value says nothing — its signal was created
        // by a read (`get` auto-creates) and never seeded. Sent, it
        // would put the WORD "undefined" in the body: stored as is in a
        // text field, refused by a bool one. Left out, the server keeps
        // its own value, as hydration only writes the fields present.
        if (fields[field] === undefined) continue;
        detail.parameters[path + "." + field] = wireValue(fields[field]);
      }
    }
  }

  /* ── ``$bz.pending`` — "is an action in flight?" ─────────────────────
   *
   * htmx KNOWS a request is in progress (it sets ``.htmx-request`` on
   * the triggering element), but that information was readable by
   * nobody: neither from a ``bz-*`` expression, nor from Python. A dev
   * who wanted a spinner during the round trip therefore had to hold the
   * boolean themselves — and they COULD not hold it on the server side,
   * since server state arrives WITH the response, that is to say when
   * the wait is already over.
   *
   * This module already owns the transport boundary, so it is here that
   * the information is published, as a signal: ``ui.pending()`` returns
   * the expression ``$bz.pending($el, 200)``, read by any ``bz-show`` /
   * ``bz-attr`` like any other source.
   *
   * TWO ADDRESSINGS, a single function. ``$el`` (the element carrying
   * the prop is the trigger) walks up to the ``hx-post``'s carrier
   * through ``closest``: indispensable, because the spinner's
   * ``bz-show`` is set on the SPINNER, not on the button (cf.
   * ``_cloak_show``). A string (the ``action_id``) addresses the same
   * action from elsewhere in the page — ``ui.pending(save)``.
   *
   * THE DELAY IS THE MECHANISM'S REASON TO BE. A spinner that appears
   * under ~200 ms produces a flash, and the interface is perceived as
   * SLOWER than showing nothing. Nobody writes it by hand; here it is
   * the default. The delay travels in the expression, so several delays
   * can coexist on one key — hence a ``Map`` of signals per delay rather
   * than a single signal.
   *
   * A counter, not a boolean: two buttons sharing the same
   * ``action_id`` can be in flight at the same time, and the first
   * return must not extinguish the second.
   */
  const PENDING_BY_ELT = new WeakMap();
  const PENDING_BY_ID = new Map();

  /* Two stores, and it is forced, not incidental: a ``WeakMap`` cannot
   * index a string, and a ``Map`` indexed by elements would hold every
   * trigger for the life of the page. */
  function pendingStore(key) {
    return typeof key === "string" ? PENDING_BY_ID : PENDING_BY_ELT;
  }

  /* The keys a request arms: the triggering element AND its
   * ``action_id``. The latter reads from ``hx-post``, whose format is
   * ``<ROUTE_ACTION>/<id>`` — and ``ROUTE_ACTION`` is SUBSTITUTED here
   * from ``protocol.py`` at build time, like the envelope and patch
   * tags. Without that the JS would become a stranger to the wire
   * format again: it would guess it by string splitting, and a route
   * change on the Python side would show up nowhere. */
  /* An app under a ``base_path`` (``core/base_path.py``) says so on
   * ``<html>``; for one at the root, ``BASE`` is empty and all this is
   * inert. */
  const BASE = document.documentElement.getAttribute("__BASE_ATTR__") || "";
  const ACTION_PREFIX = BASE + "__ROUTE_ACTION__/";

  /* The address bar's path as the app knows it: what ``current_path`` holds
   * and what the menu entries are compared with. */
  $bz._localPath = function () {
    const p = window.location.pathname;
    return BASE && (p === BASE || p.startsWith(BASE + "/")) ? p.slice(BASE.length) || "/" : p;
  };

  /* The THIRD key, reserved: "a navigation is in flight". The shell's
   * bar (``render/shell.nav_progress_html``) is only a ``bz-show`` on
   * it, so it has no mechanism of its own — it is the same registry, the
   * same timing, the same disarm.
   *
   * ``detail.boosted`` covers the links boosted by ``hx-boost`` (set at
   * the document level by the shell), menus included; ``hx-push-url`` an
   * author's own explicit ``hx-get``. */
  const NAV_KEY = "__NAV_PENDING_KEY__";

  function pendingKeys(elt, detail) {
    if (!elt || elt.nodeType !== 1) return [];
    const keys = [elt];
    const post = elt.getAttribute("hx-post");
    if (post && post.startsWith(ACTION_PREFIX)) {
      keys.push(post.slice(ACTION_PREFIX.length));
    }
    if ((detail && detail.boosted) || elt.getAttribute("hx-push-url") === "true") {
      keys.push(NAV_KEY);
    }
    return keys;
  }

  function armPending(key) {
    // No entry = nobody reads this key. Nothing to arm: we do not
    // fabricate a signal for a button with no ``ui.pending()``.
    const entry = pendingStore(key).get(key);
    if (!entry || ++entry.count > 1) return;
    entry.byDelay.forEach(function (slot, delay) {
      if (delay <= 0) {
        slot.sig.set(true);
        return;
      }
      slot.timer = setTimeout(function () {
        slot.timer = 0;
        slot.sig.set(true);
      }, delay);
    });
  }

  function disarmPending(key) {
    const entry = pendingStore(key).get(key);
    if (!entry || entry.count === 0 || --entry.count > 0) return;
    entry.byDelay.forEach(function (slot) {
      clearTimeout(slot.timer);
      slot.timer = 0;
      slot.sig.set(false);
    });
  }

  /* Whether a link is boosted: the link's own ``hx-boost``, else the
   * page's. htmx reads ``hx-boost`` by INHERITANCE, so any ancestor that
   * sets one speaks for the links it holds — and ``ui.form`` sets
   * ``hx-boost="false"`` for its OWN submit (``Form.render``): its
   * cancel link and its breadcrumb would reload the whole document,
   * sidebar included. A link with no
   * ``hx-boost`` of its own under a page that boosts (``render/shell.py``,
   * or a teleported panel that ``inheritHtmx`` gave the page's) gets its
   * own ``hx-boost="true"``, written before htmx reads it
   * (``beforeProcessNode``). An opt-out stays on the link itself: a
   * ``<a download>`` gets ``hx-boost="false"`` here. Where the boosted link
   * goes is ``boostedTarget``'s, below — same rule, the page's.
   * Registered at the module's LOAD: htmx processes the document at
   * ``DOMContentLoaded``, before ``boot()`` wires the bridge. Gate:
   * ``tests/runtime_js/test_a_link_is_boosted_wherever_it_sits.py``. */
  document.addEventListener("htmx:beforeProcessNode", function (e) {
    const a = e.target;
    if (a.tagName !== "A" || a.hasAttribute("hx-boost")) return;
    // A link to ANOTHER origin — another site, or another port of the same
    // host — is a document load, never boosted: htmx refuses a request off
    // its origin (``selfRequestsOnly``) and the click would do NOTHING, in
    // silence. Gate: same test file, ``test_a_link_to_another_origin``.
    //
    // Same thing for a page of this origin OUTSIDE this app's ``base_path``:
    // a sibling app, whose document cannot go in this app's outlet.
    //
    // And a ``<a download>``: htmx would swap the file into the page. A
    // ``@download`` route needs no attribute, it redirects htmx itself
    // (``server/routing/downloads.py``); this is for any other file route.
    const outside = BASE && a.pathname !== BASE && !a.pathname.startsWith(BASE + "/");
    const leaves = a.getAttribute("href") && (a.origin !== window.location.origin || outside);
    if (leaves || a.hasAttribute("download")) {
      a.setAttribute("hx-boost", "false");
      return;
    }
    if (a.closest('[hx-boost="true"]')) a.setAttribute("hx-boost", "true");
  });

  /* Defined at the module's LOAD, not in ``_wireBridge``: a
   * ``bz-show`` can evaluate before the bridge is wired, and a missing
   * ``$bz.pending`` would crash the expression instead of returning
   * ``false``. */
  $bz.pending = function (key, delay) {
    if (key && key.nodeType === 1) key = key.closest("[hx-post]") || key;
    const store = pendingStore(key);
    let entry = store.get(key);
    if (!entry) {
      entry = { byDelay: new Map(), count: 0 };
      store.set(key, entry);
    }
    const ms = delay || 0;
    let slot = entry.byDelay.get(ms);
    if (!slot) {
      slot = { sig: $bz.signal(false), timer: 0 };
      entry.byDelay.set(ms, slot);
    }
    // Reading INSIDE an effect = subscribing. It is the only point of
    // contact with the reactive graph: the toggle then goes through the
    // ordinary microtask flush, like any other source.
    return slot.sig.get();
  };

  /* The automatic busy state (``loading=`` on the Python side): a
   * trigger whose request is still unanswered after ``BUSY_AFTER_MS``
   * shows it on its own — the ``__BUSY_CLASS__`` class for the theme's CSS
   * (``theme/css.py``, ``_BUSY``) and ``aria-busy`` for assistive tech.
   * Under the delay, nothing: a fast answer does not flash.
   *
   * A zone the runtime asks again (``refetchZone``: another tab's change,
   * a row refresh) is the source of its own request, so it gets the same
   * state. Not for a navigation — the shell's bar shows it —, nor for
   * polling, nor a hidden carrier, nor under ``loading=False``
   * (``__BUSY_ATTR__="off"`` on the element or an ancestor). A counter,
   * like the witness above: two requests from one element, and the first
   * answer must not clear the second. */
  const BUSY_AFTER_MS = 200;
  const BUSY = new WeakMap();

  function busyTarget(elt, detail) {
    if (!elt || elt.nodeType !== 1 || elt.hidden) return null;
    if ((detail && detail.boosted) || elt.getAttribute("hx-push-url") === "true") return null;
    if (/\bevery\b/.test(elt.getAttribute("hx-trigger") || "")) return null;
    if (elt.closest('[__BUSY_ATTR__="off"]')) return null;
    return elt;
  }

  function armBusy(elt) {
    let state = BUSY.get(elt);
    if (!state) {
      state = { count: 0, timer: 0, shown: false };
      BUSY.set(elt, state);
    }
    if (++state.count > 1) return;
    state.timer = setTimeout(function () {
      state.timer = 0;
      if (!elt.isConnected) return;
      elt.classList.add("__BUSY_CLASS__");
      elt.setAttribute("aria-busy", "true");
      state.shown = true;
    }, BUSY_AFTER_MS);
  }

  function disarmBusy(elt) {
    const state = BUSY.get(elt);
    if (!state || state.count === 0 || --state.count > 0) return;
    clearTimeout(state.timer);
    // A morph may already have dropped both (the server never renders
    // them): only what this state set is taken back.
    if (state.shown && elt.classList.contains("__BUSY_CLASS__")) {
      elt.classList.remove("__BUSY_CLASS__");
      elt.removeAttribute("aria-busy");
    }
    BUSY.delete(elt);
  }

  //: Attributes the client sets on an element until an answer redraws it
  //: (``dnd.js``, ``scheduler.js``): the server never renders them,
  //: so a morph erases them, and their survival says nobody answered. A
  //: list patch keeps an element WITHOUT morphing it — but it does answer
  //: for every child it places, so it erases them too (``applyList``).
  $bz._witnesses = $bz._witnesses || new Set();

  /* ── Where the page is scrolled, across navigations ──────────────────
   *
   * The browser's rule, Next.js's and SvelteKit's: a link followed opens
   * the page at the TOP (at its anchor for ``/page#section``); the
   * browser's back / forward gives a page back WHERE IT WAS LEFT;
   * anything that is not a navigation (an action redrawing a zone, a
   * tab, the sidebar's own scroll) leaves the scroll alone.
   *
   * htmx only knows the window, and most apps do not scroll it: the
   * document is frozen and a ``ui.pane`` scrolls around the outlet
   * (``ui.viewport``). That pane SURVIVES a navigation — only the outlet
   * is swapped — so left alone it keeps the page left's ``scrollTop``: a
   * link followed from the bottom of a page lands at the bottom of the
   * next, and Back gives the page back at an arbitrary height.
   *
   * What scrolls « the page »: the window, and every scroll container
   * that holds the outlet (``scrollersOf``) — both models, no flag.
   * Elements INSIDE the page keep their own (a list, a pane of the page).
   *
   * Each history entry carries a key in ``history.state``; its positions
   * live in memory under that key, taken when the entry is LEFT. htmx
   * rewrites the state to ``{htmx: true}`` before a push
   * (``saveCurrentPageToHistory``), so the key is written back right
   * after.
   *
   * Back / forward come back LIKE A LINK: the outlet is fetched and
   * swapped, the shell stays — its sidebar, its scroll — and the
   * positions are set back once the swap is in. htmx's own restore
   * would render the whole ``<body>`` again (``historyCacheSize: 0``,
   * ``render/shell.py``), its ``<script>`` tags included: htmx and this
   * runtime would boot a SECOND time in the same window at each Back,
   * every listener doubled. A page with no outlet is reloaded: one boot,
   * always.
   *
   * ``scrollIntoViewOnBoost`` is turned off: htmx scrolls a boosted
   * link's target into view — the outlet's top, under the pane's
   * padding, and down a scrolling document — instead of the
   * page's top. Gate:
   * ``tests/runtime_js/test_a_navigation_lands_at_the_top.py``. */
  const SCROLL_KEY = "bzScroll";
  const SCROLL_KEPT = 50;
  const scrollPositions = new Map();
  let scrollEntry = null;
  //: The navigation swap awaited: its target, and the positions to set
  //: back (``null``: the top, or the anchor).
  let scrollPending = null;

  function newScrollKey() {
    return Date.now().toString(36) + Math.random().toString(36).slice(2, 8);
  }

  function stampScrollEntry(key) {
    scrollEntry = key;
    const state = Object.assign({}, window.history.state);
    state[SCROLL_KEY] = key;
    try {
      window.history.replaceState(state, "");
    } catch (e) {
      // A refused state write must not stop a navigation: the page just
      // will not come back to its position.
    }
  }

  /* ``from`` and its ancestors that scroll vertically, outermost first. */
  function scrollersOf(from) {
    const out = [];
    for (let el = from; el && el !== document.body; el = el.parentElement) {
      if (/(auto|scroll)/.test(getComputedStyle(el).overflowY)) out.unshift(el);
    }
    return out;
  }

  /* The page's scrollers: those of the DEEPEST outlet, which hold the
   * outer ones' too (nested layouts). */
  function pageScrollers() {
    const outlets = document.querySelectorAll("[data-bz-outlet]");
    return scrollersOf(outlets[outlets.length - 1]);
  }

  function rememberScroll() {
    if (!scrollEntry) return;
    scrollPositions.delete(scrollEntry);
    scrollPositions.set(scrollEntry, {
      win: window.scrollY,
      panes: pageScrollers().map(function (el) { return el.scrollTop; }),
    });
    if (scrollPositions.size > SCROLL_KEPT) {
      scrollPositions.delete(scrollPositions.keys().next().value);
    }
  }

  /* Positions given back. The page just swapped may not have its full
   * height yet (its icons draw a moment later): a position past the end
   * is cut short — 5 530 px for 5 551 on the playground's /dropdown. So
   * it is set again at each frame, for half a second at most, until it
   * holds — and not once the user moves (wheel, touch, key, pointer):
   * the page is theirs again. */
  const SCROLL_TRIES = 30;
  const USER_MOVES = ["wheel", "touchstart", "keydown", "pointerdown"];

  function setScrollBack(pos) {
    const panes = pageScrollers();
    let tries = SCROLL_TRIES;
    let moved = false;
    function stop() { moved = true; }
    USER_MOVES.forEach(function (name) {
      window.addEventListener(name, stop, { capture: true, passive: true, once: true });
    });
    function done() {
      USER_MOVES.forEach(function (name) {
        window.removeEventListener(name, stop, { capture: true });
      });
    }
    (function apply() {
      if (moved) return done();
      window.scrollTo(0, pos.win);
      let held = Math.abs(window.scrollY - pos.win) < 1;
      panes.forEach(function (el, i) {
        el.scrollTop = pos.panes[i] || 0;
        held = held && Math.abs(el.scrollTop - (pos.panes[i] || 0)) < 1;
      });
      if (held || --tries <= 0) return done();
      requestAnimationFrame(apply);
    })();
  }

  /* The outlet a navigation swaps, and how: the target and the swap
   * declared next to ``hx-boost="true"`` on the page's envelope
   * (``render/shell.py``) — the only place the framework boosts. */
  function pageOutlet() {
    const decl = document.querySelector('[data-bz-page-id][hx-boost="true"]');
    const sel = decl && decl.getAttribute("hx-target");
    const target = sel && document.querySelector(sel);
    return target ? { target: target, swap: decl.getAttribute("hx-swap") } : null;
  }

  function wireScroll() {
    if (window.htmx) window.htmx.config.scrollIntoViewOnBoost = false;
    const state = window.history.state;
    stampScrollEntry((state && state[SCROLL_KEY]) || newScrollKey());

    // A push: the page left keeps its positions, then its key (htmx has
    // just rewritten its state). Only a swap INTO an outlet is a
    // navigation; a zone that pushes its address (a filter) is not.
    document.body.addEventListener("htmx:beforeHistoryUpdate", function (e) {
      const history = e.detail && e.detail.history;
      if (!history || history.type !== "push") return;
      rememberScroll();
      stampScrollEntry(scrollEntry);
      const t = e.detail.target;
      if (t && t.nodeType === 1 && (t.matches("[data-bz-outlet]")
          || t.querySelector("[data-bz-outlet]"))) {
        scrollPending = { target: t, pos: null };
      }
    });
    document.body.addEventListener("htmx:pushedIntoHistory", function () {
      stampScrollEntry(newScrollKey());
    });

    // The navigation's swap is in: the positions left there, else the
    // top — or the anchor (htmx scrolls to it again at settle: same
    // place).
    document.body.addEventListener("htmx:afterSwap", function (e) {
      const pending = scrollPending;
      if (!pending || e.detail.target !== pending.target) return;
      scrollPending = null;
      if (pending.pos) return setScrollBack(pending.pos);
      window.scrollTo(0, 0);
      scrollersOf(pending.target).forEach(function (el) { el.scrollTop = 0; });
      const id = decodeURIComponent(window.location.hash.slice(1));
      const anchor = id && document.getElementById(id);
      if (anchor) anchor.scrollIntoView({ block: "start" });
    });

    // Back / forward. The DOM is still the page left, so its positions
    // are read here. htmx keeps the entries that are not its own
    // (``#anchor`` jumps, handled by the browser). htmx sets
    // ``onpopstate`` at ``DOMContentLoaded`` — AFTER this boot, which
    // runs as soon as the deferred runtime is evaluated (``index.js``):
    // taken then (or at ``load``, if this boot came later), never before.
    let htmxPopstate = null;
    function takePopstate() {
      if (window.onpopstate === onPopstate) return;
      htmxPopstate = window.onpopstate;
      window.onpopstate = onPopstate;
    }
    if (document.readyState === "complete") takePopstate();
    else {
      document.addEventListener("DOMContentLoaded", takePopstate);
      window.addEventListener("load", takePopstate);
    }
    function onPopstate(e) {
      rememberScroll();
      const key = e.state && e.state[SCROLL_KEY];
      if (key) scrollEntry = key;
      else stampScrollEntry(newScrollKey());
      if (!(e.state && e.state.htmx)) {
        if (htmxPopstate) htmxPopstate.call(window, e);
        return;
      }
      const outlet = pageOutlet();
      if (!outlet || !window.htmx) {
        window.location.reload();
        return;
      }
      scrollPending = { target: outlet.target, pos: scrollPositions.get(scrollEntry) || null };
      window.htmx.ajax("GET", window.location.pathname + window.location.search, {
        source: outlet.target,
        target: outlet.target,
        swap: outlet.swap || "innerHTML",
      });
    }
  }

  $bz._wireBridge = function () {
    wireScroll();

    /* One field into a request body, as a form submit would write it. */
    function appendField(data, el) {
      const type = (el.type || "").toLowerCase();
      if (/^(submit|button|reset|image)$/.test(type)) return;
      if ((type === "checkbox" || type === "radio") && !el.checked) return;
      if (type === "file") {
        for (const f of el.files) data.append(el.name, f);
      } else if (el.tagName === "SELECT" && el.multiple) {
        for (const o of el.selectedOptions) data.append(el.name, o.value);
      } else {
        data.append(el.name, el.value);
      }
    }

    /* Where a boosted link goes: the page's outlet (``pageOutlet``),
     * whatever the link's ancestors say. htmx resolves a link's target
     * by INHERITANCE, and a component carrying an action sets
     * ``hx-target="#bz-sink"`` on its element (``events.py``): a link
     * inside it — a card ``on_click``, a dialog's ``on_close`` — would go
     * to the hidden sink, the address changing and the page not.
     * ``configRequest`` names the outlet to
     * the server, ``beforeSwap`` swaps it there: htmx reads the target
     * back from neither earlier. Gate:
     * ``tests/runtime_js/test_a_link_is_boosted_wherever_it_sits.py``. */
    function boostedTarget(detail) {
      if (!detail.boosted) return null;
      const outlet = pageOutlet();
      return outlet && outlet.target !== detail.target ? outlet : null;
    }

    document.body.addEventListener("htmx:beforeSwap", function (e) {
      const config = e.detail.requestConfig;
      const to = config && config._bzBoosted;
      if (!to || !to.target.isConnected) return;
      e.detail.target = to.target;
      if (to.swap) e.detail.swapOverride = to.swap;
    });

    document.body.addEventListener("htmx:configRequest", function (e) {
      // An inert control posts NOTHING. It is inertness's third guard
      // (the other two — `bz-on:` handlers and native navigation — live
      // in directives.js, which owns the rule) and it is here because
      // this is the transport boundary: this module is "the ONLY module
      // that wires HTMX events".
      //
      // MEASURED before being written, not read in a doc: htmx 2.0.4
      // does emit `configRequest` then gives the request up on
      // `preventDefault` — the probe's unblocked witness, for its part,
      // leaves. Cf. `tests/audit/probe_configrequest_is_cancelable.py`.
      if ($bz._inert(e.detail.elt)) {
        e.preventDefault();
        return;
      }
      // A BOOSTED navigation that crosses the mobile threshold cannot
      // be a partial swap. `Screen().is_mobile` is a SERVER `if`, and
      // the layout carrying it lives OUTSIDE `[data-bz-outlet]`:
      // swapping the outlet would leave the desktop sidebar in place on
      // a phone viewport, indefinitely, until the next hard load. The
      // `<head>` script does not replay either, so the cookie stays
      // stale and even the server does not know.
      //
      // We resync the cookie and give the navigation back to the
      // browser: a full load re-renders the shell from the fresh cookie.
      // Nothing fires on a resize, only on a navigation the user asked
      // for, exactly like an F5.
      //
      // Restricted to `<a>`: the GET of `@refreshable` zones and of the
      // SSE refetch also come through here and must never become a
      // navigation. `$bzScreenSync` is defined by the `<head>` script
      // (`render/shell.py`) — absent from a custom shell, we do nothing.
      if (
        String(e.detail.verb).toLowerCase() === "get" &&
        e.detail.elt &&
        e.detail.elt.tagName === "A" &&
        typeof window.__SCREEN_SYNC_FN__ === "function" &&
        !window.__SCREEN_SYNC_FN__()
      ) {
        e.preventDefault();
        window.location.assign(
          e.detail.path || e.detail.elt.getAttribute("href"),
        );
        return;
      }
      const boosted = boostedTarget(e.detail);
      if (boosted) {
        e.detail._bzBoosted = boosted;
        e.detail.headers["HX-Target"] = boosted.target.id;
      }
      // The client-state snapshot rides ONLY on action POSTs (it's
      // form-data for the handler). Nav GETs (hx-boost partial-nav) and
      // the SSE realtime refetch must NOT carry it — otherwise
      // hx-push-url leaks the entire client store into the address-bar
      // query string (?ColorScheme.default.mode=dark&HubFilter...).
      if (String(e.detail.verb).toLowerCase() === "post") {
        injectParameters(e.detail);
      }
      e.detail.headers["X-Bretzel-Protocol"] = $bz.version;
      if ($bz._csrf) e.detail.headers["X-Bretzel-CSRF"] = $bz._csrf;
      if ($bz._pageId) e.detail.headers["X-Bretzel-Page-ID"] = $bz._pageId;
      // Who writes. The server uses it so as NOT to re-broadcast to
      // this tab what it has just answered it — cf. `$bz._tabId`.
      if ($bz._tabId) e.detail.headers["X-Bretzel-Tab"] = $bz._tabId;
      // Tell the server which @refreshable zones this document
      // carries.
      //
      // Without it, it queues EVERY zone declared on a changed state
      // class — including those of other pages — renders them, sends
      // them, and we throw them away for want of a target.
      //
      // On action POSTs, and on a navigation into an outlet: there, the
      // zones OUTSIDE it — the shell's — that read a page state are
      // redrawn for the page arrived at (``_shell_zones`` in
      // ``render/pipeline.py``). The zones inside the outlet are not listed:
      // the page brings them. Any other GET — a zone's own refetch, the
      // SSE one — sends nothing.
      //
      // We read the DOM at the instant of the request, not a list the
      // server would have given us at render: an OOB swap may have
      // introduced a zone since, and a frozen list would condemn it
      // never to refresh again.
      const verb = String(e.detail.verb).toLowerCase();
      const into = boosted ? boosted.target : e.detail.target;
      const outlet =
        verb === "get" && into && into.nodeType === 1 && into.hasAttribute("data-bz-outlet")
          ? into
          : null;
      if (verb === "post" || outlet) {
        const zones = document.querySelectorAll("[data-bz-zone]");
        if (zones.length) {
          const ids = [];
          for (const z of zones) {
            if (outlet && outlet.contains(z)) continue;
            // ``id`` alone, or ``id:fingerprint`` when we know what
            // the zone carries: the server uses it to KEEP QUIET about a
            // zone whose fresh render would be identical. The
            // fingerprint comes from IT, it is never computed here — an
            // absent or stale fingerprint can therefore only make the
            // zone be re-sent, never wrongly suppressed.
            ids.push($bz._zoneEntry(z));
          }
          if (ids.length) e.detail.headers["X-Bretzel-Zones"] = ids.join(",");
        }
      }
      // A form's fields that ``bz-teleport`` carried out of it (cf.
      // ``teleportedFieldsOf``): htmx built the body from
      // ``form.elements`` and never saw them. ``parameters`` is a view
      // over ``formData``, which htmx reads back after this event.
      const elt = e.detail.elt;
      const form =
        elt && elt.nodeType === 1 &&
        (elt.tagName === "FORM"
          ? elt
          : String(e.detail.verb).toLowerCase() !== "get" && elt.closest("form"));
      if (form && e.detail.formData && $bz._teleportedFieldsOf) {
        for (const el of $bz._teleportedFieldsOf(form)) appendField(e.detail.formData, el);
      }
      const carrier = e.detail.elt && e.detail.elt.closest("[data-bz-sig]");
      // An action POST WITH NO signature carrier does not leave.
      //
      // It is not about caution: the request is already lost. On the
      // Python side, `action_attrs` is the ONLY place that writes an
      // `hx-post`, and it sets `data-bz-sig` in the same dict — so every
      // htmx POST is an action, and every action is born signed. Not
      // finding a carrier at `configRequest` time means one thing only:
      // the element was DETACHED between the trigger and now, typically
      // by the morph of a `@refreshable` zone.
      //
      // Letting it leave costs. The server refuses
      // any invalid signature with an `_error: reload`, which
      // `handleError` executes — so an already obsolete request RELOADS
      // THE WHOLE PAGE: an autoplay ticks while a flip re-renders the
      // panel, the node disappears, the POST leaves bare, 403, reload.
      //
      // Restricted to POST: a boosted nav and an SSE zone's refetch are
      // GETs, they never have a signature and must pass.
      if (!carrier && String(e.detail.verb).toLowerCase() === "post") {
        e.preventDefault();
        return;
      }
      if (carrier) {
        e.detail.headers["X-Bz-Sig"] = carrier.getAttribute("data-bz-sig");
        const ts = carrier.getAttribute("data-bz-ts");
        if (ts) e.detail.headers["X-Bz-Ts"] = ts;
      }
    });

    /* Changes to elements with no ``id`` (``render/zone_diff.at_position``):
     * ``<__AT_TAG__ zone anchor path shape>`` holds the new element in a
     * template. Walk from the anchor by element position, skipping what
     * the runtime inserted itself (``data-bz-row``: ``bz-for`` rows,
     * ``bz-if`` mounts), check each level's shape, morph. A walk that
     * does not land — the DOM moved under us — forgets the zone's
     * fingerprint (the base check of ``_adoptZoneHashes`` then keeps it
     * forgotten) and asks a subscribed zone again at once; any other zone
     * ships whole at the next exchange. */
    // Mirror of ``zone_diff.shape_of``: djb2 over the children's tags.
    function shapeOf(kids) {
      let h = 5381;
      const text = kids.map((k) => k.localName).join(",");
      for (let i = 0; i < text.length; i++) h = (((h << 5) + h) + text.charCodeAt(i)) >>> 0;
      return h.toString(16);
    }
    function settle(node) {
      if (window.htmx) window.htmx.process(node);
      $bz._scan(node);
      // Adopt server-authoritative signals (``_serverSync`` keys) from
      // the freshly-morphed bz-data — runs AFTER the rescan so the
      // bz-attr effects are live when the value signal changes.
      $bz._resyncScopes(node);
    }
    /* A walk that did not land: forget the zone's fingerprint and ask a
     * subscribed zone again; any other zone ships whole next time. */
    function lost(tag) {
      // Said out loud: a patch refused for a node inserted by hand
      // without ``data-bz-row`` would otherwise fail in silence. The zone
      // is still redrawn whole.
      console.warn("bz: a patch of zone " + tag.getAttribute("zone") + " found the page "
        + "changed under it (a node added outside the server's render? mark it "
        + "data-bz-row) — redrawing the zone whole");
      const host = document.querySelector('[data-bz-zone][bz-id="' + tag.getAttribute("zone") + '"]');
      if (!host) return;
      host.removeAttribute("data-bz-h");
      const url = host.getAttribute("data-bz-subscribe-url");
      if (url && $bz._refetchZone) $bz._refetchZone(host, url);
    }
    /* A parent whose list of children changed, nothing else
     * (``zone_diff.ListPatch``): ``#row-2`` keeps the child with that
     * id, wherever it is now (a drag and drop moved it already), ``k3``
     * keeps the old child 3, ``m3`` keeps it and morphs it into the next
     * template, ``n`` inserts the next template. A rank counts the
     * children without id only. An id the parent does not hold is taken
     * where the browser holds it — another list of the zone, or one this
     * run just removed (``orphans``) — moved here and morphed: a card
     * dragged to another column keeps its element. The old children not
     * kept go; the kept ones are MOVED, never rebuilt — their state and
     * their listeners stay. A rank needs the parent to hold ``count``
     * children without id first, or nothing is touched. */
    /* An id a patch may name — the server's rule exactly
     * (``protocol.ADDRESSABLE_ID``). Any other element, ``id="137"``
     * included, is ranked by position: counted otherwise, a list holding
     * one would never match the count the server sent. */
    const ADDRESSABLE = /__ADDRESSABLE_ID__/;
    const named = (el) => !!el.id && ADDRESSABLE.test(el.id);
    function applyList(parent, tag, fresh, orphans) {
      const kids = counted(parent);
      const ranked = kids.filter((c) => !named(c));
      const text = tag.getAttribute("list");
      const ops = text ? text.split(" ") : [];
      if (ops.some((op) => op[0] === "k" || op[0] === "m")
          && ranked.length !== Number(tag.getAttribute("count"))) return false;
      const byId = (id) => {
        const el = kids.find((kid) => kid.id === id) || orphans.get(id) || document.getElementById(id);
        return el && !el.contains(parent) ? el : null;
      };
      const next = [];
      const morphs = [];
      const added = [];
      let f = 0;
      for (const op of ops) {
        if (op === "n") {
          const tpl = fresh[f++];
          const moved = named(tpl) ? byId(tpl.id) : null;
          if (moved) {
            morphs.push([moved, tpl]);
            next.push(moved);
          } else {
            const node = document.importNode(tpl, true);
            next.push(node);
            added.push(node);
          }
          continue;
        }
        const old = op[0] === "#" ? byId(op.slice(1)) : ranked[Number(op.slice(1))];
        if (!old) return false;
        if (op[0] === "m") morphs.push([old, fresh[f++]]);
        next.push(old);
      }
      const keep = new Set(next);
      for (const node of next) for (const name of $bz._witnesses) node.removeAttribute(name);
      for (const kid of kids) {
        if (keep.has(kid)) continue;
        kid.remove();
        if (kid.id) orphans.set(kid.id, kid);
      }
      let prev = null;
      for (const node of next) {
        const want = prev ? prev.nextSibling : parent.firstChild;
        if (node !== want) parent.insertBefore(node, want);
        prev = node;
      }
      for (const [old, tpl] of morphs) morphInto(old, tpl);
      for (const node of added) settle(node);
      return true;
    }
    /* The children the server counts: not what the runtime inserted
     * itself (``bz-for`` rows, ``bz-if`` mounts carry ``data-bz-row``). */
    function counted(el) {
      return Array.from(el.children).filter((c) => !c.hasAttribute("data-bz-row"));
    }
    function morphInto(el, tpl) {
      const live = window.Idiomorph.morph(el, tpl, { morphStyle: "outerHTML" })
        .find((n) => n.nodeType === 1);
      if (live) settle(live);
    }
    /* Where a ``<bz-at>`` points: its anchor, then each step of its path,
     * as long as every level has the shape the server saw. An empty path
     * is the anchor itself (``"".split(".")`` would be one step). */
    function target(tag) {
      let el = document.getElementById(tag.getAttribute("anchor"));
      const shapes = (tag.getAttribute("shape") || "").split(".");
      const path = tag.getAttribute("path") || "";
      const steps = path ? path.split(".") : [];
      for (let i = 0; i < steps.length && el; i++) {
        const kids = counted(el);
        el = shapeOf(kids) === shapes[i] ? kids[Number(steps[i])] : null;
      }
      return el;
    }
    /* Each ``<bz-at>`` of the sink (``zone_diff.ship``): a list patch, or
     * one element morphed where it is. */
    function applyPositionPatches() {
      const sink = document.getElementById("__SINK_ID__");
      if (!sink) return;
      const orphans = new Map();   // removed by a list this run: another may take them
      for (const tag of sink.querySelectorAll("__AT_TAG__")) {
        tag.remove();
        const el = target(tag);
        const fresh = Array.from(tag.children)
          .filter((c) => c.tagName === "TEMPLATE")
          .map((c) => c.content.firstElementChild);
        if (!el || !window.Idiomorph) lost(tag);
        else if (tag.hasAttribute("list")) {
          if (!applyList(el, tag, fresh, orphans)) lost(tag);
        } else if (fresh[0] && el.tagName === fresh[0].tagName) morphInto(el, fresh[0]);
        else lost(tag);
      }
    }

    /* Replace, do not morph, an element marked __REPLACE_ATTR__.
     * idiomorph pairs the children of a node one by one, looking for the
     * best match among siblings that carry no id — quadratic on a large
     * blob. A highlighted ``ui.code`` is thousands of ``<span>``: the morph
     * would freeze the page for seconds. Such a blob holds no client
     * state, so its content is swapped whole and its attributes synced;
     * returning ``false`` tells idiomorph to leave the node alone after
     * that. Hooked on the DEFAULTS, so both paths reach
     * it: htmx's morph extension and ``applyPositionPatches`` above. */
    /* A node RECYCLED into an identified element is a new node: no
     * transition. idiomorph's soft match takes an old element WITHOUT
     * id for any new element of the same tag, identified or not — a
     * painted ``hstack`` can become a closed dialog's backdrop, and its
     * opacity animate from 1 to 0: a black veil over the screen. A node
     * CREATED has no value before, so it never transitions; one recycled
     * must not either.
     * The node and its subtree take their values with ``transition:
     * none``, then get their transitions back in a microtask, once the
     * new values are computed. A node morphed into ITSELF (same id) keeps
     * its transitions: that is how a panel closes, animated.
     * Gate: tests/runtime_js/test_a_recycled_node_does_not_animate.py. */
    const rebirths = new WeakSet();
    const reborn = [];
    function settleReborn() {
      // Computing the style now fixes the new values without transition.
      document.documentElement.getBoundingClientRect();
      for (const [el, was] of reborn.splice(0)) {
        if (was) el.style.transition = was;
        else el.style.removeProperty("transition");
        if (el.getAttribute("style") === "") el.removeAttribute("style");
      }
    }

    if (window.Idiomorph && window.Idiomorph.defaults) {
      const callbacks = window.Idiomorph.defaults.callbacks;
      const priorAfter = callbacks.afterNodeMorphed;
      callbacks.afterNodeMorphed = function (node) {
        if (rebirths.has(node)) {
          rebirths.delete(node);
          if (!reborn.length) queueMicrotask(settleReborn);
          for (const el of [node, ...node.querySelectorAll("*")]) {
            if (!el.style) continue;
            reborn.push([el, el.style.transition]);
            el.style.transition = "none";
          }
        }
        return priorAfter.apply(this, arguments);
      };
      const prior = callbacks.beforeNodeMorphed;
      callbacks.beforeNodeMorphed = function (old, fresh) {
        if (old.nodeType === 1 && fresh.nodeType === 1 && fresh.id && !old.id) {
          rebirths.add(old);
        }
        if (old.nodeType === 1 && fresh.nodeType === 1
            && old.hasAttribute("__REPLACE_ATTR__")) {
          if (old.outerHTML !== fresh.outerHTML) {
            Array.from(old.attributes).forEach(function (a) {
              if (!fresh.hasAttribute(a.name)) old.removeAttribute(a.name);
            });
            Array.from(fresh.attributes).forEach(function (a) {
              if (old.getAttribute(a.name) !== a.value) old.setAttribute(a.name, a.value);
            });
            old.innerHTML = fresh.innerHTML;
          }
          return false;
        }
        return prior.apply(this, arguments);
      };
    }

    function afterSwap(e) {
      applyPatchTags();
      applyPositionPatches();
      let target = e.detail && e.detail.target ? e.detail.target : e.target;
      // An OOB swap that CHANGES a refreshable zone's ROOT TAG makes HTMX
      // REPLACE the node instead of morphing it in place — and the event
      // still reports the OLD, now-detached element. This happens whenever
      // a zone's single fused child changes element type across a refresh :
      // an empty-state ``ui.text`` (<span>) becoming a populated ``vstack``
      // (<div>), say. Scanning that stale node misses EVERY bz-* directive
      // in the freshly inserted subtree — the first tooltip's bz-teleport
      // never projects, a row's bz-model / bz-show never bind — and the
      // backlog only clears on the NEXT swap that happens to morph in place.
      // The replacement keeps the zone id, so re-resolve to the live node.
      if (target && target.id && !target.isConnected) {
        const live = document.getElementById(target.id);
        if (live) target = live;
      }
      if (target && target.nodeType === 1) {
        $bz._scan(target);
        $bz._resyncScopes(target);
      }
      $bz._sweepScopes();
      // The nodes this swap removed give back their effects, and what
      // their bz-init took outside them (document / window listeners).
      if ($bz._sweepDetached) $bz._sweepDetached();
      // Drop teleported panels (tooltip/overlay portals under <body>)
      // whose origin was removed by this swap — else they orphan.
      if ($bz._sweepTeleports) $bz._sweepTeleports();
      // A partial-nav swap (hx-boost) may have brought in a subscribe
      // zone on a page that had none at boot — open the SSE stream now.
      if ($bz._ensureSse) $bz._ensureSse();
    }
    for (const eventName of ["htmx:afterSwap", "htmx:oobAfterSwap"]) {
      document.body.addEventListener(eventName, afterSwap);
    }

    /* A ``redirect()`` that keeps the layout answers ``HX-Location``:
     * htmx fetches the new page into the outlet and returns BEFORE
     * swapping this response. Its out-of-band zones include the
     * layout's, which that navigation never redraws — left alone, they
     * keep their old version while ``_adoptZoneHashes`` takes the
     * fingerprint of the new one, and the next patch misses. Land them
     * first (``swapStyle: "none"`` keeps only the out-of-band parts);
     * the outlet's are replaced by the navigation anyway. */
    document.body.addEventListener("htmx:beforeOnLoad", function (e) {
      const xhr = e.detail && e.detail.xhr;
      if (!xhr || !xhr.getResponseHeader || !xhr.getResponseHeader("HX-Location")) return;
      if (xhr.responseText && window.htmx) {
        window.htmx.swap(document.body, xhr.responseText, { swapStyle: "none" });
      }
    });

    /* The witness's life cycle. ``htmx:afterRequest`` is the ONLY
     * disarm: htmx emits it in every exit case — success, 4xx/5xx,
     * network error, timeout, abort — so also listening to
     * ``sendError``/``timeout`` would decrement the counter twice and
     * would extinguish a second request still in flight on the same
     * key. */
    document.body.addEventListener("htmx:beforeRequest", function (e) {
      pendingKeys(e.detail.elt, e.detail).forEach(armPending);
      const busy = busyTarget(e.detail.elt, e.detail);
      if (busy) armBusy(busy);
    });

    /* The fingerprint of a zone lives ON its element (``data-bz-h``),
     * stamped by the server whenever it renders the zone whole; a
     * response that only patched or silenced the zone sends it in
     * ``X-Bretzel-Zone-Hashes``, with its base in ``X-Bretzel-Zone-Bases``.
     * Holding another base, we forget the fingerprint: the next exchange
     * ships the zone whole. Why: ``render/zone_diff.py``, "Crossed
     * responses".
     *
     * What that version READ (``data-bz-r``) rides along as a third part
     * — ``id:fingerprint:reads`` — so the server redraws the zone only
     * when a field THIS version read has changed. Absent, the server
     * falls back on what it learned itself: never wrongly silenced. */
    $bz._zoneEntry = function (zone) {
      const zid = zone.getAttribute("bz-id");
      const vu = zone.getAttribute("data-bz-h") || "";
      const lu = zone.getAttribute("data-bz-r");
      if (lu !== null) return zid + ":" + vu + ":" + lu;
      return vu ? zid + ":" + vu : zid;
    };
    function pairsOf(header) {
      const out = {};
      if (!header) return out;
      for (const morceau of header.split(",")) {
        const coupe = morceau.indexOf(":");
        if (coupe > 0) out[morceau.slice(0, coupe)] = morceau.slice(coupe + 1);
      }
      return out;
    }
    $bz._adoptZoneHashes = function (xhr) {
      const hashes = pairsOf(xhr.getResponseHeader("X-Bretzel-Zone-Hashes"));
      const bases = pairsOf(xhr.getResponseHeader("X-Bretzel-Zone-Bases"));
      for (const zid of Object.keys(hashes)) {
        const zone = document.querySelector('[data-bz-zone][bz-id="' + zid + '"]');
        if (!zone) continue;
        if (zid in bases && zone.getAttribute("data-bz-h") !== bases[zid]) {
          zone.removeAttribute("data-bz-h");
        } else {
          zone.setAttribute("data-bz-h", hashes[zid]);
        }
      }
    };
    document.body.addEventListener("htmx:afterRequest", function (e) {
      pendingKeys(e.detail.elt, e.detail).forEach(disarmPending);
      if (e.detail.elt && e.detail.elt.nodeType === 1) disarmBusy(e.detail.elt);

      /* The fingerprints of the zones this response has just shipped.
       * We KEEP them to present them again at the next request: the
       * server can then keep quiet about a zone whose fresh render would
       * be identical to what we are already showing.
       *
       * Nothing is computed here, and that is what makes the mechanism
       * safe: the fingerprint is that of the HTML the server sent. If
       * the DOM has changed since for another reason, the fingerprint
       * becomes wrong in the HARMLESS direction — the server will find a
       * difference and re-ship. */
      const xhr = e.detail && e.detail.xhr;
      if (!xhr || !xhr.getResponseHeader) return;

      /* A navigation starts a new page, with a fresh page state and its
       * own id (``render_context.py``). Adopt it: the actions that follow
       * must speak for the page SHOWN, not the one left — otherwise they
       * would find the old page's state again, the very defect the new
       * id closes. */
      const pageId = xhr.getResponseHeader("X-Bretzel-Page-ID");
      if (pageId) $bz._pageId = pageId;

      $bz._adoptZoneHashes(xhr);
    });

    /* A partial response has no <head>: its page title arrives in
     * ``HX-Trigger`` (``render/pipeline.py``), after every partial
     * navigation — a boosted link, a sidebar item, a ``redirect()``.
     * htmx dispatches a string value as ``detail.value``. */
    document.body.addEventListener("__TITLE_EVENT__", function (e) {
      const title = e.detail && e.detail.value;
      if (typeof title === "string") document.title = title;
    });

    document.body.addEventListener("htmx:responseError", function (e) {
      const text = e.detail.xhr ? e.detail.xhr.responseText || "" : "";
      // 4xx/5xx bodies are not swapped by HTMX, so the patch tags never
      // reach the DOM — extract them from the raw response text.
      const re = new RegExp("<" + PATCH_TAG + ">([\\s\\S]*?)</" + PATCH_TAG + ">", "g");
      let handled = false;
      let m;
      while ((m = re.exec(text)) !== null) {
        try {
          applyPayload(JSON.parse(m[1]));
          handled = true;
        } catch (err) {
          console.error("bz: malformed error <" + PATCH_TAG + ">", err);
        }
      }
      if (!handled) {
        $bz.notify({
          variant: "error",
          message: "Request failed (" + (e.detail.xhr ? e.detail.xhr.status : "?") + ")",
        });
      }
    });
  };
})();
