"""Gate : une dépendance MESURÉE est déclarée des deux côtés.

Le problème que cette gate existe pour empêcher n'a pas de symptôme au
rendu : il n'apparaît qu'à l'exécution, une fois sur deux.

Un scope runtime qui lit le DOM (``scrollWidth``,
``getBoundingClientRect``) produit une valeur qui **n'est pas un
signal**. Un ``bz-attr:disabled="_atEnd()"`` bâti dessus s'évalue donc
UNE fois, au scan, avec la mise en page qui existe à cet instant — et ne
se relit plus jamais. Le carousel l'a payé : hydraté avant que la
feuille de style s'applique, il mesurait une piste pas encore ``flex``,
concluait qu'il n'y avait nulle part où aller, désactivait ses DEUX
flèches, et ``disabled:opacity-0`` les effaçait. Aucune flèche à la
première visite, toutes au refresh — parce que le refresh rejouait la
course entre le compilateur CSS et le scan.

Le remède est une convention, et c'est elle qu'on gate ici :

    void this._geom;        // dans une méthode du scope JS
    "_geom: 0,"             // déclaré dans le bz-data émis par Python

``void this.X`` est le marqueur explicite d'une lecture faite POUR SA
DÉPENDANCE (elle ne sert à rien d'autre — sans le marqueur, elle se lit
comme du code mort et se supprime au premier nettoyage). Le champ doit
exister dans le ``bz-data`` AVANT le premier passage de l'effet : posé à
la volée côté JS, il n'a aucun abonné et rien ne se relance jamais
(même contrainte que ``still`` pour l'autoplay).

Les deux moitiés vivent dans deux langages qui ne s'importent pas. Cette
gate est le seul lien qui les tient ensemble : supprimer le ``void``,
renommer le champ, ou retirer sa déclaration Python casse ici — et pas
en production, six mois plus tard, sur une machine dont le cache est
froid.
"""

from __future__ import annotations

import re

import pytest

from tests.consistency._discovery import (
    RUNTIME_SRC_DIR,
    assert_runtime_sweep_is_not_vacuous,
    bz_data_of,
    public_component_classes,
    runtime_slabs,
)

#: ``void this.<champ>;`` — la lecture-pour-dépendance.
_VOID_READ = re.compile(r"void\s+this\.(\w+)\s*;")
#: ``$bz.carousel = {`` — le namespace qu'un module de scope publie.
_NAMESPACE = re.compile(r"^\s*\$bz\.(\w+)\s*=\s*\{", re.MULTILINE)


def _measured_deps() -> list[tuple[str, str, str]]:
    """``(module, namespace, champ)`` pour chaque ``void this.X`` du runtime.

    Découvert par balayage : un nouveau scope qui adopte la convention
    est couvert sans toucher à ce fichier.

    Le namespace est celui qui PRÉCÈDE le plus près, pas le premier du
    fichier. Un module en publie couramment plusieurs — ``16_accordion.js``
    en porte cinq (``accordion``, ``tree``, ``tabs``, ``stepper``,
    ``tooltip``), ``06_helpers.js`` trois — et prendre le premier
    attribuerait la dépendance à ``accordion``, dont AUCUN composant
    n'émet le scope. La gate accuserait alors un « scope orphelin » là où
    le champ est correctement déclaré chez les quatre vrais porteurs.

    Le namespace vaut ``""`` quand le module n'en publie aucun avant le
    marqueur ; c'est un cas d'erreur, mais il est signalé par un TEST et
    non par un ``assert`` ici — cette fonction court dans le décorateur
    ``parametrize``, donc y lever donnerait une ERREUR DE COLLECTE qui
    emporterait aussi le plancher de non-vacuité.
    """
    out: list[tuple[str, str, str]] = []
    for path in runtime_slabs():
        source = path.read_text(encoding="utf-8")
        opened = [(m.start(), m.group(1)) for m in _NAMESPACE.finditer(source)]
        for match in _VOID_READ.finditer(source):
            before = [name for pos, name in opened if pos < match.start()]
            out.append((path.name, before[-1] if before else "", match.group(1)))
    return sorted(set(out))


