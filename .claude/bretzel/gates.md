# Écrire une gate — `tests/consistency/`

> **Ce qui répare un invariant sans gate le laisse redériver.** C'est la
> règle 8 de `CLAUDE.md`, et elle est mesurée : les audits de ce dépôt
> re-découvraient les mêmes dérives, audit après audit. Ce fichier dit
> **comment** une gate se construit pour que ça n'arrive pas.

145 gates au 2026-08-19. Elles pèsent les deux tiers du sous-ensemble
rapide et c'est voulu : elles remplacent la relecture manuelle qu'un
humain ne refait pas deux fois.

---

## Les quatre gardiennes de gates

Une gate qui garde le code peut elle-même être fausse. Quatre gates
gardent les gates, chacune fermant une pathologie mesurée :

| pathologie | ce qui la garde |
|---|---|
| la population balayée est **vide** | `test_prohibition_gates_declare_a_floor` |
| un **fichier illisible** sort du balayage en silence | `test_no_gate_swallows_a_file` |
| un **composant non construit** en sort de même | `test_no_gate_swallows_a_component` |
| le **détecteur ne mord plus** (regex aveugle) | `test_a_prohibition_gate_is_mutation_tested` |

Les quatre sont vertes et leurs trois dettes sont à **zéro** depuis le
2026-08-19. Une gate neuve doit donc satisfaire les quatre du premier
coup — ce qui prend dix lignes quand on sait lesquelles.

---

## Le squelette d'une gate d'interdiction

Une **interdiction** balaie une population et affirme « zéro
contrevenant ». C'est la forme la plus courante ici, et la plus
piégeuse : elle passe **exactement aussi bien** sur une population vide.

```python
from tests.consistency._discovery import (
    COMPONENTS_DIR, PACKAGE_FLOOR, parsed_sources,
)

_OFFENDING = re.compile(r"…")          # le détecteur


def offenders() -> list[str]:           # ← extrait, pour pouvoir le MUTER
    return [
        f"{s.path.name}:{node.lineno}"
        for s in parsed_sources(COMPONENTS_DIR, floor=_COMPONENTS_FLOOR)
        for node in ast.walk(s.tree)
        if …
    ]


def test_the_sweep_is_not_vacuous() -> None:      # ① le plancher
    assert len(parsed_sources(COMPONENTS_DIR, floor=_COMPONENTS_FLOOR)) >= 200


def test_no_component_does_the_bad_thing() -> None:   # ② l'interdiction
    assert not offenders(), "…"


def test_the_detector_still_bites() -> None:      # ③ la mutation
    assert _OFFENDING.search("<le motif exact interdit>")
    assert not _OFFENDING.search("<son jumeau LICITE>")
```

Trois points comptent plus que le reste :

1. **le détecteur est une fonction extraite**, pas du code inline dans le
   test — sinon il n'est pas mutable ;
2. **le plancher lit la découverte de CETTE gate**, pas une source
   fraîche. Un plancher qui recompte depuis son propre `rglob` reste vert
   quand on débranche le balayage (memory
   `gate_floors_must_read_the_gate_source`) ;
3. **la mutation a deux versants.** Celui qui mord confirme ce qu'on
   croyait ; celui qui épargne trouve ce qu'on ne cherchait pas — les
   deux faux positifs latents du 2026-08-19 sont venus du second.

---

## Lire la source : jamais à la main

`_discovery` porte les lecteurs partagés. Ils lisent en `utf-8-sig` et
**lèvent** sur un fichier illisible ; un `except: continue` autour d'une
lecture est refusé par `test_no_gate_swallows_a_file`.

| tu veux… | appelle |
|---|---|
| tous les `.py` d'une racine, lus **et** parsés | `parsed_sources(root, floor=…)` |
| le texte/AST d'un chemin que tu tiens déjà | `source_of(path)` |
| les `theme.py` de composant | `theme_sources()` |
| la surface publique | `public_component_classes()` / `ui_name_of(cls)` |
| le HTML rendu d'un composant | `rendered_html_of(cls)` |
| le même, avec une **sonde** sur une prop | `rendered_html_of(cls, prop="size", value="lg")` |
| le mot obligatoire d'un composant (tu veux l'instance) | `bare_kwargs(cls)` |

⚠️ **Ne redevine pas comment construire un composant.** Quatre d'entre
eux exigent un mot obligatoire (`alt`, `title`, `content`, `text`) et
deux exigent un contexte parent. Cinq gates les redevinaient chacune à
leur façon, et les rataient : mesuré le 2026-08-19, **32 couples
(classe, prop) sortaient du balayage** d'une seule d'entre elles — parce
qu'elle appelait le bâtisseur partagé avec la mauvaise signature.

---

## Rattraper est permis, se taire ne l'est pas

Une gate qui construit avec une **sonde** (`icon=`, `size=`, un
`Callable`) rencontre des refus **définitionnels** : le composant ne
prend pas cette prop, point. Le `except` est alors légitime.

Ce qui ne l'est pas, c'est de ne pas regarder ce qu'il rattrape. Le
fichier doit porter un `test_…abstentions_are_declared` qui compare les
abstentions mesurées à une table **nommée**, et refuse les deux écarts :

- un composant qui tombe dans le `except` sans être déclaré ;
- une entrée qui n'y tombe plus (sinon la table pourrit).

