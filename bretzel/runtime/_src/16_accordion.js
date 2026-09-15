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
