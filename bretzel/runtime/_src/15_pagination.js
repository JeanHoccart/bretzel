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
