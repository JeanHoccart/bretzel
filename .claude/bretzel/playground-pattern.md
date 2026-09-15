# Pattern playground — one test-bench page per component

Convention for the playground at `examples/playground/`. Every shipped
component has a dedicated feature (`features/<name>.py` or
`features/<name>/`) that pairs visual demos with live HTML inspection
blocks. The page is a **test bench for the framework team** — not a
user-facing doc.

Read this file when you add a component page, when you split an
existing one that grew too large, or when you build a similar test
bench for a different app.

---

## 1. Repo structure

```
examples/playground/
├── main.py                 # Bretzel(...) + app.include(routes.PAGES, errors)
├── app/
│   ├── layout.py           # shell()
│   ├── routes.py           # page(...) libre → construit PAGES (pas d'app)
│   └── nav.py              # NAV = [(section, [(label, path, icon), ...])]
├── infra/
│   └── errors.py           # @error_page(404 / 500)
└── features/
    ├── home.py
    ├── <leaf-component>.py        # single-file pattern
    └── button/                    # folder pattern — fichier > 900 lignes (§ 7)
        ├── __init__.py            # re-export PATH + page
        ├── state.py               # *State classes + constants
        ├── logic.py               # handlers (mutate state ; deps= re-renders the panel)
        └── ui.py                  # render — refreshable panels + page
```

## 2. Launch

```bash
py -m examples.playground.main
```

From repo root. `app.run()` autodetects the entrypoint via
`__main__.__spec__.name`.

## 3. Mandatory card list — the 7 sections

A component page is **up to 10 cards** implementing **7 standard sections**.
§2 is delivered as **four separate cards** (Slots / Edge cases /
Composability / A11y), so the section count (7) and the card count (up to
10) differ by design.

| § | Card(s) | Applicable when | Live HTML block ? |
|---|---|---|---|
| **§1 All props (basic)** | `Reference` | Always | no — visual scan only |
| **§2 Custom props** | `Slots` · `Edge cases` · `Composability` · `A11y` (4 cards) | Slots: has slots ; Composability: nests ; Edge cases + A11y: always | no — visual demos |
| **§3 Server playground** | `Server playground` | Component is stateful/configurable | **yes** — re-renders on every state change |
| **§4 Server events** | `Server events` | `EVENTS` non-empty | **yes** — one representative block ; **every** event wired |
| **§5 Client playground** | `Client playground` | `BINDABLE_PROPS` non-empty | **yes** — SSR snapshot (runtime drives live updates) |
| **§7 External controls** | `External controls — the 3 modes` | Component exposes an imperative API (`.open()`/`.set()`/`.toggle()`/…) | **yes** — one block per mode where relevant |
| **§6 Client events** | `Client events` | `EVENTS` non-empty | **yes** — one representative block ; **every** event wired |

**Physical tail order is §5 → §7 → §6** (External controls before Client
events), not the numeric §5-§6-§7 sequence. This matches the order every
imperative component already shipped in (~15 pages, before §5 existed) —
churning that order across the whole catalog for a cosmetic reshuffle isn't
worth the diff. §5 and §6 are still mandatory in their own right ; only the
tail's physical position differs from the numbering.

Rules that follow from this table :

- **§5 is its own dedicated card even for components that also have §7.** The
  imperative card's "Mode 2 — ClientBinding" is NOT a substitute : §5 must
  stand alone and exercise **every** `BINDABLE_PROPS` entry with a live
  no-round-trip preview + its own emitted-HTML block. (Overlaps like an
  overlay whose only bindable prop is `open` still get a §5 card — thin is
  fine, absent is not.)
- **§7's canonical card title is `External controls — the 3 modes`.** Do not
  use "External triggers" or other variants — one title across the catalog.
  The three modes are: (1) **Imperative only** (no binding → DOM `bz-*`
  dispatch), (2) **ClientBinding only** (method writes through the binding),
  (3) **Both** (write-through shown together). Cf. `imperative-api.md` for the
  per-component method inventory.
