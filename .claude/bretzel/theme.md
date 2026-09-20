# Theme — tokens, slots, color/variant/size composition

Source : `bretzel/theme/`. Public surface : `from bretzel.theme import Theme` → `Bretzel(theme=Theme(...))` (**une instance `Theme`, jamais un dict brut**). Les composants importent leur theme depuis `bretzel/components/<famille>/<name>/theme.py`.

---

## Anatomie d'un theme de composant

```python
# Un theme.py réel — ici bretzel/components/feedback/badge/theme.py
BADGE_THEME: dict[str, Any] = {
    "slots": {
        "root":  "inline-flex items-center gap-1 rounded-md …",
        "label": "truncate",
        "close": "shrink-0 …",          # le × (si dismissible / on_close)
    },
    # ⚠️ Les variants de Badge sont des DICTS multi-slot, pas des strings.
    "variants": {
        "soft":    {"root": "bg-(--bz-bg) text-(--bz-text)"},
        "solid":   {"root": "bg-(--bz-solid) text-(--bz-on-solid)"},
        "outline": {"root": "border border-(--bz-border-hover) "
                            "text-(--bz-text)"},
    },
    # ⚠️ Ses sizes aussi — et une entrée peut porter autre chose que des
    # classes (``icon_size`` est un palier passé à un Icon enfant).
    "sizes": {
        "xs": {"root": "px-1.5 py-0 text-[10px] h-4", "close": "h-3 w-3",
               "icon_size": "xs", "close_icon_size": "xs"},
        # … sm / md / lg / xl
    },
    # Badge n'a PAS de bloc "modifiers". Deux composants seulement en ont
    # un : Text et Table.
}
```

> ⚠️ **Cet exemple était faux sur ses quatre sections jusqu'au
> 2026-08-01** : il donnait un slot `dot` qui n'existe pas, des `variants`
> et des `sizes` en strings plates alors qu'ils sont tous des dicts, et un
> bloc `"modifiers": {"loading": …}` que Badge n'a pas — tout en
> s'annonçant comme une citation de `badge/theme.py`. Il se contredisait
> même avec le § *Règle de forme `variants`* plus bas, qui cite Badge comme
> LE cas dict. Un exemple annoté d'un chemin de fichier doit être copiable
> depuis ce fichier.

---

## Comment une couleur atteint un composant — les PALIERS

⚠️ **Ce mécanisme a changé le 2026-08-30** (chantier des jetons de
couleur). Jusque-là un thème écrivait des **gabarits** — `bg-{bg_color}`,
une demi-classe comblée au rendu contre le `color=` du composant. Le
compilateur Tailwind ne peut pas voir une demi-classe, donc le framework
en calculait la **clôture** : chaque forme × chaque couleur, 3 791
classes, **80 % du `style.css`**.

Aujourd'hui un thème lit **douze paliers**, qui sont des variables CSS :

| palier | rôle |
|---|---|
| `--bz-bg` `--bz-bg-hover` `--bz-bg-active` | les fonds teintés |
| `--bz-border` `--bz-border-hover` | les bordures |
| `--bz-focus` `--bz-focus-soft` | l'anneau de focus (clavier / champ) |
| `--bz-solid` `--bz-solid-hover` `--bz-on-solid` | l'aplat plein et ce qu'on écrit dessus |
| `--bz-text` `--bz-text-muted` | le texte accentué |

Le thème écrit `bg-(--bz-bg)` : une classe **complète**, que le
compilateur voit. La couleur, elle, vient de la **classe-pont** que le
socle tamponne sur la racine rendue — `bz-c-primary`, `bz-c-error`… —
et qui installe les douze variables sur tout le sous-arbre. Cf.
`bretzel/theme/bridges.py`.

Trois conséquences qu'il faut connaître :

1. **Teindre une zone** : `bz-c-error` sur un conteneur donne ses paliers
   à tout ce qu'il contient — un composant qui pose son propre pont
   garde le sien.
2. **Repeindre une instance** : `style="--bz-solid: #b91c1c"` change les
   douze paliers de ce composant-là. Aucun `classes=` ne sait faire ça.
