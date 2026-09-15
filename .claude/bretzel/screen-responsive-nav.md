# `Screen` — nav responsive server-driven

> Spec figée avec l'utilisateur le 2026-07-13, **simplifiée le même jour** après
> reality-check. Remplace la « magie mobile » de la sidebar (flag `mob_open` +
> drawer off-canvas jugé instable) par du `UI = f(state)` : le serveur choisit la
> nav selon un cookie de viewport.

## Ce que c'est (design final)

Le dev écrit un `if` Python **dans son layout** ; le serveur rend l'arbre qui
correspond au viewport, lu depuis le cookie `bz_screen` :

```python
from bretzel import Screen, layout, ui

@layout
def shell() -> None:
    if Screen().is_mobile:                 # vrai bool, lu du cookie
        with ui.vstack():
            topbar()                       # nav en haut, contenu dessous
            ui.outlet()
    else:
        with ui.hstack():
            ui.sidebar(...)                # nav à gauche, contenu à droite
            ui.outlet()
```

- **Pas de `@refreshable`.** Le layout lit `Screen()` au render, point.
- **Une seule nav dans le DOM** (pas de double layout CSS).
- **`Screen().is_mobile` / `.is_touch`** = vrais bool (pas des ClientBinding).

## Décisions actées

- **Server-authoritative, PAS un ClientState** : un champ ClientState lu en
  render lève `ReactivityError` sur `if` (gèle la valeur) → `Screen` est un objet
  par-requête (`bretzel/render/screen.py`, `from bretzel import Screen`) qui lit
  le cookie et expose des bool.
- **Un seul seuil** (`768` = `md`), overridable `Bretzel(mobile_breakpoint=)`.
- **Cookie `bz_screen`** = seul canal client→serveur lisible au render (les modes
  `persist` ClientState sont browser-only, invisibles au serveur). Format
  `"{mobile},{touch}"` (`1`/`0`), écrit pré-paint par le boot-script.
