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
  $bz.version = "__PROTOCOL_VERSION__";

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
    // "__ENVELOPE_TAG__" is substituted at build time from protocol.py.
    const envelope = document.querySelector("__ENVELOPE_TAG__");
    if (envelope) {
      try {
        config = JSON.parse(envelope.textContent);
      } catch (e) {
        console.error("bz: malformed <__ENVELOPE_TAG__>", e);
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
