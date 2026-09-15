# Render — context, refreshables, drain

Source : `bretzel/render/`. Couvre `context.py`, `pipeline.py`, `partials.py`, `decorators/`.

---

## RenderContext — ce qui vit pendant une requête

Une instance par requête, accessible via `current_context()` (dans render scope) ou `maybe_current_context()` (peut renvoyer None).

Champs principaux :

| Champ | Rôle |
|---|---|
| `app` / `request` | Réf vers Bretzel + Starlette `Request` |
| `page_uuid` | UUID de l'instance de page (idiomorph stamp) |
| `parent_stack` | Pile des composants `with` actifs (auto-children) |
| `root_children` | Composants top-level enregistrés par la fonction page |
| `state_registry` | Cache typed-state pour cette requête |
| `client_state_payload` | ClientStates du client, décodés du **body POST** via `parse_client_payload` (V3 ; l'ancien header `X-Bretzel-Client-State` a été supprimé — cf. `realtime.py`) |
| `form_data` | Decode du body POST (lu par `get(...)`) |
| `is_partial` / `is_action` | Flags de routage (full page vs partial vs action POST) |
| `refresh_queue` | Liste des `RefreshableHandle` enqueués (via un state `deps=` changé ou `refresh(zone)`) |
| `notifications` | Liste des dicts toast pushés via `ui.notification(...)` |
| `action_registry` | Map id → callable enregistrés au render (pour HMAC sign) |
| `head_title` / `head_extras` | `ui.title()` → écrit `head_title` (string) ; `ui.meta_tag()` → append un `<meta>` à `head_extras` |
| `new_cookies` / `deleted_cookies` | Mut serveur → réponse |
| `response_headers` | Headers à émettre |

---

## Le cycle d'un POST action

1. **Middleware** : session → csrf → auth → render_context (instancie
   `RenderContext`). ⚠️ Il n'y a **pas** de middleware `client_state` :
   `parse_client_payload` est appelé DANS `RenderContextMiddleware`.
2. **Action route** : `POST /_bretzel/action/<id>`
   - Vérif HMAC — la signature arrive par le **header** `X-Bz-Sig` (avec
     `X-Bz-Ts`), pas par un champ de form ; seul `_args` est un champ
   - Decode `_args` (bound args du `partial`)
   - `resolve_handler(id)` via `sys.modules`
   - `_inject_signature_args` : path params + form keys matching kwargs
   - **Run handler** (sync ou async)
3. **Drain** : `drain_refresh_queue(app, ctx)`
   - Pour chaque `RefreshableHandle` dans `refresh_queue` → re-render sous `oob=True`
   - Si pas de refresh mais delta state OU notifications pending → emit un body minimal avec juste ces fragments
   - Si rien : `None` → 204 vide
4. **Réponse** : `RenderResult(body, status, headers, cookies)`

---

## `@refreshable` — section avec id stable

Décorateur **libre** (`from bretzel import refreshable`) — il ne touche pas
l'instance app. La zone se résout à la requête via `sys.modules` (même
schéma que les action handlers), donc l'enregistrement est implicite :
binder le résultat à un nom de module SUFFIT.

```python
from bretzel import refreshable, ui

@refreshable(deps=[TodoState])          # re-render auto quand TodoState change
def todo_list() -> None:
    state = TodoState()
    with ui.vstack():
        for it in ui.each(state.items, key="id"):
            ui.text(it["label"])
```

Ce que la décoration fait :

- Wrap dans une `RefreshableHandle` callable.
- Donne un `id = refresh_<sha1[:8](module.qualname)>` stable entre les renders.
- L'id atterrit comme `id="…"` + `bz-id="…"` sur l'élément racine de la section.
- Enregistre la zone dans `_ZONES_BY_DEP[State]` pour chaque `State` de `deps=`.
- **Refuse une zone qui déclare un paramètre nommé** (`_reject_parameters`,
  depuis le 2026-09-04).

### Une zone ne prend pas de paramètre

Le rendu de page passe par `__call__(*args, **kwargs)`, mais le
rafraîchissement appelle la poignée **nue** (`render/partials.py`). Une
signature paramétrée vit donc deux vies :

| ce qu'on écrit | ce qui arrive |
|---|---|
| `def zone(x)` | la page s'affiche, puis **500** à la première action qui touche un `deps` — sur le re-rendu, pas sur la page |
| `def zone(x=0)` | rien ne lève : la page rend `zone(3)`, chaque rafraîchissement rend `zone(0)` |

