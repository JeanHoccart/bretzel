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

### Les identités doivent survivre aux rendus partiels

Un `bz-id` calculé uniquement depuis la position courante change lorsqu'un
sous-arbre est rendu seul. Utiliser les helpers d'identité du socle et une
`key=` métier pour les collections réordonnables.

### Custom elements et morph

Le morph peut remplacer les enfants gérés par un custom element. Le composant
doit définir explicitement ce qui est préservé et réinitialiser son état après
swap. Une écriture DOM transitoire ne doit pas être stockée dans un attribut
que le rendu serveur possède.

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

### Les icônes se dimensionnent par `font-size`

`iconify-icon` peint un glyphe en `1em`. Les classes `text-*` fixent donc sa
taille ; `w-*` et `h-*` ne suffisent pas.

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

### `networkidle` n'arrive pas avec SSE

Une page qui maintient un flux SSE n'atteint pas l'inactivité réseau. Attendre
un élément ou une condition métier précise dans les probes navigateur.

### Les clés de signature ont des usages séparés

Ne pas signer directement avec `secret_key`. Utiliser les clés dérivées du
contexte pour les actions, le CSRF et l'authentification. Un test qui construit
un faux contexte doit fournir les mêmes clés que le pipeline réel.

## Où mettre une découverte

- Contrat actuel réutilisable : ici, sous le thème correspondant.
- Dette ou comportement non résolu : `.claude/work/todo.md`.
- Mesure ponctuelle ou récit d'audit : `.claude/work/`, puis suppression une
  fois les actions traitées.
- Preuve durable : un test ciblé ou une gate de cohérence.
