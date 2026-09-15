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
    /* Le focus initial RÉESSAIE frame par frame jusqu'à ce qu'il prenne.
     *
     * Ce n'est pas de la superstition : cet effet s'installe dans le flush
     * réactif qui vient de passer ``open`` à vrai, donc avant que le style
     * calculé ne bascule. Or ``focus()`` sur un élément en
     * ``visibility: hidden`` est un **no-op silencieux** — pas d'erreur,
     * pas de retour, rien. Relevé sur ``bench_dialog`` (2026-08-19), les
     * trois boutons du panneau : cachés à +1 ms, visibles à +16 ms.
     *
     * Un délai FIXE ne suffit pas, et c'est mesuré aussi : la version à
     * deux frames passait environ une fois sur trois — la frontière tombe
     * pile dans la fenêtre cachée, et elle bouge d'un run à l'autre. On
     * n'attend donc pas une durée, on attend le RÉSULTAT : on tente, on
     * vérifie que le focus a atterri, et on retente sinon.
     *
     * Sans ça, le trap était bien installé (``$el._bzTrap`` présent) et le
     * focus restait sur le déclencheur. Le contrat rétabli est écrit dans
     * ``dialog.py`` : « the first interactive child receives focus ».
     *
     * Le DOM est RE-INTERROGÉ à chaque tentative : entre l'installation et
     * la frame qui aboutit, un morph a pu remplacer le contenu du panneau,
     * et un nœud détaché se focus dans le vide. */
    let attempts = 0;
    function focusFirst() {
      if (!el.isConnected) return;
      const first = el.querySelector(FOCUSABLE);
      if (first) {
        first.focus();
        if (el.contains(document.activeElement)) return;
      }
      // ~20 frames (≈ 1/3 s) : au-delà, le panneau ne s'ouvrira pas.
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
  // Plancher de lisibilité d'un panneau ancré, en px. `matchWidth` ne
  // descend jamais sous cette largeur, quelle que soit l'ancre : un
  // `ui.select` posé dans une sidebar repliée en rail (`w-16`) rendait un
  // panneau de ~48 px où les libellés s'enroulaient lettre par lettre,
  // avec une barre de défilement horizontale (constaté sur `examples/crm`
  // le 2026-08-29). 192 px = `12rem` — la valeur que le dépôt donne déjà
  // à un panneau ancré : `min-w-[12rem]` chez `dropdown` et `popover`,
  // `min-w-48` pour la taille `sm` du `panel_free` de `combobox`.
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
        // Le plancher s'applique à l'ANCRE, pas au résultat : au-dessus
        // de `MIN_MATCHED_WIDTH`, `mw === a.width` et le comportement est
        // identique au byte près (c'est ce qui rend ce correctif sûr pour
        // les deux seuls appelants de `matchWidth`, Select et Combobox).
        // Le plancher lui-même est borné au viewport : sur un écran plus
        // étroit que 192 px, un panneau au plancher déborderait, et la
        // correction de bord plus bas (`Math.max(4, Math.min(...))`) ne
        // fait que le décaler, elle ne le rétrécit pas.
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

      /* …et OÙ est l'ancre dans le panneau, pour que la flèche la vise.
         Le milieu du panneau et le milieu du déclencheur coïncident tant
         que rien ne pousse le panneau ; le recadrage de bord juste
         au-dessus (`Math.max(4, Math.min(...))`) les sépare. La flèche
         était posée en `left-1/2` — donc au milieu de la bulle — et
         pointait à côté de son bouton dès qu'on approchait d'un bord.
         Mesuré le 2026-09-09 sur `examples/kanban` : déclencheur centré
         à 1468 px, flèche à 1443. */
      const centre =
        side === "top" || side === "bottom"
          ? a.left + a.width / 2 - left
          : a.top + a.height / 2 - top;
      // Bornée à l'intérieur du panneau : une flèche posée à 2 px du bord
      // dépasse de l'arrondi des coins et flotte à côté de la bulle.
      // 12 px couvre le rayon du panneau plus la demi-largeur de la
      // flèche (un carré de 8 px tourné de 45°, ~11 px de diagonale).
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

  /* ── L'adresse, côté client ────────────────────────────────────────
   *
   * Le pendant EXACT de ``push_url()`` côté serveur (server/navigation.py),
   * pour ce qui ne fait aucun aller-retour : un onglet bascule dans le
   * scope, le serveur n'en sait rien, donc l'en-tête ``HX-Push-Url`` ne
   * peut rien pour lui.
   *
   * ``pushState`` et pas ``replaceState`` — décision de l'utilisateur le
   * 2026-08-29 : « pushState pour les vues ». Un onglet EST une vue, donc
   * le retour doit y revenir. Une préférence d'affichage (une densité, un
   * thème) ne mérite pas une entrée d'historique et n'a rien à faire ici.
   *
   * On garde ``history.state`` intact : htmx y range le sien, et le lui
   * écraser casserait sa propre restauration sur les entrées qu'il a
   * créées.
   */
  function pushUrl(param, value) {
    const url = new URL(window.location.href);
    const next = value == null ? "" : String(value);
    if (next === "") url.searchParams.delete(param);
    else url.searchParams.set(param, next);
    if (url.href === window.location.href) return;
    window.history.pushState(window.history.state, "", url.href);
  }

  /* La valeur COURANTE d'un paramètre, ou ``null``. Lue à chaud plutôt
   * que mémorisée : après un retour, ``location`` a déjà bougé quand le
   * ``popstate`` nous parvient. */
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

    // ── Capture de pointeur — la famille pointer-drag ────────────────
    // Capturer, c'est dire au navigateur d'envoyer TOUS les événements
    // du pointeur à cet élément-là jusqu'au relâchement, même quand le
    // curseur en sort. Sans ça, le geste s'arrête au premier pixel qui
    // quitte la boîte — et une poignée fait quelques points de large.
    //
    // Les deux gardes ne sont pas de la superstition, et c'est pour
    // elles que ça vit ici plutôt que recopié :
    //   - ``pointerId !== undefined`` : un événement synthétique (un
    //     test, un script) n'en porte pas, et l'appel lèverait ;
    //   - le ``try`` : le navigateur refuse la capture si le pointeur
    //     n'est plus actif (relâché entre-temps, geste annulé par l'OS),
    //     et cette exception-là ne doit pas casser le geste en cours.
    //
    // Extrait le 2026-08-13, au 3ᵉ et 4ᵉ site (slider ×2, resizable ×2)
    // — le seuil que le dépôt s'est fixé, « deux fois une coïncidence,
    // trois fois un pattern ». Le prochain composant de la famille
    // pointer-drag (``signature_pad``) appelle ça, il ne le recopie pas.
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
    // Vide la sélection SANS fermer le panneau : c'est une commande DE
    // la barre d'en-tête, et une commande ne congédie pas ce qu'elle
    // commande. Avec un ``on_close=`` câblé, fermer ici POSTAIT la
    // sélection vide au serveur — cf. le filtre de colonne du datatable.
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
