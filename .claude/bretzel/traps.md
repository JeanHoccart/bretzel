# Pièges techniques actuels

Ce fichier contient les erreurs de conception encore faciles à reproduire dans
le code actuel. Les récits de correction, mesures datées et pièges des anciens
runtimes restent dans Git.

## Runtime et bindings

### `bz-class` fusionne, `bz-attr:class` remplace

Une classe réactive ajoutée aux classes du thème utilise `bz-class`. Employer
`bz-attr:class` remplace toute la classe statique du composant.

### Un champ de formulaire lié possède un carrier réel

`value`, `checked`, `disabled` et les actions doivent atteindre l'élément qui
porte réellement la sémantique HTML. Poser la directive seulement sur un
wrapper produit une apparence réactive sans modifier le contrôle.

Pour les contrôles éditables, le runtime protège la saisie locale pendant un
morph et réapplique ensuite la valeur serveur lorsqu'elle a réellement changé.
Ne pas contourner ce protocole avec un attribut HTMX ou un listener manuel.

### `bz-on:` n'a pas de modificateur

Tout ce qui suit `bz-on:` est un nom d'événement. Les suffixes de style Alpine
comme `.window`, `.prevent` ou `.stop` ne sont pas interprétés.

### `this` n'est pas le scope d'une expression

Une expression de directive résout les noms dans le scope Bretzel. Écrire
`this.open` ou copier une expression Alpine produit un comportement erroné.

### Une valeur de scope calculée doit rester calculable

Une mesure du DOM ou une valeur dérivée copiée dans un littéral `bz-data` est
figée au montage. Garder une méthode dans le scope ou recalculer depuis l'effet
qui dépend des signaux concernés.

### Une config serveur se re-sème aussi quand la valeur est liée

`absorb` ne réécrit jamais un signal existant : une donnée que le serveur
change (options, bornes, nombre de pages) n'atteint un scope vivant que si
`_serverSync` la nomme. Lier la VALEUR à un `ClientState` ne change pas le
propriétaire de la CONFIG. `ui.select` et `ui.combobox` liés oubliaient
`_options` / `_labels` : l'option ajoutée par un refresh s'affichait, se
cliquait, et le déclencheur restait sur le placeholder. `scope_literal`
re-sème `config=` dans les deux modes.

### Les identités doivent survivre aux rendus partiels

Un `bz-id` calculé uniquement depuis la position courante change lorsqu'un
sous-arbre est rendu seul. Utiliser les helpers d'identité du socle et une
`key=` métier pour les collections réordonnables.

### Custom elements et morph

Le morph peut remplacer les enfants gérés par un custom element. Le composant
doit définir explicitement ce qui est préservé et réinitialiser son état après
swap. Une écriture DOM transitoire ne doit pas être stockée dans un attribut
que le rendu serveur possède.

### Un état local de boucle se lie à une POSITION

Sans `key=`, le `bz-id` d'un élément répété est sa position. Un signal de
scope client (le `open` d'un dismiss, un dépliage) passe donc à l'élément
qui prend la place après un re-rendu. Quand le serveur reçoit le geste
(un `on_close` serveur), la clé est re-semée (`_serverSync`) et le rendu
fait foi ; pour un état purement local, une `key=` métier reste
obligatoire.

### Aucune valeur d'attribut ne contourne l'échappement

Une expression cliente porte des littéraux, et `then_else` écrit des `"`.
Émise sans échappement, elle referme l'attribut et le runtime lève sur
l'expression tronquée : le scan de TOUTE la page s'arrête. Émettre une
`str` ordinaire — `RawAttrValue` a été supprimé le 2026-09-29, gaté par
`test_a_client_expression_survives_its_attribute`.

### Un attribut de lien ne vit que sur un lien

`href` / `target` / `rel` / `download` sont admis en kwargs bruts (pour
`tag="a"`), mais posés sur un `<button>` ou un `<div>` ils ne font rien.
Le rendu lève depuis le 2026-09-29 ; un composant qui doit naviguer prend
`href=` en paramètre (`ui.button`, `ui.icon_button`, `ui.link`, `ui.card`).

## État

### Un binding ne se lit pas comme une valeur Python

`ClientBinding` représente une expression cliente. `bool(binding)`,
`str(binding)`, une f-string ou un cast Python lèvent volontairement. Pour une
branche serveur, utiliser un état serveur ; pour du texte réactif, transmettre
le binding à une prop déclarée bindable.

### Les mutations en place doivent passer par les objets réactifs

Une liste ou un dictionnaire client brut ne signale pas nécessairement
`append`, `push` ou l'affectation d'une clé. Utiliser les wrappers et opérations
fournis par l'état Bretzel.

### Un validator retourne la valeur

Un validator qui ne retourne rien remplace le champ par `None`. Tester le
retour et le type après coercition.

### Une navigation repart d'une page neuve, un GET du framework non

Le pont joint `X-Bretzel-Page-ID` à TOUTE requête htmx, lien boosté
compris. Le serveur l'ignore donc sur une navigation (GET hors
`/_bretzel/`, `render_context._is_navigation`) et renvoie le nouvel id
dans le même en-tête ; le pont l'adopte (`05_bridge.js`, `afterRequest`).
Sans l'adoption, la page affichée est neuve mais l'action suivante
retrouve l'état de la page quittée. Un GET du framework (refetch, export)
parle, lui, pour la page qui l'envoie : ne jamais le compter comme une
navigation. Gates : `tests/integration/server/test_a_navigation_starts_a_fresh_page.py`
et son pendant `tests/runtime_js/`.

