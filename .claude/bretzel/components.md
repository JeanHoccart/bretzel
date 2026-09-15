# Components — anatomy and rules

Source : `bretzel/components/base/`. Hiérarchie : tout composant hérite de `Component`.

---

## Class-level config (à déclarer en `ClassVar`)

**La liste est exhaustive**, et gatée à jour par
`tests/consistency/test_a_documented_population_is_complete.py` : un
`ClassVar` ajouté à `Component` sans ligne ici fait rougir la suite.
(Elle en a listé 7 sur 16 jusqu'au 2026-08-26 — dont `SEALED_PROPS`,
créé dix jours plus tôt et documenté nulle part.)

| Attribut | Rôle |
|---|---|
| `THEME` | dict (importé depuis `<comp>/theme.py`) |
| `THEME_KEY` | clé sous `app.theme.components` pour fusion utilisateur |
| `DEFAULT_TAG` | tag HTML par défaut (`"div"`, `"button"`, …) |
| `IS_CONTAINER` | `True` = accepte des enfants via `with`. `False` = leaf (Tooltip est l'exception qui wrap son trigger). |
| `COLLECTION_OWNER` | ce composant rend une COLLECTION, et sous quel nom. `None` = non. Déclaré plutôt que deviné : `test_collection_owner_decides_the_api` détecte les collections (le rendu grandit-il avec la donnée ?) et exige la déclaration. |
| `NAMED_SLOTS` | tuple des kwargs typés (`("icon", "icon_right")`) |
| `ICON_SLOTS` | sous-ensemble de `NAMED_SLOTS` qui accepte le string-shortcut (`"trash-2"` → `Icon("trash-2")`) |
| `EVENTS` | tuple des events supportés (`("click", "focus", "blur")`). **Tout `on_<event>` non listé → erreur.** |
| `SEALED_PROPS` | props héritées que ce composant REFUSE à l'appel — `HStack` scelle `direction`, épinglée à `"row"`. `bretzel.introspect` les soustrait de la fiche : annoncer un paramètre qui lève est la même faute que d'en cacher un qui marche. |
| `RESPONSIVE_THEME_KEYS` | les clés de `THEME` dont les valeurs peuvent ressortir PRÉFIXÉES par un breakpoint (`gap={"base": "sm", "md": "lg"}` → `gap-2 md:gap-6`). Sans la déclaration, `md:gap-6` n'existe dans aucun fichier, donc n'atteint pas le CSS compilé : le gap disparaît **en prod** et pas en dev. |
| `RESPONSIVE_PROPS` | les props qui ACCEPTENT un dict de paliers. ⚠️ À ne pas confondre avec `RESPONSIVE_THEME_KEYS` juste au-dessus, qui nomme des tables de thème et sert à la safelist : celui-ci nomme des PROPS et sert au REFUS. Un dict de paliers sur un prop absent d'ici lève un `ComponentUsageError` qui nomme le composant, le prop, et ce qui est gradué — sans quoi il mourrait trois frames plus bas sur `unhashable type: 'dict'` (91 couples étaient dans ce cas avant le 2026-09-04). Vide par défaut, et c'est le bon défaut : cinq props sur ~600 sont graduées — `flex.direction`/`gap`, `grid.cols`/`gap`, `resizable.gap`, `carousel.per_view`. Tout le reste est un choix STRUCTUREL, qui appartient à `if Screen().is_mobile:` dans la mise en page. |
| `ALLOW_MULTI_SERVER_EVENTS` | `True` = cette racine porte plus d'un handler serveur. Le défaut est un seul `hx-post` par racine. |
| `IMPERATIVE` | les méthodes de l'API impérative (`.open()`, `.set()`…). Source unique et introspectable de cette surface — cf. `imperative-api.md`. |
| `BINDABLE_PROPS` | les props qui acceptent une `ClientBinding`. Cf. `client-reactive-surface.md`. |
| `BINDABLE_CARRIERS` | pour un binding qui n'atterrit pas sur la racine : quel élément le porte. |

**Deux de plus sont DÉRIVÉS par la métaclasse, pas écrits à la main** —
les déclarer lève : `TWO_WAY_PROPS` (dérivé de `reactive_prop(writes=)`)
et `AUTONAME_FROM` (dérivé de `names_field=`). Le fait vit sur la prop,
pas trente lignes plus bas ; cf. `reactive_prop.py`.

⚠️ `THEME_TABLES` n'est PAS un `ClassVar` du socle : c'est une convention
locale à la famille `Flex` (« quelle table de thème lit ce prop gradué »).
Un seul composant la déclare aujourd'hui — si un deuxième s'y met, la
question de la promouvoir se pose.

---

## Routage des kwargs (`split_kwargs`)

À l'`__init__`, les kwargs sont triés en 5 buckets :

1. **Reactive props** (déclarés via `reactive_prop(default=…, emit_attr=…)`). Stockés sur `_reactive_values` ; les `ClientBinding` vont en plus dans `_binding_metadata`.
2. **Named slots** (présents dans `NAMED_SLOTS`). Stockés sur `_slot_components`.
3. **Event handlers** (`on_<event>` où `<event>` est dans `EVENTS`). Routés via `register_action` → `action_attrs` : `hx-post` (route action) + `hx-trigger="<event>"` (parfois `"<event> from:#<root>"` pour la délégation) + `data-bz-sig`.
4. **attributs bruts** (clés commençant par `:`, `@`, `x-`, `hx-`). Émis verbatim.
5. **Raw HTML attrs** (le reste). Nom normalisé (`_` → `-`, trailing `_` strip), valeur émise telle quelle.

> **Précédence réelle** : ce classement est *conceptuel*. Dans le code (`attrs.py`), le bucket **attributs bruts** (passthrough `:@x-hx-`) est **testé en premier**, avant reactive props / slots / events. L'ordre 1→5 ci-dessus liste les buckets, pas leur priorité de matching.

→ Si tu vois `aria_label="…"` dans le code, ça atterrit comme `aria-label="…"` dans le HTML.
→ Si tu vois `**{"@click": "..."}`, ça atterrit verbatim — c'est l'**escape hatch** (à éviter en code app, cf. `traps.md`).

---

## Reactive props — l'interface universelle

```python
class MyComp(Component):
    color: str = reactive_prop(default="primary", emit_attr=False)
    size: str = reactive_prop(default="md", emit_attr=False)
    open: Any = reactive_prop(default=False, emit_attr=False)
```

Au render, accès via `self._reactive_values.get("name")` pour la valeur brute (litéral ou résolu serveur), `self._binding_metadata.get("name")` pour le `ClientBinding` si binding passé.

⚠️ **Ne jamais** lire un binding via `_reactive_values.get(name)` + `isinstance(..., ClientBinding)` — la valeur stockée dans `_reactive_values` est la **valeur sous-jacente** (pour le SSR), pas l'objet binding. Le check est silencieusement toujours False. Cf. `traps.md`.

**Trois shapes acceptées par TOUT prop** (contrat universel) :

```python
ui.dialog(open=False)                  # litéral
ui.dialog(open=server_state.is_open)   # server-resolved (raw value au render)
ui.dialog(open=client_state.is_open)   # ClientBinding (réactif live)
```

→ Si un composant ne supporte qu'une des trois pour un prop censé être universel, **c'est un bug**, pas une feature. Voir `traps.md` pour les cas connus.

---

## Règles dures sur l'API publique

1. **Méthodes publiques d'instance UNIQUEMENT pour la famille write-only** : `.open()` / `.close()` / `.toggle()` / `.set(value)` / `.clear()` (+ aliases sémantiques par famille selon [`imperative-api.md`](imperative-api.md)). Retournent du `str` (source client), même contrat que `ClientBinding.set/toggle/clear` — donc s'utilisent en `on_click=instance.open()` comme un binding. Si une binding est fournie à la construction sur la prop concernée, la méthode écrit dans la binding (write-through) ; sinon elle dispatch un DOM event que la root écoute. **AUCUNE méthode de lecture exposée** (pas de `.value`, pas de `.is_open`) — pour lire un état côté Python, passer par un `ClientBinding` explicite (le contrat est inchangé).
2. **Helpers par composant tolérés UNIQUEMENT pour la famille write-only de la règle 1**. `ClientBinding` reste la primitive universelle pour tout besoin partagé (lecture, multi-composants qui dépendent du même état, persistance, server-readability). Les méthodes d'instance existent en plus, pas à la place — leur seul rôle est de **lever le coût déclaratif de state dans les contextes répétitifs** (per-row overlays, listes, tables). Pour tout autre besoin (action métier custom, primitive partagée, événement complexe), passer par le binding — pas de helper ad hoc.
3. **Aucun `name=`, `@click=`, `bz-show=`, `bz-data=` etc. dans le code user des exemples / démos.** Ces extras-HTML/JS sont des **escape hatches** — possibles pour la flexibilité, jamais l'idiom canonique. Si une démo en contient, c'est un signal que la framework manque une primitive (à ajouter), pas un pattern à reproduire.
4. **L'API V1 reste la référence côté user-facing** (noms / signatures / patterns d'usage). En cas de doute → lire V1 avant de déroger. *(L'ancienne formulation « justifier toute déviation dans le docstring » avait une adoption mesurée de 0/76 — abandonnée le 2026-07-15 : les déviations actées vivent dans EVOLUTION.md + les messages de commit, pas dans chaque docstring.)*
5. **Constantes de module** : `_UPPER` = privé au module (`_BADGE_THEME` interne), `UPPER` = exporté / API cross-module (`BADGE_THEME`, `SERVER_ACTION_ATTRS`). C'est PEP 8 — le préfixe `_` encode la visibilité, il n'est pas « en surplus » (l'ancienne règle « `_LABEL_MAX` → `LABEL_MAX` » était une erreur de lecture de PEP 8, corrigée le 2026-07-15 ; le code est uniforme sur 43 call-sites). ⚠️ En revanche les **attributs JS internes de `bz-data`** (`_pick`, `_highlight`) sont visibles dans DevTools — préférer `pick`, `highlight`. *(`_serverSync` est un marqueur délibéré, exempté.)*

## Autoname — comment `name=` disparaît du code app

Quand un composant déclare `AUTONAME_FROM = "<reactive_prop>"` (ex: Input → `"value"`, Checkbox → `"checked"`), `emit_attrs` regarde `_binding_metadata.get(<prop>)` à chaque render :

- Si le user a passé un `ClientBinding` / state field → pose `attrs["name"] = binding.field_name` automatiquement (sauf si `name=` explicite passé, qui gagne toujours).
- Sinon → pas de `name`, le composant n'apparaît pas dans la form data.

Conséquence côté code app :

```python
class Draft(PageState):
    email: str = field(default="")
    subscribe: bool = field(default=False)

ui.input(value=draft.email)            # → name="email" auto
ui.checkbox(checked=draft.subscribe)   # → name="subscribe" auto

def submit(email: str, subscribe: bool):  # signature-injected
    ...
```

⚠️ **`AUTONAME_FROM` ne se déclare PLUS à la main** — le ClassVar est
**dérivé** de `reactive_prop(names_field=True)`, et la métaclasse
**refuse** au chargement une classe qui l'écrit elle-même (« deux
endroits pour un seul fait »). `names_field=True` implique
`writes=True` : un champ dont le client n'écrit pas la valeur n'a pas de
`name=` à dériver. *(Cette section disait le contraire — « tout nouveau
composant form-bound déclare son `AUTONAME_FROM` au niveau classe » —
jusqu'au 2026-08-13, où `signature_pad` a suivi la consigne et s'est fait
refuser au premier import.)*

**Composants qui opt-in à l'autoname aujourd'hui** (source de vérité = la
prop qui porte `names_field=True`) : tous les inputs à valeur — Input,
Textarea, Select, Checkbox (`checked`), Switch (`checked`), RadioGroup,
Combobox, NumberInput, Slider, ToggleGroup, DatePicker, DateRangePicker,
Calendar, SignaturePad — plus Pagination et Tabs (navigation), Accordion
(data), Carousel et Resizable (layout).

---

## Slots — children, named, icon-shortcut

- **Children par `with`** : auto-registration sur le `parent_stack` (cf. `render.md`). Disponibles via `self._render_children()` dans le `render()`.
- **Named slots** (`NAMED_SLOTS = ("icon", "footer")`) : passés en kwargs typés. Dispo via `self._slot_components.get("icon")`.
- **Icon shortcut** (`ICON_SLOTS = ("icon_left", "icon_right")` sur Button — choix du composant) : si la valeur est une string, auto-wrap en `Icon(name)`. Permet `ui.button("Save", icon_left="check")` au lieu de `ui.button("Save", icon_left=Icon("check"))`.
- **Adoption** : `Component.adopt_slot(value, icon_shortcut=False)` détache le composant slot du `parent_stack` actif (sinon il rendrait deux fois — une dans le slot, une comme sibling).

---

## Convention — l'accent marque le pair ACTIF

**À ne pas confondre avec la suivante**, et la confusion a déjà eu lieu :
`datatable._head_title` citait « couleur d'un sous-composant embedded »
pour justifier son `color="current"`, alors que cette section-là range
justement Button parmi les composants qui gardent leur couleur de marque.
Ce sont deux règles différentes.

Celle-ci parle d'un **ensemble de contrôles pairs** — les en-têtes
triables d'un tableau, les filtres d'une barre d'outils, les options
d'une liste multi.

**Règle** : dans un tel ensemble, un contrôle au repos prend
`color="current"` (il hérite de l'encre ambiante) ; **l'accent est
réservé à celui qui est ACTIF**, où il porte une information.

Pourquoi : un accent posé partout n'est plus un signal. Une ligne
d'en-tête moitié bleu-accent, moitié gris-muet, avec la coupure qui ne
suit rien que l'œil sache interpréter, c'est le bug qui a produit cette
règle. Une barre d'outils entièrement bleue au repos est le même bug,
dans l'autre sens.

**Corollaire — la variante ne bouge pas avec l'état.** C'est la COULEUR
qui change, pas la boîte : `variant="soft"` au repos ET actif. Une
variante qui change change les métriques, donc la barre saute au moment
même où l'utilisateur pose son premier filtre.

**Sites** : `datatable._head_title` (tri), `datatable._column_filter` +
`_export_link` + « Clear filters » (barre d'outils), `select` /
`combobox` `option_check` (options prises).

---

## Convention — les SURFACES rembourrent, les EMPLACEMENTS non

Question posée le 2026-08-13 en voyant un `signature_pad` collé au bord
de son panneau de `resizable` : un conteneur devrait-il poser un padding
(ou laisser passer le `gap` du parent) pour qu'on ait « un espacement
naturel » ?

**La coupure**, et elle DÉCRIT le code plutôt qu'elle ne l'impose — au
moment où elle a été écrite, les dix composants concernés s'y rangeaient
déjà sans exception :

| | Rembourre ? | Pourquoi |
|---|---|---|
| **Surface** — `card` (échelle `paddings`), `dialog` / `drawer` (`body: px-5 py-4`), `alert`, `banner` | **oui** | elle a son propre chrome et sa propre identité visuelle. Le padding fait partie de ce qu'elle EST. |
| **Emplacement** — `resizable_panel`, `tab panel`, slide de `carousel`, `dropzone`, zone `@refreshable` | **non** | c'est une région de mise en page, pas une surface. L'appelant y met une surface ou un `vstack`. |

**Pourquoi pas de padding par défaut sur un emplacement** : choisir une
valeur, c'est choisir une politique. Un pad collé au bord est *faux*
dans un formulaire et *juste* dans un volet d'éditeur — le conteneur ne
peut pas savoir. C'est mot pour mot l'argument que `render/fusion.py`
porte déjà pour la zone `@refreshable` : « il faudrait en choisir la
valeur, et sous un `vstack(gap="lg")` on rendrait *lg dehors, md
dedans* — une incohérence pour une autre ».

**⚠️ `display: contents` ne transpose PAS.** La zone `@refreshable`
l'utilise (`fusion.py`, gaté par `test_zone_box_is_transparent.py`)
parce qu'elle est une frontière de **transport** : HTMX vise son `id`,
et rien là-dedans ne demande une boîte. Un panneau de `resizable`, une
slide, un `tab panel` **SONT** des boîtes — `basis-0` + `overflow-hidden`
pour l'un, `shrink-0 snap-start` + la largeur de `per_view` pour l'autre,
la superposition en grille pour le troisième. Les rendre transparents
détruirait la fonction. « Zone sans boîte » et « conteneur dont la boîte
est le sujet » sont deux familles, pas deux réglages.

**Si la règle coince un jour** : ce sera un modifier de padding sur la
famille EMPLACEMENT, en une fois, jamais un `padding=` ajouté à
`resizable_panel` seul — le jour où il l'a, `tab panel` et `carousel`
deviennent incohérents, et trois endroits rembourrent au lieu de deux
(principe 4).

---

## Convention — couleur d'un sous-composant embedded

Quand un composant est *visuellement subordonné* (genre Icon dans un
Button, Spinner dans un Button loading, à terme Skeleton dans une
Card), il doit hériter de la couleur de texte de son parent — pas
porter sa propre couleur de marque.

**Règle** : tout composant susceptible d'être embedded déclare son
défaut `color="current"`. Le thème de sa root slot utilise
`text-(--bz-text)` comme d'habitude — la substitution donne
`text-current` qui résout en `color: currentColor` côté CSS, donc
héritage automatique.

**Composants qui suivent la règle aujourd'hui** : Icon, Spinner.

**Composants qui gardent une couleur de marque par défaut** (parce
que visuellement autonomes) : Button (`color="primary"`), Badge
(`color="primary"`), Alert (`color="info"` selon le call site),
Pagination, Progress, etc.

**Pourquoi pas `classes="text-current"` côté parent ?** Tailwind ne
respecte pas l'ordre de la string class lors de la génération CSS —
il ordonne canoniquement dans la feuille. Un `text-primary` baked
dans le thème du sous-composant ET un `text-current` ajouté via
`classes=` côté parent finissent tous deux dans la feuille CSS ; le
gagnant dépend de l'ordre de Tailwind, pas de la string. Le seul
moyen propre est que le sous-composant **n'émette pas** de
`text-{couleur}` baked en premier lieu — d'où le défaut
`color="current"`.

Voir `traps.md` pour le détail historique du bug spinner-on-solid.

---

## Events — déclaration + routage

Chaque composant déclare ses events :

```python
class Button(Component):
    EVENTS = ("click", "focus", "blur", "mouseenter", "mouseleave")

    def __init__(self, ..., on_click=None, on_focus=None, ..., **kwargs):
        super().__init__(on_click=on_click, on_focus=on_focus, ..., **kwargs)
```

La métaclasse vérifie que **chaque event listé a un kwarg `on_<event>` dans `__init__`** (sinon erreur au load time, force un setup correct).

Routage du kwarg `on_<event>` (cf. `handlers.md` pour le détail) :

- `Callable` ou `partial` → `hx-post` (route action) + `data-bz-sig`, via `action_attrs`
- String → `bz-on:<event>="<expr>"` (expression client inline)
- `list[Callable | str]` → décomposé : un callable + N strings émis simultanément

---

## Règle bindable — le seul critère (`dismissible` et tous les flags d'affordance)

**La décision « cette prop va-t-elle dans `BINDABLE_PROPS` ? » se prend
avec UNE règle, et elle est écrite à UN seul endroit** :
[`client-reactive-surface.md`](client-reactive-surface.md) § *La règle*
(test en 3 temps, figé 2026-07-16). Ne la recopie pas ici — elle l'a été
dans quatre fichiers jusqu'au 2026-08-01, et la copie de
`kwarg-routing.md` avait déjà divergé (elle admettait un critère
« source externe : websocket, polling » abandonné depuis).
`test_bindable_rule_is_single_sourced` refuse désormais la re-copie.

Ce qui est propre à cette page, c'est la **conséquence sur les flags
d'affordance** :

**`dismissible` est ∅ partout** (Alert, Banner, Badge, overlays) : c'est
une affordance qui ne change qu'au re-render serveur → aucun driver
client, donc jamais dans `BINDABLE_PROPS`. Pour un × conditionnel :
`ui.badge(label, dismissible=state.validated)` (littéral/server-resolved,
re-rendu quand `state` bouge). *(Historique : Badge.dismissible a été
bindable jusqu'au 2026-07-16 puis coupé — la « famille Chip bindable »
était une exception non justifiée par la règle.)*

Même logique pour les autres flags de config : `required`, `multiple`,
`accept`, `total_pages`, `min`/`max` (sauf famille date, câblée), `src`,
`initials` → tous ∅. La matrice complète vit dans `kwarg-routing.md`
§ *Matrice BINDABLE_PROPS*, verrouillée par
`tests/consistency/test_bindable_surface.py`.

---

## Convention — sélecteur cluster (Tabs, ToggleGroup, … futur Carousel-dots)

Les composants à **cluster d'items sélectionnables** partagent une grammaire visuelle et technique commune. Tabs (line/pill) et ToggleGroup (joined-button bar) sont les deux références ; tout nouveau cluster (Stepper indicator, Carousel dots, future Toolbar group, etc.) doit suivre le même squelette. Le sous-pattern **sliding indicator** (thumb / underline qui glisse, mesuré par `updateIndicator()`) ne concerne que les clusters pill-style — aujourd'hui Tabs uniquement ; ToggleGroup l'a abandonné en retirant son variant `segmented` (juin 2026).

### Driver visuel — `data-selected` pas `aria-pressed`

```html
<button
  data-selected="true"                          {/* SSR initial state */}
  :data-selected="picked === 'a'"               {/* reactive driver */}
  :aria-pressed="picked === 'a'"                {/* a11y only */}
  class="... data-[selected=true]:bg-{color}/15 data-[selected=true]:text-{color} ...">
```

- Le **SSR** stamp `data-selected="true"` sur l'item initialement actif → pas de flash avant le boot du runtime.
- Le **Tailwind variant** `data-[selected=true]:` drive le visuel — plus fiable que `aria-pressed:` (test confirmé avec le browser CDN dev, juin 2026).
- `:aria-pressed` reste pour les screen readers — séparation a11y / visuel.

### Hover preview — 3 états de couleur

Standard à appliquer sur les items :

| État | "Buttons-style" (Tabs `line`, ToggleGroup joined-button bar) | "Pill-style" (Tabs `pill`) |
|---|---|---|
| **base** | `text-muted` | `text-muted` |
| **hover** | `enabled:hover:text-(--bz-text)` (preview color) | `enabled:hover:text-text` (bump neutre) |
| **selected** | `data-[selected=true]:text-(--bz-text)` (+ `bg-{color}/15`) | `data-[selected=true]:text-(--bz-on-solid)` (sur thumb coloré) |

`enabled:` important pour ne pas afficher le hover sur un item disabled.

### Sliding indicator (line / pill / thumb)

Tout indicator positionné par JS-measurement DOIT :

1. Avoir un `data-<comp>-indicator` attribute pour que la méthode `updateIndicator()` puisse le retrouver.
2. Stamper les items avec `data-<comp>-id="<value>"` pour la sélection.
3. Stamper le indicator SSR avec `style="opacity: 0;"` (anti-flash avant mesure).
4. La méthode `updateIndicator()` mesure `btn.offsetLeft + offsetWidth`, écrit `style="transform: translateX(...); width: ...px; opacity: ;"`.
5. `bz-init` wire **5 triggers** : un `bz-effect` sur `picked`, `$nextTick`, `window resize`, `ResizeObserver`, `document.fonts.ready` (optional, pour le font-load).
6. **CRITIQUE** : `@htmx:after-swap.window` re-fire `updateIndicator()` après tout partial refresh. Sinon le morph écrase l'inline-style et le indicator est stuck. Cf. `traps.md` § "Sliding indicator desync après morph".

### Imperative API (calquée Combobox)

```python
.set(value)         # replace selection
.clear()            # empty (scalar "" single, list [] multi)
.focus()            # first non-disabled item
.blur()
.select_all()       # multi-only ; raises sur single
.deselect_all()     # multi-only
```

PAS de `.add(v)` / `.remove(v)` / `.toggle(v)` per-item — les clicks UI s'en chargent ; les mutations programmatiques recomputent la liste et appellent `.set(new_list)`. Garde la surface API étroite.

### Roots `w-fit h-fit` obligatoire

Tout cluster sélecteur DOIT poser `w-fit h-fit` (ou des dimensions explicites) sur sa root, sinon les overlays qui l'enveloppent (Tooltip, Popover) se mal-positionnent à cause du stretch parent. Cf. `traps.md` § "Root inline-flex étirée par un parent flex/grid items-stretch".

---

## Two-way binding via `bz-model` — `_bind_x_model`

Form-input components (text, checkbox, switch, radio, select, future date/color/file pickers, …) doivent émettre un `bz-model="$bz.state.<path>"` quand le user passe un `ClientBinding`, et **dropper** le `bz-attr:<prop>` read-only que `emit_attrs` a déjà posé. Sinon le runtime bind deux fois et le read-only bloque le write-back.

Méthode de base sur `Component` :

```python
def render(self) -> Element:
    input_attrs: dict[str, Any] = {"type": "text", ...}
    input_attrs.update(self.emit_attrs())
    self._bind_x_model(input_attrs, prop="value")
    return Element(tag="input", attrs=input_attrs)
```

Signature : `_bind_x_model(attrs, prop="value", *, binding=None)`. Lit `self._binding_metadata[prop]` par défaut. Pour les composites où le binding vit ailleurs (Radio inherits du group, future DateRangePicker split sur 2 inputs) → passer `binding=parent._binding_metadata.get("value")` explicitement. Retourne le binding (ou `None`) pour brancher sur le fallback littéral si besoin.

Cf. `traps.md` pour le piège du `_reactive_values + isinstance` qui est la cause originelle de cette méthode.

## Composer les classes via le thème — `compose_class`

```python
def render(self) -> Element:
    cls_string = self.compose_class("root", color=color)
    attrs = self.emit_attrs()
    if cls_string:
        attrs["class"] = cls_string
    return Element(tag=self._tag, attrs=attrs, children=…)
```

`compose_class(slot_name, *, apply_variant_size_modifiers=True)` :

- Lit `THEME["slots"][slot_name]`
- ⚠️ **Ne substitue plus rien.** `color=` a vécu ici jusqu'au 2026-08-30 : il
  comblait les trous `{bg_color}` du gabarit. Un thème lit maintenant des
  PALIERS (`bg-(--bz-bg)`), et la couleur vient de la classe-PONT que le
  socle pose sur la racine rendue. Une classe composée ne dépend donc plus
  de la couleur du tout
- Applique variant + size + modifiers si `apply_variant_size_modifiers=True` ET le slot est `"root"`
- **N'ajoute PAS** le `classes=` user : c'est `_apply_universal_modifiers` (le wrap de render de la métaclasse) qui le pose sur le vrai root, en dernier (cf. `theme.md`)

Pour **les slots non-root** ou les composants à layout custom (Select, Dropdown), passer `apply_variant_size_modifiers=False` et appliquer la size manuellement (cf. `theme.md`).

---

## `emit_attrs()` — sortie standard du composant

Retourne dict avec :

- `id` (auto-généré ou explicite)
- `bz-id` (pour la résolution OOB swap)
- Tous les `reactive_prop` à `emit_attr=True` qui ont une valeur non-None
- Pour les `ClientBinding` réactifs : `bz-attr:<attr>="$bz.state.<Class>.<key>.<field>"` (chemin complet via `path_of`) **sur le root**
- Tous les `_event_attrs` (le bundle `hx-post`/`hx-trigger`/`data-bz-sig`)
- Tous les `_passthrough_attrs` (`@click=…`, `:value=…`)
- Tous les `_raw_attrs` (HTML standards)

⚠️ **`bz-attr:<attr>` atterrit toujours sur le ROOT.** Si l'attribut `<attr>` n'a aucun effet sur le tag racine (cas typique : `disabled` sur `<div>`, `src` sur `<span>`, `value` sur `<div>`), il faut le **forwarder sur l'élément carrier** via `forward_binding` (voir section suivante). Sinon le runtime écrit silencieusement à chaque tick reactif sur un attribut qui ne fait rien, et la fonctionnalité paraît cassée alors que le binding existe.

Les composants render-time peuvent en pop des entrées (ex : Select déplace le bundle d'action (`hx-post`/`hx-trigger`/`data-bz-sig`) du root vers le hidden input pour que la form-data porte name+value).

---

## Primitives binding ↔ carrier (la VRAIE plomberie)

Les composants composent souvent un wrapper + des enfants où la VRAIE cible d'un attribut HTML n'est pas le root. Six primitives sur `Component` couvrent les cas connus — utilise-les plutôt que de coder le forwarding à la main, sinon tu reproduis pile les bugs catalogués dans `traps.md` § "wrapper-vs-carrier".

### `self.forward_binding(prop, target_attrs, *, as_attr=None, root_attrs=None)`

Forwarde un binding `ClientBinding` (ou `ClientExpression`) du root vers un élément carrier intérieur. Émet `bz-attr:<as_attr or prop>` sur `target_attrs` ; quand `root_attrs=` est fourni, strippe la directive jumelle sur le root pour éviter le double-emit.

```python
# file_upload : disabled/multiple/accept/required vivent sur le native input
for prop in ("disabled", "multiple", "accept", "required"):
    self.forward_binding(prop, input_attrs, root_attrs=root_attrs)

# avatar : src vit sur l'inner img (pas le wrapper span)
self.forward_binding("src", img_attrs)
self.release_root_attr("src", root_attrs)  # pop manuel quand emit_attrs vient APRÈS

# select : multi-trigger est un <div> où "disabled" ne marche pas → forward as aria-disabled
self.forward_binding("disabled", trigger_attrs, as_attr="aria-disabled")
```

**Règle systématique** : si une `BINDABLE_PROPS` de ton composant cible un attribut HTML qui n'agit pas sur le tag du root (consulter la table `tests/audit/carriers.py:ATTR_CARRIERS`), tu DOIS forward. La gate `tests/consistency/test_binding_lands_on_carrier.py` flagge l'omission — sans navigateur, dans le run rapide.

⚠️ Forwarder ne suffit pas : mets aussi `emit_attr=False` sur le `reactive_prop`, sinon la racine garde une directive inerte que le runtime réécrit à chaque tick. C'est exactement ce que `date_picker` / `date_range_picker` faisaient (audit F01–F04).

### `self.release_root_attr(prop, root_attrs)`

Strippe `<prop>="…"` ET `bz-attr:<prop>="…"` du dict root. Usage quand le composant gère la prop par un mécanisme custom (sync bz-init, bz-effect) et qu'on veut nettoyer ce que `emit_attrs` a auto-émis.

```python
# date_picker : la value adresse le store directement (bz-model), pas via bz-attr:value
root_attrs = self.emit_attrs()
self.release_root_attr("value", root_attrs)
```

### `self.path_of(binding)` (staticmethod)

Retourne la chaîne client canonique d'un binding, quelque soit son sous-type :

- `ClientBinding` → `$bz.state.Class.key.field`
- `ClientExpression` → l'expression verbatim accumulée

Unifie le if/else qui hantait button/icon_button/toggle_group/combobox/number_input/select. Plus de `isinstance(b, ClientExpression) ? b.binding_path() : f"$bz.state.{b.serialize_path()}"` au callsite.

```python
loading_path = self.path_of(loading_binding)
disabled_path = self.path_of(disabled_binding)
attrs["bz-attr:disabled"] = f"({loading_path}) || ({disabled_path})"
```

### `self.bind_attribute_pair(attrs, attr_name, *, ssr_value, reactive_expr)`

Émet le couple SSR-static + reactive client sur un même attribut. Le SSR garantit que screen readers / no-JS / pré-boot voient la valeur ; le reactive maintient la sync après mutation.

```python
# progress : aria-valuenow doit être à la fois static (SSR) et reactive (client)
reactive = None
if value_binding is not None:
    reactive = f"Math.round(Number({self.path_of(value_binding)}) || 0)"
self.bind_attribute_pair(
    attrs, "aria-valuenow",
    ssr_value=str(int(value_raw)),
    reactive_expr=reactive,
)
```

### `BINDABLE_CARRIERS: ClassVar[dict[str, str]]` — DÉCLARATIF (préféré quand applicable)

Au-dessus des 5 primitives impératives ci-dessous, le pattern préféré pour le carrier-forwarding est **déclaratif** :

```python
class FileUpload(Component):
    BINDABLE_PROPS = ("disabled", "multiple", "accept")
    BINDABLE_CARRIERS = {
        "disabled": "nativeInput",   # bz-ref de l'élément carrier
        "multiple": "nativeInput",
        "accept":   "nativeInput",
        "required": "nativeInput",
    }

    def render(self):
        # ... build native_input avec bz-ref="nativeInput" ...
        # AUCUN appel manuel à forward_binding nécessaire :
        # le base walk l'arbre après render() et applique automatiquement.
```

Comment ça marche : la métaclasse wrap `render()` ; après que ton `render()` retourne l'arbre, le base walk pour trouver l'élément avec `bz-ref="<valeur>"`, ajoute `bz-attr:<prop>` sur SES attrs (pas sur le root), et strippe la directive dupliquée du root. Tu n'as plus que :

1. Déclarer `BINDABLE_CARRIERS = {prop: x_ref_value}` au niveau classe
2. Marquer le carrier dans `render()` avec `bz-ref="<x_ref_value>"` dans ses attrs

**Quand utiliser `BINDABLE_CARRIERS` vs `forward_binding` manuel** :

| Cas | Choisir |
|---|---|
| Tu as un seul carrier identifiable par `bz-ref` (cas le plus courant) | **`BINDABLE_CARRIERS`** |
| Plusieurs props vont sur la MÊME carrier | **`BINDABLE_CARRIERS`** (déclaration multi-key) |
| La carrier est dans une branche conditionnelle qui peut ne pas exister | `forward_binding` + check explicite (le walker silent skip si pas trouvé, mais le forwarding manuel rend l'intention claire) |
| Tu forwardes avec rename (`disabled` → `aria-disabled` sur un `<div>`) | `forward_binding(as_attr=...)` (le déclaratif ne supporte pas le rename pour rester simple) |
| Tu forwardes une expression composée (`(loading) \|\| (disabled)`) | `path_of` + écriture manuelle (pas de binding 1:1) |

Une fois `BINDABLE_CARRIERS` déclaré, **ne pas appeler `forward_binding` pour les mêmes props** : tu doublerais le travail (et risquerais un sentier de bugs au prochain refactor).

---

### `self._bind_x_model(attrs, prop="value", *, binding=None)`

(Existait avant cette session.) Wire l'`bz-model` bidirectionnel sur un input. Strip le `bz-attr:<prop>` que `emit_attrs` aurait posé (les deux directives écrivent sur le même attribut — `bz-model` gagne car bidirectionnel).

Tableau récap **par cas d'usage** :

| Besoin | Primitive | Quand |
|---|---|---|
| **Forwarder vers carrier — cas standard** | **`BINDABLE_CARRIERS` (déclaratif)** | Identifier le carrier par `bz-ref` suffit |
| Forwarder un binding avec rename / branch / expression | `forward_binding` | `disabled` → `aria-disabled`, multi-trigger, etc. |
| Nettoyer une prop que le root ne porte plus | `release_root_attr` | Quand le composant prend le contrôle manuellement |
| Convertir un binding en chaîne d'expression client | `path_of` | Composer une expression `(a) || (b)` ou `f"!{path}"` |
| Sync bidirectionnel state ↔ scope local | adressage direct du store (`bz-model` / `bz-attr:`) | date_picker adresse `$bz.state.<path>` directement — plus de paire `$watch` |
| SSR + reactive sur un même attribut | `bind_attribute_pair` | Attributs a11y (aria-valuenow, aria-checked, data-state) |
| Two-way binding sur un input | `_bind_x_model` | Form inputs (input, textarea, checkbox, switch, …) |

---

## Pour créer un nouveau composant

### A. Plomberie minimale

1. Créer `bretzel/components/<famille>/<name>/` avec `<name>.py`, `theme.py`, `__init__.py` (export class).
2. Sous-classe `Component`, déclarer THEME / THEME_KEY / DEFAULT_TAG / IS_CONTAINER / EVENTS / NAMED_SLOTS / ICON_SLOTS.
   `THEME` = le dict de `<name>/theme.py` (le thème est **per-composant**, pas de registre global — cf. § « THEME_KEY » ci-dessous). L'override utilisateur (`Theme(components={<THEME_KEY>: …})`) est fusionné dessus par `_resolved_theme` : lire le thème via `self._resolved_theme()`, **jamais** `self.THEME` en direct (gardé par `test_theme_reads_are_resolved.py`).
3. Déclarer les `reactive_prop` au niveau classe.
4. Déclarer `BINDABLE_PROPS` : tuple des props qui acceptent un `ClientBinding` (**`()` si aucune**, jamais laisser le sentinel `None` hérité — il désactive la vérification, gardé par `test_component_contracts.py`). Pour une prop **que le CLIENT ÉCRIT** (une valeur : `value` / `checked` / `open`), ne PAS déclarer un ClassVar `TWO_WAY_PROPS` — mettre l'info **sur la prop** : `value: Any = reactive_prop(default=…, emit_attr=False, writes=True)`. La métaclasse dérive `TWO_WAY_PROPS`. C'est ce qui décide (a) qu'une `ClientExpression` y est refusée (une expression n'est pas assignable) et (b) que `_serverSync` s'émet en mode server-backed. Ce n'est PAS `AUTONAME_FROM` (« d'où je dérive mon `name=` HTML »). Cf. `Component._value_server_backed`. **Si la clé du signal `bz-data` diffère du nom de la prop** (Tabs stocke `value` sous `active`, ToggleGroup sous `picked`, Calendar `month` sous `year`+`month`) : ajouter `scope_keys=("active",)` sur la prop, et lire cette clé au `render()` via `self._scope_keys("value")` plutôt que la hardcoder. Gardé par `test_scope_keys_match_emission.py` (clé émise == clé déclarée).
5. `__init__` : forwarder les kwargs **directement** à super (`super().__init__(size=size, color=color, **kwargs)`) — **plus de dict `forwarded` / garde `if x is not None`** (0 restant dans le codebase depuis le sweep 2026-07-16). Le socle (`Component.__init__`) drope les kwargs reactive à `None` (garde le défaut du descripteur) et un slot `None` se lit `.get()`→None comme s'il était absent ; le défaut de CLASSE d'une sous-classe gagne même quand elle ne passe pas la prop (VStack ne passe pas `direction` → `None` → défaut `col`). Deux gardes : `test_none_kwarg_keeps_default.py` (le socle drope bien le None) + `test_reactive_prop_round_trips.py` (**convergence** : chaque prop passée doit prendre effet → attrape un param oublié dans le forward direct). Un slot de CONTENU (`label=`, `icon=`, `title=`…) se normalise par `Component.adopt_slot(x)` à la construction (détache un Component passé en slot, sinon rendu 2×) — et se rend par `emit_text_slot` au `render()`. **Les deux vont ensemble** : `adopt_slot` seul laisse le crash `TextNode(Component)`, `emit_text_slot` seul laisse l'orphelin. Gardé par `test_slot_never_orphans.py`.
6. `render()` : retourne un `Element`. Lire les valeurs via `_reactive_values` (snapshot SSR) et `_binding_metadata` (les bindings vivants) — **jamais** `isinstance(_reactive_values[prop], ClientBinding)`, toujours False (un binding vit dans `_binding_metadata`, cf. traps.md). Chemin client d'un binding : `self.path_of(binding)`, **jamais** `f"$bz.state.{…}"` à la main (double-préfixe sur une expression ; gardé par `test_client_path_single_source.py`). Composer les classes via `compose_class`. **Ne JAMAIS ré-append `self._classes`** (les classes user `classes=`) à la string de classe : le wrap métaclasse `_apply_universal_modifiers` les pose déjà sur le vrai root — le faire aussi dans `render()` double la classe (`ui.x(classes="X")` → `X X`). Gardé par `test_no_manual_user_class_append.py`.
6bis. **Ta famille a peut-être déjà son `render()`.** Quatre familles partagent le leur depuis le 2026-08-19 — picker à panneau `<bz-calendar>` (`inputs/_picker_field.render_calendar_field`), overlay modal (`overlay/_modal.render_modal_overlay`), overlay ancré (`overlay/_anchored.render_anchored_overlay`), contrôle cochable (`inputs/_checkable.render_checkable`). Mesuré avant extraction : **62 % à 82 %** des lignes de `render()` identiques entre deux membres, toute la différence tenant en une poignée de valeurs. Ces rendus prennent des classes **déjà composées** (les chaînes de style restent par composant) et l'ORDRE des classes t'appartient — il compte, deux utilitaires de même famille et même spécificité sont départagés par la feuille. Gardé par `test_a_component_family_shares_its_render.py`, qui déclare AVEC leur raison les composants qui dérogent encore.
7. Re-export dans `bretzel/components/__init__.py` : class dans `__all__` **et** alias lowercase dans `_UI` (`test_component_contracts.py` garde la complétude de `__all__` ; `_UI` est la racine de tous les autres gates auto-évolutifs — un alias manquant rend le composant invisible à trois gates d'un coup).
8. Compléter la docstring et les métadonnées introspectées, puis vérifier avec
   ``bretzel describe <nom>``.

### B. Carrier wiring — la check-list anti-bug

Pour chaque prop dans `BINDABLE_PROPS`, te poser ces questions :

1. **L'attribut HTML correspondant agit-il sur le tag du root ?** (Consulter `_FORM_CARRIER_ATTRS` dans `tests/audit/interaction.py`.) Exemples concrets :
   - `disabled` → marche sur `input/select/textarea/button`, **PAS sur `div/span/label`**.
   - `value` → marche sur `input/select/textarea`, **PAS sur un wrapper**.
   - `src` → marche sur `img/iframe/audio/video`, **PAS sur `span`**.
   - `multiple`, `accept` → uniquement `<input>`.
   - `checked` → uniquement `<input>`.

2. **Si OUI** → ne fais rien de spécial. `emit_attrs()` pose `bz-attr:<attr>` sur le root et le runtime sync correctement. (Cas Button, Input, Textarea, Checkbox : le root EST le carrier.)

3. **Si NON** → tu DOIS forwarder le binding sur le bon élément enfant via `self.forward_binding(prop, child_attrs, root_attrs=root_attrs)`. La directive bouge sur le carrier ET le root est nettoyé du double-emit. (Cas Avatar.src → `<img>`, FileUpload.disabled/multiple/accept → `<input type="file">`, Select.disabled → `<button>` trigger.)

4. **Cas spécial — Composant gère sa prop via mécanisme custom** (date_picker adresse le store directement, calendar via custom element) : utiliser `self.release_root_attr(prop, root_attrs)` après `emit_attrs()` pour pop l'auto-émis.

5. **A11y / data-* attributes que tu veux à la fois SSR + reactive** : `self.bind_attribute_pair(attrs, "aria-valuenow", ssr_value=..., reactive_expr=...)` plutôt qu'écrire les deux à la main.

6. **Sync bidirectionnel scope local ↔ state** (rare) : adresse le store directement (`bz-model`, ou `bz-attr:value="$bz.state.<path>"`) plutôt qu'un miroir local. L'ancien helper `$watch` (`alpine_sync_with_binding`) a été supprimé — le runtime bz- n'a pas `$watch`.

### C. Tests

1. **Unit** (`tests/unit/components/<famille>/test_<name>.py`) — render avec litéral + binding + expression, assert les classes/attrs émis.

2. **Audit interactif** — ajouter une `ComponentSpec` dans `tests/audit/checklist.py` avec :
   - `route` + `root_selector` matchant l'instance demo dans chaque card
   - `has_color_axis`, `has_size_axis`, `is_interactive` selon le composant
   - Si une prop bindable ne peut pas être observée par le probe (cas `skip_dynamic_props` dans `audit.md`), la lister avec un commentaire **Pourquoi**.

   Puis lancer `py -m tests.audit.driver <name>`. Si `carrier_landing` fail → un `forward_binding` manque. Si `client_switches_drive_carrier` fail → vérifier le binding via Playwright à la main (peut être un faux positif probe-side).

3. **Playground** — créer `examples/playground/features/<name>.py` qui suit le gabarit des 7 sections (`playground-pattern.md`). La cohérence du gabarit fait que les probes d'audit fonctionnent automatiquement sans config supplémentaire.

### D. Pièges déjà payés — RELIRE `traps.md`

Avant de fermer ta PR, scan ces sections de `traps.md` :

- "wrapper-vs-carrier" — la classe de bug que `forward_binding` élimine
- "Morph guard preservait `class` même quand le nouveau render dropait `:class`" — gérer le cycle de vie des `:X` bindings
- "Refreshable __call__ bypass" — si ton composant vit dans un `@refreshable`
- "Une classe de couleur ne s'ASSEMBLE jamais" — si tu fais du theming
- "sr-only ≠ tabindex=-1" — si ton composant a un sr-only `<input>` à côté d'un wrapper focus

### E. Discipline de session

Quand tu reproduis le pattern carrier-vs-wrapper 3 fois sur 3 composants différents, **arrête et propose une primitive sur Component**. La règle "deux occurrences = coïncidence, trois = pattern" est aussi vraie ici qu'ailleurs. La session qui a accouché de `forward_binding` / `release_root_attr` / `path_of` / `bind_attribute_pair` a corrigé 5 bugs de production qui auraient continué à se reproduire sinon.
