# Kwarg routing — `Component.__init__`

Référence concise sur où vont les kwargs d'un composant Bretzel et
ce qui est bindable.

**À lire** quand tu te demandes "qu'est-ce qui se passe avec
`ui.X(foo=binding)` ?", ou quand tu ajoutes un kwarg / un escape
hatch au framework.

---

## Le contrat reactive — `BINDABLE_PROPS`

Chaque composant déclare explicitement la liste des props qui
acceptent un `ClientBinding` :

```python
class Button(Component):
    BINDABLE_PROPS: ClassVar[tuple[str, ...]] = (
        "label", "disabled", "loading",
    )
```

**Tout binding sur une prop absente de cette liste lève
`ComponentUsageError`** à la construction. Plus de silent SSR-freeze.

### Pourquoi ce contrat existe

L'ancien design promettait "tout prop scalaire est reactive", mais
en pratique certains composants fuitaient (color/size sur Input ne
recomposaient pas leurs classes par exemple). Le nouveau contrat est
explicite : les seuls props bindable sont ceux du `BINDABLE_PROPS`.

Et le runtime a été simplifié en conséquence : plus de helper
`$bz.compose` côté JS (mai 2026 — fichier `09_compose.js` supprimé).
La composition de classes reactive pour `classes=binding` passe
maintenant par la directive `bz-class` (elle accepte une string et
préserve le `class=` statique) ; les axes variant/size/color sont
design-time et bakés au render serveur.

> ⚠️ **Ne pas ré-écrire `:class`.** L'expression client inline
> (`:class="'<static>' + ' ' + (binding || '')"`) était le mécanisme V2
> Alpine — le runtime V3 ne lit que les 14 directives `bz-*` <!--count:runtime_directives-->, donc elle
> n'a jamais rien fait, en plus de supprimer le `class=` statique.
> Corrigé le 2026-07-27, gaté par
> `tests/consistency/test_reactive_classes_universal.py`.

### Critère pour rester dans `BINDABLE_PROPS`

**Le test en 3 temps vit dans
[`client-reactive-surface.md`](client-reactive-surface.md) § *La règle*.**
Ce fichier-ci porte la **matrice** (qui a quoi), pas le critère.

> ⚠️ Cette section énonçait son propre critère jusqu'au 2026-08-01, et il
> avait divergé : elle admettait « l'état reflète une source externe
> (websocket, polling, sync API) », qui n'apparaît nulle part dans la
> règle figée le 2026-07-16. Une règle recopiée à quatre endroits dérive
> à quatre vitesses — d'où le pointeur.

Ce qui suit reste vrai et sert la matrice ci-dessous : tout ce qui n'est
pas retenu — variant / size / color / type / pattern / icons, etc. —
**reste statique**. Si tu as besoin de dynamique sur une prop
non-bindable, c'est du conditional render serveur :

```python
ui.badge(
    label=state.task.title,
    color="success" if state.task.done else "error",
)
```

Le composant re-render quand `state.task` change, avec la nouvelle
color baked dedans. Pas de reactive surface inutile.

### Matrice — `BINDABLE_PROPS` par composant (règle figée 2026-07-16)

> Verdicts dérivés de la règle « driver client, sinon serveur » — cf.
> `client-reactive-surface.md` § *La règle*. Miroir machine gardé par
> `tests/consistency/test_bindable_surface.py` (le code EST la source ;
> ce tableau doit rester synchro, le gate rougit sinon). `⇄` = two-way
> (`writes=True`), `→` = one-way, `∅` = statique.

> **La matrice est dérivée à la demande** par `bretzel describe`, section
> *Surface bindable*, depuis
> `BINDABLE_PROPS` et `TWO_WAY_PROPS`. `⇄` = le client ÉCRIT la valeur,
> `→` = lecture seule, absent = statique.
>
> **Pourquoi elle a quitté ce fichier.** `test_bindable_surface` la gardait
> *indirectement* : il rougit quand la surface bindable change, ce qui
> force à mettre le funnel à jour — il ne vérifie pas que la mise à jour a
> été faite **juste**. Soixante-dix lignes recopiées à la main derrière un
> rappel manuel, c'est un délai avant dérive, pas une garantie. Dérivée,
> l'étape manuelle disparaît.

### Les verdicts qui ont demandé une décision

La matrice dit *quoi*. Ces six-là disent *pourquoi* — c'est la part qui ne
se dérive pas, et la seule qui vaut d'être écrite ici.

- **`TimePicker`** — `min`/`max` sont ∅, contrairement à la famille date.
  La règle ne les admet qu'au titre de la contrainte croisée d'un range
  (`fin.min = début`), qui n'existe pas sur une heure isolée.
