# `tests/probes/` — probes Playwright manuels + benchs composants

Le **2e étage** de la vérif visuelle, à côté de `tests/audit/`. Ici,
**un probe = un script écrit à la main** qui pilote un vrai Chromium et
**mesure la géométrie** (centrage, tab order, double scrollbar, position
absolue, clipping…) puis screenshote. C'est l'outil direct de la
discipline #3 du `CLAUDE.md` (« Playwright probe OBLIGATOIRE »).

## Les deux étages de vérif — ne pas confondre

| Dossier | Quoi | Quand |
|---|---|---|
| `tests/audit/` | étage **déterministe** (mesures, le « plancher » pas cher) | régression auto |
| **`tests/probes/`** | **probes écrits à la main**, ad-hoc, un bug/composant à la fois | dev d'un composant, repro d'un piège |

`audit/` est un **pipeline** qui génère ses cas. `probes/` est **écrit à
la main et opportuniste** : on en écrit un quand on traque un bug visuel
précis ou qu'on valide un fix avant de shipper.

**« Manuel » ne veut plus dire « jamais lancé » depuis le 2026-08-19** :

```bash
pytest -m probes        # les 53, un sous-process chacun, ~7 min
```

Le marqueur vit dans `test_probes.py`, qui ne fait qu'une chose —
transformer le code de sortie de chaque script en test. Il est
désélectionné du run rapide. Avant lui, `probes/` n'était collecté par
personne : les lancer tous pour la première fois a rendu **17 rouges sur
52**, dont trois probes **verts à tort** qui affirmaient sans avoir
chargé le runtime.

⚠️ Il y avait un 3e étage, la suite *visual* — un modèle vision qui jugeait
un screenshot. **Supprimée le 2026-08-16** (16 235 lignes, peu rentable ;
`git log --diff-filter=D` la retrouve).
`probes/` est donc désormais le SEUL étage qui regarde vraiment le rendu :
ce que tu n'écris pas ici, personne ne le voit.

⚠️ **Strictement séquentiel** : plusieurs probes partagent un port
(`:8974` en sert trois). `pytest-xdist` est installé depuis le
2026-08-27, et `test_probes.py` les épingle donc tous sur un même worker
par un `xdist_group`. (Cette ligne a dit « pas installé » après coup.)
Un probe porté sur `bretzel.probe` n'a pas ce problème : le harnais prend
un port LIBRE.

## Deux formes — et la neuve est le défaut

**Un probe d'APP s'écrit sur `bretzel.probe`.** Le harnais sert l'app,
ouvre les fenêtres — des CONTEXTES, donc des sessions distinctes —,
attend l'ÉTAT, compte les requêtes d'un geste, lit l'état serveur,
balaie à la sortie et rend le verdict. Il n'y a ni port, ni `check` à
redéfinir, ni code de sortie à câbler.

```python
from bretzel.probe import probe

with probe("examples.messagerie.main:app") as p:
    (a,) = p.windows
    a.goto("/")
    p.check("l'état vide est affiché", a.has("text=Aucune conversation"))
```

Référence : **`probe_messagerie.py`**, le premier porté (2026-09-11).
Il ne fait pas moins de lignes — 545 avant, 549 après — mais il passe de
**34 constats à 42** : erreurs JS, requêtes en échec et avertissements de
console assertés, une seconde taille de fenêtre, les deux thèmes
capturés, la tabulation relue. Aucun de ces onze n'est écrit dans le
fichier.

Ce qui ne rentre pas dans le harnais, c'est le harnais qu'il faut
étendre — pas le contourner. `test_probe_boilerplate_only_shrinks.py`
tient le compte : les quatre marques du harnais réécrit à la main ne
peuvent que descendre.

### La forme historique — un probe de COMPOSANT, toujours par paire

- `bench_X.py` → une mini-app Bretzel qui rend le composant isolé sur un
  port dédié (ex. `:8977`). C'est la *fixture sous test*.
- `probe_X.py` → lance le bench en sous-process, attend `bz-ready`, mesure
  via `page.evaluate(...)`, screenshote, renvoie `0` (vert) / `1` (rouge).

⚠️ **Il n'y a pas de troisième forme.** `pytest -m probes` collecte
`probe_*.py`, et rien d'autre : un probe rangé ailleurs — dans le bench
derrière un `--probe`, dans un `debug_*.py` — n'est lancé par personne, et
ce dossier a payé les deux :

- `bench_sidebar_collapse.py --probe` a vécu ainsi jusqu'au 2026-08-26. En
  le sortant, on a découvert qu'il **plantait** sur un `TimeoutError` avant
  d'atteindre le moindre verdict ;
- `probe_fdbg.py` s'appelait bien `probe_*` mais n'avait aucun check et
  aucun bench jumeau : il tournait à chaque run pour n'affirmer rien.
  Supprimé.

Deux gates tiennent maintenant ces deux bords :
`tests/consistency/test_a_probe_can_actually_fail.py` (un probe DOIT
pouvoir sortir non-nul) et
`tests/consistency/test_every_bench_page_still_renders.py` (toutes les
pages de tous les bancs rendent, en 4 s dans la suite rapide).

```bash
py tests/probes/probe_switch.py      # spawn bench_switch.py :8977, mesure, screenshot
```

Le probe trouve la racine du repo via `HERE.parent.parent` (← `tests/probes/`)
et lance le bench avec `cwd=` cette racine, pour que `from bretzel import …`
et `import examples.playground.main` résolvent.

## Un probe ne doit rien affirmer sur AUJOURD'HUI

Trouvé le 2026-09-05, un samedi : `probe_ecole` exigeait qu'un jour « à
venir » apparaisse dans la semaine courante du cahier de texte. L'app
avait raison — un jour futur s'étiquette « à venir », un jour passé « à
consigner » — mais un samedi il ne reste plus de jour futur avec cours.
Le probe passait donc du lundi au jeudi et tombait le vendredi et le
week-end, sans que rien n'ait changé dans le code.

C'est la pire forme de pourrissement : il ne dérive pas une fois, il
**revient**, et le rouge accuse le dernier commit venu.

La règle : viser une fenêtre que la date ne peut pas vider. Ici, le
probe décale d'une semaine — toute la semaine suivante est future quel
que soit le jour — puis revient, ce qui prouve en passant que le
décalage en était un. Sauter le check quand la date ne s'y prête pas
aurait donné une assertion qui se tait au lieu d'une qui ment : c'est
moins bruyant, et ça ne vérifie plus rien.

---

## Repros canoniques

Une partie de ces fichiers sont **load-bearing** : `.claude/bretzel/traps.md`
(+ quelques fichiers source du framework) les citent comme « voici comment
reproduire ce piège ». Ne pas les supprimer sans corriger ces références —
ils documentent un bug résolu et sa non-régression.

## Artefacts

Les `*.png` (screenshots) et `_probe_*.html` (dumps) sont **gitignored** :
régénérés à chaque run, jamais versionnés. Seuls les `*.py` sont suivis.
