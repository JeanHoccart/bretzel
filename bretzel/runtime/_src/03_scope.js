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