3. **Un composant TIERS n'a rien à déclarer** : sa classe est complète,
   donc le compilateur la trouve dans son source.

---

## Tokens de palette

**11 slots sémantiques** <!--count:semantic_color_slots-->, fixes et connus
du framework (`SEMANTIC_COLOR_NAMES`,
`bretzel/theme/tokens.py`). Chacun reçoit sa **classe-pont** `bz-c-<nom>` :

`primary` · `secondary` · `success` · `error` · `warning` · `info` ·
`background` · `surface` · `interface` · `text` · `muted`

**Foreground auto** : pour chaque slot, un `<color>-foreground` est dérivé
automatiquement par algèbre de contraste (`palette.py`) — c'est ce que le
palier `--bz-on-solid` porte. Il est **teinté** de la teinte du fond pour
que la paire reste d'un seul morceau, mais depuis le 2026-09-01 cette
teinte **recule** dès qu'elle empêcherait d'atteindre WCAG AA (4,5:1) :
`_readable_fg` s'arrête au premier cran suffisant, donc une couleur qui
clôt AA d'emblée sort inchangée à l'octet près.

**Les deux paliers de TEXTE reculent quand il le faut.** `--bz-text`
(corps de texte accentué, barre 4,5:1) et `--bz-text-muted` (une
affordance, barre 3:1) valent 55 % et 70 % de la teinte — sauf sur une
teinte trop claire pour que ça suffise. `bridges.readable_step_pct`
recule alors vers le texte au premier cran qui franchit la barre :
`amber` sort à 50/65, `yellow` à 45/60, les 41 autres couleurs sont
inchangées à l'octet près. Une DÉRIVATION, pas une table par teinte —
une couleur ajoutée demain est servie sans qu'on y touche.

⚠️ Les cinq slots de SURFACE (`background`, `surface`, `interface`,
`white`, `black`) en sont ÉCARTÉS bien qu'ils échouent la même barre :
la gate ne les juge pas, et le fond contre lequel ils devraient se
mesurer n'est pas la page. Cf. `todo.md`.

⚠️ **Cette algèbre est écrite DEUX fois.** Le theme studio du playground
ne parle jamais au serveur, donc il la redit en JavaScript
(`FOREGROUND_JS`). Une modification d'un seul côté fait diverger le CSS
généré et l'aperçu du studio, sans que rien ne casse — les deux moitiés
restent plausibles séparément. C'est gardé par
`test_foreground_algebra_is_mirrored` (chaque nombre nommé doit exister
des deux côtés) et prouvé par `probe_foreground_mirror` (l'égalité des
SORTIES sur 18 couleurs, hexadécimal exact).

### Les valeurs livrées — neutres ACHROMATIQUES (2026-09-13)

| slot | clair | sombre |
|---|---|---|
| `background` | `#fafafa` | `#0a0a0a` |
| `surface` | `#ffffff` | `#151515` |
| `interface` | `#f0f0f1` | `#212121` |
| `text` | `#171717` | `#f5f5f5` |
| `muted` | `#6b6b6e` | `#a0a0a3` |
| `primary` | `#3a52b0` | *(idem — les couleurs de marque ne basculent pas)* |
| `secondary` | `#9c3f72` | *(idem)* |

Les neutres étaient le `slate` de Tailwind, donc **bleutés**. Un gris qui
porte une teinte prend parti pour elle : il réchauffe ou refroidit tout ce
qu'on pose dessus, et il se querelle avec l'accent de l'app dès que
celui-ci part dans l'autre sens. À teinte nulle, le fond ne dit rien et la
marque est la seule couleur de l'écran — ce qu'on attend du défaut d'un
framework, qui ne connaît pas la marque de l'app qui l'utilisera.

⚠️ **`interface` ne vaut plus `background`.** Les deux étaient à `#f8fafc`
en clair : un champ, un panneau de select, un creux de contrôle rendaient
EXACTEMENT la couleur de la page, et toute la hiérarchie de profondeur
reposait sur la seule bordure. Ce n'était pas un choix — c'était le même
jeton recopié deux fois.

