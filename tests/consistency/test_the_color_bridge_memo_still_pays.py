"""Le mémo de ``bridged_color_names`` reste rentable — et reste étanche.

Ce que cette gate ferme
-----------------------

:func:`bretzel.theme.bridges.bridged_color_names` balaie toute la
palette : ``envelope_dict()`` recalcule un ``bg_class`` et un
``fg_class`` pour chacune de ses ~42 couleurs. Elle est appelée par
``_wiring._refuse_unknown_color``, donc **une fois par composant
coloré** — 323 fois pour un chargement dur de ``/tabs``, mesuré le
2026-09-05, pour 19 % du temps de la requête passé à répondre la même
chose.

Le mémo tient parce qu'une :class:`~bretzel.theme.palette.Palette` est
construite une fois au démarrage et que ``Theme.get_palette`` rend
toujours la même instance. Si ça cessait d'être vrai — une palette
rebâtie par requête, une palette dérivée par composant — **rien ne
casserait** : la page resterait juste, elle serait juste redevenue
lente. C'est exactement la dérive qu'un test de justesse ne peut pas
voir. Mesuré : ``/tabs`` 86,4 → 68,2 ms (−21 %), ``/datatable``
330,1 → 198,3 ms (−40 %), A/B alterné dans le même process.

Pourquoi le taux de succès et pas le temps
-------------------------------------------

La machine dérive d'un facteur 2 à 3 entre deux exécutions (memory
``inprocess_ab_or_no_measurement``). Le compte de succès et d'échecs,
lui, est déterministe.

Le risque PROPRE à ce mémo
---------------------------

Un cache global sur une fonction qui prend un thème peut servir les
couleurs d'une app à une autre. ``test_the_memo_stays_keyed_per_palette``
est le versant qui mord là-dessus : une app qui déclare ``brand`` doit
avoir son pont, et le thème par défaut ne doit pas l'hériter.
"""

from __future__ import annotations

import pytest

from bretzel.theme import Theme
from bretzel.theme import bridges as bridges_mod

#: Le seuil, écrit UNE fois — le test de la vraie page et la preuve de
#: morsure ci-dessous lisent le même, sinon la preuve pourrait valider un
#: détecteur qui n'est pas celui qui garde.
MIN_HIT_RATE = 0.95


def hit_rate(pick_palette) -> float:
    """Taux de succès du mémo sur 40 appels, la palette venant de ``pick_palette``.

    Le régime EST le paramètre : une palette partagée (ce que le
    framework fait) contre une palette rebâtie à chaque appel (la
    dérive). Lit le compteur de la VRAIE fonction.
    """
    before = bridges_mod.bridged_color_names.cache_info()
    for _ in range(40):
        bridges_mod.bridged_color_names(pick_palette())
    after = bridges_mod.bridged_color_names.cache_info()
    hits, misses = after.hits - before.hits, after.misses - before.misses
    return hits / (hits + misses)


def hit_rate_on_a_rendered_page() -> tuple[int, int]:
    """``(succès, échecs)`` du mémo pendant le rendu d'une vraie page.

    Extrait pour être MUTABLE, et surtout pour lire le compteur de la
    VRAIE fonction — recompter depuis un mémo fabriqué ici laisserait la
    gate verte si le mémo disparaissait du module.
    """
    from fastapi.testclient import TestClient

    from examples.playground.main import app

    cache_info = getattr(bridges_mod.bridged_color_names, "cache_info", None)
    assert callable(cache_info), (
        "`bridged_color_names` n'est plus mémoïsée. Elle balaie toute la "
        "palette et elle est appelée une fois par composant coloré : la "
        "retirer rend 19 % du temps d'un chargement dur (mesuré le "
        "2026-09-05, /tabs 68,2 → 86,4 ms) sans changer une ligne du HTML. "
        "Si le mémo devait partir, c'est le refus de couleur inconnue "
        "qu'il faut déplacer, pas le mémo qu'il faut supprimer."
    )

    with TestClient(app) as client:
        client.get("/tabs")  # remplit le cache : on mesure le RÉGIME
        before = bridges_mod.bridged_color_names.cache_info()
        client.get("/tabs")
        after = bridges_mod.bridged_color_names.cache_info()
    return after.hits - before.hits, after.misses - before.misses


@pytest.fixture(scope="module")
def measured() -> tuple[int, int]:
    return hit_rate_on_a_rendered_page()


