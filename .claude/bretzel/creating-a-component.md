# Créer un composant — de zéro à livré

Le parcours unique. **Ce fichier ne réexplique aucune règle** : il
séquence, et pointe vers la page qui possède chaque sujet.

> Fusionné le 2026-08-01 avec `component-rollout-checklist.md` (replié dans
> git). Les deux séquençaient le même travail avec deux numérotations
> concurrentes, deux listes de pré-lecture identiques, et une redite
> card-par-card de `playground-pattern.md`. Le composant de référence reste
> **Button** (`examples/playground/features/button/`) : en cas de doute sur
> une forme, va la regarder là-bas plutôt que d'inventer.

L'ordre : `cadrer → lire → décider bindable → écrire → gates → tests →
bencher → auto-relecture → bug hunt → vérif visuelle → fermer`.

---

## 0. Cadrer — 4 décisions AVANT de coder

1. **Quelle famille ?** primitive / action / input / feedback / overlay /
   navigation / data / chart / layout / meta → détermine le groupe
   (`bretzel/components/<group>/`) et les voisins à imiter.
2. **Quel état détient-il ?**
   - Rien (affichage pur) → pas de `writes=`, pas d'impératif.
   - Une **valeur éditée par l'user** → `value`/`checked` en **⇄ two-way**
     + `AUTONAME_FROM` si form-bound.
   - Un **open/close** → `open` en two-way + `.open()/.close()/.toggle()`.
3. **Quelles props méritent un binding client ?** → applique la règle
   (§ 2), prop par prop. Ne devine pas.
4. **Rend-il une COLLECTION ? Alors : qui écrit le `for` ?** → déclare
   `COLLECTION_OWNER`. Voir juste en dessous — c'est la décision qu'on
   oublie, et celle qui fige l'API pour de bon.

### La règle des collections — `COLLECTION_OWNER`

Un composant qui rend une liste peut exposer son contenu de deux façons :
des **enfants** dans un `with`, ou un **rappel `render=`**. Ce n'est pas
un goût, et il ne faut pas copier le premier voisin croisé. Une seule
question tranche : **qui écrit la boucle ?**

| réponse | valeur | ce que le composant DOIT alors offrir | exemples |
|---|---|---|---|
| l'auteur | `"author"` | des **enfants** (`IS_CONTAINER`), parce qu'il lui faut un endroit où poser son balisage. Un param de données (`items=`, `options=`) reste bienvenu comme **raccourci du cas simple**, et matérialise les mêmes enfants | `breadcrumb`, `toggle_group`, `tabs`, `stepper`, `accordion`, `tree`, `sidebar`, `navbar`, `dropdown`, `bottom_bar`, `carousel` |
| le composant | `"component"` | un **rappel de contenu**, seul point d'entrée possible : l'auteur *ne peut pas* écrire cette boucle (`datatable` cherche, filtre, trie et pagine) | `table`, `datatable` (`ui.column(render=)`) |
| le client | `"client"` | **ni l'un ni l'autre** — le navigateur re-rend la liste au runtime, un rappel Python ne s'y branche pas. Il faut un mécanisme propre, et la docstring doit dire lequel | `select`, `combobox` |

Deux conséquences qu'on ne voit pas tout de suite :

- avec des enfants, **`is_last` disparaît** — le parent connaît la
  longueur de sa liste, l'auteur n'a rien à calculer ;
- les paramètres d'un rappel ne sont **ni typés, ni autocomplétés, ni
  visibles depuis `bretzel describe`**. Ceux d'un sous-composant le sont.

> ⚠️ **Pourquoi cette section existe.** Le 2026-08-18, `breadcrumb` a reçu
> un `render=` parce que `table` en avait un : un exemplaire copié contre
> dix qui prennent des enfants. La faute n'était pas d'avoir mal jugé,
> c'est qu'il n'y avait **rien à lire**. Le défaut était mesurable :
> `items=` accepte dict, tuple *et* string, donc un rappel
> `lambda item, last: item["label"]` plantait sur deux des trois formes —
> celui de la démo playground compris. Gaté par
> `tests/consistency/test_collection_owner_decides_the_api.py`, qui
> **détecte** les collections (le rendu gagne-t-il des balises quand la
> donnée gagne des éléments ?) et exige la déclaration.

> Avant d'inventer un helper ou une convention : **grep les voisins et
> `archive/V1/`** (CLAUDE.md règle 2). Pour un input imite Input, pour un
> overlay Dialog, pour un cluster sélecteur Tabs/ToggleGroup.

---

## 1. Pré-lecture

L'index du funnel ([`README.md`](README.md)) dit qui possède quoi. Le
minimum avant de coder un composant, dans l'ordre :

[`components.md`](components.md) (anatomie + règles dures) →
[`client-reactive-surface.md`](client-reactive-surface.md) § *La règle* →
[`kwarg-routing.md`](kwarg-routing.md) (les 7 chemins + la matrice) →
[`theme.md`](theme.md) → [`state.md`](state.md) →
[`handlers.md`](handlers.md) → [`traps.md`](traps.md) **avant de coder,
pas après le crash** → [`imperative-api.md`](imperative-api.md) si tu
exposes `.open/.set/…`.

**Done** : tu sais, pour ta prop `foo`, dans quelle catégorie kwarg elle
tombe et si `ui.X(foo=binding)` doit marcher ou lever.

---

## 2. La règle bindable

**Le test en 3 temps vit dans
[`client-reactive-surface.md`](client-reactive-surface.md) § *La règle*.**
Applique-le prop par prop ; ne te fie pas à une paraphrase (il y en a eu
quatre concurrentes jusqu'au 2026-08-01, dont une divergente).

L'intuition, pour savoir ce que tu cherches : **serveur = source de
vérité, mutation → `@refreshable` re-render avec la valeur bakée** — donc
un binding client ne se justifie que s'il existe un *driver côté client*.

Ta décision est verrouillée par `tests/consistency/test_bindable_surface.py` :
il FAUT y ajouter la ligne de ton composant (+ la matrice de
`kwarg-routing.md`), sinon la gate rougit « composant absent du snapshot ».

---

## 3. Écrire le composant

### Auditer d'abord ce qui existe

Si tu ramènes un composant déjà livré au niveau Button : lis son `.py` et
son `theme.py` **en entier**, liste ses `reactive_prop` / `NAMED_SLOTS` /
`ICON_SLOTS` / `EVENTS`, ses spécificités (`AUTONAME_FROM`,
`IS_CONTAINER`, mutex structurel, bindings spéciaux), ses tests, et
compare sa signature à `bretzel describe <nom>` — les écarts sont ta liste de
travail.

### Ta famille a peut-être déjà son rendu

**Avant d'écrire un `render()`, regarde si ta famille en a un.** Quatre
familles partagent le leur depuis le 2026-08-19, parce qu'elles étaient
écrites deux fois :

| ta famille | le rendu partagé |
|---|---|
| picker à panneau `<bz-calendar>` | `inputs/_picker_field.render_calendar_field` |
| overlay modal (backdrop + verrou de scroll) | `overlay/_modal.render_modal_overlay` |
| overlay ancré (panneau téléporté, flottant) | `overlay/_anchored.render_anchored_overlay` |
| contrôle cochable (`<input type=checkbox>` caché) | `inputs/_checkable.render_checkable` |

Mesuré avant extraction : entre **62 % et 82 %** des lignes de `render()`
étaient identiques d'un membre à l'autre. Toute la différence tenait en
une poignée de valeurs — et une bonne part de ce qui restait n'était pas
du code mais des **commentaires** expliquant la même mécanique
différemment, ce qui empêchait de savoir si les deux se comportaient
pareil sans relire les deux.

`test_a_component_family_shares_its_render` rougit si tu assembles à la
main : les quelques composants qui dérogent y sont déclarés AVEC leur
raison.

⚠️ Ces rendus prennent des classes **déjà composées** — les chaînes de
style restent par composant (`feedback_no_shared_style_tokens`), et
l'ORDRE des classes t'appartient.

### Le squelette

Détail dans `components.md` § *Class-level config* et § *Pour créer un
nouveau composant*.

```python
class Foo(Component):
    THEME: ClassVar[dict] = FOO_THEME
    THEME_KEY: ClassVar[str] = "foo"
    # DEFAULT_TAG / IS_CONTAINER / EVENTS : à ne déclarer QUE s'ils
    # diffèrent du défaut de Component (90 recopies retirées le
    # 2026-07-30 ; une gate refuse désormais la redite).

    BINDABLE_PROPS: ClassVar[tuple[str, ...]] = ("value", "disabled")
    IMPERATIVE: ClassVar[tuple[str, ...]] = ("set", "clear")  # write-only
    AUTONAME_FROM: ClassVar[str | None] = "value"             # form input
    BINDABLE_CARRIERS: ClassVar[dict[str, str]] = {"disabled": "nativeInput"}

    value: Any = reactive_prop(default=None, writes=True)
    disabled: bool = reactive_prop(default=False)
    color: str = reactive_prop(default="primary", emit_attr=False)

    def __init__(self, *, ..., **kwargs): ...   # forward direct
    def render(self) -> Element: ...