⚠️ **Le sombre n'est plus un quasi-noir marine.** `#020617` était presque
noir ET très bleu : sous un aplat saturé il fatigue en quelques secondes,
et l'écart jusqu'à `surface` était un saut. Les trois plans montent
maintenant par crans réguliers, ce qui est ce qui fait lire une
profondeur.

**La distance entre les deux accents est MESURÉE**, pas jugée à l'œil :
`test_palette_distinctness` exige ΔE ≥ 30 entre couleurs de marque. La
prune est à 47 de l'indigo et 47 du rouge d'erreur. Un améthyste
(`#8455ab`) a été essayé le même jour et **refusé par la gate** — ΔE 21 de
l'accent, donc deux couleurs sémantiques qui se ressemblent et une matrice
de variantes ambiguë.

Sous les 11 slots vit une **palette de ~30 teintes hex nommées** (le "raw").

Personnalisation — **via une instance `Theme`**, jamais `Bretzel(palette=...)`
(ce param n'existe pas) :

```python
from bretzel.theme import Theme

app = Bretzel(theme=Theme(
    semantic={"primary": "#27754a"},   # override d'un slot sémantique
    palette={"tomato": "#e54d2e"},     # override d'une teinte brute
))
```

---

## `compose_class(slot, *, color=None, apply_variant_size_modifiers=True)`

Appel typique dans un `render()` :

```python
attrs["class"] = self.compose_class("root", color=current_color)
```

**Pour le slot `"root"` avec `apply_variant_size_modifiers=True`** (défaut), assemble dans cet ordre :

1. `theme["slots"]["root"]`
2. `theme["variants"][<reactive variant>]` si présent
3. `theme["sizes"][<reactive size>]` si **string** (ignoré si dict)
4. Toute clé de `theme["modifiers"]` dont le reactive_prop éponyme est truthy

> ⚠️ Ni le `classes=` user ni l'override `slots={"root": "…"}` ne sont ajoutés
> par `compose_class`. Les deux sont appliqués plus tard, sur le vrai root, par
> `_apply_universal_modifiers` (le wrap de render de la métaclasse) — ainsi
> **tous** les composants les honorent uniformément, quel que soit le slot qui
> compose leur root, et même s'ils lisent `theme["slots"]["root"]` à la main.
> Fonctionnellement ils gagnent quand même (ajoutés en dernier → source order),
> dans cet ordre : thème → `slots={"root"}` → `classes=`.
>
> Avant ce déplacement (audit du socle 2026-07-29), `slots={"root": …}` n'avait
> qu'un seul lecteur — cette étape — donc Card, Text, Badge, Input, Heading,
> Divider, Sidebar et Navbar le perdaient **en silence**. Gate :
> `tests/consistency/test_root_slot_override_universal.py`.

**Pour les slots non-root** ou `apply_variant_size_modifiers=False` : juste l'étape 1, **plus** l'override `slots={"<slot>": "…"}` de l'instance s'il y en a un. Utilisé par les composants multi-slots qui composent eux-mêmes leur size (Checkbox, Switch, Input, Select, Dropdown).

> ✅ **Un slot non-root est honoré même sans `compose_class`** — réparé le
> 2026-07-29 (chantier socle, item 1). La fusion vit dans
> `_resolved_theme()`, où puisent AUSSI les 164 lectures manuelles de
> `theme["slots"][X]` : le socle ne patche pas le nœud rendu, il donne le
> bon thème AVANT le rendu. Un fix posé dans le seul compositeur n'aurait
> atteint qu'un cinquième du catalogue (35 fichiers composent via
> `compose_class`, contre 164 lectures directes). `ToggleGroup`, le cas qui
> avait servi de mesure, lit bien `self._resolved_theme()`.
>
> ⚠️ Ce paragraphe annonçait « dette ouverte, pas encore gatée » jusqu'au
> 2026-08-01 — pessimisme périmé, et la règle EST gatée par
> `test_theme_reads_are_resolved`.

→ Quand le size est un dict (`sizes["md"] = {"root": "...", "icon": "..."}`), le composant lit le dict manuellement dans son `render()`. C'est pour ça qu'on voit `size_map = sizes.get(size_key, {})` partout.