- **⚠️ PAS de live-resize** (décision 2026-07-13, la plus importante) : on a
  retiré tout le mécanisme live (listener matchMedia, route
  `/_bretzel/rescreen`, refetch de zone, morph, auto-détection
  `data-bz-screen-url`, `mobile_breakpoint` dans l'envelope). La correction est
  **au chargement**, pas au redimensionnement.
  ⚠️ La justification d'origine — « changer de device en cours de session
  n'arrive pas » — est vraie pour un *device* et **fausse pour une fenêtre** :
  un dev qui redimensionne son navigateur traverse le seuil plusieurs fois par
  minute, et c'est ce qui a fait remonter le bug des deux F5 le 2026-08-16. Ce
  qui tient de la décision, c'est qu'aucun listener ne réarrange le layout sous
  les doigts ; le prix assumé est **un chargement dur par traversée**.
- **v1 = `is_mobile` + `is_touch`.** Extensions futures si un usage co-occurre :
  `orientation`, `breakpoint` (sm/md/lg/xl).

## Positionnement (à assumer)

`Screen().is_mobile` = **échappatoire pour un swap STRUCTUREL** (sidebar ⇆ topbar :
deux arbres que le CSS ne peut pas échanger proprement). Pour les 90% du
responsive (espacements, colonnes, cacher un panneau, tailles) → **CSS Tailwind**
(`md:` / `max-md:`), instantané, sans cookie ni roundtrip. Ne PAS vendre `Screen`
comme « le responsive à tout faire » (sinon on paie un cookie là où le CSS est
gratuit). Aucun concurrent (LiveView/Streamlit/Reflex/Dash) ne branche le rendu
serveur sur le device → c'est un angle propre, à condition de ce cadrage.

## Mécanisme (2 pièces seulement)

| Pièce | Fichier | Rôle |
|---|---|---|
| **Boot-script** (`<head>`, pré-paint) | `render/shell.py::_screen_boot_script` | lit `matchMedia('(max-width:{bp}px)')` + `(pointer:coarse)` → écrit le cookie `bz_screen`. Seuil interpolé de la config (jamais hardcodé — anti-règle 3). |
| **`Screen`** (au render) | `render/screen.py` | lit le cookie sur `current_context().request` → `is_mobile`/`is_touch` bool ; fallback desktop si absent/hors-contexte. |

**Premier hit** (nouveau visiteur, pas de cookie) : le serveur rend desktop par
défaut ; le boot-script écrit le cookie et, si le viewport réel diffère de ce que
le serveur a supposé, fait **un reload correctif** pré-paint. La requête suivante
porte le bon cookie → rendu correct. Steady-state (cookie déjà bon) : aucun
reload.

**Le garde-fou anti-boucle, et pourquoi il se CONSOMME** (fix 2026-08-16). Le
drapeau `sessionStorage` `bz:screen-synced` est lu **et effacé à chaque
chargement, avant toute sortie anticipée** : il ne décrit donc que le
chargement que le script s'est lui-même infligé.

- Bascule légitime (on redimensionne la fenêtre, on tape F5) → drapeau vierge,
  la correction part : **un seul F5**, dans les deux sens, indéfiniment.
- Oscillation pathologique (fenêtre posée pile sur le seuil : la bascule de
  layout ajoute/retire la scrollbar du document, ce qui déplace le viewport
  d'environ 15px et refait basculer `max-width`) → le chargement forcé retrouve
  le drapeau ET un désaccord, il abandonne. Jamais de boucle.

⚠️ Le drapeau était un **booléen jamais effacé** jusqu'au 2026-08-16 : la
première correction de l'onglet le consommait pour de bon et toutes les
suivantes étaient avalées — cookie réécrit, peinture périmée à l'écran, **deux
F5 par bascule** (signalé sur une app de démo depuis retirée). Deux reformulations plus simples
ont été essayées et rejetées, elles sont documentées dans le docstring de la
gate : drapeau keyé par forme et accumulé (borné à 4 reloads → le bug revient),
et quota de reloads par fenêtre de temps (bloque un dev qui redimensionne vite).

**La navigation BOOSTÉE corrige aussi** (livré le 2026-08-16, dans la foulée).
`hx-boost` ne remplace que `[data-bz-outlet]`, or le layout qui porte le
`if Screen().is_mobile` vit au-dessus, et le script de `<head>` ne rejoue pas :
cliquer des liens après un redimensionnement repeignait l'ancienne forme
**indéfiniment**, et le cookie restait périmé — le serveur ne pouvait même pas
le savoir. Aucune erreur, aucun 4xx : juste la mauvaise nav à l'écran.

`05_bridge.js` appelle donc `$bzScreenSync()` sur `htmx:configRequest` quand la
requête est un GET déclenché par un `<a>`. Si la forme a changé, il annule le
swap (`preventDefault`, mécanisme déjà éprouvé par le garde d'inertie) et rend
la navigation au navigateur : chargement complet, shell re-rendu depuis le
cookie frais. Sinon — le cas courant — le partial-nav suit son cours intact.

⚠️ **Ce n'est pas un retour du live-resize.** Rien ne se déclenche au
redimensionnement ; la resynchro est accrochée à une navigation que
l'utilisateur a demandée, exactement comme un F5. La restriction aux `<a>` est
load-bearing : les GET des zones `@refreshable` et du refetch SSE passent par le
même hook et ne doivent jamais devenir une navigation.

**Le partage `$bzScreenSync`** : la mesure du viewport (matchMedia + seuil
interpolé + écriture du cookie) est définie UNE fois dans le script pré-paint
(`shell.py::_screen_sync_script`) et appelée par deux endroits — le booteur et
le runtime. Le nom vit dans `protocol.py` (`SCREEN_SYNC_FN`), substitué dans le
bundle par `_build.py` et miroité par `test_python_js_mirror`. C'est le lecteur
JS qui lui vaut sa place là ; la clé `sessionStorage` du drapeau, elle, reste
locale à `shell.py` — personne ne la lit côté JS.

Gaté deux fois : `tests/consistency/test_screen_sync_guard_is_consumed.py` (le
texte des deux scripts + l'appel côté runtime — **le seul des deux qui tourne
dans le sous-ensemble par défaut**) et
`tests/runtime_js/test_screen_switch_costs_one_reload.py` (le comportement,
marqué `browser` donc opt-in) : quatre bascules au F5 dans un test, et un
second test qui **clique** — l'app-sonde y place son repère dans le LAYOUT, hors
outlet, sinon le boost l'échangerait et le test passerait en croyant mesurer le
layout. Il porte aussi un témoin en sens inverse : une nav qui ne traverse aucun
seuil doit rester un swap partiel, sinon un « fix » qui rechargerait tout
passerait en ayant supprimé le partial-nav.

La gate déterministe a d'abord été livrée en version faible : verte sur trois
mutations dont deux remettaient le bug mot pour mot. Ce qui l'a réparée : borner
**l'écriture** du drapeau (une seule, après toutes les sorties) et sa
**polarité**, pas seulement sa consommation.

## État — LIVRÉ (2026-07-13)

- ✅ `Screen` server-authoritative (`render/screen.py`), `from bretzel import Screen`, 7 unit tests.
- ✅ `Bretzel(mobile_breakpoint=768)` validé, threadé jusqu'au boot-script.
- ✅ Boot-script cookie + reload correctif (`shell.py`), tests shell.
- ✅ Serveur branche sur le cookie, outlet rempli (`test_screen_responsive.py`, e2e).
- ✅ Live-resize retiré (rescreen route / listener / morph / auto-détection / envelope-breakpoint).
- ✅ Démo dédiée (port 8005) : `@layout` + `if` + outlet, `ui.sidebar`/`ui.navbar`, zéro Tailwind hand-drawn. ⚠️ L'app a été retirée le 2026-09-07 à l'élagage des exemples ; le pattern est celui de `examples/chat` et `examples/crm`, qui branchent tous deux sur `Screen().is_mobile`.
- ✅ **Reload correctif confirmé en navigateur** (2026-08-16) : `tests/runtime_js/test_screen_switch_costs_one_reload.py` monte une app-sonde, bascule quatre fois de part et d'autre du seuil et exige un seul F5 par bascule. C'est ce qui restait « browser-only » ici.
- ✅ **Phase 6 (2026-07-14)** : magie mobile intégrée de `ui.sidebar` retirée (`mob_open`/drawer off-canvas/backdrop/hamburger/`max-md:` topbar auto) — composant + thème + tests + catalogue visuel + docstring navbar. Desktop rail/drawer/collapse intacts. Le mobile est le `if Screen().is_mobile` du dev.
- 🔲 Reste : migrer les exemples (`docs`/…) qui dépendaient de la magie mobile vers le pattern `Screen` (décision différée — ils cassent sur mobile en attendant). `chat` et `crm` sont déjà sur le pattern (`features/shell.py`).
