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
  const ACTION_PREFIX = "__ROUTE_ACTION__/";

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
        typeof window.__SCREEN_SYNC_FN__ === "function" &&
        !window.__SCREEN_SYNC_FN__()
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
