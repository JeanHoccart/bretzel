# Carte d'app — le modèle v4 (ACTÉ, 2026-07-05)

> Statut : **ACTÉ** — fork socle tranché par l'utilisateur : **Option A**
> (groupes socle accrochés aux layouts uniquement, jamais aux pages ;
> le privé-à-une-page remonte au layout avec badge). Le composant
> ``examples/shared/app_map_view.py`` est construit sur ce modèle.

## Pourquoi une v4 — les défauts constatés (tous vérifiés sur MAD)

1. **Une ligne = deux fonctions.** `_render_node : if kids or socle →
   _toggle_row` : toute feature avec enfants OU socle devient un
   chevron-toggle. Cliquer `dashboard` replie au lieu de sélectionner ;
   le détail de TOUTE ligne à chevron (layouts compris) est inaccessible ;
   l'icône de kind disparaît → une page se lit comme un layout.
2. **Placement transitif inexpliqué.** `geo` est placé sous `planning_nav`
   (LCA de {planning, tournees}, atteints VIA planning_engine) mais le
   hover et le détail ne montrent que le direct → le lecteur ne peut pas
   reconstituer le pourquoi. Vérifié : `planning.uses = [planning_engine]`,
   geo absent des deux pages.
3. **Donnée sans vue.** Badge « 6 routes » : le compte s'affiche, la liste
   (`AppGraph.routes`, elle existe) n'est visible nulle part.
4. **`errors` mélangé aux pages de nav.** Exact au fond (`@error_page(404,
   layout=shell)` → le 404 SE REND dans le shell) mais présenté comme une
   page navigable.

**Cause racine** : deux relations de natures différentes — la CONTENANCE
(un arbre, déclaré par `layout=`/`parent=`) et la DÉPENDANCE (un graphe,
déclaré par `uses`/`reads`) — fondues dans UNE seule structure spatiale.
Le LCA est une analyse ; en faire la position produit des placements
inexplicables, des pages-dossiers et des clics contradictoires.

## Prior art — ce que font les systèmes réels (vérifié sur docs officielles,
recherche 2026-07-05)

- **Encore.dev** : les frontières (services = dossiers) et les ressources
  (API/DB/pubsub) sont déclarées en code ; **les arêtes ne sont JAMAIS
  déclarées — toujours dérivées par analyse statique** (« 100% accuracy…
  any deviation is caught as a compilation error »). Dans Flow : boxes +
  flèches (pleine = appel API, tiretée = pubsub). Les « systems » (dossiers)
  sont explicitement non-sémantiques. Pas de placement par usage.
- **Backstage** : tout est **déclaré** en YAML ; vocabulaires disjoints
  contenance (`partOf`/`hasPart`) vs dépendance (`dependsOn`,
  `consumesApis`) ; visualisation = vues de voisinage par entité avec
  filtres, pas un arbre global. **Aucune vérification contre le code** —
  le mode d'échec canonique du catalogue déclaré-seulement.
- **Nx** : arêtes **dérivées des imports** ; intention **déclarée** (tags) ;
  `enforce-module-boundaries` (lint) **réconcilie les deux** — le seul des
  quatre où l'architecture déclarée est machine-vérifiée contre le code.
  Groupes visuels = dossiers (cosmétique) ; **provenance d'arête** : cliquer
  une dépendance montre quels fichiers l'ont créée ; traçage de chemin
  start→end à la demande (pas dessiné par défaut).
- **C4** : la contenance vit sur l'**axe du zoom** (un diagramme = l'intérieur
  d'UN système) ; « large diagrams are usually hard to interpret… nobody is
  going to look at it » ; remède officiel : plusieurs diagrammes simples
  issus d'**un seul modèle** (Structurizr).

**Leçons appliquées à Bretzel** :
1. contenance et dépendance = deux axes, jamais fondus (→ Fautes v3) ;
2. le pattern gagnant = déclaré (intention) + dérivé (réalité) + **lint
   réconciliateur** (→ L1/L2 ci-dessous — sans L2, `uses=` devient un
   catalog-info.yaml : un mensonge bien intentionné) ;
3. la liberté du repo est sûre précisément parce que la vérité ne vient
   pas des dossiers ;
4. un modèle, plusieurs vues focalisées — pas de méga-carte ;
5. **une arête doit pouvoir se prouver** (provenance : quel import/état l'a
   créée) — à brancher sur L2 quand le lint existera.

**Écart assumé (Option A)** : le prior art strict ne niche jamais par usage ;
l'Option A place des GROUPES socle dans l'arbre, accrochés aux layouts.
C'est une projection étiquetée de l'axe dépendance (connecteur tireté +
eyebrow « socle », jamais sous une page), pas une prétention de contenance —
choisie sciemment pour l'effet spatial validé par l'utilisateur.

