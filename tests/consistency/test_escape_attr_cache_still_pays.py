"""Le mémo d'``escape_attr`` reste rentable — et son jumeau reste nu.

Ce que cette gate ferme
-----------------------

:func:`bretzel.core.escape.escape_attr` est mémoïsée parce qu'une valeur
d'attribut est presque toujours **écrite par le framework** : chaîne de
classes Tailwind, expression ``bz-*``, rôle ARIA. Mesuré le 2026-08-27
sur une page du playground : ~4 000 appels pour ~1 150 valeurs
distinctes, et ~2 400 pour tout le site — 99 % de réutilisation.

Le pari n'est pas gratuit : sur un flux **sans aucune réutilisation**, le
mémo coûte +27 % (mesuré sur 40 000 valeurs jamais revues). Il ne tient
donc que tant que les attributs restent du vocabulaire de framework. Le
jour où des données utilisateur y passeraient en masse — une colonne de
``datatable`` versée en ``data-*``, un ``title=`` par ligne — le taux
s'effondrerait sans que rien ne casse : la page resterait juste, elle
serait juste plus lente. C'est exactement la dérive qu'un test de
justesse ne peut pas voir.

Pourquoi le taux de succès et pas le temps
-------------------------------------------

Le temps n'est pas mesurable ici : la machine dérive d'un facteur 2 à 3
entre deux exécutions (memory ``inprocess_ab_or_no_measurement``). Le
compte de succès et d'échecs, lui, est déterministe.
"""

from __future__ import annotations

import pytest

from bretzel.core import escape as escape_mod


def hit_rate_on_a_rendered_page() -> tuple[int, int]:
    """``(succès, échecs)`` du mémo pendant le rendu d'une vraie page.

    Extrait pour être MUTABLE, et surtout pour lire le compteur du VRAI
    ``escape_attr`` — recompter depuis un mémo fabriqué ici laisserait la
    gate verte si le mémo disparaissait du module.
    """
    from fastapi.testclient import TestClient

    from examples.playground.main import app

    with TestClient(app) as client:
        client.get("/tabs")  # remplit le cache : on mesure le RÉGIME, pas le démarrage
        before = escape_mod.escape_attr.cache_info()
        client.get("/tabs")
        after = escape_mod.escape_attr.cache_info()
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
    assert hits + misses >= 1000, (
        f"seulement {hits + misses} appels à `escape_attr` pendant le rendu "
        "de `/tabs` — la gate ne mesure plus une vraie page."
    )


def test_the_memo_still_pays_on_a_real_page(measured: tuple[int, int]) -> None:
    """L'invariant : les attributs restent du vocabulaire de framework."""
    hits, misses = measured
    rate = hits / (hits + misses)
    assert rate >= 0.60, (
        f"taux de succès du mémo tombé à {rate:.0%} ({hits} succès, "
        f"{misses} échecs). Le mémo coûte +27 % quand rien ne se répète : "
        "sous ce seuil il faut soit le retirer, soit trouver ce qui verse "
        "des données uniques dans des attributs."
    )


def test_escape_html_is_deliberately_not_memoised() -> None:
    """Le versant licite : l'asymétrie est un choix mesuré, pas un oubli.

    ``escape_html`` reçoit le CORPS du document, donc les données de
    l'utilisateur : 266 succès pour 2 471 échecs le 2026-08-27. Le
    mémoïser paierait le surcoût sans le gain. Si quelqu'un l'ajoute
    « par symétrie », cette gate le dit.
    """
    assert not hasattr(escape_mod.escape_html, "cache_info"), (
        "`escape_html` a été mémoïsée. Elle voit les données de "
        "l'utilisateur, pas du vocabulaire de framework — mesuré à 10 % de "
        "succès. Mesurer avant de garder."
    )


def test_the_memo_catches_every_character_the_plain_chain_catches() -> None:
    """Le versant qui MORD : le mémo ne doit rien changer au résultat.

    Rejoue la chaîne de remplacements à la main sur les caractères qui
    comptent, et sur un cas licite qui ne contient rien à échapper.

    ⚠️ La chaîne témoin lit ``_ATTR_ESCAPES``, la table d'``escape_attr``
    — plus ``_HTML_ESCAPES`` suivie d'un complément. Les deux ont
    divergé le 2026-08-28 : ``'`` reste échappée dans le CORPS et ne
    l'est plus dans un ATTRIBUT.
    """

    def plain(value: str) -> str:
        out = value
        for char, entity in escape_mod._ATTR_ESCAPES:
            out = out.replace(char, entity)
        return out

    for value in (
        'a<b>"c"&\'d\te\nf\rg',
        "data-[open=false]:bg-x",  # le `=` NE doit pas être échappé
        "rien-a-echapper",
        "",
        "&amp;",  # déjà une entité : ré-échappée, comme documenté
        "picked ? 'true' : 'false'",  # l'apostrophe NE doit pas être échappée
    ):
        assert escape_mod.escape_attr(value) == plain(value), value
        assert escape_mod.escape_attr(value) == plain(value), f"2e appel : {value}"