- **§4 / §6 wire every event.** The emitted-HTML block may show one
  representative event, but each event in `EVENTS` must have a live control
  (a server handler for §4, a `clientstate.log.push(...)` expression for §6).

The stateful cards (§3, §4, §5, §6) carry **at least one**
`ui.code(serialize_html(...), lang="html")` block — via
`emitted_html_block()`, jamais à la main (74 pages sur 74 le font).

⚠️ **Cette ligne disait « exactly one » jusqu'au 2026-09-06, et elle
était fausse** : vingt `Client playground` sur vingt-cinq en portent
deux, une démo par forme de binding avec son propre bloc. Le pluriel
est la pratique, et elle est bonne — deux formes de binding méritent
deux blocs. C'est la règle qui a été corrigée, pas les vingt pages. The bindings they emit
differ radically (server callable → `hx-post`+`data-bz-sig`, client binding →
`bz-attr:disabled=`, expression client → `@click=`, etc.) — showing the shapes
side by side is the whole point of the gabarit.

For leaf components like `Divider`, the page may be just §1 + §2 (Edge cases +
A11y). That's fine. Don't pad — sections whose applicability condition is false
are omitted entirely (no empty cards).

## 4. Server playground — THE test bench

The card that does the heavy lifting. Inside the `@refreshable`
panel :

1. A **`PageState`** carries one field per component prop AND one field
   per universal escape hatch (`classes`, `custom_id`, `aria_label`,
   `style`, `extra_attrs`) AND one field per universal modifier
   (`visible`, `tooltip`) AND any event-handler-shape toggle the
   component supports (`on_click_mode` etc.). 15-17 fields total for
   a rich component, fewer for simpler ones.
2. A **controls grid** exposes every field as `ui.input` / `ui.select`
   / `ui.switch` / `ui.textarea`, wired to a shared `on_change=` handler
   that mutates the state ; the panel's `deps=` re-renders it.
3. A **`build_preview(state)`** helper at module scope maps state → kwargs
   (empty strings collapse to missing kwargs ; `aria_label` + `extra_attrs`
   merge into a single `attrs={}` dict ; `on_click_mode` switches
   between callable / string / list).
4. A **preview** constructed via `build_preview(state)`.
5. **One** `ui.code(serialize_html(build_preview(state)), lang="html")`
   block under the preview, labelled `"Emitted HTML"` with a muted
   caption.

## 5. The four stateful cards each have HTML inspection

Server playground / Server events / Client playground / Client events
each end in a `ui.code(serialize_html(...), lang="html")` block. The
purpose is to expose the **4 binding shapes** Bretzel emits :

| Card | Distinctive HTML attrs |
|---|---|
| Server playground | Whatever the controls compose live — refreshable, re-renders on every change |
| Server events | `hx-post`/`hx-trigger`/`data-bz-sig` + identity (`id` / `bz-id`) — server-callable wiring |
| Client playground | `bz-attr:disabled=`, `:class="'<static>' + ' ' + (...)"`, `:icon="$bz._resolveIcon(...)"` — plomberie réactive client, SSR snapshot only |
| Client events | `@<event>="$bz.state.X.log.push(...)"` — pure expression client, zero round-trip |

Show one representative button per events card (they only differ by
event name) ; the playground cards show the live preview button itself.

## 6. Hard rules

1. `classes=` / `id=` / `attrs=` / `style=` belong in the **Server
   playground** as controls. **Forbidden** in the visual cards (1-5) —
   those must exercise the component's public API only.
2. No display helpers (`prop_row()`, `card_block()`). Inline 5-10 line
   blocks even if repeated.