### Un plateau qui change à chaque tick ne se re-rend pas

Une zone `@refreshable` reconstruit tous ses composants : 1 600 `ui.card`
cliquables pèsent environ 1 Mo et 350 ms de rendu, donc cinq générations
par seconde sont hors de portée. Rendre les cellules une fois, lier leur
aspect à un `ClientState` que le handler réécrit
(`classes=etat.vivantes.contains(i).then_else(...)`) : un tick ne
transporte plus que la liste. Cf. `examples/life`.

### Un défaut serveur doit être déterministe

Une `default_factory` aléatoire ou dépendante de l'heure reconstruit une valeur
différente entre le rendu et une action adressée par identifiant. Persister la
valeur ou fournir une clé métier stable.

## Composants

### Slot Component stocké sans `adopt_slot`

Un composant reçu dans un slot doit être adopté dans `__init__`, puis rendu par
`emit_text_slot`. Oublier l'adoption peut l'attacher deux fois ; oublier
l'émission peut le transformer en texte ou l'orpheliner.

### Icon construit dans `render()` sans détachement

Créer un sous-composant pendant `render()` peut l'attacher au contexte de rendu
extérieur. Préférer l'adoption à la construction ou utiliser les helpers qui
isolent le rendu des sous-composants.

### `disabled` sur un élément non natif ne désactive rien

Un `<a>` ou un `<div>` demande au minimum `aria-disabled`, retrait du focus et
neutralisation de l'action. Un lien désactivé doit retirer le `href` littéral
et toute directive réactive capable de le restaurer.

### Une API impérative exige une identité

Une commande locale cible la racine par son `id`. `_dispatch_command()` se
charge de cette identité. Une méthode dont le nom collisionne avec une
`reactive_prop`, comme `open`, doit être installée sur l'instance.

### Un event déclaré doit partir du bon élément

`EVENTS` et la signature publique ne prouvent pas qu'un événement est
atteignable. Le carrier doit porter l'action, la valeur et le déclencheur
attendu, notamment pour `change`, `focus` et `blur`.

## Thème et mise en page

### L'ordre dans `class=` ne tranche pas un conflit Tailwind

Deux utilitaires de même propriété sont départagés par l'ordre de la feuille
CSS. Une classe utilisateur conflictuelle doit passer par le mécanisme de
surcharge prévu, et les thèmes ne doivent pas empiler deux valeurs concurrentes.

### Une classe Tailwind assemblée peut disparaître en production

Une classe formée par concaténation ou f-string n'est pas forcément vue par le
scanner. Utiliser des littéraux complets ou la safelist produite par le thème.

### Le cache `style.css` ne voit que ce que sa marche parcourt

La clé inclut l'empreinte des fichiers balayés : une classe écrite seulement
sous un dossier élagué (caché, venv, `build/`, `dist/`, `archive/` racine) ne
recompile rien. Une racine `@source` nichée sous un dossier élagué — le paquet
installé dans le `.venv` de l'app — reste une racine à part entière, sinon les
thèmes du framework sortent de la clé.

### Les icônes se dimensionnent par `font-size`

`iconify-icon` peint un glyphe en `1em`. Les classes `text-*` fixent donc sa
taille ; `w-*` et `h-*` ne suffisent pas.

### Un texte sans taille hérite, et le navigateur dit 16 px

`ui.text` et `ui.link` n'écrivent aucune classe de taille par défaut, un
conteneur nu non plus : leur texte hérite. `<body>` porte `text-base` pour
que ce soit le palier médian du thème (14 px), pas les 16 px du navigateur.
Une coque qui ne passe pas par `render/shell.py` doit le reposer, et une app
qui voit tout « un cran trop gros » ne compense pas avec `size="sm"`
partout : elle regarde d'abord ce qu'hérite le texte nu.

