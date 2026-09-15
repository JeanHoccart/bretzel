/* 19_dnd.js — le geste node-DnD partagé par `dropzone` / `draggable`.
 *
 * ⚠️ **Distinct du « drag » des deux autres familles du dépôt**, et le
 * §6 de la roadmap insiste parce que les confondre coûte cher :
 *   - `12_slider.js`      = pointer-drag (pointeur → valeur continue) ;
 *   - `08_file_upload.js` = DnD HTML5 natif (fichiers de l'OS, DataTransfer).
 * Ici c'est le troisième : **déplacer un nœud** d'une position à une autre.
 *
 * ── Pourquoi Pointer Events et pas l'API HTML5 `draggable` ────────────
 * L'API HTML5 ne déclenche tout simplement pas `dragstart` sur mobile.
 * Décision de cadrage figée : Pointer Events, comme le slider.
 *
 * ── Pourquoi la délégation au document ───────────────────────────────
 * Un listener par zone devrait se re-brancher après chaque morph, et un
 * `bz-init` qui re-tourne double-bind (le rescan du bridge dispose et
 * re-bind les directives). Un seul listener au document, qui retrouve sa
 * cible par `closest()`, est **insensible au morph** et ne garde aucun
 * état sur les nœuds — la contrainte que traps.md § « bz-class perdue
 * après un morph » a rendue non négociable.
 *
 * ── Pourquoi on déplace le VRAI nœud, sans clone ─────────────────────
 * Le réordonnancement est appliqué au DOM pendant le geste. Donc :
 *   1. l'aperçu est gratuit — pas de fantôme à positionner, pas de calcul
 *      de décalage pour les voisins, le navigateur reflow tout seul ;
 *   2. au drop, **l'ordre du DOM EST le résultat** — on lit les index au
 *      lieu de les calculer, donc l'aperçu ne peut pas mentir sur ce qui
 *      part au serveur ;
 *   3. c'est déjà l'optimiste. Le serveur re-rend, idiomorph réapparie par
 *      `bz-id` et le nœud déplacé est RÉUTILISÉ, pas recréé — mesuré, et
 *      gaté par `tests/runtime_js/test_morph_preserves_reordered_nodes.py`.
 *
 * ── Le snap-back d'un refus a besoin de code, contrairement à ce qui
 *    était écrit ici ──────────────────────────────────────────────────
 * Cette ligne a longtemps dit « un refus serveur = pas de mutation = le
 * morph remet l'item en place. Aucun code dédié ici. » C'était FAUX, et
 * la gate qui prétendait le prouver était vacante : le handler du
 * playground incrémente un compteur de refus, donc son état changeait,
 * donc la zone se re-rendait — le snap-back ne venait pas du refus mais
 * du compteur. Un handler qui refuse en ne mutant RIEN — le cas que
 * `Move` documente comme LA façon de refuser, et celui d'`examples/crm`
 * — ne fait re-rendre aucune zone : le serveur répond zéro octet et la
 * carte reste là où le doigt l'a lâchée. Mesuré le 2026-09-09 sur
 * `examples/kanban` : une limite d'en-cours refusait au serveur, et
 * l'écran montrait quatre cartes dans une colonne qui en accepte trois.
 *
 * D'où le TÉMOIN ci-dessous. Il ne coûte rien au cas normal et ne
 * demande rien à l'auteur d'app : l'attribut est posé sur l'item au
 * moment du dépôt, le serveur ne le rend jamais, donc idiomorph l'efface
 * dès qu'il ré-apparie le nœud. S'il est encore là quand la requête
 * retombe, personne n'a répondu pour cet item — et le geste se défait.
 *
 * ── La géométrie est LUE, jamais configurée ──────────────────────────
 * L'axe (liste verticale ou horizontale) est déduit de la position réelle
 * de deux items, comme le Carousel déduit sa foulée. Aucun breakpoint,
 * aucun prop `orientation=` à tenir synchronisé avec le CSS.
 *
 * Contrat DOM attendu du Python (aucune directive `bz-*` neuve) :
 *   zone : data-bz-dropzone="<name>"  data-bz-accepts="a,b"  [data-bz-locked]
 *          + un carrier caché [data-bz-move-carrier] portant le hx-post
 *   item : data-bz-draggable  data-bz-key="…"  [data-bz-group] [data-bz-disabled]
 *          [data-bz-handle]  → si présent, seul [data-bz-drag-handle] attrape
 */
