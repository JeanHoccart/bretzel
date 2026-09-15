# Client-reactive surface — la règle d'or

> **Une prop n'accepte une `ClientBinding` que si elle figure dans le
> `BINDABLE_PROPS` du composant.** Tout autre binding lève
> `ComponentUsageError` à la construction. Les collections d'items
> passent par `@refreshable` (server-driven, avec `ui.each(items,
> key=...)` pour l'identité keyée — **existe**). Le rendu de liste
> *client-driven* (une `ClientBinding[list]` re-rendue sans aller-retour)
> n'est pas encore livré (Phase 4).

La surface reactive est curated par composant — pas universelle. Pour
la liste exhaustive, voir `kwarg-routing.md` § *Matrice BINDABLE_PROPS*.
Pour de la dynamique sur un prop non-bindable (color, variant, size,
icon, ...), faire un conditional render côté serveur :
``ui.badge(label, color="error" if state.failed else "success")``.

---

## La règle — quelle prop mérite un binding (figée 2026-07-16)

Bretzel a un modèle : **le serveur est source de vérité, une mutation
d'état → `@refreshable` re-render le sous-arbre avec la nouvelle valeur
bakée dedans.** Corollaire décisif :

> **Un binding client ne se justifie que s'il existe un *driver côté
> client*.** Si une prop ne change QUE quand le serveur re-render,
> `@refreshable` fait déjà le boulot — le binding n'ajoute que de la
> surface pour rien.

Le test à appliquer à **chaque** prop, dans l'ordre :

1. **L'utilisateur édite-t-il cette valeur en interagissant avec CE
   composant ?** (frappe, toggle, sélection, ouverture) → **⇄ two-way**
   (`reactive_prop(writes=True)`, listé dans `BINDABLE_PROPS`). C'est
   `value` / `checked` / `open` / `month` / la sélection. Le composant
   *est* l'éditeur de cet état.
2. **Sinon : la valeur change-t-elle côté client SANS aller-retour ?**
   (pilotée par un `ClientState` / `ClientExpression` : `disabled =
   form.submitting`, un compteur live, une présence SSE, `active =
   route == "x"`) → **→ one-way** (dans `BINDABLE_PROPS`, pas `writes`).
3. **Sinon** (ne bouge qu'au re-render serveur, ou config design :
   color / size / variant / type / pattern / required / min-max-hors-date
   / accept / total_pages…) → **∅ statique**. Dynamique = conditional
   render serveur.

### Le socle — ce qui mérite un binding, par classe de prop

| Classe de prop | Verdict | Où |
|---|---|---|
| `value` / `checked` / `open` / `month` / sélection | ⇄ two-way | tous les inputs, overlays, tabs, pagination, tree, accordion |
| `disabled` / `loading` / `readonly` | → one-way | actions, inputs (gate par état client : submit en cours, form invalide) |
| slots d'affichage : `label` / `title` / `message` / `text` / `progress.value` / `progress.label` | → one-way | actions, feedback, primitives (texte live via `bz-text`) |
| `active` / `badge` (nav items) | → one-way | sidebar / navbar items (highlight route + compteur live) |
| `status` (avatar) | → one-way | présence live (SSE / polling) |
| `min` / `max` (**famille date uniquement**) | → one-way | date_picker / date_range_picker / calendar — contrainte croisée client-side (`fin.min = début`), câblée via forward au Calendar enfant |

### Exceptions & pièges documentés

- **`min` / `max` sont one-way SEULEMENT sur la famille date.** Sur
  `number_input` / `slider`, `min`/`max` sont **bakés en JSON statique**
  dans le scope JS (pas de chemin réactif) → rester `∅`. Les rendre
  bindables = travail runtime (signaux `_min`/`_max`), pas une ligne de
  matrice. Différé (2026-07-16).
- **`form_field.error` est ⇄ two-way** : le client y écrit `""` sur
  `input` (`bz-on:input="{path} = ''"`, `form_field.py`) pour effacer
  l'erreur dès que l'utilisateur corrige. Seul champ « message » two-way.
- **Config / contrainte = ∅** : `required`, `multiple`, `accept`,
  `total_pages`, `placeholder`, `dismissible`, `avatar.src/initials`.
  Elles ne changent qu'au re-render serveur → `@refreshable`. (Coupées
  du bindable 2026-07-16 : elles étaient câblées mais sans driver client
  réel — surface opinionated resserrée.)

---

## 1. Cinq sous-catégories de bindings scalaires

Chaque sous-catégorie = un mécanisme JS unique. Tu bindes une prop
listée dans `BINDABLE_PROPS`, le framework choisit le bon canal. Tu
n'as jamais à écrire le canal toi-même.

