# Structure d'une app Bretzel — tout est feature, le contrat est déclaré

**À lire** quand tu démarres une app, ajoutes une feature, ou hésites sur où
mettre un fichier.

> ⚠️ **Réécrit le 2026-08-01.** La version précédente décrivait un modèle
> que le code avait dépassé : elle ne mentionnait **nulle part** le contrat
> `Feature` — qui fait échouer le boot quand il est violé —, prescrivait
> `h-screen` là où les shells réels faisaient `fixed inset-0` (et où
> `traps.md` conclut « ne PAS re-reverter » — depuis le 2026-08-23 c'est
> `ui.viewport` qui le porte), et bannissait `shared/` avec
> trois contre-exemples vivants. Références vérifiées : `examples/crm`
> pour la structure, `examples/docs` et `examples/playground` pour le
> reste.
>
> ⚠️ **Troisième app de référence en deux semaines** : une app à plat
> jusqu'au 2026-09-07, `mad` jusqu'au 2026-09-10, toutes deux parties à
> l'élagage. Une doc de structure ancrée sur une DÉMO est réécrite
> chaque fois qu'une démo tombe, et une démo est là pour pouvoir
> tomber. `crm` est l'instrument d'usage réel — la seule app
> d'`examples/` qui ne relève pas de la règle d'élagage.

---

## 1. Le principe

**Une feature = un dossier ou un fichier qui se décrit lui-même.** Elle
déclare ce qu'elle expose, ce dont elle a besoin, et se décore elle-même
(`@page` / `@layout` / `@error`). Aucune feature n'importe l'instance d'app.
`main.py` est le seul fichier qui la connaît, et il ne fait qu'une chose :
`app.include(...)`.

Il n'y a pas de « type spécial » de feature. Un **shell est une feature** qui
expose une région (`ui.outlet()`). Une source de données est une feature qui
n'expose aucune page. La hiérarchie ne vit pas dans l'arborescence, elle vit
dans le **contrat**.

---

## 2. Le contrat `Feature` — le cœur

```python
from bretzel import Feature

feature = Feature(
    name="notes",
    kind="page",
    provides=[notes_page, NotesDraft],   # ce que les autres peuvent importer
    uses=["notes_data"],                 # les features dont je dépends
)
```

Les six champs : `name`, `kind`, `provides`, `uses`, `reads`, `module`.

**Les 10 `kind`** — `shell` · `layout` · `page` · `error` · `state` · `data`
· `logic` · `infra` · `facade` · `job`. Un `kind` hors de cette liste est
refusé.

**`provides` expose des symboles, pas seulement des `State`.** Une feature de
données publie légitimement son store, ses fonctions et ses vues :
`examples/crm/features/accounts_data.py` fait
`provides=[PatientsRev, list_patients, get_patient, add_patient,
delete_patient]` — un store de révision, trois lectures et deux écritures
dans le même contrat. C'est le contrat déclaré qui autorise l'import, pas
le type du symbole.

**Le contrat est validé au démarrage, pas à l'`include`.**
`validate_features()` tourne dans le lifespan (`server/app.py`) et **fait
échouer le boot** sur un contrat invalide. Deux linters s'y ajoutent, en
WARN :

| Lint | Ce qu'il attrape |
|---|---|
| `undeclared_provides` | un symbole importé par une autre feature sans être dans son `provides` — l'**oubli** de déclaration |
| `dependency_drift` | un `uses` déclaré qui ne correspond plus aux imports réels (dérivés par AST) — la **dérive** |

Les deux ensemble : L1 attrape l'oubli, L2 attrape le mensonge.

**`describe_app(features) → AppGraph`** dérive le graphe depuis le contrat ;
c'est ce qui alimente les pages *app map* de `crm` et
du playground. Le
modèle de rendu est dans [`app-map-model.md`](app-map-model.md).

---

## 3. `main.py` — la racine de composition

```python
from bretzel import Bretzel
from myapp.core.theme import THEME
from myapp.features import shell, home, notes, notes_data

app = Bretzel(title="My App", secret_key="…", theme=THEME, mode="dev")

# Ajouter une feature = l'ajouter ici. include() lit les contrats Feature(),
# monte les provides, et VALIDE le graphe au démarrage.
app.include(shell, notes_data, home, notes)

if __name__ == "__main__":
    app.run(port=8000, reload=True)
```

`app.include(*targets)` accepte **cinq formes** : un module, un **nom** de
module déjà importé (`app.include(__name__)` pour une app mono-fichier), un
objet **`Feature`**, un callable marqué par un décorateur, ou un itérable de
tout ça. Idempotent.

⚠️ **Le shell s'inclut comme le reste.** Dès qu'une app utilise les contrats,
un layout DOIT être passé à `include` — sinon il manque au graphe.
`examples/crm/main.py` inclut son `shell` au même titre que ses pages.
(Seule `examples/docs`, qui n'utilise pas `Feature`, s'en dispense : son
layout se résout par référence.)