@pytest.fixture(scope="module")
def bz_data_by_component() -> dict[str, str]:
    return {
        cls.__name__: bz_data_of(cls) or "" for cls in public_component_classes()
    }


def test_every_marker_sits_under_a_published_namespace() -> None:
    """Un ``void this.X`` hors de tout ``$bz.<nom> = {`` n'est rattachable
    à aucun composant — donc invérifiable, donc à signaler ici plutôt
    qu'à laisser passer en silence."""
    orphans = [(mod, field) for mod, ns, field in _measured_deps() if not ns]
    assert not orphans, (
        f"marqueurs de dépendance mesurée sans namespace publié : {orphans}. "
        f"Aucun composant ne peut être tenu de déclarer le champ, donc rien "
        f"n'est vérifié pour eux."
    )


@pytest.mark.parametrize(("module", "namespace", "field"), _measured_deps())
def test_measured_dep_is_declared_in_the_scope_literal(
    module: str, namespace: str, field: str, bz_data_by_component: dict[str, str]
) -> None:
    if not namespace:
        pytest.skip("orphelin — couvert par test_every_marker_sits_under_a_...")
    marker = f"$bz.{namespace}.scope"
    users = {
        name: data for name, data in bz_data_by_component.items() if marker in data
    }
    assert users, (
        f"{module} lit ``void this.{field}`` pour sa dépendance, mais aucun "
        f"composant n'émet {marker} — le scope est orphelin, donc la "
        f"déclaration ne peut être vérifiée nulle part."
    )
    missing = [name for name, data in users.items() if f"{field}:" not in data]
    assert not missing, (
        f"{module} lit ``void this.{field}`` POUR SA DÉPENDANCE, mais "
        f"{', '.join(missing)} ne déclare pas ``{field}:`` dans son bz-data. "
        f"Un champ absent du littéral n'existe pas au premier passage de "
        f"l'effet : celui-ci ne s'y abonne jamais, et la valeur mesurée "
        f"reste figée sur la mise en page du scan. C'est le bug « aucune "
        f"flèche à la première visite, toutes au refresh »."
    )


def test_the_swept_population_is_not_vacuous() -> None:
    """Plancher de non-vacuité — deux étages, parce qu'il y a deux façons
    de devenir aveugle ici.

    Le glob peut cesser de trouver les modules (``_src/`` déplacé), et le
    marqueur peut cesser d'être trouvé DANS les modules (``void this.X``
    renommé). Les deux rendraient la paramétrisation vide, donc la gate
    verte sur zéro cas — la pathologie que ce dépôt a déjà payée trois
    fois.
    """
    assert_runtime_sweep_is_not_vacuous()
    assert _measured_deps(), (
        f"aucun ``void this.X;`` trouvé dans les modules de "
        f"{RUNTIME_SRC_DIR} — le marqueur de dépendance mesurée a été "
        f"renommé ou supprimé. Une gate sans cas est verte pour rien."
    )


def test_the_detector_still_bites() -> None:
    """Mutation : la convention ``void this.x;`` est encore reconnue.

    Une mesure du DOM (``scrollWidth``) n'est PAS un signal : un
    ``bz-attr`` bâti dessus s'évalue une fois au scan et se fige. La
    convention ``void this._geom`` déclare la dépendance ; si la regex
    cessait de la voir, la gate ne garderait plus que l'orthographe.
    """
    assert _VOID_READ.search("void this._geom;").group(1) == "_geom"
    assert not _VOID_READ.search("this._geom;"), "faux positif"
    assert _NAMESPACE.search("$bz.helpers = {").group(1) == "helpers"
    assert not _NAMESPACE.search("const x = $bz.helpers = {"), "faux positif"
