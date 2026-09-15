"""Gate : la population que `ruff` voit dans `bretzel/` est FIGÉE.

Le problème qu'elle ferme
-------------------------
Ruff est **configuré** dans `pyproject.toml` — huit familles de règles,
deux `ignore` motivés, une liste de confusables — et **déclaré** dans
l'extra `dev`, à côté de pytest. Il n'était lancé par personne : ni CI, ni
hook, ni test. Il remontait 153 constats sur `bretzel/` au 2026-09-07, ce
qui est exactement le régime où plus personne ne le lance, et où les
constats neufs se noient dans les anciens.

Le coût est mesuré, pas théorique. Le même matin, cette sortie contenait :

- **24 `F811`** — douze clauses d'import liant deux fois `theme_context`.
  Inerte à l'exécution, invisible en revue, douze fois la même faute :
  un geste automatisé que rien ne rattrapait ;
- **1 `F821`** — `color_shapes.py` appelait un nom défini nulle part,
  inoffensif seulement parce que la fonction qui l'entourait était morte.
  Personne ne l'avait vu en trois semaines ; c'est la base qui l'a mis
  sous les yeux, et il a été supprimé le jour même.

C'est la deuxième fois que ce dépôt tombe dessus. La règle « uniquement
depuis `__init__`, Ruff `tidy-imports` enforce » a été retirée le
2026-07-04 pour être « aspirationnelle et non-outillée », et remplacée
par `import-linter`, qui a un fichier de config **et** une commande. Un
linter que rien n'exécute décrit une intention, pas un invariant.

La forme : la même que `test_lint_baseline_on_examples`
--------------------------------------------------------
On ne peut pas exiger zéro — 35 constats subsistent, et plusieurs ne
valent pas de l'être (`N806` sur des
constantes locales délibérément majuscules, `SIM108` sur des branches
dont chaque côté porte son commentaire). On gèle donc le couple
**(fichier, règle) → nombre**, dans `_ruff_baseline.txt`, et l'égalité est
STRICTE dans les deux sens : une occurrence neuve rougit, une occurrence
réparée rougit aussi tant que sa ligne n'est pas retirée. Une base qui ne
refuse que la croissance pourrit — c'est le défaut qu'elle corrige.

La table vit dans un `.txt` plutôt que dans ce module parce qu'elle passe
la dizaine d'entrées (cf. `.claude/bretzel/gates.md`, « le `.py` garde le
raisonnement, pas la dette »). Chaque bloc de règle y porte sa raison ;
une entrée sans raison serait juste une gate qu'on a fait taire.

Ce que cette gate ne fait PAS
------------------------------
Elle ne couvre que `bretzel/`. `tests/` en porte ~378, `examples/` est
exclu de ruff par `extend-exclude` (le lint d'`examples/` est celui de
`bretzel.lint`, gelé par `test_lint_baseline_on_examples`). Et elle ne
juge pas la sévérité : `F821` et `W291` pèsent pareil ici, c'est le
fichier de base qui les distingue en prose.
"""

from __future__ import annotations

import collections
import functools
import json
import pathlib
import subprocess
import sys

from tests.consistency._discovery import PACKAGE_DIR, PACKAGE_FLOOR, REPO_ROOT

#: Pas de détecteur à rendre aveugle — cf.
#: ``test_a_prohibition_gate_is_mutation_tested``. Le détecteur est ruff
#: lui-même ; ce module gèle la population qu'il voit.
MUTATION_NOT_APPLICABLE = (
    "gèle un COUPLE (fichier, règle) → nombre mesuré par `ruff` ; le "
    "détecteur est ruff, pas du code de ce dépôt, et le plancher lit sa "
    "propre découverte (`ruff check --show-files`)"
)

