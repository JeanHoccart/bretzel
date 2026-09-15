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
