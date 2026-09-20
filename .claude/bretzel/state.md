# State — typed scopes, fields, validators, computed, bindings

Source : `bretzel/state/`. Public surface : `from bretzel.state import …`.

---

## Deux familles

| Famille | Vit où | Subclasses | Mutation |
|---|---|---|---|
| `ServerState` | mémoire serveur | `PageState` / `SessionState` / `UserState` / `AppState` | handler Python |
| `ClientState` | mémoire navigateur (mirror par le runtime) | déclaration directe avec `persist=` | callable serveur OU expression client bake-time |

```python
from bretzel.state import (
    ServerState, ClientState,
    PageState, SessionState, UserState, AppState,
    field, computed, validator, get,
)
```

---

## ServerState — 4 scopes <!--count:server_state_scopes-->

```python
class CartState(SessionState):           # ou PageState / UserState / AppState
    items: list[dict] = field(default_factory=list)
    coupon: str = field(default="")

    @validator("coupon")
    def _normalize(self, value: str) -> str:
        return value.strip().upper()

    @computed
    def total(self) -> float:
        return sum(it["price"] for it in self.items)
```

- **`PageState`** — vit le temps d'une page affichée : **persiste à travers les actions (POST)** d'une même page (clé `page_id`, TTL 1 h), **reset** au F5 / à la navigation (nouveau `page_id`).
- **`SessionState`** — **TTL 24 h**, explicitement indépendant du cookie :
  `DEFAULT_TTLS["session"] = 86400` (`state/registry.py`), là où le cookie
  `Bretzel_session` vit 30 jours par défaut. (Cette ligne disait « durée du
  cookie » jusqu au 2026-08-01.)
- **`UserState`** — attaché à un compte authentifié. Instancier sans auth → `AuthRequiredError`.
- **`AppState`** — singleton process-wide.

Pas de `scope=` à passer en sous-classant : utilise la base pré-scopée.
⚠️ Sauf pour **re-scoper** une base du framework — `class
Issues(DatatableState, scope="session")` est le geste qui fait survivre
un tri ou un filtre à une navigation, sans rien exposer dans l'URL.

---

## L'état DANS L'URL — `addressable=True`

Un `PageState` est indexé par un uuid de rendu **neuf à chaque
navigation** : c'est pour ça qu'un filtre ne survit ni au changement de
page ni au bouton retour. Le remède est de déclarer les champs dont
**l'URL fait foi** :

```python
class Issues(DatatableState, addressable=True):
    per_page: int = field(default=25)
# → /issues?tri=title&sens=desc&p=3&q=…

sort_key: str = field(default="", url="tri")   # le nommage, par champ
URL = {"sort_key": "sort"}                     # renommer, ou un etat maison
```

**`field(url=…)` NOMME, `addressable=True` ALLUME.** Les deux sont
séparés parce que ce qui est dans une URL est **public** — historique du
navigateur, logs d'accès, en-tête `Referer` — et ne doit jamais
s'obtenir par accident. Un champ que le framework n'a pas nommé ne peut
donc pas être allumé : c'est ainsi que `DatatableState.filters` reste
hors de l'adresse **par construction**, et pas par consigne.

**Ne lis pas la source pour connaître les noms — demande** :

```bash
py -m bretzel.cli.main describe DatatableState
# Portée      page
# Adressable  — éteint  (`addressable=True` publierait sort_key→tri, …)
```

La ligne `Adressable` a trois états : les paramètres publiés quand
l'état est allumé, les champs nommés et *éteints* sinon (« il ne manque
qu'`addressable=True` »), et rien du tout — le défaut. Les cinq noms de
`DatatableState` s'y lisent sans ouvrir `state/datatable/state.py`, qui
est le seul endroit où ils sont écrits — et une sous-classe n'en écrit
aucun.

Un nom d'URL est **écrit**, jamais dérivé du nom Python : une URL est une
API publique qu'un renommage de champ ne doit pas casser. Il est hérité
quand une sous-classe surcharge le défaut (`sort_key: str = "name"` garde
`tri`).

