# Référence Bretzel

Ce dossier explique les mécanismes et les conventions que le code seul ne rend
pas évidents. Il ne contient ni roadmap, ni inventaire manuel de l'API, ni état
de chantier.

Pour connaître la surface livrée :

```powershell
bretzel describe
bretzel describe button
bretzel describe ClientBinding
```

`describe` dérive les signatures, bindings, événements, slots, commandes
impératives et clés de thème depuis le code. Il remplace les anciens
`api-index.md` et `inventory.md`.

## Choisir le bon document

| Besoin | Référence |
|---|---|
| Créer et livrer un composant | [`creating-a-component.md`](creating-a-component.md) |
| Comprendre le socle des composants | [`components.md`](components.md) |
| Décider si une prop est réactive côté client | [`client-reactive-surface.md`](client-reactive-surface.md) |
| Comprendre le routage des kwargs | [`kwarg-routing.md`](kwarg-routing.md) |
| Utiliser les commandes `.open()`, `.set()`… | [`imperative-api.md`](imperative-api.md) |
| Déclarer et persister un état | [`state.md`](state.md) |
| Écrire un handler | [`handlers.md`](handlers.md) |
| Comprendre le rendu et les refreshables | [`render.md`](render.md) |
| Comprendre le runtime `bz-*` | [`runtime.md`](runtime.md) |
| Composer ou surcharger un thème | [`theme.md`](theme.md) |
| Vérifier sécurité, cookies et CSP | [`security.md`](security.md) |
| Structurer une application | [`app-structure.md`](app-structure.md) |
| Livrer une application | [`livrer-une-app.md`](livrer-une-app.md) |
| Construire une navigation responsive | [`screen-responsive-nav.md`](screen-responsive-nav.md) |
| Ajouter une page au playground | [`playground-pattern.md`](playground-pattern.md) |
| Comprendre la carte d'application | [`app-map-model.md`](app-map-model.md) |
| Écrire une gate de cohérence | [`gates.md`](gates.md) |
| Écrire commentaires et docstrings | [`prose-and-comments.md`](prose-and-comments.md) |
| Retrouver un piège technique précis | [`traps.md`](traps.md) |

Le travail ouvert et les rapports vivent dans [`.claude/work/`](../work/).

## Contrats transverses

1. L'API applicative canonique est en Python. Les directives `bz-*` et les
   attributs de transport sont produits par le framework.
2. Une action serveur passe par un paramètre `on_<event>` ; le framework ajoute
   la route, la signature et les en-têtes nécessaires.
3. Seules les props déclarées dans `BINDABLE_PROPS` acceptent un
   `ClientBinding`. `bretzel describe <composant>` les affiche.
4. Les commandes d'instance sont write-only. Pour partager ou lire une valeur,
   utiliser un binding explicite.
5. Un champ de formulaire lié reçoit son `name` automatiquement.
6. Les modules forment un graphe d'import acyclique. Le socle ne dépend pas des
   couches applicatives.
7. Les exemples montrent l'usage public et restent lisibles sans plomberie
   interne.
8. Une nouvelle règle structurelle est protégée par une gate qui prouve aussi
   qu'elle détecte le défaut visé.

## Entretien

- Changement de surface publique : mettre à jour les docstrings introspectées
  et vérifier avec `bretzel describe`.
- Changement de mécanisme : mettre à jour la référence de couche concernée.
- Dette nouvelle : l'ajouter à `.claude/work/todo.md`, avec sa preuve.
- Fichier de référence ajouté ou supprimé : mettre cet index à jour.
- Récit daté ou correction terminée : le retirer de la référence vivante ; Git
  conserve l'historique.