```

Points de vigilance, chacun avec sa doc :

- **`writes=True`** dérive `TWO_WAY_PROPS` ; **`scope_keys=`** la clé de
  `bz-data`. Les deux se déclarent SUR la prop.
- **Impératif** = famille write-only uniquement, aucune méthode de
  lecture. Cf. `imperative-api.md`.
- **Slots** : `Component.adopt_slot(...)` dans `__init__`, jamais dans
  `render()`.
- **Lire un binding** : `self._binding_metadata.get(name)`, jamais
  `isinstance(_reactive_values[name], ClientBinding)`.
- **Carriers** : `BINDABLE_CARRIERS` (déclaratif) ou `forward_binding`.
  L'arbre de décision entre les trois routes est dans `components.md`.
- **Transport** : jamais de `fetch()` ni de `hx-post` à la main ; une
  action serveur = un handler `on_<event>=`, le comportement client pur =
  des directives `bz-*`. Cf. CLAUDE.md principe 2.
- **Thème** : slots/sizes/variants composés via `compose_class`. Les
  chaînes de classes restent **par composant** — pas de token de style
  partagé.

---

## 4. Les gates — la vraie definition of done

Un composant n'est pas livré tant que le sous-ensemble rapide n'est pas
vert :

```bash
pytest
```

**`pytest` nu EST le bon défaut** : `addopts` désélectionne `e2e`,
`browser` et `audit`, donc il ne lance que unit + integration +
consistency. 16 005 verts en 3 à 7 min selon la charge de la machine
(mesuré le 2026-08-19).

⚠️ Cette ligne a dit « pas de `pytest` nu, il part dans les suites
navigateur et pend » jusqu'au 2026-08-19 — **c'était faux depuis le
2026-07-14**, quand la config l'a réparé. Une consigne périmée coûte
plus qu'une consigne absente : elle se recopie.

**Écrire une gate a sa propre référence** : [`gates.md`](gates.md) — le
squelette (plancher / interdiction / mutation), les lecteurs partagés de
`_discovery`, et les trois façons de prouver qu'elle mord. Les gates de
`tests/consistency/` s'auto-expliquent — lance, lis, corrige. Regroupées
par ce qu'elles t'obligent à faire :

**Contrat / surface bindable** — `test_component_contracts` (les props
nommées existent, `BINDABLE_CARRIERS ⊆ BINDABLE_PROPS`, ta classe est
dans `components/__init__.py::__all__`) · `test_bindable_surface`
(**ajoute ta ligne dans `_EXPECTED`**) · `test_two_way_props` ·
`test_scope_keys_match_emission` · `test_serversync_*` ·
`test_declared_event_is_reachable` (chaque `EVENTS` a un `$dispatch`
atteignable) · `test_imperative_classvar_is_complete`.

**Reactive prop / kwargs** — `test_reactive_prop_round_trips` ·
`test_none_kwarg_keeps_default` · `test_client_path_single_source` ·
`test_no_universal_kwarg_shadowing` · `test_no_classvar_restates_the_default`.

**Thème / visuel déterministe** — `test_size_reaches_slots` (aucun slot
hors de la table `sizes` ne gèle une taille) et `test_sizes_are_distinct`
(deux `size=` ne rendent pas les mêmes classes — deux gates distinctes,
souvent confondues) · `test_color_wiring` · `test_palette_distinctness` ·
`test_control_height_ladder` · `test_disabled_affordance` ·
`test_theme_reads_are_resolved` · `test_theme_override_merge` ·
`test_root_slot_override_universal` · `test_input_root_fills_width` ·
`test_truncate_needs_width` · `test_no_manual_user_class_append`.

**Slots** — `test_slot_adoption` · `test_slot_never_orphans`.

**Action wiring** — `test_action_payload` · `test_action_wire_attrs` ·
`test_wire_id` · `test_server_action_routing_is_shared`.

**Surface + docs** — `test_every_public_symbol_is_describable` ·
`test_bindable_surface` · `test_playground_demos_the_api`.
*(`test_catalog_surface_coverage` et `test_visual_contracts_fresh` ont été
supprimées le 2026-08-16 avec la suite visual — elles ne gardaient qu'elle.
Avec elles disparaît l'alerte « ce prop / cet événement n'est couvert par
rien » : c'est désormais à la relecture de la voir.)*

**Python ↔ JS** — `test_python_js_mirror` : une logique portée des deux
côtés (ex. `compute_range`) doit concorder.

⚠️ **Si tu ajoutes une gate d'interdiction, elle doit déclarer un
plancher de non-vacuité** — `test_prohibition_gates_declare_a_floor` te
le rappellera. Une gate verte sur zéro fichier est pire que pas de gate.

---

## 5. Tests unitaires

Dans `tests/unit/components/<group>/<name>/` :

- structure du render (tags, classes clés, refs, carriers) ;
- chaque axe `size=`/`color=`/`variant=` produit des classes distinctes ;
- `value`/`checked`/`open` two-way : `bz-model` émis, `_serverSync` gated ;
- un binding sur une prop **hors** `BINDABLE_PROPS` lève
  `ComponentUsageError` ;
- chaque event a son affordance de dispatch ;
- impératif : `.set()`/`.open()` renvoient du `str`.

**Fige le contrat, pas la chaîne.** Un test qui épingle
`"(open).toString()"` rougit sur un refactor correct — asserte
`== bool_attr("open")`.

Chaque fix de bug framework = un test de régression.

---

## 6. Bencher — la page playground

**Le gabarit (7 sections, jusqu'à 10 cards) vit dans
[`playground-pattern.md`](playground-pattern.md)** — ne le recopie pas
ici. Ce qui est propre au montage :

**Structure de fichier** — single file `features/<name>.py` par défaut ;
dossier `features/<name>/` (`state.py` / `logic.py` / `ui.py`) au-delà de
~400 LOC.

**Les buckets de state** (chacun optionnel) :
`<Name>Playground` (PageState — un field par prop, par escape hatch
universel, par modifier universel, par toggle event-shape) ·
`<Name>Events` (PageState, log serveur) · `<Name>Client`
(ClientState `persist="memory"`) · `<Name>ClientEvents`. Les constantes
d'axes (VARIANTS / SIZES / COLORS) en haut du fichier.

Conventions de type qui portent du sens : chaîne vide = « ne passe pas le
kwarg » ; `visible: str = "on"` (tri-état string, pas bool) ;
`extra_attrs: str` multi-ligne parsé en dict.

**Handlers** — module-level, pas de lambda, pas de closure. Un `log_*` par
event déclaré, un `clear_log`, un `server_changed(state: <Name>Playground)`
typé (corps `pass` — c'est `deps=[<Name>Playground]` sur le panel qui
re-render).

**`build_preview(state)`** est la fonction centrale : elle mappe state →
kwargs. Chaîne vide → kwarg omis ; `aria_label` + `extra_attrs` fusionnés
en un seul `attrs={}` ; `visible == "off"` → `visible=False` ; le mode
d'event switch entre callable / expression client / liste.

**Wiring** — le `__init__.py` re-exporte `PATH` + `page` ; ajoute une
entrée `page(feat.PATH, layout=shell)(feat.page)` dans `PAGES`
(`examples/playground/app/routes.py`) et le lien dans `app/nav.py`.
⚠️ **Décorateur libre + `app.include`** — jamais `app.page(...)`, aucune
feature n'importe l'instance d'app.

---

## 7. Auto-relecture des pièges (AVANT de tester)

Grep ton propre code pour ces patterns. Chaque ligne renvoie à sa section
de `traps.md` **par son titre** — ce fichier n'a pas de numérotation, et
dix renvois « Trap #22 / #33 / #42 » pointaient dans le vide jusqu'au
2026-08-01.

**Toujours**

- *« Slot Component stocké sans `adopt_slot` → double-render »* — tout
  slot Component-typé passe par `adopt_slot(...)` **dans `__init__`**.
- *« Lire un binding via `_reactive_values` + `isinstance(ClientBinding)` »*
  — toujours `_binding_metadata.get(name)`.
- *« Méthode d'instance avec le même nom qu'une `reactive_prop` »* — les
  méthodes impératives sont assignées en **instance attr**.
- *« Composant à API imperative sans `id` rendu → dispatch silent-fail »*
  — si tu exposes `.open/.set/…`, `_needs_identity()` doit rendre `True`.
- *« Élément `inline-flex` étiré pleine largeur dans un `vstack` »* — root
  en `w-fit h-fit` (ou dimensions explicites), sinon un tooltip qui
  l'enveloppe se mal-positionne.
- *« `aria-enabled:` n'est PAS un variant Tailwind »* — les `hover:` d'un
  control se préfixent `enabled:hover:`. Gardé par
  `test_disabled_affordance`.
- Chaque `EVENTS` déclaré a un `$dispatch` atteignable — gardé par
  `test_declared_event_is_reachable`.
- Un `bz-data` ne porte que de la **donnée**, jamais un algorithme, et
  jamais un littéral Python (`True`/`None`) — deux gates le tiennent.

**Cluster sélecteur** (Tabs / ToggleGroup / futur Carousel-dots) — driver
visuel `data-selected="true"` SSR + `bz-attr:data-selected` réactif (PAS
le variant Tailwind `aria-pressed:`) ; `aria-*` émis **en plus** pour
l'a11y ; nom de variable de scope qui ne collisionne pas avec un attribut
HTML des enfants (`picked`, pas `value`) ; impératif étroit
(`.set/.clear/.focus/.blur` + `select_all/deselect_all`), pas de
`.add/.remove` par item.

**Overlay ancré** — panneau via `helpers.floating()` (repositionné en
`position: fixed`, il échappe nativement à tout `overflow-hidden`) ; aucun
`transform`/`translate`/`scale` sur un conteneur susceptible de
l'héberger (il deviendrait containing block) ; `prestamp display:none`
anti-flash ; `bz-teleport="body"` si un ancêtre peut le clipper — et
alors **`bz-ref="bzpanel"` obligatoire**, sinon le click-outside résout le
panneau d'un autre scope (gardé par `test_dismiss_scope_owns_its_panel`).

---

## 8. Bug hunt

Tu ne construis pas la page, tu **explores le composant à travers elle**.
Toggle chaque control, combine-les, et cherche l'écart entre ce que tu
attends et ce que le bloc HTML émis montre.

Surfaces à stresser : `id=` · `attrs={"data-x": "y"}` (apparaît-il, ou un
`attrs="{...}"` littéral ?) · un Component passé en slot textuel (rendu
propre ou `__repr__` Python ?) · `style=` · `tooltip=` · `visible="off"`
(`FragmentNode` vide ?) · les modes d'event (les variantes émettent-elles
vraiment des HTML différents ?) · un binding sur prop bindable (le bon
mécanisme selon la catégorie ?) · un binding sur prop non-bindable (lève
au construct ?).

Pour chaque écart : reproduire → localiser dans le framework → trancher
**bug** (contrat universel violé → fix + test de régression + commit
dédié) ou **frontière de design** (jamais promis → documenter dans
`kwarg-routing.md` ou ``bretzel describe``). Ne pas empiler de features avant
d'avoir tranché.

---

## 9. Vérification visuelle — BLOQUANT

`TestClient.get() → 200` prouve que Python a sérialisé du HTML. **Rien
d'autre** : ni que Tailwind a compilé, ni que `getComputedStyle` reflète
le design, ni qu'il n'y a pas de scrollbar parasite, ni que le tab order
tient. Six bugs sur six du sprint date_picker / date_range_picker /
file_upload étaient visibles en deux minutes dans un navigateur ; aucun
n'a été attrapé par TestClient.

Utilise le harnais existant — **n'écris pas ton propre lanceur uvicorn** :

```python
from tests.audit.harness import audit_server, browser_page
```

Il monte le playground sur un **port libre** (il ne touche pas au serveur
de dev) et donne un Chromium headless en 1400×900.

**Les 6 probes minimaux** : (A) *color distinctness* — les swatches de
`color=` rendent des `getComputedStyle` distincts ; (B) *size
distinctness* — idem sur `size=` ; (C) *tab order* — Tab depuis le host,
vérifier `activeElement` ; (D) *pas de double scrollbar* —
`document.body.scrollHeight - clientHeight == 0` ; (E) *screenshot* du
composant, relu à l'œil (clipping, chevauchement, alignement).

Selon le contexte, ajoute : bascule de `variant=` via l'UI et vérif de
l'`outerHTML` · scope `bz-data` correct après un refresh idiomorph ·
`dragenter` synthétique sur une dropzone · ouverture d'overlay
(position dans le viewport + fermeture au clic dehors) · `setAttribute`
sur un custom element qui déclenche bien `attributeChangedCallback`.

**(F) Compter les requêtes réseau de la page du banc** — ajouté le
2026-08-14, après un bug que rien d'autre n'a vu. `ui.image` et
`ui.video` émettaient `src=""` quand aucune source n'était passée ; un
attribut vide se résout contre l'URL du document, donc **le navigateur
retéléchargeait la page courante en croyant charger le média**. Résultat :
des dizaines de requêtes par chargement, et rien d'anormal à l'écran.

Ni les 12 000 tests, ni les cinq probes ci-dessus ne pouvaient le voir —
ils regardent le DOM et les pixels, jamais le réseau. C'est l'utilisateur
qui l'a trouvé en lisant les logs d'uvicorn. Le probe tient en cinq
lignes :

```python
seen = []
page.on("request", lambda r: seen.append(r.url))
page.reload(wait_until="networkidle")
# Une même ressource demandée > 3 fois = quelque chose boucle.
```

Vaut pour tout composant qui charge quoi que ce soit — média, police,
embed, sprite d'icônes.

⚠️ **Les probes minimaux couvrent le COMPOSANT, pas la page qui
l'utilise.** Ils sont tous scopés à l'instance (ses couleurs, ses
tailles, son tab order, son overflow) — donc aucun ne voit un défaut de
COMPOSITION : deux blocs collés faute d'un `ui.vstack`, un titre orphelin,
une carte qui respire mal. Mesuré en livrant le stepper : neuf probes
verts, et l'user a vu en dix secondes des boutons collés à leur panneau
dans trois cards (un `ui.card()` ouvert sans `vstack`, donc des enfants
frères sans gap). Le correctif de process est gratuit : **screenshoter
CHAQUE card de la page, pas seulement celles pour lesquelles tu as écrit
un probe** — tu choisis tes probes là où tu attends un bug, et c'est
précisément pour ça qu'ils ne trouvent pas ceux que tu n'attends pas.

Si le probe trouve un bug : **le fixer dans la session**, ajouter
l'entrée `traps.md` si non-trivial, et se demander s'il doit devenir un
test permanent dans `tests/runtime_js/`.

Si la vérif est impossible (interaction complexe, état persistant
long-terme) → le dire explicitement, jamais de « shipped » implicite.

---

## 10. Fermer

- `Skill: simplify` sur le `git diff` de la session (CLAUDE.md règle 4).
- Docstring et métadonnées introspectées à jour ; `bretzel describe <nom>`
  rend la surface attendue.
  (la ligne du composant), `kwarg-routing.md` (la matrice) +
  `test_bindable_surface._EXPECTED`, `traps.md` (piège neuf),
  `todo.md` (follow-ups).
- Un commit par item, sur `main` par défaut — **jamais de branche sans
  demander**.

**Anti-patterns** : construire la page sans toggler activement chaque
control (tu rates les bugs) · loguer un écart dans `todo.md` sans même
évaluer si c'est un bug ou un choix · empiler trois composants avant de
payer les dettes · inventer un pattern de card sans regarder Button ·
sauter une étape « parce que je sais déjà » · le commit géant de fin de
session.
