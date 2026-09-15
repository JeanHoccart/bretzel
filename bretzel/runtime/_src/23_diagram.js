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
