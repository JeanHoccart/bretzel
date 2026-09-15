/* 00_index.js — bootstrap + window.$bz wiring.
 *
 * First in concatenation order but everything heavy runs at
 * DOMContentLoaded, after all modules have registered their pieces on
 * window.$bz. Bootstrap sequence (spec 03-runtime.md §00_index.js) :
 *
 *   1. Parse <bz-envelope> (one-shot bootstrap blob).
 *   2. Seed the global signal store from envelope.client_state.
 *   3. Register persistence adapters per instance (saved snapshots
 *      overlay envelope defaults).
 *   4. Wire the HTMX bridge listeners.
 *   5. Wire the OS color-scheme listener ($bz._osScheme signal).
 *   6. Scan the document : bz-data scopes + all bz-* directives.
 *      (L'ordre 5/6 était inversé dans ce commentaire jusqu'au
 *      2026-08-01 — le listener OS est câblé AVANT le scan.)
 *   7. Wire the SSE EventSource + data-bz-subscribe-* zones.
 *   8. Add .bz-ready on <html> (releases [bz-data]{visibility:hidden}),
 *      dispatch bz:ready.
 *
 * Public surface : window.$bz = { version, state, signal, effect,
 * computed, helpers, notify }.
 */
(function () {
  "use strict";
  const $bz = (window.$bz = window.$bz || {});
  $bz.version = "v1.0";

  // Le vocabulaire de config de transport que le CLIENT consomme, déclaré
  // en UN endroit et copié en boucle plus bas. C'est un point d'ancrage
  // SYNTAXIQUE, pas du style : la gate
  // ``tests/consistency/test_client_state_transport_config.py`` lit ce
  // littéral pour vérifier que le serveur émet bien tout ce qu'on lit.
  // Sans lui, elle devait deviner les lectures à la regex (``cfg.<x>``),
  // ce qui ramassait ``cfg.mode`` / ``cfg.weekstart`` du calendrier — et
  // compensait par une liste de noms écrite à la main, donc ne couvrait
  // PAS la clé suivante. Même rôle que le ``kind === "…"`` sur lequel
  // s'ancre la gate soeur des kinds d'erreur.
  const CONFIG_KEYS = ["send_to_server"];

  // Adopter la config de transport d'UNE instance. Deux appelants, un
  // seul corps : le boot (depuis l'``<bz-envelope>``) et le bridge
  // (depuis le ``<bz-patch>`` de seed d'une nav partielle). Avant le
  // 2026-08-15 ce corps n'existait qu'inline dans le boot, donc un
  // ``ClientState`` découvert en nav partielle recevait ses champs sans
  // sa config : ``send_to_server`` ignoré, et ``persist`` sans
  // adaptateur — donc une valeur sauvegardée jamais relue.
  //
  // ⚠️ À appeler APRÈS avoir semé les champs de l'instance : ``register``
  // superpose le snapshot déjà stocké, qui doit gagner sur les défauts du
  // serveur (« the user's browser knows better », 04_persistence.js).
  function adoptConfig(path, entry) {
    const cfg = {};
    for (const key of CONFIG_KEYS) cfg[key] = entry[key];
    $bz._config[path] = cfg;
    $bz._persistence.register(path, entry.persist || "memory");
  }
  $bz._adoptConfig = adoptConfig;

  // ── Global typed store : "Class.key.field" → signal ────────────────
  const flat = new Map();
  $bz._store = {
    entries() {
      return flat.entries();
    },
    get(path) {
      // Auto-create on first read so effects subscribe even before the
      // first patch creates the field.
      if (!flat.has(path)) flat.set(path, $bz.signal(undefined));
      return flat.get(path).get();
    },
    peek(path) {
      return flat.has(path) ? flat.get(path).peek() : undefined;
    },
    set(path, value) {
      if (!flat.has(path)) flat.set(path, $bz.signal(value));
      else flat.get(path).set(value);
      if ($bz._persistence) $bz._persistence.notify(path, value);
    },
    // Poser une valeur INITIALE : ne fait rien si le champ en a déjà une.
    //
    // C'est ce qui sépare « semer » de « pousser », et la différence a
    // coûté le mode de couleur de l'utilisateur : à chaque navigation
    // partielle, le serveur ré-émet TOUTES les instances de la page
    // (`include_unchanged=True`) — avec ses valeurs à lui, c'est-à-dire
    // les défauts, puisqu'il ne peut pas connaître celles du navigateur.
    // Un `set` les écrasait, et comme `set` notifie la persistance, le
    // défaut partait dans localStorage AVANT que `adoptConfig` n'aille y
    // relire le snapshot. Le choix de l'utilisateur était détruit, pas
    // seulement masqué.
    //
    // `undefined` compte comme absent : `get()` auto-crée un signal vide
    // pour qu'un effet puisse s'abonner avant le premier patch, donc
    // l'existence du signal ne dit pas qu'il porte une valeur.
    seed(path, value) {
      if (flat.has(path) && flat.get(path).peek() !== undefined) return;
      this.set(path, value);
    },
    fieldsOf(instancePath) {
      const prefix = instancePath + ".";
      const out = {};
      for (const [path, sig] of flat.entries()) {
        if (path.startsWith(prefix)) out[path.slice(prefix.length)] = sig.peek();
      }
      return out;
    },
  };

  // $bz.state.Class.key.field — 3-level proxy over the flat store.
  function level(prefix, depth) {
    return new Proxy(
      {},
      {
        get(_t, key) {
          if (typeof key !== "string") return undefined;
          const path = prefix ? prefix + "." + key : key;
          if (depth === 2) return $bz._store.get(path);
          return level(path, depth + 1);
        },
        set(_t, key, value) {
          if (depth !== 2) {
            throw new Error("bz: only leaf fields of $bz.state are assignable");
          }
          $bz._store.set(prefix + "." + key, value);
          return true;
        },
      },
    );
  }
  $bz.state = level("", 0);

  // ── Notifications ───────────────────────────────────────────────────
  $bz.notify = function (payload) {
    document.dispatchEvent(new CustomEvent("bz:notify", { detail: payload }));
  };

  // ── Bootstrap ───────────────────────────────────────────────────────
  // SSE opens LAZILY : the EventSource is established the first time a
  // subscribe zone is present — at boot OR after a partial-nav swap that
  // brings one in (hx-boost into the outlet). Without this, landing on a
  // page with no subscribe zone (a list / hub) then boost-navigating to a
  // subscribed page (the stepper) would never open the stream — the
  // runtime only boots once, and the old ``if (!zones.length) return``
  // bailed out for good. ``$bz._ensureSse`` is re-called from the bridge's
  // afterSwap, so a zone arriving via partial nav wires up.
  let _sseUrl = null;
  let _sseSource = null;

  /* L'identité de CET onglet, tirée une fois par chargement de page.
     Elle ne désigne rien côté serveur, ne survit pas à la fermeture de
     l'onglet, et sert à une seule chose : permettre au serveur de ne PAS
     rediffuser à celui qui vient d'écrire ce qu'il vient de recevoir.
     Sans elle, cocher une case sur un tableau partagé coûtait cinq
     requêtes au lieu d'une — l'action, puis une re-lecture par zone
     abonnée, chacune renvoyant exactement ce que la première avait
     livré (mesuré sur `examples/kanban` : 354 Ko pour 177 Ko utiles).

     `crypto.randomUUID` n'est pas garanti hors contexte sécurisé — un
     `http://192.168.x.x` de test le perd — d'où le repli. La valeur n'a
     aucune exigence cryptographique : elle doit seulement être unique
     parmi les onglets ouverts d'une même personne. */
  $bz._tabId = (function () {
    try {
      if (window.crypto && window.crypto.randomUUID) {
        return window.crypto.randomUUID();
      }
    } catch (e) { /* contexte non sécurisé */ }
    return (Date.now().toString(36) + Math.random().toString(36).slice(2, 10));
  })();

  // ── Le refetch d'UNE zone abonnee ────────────────────────────────
  //
  // ⚠️ Ceci s'ecrivait, jusqu'au 2026-09-04 :
  //
  //     window.htmx.ajax("GET", url, { swap: "none" })
  //
  // Sans ``source``, htmx rattache la requete a ``document.body`` —
  // donc les N zones d'une page partagent UN element, et son
  // ``hx-sync`` implicite les fait se supprimer les unes les autres.
  // Mesure sur trois zones abonnees au meme etat, sur un client qui ne
  // recoit QUE le flux (pas les swaps OOB de sa propre action) :
  //
  //     tour 1   a=5    b=0    c=5     (attendu 5 partout)
  //     tour 2   a=5    b=0    c=10    (attendu 10)
  //     tour 3   a=10   b=0    c=15    (attendu 15)
  //
  // La zone du MILIEU ne se rafraichit jamais, la premiere reste un
  // tour en arriere, seule la derniere est juste. Ce n'est pas une
  // lenteur, c'est de la donnee FAUSSE affichee indefiniment — et rien
  // ne le signale, ni console, ni reseau : les requetes perdues n'ont
  // jamais ete emises.
  //
  // ``source: zone`` rend a chaque zone son propre cycle de requete.
  //
  // ── Et la coalescence, qui est l'autre moitie ─────────────────────
  //
  // Le meme evenement SSE reveille tous les clients a la meme
  // milliseconde, et deux signaux rapproches valent deux requetes dont
  // la premiere decrit deja un etat perime. D'ou une fenetre par zone
  // (on garde la DERNIERE demande) et un decalage aleatoire par client
  // (on etale la horde).
  //
  // Les deux nombres sont petits a dessein : au-dela, un « temps reel »
  // cesse d'en etre un. 40 ms de fenetre tiennent une rafale de
  // signaux, 60 ms d'etalement suffisent a desynchroniser des clients
  // que le meme evenement reveille ensemble.
  const REFETCH_WINDOW_MS = 40;
  const REFETCH_SPREAD_MS = 60;

  // Le decalage est tire UNE fois par page : le re-tirer a chaque
  // evenement re-synchroniserait les clients en moyenne, ce qui est
  // exactement ce qu'on cherche a eviter.
  const _refetchJitter = Math.random() * REFETCH_SPREAD_MS;

  // Cle par ELEMENT : une zone remplacee par un morph perd son entree
  // avec lui, et n'herite pas du minuteur de l'ancienne.
  const _refetchPending = new WeakMap();

  function refetchZone(zone, url) {
    let state = _refetchPending.get(zone);
    if (!state) {
      state = { timer: null };
      _refetchPending.set(zone, state);
    }
    // Une demande plus recente remplace celle qui attendait : elles
    // decrivent le meme etat final, et seule la derniere le connait.
    if (state.timer) clearTimeout(state.timer);
    state.timer = setTimeout(function () {
      state.timer = null;
      window.htmx.ajax("GET", url, { source: zone, swap: "none" });
    }, REFETCH_WINDOW_MS + _refetchJitter);
  }
  $bz._refetchZone = refetchZone;

  function ensureSse() {
    if (_sseSource || !_sseUrl) return;
    if (!document.querySelector("[data-bz-subscribe-state]")) return;
    // Framework-owned ``LiveConnection`` builtin ClientState : mirror the
    // EventSource connection into a store cell apps can bind a live/offline
    // indicator to (``visible=LiveConnection().connected``). Seeded here (not at
    // boot) so only pages that actually open the stream carry it. Starts
    // false ; ``open`` flips it true, ``error`` (transient drop) false —
    // EventSource auto-reconnects and fires ``open`` again.
    $bz._persistence.register("LiveConnection.default", "memory");
    $bz._store.set("LiveConnection.default.connected", false);
    _sseSource = new EventSource(_sseUrl);
    _sseSource.addEventListener("open", function () {
      $bz._store.set("LiveConnection.default.connected", true);
    });
    _sseSource.addEventListener("error", function () {
      $bz._store.set("LiveConnection.default.connected", false);
    });
    _sseSource.addEventListener("state-dirty", function (event) {
      const qualname = event.data;
      for (const zone of document.querySelectorAll("[data-bz-subscribe-state]")) {
        // A broadcast zone lists ALL its deps (space-separated) ; refetch
        // when the dirtied state is one of them.
        const states = zone.getAttribute("data-bz-subscribe-state").split(" ");
        if (!states.includes(qualname)) continue;
        const url = zone.getAttribute("data-bz-subscribe-url");
        if (url && window.htmx) refetchZone(zone, url);
      }
    });
  }
  $bz._ensureSse = ensureSse;

  function boot() {
    let config = null;
    // "bz-envelope" is substituted at build time from protocol.py.
    const envelope = document.querySelector("bz-envelope");
    if (envelope) {
      try {
        config = JSON.parse(envelope.textContent);
      } catch (e) {
        console.error("bz: malformed <bz-envelope>", e);
      }
    }
    $bz._config = {};
    if (config) {
      const clientState = config.client_state || {};
      for (const path of Object.keys(clientState)) {
        const entry = clientState[path];
        // Les champs D'ABORD, la config ENSUITE : ``adoptConfig`` appelle
        // ``register``, qui superpose le snapshot stocké — il doit écraser
        // les défauts du serveur, pas l'inverse.
        const fields = entry.fields || {};
        for (const field of Object.keys(fields)) {
          $bz._store.set(path + "." + field, fields[field]);
        }
        adoptConfig(path, entry);
      }
      $bz._csrf = config.csrf || null;
      // L'identite de page, que le pont pose en en-tete sur chaque
      // action. Sans elle, le serveur en forge une neuve et l'action
      // repart avec un etat de scope ``page`` VIERGE. Elle n'arrivait
      // jusque-la que par le ``hx-headers`` du conteneur de page, dont
      // un panneau teleporte dans <body> est sorti — d'ou un handler de
      // dropdown / dialog / drawer qui perdait l'etat en silence.
      $bz._pageId = config.page_id || null;
      $bz._endpoints = config.endpoints || {};

      // ── L'adresse, corrigee ────────────────────────────────────────
      //
      // Un etat de portee ``session`` se souvient d'un tri ou d'un
      // filtre par-dela les navigations : revenir sur ``/comptes`` nu
      // rend une vue triee sous une adresse qui n'en dit rien, et le
      // lien copie montre autre chose chez qui le recoit. Le serveur
      // sait les deux et pose ici l'adresse juste.
      //
      // ``replaceState`` et PAS ``pushState`` : corriger n'est pas
      // naviguer. Empiler une entree a chaque chargement rendrait le
      // bouton retour inutilisable — il faudrait deux clics pour un
      // mouvement.
      //
      // ``history.state`` est preserve : htmx y range le sien, et le lui
      // ecraser casserait sa restauration sur les entrees qu'il a creees.
      if (config.address) {
        try {
          window.history.replaceState(
            window.history.state, "", config.address,
          );
        } catch (e) {
          // Une adresse refusee (origine differente) ne doit pas empecher
          // la page de booter : l'adresse restera muette, la vue est
          // juste. On degrade, on ne casse pas.
          console.error("bz: adresse non corrigeable", config.address, e);
        }
      }
    }

    $bz._wireBridge();

    // OS color-scheme derived signal — bz-effects depending on both
    // ColorScheme.mode and the OS preference re-run on either change.
    const osDark = window.matchMedia("(prefers-color-scheme: dark)");
    $bz._osScheme = $bz.signal(osDark.matches ? "dark" : "light");
    osDark.addEventListener("change", function () {
      $bz._osScheme.set(osDark.matches ? "dark" : "light");
    });

    // Framework-owned color scheme. ColorScheme is a builtin ClientState,
    // not app state — so the app never has to instantiate it. Guarantee
    // its ``local`` persistence adapter + store cell exist even when the
    // envelope never carried it (no ``ColorScheme()`` in the app), then
    // drive ``<html>.dark`` LIVE. register() is idempotent : if the
    // envelope already registered the adapter above, this is a no-op ;
    // otherwise it overlays any saved snapshot from localStorage.
    // ⚠️ The mode→dark resolution MUST match the FOUC script in
    // ``render/shell.py`` (which runs pre-paint, before this loads).
    $bz._persistence.register("ColorScheme.default", "local");
    if ($bz._store.peek("ColorScheme.default.mode") === undefined) {
      $bz._store.set("ColorScheme.default.mode", "system");
    }
    // La resolution mode -> sombre, en UN endroit. L'effet ci-dessous la
    // pose sur <html> ; ``ColorScheme.toggle()`` (Python) l'appelle pour
    // basculer contre CE QU'ON VOIT et non contre le jeton stocke.
    //
    // Sans ca, partir de ``system`` sur un OS sombre rendait le PREMIER
    // clic invisible : il ecrivait ``dark``, deja la valeur resolue.
    // Mesure sur les deux apps de demo le 2026-09-04 -- l'utilisateur l'a
    // rapporte comme "le bouton ne marche pas", ce qui est la bonne
    // lecture d'un controle qui ne fait rien une fois sur deux.
    //
    // Lit deux signaux, donc appele DANS l'effet il garde le suivi.
    $bz._isDark = function () {
      const m = $bz._store.get("ColorScheme.default.mode");
      return (
        m === "dark" ||
        ((m === "system" || m === "auto") && $bz._osScheme.get() === "dark")
      );
    };
    $bz.effect(function () {
      document.documentElement.classList.toggle("dark", $bz._isDark());
    });

    // Boot scan timing — exposed as a ``performance.measure`` so the
    // load-handler cost can be attributed (our directive binding vs the
    // debug-only in-browser Tailwind compiler). Negligible overhead, kept
    // permanently for diagnostics : read via
    // ``performance.getEntriesByName("bz:boot-scan")``.
    const _perf = window.performance && performance.mark ? performance : null;
    if (_perf) _perf.mark("bz:scan-start");
    $bz._scan(document.body);
    if (_perf) {
      _perf.mark("bz:scan-end");
      try {
        _perf.measure("bz:boot-scan", "bz:scan-start", "bz:scan-end");
      } catch (e) {
        /* marks evicted under buffer pressure — ignore */
      }
    }

    if ($bz._endpoints && $bz._endpoints.sse) {
      // L'identité passe par l'URL : `EventSource` n'a aucune façon de
      // poser un en-tête.
      _sseUrl = $bz._endpoints.sse
        + ($bz._endpoints.sse.indexOf("?") >= 0 ? "&" : "?")
        + "tab=" + encodeURIComponent($bz._tabId);
      ensureSse();
    }

    document.documentElement.classList.add("bz-ready");
    document.dispatchEvent(new CustomEvent("bz:ready"));
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    // Already-ready DOM : defer one microtask so the rest of the
    // bundle (01..06, concatenated after this module) is evaluated
    // before boot() touches $bz._scan / $bz._wireBridge.
    queueMicrotask(boot);
  }
})();


/* 01_signals.js — reactive primitives : signal / effect / computed.
 *
 * The signal store is the one thing HTMX does not do at all. Design
 * references : Solid.js fine-grained reactivity, Vue 3 ref/computed.
 * We use the simplest viable model — no proxies on arrays, no
 * auto-tracking of nested object mutations (`signal({a:1})` then
 * mutating `.a` does NOT trigger ; `.set({a:2})` with a fresh object
 * does). Predictable, debuggable.
 *
 *   signal(initial) → { get, set, peek, subscribe }
 *     get()        reads + registers the running effect as dependent
 *     peek()       reads without registering
 *     set(v)       triggers dependents unless Object.is(v, current)
 *     subscribe(fn) plain observer (fires on change), returns unsubscribe
 *
 *   effect(fn) → { dispose }
 *     runs now, re-runs whenever any signal it read changes. A per-tick
 *     dirty queue + microtask flush coalesce multiple writes into one
 *     re-run. Re-entering a running effect throws (cycle detection).
 *
 *   computed(fn) → { get, peek, dispose }
 *     memoized derivation, recomputed when a dependency changes.
 *
 * Spec : spec/V3/03-runtime.md §"_src/01_signals.js".
 */
(function () {
  "use strict";
  const $bz = (window.$bz = window.$bz || {});

  let activeEffect = null;
  const pending = new Set();
  let flushScheduled = false;

  function scheduleFlush() {
    if (flushScheduled) return;
    flushScheduled = true;
    queueMicrotask(function () {
      flushScheduled = false;
      const batch = Array.from(pending);
      pending.clear();
      for (const eff of batch) eff._run();
    });
  }

  function signal(initial) {
    let value = initial;
    const subs = new Set();      // dependent effects
    const observers = new Set(); // plain subscribe() callbacks
    return {
      get() {
        if (activeEffect) {
          subs.add(activeEffect);
          activeEffect._deps.add(subs);
        }
        return value;
      },
      peek() {
        return value;
      },
      set(v) {
        if (Object.is(v, value)) return;
        value = v;
        for (const eff of subs) pending.add(eff);
        scheduleFlush();
        for (const fn of observers) fn(v);
      },
      subscribe(fn) {
        observers.add(fn);
        return function () {
          observers.delete(fn);
        };
      },
    };
  }

  function effect(fn) {
    const eff = {
      _deps: new Set(),
      _disposed: false,
      _running: false,
      _run() {
        if (eff._disposed) return;
        if (eff._running) throw new Error("bz: effect cycle detected");
        for (const subs of eff._deps) subs.delete(eff);
        eff._deps.clear();
        const prev = activeEffect;
        activeEffect = eff;
        eff._running = true;
        try {
          fn();
        } finally {
          activeEffect = prev;
          eff._running = false;
        }
      },
      dispose() {
        eff._disposed = true;
        for (const subs of eff._deps) subs.delete(eff);
        eff._deps.clear();
      },
    };
    eff._run();
    return eff;
  }

  function computed(fn) {
    const out = signal(undefined);
    const eff = effect(function () {
      out.set(fn());
    });
    return { get: out.get, peek: out.peek, dispose: eff.dispose };
  }

  $bz.signal = signal;
  $bz.effect = effect;
  $bz.computed = computed;
})();


/* 02_directives.js — the 13 bz-* directives + the binding engine.
 *
 *   bz-on:<event>="<expr>"   addEventListener, runs expr in scope
 *   bz-model="<path>"        two-way binding on form inputs only
 *   bz-attr:<name>="<expr>"  one-way attribute bind (false/null/undefined
 *                            → removeAttribute, true → empty attr)
 *   bz-class="<obj|array>"   classList add/remove per truthiness ;
 *                            statically-emitted class="" preserved
 *   bz-text="<expr>"         textContent (display-only)
 *   bz-show="<expr>"         style.display toggle, element stays mounted
 *   bz-if="<expr>"           mount/unmount (fresh subtree each mount)
 *   bz-for="v in expr [:key=expr] [:flip]"  keyed iteration — lives on a
 *                            <template> with a single root child. ``:flip``
 *                            FLIP-animates surviving rows on insert/remove.
 *   bz-init="<expr>"         one-shot on first mount of the node
 *   bz-effect="<expr>"       continuous reactive effect
 *   bz-ref="<name>"          register el in scope refs
 *   bz-teleport="<selector>" move <template> content to target, scope
 *                            stays bound to the origin location
 *   (bz-data is owned by 03_scope.js)
 *
 * Engine contract (validated by the Phase 0 spike) :
 *   - scan(root) binds the whole subtree, document order (parents
 *     first, so bz-data scopes exist before descendants resolve them).
 *   - REBIND-AFTER-MORPH : the bridge re-scans every swapped subtree ;
 *     existing bindings are disposed and re-bound, effects re-run and
 *     restore any reactive write idiomorph clobbered (textContent,
 *     display, value). This single rule replaces V2's whole
 *     morph-guard machinery (02_morph_hook.js).
 *
 * Expression sandbox : `new Function` compiled once per (mode, expr),
 * cached. `with($scope)` puts the bz-data scope proxy on the scope
 * chain — bare names read/write scope signals, `$bz.state.X.Y.Z`
 * reaches the global typed store.
 *
 * A CSP IS shipped since 2026-09-05 (`Bretzel(csp=True)`, cf.
 * `.claude/bretzel/security.md`) : it carries `'unsafe-eval'` for this
 * very `new Function`, but NOT `'unsafe-inline'`, so an injected
 * <script> stays inert. Only the `unsafe-eval`-FREE mode is still
 * deferred, and its cost is measured there — 29 % of the expressions
 * this engine receives fall outside any tractable subset.
 */