**Pas un plafond chiffré.** « Pas plus de deux » laisse passer « un qui
sort, un qui rentre » ; une table dit LESQUELS.

Au-delà d'une dizaine d'entrées, la table va dans un `.txt` à côté de la
gate — comme `_not_graded.txt` (127) et `_not_a_text_slot.txt` (35) —
avec sa raison en tête. Le `.py` garde le raisonnement, pas la dette.

---

## Prouver qu'une gate mord : trois voies

`test_a_prohibition_gate_is_mutation_tested` en accepte trois, et
**vérifie les trois** :

1. **Une entrée dans `_mutation_audit.MUTATIONS`** — pour ce qui se mute
   dans un vrai fichier du framework (`py -m tests.consistency._mutation_audit`).
2. **Un test dans la gate** — nommé avec l'un des marqueurs reconnus
   (`still_bites`, `mutation`, `detector`, `catches`, `would_`,
   `fabriqu`…). C'est souvent le plus honnête : la preuve vit à côté de
   ce qu'elle prouve et tourne à chaque `pytest`.
3. **`MUTATION_PROOF = "nom_du_test"`** — quand la preuve existe déjà
   sous un autre nom. Le pointeur est vérifié : le test doit exister.

Et une sortie, **fermée à clé** :

4. **`MUTATION_NOT_APPLICABLE = "raison"`** — pour une gate sans
   détecteur (elle compare des ensembles, ou exécute un comportement).
   **Refusée** si le fichier contient un `re.compile(` ou un
   `ast.walk(` : il a bel et bien un détecteur.

### Le contrôle POSITIF compte autant qu'une violation fabriquée

C'est la découverte du remboursement de la dette : beaucoup de gates
prouvent leur détecteur en vérifiant qu'il **reconnaît encore un cas
réel** — « le motif est là où il DOIT être » (`test_the_sweep_reads_something`,
`test_the_gate_finds_scope_consumers`) — ou par un contre-cas (« un
attribut du dialecte mort doit LEVER »). Un détecteur qui reconnaît un
cas réel n'est pas aveugle. Sur les 113 gates sans preuve du matin,
**~40 en avaient déjà une** sous un nom que personne n'avait désigné.

### Une gate qui cherche un NOM peut être vide sans le dire

Mesuré le 2026-08-24, sur une gate écrite le jour même
(`test_framework_words_go_through_the_table`). Son détecteur cherchait
les appels à `_TextNode` — le nom que **deux** modules de composants
utilisent. Les **vingt autres** importent `Text as TextNode`. La branche
trouvait donc zéro contrevenant, ce qui se lit exactement comme « tout
est propre ».

Le plancher ne l'a pas vue, et il avait raison de ne pas la voir : il
comptait 180 fichiers balayés, et 180 fichiers l'étaient. C'est la
BRANCHE qui était vide, pas le balayage. Un plancher borne la population
lue ; il ne dit rien de ce que le détecteur y reconnaît.

**Le remède se formule à l'envers de l'interdiction.** Au lieu de
« zéro contrevenant », compter les **occurrences de la forme
surveillée** et exiger qu'il y en ait :

```python
def test_both_spellings_of_the_text_node_are_watched() -> None:
    seen = dict.fromkeys(_TEXT_NODES, 0)
    ...                                   # compte les APPELS, pas les fautes
    assert not [k for k, n in seen.items() if n == 0]
```

Toute gate qui code en dur un **identifiant** — nom de fonction, de
décorateur, d'attribut, de kwarg — en a besoin. Un identifiant se
renomme, s'aliase, se déplace, et la gate devient muette sans rougir.

Deux corollaires du même jour, sur le même détecteur :

- **la FORME compte autant que le nom.** Il ne connaissait que le
  littéral nu ; `"Donut" if donut else "Pie"` et `s.name or "Series"`
  lui échappaient, et cinq phrases visibles passaient par là — dont une
  écrite en français dans un framework anglais.
- **une gate doit écrire ce qu'elle ne voit pas.** Une valeur qui
  traverse le paramètre d'une fonction d'aide demanderait un vrai flot
  de données. Le détecteur remonte d'UN cran (une constante de module
  passée par son nom) et sa docstring nomme la limite — sans quoi le
  lecteur suivant croira la promesse plutôt que la portée.

---

## Ce qu'une gate ne doit PAS faire

- **Recopier une population dans un plancher.** `assert len(x) == 27`
  rougit au premier composant retiré, pour rien. Un plancher borne, il
  ne fige pas — sauf quand la population EST le sujet (une allowlist).
- **Élargir une allowlist pour se taire.** Le dépôt en a vu pourrir
  plusieurs ; c'est pourquoi chaque table ici refuse aussi les entrées
  **périmées**.
- **Mesurer une intention.** Une gate juge une forme mécanique. « Ce
  slot est-il joli » n'est pas gatable — ça va dans `tests/probes/`,
  au navigateur.
- **Muter le détecteur lui-même.** Changer la regex fait rougir la gate
  sans rien prouver de la dérive réelle.

---

## Mutation-tester à la main

```bash
py -m tests.consistency._mutation_audit          # tout
py -m tests.consistency._mutation_audit slot     # filtre par substring
```

⚠️ Le harnais **refuse de tourner si l'arbre a des modifications non
commitées**, et défait ses mutations par restauration du contenu
sauvegardé — jamais par `git checkout`, qui détruirait du travail non
commité (erreur faite cinq fois sur ce dépôt).
