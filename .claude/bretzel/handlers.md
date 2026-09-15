# Handlers — les règles de l'event dispatch

Source : `bretzel/components/base/events.py` + `bretzel/server/handlers.py` + `bretzel/server/routing/actions.py`.

---

## Pourquoi ces règles existent

V2 résout les handlers **statelessly** — l'id rendu en HTML est un chemin d'import (`module::qualname`), signé HMAC. À l'arrivée du POST, le serveur fait `sys.modules[module].qualname()`. **Pas de table d'actions stockée par page.**

Ça veut dire :

- Tout handler doit être **adressable par chemin d'import** (= module-level OU décoré).
- Toute donnée à passer au handler doit voyager **avec le POST** (pas via une closure capturée au render).

V1 stockait les handlers dans une table par page → lambdas + closures fonctionnaient mais coûtaient une table par utilisateur. V2 a fait l'inverse : plus simple côté serveur, plus strict côté API.

---

## Ce qui est accepté dans `on_click=` (et autres `on_*`)

| Forme | OK ? | Note |
|---|---|---|
| Module-level callable | ✅ | `on_click=delete_item` |
| `@staticmethod` / `@classmethod` adressable | ✅ | qualname avec `Class.method` |
| `functools.partial(handler, *args, **kwargs)` | ✅ | bound args base64-JSON dans le **body POST** (émis en `hx-vals` → champ `_args`, lu depuis `form_data`) |
| chaîne client | ✅ (cas client) | ex: `on_click="open = false"`, ou produit par `binding.set(...)` |
| `ClientExpression` (résultat d'op sur `ClientBinding`) | ✅ | sérialisé via `__str__` |
| `list[Callable | str | ClientExpression]` | ✅ | composer serveur + N actions client (cf. plus bas) |
| Lambda | ❌ | `HandlerError` au render |
| Closure (`def inside_function`) | ❌ | `HandlerError` au render |
| Méthode d'instance | ❌ | non-adressable par sys.modules |

---

## Un handler SYNCHRONE ne bloque pas le serveur (2026-09-04)

Écris `def`, ou écris `async def` — les deux sont servis, et le cas
courant EST le `def` (mesuré : `examples/` porte 1 659 `def` pour
16 `async def`, parce que `state.n += 1` n'a rien à attendre).

```python
def export_pdf():        # bloquant : base sync, requests.get, time.sleep
    ...                  # → délesté sur le threadpool de Starlette

async def fetch_rows():  # → attendu sur la boucle, sans saut de thread
    ...
```

Le framework le décide seul, partout où du code d'app est appelé : le
handler d'une action, le corps d'une page et de ses layouts, **le
rabattage de l'arbre** (c'est là que se rappellent le `rows=` d'un
`ui.datatable` et le `render=` d'une colonne), le corps d'une zone
rendue seule (OOB / refetch SSE), le `rows=` d'un export CSV, la
fonction d'un `@download`, la callback d'une porte `@auth.door`, les
hooks de cycle de vie. Tous passent par
`bretzel.core.call_without_blocking` ; rien à déclarer, donc rien à
oublier de déclarer.

Le `rows=` du datatable mérite sa ligne : le framework **refuse** qu'il
soit une coroutine (`render()` est synchrone), donc c'est le framework
lui-même qui garantit un appel bloquant — et jusqu'ici il le lançait sur
la boucle, à chaque rendu de page.

**Pourquoi ça compte.** Jusqu'à cette date, un `def` bloquant tournait
dans le thread de la boucle : pendant ses deux secondes, le worker ne
servait plus AUCUNE requête et les heartbeats SSE s'arrêtaient — pour
tous les utilisateurs connectés, pas seulement celui qui a cliqué. Rien
ne levait, rien ne s'affichait ; ça se lit comme « le serveur est
tombé ». Mesuré sur un blocage de 600 ms, une seconde requête mettait
539 ms à être servie ; elle en met 13 aujourd'hui.

**Ce que ça coûte** : 0,19 ms de saut de thread (p95 0,78) sur un
aller-retour d'action qui en pèse 2,90. Et un plafond : le pool fait 40
threads, donc 41 handlers bloquants simultanés font attendre le 41ᵉ —
sans commune mesure avec une boucle gelée, où c'est le worker entier
qui s'arrête.

⚠️ **Deux conséquences à connaître**, les deux dans `traps.md` §
*Serveur* :

- un `ContextVar.set()` fait dans un handler synchrone ne remonte pas
  au-delà de l'appel (le thread reçoit une COPIE du contexte). Lire ce
  que le framework a posé marche ; poser quelque chose pour la suite de
  la requête, non — accroche-le au `RenderContext` ;
- deux handlers `def` peuvent maintenant tourner **en même temps**. La
  boucle mono-thread les sérialisait ; elle ne le fait plus. Un
  `state.counter += 1` sur un état partagé peut perdre un incrément
  entre deux onglets, là où il fallait avant deux workers.

Gaté par `tests/consistency/test_app_code_never_runs_on_the_loop.py`
(la forme interdite, et les quatre portes nommées) et par
`tests/integration/server/test_blocking_app_code_frees_the_loop.py`
(deux threads, une boucle, on mesure le temps).

---

## Passer un argument à un handler — `functools.partial`

C'est **le pattern V2** quand chaque ligne d'une liste a son propre `id` à passer.

```python
from functools import partial

def delete_issue(issue_id: str) -> None:
    store = IssueStore()
    store.issues = [it for it in store.issues if it["id"] != issue_id]
    # Pas de refresh manuel : issues_table déclare deps=[IssueStore], le
    # snapshot-diff détecte la mutation → re-render auto en fin d'action.

# Dans la render :
@refreshable(deps=[IssueStore])
def issues_table() -> None:
    store = IssueStore()
    for it in store.issues:
        ui.icon_button("trash-2", on_click=partial(delete_issue, it["id"]))
```

Côté plomberie :

1. `encode_handler_id(partial)` unwrap → renvoie l'id de la fonction sous-jacente.
2. `encode_args(partial)` extrait `args` + `kwargs` → blob base64-JSON.
3. Le composant émet le bundle `hx-post` + `hx-trigger:click` + `data-bz-sig` (via `action_attrs`).
4. Le bridge JS POSTe sur `/_bretzel/action/<id>` : le blob `_args` part en form field (émis via `hx-vals` au render), la sig dans le header `X-Bz-Sig` (+ l'horodatage dans `X-Bz-Ts`). (Le wire query-param `?_args=&_sig=` était le V2 — périmé.)
5. Le serveur vérifie HMAC, decode `_args`, fait `handler(*args, **kwargs)`.

**Contraintes sur les bound args** : `str / int / float / bool / None / list / dict` uniquement (JSON-serializable). Pas d'objets custom, pas de `Decimal`, pas de `datetime`. Échec → `HandlerResolutionError` au render (fail-fast).

**État actuel** : branché end-to-end. `register_action` (render/context.py) appelle `encode_args(handler)` + `sign_action(action_key, id, blob, ts)` (clé **dérivée**, pas le secret maître ; le `ts` render-time est signé aussi). Il retourne un tuple `(action_id, args_blob, sig)` que `action_attrs` émet en **attributs HTMX natifs séparés** : `hx-post=/_bretzel/action/<id>`, `hx-vals={"_args": blob}`, `data-bz-sig=<sig>`, `data-bz-ts=<ts>`. **Aucun token pipe-délimité `<id>|<blob>|<sig>` ne part sur le wire** — le `<id>|<blob>|<ts>` n'existe qu'en interne comme payload de signature HMAC (`handlers.py`). Le bridge JS (05) rejoue ces attributs, POSTe `_args` en form field + la sig en header `X-Bz-Sig`. `_inject_signature_args` côté serveur passe les args positionnels au handler.

---

## Composer serveur + actions client en un clic

```python
ui.button(
    "Delete",
    on_click=[delete_issue, ui_state.confirm_open.set(False)],
    #          ^^ callable          ^^ chaîne client
)
```

La base décompose la liste :

- 0 ou 1 callable → routé en `on_click=` (server).
- N strings → joints avec `;` et émis en `bz-on:<event>=` (client, fire en parallèle).
- 2+ callables → `ComponentUsageError` (un seul handler serveur par event).

Use case canonique : optimistic close (le dialog ferme côté client *immédiatement*, le serveur fait son boulot en parallèle, le toast confirme quand la réponse atterrit).

---

## Lecture des données du POST

Le handler n'a pas d'argument du dispatcher. Il lit ce qu'il veut depuis la requête courante :

```python
def my_handler(issue_id: str) -> None:    # args: bound via partial
    extra = (get("extra_field") or "").strip()  # form data
    ...
```

- **Args positionnels / kwargs** : viennent du `partial` (rid via `_args`).
- **Form data** : `get("name")` ou un State typé. Inclut tout ce qu'envoie le navigateur (input names, button name+value, hidden inputs).
- **Path params** : signature-injectés (`async def fn(id: int)` avec route `/foo/{id}` → `id` peuplé).

---

## Tâche après-réponse — `@background` (juin 2026)

Pour du fire-and-forget qui doit tourner APRÈS l'envoi de la réponse
(email, analytics, cache warmup, une boucle d'animation SSE) :

```python
from bretzel import background          # ← fonction libre, pas app.background

@background
async def send_welcome(user_id: str):
    await mailer.send(user_id)

def signup():                       # handler d'action normal
    user = save(...)
    send_welcome.schedule(user_id=user.id)   # enfilé, pas attendu
    # signup() rend tout de suite ; send_welcome tourne après la réponse
```

- `@background` enveloppe une coroutine dans un `BackgroundHandle`.
  `.schedule(**kwargs)` l'enfile sur le `BackgroundTasks` de la requête
  courante (contextvar bindée par le route d'action) ; Starlette la draine
  après le body. Hors requête → `BackgroundContextError` (le hint pointe
  vers `await fn(**kwargs)` direct).
- **Ce que ce n'est PAS** : ni job queue (retries/persistance), ni planifié
  périodique en soi, ni substitut au broadcast SSE (`broadcast=[State]`).
  Best-effort : une task qui lève est loggée, jamais ne crash le worker
  (la réponse est déjà partie).
- **PAS pour une animation PAUSABLE.** `@background` est fire-and-forget
  **non annulable** : une boucle `for _ in range(ticks): sleep; muter+refresh`
  tourne
  jusqu'au bout même si l'user met Pause (contextless → ne peut pas lire l'état)
  → requêtes orphelines + re-renders en boucle. Pour une cadence **contrôlable**
  (run/pause), utiliser **`ui.interval`** (timer client gaté sur un
  `ClientBinding` → flip = clear instantané ; cf. ``bretzel describe``). Le stepper
  qui a motivé la bascule `@background`+SSE → `ui.interval` vivait dans la
  famille *matrix* du playground, supprimée le 2026-08-30 (son chemin
  n'est plus cité ici : il n'existe plus, et
  `test_documented_paths_exist` le refuse) ; la démo vivante est la carte
  *Interval* de `features/meta.py`. `@background` reste pour le one-shot
  après-réponse (email, analytics, cache warmup). Impl :
  `bretzel/server/decorators/background.py`.
- **C'était `@app.background` jusqu'au 2026-08-15** — une méthode
  d'instance qui n'utilisait pas `self`, pendant qu'`@idempotent`, de même
  nature, était une fonction module. Deux formes pour une seule chose.
  `background` est maintenant `from bretzel import background`, gardé par
  `tests/consistency/test_handler_helpers_have_one_home.py`.

---

## `@page` ou `@app.page` ? La règle (août 2026)

Bretzel a **deux formes de décorateur**, et laquelle s'applique n'était
écrit nulle part avant le 2026-08-20 — seulement en « Free decorator — »
dans quatre docstrings. La règle :

| forme | lesquels | pourquoi |
|---|---|---|
| **libre** — `from bretzel import …` | `@page` `@layout` `@refreshable` `@error` `@background` `@idempotent` | ils vivent dans une **feature**, et une feature ne doit pas connaître l'app (anti-règle 4 : pas d'enregistrement à l'import). Ils se contentent de MARQUER la fonction ; `app.include()` ramasse les marques |
| **sur l'instance** — `@app.…` | `@app.middleware` `@app.startup` `@app.shutdown` | ils vivent dans `main.py`, la **racine de composition** — le seul fichier qui a le droit de connaître l'instance |

Le test pour un décorateur neuf : *est-ce qu'une feature aurait besoin de
l'écrire ?* Oui → libre. Non, ça ne se déclare qu'une fois pour l'app →
sur l'instance.

⚠️ Ce n'est pas cosmétique. Un décorateur libre qui enregistrerait
vraiment ferait dépendre le comportement de l'**ordre des imports** —
c'est précisément ce que l'anti-règle 4 interdit, et c'est pour ça que
`@page` stampe `_bz_page` au lieu de monter la route lui-même.

---

## Garder des pages derrière un login — le middleware (août 2026)

La garde d'auth est un **middleware**, pas un `@page(auth=…)`. Un kwarg
par page met la politique de sécurité en défaut-OUVERT : une page ajoutée
sans le kwarg fuit en silence. Un middleware est en défaut-FERMÉ — tout
est protégé sauf une liste publique explicite.

```python
from bretzel import auth
from bretzel.server import action_path, redirect_response

PUBLIC = {"/login", action_path(login.sign_in), *app.public_paths}

@app.middleware
async def require_login(request, call_next):
    if request.url.path in PUBLIC or auth.user_id(request):
        return await call_next(request)
    return redirect_response(request, "/login")
```

⚠️ **`action_path(login.sign_in)` n'est pas décoratif**, et c'est la
ligne que deux apps sur deux ont oubliée. Le formulaire de connexion
**POSTe une action**, qu'une garde en défaut-fermé bloque comme le reste.
Le symptôme ne ressemble à rien : htmx suit la redirection en
transparence, le HTML de `/login` revient dans la réponse, et **le bouton
paraît mort** — aucune erreur, nulle part. Une action publique par
formulaire public.

⚠️ **`app.public_paths` n'est pas décoratif.** Il porte deux familles que
l'app ne peut pas connaître : les assets du runtime (`PUBLIC_ASSET_ROUTES`
— le runtime et les deux feuilles, servis sous `/_bretzel`, dont une page
de connexion a besoin **avant** que quiconque soit connecté, sans quoi
elle s'affiche sans style et son formulaire ne POSTe pas), et **les deux
routes de chaque porte `@auth.door`**. Oublier la seconde de ces deux-là
produit une boucle de redirection dont le symptôme ne désigne rien : le
fournisseur renvoie, la garde refuse, on repart chez le fournisseur.

Et ce que la constante évite surtout, c'est le raisonnement inverse :
**tout le reste de `/_bretzel` doit rester FERMÉ**, ce qui n'a rien
d'évident. `/_bretzel/refetch/…` re-rend une zone, `/_bretzel/sse` pousse
les signaux qui déclenchent ces refetch, `/_bretzel/action/…` exécute du
code d'app et `/_bretzel/datatable.csv` exporte des lignes. Ouvrir
`/_bretzel` en bloc, c'est laisser une app entière se rendre pour un
anonyme.

Le classement appartient donc à celui qui monte les routes, pas à l'app,
et il est gaté : `tests/consistency/test_framework_routes_are_classified.py`
lit les routes réellement montées et rougit sur une route non classée.
*(Trouvé par `examples/crm`, premier exemple à écrire une garde — il
énumérait les trois chemins à la main, plus un quatrième que personne ne
monte.)*

**Le piège que `redirect_response` absorbe** — et qu'il ne faut surtout
pas recopier à la main : un middleware voit **deux natures de requête**.

| Requête | Ce qu'il faut rendre | Si on se trompe |
|---|---|---|
| GET de page | une vraie `302` | — |
| POST d'action (bridge) | `200` + `HX-Redirect` | une 302 est suivie **en transparence** par `fetch`, et le HTML de `/login` finit swappé **dans le bouton** |

`redirect_response(request, url)` tranche pour toi, sur l'en-tête
`HX-Request`. La nav partielle boostée compte comme requête htmx.

⚠️ **`auth.user_id(request)` — avec la requête — est la SEULE lecture
d'identité qui réponde ici**, et c'est structurel : à ce niveau ni
`auth.user_id()` nu ni `request.state.user_id` ne répondent. Le premier
lit le contexte de rendu, qui n'est posé que pendant le rendu de la page
(`render/pipeline.py`, `use_context`) ; le second est écrit par
`AuthMiddleware`, plus INTERNE que ton middleware. Il ne reste que la
requête — et cette fonction en tire l'identité en jouant la chaîne
complète (cookie signé, puis les sources `@auth.source`), clé dérivée
comprise.

Elle rend l'**identifiant**, pas un booléen. Une garde qui veut juste
savoir « connecté ? » teste la vérité de la valeur ; une garde qui
journalise ou qui autorise par rôle a le nom sans relire le cookie.

*(Elle n'existe que depuis le 2026-08-23. Avant, cette recette s'arrêtait
juste avant ce point et laissait écrire `is_signed_in(request)` sans dire
comment — la seule écriture possible passait par `app.config._auth_key`,
un attribut privé, sur le chemin le plus sensible d'une app. Le manque
était noté depuis le 2026-08-14 avec la prédiction « tout le monde va le
copier » ; `examples/crm` l'a copiée, ce qui a débloqué la correction.
Bout en bout :
`tests/integration/server/test_a_middleware_reads_the_signed_in_user.py`.)*

⚠️ **`redirect()` n'est PAS appelable depuis un middleware.** Un middleware
utilisateur est le plus EXTERNE (`lifecycle.py` : « user middlewares last
so they wrap everything above »), donc à l'inbound il tourne AVANT
`RenderContextMiddleware` : `current_context()` lève. C'est précisément
pour ça que `redirect_response` existe — pour que le middleware ait
quelque chose à **appeler** au lieu de quelque chose à copier.

**Ordre** : le PREMIER `@app.middleware` écrit est le plus externe (comme
le `MIDDLEWARE` de Django). Écris donc ta garde d'auth en premier.

⚠️ Historique utile : `@app.middleware` a été un **no-op complet** jusqu'au
2026-08-15 — la pile était construite dans `Bretzel.__init__`, donc figée
avant que le décorateur puisse tourner. Aucun symptôme : un middleware qui
ne tourne pas ne casse rien, il laisse passer. Sur une garde d'auth, c'est
le pire mode de panne. Gaté par
`tests/integration/server/test_user_middleware_actually_runs.py`.

---

## L'identité : qui est cette requête, et comment on entre (août 2026)

Deux questions, deux décorateurs **libres**, et c'est le partage qui
tient tout le sujet.

| Question | Ce qu'on écrit | Joué |
|---|---|---|
| **qui est cette requête ?** | `@auth.source` | à **chaque** requête |
| **comment devient-on connu ?** | `@auth.door(porte)` | **une** fois |

Le cookie signé de Bretzel est la réponse par défaut à la première, et
l'aboutissement obligé de la seconde : une porte ne remplace pas la
lecture, elle l'alimente en appelant `auth.login(user_id)`.

### `@auth.source` — les identités que Bretzel n'a pas signées

```python
from bretzel import identify

@auth.source
def from_bearer(request) -> str | None:
    token = request.headers.get("authorization", "")
    return subject_of(token) if token.startswith("Bearer ") else None
```

L'ordre est : **le cookie d'abord, les sources ensuite dans l'ordre
d'écriture**, première réponse non-`None` gagne. Ça couvre le JWT porté,
la clé d'API, l'en-tête posé par un proxy SSO (`X-Remote-User`, IAP,
Cloudflare Access) et la session empruntée à une app voisine.

⚠️ **Synchrone, et c'est un contrat.** La fonction tourne à chaque
requête, y compris depuis un middleware utilisateur ; une `async def`
est **refusée** au décorateur plutôt qu'attendue en silence. Une source
qui a besoin du réseau (rafraîchir un JWKS) le fait hors requête et sert
un cache.

⚠️ **Une source qui lève REMONTE.** Une identité avalée se lit
« anonyme », donc la garde referme la porte au nez de tout le monde sans
qu'aucune erreur ne s'affiche.

*(Ce que ça a réparé : jusqu'au 2026-08-23, `AuthMiddleware` lisait le
cookie lui-même et écrasait `state.user_id` APRÈS le middleware de
l'app. Une app qui résolvait son propre utilisateur recevait **401** sur
toute page à `UserState` — le charter disait « l'app fait son auth »
pendant que le code livrait un scope d'état qui n'existait que par le
cookie du framework. Gaté par
`tests/consistency/test_identity_is_read_in_one_place.py`.)*

### `@auth.door` — les portes OAuth / OIDC

```python
from bretzel import login_with, oauth

@auth.door(oauth.OIDC(name="google", issuer="https://accounts.google.com",
                       client_id=..., client_secret=...))
def google_user(profile: oauth.OAuthProfile) -> str | None:
    if not profile.email.endswith("@macorp.fr"):
        return None                      # refus
    return str(users.upsert(email=profile.email).id)
```

**Deux classes, aucun service nommé.** `oauth.OIDC(issuer=…)` couvre tout
ce qui publie une découverte — Google, Microsoft Entra, Auth0, Okta,
Keycloak, Authentik, GitLab, LinkedIn… — et `oauth.OAuth2(authorize=,
token=, userinfo=, subject=)` couvre le reste (GitHub, Discord, Slack,
Notion…). Un préréglage `oauth.Google(...)` figerait trois URL que
`/.well-known/openid-configuration` va chercher correctement pour
toujours : le catalogue est de la **donnée**, dans le code de l'app,
jamais de l'API ici.

Ce que la porte fait, et qu'on n'a donc pas à écrire : le `state` lié à
la session dans un cookie **signé**, le `nonce`, **PKCE** (S256),
l'échange du code hors navigateur, la vérification `iss` / `aud` / `exp`
/ `nonce` de l'`id_token`, et l'enregistrement de ses deux chemins dans
`app.public_paths`.

- **La fonction décorée est obligatoire, et c'est un choix de sécurité.**
  Sans elle, le défaut serait « toute personne ayant un compte chez le
  fournisseur entre » — un défaut-ouvert qui ne se voit jamais en
  relecture, parce que la page s'affiche parfaitement. Elle rend **ton**
  identifiant (celui de ta table), ou `None` pour refuser.
- **`profile.subject` n'est pas ton `user_id`** : c'est la clé de
  jointure chez le fournisseur. `profile.raw` porte le profil entier.
- **Aucune dépendance neuve.** Pas de vérification de signature JWT (le
  jeton arrive du token endpoint par TLS en réponse à notre POST
  authentifié — OIDC Core § 3.1.3.7), donc pas de `cryptography` ; et
  `urllib.request` poussé dans un thread par `anyio`, donc pas d'`httpx`
  en production. Corollaire : **Apple est hors de portée** (son
  `client_secret` est un JWT ES256), sauf à fabriquer le secret
  soi-même.

### Pourquoi des décorateurs LIBRES et pas `@app.identify`

C'est la règle du § précédent, appliquée : *une feature doit-elle pouvoir
l'écrire ?* Oui — la porte de connexion et le mappage du profil sont de
la logique d'app, pas de la composition. Un `@app.login_with` obligerait
`features/login.py` à importer l'instance, ce que `app-structure.md` § 9
interdit noir sur blanc (« `from myapp.main import app` dans une
feature. Jamais. »). Comme `@page`, ces décorateurs **marquent** ;
`app.include(...)` ramasse, et les portes sont montées au startup.

*(Bout en bout :
`tests/integration/server/test_a_login_door_opens_a_session.py` — le flux
complet contre un fournisseur simulé, plus les six refus.)*

---

## Changer de page depuis un handler — `redirect()` (août 2026)

La navigation est **déclarative** par défaut : un menu, un fil d'Ariane,
une ligne cliquable, c'est `ui.link(href=…)`, et la nav partielle est
gérée. `redirect()` couvre le seul cas qu'un lien ne PEUT pas porter —
l'URL n'existe qu'après la mutation :

```python
from bretzel import redirect

def save():
    invoice = create_invoice(...)
    redirect(f"/factures/{invoice.id}")   # ← l'URL vient de naître
```

- **Zéro code runtime.** Ça pose l'en-tête `HX-Redirect`, qu'htmx traite
  nativement (`render/shell.py` charge htmx complet), et qui voyage par
  `ctx.response_headers` — le canal que les trois sorties recopiaient
  déjà. Même schéma que `auth.login()` : une fonction appelée depuis un
  handler, dont l'effet transite par le contexte de requête.
- **Ce n'est pas un composant** : la forme V1 (`ui.navigate`) en était un,
  dont le `__init__` écrivait un en-tête de réponse selon un
  `ctx._is_action_context` invisible — un effet de bord dans un
  constructeur, et un « composant » qui ne rend rien.
  La règle qui tranche, écrite le 2026-08-15 et gatée par
  `tests/consistency/test_handler_helpers_have_one_home.py` : **`ui.*`
  s'appelle depuis un corps de rendu, `bretzel.*` depuis un handler**, et
  un helper de handler a **exactement un** point d'accès. Le critère n'est
  donc PAS « retourne un nœud » — `ui.notification` produit un toast sans
  rien retourner, et il reste dans `ui` parce que son effet est à l'écran.
  `ui.abort` en est sorti le même jour : il produisait un statut HTTP, et
  n'existait en double que pour contourner le DAG.
- **Pas de sortie non-locale**, contrairement à `abort()` : l'appel pose
  l'en-tête et le handler continue.
- **Lève sur un rendu de page NU** (htmx hors de la boucle → l'en-tête
  serait invisible). Une nav partielle boostée passe. Pour garder une page
  derrière un login, c'est un middleware (il peut répondre une vraie 302) ;
  pour la refuser, `abort(401)` + `@error_page(401)`.
- **Lève sur un CR/LF/NUL dans l'URL** — une URL de redirection vient
  souvent d'un `?next=`.
- Impl : `bretzel/server/errors.py`. Gates :
  `tests/integration/server/test_redirect_header.py` (l'en-tête traverse),
  `tests/runtime_js/test_redirect_actually_navigates.py` (le navigateur
  navigue vraiment).

⚠️ **Il n'y a PAS de kind `"redirect"` dans le protocole d'envelope**, et
il ne doit pas revenir. Le bridge en a lu un pendant des mois
(`window.location = err.url`) sans qu'aucun Python ne l'émette — ni ne le
PUISSE, `error_envelope(kind, message)` n'ayant pas de quoi porter une
url. Retiré le 2026-08-14, gaté par
`tests/consistency/test_bridge_error_kinds_are_emitted.py`, qui vérifie la
classe : tout `kind` sur lequel le bridge aiguille doit être émissible.

### La famille des trois — aller ailleurs, recharger, renommer

`server/navigation.py` possède **les trois façons d'agir sur la barre
d'adresse depuis une réponse**, et il n'y a aucun code runtime derrière :
ce sont des en-têtes qu'htmx traite nativement.

| tu veux | la fonction | l'en-tête |
|---|---|---|
| charger une autre page | `redirect(url)` | `HX-Redirect` |
| recharger celle-ci | `reload()` | `HX-Refresh` |
| **renommer sans bouger** | `push_url(url)` | `HX-Push-Url` |

`push_url()` est ce qui donne une **adresse à une vue** : trier une
table, choisir un filtre, ouvrir un onglet. Le contenu arrive par le swap
que l'action renvoie déjà ; la fonction ne fait suivre que la barre
d'adresse, et le bouton retour redemande l'URL au serveur.

⚠️ **Le socle l'appelle pour toi** dès qu'un champ déclaré
`addressable=True` a bougé (cf. `state.md` § *L'état DANS L'URL*).
L'appel direct est l'échappatoire — une adresse que le framework ne peut
pas deviner :

```python
def open_step(n: int) -> None:
    Wizard().step = n
    push_url(f"/inscription/etape-{n}")
```

Ne confonds pas avec `redirect()` : l'une fait charger une autre page,
l'autre ne fait que renommer celle qu'on regarde. Poser l'une pour
l'autre donne soit une navigation qu'on n'a pas demandée, soit une
adresse qui ment sur ce qui est affiché.

Les trois lèvent sur un rendu de page classique, où l'en-tête serait
ignoré en silence.

---

## Anti-patterns

❌ **Pas de `name=` / `value=` manuels dans le code app.** L'API user-facing est 100 % Python ; tout `name=` / `value=` qui apparaît dans une démo est un signal que :
- soit on a oublié d'utiliser `partial(handler, arg)` (cas per-row click)
- soit on a oublié l'autoname (cas form-input avec binding)
- soit le composant ne supporte pas encore une primitive qui devrait exister

Pour les boutons par ligne — `partial` :

```python
ui.icon_button("trash-2", on_click=partial(delete_issue, issue_id))
def delete_issue(issue_id: str): …
```

Pour les inputs de formulaire — autoname (cf. `components.md`) :

```python
class Draft(PageState):
    title: str = field(default="")

ui.input(value=draft.title)  # name="title" auto-derived
def submit(title: str): …    # signature-injected from form data
```

❌ **Lambda pour différer un appel** :

```python
on_click=lambda: edit(123)        # rejeté
```

→ `partial(edit, 123)`.

❌ **Closure pour capturer un id** :

```python
def make_handler(id):
    def handler(): ...
    return handler                 # rejeté
ui.button(on_click=make_handler(42))
```

→ `partial(handler, 42)`.

---

## Sécurité — HMAC signing

Chaque action_id émis est signé avec une **clé dérivée** du `secret_key` master (`Bretzel(secret_key=...)`). Format final dans l'attribut : `<id>|<sig>` (16 hex chars, ~64 bits). Le serveur vérifie la sig avant tout — id forgé sans la clé → 403.

### Dérivation de clés (depuis 2026-05)

Le `secret_key` est un **master** ; chaque surface HMAC a sa propre **clé dérivée** via `bretzel/server/crypto.py:derive_key(master, purpose)` :

| Clé dérivée | Sert à | Purpose label |
|---|---|---|
| `config._action_key` | sign/verify_action sur `/_bretzel/action/*` | `bretzel.action.v1` |
| `config._auth_key` | sign cookie `Bretzel_auth` | `bretzel.auth.v1` |
| `config._csrf_key` | CSRF token (`hmac(csrf_key, session_id)`) | `bretzel.csrf.v1` |

**Pourquoi** : si une clé fuite via un sous-système (log, exception, dump mémoire), les autres tiennent. Dérivation = `HMAC-SHA256(master, purpose)` — KDF single-block qui produit 32 bytes indépendants par purpose. Pas besoin de HKDF Extract+Expand : le master est déjà haute entropie (validé ≥16 chars en config). Suffixe `.v1` pour rotation future.

**Conséquence côté code** : `sign_action` / `verify_action` / `verify_auth_cookie` prennent **bytes** (la clé dérivée), pas **str** (le master). Toujours lire `config._action_key` / `config._auth_key` / `config._csrf_key`, jamais `config.secret_key` directement pour signer.

### CSRF — `CSRFMiddleware`

Toute requête non-safe (POST/PUT/PATCH/DELETE) hors `/_bretzel/action/*` est CSRF-checkée :

- Token = `hmac(csrf_key, session_id)[:32]` — déterministe, session-bound
- Le runtime lit `$bz.csrfToken` depuis l'envelope (rendu côté serveur via `ctx.csrf_token`) et l'echoe en header `X-Bretzel-CSRF` sur chaque POST
- Origin/Referer check belt-and-suspenders : Origin host doit matcher `Host` request ou un `trusted_hosts` config
- Action routes (`/_bretzel/action/*`) bypassent — leur HMAC sur `action_id + bound_args` les protège déjà

Toujours-on, pas de knob `csrf=False`. Pour un webhook / endpoint API non-CSRF, l'exposer hors du router Bretzel.

### Discipline secret_key

Ne jamais commit un `secret_key` réel. Utilise des variables d'env / un secret manager en prod. Valeur recommandée : `secrets.token_hex(32)` (64 hex chars). `BretzelConfig.__post_init__` rejette <16 chars.

---

## Configuration — `mode` est un préréglage, pas un levier

`Bretzel(mode="dev"|"prod")` ne décide plus rien tout seul. Il pose les
défauts de réglages **indépendants**, chacun surchargeable :

| axe | champ de config | qui le lit |
|---|---|---|
| Transport | `secure_cookies` (`None` = déduit du scheme) | `auth.resolve_cookie_secure`, `SessionMiddleware` |
| Exposition | `expose_errors` | `routing/errors.py` |
| Diagnostics | `debug` | drift de features, `each()` sans clé, IDs lisibles |
| Assets / cache | `config.is_dev` | `lifecycle`, `routing/static.py` (`dev=`), `render/pipeline` |

**`config.debug` ne signifie QUE « sois bavard ».** Il ne gouverne ni le
transport, ni l'exposition, ni les assets — et il ne pilote aucun log (le
niveau de log est un paramètre de `app.run()`). Si tu écris
`if config.debug:` pour autre chose que de la verbosité, tu te trompes
d'axe : prends `config.is_dev` (assets) ou `config.expose_errors`.

### `Secure` sur les cookies suit le TRANSPORT

`resolve_cookie_secure(scheme, override)` — jamais le mode. Un cookie
`Secure` n'est pas renvoyé sur une origine `http://`, donc lier les deux
casse la session de toute app déployée sans TLS. C'était le cas : un
outil interne en `mode="prod"` sur un LAN sans TLS perdait sa session à
chaque requête, sans erreur ni log, et le seul contournement
(`mode="dev"`) exposait les stack traces. Invisible en local, les
navigateurs traitant `localhost` comme une origine de confiance.

Le `SessionMiddleware` résout **par requête** (`scope["scheme"]`) et non
à la construction : la même app peut être atteinte en http et en https.
Derrière un proxy TLS, uvicorn ne réécrit le scheme que lancé avec
`proxy_headers=True` ; sinon forcer `secure_cookies=True`.

Gates : `tests/consistency/test_cookie_secure_follows_transport.py` et
`test_config_axes_are_independent.py`.

### Le pipeline CSS est un réglage, pas une implication du mode

`config.css` (`"auto" | "build" | "browser"`) → `config.css_pipeline`
résout `auto` en `build` (prod) / `browser` (dev). Le shell reçoit
`browser_css=` : **il ne connaît plus le mode du tout**.

C'était le seul fork sur `mode` qui changeait ce qui est RENDU, donc la
source de la classe « marche en dev, cassé en prod ». Gate :
`tests/consistency/test_mode_does_not_change_rendering.py` — à pipeline
égal, les deux modes produisent le même document, cache-bust mis à part.

`auto` garde le compromis historique parce que compiler coûte ~2,8 s
mesurées sans gain à chaud : l'imposer à chaque `--reload` serait un
recul. `css="build"` en dev donne la parité exacte.

Le binaire s'installe via l'extra `bretzel[css]` — plus de téléchargement
de 112 Mo en effet de bord d'un démarrage. `get_or_build_css` échoue
proprement sans binaire (`allow_download` réservé à un appel explicite),
et `lifecycle` retombe sur le compilateur navigateur **en le disant**.

⚠️ Le cache `style.css` est clé sur l'empreinte du thème seul : une classe
ajoutée dans le code utilisateur ne l'invalide pas. Cf. `todo.md` — le
mode `--watch` (`start_lightning_watch`, écrit et sans appelant) est la
bonne issue.