Les deux sont refusées **à la décoration**, donc au chargement du module.
Le fond : une zone est re-rendue *hors de son appelant*, donc tout ce dont
elle a besoin doit être joignable depuis elle — un état. Deux pages qui
appelleraient la même zone avec deux arguments partageraient de toute
façon un `id` et un `name` uniques : le modèle n'a nulle part où ranger la
différence.

`*args` / `**kwargs` restent acceptés — une signature ne dit pas ce qu'un
`**kwargs` porte, et les refuser reviendrait à juger sur le nom. Le
résidu : une zone variadique appelée AVEC des arguments les perd au
rafraîchissement, en silence.

Remède quand on croit avoir besoin d'un paramètre : le lire dans un état,
ou garder une fonction ordinaire paramétrable que la zone appelle.

**Deux façons de déclencher un re-render** (une seule direction, IA-friendly) :

- **Déclaratif (défaut)** : `deps=[State]`. Un handler mute le state → le
  snapshot-diff détecte le changement net en fin d'action → la zone est
  enqueuée automatiquement. Aucun appel.
- **Impératif** : la fonction libre `refresh(zone_ou_nom)`, appelable de
  partout (handle type-safe OU `name=` en str). Elle absorbe l'ancienne
  méthode `.refresh()` ET l'ancien `publish()` (tous deux **supprimés**).
  `broadcast` sur la zone → fan-out SSE aux autres onglets en plus.

### `deps` et `broadcast` — deux listes, une seule question

**Qui change cet état ?** C'est ça que les deux listes séparent, et elles
sont **orthogonales** : aucune règle d'inclusion, aucune ne dérive de
l'autre.

| qui le change | où on l'écrit | ce que ça coûte |
|---|---|---|
| **moi**, par mon action | `deps` | re-rendu DANS la réponse — un aller-retour, un swap |
| **les autres** (autre onglet, autre utilisateur, un job) | `broadcast` | signal SSE puis refetch — deux allers-retours |
| **les deux** | les deux listes | instantané pour moi, poussé aux autres |

```python
@refreshable(deps=[Cart])                              # purement local
@refreshable(broadcast=[FileAttente])                  # je ne le change jamais
@refreshable(deps=[Deals], broadcast=[Deals])          # les deux chemins
@refreshable(deps=[Deals, MesPrefs], broadcast=[Deals])
```

Nommer un état dans les deux listes **n'est pas une redondance** : ça dit
« je veux les deux chemins ». Et un `broadcast=` **seul** est légitime —
c'est le cas « cet état, je ne le change jamais moi-même ».

⚠️ **Le défaut que ça répare.** Jusqu'au 2026-08-23, `broadcast` était un
booléen et `deps` servait les deux rôles à la fois : y déclarer la
préférence d'un utilisateur aurait fait refetcher **tous** les clients dès
qu'une seule personne change son réglage. La zone temps réel
d'`examples/crm` ne suivait donc pas le changement de portefeuille de la
direction — pas par oubli, faute de pouvoir l'écrire.

⚠️ **`broadcast=True` est supprimé**, pas déprécié : il voulait dire
« tous mes deps », donc il recoud exactement les deux listes qu'on vient
de séparer, et il donnerait une seconde façon d'écrire
`deps=[X], broadcast=[X]` (principe 4). Il lève, avec le message de
migration.

Ce qui traverse n'est qu'un **signal** : chaque client refetch dans SON
contexte, aucune donnée ne passe d'un client à l'autre. Le coût d'une
sur-diffusion est du bruit, pas une fuite.

Gaté par `tests/integration/test_a_zone_broadcasts_only_what_it_declares.py`,
qui mesure ce qui part **sur le fil** et pas ce que la zone déclare.

À l'init de page : on appelle `todo_list()` comme une fonction normale → la section est rendue inline dans la page.
À l'action : un changement de `TodoState` (ou `refresh(todo_list)`) → re-render OOB ciblant le même `id`.

### Une zone peut être `async` — et s'appelle pareil

```python
@refreshable(deps=[Contacts])
async def liste() -> None:
    rows = await db.fetch("select * from contacts")
    for r in rows:
        ui.text(r["nom"])

@page("/")
def home() -> None:
    liste()          # PAS `await liste()`
```

La convention d'appel ne change pas avec l'asynchronie du corps, et c'est
une décision : un `await` à écrire serait un `await` à oublier, et
l'oublier redonne une zone VIDE sans erreur — la panne exacte qui vivait
ici jusqu'au 2026-08-21.

