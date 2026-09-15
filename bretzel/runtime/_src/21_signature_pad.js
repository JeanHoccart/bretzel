/* 21_signature_pad.js — scope partagé du composant SignaturePad.
 *
 * **Le premier et le seul `<canvas>` du dépôt** (vérifié : zéro autre
 * occurrence, les charts sont en SVG). Tout ce qui suit découle de deux
 * propriétés du canvas que le reste du framework n'a jamais eu à gérer :
 * il n'a aucune taille intrinsèque, et **le redimensionner l'efface**.
 *
 * ── Troisième membre de la famille pointer-drag ───────────────────────
 *   - `12_slider.js`      = pointeur → une VALEUR sur une échelle ;
 *   - `20_resizable.js`   = pointeur → une DIMENSION ;
 *   - ici                 = pointeur → un TRACÉ.
 * Rien à voir avec le node-DnD de `19_dnd.js`. La capture de pointeur
 * passe par `$bz.helpers.capturePointer`, extraite le 2026-08-13 en
 * livrant `resizable` — ce fichier est son premier appelant neuf.
 *
 *   bz-data="{...$bz.signaturePad.scope, value: '', _canvas: null,
 *             _strokes: [], _drawing: null, _base: null,
 *             _read(){…}, _write(v){…}}"
 *
 * ── Pourquoi on garde les POINTS, alors qu'il n'y a pas d'undo ────────
 * Ce n'est pas pour annuler — l'API n'expose que `.clear()`, une
 * signature se refait et ne se retouche pas. C'est parce qu'un canvas
 * **perd son contenu à chaque changement de taille**, et qu'un pad dans
 * un formulaire responsive en change pour de vrai : un téléphone qu'on
 * tourne, un panneau qu'on ouvre, un `resizable` qu'on tire. Sans les
 * points, la signature disparaît à la rotation. L'alternative — relire
 * le bitmap et le redessiner à l'échelle — dégrade à chaque passe.
 *
 * ── La valeur est VIDE tant que rien n'est tracé ──────────────────────
 * Un canvas neuf rend un PNG parfaitement valide : un rectangle blanc.
 * Le publier ferait passer « pas encore signé » pour « signé », côté
 * serveur, sans que rien ne semble faux. Zéro trait ⇒ chaîne vide.
 */