| # | Catégorie | Exemples de props | Mécanisme JS |
|---|---|---|---|
| **A.1** | DOM attr réel | `disabled`, `checked`, `value`, `href`, `src`, `open`, `placeholder`, `min`, `max`, `name`, `required`, `readonly` | `bz-attr:<attr>` one-way / `bz-model` two-way |
| **A.2** | Slot textuel | `label`, `message`, `title`, `body`, `tooltip`, `error_text`, `text` (Heading), `initials` (Avatar) | `<span bz-text="$bz.state.X.Y">` via `Component.emit_text_slot` |
| **A.3** | Visibilité / mutex structurel | `visible=`, `loading=` (spinner ↔ icon mutex), `dismissible=` | `bz-show + prestamp display:none`, branches émises en parallèle via `Component._cloak_show` |
| **A.4** | Référence d'icône | `icon`, `icon_left`, `icon_right` | `:icon="$bz._resolveIcon(state, defaultSet)"` sur `<iconify-icon>` |
| **A.5** | Style / classes extras user | `classes=`, `style=` | `classes=` → `bz-class="$bz.state.X.Y"` (le `class=` statique du thème est **préservé**, `bz-class` ne pilote que les classes qu'il ajoute) ; `style=` → `bz-attr:style` |

## 2. Collections — deux mécanismes, deux usages

| # | Catégorie | Exemple | Mécanisme |
|---|---|---|---|
| **B.1** | Collection statique SSR | `options=[("a","A")]` | Rendu Python, pas de binding |
| **B.2** | Collection mutée par le serveur (filtres, pagination data) | `rows=`, items DB | Section enveloppée `@refreshable`, roundtrip ~50 ms |
| **B.3** | Collection mutée par le **client** sans aller-retour (todos, panier) | rendre une `ClientBinding[list]` côté client (le primitive runtime `bz-for` existe, mais aucune API composant ne l'expose encore) | **Phase 4 — pas encore livré** (≠ `ui.each`, qui est server-side et existe) |

## 3. Discipline

Passer une `ClientBinding[list]` à une prop scalaire `reactive_prop`
lève `ComponentUsageError` au `Component.__init__`. Le message dit
exactement quelle prop, quel type attendu, quel type reçu, et suggère
`ui.each` / `@refreshable`. **Limite connue** : la discipline ne couvre
PAS encore les kwargs hors-`reactive_prop` (`classes=`, `style=`,
positional `label`) — passer une `ClientBinding[list]` y rend
silencieusement de la garbage. Hardening prévu sur le passage au type
discipline généralisée.

## 4. Server-state bindings

`ui.button(disabled=server_state.x)` reste valide : lire un champ
`ServerState` en render scope renvoie la **valeur littérale** au SSR
(il n'existe pas de type `ServerBinding` — juste la valeur), donc le
client ne voit rien de reactive. La page se refresh via `@refreshable`
quand le state serveur bouge.

## 5. Hors-scope (par design)

Trois choses ne sont **pas** reactive, et ne le seront jamais :

- **Event handlers** (`on_click=fn`) — ce sont des callables résolus
  au SSR. Pas de prop reactive.
- **Structural children passés en argument** (`Card([child1,
  child2])`) — composition statique. Pour la reactivité, utiliser
  `@refreshable` ou `ui.each(binding)`.
- **Types** des props (la déclaration `label: str` ne change pas à
  l'exécution).

Une chose est hors-scope par **architecture**, pas par design :

- **Notifications toast** (`ui.notification("Saved", title=...)`) —
  c'est un helper de queue fire-and-forget, pas un composant rendu
  côté Python. Le payload est sérialisé en JSON et consommé par le
  runtime JS qui construit la toast client-side. Une `ClientBinding`
  sur `title=` / `message=` n'est PAS résolue ; passer une binding y
  produira un JSON malformé. À retravailler en Phase 4+ si l'usage
  émerge.

## 6. Helpers framework — où vit chaque mécanisme

| Mécanisme | Helper | Fichier |
|---|---|---|
| Composition de classes statique | `Component.compose_class` | `bretzel/components/base/component.py` |
| Texte réactif | `Component.emit_text_slot` | idem |
| Cloak mutex (bz-show + prestamp display:none) | `Component._cloak_show` | idem |
| Classes / styles extras réactifs | `Component.apply_class_attrs` / `apply_style_attr` | idem |
| Discipline scalaire | `Component.__init__` + `binding_discipline.validate_scalar_binding` | `bretzel/components/base/binding_discipline.py` |
| Contract BINDABLE_PROPS | `Component.__init__` check au moment du split kwargs | idem |
| Wrap icon binding | `Component.adopt_slot(icon_shortcut=True)` | `bretzel/components/base/component.py` |
| JS resolve icon name | `$bz._resolveIcon(name, defaultSet, defaultStyle)` | `bretzel/runtime/_src/06_helpers.js` |