Mécanique : `RefreshableHandle.__call__` pose la **section** dans l'arbre
tout de suite — la place de la zone dans la page se décide à l'appel, pas
quand sa donnée arrive — puis empile `(section, coroutine)` dans
`ctx.pending_async_zones`. `drain_pending_async_zones(ctx)` attend ensuite
les corps, section repoussée sur `parent_stack` pour que les enfants
atterrissent au bon endroit. **Deux appelants** : `pipeline` (page
complète) et `partials._render_one` (fragment OOB / refetch SSE) — une
zone se rend par les deux, et n'en drainer qu'un donne une zone pleine au
premier affichage et vide à chaque refresh.

Deux propriétés du drain, chacune pour une façon de se tromper :

- **en boucle** : une zone async peut en appeler une autre, qui s'ajoute à
  la file pendant qu'on attend la première ;
- **en série, jamais en `gather`** : les corps partagent `parent_stack`,
  donc deux corps concurrents enregistreraient leurs enfants l'un chez
  l'autre. La concurrence se prend **dans** un corps (`asyncio.gather` sur
  ses requêtes), là où elle ne traverse pas la pile.

Gaté par `tests/integration/test_an_async_zone_renders_on_both_paths.py`,
qui exerce les deux chemins et le cas imbriqué.

**Idiomorph note** : les swaps OOB passent par `hx-swap-oob="morph"` — donc **via idiomorph**. Primary comme extras shippent tous `hx-swap-oob="morph"` (pas de cas spécial `morph:innerHTML` ; `_render_one` pose `"morph"` pour chaque section — cf. `partials.py`). L'id stable est CRITIQUE — un id qui change entre deux renders → le morph rate sa cible silencieusement.


**Une zone qui lève au drain n'emporte plus les autres** (2026-09-05).
Elle rend une alerte d'erreur à sa place, les zones valides partent
normalement, et le drain va au bout — donc `commit()` s'exécute.

Le troisième point est le vrai : `commit()` vient **après** le drain, et
une exception y annulait donc les mutations du handler. Un bug
d'affichage effaçait l'enregistrement demandé, sans un message — htmx ne
swappe pas sur un non-2xx, alors l'utilisateur voyait juste sa page ne
rien faire. Le commit n'a pas été déplacé pour autant : un corps de zone
peut lui aussi muter l'état, donc commiter plus tôt perdrait ces
écritures.

Le détail de l'exception suit `expose_errors`, jamais `debug` — c'est
déjà la ligne du framework pour les pages d'erreur (`routing/errors.py`),
une décision d'exposition et non de verbosité.

⚠️ **Le rendu de PAGE n'est pas isolé**, et c'est voulu : l'exception
remonte à `@error_page`. Là, il n'y a pas d'autre contenu valide à
sauver, et l'avaler donnerait une page à moitié vraie. Gaté dans les
deux sens par
`tests/integration/server/test_a_broken_zone_does_not_sink_the_response.py`.
---

## `ui.each(items, key=...)` — keyed iteration

```python
for item in ui.each(state.items, key="id"):
    ui.checkbox(checked=item["done"], …)
```

Pousse la `key` sur `parent_stack` au moment de chaque tour → les composants stateful enfants gardent leur identité même si la liste se réordonne. Sans `each`, un `for natif` provoque des collisions de bz-id (positionnel) qui cassent le morph.

Toujours `ui.each` quand l'itération produit des composants à état (checkbox, dialog ouvert, etc.). Pour des éléments purement statiques (`ui.text` × N), un `for` Python suffit.

---

## La drain post-action — détaillée

```python
async def drain_refresh_queue(app, ctx):
    if not ctx.refresh_queue:
        # Pas de refresh — mais on a peut-être des deltas/toasts à envoyer
        pieces = []
        delta_html = _render_delta(ctx)
        if delta_html: pieces.append(delta_html)
        notif_html = serialise_pending(ctx.notifications)
        if notif_html: pieces.append(notif_html)
        return RenderResult(body="\n".join(pieces), …) if pieces else None

    # Sinon : render chaque section, append delta + notifs en queue
    primary = ctx.refresh_queue[0]
    extras = ctx.refresh_queue[1:]
    return await render_partial(app, primary, ctx=ctx, extra_handles=extras)
```

→ Un handler qui ne refresh rien mais notifie un toast → la réponse
contient juste un `<bz-patch>` sous la clé réservée `_notifications` (le
`<script>` inline était le transport V2).

→ Un handler qui mutate un ClientState mais ne refresh aucune section → la réponse contient juste le `<bz-patch>` (format wire V3) qui patch le store côté client.

