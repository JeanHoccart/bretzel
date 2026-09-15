"""Les deux moitiés de ``resizable`` doivent normaliser à l'identique.

``normalize_weights`` (``components/layout/resizable/resizable.py``) et
``$bz.resizable.scope._weights`` (``runtime/_src/20_resizable.js``) sont
la MÊME fonction, écrite deux fois : le serveur pose les ``flex-grow`` du
premier paint, le runtime les repose à chaque tick réactif.

**Pourquoi une gate, et pas seulement des tests unitaires de chaque côté.**
La divergence est arrivée pour de vrai, le 2026-08-13, entre l'écriture et
la relecture : le Python normalisait à 100, le JS rendait les poids
BRUTS. Aucun test ne l'a vu, et aucun n'aurait pu — chaque moitié était
cohérente avec elle-même, et le mode local masquait tout parce que le
``bz-data`` semé par le serveur est déjà normalisé.

Ce que ça coûtait, mesuré : ``_mins`` voyage en POINTS DE POURCENTAGE.
Poids bruts + minimums en pourcents, et les deux échelles ne se parlent
plus. ``ui.resizable(sizes=[1, 3])`` avec ``min_size=15`` — deux
écritures documentées — donnait ``pair = 4``, ``lo = 15``, donc
``hi < lo`` à chaque frame, donc **une poignée qui ne bougeait jamais**.
Sans erreur, sans rien dans la console, et uniquement en mode binding :
celui-là même que le composant met en avant pour ``persist="local"``.

``test_python_js_mirror`` ne couvre que les jetons de fil de
``protocol.py`` — cette classe de miroir-là n'avait aucune gate.

Lourd (uvicorn + Chromium) — à lancer explicitement :
``py -m pytest tests/runtime_js/test_resizable_mirrors_python.py -q -m browser``
"""

from __future__ import annotations

import json

import pytest

from bretzel.components.layout.resizable import normalize_weights
from tests.audit.harness import audit_server, browser_page

#: (poids bruts, nombre de panneaux). Chaque ligne tient une classe
#: d'entrée que les deux moitiés doivent traiter pareil — pas des
#: variations du même cas.
_TABLE: list[tuple[object, int]] = [
    (None, 2),                    # rien de déclaré → parts égales
    (None, 3),                    # …et le tiers, qui ne tombe pas juste
    ([50, 50], 2),                # déjà normalisé
    ([25, 75], 2),                # normalisé, inégal
    ([1, 3], 2),                  # RATIO — le cas qui a cassé
    ([2, 3, 5], 3),               # ratio à trois
    ([50], 3),                    # liste trop courte → complétée
    ([50, 50, 50, 50], 2),        # liste trop longue → tronquée
    ([-10, 40], 2),               # négatif → repli sur la part
    (["nope", 40], 2),            # non numérique → repli
    ([0, 0], 2),                  # somme nulle → parts égales
    ([100, 0], 2),                # un panneau à zéro reste légal
    ([0.5, 0.25, 0.25], 3),       # fractions < 1
    ("50,50", 2),                 # une CHAÎNE est une Sequence : repli
]

#: Les deux moitiés arrondissent au centième. Python arrondit au pair
#: (``round`` est *banker's rounding*), ``Math.round`` arrondit vers le
#: haut : sur une valeur pile à ``x.xx5`` elles peuvent différer d'un
#: centième, et ce n'est pas une dérive de logique. La tolérance vaut
#: exactement cette résolution — toute vraie divergence est de plusieurs
#: points, pas de 0,01.
_TOL = 0.011


@pytest.fixture(scope="module")
def js_weights():
    """Un évaluateur qui fait tourner la moitié JS dans un vrai navigateur.

    Le scope est monté à la main plutôt que pris sur un composant de la
    page : on teste ``_weights`` en isolation, pas l'instance du banc.
    ``_panels`` est stubé — la fonction ne s'en sert que pour compter,
    et le compte est justement le paramètre qu'on fait varier.
    """
    with audit_server() as base:
        with browser_page(base, "/resizable") as page:
            page.wait_for_timeout(1500)

            def run(raw: object, count: int) -> list[float]:
                return page.evaluate(
                    """([raw, n]) => {
                        const s = Object.create($bz.resizable.scope);
                        s._read = () => raw;
                        s._panels = () => new Array(n);
                        return s._weights(n);
                    }""",
                    [raw, count],
                )

            yield run


@pytest.mark.parametrize(
    "raw,count", _TABLE, ids=[f"{json.dumps(r)}x{c}" for r, c in _TABLE]
)
def test_js_matches_python(js_weights, raw: object, count: int) -> None:
    expected = normalize_weights(raw, count)
    actual = js_weights(raw, count)
    assert len(actual) == len(expected), (
        f"longueurs différentes pour {raw!r} sur {count} panneaux : "
        f"JS {actual} vs Python {expected}. Les deux moitiés doivent "
        f"rendre UN poids par panneau — un panneau sans poids reçoit "
        f"``undefined`` et disparaît."
    )
    for index, (got, want) in enumerate(zip(actual, expected)):
        assert abs(got - want) <= _TOL, (
            f"poids {index} divergent pour {raw!r} sur {count} panneaux : "
            f"JS {actual} vs Python {expected}.\n"
            f"  Les deux moitiés doivent normaliser PAREIL — le serveur "
            f"pose le premier paint, le runtime repose la suite. Une "
            f"divergence se voit comme un saut de mise en page à "
            f"l'hydratation, et casse le butoir ``min_size`` (qui est en "
            f"points de pourcentage)."
        )


@pytest.mark.parametrize("raw,count", _TABLE, ids=[f"sum{i}" for i in
                                                   range(len(_TABLE))])
def test_js_sums_to_a_hundred(js_weights, raw: object, count: int) -> None:
    """La propriété qui fait que ``_mins`` a un sens.

    Séparée du test de miroir à dessein : deux moitiés pourraient
    s'accorder sur une échelle FAUSSE. Celui-ci dit laquelle est la
    bonne — la même que celle de ``min_size``.
    """
    actual = js_weights(raw, count)
    assert sum(actual) == pytest.approx(100.0, abs=0.05), (
        f"les poids JS somment à {sum(actual)} et non 100 pour {raw!r} : "
        f"``_mins`` voyage en points de pourcentage, donc une autre "
        f"échelle rend le butoir ``min_size`` incohérent — jusqu'à figer "
        f"la poignée pour toujours."
    )