(function () {
  "use strict";
  const $bz = (window.$bz = window.$bz || {});

  /* ── Inertie d'un contrôle désactivé ────────────────────────────────
   *
   * UN support natif (`<button disabled>`, `<input disabled>`) est rendu
   * inerte par le navigateur, gratuitement. Un `<a>`, un `<div>`, un
   * `role="menuitem"` ne le sont JAMAIS : l'attribut `disabled` n'existe
   * pas sur eux, il est simplement ignoré.
   *
   * Jusqu'au 2026-08-13 chaque composant s'en tirait tout seul, et
   * mesure faite, deux des trois façons employées étaient cassées :
   *   - MenuItem retirait ses câblages À LA CONSTRUCTION — donc jamais
   *     quand `disabled` est piloté par une binding, où la valeur au
   *     rendu est `false`. `ui.dropdown_item(disabled=<binding>)` restait
   *     entièrement cliquable en paraissant actif ;
   *   - les trois items de nav posaient `pointer-events-none`, ce qui
   *     bloque bien le clic mais ANNULE le `cursor-not-allowed` du même
   *     élément (aucun événement de pointeur ⇒ aucun curseur peint).
   *
   * L'inertie est donc devenue une propriété du SOCLE, dérivée du seul
   * `aria-disabled="true"` — l'attribut que l'a11y exige de toute façon,
   * et que le serveur sait rendre réactif via `bz-attr:`. Trois gardes,
   * chacune à sa frontière : les handlers `bz-on:` ici, la navigation
   * native juste en dessous, et l'action serveur dans `05_bridge.js`
   * (mesuré : `preventDefault` sur `htmx:configRequest` annule bien la
   * requête en htmx 2.0.4, cf. `tests/audit/probe_configrequest_is_
   * cancelable.py`).
   *
   * `closest()` et pas une lecture directe : un clic atterrit sur
   * l'enfant (l'icône, le label), pas sur le contrôle qui porte l'état.
   */
  const INERT_SELECTOR = '[aria-disabled="true"]';

  // Les événements qui DÉMARRENT une interaction. La liste est fermée à
  // dessein : bloquer tout événement rendrait un `bz-on:mouseleave` de
  // fermeture inopérant sur un contrôle désactivé, donc laisserait un
  // état ouvert coincé. Ce qu'on refuse, c'est d'agir — pas d'observer.
  const ACTIVATION_EVENTS = new Set([
    "click", "dblclick", "mousedown", "pointerdown", "touchstart",
    "keydown", "keypress", "keyup", "submit",
  ]);

  $bz._inert = function (el) {
    return !!(el && el.closest && el.closest(INERT_SELECTOR));
  };

  // La navigation native d'un `<a href>` inerte. Elle n'a pas de
  // `bz-on:` à intercepter et n'est pas toujours boostée par HTMX, donc
  // elle a besoin de son propre garde. `preventDefault` SEUL, jamais
  // `stopPropagation` : couper la propagation ici tuerait le
  // click-outside des overlays ouverts ailleurs dans la page — un
  // dropdown resterait ouvert parce qu'on a cliqué sur un bouton
  // désactivé à l'autre bout de l'écran.
  document.addEventListener("click", function (event) {
    const target = event.target;
    if (target && target.closest && target.closest("a" + INERT_SELECTOR)) {
      event.preventDefault();
    }
  }, true);

  // ── Expression compiler ────────────────────────────────────────────
  const exprCache = new Map();
  function compile(expr, mode) {
    // mode: "get" (return expr) | "run" (statements) | "set" (expr = $value)
    const key = mode + " " + expr;
    let fn = exprCache.get(key);
    if (!fn) {
      let body;
      if (mode === "get") body = "with($scope){ return (" + expr + ") }";
      else if (mode === "run") body = "with($scope){ " + expr + " }";
      else body = "with($scope){ " + expr + " = $value }";
      fn = new Function(
        "$scope", "$el", "$refs", "$event", "$value", "$dispatch", "$nextTick",
        body,
      );
      exprCache.set(key, fn);
    }
    return fn;
  }

  /* Les événements de CYCLE DE VIE d'un composant. Ils appartiennent à
   * leur racine et n'ont rien à dire à un ancêtre — contrairement à
   * ``bz-dropdown-pick`` / ``menu-pick``, qui remontent EXPRÈS.
   *
   * Miroir de ``_wiring.ROOT_DISPATCHED_EVENTS`` côté Python, gardé par
   * ``tests/consistency/test_scoped_events_mirror_python.py``.
   *
   * Pourquoi ils ne bullent pas (mesuré au navigateur le 2026-08-19)
   * ----------------------------------------------------------------
   * ``on_open=`` / ``on_close=`` posent leur ``hx-trigger`` sur la
   * RACINE du composant. Avec ``bubbles: true``, cette racine attrapait
   * donc aussi les ``open``/``close`` de ses descendants :
   *
   *   - ``ui.select`` dans un ``ui.dialog(on_open=…)`` → ouvrir le
   *     panneau POSTait le handler DU DIALOG, et Échap en POSTait DEUX
   *     ``on_close`` ;
   *   - ``ui.alert(dismissible=True)`` dans un ``ui.dialog(on_close=…)``
   *     → congédier l'alerte POSTait le ``on_close`` DU DIALOG.
   *
   * Huit composants exposent ces deux events et huit les émettent :
   * n'importe quel émetteur imbriqué dans n'importe quel écouteur
   * fuyait. Repro : ``tests/probes/probe_overlay_bubble.py``. */
  const SCOPED_EVENTS = new Set(["open", "close"]);

  /* La racine du composant qui contient ``el`` : le premier ancêtre à
   * ``bz-data``, en remontant les téléportations par leur origine.
   *
   * Même marche que ``findScope`` (``03_scope.js``) — sans le saut
   * ``_bzScopeHost``, un panneau projeté sous ``<body>`` (Tooltip,
   * Popover, Dropdown, popover de SidebarFooter) chercherait sa racine
   * dans le ``<body>`` et n'en trouverait aucune. Aucun ``open``/``close``
   * n'en part aujourd'hui — mesuré, seul ``bz-dropdown-pick`` y vit — mais
   * un composant à venir n'a pas à redécouvrir ce piège. */
  function componentRootOf(el) {
    let node = el;
    while (node) {
      if (node._bzScopeHost) {
        node = node._bzScopeHost;
        continue;
      }
      if (node.hasAttribute && node.hasAttribute("bz-data")) return node;
      node = node.parentElement;
    }
    return null;
  }

  function makeDispatch(el) {
    // Memoized per node — handlers on the same element share one closure.
    if (!el._bzDispatch) {
      el._bzDispatch = function (name, detail) {
        // La CIBLE est la racine du composant émetteur, pas le nœud qui
        // appelle : le ``×`` d'une Alert est un descendant, et son
        // ``close`` doit quand même atteindre l'écouteur de la racine.
        // Le bullage le faisait ; en le coupant, il faut viser la racine
        // directement. Repli sur ``el`` si le composant n'a pas de scope
        // — un dispatch de moins vaut mieux qu'un dispatch ailleurs.
        const scoped = SCOPED_EVENTS.has(name);
        const target = (scoped && componentRootOf(el)) || el;
        target.dispatchEvent(
          new CustomEvent(name, { detail: detail, bubbles: !scoped }),
        );
      };
    }
    return el._bzDispatch;
  }

  function nextTick(fn) {
    queueMicrotask(function () {
      queueMicrotask(fn); // after the signal flush microtask
    });
  }

  function evaluate(el, expr, scope) {
    return compile(expr, "get")(
      scope.proxy, el, scope.refs, null, null, makeDispatch(el), nextTick,
    );
  }

  // ── Binding registry ───────────────────────────────────────────────
  const bound = new WeakMap(); // node → array of dispose fns
  // Teleported nodes (panels moved to <body> by bz-teleport) — tracked
  // so a swap that removes the ORIGIN template can sweep the orphan
  // (idiomorph only touches the swapped subtree, never the panel in
  // <body>). cf. ``sweepTeleports`` + the bridge afterSwap.
  const teleported = new Set();

  function disposeEl(el) {
    const disposers = bound.get(el);
    if (!disposers) return;
    for (const d of disposers) d();
    bound.delete(el);
  }

  function disposeTree(node) {
    if (node.nodeType !== 1) return;
    disposeEl(node);
    for (const child of node.querySelectorAll("*")) disposeEl(child);
  }

  function elEffect(el, fn, disposers) {
    const eff = $bz.effect(fn);
    disposers.push(eff.dispose);
  }

  // ── Simple (non-structural) directives ─────────────────────────────
  const HANDLERS = {
    ref(el, expr, scope, disposers) {
      scope.refs[expr] = el;
      disposers.push(function () {
        if (scope.refs[expr] === el) delete scope.refs[expr];
      });
    },

    model(el, expr, scope, disposers) {
      const getter = compile(expr, "get");
      const setter = compile(expr, "set");
      const dispatch = makeDispatch(el);
      const isCheckbox = el.type === "checkbox";
      const isRadio = el.type === "radio";
      elEffect(el, function () {
        const v = getter(scope.proxy, el, scope.refs, null, null, dispatch, nextTick);
        if (isCheckbox) el.checked = !!v;
        else if (isRadio) el.checked = String(v) === el.value;
        else {
          const s = v === undefined || v === null ? "" : String(v);
          if (el.value !== s) el.value = s;
        }
      }, disposers);
      const eventName =
        isCheckbox || isRadio || el.tagName === "SELECT" ? "change" : "input";
      const listener = function (event) {
        const value = isCheckbox ? el.checked : el.value;
        if (isRadio && !el.checked) return;
        setter(scope.proxy, el, scope.refs, event, value, dispatch, nextTick);
      };
      el.addEventListener(eventName, listener);
      disposers.push(function () {
        el.removeEventListener(eventName, listener);
      });
    },

    attr(el, expr, scope, disposers, name) {
      // ``value`` / ``checked`` are IDL properties whose LIVE state
      // diverges from the attribute on form controls : a dirty input
      // displays ``el.value`` (the property), not the ``value``
      // attribute, and idiomorph clobbers the property on morph — so a
      // bz-attr:value that only set the attribute would empty the input
      // after a refresh (same attribute-vs-property trap as bz-text vs
      // textContent). Mirror onto the property too. The ``el.value !==
      // str`` guard avoids resetting the caret while the user types.
      // Scoped to native form controls : custom elements (e.g.
      // <bz-calendar>) reflect ``value`` through their own
      // attributeChangedCallback and must NOT be short-circuited by a
      // direct property write (cf. traps.md § bz-attr value on a custom
      // element).
      const tag = el.tagName;
      const formControl = tag === "INPUT" || tag === "SELECT" || tag === "TEXTAREA";
      const idlValue = name === "value" && formControl;
      const idlChecked = name === "checked" && tag === "INPUT";
      elEffect(el, function () {
        const v = evaluate(el, expr, scope);
        if (v === false || v === null || v === undefined) {
          el.removeAttribute(name);
          if (idlValue) { if (el.value !== "") el.value = ""; }
          else if (idlChecked) el.checked = false;
        } else {
          const str = v === true ? "" : String(v);
          el.setAttribute(name, str);
          if (idlValue) { if (el.value !== str) el.value = str; }
          else if (idlChecked) el.checked = !!v;
        }
      }, disposers);
    },

    class(el, expr, scope, disposers) {
      // Dynamic classes are tracked so the static class="" set by the
      // server is never touched. The tracking set is per-BIND (this
      // closure), NOT a property persisted on the element.
      //
      // Why it MUST be per-bind : a @refreshable morph rewrites the
      // element's class="" back to the freshly-rendered SSR baseline,
      // which STRIPS the classes this directive had added (the active
      // pill on a Pagination page, the grid-rows-[1fr] on an open
      // Accordion body, a Sidebar's active item…). The bridge then
      // re-scans the swapped subtree, disposing and RE-BINDING us. If the
      // set lived on the element (`el._bzClassDyn`) it survived the morph,
      // so the re-bound effect saw prev===next and NEVER re-added the
      // stripped classes — the styling silently vanished until the next
      // interaction (reproduced: pagination active page loses its pill,
      // accordion body flashes back open on close). A fresh per-bind set
      // starts empty, so the first run after a morph re-adds every class
      // from the real (clobbered) DOM baseline. Within a single bind the
      // closure persists across signal-driven re-runs, so normal
      // add/remove diffing is unchanged. Cf. traps.md § "bz-class perdue
      // après un morph (tracking sur le noeud)".
      //
      // `managed` seul ne suffit PAS à tenir cette promesse : il retient ce
      // que l'EXPRESSION a produit, pas ce qui a réellement été ajouté. Or
      // `classList` est un set — un token déjà présent dans le `class=` SSR
      // rend le `add` inopérant, mais le `remove` le supprime pour de bon.
      // Un thème qui répète un token entre sa couche statique et sa couche
      // dynamique voyait donc le token statique DÉTRUIT au premier
      // basculement (mesuré : un bouton Pagination qui cesse d'être une
      // ellipse perdait `w-10 text-sm flex items-center justify-center` et
      // s'effondrait de 40 px à 8 px, `h-10` intacte). D'où `base` : la
      // baseline lue au bind, jamais retirable. Cf. traps.md § « bz-class
      // détruit un token que le thème partage avec sa couche statique ».
      let managed = new Set();
      const base = new Set(el.classList);
      elEffect(el, function () {
        const v = evaluate(el, expr, scope);
        const next = new Set();
        if (Array.isArray(v)) {
          for (const entry of v) {
            if (!entry) continue;
            for (const cls of String(entry).split(/\s+/)) if (cls) next.add(cls);
          }
        } else if (v && typeof v === "object") {
          for (const key of Object.keys(v)) {
            if (!v[key]) continue;
            for (const cls of key.split(/\s+/)) if (cls) next.add(cls);
          }
        } else if (typeof v === "string") {
          for (const cls of v.split(/\s+/)) if (cls) next.add(cls);
        }
        for (const cls of managed)
          if (!next.has(cls) && !base.has(cls)) el.classList.remove(cls);
        for (const cls of next) if (!managed.has(cls)) el.classList.add(cls);
        managed = next;
      }, disposers);
      // Un effet qui AJOUTE des classes les RETIRE a sa disposition.
      //
      // Sans cette symetrie, `base` finit par proteger ce que le RUNTIME
      // a ajoute au lieu de ce que le SERVEUR a ecrit. `bindEl` commence
      // par `disposeEl`, donc chaque re-bind (le bridge re-bind apres
      // CHAQUE swap htmx) recapture `base = new Set(el.classList)` — et
      // si l'ancien effet a laisse ses classes en place, elles entrent
      // dans la nouvelle baseline et deviennent DEFINITIVEMENT
      // irretirables.
      //
      // Symptome mesure le 2026-08-16 sur une app de demo retiree : apres une
      // navigation partielle de `/` vers `/stats`, l'entree « Tasks »
      // gardait son fond `bg-primary` alors que son `data-active` etait
      // bien repasse a `false` — un item a MOITIE actif, fond peint et
      // texte reste gris. `bz-attr` n'a pas de baseline, donc lui restait
      // juste : les deux canaux d'un meme etat divergeaient.
      //
      // Touche les 9 composants qui emettent `bz-class`, pas seulement la
      // sidebar. Cf. traps.md § « bz-class perdue apres un morph » — meme
      // famille, sens inverse : la classe SURVIT au lieu de disparaitre.
      disposers.push(function () {
        for (const cls of managed)
          if (!base.has(cls)) el.classList.remove(cls);
      });
    },

    text(el, expr, scope, disposers) {
      elEffect(el, function () {
        const v = evaluate(el, expr, scope);
        el.textContent = v === undefined || v === null ? "" : String(v);
      }, disposers);
    },

    show(el, expr, scope, disposers) {
      elEffect(el, function () {
        el.style.display = evaluate(el, expr, scope) ? "" : "none";
      }, disposers);
    },

    on(el, expr, scope, disposers, eventName) {
      const runner = compile(expr, "run");
      const dispatch = makeDispatch(el);
      const guarded = ACTIVATION_EVENTS.has(eventName);
      const listener = function (event) {
        // Un contrôle inerte ne DÉMARRE pas d'interaction. Le garde vit
        // ici parce que c'est le seul endroit du runtime qui installe un
        // ``bz-on:`` — donc la règle vaut pour les 76 composants sans
        // qu'aucun ne la réécrive.
        if (guarded && $bz._inert(el)) return;
        runner(scope.proxy, el, scope.refs, event, null, dispatch, nextTick);
      };
      el.addEventListener(eventName, listener);
      disposers.push(function () {
        el.removeEventListener(eventName, listener);
      });
    },

    effect(el, expr, scope, disposers) {
      const runner = compile(expr, "run");
      const dispatch = makeDispatch(el);
      elEffect(el, function () {
        runner(scope.proxy, el, scope.refs, null, null, dispatch, nextTick);
      }, disposers);
    },

    init(el, expr, scope) {
      if (el._bzInitDone) return; // one-shot per NODE (survives rebind)
      el._bzInitDone = true;
      compile(expr, "run")(
        scope.proxy, el, scope.refs, null, null, makeDispatch(el), nextTick,
      );
    },
  };

  // Binding order : refs first (siblings may use them in init), init
  // last (element fully wired when it runs).
  const ORDER = ["ref", "model", "attr", "class", "text", "show", "on", "effect", "init"];

  function bindEl(el) {
    disposeEl(el);
    const todo = [];
    for (const attr of Array.from(el.attributes)) {
      const name = attr.name;
      if (name.startsWith("bz-on:")) todo.push(["on", attr.value, name.slice(6)]);
      else if (name.startsWith("bz-attr:")) todo.push(["attr", attr.value, name.slice(8)]);
      else if (name === "bz-model") todo.push(["model", attr.value, null]);
      else if (name === "bz-class") todo.push(["class", attr.value, null]);
      else if (name === "bz-text") todo.push(["text", attr.value, null]);
      else if (name === "bz-show") todo.push(["show", attr.value, null]);
      else if (name === "bz-ref") todo.push(["ref", attr.value, null]);
      else if (name === "bz-effect") todo.push(["effect", attr.value, null]);
      else if (name === "bz-init") todo.push(["init", attr.value, null]);
    }
    if (!todo.length) return;
    todo.sort(function (a, b) {
      return ORDER.indexOf(a[0]) - ORDER.indexOf(b[0]);
    });
    const disposers = [];
    bound.set(el, disposers);
    const scope = $bz._scopeFor(el);
    for (const [kind, expr, arg] of todo) HANDLERS[kind](el, expr, scope, disposers, arg);
  }

  // ── Structural : bz-if ─────────────────────────────────────────────
  function bindIf(el) {
    const expr = el.getAttribute("bz-if");
    const anchor = document.createComment("bz-if");
    el.parentNode.insertBefore(anchor, el);
    const template = el;
    template.remove();
    const scope = $bz._scopeFor(anchor.parentElement || document.body);
    let mounted = null;
    const eff = $bz.effect(function () {
      const v = compile(expr, "get")(
        scope.proxy, anchor, scope.refs, null, null, function () {}, nextTick,
      );
      if (v && !mounted) {
        mounted = template.cloneNode(true);
        mounted.removeAttribute("bz-if");
        anchor.parentNode.insertBefore(mounted, anchor.nextSibling);
        scan(mounted);
      } else if (!v && mounted) {
        disposeTree(mounted);
        mounted.remove();
        mounted = null;
      }
    });
    bound.set(anchor, [
      eff.dispose,
      function () {
        if (mounted) {
          disposeTree(mounted);
          mounted.remove();
          mounted = null;
        }
      },
    ]);
  }

  // Generic reflow-motion tokens for the ``:flip`` list option — the
  // framework's standard short duration + easing (the same easing the shell
  // uses across its keyframes). Not slaved to any one component ; a toast's
  // leave dance happens to share the 200ms so its neighbour's slide reads as
  // one motion, but nothing here needs to track ``LEAVE_MS``.
  const FLIP_MS = 200;
  const FLIP_EASING = "cubic-bezier(.4,0,.2,1)";

  // FLIP "Play" — slide each surviving row from its recorded box to its new
  // one. Shared by ``bindFor`` when the loop opts in with ``:flip``. Skips
  // rows that did not move and rows with no "First" rect (they are new —
  // their own enter animation owns the entrance).
  //
  // Driven by the Web Animations API rather than a transition + inverse
  // transform : the manual invert/release pattern needs the inverted frame
  // to PAINT before the release, but rAF callbacks run before the paint
  // step (HTML rendering order : rAF → layout → paint), so releasing in the
  // next rAF cancels the invert and nothing animates. ``element.animate``
  // interpolates from → to with no timing dance and auto-clears its effect
  // (default ``fill: none``) — no inline style residue, no ``transitionend``
  // bookkeeping.
  function flipPlay(rows, firstRects) {
    if (typeof Element.prototype.animate !== "function") return;
    for (const [key, row] of rows) {
      const first = firstRects.get(key);
      if (!first) continue;
      const node = row.node;
      const last = node.getBoundingClientRect();
      const dx = first.left - last.left;
      const dy = first.top - last.top;
      if (Math.abs(dx) < 0.5 && Math.abs(dy) < 0.5) continue;
      // Cancel a FLIP still in flight (rapid successive removals) so the new
      // delta starts from the current visual position, not a stale one.
      if (node._bzFlip) node._bzFlip.cancel();
      node._bzFlip = node.animate(
        [
          { transform: "translate(" + dx + "px," + dy + "px)" },
          { transform: "translate(0px,0px)" },
        ],
        { duration: FLIP_MS, easing: FLIP_EASING },
      );
    }
  }

  // ── Structural : bz-for (on a <template>, single root child) ──────
  function bindFor(template) {
    let raw = template.getAttribute("bz-for");
    // ``:flip`` — optional trailing flag that opts the loop into FLIP reflow
    // animation (surviving rows glide to their new box instead of teleporting
    // when a sibling is inserted/removed). Stripped BEFORE the main parse so
    // the greedy ``:key=`` group never swallows it ; other loop options thus
    // stay on one surface (the bz-for expression), next to ``:key=``.
    const flipEnabled = /\s+:flip\s*$/.test(raw);
    if (flipEnabled) raw = raw.replace(/\s+:flip\s*$/, "");
    const match = raw.match(/^\s*(\w+)\s+in\s+(.+?)(?:\s+:key=(.+))?\s*$/);
    if (!match) {
      console.error("bz: invalid bz-for expression:", raw);
      return;
    }
    const varName = match[1];
    const listExpr = match[2];
    const keyExpr = match[3] || null;
    const content = template.content.firstElementChild;
    if (!content) {
      console.error("bz: <template bz-for> needs a single root child");
      return;
    }
    if (template._bzForRows) {
      // Rebind after morph : rows are keyed in the Map, effect below
      // reconciles against it — dispose the old effect first.
      disposeEl(template);
    }
    const rows = (template._bzForRows = template._bzForRows || new Map());
    const scope = $bz._scopeFor(template.parentElement || document.body);
    // ``:flip`` opt-in (parsed above) makes surviving rows slide from their
    // old box to the new one when a sibling is inserted or removed, instead
    // of teleporting into the freed space. The notification stack uses it so
    // a dismissed toast's neighbours glide up rather than snap (cf. traps.md
    // § "Toast reflow jumps"). Reconciliation stays key-based (nodes are
    // reused, never remounted) — FLIP only animates the layout delta of nodes
    // present both BEFORE and AFTER the update.

    const eff = $bz.effect(function () {
      const items =
        compile(listExpr, "get")(
          scope.proxy, template, scope.refs, null, null, function () {}, nextTick,
        ) || [];
      // FLIP "First" : snapshot every connected row's box before we mutate.
      // Honour prefers-reduced-motion via the shared gate (06_helpers.js) —
      // read live so an OS toggle mid-session is respected.
      const flip = flipEnabled && !$bz.helpers.prefersReducedMotion();
      const firstRects = flip ? new Map() : null;
      if (flip) {
        for (const [k, r] of rows) {
          if (r.node.isConnected) firstRects.set(k, r.node.getBoundingClientRect());
        }
      }
      const seen = new Set();
      let cursor = template;
      items.forEach(function (item, index) {
        let key;
        if (keyExpr) {
          const probe = $bz._makeItemScope(scope, { [varName]: item, $index: index });
          key = compile(keyExpr, "get")(
            probe.proxy, template, scope.refs, null, null, function () {}, nextTick,
          );
        } else {
          key = index;
        }
        key = String(key);
        seen.add(key);
        let row = rows.get(key);
        if (!row) {
          const node = content.cloneNode(true);
          const itemScope = $bz._makeItemScope(scope, { [varName]: item, $index: index });
          node._bzItemScope = itemScope;
          row = { node: node, scope: itemScope };
          rows.set(key, row);
          cursor.parentNode.insertBefore(node, cursor.nextSibling);
          scan(node);
        } else {
          row.scope.vars[varName].set(item);
          row.scope.vars.$index.set(index);
          if (cursor.nextSibling !== row.node) {
            cursor.parentNode.insertBefore(row.node, cursor.nextSibling);
          }
        }
        cursor = row.node;
      });
      for (const [key, row] of Array.from(rows.entries())) {
        if (seen.has(key)) continue;
        disposeTree(row.node);
        row.node.remove();
        rows.delete(key);
      }
      // FLIP "Last / Invert / Play" : now the DOM is final, measure each
      // surviving row's new box, jump it back to where it was with an
      // instant inverse transform, then release it on the next frame so it
      // transitions to its resting place. Rows absent from ``firstRects``
      // are freshly inserted — they run their own enter animation, not FLIP.
      if (flip) flipPlay(rows, firstRects);
    });
    bound.set(template, [eff.dispose]);
  }

  // ── Structural : bz-teleport (on a <template>) ─────────────────────
  function bindTeleport(template) {
    // ``<template>.innerHTML`` serialises the content fragment. idiomorph
    // DOES morph into template content (verified), and the runtime never
    // mutates it (directives run on the teleported CLONE under the target,
    // not here) — so it is a reliable signature of the SOURCE. When it
    // changes, a refresh rewrote the panel and the live <body> copy is
    // stale and must be re-projected (else e.g. a tooltip's text / color /
    // arrow stays frozen on its first render inside a refreshable).
    const sig = template.innerHTML;
    const live =
      template._bzTeleported &&
      template._bzTeleported.some(function (n) {
        return n.isConnected;
      });
    if (live && template._bzTeleportSig === sig) {
      return; // already live AND source unchanged : keep the clone (no
      // flicker, preserves the panel's floating position / open state)
    }
    const target = document.querySelector(template.getAttribute("bz-teleport"));
    if (!target) {
      console.error("bz: bz-teleport target not found:", template.getAttribute("bz-teleport"));
      return;
    }
    // A morph rewrote the source : drop the stale clones before
    // re-projecting so the target reflects the new content.
    if (template._bzTeleported) {
      for (const stale of template._bzTeleported) {
        disposeTree(stale);
        stale.remove();
        teleported.delete(stale);
      }
      template._bzTeleported = null;
    }
    const moved = [];
    for (const child of Array.from(template.content.children)) {
      const node = child.cloneNode(true);
      node._bzScopeHost = template; // scope resolves at the ORIGIN location
      target.appendChild(node);
      moved.push(node);
      teleported.add(node);
      scan(node); // bz-* directives on the clone
      // htmx wiring on the clone. A teleported panel can carry ``hx-post``
      // action buttons (Dropdown items, a Popover's server buttons). The
      // ORIGIN lives inside an inert ``<template>`` (htmx never processes
      // template content), and a re-projection after a refresh appends the
      // clone OUTSIDE htmx's swap path — so htmx never wires the action and
      // the click fires only the client ``bz-dropdown-pick`` (menu closes),
      // never the POST. We own projecting the clone, so we own processing
      // it — mirror of ``scan``. Idempotent : htmx skips already-initialised
      // nodes, so the first projection (caught by htmx's observer) is a
      // no-op here. cf. traps.md § "Teleported hx-post dead after refresh".
      if (window.htmx) window.htmx.process(node);
    }
    template._bzTeleportSig = sig;
    template._bzTeleported = moved;
    bound.set(template, [
      function () {
        for (const node of moved) {
          disposeTree(node);
          node.remove();
          teleported.delete(node);
        }
        template._bzTeleported = null;
      },
    ]);
  }

  // Remove teleported panels whose ORIGIN template left the DOM (a morph
  // dropped the owning tooltip/overlay). Without this they linger under
  // <body> — a tooltip that re-renders away mid-hover stays visible
  // forever. Called from the bridge afterSwap.
  function sweepTeleports() {
    if (!teleported.size) return;
    for (const node of Array.from(teleported)) {
      const host = node._bzScopeHost;
      if (!host || !host.isConnected) {
        disposeTree(node);
        node.remove();
        teleported.delete(node);
      }
    }
  }

  // ── Scan ───────────────────────────────────────────────────────────
  function scan(root) {
    if (!root || root.nodeType !== 1) return;
    const els = [root].concat(Array.from(root.querySelectorAll("*")));
    // Pass 1 : materialise bz-data scopes (parents before children).
    for (const el of els) {
      if (el.hasAttribute("bz-data")) $bz._ensureScope(el);
    }
    // Pass 1.5 : register bz-ref tree-wide BEFORE any binding runs, so a
    // parent's bz-init can read a DESCENDANT ref. bindEl's per-element
    // ORDER only guarantees ref-before-init on the SAME element ; a root
    // bz-init that reads $refs of a child (Slider capturing its track /
    // change carrier) would otherwise see undefined — the child binds
    // later in document order, so the click→snap-to-min path lost its
    // track. Idempotent with HANDLERS.ref, which still owns the disposer
    // for cleanup. (cf. traps.md § Slider click → 0 / bz-init descendant
    // refs.)
    for (const el of els) {
      const refName = el.getAttribute("bz-ref");
      if (refName) $bz._scopeFor(el).refs[refName] = el;
    }
    // Pass 2 : structural + simple bindings.
    for (const el of els) {
      if (!el.isConnected && el !== root) continue; // removed by a structural directive
      if (el.tagName === "TEMPLATE") {
        if (el.hasAttribute("bz-for")) bindFor(el);
        else if (el.hasAttribute("bz-teleport")) bindTeleport(el);
        continue;
      }
      if (el.hasAttribute("bz-if")) {
        bindIf(el);
        continue;
      }
      bindEl(el);
    }
  }

  $bz._scan = scan;
  $bz._disposeTree = disposeTree;
  $bz._compile = compile;
  $bz._sweepTeleports = sweepTeleports;
})();


/* 03_scope.js — bz-data component-scoped state, keyed by bz-id.
 *
 * The piece Datastar lacked and Alpine implemented in the wrong place
 * (the DOM). Scope state lives in a runtime-side Map keyed by the
 * bz-id STRING — not in the DOM, not keyed by element : the node may
 * be replaced by idiomorph, the bz-id attribute is what survives.
 * Confirmed by the Phase 0 spike : a morph that re-emits
 * bz-data="{clicks: 0}" does NOT reset an existing scope.
 *
 * On first encounter of <div bz-data="{open: false, helper() {...}}">:
 *   1. evaluate the object literal ($el / $bz are in scope),
 *   2. wrap non-function fields in signals ; functions become helpers
 *      bound to the scope proxy (so `this.open = ...` writes the scope),
 *   3. stamp bz-id if absent (monotonic counter),
 *   4. store the scope in the Map.
 *
 * On re-encounter (same bz-id — typically after a morph) : reuse
 * existing signals, absorb new fields only, refresh helpers, NEVER
 * reset existing values.
 *
 * Nested scopes : a child bz-data reads its parent's vars, cannot
 * write them (throws — settled at the Phase 0 spike, open question #7).
 * bz-for item scopes are different : they're the SAME component scope
 * plus loop vars, so writes fall through to the parent.
 *
 * Eviction : _sweepScopes() drops scopes whose bz-id no longer exists
 * in the document — called by the bridge after swaps.
 */
(function () {
  "use strict";
  const $bz = (window.$bz = window.$bz || {});

  const scopes = new Map(); // bz-id → scope record
  let idCounter = 0;

  function evalDataLiteral(src, el) {
    return new Function("$el", "$bz", "return (" + src + ")")(el, $bz);
  }

  function makeScope(initialParent) {
    // MUTABLE : le parent se RE-RÉSOUT (cf. ``reparent``). Les traps le
    // lisent par la variable, jamais par une copie capturée.
    let parent = initialParent;
    const signals = new Map();
    const helpers = new Map();
    const refs = parent && parent.refs ? Object.create(parent.refs) : {};

    const proxy = new Proxy(
      {},
      {
        has(_t, key) {
          if (typeof key !== "string") return false;
          if (signals.has(key) || helpers.has(key)) return true;
          return parent ? key in parent.proxy : false;
        },
        get(_t, key) {
          if (key === Symbol.unscopables) return undefined;
          if (signals.has(key)) return signals.get(key).get();
          if (helpers.has(key)) return helpers.get(key).bind(proxy);
          if (parent) return parent.proxy[key];
          return undefined;
        },
        set(_t, key, value) {
          if (signals.has(key)) {
            signals.get(key).set(value);
            return true;
          }
          // A var owned by an ancestor scope is written THERE (walk up
          // via the parent proxy), matching Alpine's nested-x-data
          // semantics — e.g. a nested <bz-calendar>{year,month} whose
          // change handler writes the date picker's parent {open,val}.
          // (The Phase-0 spike threw here ; real composite components
          // need the delegation, so the guard was lifted.)
          if (parent && key in parent.proxy) {
            parent.proxy[key] = value;
            return true;
          }
          signals.set(key, $bz.signal(value));
          return true;
        },
      },
    );

    return {
      signals: signals,
      helpers: helpers,
      refs: refs,
      proxy: proxy,
      parentScope() {
        return parent;
      },
      /* Ré-accrocher ce scope à son parent COURANT.
       *
       * Un scope est indexé par son ``bz-id`` STRING et survit donc au
       * remplacement de son nœud — c'est voulu. Mais son parent était
       * capturé UNE fois, à la création, et plus jamais revu : un nœud
       * qui réapparaît sous un autre parent gardait l'ancien à vie.
       *
       * Ça mordait sur une navigation ``hx-boost``, qui ne recharge pas
       * le runtime : le ``<bz-calendar>`` d'un picker portait un id
       * page-indépendant, donc la nouvelle page retrouvait le scope de
       * l'ancienne, dont le parent était le picker de la page
       * PRÉCÉDENTE. Le ``on_change`` écrivait sa valeur dans un scope
       * mort — grille surlignée, champ vide, et un F5 pour s'en sortir.
       *
       * Les ids sont désormais uniques par page (``panel_calendar``),
       * donc ce chemin n'est plus atteint par les pickers. Ceci est le
       * durcissement : il ferme la CLASSE, pour que la prochaine
       * collision d'id — quelle qu'elle soit — ne redevienne pas un bug
       * silencieux.
       *
       * ``refs`` hérite par PROTOTYPE, donc se ré-accrocher demande de
       * bouger le prototype aussi, sinon les ``$refs`` continueraient de
       * résoudre chez l'ancien parent. */
      reparent(next) {
        if (next === parent) return;
        parent = next;
        Object.setPrototypeOf(
          refs, next && next.refs ? next.refs : Object.prototype,
        );
      },
      absorb(decl) {
        for (const key of Object.keys(decl)) {
          if (key === "_serverSync") continue; // swap-resync marker, not a signal
          const v = decl[key];
          if (typeof v === "function") helpers.set(key, v);
          else if (!signals.has(key)) signals.set(key, $bz.signal(v));
        }
      },
    };
  }

  // Root scope : empty, every name falls through to JS globals.
  const rootScope = makeScope(null);

  /* Item scope for bz-for rows : loop vars shadow, everything else
   * (reads AND writes) falls through to the host component scope. */
  function makeItemScope(parent, initialVars) {
    const vars = {};
    for (const key of Object.keys(initialVars)) {
      vars[key] = $bz.signal(initialVars[key]);
    }
    const proxy = new Proxy(
      {},
      {
        has(_t, key) {
          if (typeof key !== "string") return false;
          return key in vars || key in parent.proxy;
        },
        get(_t, key) {
          if (key === Symbol.unscopables) return undefined;
          if (key in vars) return vars[key].get();
          return parent.proxy[key];
        },
        set(_t, key, value) {
          if (key in vars) {
            vars[key].set(value);
            return true;
          }
          parent.proxy[key] = value; // delegate — same component scope
          return true;
        },
      },
    );
    return { vars: vars, proxy: proxy, refs: parent.refs };
  }

  function ensureScope(el) {
    let id = el.getAttribute("bz-id");
    if (!id) {
      id = "bz-" + ++idCounter;
      el.setAttribute("bz-id", id);
    }
    let scope = scopes.get(id);
    if (!scope) {
      scope = makeScope(parentScopeOf(el));
      scopes.set(id, scope);
    } else {
      // Retrouvé, donc potentiellement sous un AUTRE parent qu'à sa
      // création (cf. ``reparent``). Sur la même page c'est le même
      // objet et l'appel ne fait rien.
      scope.reparent(parentScopeOf(el));
    }
    scope.absorb(evalDataLiteral(el.getAttribute("bz-data"), el));
    return scope;
  }

  /* Single upward walk shared by scopeFor / parentScopeOf : item scopes
   * (bz-for rows) win first, teleported subtrees resolve at their
   * origin template, bz-data hosts materialise their scope. */
  function findScope(node) {
    while (node) {
      if (node._bzItemScope) return node._bzItemScope;
      if (node._bzScopeHost) {
        node = node._bzScopeHost; // teleported subtree → resolve at origin
        continue;
      }
      if (node.hasAttribute && node.hasAttribute("bz-data")) return ensureScope(node);
      node = node.parentElement;
    }
    return rootScope;
  }

  function parentScopeOf(el) {
    return findScope(el.parentElement);
  }

  /* Nearest scope for any element, self included. */
  function scopeFor(el) {
    return findScope(el);
  }

  function sweepScopes() {
    if (!scopes.size) return;
    const live = new Set();
    for (const el of document.querySelectorAll("[bz-id]")) {
      live.add(el.getAttribute("bz-id"));
    }
    for (const id of Array.from(scopes.keys())) {
      if (!live.has(id)) scopes.delete(id);
    }
  }

  /* Swap-boundary value adoption. ``absorb`` deliberately SKIPS keys
   * whose signal already exists, so a morph that re-emits bz-data never
   * resets live client state (an open dropdown, a half-typed query).
   * But a server-bound input (NumberInput / Slider / Select / Combobox
   * in local mode) seeds its ``value`` signal from the server : when
   * its @refreshable zone re-renders with a NEW value, the fresh value
   * rides in the morphed bz-data attribute yet absorb keeps the stale
   * one. Such components opt the affected keys in via a ``_serverSync``
   * array ; the bridge calls this ONCE per swap (after the rescan) to
   * adopt exactly those keys from the freshly-morphed attribute. Keys
   * NOT listed (isOpen, _query, …) stay client-owned. Binding-mode
   * inputs need nothing here — their value lives in $bz._store, which
   * the patch envelope updates and which never rides a scope signal. */
  function resyncScopes(root) {
    if (!root || root.nodeType !== 1 || !scopes.size) return;
    const hosts = [];
    if (root.hasAttribute("bz-data")) hosts.push(root);
    for (const el of root.querySelectorAll("[bz-data]")) hosts.push(el);
    for (const el of hosts) {
      const id = el.getAttribute("bz-id");
      if (!id) continue;
      const scope = scopes.get(id);
      if (!scope) continue;
      let decl;
      try {
        decl = evalDataLiteral(el.getAttribute("bz-data"), el);
      } catch (e) {
        continue;
      }
      const keys = decl && Array.isArray(decl._serverSync) ? decl._serverSync : null;
      if (!keys) continue;
      for (const key of keys) {
        const sig = scope.signals.get(key);
        if (sig) sig.set(decl[key]);
      }
    }
  }

  $bz._scopes = scopes;
  $bz._scopeFor = scopeFor;
  $bz._ensureScope = ensureScope;
  $bz._makeItemScope = makeItemScope;
  $bz._sweepScopes = sweepScopes;
  $bz._resyncScopes = resyncScopes;
})();


/* 04_persistence.js — storage adapters per ClientState instance.
 *
 * Per envelope.client_state[<Class>.<key>].persist :
 *
 *   "memory"    → JS memory only, dropped on reload (no adapter). C'est
 *                 le DÉFAUT côté Python (``ClientState.__persist__``).
 *   "session"   → sessionStorage, key "$bz:<Class>.<key>"
 *   "local"     → localStorage, same key
 *
 * ⚠️ ``"volatile"`` et ``"cross_tab"`` étaient listés ici jusqu'au
 * 2026-08-01 : l'enum Python (``state/scopes/client.py::PERSISTS``) ne
 * peut émettre que les trois ci-dessus, donc ces deux modes sont
 * inatteignables — et "memory", le défaut, n'était pas documenté. Le
 * test ``mode === "volatile"`` du code ci-dessous ne matche donc jamais ;
 * il tombe dans le même no-op que "memory" (storageFor → null).
 *
 * Wiring : 00_index.js calls register(path, mode) for each instance
 * AFTER seeding the envelope defaults — register() then overlays any
 * saved snapshot. Every store write is funnelled through
 * $bz._persistence.notify(fullPath) by the store itself ; the adapter
 * saves the instance's full field map. cross_tab adapters additionally
 * publish the change and mirror remote ones into the store (with an
 * echo guard).
 *
 * "page" mode (V2) is gone — page identity is a server concept, not a
 * client persistence target. TTL plumbing is gone too (cf. .claude/bretzel/state.md).
 */
(function () {
  "use strict";
  const $bz = (window.$bz = window.$bz || {});

  const adapters = new Map(); // instancePath → adapter

  function storageFor(mode) {
    if (mode === "session") return window.sessionStorage;
    if (mode === "local" || mode === "cross_tab") return window.localStorage;
    return null;
  }

  function storageKey(path) {
    return "$bz:" + path;
  }

  function register(path, mode) {
    if (mode === "volatile" || adapters.has(path)) return;
    const storage = storageFor(mode);
    if (!storage) return;

    const adapter = { mode: mode, storage: storage, channel: null, muted: false };
    adapters.set(path, adapter);

    // Overlay the saved snapshot (it wins over envelope defaults —
    // the user's browser knows better than the server's defaults).
    try {
      const raw = storage.getItem(storageKey(path));
      if (raw) {
        const saved = JSON.parse(raw);
        for (const field of Object.keys(saved)) {
          $bz._store.set(path + "." + field, saved[field]);
        }
      }
    } catch (e) {
      console.error("bz: corrupt persisted state for", path, e);
      storage.removeItem(storageKey(path));
    }

    if (mode === "cross_tab" && "BroadcastChannel" in window) {
      adapter.channel = new BroadcastChannel(storageKey(path));
      adapter.channel.onmessage = function (msg) {
        adapter.muted = true; // don't re-publish what we just received
        try {
          $bz._store.set(path + "." + msg.data.field, msg.data.value);
        } finally {
          adapter.muted = false;
        }
      };
    }
  }

  /* Called by the store on every set whose path belongs to a
   * registered instance. */
  function notify(fullPath, value) {
    const cut = fullPath.lastIndexOf(".");
    const path = fullPath.slice(0, cut);
    const field = fullPath.slice(cut + 1);
    const adapter = adapters.get(path);
    if (!adapter) return;
    adapter.storage.setItem(
      storageKey(path),
      JSON.stringify($bz._store.fieldsOf(path)),
    );
    if (adapter.channel && !adapter.muted) {
      adapter.channel.postMessage({ field: field, value: value });
    }
  }

  $bz._persistence = { register: register, notify: notify };
})();


/* 05_bridge.js — HTMX glue : signal snapshot out, <bz-patch> in.
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
 *   (Il n'y a PAS de kind "redirect" : une redirection passe par l'en-tête
 *   HX-Redirect, qu'htmx traite nativement, et `bretzel.redirect()` la pose.
 *   Le kind est resté ici six mois sans que rien ne l'émette côté Python —
 *   et sans qu'il PUISSE l'être, error_envelope() ne sachant pas porter
 *   d'url. Gate : tests/consistency/test_bridge_error_kinds_are_emitted.py.)
 */
