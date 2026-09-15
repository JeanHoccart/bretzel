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
