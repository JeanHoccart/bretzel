"""Les sélecteurs de l'audit visuel nomment des classes qui EXISTENT.

Ce que cette gate ferme
-----------------------

``tests/audit/checklist.py`` ancre chaque composant par un sélecteur CSS
— ``span.inline-flex.rounded-md`` pour le badge, ``div.rounded-xl.
shadow-sm.overflow-hidden`` pour la carte. Ces sélecteurs sont des
COPIES de classes de thème, faites à la main, et rien ne les reliait à
leur source.

Le 2026-08-30, les rayons du framework sont passés à trois familles :
``rounded-md`` est devenu ``rounded-selector``, ``rounded-xl`` est devenu
``rounded-box``. Les deux sélecteurs ci-dessus ont cessé de désigner quoi
que ce soit **le jour même**, et personne ne l'a su pendant vingt-quatre
heures — parce que l'audit visuel demandait cinquante-deux minutes, donc
ne se lançait jamais.

Ce que ça coûte exactement
---------------------------

Un sélecteur qui ne matche plus rien ne rend pas l'audit muet en
silence : ``color_distinctness`` échoue franchement (« no swatches after
color heading for selector=… »). C'est la bonne moitié de la nouvelle.

La mauvaise est qu'on ne peut pas compter là-dessus. Un sélecteur qui
matche encore quelque chose — le MAUVAIS quelque chose — passerait, et
l'audit jugerait alors un autre élément que le composant. Cette gate
coupe la racine commune : une classe nommée dans un sélecteur doit être
une classe que le framework écrit vraiment.

Portée honnête
--------------

On ne vérifie que les jetons de CLASSE (ce qui suit un point). Les
balises, les pseudo-classes, les attributs et les classes marqueur
``.bz-*`` sont hors sujet : ``.bz-html`` est posée exprès par le
composant et n'apparaît dans aucune chaîne de slot. Le corpus de
référence est celui des chaînes de slot des thèmes, lu par le lecteur
PARTAGÉ de ``_discovery`` — le même que la gate du rayon.
"""

from __future__ import annotations

import re

import pytest

from tests.audit.checklist import COMPONENT_SPECS
from tests.consistency._discovery import theme_slot_strings, theme_sources

#: Preuve de morsure : le lecteur de sélecteurs, sur ses deux versants.
MUTATION_PROOF = "test_the_selector_reader_still_bites"

#: 75 specs le 2026-08-31. Le plancher ancre la DÉCOUVERTE : vider
#: ``COMPONENT_SPECS`` ou casser l'aplatissement rendrait la boucle
#: ci-dessous verte en n'ayant rien lu.
_SPEC_FLOOR = 60

#: Un jeton de classe dans un sélecteur CSS simple.
_CLASS_TOKEN = re.compile(r"\.([A-Za-z_][-\w]*)")

#: Les sélecteurs d'ATTRIBUT, retirés avant toute lecture de classe.
#:
#: Sans ce retrait, ``div[bz-data*='$bz.stepper.scope']`` livrait les
#: « classes » ``scope`` et ``stepper`` — six specs rougissaient sur des
#: sélecteurs parfaitement corrects. Trouvé par la gate elle-même à sa
#: première exécution, et c'est le versant que son contre-cas manquait :
#: il essayait ``input[name='x']``, qui ne porte aucun point.
_ATTR_BLOCK = re.compile(r"\[[^\]]*\]")

#: Les préfixes hors corpus, avec leur raison.
#:
#: - ``bz-`` : classes MARQUEUR, posées par le composant pour être
#:   trouvées, jamais écrites dans une chaîne de slot.
#: - ``htmx-`` : posées par HTMX au vol.
_OUT_OF_CORPUS = ("bz-", "htmx-")


def specs() -> list:
    return [s for group in COMPONENT_SPECS.values() for s in group]


def class_tokens(selector: str) -> set[str]:
    """Les classes nommées par un sélecteur, hors marqueurs."""
    return {
        tok for tok in _CLASS_TOKEN.findall(_ATTR_BLOCK.sub("", selector))
        if not tok.startswith(_OUT_OF_CORPUS)
    }


def emitted_classes() -> set[str]:
    """Toutes les classes que les thèmes du framework écrivent.

    Lues par ``theme_slot_strings``, le lecteur partagé — celui-là même
    dont la gate du rayon se sert. Redeviner comment lire une source est
    précisément ce que `gates.md` interdit.
    """
    out: set[str] = set()
    for src in theme_sources():
        for _slot, value in theme_slot_strings(src.text):
            out.update(value.split())
    return out


_SPECS = specs()
_EMITTED = emitted_classes()