(function () {
  "use strict";
  const $bz = (window.$bz = window.$bz || {});

  //: Souris/stylet : distance avant que le geste devienne un drag. C'est
  //: ce seuil qui PRÉSERVE LE CLIC — sans lui, tout clic sur une carte
  //: démarrerait un déplacement.
  const MOUSE_THRESHOLD_PX = 5;
  //: Tactile : durée d'appui avant d'attraper.
  const TOUCH_HOLD_MS = 250;
  //: …et la distance au-delà de laquelle on abandonne avant la fin du
  //: délai. C'est elle qui PRÉSERVE LE SCROLL : un doigt qui file dans une
  //: liste ne doit pas emporter la carte qu'il a effleurée.
  const TOUCH_TOLERANCE_PX = 8;

  //: Le témoin d'un dépôt en attente de réponse. Posé sur l'item, effacé
  //: par le morph — le serveur ne rend jamais cet attribut, donc
  //: idiomorph le retire en ré-appariant le nœud. C'est la seule mesure
  //: possible depuis le client de « la réponse a-t-elle touché cet
  //: item », et elle ne demande aucun protocole neuf.
  const PENDING_ATTR = "data-bz-drop-pending";

  const ZONE_SEL = "[data-bz-dropzone]";
  const ITEM_SEL = "[data-bz-draggable]";
  const HANDLE_SEL = "[data-bz-drag-handle]";
  const CARRIER_SEL = "[data-bz-move-carrier]";
  //: Pose sur la ZONE pendant le survol d'un ecrasement. Le theme s'y
  //: accroche ; rien d'autre ne le lit.
  const REPLACE_ATTR = "data-bz-drop-replace";

  //: Un seul geste à la fois — c'est une vérité physique du pointeur, pas
  //: un raccourci d'implémentation. `armed` = doigt posé, drag pas encore
  //: décidé ; `active` = drag en cours.
  let armed = null;
  let active = null;

  // ── Lecture du contrat DOM ───────────────────────────────────────────

  function zoneOf(el) {
    return el ? el.closest(ZONE_SEL) : null;
  }

  function itemsOf(zone) {
    // Les items d'une zone IMBRIQUÉE ne sont pas les nôtres.
    return Array.prototype.filter.call(
      zone.querySelectorAll(ITEM_SEL),
      function (it) { return zoneOf(it) === zone; }
    );
  }

  function indexOf(item) {
    const zone = zoneOf(item);
    return zone ? itemsOf(zone).indexOf(item) : -1;
  }

  /* Où insérer, quand il n'y a aucun item à viser.
     ⚠️ **Un item n'est PAS forcément enfant direct de sa zone.** Une
     dropzone n'arrange rien — elle reçoit — donc l'appelant empile ses
     items avec le conteneur qu'il utilise déjà (`ui.vstack`, `ui.grid`).
     Insérer dans la ZONE mettrait la carte à côté de cette pile, et
     `insertBefore` lève carrément quand la cible n'est pas son enfant.
     C'est le bug que la page de banc a révélé et que le DOM synthétique
     des tests de geste ne pouvait pas produire. */
  function itemsContainer(zone) {
    const first = itemsOf(zone)[0];
    if (first) return first.parentNode;
    /* Zone VIDE. Retomber sur la zone elle-même était un bug, et le
       commentaire qui vivait ici disait pourquoi il passait inaperçu :
       « le prochain rendu serveur remettra la carte dans la pile ». Il
       ne la remet pas. Le nœud déplacé garde son `bz-id`, qui encode son
       chemin dans l'arbre ; ce chemin a changé, donc idiomorph ne le
       ré-apparie pas et la carte RESTE là où on l'a posée — c'est-à-dire
       enfant direct de la zone, HORS du conteneur que l'app a rendu.

       Reproduit le 2026-09-13 sur `/dnd`, par un glisser qui HÉSITE :
       on sort l'item de sa zone, on change d'avis, on revient. La zone
       d'origine est alors vide, l'item y est ré-append à la racine, et
       il s'affiche à côté de sa boîte au lieu de dedans. Un geste
       hésitant est le geste ordinaire.

       Ce qu'on fait à la place : l'app a rendu ses items dans un
       conteneur à elle (un `vstack`, une grille) — il est toujours là,
       vide. On descend la chaîne des enfants UNIQUES pour le retrouver.
       Le porteur caché du `hx-post` ne compte pas : il est toujours
       présent et fausserait le décompte. */
    let node = zone;
    for (;;) {
      const kids = Array.prototype.filter.call(
        node.children,
        function (k) { return !k.matches(CARRIER_SEL); }
      );
      if (kids.length !== 1) return node;
      node = kids[0];
    }
  }

  /* Une zone qui ne tient qu'UN element. Le defaut, `many`, ne s'ecrit
     pas : l'absence d'attribut suffit. */
  function holdsOne(zone) {
    return zone.getAttribute("data-bz-holds") === "one";
  }

  /* Marquer la cible d'un ECRASEMENT, et ne marquer qu'elle. */
  function markReplace(zone) {
    if (active.replaceZone === zone) return;
    clearReplace();
    active.replaceZone = zone;
    if (zone) zone.setAttribute(REPLACE_ATTR, "true");
  }

  function clearReplace() {
    if (active && active.replaceZone) {
      active.replaceZone.removeAttribute(REPLACE_ATTR);
      active.replaceZone = null;
    }
  }

  function groupOf(item) {
    return item.getAttribute("data-bz-group") || "";
  }

  /* La zone accepte-t-elle ce groupe ?
     ⚠️ `data-bz-accepts` absent ne veut PAS dire « accepte tout ». Une
     zone sans déclaration ne reçoit **que ses propres items** : deux
     listes indépendantes sur la même page ne doivent pas s'échanger des
     cartes parce que personne n'a rien déclaré. C'est le défaut de
     Sortable.js (un groupe anonyme y est unique par instance), et le
     banc du playground l'a prouvé nécessaire — sans lui, attraper une
     carte du kanban surlignait les cinq zones sans rapport de la page.
     Recevoir d'ailleurs est donc un OPT-IN, pas un défaut. */
  function accepts(zone, group, originZone) {
    //: ⚠️ `accepts` gouverne l'ENTRÉE DEPUIS AILLEURS, pas le
    //: réordonnancement interne. Réordonner dans sa propre zone n'est pas
    //: y entrer : l'item y est déjà, et personne n'a rien déclaré à ce
    //: sujet. Consulter `accepts` ici gelait une liste entière dès que le
    //: `group=` des items ne répondait pas à son `accepts=` — mesuré :
    //: `accepts=["card"]` sur des items sans groupe rendait la zone
    //: totalement inerte, en silence. Sortable.js sépare pour la même
    //: raison `put` (recevoir) de `sort` (réordonner).
    if (zone === originZone) return true;
    const raw = (zone.getAttribute("data-bz-accepts") || "").trim();
    //: Absent OU vide : la zone ne reçoit rien d'ailleurs. Les deux se
    //: valent maintenant que le cas interne est sorti — donc
    //: `accepts=[]` scelle bien ce qu'il annonce, ce qui n'était pas le
    //: cas quand la liste vide se confondait avec « non déclarée ».
    if (!raw) return false;
    return raw.split(",").some(function (g) { return g.trim() === group; });
  }

  /* Les deux portes du §6, gardées SÉPARÉES : `accepts` décide de
     l'entrée, `locked` décide de la sortie. Une corbeille est une zone
     qui accepte un groupe et dont rien ne ressort. */
  function canLeave(zone) {
    return !zone.hasAttribute("data-bz-locked");
  }

  function canEnter(zone, group, originZone) {
    if (!accepts(zone, group, originZone)) return false;
    if (zone !== originZone && !canLeave(originZone)) return false;
    return true;
  }

  // ── Géométrie mesurée ────────────────────────────────────────────────

  /* Axe dominant, déduit de deux items réels. Une liste dont les items
     s'écartent surtout en X est horizontale — le CSS a déjà tranché, on
     se contente de le lire. Repli sur l'axe vertical (le cas courant)
     quand il n'y a pas deux items à comparer. */
  function axisOf(zone) {
    //: L'item tiré n'est PAS exclu, et c'est le correctif du 2026-08-10 :
    //: on déplace le vrai nœud, donc il est toujours dans le flux et sa
    //: boîte est aussi valable que celle d'un autre. L'exclure laissait
    //: une liste de DEUX items avec un seul repère, donc un repli sur
    //: l'axe vertical — mesuré : une rangée horizontale de deux cartes
    //: était impossible à réordonner, la comparaison se faisant sur un Y
    //: que les deux partagent.
    const items = itemsOf(zone);
    if (items.length >= 2) {
      const a = items[0].getBoundingClientRect();
      const b = items[1].getBoundingClientRect();
      if (a.left !== b.left || a.top !== b.top) {
        return Math.abs(b.left - a.left) > Math.abs(b.top - a.top) ? "x" : "y";
      }
    }
    //: Un seul item (ou deux superposés) : plus rien à mesurer entre deux
    //: boîtes, on demande au CSS ce qu'il a décidé. Toujours LU, jamais
    //: configuré — aucun prop `orientation=` à tenir synchronisé.
    const box = itemsContainer(zone);
    const dir = (getComputedStyle(box).flexDirection || "");
    return dir.indexOf("row") === 0 ? "x" : "y";
  }

  /* Faut-il insérer APRÈS l'item survolé ? On compare le pointeur au
     milieu de sa boîte, sur l'axe de la liste. */
  function isPastMiddle(rect, x, y, axis) {
    return axis === "x"
      ? x - rect.left > rect.width / 2
      : y - rect.top > rect.height / 2;
  }

  // ── Le geste ─────────────────────────────────────────────────────────

  function disarm() {
    if (armed && armed.timer) clearTimeout(armed.timer);
    armed = null;
  }

  function onPointerDown(e) {
    if (active || armed) return;
    //: Bouton principal seulement : un clic droit ouvre un menu, il
    //: n'attrape pas.
    if (e.pointerType === "mouse" && e.button !== 0) return;

    const item = e.target.closest ? e.target.closest(ITEM_SEL) : null;
    if (!item || item.hasAttribute("data-bz-disabled")) return;
    const zone = zoneOf(item);
    if (!zone) return;

    //: `handle=True` : la carte entière reste inerte, seule la poignée
    //: attrape. C'est une RESTRICTION opt-in, pas le geste par défaut.
    if (item.hasAttribute("data-bz-handle")) {
      const handle = e.target.closest(HANDLE_SEL);
      if (!handle || !item.contains(handle)) return;
    }

    armed = {
      item: item,
      zone: zone,
      pointerId: e.pointerId,
      touch: e.pointerType === "touch",
      x: e.clientX,
      y: e.clientY,
      timer: null,
    };

    if (armed.touch) {
      //: Tactile : c'est le TEMPS qui décide, pas la distance.
      armed.timer = setTimeout(function () {
        if (armed) begin();
      }, TOUCH_HOLD_MS);
    }
  }

  function begin() {
    if (!armed) return;
    const a = armed;
    if (a.timer) clearTimeout(a.timer);
    armed = null;

    active = {
      item: a.item,
      originZone: a.zone,
      originIndex: indexOf(a.item),
      //: De quoi défaire le geste exactement — `insertBefore(item, null)`
      //: rend un append, donc un item repris en dernière position se
      //: restaure sans cas particulier.
      originParent: a.item.parentNode,
      originNext: a.item.nextSibling,
      group: groupOf(a.item),
      pointerId: a.pointerId,
    };
    //: Un attribut, pas une classe : le thème s'y accroche en
    //: `data-[bz-dragging]:…`, et un morph qui réécrit `class=` ne peut
    //: pas l'effacer par accident.
    active.item.setAttribute("data-bz-dragging", "true");
    /* ⚠️ L'AXE — un HOOK pour le thème, pas un réglage du runtime.
       Le défaut livré n'en fait rien : une carte en vol garde sa taille
       (cf. le slot `dragging` de `draggable`). Il est publié pour qu'une
       app qui préfère un EMPLACEMENT puisse l'obtenir en surchargeant ce
       slot, sans prop et sans toucher au geste.

       Pourquoi l'axe et pas un booléen : « plus petit » n'a pas le même
       sens dans les deux sens. Une liste verticale veut une barre pleine
       largeur, une rangée horizontale veut une colonne pleine hauteur.
       Le CSS ne sait pas mesurer une liste ; `axisOf` le déduit déjà de
       la position réelle de deux items.

       Pourquoi pas sur une zone `holds="one"` : elle n'insère rien. Sa
       carte ne laisse pas un espace à combler, elle laisse une place
       VIDE — et un thème qui réduirait un occupant à une barre dans sa
       chaise raconterait quelque chose de faux. */
    if (!holdsOne(a.zone)) {
      active.item.setAttribute("data-bz-drag-axis", axisOf(a.zone));
    }
    makePreview(a.x, a.y);
    markValidZones();
  }

  /* L'aperçu qui suit le pointeur.
     Sans lui, seule la LISTE bouge : les voisins s'écartent, mais rien
     n'est « en main » et le geste se lit comme un curseur qui se promène.
     C'est le clone qui vole et l'original qui reste — la forme de
     Sortable.js et du DragOverlay de dnd-kit — plutôt que de translater
     le vrai nœud, qui est déjà réordonné dans le flux et se déplacerait
     donc deux fois.

     ⚠️ **Le clone doit être ANONYME.** On lui retire `id`, `bz-id` et
     `data-bz-draggable`, sur lui ET sur toute sa descendance : un id en
     double ferait apparier n'importe quoi à idiomorph au prochain morph,
     et un `data-bz-draggable` en double fausserait les index lus par
     `itemsOf`. Le reste de son apparence est un simple clone de ce que
     l'utilisateur regardait déjà. */
  function makePreview(x, y) {
    const src = active.item;
    const rect = src.getBoundingClientRect();
    const node = src.cloneNode(true);

    node.removeAttribute("data-bz-dragging");
    node.removeAttribute("data-bz-drag-axis");
    const strip = ["id", "bz-id", "data-bz-draggable", "data-bz-key",
                   "data-bz-drag-handle", "data-bz-move-carrier",
                   "data-bz-drag-axis"];
    const scrub = function (el) {
      for (let i = 0; i < strip.length; i++) el.removeAttribute(strip[i]);
    };
    scrub(node);
    Array.prototype.forEach.call(node.querySelectorAll("*"), scrub);

    node.classList.add("bz-drag-preview");
    //: Largeur figée : hors du flux, un bloc n'a plus de parent dont
    //: hériter, et l'aperçu s'effondrerait sur son contenu.
    node.style.width = rect.width + "px";
    node.style.height = rect.height + "px";
    node.style.left = rect.left + "px";
    node.style.top = rect.top + "px";

    //: L'écart entre le point saisi et le coin de la carte. C'est lui qui
    //: fait que la carte ne « saute » pas sous le curseur au moment où on
    //: l'attrape — elle reste tenue là où on l'a prise.
    active.grabDX = x - rect.left;
    active.grabDY = y - rect.top;
    active.preview = node;
    document.body.appendChild(node);
  }

  function movePreview(x, y) {
    if (!active.preview) return;
    active.preview.style.left = (x - active.grabDX) + "px";
    active.preview.style.top = (y - active.grabDY) + "px";
  }

  function dropPreview() {
    if (active && active.preview && active.preview.parentNode) {
      active.preview.parentNode.removeChild(active.preview);
    }
  }

  /* Exigence 1 du cadrage : montrer OÙ l'item peut atterrir, pendant le
     geste. Gaté sur un attribut posé par le geste, jamais sur `:hover` —
     un survol n'existe pas au doigt, et c'est le pointeur de référence de
     ce projet. */
  function markValidZones() {
    Array.prototype.forEach.call(
      document.querySelectorAll(ZONE_SEL),
      function (z) {
        if (canEnter(z, active.group, active.originZone)) {
          z.setAttribute("data-bz-drop-ok", "true");
        }
      }
    );
  }

  function clearValidZones() {
    Array.prototype.forEach.call(
      document.querySelectorAll("[data-bz-drop-ok]"),
      function (z) { z.removeAttribute("data-bz-drop-ok"); }
    );
  }

  function onPointerMove(e) {
    if (armed && e.pointerId === armed.pointerId) {
      const dx = Math.abs(e.clientX - armed.x);
      const dy = Math.abs(e.clientY - armed.y);
      if (armed.touch) {
        //: Le doigt a filé avant la fin du délai : c'était un scroll.
        if (Math.max(dx, dy) > TOUCH_TOLERANCE_PX) disarm();
      } else if (Math.max(dx, dy) > MOUSE_THRESHOLD_PX) {
        begin();
      }
      return;
    }
    if (!active || e.pointerId !== active.pointerId) return;

    //: Pendant un drag tactile, le geste nous appartient : sans ça la
    //: page défile sous la carte.
    if (e.cancelable) e.preventDefault();
    //: L'aperçu d'abord : il doit suivre le doigt même quand le pointeur
    //: survole une zone qui refuse, sinon la carte se fige et le geste a
    //: l'air cassé alors qu'il est simplement refusé.
    movePreview(e.clientX, e.clientY);
    hoverTo(e.clientX, e.clientY);
  }

  /* Le cœur : replacer le nœud là où le pointeur dit qu'il va. */
  function hoverTo(x, y) {
    const under = document.elementFromPoint(x, y);
    if (!under) return;
    const overZone = zoneOf(under);
    if (!overZone) return;
    if (!canEnter(overZone, active.group, active.originZone)) return;

    /* ⚠️ ECRASEMENT. Une zone qui ne tient qu'un element et en porte
       deja un ne doit RIEN recevoir pendant le geste : y glisser le noeud
       la ferait contenir deux occupants — ce que l'utilisateur voit comme
       « l'item prend enormement de place ». On la marque, on ne la
       remplit pas. Le depot partira quand meme au handler, qui decide
       (echanger, refuser) : c'est le serveur qui arbitre, ici on ne fait
       qu'annoncer honnetement ce qui va se passer. */
    if (holdsOne(overZone) && overZone !== zoneOf(active.item)
        && itemsOf(overZone).length > 0) {
      markReplace(overZone);
      return;
    }
    clearReplace();

    const overItem = under.closest(ITEM_SEL);
    if (overItem && overItem !== active.item && zoneOf(overItem) === overZone) {
      const rect = overItem.getBoundingClientRect();
      const axis = axisOf(overZone);
      const after = isPastMiddle(rect, x, y, axis);
      //: Relatif au PARENT DE LA CIBLE, jamais à la zone — cf.
      //: `itemsContainer`. Les items peuvent vivre à n'importe quelle
      //: profondeur sous la zone.
      overItem.parentNode.insertBefore(
        active.item, after ? overItem.nextSibling : overItem
      );
      return;
    }
    //: Survol de la zone hors de tout item — typiquement une colonne vide
    //: ou l'espace sous le dernier item. On n'append que si l'item n'est
    //: pas déjà ici, sinon chaque pointermove le rejetterait à la fin.
    if (!overItem && zoneOf(active.item) !== overZone) {
      itemsContainer(overZone).appendChild(active.item);
    }
  }

  function onPointerUp(e) {
    if (armed && e.pointerId === armed.pointerId) return disarm();
    if (!active || e.pointerId !== active.pointerId) return;
    finish();
  }

  function onPointerCancel(e) {
    if (armed && e.pointerId === armed.pointerId) return disarm();
    if (active && e.pointerId === active.pointerId) cancel();
  }

  function onKeyDown(e) {
    if (e.key === "Escape") {
      if (armed) disarm();
      else if (active) cancel();
    }
  }

  function cleanup() {
    dropPreview();
    if (active) {
      clearReplace();
      active.item.removeAttribute("data-bz-dragging");
      active.item.removeAttribute("data-bz-drag-axis");
    }
    clearValidZones();
    active = null;
  }

  /* Annuler = remettre le nœud exactement d'où il vient. Utilisé par
     Échap et par `pointercancel` — JAMAIS par un refus serveur, qui lui
     passe par le morph (cf. l'en-tête de ce fichier). */
  function cancel() {
    if (!active) return;
    active.originParent.insertBefore(active.item, active.originNext);
    cleanup();
  }

  /* Défaire le dépôt si la réponse ne l'a pas confirmé.
     ⚠️ Deux images d'attente, pas une : `htmx:afterRequest` est le seul
     désarmement fiable (htmx l'émet aussi sur 4xx, réseau, abandon), mais
     le swap et le rescan qui l'entourent se posent sur les images
     suivantes. Vérifier tout de suite lirait le témoin avant que le morph
     ait eu l'occasion de l'effacer, et TOUT dépôt reviendrait en arrière. */
  function armSnapBack(item, parent, next, carrier) {
    const itemKey = item.getAttribute("data-bz-key") || "";
    const destination = zoneOf(item);
    const destinationName = destination
      ? destination.getAttribute("data-bz-dropzone") || ""
      : "";
    item.setAttribute(PENDING_ATTR, "");
    function settle(e) {
      if (e.detail && e.detail.elt && e.detail.elt !== carrier) return;
      document.body.removeEventListener("htmx:afterRequest", settle);
      requestAnimationFrame(function () {
        requestAnimationFrame(function () {
          if (!item.hasAttribute(PENDING_ATTR)) return;
          item.removeAttribute(PENDING_ATTR);
          //: Le serveur peut avoir retiré l'item (archivage) : il n'y a
          //: alors rien à remettre, et son ancien parent peut lui-même
          //: avoir disparu.
          if (!item.isConnected || !parent.isConnected) return;
          parent.insertBefore(
            item, next && next.parentNode === parent ? next : null
          );
        });
        requestAnimationFrame(function () {
          restoreSequentialFocus(itemKey, destinationName);
        });
      });
    }
    document.body.addEventListener("htmx:afterRequest", settle);
  }

  /* Reposer le point de départ de la navigation séquentielle après le
     morph. Un déplacement entre zones change le `bz-id` de la carte :
     idiomorph recrée alors son nœud et Chromium remet le focus sur BODY.
     Dans cet état, le premier Tab est avalé au lieu d'atteindre le prochain
     contrôle. On focalise la carte rendue par le serveur comme ancre
     temporaire ; elle n'entre pas durablement dans l'ordre de tabulation. */
  function restoreSequentialFocus(itemKey, zoneName) {
    if (!itemKey || !zoneName) return;
    const zones = document.querySelectorAll(ZONE_SEL);
    let item = null;
    for (let i = 0; i < zones.length && !item; i++) {
      if (zones[i].getAttribute("data-bz-dropzone") !== zoneName) continue;
      const candidates = itemsOf(zones[i]);
      for (let j = 0; j < candidates.length; j++) {
        if (candidates[j].getAttribute("data-bz-key") === itemKey) {
          item = candidates[j];
          break;
        }
      }
    }
    if (!item || !item.isConnected) return;
    const hadTabindex = item.hasAttribute("tabindex");
    if (!hadTabindex) item.setAttribute("tabindex", "-1");
    item.focus({preventScroll: true});
    if (!hadTabindex) {
      item.addEventListener("blur", function removeTemporaryTabindex() {
        item.removeAttribute("tabindex");
      }, {once: true});
    }
  }

  function finish() {
    const a = active;
    //: Un ecrasement n'a PAS deplace le noeud : la zone visee se lit sur
    //: la marque, pas sur la position. Son index est 0 — une zone a un
    //: element n'en a pas d'autre.
    const remplace = a.replaceZone;
    const toZone = remplace || zoneOf(a.item);
    const toIndex = remplace ? 0 : indexOf(a.item);
    const origin = {parent: a.originParent, next: a.originNext, item: a.item};
    cleanup();
    if (!toZone) return;

    //: Rien n'a bougé → aucun aller-retour serveur. Un drag qui repose
    //: l'item où il était ne doit pas produire de `Move`.
    if (!remplace && toZone === a.originZone && toIndex === a.originIndex) {
      return;
    }

    //: C'est la zone qui REÇOIT qui décide — son `on_move` est le
    //: handler, et son carrier porte le hx-post.
    //: ⚠️ Filtré par `zoneOf`, comme `itemsOf` : `querySelector` fouille
    //: TOUT le sous-arbre, donc une dropzone imbriquée — dont le carrier
    //: précède forcément celui du parent, puisqu'il est rendu en dernier —
    //: capterait le drop du parent et le POSTerait à SON handler.
    const carrier = Array.prototype.find.call(
      toZone.querySelectorAll(CARRIER_SEL),
      function (el) { return zoneOf(el) === toZone; }
    );
    if (!carrier) return;

    carrier.value = JSON.stringify({
      item_key: a.item.getAttribute("data-bz-key") || "",
      from_zone: a.originZone.getAttribute("data-bz-dropzone") || "",
      to_zone: toZone.getAttribute("data-bz-dropzone") || "",
      from_index: a.originIndex,
      to_index: toIndex,
    });
    //: Le transport maison — le JS écrit, dispatche, et c'est le hx-post
    //: du carrier qui part. Aucun `fetch` ici : la frontière transport
    //: appartient au bridge (charter, principe 2).
    armSnapBack(origin.item, origin.parent, origin.next, carrier);
    $bz.helpers.emitChange(carrier, "move");
  }

  //: Une fois le geste ATTRAPÉ, le doigt nous appartient : c'est ce
  //: `preventDefault` sur le `touchmove` qui empêche le navigateur de
  //: faire défiler sous la carte.
  //:
  //: Il ne double PAS celui de `onPointerMove`. Un `preventDefault` sur
  //: un `pointermove` n'annule pas un défilement tactile — seul le
  //: `touchmove` le peut, et seulement en écoute NON PASSIVE. Tant que
  //: la CSS posait `touch-action: none` la question ne se posait pas :
  //: le navigateur ne défilait jamais. Depuis que l'item laisse le
  //: `pan-x pan-y` (finding [27] : sans ça le doigt ne pouvait plus
  //: faire défiler une colonne de cartes), il faut reprendre le geste au
  //: moment où l'appui long aboutit — et à cet instant précis le doigt
  //: n'a pas bougé, donc aucun défilement n'est en cours et la reprise
  //: est propre.
  //:
  //: ⚠️ On ne prévient RIEN tant que le drag n'est qu'`armed` : c'est
  //: exactement le cas « un doigt file dans la liste et effleure une
  //: carte », que la tolérance de 8 px laisse au défilement.
  function onTouchMove(e) {
    if (active && e.cancelable) e.preventDefault();
  }

  document.addEventListener("pointerdown", onPointerDown, true);
  //: `passive: false` — `onPointerMove` doit pouvoir `preventDefault()`
  //: pour tenir le scroll pendant un drag à la SOURIS (sélection de
  //: texte, drag natif d'image).
  document.addEventListener("pointermove", onPointerMove, { passive: false });
  document.addEventListener("touchmove", onTouchMove, { passive: false });
  document.addEventListener("pointerup", onPointerUp, true);
  document.addEventListener("pointercancel", onPointerCancel, true);
  document.addEventListener("keydown", onKeyDown, true);

  //: Exposé pour les tests et pour un futur composant qui piloterait le
  //: geste. Le contrat public reste les data-attributes.
  $bz.dnd = {
    MOUSE_THRESHOLD_PX: MOUSE_THRESHOLD_PX,
    TOUCH_HOLD_MS: TOUCH_HOLD_MS,
    TOUCH_TOLERANCE_PX: TOUCH_TOLERANCE_PX,
    _state: function () { return { armed: armed, active: active }; },
    _axisOf: axisOf,
    _accepts: accepts,
    _canEnter: canEnter,
    _indexOf: indexOf,
  };
})();