### Une boîte en crans autour d'un texte en paliers

Les crans (`w-9`, `w-64`) suivent `--spacing` ; les paliers `text-*` non.
Une largeur écrite en crans pour contenir du texte déborde dès que la
densité se resserre (calendrier à 2,4 px : « LUN.MAR. » collés), et un
CADRE écrit en crans rétrécit avec les contrôles (sidebar à 192 px au lieu
de 256). Le texte fixe le plancher (`min-w-fit`, `min-w-max`) ; un cadre
s'écrit en `rem` (gate `test_a_frame_width_is_not_a_density_step`) ; un
écart en `px` calé pour 4 px par cran se réécrit en demi-cran (switch).

### SVG étiré : `pathLength` + `non-scaling-stroke` rend la ligne en pointillés

Dans un `<svg preserveAspectRatio="none">` étiré, un trait
`vector-effect: non-scaling-stroke` avec `pathLength="1"` et
`stroke-dasharray: 1` : Chromium calcule le tiret sur la longueur non
étirée et dessine sur la longueur étirée — la ligne finie sort en tirets.
Pour révéler un tracé étiré, découper (`clip-path`), pas jouer des tirets.

### Un overlay hérite des contraintes de ses ancêtres

`overflow`, `transform` et les contextes d'empilement peuvent clipper ou
décaler un panneau pourtant positionné en `fixed`. Utiliser les composants
d'overlay et leurs helpers de placement ; ne pas reconstruire leur shell dans
l'application.

### Une colonne qui défile ÉCRASE ses items

Dans une colonne flex contrainte, une racine avec `overflow-hidden`,
`overflow-auto` ou `overflow-scroll` peut rétrécir sous son contenu. Les racines
actuellement concernées sont `ui.accordion`, `ui.card`, `ui.diagram`,
`ui.table`, `ui.toggle_button`, `ui.toggle_group` et `ui.viewport`.

Le conteneur déroulant utilise l'idiome complet :

```text
flex-1 min-h-0 overflow-y-auto [&>*]:shrink-0
```

`[&>*]:shrink-0` empêche les enfants de payer la réduction nécessaire au
scroll. Si la racine clippante porte elle-même `shrink-0`, elle n'a pas besoin
d'être ajoutée à cette liste.

### Un espace en tête d'un texte dans un hstack disparaît

Chaque enfant d'un `ui.hstack` est un élément flex, donc un bloc : son
espace de tête est avalé. `ui.text(" of 3")` après un compteur rendait
« 2of 3 » dans le tiroir du kanban, alors que le HTML contient l'espace.
Un liant et du texte se composent en UN nœud :
`ui.text(etat.faites + " of 3")` reste réactif (seule la f-string lève).

### Une colonne centrée rétrécit `ui.outlet()` à son contenu

Un `ui.vstack(align="center")` n'étire pas ses enfants : l'outlet prend la
largeur de ce qu'il contient, et un `w-full` posé dans la page se résout
contre lui. La grille de `examples/life` sortait à la largeur de sa rangée
de boutons, 332 px au lieu de 448. Donner `classes="w-full"` à l'outlet, et
centrer la page avec `mx-auto`.

### Un champ `w-full` dans un hstack avec wrap forme une pile

`w-full` consomme toute la ligne. Pour une barre qui doit se replier, donner au
champ une base et `grow`, ou changer explicitement de structure au breakpoint.

## Handlers, serveur et sécurité

### Pas de lambda ni de closure pour une action serveur

L'identité signée d'un handler est un chemin importable. Utiliser un callable
au niveau module ou `functools.partial` avec des arguments sérialisables.

### Le code applicatif synchrone peut être concurrent

Les `def` sont exécutés dans un threadpool. Deux actions peuvent donc modifier
la même ressource en parallèle ; protéger les read-modify-write dans le
backend ou avec le verrou prévu par l'état.

### `TestClient` doit exécuter le lifespan

Utiliser `with TestClient(app) as client:` lorsque le test dépend des routes,
du broker ou des ressources initialisées au démarrage.
Passer l'objet `Bretzel`, pas `app.fastapi` : sans le middleware de Bretzel,
la page lève « No render context is active ».
Chaque `with TestClient(app)` redémarre l'app, et le démarrage refait le
stockage en mémoire : un second client ouvert APRÈS des requêtes efface ce
qu'elles ont écrit. Ouvrir tous les clients d'un test d'un coup
(`with TestClient(app) as a, TestClient(app) as b:`), sinon le test passe à
vide — mesuré par mutation sur `test_a_session_key_opens_its_session.py`.