- **`SignaturePad`** — `value`⇄ est la data-URL PNG du tracé, que le
  client écrit en dessinant. ⚠️ Y lier un `ClientState` renvoie le PNG
  **à chaque POST**.
- **`Slider`** — `min`/`max` ∅, bakés statiques : ce sont des bornes de
  conception, pas des valeurs que quiconque édite.
- **`Resizable`** — `sizes`⇄ parce que l'utilisateur l'édite en tirant une
  poignée : driver client au sens strict. `ResizablePanel.min_size` est
  une CONTRAINTE, elle ne change qu'au re-render serveur.
- **La famille DnD** (`Dropzone` / `Draggable`) — `()`. Ce qui bouge est
  de l'état **serveur**, muté par `on_move` ; rien ne transite par le
  client.
- **Les charts** — `()`. Les données arrivent par `@refreshable`, pas par
  binding.

**Sémantique du `()` vs `None`** :
- `()` (tuple vide) = audité, **rien n'est bindable** sur ce composant. Tout binding lève `ComponentUsageError`.
- `None` (sentinel) = **non audité**, check skippée, comportement legacy. Aucun composant Bretzel n'utilise plus cette valeur — toujours déclarer un tuple explicite, vide si nécessaire.

**`reactive_prop` non-bindable — c'est OK** :

Certains composants déclarent un prop via `reactive_prop()` SANS l'inclure dans `BINDABLE_PROPS`. Exemple : `name: str | None = reactive_prop(default=None, emit_attr=False)` sur Input, Checkbox, Select, Tabs, Pagination, etc.

C'est intentionnel. Le `reactive_prop()` decorator sert ici uniquement à :
- Faire reconnaître `name=` comme prop connue par `split_kwargs` (au lieu de tomber dans `_raw_attrs`)
- Donner accès à la valeur via `_reactive_values.get("name")` au render

Pas de réactivité réelle — la matrice `BINDABLE_PROPS` enforce qu'un binding sur `name=` lève `ComponentUsageError`. En pratique : `name=` accepte literal + server-resolved string, refuse ClientBinding. **Ne pas s'inquiéter de la "fausse" reactive_prop — c'est juste de la plomberie kwarg-routing.** Convention : si tu rajoutes un prop statique qui doit traverser `_reactive_values`, déclare-le `reactive_prop()` ET ne l'ajoute PAS à `BINDABLE_PROPS`.

### Modifiers universels — toujours bindable

Ces kwargs sont reserved, popés avant le check, bindable sur tous
les composants :

| Kwarg | Mécanisme |
|---|---|
| `visible=binding` | `bz-show + prestamp display:none` post-render (universal modifier) |
| `tooltip=binding` | Tooltip wrap dont le panel utilise `bz-text` |
| `classes=binding` | `bz-class="$bz.state.X.Y"` posé sur le vrai root par `_apply_universal_modifiers` — donc **tous** les composants, pas seulement ceux qui appellent `apply_class_attrs`. La composition statique du thème reste dans `class=` : `bz-class` ne retire que les classes qu'il a lui-même ajoutées |
| `style=binding` | `bz-attr:style="$bz.state.X.Y"` (résolu par `path_of`) |

---

## Le routing kwarg — 5 buckets (+ 2 étapes autour)

`split_kwargs` (`attrs.py`) carve les kwargs en **5 buckets** (lignes 2→6
ci-dessous). Autour, le constructeur **pop d'abord les reserved** (ligne 1,
*avant* `split_kwargs`) et **lève** si un composant s'égare dans le raw HTML
(ligne 7, *après*). Vue d'ensemble :

> 🤖 **La table des seaux est GÉNÉRÉE** — elle vit dans
> `bretzel describe` § *Routage des kwargs*, dérivée des
> constantes du socle (`RESERVED_KWARGS`, `_PASSTHROUGH_PREFIXES`,
> `_DEAD_ALPINE_PREFIXES`, `_RAW_HTML_PREFIXES`, `_RAW_HTML_NAMES`).
> La commande relit ces constantes à chaque exécution ; aucun snapshot n'est
> maintenu dans le dépôt.
>
> **Pourquoi elle a quitté ce fichier.** Écrite à la main, elle portait le
> 2026-08-16 **trois affirmations fausses en même temps** — et les neuf
> gates de doc du dépôt étaient toutes vertes, parce qu'elles vérifient
> des chemins, des symboles et des inventaires : des choses *décidables*.
> « Ce paragraphe décrit-il encore le comportement ? » ne l'est pas.
>
> Trois gates candidates ont été mesurées puis écartées : sur les
> constantes citées (population 3, trois faux positifs sur trois), sur le
> vocabulaire Alpine étendu au funnel (~60 exceptions, presque toutes du
> récit légitime), et sur la fraîcheur par co-changement git (**9 docs sur
> 11 en retard en permanence** — un signal toujours allumé n'est pas un
> signal). Le seul remède qui survit à la mesure : **ne pas écrire la
> partie décidable**. Ce fichier garde le *pourquoi*, qui ne dérive pas.