### 3bis. La langue — `lang=` et `texts=`

```python
app = Bretzel(title="Mon app", secret_key="…", lang="fr", texts={
    "datatable.clear_filters": "Effacer les filtres",
    "alert.dismiss": "Fermer l'alerte",
})
```

Deux réglages parce qu'il y a **deux natures de texte**, et confondre les
deux est ce qui produisait la moitié-configurable-moitié-pas :

| | qui le produit | comment on le change |
|---|---|---|
| noms de mois et de jours, axes temporels | **dérivable** d'un code de langue | `lang=` seul |
| « Clear filters », « No results », « Dismiss alert » | des phrases que **Bretzel a écrites** | `texts=` |

`lang=` est une étiquette BCP-47 (`"fr"`, `"pt-BR"`) ; elle pose
`<html lang>` — un lecteur d'écran y choisit sa voix — et voyage jusqu'aux
composants. Les quatre composants de date n'ont **plus de table anglaise**
figée : sans `month_names=` / `weekday_names=`, c'est `Intl` qui nomme,
dans le navigateur. Python ne peut pas le faire (son module `locale` est
un état **global au processus**, et Babel serait une dépendance).

`texts=` fusionne sur les valeurs anglaises de
`bretzel.render.texts.DEFAULT_TEXTS`. **Une clé inconnue lève au
démarrage** : une faute de frappe dans un dict de traduction ne produit
aucune erreur, et se manifeste seulement par une phrase restée en anglais
que l'auteur de la traduction ne relira jamais.

Ce n'est **pas de l'i18n** (hors périmètre v2.0) : pas de catalogue, pas
d'extraction, pas de négociation `Accept-Language`, et la seule règle de
pluriel est *un / autre*. Une app multilingue reste à construire par
l'app.

Côté framework : une phrase neuve dans un composant s'écrit
`text("mon_composant.ma_clé")` et sa valeur anglaise se pose dans
`DEFAULT_TEXTS`. L'ordre inverse est interdit par
`tests/consistency/test_framework_words_go_through_the_table.py`.

---

## 4. L'arborescence

```
my_app/
├── main.py             # Bretzel(...) + app.include(...) — le seul à voir l'app
├── core/
│   └── theme.py        # THEME = Theme(...) — le seul vrai « global »
└── features/
    ├── shell.py        # @layout — expose ui.outlet()
    ├── home.py         # @page("/") — feature mono-fichier
    ├── notes/          # feature en dossier
    │   ├── __init__.py #   ré-exporte `feature` (le contrat)
    │   ├── feature.py  #   Feature(name=, kind=, provides=, uses=)
    │   ├── state.py
    │   ├── logic.py    #   les handlers, module-level
    │   └── ui.py       #   le rendu + les décorateurs @page
    └── core/           # les features SANS page, groupées
        └── notes_data/ #   (state + logic + ui + feature)
```

**`features/` peut être imbriqué** — regrouper par domaine est permis.
⚠️ Aucune app ne le fait aujourd'hui : `mad`, qui portait
`features/planning/`, est partie le 2026-09-10, et `crm` est plat sur
ses 25 features. La permission reste ; l'exemple vivant a disparu avec
elle. Le mot « flat »
qualifie l'absence de couches techniques (`app/`, `views/`, `controllers/`),
pas une interdiction de regrouper par domaine.

**Mono-fichier ou dossier ?** Dossier au-delà de ~400 LOC, ou dès que le
contrat devient non trivial. ⚠️ Le seuil est *indicatif* : 37 features
mono-fichier du playground le dépassent aujourd'hui, dont une à 933 lignes —
c'est de la dette assumée, pas la règle.

**Un `core/` app-level** pour ce qui est vraiment global (le thème). Un
`features/core/` pour les features sans page. Les deux coexistent.

---

## 5. Le shell — `ui.viewport` et `ui.pane`

```python
@layout
def shell() -> None:
    with ui.viewport():
        with ui.sidebar(collapsible="rail"):
            ui.sidebar_title("Brand", icon=ui.icon("box", size="lg"))
            with ui.sidebar_section(label="MENU"):
                ui.sidebar_item("Home", icon="home", href="/")
        with ui.pane(gap="none", padding="lg"):
            ui.outlet()
```

**Écrire `ui.viewport()`, c'est choisir un modèle de défilement.** Deux
existent, et Bretzel garde le second par DÉFAUT :

| modèle | qui défile | qui le fait |
|---|---|---|
| **document gelé** — `ui.viewport` + `ui.pane` | des régions, chacune la sienne | les outils (VS Code, Slack) ; Quasar en mode `container` |
| **chrome fixe** (le défaut) | le document | le web (Mantine `AppShell`, shadcn `Sidebar`) |