3. **Allowed at module scope** — et AUCUN ne porte de préfixe `_`.

   ⚠️ **Portée de cette règle**, écrite le 2026-09-07 parce qu'elle
   manquait : elle s'adresse à une page de COMPOSANT, c'est-à-dire une
   page dont le nom est celui d'un `ui.*`. Les neuf autres du corpus
   n'ont rien à prévisualiser et sont hors périmètre — l'infrastructure
   du playground (`home`, `app_map`, `inspection`, `meta`,
   `theme_studio`), les pages de FAMILLE qui montrent plusieurs
   composants en relation (`stack`, `dnd`, `screen`), et `notification`,
   qui est un helper qu'on déclenche et non un composant qu'on rend.
   L'audit du 2026-09-06 comptait six pages sans ces helpers ; les six
   ont rattrapé, et `test_a_component_page_carries_its_preview_helpers`
   les y garde — 70 sur 70. Le critère se DÉRIVE du catalogue, il ne se
   liste pas : pas d'exemption à tenir à jour, donc pas d'exemption
   périmée qui cache la page suivante.
   La règle 6 du CLAUDE.md l'interdit sur une fonction d'app, et cette
   page prescrivait pourtant `_build_preview` / `_control` : deux
   conventions concurrentes, chacune adossée à un document du dépôt,
   66 pages contre 8. Arbitré le 2026-09-06 en faveur de la règle 6,
   et gaté par `test_examples_have_no_private_functions.py` — 99
   fonctions renommées, dont cinq qui ont dû choisir un meilleur nom
   parce que le nom nu était déjà pris (`_format` → `format_result`,
   `_n` → `feature_node`).
   - `build_preview(state)` — concentrates the prop-to-kwargs translation
   - `parse_extra_attrs(blob)` — local parsing util for the `extra_attrs`
     textarea
   - `control(label)` — labelled input cell helper, used by every
     control row
   - Constants (`VARIANTS = [...]` etc.) if used twice or more
   - Module-level handler callables (must be addressable via
     `module::qualname`)
4. **Forbidden at module scope** : single-use cosmetic helpers,
   functions that wrap < 5 lines of inline code.
5. Components without certain features (no slots, no events) omit
   the corresponding card entirely. No conditional logic inside the
   page.

## 7. When to split the feature file

Per `app-structure.md` § 6.2 :

| Trigger | Action |
|---|---|
| Fichier unique > **900 lignes** | découper en dossier |
| en dessous | rester en fichier unique |

⚠️ **Le seuil disait 400 jusqu'au 2026-09-06, et il était faux.**
Mesuré ce jour-là : **52 pages sur 70 le dépassaient** — `sidebar`
1 064 lignes, `toggle_group` 914, `dialog` 905, `combobox` 894. Une
règle qu'enfreignent trois quarts du corpus ne guide pas, elle induit
en erreur : elle a fait découper `diagram` en paquet à 449 lignes pour
rien. 900 est le réel : **69 pages sur 73 s'y tiennent**.

⚠️ Et la première version de ce paragraphe a écrit « au-dessus, seule
`sidebar` reste » en citant `toggle_group` 914 et `dialog` 905 trois
lignes plus haut — une phrase qui contredisait ses propres chiffres, le
jour où elle corrigeait une règle fausse. Elles sont **quatre** :
`sidebar` 1 065, `accordion` 933, `toggle_group` 914, `dialog` 905.
Nommées dans `test_a_playground_page_stays_under_the_threshold`, une
liste qui ne fait que rétrécir — c'est ce qui rend le seuil VRAI au
lieu d'aspirationnel.

Folder pattern :

```
features/<name>/
├── __init__.py     # re-export PATH + page (only what routes.py needs)
├── state.py        # *State classes + axis constants (VARIANTS / SIZES / ...)
├── logic.py        # handlers (mutate state + refresh panel)
└── ui.py           # refreshable panels + page + render helpers
```

Import rules inside the package :