## Le modèle v4 — 3 questions → 3 vues, 1 manifeste arbitré

### Les rôles (l'API `Feature` ne change pas)

Les 10 kinds se répartissent en 3 comportements de modèle :

| rôle | kinds | se comporte comme |
|---|---|---|
| **ANCRE** (se rend) | shell, layout, page, error | nœud de l'arbre de rendu |
| **SOCLE** (se consomme) | data, state, logic, facade, infra | feuille de dépendance |
| **ENTRÉE** (se déclenche) | job | point d'entrée hors HTTP |

### Le manifeste : contrat ↔ réalité ↔ lint

- **Déclaré** (l'intention, 5 champs) : `name, kind, provides, uses, reads`.
- **Dérivé** (les faits, gratuits) : arbre de rendu (marks `@page`/`@layout`),
  routes, fichier par symbole (`__module__` de chaque provide), **portée**
  (LCA → badge `global | branche <layout> | privé à <page>`), chaînes de
  consommation transitives (« geo ← planning_engine ← planning, tournées »).
- **Linté** (la doc ne peut pas mentir) — **LIVRÉ 2026-07-05** :
  - L1 — `undeclared_provides()` : routable couvert par aucune Feature →
    WARN au startup + section « ⚠ non déclaré » dans la carte
    (`app.undeclared_pages`). Silencieux si l'app n'utilise pas les
    Features (pas de sermon rétroactif).
  - L2 — `dependency_drift()` : `uses`/`reads` déclarés vs **imports
    réels** (AST des modules de chaque feature, via `sys.modules`) →
    WARN dans les deux sens (missing = importé-non-déclaré, stale =
    déclaré-non-importé). Excusés : soi-même, le parent de RENDU (le lien
    `layout=` est déclaré par le mark), les modules hors features.
    Dev-mode only (`config.debug`). Limites documentées : l'union
    uses∪reads est comparée (la nuance n'est pas dérivable d'un import) ;
    les imports sous `TYPE_CHECKING` comptent.
  - Garde permanente : `test_dependency_drift_clean_on_real_examples`
    force les contrats de mad à coller à leurs imports, pour
    toujours.

C'est la réponse à « flexible ET manifeste clair » : le repo reste libre
(les dossiers ne portent AUCUNE sémantique), le manifeste reste 5 champs,
et le framework **arbitre** contrat contre réalité — c'est ce qui rend la
doc vivante fiable pour un humain comme pour une IA.

### Vue 1 — INTERFACE : l'arbre de rendu PUR

- shell → layouts → pages. Une page n'est **jamais** un dossier.
- Les erreurs : micro-groupe distinct « erreurs » sous leur layout
  (icône ⚠, pas mélangées aux pages de nav).
- **Grammaire de clic** : clic ligne = TOUJOURS sélection/détail ;
  le chevron est une petite cible séparée (layouts uniquement).

### Vue 2 — SOCLE : groupé par portée (fork TRANCHÉ — Option A)

Chaque feature socle porte un badge de portée dérivé :
`global` · `branche <layout>` · `privé à <page>`.

- **Option A — RETENUE** (2026-07-05, par l'utilisateur ; `examples/shared/app_map_view.py` est construit dessus) : les groupes socle restent dans l'arbre mais
  accrochés aux **layouts uniquement** (shell, planning_nav…) — jamais
  sous une page ; le privé-à-une-page remonte au layout parent avec badge
  « privé à dashboard ». Garde l'effet spatial validé
  (account_data-sous-account_nav) sans pages-dossiers.
- **Option B** : zone Socle séparée sous l'arbre, groupée par portée.
  L'arbre reste 100 % rendu ; le lien spatial est remplacé par badges+hover.
- **Option C** : les deux, avec un toggle de vue.

### Vue 3 — DÉTAIL & FLUX : l'explication

- Détail (clic) : contrat + **fichier par symbole** (chemin cliquable) +
  **consommateurs transitifs avec la chaîne via** — c'est ce qui rend le
  placement de `geo` lisible.
- Hover : éclaire le direct en fort + le transitif en atténué.
- Badge routes **cliquable** → table `route → feature`.
- Jobs : listés comme « entrées », avec ce qu'ils déclenchent.

## Ce que la v4 SUPPRIME (simplification du composant)

- L'injection du socle dans la récursion de rendu (la cause de la moitié
  des bugs) — l'arbre redevient trivial.
- Le double-rôle du clic — un seul comportement par cible.
- Les compteurs sans vue.