---

## Variants vs Sizes vs Modifiers

| Notion | Reactive prop | Format theme | Application |
|---|---|---|---|
| **Variant** | `variant: str = reactive_prop(default="solid")` | `theme["variants"][<v>] = "…"` ou dict | Une seule valeur active à la fois |
| **Size** | `size: str = reactive_prop(default="md")` | `theme["sizes"][<s>] = "…"` ou dict | Une seule valeur active à la fois |
| **Modifier** | `loading: bool = reactive_prop(default=False)` | `theme["modifiers"][<bool_prop_name>] = "…"` | Multiples actifs en même temps |

Pour un composant Button : `variant=solid` + `size=md` → **2** classes
empilées, pas 3. `BUTTON_THEME` n'a **pas** de bloc `modifiers` (son thème
le dit en commentaire : « No ``modifiers`` map »), donc `loading=True`
n'empile rien par cet axe — l'affordance loading passe par un swap de
spinner, pas par une classe de modifier. Deux composants seulement ont un
bloc `modifiers` : Text et Table.

### Règle de forme `variants` (string vs dict)

Une `variants` value est :

- **String plate** quand la variante ne tweake QUE le slot `root` (cas par défaut, e.g. Button : `"solid": "bg-(--bz-solid) …"`).
- **Dict multi-slot** quand la variante tweake plusieurs slots ensemble — typique des composants à × button où la variante doit ajuster le bg ET la couleur du close icon (e.g. Badge : `"soft": {"root": "bg-…/15 …", "close": "text-…/80 …"}`).

Pas de mix dans le même composant : si UNE variante a besoin du dict, TOUTES doivent l'avoir (sinon `compose_class` casse au runtime sur les variants qui restent strings). ⚠️ **`compose_class` ne sait PAS lire un dict** : il passe
`theme["variants"][v]` tel quel à `_resolve_template`, qui attend une
string. C'est l'inverse de ce que cette ligne affirmait jusqu'au
2026-08-01 — ce sont les **dicts** qui ne passent pas par le compositeur.
Badge, seul cas dict du dépôt, lit donc ses variants **à la main** dans
`badge.py`. Corollaire : le « sinon `compose_class` casse sur les variants
qui restent strings » était inversé aussi. Les autres slots du dict (close, icon, …) sont lus manuellement dans `render()`.

Idem pour `sizes` : string si seul le root bouge (Button), dict si plusieurs slots scalent ensemble (Badge avec `root` + `close` + `icon_size` + `close_icon_size`).

---

## Personnalisation app-level

```python
app = Bretzel(
    theme=Theme(
        components={
            "button": {
                "slots": {"root": "rounded-2xl …"},  # override partiel
            },
        },
    ),
)
```

**Le vocabulaire accepté se lit** — depuis le 2026-08-16, `bretzel describe
<nom>` liste les groupes du thème et leurs clés (les valeurs, les chaînes de
classes des 102 composants <!--count:components-->, restent dans le code) :

```
Thème (clé : sidebar) — Theme(components={'sidebar': {…}})
  backdrop      — (valeur unique)
  collapse      none, offcanvas, overlay, rail
  slots         rail_tip, root, scroll, section, section_divider, …
  widths        lg, md, sm
```

⚠️ **La clé est `THEME_KEY`, pas le nom `ui.*`** — huit composants diffèrent, et
trois écrivent sous le thème d'un AUTRE : `sidebar_section` et `sidebar_title`
s'écrivent tous deux sous `'sidebar'`, `navbar_section` sous `'navbar'`. Les
classes qui partagent une clé partagent le **même objet** `THEME` (vérifié :
92 clés distinctes <!--count:theme_keys-->, 2 partagées).

⚠️ **39 noms de groupes de premier niveau** <!--count:theme_group_names--> dans
le catalogue, pas trois :
`slots` (89 composants <!--count:theme_slots_group-->),
`sizes` (46 <!--count:theme_sizes_group-->),
`variants` (8 seulement <!--count:theme_variants_group-->), puis
`widths`, `gaps`, `paddings`, `modifiers`, `colors`, `shapes`, `statuses`,
`ratios`, `sides`, `collapse`, `backdrop`… **21 groupes** <!--count:theme_scalar_groups-->
ne sont pas des tables mais une valeur unique (`hoverable`, `sticky`,
`wrap`, `palette`, `icon_size`). Dispersion connue et non normalisée : l'indexer d'abord la rend
visible, on ne gate pas un vocabulaire qu'on ne sait pas énumérer.

