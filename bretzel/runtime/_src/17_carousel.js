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