def test_the_sweep_is_not_vacuous() -> None:
    """Plancher sur la DÉCOUVERTE, des deux côtés.

    Deux façons de rendre ce fichier vide sans rien casser d'autre :
    perdre les specs, ou perdre le corpus. Les deux sont ancrées.
    """
    assert len(_SPECS) >= _SPEC_FLOOR, (
        f"{len(_SPECS)} spec(s) d'audit découverte(s) (plancher "
        f"{_SPEC_FLOOR}) — l'aplatissement de `COMPONENT_SPECS` est "
        f"cassé, et cette gate ne vérifie plus rien."
    )
    assert len(_EMITTED) >= 400, (
        f"{len(_EMITTED)} classe(s) dans le corpus des thèmes — le "
        f"lecteur partagé ne rend plus rien, donc TOUT sélecteur "
        f"paraîtrait périmé."
    )
    concernes = [s for s in _SPECS if class_tokens(s.root_selector)]
    assert len(concernes) >= 10, (
        f"seulement {len(concernes)} sélecteur(s) nomment une classe — "
        f"l'extracteur `_CLASS_TOKEN` ne trouve plus rien."
    )


@pytest.mark.parametrize(
    "spec", _SPECS, ids=lambda s: s.name,
)
def test_an_audit_selector_names_only_live_classes(spec) -> None:
    """Chaque classe d'un sélecteur d'ancrage doit être émise."""
    selectors = [spec.root_selector, spec.color_sample_selector]
    mortes = sorted(
        tok
        for sel in selectors if sel
        for tok in class_tokens(sel)
        if tok not in _EMITTED
    )
    assert not mortes, (
        f"le sélecteur d'audit de `{spec.name}` nomme {mortes}, "
        f"qu'aucun thème du framework n'écrit plus.\n"
        f"  Sélecteur : {spec.root_selector!r}\n"
        f"  L'audit ne retrouvera pas le composant — et s'il retrouve "
        f"un AUTRE élément, il jugera celui-là sans le dire. C'est ce "
        f"qui est arrivé à `badge` et `card` le 2026-08-30, quand les "
        f"rayons sont passés à trois familles : `rounded-md` et "
        f"`rounded-xl` ont disparu du dépôt le même jour.\n"
        f"  Rends le sélecteur à ce que le composant écrit vraiment "
        f"(`rendered_html_of` de `_discovery` le dit)."
    )


def test_the_selector_reader_still_bites() -> None:
    """Les deux versants de l'extracteur de classes.

    Il cherche une FORME — un point suivi d'un identifiant — donc il
    peut cesser de voir sans rien faire rougir, et la gate ci-dessus
    passerait alors en ne comparant aucun jeton.
    """
    assert class_tokens("div.rounded-box.shadow-sm") == {
        "rounded-box", "shadow-sm",
    }
    assert class_tokens("span.inline-flex.rounded-selector") == {
        "inline-flex", "rounded-selector",
    }
    # Le versant qui ÉPARGNE, et il compte : une balise nue ne nomme
    # aucune classe, et une classe marqueur `.bz-*` est posée par le
    # composant — l'exiger dans le corpus des thèmes rougirait sur des
    # sélecteurs parfaitement corrects, ce qui est la meilleure façon
    # de faire débrancher la règle.
    assert class_tokens("iconify-icon") == set()
    assert class_tokens(".bz-html") == set()
    assert class_tokens("input[name='x']") == set()
    # Le cas qui a VRAIMENT mordu : un point à l'intérieur d'un
    # sélecteur d'attribut n'introduit pas une classe. Six specs
    # rougissaient là-dessus, dont ``stepper`` et ``tabs``.
    assert class_tokens("div[bz-data*='$bz.stepper.scope']") == set()
    assert class_tokens("div.rounded-box[data-x='a.b']") == {"rounded-box"}


def test_the_corpus_really_holds_the_families() -> None:
    """Le versant LICITE du corpus.

    Si ``emitted_classes`` rendait un ensemble plausible mais faux — les
    noms de slots au lieu de leur contenu, par exemple — la gate serait
    verte en comparant à côté. On vérifie donc qu'il contient ce qu'on
    sait y être.
    """
    for connue in ("rounded-box", "rounded-selector", "rounded-full",
                   "inline-flex", "shadow-sm"):
        assert connue in _EMITTED, (
            f"`{connue}` manque au corpus des classes émises : le "
            f"lecteur ne lit pas ce qu'on croit."
        )
    for morte in ("rounded-md", "rounded-xl"):
        assert morte not in _EMITTED, (
            f"`{morte}` est revenue dans un thème — la migration des "
            f"trois familles a été défaite quelque part."
        )