> ⚠️ **Trois corrections datées, parce que cette table a menti longtemps.**
>
> - **Ligne 2** annonçait `:foo` / `@foo` / `x-foo` comme passthrough. **Faux
>   depuis le 2026-07-30** : ils LÈVENT (`reject_dead_alpine_attr`), et
>   `_PASSTHROUGH_PREFIXES` ne vaut plus que `("hx-",)`.
> - **Ligne 6 s'appelait « Catch-all raw HTML »**, et c'était exact : tout
>   kwarg inconnu partait dans le DOM en attribut inerte. **Fermé le
>   2026-08-16** — le seau 5 était le seul des cinq à ne rien refuser, ce
>   qui a produit 44 kwargs morts sur `examples/`, dont `ui.input(label=…)`
>   sur 22 sites rendant `<input label="…">` sans aucun libellé.
> - **L'ancien avertissement disait que `bz-*` n'est « pas routé comme
>   attribut brut user ». Faux** : mesuré au runtime sur 14 685 tests, six
>   directives `bz-*` passent bien par ce seau quand on les écrit en
>   kwarg. Elles y sont désormais **déclarées**, pas tolérées.
>
> L'échappatoire n'est pas fermée, elle est **explicite** : préfixes
> `aria_` / `aria-` / `data_` / `data-` / `bz-`, plus les noms exacts
> `class_`, `role`, et la famille de l'ancre (`href` / `target` / `rel` /
> `download`, débloquée par `tag="a"`). Tout le reste lève, avec un
> message qui pointe `attrs={...}` et `bretzel describe <composant>`.
>
> **Limite connue** : la validité d'un attribut HTML dépend du TAG RENDU,
> que `split_kwargs` ne connaît pas (`tag=` est retiré avant). Donc
> `ui.button(href=…)` sans `tag="a"` passe encore et reste inerte —
> `bretzel check` le voit, lui, puisqu'il lit le call-site.

Les catégories 3 (reactive prop) et 4 (named slot) sont soumises au
check `BINDABLE_PROPS`. Les autres ne le sont pas (les reserved gèrent
leur propre binding, les events ne sont pas du binding, les raw* sont
l'escape hatch explicite de l'utilisateur).

### Normalisations cachées (catégorie 6)

- `aria_label` → `aria-label` (underscore → dash)
- `data_testid` → `data-testid`
- `class_` → `class` (trailing `_` strip — Python reserved)
- `for_` → `for`

---

## Pièges anciens (résolus par le contrat)

Ces problèmes ont disparu avec `BINDABLE_PROPS` :

- **Silent SSR-freeze** quand un binding était passé à un prop "techniquement reactive mais pas câblé". Maintenant erreur loud.
- **Matrice par-composant à mémoriser**. Maintenant un seul attribut de classe (`BINDABLE_PROPS`) lisible directement dans le code.
- **Promesse "toute prop est reactive" non tenue**. Maintenant promesse explicite et limitée.

---

## Comment auditer un composant pour le passage en strict

1. Lister tous les props (reactive_prop + NAMED_SLOTS).
2. Pour chacun, demander : "est-ce qu'un utilisateur a un cas concret où il veut binder ça à du state ?". Si non → static.
3. Critère "essentiel" : data du composant + flags d'état (disabled/loading/open/checked). PAS la config visuelle.
4. Déclarer `BINDABLE_PROPS = ("...", ...)` sur la classe.
5. Si des tests existants binding des props non-bindables → soit fix le test (binding raise), soit utiliser un test-only subclass.
6. Mettre à jour le banc de test playground : la card Client playground ne montre que les bindables, point.

---

## Liens

- `components.md` — règles dures sur l'API publique
- `state.md` — comment ClientBinding / ClientExpression se sérialisent
- `runtime.md` — comment `$bz._resolveIcon`, `bz-attr`, les actions `hx-post` sont consommés côté client (note : `$bz.compose` a été retiré mai 2026)
- `playground-pattern.md` — gabarit du banc de test
- `traps.md` — pièges connus
