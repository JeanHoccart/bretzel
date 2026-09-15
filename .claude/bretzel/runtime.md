# Runtime — `$bz`, moteur de directives `bz-*`, OOB swaps, FOUC

Source : `bretzel/runtime/_src/*.js`, concaténés **dans l'ordre numérique** en
`runtime.js` par `bretzel/runtime/_build.py` (`tests/unit/runtime/test_build.py`
vérifie que chaque fichier est listé). **Aucun Alpine.js** — le runtime client
est un moteur maison : signaux réactifs + directives `bz-*` + un bridge HTMX
pour la frontière transport.

---

## Ce que la page charge vraiment (2026-08-27)

Deux fichiers, une seule URL `/_bretzel/runtime.js` : **le dev sert le
lisible, la prod sert `runtime.min.js`**. Le lisible porte 143 Ko de
commentaires sur 286 ; sa réduction — commentaires et indentation
retirés, aucune ligne fusionnée, aucun identifiant renommé — pèse
**26,5 Ko gzippés contre 90,5**. Les deux sont produits et vérifiés par
`python -m bretzel.runtime._build` (`--check` regarde les DEUX : un
`runtime.min.js` périmé ne casserait qu'en prod). Le scanner est dans
`bretzel/runtime/_minify.py` ; c'est un navigateur qui le juge, dans
`tests/runtime_js/test_the_minified_runtime_boots.py`.

Les trois scripts qui ne sont pas de nous — htmx, l'extension idiomorph,
le composant web iconify — se rapatrient dans `./.bretzel/vendor/` par
`python -m bretzel.render.vendor` (même patron que le binaire Tailwind
dans `.bretzel/bin/` : un cache de projet, rien de tiers dans le dépôt,
empreinte SHA-256 vérifiée). Tant que le cache est vide, le shell pointe
sur le CDN et tout marche — le repli est la règle de départ, pas une
panne.

Ce que ça change, mesuré en mode prod, cache froid, sur une page
minimale : `DOMContentLoaded` **644 ms → 110 ms**. Les trois scripts
tombent de 593 / 592 / 489 ms à ~50 ms chacun, parce qu'ils passent par
la connexion déjà ouverte de l'app au lieu de trois origines à résoudre
et à négocier. Les données d'icône passent par `/_bretzel/icons`. Le
navigateur reste en même origine ; le serveur consulte Iconify au premier
manque, puis sert son cache de projet. Une production sans accès sortant
doit donc préremplir ce cache ou éviter les glyphes qui n'y figurent pas.

---

## Modules dans l'ordre de chargement

| # | Fichier | Rôle |
|---|---|---|
| 00 | `00_index.js` | bootstrap + wiring de `window.$bz`, scan initial du DOM, listener OS color-scheme (`$bz._osScheme`) |
| 01 | `01_signals.js` | primitives réactives : `signal(init) → {get,set,peek,subscribe}`, `effect`, `computed` (auto-tracking) |
| 02 | `02_directives.js` | les 14 directives `bz-*` <!--count:runtime_directives--> + le moteur de binding (compile `new Function` + `with($scope)`, cache par expr) |
| 03 | `03_scope.js` | état `bz-data` scopé par composant, keyé par `bz-id` (survit au morph) |
| 04 | `04_persistence.js` | adaptateurs de storage (`volatile`/`session`/`local`/`cross_tab`) par instance ClientState — `volatile` = le `memory` de l'API Python ; le mode `page` (V2) a disparu |
| 05 | `05_bridge.js` | glue HTMX : snapshot des signaux en sortie, `<bz-patch>` appliqué en entrée, rebind-after-morph |
| 06 | `06_helpers.js` | helpers partagés des composants overlay |
| 06 | `06_locale.js` | `$bz.locale` : noms de mois et de jours dérivés de la langue. ⚠️ **06 est une contrainte d'ORDRE** — il portait le rang **22** jusqu'au 2026-08-27, donc chargeait après son unique consommateur, `07_calendar` — une exception jetée par calendrier, et `-m audit` qui pendait dessus |
| 07 | `07_calendar.js` | custom element `<bz-calendar>` (grille de jours stateful) |
| 08 | `08_file_upload.js` | factory `$bz.fileUpload.makeScope` pour `ui.file_upload` |
| 09 | `09_notification.js` | stack de toasts (`$bz.notify`) |
| 10 | `10_charts.js` | scopes tooltip + legend partagés des charts |
| 11 | `11_number_input.js` | scope de NumberInput : précision, clamp, snap-to-step, brouillon-vs-valeur, nudge |
| 12 | `12_slider.js` | scope de Slider : drag / clavier / pointeur / clamp / snap (~15 méthodes) |
| 13 | `13_select.js` | scopes de Select : pick, surbrillance, appartenance multi, actions groupées |
| 14 | `14_combobox.js` | scopes de Combobox — le plus gros (~30 méthodes) : normalise / filtre / navigation + pick |
| 15 | `15_pagination.js` | scope de Pagination (`$bz.pagination`) |
| 16 | `16_accordion.js` | scopes d'Accordion / Tree / Tabs / Tooltip |
| 17 | `17_carousel.js` | scope de Carousel — le défilement est du **CSS scroll-snap**, pas un `translateX` piloté d'ici |
| 18 | `18_time_picker.js` | scope de TimePicker ; la valeur est la chaîne `"HH:MM"`, même forme que l'ISO des pickers de date |
| 19 | `19_dnd.js` | le geste **node-DnD** de `dropzone` / `draggable` : déplacer un nœud d'une position à une autre |
| 20 | `20_resizable.js` | Resizable (split panes) : pointeur → une **dimension**, deux voisins se repartagent leur place |
| 21 | `21_signature_pad.js` | SignaturePad — le seul `<canvas>` du dépôt (les charts sont en SVG) |
| 22 | `22_verbs.js` | La moitié cliente des **verbes** (`bretzel.copy`) — une action du NAVIGATEUR déclenchée depuis un `on_*=`. `copy`, `share` et `vibrate` y vivent — les deux premiers pour leur REPLI (hors contexte sécurisé pour `copy` ; `navigator.share` absente sur bureau pour `share`, qui retombe alors sur la copie de l'URL), `vibrate` pour la garde d'absence. `print_page` et `fullscreen` tiennent en une expression que Python écrit en toutes lettres |
| 23 | `23_diagram.js` | La mise en évidence des voisins dans `ui.diagram` — `light(clé, adjacence)`, `isLit(clé)`, `isEdgeLit(a, b)`. Le graphe est PLACÉ côté serveur ; ce slab ne place rien. Il répond à la seule question locale : ce que je viens de désigner touche-t-il ce nœud, cette arête ? L'adjacence est cuite dans le DOM au rendu, donc rien n'est parcouru. **La frontière avec le serveur est nette** : éclairer ne change pas QUELS nœuds existent (client, zéro requête), resserrer sur un voisinage (`focus=`) change le placement (serveur). Recliquer le nœud désigné éteint — c'est la seule sortie sur un écran sans survol. Une arête n'est en avant que si ses DEUX extrémités le sont : avec un « ou », toutes celles qui quittent le voisinage resteraient allumées |

⚠️ **Trois familles de « drag », à ne pas confondre** — les trois fichiers
le disent chacun en tête, parce que les mélanger coûte cher :
`12_slider` = pointeur → une VALEUR ; `19_dnd` = déplacer un NŒUD ;
`20_resizable` = pointeur → une DIMENSION. (`08_file_upload` est encore
autre chose : le DnD HTML5 natif, des fichiers de l'OS.)

Ajouter un module → numéro **23+** (ou, si un slab existant en dépend, un rang AVANT lui), puis `python -m bretzel.runtime._build`.
`test_build.py` doit lister le nouveau fichier, et
`tests/consistency/test_a_documented_population_is_complete.py` exige que
la table ci-dessus le cite.

*(Cette table s'est arrêtée trop tôt **deux fois**. À 14 en disant « 15+ »
jusqu'au 2026-08-01, alors que 15 et 16 existaient. Puis à 16 en disant
« 17+ » jusqu'au 2026-08-26, alors que 17 à 22 existaient — dont
`22_locale`, livré dix jours plus tôt (renommé `06_locale` depuis). Réparer sans gater, c'est
programmer la troisième fois : d'où la gate, cette fois-ci.)*

---

## `$bz` — l'objet global runtime

**Public** :

| Propriété / méthode | Quand l'utiliser |
|---|---|
| `$bz.state.<Class>.<key>.<field>` | le **signal** du champ — path évalué dans `bz-attr:`, `bz-show`, `bz-model`, etc. (`get`/`set`/`peek`/`subscribe`) |
| `$bz.signal(init)` / `$bz.effect(fn)` | primitives réactives exposées, utilisées par les scopes composant |
| `$bz.notify` | stack de toasts côté client (cf. `09_notification.js`) |
| `$bz.charts` / `$bz.fileUpload` / `$bz.combobox` / `$bz.slider` / `$bz.select` / `$bz.numberInput` | factories de scope de ces composants |
| `$bz.helpers` | helpers overlay partagés |
| `$bz.version` | stamp de version protocol (`v1.0`) |

**Tout ce qui est préfixé `_` est privé** (`$bz._store`, `$bz._csrf`,
`$bz._endpoints`, `$bz._scan`, `$bz._config`, `$bz._persistence`, `$bz._osScheme`,
`$bz._ensureSse`, `$bz._sweepScopes` / `_sweepTeleports` / `_resyncScopes`…) —
ne pas appeler depuis du code app/composant.

---

## OOB swap — comment les fragments arrivent dans la page

Chaque action POST renvoie un body = fragments OOB HTMX + un `<bz-patch>` :

```html
<div id="refresh_<hash>" hx-swap-oob="morph">…contenu refreshable…</div>
<bz-patch>{"patches":{"State.key":{"field":value}, "_notifications":[…]}}</bz-patch>
```

- Chaque `@refreshable` enqueué (un state `deps=` a muté, ou `refresh(zone)`) →
  fragment `hx-swap-oob="morph"` ciblé sur son `id` (idiomorph applique par id).
- `<bz-patch>` porte le **delta de state** ; le bridge l'applique dans le store
  **après** le swap (`htmx:afterSwap` / `oobAfterSwap`), puis **re-scanne** le
  sous-arbre swappé pour re-binder les directives qu'idiomorph a clobberé
  (`rebind-after-morph` — la règle unique qui remplace l'ancienne machinerie
  `02_morph_hook`).
- Sur **4xx/5xx** (non swappés par HTMX), le bridge extrait quand même le
  `<bz-patch>` du texte brut de la réponse (ex : erreurs de formulaire).
- Rien à taper : le runtime **possède** la frontière transport.

**Action serveur** : émise en `hx-post` natif (+ `data-bz-sig`) au render ; le
bridge intercepte `htmx:configRequest` pour ajouter le header HMAC (`X-Bz-Sig`),
le snapshot de client-state (form-fields namespacés `Class.key.field`) et les
headers protocol. Pas de `fetch()` manuel dans un composant.

### Un nœud NEUF est inerte pendant ~6 ms — assumé, ne pas re-mesurer

Corollaire direct du re-scan ci-dessus : il tourne **après** le swap, donc
entre l'instant où un nœud nouvellement inséré est peint et l'instant où il
est re-bindé, un clic dessus **ne fait rien — en silence**. Pas d'erreur,
pas de POST, rien à observer.

Mesuré le 2026-08-16, 25 essais, séparation nette et sans chevauchement :

| | délai depuis la **peinture** du nœud |
|---|---|
| clics perdus (15) | 1,3 → **5,5 ms** (médiane 3,3) |
| clics réussis (10) | **14,2** → 36,5 ms (médiane 22,8) |

Soit **~6 ms**, moins d'une frame à 60 Hz — cohérent avec un re-bind qui
s'achève à la frame suivant la peinture, non prouvé.

**Seuls les nœuds NEUFS sont concernés.** Contre-épreuve, 24 essais sur une
ligne préexistante qu'idiomorph préserve : **0 perte**, y compris à 1,0 ms
après peinture, en plein dans la fenêtre fatale aux nœuds neufs. Ce qui est
réutilisé garde son câblage de bout en bout.

**Décision (2026-08-16) : on assume.** Pas de signal de fin de swap, pas de
classe posée sur la zone. Atteindre cette fenêtre à la main demanderait de
cliquer un élément *qui n'existait pas* moins de 6 ms après son apparition,
quand le plancher de réaction visuelle humaine est de 200-250 ms — un
facteur 40. Le coût réel connu est **un test à synchroniser, pas un
utilisateur gêné**.

Ce que ça implique quand tu écris un test qui pilote une zone rafraîchie :
« le contenu est visible » n'est **pas** un point de synchronisation
suffisant. Il faut attendre que la zone soit *posée* — aucune requête htmx
en vol **et** le DOM silencieux quelques sondages d'affilée. Le helper
`_settled` de `tests/e2e/test_todo.py` porte cette attente et sa mesure ;
avant lui, cocher une case juste après un ajout aboutissait 9 fois sur 20.

⚠️ **Ne re-mesure pas ça avec un sondage depuis Python.** Une première
instrumentation interrogeait la page toutes les 2 ms via Playwright : chaque
aller-retour rend la main à la boucle d'événements du navigateur, le re-bind
a le temps de finir, et elle mesurait **0 perte sur 24** en n'atteignant
jamais un clic sous 11 ms. L'instrument effaçait le phénomène. Il faut armer
la frise **dans la page** (MutationObserver + `requestAnimationFrame`) et ne
la relire qu'une fois la séquence terminée.

---

## `bz-data` scopes + le piège du `this.`

Le state réactif app-level vit dans `$bz.state.<Class>.<key>` (des **signaux**,
pas dans `bz-data`). `bz-data` sert aux **composants** pour un scope local keyé
par `bz-id` (`03_scope`) — typiquement l'`open` d'un overlay en mode littéral.

```js
{ open: false, _pick(v) { open = false; } }       // ❌ crée un global !
{ open: false, _pick(v) { this.open = false; } }  // ✅ écrit dans le scope
```

Le moteur wrap les expressions **inline** avec `with($scope){ … }` (rebind des
bare names), mais **pas** les méthodes shorthand → toujours `this.field` dans
une méthode de scope `bz-data`.

---

## Les 14 directives `bz-*` <!--count:runtime_directives-->

Émises automatiquement par les composants — pas à taper à la main (escape hatch
seulement).

| Directive | Sur quoi | Ce qu'elle fait |
|---|---|---|
| `bz-attr:<attr>="<expr>"` | attr réactif une-voie | (re)set l'attribut à chaque mutation ; `false/null/undefined` → `removeAttribute` |
| `bz-model="<path>"` | binding deux-voies | inputs de formulaire uniquement |
| `bz-on:<event>="<expr>"` | listener d'event | exécute l'expr dans le scope (client-only) |
| `bz-class="<obj\|array>"` | classes | add/remove par truthiness ; `class=""` statique préservé |
| `bz-text="<expr>"` | `textContent` | display-only |
| `bz-show="<expr>"` | `display` toggle | l'élément reste monté |
| `bz-if="<expr>"` | mount/unmount | sous-arbre frais à chaque mount |
| `bz-for="v in expr [:key=…] [:flip]"` | itération keyée (`:flip` = reflow FLIP optionnel) | sur un `<template>` à racine unique |
| `bz-init="<expr>"` | one-shot | au premier mount du nœud |
| `bz-effect="<expr>"` | effet réactif continu | (remplace l'ancien `$watch`) |
| `bz-ref="<name>"` | enregistre l'él dans les refs du scope | |
| `bz-teleport="<selector>"` | déplace le `<template>` vers la cible | scope reste bindé à l'origine |
| `bz-data="{…}"` | ouvre un scope | possédé par `03_scope` |

Sandbox d'expression : `new Function` + `with($scope)`, magics `$bz` / `$el` /
`$refs` / `$event` / `$value` / `$dispatch` / `$nextTick`.

⚠️ **Une CSP est livrée depuis le 2026-09-05** — cf.
[`security.md`](security.md). Elle porte `'unsafe-eval'`, que ce
`new Function` exige, mais PAS `'unsafe-inline'` : un `<script>` injecté
ne s'exécute pas. Le mode qui retirerait `'unsafe-eval'` reste différé,
et son coût est chiffré là-bas (29 % des expressions émises sortent d'un
sous-ensemble interprétable — c'est un interpréteur JS, pas un réglage).
Cette ligne a longtemps dit « mode CSP différé » tout court, ce qui se
lisait comme « pas de CSP possible » — et c'est ce que la revue
extérieure du 2026-09-04 en a conclu.

---

## FOUC — deux mécanismes (plus de `x-cloak`)

1. **Scopes** : le shell émet inline en `<head>` (avant toute stylesheet)
   `html:not(.bz-ready) [bz-data]{visibility:hidden}`.
   `00_index` pose `.bz-ready` sur `<html>` après le premier scan (~10-30 ms) →
   aucun élément à scope ne flashe.
   ⚠️ C'était une PAIRE — la règle globale, plus `html.bz-ready [bz-data]
   {visibility:visible}` pour la relever. Écrire `visible` explicitement
   affranchit la cible de tout ancêtre masqué, or `visibility` est
   justement la propriété qu'un descendant peut reprendre : un `ui.dialog`
   fermé, qui se cache en `visibility:hidden`, laissait le premier
   composant à état client qu'il contient dans l'ordre de tabulation
   (mesuré sur `examples/messagerie`, corrigé le 2026-09-10). Une seule
   règle bornée au pré-boot dit la même chose sans relever quoi que ce
   soit.
2. **Branches mutex** (`Component._cloak_show`, ex Button loading↔icon,
   Alert dismissible) : la branche dont l'évaluation initiale est falsy reçoit un
   `style="display:none"` **pré-stampé au serveur** (`stamp_display_none`) +
   `bz-show` ; rien ne flashe avant le premier effet.

> Il n'y a **plus** de directive ni de CSS `[x-cloak]` — c'était le mécanisme
> Alpine, remplacé par les deux ci-dessus.

---

## Anti-FOUC dark mode

Le shell émet inline dans le `<head>`, **avant toute stylesheet** (mais pas
en première position : charset / viewport / meta htmx-config / title /
description le précèdent), un script qui lit
`localStorage.getItem('$bz:ColorScheme.default')` puis
retombe sur `prefers-color-scheme`, et pose `.dark` sur `<html>` au moment où le
CSS compute la première fois → pas de flash blanc.

---

## CSRF / sécurité

- `Bretzel(secret_key=…)` dérive une clé **par usage** (HMAC-SHA256) ; chaque
  `action_id` est signé (HMAC tronqué) et forwarded en header `X-Bz-Sig`.
- Chaque POST porte `X-Bretzel-CSRF` (token lu de `$bz._csrf`, posé par
  l'envelope), `X-Bretzel-Protocol`, `X-Bretzel-Page-ID` (via `hx-headers` posé sur le **wrapper** `div#bz-page-…`, pas sur `<body>`
  sur le `<body>`, cf. `shell.py`) et `X-Bz-Ts` (timestamp signé — cf.
  anti-replay ci-dessous).
- Un POST d'action porte en plus **`X-Bretzel-Zones`** — les `bz-id` des
  zones `@refreshable` que le document a réellement sous les yeux, lues
  au moment de la requête sur `[data-bz-zone]`. Ce n'est pas de la
  sécurité, c'est ce qui permet au drain de ne rendre que ces zones-là :
  `_ZONES_BY_DEP` est indexé par CLASSE d'état, donc une classe partagée
  entre écrans traînait les zones des AUTRES pages, que le serveur
  rendait et que le navigateur jetait faute de cible. Mesuré le
  2026-09-05 sur `examples/mad` : 8,4 ms de rendu perdus contre 9,6 ms
  utiles, près de la moitié du drain.
  ⚠️ **En-tête absent = « je ne sais pas », pas « aucune zone »** : le
  serveur ne filtre alors rien. Un runtime en cache ou un client tiers
  retombe donc sur l'ancien comportement, jamais sur une page qui cesse
  silencieusement de se mettre à jour. Le DOM est lu à chaque requête et
  non une liste donnée au rendu — un swap OOB peut avoir introduit une
  zone depuis, et une liste figée la condamnerait.
- La route `/_bretzel/action/*` vérifie le HMAC **avant** toute résolution → une
  URL forgée sans le secret = 403. La défense CSRF réelle tient au couple
  header-custom `X-Bz-Sig` (non-settable cross-origin sans préflight) +
  `SameSite=Lax`.
- **Anti-replay (HMAC v2, livré)** : la signature d'action bake un **timestamp
  au render**, forwarded par le bridge en `X-Bz-Ts`. Deux défenses :
  **(a)** fenêtre de validité — si `Bretzel(action_max_age=…)` est réglé, le
  serveur rejette toute action dont le `ts` signé est trop vieux
  (`routing/actions.py`) ; **(b)** `@idempotent` — un handler ainsi marqué
  dédup les rejeux par clé pendant son TTL. **Il n'y a PAS de header
  `X-Bz-Nonce`** ni de table de nonces : une signature figée au render ne peut
  pas couvrir le body, donc le nonce du spec initial a été abandonné au profit
  de ce couple ts-signé + idempotence (cf. `project_hmac_v2_design`).
