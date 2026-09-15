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