### Une zone imbriquée n'expédie qu'un fragment

Deux zones qui lisent le même état et dont l'une contient l'autre sont
**toutes les deux** dans la file : `enqueue_deps` ne voit que des `deps`.
Le parent rend pourtant déjà son sous-arbre, enfant compris. Sans rien,
le contenu de l'enfant partait deux fois — trois à trois niveaux — et le
morph en jetait la moitié, sans un mot. Mesuré : 19 692 → 9 906 octets à
deux zones de 200 lignes, 29 720 → 10 027 à trois.

`render_partial` retire donc de la file toute zone qu'un fragment déjà
émis CONTIENT — lu dans l'arbre produit (`_zone_ids_inside`), pas dans
une table de qui-contient-qui : l'imbrication est un fait de rendu, et
elle peut être conditionnelle. Deux zones **sœurs** gardent chacune la
sienne. Gaté par
`tests/integration/test_a_nested_zone_ships_once.py`.

---

## `current_context()` vs `maybe_current_context()`

- `current_context()` : raise `RuntimeError` si pas de contexte. Utilise dans le code "render-time" qui n'a aucun sens hors requête.
- `maybe_current_context()` : retourne `None`. Utilise dans le code shared (helpers appelables depuis n'importe où). Permet le degrade graceful.

Exemple : `ui.notification(...)` utilise `maybe_current_context()` → no-op silencieux hors requête. La fonction libre `refresh(...)` pareil. C'est volontaire — le code shared (helpers appelés de partout) degrade proprement hors d'une requête.

---

## `head_title` / `head_extras` — `ui.title()` / `ui.meta_tag()`

Pour pousser un `<title>` ou des `<meta>` user dans le `<head>` du shell :

```python
from bretzel import page, ui

@page("/")               # décorateur libre — marque seulement ; main.py
def home():              # ramasse via app.include(...) (cf. app-structure.md)
    ui.title("My page")
    ui.meta_tag(property="og:image", content="...")
    # … reste du body
```

`ui.title()` écrit `ctx.head_title` (une string) ; `ui.meta_tag()` append un `<meta>` à `ctx.head_extras`. Le shell lit **les deux** en assemblant le `<head>`, après les meta de base + l'envelope. (`ui.meta_tag` : exactement UN identifiant parmi `name=` / `property=` / `http_equiv=`, plus `content=`.)

---

## La langue — résolue par REQUÊTE, pas par application

```python
app = Bretzel(lang="en", languages=["en", "fr"], texts={"fr": FR})
```

Une app qui ne déclare rien est monolingue et rien ne change pour elle :
`languages` est **normalisé à `(lang,)`**, pas laissé vide — deux
représentations du même état obligeaient trois modules à tester le vide
séparément. La langue est choisie à chaque requête par
`render.lang.resolve_language`, pair de `render/screen.py`, dans cet
ordre :

1. le cookie `bz_lang`, s'il nomme une langue déclarée ;
2. `Accept-Language`, négocié contre `languages` ;
3. `lang=`.

**L'ordre est le sujet, et il n'est pas un goût** : c'est celui de
Django (`LocaleMiddleware`), de Rails et de next-intl. L'en-tête décrit
la configuration de l'OS, pas un choix de lecture — quelqu'un dont le
système est anglais mais qui lit en français doit pouvoir le dire, et
une page qui dépend du seul en-tête n'est plus adressable (deux
personnes ouvrant la même URL voient deux pages, et le cache doit
`Vary`). L'inverser ne casse **rien de visible** : seul le sélecteur de
langue cesse d'avoir un effet. D'où
`tests/integration/test_the_language_is_resolved_per_request.py` et
`tests/probes/probe_lang.py`, qui mesure les deux bouts au navigateur.

**Les tables de mots sont un objet, pas un dict indexé.**
`config.texts` reste ce que l'utilisateur a écrit ; `config.text_tables`
(`render.lang.LanguageTables`) est dérivé et s'INTERROGE —
`for_language(code)` retombe sur la langue par défaut. La première
version indexait `cfg.texts[resolved]`, ce qui tenait par un invariant
non écrit réparti sur trois fichiers, et dont la rupture n'aurait pas
donné un repli mais une `KeyError` sur chaque requête.