def test_the_page_actually_exercises_the_function(
    measured: tuple[int, int],
) -> None:
    """Le plancher — et il lit la mesure de CETTE gate.

    Un taux de 100 % sur trois appels ne dirait rien. Le plancher lit le
    total de la mesure elle-même, pas un recomptage indépendant (memory
    ``gate_floors_must_read_the_gate_source``).
    """
    hits, misses = measured
    assert hits + misses >= 100, (
        f"seulement {hits + misses} appels à `bridged_color_names` pendant "
        "le rendu de `/tabs` (323 le 2026-09-05) — soit la page a maigri, "
        "soit le refus de couleur inconnue a été déposé et cette gate ne "
        "mesure plus rien."
    )


def test_the_memo_still_pays_on_a_real_page(measured: tuple[int, int]) -> None:
    """L'invariant : une palette par app, pas une par composant."""
    hits, misses = measured
    rate = hits / (hits + misses)
    assert rate >= MIN_HIT_RATE, (
        f"taux de succès du mémo tombé à {rate:.0%} ({hits} succès, "
        f"{misses} échecs). Une palette est censée être construite UNE fois "
        "au démarrage et partagée par tout le rendu. Sous ce seuil, "
        "quelqu'un en rebâtit une par requête ou par composant : le rendu "
        "reste juste et redevient lent (19 % du temps d'un chargement dur)."
    )


def test_the_memo_stays_keyed_per_palette() -> None:
    """Le versant qui MORD : un cache global ne doit pas mélanger deux apps.

    Deux thèmes vivants en même temps, dont un seul déclare ``brand``.
    Si la clé du mémo se relâchait — une constante, un ``maxsize=1`` mal
    invalidé, une clé sur le NOM du thème — la seconde app hériterait des
    ponts de la première : ``ui.badge(color="brand")`` serait accepté là
    où il rendrait sans style.
    """
    plain = bridges_mod.bridged_color_names(Theme().get_palette())
    branded = bridges_mod.bridged_color_names(
        Theme(palette={"brand": "#ff0000"}).get_palette()
    )

    assert "brand" in branded, (
        "une couleur déclarée par l'app n'a pas de pont — le mémo rend une "
        "liste qui n'est pas celle de CETTE palette."
    )
    assert "brand" not in plain, (
        "le thème par défaut a hérité de la couleur d'un AUTRE thème — le "
        "mémo n'est pas keyé sur la palette."
    )


def test_the_memo_changes_nothing_to_the_answer() -> None:
    """Le versant LICITE : le mémo ne doit pas altérer le résultat.

    Rejoue le corps à la main sur la palette par défaut. Un mémo qui
    figerait un ordre, dédoublonnerait ou perdrait ``current`` passerait
    tous les tests de perf ci-dessus.
    """
    palette = Theme().get_palette()
    expected = tuple(
        list(bridges_mod.SEMANTIC_COLOR_NAMES)
        + [bridges_mod.CURRENT_COLOR_NAME]
        + sorted(
            set(palette.envelope_dict()) - set(bridges_mod.SEMANTIC_COLOR_NAMES)
        )
    )
    assert bridges_mod.bridged_color_names(palette) == expected
    assert bridges_mod.bridged_color_names(palette) == expected, "2e appel"


def test_the_rate_detector_catches_a_palette_rebuilt_per_call() -> None:
    """La preuve que la gate MORD, fabriquée en mémoire — et son cas licite.

    La dérive à attraper n'a pas de symptôme : une palette rebâtie par
    requête (ou dérivée par composant) rend exactement le même HTML,
    juste plus lentement. On la fabrique ici pour vérifier que le
    détecteur — le taux de succès du mémo, lu sur la VRAIE fonction — la
    voit, et surtout qu'il ne crie pas sur le régime licite d'à côté.

    Le versant licite compte autant : un détecteur qui rougirait aussi
    sur une palette partagée serait inutilisable, et c'est ce versant-là
    qui a trouvé les deux seuls bugs de gate de ce dépôt.
    """
    shared = Theme().get_palette()

    licite = hit_rate(lambda: shared)
    assert licite >= MIN_HIT_RATE, (
        f"le détecteur rougit sur le régime NORMAL ({licite:.0%}) — une "
        "palette partagée est ce que le framework fait, la gate serait "
        "inutilisable."
    )

    derive = hit_rate(lambda: Theme().get_palette())
    assert derive < MIN_HIT_RATE, (
        f"une palette rebâtie à chaque appel donne {derive:.0%} de succès et "
        "passe quand même le seuil — le détecteur ne voit pas la dérive "
        "qu'il est censé garder."
    )
