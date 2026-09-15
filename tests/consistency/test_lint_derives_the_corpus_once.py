"""Une règle qui lit le corpus le lit UNE fois, pas une fois par module.

Ce que cette gate ferme
-----------------------

``bretzel.lint.run`` expose le corpus du passage pour les rares règles
qui ne peuvent pas juger sur un seul fichier (`valeur-hors-table` doit
savoir ce qu'un ``Theme(components=…)`` déclare *ailleurs*). La
dérivation qui en découle est la MÊME pour les N modules du passage —
mais rien n'oblige une règle à s'en souvenir, et une règle qui l'oublie
rend le passage **quadratique** sans qu'aucun test ne rougisse : le
verdict est identique, seul le temps change.

Mesuré le 2026-08-27, avant le correctif : `valeur-hors-table`
reparcourait l'AST des 322 fichiers d'``examples/`` pour chacun de ces
322 fichiers — **56 s**, payées deux fois dans un ``pytest`` nu (la
règle seule, puis la baseline), soit ~110 s des 230 s du run rapide.
Après : 1,6 s et 4,1 s.

Pourquoi compter les APPELS et pas le temps
--------------------------------------------

Un seuil en secondes sur cette machine ne veut rien dire — elle dérive
d'un facteur 2 à 3 entre deux exécutions (memory
``inprocess_ab_or_no_measurement``). Le nombre d'appels à
``_declared_in``, lui, est déterministe : linéaire ou quadratique se
distingue sans chronomètre.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from bretzel.lint import corpus as lint_corpus
from bretzel.lint import run
from bretzel.lint.rules import variant

REPO_ROOT = Path(__file__).resolve().parents[2]
EXAMPLES = REPO_ROOT / "examples"

#: Le corpus de la MUTATION — assez grand pour que quadratique se voie,
#: assez petit pour que le versant fautif reste payable (24 fichiers
#: contre 277 : 576 parcours d'AST au lieu de plus de 60 000).
#: ⚠️ **Troisième adresse en deux semaines** : ``examples/flat`` jusqu'à
#: l'élagage du 2026-09-07, puis ``mad`` jusqu'à celui du 2026-09-10.
#: Un corpus de mutation ancré sur une app de DÉMO est repris à chaque
#: fois qu'une démo tombe — et une démo est là pour pouvoir tomber.
#: `crm` est l'instrument d'usage réel, pas une démo : c'est la seule
#: adresse d'`examples/` qui ne relève pas de la règle d'élagage.
SMALL = REPO_ROOT / "examples" / "crm"


def declared_in_calls(
    paths: tuple[Path, ...], *, monkeypatch: pytest.MonkeyPatch
) -> tuple[int, int]:
    """``(appels à _declared_in, fichiers balayés)`` pour un passage.

    Extrait pour être MUTABLE : le versant fautif de la gate rejoue le
    même comptage avec la mémoire du corpus débranchée.
    """
    calls = [0]
    real = variant._declared_in

    def counting(tree):  # type: ignore[no-untyped-def]
        calls[0] += 1
        return real(tree)

    monkeypatch.setattr(variant, "_declared_in", counting)
    report = run(list(paths), rules=(variant.RULE,))
    return calls[0], report.files_scanned


@pytest.fixture(scope="module")
def measured(request: pytest.FixtureRequest) -> tuple[int, int]:
    """Un SEUL passage sur ``examples/`` pour les deux affirmations.

    Le plancher et l'interdiction lisent la même mesure — c'est ce que
    demande ``gate_floors_must_read_the_gate_source``, et ça évite de
    payer deux fois le balayage dans le sous-ensemble rapide.
    """
    patch = pytest.MonkeyPatch()
    request.addfinalizer(patch.undo)
    return declared_in_calls((EXAMPLES,), monkeypatch=patch)


def test_the_corpus_is_not_trivial(measured: tuple[int, int]) -> None:
    """Le plancher — et il lit la découverte de CETTE gate.

    Recompter les fichiers avec un ``rglob`` frais laisserait la gate
    verte si ``run`` cessait de balayer quoi que ce soit (memory
    ``gate_floors_must_read_the_gate_source``).
    """
    _, scanned = measured
    assert scanned >= 200, (
        f"`examples/` n'a été balayé que sur {scanned} fichiers — la gate "
        "ne mesure plus rien de significatif."
    )


def test_the_union_is_derived_once_not_once_per_module(
    measured: tuple[int, int],
) -> None:
    """L'interdiction : le corpus est parcouru une fois, pas N fois.

    La borne est ``scanned + 1`` et non ``scanned`` : la dérivation
    parcourt les ``scanned`` arbres du corpus, et le ``+ 1`` laisse la
    place à un module hors corpus (le cas de repli documenté dans
    ``_declared_everywhere``) sans rien concéder sur l'ordre de
    grandeur.
    """
    calls, scanned = measured
    assert calls <= scanned + 1, (
        f"{calls} parcours d'AST pour {scanned} fichiers — la règle "
        f"re-dérive le corpus par module. Attendu : au plus {scanned + 1}. "
        "Passer par `bretzel.lint.corpus.derived`."
    )


def test_the_detector_still_bites_without_the_memo(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Le versant qui MORD : la mémoire débranchée, le compte explose.

    Sans ça, la gate serait vraie pour une raison qu'on n'a pas
    vérifiée — un corpus vide la rendrait verte tout autant. Le versant
    LICITE est le test suivant : hors passage, la règle doit continuer
    à voir ce que son propre module déclare.
    """
    monkeypatch.setattr(lint_corpus, "derived", lambda key, build: build())
    monkeypatch.setattr(variant, "derived", lambda key, build: build())
    calls, scanned = declared_in_calls((SMALL,), monkeypatch=monkeypatch)
    assert scanned >= 10, f"corpus de mutation trop maigre : {scanned} fichiers"
    assert calls > scanned + 1, (
        "la mémoire débranchée n'a PAS rendu le passage quadratique — "
        f"{calls} appels pour {scanned} fichiers. La gate ne prouve donc "
        "rien : `derived` n'est plus le point de passage."
    )


def test_a_rule_called_outside_run_still_sees_its_own_module() -> None:
    """Le versant LICITE : hors passage, la règle ne perd rien.

    C'est là que la mémoire pourrait casser sans bruit — un cache
    global rendrait la dérivation d'un AUTRE corpus, ou un
    ``ContextVar`` mal réinitialisé la rendrait vide. Une règle exercée
    seule (un test unitaire) doit continuer à lire le thème que son
    propre fichier déclare.
    """
    import ast

    source = (
        "from bretzel import ui, Theme\n"
        'THEME = Theme(components={"button": {"variants": {"maison": "bg-x"}}})\n'
        'ui.button("ok", variant="maison")\n'
    )
    module = lint_corpus.Module(
        path=Path("fictif.py"), tree=ast.parse(source), source=source
    )
    assert lint_corpus.current() == (), "ce test doit tourner hors `run`"
    declared = variant._declared_everywhere(module)
    assert "maison" in declared.get("button", {}).get("variants", set()), (
        "hors `run`, la règle ne voit plus la variante déclarée par son "
        "propre module — elle condamnerait la forme recommandée."
    )