Une page **sans** coque défile normalement, sans que personne n'écrive
quoi que ce soit. Le modèle gelé s'obtient explicitement, et il se paie :
il faut une chaîne de hauteurs continue de la racine à la région. Ce qu'il
achète, c'est **N régions à défilement indépendant** — un maître-détail,
des colonnes de kanban, un fil de messages à côté d'une liste — que le
modèle par défaut ne sait pas faire.

⚠️ **Les deux chaînes de classes que ce § prescrivait sont mortes le
2026-08-23**, absorbées dans les deux composants : `fixed inset-0 w-full
overflow-hidden` (neuf copies) et `flex-1 min-h-0 overflow-y-auto` (dix-
sept). Le POURQUOI de chaque utilitaire vit maintenant dans le thème du
composant concerné, en un seul endroit — dont le `min-h-0` load-bearing
et le `[&>*]:shrink-0` que personne n'écrivait.

🔴 **Ne pas revenir à `h-screen` sur la racine d'une coque.** Le piège a
été reverté **deux fois** vers `h-screen`, chaque fois avec une
justification que la mesure démentait ; `traps.md` conclut « ne PAS
re-reverter ». ⚠️ Nuance ajoutée le 2026-08-23 : l'inflation
(`html.scrollHeight` 7 657 pour un `clientHeight` de 800) **ne s'est pas
reproduite** dans une forme minimale re-testée en Chromium, donc elle
venait d'autre chose que du seul `h-screen`. Ça ne rouvre pas le sujet —
`fixed inset-0` est la forme livrée et elle n'a jamais rien cassé — mais
la justification écrite n'a pas été re-mesurée.

**La nav** (les `sidebar_item`) est listée en dur dans le shell. C'est le
seul couplage restant, et exactement là que le placement déclaré par chaque
feature gagnera sa place le jour où on le construira.

---

## 6. Les helpers partagés — autorisés, mais nommés

Un dossier de helpers partagés **dans** l'app est légitime dès qu'il évite la
copie intra-app :

- `examples/crm/core/ui.py` — la carte KPI, factorisée.
- `examples/docs/lib/` — `introspect.py` + `blocks.py` ; l'app documente
  elle-même ce dossier comme partie de son squelette.
- `examples/shared/app_map_view.py` — partagé **entre** exemples, importé par
  `crm` et le playground.

*(L'ancienne règle « pas de `shared/` — banni » avait ces trois
contre-exemples vivants. Ce qui reste vrai : un dossier de helpers n'est pas
un fourre-tout — s'il grossit, c'est qu'il contient une feature qu'on n'a pas
nommée.)*

---

## 7. Les erreurs

```python
@error_page(404, layout=shell)
def not_found() -> None:
    ui.empty_state("Page introuvable", icon="search-x")
```

`abort(403)` (`from bretzel import abort`) lève depuis un handler ou un render pour router vers la page
d'erreur correspondante.

⚠️ **Le catch-all `Exception` est gouverné par `expose_errors`, pas par le
mode.** `expose_errors` prend son défaut du `mode` mais reste surchargeable
seul (`Bretzel(mode="dev", expose_errors=False)`). Vrai par défaut, faux
comme règle.

---

## 8. Le playground fait exception, et c'est écrit

`examples/playground` garde un `app/` (`routes.py` + `nav.py` + `layout.py`)
et un `infra/errors.py`, parce qu'il monte **90 routes** écrites une par
une. Sa convention propre est dans
[`playground-pattern.md`](playground-pattern.md).

⚠️ La justification a changé le 2026-08-30 : elle disait « ~57 pages
générées par un sous-système (`features/matrix/`) », et ce
sous-système a été supprimé. La dérogation tient toujours — un
catalogue de 90 pages a besoin d'un index écrit — mais plus pour la
raison qui était écrite ici.

C'est une **dérogation assumée pour un catalogue**, pas le modèle d'une app
produit. Pour une app, la règle du § 4 tient.

---

## 9. Anti-patterns

- ❌ `from myapp.main import app` dans une feature. Jamais. Les décorateurs
  sont libres (`from bretzel import page, layout`), `include` fait le reste.
- ❌ Importer un symbole d'une autre feature sans qu'il soit dans son
  `provides` — `undeclared_provides` le dira.
- ❌ Déclarer un `uses` qu'on n'utilise plus — `dependency_drift` le dira.
- ❌ `h-screen` sur la racine du shell (§ 5).
- ❌ Recréer une couche technique (`views/`, `controllers/`, un `app/` dans
  une app produit).
- ❌ Un handler en lambda ou en closure — cf. [`handlers.md`](handlers.md).

## 10. Checklist — ajouter une feature

1. Un fichier `features/<nom>.py`, ou un dossier si le contrat est gros.
2. Son `Feature(name=, kind=, provides=, uses=)`.
3. Ses `@page` / `@layout` / `@error`, en important **seulement** `bretzel`.
4. La ligne dans `app.include(...)` de `main.py`.
5. Démarrer : un contrat invalide **fait échouer le boot** et te le dit ; un
   `provides` oublié ou un `uses` dérivé sort en WARN.