(function () {
  "use strict";
  const $bz = (window.$bz = window.$bz || {});

  // Wire-format tag name — substituted at build time from protocol.py
  // (single source of truth, even inside the JS).
  const PATCH_TAG = "bz-patch";

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
    // SEMER ou POUSSER — deux chemins, deux intentions.
    //
    //   seed   (nav partielle) : le serveur ré-émet toutes les instances
    //          de la page, avec SES valeurs, qui sont les défauts. Il ne
    //          peut pas connaître celles du navigateur. Elles ne doivent
    //          donc servir qu'à créer ce qui manque.
    //   push   (réponse d'action) : le serveur a délibérément muté un
    //          champ. Il gagne.
    //
    // `config` est le marqueur, et il n'est pas approximatif : côté
    // Python, `build_patch` ne l'émet QUE sous `include_unchanged=True`,
    // c'est-à-dire exactement le chemin de seed. Accord gaté par
    // `tests/consistency/test_a_seed_patch_never_overwrites.py`, et le
    // resultat par `tests/runtime_js/test_a_partial_nav_never_clobbers_client_state.py`.
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
    // Config de transport du seed de nav partielle — APRÈS les champs,
    // parce que ``adoptConfig`` enregistre la persistance et que celle-ci
    // superpose le snapshot stocké, qui doit gagner. Absente d'une réponse
    // d'action ordinaire : le client a déjà la config de ces instances.
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

  // Une valeur COMPOSITE part en JSON, pas telle quelle.
  //
  // Un corps de formulaire ne transporte que des chaînes, et htmx traite un
  // tableau à part : `formDataFromObject` fait `obj[key].forEach(v =>
  // append(key, v))`. Deux conséquences, mesurées le 2026-08-19 :
  //
  //   - `["a","b"]` part en DEUX champs de même nom, et le serveur garde le
  //     dernier — donc `["a","b"]` arrive comme `"b"`, et `["change"]`
  //     comme `"change"` ;
  //   - `[]` n'ajoute RIEN, donc la clé est absente du corps. Comme
  //     l'hydratation n'écrit que les champs présents, **une liste client
  //     vidée ne pouvait plus jamais vider son champ serveur** — le jumeau
  //     exact de la case décochée qui ne soumet rien, sur l'autre
  //     transport.
  //
  // `JSON.stringify` remet le magasin client sur la même convention que les
  // sept porteurs cachés du catalogue (`toggle_group`, `select`,
  // `combobox`, `date_range_picker`, `slider`, `resizable`, `accordion`),
  // et c'est `_coerce_composite` qui le défait côté Python — un seul
  // contrat de wire pour les deux chemins, au lieu de deux.
  //
  // Les scalaires ne sont PAS touchés : ils traversent déjà juste, et les
  // encoder ferait arriver `'"texte"'` là où le champ attend `texte`.
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
      // ``send_to_server: false`` (déclaré côté Python sur la classe) est
      // le SEUL filtre ici, et il est tout-ou-rien. Un mode "delta" a vécu
      // à cette place jusqu'au 2026-08-14 ; il était faux, pas seulement
      // inutile — raison complète dans le docstring de ``ClientState``
      // (bretzel/state/scopes/client.py § "Il n'y a PAS de mode delta").
      // Ne pas le réintroduire sans lire ce paragraphe d'abord.
      const cfg = config[path] || {};
      if (cfg.send_to_server === false) continue;
      for (const field of Object.keys(fields)) {
        detail.parameters[path + "." + field] = wireValue(fields[field]);
      }
    }
  }

  /* ── ``$bz.pending`` — « une action est-elle en vol ? » ──────────────
   *
   * htmx SAIT qu'une requête est en cours (il pose ``.htmx-request`` sur
   * l'élément déclencheur), mais cette information n'était lisible par
   * personne : ni depuis une expression ``bz-*``, ni depuis Python. Un
   * dev qui voulait un spinner pendant l'aller-retour devait donc tenir
   * le booléen lui-même — et il ne POUVAIT pas le tenir côté serveur,
   * puisqu'un état serveur arrive AVEC la réponse, c'est-à-dire quand
   * l'attente est déjà finie.
   *
   * Ce module possède déjà la frontière transport, donc c'est ici que
   * l'information se publie, sous forme de signal : ``ui.pending()`` rend
   * l'expression ``$bz.pending($el, 200)``, lue par n'importe quel
   * ``bz-show`` / ``bz-attr`` comme n'importe quelle autre source.
   *
   * DEUX ADRESSAGES, une seule fonction. ``$el`` (l'élément qui porte la
   * prop est le déclencheur) remonte au porteur du ``hx-post`` via
   * ``closest`` : indispensable, parce que le ``bz-show`` du spinner est
   * posé sur le SPINNER, pas sur le bouton (cf. ``_cloak_show``). Une
   * chaîne (l'``action_id``) adresse la même action depuis ailleurs dans
   * la page — ``ui.pending(save)``.
   *
   * LE DÉLAI EST LA RAISON D'ÊTRE DU MÉCANISME. Un spinner qui apparaît
   * sous ~200 ms produit un flash, et l'interface est perçue comme PLUS
   * lente qu'en ne montrant rien. Personne ne l'écrit à la main ; ici
   * c'est le défaut. Le délai voyage dans l'expression, donc plusieurs
   * délais peuvent coexister sur une même clé — d'où une ``Map`` de
   * signaux par délai plutôt qu'un signal unique.
   *
   * Un compteur, pas un booléen : deux boutons qui partagent le même
   * ``action_id`` peuvent être en vol en même temps, et le premier
   * retour ne doit pas éteindre le second.
   */
  const PENDING_BY_ELT = new WeakMap();
  const PENDING_BY_ID = new Map();

  /* Deux magasins, et c'est forcé, pas incident : une ``WeakMap`` ne
   * peut pas indexer une chaîne, et une ``Map`` indexée par éléments
   * retiendrait chaque déclencheur pour la vie de la page. */
  function pendingStore(key) {
    return typeof key === "string" ? PENDING_BY_ID : PENDING_BY_ELT;
  }

  /* Les clés qu'une requête arme : l'élément déclencheur ET son
   * ``action_id``. Celui-ci se lit dans ``hx-post``, dont le format est
   * ``<ROUTE_ACTION>/<id>`` — et ``ROUTE_ACTION`` est SUBSTITUÉ ici
   * depuis ``protocol.py`` au build, comme les balises d'enveloppe et
   * de patch. Sans ça le JS redeviendrait tiers au format de fil : il
   * le devinerait par découpage de chaîne, et un changement de route
   * côté Python ne se verrait nulle part. */
  const ACTION_PREFIX = "/_bretzel/action/";

  /* La TROISIEME cle, reservee : « une navigation est en vol ». La barre
   * de shell (``render/shell.nav_progress_html``) n'est qu'un ``bz-show``
   * dessus, donc elle n'a aucun mecanisme a elle — c'est le meme
   * registre, la meme temporisation, le meme desarmement.
   *
   * Deux formes de navigation dans ce depot, et il faut les deux :
   * ``detail.boosted`` couvre les liens boostes par ``hx-boost`` (pose
   * au niveau document par le shell), et ``hx-push-url`` couvre la nav
   * partielle de la sidebar / navbar, qui n'est pas boostee mais un
   * ``hx-get`` explicite (``navigation/_wiring.py``). Tester l'un sans
   * l'autre laisserait la moitie des menus sans barre. */
  const NAV_KEY = "@nav";

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
    // Pas d'entrée = personne ne lit cette clé. Rien à armer : on ne
    // fabrique pas de signal pour un bouton sans ``ui.pending()``.
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

  /* Défini au CHARGEMENT du module, pas dans ``_wireBridge`` : un
   * ``bz-show`` peut s'évaluer avant que le bridge soit câblé, et une
   * ``$bz.pending`` absente ferait planter l'expression au lieu de
   * rendre ``false``. */
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
    // Lecture DANS un effet = abonnement. C'est le seul point de
    // contact avec le graphe réactif : la bascule passe ensuite par le
    // flush microtask ordinaire, comme toute autre source.
    return slot.sig.get();
  };

  $bz._wireBridge = function () {
    document.body.addEventListener("htmx:configRequest", function (e) {
      // Un contrôle inerte ne poste RIEN. C'est le troisième garde de
      // l'inertie (les deux autres — handlers `bz-on:` et navigation
      // native — vivent dans 02_directives.js, qui possède la règle) et
      // il est ici parce que c'est la frontière transport : ce module
      // est « the ONLY module that wires HTMX events ».
      //
      // MESURÉ avant d'être écrit, pas lu dans une doc : htmx 2.0.4 émet
      // bien `configRequest` puis renonce à la requête sur
      // `preventDefault` — le témoin non bloqué du probe, lui, part.
      // Cf. `tests/audit/probe_configrequest_is_cancelable.py`.
      if ($bz._inert(e.detail.elt)) {
        e.preventDefault();
        return;
      }
      // Une navigation BOOSTÉE qui traverse le seuil mobile ne peut pas
      // être un swap partiel. `Screen().is_mobile` est un `if` SERVEUR, et
      // le layout qui le porte vit HORS de `[data-bz-outlet]` : échanger
      // l'outlet laisserait la sidebar desktop en place sur un viewport
      // téléphone, indéfiniment, jusqu'au prochain chargement dur. Le
      // script de `<head>` ne rejoue pas non plus, donc le cookie reste
      // périmé et même le serveur ne le sait pas.
      //
      // On resynchronise le cookie et on rend la navigation au navigateur :
      // un chargement complet re-rend le shell depuis le cookie frais.
      // Ce n'est PAS un retour du live-resize retiré le 2026-07-13 — rien
      // ne se déclenche au redimensionnement, seulement sur une navigation
      // que l'utilisateur a demandée, exactement comme un F5.
      //
      // Restreint aux `<a>` : les GET des zones `@refreshable` et du
      // refetch SSE passent aussi par ici et ne doivent jamais devenir une
      // navigation. `$bzScreenSync` est défini par le script de `<head>`
      // (`render/shell.py`) — absent d'un shell custom, on ne fait rien.
      if (
        String(e.detail.verb).toLowerCase() === "get" &&
        e.detail.elt &&
        e.detail.elt.tagName === "A" &&
        typeof window.$bzScreenSync === "function" &&
        !window.$bzScreenSync()
      ) {
        e.preventDefault();
        window.location.assign(
          e.detail.path || e.detail.elt.getAttribute("href"),
        );
        return;
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
      // Qui écrit. Le serveur s'en sert pour ne PAS rediffuser à cet
      // onglet ce qu'il vient de lui répondre — cf. `$bz._tabId`.
      if ($bz._tabId) e.detail.headers["X-Bretzel-Tab"] = $bz._tabId;
      // Dire au serveur quelles zones @refreshable ce document porte.
      //
      // Sans ça il enfile TOUTES les zones declarees sur une classe
      // d'etat changee — y compris celles d'autres pages — les rend,
      // les envoie, et nous les jetons faute de cible. Mesure sur
      // examples/mad : 8,4 ms de rendu serveur perdus contre 9,6 ms
      // utiles, soit pres de la moitie du drain.
      //
      // Sur les POST d'action seulement : une nav GET (hx-boost) n'a
      // pas de drain, et l'entete se retrouverait dans l'URL poussee.
      //
      // On lit le DOM a l'instant de la requete, pas une liste que le
      // serveur nous aurait donnee au rendu : un swap OOB peut avoir
      // introduit une zone depuis, et une liste figee la condamnerait
      // a ne plus jamais se rafraichir.
      if (String(e.detail.verb).toLowerCase() === "post") {
        const zones = document.querySelectorAll("[data-bz-zone]");
        if (zones.length) {
          const ids = [];
          for (const z of zones) {
            // ``id`` seul, ou ``id:empreinte`` quand on sait ce que
            // la zone porte : le serveur s en sert pour TAIRE une
            // zone dont le rendu neuf serait identique. L empreinte
            // vient de LUI, elle n est jamais calculee ici — une
            // empreinte absente ou perimee ne peut donc que faire
            // re-expedier la zone, jamais la taire a tort.
            const zid = z.getAttribute("bz-id");
            const vu = $bz._zoneHashes && $bz._zoneHashes[zid];
            ids.push(vu ? zid + ":" + vu : zid);
          }
          e.detail.headers["X-Bretzel-Zones"] = ids.join(",");
        }
      }
      const carrier = e.detail.elt && e.detail.elt.closest("[data-bz-sig]");
      // Un POST d'action SANS porteur de signature ne part pas.
      //
      // Il ne s'agit pas de prudence : la requête est déjà perdue. Côté
      // Python, `action_attrs` est le SEUL endroit qui écrit un
      // `hx-post`, et il y pose `data-bz-sig` dans le même dict — donc
      // tout POST htmx est une action, et toute action naît signée. Ne
      // pas trouver de porteur au moment du `configRequest` ne veut dire
      // qu'une chose : l'élément a été DÉTACHÉ entre le déclenchement et
      // maintenant, typiquement par le morph d'une zone `@refreshable`.
      //
      // La laisser partir coûte cher, et c'est mesuré. Le serveur refuse
      // toute signature invalide par un `_error: reload`, que
      // `handleError` exécute — donc une requête déjà obsolète fait
      // RECHARGER LA PAGE ENTIÈRE. Reproduit sur `/carousel` le
      // 2026-08-27 : un autoplay tique pendant qu'un flip re-rend le
      // panneau, le nœud disparaît, le POST part nu, 403, rechargement.
      // L'audit voyait « Execution context was destroyed » et le
      // comptait comme un flake de concurrence ; c'était déterministe.
      //
      // Restreint au POST : une nav boostée et le refetch d'une zone SSE
      // sont des GET, ils n'ont jamais de signature et doivent passer.
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

    function afterSwap(e) {
      applyPatchTags();
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
        // Adopt server-authoritative signals (``_serverSync`` keys) from
        // the freshly-morphed bz-data — runs AFTER the rescan so the
        // bz-attr effects are live when the value signal changes.
        $bz._resyncScopes(target);
      }
      $bz._sweepScopes();
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

    /* Le cycle de vie du témoin. ``htmx:afterRequest`` est le SEUL
     * désarmement : htmx l'émet dans tous les cas de sortie — succès,
     * 4xx/5xx, erreur réseau, timeout, abandon — donc écouter en plus
     * ``sendError``/``timeout`` décrémenterait deux fois le compteur et
     * éteindrait une seconde requête encore en vol sur la même clé. */
    document.body.addEventListener("htmx:beforeRequest", function (e) {
      pendingKeys(e.detail.elt, e.detail).forEach(armPending);
    });
    document.body.addEventListener("htmx:afterRequest", function (e) {
      pendingKeys(e.detail.elt, e.detail).forEach(disarmPending);

      /* Les empreintes des zones que cette reponse vient d expedier.
       * On les GARDE pour les representer a la requete suivante : le
       * serveur peut alors taire une zone dont le rendu neuf serait
       * identique a ce qu on affiche deja.
       *
       * Rien n est calcule ici, et c est ce qui rend le mecanisme sur :
       * l empreinte est celle du HTML que le serveur a envoye. Si le
       * DOM a change depuis pour une autre raison, l empreinte devient
       * fausse dans le sens INOFFENSIF — le serveur trouvera une
       * difference et re-expediera. */
      const xhr = e.detail && e.detail.xhr;
      if (!xhr || !xhr.getResponseHeader) return;
      const brut = xhr.getResponseHeader("X-Bretzel-Zone-Hashes");
      if (!brut) return;
      $bz._zoneHashes = $bz._zoneHashes || {};
      for (const morceau of brut.split(",")) {
        const coupe = morceau.indexOf(":");
        if (coupe > 0) {
          $bz._zoneHashes[morceau.slice(0, coupe)] = morceau.slice(coupe + 1);
        }
      }
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


/* 06_locale.js — les noms de mois et de jours, dérivés de la langue.
 *
 * ⚠️ **Le numéro 06 est une CONTRAINTE D'ORDRE, pas une identité.** Ce
 * slab s'appelait ``22_locale.js`` jusqu'au 2026-08-27, donc chargé QUINZE
 * slabs après son unique consommateur, ``07_calendar.js``. Or celui-ci
 * appelle ``customElements.define('bz-calendar', …)``, ce qui met à niveau
 * IMMÉDIATEMENT tous les calendriers déjà dans le DOM — leur constructeur
 * lit alors ``$bz.locale.weekdayNames()`` sur un ``$bz.locale`` qui
 * n'existe pas encore.
 *
 * Mesuré : **une exception jetée par calendrier**, soit 54 sur la page
 * ``/calendar`` du playground, 44 sur ``/date_picker``, 45 sur
 * ``/date_range_picker``, 35 sur ``/month_picker``. L'écran s'en remettait
 * — la directive ``bz-text`` repasse plus tard — mais le flot d'erreurs
 * empêchait ``networkidle`` d'arriver, et ``pytest -m audit`` PENDAIT
 * dessus. Une suite d'une heure rendue inutilisable par une ligne d'ordre.
 *
 * Ce fichier ne dépend de rien (il crée ``window.$bz`` si besoin), donc il
 * pourrait vivre n'importe où avant 07. Il est posé JUSTE avant son
 * consommateur pour qu'un lecteur qui se demande « pourquoi ici ? »
 * trouve la réponse à la ligne suivante du dossier.
 *
 * Gardé par ``tests/runtime_js/test_no_page_throws_on_load.py``, qui
 * charge les 74 pages de composants et exige ZERO exception. Une gate
 * STATIQUE (interdire de lire un ``$bz.<ns>`` posé plus tard) a été
 * écartée après mesure : 9 cas dans le dépôt, et les 9 sont légitimes
 * — des lectures DIFFÉRÉES, dans des fonctions appelées bien après le
 * chargement. Ce qui distingue le défaut, c'est le MOMENT de la
 * lecture, et seul un navigateur le sépare.
 *
 * Exposé en window.$bz.locale, lu par 07_calendar.js et par les
 * expressions bz-* (``bz-text="$bz.locale.monthName(month)"``).
 *
 * Pourquoi ici plutôt que côté serveur
 * -------------------------------------
 * Python n'a aucun moyen sûr de nommer un mois dans une langue donnée :
 * le module ``locale`` de la stdlib est un état GLOBAL au processus (et
 * dépend des locales installées sur la machine), et Babel serait une
 * dépendance — que le charter exclut. Le navigateur, lui, embarque déjà
 * la table complète : ``Intl.DateTimeFormat`` la donne pour n'importe
 * quelle étiquette BCP-47, sans un octet de plus.
 *
 * La langue vient de ``<html lang>``, que ``Bretzel(lang=...)`` pose —
 * pas d'un attribut ad hoc. C'est l'endroit standard, celui qu'un
 * lecteur d'écran lit déjà pour choisir sa voix, et le seul qui reste
 * juste si l'app le change à la main.
 *
 *   $bz.locale.tag()            l'étiquette courante ("fr", "en"…)
 *   $bz.locale.monthNames()     12 noms longs, janvier en tête
 *   $bz.locale.monthName(i)     un seul, 0-indexé
 *   $bz.locale.weekdayNames()     7 noms courts, DIMANCHE en tête
 *   $bz.locale.weekdayLongNames() les mêmes en entier, pour un ``title=``
 *
 * ⚠️ Dimanche en tête, toujours : c'est l'ordre de ``Date.getDay()``, et
 * c'est le composant qui fait tourner la liste selon ``weekstart``. Une
 * liste écrite lundi-première — le réflexe français — décale toutes les
 * colonnes d'un jour (piège [14] du chantier CRM).
 */
(function () {
  "use strict";
  const $bz = (window.$bz = window.$bz || {});

  // Repli si le moteur n'a pas d'Intl utilisable, ou si l'étiquette est
  // invalide (Intl LÈVE sur "français"). C'est exactement ce que le
  // framework rendait avant, donc un repli ne change rien pour personne.
  const FALLBACK_MONTHS = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
  ];
  const FALLBACK_WEEKDAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];

  // 2023-01-01 EST un dimanche, et 2023 a douze mois — les deux ancres
  // dont on a besoin. Tout est calculé en UTC : construire ces dates en
  // heure locale décalerait d'un jour à l'ouest de Greenwich, donc le
  // nom du jour aussi.
  const SUNDAY = Date.UTC(2023, 0, 1);
  const DAY_MS = 86400000;

  const memo = Object.create(null);

  function names(tag) {
    let entry = memo[tag];
    if (entry) return entry;
    try {
      const month = new Intl.DateTimeFormat(tag, {
        month: "long",
        timeZone: "UTC",
      });
      const weekday = new Intl.DateTimeFormat(tag, {
        weekday: "short",
        timeZone: "UTC",
      });
      // Le nom ENTIER, pour le ``title=`` des en-tetes de colonne. Meme
      // memo, meme construction : sept appels de plus, une seule fois par
      // etiquette de langue, jamais par calendrier.
      const weekdayLong = new Intl.DateTimeFormat(tag, {
        weekday: "long",
        timeZone: "UTC",
      });
      entry = {
        months: FALLBACK_MONTHS.map(function (_, i) {
          return month.format(new Date(Date.UTC(2023, i, 15)));
        }),
        weekdays: FALLBACK_WEEKDAYS.map(function (_, i) {
          return weekday.format(new Date(SUNDAY + i * DAY_MS));
        }),
        weekdaysLong: FALLBACK_WEEKDAYS.map(function (_, i) {
          return weekdayLong.format(new Date(SUNDAY + i * DAY_MS));
        }),
      };
    } catch (e) {
      // Le repli n'a QUE des abreviations. ``weekdaysLong`` y vaut donc
      // la meme chose : un ``title`` identique au texte visible est
      // inutile mais jamais faux, la ou inventer un nom entier le serait.
      entry = {
        months: FALLBACK_MONTHS,
        weekdays: FALLBACK_WEEKDAYS,
        weekdaysLong: FALLBACK_WEEKDAYS,
      };
    }
    memo[tag] = entry;
    return entry;
  }

  $bz.locale = {
    tag: function () {
      return (document.documentElement.getAttribute("lang") || "en").trim() || "en";
    },
    monthNames: function () {
      return names(this.tag()).months;
    },
    monthName: function (index) {
      return this.monthNames()[index] || "";
    },
    weekdayNames: function () {
      return names(this.tag()).weekdays;
    },
    weekdayLongNames: function () {
      return names(this.tag()).weekdaysLong;
    },
  };
})();


/* 07_calendar.js — <bz-calendar> custom element (stateful day grid). */
// ════════════════════════════════════════════════════════════════════════
// 07 CALENDAR — <bz-calendar> custom element.
//
// A stateful widget as a custom element : the day-grid logic (month
// math, range preview, keyboard grid nav) is genuinely complex and a
// custom element with its own state + attribute observers is the right
// tool — framework-agnostic, survives idiomorph for free (the element
// node persists by id, only observed attributes morph).
//
// The custom element owns its internal state ; configuration lives in
// observed HTML attributes that idiomorph can morph freely. Each
// attribute change triggers ``attributeChangedCallback`` which schedules
// a re-render. Form participation rides a child ``<input type="hidden">``
// onto which the V3 server-action attrs (hx-post / bz-on:change) are
// relocated by Python — the element fires a synthetic ``change`` on it
// whenever the value mutates.
//
// Public DOM API (callable from imperative handlers) :
//   .set(value), .clear(), .focus(), .blur(),
//   .prevMonth(), .nextMonth()
//
// Custom events dispatched :
//   change       — { value: string | [start, end] }
//   month-change — { year: int, month: 1..12 }
//
// Theme classes arrive via a JSON blob in the ``data-bz-theme`` attr ;
// Python's ``Calendar.render()`` composes the slot strings once and
// hands them over.
// ════════════════════════════════════════════════════════════════════════

(function () {
    'use strict';

    if (typeof customElements === 'undefined') return;
    if (customElements.get('bz-calendar')) return;

    // Dérivés de ``<html lang>`` par 22_locale.js, pas écrits ici : une
    // table en dur rendait « August / MON TUE WED » à toute app, quelle
    // que soit sa langue, et la seule prise était de repasser
    // ``month_names=`` À CHAQUE MONTAGE (trois fois sur un seul écran du
    // CRM). Les listes explicites du composant gagnent toujours — elles
    // arrivent par attribut et ces défauts ne servent qu'à leur absence.
    function DEFAULT_WEEKDAYS() { return window.$bz.locale.weekdayNames(); }
    function DEFAULT_WEEKDAYS_LONG() {
        return window.$bz.locale.weekdayLongNames();
    }
    function DEFAULT_MONTHS() { return window.$bz.locale.monthNames(); }

    function iso(d) {
        return d.getFullYear() + '-' +
            String(d.getMonth() + 1).padStart(2, '0') + '-' +
            String(d.getDate()).padStart(2, '0');
    }

    /* Le jour ISO décalé de ``n`` jours. Passe par un ``Date`` plutôt que
     * par de l'arithmétique sur la chaîne : lui seul connaît les fins de
     * mois et les années bissextiles. */
    function addDays(isoStr, n) {
        var p = isoStr.split('-');
        return iso(new Date(+p[0], +p[1] - 1, +p[2] + n));
    }

    /* Le premier jour de la semaine qui CONTIENT ``isoStr``, selon
     * ``weekstart`` (0 = dimanche, 1 = lundi…).
     *
     * C'est la seule règle du mode ``week`` : cliquer n'importe quel jour
     * choisit sa semaine, et la valeur rendue est ce premier jour. Le
     * modulo est doublé (``% 7 + 7) % 7``) parce que JS rend un reste
     * NÉGATIF pour un dividende négatif — sans lui, toute semaine dont le
     * jour cliqué tombe avant ``weekstart`` remonterait d'une semaine.
     */
    function weekStartOf(isoStr, weekstart) {
        var p = isoStr.split('-');
        var d = new Date(+p[0], +p[1] - 1, +p[2]);
        var back = (d.getDay() - weekstart + 7) % 7;
        return iso(new Date(+p[0], +p[1] - 1, +p[2] - back));
    }

    function parseJSON(value, fallback) {
        if (!value) return fallback;
        try { return JSON.parse(value); } catch (e) { return fallback; }
    }

    function escapeAttr(s) {
        return String(s)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;');
    }

    class BzCalendar extends HTMLElement {
        static get observedAttributes() {
            return [
                'mode', 'value', 'month', 'weekstart',
                'min', 'max', 'disabled',
                'disabled-dates', 'marks', 'weekday-names', 'month-names',
                'data-bz-theme',
                // ``data-bz-value-path`` / ``data-bz-month-path`` carry the
                // ``$bz.state.X.y`` dotted path the framework wants the
                // custom element to write into when the user picks a
                // value or navigates a month. Without these the binding
                // is one-way only (state → attribute) and the Client
                // playground / Client events cards stay silent.
                'data-bz-value-path',
                'data-bz-month-path',
            ];
        }

        constructor() {
            super();
            this._displayedYear = null;
            this._displayedMonth = null;
            this._hoverDate = null;
            // Le début d'une plage EN COURS de sélection, mode ``range``
            // seulement. Il vit ici et PAS dans l'attribut ``value`` —
            // c'est tout le point.
            //
            // Le premier clic d'une plage n'émet aucun ``change`` (il n'y
            // a pas encore de valeur à annoncer), donc le scope du picker
            // ne peut pas représenter cet état : il n'a que ``vstart`` /
            // ``vend``, tous deux vides. Or le ``bz-effect`` miroir du
            // wrapper traite ce scope comme la source de vérité et pousse
            // ``''`` dans l'attribut dès qu'il re-tourne — ce qui arrive à
            // CHAQUE swap HTMX, le bridge rescannant la cible. Tant que le
            // début en attente vivait dans l'attribut, ce miroir l'effaçait
            // et le second clic rouvrait une plage au lieu de la fermer :
            // le champ restait vide et l'utilisateur cliquait sans fin.
            //
            // Ici le miroir n'a plus rien à écraser — il réécrit ``''``
            // par-dessus ``''``, donc aucun ``attributeChangedCallback``,
            // donc l'attente survit. L'attribut ne porte plus que du
            // COMMITÉ ; c'est la surface de synchro avec l'extérieur, pas
            // un tampon d'état transitoire. ``_hoverDate`` avait déjà
            // exactement ce statut, d'où le voisinage.
            this._pendingStart = null;
            this._initialized = false;
            this._renderScheduled = false;
        }

        connectedCallback() {
            if (this._initialized) return;
            this._initialized = true;

            // Seed the displayed month from the ``month`` attribute or
            // today. We never re-read this from the attribute after
            // init — prev/next clicks mutate it internally and write
            // back to the attribute so external observers see the
            // current displayed month.
            var monthAttr = this.getAttribute('month');
            if (monthAttr) {
                var parts = monthAttr.split('-');
                this._displayedYear = parseInt(parts[0], 10);
                this._displayedMonth = parseInt(parts[1], 10) - 1;
            }
            if (this._displayedYear == null || isNaN(this._displayedYear)) {
                var t = new Date();
                this._displayedYear = t.getFullYear();
                this._displayedMonth = t.getMonth();
            }

            // Bretzel SSR emits the header + weekday row + an EMPTY
            // grid container (``data-bz-cal-grid`` with no children).
            // Fill the grid here on first connect ; subsequent attr
            // changes go through ``attributeChangedCallback`` →
            // ``_render`` which replaces all rendered children.
            this._render();
        }

        attributeChangedCallback(name, oldVal, newVal) {
            if (!this._initialized) return;     // initial attr setting
            if (oldVal === newVal) return;

            // Une écriture de ``value`` qui PASSE est autoritaire : elle
            // vient soit de notre propre commit, soit de l'extérieur (le
            // miroir du wrapper, un ``.set()``). Dans les deux cas la
            // sélection en cours est caduque. Le miroir qui repousse la
            // même valeur ne passe PAS par ici (garde ``oldVal ===
            // newVal`` ci-dessus), donc une attente ne meurt jamais d'un
            // simple rescan — c'est exactement l'invariant recherché.
            if (name === 'value') this._pendingStart = null;

            // Sync the displayed month if the external observer (e.g.
            // a ClientBinding) wrote back through ``month=``.
            if (name === 'month' && newVal) {
                var parts = newVal.split('-');
                var y = parseInt(parts[0], 10);
                var m = parseInt(parts[1], 10) - 1;
                if (!isNaN(y) && !isNaN(m) &&
                    (y !== this._displayedYear ||
                     m !== this._displayedMonth)) {
                    this._displayedYear = y;
                    this._displayedMonth = m;
                }
            }

            this._scheduleRender();
        }

        _scheduleRender() {
            // Batch multiple attribute changes (typical when idiomorph
            // morphs several attrs in one tick) into a single render.
            if (this._renderScheduled) return;
            this._renderScheduled = true;
            queueMicrotask(() => {
                this._renderScheduled = false;
                this._render();
            });
        }

        // ── Public DOM API ───────────────────────────────────────────

        set(value) {
            var mode = this.getAttribute('mode') || 'picker';
            var serialized;
            if (mode === 'range' && Array.isArray(value)) {
                serialized = JSON.stringify(value);
            } else if (value == null) {
                serialized = '';
            } else {
                serialized = String(value);
            }
            // Explicite, et pas seulement via ``attributeChangedCallback``:
            // un ``.clear()`` sur un calendrier dont l'attribut vaut déjà
            // ``''`` ne déclenche aucun callback, et laisserait sinon une
            // sélection en attente survivre à un effacement demandé.
            this._pendingStart = null;
            this.setAttribute('value', serialized);
            this._syncHiddenAndFireChange(serialized, value);
        }

        clear() {
            this.set(null);
        }

        /* Repeindre APRÈS un morph qui a effacé le corps rendu ici.
         *
         * Le trou, mesuré le 2026-08-21 : le SSR émet un conteneur de
         * grille VIDE que ``connectedCallback`` remplit. Quand idiomorph
         * morphe le calendrier EN PLACE — le refresh d'une zone
         * ``@refreshable`` qui le contient — les enfants reviennent à la
         * version serveur, donc vides. ``connectedCallback`` ne re-tourne
         * pas (le nœud a SURVÉCU), ``attributeChangedCallback`` non plus
         * (aucun attribut n'a changé) : personne ne re-remplit, et le
         * calendrier reste amputé DÉFINITIVEMENT.
         *
         * L'en-tête du fichier dit que la configuration vit dans des
         * attributs « que idiomorph peut morpher librement ». C'est vrai
         * des ATTRIBUTS ; ça ne l'est pas des ENFANTS, et c'est la
         * contrepartie que le choix « custom element » n'avait pas tenue.
         *
         * Appelé par le ``bz-effect`` que le Python pose sur la racine,
         * et c'est bien ``bz-effect`` et PAS ``bz-init`` : ce dernier est
         * one-shot par NŒUD (``el._bzInitDone``, qui survit
         * explicitement au rebind), or idiomorph morphe EN PLACE — le
         * nœud survit, donc un ``bz-init`` ne re-tournerait jamais. Un
         * ``bz-effect`` est disposé puis refait par ``bindEl`` à chaque
         * rescan, et le bridge rescanne sa cible à chaque swap. Même
         * choix et même raison que ``_observe()`` du SignaturePad, qui
         * écrit noir sur blanc « à chaque rescan plutôt qu'au bz-init ».
         *
         * Aucun vocabulaire neuf, donc : pas de ``hx-preserve``, pas de
         * hook de morph maison. Le jour où un DEUXIÈME custom element
         * existera, ce sera le moment d'en faire une politique du
         * runtime — pas avant.
         *
         * La garde est une mesure du DOM, et c'est ici légitime : elle ne
         * DÉRIVE rien (aucun affichage n'en dépend), elle constate un
         * fait ponctuel — mes enfants ont-ils été effacés — au seul
         * moment où la question se pose. Sans elle, chaque swap sans
         * rapport repeindrait la grille et tuerait l'aperçu de plage en
         * cours de survol.
         */
        rehydrate() {
            if (!this._initialized) return;   // connectedCallback rendra
            var body = this.querySelector('[data-bz-cal-grid]') ||
                       this.querySelector('[data-bz-cal-months]');
            if (!body || body.firstElementChild) return;
            this._render();
        }

        // The picker's selected date (single) or range start, as an ISO
        // string — or null when nothing is picked. Used by ``focus()`` to
        // know where to navigate.
        _selectedDate() {
            var mode = this.getAttribute('mode') || 'picker';
            // ``week`` rend une DATE scalaire comme ``picker`` (le premier
            // jour de la semaine), pas une paire — donc même lecture.
            if (mode === 'picker' || mode === 'week') {
                var v = this.getAttribute('value');
                return (v && /^\d{4}-\d{2}-\d{2}$/.test(v)) ? v : null;
            }
            // Une plage en cours de sélection A un début, même s'il n'est
            // pas encore dans l'attribut : ``.focus()`` doit naviguer vers
            // LUI, pas vers l'ancienne plage commitée.
            if (this._pendingStart) return this._pendingStart;
            var arr = parseJSON(this.getAttribute('value') || '', []);
            return (Array.isArray(arr) && arr[0]
                && /^\d{4}-\d{2}-\d{2}$/.test(arr[0])) ? arr[0] : null;
        }

        focus() {
            // If a date is SELECTED but sits outside the displayed month,
            // navigate the grid to it FIRST — otherwise its cell doesn't
            // exist in the DOM and ``.focus()`` silently lands on the
            // current view's first cell (no visible movement). This is
            // what makes ``.focus()`` truly "focus the selected date".
            var self = this;
            var sel = this._selectedDate();
            if (sel) {
                var y = +sel.slice(0, 4);
                var m = +sel.slice(5, 7) - 1;
                if (y !== this._displayedYear || m !== this._displayedMonth) {
                    this._displayedYear = y;
                    this._displayedMonth = m;
                    // Sync the Python header scope + any ``month`` binding.
                    // ``_dispatchMonthChange`` sets the ``month`` attr, which
                    // schedules a microtask ``_render`` — so DON'T render
                    // synchronously here (that cell would be blown away and
                    // focus stolen). Defer the focus one microtask so it runs
                    // AFTER that render rebuilds the grid.
                    this._dispatchMonthChange();
                    queueMicrotask(function () { self._focusBestCell(); });
                    return;
                }
            }
            this._focusBestCell();
        }

        // Focus the SELECTED date, then TODAY, then the first focusable
        // cell in the CURRENT view. ``data-selected`` / ``data-today`` are
        // stamped per cell in ``_render`` ; each falls through gracefully
        // (querySelector → null) to the next candidate.
        _focusBestCell() {
            var target =
                this.querySelector(
                    '[data-day-cell][data-selected="true"]'
                    + ':not([aria-disabled="true"])'
                ) ||
                this.querySelector(
                    '[data-day-cell][data-today="true"]'
                    + ':not([aria-disabled="true"])'
                ) ||
                this.querySelector(
                    '[data-day-cell]:not([aria-disabled="true"])'
                );
            if (target) target.focus();
        }

        blur() {
            var focused = this.querySelector('[data-day-cell]:focus');
            if (focused) focused.blur();
        }

        prevMonth() {
            if (this._displayedMonth === 0) {
                this._displayedMonth = 11;
                this._displayedYear -= 1;
            } else {
                this._displayedMonth -= 1;
            }
            this._dispatchMonthChange();
            this._scheduleRender();
        }

        nextMonth() {
            if (this._displayedMonth === 11) {
                this._displayedMonth = 0;
                this._displayedYear += 1;
            } else {
                this._displayedMonth += 1;
            }
            this._dispatchMonthChange();
            this._scheduleRender();
        }

        // ── Internals ────────────────────────────────────────────────

        _dispatchMonthChange() {
            this.dispatchEvent(new CustomEvent('month-change', {
                detail: {
                    year: this._displayedYear,
                    month: this._displayedMonth + 1,
                },
                bubbles: true,
            }));
            var newIso = this._displayedYear + '-' +
                String(this._displayedMonth + 1).padStart(2, '0') + '-01';
            this._suppressMonthSync = true;
            this.setAttribute('month', newIso);
            this._suppressMonthSync = false;
            // Write back to bound ClientState (``month=binding`` at the
            // Python call site). Without this the Client playground
            // ``ui.text(client.displayed_month)`` echo stays empty.
            this._writeBinding(
                this.getAttribute('data-bz-month-path'), newIso
            );
        }

        _syncHiddenAndFireChange(serializedAttr, detailValue) {
            var hidden = this.querySelector('input[type="hidden"]');
            if (hidden) {
                hidden.value = serializedAttr;
                hidden.dispatchEvent(
                    new Event('change', { bubbles: true })
                );
            }
            // Write back to bound ClientState (``value=binding`` at the
            // Python call site). Without this the Client playground
            // ``ui.text(client.picked)`` echo stays empty.
            this._writeBinding(
                this.getAttribute('data-bz-value-path'), detailValue
            );
            this.dispatchEvent(new CustomEvent('change', {
                detail: { value: detailValue },
                bubbles: true,
            }));
        }

        _writeBinding(path, value) {
            // Walk a ``$bz.state.X.y.field`` dotted path and assign
            // ``value`` to the leaf. Bails silently if the runtime
            // store hasn't booted yet (defensive — connectedCallback
            // can race with bootstrap in pathological cases).
            if (!path) return;
            var bz = window.$bz;
            if (!bz || !bz.state) return;
            var parts = path.split('.');
            if (parts[0] === '$bz') parts.shift();
            if (parts[0] === 'state') parts.shift();
            if (parts.length === 0) return;
            var obj = bz.state;
            for (var i = 0; i < parts.length - 1; i++) {
                if (obj[parts[i]] == null) return;
                obj = obj[parts[i]];
            }
            obj[parts[parts.length - 1]] = value;
        }

        _parseConfig() {
            var thisYear = new Date().getFullYear();
            return {
                mode: this.getAttribute('mode') || 'picker',
                value: this.getAttribute('value') || '',
                weekstart:
                    (parseInt(this.getAttribute('weekstart') || '1', 10)
                        % 7 + 7) % 7,
                min: this.getAttribute('min') || '',
                max: this.getAttribute('max') || '',
                disabled: this.hasAttribute('disabled'),
                disabledSet: new Set(
                    parseJSON(this.getAttribute('disabled-dates'), [])
                ),
                // ``marks`` : {iso: compte}. Le gabarit du nom
                // accessible arrive RESOLU du serveur — la table des
                // mots du framework est en Python, et cette grille est
                // batie ici.
                marks: parseJSON(this.getAttribute('marks'), {}),
                markLabel: this.getAttribute('data-bz-mark-label')
                    || '{day}, {n} events',
                weekdayNames: parseJSON(
                    this.getAttribute('weekday-names'), DEFAULT_WEEKDAYS()
                ),
                // Les noms ENTIERS, pour le ``title=`` des en-tetes.
                //
                // Vide des que l'app fournit ses propres abreviations :
                // deviner « mer. » -> « mercredi » marcherait en francais
                // et nulle part ailleurs, et un title FAUX est pire que
                // pas de title. Une app qui veut les siens declare sa
                // langue et laisse la locale faire.
                weekdayLongNames: this.getAttribute('weekday-names')
                    ? []
                    : DEFAULT_WEEKDAYS_LONG(),
                monthNames: parseJSON(
                    this.getAttribute('month-names'), DEFAULT_MONTHS()
                ),
                theme: parseJSON(
                    this.getAttribute('data-bz-theme'), {}
                ),
                yearMin: parseInt(
                    this.getAttribute('data-bz-year-min') || (thisYear - 10),
                    10,
                ),
                yearMax: parseInt(
                    this.getAttribute('data-bz-year-max') || (thisYear + 10),
                    10,
                ),
            };
        }

        /* La grille d'ANNÉE du mode ``month`` — 12 cellules au lieu du
         * couple ligne-de-jours + grille-de-jours.
         *
         * C'est le SECOND type de grille du composant, et le seul point
         * où il ne rend pas des jours. Tout le reste (header Python,
         * input caché, dispatch du change, listeners impératifs) est
         * partagé — d'où le retour anticipé dans ``_render`` plutôt
         * qu'une classe séparée.
         *
         * Les bornes se comparent en ``"YYYY-MM"``, jamais en dates :
         * le format est zéro-paddé, donc il se trie lexicographiquement
         * comme chronologiquement. ``min`` / ``max`` arrivent en
         * ``YYYY-MM-DD`` — on les tronque, ce qui rend un mois PARTIEL-
         * lement autorisé cliquable, et c'est voulu : un ``min`` au
         * 15 mars n'interdit pas « mars ».
         */
        _renderMonthGrid(cfg) {
            var theme = cfg.theme || {};
            var cellCls = escapeAttr(theme.month_cell || '');
            var selected = /^\d{4}-\d{2}$/.test(cfg.value) ? cfg.value : '';
            var now = new Date();
            var currentYm = now.getFullYear() + '-' +
                String(now.getMonth() + 1).padStart(2, '0');
            var lo = cfg.min ? cfg.min.slice(0, 7) : '';
            var hi = cfg.max ? cfg.max.slice(0, 7) : '';
            var html = '';
            for (var m = 0; m < 12; m++) {
                var ym = this._displayedYear + '-' +
                    String(m + 1).padStart(2, '0');
                var dis = (lo && ym < lo) || (hi && ym > hi);
                html +=
                    '<button type="button" data-month-cell ' +
                    'class="' + cellCls + '" ' +
                    'data-value="' + ym + '" ' +
                    'data-selected="' + (ym === selected) + '" ' +
                    'data-current="' + (ym === currentYm) + '" ' +
                    'aria-disabled="' + dis + '" ' +
                    'tabindex="' + (dis ? -1 : 0) + '"' +
                    (cfg.disabled ? ' disabled' : '') +
                    '><span>' + escapeAttr(cfg.monthNames[m]) + '</span>' +
                    '</button>';
            }
            return '<div data-bz-cal-months class="' +
                escapeAttr(theme.month_grid || '') + '">' + html + '</div>';
        }

        _render() {
            var cfg = this._parseConfig();
            if (cfg.mode === 'month') {
                this._replaceBody(this._renderMonthGrid(cfg));
                return;
            }
            var label = cfg.monthNames[this._displayedMonth] + ' ' +
                this._displayedYear;
            var rotatedWeekdays = cfg.weekdayNames
                .slice(cfg.weekstart)
                .concat(cfg.weekdayNames.slice(0, cfg.weekstart));
            // Tournee du MEME nombre de crans, sinon le title d'une
            // colonne nommerait le jour d'a cote — pire que rien.
            var longs = cfg.weekdayLongNames || [];
            var rotatedLong = longs.length === 7
                ? longs.slice(cfg.weekstart).concat(longs.slice(0, cfg.weekstart))
                : [];

            // Range bounds for highlighting
            var rangeStart = '', rangeEnd = '';
            if (cfg.mode === 'range') {
                // Le garde de mode est load-bearing et reste UNE seule
                // condition : un attribut ``mode`` qui bascule pendant
                // qu'une attente est vivante ne la nettoie pas.
                if (this._pendingStart) {
                    // Sélection en cours : le début en attente prime sur
                    // la valeur commitée, encore l'ANCIENNE plage.
                    rangeStart = this._pendingStart;
                } else if (cfg.value) {
                    var arr = parseJSON(cfg.value, []);
                    if (Array.isArray(arr) && arr.length >= 1) {
                        rangeStart = arr[0] || '';
                        rangeEnd = arr[1] || '';
                    }
                }
            } else if (cfg.mode === 'week' && cfg.value) {
                // Une semaine EST une plage fermée de 7 jours. La rendre
                // comme telle réutilise TOUT le rendu de bande du mode
                // range — extrémités plates côté intérieur, milieu
                // teinté — au lieu d'inventer un second vocabulaire
                // visuel pour la même idée.
                rangeStart = weekStartOf(cfg.value, cfg.weekstart);
                rangeEnd = addDays(rangeStart, 6);
            }
            var picked = cfg.mode === 'picker' ? cfg.value : '';

            var self = this;
            function isSelected(s) {
                if (cfg.mode === 'picker') return s === picked;
                return s === rangeStart || s === rangeEnd;
            }
            function rangeBounds() {
                if (cfg.mode === 'week') {
                    // Pas de survol progressif ici : une semaine est
                    // choisie d'un seul clic, donc ses bornes sont
                    // toujours connues et complètes.
                    return rangeStart
                        ? { lo: rangeStart, hi: rangeEnd }
                        : { lo: null, hi: null };
                }
                if (cfg.mode !== 'range' || !rangeStart) {
                    return { lo: null, hi: null };
                }
                var effEnd = rangeEnd || self._hoverDate;
                if (!effEnd) {
                    return { lo: rangeStart, hi: rangeStart };
                }
                var lo = rangeStart < effEnd ? rangeStart : effEnd;
                var hi = rangeStart < effEnd ? effEnd : rangeStart;
                return { lo: lo, hi: hi };
            }
            function isInRange(s) {
                var b = rangeBounds();
                return b.lo !== null && s > b.lo && s < b.hi;
            }
            function isRangeStart(s) {
                var b = rangeBounds();
                return b.lo !== null && s === b.lo && b.lo !== b.hi;
            }
            function isRangeEnd(s) {
                var b = rangeBounds();
                return b.hi !== null && s === b.hi && b.lo !== b.hi;
            }
            function isCellDisabled(s) {
                if (cfg.disabledSet.has(s)) return true;
                if (cfg.min && s < cfg.min) return true;
                if (cfg.max && s > cfg.max) return true;
                return false;
            }

            // Compute the 6 × 7 grid
            var first = new Date(
                this._displayedYear, this._displayedMonth, 1
            );
            var offset = (first.getDay() - cfg.weekstart + 7) % 7;
            var todayStr = iso(new Date());
            var theme = cfg.theme || {};
            var cellsHTML = '';
            for (var w = 0; w < 6; w++) {
                for (var c = 0; c < 7; c++) {
                    var d = new Date(
                        this._displayedYear, this._displayedMonth,
                        1 + w * 7 + c - offset
                    );
                    var s = iso(d);
                    var day = d.getDate();
                    var inMonth = d.getMonth() === this._displayedMonth;
                    var isDis = isCellDisabled(s);
                    // Une marque ne vit QUE dans le mois affiche : la
                    // grille deborde de six jours de part et d'autre, et
                    // pastiller un 31 juillet visible depuis aout ferait
                    // lire une charge qui n'est pas celle du mois qu'on
                    // regarde.
                    var mark = inMonth ? (cfg.marks[s] | 0) : 0;
                    var markHTML = mark > 0
                        ? '<span class="' + escapeAttr(theme.day_mark || '') +
                          '" aria-hidden="true"></span>'
                        : '';
                    var markLabel = mark > 0
                        ? ' aria-label="' + escapeAttr(
                              cfg.markLabel
                                  .replace('{day}', day)
                                  .replace('{n}', mark)
                          ) + '"'
                        : '';
                    cellsHTML +=
                        '<button type="button" data-day-cell ' +
                        'class="' + escapeAttr(theme.day_cell || '') + '" ' +
                        'data-date="' + s + '" ' +
                        'data-mark="' + mark + '"' + markLabel + ' ' +
                        'data-outside="' + (!inMonth) + '" ' +
                        'data-today="' + (s === todayStr) + '" ' +
                        'data-selected="' + isSelected(s) + '" ' +
                        'data-in-range="' + isInRange(s) + '" ' +
                        'data-range-start="' + isRangeStart(s) + '" ' +
                        'data-range-end="' + isRangeEnd(s) + '" ' +
                        'aria-disabled="' + isDis + '" ' +
                        'tabindex="' + (isDis ? -1 : 0) + '"' +
                        (cfg.disabled ? ' disabled' : '') +
                        '><span>' + day + '</span>' + markHTML + '</button>';
                }
            }

            var chevronCls = escapeAttr(theme.chevron_class || '');
            var navCls = escapeAttr(theme.nav_button || '');
            var labelCls = escapeAttr(theme.month_label || '');
            var weekdayRowCls = escapeAttr(theme.weekday_row || '');
            var weekdayCls = escapeAttr(theme.weekday || '');
            var weekRowCls = escapeAttr(theme.week_row || '');
            var headerCls = escapeAttr(theme.header || '');
            var disabledAttr = cfg.disabled ? ' disabled' : '';

            var weekdaysHTML = '';
            for (var i = 0; i < rotatedWeekdays.length; i++) {
                // ``title`` seulement s'il APPORTE quelque chose : le
                // reflux sans Intl rend les memes abreviations des deux
                // cotes, et un title identique au texte visible est du
                // bruit pour un lecteur d'ecran.
                var entier = rotatedLong[i];
                var titre = (entier && entier !== rotatedWeekdays[i])
                    ? ' title="' + escapeAttr(entier) + '"'
                    : '';
                weekdaysHTML +=
                    '<div class="' + weekdayCls + '"' + titre + '>' +
                    escapeAttr(rotatedWeekdays[i]) + '</div>';
            }

            // The header (prev/next + month/year selectors) is now
            // rendered by Python using ``ui.dropdown`` + ``ui.icon_button``
            // so it inherits the framework theme. We preserve any
            // ``data-bz-cal-header`` child the Python side emitted and
            // never generate one here.
            var html =
                '<div data-bz-cal-weekdays class="' + weekdayRowCls + '">' +
                  weekdaysHTML +
                '</div>' +
                '<div data-bz-cal-grid class="' + weekRowCls + '">' +
                  cellsHTML +
                '</div>';

            this._replaceBody(html);
        }

        /* Remplacer le CORPS du calendrier en préservant les deux enfants
         * qui ne viennent pas d'ici : l'input caché (porteur de form
         * data) et le header rendu par Python (``data-bz-cal-header``,
         * qui contient les IconButton et les dropdowns du thème).
         *
         * Extrait de ``_render`` quand le mode ``month`` est arrivé : il
         * rend une grille TOTALEMENT différente mais doit préserver
         * exactement les mêmes deux enfants. Recopier la boucle aurait
         * garanti qu'un des deux modes oublie l'un d'eux un jour.
         */
        _replaceBody(html) {
            var hidden = this.querySelector('input[type="hidden"]');
            var pyHeader = this.querySelector('[data-bz-cal-header]');
            var children = Array.from(this.childNodes);
            for (var i = 0; i < children.length; i++) {
                var child = children[i];
                if (child === hidden) continue;
                if (child === pyHeader) continue;
                this.removeChild(child);
            }
            this.insertAdjacentHTML('beforeend', html);
            this._wireListeners();
        }

        _paintHoverPreview() {
            // Patch only the ``data-in-range`` / ``data-range-start`` /
            // ``data-range-end`` attributes on EXISTING cells. No
            // children removal, no listener re-bind. Used during
            // mouse hover preview to avoid the "cell vanishes under
            // the cursor" bug.
            // Ce chemin n'existe QUE pendant une sélection en cours : ses
            // deux appelants sont derrière ``_pendingStart`` (le
            // ``mouseenter`` directement, le ``mouseleave`` via
            // ``_hoverDate`` qui n'est posé que là). Il n'a donc jamais à
            // lire l'attribut — qui, depuis le fix, ne peut de toute façon
            // plus porter de paire à moitié ouverte. Le tester ici
            // contredirait le reste du fichier.
            //
            // Le garde de mode est implicite : ``_pendingStart`` n'est posé
            // que dans la branche ``range`` de ``_handleCellClick``.
            var rangeStart = this._pendingStart;
            if (!rangeStart) return;
            var effEnd = this._hoverDate || '';
            var lo = '', hi = '';
            if (effEnd && effEnd !== rangeStart) {
                lo = rangeStart < effEnd ? rangeStart : effEnd;
                hi = rangeStart < effEnd ? effEnd : rangeStart;
            }
            var cells = this.querySelectorAll('[data-day-cell]');
            cells.forEach(function (cell) {
                var s = cell.getAttribute('data-date');
                var inRange = !!(lo && s > lo && s < hi);
                var isStart = !!(lo && s === lo);
                var isEnd = !!(hi && s === hi && lo !== hi);
                cell.setAttribute('data-in-range', inRange.toString());
                cell.setAttribute('data-range-start', isStart.toString());
                cell.setAttribute('data-range-end', isEnd.toString());
            });
        }

        _wireListeners() {
            var self = this;
            // Mode ``month`` : des cellules d'un autre type, un clic d'une
            // autre nature. Câblé AVANT la boucle des jours parce qu'en
            // mode month il n'y a aucune cellule de jour — la boucle
            // ci-dessous tourne à vide.
            this.querySelectorAll('[data-month-cell]').forEach(function (c) {
                c.onclick = function () {
                    if (c.getAttribute('aria-disabled') === 'true') return;
                    var ym = c.getAttribute('data-value');
                    self.setAttribute('value', ym);
                    self._syncHiddenAndFireChange(ym, ym);
                };
            });
            // Prev / next buttons live in the Python-rendered header
            // (``data-bz-cal-header``). They're ``bz-on:click``
            // handlers that mutate the wrapper's ``year`` / ``month``
            // scope ; nothing to wire here.

            var cells = this.querySelectorAll('[data-day-cell]');
            var mode = this.getAttribute('mode') || 'picker';
            cells.forEach(function (cell) {
                cell.onclick = function () { self._handleCellClick(cell); };
                if (mode === 'range') {
                    // CRITICAL : mouse events must NOT trigger a full
                    // re-render. Each ``_render`` removes + re-inserts
                    // every cell, which means the cell currently under
                    // the cursor is replaced with a fresh DOM node — but
                    // that node never receives a ``mouseenter`` (the
                    // cursor was already over the position when it
                    // appeared), so ``_hoverDate`` freezes at the last
                    // value AND the new cell's ``onclick`` may not have
                    // settled by the time the user clicks. Bug visible
                    // on every range pick : the hover bar gets stuck
                    // mid-flight and the second click vanishes.
                    //
                    // Fix : ``_paintHoverPreview`` patches the data-*
                    // attrs IN PLACE on the existing cells. No DOM
                    // mutation beyond the affected attributes, so the
                    // cursor stays over the SAME node from start to
                    // finish, listeners stay live.
                    cell.onmouseenter = function () {
                        // « Sommes-nous entre les deux clics ? » se lit
                        // désormais sur ``_pendingStart`` — l'attribut ne
                        // porte plus jamais de paire à moitié ouverte.
                        if (!self._pendingStart) return;
                        self._hoverDate = cell.getAttribute('data-date');
                        self._paintHoverPreview();
                    };
                    cell.onmouseleave = function () {
                        if (self._hoverDate) {
                            self._hoverDate = null;
                            self._paintHoverPreview();
                        }
                    };
                }
            });

            // Listen for the imperative ``bz-set`` / ``bz-prev-month`` /
            // ``bz-next-month`` events dispatched by Python's
            // ``.set()`` / ``.prev_month()`` / ``.next_month()`` methods.
            // Also relay ``focusin``/``focusout`` (which DO bubble from
            // the cells) as ``focus``/``blur`` CustomEvents on the root —
            // this is what makes ``on_focus`` / ``on_blur`` Python
            // kwargs fire when a cell receives keyboard focus, since
            // native focus / blur don't bubble.
            if (!this._wiredImperativeListeners) {
                this._wiredImperativeListeners = true;
                this.addEventListener('bz-set', function (e) {
                    self.set(e.detail && e.detail.value);
                });
                this.addEventListener('bz-prev-month', function () {
                    self.prevMonth();
                });
                this.addEventListener('bz-next-month', function () {
                    self.nextMonth();
                });
                this.addEventListener('focusin', function (e) {
                    // Only relay child focus, not focus on the root
                    // itself (which would be ambiguous and rare).
                    if (e.target !== self) {
                        self.dispatchEvent(new CustomEvent('focus', {
                            detail: { target: e.target },
                            bubbles: true,
                        }));
                    }
                });
                this.addEventListener('focusout', function (e) {
                    if (e.target !== self) {
                        self.dispatchEvent(new CustomEvent('blur', {
                            detail: { target: e.target },
                            bubbles: true,
                        }));
                    }
                });
            }
        }

        _handleCellClick(cell) {
            if (cell.getAttribute('aria-disabled') === 'true') return;
            var s = cell.getAttribute('data-date');
            var mode = this.getAttribute('mode') || 'picker';

            if (mode === 'picker') {
                this.setAttribute('value', s);
                this._syncHiddenAndFireChange(s, s);
                return;
            }

            if (mode === 'week') {
                // Cliquer N'IMPORTE quel jour choisit sa semaine, et ce
                // qui sort est le PREMIER jour de cette semaine — jamais
                // le jour cliqué. Sans ce recalage, deux clics dans la
                // même semaine produiraient deux valeurs différentes
                // pour la même sélection.
                var ws = (parseInt(
                    this.getAttribute('weekstart') || '1', 10
                ) % 7 + 7) % 7;
                var start = weekStartOf(s, ws);
                this.setAttribute('value', start);
                this._syncHiddenAndFireChange(start, start);
                return;
            }

            // range mode — deux temps : on ouvre sur un début EN ATTENTE,
            // on ferme sur le second clic. Seule la fermeture touche
            // l'attribut ``value`` (cf. ``_pendingStart``).
            var rangeStart = this._pendingStart;

            if (!rangeStart) {
                this._hoverDate = null;
                this._pendingStart = s;
                // Repeindre : sans écriture d'attribut il n'y a plus de
                // ``attributeChangedCallback`` pour le faire. On passe par
                // ``_scheduleRender`` et pas ``_render`` pour garder le
                // rendu ASYNCHRONE comme avant — le chemin par l'attribut
                // batchait déjà en microtask.
                this._scheduleRender();
                return;
            }

            // Close the range
            var newStart = rangeStart, newEnd = s;
            if (s < rangeStart) {
                newStart = s;
                newEnd = rangeStart;
            }
            this._hoverDate = null;
            this._pendingStart = null;
            var newVal = JSON.stringify([newStart, newEnd]);
            this.setAttribute('value', newVal);
            this._syncHiddenAndFireChange(newVal, [newStart, newEnd]);
        }
    }

    customElements.define('bz-calendar', BzCalendar);
})();


/* 08_file_upload.js — $bz.fileUpload.makeScope factory for ui.file_upload. */
// ════════════════════════════════════════════════════════════════════════
// 08 FILE UPLOAD — bz-data scope factory for <ui.file_upload>.
//
// Why a runtime slab
// ──────────────────
// The component carries enough JS for the inline-bz-data shape to bloat
// every instance by ~3 kB. Externalising into one factory means each
// instance just drops ``bz-data="$bz.fileUpload.makeScope({el: $el, …})"``
// (~250 chars). The factory owns :
//
// V3 notes : (a) the scope captures its root element (``opts.el``,
// available in the ``bz-data`` expression) — V3 scope methods get no
// ``$root`` / ``$refs`` / ``$dispatch`` magic. (b) V3 signals compare
// by identity, so array mutations REASSIGN (``files = [...]``) and
// per-file updates replace the entry object (keyed by id) so the
// ``bz-for`` rows re-render.
// The factory owns :
//
//   1. Drag state (``isDragging``).
//   2. The file list (each entry carries the raw ``File`` + UI status :
//      progress / done / error).
//   3. Client-side validation : ``accept`` filter, ``max_size_mb``,
//      ``max_files``, single vs multi.
//   4. DataTransfer sync with the hidden native ``<input type="file">``
//      so a parent ``<form>`` submit ships exactly what's displayed.
//   5. Image-preview thumbnails via ``URL.createObjectURL`` (revoked on
//      remove to free memory).
//   6. Optional async upload mode (``uploadUrl`` opt-in) via per-file
//      XMLHttpRequest with progress events. ``upload_*`` Alpine events
//      dispatch with the raw ``File`` so a ClientBinding push or a
//      server callable receives identity.
//
// Public DOM event shape (what the framework hooks onto) :
//   change            — files added / removed
//   upload-start      — async POST started for one file
//   upload-progress   — per-file progress %, NOT bridged to the server
//                       (every-tick round-trip would melt the wire)
//   upload-complete   — async POST returned 2xx
//   upload-error      — async POST returned 4xx/5xx or threw
//
// Validation errors live in ``errors`` (array of strings) — rendered
// inline by the component. We don't dispatch them as events ; the panel
// is reactive on the array.
// ════════════════════════════════════════════════════════════════════════

(function () {
    'use strict';

    if (typeof window === 'undefined') return;
    if (!window.$bz) window.$bz = {};
    if (window.$bz.fileUpload) return;

    function formatSize(bytes) {
        if (bytes >= 1048576) return (bytes / 1048576).toFixed(1) + ' MB';
        if (bytes >= 1024) return (bytes / 1024).toFixed(0) + ' KB';
        return bytes + ' B';
    }

    // Compare ``file`` against ``accept`` token (mirror of the HTML
    // accept-attribute matching, simplified) :
    //   ".pdf"      → extension match
    //   "image/*"   → MIME family match
    //   "image/png" → exact MIME match
    function matchesToken(file, token) {
        token = token.trim().toLowerCase();
        if (!token) return true;
        if (token.charAt(0) === '.') {
            const idx = file.name.lastIndexOf('.');
            if (idx < 0) return false;
            return file.name.slice(idx).toLowerCase() === token;
        }
        const type = (file.type || '').toLowerCase();
        if (token.endsWith('/*')) {
            return type.startsWith(token.slice(0, -1));
        }
        return type === token;
    }

    function matchesAccept(file, acceptList) {
        if (!acceptList || acceptList.length === 0) return true;
        for (let i = 0; i < acceptList.length; i++) {
            if (matchesToken(file, acceptList[i])) return true;
        }
        return false;
    }

    // Stable id per file entry so ``bz-for`` :key= stays consistent
    // through removals (browsers don't expose a native handle).
    let _uid = 0;
    function nextId() { _uid += 1; return _uid; }

    function isImage(file) {
        return (file.type || '').startsWith('image/');
    }

    function makeScope(opts) {
        const acceptList = opts.accept
            ? String(opts.accept).split(',').map((s) => s.trim()).filter(Boolean)
            : null;
        const maxSizeMB = opts.maxSizeMB || null;
        const maxFiles = opts.maxFiles || null;
        const multiple = !!opts.multiple;
        const showPreviews = opts.showPreviews !== false;  // default true
        const uploadUrl = opts.uploadUrl || null;

        return {
            // Root element captured from the bz-data expression — the
            // V3 replacement for Alpine's $root / $refs.
            _el: opts.el || null,
            // ── State ──────────────────────────────────────────────
            isDragging: false,
            // ``isGlobalDragActive`` flips true when the user is
            // dragging a file ANYWHERE on the page (from the OS).
            // Every dropzone subscribes via ``@dragenter.window`` so
            // the user can see the drop target highlight from any
            // scroll position. Tracked with a counter because
            // ``dragenter`` / ``dragleave`` fire one per element
            // boundary crossed ; the counter reaches 0 only when the
            // drag truly leaves the window.
            isGlobalDragActive: false,
            _globalDragCounter: 0,
            files: [],
            errors: [],

            // ⚠️ Pas de ``destroy()`` : le moteur de scope V3 n'a AUCUN
            // hook de démontage — la méthode qui vivait ici venait de
            // l'ère Alpine, où elle était appelée automatiquement, et
            // n'a plus jamais tourné depuis (audit F22/F74). Les blob
            // URLs des previews sont révoquées aux trois endroits qui
            // retirent un fichier (remplacement single-file, removeFile,
            // clear) ; ce qui reste non libéré, ce sont les previews
            // d'un composant retiré du DOM avec des fichiers encore
            // dedans. Dette connue, tracée dans inventory.md : la
            // rouvrir demande un vrai hook d'unmount côté runtime, pas
            // une méthode que personne n'appelle.

            // ── Validation + add ───────────────────────────────────
            handleFiles(fileList) {
                this.errors = [];
                let incoming = Array.from(fileList);
                let sizeRejected = 0;
                let formatRejected = 0;
                let firstReject = '';

                if (!multiple && incoming.length > 1) {
                    this.errors = this.errors.concat(['Only one file allowed.']);
                    incoming = [incoming[0]];
                }
                if (!multiple && this.files.length > 0) {
                    // Replace mode — drop the previous one (and its preview).
                    this.files.forEach((f) => {
                        if (f._preview) URL.revokeObjectURL(f._preview);
                    });
                    this.files = [];
                }
                if (multiple && maxFiles) {
                    const room = maxFiles - this.files.length;
                    if (room <= 0) {
                        this.errors = this.errors.concat(
                            ['Maximum ' + maxFiles + ' files reached.']);
                        return;
                    }
                    if (incoming.length > room) {
                        this.errors = this.errors.concat([
                            (incoming.length - room) + ' files skipped — limit ' +
                            maxFiles + ' reached.'
                        ]);
                        incoming = incoming.slice(0, room);
                    }
                }

                const accepted = [];
                for (let i = 0; i < incoming.length; i++) {
                    const f = incoming[i];
                    if (maxSizeMB && f.size > maxSizeMB * 1048576) {
                        sizeRejected += 1;
                        if (!firstReject) firstReject = f.name;
                        continue;
                    }
                    if (!matchesAccept(f, acceptList)) {
                        formatRejected += 1;
                        if (!firstReject) firstReject = f.name;
                        continue;
                    }
                    accepted.push(f);
                }

                if ((sizeRejected || formatRejected) && this.errors.length === 0) {
                    const rejected = sizeRejected + formatRejected;
                    let msg;
                    if (rejected === 1) {
                        const reason = sizeRejected
                            ? 'exceeds ' + maxSizeMB + ' MB'
                            : 'format not supported';
                        msg = firstReject + ' — ' + reason;
                    } else {
                        let reason = 'invalid';
                        if (sizeRejected && !formatRejected) reason = 'too large';
                        else if (formatRejected && !sizeRejected) reason = 'wrong format';
                        else reason = 'size or format';
                        msg = rejected + ' files skipped (' + reason + ').';
                    }
                    this.errors = this.errors.concat([msg]);
                }

                // Build the new entries then reassign ``files`` once (V3
                // signals are identity-compared — an in-place push won't
                // re-render the bz-for list).
                const newEntries = [];
                for (let i = 0; i < accepted.length; i++) {
                    const f = accepted[i];
                    newEntries.push({
                        id: nextId(),
                        file: f,
                        name: f.name,
                        size: f.size,
                        sizeLabel: formatSize(f.size),
                        type: f.type,
                        isImage: isImage(f),
                        _preview: (showPreviews && isImage(f))
                            ? URL.createObjectURL(f)
                            : null,
                        progress: 0,
                        status: 'idle',  // idle | uploading | done | error
                        error: '',
                    });
                }
                this.files = this.files.concat(newEntries);

                this.syncInput();
                this.dispatch('change', {
                    files: this.files.map((e) => e.file),
                    count: this.files.length,
                });

                if (uploadUrl) {
                    for (let i = 0; i < accepted.length; i++) {
                        // Find the entry we just pushed for this file.
                        const entry = this.files.find((e) => e.file === accepted[i]);
                        if (entry) this.uploadOne(entry.id);
                    }
                }
            },

            // Replace one entry (keyed by id) with a patched copy so the
            // keyed bz-for row re-renders (V3 entries aren't deep-reactive).
            _patchFile(id, patch) {
                this.files = this.files.map(
                    (e) => (e.id === id ? Object.assign({}, e, patch) : e),
                );
            },

            // ── Remove ─────────────────────────────────────────────
            removeFile(entry, evt) {
                if (evt) evt.preventDefault();
                if (entry._preview) URL.revokeObjectURL(entry._preview);
                if (entry._xhr) {
                    try { entry._xhr.abort(); } catch (e) {}
                }
                this.files = this.files.filter((e) => e.id !== entry.id);
                this.errors = [];
                this.syncInput();
                this.dispatch('change', {
                    files: this.files.map((e) => e.file),
                    count: this.files.length,
                });
            },

            // ── DataTransfer → native input ────────────────────────
            syncInput() {
                if (typeof DataTransfer === 'undefined') return;  // very old browsers
                const dt = new DataTransfer();
                this.files.forEach((entry) => dt.items.add(entry.file));
                const native = this._el && this._el.querySelector('input[type=file]');
                if (native) native.files = dt.files;
            },

            // ── Native input change passthrough ────────────────────
            onNativeChange(evt) {
                if (!evt.isTrusted) return;  // we set .files programmatically too
                if (evt.target.files && evt.target.files.length > 0) {
                    this.handleFiles(evt.target.files);
                }
            },

            // ── Drag-drop (instance-level) ─────────────────────────
            onDragEnter(evt) { evt.preventDefault(); this.isDragging = true; },
            onDragOver(evt)  { evt.preventDefault(); this.isDragging = true; },
            onDragLeave(evt) { evt.preventDefault(); this.isDragging = false; },
            onDrop(evt) {
                evt.preventDefault();
                this.isDragging = false;
                // Drop also tears down the global highlight on every
                // dropzone — the drag is over.
                this._globalDragCounter = 0;
                this.isGlobalDragActive = false;
                if (evt.dataTransfer && evt.dataTransfer.files) {
                    this.handleFiles(evt.dataTransfer.files);
                }
            },

            // ── Drag-drop (window-level, "page is the target") ─────
            // The handlers below subscribe to ``dragenter`` /
            // ``dragleave`` / ``drop`` on the window, so a drag from
            // the OS — anywhere on the page — surfaces this dropzone
            // as a candidate target. ``isGlobalDragActive`` flips
            // true while the drag is in flight ; the wrapper's
            // ``:class`` adds ``dropzone_global_drag`` (ring + glow)
            // so the user can see where to drop.
            //
            // ``dragenter`` / ``dragleave`` fire one PER element
            // boundary crossed (drag over a button → dragenter,
            // drag off it → dragleave). We use a counter to know
            // when the drag truly entered or left the window.
            onWindowDragEnter(evt) {
                if (!this._dragCarriesFiles(evt)) return;
                this._globalDragCounter += 1;
                this.isGlobalDragActive = true;
            },
            onWindowDragLeave(evt) {
                if (!this._dragCarriesFiles(evt)) return;
                this._globalDragCounter -= 1;
                if (this._globalDragCounter <= 0) {
                    this._globalDragCounter = 0;
                    this.isGlobalDragActive = false;
                }
            },
            onWindowDrop() {
                this._globalDragCounter = 0;
                this.isGlobalDragActive = false;
            },

            _dragCarriesFiles(evt) {
                // ``dataTransfer.types`` is a DOMStringList containing
                // 'Files' for OS-originated drags ; for in-page drags
                // it'll be 'text/plain' or similar. Filter so we don't
                // highlight on a Notion-style block drag.
                const types = evt.dataTransfer && evt.dataTransfer.types;
                if (!types) return false;
                for (let i = 0; i < types.length; i++) {
                    if (types[i] === 'Files') return true;
                }
                return false;
            },

            // ── Browse-trigger click (delegated to native input) ──
            openPicker() {
                const native = this._el && this._el.querySelector('input[type=file]');
                if (native) native.click();
            },

            // ── Async upload (one file, keyed by id) ───────────────
            uploadOne(id) {
                const entry0 = this.files.find((e) => e.id === id);
                if (!entry0) return;
                const file = entry0.file;
                this._patchFile(id, { status: 'uploading', progress: 0, error: '' });
                this.dispatch('upload-start', { file: file });

                const xhr = new XMLHttpRequest();
                this._patchFile(id, { _xhr: xhr });
                xhr.upload.addEventListener('progress', (e) => {
                    if (e.lengthComputable) {
                        const pct = Math.round((e.loaded / e.total) * 100);
                        this._patchFile(id, { progress: pct });
                        this.dispatch('upload-progress', { file: file, progress: pct });
                    }
                });
                xhr.addEventListener('load', () => {
                    if (xhr.status >= 200 && xhr.status < 300) {
                        this._patchFile(id, { status: 'done', progress: 100 });
                        this.dispatch('upload-complete', {
                            file: file,
                            response: xhr.responseText,
                            status: xhr.status,
                        });
                    } else {
                        this._patchFile(id, { status: 'error', error: 'HTTP ' + xhr.status });
                        this.dispatch('upload-error', {
                            file: file,
                            error: 'HTTP ' + xhr.status,
                            status: xhr.status,
                        });
                    }
                });
                xhr.addEventListener('error', () => {
                    this._patchFile(id, { status: 'error', error: 'Network error' });
                    this.dispatch('upload-error', {
                        file: file,
                        error: 'Network error',
                        status: 0,
                    });
                });
                const form = new FormData();
                form.append('file', file, entry0.name);
                xhr.open('POST', uploadUrl);
                // Le middleware CSRF de Bretzel est TOUJOURS actif et
                // protège tout POST hors ``/_bretzel/action/*``. Sans ce
                // header, l'upload async se prend un 403 — donc
                // ``upload_url=`` ne pouvait fonctionner dans AUCUNE app,
                // le framework rejetant son propre composant. Même source
                // et même en-tête que le bridge (05_bridge.js).
                if ($bz._csrf) {
                    xhr.setRequestHeader('X-Bretzel-CSRF', $bz._csrf);
                }
                xhr.send(form);
            },

            // ── Dispatch helper — kebab DOM events on the root ─────
            dispatch(name, detail) {
                if (!this._el) return;
                this._el.dispatchEvent(new CustomEvent(name, {
                    detail: detail,
                    bubbles: true,
                }));
            },
        };
    }

    window.$bz.fileUpload = { makeScope: makeScope, formatSize: formatSize };
})();


/* 09_notification.js — toast stack manager (bz-data scope factory). */
// ════════════════════════════════════════════════════════════════════════
// 09 NOTIFICATION — toast stack data manager.
//
// The user calls ``ui.notification("Saved!")`` from a handler ; the
// server rides the payload back in a ``<bz-patch>{"patches":
// {"_notifications":[…]}}`` block, the bridge forwards each to
// ``$bz.notify`` (→ a ``bz:notify`` DOM event), and the toaster
// container (pre-rendered in the shell) catches it and pushes the
// toast into its own ``bz-data`` scope.
//
// V3 vs V2 : no ``Alpine.store`` — the toaster owns its state in a
// bz-data scope (``stacks``, one bucket per position). The factory
// here builds that scope. Reassignment (not in-place push/splice) so
// the ``bz-for`` over each bucket re-renders (V3 signals are
// identity-compared). Enter animation is a CSS keyframe fired on mount ;
// leave is a two-phase dismiss (flip ``_leaving`` → wait ``LEAVE_MS`` →
// splice) so the ``bz-toast-leave`` keyframe can play before removal.
//
// Variant / icon / position normalisation reads the theme blob the
// shell injects on ``window.$bz_theme.notification``.
// ════════════════════════════════════════════════════════════════════════

(function () {
  "use strict";
  const $bz = window.$bz;
  if (!$bz) return;

  // Mirrors the ``bz-toast-out`` duration in the shell keyframes
  // (``_NOTIFICATION_ANIM_STYLE``). Keep them in sync.
  const LEAVE_MS = 200;

  // Shared with the bz-for FLIP reflow — see 06_helpers.js.
  const prefersReducedMotion = $bz.helpers.prefersReducedMotion;

  function genId() {
    return "bz-toast-" + Date.now() + "-" + Math.random().toString(36).slice(2, 8);
  }

  function makeScope() {
    const THEME = (window.$bz_theme && window.$bz_theme.notification) || {};
    const positions = Object.keys(THEME.positions || { "top-right": 1 });
    const variants = Object.keys(THEME.variants || { info: 1 });
    const icons = THEME.icons || {};

    function emptyStacks() {
      const out = {};
      for (const p of positions) out[p] = [];
      return out;
    }

    function normalise(opts) {
      opts = opts || {};
      const variant = variants.indexOf(opts.variant) >= 0 ? opts.variant : "info";
      let icon;
      if (opts.icon === "" || opts.icon === false) icon = null;
      else if (typeof opts.icon === "string" && opts.icon) icon = opts.icon;
      else icon = icons[variant] || null;
      return {
        id: opts.id || genId(),
        message: String(opts.message || ""),
        title: opts.title || null,
        variant: variant,
        position: positions.indexOf(opts.position) >= 0 ? opts.position : "top-right",
        duration_ms: typeof opts.duration_ms === "number" ? opts.duration_ms : 4000,
        dismissible: opts.dismissible !== false,
        icon: icon,
      };
    }

    return {
      stacks: emptyStacks(),

      show(opts) {
        const toast = normalise(opts);
        const pos = toast.position;
        const next = Object.assign({}, this.stacks);
        next[pos] = next[pos].concat([toast]);
        this.stacks = next;
        if (toast.duration_ms > 0) {
          const self = this;
          setTimeout(function () {
            self.dismiss(toast.id);
          }, toast.duration_ms);
        }
        return toast.id;
      },

      dismiss(id) {
        // No animation wanted : drop it now, skip the leave dance.
        if (prefersReducedMotion()) {
          this._remove(id);
          return;
        }
        // Phase 1 — mark the toast leaving so the ``bz-toast-leave``
        // keyframe plays (``bz-class`` reacts to ``_leaving``). Reassign a
        // fresh object under the same ``id`` so the keyed ``bz-for`` updates
        // the existing node in place instead of remounting it. Guard against
        // a double dismiss (manual click + auto-timeout) so we never restart
        // the animation or schedule a second removal.
        let found = false;
        const next = {};
        for (const p of Object.keys(this.stacks)) {
          next[p] = this.stacks[p].map(function (t) {
            if (t.id === id && !t._leaving) {
              found = true;
              return Object.assign({}, t, { _leaving: true });
            }
            return t;
          });
        }
        if (!found) return;
        this.stacks = next;
        // Phase 2 — actually splice once the leave animation has played.
        const self = this;
        setTimeout(function () {
          self._remove(id);
        }, LEAVE_MS);
      },

      _remove(id) {
        const next = {};
        let changed = false;
        for (const p of Object.keys(this.stacks)) {
          const before = this.stacks[p];
          next[p] = before.filter(function (t) {
            return t.id !== id;
          });
          if (next[p].length !== before.length) changed = true;
        }
        if (changed) this.stacks = next;
      },
    };
  }

  $bz.notification = { makeScope: makeScope };
})();


/* 10_charts.js — shared chart tooltip + legend scope factories. */
// ════════════════════════════════════════════════════════════════════════
// 10 CHARTS — shared tooltip for bar / line / pie / sparkline.
//
// Why a runtime slab at all
// ─────────────────────────
// The charts are server-rendered SVG ; the framework already paints the
// silhouette on first paint with zero JS. What we DON'T render server-
// side is the floating tooltip — its position depends on the cursor
// (mouse) or the trigger rect (keyboard focus), neither of which Python
// can know. So this slab :
//
// 1. Lazily mounts a single ``<div class="bz-chart-tooltip">`` on
//    ``<body>`` the first time a chart needs it (zero cost on a page
//    with no charts at all).
// 2. Exposes ``$bz.charts.tooltipScope()`` — a bz-data scope factory
//    every chart wrapper drops on its root. Bars / segments / points
//    handle ``bz-on:mouseenter="show($event)"`` / ``bz-on:mouseleave="hide()"``.
//    The factory reads ``data-bz-display`` off ``event.currentTarget``,
//    formats it server-side (so there's nothing for the JS to know about
//    locale / units), and positions the panel above the trigger.
//
// V3 : ``toggleSeries`` REASSIGNS the ``visible`` array (V3 signals are
// identity-compared — an in-place ``visible[i] = …`` wouldn't re-render
// the ``bz-show``'d paths/dots/legend slots).
//
// Public DOM API
// ──────────────
//   $bz.charts.tooltipScope() → bz-data scope object (bar / pie / sparkline)
//   $bz.charts.lineScope()    → bz-data scope tracking ``active`` for the
//                               line-chart hover state + per-series
//                               ``visible`` toggles.
//   $bz.charts.scatterScope() → bz-data scope (per-dot tooltip + legend)
//   $bz.charts.hide()         → force-hide (e.g. on htmx swap)
// ════════════════════════════════════════════════════════════════════════

(function () {
    'use strict';

    var $bz = window.$bz;
    if (!$bz) return;

    var tip = null;
    var hideTimer = null;
    // Closure that recomputes the visible tooltip's viewport rect from
    // live geometry (returns null when it can't). Each show path installs
    // one capturing whatever it needs — a bar's ``.bz-bar-fill``, a
    // scatter dot, a pie centroid, a line column + fraction. Scroll /
    // resize replay it so a ``fixed`` panel positioned once stays glued
    // to its data point instead of drifting as the page scrolls.
    var activeReposition = null;

    // Tailwind classes carry the Bretzel theme tokens (``bg-text`` /
    // ``text-background`` resolve to the semantic palette set by the
    // user's ``Theme(...)``). The framework already ships these
    // classes (line_chart's tooltip slot uses the same recipe) so
    // they're guaranteed to be in the compiled CSS.
    var TOOLTIP_CLASSES = (
        'bz-chart-tooltip fixed z-50 pointer-events-none ' +
        'px-2.5 py-1.5 rounded-box bg-text/95 text-background ' +
        'text-xs font-medium leading-relaxed whitespace-pre-line ' +
        'shadow-md opacity-0 transition-opacity duration-150'
    );

    function ensureTooltip() {
        if (tip) return tip;
        tip = document.createElement('div');
        tip.className = TOOLTIP_CLASSES;
        tip.setAttribute('role', 'tooltip');
        document.body.appendChild(tip);
        return tip;
    }

    // Set the panel's left/top for a viewport-space ``rect`` — top-
    // anchored, flips below when the trigger hugs the top edge. Reads
    // the panel's own size first (textContent is already set).
    function placeAt(rect) {
        var t = ensureTooltip();
        var tw = t.offsetWidth;
        var th = t.offsetHeight;
        var cx = rect.left + rect.width / 2;
        var aboveY = rect.top - th - 8;
        var flipped = aboveY < 4;
        var y = flipped ? (rect.bottom + 8) : aboveY;
        var x = Math.max(4, Math.min(window.innerWidth - tw - 4, cx - tw / 2));
        t.style.left = x + 'px';
        t.style.top = y + 'px';
    }

    function position(rect) {
        var t = ensureTooltip();
        t.style.left = '0px';
        t.style.top = '0px';
        placeAt(rect);
        t.style.opacity = '1';
    }

    // Viewport rect for an anchor element — a pie wedge's ``data-bz-ax/ay``
    // centroid (SVG-space → screen via the CTM) when present, else the
    // ``rect`` / ``circle`` bounding box. ``null`` when the element can't
    // be resolved (e.g. a path with no centroid attrs) so callers fall
    // back to the cursor.
    function rectForAnchor(anchor) {
        if (!anchor) return null;
        var ax = anchor.getAttribute('data-bz-ax');
        var ay = anchor.getAttribute('data-bz-ay');
        var svg = anchor.ownerSVGElement;
        var ctm = svg && svg.getScreenCTM && svg.getScreenCTM();
        if (ax !== null && ay !== null && ctm) {
            var pt = svg.createSVGPoint();
            pt.x = parseFloat(ax);
            pt.y = parseFloat(ay);
            var screen = pt.matrixTransform(ctm);
            return {
                left: screen.x, right: screen.x,
                top: screen.y, bottom: screen.y,
                width: 0, height: 0,
            };
        }
        var tag = anchor.tagName && anchor.tagName.toLowerCase();
        if (tag === 'rect' || tag === 'circle') {
            return anchor.getBoundingClientRect();
        }
        return null;
    }

    // Keep the visible panel glued to its anchor across scroll / resize —
    // recompute geometry and move (no opacity toggle, so no re-fade).
    function reposition() {
        if (!tip || tip.style.opacity !== '1' || !activeReposition) return;
        var rect = activeReposition();
        if (rect) placeAt(rect);
    }
    // Capture phase so scrolls inside any nested scroll container (not
    // just the window) reach us — scroll events don't bubble.
    window.addEventListener('scroll', reposition, true);
    window.addEventListener('resize', reposition);

    function hideTooltip() {
        activeReposition = null;
        if (!tip) return;
        // Tiny grace period so a fast cursor leaving one bar and entering
        // the next doesn't flash the tooltip in/out — the next ``show``
        // cancels the pending hide.
        clearTimeout(hideTimer);
        hideTimer = setTimeout(function () {
            if (tip) tip.style.opacity = '0';
        }, 60);
    }

    // The ``show`` handshake every hover path repeats : resolve the
    // hovered element, read its pre-formatted label, cancel a pending
    // hide, make sure the tooltip node exists, and write the text ONLY
    // when it changed (writing the same string would invalidate layout
    // before ``offsetWidth`` is read, for nothing).
    //
    // Returns the hovered element when a label is on screen, or null
    // when there was nothing to show — each caller then does its own
    // anchoring, which is where they genuinely differ (bar-fill lookup,
    // dot rect, line-column band). Three copies before (audit F59).
    function showLabel(event) {
        var el = event && event.currentTarget;
        if (!el) return null;
        var label = el.getAttribute('data-bz-display');
        if (!label) return null;
        clearTimeout(hideTimer);
        var t = ensureTooltip();
        if (t.textContent !== label) t.textContent = label;
        return el;
    }

    function tooltipScope() {
        return {
            show: function (event) {
                var el = showLabel(event);
                if (!el) return;
                // Bar charts widen the hit target to the whole column via
                // a transparent ``.bz-bar-hit`` overlay that spans the
                // plot. Anchoring on the overlay itself would float the
                // tooltip at the top of the column ; anchor on the sibling
                // ``.bz-bar-fill`` instead so it lands on the data point.
                var anchor = el;
                if (el.classList && el.classList.contains('bz-bar-hit')) {
                    var fill = el.parentNode &&
                        el.parentNode.querySelector('.bz-bar-fill');
                    if (fill) anchor = fill;
                }
                // Anchor on the data point : a bar's ``.bz-bar-fill``, a
                // scatter/line dot, or a pie wedge's ``data-bz-ax/ay``
                // centroid (a ``<path>`` bbox would float the panel at the
                // pie's centre). ``rectForAnchor`` resolves all three ;
                // stash the element so scroll / resize can re-anchor.
                var rect = rectForAnchor(anchor);
                if (rect) {
                    activeReposition = function () {
                        return rectForAnchor(anchor);
                    };
                    position(rect);
                } else {
                    // Last-resort fallback (path with no centroid attrs) —
                    // pin to the cursor ; nothing to re-anchor on scroll.
                    activeReposition = null;
                    position({
                        left: event.clientX, right: event.clientX,
                        top: event.clientY, bottom: event.clientY,
                        width: 0, height: 0,
                    });
                }
            },
            hide: function () { hideTooltip(); },
        };
    }

    // Force-hide on htmx swap so a refresh that replaces the chart
    // doesn't leave the tooltip pointing at thin air.
    document.addEventListener('htmx:before-swap', function () {
        activeReposition = null;
        if (tip) tip.style.opacity = '0';
    });

    function parseJSON(attr, fallback) {
        if (!attr) return fallback;
        try { return JSON.parse(attr); } catch (e) { return fallback; }
    }

    // Legend visibility, shared by every multi-series chart scope.
    // ``visible[i]`` drives ``bz-show`` on the path / dots / markers the
    // server rendered with series index ``i``.
    //
    // Two load-bearing details lived in two copies (audit F18) : the
    // "never toggle the last one off" guard (an all-hidden chart reads
    // as broken — Vercel and Stripe ship the same rule), and the
    // REASSIGN in toggleSeries (V3 signals are identity-compared, so an
    // in-place ``visible[i] = …`` would not re-render).
    function seriesVisibility(nSeries) {
        var visible = [];
        for (var i = 0; i < nSeries; i++) visible.push(true);
        return {
            visible: visible,
            isVisible: function (i) { return !!this.visible[i]; },
            toggleSeries: function (i) {
                if (i < 0 || i >= this.visible.length) return;
                var on = this.visible.filter(Boolean).length;
                if (this.visible[i] && on <= 1) return;
                this.visible = this.visible.map(function (v, j) {
                    return j === i ? !v : v;
                });
            },
        };
    }

    function lineScope(opts) {
        var nSeries = (opts && opts.n_series) || 1;
        var vis = seriesVisibility(nSeries);
        return {
            active: -1,
            visible: vis.visible,
            isVisible: vis.isVisible,
            // Full-column hover (single + multi). Sets the ``active``
            // index (drives the crosshair + per-series active dots via
            // bz-attr) AND positions the shared floating tooltip above
            // the active column. The hit rect (``event.currentTarget``)
            // spans the plot vertically, so its screen bbox gives us
            // both the column's screen-x band and the plot top —
            // scale-robust, no SVG CTM. ``data-bz-anchor-x`` is the
            // data-x's fraction within the rect, mapped onto that band.
            onHover: function (event, idx) {
                this.active = idx;
                var el = showLabel(event);
                // Nothing to show (no target, or a column with no
                // label) → hide. The pre-shared version returned early
                // without hiding in the no-target case ; a dispatched
                // mouseenter always has a currentTarget, and hideTooltip
                // no-ops when no tooltip node exists yet.
                if (!el) { hideTooltip(); return; }
                // Zero-size anchor at (column-x, plot-top) → the tooltip
                // floats above the plot, never over the curve. ``bottom
                // = r.top`` so the near-top flip lands just inside the
                // plot instead of at the far plot bottom. Recomputed from
                // the live hit rect so scroll / resize keep it glued.
                var lineRect = function () {
                    var r = el.getBoundingClientRect();
                    var frac = parseFloat(el.getAttribute('data-bz-anchor-x'));
                    if (isNaN(frac)) frac = 0.5;
                    var ax = r.left + frac * r.width;
                    return {
                        left: ax, right: ax, top: r.top, bottom: r.top,
                        width: 0, height: 0,
                    };
                };
                activeReposition = lineRect;
                position(lineRect());
            },
            onLeave: function () { this.active = -1; hideTooltip(); },
            // The shared toggle, plus line's own extra : drop the hover
            // index when the series it points at goes hidden. Wrapped
            // rather than re-copied, so the guard and the reassign stay
            // in one place.
            toggleSeries: function (i) {
                vis.toggleSeries.call(this, i);
                if (!this.visible[i]) this.active = -1;
            },
        };
    }

    function scatterScope(opts) {
        var vis = seriesVisibility((opts && opts.n_series) || 1);
        return {
            visible: vis.visible,
            isVisible: vis.isVisible,
            toggleSeries: vis.toggleSeries,
            // Floating tooltip on per-dot hover. Each ``<circle>``
            // dot carries ``data-bz-display`` ; the circle's
            // ``getBoundingClientRect()`` is tight (``r × 2`` box)
            // so anchoring above it lands cleanly on the dot.
            show: function (event) {
                var el = showLabel(event);
                if (!el) return;
                activeReposition = function () {
                    return el.getBoundingClientRect();
                };
                position(el.getBoundingClientRect());
            },
            hide: function () { hideTooltip(); },
        };
    }

    $bz.charts = {
        tooltipScope: tooltipScope,
        lineScope: lineScope,
        scatterScope: scatterScope,
        hide: hideTooltip,
    };
})();


/* 11_number_input.js — shared scope for the NumberInput component.
 *
 * The full client logic (precision, clamp, snap-to-step, draft-vs-value,
 * nudge, change emission) lived INLINE in every instance's bz-data
 * attribute (~1.5 KB of method bodies repeated per <ui.number_input>).
 * It now lives here ONCE ; each instance emits only its state +
 * ``_read``/``_write`` so the same methods serve both modes :
 *
 *   bz-data="{...$bz.numberInput.scope, value: 42,
 *             _read(){return this.value}, _write(v){this.value=v},
 *             _min: null, _max: null, _step: 1, _draft: "42",
 *             _focused: false, _carrier: null, _precCache: undefined}"
 *
 * Value access goes through ``this._read()`` / ``this._write(v)`` so the
 * SAME methods cover local mode (a ``value`` signal field) and binding
 * mode (a ``$bz.state.<path>`` store cell) — the per-instance scope
 * supplies the right pair. (We can't bake a live ``get value()`` into
 * the literal : ``scope.absorb`` reads every key once, freezing getters —
 * cf. traps.md.)
 */
(function () {
  "use strict";
  const $bz = (window.$bz = window.$bz || {});

  $bz.numberInput = {
    scope: {
      // Decimal precision implied by the step (step=0.01 → 2), memoised
      // on ``_precCache``. Guards float drift in the displayed value.
      _precision: $bz.num.cachedPrecision,
      _round(v) {
        const p = this._precision();
        return p > 0 ? Number(v.toFixed(p)) : v;
      },
      _clamp(v) {
        let out = v;
        if (this._min !== null) out = Math.max(this._min, out);
        if (this._max !== null) out = Math.min(this._max, out);
        return this._round(out);
      },
      _snap(v) {
        const base = this._min !== null ? this._min : 0;
        return this._round(Math.round((v - base) / this._step) * this._step + base);
      },
      _atMin() {
        const v = this._read();
        return this._min !== null && v != null && Number(v) <= this._min;
      },
      _atMax() {
        const v = this._read();
        return this._max !== null && v != null && Number(v) >= this._max;
      },
      _displayValue() {
        const v = this._read();
        if (v == null || v === "") return "";
        return String(this._round(Number(v)));
      },
      _commitDraft(final) {
        const raw = String(this._draft || "").trim();
        if (raw === "" || raw === "-" || raw === ".") {
          if (final) { this._write(null); this._emitChange(); }
          return;
        }
        const n = Number(raw);
        if (isNaN(n)) {
          if (final) this._draft = this._displayValue();
          return;
        }
        if (final) {
          const clamped = this._snap(this._clamp(n));
          this._write(clamped);
          this._draft = String(clamped);
          this._emitChange();
        } else {
          this._write(this._round(n));
        }
      },
      _nudge(delta) {
        const cur = this._read() == null ? 0 : Number(this._read());
        const next = this._snap(this._clamp(cur + delta));
        this._write(next);
        if (this._focused) this._draft = String(next);
        this._emitChange();
      },
      _setValue(raw) {
        const n = Number(raw);
        if (raw == null || raw === "" || isNaN(n)) {
          this._write(null);
          this._draft = "";
          this._emitChange();
          return;
        }
        const next = this._snap(this._clamp(n));
        this._write(next);
        this._draft = String(next);
        this._emitChange();
      },
      // Dispatch a synthetic ``bzchange`` from the captured <input> so a
      // relocated ``on_change`` (bz-on:bzchange / hx-trigger="bzchange")
      // observes the COMMITTED value. We deliberately do NOT reuse the
      // native ``change`` event : the browser fires its own ``change`` on
      // blur, BEFORE we reformat the draft, carrying the raw typed text —
      // routing observers onto our private event sidesteps that dirty
      // dispatch (and the resulting double-fire). Deferred a microtask so
      // the signal flush (which also rides queueMicrotask, FIFO-ordered
      // before this one) lands the canonical value on the DOM input first.
      // ``bzchange``, not the native ``change`` : the inner input fires
      // ``change`` on its own while the user types, so a user
      // ``on_change=`` must not see it.
      _emitChange() { $bz.helpers.emitChange(this._carrier, "bzchange"); },
    },
  };
})();


/* 12_slider.js — shared scope for the Slider component.
 *
 * The drag / keyboard / pointer / clamp / snap logic (~15 methods)
 * lived INLINE in every instance's bz-data. It now lives here ONCE ;
 * each instance emits only its state + ``_read``/``_write`` (value
 * access) and a ``_range`` flag (single scalar vs ``[start, end]``).
 *
 *   bz-data="{...$bz.slider.scope, value: 50,
 *             _read(){return this.value}, _write(v){this.value=v},
 *             _range: false, _min: 0, _max: 100, _step: 1,
 *             _dragging: null, _hovered: null, _focused: null,
 *             _track: null, _carrier: null, _precCache: undefined}"
 *
 * Value access goes through ``this._read()`` / ``this._write(v)`` so the
 * same methods serve local mode (a ``value`` field) and binding mode
 * (a ``$bz.state.<path>`` cell). The mode-specific bits (``_picked`` /
 * ``_setHandle`` / ``_setValue`` / ``_jumpToPointer``) branch on
 * ``this._range`` instead of being baked per instance.
 */
(function () {
  "use strict";
  const $bz = (window.$bz = window.$bz || {});

  $bz.slider = {
    scope: {
      // Static disabled (aria-disabled + tabindex) is applied at render
      // time ; the scalar guard stays a constant here.
      _disabledState() { return false; },
      _pct(v) {
        const range = this._max - this._min;
        if (range === 0) return 0;
        return ((v - this._min) / range) * 100;
      },
      _precision: $bz.num.cachedPrecision,
      _clamp(v) {
        const stepped = Math.round((v - this._min) / this._step) * this._step + this._min;
        const clamped = Math.max(this._min, Math.min(this._max, stepped));
        const p = this._precision();
        return p > 0 ? Number(clamped.toFixed(p)) : clamped;
      },
      _emitChange() { $bz.helpers.emitChange(this._carrier); },
      _pointerToValue(e) {
        const t = this._track;
        if (!t) return this._min;
        const rect = t.getBoundingClientRect();
        if (!rect.width) return this._min;
        const pct = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width));
        return this._clamp(this._min + pct * (this._max - this._min));
      },
      _startDrag(target, e) {
        if (this._disabledState()) return;
        this._dragging = target;
        $bz.helpers.capturePointer(this._track, e);
        this._setHandle(target, this._pointerToValue(e));
      },
      _drag(e) {
        if (this._dragging) this._setHandle(this._dragging, this._pointerToValue(e));
      },
      _endDrag(e) {
        $bz.helpers.releasePointer(this._track, e);
        this._dragging = null;
        this._emitChange();
      },
      _nudge(target, delta) {
        if (this._disabledState()) return;
        const cur = target === "value"
          ? this._picked()
          : this._picked()[target === "start" ? 0 : 1];
        this._setHandle(target, cur + delta);
        this._emitChange();
      },
      // ── Mode-aware (branch on this._range) ───────────────────────
      _picked() {
        const v = this._read();
        if (this._range) {
          return Array.isArray(v) && v.length >= 2
            ? [Number(v[0]), Number(v[1])]
            : [this._min, this._max];
        }
        if (v == null || isNaN(Number(v))) return this._min;
        return Number(v);
      },
      _setHandle(target, raw) {
        if (this._range) {
          const cur = this._picked();
          const v = this._clamp(raw);
          let next;
          if (target === "start") next = [Math.min(v, cur[1]), cur[1]];
          else next = [cur[0], Math.max(v, cur[0])];
          this._write(next);
        } else {
          this._write(this._clamp(raw));
        }
      },
      _setValue(raw) {
        if (this._range) {
          if (Array.isArray(raw) && raw.length >= 2) {
            this._write(
              [this._clamp(Number(raw[0])), this._clamp(Number(raw[1]))]
                .sort(function (a, b) { return a - b; }),
            );
            this._emitChange();
          }
        } else {
          const n = Number(raw);
          if (!isNaN(n)) { this._write(this._clamp(n)); this._emitChange(); }
        }
      },
      _jumpToPointer(e) {
        if (this._disabledState()) return;
        if (this._range) {
          const v = this._pointerToValue(e);
          const cur = this._picked();
          const target = Math.abs(v - cur[0]) < Math.abs(v - cur[1]) ? "start" : "end";
          this._startDrag(target, e);
        } else {
          this._startDrag("value", e);
        }
      },
    },
  };
})();


/* 13_select.js — shared scopes for the Select component.
 *
 * The pick / highlight / multi-membership / bulk-action methods lived
 * INLINE in every instance's bz-data. They live here ONCE, split into
 * two scopes (single vs multi — the modes diverge too much for one
 * branching set). Each instance emits only its data + ``_read``/
 * ``_write`` :
 *
 *   bz-data="{...$bz.select.single, value: 'a',
 *             _read(){return this.value}, _write(v){this.value=v},
 *             open: false, _highlight: -1, _options: [...]}"
 *
 * ``_options`` (option values) and ``_labels`` (value→label map) stay
 * per instance — they differ per Select. Value access goes through
 * ``this._read()`` / ``this._write(v)`` (local: a ``value`` field ;
 * binding: a ``$bz.state.<path>`` cell). No live ``get value()`` —
 * ``scope.absorb`` freezes getters (cf. traps.md) ; the label / hidden
 * input read ``value_expr`` directly.
 */
(function () {
  "use strict";
  const $bz = (window.$bz = window.$bz || {});

  // No scope-level change dispatcher : ``change`` is fired by the
  // per-instance ``_change_emit_effect`` posted ON the hidden input
  // (select.py). That effect dispatches from the hidden input itself, so
  // the relocated htmx listener always sees it ; a scope method's carrier
  // resolved unreliably (root vs hidden, depending on bind order) — for
  // Select it landed on the root and never reached the input at all. The
  // value-setting methods below just ``_write`` ; the effect observes the
  // mutation and dispatches (mirror of Combobox).

  $bz.select = {
    single: {
      // Le libellé d'une valeur. Select GARDE sa carte ``_labels``
      // (son ``_options`` ne porte que des valeurs, donc elle n'y
      // est pas redondante) ; ce qui a disparu le 2026-08-28, c'est
      // la carte RÉ-INLINÉE dans le ``bz-text`` de chaque gabarit de
      // pastille — un troisième exemplaire de la même table. Le
      // gabarit partagé (``_picker.build_pills_template``) appelle
      // désormais cette méthode, que Combobox définit à sa façon.
      _labelOf(v) { return this._labels[String(v)] || ""; },
      _pick(v) { this._write(v); this.open = false; },
      _isPicked(v) { return String(this._read() || "") === String(v); },
      _highlightFromValue() {
        this._highlight = Math.max(0, this._options.indexOf(String(this._read())));
      },
    },
    multi: {
      ...$bz.multiSelect,
      // Le libellé d'une valeur. Select GARDE sa carte ``_labels``
      // (son ``_options`` ne porte que des valeurs, donc elle n'y
      // est pas redondante) ; ce qui a disparu le 2026-08-28, c'est
      // la carte RÉ-INLINÉE dans le ``bz-text`` de chaque gabarit de
      // pastille — un troisième exemplaire de la même table. Le
      // gabarit partagé (``_picker.build_pills_template``) appelle
      // désormais cette méthode, que Combobox définit à sa façon.
      _labelOf(v) { return this._labels[String(v)] || ""; },
      _value() { const v = this._read(); return v == null ? [] : v; },
      // Select-specific : every option is always visible (no query).
      // ``_clearAll`` n'est PAS redéclaré — celui du mixin fait
      // exactement ça, et le redire ici est comment les deux pickers
      // divergeaient (audit F19).
      _selectAll() { this._write(this._options.slice()); },
      _highlightFromValue() {
        const picks = this._picked();
        if (picks.length) this._highlight = Math.max(0, this._options.indexOf(picks[0]));
        else this._highlight = 0;
      },
    },
  };
})();


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
 * ⚠️ Il y avait aussi un ``_labels: {valeur: libellé}``, retiré le
 * 2026-08-28 : chaque entrée d'``_options`` porte DÉJÀ son ``label``,
 * donc la carte redisait la moitié de la liste — 501 octets sur 22 586
 * pour vingt options. Son unique lecteur (le libellé affiché dans le
 * champ fermé, en mode simple) passe par ``_labelOf`` ci-dessous.
 * ``Select``, lui, le GARDE : son ``_options`` ne porte que des
 * valeurs, donc la carte n'y est pas redondante.
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
    /* ── Les options, peintes par le PANNEAU ────────────────────────
     *
     * Avant le 2026-09-02, chaque option portait cinq directives :
     * ``bz-class``, ``bz-attr:aria-selected``, ``bz-show`` et deux
     * ``bz-on:``. Mesuré : 461 octets par option, dont 177 rien que
     * pour ces directives, répétées à l'identique N fois.
     *
     * Trois d'entre elles deviennent UN effet et DEUX écouteurs
     * délégués, sur le panneau. ``bz-show`` reste par option : c'est le
     * filtre de recherche, et le runtime a sa propre machinerie de
     * masquage.
     *
     * ⚠️ Pourquoi les options restent rendues par le SERVEUR — et
     * pourquoi ce n'est pas la moitié d'un travail. La règle du dépôt
     * (« qui écrit le ``for`` ? », gatée par
     * ``test_collection_owner_decides_the_api``) lie l'endroit du rendu
     * à la forme de l'API : un composant qui rend sa collection côté
     * SERVEUR a droit à un rappel ``render=``, un composant dont le
     * client crée les nœuds n'y a PAS droit — un callback Python ne
     * tourne pas dans le navigateur. Peindre les options ici ferait
     * donc perdre au combobox son ``render=``, ajouté le 2026-08-18
     * précisément parce que la thèse d'agencement l'avait compté parmi
     * les quatre collections SANS aucune sortie pour l'auteur. Le gain
     * en octets ne vaut pas une échappatoire de contenu dans un
     * framework qui en a neuf pour 498 slots de style.
     */
    optionOf(ev) {
      const o = ev.target.closest('[role="option"]');
      // Un bouton désactivé ne dispatche pas de clic, mais IL REÇOIT
      // les survols — sans ce garde, passer la souris sur une option
      // grisée la surlignerait comme si elle était choisissable.
      return o && !o.disabled ? o : null;
    },

    /* Repeindre l'état de toutes les options : le surlignage (clavier
     * et souris) et la sélection.
     *
     * Les deux chaînes de classe voyagent UNE fois, sur le panneau, au
     * lieu d'être recopiées dans le ``bz-class`` de chaque option.
     *
     * ⚠️ On manipule ``classList`` directement plutôt que de garder un
     * suivi sur le nœud. C'est délibéré et c'est la leçon de
     * ``bz-class`` (traps.md) : un état gardé sur l'élément ne survit
     * pas à un morph, donc la classe active n'était jamais ré-ajoutée
     * au rescan. Ici l'effet REPEINT tout à chaque passage depuis la
     * vérité (``_highlight`` et ``isPicked``), donc un morph qui
     * remettrait la classe SSR est rattrapé au passage suivant.
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
      // Le libellé d'une valeur, lu dans ``_options`` — qui le porte
      // déjà. Remplace la carte ``_labels`` que chaque instance émettait
      // en plus (cf. l'en-tête). Un seul lecteur : le champ FERMÉ en
      // mode simple, donc un balayage linéaire sur une liste d'options
      // ne coûte rien de mesurable, et il s'aligne sur ``_options``
      // quand un refresh serveur la re-sème — ce qu'une carte figée dans
      // un autre champ pouvait rater.
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
      // Le mixin vide la sélection sans fermer ; Combobox AJOUTE le
      // reset de la requête (Select n'a pas de champ de recherche).
      _clearAll() { $bz.multiSelect._clearAll.call(this); this.query = ""; },
    },
  };
})();


/* 15_pagination.js — scope partagé du composant Pagination.
 *
 * Tout l'algorithme ``range()`` — le calcul des numéros de page visibles
 * avec ses ellipses — vivait INLINE dans le ``bz-data`` de chaque
 * instance : 957 octets par ``<ui.pagination>``, le plus gros du dépôt.
 * Pire, sa configuration était cuite DANS les corps de méthode :
 *
 *     totalPages() { return Math.max(1, +(10) || 1); }
 *     maxVisible() { return +(7) || 7; }
 *     isDisabled() { return !!(false); }
 *
 * — trois constantes littérales là où il fallait trois données. C'est ce
 * qui rendait la factorisation impossible : deux instances avec des
 * ``total_pages`` différents produisaient deux CODES différents, pas deux
 * états différents.
 *
 * La bascule est donc « config en données », le prérequis que NumberInput
 * avait déjà appliqué (cf. 11_number_input.js) :
 *
 *   bz-data="{...$bz.pagination.scope, value: 1, _total: 10,
 *             _maxVisible: 7, _disabled: false,
 *             _read(){return this.value}, _write(v){this.value = v}}"
 *
 * ``_read`` / ``_write`` couvrent les DEUX modes avec les mêmes méthodes —
 * champ local (``value``) ou cellule du store (``$bz.state.<path>``). On
 * ne peut pas y mettre un ``get value()`` : ``scope.absorb`` lit chaque
 * clé une fois à l'enregistrement et figerait le getter (cf. traps.md).
 *
 * ``range()`` est le portage JS de ``compute_range`` (Python). Les deux
 * doivent concorder — c'est ce que vérifie ``test_python_js_mirror``.
 */
(function () {
  "use strict";
  const $bz = (window.$bz = window.$bz || {});

  $bz.pagination = {
    scope: {
      // ── Lectures normalisées ─────────────────────────────────────
      // Des MÉTHODES, pas des getters : le scope les invoque à
      // l'enregistrement, ce qui figerait un getter sur sa première
      // valeur.
      current() {
        return +this._read() || 1;
      },
      totalPages() {
        return Math.max(1, +this._total || 1);
      },
      maxVisible() {
        return +this._maxVisible || 7;
      },
      // Constante par défaut, surchargée depuis le builder quand le verrou
      // est réel (littéral ou binding) — même mécanique que
      // ``_disabledState`` du Slider (12_slider.js:28).
      //
      // ⚠️ Ce N'EST PAS une donnée. Un champ ``_disabled: <chemin de store>``
      // dans le bz-data serait évalué UNE FOIS, hors effet : ``absorb``
      // emballe le snapshot dans un signal neuf découplé de la cellule, et
      // plus rien ne le réécrit. Le verrou restait donc figé sur sa valeur
      // au montage (mesuré : le switch bascule, la pagination reste
      // cliquable). Une expression liée doit vivre dans un CORPS DE
      // MÉTHODE, seul endroit relu à chaque appel donc tracé par l'effet
      // appelant. Cf. traps.md § « un champ de bz-data n'est pas réactif ».
      isDisabled() {
        return false;
      },

      // Setter — ne mute que sur un vrai changement, donc un clic sur la
      // page courante est un no-op. C'est le ``bz-effect`` de l'input
      // caché qui transforme la mutation en ``change`` bullant.
      //
      // Le verrou et la borne vivent ICI, dans l'unique mutateur, parce
      // que les appelants ne se valent plus : les boutons du rail sont
      // déjà gardés par leur ``bz-attr:disabled`` et ne passent que des
      // valeurs issues de ``range()``, mais l'API impérative
      // (``p.next()`` sur un bouton ailleurs dans la page) n'a aucun de
      // ces deux garde-fous. Un seul mutateur gardé plutôt que deux
      // chemins à garder séparément (principe 4 de la charte).
      setActive(v) {
        if (this.isDisabled()) return;
        const n = Math.max(1, Math.min(this.totalPages(), +v || 1));
        if (this.current() === n) return;
        this._write(n);
      },

      // Les deux directions se DÉRIVENT du mutateur : la borne y est
      // déjà, donc ``next()`` sur la dernière page se clampe à
      // ``totalPages()``, retombe sur ``current()`` et sort — le no-op
      // au bord est gratuit, pas une branche de plus.
      next() {
        this.setActive(this.current() + 1);
      },
      prev() {
        this.setActive(this.current() - 1);
      },

      // ── Le calcul des pages visibles ─────────────────────────────
      // Portage direct de ``compute_range``. Se recalcule dès que
      // current() / totalPages() / maxVisible() lisent un signal changé —
      // l'effet du runtime trace les lectures.
      //
      // Dans un corps de méthode, un identifiant nu ne voit PAS le scope :
      // tout passe par ``this.<nom>()``.
      range() {
        const tp = this.totalPages();
        const slots = Math.max(5, this.maxVisible());
        const ap = this.current();
        if (tp <= slots) {
          return Array.from({ length: tp }, (_, i) => i + 1);
        }
        const side = Math.floor(slots / 2);
        const showLeft = ap > side + 1;
        const showRight = ap < tp - side;
        if (!showLeft) {
          const r = [];
          for (let i = 1; i < slots - 1; i++) r.push(i);
          r.push("ellipsis");
          r.push(tp);
          return r;
        }
        if (!showRight) {
          const r = [1, "ellipsis"];
          for (let i = tp - (slots - 3); i <= tp; i++) r.push(i);
          return r;
        }
        const r = [1, "ellipsis"];
        const middle = slots - 4;
        const start = ap - Math.floor(middle / 2);
        for (let i = 0; i < middle; i++) r.push(start + i);
        r.push("ellipsis");
        r.push(tp);
        return r;
      },
    },
  };
})();


/* 16_accordion.js — scopes partagés d'Accordion, Tree, Tabs, Stepper
 * et Tooltip. (Le nom du fichier date du premier arrivant.)
 *
 * Les deux composants sérialisaient tous leurs corps de méthode dans le
 * ``bz-data`` de chaque instance — Accordion 622 octets, Tree 293 — et
 * Accordion cuisait en plus sa configuration DANS le code :
 *
 *     toggle(v) { … if (cur === target) { if (true) { … } } … }
 *                                            ^^^^ collapsible
 *     expandAll() { const ids = ["a","b","c"]; … }
 *
 * Deux accordéons de configurations différentes produisaient donc deux
 * CODES différents, pas deux états différents — c'est ce qui rendait la
 * factorisation impossible. La bascule est « config en données », le même
 * prérequis que NumberInput (11) et Pagination (15).
 *
 *   bz-data="{...$bz.accordion.single, value: "a", _read(){…}, _write(v){…},
 *             _collapsible: true, _allIds: ["a","b"]}"
 *   bz-data="{...$bz.accordion.multi,  value: ["a"],
 *             _allIds: ["a","b"]}"
 *
 * Deux variantes plutôt qu'une seule paramétrée : le mode single porte une
 * CHAÎNE, le mode multi un TABLEAU. Fusionner obligerait chaque méthode à
 * re-tester le type à l'exécution — la même raison qui a donné
 * ``$bz.select.single`` et ``$bz.select.multi``.
 *
 * ⚠️ Des MÉTHODES, jamais des getters : ``scope.absorb`` invoque chaque
 * clé à l'enregistrement et figerait un getter sur sa première valeur
 * (cf. traps.md).
 */
(function () {
  "use strict";
  const $bz = (window.$bz = window.$bz || {});

  $bz.accordion = {
    // ── Un seul panneau ouvert à la fois ────────────────────────────
    single: {
      isOpen(v) {
        return String(this._read() || "") === String(v);
      },
      toggle(v) {
        const cur = String(this._read() || "");
        const target = String(v);
        if (cur === target) {
          // ``_collapsible`` : refermer le panneau courant est-il permis ?
          if (this._collapsible) this._write("");
        } else {
          this._write(target);
        }
      },
      expand(v) {
        const target = String(v);
        if (String(this._read() || "") !== target) this._write(target);
      },
      collapse(v) {
        const target = String(v);
        if (String(this._read() || "") === target && this._collapsible) {
          this._write("");
        }
      },
      // En mode single, « tout ouvrir » ne peut ouvrir que le premier.
      expandAll() {
        const ids = this._allIds || [];
        if (ids.length) this._write(String(ids[0]));
      },
      collapseAll() {
        if (this._collapsible) this._write("");
      },
    },

    // ── Plusieurs panneaux ouverts ──────────────────────────────────
    multi: {
      isOpen(v) {
        return (this._read() || []).indexOf(v) >= 0;
      },
      toggle(v) {
        const cur = this._read() || [];
        const i = cur.indexOf(v);
        this._write(i >= 0 ? cur.filter((_, j) => j !== i) : [...cur, v]);
      },
      expand(v) {
        const cur = this._read() || [];
        if (cur.indexOf(v) < 0) this._write([...cur, v]);
      },
      collapse(v) {
        const cur = this._read() || [];
        const i = cur.indexOf(v);
        if (i >= 0) this._write(cur.filter((_, j) => j !== i));
      },
      expandAll() {
        this._write((this._allIds || []).slice());
      },
      collapseAll() {
        this._write([]);
      },
    },
  };

  // ── Tree ──────────────────────────────────────────────────────────
  // Même famille : ouverture multiple (les nœuds dépliés) + une sélection
  // unique optionnelle. ``sel`` / ``isSel`` / ``select`` ne servent que
  // lorsque ``selectable=True`` ; les laisser dans le scope partagé ne
  // coûte rien (le HTML ne les appelle pas) et évite une seconde variante.
  $bz.tree = {
    scope: {
      isOpen(id) {
        return (this._read() || []).indexOf(id) >= 0;
      },
      toggle(id) {
        const cur = this._read() || [];
        const i = cur.indexOf(id);
        this._write(i >= 0 ? cur.filter((_, j) => j !== i) : [...cur, id]);
      },
      isSel(id) {
        return String(this._readSel() || "") === String(id);
      },
      select(id) {
        this._writeSel(String(id));
      },
      // Défauts pour le cas NON sélectionnable : le composant ne les
      // remplace que quand ``selectable=True``. Sans eux, ``isSel``
      // lèverait si un thème appelait la méthode.
      _readSel() {
        return "";
      },
      _writeSel(_v) {},
    },
  };

  // ── Tabs ──────────────────────────────────────────────────────────
  // Un setter avec garde de changement — même forme que
  // ``$bz.pagination.setActive``. Sérialisé par instance jusqu'au
  // 2026-07-29.
  //
  // ``_url`` — le nom du paramètre d'URL, quand l'appelant a écrit
  // ``ui.tabs(url="onglet")``. Absent par défaut, donc tout ce qui suit
  // est inerte : un onglet n'a d'adresse que si on la demande.
  //
  // C'est le pendant CLIENT de ``URL = {…}`` sur un état serveur. Les
  // deux existent parce que les deux chemins existent : un tri passe par
  // le serveur, qui peut poser un en-tête ; un onglet bascule dans le
  // scope, sans requête — personne côté serveur n'apprend rien, donc
  // c'est au runtime de faire suivre la barre d'adresse.
  $bz.tabs = {
    scope: {
      setTab(v) {
        const s = String(v == null ? "" : v);
        if (String(this._read()) === s) return;
        this._write(s);
        if (this._url) $bz.helpers.pushUrl(this._url, s);
      },

      // Le RETOUR. Sans lui, la flèche du navigateur changerait l'adresse
      // et laisserait l'onglet où il est — pire que pas d'adresse du
      // tout, parce que l'URL affichée mentirait alors sur ce qui est à
      // l'écran.
      //
      // On ne peut pas laisser htmx s'en charger : il ne restaure que
      // les entrées qu'il a lui-même créées (il teste sa propre marque
      // dans ``history.state``), et celle-ci vient d'ici. Et le faire
      // nous-même est de toute façon meilleur — c'est un basculement de
      // signal, instantané, là où htmx referait la page entière pour
      // changer d'onglet.
      //
      // Posé par ``bz-init``, la voie que ``06_helpers.js`` documente
      // pour un événement qui n'existe que sur ``window``.
      _urlInit() {
        if (!this._url) return;
        const param = this._url;
        const self = this;
        // Ce que le SERVEUR a rendu — l'onglet quand l'adresse ne dit
        // rien. Capturé ici, au montage, parce que le signal aura bougé
        // quand le premier ``popstate`` arrivera.
        const initial = String(self._read());
        $bz.helpers.onWindow("popstate", function () {
          const raw = $bz.helpers.urlParam(param);
          // **Absent = le défaut.** Pas « ne rien faire » : revenir sur
          // ``/contacts/5`` après ``?onglet=activites`` doit ROUVRIR
          // l'onglet initial. La première écriture gardait sur
          // ``if (next)`` et laissait donc l'onglet précédent affiché
          // sous une adresse qui disait autre chose — attrapé par
          // ``probe_tabs_url``, invisible à tout test SSR.
          //
          // C'est aussi la règle que le serveur applique déjà des deux
          // côtés (``state/url.py`` : absent → on garde le défaut, à son
          // défaut → n'apparaît pas). Les trois s'accordent, donc un
          // aller-retour est fidèle.
          const next = raw == null || raw === "" ? initial : String(raw);
          if (String(self._read()) !== next) self._write(next);
        });
      },
    },
  };

  // ── Stepper ───────────────────────────────────────────────────────
  // L'index courant est un ENTIER, et c'est ce qui rend le scope aussi
  // petit : « cette étape est-elle faite ? » se répond par une
  // comparaison, là où un id demanderait un indexOf dans une liste bakée.
  //
  //   bz-data="{...$bz.stepper.scope, current: 1, _read(){…}, _write(v){…},
  //             _max: 3}"
  //
  // ``_max`` = le plus grand index atteignable — le nombre d'ÉTAPES, ou de
  // PANNEAUX s'il y en a un de plus (l'écran « terminé »). Sans lui,
  // ``next()`` ne saurait pas où s'arrêter, et cuire la borne dans le
  // corps de la méthode ferait deux CODES différents pour deux steppers
  // de longueurs différentes — la dérive que ce fichier existe pour tuer.
  $bz.stepper = {
    scope: {
      // Le seul état que le thème lit (``data-[status=done]/step:``).
      // Une étape en ERREUR ne passe pas par ici : son attribut est
      // statique côté serveur, donc jamais recalculé.
      _status(i) {
        const cur = Number(this._read()) || 0;
        return i < cur ? "done" : i === cur ? "current" : "upcoming";
      },
      goTo(i) {
        const n = Number(i);
        if ((Number(this._read()) || 0) === n) return;
        this._write(n);
      },
      next() {
        const cur = Number(this._read()) || 0;
        if (cur < this._max) this._write(cur + 1);
      },
      prev() {
        const cur = Number(this._read()) || 0;
        if (cur > 0) this._write(cur - 1);
      },
    },
  };

  // ── Tooltip ───────────────────────────────────────────────────────
  // Le cas le plus net de « config cuite dans le code » après Pagination :
  // le corps sérialisé contenait ``if (!(true)) return;`` — le drapeau
  // d'activation en dur — et le délai d'ouverture en littéral. Deux
  // tooltips de délais différents produisaient deux CODES différents.
  //
  // ``_delay`` passe en données — c'est un littéral server-side, donc une
  // VRAIE donnée. ``_enabled`` non : il accepte un ClientBinding ou une
  // expression JS vive, et un champ de bz-data n'est évalué qu'une fois,
  // hors effet (``absorb`` en découple le snapshot du store). La bascule
  // en champ l'avait donc figé au montage alors que la docstring du
  // builder promettait l'inverse — « la condition est évaluée au moment
  // du survol ». Il redevient une MÉTHODE : constante par défaut ici,
  // surchargée par le builder quand la condition est réelle.
  $bz.tooltip = {
    scope: {
      _enabled() {
        return true;
      },
      _show() {
        if (!this._enabled()) return;
        clearTimeout(this._t);
        this._t = setTimeout(() => {
          this.open = true;
        }, this._delay);
      },
      _hide() {
        clearTimeout(this._t);
        this.open = false;
      },
    },
  };
})();


/* 17_carousel.js — scope partagé du composant Carousel.
 *
 * Le défilement est du **CSS scroll-snap**, pas un translateX piloté d'ici :
 * la piste est un conteneur `overflow-x-auto snap-x snap-mandatory` et
 * chaque slide porte `snap-start`. Ce choix décide de tout ce fichier.
 *
 * Ce que le navigateur fait, et qu'on n'écrit donc pas : le swipe tactile
 * avec son inertie et son rubber-banding, le scroll à la molette, le
 * clavier, et l'aimantation elle-même. Il reste ici deux choses — aller à
 * un index, et lire l'index depuis la position de scroll.
 *
 *   bz-data="{...$bz.carousel.scope, current: 0, _track: null,
 *             _read(){…}, _write(v){…}}"
 *
 * ``_track`` est capturé au ``bz-init`` du root (`_track = $refs.bztrack`)
 * : une méthode de scope n'a **pas** accès à ``$refs``, seules les
 * directives en ont (même contrainte que Slider, cf. sa docstring).
 *
 * ⚠️ **Toute la géométrie est LUE du DOM, jamais calculée.** La foulée
 * vient de l'écart réel entre deux slides, la borne de
 * ``scrollWidth - clientWidth``. C'est ce qui rend le ``per_view``
 * responsive (`{"base": 1, "md": 3}`) gratuit : le JS n'a aucun
 * breakpoint à connaître, il mesure ce que CSS a décidé.
 */
(function () {
  "use strict";
  const $bz = (window.$bz = window.$bz || {});

  //: Silence après le dernier événement de scroll avant de considérer que
  //: la position est arrêtée. Sans ce délai, un défilement fluide de 0 à 3
  //: publierait 1 puis 2 en passant — et sur un ``value`` lié au serveur,
  //: chaque valeur intermédiaire partirait en ``change``.
  const SETTLE_MS = 120;

  $bz.carousel = {
    scope: {
      // ── Géométrie ────────────────────────────────────────────────
      // Des MÉTHODES, jamais des getters : ``scope.absorb`` invoque
      // chaque clé à l'enregistrement et figerait un getter sur sa
      // première valeur (cf. traps.md).
      _step() {
        const t = this._track;
        if (!t || !t.children.length) return 0;
        const a = t.children[0];
        // L'écart entre DEUX slides, pas la largeur d'une seule : il
        // comprend le gap, donc il reste juste quel que soit l'espacement
        // du thème.
        if (t.children.length > 1) {
          return (
            t.children[1].getBoundingClientRect().left -
            a.getBoundingClientRect().left
          );
        }
        return a.getBoundingClientRect().width;
      },
      _maxIndex() {
        // ``void this._geom`` n'est PAS mort : c'est la lecture qui
        // INSCRIT la dépendance réactive de tout ce qui mesure. Une
        // mesure DOM n'est pas un signal — sans ce lien, un
        // ``bz-attr:disabled="_atEnd()"`` s'évalue une fois au scan, avec
        // la mise en page de cet instant-là, et ne se relit jamais. Payé
        // pour de vrai : hydraté avant que la feuille Tailwind s'applique,
        // la piste n'est pas encore ``flex``, donc ``scrollWidth ===
        // clientWidth``, donc la borne vaut 0, donc les DEUX flèches sont
        // désactivées — et ``disabled:opacity-0`` les efface. Aucune
        // flèche à la première visite, toutes au refresh. Cf.
        // ``_observeGeom`` pour qui bouge ce signal.
        void this._geom;
        // ``_step()`` rend déjà 0 sans piste, donc ce test couvre les
        // deux cas — et ``_geomIndex`` juste dessous s'appuie sur la même
        // propriété. Doubler la garde ici ferait croire que les deux
        // voisins ne sont pas d'accord.
        const step = this._step();
        if (!step) return 0;
        const t = this._track;
        return Math.max(0, Math.round((t.scrollWidth - t.clientWidth) / step));
      },
      _geomIndex() {
        const step = this._step();
        return step ? Math.round(this._track.scrollLeft / step) : 0;
      },

      // ── Ce qui rend la mesure ré-évaluable ───────────────────────
      // Appelé depuis un ``bz-effect`` porté par la PISTE, et surtout pas
      // depuis le ``bz-init`` du root : ``bz-init`` est one-shot par NŒUD
      // (``el._bzInitDone``), or idiomorph morphe EN PLACE — le nœud du
      // root survit, donc le hook ne re-court pas, donc les slides
      // ajoutées par un morph ne seraient jamais observées. Un
      // ``bz-effect`` est jeté et refait à chaque rescan, ce qui
      // ré-observe l'ensemble courant sans rien de plus à écrire.
      // (``ui.carousel`` + ``ui.each`` dans une zone rafraîchie est le
      // cas d'usage numéro un du composant : ce chemin-là n'est pas un
      // coin.)
      //
      // Il ne doit PAS rejoindre l'effet du root, qui dépend déjà de
      // ``_geom`` via ``_syncFromValue`` → ``_maxIndex`` : le bump du
      // premier rapport de l'observer le relancerait, ce qui rebrancherait
      // l'observer, qui rapporterait à nouveau — une boucle.
      //
      // Pourquoi un ResizeObserver et pas un ``window.resize`` : la borne
      // bouge sans que la fenêtre bouge. Un ``per_view`` responsive
      // change la largeur des SLIDES au breakpoint ; un carousel hydraté
      // dans un panneau replié mesure zéro jusqu'à l'ouverture ; une
      // feuille de style qui arrive après le scan retourne la piste de
      // ``block`` à ``flex``. Les trois se voient sur une boîte observée,
      // aucune ne passe par un événement de fenêtre.
      //
      // UNE slide est observée en plus de la piste, et une seule suffit :
      // elles portent toutes la MÊME chaîne de classes (``slide_class``
      // est composée une fois côté Python puis appliquée à chacune), donc
      // elles changent de taille ensemble. La première est un témoin
      // fidèle du groupe ; observer les quatre-vingts autres n'apporterait
      // pas une information de plus.
      _observeGeom() {
        const t = this._track;
        if (!t) return;
        // L'observer est rangé sur le NŒUD observé, pas sur le scope —
        // même choix que ``$bz._tick`` avec ``el._bzTickId``, et pour la
        // même raison : sa durée de vie est celle de la piste, donc une
        // piste détachée emporte son observer avec elle. Sur le scope, il
        // survivrait à son sujet.
        //
        // Le ranger là évite AUSSI une boucle : cette méthode court dans
        // un effet, et un champ de scope écrit depuis un effet qui le lit
        // se rappellerait lui-même sans fin (un champ non déclaré devient
        // un signal à la première écriture — cf. ``03_scope.js``). Une
        // propriété de nœud n'est pas réactive, donc rien ne se relance.
        if (t._bzGeomRo) t._bzGeomRo.disconnect();
        const self = this;
        // Bumper un compteur plutôt que publier la mesure : la mesure
        // reste lue au moment où on en a besoin (une seule source), le
        // signal ne sert qu'à dire « relis ». Pas de boucle possible —
        // ce que l'effet écrit derrière (``disabled``, donc une opacité)
        // ne change aucune boîte.
        const ro = new ResizeObserver(function () {
          self._geom = self._geom + 1;
        });
        ro.observe(t);
        if (t.children[0]) ro.observe(t.children[0]);
        t._bzGeomRo = ro;
      },

      // ── Bornes — l'état désactivé des flèches ────────────────────
      // Lire ``_read()`` inscrit la dépendance réactive (c'est lui qui
      // bouge) ; la BORNE, elle, vient de la géométrie — donc aucun
      // calcul de per_view ni de breakpoint.
      _atStart() {
        return Number(this._read()) <= 0;
      },
      _atEnd() {
        return Number(this._read()) >= this._maxIndex();
      },

      // ── Navigation ───────────────────────────────────────────────
      goTo(i) {
        const t = this._track;
        if (!t) return;
        const n = Math.max(0, Math.min(this._maxIndex(), Number(i) || 0));
        t.scrollTo({ left: n * this._step(), behavior: "smooth" });
        // On n'écrit PAS l'état ici : ``_onScroll`` est la source unique
        // de l'index, et il le publiera quand la position sera arrêtée.
        // Écrire des deux côtés ferait diverger le signal de ce que
        // l'utilisateur voit dès qu'il interrompt l'animation d'un doigt.
      },
      // ``next`` / ``prev`` BOUCLENT, et ce n'est pas en contradiction
      // avec des flèches qui butent : les flèches sont désactivées aux
      // bords, donc elles n'arrivent jamais ici au bout. Ce qui arrive
      // ici au bout, c'est l'autoplay — et une rotation qui s'arrête
      // n'est plus une rotation.
      next() {
        const max = this._maxIndex();
        const cur = Number(this._read()) || 0;
        this.goTo(cur >= max ? 0 : cur + 1);
      },
      prev() {
        const cur = Number(this._read()) || 0;
        this.goTo(cur <= 0 ? this._maxIndex() : cur - 1);
      },

      // ── Le pont position → état ──────────────────────────────────
      _onScroll() {
        clearTimeout(this._settleId);
        this._settleId = setTimeout(() => {
          const i = this._geomIndex();
          if (Number(this._read()) !== i) this._write(i);
        }, SETTLE_MS);
      },

      // ── Le pont état → position ──────────────────────────────────
      // Appelé depuis un ``bz-effect`` du root : lire ``_read()`` inscrit
      // la dépendance, donc un écrivain EXTERNE (une binding pilotée
      // ailleurs, un `.set(i)`) fait défiler la piste.
      //
      // La garde ``!==`` est ce qui empêche la boucle avec ``_onScroll``,
      // et elle suffit : pendant un défilement fluide, la position
      // publiée finit par égaler la cible, l'effet se relance, ne trouve
      // plus d'écart, et n'appelle pas ``scrollTo`` une seconde fois.
      _syncFromValue() {
        const t = this._track;
        if (!t) return;
        const target = Math.max(
          0,
          Math.min(this._maxIndex(), Number(this._read()) || 0)
        );
        if (this._geomIndex() === target) return;
        // Le tout premier accord est INSTANTANÉ : un carousel rendu à
        // value=2 doit s'afficher sur la slide 2, pas défiler depuis la 0
        // sous les yeux de l'utilisateur au chargement.
        const behavior = this._booted ? "smooth" : "auto";
        this._booted = true;
        t.scrollTo({ left: target * this._step(), behavior: behavior });
      },

      // ── Autoplay ─────────────────────────────────────────────────
      // Un seul geste de l'utilisateur et la rotation s'arrête, pour de
      // bon. Pas de reprise après un délai : un contenu qui se remet à
      // bouger pendant qu'on le lit est la plainte d'accessibilité
      // numéro un sur les carrousels. Pas de pause au survol non plus —
      // elle n'existe pas sur un pointeur grossier.
      //
      // ``still`` est un SIGNAL déclaré dans le ``bz-data`` (pas un champ
      // posé à la volée) : c'est l'effet du root qui le lit, en
      // ``$bz._tick($el, !still, ms)``, et un champ non déclaré ne
      // relancerait jamais cet effet — l'autoplay tournerait pour
      // toujours.
      _touch() {
        if (!this.still) this.still = true;
      },
    },
  };
})();


/* 18_time_picker.js — scope partagé du composant TimePicker.
 *
 * La valeur est une CHAÎNE ``"HH:MM"`` — même forme que l'ISO des
 * pickers de date : triable, comparable, sérialisable telle quelle dans
 * une form data, et lisible par un humain dans le champ éditable.
 *
 *   bz-data="{...$bz.time.scope, open: false, value: "09:30",
 *             _read(){…}, _write(v){…}}"
 *
 * ⚠️ ``_read`` / ``_write`` ne sont PAS une élégance : une expression
 * liée doit vivre dans un CORPS DE MÉTHODE. Un champ de ``bz-data`` est
 * évalué UNE fois, hors effet — ``absorb`` en emballe le snapshot dans
 * un signal neuf découplé de la cellule du store, que plus rien ne
 * réécrit (régression mesurée sur Pagination et Tooltip, cf. traps.md
 * § « un champ de bz-data n'est pas réactif »).
 *
 * Pourquoi un scope partagé plutôt que des expressions inline : un
 * panneau à 24 heures et 4 minutes fait 28 boutons. Écrire le pick et le
 * test de sélection en toutes lettres sur chacun sérialiserait le même
 * algorithme 28 fois PAR INSTANCE — exactement ce que les bascules
 * « config en données » de Pagination et Accordion ont retiré.
 */
(function () {
  "use strict";
  const $bz = (window.$bz = window.$bz || {});

  //: Index des deux parties dans le tuple rendu par ``_parts``.
  const HOUR = 0;
  const MINUTE = 1;

  $bz.time = {
    scope: {
      // ── Lecture ──────────────────────────────────────────────────
      // Des MÉTHODES, jamais des getters : ``scope.absorb`` invoque
      // chaque clé à l'enregistrement et figerait un getter sur sa
      // première valeur (cf. traps.md).
      _parts() {
        const m = String(this._read() || "").match(/^(\d{1,2}):(\d{2})/);
        // Deux chaînes vides plutôt que null : les appelants comparent,
        // ils n'ont jamais à tester la présence.
        return m ? [m[1].padStart(2, "0"), m[2]] : ["", ""];
      },
      _is(part, v) {
        return this._parts()[part] === v;
      },

      // ── Écriture ─────────────────────────────────────────────────
      _pick(part, v) {
        const p = this._parts();
        p[part] = v;
        // Une heure choisie alors que la minute est inconnue vaut ``:00``
        // — sinon le champ resterait VIDE juste après un clic, et
        // l'utilisateur croirait que le clic n'a pas pris. Symétrique
        // pour une minute choisie en premier.
        this._write(
          (p[HOUR] || "00") + ":" + (p[MINUTE] || "00")
        );
      },
      // Le clic sur une MINUTE referme le panneau, celui sur une heure
      // non : l'ordre de lecture est heure puis minute, donc refermer à
      // l'heure couperait la main de l'utilisateur au milieu de son
      // geste. ``_closeOnPick`` est une donnée (le prop du composant).
      pick(part, v) {
        this._pick(part, v);
        if (this._closeOnPick && part === MINUTE) this.open = false;
      },
    },

    /* Peindre les cellules des deux colonnes, puis marquer la sélection.
     *
     * Pourquoi les cellules ne sont plus rendues par Python
     * ------------------------------------------------------
     * Elles portaient chacune la chaîne de classe du thème — 452
     * caractères — et deux directives (``bz-attr:data-selected`` +
     * ``bz-on:click``). À ``step=1`` ça fait 84 cellules : 49 Ko sur les
     * 54 que pesait le composant, dont 38 pour la seule classe répétée à
     * l'identique. Mesuré le 2026-09-01.
     *
     * C'est le même remède que ``<bz-calendar>``, qui laisse sa grille
     * VIDE en SSR et la remplit ici — mais SANS custom element : sa
     * docstring dit qu'un deuxième serait le moment d'en faire une
     * politique du runtime, et alléger un payload ne justifie pas
     * d'ouvrir ce chantier. Un ``bz-effect`` sur le conteneur suffit.
     *
     * Les cellules n'ont plus AUCUNE directive
     * -----------------------------------------
     * Un clic délégué remplace 84 ``bz-on:click``, et cet effet remplace
     * 84 ``bz-attr:data-selected``. C'est ce qui évite d'avoir à
     * rescanner le sous-arbre après l'avoir peint — un ``$bz._scan``
     * appelé depuis le corps d'un effet qu'un scan vient d'installer se
     * réinstallerait lui-même.
     *
     * L'effet re-tourne à chaque changement de la valeur (il lit
     * ``_parts()``), donc la sélection se repeint sans que rien d'autre
     * ne bouge. La construction, elle, ne se fait qu'une fois : la garde
     * est une MESURE du DOM (« ai-je déjà des cellules ? »), légitime
     * ici pour la même raison que dans ``bz-calendar.rehydrate`` — elle
     * ne dérive aucun affichage, elle constate un fait ponctuel au seul
     * moment où la question se pose.
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

        // Un seul écouteur par colonne. Le drapeau vit sur le NŒUD, et
        // c'est correct ici : si idiomorph garde le nœud, l'écouteur
        // survit avec lui ; s'il le remplace, le nouveau n'a pas le
        // drapeau et se recâble. Le drapeau et l'écouteur sont toujours
        // d'accord — c'est très exactement ce qui manquait au suivi de
        // ``bz-class`` (cf. traps.md).
        if (!col._bzTimeWired) {
          col._bzTimeWired = true;
          col.addEventListener("click", function (ev) {
            const cell = ev.target.closest("[data-bz-v]");
            if (!cell || cell.disabled) return;
            pick(part, cell.getAttribute("data-bz-v"));
          });
        }

        // La sélection, à chaque passage de l'effet.
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


/* 19_dnd.js — le geste node-DnD partagé par `dropzone` / `draggable`.
 *
 * ⚠️ **Distinct du « drag » des deux autres familles du dépôt**, et le
 * §6 de la roadmap insiste parce que les confondre coûte cher :
 *   - `12_slider.js`      = pointer-drag (pointeur → valeur continue) ;
 *   - `08_file_upload.js` = DnD HTML5 natif (fichiers de l'OS, DataTransfer).
 * Ici c'est le troisième : **déplacer un nœud** d'une position à une autre.
 *
 * ── Pourquoi Pointer Events et pas l'API HTML5 `draggable` ────────────
 * L'API HTML5 ne déclenche tout simplement pas `dragstart` sur mobile.
 * Décision de cadrage figée : Pointer Events, comme le slider.
 *
 * ── Pourquoi la délégation au document ───────────────────────────────
 * Un listener par zone devrait se re-brancher après chaque morph, et un
 * `bz-init` qui re-tourne double-bind (le rescan du bridge dispose et
 * re-bind les directives). Un seul listener au document, qui retrouve sa
 * cible par `closest()`, est **insensible au morph** et ne garde aucun
 * état sur les nœuds — la contrainte que traps.md § « bz-class perdue
 * après un morph » a rendue non négociable.
 *
 * ── Pourquoi on déplace le VRAI nœud, sans clone ─────────────────────
 * Le réordonnancement est appliqué au DOM pendant le geste. Donc :
 *   1. l'aperçu est gratuit — pas de fantôme à positionner, pas de calcul
 *      de décalage pour les voisins, le navigateur reflow tout seul ;
 *   2. au drop, **l'ordre du DOM EST le résultat** — on lit les index au
 *      lieu de les calculer, donc l'aperçu ne peut pas mentir sur ce qui
 *      part au serveur ;
 *   3. c'est déjà l'optimiste. Le serveur re-rend, idiomorph réapparie par
 *      `bz-id` et le nœud déplacé est RÉUTILISÉ, pas recréé — mesuré, et
 *      gaté par `tests/runtime_js/test_morph_preserves_reordered_nodes.py`.
 *
 * ── Le snap-back d'un refus a besoin de code, contrairement à ce qui
 *    était écrit ici ──────────────────────────────────────────────────
 * Cette ligne a longtemps dit « un refus serveur = pas de mutation = le
 * morph remet l'item en place. Aucun code dédié ici. » C'était FAUX, et
 * la gate qui prétendait le prouver était vacante : le handler du
 * playground incrémente un compteur de refus, donc son état changeait,
 * donc la zone se re-rendait — le snap-back ne venait pas du refus mais
 * du compteur. Un handler qui refuse en ne mutant RIEN — le cas que
 * `Move` documente comme LA façon de refuser, et celui d'`examples/crm`
 * — ne fait re-rendre aucune zone : le serveur répond zéro octet et la
 * carte reste là où le doigt l'a lâchée. Mesuré le 2026-09-09 sur
 * `examples/kanban` : une limite d'en-cours refusait au serveur, et
 * l'écran montrait quatre cartes dans une colonne qui en accepte trois.
 *
 * D'où le TÉMOIN ci-dessous. Il ne coûte rien au cas normal et ne
 * demande rien à l'auteur d'app : l'attribut est posé sur l'item au
 * moment du dépôt, le serveur ne le rend jamais, donc idiomorph l'efface
 * dès qu'il ré-apparie le nœud. S'il est encore là quand la requête
 * retombe, personne n'a répondu pour cet item — et le geste se défait.
 *
 * ── La géométrie est LUE, jamais configurée ──────────────────────────
 * L'axe (liste verticale ou horizontale) est déduit de la position réelle
 * de deux items, comme le Carousel déduit sa foulée. Aucun breakpoint,
 * aucun prop `orientation=` à tenir synchronisé avec le CSS.
 *
 * Contrat DOM attendu du Python (aucune directive `bz-*` neuve) :
 *   zone : data-bz-dropzone="<name>"  data-bz-accepts="a,b"  [data-bz-locked]
 *          + un carrier caché [data-bz-move-carrier] portant le hx-post
 *   item : data-bz-draggable  data-bz-key="…"  [data-bz-group] [data-bz-disabled]
 *          [data-bz-handle]  → si présent, seul [data-bz-drag-handle] attrape
 */
(function () {
  "use strict";
  const $bz = (window.$bz = window.$bz || {});

  //: Souris/stylet : distance avant que le geste devienne un drag. C'est
  //: ce seuil qui PRÉSERVE LE CLIC — sans lui, tout clic sur une carte
  //: démarrerait un déplacement.
  const MOUSE_THRESHOLD_PX = 5;
  //: Tactile : durée d'appui avant d'attraper.
  const TOUCH_HOLD_MS = 250;
  //: …et la distance au-delà de laquelle on abandonne avant la fin du
  //: délai. C'est elle qui PRÉSERVE LE SCROLL : un doigt qui file dans une
  //: liste ne doit pas emporter la carte qu'il a effleurée.
  const TOUCH_TOLERANCE_PX = 8;

  //: Le témoin d'un dépôt en attente de réponse. Posé sur l'item, effacé
  //: par le morph — le serveur ne rend jamais cet attribut, donc
  //: idiomorph le retire en ré-appariant le nœud. C'est la seule mesure
  //: possible depuis le client de « la réponse a-t-elle touché cet
  //: item », et elle ne demande aucun protocole neuf.
  const PENDING_ATTR = "data-bz-drop-pending";

  const ZONE_SEL = "[data-bz-dropzone]";
  const ITEM_SEL = "[data-bz-draggable]";
  const HANDLE_SEL = "[data-bz-drag-handle]";
  const CARRIER_SEL = "[data-bz-move-carrier]";
  //: Pose sur la ZONE pendant le survol d'un ecrasement. Le theme s'y
  //: accroche ; rien d'autre ne le lit.
  const REPLACE_ATTR = "data-bz-drop-replace";

  //: Un seul geste à la fois — c'est une vérité physique du pointeur, pas
  //: un raccourci d'implémentation. `armed` = doigt posé, drag pas encore
  //: décidé ; `active` = drag en cours.
  let armed = null;
  let active = null;

  // ── Lecture du contrat DOM ───────────────────────────────────────────

  function zoneOf(el) {
    return el ? el.closest(ZONE_SEL) : null;
  }

  function itemsOf(zone) {
    // Les items d'une zone IMBRIQUÉE ne sont pas les nôtres.
    return Array.prototype.filter.call(
      zone.querySelectorAll(ITEM_SEL),
      function (it) { return zoneOf(it) === zone; }
    );
  }

  function indexOf(item) {
    const zone = zoneOf(item);
    return zone ? itemsOf(zone).indexOf(item) : -1;
  }

  /* Où insérer, quand il n'y a aucun item à viser.
     ⚠️ **Un item n'est PAS forcément enfant direct de sa zone.** Une
     dropzone n'arrange rien — elle reçoit — donc l'appelant empile ses
     items avec le conteneur qu'il utilise déjà (`ui.vstack`, `ui.grid`).
     Insérer dans la ZONE mettrait la carte à côté de cette pile, et
     `insertBefore` lève carrément quand la cible n'est pas son enfant.
     C'est le bug que la page de banc a révélé et que le DOM synthétique
     des tests de geste ne pouvait pas produire. */
  function itemsContainer(zone) {
    const first = itemsOf(zone)[0];
    if (first) return first.parentNode;
    /* Zone VIDE. Retomber sur la zone elle-même était un bug, et le
       commentaire qui vivait ici disait pourquoi il passait inaperçu :
       « le prochain rendu serveur remettra la carte dans la pile ». Il
       ne la remet pas. Le nœud déplacé garde son `bz-id`, qui encode son
       chemin dans l'arbre ; ce chemin a changé, donc idiomorph ne le
       ré-apparie pas et la carte RESTE là où on l'a posée — c'est-à-dire
       enfant direct de la zone, HORS du conteneur que l'app a rendu.

       Reproduit le 2026-09-13 sur `/dnd`, par un glisser qui HÉSITE :
       on sort l'item de sa zone, on change d'avis, on revient. La zone
       d'origine est alors vide, l'item y est ré-append à la racine, et
       il s'affiche à côté de sa boîte au lieu de dedans. Un geste
       hésitant est le geste ordinaire.

       Ce qu'on fait à la place : l'app a rendu ses items dans un
       conteneur à elle (un `vstack`, une grille) — il est toujours là,
       vide. On descend la chaîne des enfants UNIQUES pour le retrouver.
       Le porteur caché du `hx-post` ne compte pas : il est toujours
       présent et fausserait le décompte. */
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

  /* Une zone qui ne tient qu'UN element. Le defaut, `many`, ne s'ecrit
     pas : l'absence d'attribut suffit. */
  function holdsOne(zone) {
    return zone.getAttribute("data-bz-holds") === "one";
  }

  /* Marquer la cible d'un ECRASEMENT, et ne marquer qu'elle. */
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

  /* La zone accepte-t-elle ce groupe ?
     ⚠️ `data-bz-accepts` absent ne veut PAS dire « accepte tout ». Une
     zone sans déclaration ne reçoit **que ses propres items** : deux
     listes indépendantes sur la même page ne doivent pas s'échanger des
     cartes parce que personne n'a rien déclaré. C'est le défaut de
     Sortable.js (un groupe anonyme y est unique par instance), et le
     banc du playground l'a prouvé nécessaire — sans lui, attraper une
     carte du kanban surlignait les cinq zones sans rapport de la page.
     Recevoir d'ailleurs est donc un OPT-IN, pas un défaut. */
  function accepts(zone, group, originZone) {
    //: ⚠️ `accepts` gouverne l'ENTRÉE DEPUIS AILLEURS, pas le
    //: réordonnancement interne. Réordonner dans sa propre zone n'est pas
    //: y entrer : l'item y est déjà, et personne n'a rien déclaré à ce
    //: sujet. Consulter `accepts` ici gelait une liste entière dès que le
    //: `group=` des items ne répondait pas à son `accepts=` — mesuré :
    //: `accepts=["card"]` sur des items sans groupe rendait la zone
    //: totalement inerte, en silence. Sortable.js sépare pour la même
    //: raison `put` (recevoir) de `sort` (réordonner).
    if (zone === originZone) return true;
    const raw = (zone.getAttribute("data-bz-accepts") || "").trim();
    //: Absent OU vide : la zone ne reçoit rien d'ailleurs. Les deux se
    //: valent maintenant que le cas interne est sorti — donc
    //: `accepts=[]` scelle bien ce qu'il annonce, ce qui n'était pas le
    //: cas quand la liste vide se confondait avec « non déclarée ».
    if (!raw) return false;
    return raw.split(",").some(function (g) { return g.trim() === group; });
  }

  /* Les deux portes du §6, gardées SÉPARÉES : `accepts` décide de
     l'entrée, `locked` décide de la sortie. Une corbeille est une zone
     qui accepte un groupe et dont rien ne ressort. */
  function canLeave(zone) {
    return !zone.hasAttribute("data-bz-locked");
  }

  function canEnter(zone, group, originZone) {
    if (!accepts(zone, group, originZone)) return false;
    if (zone !== originZone && !canLeave(originZone)) return false;
    return true;
  }

  // ── Géométrie mesurée ────────────────────────────────────────────────

  /* Axe dominant, déduit de deux items réels. Une liste dont les items
     s'écartent surtout en X est horizontale — le CSS a déjà tranché, on
     se contente de le lire. Repli sur l'axe vertical (le cas courant)
     quand il n'y a pas deux items à comparer. */
  function axisOf(zone) {
    //: L'item tiré n'est PAS exclu, et c'est le correctif du 2026-08-10 :
    //: on déplace le vrai nœud, donc il est toujours dans le flux et sa
    //: boîte est aussi valable que celle d'un autre. L'exclure laissait
    //: une liste de DEUX items avec un seul repère, donc un repli sur
    //: l'axe vertical — mesuré : une rangée horizontale de deux cartes
    //: était impossible à réordonner, la comparaison se faisant sur un Y
    //: que les deux partagent.
    const items = itemsOf(zone);
    if (items.length >= 2) {
      const a = items[0].getBoundingClientRect();
      const b = items[1].getBoundingClientRect();
      if (a.left !== b.left || a.top !== b.top) {
        return Math.abs(b.left - a.left) > Math.abs(b.top - a.top) ? "x" : "y";
      }
    }
    //: Un seul item (ou deux superposés) : plus rien à mesurer entre deux
    //: boîtes, on demande au CSS ce qu'il a décidé. Toujours LU, jamais
    //: configuré — aucun prop `orientation=` à tenir synchronisé.
    const box = itemsContainer(zone);
    const dir = (getComputedStyle(box).flexDirection || "");
    return dir.indexOf("row") === 0 ? "x" : "y";
  }

  /* Faut-il insérer APRÈS l'item survolé ? On compare le pointeur au
     milieu de sa boîte, sur l'axe de la liste. */
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
    //: Bouton principal seulement : un clic droit ouvre un menu, il
    //: n'attrape pas.
    if (e.pointerType === "mouse" && e.button !== 0) return;

    const item = e.target.closest ? e.target.closest(ITEM_SEL) : null;
    if (!item || item.hasAttribute("data-bz-disabled")) return;
    const zone = zoneOf(item);
    if (!zone) return;

    //: `handle=True` : la carte entière reste inerte, seule la poignée
    //: attrape. C'est une RESTRICTION opt-in, pas le geste par défaut.
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
      //: Tactile : c'est le TEMPS qui décide, pas la distance.
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
      //: De quoi défaire le geste exactement — `insertBefore(item, null)`
      //: rend un append, donc un item repris en dernière position se
      //: restaure sans cas particulier.
      originParent: a.item.parentNode,
      originNext: a.item.nextSibling,
      group: groupOf(a.item),
      pointerId: a.pointerId,
    };
    //: Un attribut, pas une classe : le thème s'y accroche en
    //: `data-[bz-dragging]:…`, et un morph qui réécrit `class=` ne peut
    //: pas l'effacer par accident.
    active.item.setAttribute("data-bz-dragging", "true");
    /* ⚠️ L'AXE — un HOOK pour le thème, pas un réglage du runtime.
       Le défaut livré n'en fait rien : une carte en vol garde sa taille
       (cf. le slot `dragging` de `draggable`). Il est publié pour qu'une
       app qui préfère un EMPLACEMENT puisse l'obtenir en surchargeant ce
       slot, sans prop et sans toucher au geste.

       Pourquoi l'axe et pas un booléen : « plus petit » n'a pas le même
       sens dans les deux sens. Une liste verticale veut une barre pleine
       largeur, une rangée horizontale veut une colonne pleine hauteur.
       Le CSS ne sait pas mesurer une liste ; `axisOf` le déduit déjà de
       la position réelle de deux items.

       Pourquoi pas sur une zone `holds="one"` : elle n'insère rien. Sa
       carte ne laisse pas un espace à combler, elle laisse une place
       VIDE — et un thème qui réduirait un occupant à une barre dans sa
       chaise raconterait quelque chose de faux. */
    if (!holdsOne(a.zone)) {
      active.item.setAttribute("data-bz-drag-axis", axisOf(a.zone));
    }
    makePreview(a.x, a.y);
    markValidZones();
  }

  /* L'aperçu qui suit le pointeur.
     Sans lui, seule la LISTE bouge : les voisins s'écartent, mais rien
     n'est « en main » et le geste se lit comme un curseur qui se promène.
     C'est le clone qui vole et l'original qui reste — la forme de
     Sortable.js et du DragOverlay de dnd-kit — plutôt que de translater
     le vrai nœud, qui est déjà réordonné dans le flux et se déplacerait
     donc deux fois.

     ⚠️ **Le clone doit être ANONYME.** On lui retire `id`, `bz-id` et
     `data-bz-draggable`, sur lui ET sur toute sa descendance : un id en
     double ferait apparier n'importe quoi à idiomorph au prochain morph,
     et un `data-bz-draggable` en double fausserait les index lus par
     `itemsOf`. Le reste de son apparence est un simple clone de ce que
     l'utilisateur regardait déjà. */
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
    //: Largeur figée : hors du flux, un bloc n'a plus de parent dont
    //: hériter, et l'aperçu s'effondrerait sur son contenu.
    node.style.width = rect.width + "px";
    node.style.height = rect.height + "px";
    node.style.left = rect.left + "px";
    node.style.top = rect.top + "px";

    //: L'écart entre le point saisi et le coin de la carte. C'est lui qui
    //: fait que la carte ne « saute » pas sous le curseur au moment où on
    //: l'attrape — elle reste tenue là où on l'a prise.
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

  /* Exigence 1 du cadrage : montrer OÙ l'item peut atterrir, pendant le
     geste. Gaté sur un attribut posé par le geste, jamais sur `:hover` —
     un survol n'existe pas au doigt, et c'est le pointeur de référence de
     ce projet. */
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
        //: Le doigt a filé avant la fin du délai : c'était un scroll.
        if (Math.max(dx, dy) > TOUCH_TOLERANCE_PX) disarm();
      } else if (Math.max(dx, dy) > MOUSE_THRESHOLD_PX) {
        begin();
      }
      return;
    }
    if (!active || e.pointerId !== active.pointerId) return;

    //: Pendant un drag tactile, le geste nous appartient : sans ça la
    //: page défile sous la carte.
    if (e.cancelable) e.preventDefault();
    //: L'aperçu d'abord : il doit suivre le doigt même quand le pointeur
    //: survole une zone qui refuse, sinon la carte se fige et le geste a
    //: l'air cassé alors qu'il est simplement refusé.
    movePreview(e.clientX, e.clientY);
    hoverTo(e.clientX, e.clientY);
  }

  /* Le cœur : replacer le nœud là où le pointeur dit qu'il va. */
  function hoverTo(x, y) {
    const under = document.elementFromPoint(x, y);
    if (!under) return;
    const overZone = zoneOf(under);
    if (!overZone) return;
    if (!canEnter(overZone, active.group, active.originZone)) return;

    /* ⚠️ ECRASEMENT. Une zone qui ne tient qu'un element et en porte
       deja un ne doit RIEN recevoir pendant le geste : y glisser le noeud
       la ferait contenir deux occupants — ce que l'utilisateur voit comme
       « l'item prend enormement de place ». On la marque, on ne la
       remplit pas. Le depot partira quand meme au handler, qui decide
       (echanger, refuser) : c'est le serveur qui arbitre, ici on ne fait
       qu'annoncer honnetement ce qui va se passer. */
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
      //: Relatif au PARENT DE LA CIBLE, jamais à la zone — cf.
      //: `itemsContainer`. Les items peuvent vivre à n'importe quelle
      //: profondeur sous la zone.
      overItem.parentNode.insertBefore(
        active.item, after ? overItem.nextSibling : overItem
      );
      return;
    }
    //: Survol de la zone hors de tout item — typiquement une colonne vide
    //: ou l'espace sous le dernier item. On n'append que si l'item n'est
    //: pas déjà ici, sinon chaque pointermove le rejetterait à la fin.
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

  /* Annuler = remettre le nœud exactement d'où il vient. Utilisé par
     Échap et par `pointercancel` — JAMAIS par un refus serveur, qui lui
     passe par le morph (cf. l'en-tête de ce fichier). */
  function cancel() {
    if (!active) return;
    active.originParent.insertBefore(active.item, active.originNext);
    cleanup();
  }

  /* Défaire le dépôt si la réponse ne l'a pas confirmé.
     ⚠️ Deux images d'attente, pas une : `htmx:afterRequest` est le seul
     désarmement fiable (htmx l'émet aussi sur 4xx, réseau, abandon), mais
     le swap et le rescan qui l'entourent se posent sur les images
     suivantes. Vérifier tout de suite lirait le témoin avant que le morph
     ait eu l'occasion de l'effacer, et TOUT dépôt reviendrait en arrière. */
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
          //: Le serveur peut avoir retiré l'item (archivage) : il n'y a
          //: alors rien à remettre, et son ancien parent peut lui-même
          //: avoir disparu.
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

  /* Reposer le point de départ de la navigation séquentielle après le
     morph. Un déplacement entre zones change le `bz-id` de la carte :
     idiomorph recrée alors son nœud et Chromium remet le focus sur BODY.
     Dans cet état, le premier Tab est avalé au lieu d'atteindre le prochain
     contrôle. On focalise la carte rendue par le serveur comme ancre
     temporaire ; elle n'entre pas durablement dans l'ordre de tabulation. */
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
    //: Un ecrasement n'a PAS deplace le noeud : la zone visee se lit sur
    //: la marque, pas sur la position. Son index est 0 — une zone a un
    //: element n'en a pas d'autre.
    const remplace = a.replaceZone;
    const toZone = remplace || zoneOf(a.item);
    const toIndex = remplace ? 0 : indexOf(a.item);
    const origin = {parent: a.originParent, next: a.originNext, item: a.item};
    cleanup();
    if (!toZone) return;

    //: Rien n'a bougé → aucun aller-retour serveur. Un drag qui repose
    //: l'item où il était ne doit pas produire de `Move`.
    if (!remplace && toZone === a.originZone && toIndex === a.originIndex) {
      return;
    }

    //: C'est la zone qui REÇOIT qui décide — son `on_move` est le
    //: handler, et son carrier porte le hx-post.
    //: ⚠️ Filtré par `zoneOf`, comme `itemsOf` : `querySelector` fouille
    //: TOUT le sous-arbre, donc une dropzone imbriquée — dont le carrier
    //: précède forcément celui du parent, puisqu'il est rendu en dernier —
    //: capterait le drop du parent et le POSTerait à SON handler.
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
    //: Le transport maison — le JS écrit, dispatche, et c'est le hx-post
    //: du carrier qui part. Aucun `fetch` ici : la frontière transport
    //: appartient au bridge (charter, principe 2).
    armSnapBack(origin.item, origin.parent, origin.next, carrier);
    $bz.helpers.emitChange(carrier, "move");
  }

  //: Une fois le geste ATTRAPÉ, le doigt nous appartient : c'est ce
  //: `preventDefault` sur le `touchmove` qui empêche le navigateur de
  //: faire défiler sous la carte.
  //:
  //: Il ne double PAS celui de `onPointerMove`. Un `preventDefault` sur
  //: un `pointermove` n'annule pas un défilement tactile — seul le
  //: `touchmove` le peut, et seulement en écoute NON PASSIVE. Tant que
  //: la CSS posait `touch-action: none` la question ne se posait pas :
  //: le navigateur ne défilait jamais. Depuis que l'item laisse le
  //: `pan-x pan-y` (finding [27] : sans ça le doigt ne pouvait plus
  //: faire défiler une colonne de cartes), il faut reprendre le geste au
  //: moment où l'appui long aboutit — et à cet instant précis le doigt
  //: n'a pas bougé, donc aucun défilement n'est en cours et la reprise
  //: est propre.
  //:
  //: ⚠️ On ne prévient RIEN tant que le drag n'est qu'`armed` : c'est
  //: exactement le cas « un doigt file dans la liste et effleure une
  //: carte », que la tolérance de 8 px laisse au défilement.
  function onTouchMove(e) {
    if (active && e.cancelable) e.preventDefault();
  }

  document.addEventListener("pointerdown", onPointerDown, true);
  //: `passive: false` — `onPointerMove` doit pouvoir `preventDefault()`
  //: pour tenir le scroll pendant un drag à la SOURIS (sélection de
  //: texte, drag natif d'image).
  document.addEventListener("pointermove", onPointerMove, { passive: false });
  document.addEventListener("touchmove", onTouchMove, { passive: false });
  document.addEventListener("pointerup", onPointerUp, true);
  document.addEventListener("pointercancel", onPointerCancel, true);
  document.addEventListener("keydown", onKeyDown, true);

  //: Exposé pour les tests et pour un futur composant qui piloterait le
  //: geste. Le contrat public reste les data-attributes.
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


/* 20_resizable.js — scope partagé du composant Resizable (split panes).
 *
 * ⚠️ **Troisième famille de « drag » du dépôt, et la confondre coûte cher** :
 *   - `12_slider.js`      = pointeur → une VALEUR sur une échelle ;
 *   - `19_dnd.js`         = déplacer un NŒUD d'une position à une autre ;
 *   - ici                 = pointeur → une DIMENSION. Rien ne bouge, rien
 *                           ne change de parent : deux voisins se
 *                           repartagent la place qu'ils occupent déjà.
 * C'est la famille du slider (pointer-drag, delta continu), pas celle du
 * node-DnD — la roadmap le dit depuis le cadrage #6 et ce fichier n'a donc
 * AUCUNE dépendance vers `19_dnd.js`.
 *
 *   bz-data="{...$bz.resizable.scope, sizes: [30,70], _mins: [10,10],
 *             _vertical: false, _group: null,
 *             _read(){…}, _write(v){…}}"
 *
 * ``_group`` est capturé au ``bz-init`` du root (`_group = $el`) : une
 * méthode de scope n'a pas accès à ``$el``, seules les directives en ont
 * (même contrainte et même remède que Slider et Carousel).
 *
 * ── Le partage se fait en POIDS, jamais en pixels ─────────────────────
 * Chaque panneau est un ``flex-grow: w`` sur une base nulle, donc le
 * navigateur répartit la place restante au prorata des poids — la largeur
 * des poignées est déduite AVANT le partage, sans qu'on la connaisse, et
 * un groupe qui rétrécit garde ses proportions sans qu'on écoute le
 * moindre ``resize``. Les pixels n'entrent ici qu'à un seul endroit : la
 * conversion du delta du pointeur, mesurée à chaque geste.
 *
 * ── Deux voisins, jamais plus ─────────────────────────────────────────
 * Tirer une poignée ne redistribue QUE la paire qu'elle sépare : leur
 * somme est invariante pendant le geste, donc les autres panneaux ne
 * bougent pas d'un pixel. C'est le comportement de tous les vrais
 * splitters, et c'est ce qui rend le geste prévisible — un utilisateur qui
 * élargit sa colonne de gauche n'a pas envie de voir la droite se
 * réorganiser.
 *
 * ── Pourquoi rien n'est publié PENDANT le geste ───────────────────────
 * Le glissement écrit les styles en direct (chemin rapide, aucun tick de
 * signal) ; l'état n'est publié qu'au relâchement. Publier chaque frame
 * enverrait un ``change`` par pixel au serveur, et ferait écrire
 * localStorage cent fois par seconde quand le ClientState est
 * ``persist="local"``. Même raison que le ``SETTLE_MS`` du Carousel.
 */
(function () {
  "use strict";
  const $bz = (window.$bz = window.$bz || {});

  //: Le pas d'une flèche du clavier, en points de pourcentage. Le motif
  //: ARIA « window splitter » exige que la poignée soit pilotable sans
  //: pointeur — c'est la seule façon de redimensionner au clavier, et
  //: elle est aussi la seule qui marche sans souris ET sans écran
  //: tactile.
  const KEY_STEP = 2;

  $bz.resizable = {
    scope: {
      // ── Lecture du DOM ───────────────────────────────────────────
      // ``:scope >`` et pas un querySelectorAll nu : un Resizable
      // IMBRIQUÉ dans un panneau (le cas d'usage « éditeur + aperçu »
      // dans une colonne redimensionnable) verrait sinon les panneaux
      // de son enfant comme les siens.
      _panels() {
        if (!this._group) return [];
        return Array.prototype.slice.call(
          this._group.querySelectorAll(":scope > [data-bz-rz-panel]")
        );
      },
      _px(el) {
        const r = el.getBoundingClientRect();
        return this._vertical ? r.height : r.width;
      },

      // ── L'état → la mise en page ─────────────────────────────────
      // Appelé depuis un ``bz-effect`` du root : lire ``_read()``
      // inscrit la dépendance, donc un écrivain EXTERNE (une binding
      // pilotée ailleurs, un `.set([…])`, une restauration depuis
      // localStorage au boot) repose les panneaux tout seul.
      //
      // C'est aussi ce qui rend l'anti-FOUC gratuit : le root porte un
      // ``bz-data``, donc il reste ``visibility:hidden`` jusqu'à
      // ``html.bz-ready`` (cf. ``render/shell.py`` § _ANTI_FLASH_STYLE),
      // et le boot hydrate le store depuis localStorage AVANT le scan
      // qui exécute cet effet. Les tailles mémorisées sont donc en place
      // au premier pixel peint — aucun script pré-paint à écrire.
      _apply() {
        // Les panneaux d'abord, leur COMPTE ensuite passé à ``_weights``
        // : sans ça les deux méthodes lancent chacune le même
        // ``querySelectorAll``, à chaque tick de l'effet.
        const panels = this._panels();
        const sizes = this._weights(panels.length);
        for (let i = 0; i < panels.length; i++) {
          const w = sizes[i];
          if (w === undefined) continue;
          // Le style INLINE et pas une classe : la valeur est continue
          // (un utilisateur s'arrête où il veut), donc aucune classe
          // Tailwind ne peut l'exprimer — et une classe assemblée
          // n'existerait pas dans le CSS compilé de prod.
          panels[i].style.flexGrow = String(w);
        }
        // ``aria-valuenow`` est reposé ICI, dans l'unique passe
        // réactive, et pas seulement dans les gestes. C'est ce qui rend
        // les QUATRE chemins d'écriture corrects par construction :
        // pointeur, clavier, `.set()` / `.reset()`, et une binding
        // pilotée ailleurs. Recopié dans chaque geste, il ne couvrait
        // que les deux premiers — `.set([20, 80])` laissait un lecteur
        // d'écran sur la valeur du premier rendu.
        if (this._group) {
          const handles = this._group.querySelectorAll(
            ":scope > [data-bz-rz-handle]"
          );
          for (let i = 0; i < handles.length; i++) {
            this._announce(handles[i], sizes[i]);
          }
        }
      },

      // Le tableau de poids **normalisé à 100**. Un panneau ajouté par
      // un morph sans que ``sizes`` suive (une liste de panneaux qui
      // vient des données) recevrait sinon ``undefined`` : il tombe à
      // part égale plutôt que de disparaître.
      //
      // ⚠️ **La normalisation n'est pas cosmétique, et l'oublier ici a
      // rendu le composant inerte.** ``_mins`` voyage en POINTS DE
      // POURCENTAGE ; si les poids restent bruts, les deux échelles ne
      // se parlent plus. Mesuré : ``sizes=[1, 3]`` (une écriture
      // documentée — c'est le RAPPORT qui compte) avec
      // ``min_size=15`` donne ``pair = 4``, ``lo = 15``, donc
      // ``hi < lo`` à chaque frame, donc une poignée qui ne bouge
      // JAMAIS — sans erreur, sans rien dans la console. En mode local
      // le défaut était invisible parce que le ``bz-data`` semé par le
      // serveur est déjà normalisé ; il n'apparaissait qu'en mode
      // binding, celui-là même que le composant met en avant pour
      // ``persist="local"``.
      //
      // MIROIR EXACT de ``normalize_weights`` (``resizable.py``), gaté
      // par ``tests/runtime_js/test_resizable_mirrors_python.py``, qui
      // fait tourner les deux moitiés sur la même table.
      //
      // ``count`` est optionnel : l'appelant qui vient DÉJÀ de compter
      // les panneaux le passe (``_apply``), les autres le laissent
      // dériver. ⚠️ La lecture de ``_read()`` reste la PREMIÈRE ligne :
      // c'est elle qui inscrit la dépendance réactive de l'effet, et la
      // déplacer après un retour anticipé la perdrait en silence.
      _weights(count) {
        const raw = this._read();
        const n = count === undefined ? this._panels().length : count;
        if (n <= 0) return [];
        const share = 100 / n;
        const out = [];
        let total = 0;
        for (let i = 0; i < n; i++) {
          const v = Array.isArray(raw) ? Number(raw[i]) : NaN;
          const w = isFinite(v) && v >= 0 ? v : share;
          out.push(w);
          total += w;
        }
        if (total <= 0) return out.map(() => Math.round(share * 100) / 100);
        return out.map((w) => Math.round((w * 100) / total * 100) / 100);
      },

      _min(i) {
        const m = Array.isArray(this._mins) ? Number(this._mins[i]) : 0;
        return isFinite(m) && m > 0 ? m : 0;
      },

      // Le PLAFOND, en points de pourcentage. ``100`` est la valeur
      // neutre et non une sentinelle : un panneau qui peut prendre toute
      // la place n'est pas borné. Ajouté le 2026-08-23 — ``_min`` vivait
      // seul, ce qui était une asymétrie et pas une décision.
      _max(i) {
        const m = Array.isArray(this._maxs) ? Number(this._maxs[i]) : 100;
        return isFinite(m) && m > 0 && m <= 100 ? m : 100;
      },

      // ── Le geste ─────────────────────────────────────────────────
      // Aucun seuil d'activation, contrairement au node-DnD : une
      // poignée de splitter n'a pas de « clic » concurrent à préserver
      // (elle ne fait rien d'autre), et elle est déjà une cible dédiée.
      // Le seuil du DnD existe pour que cliquer une CARTE reste un clic ;
      // ici il ne protégerait rien et ajouterait une latence au premier
      // pixel.
      _start(e, i) {
        const panels = this._panels();
        const a = panels[i];
        const b = panels[i + 1];
        if (!a || !b) return;
        const totalPx = panels.reduce((s, p) => s + this._px(p), 0);
        if (!totalPx) return;
        const weights = this._weights(panels.length);
        this._drag = {
          i: i,
          from: this._vertical ? e.clientY : e.clientX,
          // Le facteur px → poids est figé au DÉBUT du geste, et c'est
          // volontaire : la somme des poids ne bouge pas pendant qu'on
          // tire (on ne fait que la répartir), donc le rapport reste
          // juste jusqu'au relâchement.
          factor: weights.reduce((s, w) => s + w, 0) / totalPx,
          // Le poids du panneau gauche AU DÉBUT du geste : c'est la base
          // à laquelle le delta s'ajoute, donc elle ne doit pas suivre
          // les valeurs intermédiaires (sinon le déplacement se cumule
          // et le pointeur « glisse » sous la poignée). Le poids droit,
          // lui, se déduit de la paire — inutile de le retenir.
          a: weights[i],
          sizes: weights,
          // Les deux panneaux et la poignée sont RETENUS ici, pas
          // re-cherchés à chaque frame : ``_move`` tourne à la cadence
          // du pointeur, et rien de tout ça ne peut changer pendant un
          // geste. Sans cette capture, chaque frame relançait DEUX
          // ``querySelectorAll`` (les panneaux, puis les poignées pour
          // ``aria-valuenow``) pour atteindre trois nœuds connus.
          aEl: a,
          bEl: b,
          handle: e.currentTarget,
        };
        // Capturer sur la POIGNÉE : le curseur sort de sa boîte dès le
        // premier pixel (elle fait quelques points de large), et sans
        // capture le geste s'arrêterait là.
        $bz.helpers.capturePointer(e.currentTarget, e);
      },

      // Répartir ``want`` sur la paire ``i`` / ``i+1``, en place, en
      // respectant les deux minimums. Rend ``false`` quand la paire est
      // FIGÉE — le cas où les deux minimums ne tiennent pas dedans (60 +
      // 60 sur 100) : on préfère ne rien bouger plutôt que de violer
      // l'un des deux au motif que l'autre l'exige aussi.
      //
      // Une seule copie pour le pointeur ET le clavier : c'est la même
      // arithmétique, seule la provenance de ``want`` diffère (un delta
      // de pointeur, ou un pas de flèche). Écrite deux fois, elle se
      // serait corrigée une fois sur deux.
      _pair(sizes, i, want) {
        const pair = sizes[i] + sizes[i + 1];
        // Les quatre contraintes se croisent : le plancher de GAUCHE et
        // le plafond de DROITE poussent la poignée dans le même sens
        // (vers la droite), les deux autres dans l'autre. D'où le
        // ``max`` sur les planchers et le ``min`` sur les plafonds,
        // exprimés dans la même unité — la taille du panneau de gauche.
        const lo = Math.max(this._min(i), pair - this._max(i + 1));
        const hi = Math.min(pair - this._min(i + 1), this._max(i));
        // Paire FIGÉE : les contraintes ne tiennent pas ensemble (60 +
        // 60 sur 100, ou un plafond sous un plancher). On préfère ne
        // rien bouger plutôt que d'en violer une au motif qu'une autre
        // l'exige.
        if (hi < lo) return false;
        sizes[i] = Math.max(lo, Math.min(hi, want));
        sizes[i + 1] = pair - sizes[i];
        return true;
      },

      // Publier : c'est ici, et seulement ici, que l'état sort du geste.
      // L'arrondi à deux décimales évite de persister des flottants à
      // dix-sept chiffres dans localStorage.
      _publish(sizes) {
        this._write(sizes.map((w) => Math.round(w * 100) / 100));
      },

      _move(e) {
        const d = this._drag;
        if (!d) return;
        const delta =
          ((this._vertical ? e.clientY : e.clientX) - d.from) * d.factor;
        if (!this._pair(d.sizes, d.i, d.a + delta)) return;
        // Écriture DIRECTE, sans passer par l'état : voir l'en-tête du
        // fichier. La publication a lieu une fois, au relâchement.
        d.aEl.style.flexGrow = String(d.sizes[d.i]);
        d.bEl.style.flexGrow = String(d.sizes[d.i + 1]);
        this._announce(d.handle, d.sizes[d.i]);
      },

      _end(e) {
        const d = this._drag;
        this._drag = null;
        if (!d) return;
        $bz.helpers.releasePointer(d.handle, e);
        this._publish(d.sizes);
      },

      // ── a11y ─────────────────────────────────────────────────────
      // ``aria-valuenow`` dit « le panneau qui me précède occupe N % ».
      // Le serveur ne le rend qu'une fois, en statique — la poignée
      // n'est pas un composant, elle n'a pas de prop réactive à lier —
      // donc c'est le JS qui le tient à jour.
      //
      // **Un seul auteur pour l'état publié** : ``_apply``, la passe
      // réactive. Tout ce qui écrit l'état y repasse, donc les quatre
      // chemins sont couverts sans qu'aucun ait à y penser. ``_move``
      // l'appelle EN PLUS, et uniquement parce qu'il est le seul à ne
      // rien publier avant le relâchement — sans ça un lecteur d'écran
      // annoncerait la valeur d'avant pendant toute la durée du drag.
      _announce(handle, value) {
        if (handle && value !== undefined) {
          handle.setAttribute("aria-valuenow", String(Math.round(value)));
        }
      },

      // ── Le repli ─────────────────────────────────────────────────
      // Ranger le panneau ``i`` en donnant sa place à ``j``, son voisin
      // d'en face. Re-jouer le geste le restaure.
      //
      // ⚠️ **Le repli PASSE OUTRE ``min_size``, et c'est le but.** Il ne
      // passe donc PAS par ``_pair``, qui existe pour empêcher qu'on
      // franchisse un minimum en TIRANT. Le minimum dit « ne me réduis
      // pas par accident » ; le repli est un geste explicite qui dit
      // « range-le ». Sans cette sortie, ``min_size=20`` rendrait un
      // panneau repliable non repliable, et il faudrait un second
      // vocabulaire pour dire la même chose. VS Code et shadcn font
      // pareil.
      //
      // ``_folded`` retient la taille d'avant, par index. Elle vit dans
      // le scope — donc elle survit à un morph, comme le reste de
      // l'état du composant — et pas côté serveur, qui n'a aucune idée
      // de ce que quelqu'un a rangé il y a trois secondes.
      _fold(i, j) {
        const sizes = this._weights();
        if (sizes[i] === undefined || sizes[j] === undefined) return;
        const memo = this._folded || (this._folded = {});
        const back = memo[i];
        const pair = sizes[i] + sizes[j];

        if (back !== undefined) {
          // Restaurer. Le voisin garde son propre plancher : rendre au
          // panneau rangé plus que la paire ne contient l'écraserait.
          const want = Math.min(back, Math.max(0, pair - this._min(j)));
          sizes[i] = want;
          sizes[j] = pair - want;
          delete memo[i];
        } else if (sizes[i] <= 0.01) {
          // Replié SANS souvenir : le cas d'un partage restauré depuis
          // localStorage, où un panneau était à zéro avant le F5. Sans
          // cette branche, double-cliquer ne ferait rien du tout — le
          // panneau resterait rangé pour toujours. Il revient à son
          // plancher, ou à part égale s'il n'en a pas.
          const want = Math.min(
            this._min(i) || 100 / Math.max(1, this._panels().length),
            Math.max(0, pair - this._min(j))
          );
          sizes[i] = want;
          sizes[j] = pair - want;
        } else {
          memo[i] = sizes[i];
          sizes[j] = pair;
          sizes[i] = 0;
        }
        this._publish(sizes);
      },

      // ── Clavier ──────────────────────────────────────────────────
      // La poignée est un ``role="separator"`` focusable : les flèches
      // la déplacent, comme un slider. Le pas est en points de
      // pourcentage, donc indépendant de la largeur du groupe.
      _key(e, i, fold) {
        const key = e.key;
        // ``Entrée`` replie, quand la poignée touche un panneau
        // repliable. C'est le jumeau clavier du double-clic, et le motif
        // ARIA « window splitter » le prescrit : une poignée focusable
        // dont la seule commande de repli serait un geste souris n'a pas
        // de repli du tout pour qui n'a pas de souris.
        if (key === "Enter" && Array.isArray(fold)) {
          e.preventDefault();
          this._fold(fold[0], fold[1]);
          return;
        }
        const back = this._vertical ? "ArrowUp" : "ArrowLeft";
        const fwd = this._vertical ? "ArrowDown" : "ArrowRight";
        if (key !== back && key !== fwd) return;
        e.preventDefault();
        const sizes = this._weights();
        const step = key === back ? -KEY_STEP : KEY_STEP;
        // Pas de ``_announce`` ici : ``_publish`` relance ``_apply``,
        // qui repose tous les ``aria-valuenow``. L'appeler EN PLUS
        // donnerait deux auteurs à la même valeur.
        if (this._pair(sizes, i, sizes[i] + step)) this._publish(sizes);
      },

      // ── Impératif ────────────────────────────────────────────────
      set(v) {
        if (Array.isArray(v)) this._write(v);
      },
      // Revenir au partage égal. Une méthode et pas un « re-set des
      // tailles initiales » : le serveur ne rend le composant qu'une
      // fois, donc « initial » n'a pas de sens stable une fois que
      // l'utilisateur a tiré une poignée — alors que « à parts égales »
      // est vrai à tout moment.
      reset() {
        const n = this._panels().length;
        if (!n) return;
        this._write(new Array(n).fill(Math.round((100 / n) * 100) / 100));
      },
    },
  };
})();


/* 21_signature_pad.js — scope partagé du composant SignaturePad.
 *
 * **Le premier et le seul `<canvas>` du dépôt** (vérifié : zéro autre
 * occurrence, les charts sont en SVG). Tout ce qui suit découle de deux
 * propriétés du canvas que le reste du framework n'a jamais eu à gérer :
 * il n'a aucune taille intrinsèque, et **le redimensionner l'efface**.
 *
 * ── Troisième membre de la famille pointer-drag ───────────────────────
 *   - `12_slider.js`      = pointeur → une VALEUR sur une échelle ;
 *   - `20_resizable.js`   = pointeur → une DIMENSION ;
 *   - ici                 = pointeur → un TRACÉ.
 * Rien à voir avec le node-DnD de `19_dnd.js`. La capture de pointeur
 * passe par `$bz.helpers.capturePointer`, extraite le 2026-08-13 en
 * livrant `resizable` — ce fichier est son premier appelant neuf.
 *
 *   bz-data="{...$bz.signaturePad.scope, value: '', _canvas: null,
 *             _strokes: [], _drawing: null, _base: null,
 *             _read(){…}, _write(v){…}}"
 *
 * ── Pourquoi on garde les POINTS, alors qu'il n'y a pas d'undo ────────
 * Ce n'est pas pour annuler — l'API n'expose que `.clear()`, une
 * signature se refait et ne se retouche pas. C'est parce qu'un canvas
 * **perd son contenu à chaque changement de taille**, et qu'un pad dans
 * un formulaire responsive en change pour de vrai : un téléphone qu'on
 * tourne, un panneau qu'on ouvre, un `resizable` qu'on tire. Sans les
 * points, la signature disparaît à la rotation. L'alternative — relire
 * le bitmap et le redessiner à l'échelle — dégrade à chaque passe.
 *
 * ── La valeur est VIDE tant que rien n'est tracé ──────────────────────
 * Un canvas neuf rend un PNG parfaitement valide : un rectangle blanc.
 * Le publier ferait passer « pas encore signé » pour « signé », côté
 * serveur, sans que rien ne semble faux. Zéro trait ⇒ chaîne vide.
 */
(function () {
  "use strict";
  const $bz = (window.$bz = window.$bz || {});

  //: Épaisseur du trait, en pixels CSS. Une constante et pas un prop :
  //: une signature n'a qu'une graisse qui marche, et la rendre réglable
  //: n'ajouterait aucun pouvoir (memory `project_api_opinionation_thesis`).
  const LINE_WIDTH = 2;

  $bz.signaturePad = {
    scope: {
      // ── Le canvas et sa taille ───────────────────────────────────
      // ⚠️ Redimensionner un canvas l'EFFACE, et lui donner une taille
      // en pixels CSS ne suffit pas : sans le facteur de densité, le
      // trait est flou sur tout écran retina — c'est-à-dire sur tous
      // les téléphones, l'environnement de test de ce dépôt.
      _resize() {
        const c = this._canvas;
        if (!c) return;
        const box = c.getBoundingClientRect();
        if (!box.width || !box.height) return;
        const dpr = window.devicePixelRatio || 1;
        const w = Math.round(box.width * dpr);
        const h = Math.round(box.height * dpr);
        // Ne rien faire quand rien n'a bougé : une écriture sur
        // ``canvas.width`` efface le contenu MÊME si la valeur est
        // identique. L'observer rapporte au premier branchement, donc
        // sans cette garde le pad s'effacerait à chaque rescan.
        if (c.width === w && c.height === h) return;
        c.width = w;
        c.height = h;
        const ctx = c.getContext("2d");
        ctx.scale(dpr, dpr);
        this._redraw();
      },

      // Rebrancher l'observer à chaque rescan plutôt qu'au ``bz-init``,
      // et le ranger sur le NŒUD : ``bz-init`` est one-shot par nœud et
      // idiomorph morphe en place, donc un observer installé là ne
      // reverrait jamais un canvas remplacé. Même choix, même raison que
      // ``_observeGeom`` du Carousel.
      _observe() {
        const c = this._canvas;
        if (!c) return;
        if (c._bzPadRo) c._bzPadRo.disconnect();
        const self = this;
        const ro = new ResizeObserver(function () {
          self._resize();
        });
        ro.observe(c);
        c._bzPadRo = ro;
        this._resize();
        this._hydrate();
      },

      // ── La signature DÉJÀ LÀ ─────────────────────────────────────
      // Un dossier rouvert rend sa data-URL au SSR. Sans ce chargement,
      // le cadre s'affichait VIDE — et sans invite, puisque le serveur
      // avait déjà posé ``data-empty="false"``. Le composant annonçait
      // donc « il y a une signature » en n'en montrant aucune.
      //
      // L'image chargée devient une COUCHE DE FOND, distincte des
      // points : ``_redraw`` la peint d'abord, les traits par-dessus.
      // C'est ce qui la fait survivre au redimensionnement comme le
      // reste — sans ça elle disparaîtrait au premier changement de
      // taille, avec le canvas qu'on efface pour le redimensionner.
      //
      // Une seule fois par NŒUD (``_bzHydrated``), et pas dans un effet
      // réactif : ``_publish`` écrit dans le même état, donc un effet
      // qui le lit se rechargerait lui-même à chaque trait. Après le
      // boot, c'est le canvas qui fait foi. Propriété de nœud et pas
      // champ de scope, pour la même raison que ``_bzPadRo`` — une
      // durée de vie qui est celle du canvas.
      _hydrate() {
        const c = this._canvas;
        if (!c || c._bzHydrated) return;
        c._bzHydrated = true;
        const src = this._read();
        if (!src) return;
        const img = new Image();
        const self = this;
        img.onload = function () {
          self._base = img;
          self._redraw();
          self._empty(false);
        };
        img.src = src;
      },

      // ── Le tracé ─────────────────────────────────────────────────
      // L'encre est LUE sur l'élément (``color`` calculée), jamais
      // configurée : le thème décide, et la valeur suit le mode sombre
      // toute seule. Un prop ``pen_color`` aurait figé une couleur qui
      // devient invisible sur l'autre fond.
      _ink() {
        return getComputedStyle(this._canvas).color || "#000";
      },
      _redraw() {
        const c = this._canvas;
        if (!c) return;
        const ctx = c.getContext("2d");
        const dpr = window.devicePixelRatio || 1;
        const w = c.width / dpr;
        const h = c.height / dpr;
        ctx.clearRect(0, 0, w, h);
        // La signature déjà là, sous les traits neufs. Étirée à la
        // boîte courante : une image matricielle n'a pas d'autre
        // option, et le cadre d'origine n'est pas connu — c'est le même
        // compromis que n'importe quel rendu raster redimensionné.
        if (this._base) {
          try {
            ctx.drawImage(this._base, 0, 0, w, h);
          } catch (err) {
            /* image cassée / cross-origin : on garde les traits */
          }
        }
        ctx.lineWidth = LINE_WIDTH;
        ctx.lineCap = "round";
        ctx.lineJoin = "round";
        ctx.strokeStyle = this._ink();
        for (const stroke of this._strokes) {
          if (stroke.length < 2) {
            // Un point isolé : un tap sans mouvement doit laisser une
            // marque, sinon signer d'un point ne produit rien.
            if (stroke.length === 1) {
              ctx.beginPath();
              ctx.arc(
                stroke[0][0], stroke[0][1], LINE_WIDTH / 2, 0, Math.PI * 2
              );
              ctx.fillStyle = this._ink();
              ctx.fill();
            }
            continue;
          }
          ctx.beginPath();
          ctx.moveTo(stroke[0][0], stroke[0][1]);
          for (let i = 1; i < stroke.length; i++) {
            ctx.lineTo(stroke[i][0], stroke[i][1]);
          }
          ctx.stroke();
        }
      },

      _at(e) {
        const r = this._canvas.getBoundingClientRect();
        return [e.clientX - r.left, e.clientY - r.top];
      },

      _start(e) {
        if (this._locked()) return;
        // Empêche le navigateur de comprendre le geste comme une
        // sélection de texte ou un défilement. ``touch-none`` sur le
        // canvas couvre le défilement ; ceci couvre le reste.
        e.preventDefault();
        $bz.helpers.capturePointer(this._canvas, e);
        this._drawing = [this._at(e)];
        this._strokes.push(this._drawing);
        this._redraw();
        this._empty(false);
      },

      _draw(e) {
        if (!this._drawing) return;
        this._drawing.push(this._at(e));
        this._redraw();
      },

      _end(e) {
        if (!this._drawing) return;
        $bz.helpers.releasePointer(this._canvas, e);
        this._drawing = null;
        // Publier au LEVER du stylo, pas à chaque point : un PNG fait
        // des dizaines de kilo-octets, et l'émettre par frame ferait
        // partir autant de POST si un ``on_change`` est câblé. Même
        // règle que le relâchement de poignée du Resizable.
        this._publish();
      },

      // ── La valeur ────────────────────────────────────────────────
      // Écrite dans l'ÉTAT (``_write``), pas sur le porteur : c'est le
      // ``bz-attr:value`` du porteur qui la reporte dans le DOM, et son
      // ``bz-effect`` qui en tire le ``change``. Un seul auteur, la même
      // mécanique que Slider / Carousel / Resizable — écrire les deux
      // ferait diverger le champ de formulaire de l'état dès qu'un
      // écrivain externe passe par le second.
      _publish() {
        // ``_base`` compte autant que les traits : un dossier rouvert
        // puis soumis sans y toucher ne doit pas EFFACER la signature
        // qu'il portait.
        const inked = this._strokes.length || this._base;
        this._write(inked ? this._canvas.toDataURL("image/png") : "");
      },

      // Le marqueur que le thème lit pour montrer / cacher l'invite.
      // Un attribut et pas une classe : ``data-[empty=true]:`` est le
      // variant Tailwind que le reste du dépôt utilise pour les états
      // pilotés par le JS.
      _empty(value) {
        if (this._canvas && this._canvas.parentElement) {
          this._canvas.parentElement.setAttribute(
            "data-empty", value ? "true" : "false"
          );
        }
      },

      _locked() {
        return !!(
          this._canvas && this._canvas.hasAttribute("data-bz-pad-locked")
        );
      },

      // ── Impératif ────────────────────────────────────────────────
      // ``.clear()`` et rien d'autre : une signature se refait, elle ne
      // se retouche pas. Les points gardés en mémoire servent au
      // redimensionnement (cf. l'en-tête), pas à un undo.
      clear() {
        this._strokes.length = 0;
        // La couche de fond part AVEC les traits : « effacer » veut
        // dire un cadre vide, pas « revenir à la signature d'avant ».
        this._base = null;
        this._drawing = null;
        this._redraw();
        this._empty(true);
        this._publish();
      },
    },
  };
})();


/* 22_verbs.js — la moitié CLIENT des verbes de `bretzel.runtime.verbs`.
 *
 * Un verbe est une action du NAVIGATEUR déclenchée depuis un `on_*=` :
 *
 *     ui.button("Copier", on_click=bretzel.copy(state.api_key))
 *
 * Il se branche dans le slot qui accepte déjà une CHAÎNE de source
 * client — le même que `dialog.open()` — donc il n'ajoute aucune
 * plomberie : ni requête, ni directive, ni scope.
 *
 * Seul `copy` a besoin de ce fichier. `print` et `fullscreen` tiennent
 * en une expression que Python écrit en toutes lettres ; les mettre ici
 * aurait ajouté une indirection sans rien garder de commun.
 *
 * ⚠️ Pourquoi `copy` n'est PAS un `navigator.clipboard.writeText` nu
 * ---------------------------------------------------------------------
 * L'API Presse-papiers exige un **contexte sécurisé**. `https://` et
 * `http://localhost` en sont ; `http://192.168.1.20:8000` n'en est PAS.
 * Or c'est très exactement la façon dont un outil interne se sert — le
 * public que Bretzel vise. Sur ce chemin-là `navigator.clipboard` vaut
 * `undefined`, et un appel nu lèverait un TypeError : le bouton ne
 * ferait rien, sans un mot.
 *
 * D'où le repli sur `document.execCommand('copy')`. Il est déprécié et
 * il marche partout, y compris hors contexte sécurisé — c'est le seul
 * chemin qui existe là-bas, donc « déprécié » n'est pas un argument
 * contre lui, c'est un argument pour ne pas s'en servir en premier.
 */
(function () {
  "use strict";
  const $bz = (window.$bz = window.$bz || {});

  /* Le repli hors contexte sécurisé.
   *
   * Le `<textarea>` est posé hors écran plutôt que `display:none` : un
   * élément non rendu n'est pas sélectionnable, donc la copie échouerait
   * silencieusement. `readOnly` empêche le clavier virtuel de s'ouvrir
   * sur mobile, et `position:fixed` évite de faire défiler la page vers
   * un champ que personne ne doit voir.
   */
  function viaTextarea(text) {
    const ta = document.createElement("textarea");
    ta.value = text;
    ta.setAttribute("readonly", "");
    ta.style.cssText = "position:fixed;top:0;left:-9999px;opacity:0";
    document.body.appendChild(ta);
    const selection = document.getSelection();
    const previous = selection && selection.rangeCount > 0
      ? selection.getRangeAt(0) : null;
    ta.select();
    let ok = false;
    try {
      ok = document.execCommand("copy");
    } catch (e) {
      ok = false;
    }
    document.body.removeChild(ta);
    // Rendre la sélection de l'utilisateur : `select()` l'a écrasée, et
    // perdre son surlignage parce qu'on a copié autre chose se voit.
    if (previous && selection) {
      selection.removeAllRanges();
      selection.addRange(previous);
    }
    return ok;
  }

  $bz.verbs = {
    /* Partager — la feuille native, ou le presse-papiers.
     *
     * ⚠️ `navigator.share` est **undefined** sur le Chromium de bureau
     * (mesuré le 2026-09-02 : `typeof navigator.share === "undefined"`).
     * L'absence n'est donc pas un cas limite, c'est le cas NORMAL sur la
     * machine où les utilisateurs de Bretzel développent.
     *
     * Ne rien faire là-dedans donnerait un bouton « Partager » inerte
     * pour la majorité — exactement ce que ce dépôt refuse ailleurs (cf.
     * le refus de `tracks=` sur `ui.audio`, qui aurait promis des
     * sous-titres et livré un attribut). Le repli COPIE donc l'URL : le
     * bouton fait toujours quelque chose d'utile, et c'est un contrat,
     * pas un accident.
     */
    share(data) {
      const charge = data || {};
      if (!charge.url) charge.url = window.location.href;
      if (navigator.share) {
        // Un refus de l'utilisateur (il ferme la feuille) rejette la
        // promesse. Ce n'est pas une erreur de l'app : on ne retombe PAS
        // sur la copie, sinon annuler un partage copierait dans son dos.
        return navigator.share(charge).then(
          function () { return "shared"; },
          function () { return "cancelled"; }
        );
      }
      return $bz.verbs.copy(charge.url).then(function (ok) {
        return ok ? "copied" : "failed";
      });
    },

    /* Vibrer. `navigator.vibrate` EXISTE partout (mesuré : `function`
     * sur le Chromium de bureau) et ne fait rien sans matériel — il n'y a
     * donc aucune absence à gérer, contrairement à `share`.
     */
    vibrate(motif) {
      return navigator.vibrate ? navigator.vibrate(motif) : false;
    },

    /* Copier `value` dans le presse-papiers. Rend une promesse de
     * booléen — jamais une exception : un verbe est appelé depuis un
     * `on_*=`, où personne n'attrape rien, donc une rejection
     * remonterait en `unhandledrejection` dans la console de l'app.
     */
    copy(value) {
      const text = value === null || value === undefined ? "" : String(value);
      if (window.isSecureContext && navigator.clipboard) {
        return navigator.clipboard.writeText(text).then(
          function () { return true; },
          // Un refus reste possible EN contexte sécurisé (permission
          // révoquée, document sans focus). Le repli est alors la
          // dernière chance, pas un chemin mort.
          function () { return viaTextarea(text); }
        );
      }
      return Promise.resolve(viaTextarea(text));
    },
  };
})();


/* 23_diagram.js — la mise en évidence des voisins, dans `ui.diagram`.
 *
 * Le graphe est PLACÉ côté serveur : positions, couches, tracés, tout
 * arrive calculé. Ce fichier ne place rien. Il ne fait qu'une chose, et
 * elle est purement locale : quand on désigne un nœud, tout ce qui n'est
 * pas relié s'estompe.
 *
 * Pourquoi ça ne peut pas être un aller-retour
 * ---------------------------------------------
 * Éclairer ne change pas QUELS nœuds existent, seulement lesquels sont
 * en avant. Passer par le serveur pour ça coûterait une requête et un
 * morph par désignation, pour un résultat que le navigateur connaît
 * déjà : l'adjacence est cuite dans le DOM au rendu.
 *
 * Ce que le serveur garde, lui, c'est le RESSERREMENT (`focus=`) — là
 * les nœuds dessinés changent, donc le placement change, donc il faut
 * re-rendre. Les deux gestes se ressemblent à l'écran et n'ont pas le
 * même coût ; c'est la seule raison pour laquelle ils sont séparés.
 *
 * Pourquoi un slab plutôt qu'une expression par nœud
 * ---------------------------------------------------
 * Même raison que 16_accordion : sérialiser ces corps de méthode dans le
 * `bz-data` de chaque nœud ferait 120 octets × N. Ici seule l'ADJACENCE
 * voyage — un tableau de clés par nœud, la seule chose qui diffère
 * réellement d'un nœud à l'autre.
 *
 * ⚠️ Des MÉTHODES, jamais des getters : `scope.absorb` invoque chaque clé
 * à l'enregistrement et figerait un getter sur sa première valeur
 * (cf. traps.md).
 */
(function () {
  "use strict";
  const $bz = (window.$bz = window.$bz || {});

  $bz.diagram = {
    scope: {
      /* La sélection — LUE ET ÉCRITE par `_read` / `_write`.
       *
       * Ces deux-là portent l'indirection : les mêmes méthodes servent
       * le champ local `value` (aucun binding) et la cellule du magasin
       * (`value=` lié à un `ClientState`). C'est l'idiome de `tree` et
       * de `toggle_group` — sans lui, chaque méthode devrait tester en
       * quel mode elle tourne.
       *
       * Pas de getter : `scope.absorb` invoque chaque clé une fois à
       * l'enregistrement et le figerait sur sa première valeur.
       */
      _read() {
        return this.value;
      },
      _write(v) {
        this.value = v;
      },

      /* Désigner `key`, dont `adj` liste les voisins (lui compris).
       *
       * Recliquer le nœud déjà désigné éteint. C'est la seule sortie au
       * clavier et au doigt — sans elle on reste éclairé sans savoir
       * comment revenir, et il n'y a pas de survol pour s'en sortir sur
       * un écran tactile. */
      light(key) {
        this._write(
          String(this._read() || "") === String(key) ? "" : String(key)
        );
      },

      /* Ce nœud doit-il rester en avant ?
       *
       * DÉRIVÉ de la sélection, jamais stocké. La première version
       * gardait un tableau `lit` que `light()` remplissait — et ce
       * tableau ne bougeait pas quand la sélection changeait depuis
       * DEHORS (un `select` lié au même `ClientState`, un
       * `state.node.set(...)`). Le magasin suivait, l'écran non :
       * mesuré à `dim = 0` là où un clic donnait 3.
       *
       * `adj` est l'adjacence du nœud, cuite par le serveur dans son
       * `bz-class`. On teste donc « le sélectionné est-il MON voisin »
       * plutôt que l'inverse — c'est le même prédicat, et il ne demande
       * aucun état.
       */
      isLit(key, adj) {
        const sel = String(this._read() || "");
        if (!sel) return true;
        if (sel === String(key)) return true;
        return (adj || []).indexOf(sel) !== -1;
      },

      /* Tout rallumer. */
      reset() {
        this._write("");
      },

      /* Armer le clic-hors-du-diagramme, une seule fois.
       *
       * Désigner un nœud est un geste de lecture : on doit pouvoir en
       * sortir en cliquant n'importe où, pas seulement en retrouvant le
       * nœud qu'on avait désigné. Sans ça on reste éclairé, et sur un
       * écran tactile il n'y a même pas de survol pour s'en douter.
       *
       * `$bz.helpers.clickOutside` plutôt qu'un écouteur maison : c'est
       * lui que les overlays utilisent, il est en phase de CAPTURE (donc
       * un `stopPropagation` intérieur ne l'étouffe pas) et il rend son
       * désabonnement.
       *
       * Idempotent : `bz-effect` est réévalué après chaque morph, et
       * sans le drapeau on empilerait un écouteur par rafraîchissement.
       */
      arm(el) {
        if (!el || el._bzDiagramOff) return;
        const scope = this;
        el._bzDiagramOff = $bz.helpers.clickOutside(el, function () {
          scope.reset();
        });
      },

      /* Une arête reste en avant si elle TOUCHE le nœud désigné.
       *
       * « Incidente », et pas « ses deux extrémités sont éclairées » :
       * deux voisins d'un même nœud sont tous deux en avant, mais
       * l'arête qui les relie l'un à l'autre ne dit rien de ce qu'on a
       * désigné. La garder allumée remplissait l'écran de ce qu'on
       * cherchait justement à retirer. */
      isEdgeLit(a, b) {
        const sel = String(this._read() || "");
        return !sel || sel === a || sel === b;
      },
    },
  };
})();