`Language.set(code)` (`render/lang.py`) est le sélecteur : il
pose le cookie puis appelle `bretzel.reload()`. Celui-ci est le
pendant de `redirect()` pour le cas où la cible EST la page courante —
un changement de langue, de locataire, de devise. Il passe par
`HX-Refresh` et non par `redirect()` parce que le navigateur connaît son
URL et le serveur non : une action POSTe vers `/_bretzel/action/<id>`,
donc `redirect()` demanderait de lire le `Referer`. Et il RECHARGE au
lieu de re-rendre parce qu'une réponse d'action ne rapporte que les
zones qu'elle a rafraîchies : sur un changement qui touche toute la
page, un re-rendu partiel en laisserait la moitié dans l'ancien état.

### Ce que ça traduit, et ce que ça ne traduit pas

Les mots que le **framework** écrit (`texts=`), plus tout ce qui se
DÉRIVE d'un code de langue — et c'est le gain caché : les noms de mois
et de jours du calendrier et des quatre pickers viennent d'`Intl` **dans
le navigateur**, à partir du `<html lang>` que le shell pose. Ils suivent
donc sans qu'une seule traduction soit écrite. Le HTML servi ne contient
aucun nom de mois, ce que le probe vérifie avant même d'ouvrir Chromium.

Les chaînes de l'**app**, non — aucun framework ne les traduit, il donne
où les ranger. `bretzel.lang()` rend la langue résolue, et un dict par
langue fait le reste :

```python
STRINGS = {"en": {"save": "Save"}, "fr": {"save": "Enregistrer"}}

def t(key, **fmt):
    return STRINGS.get(lang(), STRINGS["en"])[key].format(**fmt)
```

Catalogues, extraction, `.po`, pluriels par langue : v2.1, pas ici.

⚠️ `month_names=` / `weekday_names=` **désactivent** la langue
automatique — ce sont des listes Python sans axe de langue, donc une app
qui les passe fige une langue pour tous ses visiteurs. Ça reste
l'échappatoire tier 2 légitime : `Intl` rend `janvier` et `dim.` là où
le CRM veut `Janvier` et `Di`, et c'est un choix typographique que
personne ne peut deviner. Mesuré le 2026-08-28 — ces listes ne sont donc
PAS redondantes avec `lang=`, contrairement à ce qu'on pourrait croire.

## La barre de navigation — allumée par défaut, et sans mécanisme à elle

Le shell injecte `<div id="bz-nav-progress">` dans chaque page
(`render/shell.nav_progress_html`). Sur une page qui met 800 ms à
revenir, on clique et rien ne bouge — donc on reclique.

**Ce n'est pas un second mécanisme de chargement.** C'est le signal de
`ui.pending()` lu sur une clé réservée : le bridge arme
`NAV_PENDING_KEY` (`"@nav"`, dans `runtime/protocol.py`) quand la
requête en vol est une navigation, et la barre n'est qu'un `bz-show`
de plus. Même registre, même seuil de 200 ms, même désarmement.

Deux formes de navigation dans le dépôt, et le bridge teste les deux —
en tester une seule laisse la moitié des menus sans barre :

| forme | ce qui la reconnaît | qui l'émet |
|---|---|---|
| lien boosté | `detail.boosted` | le `hx-boost` posé au niveau document par le shell |
| nav partielle | `hx-push-url="true"` sur le déclencheur | `navigation/_wiring.py` (sidebar, navbar) |

C'est le SEUL témoin de chargement que le framework allume sans qu'on
le demande, et la raison tient en une phrase : il n'a aucune décision
de placement à poser. Une bande en bord d'écran, une par app, jamais
dans le flux. Un témoin d'action en vol, lui, doit dire OÙ il
s'affiche — d'où `ui.pending()`, explicite. `Bretzel(nav_progress=False)`
l'éteint (et retire la keyframe avec).

Ce n'est pas un `ui.progress` : aucune progression n'est connue, donc
une fraction serait inventée. Bande indéterminée, `bg-primary`
littéral, `z-50` (le haut de l'échelle de la maison), et un repli
immobile sous `prefers-reduced-motion`.

Gates : `test_shell.py::TestNavProgress`,
`test_no_build_token_survives_in_the_bundle.py` (la clé réservée est
substituée au build depuis `protocol.py` — un jeton oublié partirait
en littéral, sans que rien ne lève), et
`tests/probes/probe_nav_progress.py` pour le seuil et les deux formes.

## Cookies, headers de réponse

```python
def my_handler():
    ctx = current_context()
    ctx.set_cookie("pref", "dark", max_age=3600*24*30)
    ctx.delete_cookie("old_pref")
    ctx.response_headers["X-Custom"] = "v"
```

Appliqués par le middleware à la réponse finale (post-render).