(function () {
  "use strict";
  const $bz = (window.$bz = window.$bz || {});

  //: Épaisseur du trait, en pixels CSS. Une constante et pas un prop :
  //: une signature n'a qu'une graisse qui marche, et la rendre réglable
  //: n'ajouterait aucun pouvoir (memory `project_api_opinionation_thesis`).
  const LINE_WIDTH = 2;

  $bz.signaturePad = {
    scope: {
      // ── Le canvas et sa taille ───────────────────────────────────
      // ⚠️ Redimensionner un canvas l'EFFACE, et lui donner une taille
      // en pixels CSS ne suffit pas : sans le facteur de densité, le
      // trait est flou sur tout écran retina — c'est-à-dire sur tous
      // les téléphones, l'environnement de test de ce dépôt.
      _resize() {
        const c = this._canvas;
        if (!c) return;
        const box = c.getBoundingClientRect();
        if (!box.width || !box.height) return;
        const dpr = window.devicePixelRatio || 1;
        const w = Math.round(box.width * dpr);
        const h = Math.round(box.height * dpr);
        // Ne rien faire quand rien n'a bougé : une écriture sur
        // ``canvas.width`` efface le contenu MÊME si la valeur est
        // identique. L'observer rapporte au premier branchement, donc
        // sans cette garde le pad s'effacerait à chaque rescan.
        if (c.width === w && c.height === h) return;
        c.width = w;
        c.height = h;
        const ctx = c.getContext("2d");
        ctx.scale(dpr, dpr);
        this._redraw();
      },

      // Rebrancher l'observer à chaque rescan plutôt qu'au ``bz-init``,
      // et le ranger sur le NŒUD : ``bz-init`` est one-shot par nœud et
      // idiomorph morphe en place, donc un observer installé là ne
      // reverrait jamais un canvas remplacé. Même choix, même raison que
      // ``_observeGeom`` du Carousel.
      _observe() {
        const c = this._canvas;
        if (!c) return;
        if (c._bzPadRo) c._bzPadRo.disconnect();
        const self = this;
        const ro = new ResizeObserver(function () {
          self._resize();
        });
        ro.observe(c);
        c._bzPadRo = ro;
        this._resize();
        this._hydrate();
      },

      // ── La signature DÉJÀ LÀ ─────────────────────────────────────
      // Un dossier rouvert rend sa data-URL au SSR. Sans ce chargement,
      // le cadre s'affichait VIDE — et sans invite, puisque le serveur
      // avait déjà posé ``data-empty="false"``. Le composant annonçait
      // donc « il y a une signature » en n'en montrant aucune.
      //
      // L'image chargée devient une COUCHE DE FOND, distincte des
      // points : ``_redraw`` la peint d'abord, les traits par-dessus.
      // C'est ce qui la fait survivre au redimensionnement comme le
      // reste — sans ça elle disparaîtrait au premier changement de
      // taille, avec le canvas qu'on efface pour le redimensionner.
      //
      // Une seule fois par NŒUD (``_bzHydrated``), et pas dans un effet
      // réactif : ``_publish`` écrit dans le même état, donc un effet
      // qui le lit se rechargerait lui-même à chaque trait. Après le
      // boot, c'est le canvas qui fait foi. Propriété de nœud et pas
      // champ de scope, pour la même raison que ``_bzPadRo`` — une
      // durée de vie qui est celle du canvas.
      _hydrate() {
        const c = this._canvas;
        if (!c || c._bzHydrated) return;
        c._bzHydrated = true;
        const src = this._read();
        if (!src) return;
        const img = new Image();
        const self = this;
        img.onload = function () {
          self._base = img;
          self._redraw();
          self._empty(false);
        };
        img.src = src;
      },

      // ── Le tracé ─────────────────────────────────────────────────
      // L'encre est LUE sur l'élément (``color`` calculée), jamais
      // configurée : le thème décide, et la valeur suit le mode sombre
      // toute seule. Un prop ``pen_color`` aurait figé une couleur qui
      // devient invisible sur l'autre fond.
      _ink() {
        return getComputedStyle(this._canvas).color || "#000";
      },
      _redraw() {
        const c = this._canvas;
        if (!c) return;
        const ctx = c.getContext("2d");
        const dpr = window.devicePixelRatio || 1;
        const w = c.width / dpr;
        const h = c.height / dpr;
        ctx.clearRect(0, 0, w, h);
        // La signature déjà là, sous les traits neufs. Étirée à la
        // boîte courante : une image matricielle n'a pas d'autre
        // option, et le cadre d'origine n'est pas connu — c'est le même
        // compromis que n'importe quel rendu raster redimensionné.
        if (this._base) {
          try {
            ctx.drawImage(this._base, 0, 0, w, h);
          } catch (err) {
            /* image cassée / cross-origin : on garde les traits */
          }
        }
        ctx.lineWidth = LINE_WIDTH;
        ctx.lineCap = "round";
        ctx.lineJoin = "round";
        ctx.strokeStyle = this._ink();
        for (const stroke of this._strokes) {
          if (stroke.length < 2) {
            // Un point isolé : un tap sans mouvement doit laisser une
            // marque, sinon signer d'un point ne produit rien.
            if (stroke.length === 1) {
              ctx.beginPath();
              ctx.arc(
                stroke[0][0], stroke[0][1], LINE_WIDTH / 2, 0, Math.PI * 2
              );
              ctx.fillStyle = this._ink();
              ctx.fill();
            }
            continue;
          }
          ctx.beginPath();
          ctx.moveTo(stroke[0][0], stroke[0][1]);
          for (let i = 1; i < stroke.length; i++) {
            ctx.lineTo(stroke[i][0], stroke[i][1]);
          }
          ctx.stroke();
        }
      },

      _at(e) {
        const r = this._canvas.getBoundingClientRect();
        return [e.clientX - r.left, e.clientY - r.top];
      },

      _start(e) {
        if (this._locked()) return;
        // Empêche le navigateur de comprendre le geste comme une
        // sélection de texte ou un défilement. ``touch-none`` sur le
        // canvas couvre le défilement ; ceci couvre le reste.
        e.preventDefault();
        $bz.helpers.capturePointer(this._canvas, e);
        this._drawing = [this._at(e)];
        this._strokes.push(this._drawing);
        this._redraw();
        this._empty(false);
      },

      _draw(e) {
        if (!this._drawing) return;
        this._drawing.push(this._at(e));
        this._redraw();
      },

      _end(e) {
        if (!this._drawing) return;
        $bz.helpers.releasePointer(this._canvas, e);
        this._drawing = null;
        // Publier au LEVER du stylo, pas à chaque point : un PNG fait
        // des dizaines de kilo-octets, et l'émettre par frame ferait
        // partir autant de POST si un ``on_change`` est câblé. Même
        // règle que le relâchement de poignée du Resizable.
        this._publish();
      },

      // ── La valeur ────────────────────────────────────────────────
      // Écrite dans l'ÉTAT (``_write``), pas sur le porteur : c'est le
      // ``bz-attr:value`` du porteur qui la reporte dans le DOM, et son
      // ``bz-effect`` qui en tire le ``change``. Un seul auteur, la même
      // mécanique que Slider / Carousel / Resizable — écrire les deux
      // ferait diverger le champ de formulaire de l'état dès qu'un
      // écrivain externe passe par le second.
      _publish() {
        // ``_base`` compte autant que les traits : un dossier rouvert
        // puis soumis sans y toucher ne doit pas EFFACER la signature
        // qu'il portait.
        const inked = this._strokes.length || this._base;
        this._write(inked ? this._canvas.toDataURL("image/png") : "");
      },

      // Le marqueur que le thème lit pour montrer / cacher l'invite.
      // Un attribut et pas une classe : ``data-[empty=true]:`` est le
      // variant Tailwind que le reste du dépôt utilise pour les états
      // pilotés par le JS.
      _empty(value) {
        if (this._canvas && this._canvas.parentElement) {
          this._canvas.parentElement.setAttribute(
            "data-empty", value ? "true" : "false"
          );
        }
      },

      _locked() {
        return !!(
          this._canvas && this._canvas.hasAttribute("data-bz-pad-locked")
        );
      },

      // ── Impératif ────────────────────────────────────────────────
      // ``.clear()`` et rien d'autre : une signature se refait, elle ne
      // se retouche pas. Les points gardés en mémoire servent au
      // redimensionnement (cf. l'en-tête), pas à un undo.
      clear() {
        this._strokes.length = 0;
        // La couche de fond part AVEC les traits : « effacer » veut
        // dire un cadre vide, pas « revenir à la signature d'avant ».
        this._base = null;
        this._drawing = null;
        this._redraw();
        this._empty(true);
        this._publish();
      },
    },
  };
})();