### Une lecture par requête ne vit pas au niveau module

`Language()`, `Screen()` et tout ce qui les lit (le `tr(en, fr)` des apps
bilingues) rendent la valeur de LA REQUÊTE. Évalués une seule fois — une
constante de module, un corps de classe, `@page(title=…)`, un défaut
d'argument — ils ne voient aucune requête : repli silencieux sur la langue
par défaut, pour tout le monde. Un `lru_cache` fait pire : il fige la valeur
du premier visiteur. Une table traduite est une fonction appelée au rendu ;
un titre de page dépendant de la langue s'écrit `ui.title(…)` dans la page.
Gardé pour `tr()` par `test_a_translation_is_resolved_per_request`, et pour
`text()` dans un `reactive_prop(default=…)` par
`test_framework_words_go_through_the_table`.

### Une requête de base ne vit pas au niveau module non plus

Une constante de module qui interroge la base — les choix d'un filtre de
colonne, typiquement — rend l'IMPORT dépendant du disque : schéma absent sur
un clone neuf, vues en reconstruction par un autre processus sous
`pytest -n`, valeurs figées au démarrage. Appeler `init_db()` avant les
imports ne fait que déplacer la course. La valeur se construit dans une
fonction appelée au rendu (`columns()` dans
`examples/atelier/features/tasks.py`).

### `networkidle` n'arrive pas avec SSE

Une page qui maintient un flux SSE n'atteint pas l'inactivité réseau. Attendre
un élément ou une condition métier précise dans les probes navigateur.

### Un 502 ferme `EventSource` pour de bon

`EventSource` retente seul un flux coupé, mais une reprise qui reçoit autre
chose qu'un `200 text/event-stream` — le 502 d'un proxy pendant un redémarrage —
le ferme définitivement (`readyState === CLOSED`). Le runtime le rouvre lui-même
avec un délai croissant, puis relit toutes les zones abonnées : le broker ne
rejoue pas ce qui a été diffusé pendant la coupure (`00_index.js`, `ensureSse`).
Côté navigateur, la coupure s'affiche en `ERR_HTTP2_PROTOCOL_ERROR` derrière
Cloudflare ; c'est le redémarrage, pas une erreur de protocole. Gardé par
`test_the_live_stream_survives_a_502`.

### Les clés de signature ont des usages séparés

Ne pas signer directement avec `secret_key`. Utiliser les clés dérivées du
contexte pour les actions, le CSRF et l'authentification. Un test qui construit
un faux contexte doit fournir les mêmes clés que le pipeline réel.

### Seul `Bearer` dispense du CSRF, jamais `Authorization` en entier

Le CSRF dispense du token une requête qui porte `Authorization: Bearer` : le
navigateur ne joint jamais ce jeton de lui-même. Élargir à tout l'en-tête
`Authorization` ouvrirait le trou : après un défi 401, le navigateur met les
identifiants `Basic` en cache et les rejoue sur chaque requête vers
l'origine — un identifiant ambiant, comme le cookie. Le contrôle d'`Origin`,
lui, reste : une origine admise par `cors_origins` peut poser l'en-tête ET
porter le cookie de la victime, que l'identité lit en premier. Gardé par
`test_other_authorization_stays_checked` et
`test_bearer_from_an_untrusted_origin_is_rejected`.

### Une route d'API sauvegarde au début de la réponse, pas après

Une route de `app.fastapi` voit son état typé sauvegardé quand la réponse
commence, et seulement pour un succès. Ce qu'elle écrit APRÈS — dans le
corps d'une `StreamingResponse`, dans une tâche de fond — n'est pas
enregistré, sans erreur. Écrire l'état avant de rendre la réponse
(`render_context._save_route_state`).

### Un POST d'action en TestClient re-rend toutes les zones dépendantes

Sans en-tête `X-Bretzel-Zones`, une action re-rend toutes les zones qui
dépendent de l'état muté, même absentes de la page. Un test qui compte les
fragments d'une réponse doit poser l'en-tête comme le runtime.

### Git Bash réécrit un argument `/route` en chemin Windows

`py script.py /button` reçoit `C:/Program Files/Git/button` : un filtre de
routes ne correspond plus à rien et un script de fumée affiche « 0
erreur » sans avoir rien testé. Préfixer `MSYS_NO_PATHCONV=1`.

## Où mettre une découverte

- Contrat actuel réutilisable : ici, sous le thème correspondant.
- Dette ou comportement non résolu : `.claude/work/todo.md`.
- Mesure ponctuelle ou récit d'audit : `.claude/work/`, puis suppression une
  fois les actions traitées.
- Preuve durable : un test ciblé ou une gate de cohérence.