| ce qu'on veut | le mot |
|---|---|
| survivre à une navigation | `scope="session"` |
| être partageable par lien | `addressable=True` |
| les deux | les deux — l'adresse se corrige seule au rendu |

**Refusé, et c'est délibéré** : un champ dont la valeur est une structure
(`dict` / `list`). Une query ne porte que des chaînes, il n'existe pas
encore de format, et sans ce garde la valeur d'URL remplacerait le dict
par une `str` — le premier `.get()` du composant casserait sans que la
déclaration n'ait rien signalé.

Mécanique : `bretzel/state/url.py` (le contrat), `register()` (le semis,
AVANT la photo de référence), `server/routing/actions.py` (`HX-Push-Url`
quand un champ déclaré bouge), `render/pipeline.py` (`replaceState` quand
la mémoire de session rend l'adresse muette). Gates :
`tests/integration/server/test_a_view_survives_its_url.py` (l'aller-retour
rend la même vue) et `tests/consistency/test_a_state_fiche_names_its_url.py`
(un champ nommé le dit dans sa fiche, et un champ sans `url=` en reste
absent).

---

## ClientState — 3 modes de persistance

```python
class FilterState(ClientState, persist="local"):
    sort_by: str = field(default="date")

class ToastUI(ClientState, persist="memory"):
    open: bool = field(default=False)
```

`persist=` décide d'une seule chose : **combien de temps la valeur survit**.

| Valeur | Stockage (runtime) | Survit reload (F5) ? | Survit fermeture onglet ? |
|---|---|---|---|
| `"memory"` (défaut) | RAM JS (`volatile`, aucun adaptateur) | ❌ non | ❌ non |
| `"session"` | `sessionStorage` | ✅ oui | ❌ non |
| `"local"` | `localStorage` | ✅ oui | ✅ oui |

> ⚠️ **Retiré (reliquats V2, sans effet côté runtime — cf. `04_persistence.js`)** :
> le mode `"page"` (n'a jamais reset à la navigation en V3, = `memory`) ET
> `ttl_hours=`. Les deux ont été supprimés de l'enum Python + du constructeur
> le 2026-07-04. Le runtime a aussi un mode `"cross_tab"` (localStorage +
> BroadcastChannel) non exposé par l'API Python.

---

## Field, validator, computed

- **Tout champ passe par `field()`.** Une seule forme, et la métaclasse
  REFUSE l'autre avec la phrase qui dit quoi écrire :

  ```python
  class S(SessionState):
      count: int = field(default=0)
      tags: list[str] = field(default_factory=list)   # mutable → factory
      requis: str = field()                           # sans défaut
      tri: str = field(default="date", url="tri")
      vues: int = field(default=0, merge="add")
  ```

  `count: int = 0` était rigoureusement équivalent à
  `field(default=0)` — même défaut, même type, même URL (vérifié). Deux
  orthographes pour un résultat identique obligeaient un lecteur à savoir
  laquelle porte quoi, et surtout : **une option de champ n'a nulle part
  où se poser sur la forme courte**, donc chaque déclaration nouvelle
  devait s'inventer un type et grossir la surface publique. Avec un
  appel, elles s'ajoutent en paramètres.

  L'annotation, elle, reste : c'est la seule position où Python lit une
  *expression* de type, donc la seule qui sache dire `int | None` — en
  argument, une union n'est pas une classe et le typage tombe en `Any`
  (mesuré avec mypy ET Pyright).

- Les quatre paramètres : `default`, `default_factory` (l'un OU l'autre),
  `url` (le nom dans l'adresse), `merge` (comment deux écritures
  concurrentes se combinent — cf. plus bas).

- **`@validator("nom_champ")`** : single-field, reçoit `(self, value)` (l'instance + la valeur écrite), **retourne** la valeur (peut transformer). Lever annule l'écriture.
- **`@validator`** sans argument : whole-instance, reçoit `(self)` seul, retourne `None`. Pour invariants multi-champs (lit plusieurs `self.champ`).
- **`@computed`** : descripteur dérivé qui auto-track ses deps (lit d'autres `field` du state) et invalide à chaque mutation. Cache par instance, garbage-collected proprement.

### Ce qu'un champ COERCE en arrivant d'un formulaire

Une soumission n'apporte que des chaînes — c'est tout ce qu'un `<input>`
sait porter. `Field.__set__` les convertit vers le type déclaré **avant**
que le moindre validateur les voie, en deux temps :

| le champ déclare | ce qui arrive | ce qui est rangé |
|---|---|---|
| `bool` | `"on"` / `"true"` / `"1"` / `"yes"` | `True` |
| `bool` | `"false"` / `"off"` / `"0"` / `"no"` / `""` | `False` |
| `int` / `float` | `"12.5"` | `12.5` |
| `int` / `float` | `""` | **écriture sautée** — l'utilisateur a vidé le champ, pas choisi zéro |
| `list` / `dict` | `'["a","b"]'` | `["a", "b"]` |
| `list` / `dict` | `""` | `[]` / `{}` — « rien de sélectionné » EST un choix |
| `str` | n'importe quoi | inchangé, y compris du JSON |
| `list` / `dict` | une chaîne qui ne commence PAS par `[` ou `{` | **inchangée** |

**Le décodage `list`/`dict` (août 2026)** existe parce que sept contrôles
portent une valeur non scalaire et la sérialisent en `JSON.stringify` dans
un champ caché : les trois sélections multiples (`toggle_group`, `select`,
`combobox`), les deux plages (`date_range_picker`, `slider(range=True)`),
`resizable` et `accordion(multiple=True)`. Sans lui, un champ `list`
rangeait la CHAÎNE telle quelle, le rendu suivant faisait `list(...)` dessus
et affichait ses caractères un par un — et la bouillie survivait au
rechargement. Aucune erreur nulle part.

Un JSON malformé, ou décodé vers le mauvais conteneur, **lève** — donc
`form.errors` le porte, comme pour un `int` malformé.

⚠️ **Le magasin client voyage en JSON lui aussi — depuis le 2026-08-19
seulement.** Avant, le pont posait la valeur brute et htmx sérialisait un
tableau **élément par élément** (`formDataFromObject`) : `["a","b"]`
arrivait comme `"b"`, et `[]` n'ajoutait **rien**, donc une liste client
vidée ne pouvait plus jamais vider son champ serveur. `injectParameters`
encode maintenant les valeurs composites (`wireValue`, `05_bridge.js`), ce
qui met les deux transports — porteur caché et magasin client — sur la
**même convention**.

La dernière ligne du tableau reste néanmoins load-bearing : on ne décode
que ce qui **ressemble** à un conteneur. Une première version décodait
toute chaîne, et comme `State._apply_fields` n'a aucune garde, elle rendait
**500 sur toute action** d'une page portant un état à liste — six états du
playground concernés, 16 138 tests verts.

⚠️ `tuple` n'est PAS décodé : `json.loads` ne produit jamais de tuple, donc
l'annoncer ferait lever tout ce qui vient d'un formulaire.

Le tout est gaté par `test_a_bound_control_transmits_every_value`, qui rend
chacun des sept porteurs et relit sa valeur — plutôt que de vérifier le
décodage sur des chaînes écrites par l'auteur de la gate.

---

## Les types métier

`date`, `datetime`, `time`, `Decimal`, `UUID` et toute sous-classe
d'`Enum` s'utilisent nus. L'annotation suffit, `field()` ne reçoit rien
de plus :

```python
class Facture(SessionState):
    jour: date = field(default_factory=date.today)
    montant: Decimal = field(default=Decimal("0"))
    statut: Statut = field(default=Statut.BROUILLON)
```

Pour une classe à toi, une déclaration unique — par TYPE, pas par champ :

```python
from bretzel.state import register_type

register_type(Money, encode=str, decode=Money.parse)
```

Et pour une FAMILLE — une base dont les champs déclarent les héritiers —
``subclasses=True``, où ``decode`` reçoit la classe concrète :

```python
register_type(Ref, encode=str,
              decode=lambda brut, cible: cible(brut),
              subclasses=True)      # couvre RefClient, RefFournisseur…
```

C'est par cette porte qu'``Enum`` s'inscrit lui-même. Il a été un cas
particulier codé en dur — cinq branches, et un `register_type` qui
REFUSAIT une énumération — jusqu'au 2026-09-06 : un mécanisme public qui
doit refuser une entrée légitime a une porte trop étroite.

**Une seule règle, récursive.** Un type passe s'il a un codec, s'il est
natif pour `json`, ou si c'est un conteneur / une union / un `Literal`
dont les membres passent. Donc tout ceci se déclare sans rien savoir de
plus :

```python
jours: list[date]                 = field(default_factory=list)
tarifs: dict[str, Decimal]        = field(default_factory=dict)
bornes: tuple[date, date] | None  = field(default=None)
vus: set[UUID]                    = field(default_factory=set)
grille: dict[str, list[Statut]]   = field(default_factory=dict)
```

L'encodage ET le décodage descendent tous deux dans les conteneurs, et
c'est cette symétrie qui supprime les exceptions : tant que seul
l'encodage descendait, un `list[date]` se relisait en chaînes et devait
être refusé à la déclaration. `tuple` et `set` sortent en liste — `json`
ne connaît qu'elle — et sont reconstruits depuis le type déclaré.

**Un type inconnu est refusé au DÉMARRAGE.** Avant le 2026-09-05,
`jour: date` était accepté, le magasin mémoire gardait l'objet Python
vivant, et la faute attendait le branchement de Redis : ça marchait en
dev et cassait au déploiement. `Any` reste l'échappatoire assumée pour
qui sait ce qu'il fait — c'est alors le magasin qui refuse à l'écriture,
en nommant le champ.

L'encodage a lieu **dans le registre, avant le magasin** : une seule
fois, donc la mémoire et Redis ne peuvent plus diverger. Le décodage vit
dans `Field.__set__`, ce qui lui fait couvrir deux chemins d'un coup —
la relecture depuis le magasin et l'écriture d'un formulaire. Un champ
`date` recevant `"2026-12-25"` d'un `<input>` y range bien une `date` ;
avant, il gardait la chaîne sans un mot.

⚠️ **`decode(encode(v)) == v` est supposé partout.** Le registre compare
la photo prise à la lecture avec la valeur courante pour décider quoi
écrire : un codec qui perd de l'information ferait réécrire le champ à
chaque requête, en silence. C'est pour ça que `Decimal` s'encode en
`str` et jamais en `float`.

⚠️ **Ne pas confondre avec `merge=`.** L'annotation dit ce que la valeur
EST, `field()` dit comment elle se COMPORTE. Un `Decimal` est un montant
quel que soit son usage ; un `int` est additif ou non selon ce que l'app
en fait, et aucun type standard ne peut le dire. Corollaire : un total
d'argent qui doit s'additionner sous concurrence se compte en **unités
mineures**, donc en `int` avec `merge="add"` — `HINCRBYFLOAT` incrémente
en flottant et retirerait à `Decimal` sa raison d'être.

---

## ClientBinding — le pivot universel

Quand on lit un champ d'un `ClientState` **dans une render scope**, l'attribut renvoie un `ClientBinding` (pas la valeur brute). Hors render scope (handler), il renvoie la valeur brute.

> Pour savoir **quelles props de quel composant** acceptent un `ClientBinding` de manière vraiment reactive côté client (versus rendues statiquement au SSR), cf. [`client-reactive-surface.md`](client-reactive-surface.md). Heuristique rapide : tout attribut HTML réel (`value`, `checked`, `disabled`, `href`, `src`, `open`) + les `value=` de Tabs/Pagination. Les props "design" (variant/size/color) sont SSR-only par construction.

```python
ui_state = AccountUI()           # dans @page → render scope
ui.dialog(open=ui_state.is_open) # ui_state.is_open == ClientBinding
                                 # le composant détecte et émet le path
```

**Méthodes mutationnelles** (renvoient une chaîne client prête pour `on_click=`) :

| Méthode | Résultat (équivalent JS) |
|---|---|
| `binding.set(value)` | `$bz.state.X.Y.field = value` |
| `binding.toggle()` | `$bz.state.X.Y.field = !$bz.state.X.Y.field` |
| `binding.increment(by=1)` | `… += 1` |
| `binding.decrement(by=1)` | `… -= 1` |
| `binding.push(item)` | `… = [...(… \|\| []), item]` (réassigne un tableau neuf → re-render) |
| `binding.clear()` | `… = []` |

**Opérateurs** (renvoient `ClientExpression` composable) :

```python
expr = (filter.mode == "all") | (filter.mode == "active")
ui.hstack(visible=expr, ...)        # le kwarg universel (l'exemple
                                    # écrivait `x_show=`, du vocabulaire
                                    # Alpine mort, jusqu'au 2026-08-01)
```

Supportés : `==`, `!=`, `<`, `<=`, `>`, `>=`, `+`, `-`, `*`, `/`, `//`, `%`, `~` (not), `&` (and), `|` (or). Plus méthodes nommées : `eq` `ne` `lt` `le` `gt` `ge` `not_` `between(low, high)` `length()` `contains(item)`.

`ClientExpression` hérite de `ClientBinding` → composable à l'infini.

---

## get(name, default=None, *, cast=None) — escape hatch

Lecture brute d'un champ FormData de la requête courante. Pour valeurs transientes qui ne méritent pas un State typé :

```python
def my_handler():
    bio = (get("bio") or "").strip()
    is_admin = get("admin", cast=bool)   # honore "on"/"true"/"1"/"yes"
```

Préfère un State typé pour tout ce qui a une structure ou se réutilise.

---

## Persistence backends

`Backend` (abstract) → `MemoryBackend`, `RedisBackend`. **Mémoire par défaut** ; Redis se branche via `Bretzel(redis_url=...)` (il n'y a PAS de param `state_backend=` — le backend est câblé au démarrage selon `redis_url`, cf. `server/app.py::__init__`). Le snapshot d'état client voyage dans l'envelope d'action : côté serveur `runtime/envelope.py` (`serialize_envelope` / `parse_client_payload`) ; côté navigateur la persistance (`localStorage` / `sessionStorage`) est gérée par le runtime JS (`04_persistence.js`). Runtime-only, jamais l'app.

### Ce que le commit écrit : des CHAMPS, pas le document

En fin de requête, le registre n'envoie au backend **que les champs que
cette requête a modifiés** (`Backend.merge`), et jamais le document
entier. La différence n'est pas une économie d'octets, c'est une
correction :

```
onglet A           onglet B
lit {filtre:"", panier:[]}
                   lit {filtre:"", panier:[]}
filtre = "rouge"
                   panier = ["pull"]
écrit              →  {filtre:"rouge"}
                   écrit → {panier:["pull"]}
relecture : {filtre:"rouge", panier:["pull"]}   ← les deux survivent
```

Avant le 2026-09-04, chaque requête réécrivait le document entier :
l'écriture de B remettait `filtre` à sa valeur lue, donc `"rouge"`
disparaissait — sans erreur, sans trace. C'est la « mise à jour
perdue », et elle demandait juste deux onglets.

La fusion est **atomique** côté backend, et c'est le format de stockage
qui la rend telle. Un état Redis est un **hash** : une clé, un champ
Redis par champ d'état. Écrire un champ, c'est `HSET clé filtre "rouge"`
— Redis ne lit rien, ne touche à rien d'autre, et le fait en un seul
aller-retour. Côté mémoire, la méthode ne contient aucun `await` et
prend un verrou.

C'est la forme que Redis propose pour un objet, et ce n'est pas un
détail d'implémentation : sans elle il faudrait relire le document,
fusionner, tout réécrire sous un verrou optimiste — trois allers-retours
et une boucle de reprise pour changer un champ, avec le document entier
sur le fil à chaque fois.

⚠️ **Ce que ça ne répare pas** : deux requêtes qui écrivent LE MÊME
champ. Le second gagne — sauf si le champ DIT ce qu'il est.

### Un compteur : `merge="add"`

```python
class Stats(AppState):
    vues: int = field(default=0, merge="add")      # un TOTAL : on y ajoute
    solde: float = field(default=0.0, merge="add") # idem, en décimal
    page: int = field(default=1)                   # un CHOIX : le dernier gagne
```

`state.vues += 1` s'écrit toujours pareil. Ce qui change est invisible
depuis l'app : le commit envoie l'**écart** (« ajoute 1 ») au lieu de la
valeur, et c'est le magasin qui additionne — `HINCRBY` côté Redis, une
addition sous verrou en mémoire. Deux clics concurrents font donc deux,
là où ils faisaient un.

Le registre a déjà les deux nombres : la photo de ce qu'il a lu et la
valeur courante. Trois mutations dans une requête donnent donc **un**
écart de trois, et un aller-retour (`+1` puis `−1`) n'écrit rien du tout.

**Pourquoi une déclaration et pas un automatisme** : `int` ne dit pas de
quel genre de nombre il s'agit. Un total est une somme de contributions,
un choix est une valeur qu'on désigne. Rendre tout additif ferait
répondre 7 à deux onglets qui vont à la page 3 et à la page 5 — une page
que personne n'a demandée. Sur les 132 champs numériques d'`examples/`,
la grande majorité sont des réglages et des identifiants.

⚠️ **Trois choses à savoir** :

- **le nombre AFFICHÉ reste le nombre local.** L'écriture a lieu après le
  rendu : la page montre 6 même si le total vrai est 7 parce qu'un autre
  onglet a compté aussi. Le rafraîchissement suivant le corrige ;
- **toute écriture est une contribution.** `state.vues = 0` après avoir lu
  5 vaut « retire 5 », pas « mets à zéro ». Sous concurrence c'est
  d'ailleurs le seul sens défendable — deux remises à zéro simultanées
  pendant que d'autres comptent n'ont pas de réponse ;
- **un total part de zéro**, et la métaclasse refuse un autre défaut :
  le magasin compte à partir de 0 quand la ligne n'existe pas encore.
  Elle refuse aussi `merge="add"` sur autre chose qu'un nombre.

### Ce qui ne se combine pas : `lock()`

La fusion par champ et `merge="add"` sauvent ce qui se **combine**. Reste
ce qui CALCULE à partir de ce qu'il a lu :

```python
store.taches = [t for t in store.taches if t["id"] != cible]
```

Deux suppressions simultanées lisent la même liste, en retirent chacune un
élément, et la seconde écriture réintroduit celui que la première venait
d'ôter. Aucune opération de magasin ne peut résoudre ça — ce n'est ni un
ajout ni un nombre. Mesuré : sans protection, `a,c` là où on attend `c`.

```python
def supprimer(cible: str) -> None:
    with Kanban.lock() as store:
        store.taches = [t for t in store.taches if t["id"] != cible]
```

Le bloc est une **petite transaction** : à l'entrée le verrou est pris
puis l'état RELU (ce que tu lis dedans est frais), à la sortie les champs
modifiés sont écrits puis le verrou relâché. L'écriture est dans le bloc,
et c'est le point : se contenter de bloquer en laissant le commit de fin
de requête écrire plus tard laisserait une autre requête se glisser entre
la libération et l'écriture.

`with` et non `async with` : les handlers s'écrivent `def`. Le même objet
accepte `async with` dans un corps `async def`.

⚠️ **Ce qu'un verrou à durée ne peut pas.** Il porte un `ttl` (5 s par
défaut) sans quoi un processus tué le garderait pour toujours — et la
contrepartie est inhérente : si ton bloc dépasse le `ttl`, un second
porteur entre. Le jeton empêche de relâcher le verrou d'autrui, pas le
recouvrement. Garde le bloc court : lire, calculer, écrire — jamais un
appel réseau ni un rendu. L'attente d'un suiveur est bornée elle aussi
(3 s), et son dépassement lève `LockTimeoutError` plutôt que d'exécuter
la section sans protection.

Et il **sérialise** : deux requêtes sur la même clé s'attendent. C'est le
prix demandé, et il n'est payé que là où on l'a demandé — d'où le choix
de ne PAS verrouiller par défaut.

**Les listes n'ont toujours pas d'opération typée**, et c'est délibéré :
`RPUSH` n'existe que sur une vraie liste Redis, donc il faudrait une clé
par champ liste — un état éclaté, une lecture en N+1, l'atomicité par
ligne perdue. Mesuré sur `examples/` : un seul `append` dans 21 apps,
contre trois réécritures dans le même fichier — que `RPUSH` n'aurait pas
sauvées de toute façon.

⚠️ Et l'atomicité est **par ligne, pas par requête** : une requête qui
touche trois états fait trois écritures indépendantes. Un plantage au
milieu la laisse à moitié persistée — c'était déjà vrai avant.

Un état marqué sale dont aucun champ n'a bougé n'écrit rien du tout.

Gates : `tests/unit/state/test_a_commit_keeps_a_concurrent_field.py`
(le chevauchement, écrit à la main plutôt que joué au chronomètre),
`tests/unit/state/persistence/test_both_backends_agree.py` (le MÊME
scénario joué sur les deux backends — c'est l'absence de ce fichier qui
avait laissé leurs sémantiques diverger le jour du changement de
format),
`tests/integration/server/test_redis_merges_instead_of_overwriting.py`
(la fusion ne LIT rien, et une ligne de l'ancien format ne fait planter
personne) et
`tests/consistency/test_a_commit_writes_fields_not_documents.py` (le
registre ne peut plus réécrire un document, et un backend neuf ne peut
pas oublier `merge`).

---

### Lire un backend qui ne répond qu'en `await`

`MemoryBackend` se lit aussi **synchroniquement** (`load_sync`) ; Redis, non — il lit par le réseau. Or `MonEtat()` est un constructeur, et un constructeur ne peut pas attendre. Deux chemins existent donc, et le second est arrivé le 2026-09-04 :

| d'où tu appelles | ce qui se passe |
|---|---|
| un corps `def` (le cas courant) | délesté sur un thread par `core/invoke.py` → le registre fait exécuter le `load` **par** la boucle et attend le résultat. `MonEtat()` marche tel quel. |
| un corps `async def` | tourne **sur** la boucle : y attendre la gèlerait pour tous les autres utilisateurs. `MonEtat()` lève `StateHydrationError` et nomme le geste : `etat = await MonEtat.load()`. |

⚠️ Avant cette date, le second cas ne levait pas : il rendait les valeurs par **défaut**, et comme `commit` ne regarde que `_dirty`, la première mutation **écrasait** la valeur stockée. Ça ne pouvait se voir sur aucune suite — toutes tournent sur la mémoire, qui a `load_sync`. La gate est `tests/integration/server/test_an_async_only_backend_still_hydrates.py`, et elle monte un backend privé de `load_sync` exprès.

⚠️ Et le refus dépend du **backend** : en mémoire, `MonEtat()` dans un `async def` marche. La faute n'apparaît donc qu'en prod. `bretzel check` la signale en dev (`state-built-on-the-loop`) — mais seulement quand la construction est DIRECTE dans le corps `async`, pas quand elle passe par un helper synchrone.

---

## Pièges à ne PAS refaire

- **Hors render scope, `state.field` renvoie la valeur brute** → `binding.set(...)` ne marchera pas. Toujours dans `@page` / `@refreshable`. (cf. `traps.md`)
- **`SessionState.field` ne renvoie PAS un Binding** — c'est du serveur. Pour lier un widget client à un état serveur, passe par un `ClientState` ou un refresh.
- **Tag `@validator` retourne la valeur** (pas `None`). Oubli courant : `def _norm(self, v): v.strip()` au lieu de `return v.strip()` → écrit `None`.
- **`@computed` n'accepte qu'un argument `self`.** Pas de cache key custom. Si tu veux paramétrer, c'est une méthode normale.