**Une clé inconnue LÈVE** (2026-08-16). Deux moments, et l'asymétrie est
imposée par l'architecture, pas choisie :

| Section | Quand | Pourquoi |
|---|---|---|
| `semantic`, `semantic_dark` | **à la construction** (`Palette.__init__`) | les 11 slots vivent dans `theme/tokens.py`, même couche |
| `components` | **au démarrage de l'app** (`server.lifecycle._validate_theme`) | le vocabulaire vient des classes de composants, et `.importlinter` interdit à `bretzel.theme` de les importer |

Contrepartie assumée du second cas : un `Theme` reste **constructible sans la
couche composants**, donc testable seul. `Theme(components={"crad": …})` ne
lève qu'au boot — gaté par `test_theme_refuses_unknown_keys`.

**Ce qui reste ouvert, et doit le rester** : `palette` / `palette_dark` (liste
ouverte de couleurs nommées — la fermer casserait la fonctionnalité) et les
clés des groupes adressés par une valeur de prop (`variants`, `sizes`,
`paddings`…), où ajouter une entrée est le chemin **recommandé** pour dévier
du thème livré. Seul `slots` est fermé : un slot est composé par le code du
composant, donc un nom qu'il ignore est mort par construction.

La règle de lint `unknown-theme-vocabulary` applique **la même** table, en
statique — elle voit sans exécuter, donc elle attrape aussi le thème d'un
module jamais importé. Le vocabulaire est dérivé une seule fois, dans
`bretzel.introspect.theme_vocabulary()`, et consommé par les deux règles de
lint ET la validation au démarrage : une seule table, un seul comportement.