| Module | May import | May NOT import |
|---|---|---|
| `state.py` | `bretzel.state`, stdlib | `logic`, `ui`, the app |
| `logic.py` | `state`, `bretzel.state` | `ui` (handlers just mutate state ; the panel's `deps=` re-renders it — no import of the panel needed) |
| `ui.py` | `state`, `logic`, `bretzel.*`, `examples.playground.main` | nothing forbidden |
| `__init__.py` | `ui` only | implementation details (handlers, render helpers) |

**No handler/panel cycle** : the panel declares `deps=[XPlayground]`, so a
handler that mutates that state re-renders the panel automatically —
`logic.py` never imports `ui.py`. The handler just receives the typed
control value and lets the snapshot-diff do the rest :

```python
def server_changed(state: ButtonPlayground) -> None:
    # Typed param : the dispatcher hydrates the changed control's value
    # into ``state`` (coerced by the field type, persisted at end of
    # request) — no ``**kwargs`` / ``setattr`` loop. server_panel declares
    # deps=[ButtonPlayground], so it re-renders on its own — the body can
    # be a plain ``pass``. (Need to inspect WHICH field changed? Use the
    # ``state.form_value("name")`` escape hatch — cf. the sparkline playground.)
    pass
```

The typed ``state`` parameter is the canonical way to receive control
values into server state — the same mechanism as a typed form handler
(``def save(form: MyForm)``), cf. `state.md` § form hydration. A param
annotated with a ``ServerState`` subclass is resolved through the registry
and hydrated from the submission before the handler runs ; the panel's
``deps=`` then triggers the re-render, no manual call.

## 8. La procédure — à SUIVRE, pas à survoler

> ⚠️ Cette section a été réécrite le 2026-09-06, après qu'une page
> livrée ait manqué **trois cartes obligatoires sur huit**. La version
> précédente était une liste de dix points ; elle n'était pas fausse,
> elle était **survolable**. Ce qui suit ne l'est pas : chaque étape a
> une commande ou une question à laquelle on répond par oui ou non.

### Étape 0 — VÉRIFIER les ClassVars avant de s'en servir

**C'est l'étape qu'on saute, et c'est celle qui coûte tout le reste.**
Le § 3 dérive la liste des cartes de `EVENTS`, `BINDABLE_PROPS`,
`NAMED_SLOTS` et `IMPERATIVE`. Si l'un d'eux est faux, la liste est
fausse — et elle a l'air juste.

Le défaut mesuré : `ui.diagram` déclarait `EVENTS = ()` et
`BINDABLE_PROPS = ()`. J'en ai conclu « ce composant n'a ni event ni
sélection », donc pas de carte Server events, pas de Client events, pas
de Client playground. Les deux ClassVars étaient vides **parce que je ne
les avais pas déclarés**, pas parce qu'il n'y avait rien à déclarer.

Donc, dans l'ordre, et avant d'écrire une ligne de page :

1. **`EVENTS` est-il complet ?** Le composant appelle-t-il
   `register_action` ou `item_action_attrs` ? Son `__init__` nomme-t-il
   un `on_<x>` ? Alors `<x>` DOIT être dans `EVENTS`.
   Gardé par `tests/consistency/test_a_wired_event_is_declared.py`.
2. **`BINDABLE_PROPS` est-il complet ?** Applique le test de
   `client-reactive-surface.md` § *La règle* **prop par prop**, pas de
   mémoire. Le premier temps suffit le plus souvent : « l'utilisateur
   édite-t-il cette valeur en interagissant avec CE composant ? » —
   une sélection, un `value`, un `checked`, un `open` répondent oui.
3. **`NAMED_SLOTS` / `IMPERATIVE`** — même question, mêmes fichiers
   (`components.md`, `imperative-api.md`).

Tant que ces quatre ne sont pas VÉRIFIÉS, la suite ne veut rien dire.

### Étape 1 — dériver la liste des cartes

Écris-la noir sur blanc dans le docstring du module, avec la raison de
chaque omission. Une carte omise sans raison écrite est une carte
oubliée.

| Si… | alors la carte est |
|---|---|
| toujours | `Reference` · `Edge cases` · `A11y` |
| le composant se pose dans d'autres conteneurs | `Composability` |
| `NAMED_SLOTS` non vide | `Slots` |
| le composant a des props configurables | `Server playground` |
| `EVENTS` non vide | `Server events` **ET** `Client events` |
| `BINDABLE_PROPS` non vide | `Client playground` |
| `IMPERATIVE` non vide | `External controls — the 3 modes` |

### Étape 2 — écrire chaque carte contre SON contrat

Le titre ne suffit pas. Ce que la gate vérifie, c'est le titre ; ce que
la carte doit CONTENIR est ci-dessous, et personne ne le vérifie à ta
place.

- **Reference** — un sous-titre `level=3` par axe, et **tous** les
  paliers de chaque axe : chaque `size`, chaque `color`, chaque valeur
  d'une table fermée. Pas d'échappatoire universelle ici.
- **Composability** — le composant DANS d'autres conteneurs, en
  choisissant ceux qui cassent : une cellule de grille plus étroite que
  lui, une colonne de hauteur bornée, un `ui.pane`. Un montage isolé ne
  montre aucun de ces défauts.
- **Edge cases** — le vide, l'unique, le très long, le cyclique, le
  caractère à échapper, la valeur qui ne désigne rien.
- **A11y** — ce que le composant promet au clavier et au lecteur
  d'écran, DÉMONTRÉ. Pas une phrase qui l'affirme.
- **Server playground** — `build_preview(state)` au niveau module,
  `control(label)` pour chaque contrôle, **un champ par prop ET par
  échappatoire universelle ET par modificateur**, et UN
  `emitted_html_block`.
- **Server events / Client events** — chaque event de `EVENTS` a un
  contrôle vivant. Serveur : un handler qui journalise, un log affiché,
  un bouton `Clear`. Client : une `ClientExpression` qui empile dans un
  `ClientState`, un log qui se ré-évalue **sans `@refreshable`**.
- **Client playground** — ⚠️ **un contrôle EXTERNE lié au même champ**,
  pas seulement le composant. Sans lui la carte ne montre qu'un sens, et
  « ⇄ two-way » reste une affirmation. Le `select` écrit, le composant
  lit ; le composant écrit, le `select` suit.
- **External controls** — les trois modes, sous ce titre exact.

### Étape 3 — brancher

`page(<feat>.PATH, layout=shell)(<feat>.page)` dans `app/routes.py`
(décorateur LIBRE, `routes.py` n'importe jamais l'app), puis
`(label, path, icon)` dans `app/nav.py` — **dans la section qui
correspond à l'usage du composant**, pas celle de son dossier.

### Étape 4 — vérifier, au navigateur

Un `curl` à 200 ne prouve rien : il dit que Python a sérialisé du HTML.

1. `pytest` — la page doit satisfaire `test_a_component_page_carries_its_cards`
   et `test_playground_demos_the_api` ;
2. ouvre la page dans Chromium et **relis la console** — une expression
   cliente malformée n'y dégrade rien, elle empêche le runtime ENTIER de
   démarrer (`html.bz-ready` n'arrive jamais) ;
3. **exerce chaque carte à état**, à la main ou par un script : le
   handler serveur journalise-t-il ? l'expression cliente part-elle bien
   à zéro requête ? le binding va-t-il dans les DEUX sens ?
4. si le fichier dépasse le seuil du § 7, découpe-le maintenant.

## 9. Aucun `from main import app` — décorateurs libres

`ui.py` importe les décorateurs **libres** `from bretzel import refreshable, ui`
(ajouter `broadcast=[State]` au `@refreshable` pour du cross-onglet) — il ne fait JAMAIS
`from examples.playground.main import app`. La zone se résout à la requête
via `sys.modules`, donc l'enregistrement est implicite. `state.py` et
`logic.py` restent purs aussi. Seul `main.py` connaît l'instance app
(`app.include(routes.PAGES, errors)`).

## 10. The Button page is the canonical reference

When in doubt about a card's layout or the split structure, look at
`examples/playground/features/button/`. It's the gabarit this template
was designed against.