_BASELINE_FILE = pathlib.Path(__file__).with_name("_ruff_baseline.txt")
#: Ce qu'on donne à ruff, en relatif : il résout sa config depuis les
#: ancêtres du fichier lu, donc `cwd=REPO_ROOT` + un chemin relatif
#: garantissent que c'est le `[tool.ruff]` du dépôt qui gagne, quel que
#: soit le répertoire d'où pytest est lancé.
_TARGET = f"{PACKAGE_DIR.name}/"


def _ruff(*args: str) -> subprocess.CompletedProcess[str]:
    """Lance ruff, et **lève** s'il est absent ou casse.

    Pas de `pytest.importorskip` : un skip est la façon la moins chère de
    rendre cette gate muette, et elle existe précisément parce que
    personne ne lançait ruff. Il est déclaré dans l'extra `dev` à côté de
    pytest — s'il manque, l'environnement est faux, pas la gate.
    """
    proc = subprocess.run(
        [sys.executable, "-m", "ruff", *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        cwd=REPO_ROOT,
    )
    # 1 = « ruff a tourné et a trouvé des constats », le cas NORMAL ici.
    # Un interpréteur SANS ruff rend AUSSI 1 (« No module named ruff »),
    # et confondre les deux donnerait un `json.loads("")` trois lignes
    # plus loin, dont le message ne nomme pas ce qui manque.
    absent = "No module named" in proc.stderr
    assert proc.returncode in (0, 1) and not absent, (
        f"`ruff {' '.join(args)}` a rendu {proc.returncode} — ruff est "
        f"déclaré dans l'extra `dev` du `pyproject.toml`, à côté de "
        f"pytest. Installe-le plutôt que de sauter cette gate : elle "
        f"existe parce que personne ne le lançait.\n{proc.stderr.strip()}"
    )
    return proc


@functools.lru_cache(maxsize=1)
def ruff_version() -> str:
    return _ruff("--version").stdout.strip()


@functools.lru_cache(maxsize=1)
def baseline_text() -> str:
    """Le `.txt` lu UNE fois — la table et sa prose sortent d'ici.

    Deux lectures, c'est deux occasions de voir un fichier différent.
    """
    return _BASELINE_FILE.read_text(encoding="utf-8")


@functools.lru_cache(maxsize=1)
def scanned_files() -> tuple[str, ...]:
    """Ce que ruff DÉCOUVRE — sa propre liste, pas un `rglob` d'ici.

    Un plancher qui recompte depuis une source fraîche reste vert quand
    on débranche le balayage réel (memory
    `gate_floors_must_read_the_gate_source`). Ici la source du plancher
    EST celle de la mesure : si `extend-exclude` avalait `bretzel/`, les
    deux tomberaient à zéro ensemble.
    """
    out = _ruff("check", "--show-files", _TARGET).stdout
    return tuple(line for line in out.splitlines() if line.strip())


@functools.lru_cache(maxsize=1)
def measured() -> dict[tuple[str, str], int]:
    """``(chemin, règle) → nombre``, tel que ruff le voit aujourd'hui."""
    proc = _ruff("check", "--output-format=json", _TARGET)
    findings = json.loads(proc.stdout)
    return dict(
        collections.Counter(
            (
                pathlib.Path(f["filename"]).resolve().relative_to(REPO_ROOT).as_posix(),
                f["code"],
            )
            for f in findings
        )
    )


@functools.lru_cache(maxsize=1)
def baseline() -> dict[tuple[str, str], int]:
    """La table gelée. Une ligne malformée LÈVE — elle ne se saute pas."""
    entries: dict[tuple[str, str], int] = {}
    for number, line in enumerate(baseline_text().splitlines(), start=1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        parts = line.split("\t")
        assert len(parts) == 3, (
            f"{_BASELINE_FILE.name}:{number} — attendu "
            f"`nombre <TAB> règle <TAB> chemin`, lu : {line!r}"
        )
        count, rule, path = (p.strip() for p in parts)
        assert count.isdigit(), f"{_BASELINE_FILE.name}:{number} — {count!r} n'est pas un nombre"
        key = (path, rule)
        assert key not in entries, (
            f"{_BASELINE_FILE.name}:{number} — {path} [{rule}] est inscrit deux fois ; "
            f"la seconde ligne écraserait la première en silence."
        )
        entries[key] = int(count)
    return entries


def test_ruff_sees_the_whole_package() -> None:
    """Plancher, lu sur la découverte de ruff lui-même.

    Une base gelée à 35 affirme « la dette n'a pas bougé ». Sur un
    balayage vide, elle affirmerait la même chose en n'ayant rien lu — et
    ce serait le pire vert du répertoire, puisqu'elle est justement là
    parce que personne ne regardait.

    Le SEUIL vient de `_discovery`, comme pour les autres balayages de
    `bretzel/` : l'écrire ici en dupliquerait la valeur, et le jour d'une
    réorganisation une seule des deux bougerait. Le COMPTE, lui, reste
    celui de ruff. Mesuré le 2026-09-07 : 432 fichiers des deux côtés —
    ruff voit exactement la population que balaie
    `test_no_import_clause_repeats_a_name`.
    """
    assert len(scanned_files()) >= PACKAGE_FLOOR, (
        f"ruff ne voit plus que {len(scanned_files())} fichiers sous "
        f"{_TARGET} (>= {PACKAGE_FLOOR} attendus) — vérifie "
        f"`extend-exclude` avant de croire que la dette a fondu."
    )


def test_the_baseline_is_documented_rule_by_rule() -> None:
    """Chaque règle gelée porte sa raison, en prose, dans le `.txt`.

    C'est ce qui distingue une base d'un silence (`.claude/bretzel/gates.md`).
    Vérifié mécaniquement : le nom de la règle doit apparaître dans une
    ligne de COMMENTAIRE, pas seulement dans ses lignes de données — sans
    quoi on peut ajouter une règle entière sans jamais dire pourquoi.
    """
    commented = {
        word
        for line in baseline_text().splitlines()
        if line.lstrip().startswith("#")
        for word in line.replace(":", " ").split()
    }
    undocumented = sorted({rule for _, rule in baseline()} - commented)
    assert not undocumented, (
        f"ces règles sont gelées sans un mot d'explication : {undocumented}. "
        f"Écris ce qu'elles refusent et ce que la réparation coûte, sinon la "
        f"prochaine lecture ne saura pas si l'entrée est une dette ou une "
        f"décision."
    )


def test_the_population_has_not_moved() -> None:
    now, frozen = measured(), baseline()
    grown = {k: n for k, n in now.items() if frozen.get(k, 0) != n}
    paid = {k: n for k, n in frozen.items() if now.get(k, 0) != n}
    if not grown and not paid:
        return

    def fmt(entries: dict[tuple[str, str], int]) -> str:
        return "\n".join(
            f"      {path}  [{rule}] ×{n}" for (path, rule), n in sorted(entries.items())
        ) or "      (aucune)"

    raise AssertionError(
        f"la population vue par `ruff check {_TARGET}` a bougé "
        f"({sum(now.values())} constats mesurés, {sum(frozen.values())} gelés).\n"
        f"  mesuré aujourd'hui, absent ou différent dans la base :\n{fmt(grown)}\n"
        f"  inscrit dans la base, plus mesuré ainsi :\n{fmt(paid)}\n\n"
        f"  Occurrence NEUVE : lis le constat et corrige-le. L'inscrire ici "
        f"est le dernier recours, et il faut écrire pourquoi.\n"
        f"  Occurrence RÉPARÉE — ou fichier RENOMMÉ, ce qui se lit "
        f"pareil : retire sa ligne de `{_BASELINE_FILE.name}`, sinon la "
        f"base autorise plus que la réalité.\n"
        f"  Ni l'un ni l'autre : regarde la version de ruff. La base a été "
        f"mesurée avec 0.15.21, l'environnement porte « {ruff_version()} », "
        f"et le `pyproject.toml` ne contraint que `ruff>=0.8`."
    )