`_resolved_theme()` (méthode de `Component`) appelle `app.theme.merged_component_theme(<THEME_KEY>, cls.THEME)` : deep-merge **récursif** clé-par-clé à tous les étages (`merge_component_themes`, cf. `theme/slots.py`) — un override de `slots.root` n'efface ni les autres slots, ni `variants`/`sizes`. Une **feuille string** redéfinit son entrée en entier (fournir le template complet) — ≠ du `slots=` par-instance qui AJOUTE. Le merge est mémoïsé par `THEME_KEY` sur l'instance `Theme` (les deux entrées sont immuables après le boot ; `compose_class` résout le thème une fois PAR SLOT). Gate : `tests/consistency/test_theme_override_merge.py`. *(Avant le 2026-07-15, l'override remplaçait le dict livré ENTIER — cf. traps.md § « Theme(components=…) écrasait le thème livré ».)*

---

## Les formes — `Theme(shape=…)` et `Theme(stroke=…)` (2026-08-30)

```python
Theme(shape={"box": "1rem", "field": "0.5rem", "selector": "0.25rem"},
      stroke="1px")
```

### Trois familles de rayon, pas une échelle

Émises dans `@theme` comme `--radius-<famille>`, donc Tailwind v4 en
fabrique de vraies utilitaires avec leurs variantes de coin :

| famille | ce qu'elle veut dire | exemples |
|---|---|---|
| `rounded-box` | l'élément **contient** d'autres éléments | card, dialog, panneau de select, popover, table, sidebar |
| `rounded-field` | un contrôle qu'on **vise**, avec son cadre | button, input, textarea, cadre de picker, pagination |
| `rounded-selector` | une petite **marque**, ou un contrôle **imbriqué** | checkbox, badge, croix d'effacement, cellule de calendrier, onglet |

Avant, six jetons — `xl` 46×, `full` 31×, `md` 28×, `lg` 12×, `sm` 7×,
`2xl` 3× — et **rien n'écrivait pourquoi**. Ce n'était pas un défaut de
discipline : il n'y avait aucune question à laquelle répondre en écrivant
un slot neuf, donc chacun copiait son voisin.

⚠️ **`rounded-full` n'appartient à aucune famille, et ne doit pas y
entrer.** Le rond d'un switch, d'un radio, d'un spinner ou d'une barre de
progression est leur FORME : les équarrir ferait lire le switch comme une
case à cocher. 32 slots restent en dur. Radix Themes documente la même
règle — chez eux `radius="full"` rend un bouton en pilule mais ne rendra
jamais une checkbox ronde. **30 chaînes de slot** l'écrivent en dur
(re-mesuré le 2026-08-31 par le lecteur partagé de `_discovery`, celui de
la gate ; le « 32 » écrit ici la veille venait d'un `grep` de lignes, qui
compte aussi les docstrings). `rounded-none` est la seconde sortie —
**1 slot** : l'angle vif volontaire, au milieu d'une plage de calendrier.

### Une largeur de trait, deux crans dérivés

```
--bz-stroke:        1px                          71 slots
--bz-stroke-strong: calc(var(--bz-stroke) * 2)   12 — l'emphase (bouton `outline`, onglet actif)
--bz-stroke-accent: calc(var(--bz-stroke) * 4)    3 — l'accent latéral (bandeau, citation)
```

Écrites en `border-(length:--bz-stroke)`, qui pose `border-style` en plus
de la largeur — donc remplace `border` à l'identique. `border-0` reste
licite : il RETIRE une bordure, il ne règle pas une largeur.

Les crans **dérivent** au lieu d'être réglés : à largeur fixe, pousser la
base à 2 px ferait disparaître l'emphase, et le bouton `outline`
cesserait de se distinguer du bouton plein.

⚠️ **`--bz-stroke` et non `--bz-border`** : ce dernier est déjà un palier
de couleur des ponts, et `border-(--bz-border)` compile en
`border-color`. Le nom vient de Fluent 2.

### La densité — l'échelle d'un OUTIL, livrée (2026-09-13)

Le défaut de Bretzel n'est plus celui de Tailwind : **contrôle à 30 px,
texte médian à 14 px**. Une app n'a rien à demander. Pour reprendre
l'échelle d'un document :

```python
Theme(spacing="0.25rem", text={"base": "16px", "sm": "14px", "xs": "12px"})
```

C'est **la base de l'échelle, pas un multiplicateur**, et la distinction
est le sujet. Cette place disait « la densité n'est PAS ouverte » : un
curseur global (Radix `scaling`, Reflex `scaling`, Mantine `scale`) serait
une seconde manière de faire ce que `size=` fait déjà par composant. Ce
motif tient toujours. Sa propre clause de sortie disait quoi ouvrir le
jour où le besoin remonterait — *« la BASE de cette échelle, pas un axe
neuf »* — et c'est ce qui est livré :

| paramètre | ce qu'il émet | ce qui en dérive |
|---|---|---|
| `spacing` (défaut `0.1875rem` = 3 px) | `--spacing` | `h-10`, `p-4`, `gap-2`, `w-6`… tout en `calc(var(--spacing) * n)` |
| `text` (défaut 11/13/14/16/18/22) | `--text-<palier>` | les utilitaires `text-*` des thèmes |

⚠️ **Toujours émis**, contrairement aux fontes. La règle « on ne recopie
pas une valeur d'amont » vaut pour ce qu'on HÉRITE ; ici Bretzel
**choisit**, et une valeur choisie doit sortir. Les paliers d'affiche
(`3xl` et au-delà) restent ceux de Tailwind : aucun chrome ne les écrit.

⚠️ **Le palier médian se dit `base`, pas `md`.** Deux échelles se touchent
ici et une seule fois : `--text-*` est celle des jetons CSS, `xs→xl` celle
des `size=` d'un composant, et c'est le thème du composant qui traduit
(`"md": "text-base"`). Une clé inconnue lève à la construction.

`DEFAULT_SPACING_PX` (3) est exporté pour les apps qui doivent COMPOSER
une géométrie en Python — la hauteur d'un bloc de N heures dans une
grille. Une classe Tailwind ne sait pas additionner, et deux autorités sur
la même grandeur ne se composent pas : leur accord est gaté.

### Pourquoi c'est le DÉFAUT et pas un préréglage

Il l'a été une journée, sous le nom `COMPACT`, et c'était un détour. Le
repère qui a tranché : les **défauts** d'Ant Design sont `controlHeight`
32 et `fontSize` 14, à peu près où les nôtres atterrissent, et son
`compactAlgorithm` descend ENCORE en dessous. C'était donc le défaut de
Bretzel qui était l'exception — hérité de Tailwind, qui vise des pages,
jamais choisi.

Le besoin était remonté deux fois, mesuré : `examples/kanban` puis
`examples/ecole` ont écrit la même correction, chacun de son côté. La
première tentative d'`ecole` est le résultat utile : 300 lignes copiées du
kanban, une table de tailles **composant par composant**, onze noms cités.
L'app en utilisait onze autres, restés au défaut → **quatre hauteurs de
champ texte sur un même écran**. Une liste écrite à la main est une liste
de composants qu'on a pensé à citer. Le défaut livré ne nomme donc **aucun**
composant : sa couverture ne peut pas être partielle.

Il n'y a pas non plus de préréglage `DOCUMENT` pour revenir en arrière :
ce serait un second nom pour les valeurs de Tailwind, donc exactement le
doublon d'amont que la règle des fontes écarte. Les deux paramètres
suffisent.

⚠️ **Ce que déplacer la base ne répare pas** : 39 chaînes de thème
écrivent une taille littérale (`text-[10px]`, `h-[1.75rem]`). Elles sont
hors de portée d'un jeton, et c'est la dette « `size=` n'atteint pas tous
les slots » de `todo.md` — pas un trou de ce paramètre.

### La gate

`tests/consistency/test_a_radius_belongs_to_a_family.py` refuse tout
`rounded-<cran d'échelle>` et toute largeur littérale dans `bretzel/` —
thèmes ET runtime JS.

---

## Typographie — `Theme(fonts=…)` (août 2026)

```python
Theme(fonts={"sans": "Inter, ui-sans-serif, system-ui, sans-serif"})
```

Trois slots, **fermés** : `sans` / `serif` / `mono` (`FONT_SLOT_NAMES`). Ce ne
sont pas des noms maison — ce sont ceux de Tailwind v4, ce qui donne trois
choses gratuitement : les utilitaires `font-sans`/`font-serif`/`font-mono`
suivent ; `--default-font-family: var(--font-sans)` (posé par Tailwind) fait
que redéfinir `sans` **repeint le document entier** via le preflight
`html { font-family: var(--default-font-family, …) }` ; et `Heading` écrit
déjà `font-sans` en dur dans son thème, donc les titres suivent sans qu'un
composant bouge. Vérifié sur un `style.css` réellement compilé : **une** seule
déclaration `--font-sans` en sortie, la nôtre — Tailwind fusionne notre
`@theme` par-dessus ses défauts au lieu de l'ajouter après.

Une clé hors des trois **lève** (`ThemeError`), une famille vide aussi. Pour
une fonte de titre distincte, c'est `Theme(components={"heading": …})` — pas
un quatrième slot, qu'il faudrait inventer côté Tailwind ET câbler composant
par composant.

**Aucun défaut n'est recopié** côté Bretzel : section absente ⇒ rien d'émis
⇒ les piles de Tailwind tiennent. Recopier `ui-sans-serif, system-ui, …` ici
créerait un doublon dont la seule évolution possible est de diverger de
l'amont, en silence.

⚠️ `fonts=` déclare la **famille**, pas le **fichier**. Bretzel ne télécharge
aucune fonte et n'écrit aucun `<link>` vers un CDN tiers : le `@font-face`
va dans `Theme(css=…)` et le `.woff2` se sert depuis `Bretzel(static_dir=…)`.

## La porte CSS — `Theme(css=…)` (août 2026)

```python
Theme(css=Path("app/identity.css"))     # ou une chaîne littérale
```

La sortie pour ce qu'aucun theming de composant ne peut exprimer :
`@font-face`, `@keyframes`, `@supports`, propriétés custom, CSS de survie sur
du balisage tiers. Chaîne **ou** `Path` — le discriminant est le type, pas une
heuristique sur le contenu ; un fichier absent lève.

Trois propriétés, et elles viennent toutes du fait qu'elle traverse le **même**
pipeline que le reste :

1. **Elle est la dernière section**, donc l'app gagne la cascade à
   spécificité égale. C'est tout l'intérêt : une échappatoire qui perd contre
   ce qu'elle vient corriger n'échappe à rien.
2. **Elle est compilée et minifiée** avec le thème.
3. **Elle entre dans l'empreinte sha256** de `get_or_build_css`, donc changer
   une règle invalide le `.bretzel/style.css` en cache — comme changer une
   couleur. Un `<style>` injecté dans le `<head>` n'aurait eu aucune des trois.

Elle **s'ajoute** à celle de la base (`Theme(base=…)`), elle ne la remplace
pas — et `css=""` remet à zéro, seule sortie explicite, comme
`scrollbar=None`. La première version remplaçait ; mesuré, ça donnait une
moitié de thème : un enfant qui déclarait son CSS gardait le `--font-sans` de
la marque (les sections dict, elles, se mergent) et perdait le `@font-face`
qui rendait cette fonte chargeable — retour à la pile système, sans un mot.
Le morceau de l'enfant vient après celui de la base, donc la cascade CSS suffit
à surcharger : pas besoin d'un mécanisme de retrait en plus.

Gate : `tests/consistency/test_theme_declaration_reaches_the_sheet.py`.

---

## Pièges thèmes

- **Une classe de couleur ne s'ASSEMBLE jamais.** `f"bg-{color}/10"` produit une classe qui n'existe dans aucune source : le compilateur de prod ne la génère pas, et elle ne marche qu'en dev (où il scanne le DOM vivant). Écris le palier, laisse le pont porter la couleur. Gaté par `test_no_colour_class_is_assembled_by_hand`.
- **Une couleur inconnue LÈVE.** `ui.badge(color="neutral")` — un nom de Tailwind ou de shadcn qu'on écrit par réflexe — n'a pas de pont, donc pas de paliers, donc un composant rendu nu. Le socle refuse au rendu (`_wiring._refuse_unknown_color`).
- ⚠️ **`classes=` ne gagne PAS de façon fiable contre le slot** — cette ligne
  a affirmé le contraire jusqu'au 2026-08-16 (« gagne en source order […] si
  tu veux qu'elle gagne, c'est déjà le cas »), et le commentaire de
  `compose_class` le dit encore. C'est faux : entre deux utilitaires de la
  **même propriété**, l'arbitre est l'ordre de la FEUILLE, que Tailwind
  décide, pas l'ordre de l'attribut `class`. Mesuré sur `.bretzel/style.css`
  compilé, pour un `ui.card` : `bg-black` (offset 66348) **perd** contre le
  `bg-surface` du thème (80394) ; idem `rounded-none` (34455 < 34528),
  `shadow-none` (201508 < 201677), `w-fit` (22460 < 22485). Seul
  `overflow-visible` (33654 > 33621) passe. Sur le padding l'override ne
  gagne que vers le HAUT (`p-8` bat `p-4`, `p-2` non). Le mode de défaillance
  est silencieux : la classe est dans le DOM, la règle est dans la feuille,
  rien ne s'applique.
  **Ce qui marche** : le suffixe important (`bg-black!`, idiome déjà utilisé
  pour `h-full!` dans le thème sidebar), ou — mieux — nommer la déviation
  dans le thème (`Theme(components={…})`, `variants`), ce qui compose UNE
  chaîne racine et ne met rien en concurrence.

---

## Pour ajouter un nouveau theme

1. Créer `bretzel/components/<famille>/<name>/theme.py` avec `<NAME>_THEME = {...}`.
2. Le `<name>.py` importe `from .theme import <NAME>_THEME` et le pose en `THEME: ClassVar = …`.
3. Pas besoin de plug global — `_resolved_theme()` lit `cls.THEME` par défaut, et merge l'override app si présent sous `THEME_KEY`.
4. Si tu utilises `compose_class("root")` standard, tout est branché.
