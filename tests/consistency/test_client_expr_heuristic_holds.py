"""L'heuristique « cette chaîne est-elle du code client ? » ne dérive pas.

``looks_like_client_expr`` décide, pour une valeur de prop de type ``str``,
si c'est du **texte** (à rendre tel quel en SSR) ou une **expression
client** (à émettre en ``bz-attr:``). Python n'a aucun porteur de type qui
distingue les deux — c'est la contrainte, pas un choix.

Pourquoi une gate plutôt qu'un remplacement (décision D3, 2026-07-29)
---------------------------------------------------------------------
L'audit du socle la classait « le plus frontalement anti-modèle » : le
modèle dit « jamais de chaîne pour adresser l'état », et ici une regex
renifle une chaîne pour décider si c'est du code. Le juge défense
répondait que la contrainte vient de **Python** — Svelte a ``$bindable()``,
Solid passe la paire ``[get, set]`` ; les deux ont un porteur de type,
Bretzel n'en a pas ici — et que l'API à deux tiers **actée** exige le
tier-2 où l'utilisateur écrit une expression brute.

Mesuré avant de trancher : sur un corpus de prose réaliste,
**8 classements corrects sur 8** ; sur du vrai code client, **6 sur 6**.
L'heuristique n'est pas le problème.

Le vrai trou était **l'échappatoire**, et il est fermé
-------------------------------------------------------
La docstring promettait de forcer le binding « via the explicit
``:attr_name`` » — or ``:`` est un préfixe **Alpine**, mort depuis V3. Il
n'y avait donc **aucun opt-out documenté ET fonctionnel**. Depuis le
2026-07-29 : ``attrs={...}`` pour forcer le littéral, ``**{"bz-attr:x": …}``
pour forcer l'expression — les deux vérifiés au rendu, et ``:attr_name``
lève désormais.

Cette gate fige les deux moitiés : le corpus de classement, et le fait que
les échappatoires marchent.
"""

from __future__ import annotations

import pytest

from bretzel.components.base.reactive_prop import looks_like_client_expr

#: Preuve de morsure : l'heuristique DOIT reconnaître chaque forme d'expression client, et
#: `test_prose_stays_literal` garde l'autre sens.
MUTATION_PROOF = "test_client_code_is_detected"

# ── Prose : DOIT rester du texte ──────────────────────────────────────
# Chaque entrée porte le piège qu'elle tend. Un faux positif ici fait
# DISPARAÎTRE le littéral du SSR — la valeur part en ``bz-attr:`` et le
# navigateur évalue une expression qui n'existe pas.
_PROSE: tuple[tuple[str, str], ...] = (
    ("Helpful hint", "prose banale"),
    ("Save", "un mot"),
    ("/users/42", "une URL — les slashes ne sont pas une division"),
    ("Rechercher...", "les points de suspension"),
    ("Nom (requis)", "des parenthèses SANS appel de fonction"),
    ("Prix : 10 $", "un dollar de devise, pas le préfixe runtime"),
    ("e-mail@site.fr", "un arobase d'adresse, pas une directive"),
    ("Tapez a & b", "une esperluette SIMPLE — ce n'est pas ``&&``"),
    # ── Les data-URI ont QUITTÉ ce corpus le 2026-08-26 ────────────
    # Trois entrées vivaient ici (padding ``==``, padding ``=``, SVG
    # percent-encodé), et elles gardaient une exclusion ``value.startswith
    # ("data:")`` posée dans l'heuristique le 2026-08-13 — un PNG sur
    # quatre partait en ``bz-attr:value=``, le runtime compilait la
    # data-URI en JS, et le boot s'arrêtait avant ``.bz-ready`` : page
    # blanche selon la taille de l'image.
    #
    # L'exclusion est retirée, et la protection a changé d'ÉTAGE : elle
    # vit désormais sur la prop (``reactive_prop(never_code=True)``), où
    # elle couvre AUSSI les URLs — le cas que l'exclusion ne voyait pas,
    # et qui a coûté l'export CSV du datatable. Gardé par
    # ``test_a_url_prop_is_never_read_as_code``, qui nomme
    # ``SignaturePad.value``.
    #
    # ⚠️ Ne PAS ré-ajouter d'entrée data-URI ici. Deux des trois
    # passeraient encore — par accident, faute de marqueur — et ce vert
    # rallumerait la croyance que l'heuristique protège les URI. C'est
    # cette croyance, écrite noir sur blanc dans la docstring de
    # ``looks_like_client_expr`` (« Returns False for … URLs »), qui a
    # laissé passer les trois régressions.
)

# ── Code client : DOIT être détecté ───────────────────────────────────
_CODE: tuple[tuple[str, str], ...] = (
    ("a && b", "conjonction"),
    ("$bz.state.X.y", "chemin du store"),
    ("open ? 1 : 2", "ternaire"),
    ("foo()", "appel de fonction"),
    ("a < b", "comparaison"),
    ("count >= 10", "comparaison composée"),
)


@pytest.mark.parametrize(
    ("value", "why"), _PROSE, ids=[w for _, w in _PROSE]
)
def test_prose_stays_literal(value: str, why: str) -> None:
    assert not looks_like_client_expr(value), (
        f"{value!r} ({why}) est classé comme une EXPRESSION CLIENT.\n"
        f"  Conséquence : le littéral disparaît du SSR — la valeur part en "
        f"`bz-attr:` et le navigateur évalue une expression inexistante.\n"
        f"  Si le resserrage est volontaire, l'échappatoire pour l'appelant "
        f"est `attrs={{...}}` (qui gagne la précédence)."
    )


@pytest.mark.parametrize(
    ("value", "why"), _CODE, ids=[w for _, w in _CODE]
)
def test_client_code_is_detected(value: str, why: str) -> None:
    assert looks_like_client_expr(value), (
        f"{value!r} ({why}) n'est PAS détecté comme expression client — il "
        f"partirait en attribut HTML littéral, inerte.\n"
        f"  L'échappatoire pour forcer : `**{{'bz-attr:<prop>': <expr>}}`."
    )


def test_both_escape_hatches_actually_work() -> None:
    """Les deux opt-out documentés, vérifiés AU RENDU.

    C'est la moitié qui manquait : la docstring annonçait ``:attr_name``,
    un préfixe Alpine inerte. Une échappatoire qu'on ne teste pas est une
    promesse, pas un mécanisme."""
    import re

    from bretzel.components import Input
    from bretzel.components.base.testing import render_isolated
    from bretzel.core.serialize import serialize

    # 1. Forcer le LITTÉRAL quand l'heuristique voit du code.
    with render_isolated():
        html = serialize(Input(attrs={"placeholder": "a && b"}).render())
    assert re.search(r'placeholder="a &amp;&amp; b"', html), (
        "`attrs={...}` doit préserver le littéral — c'est l'échappatoire "
        "quand l'heuristique se trompe dans le sens « je vois du code »."
    )

    # 2. Forcer l'EXPRESSION quand l'heuristique voit du texte.
    with render_isolated():
        html = serialize(Input(**{"bz-attr:placeholder": "somePath"}).render())
    assert "bz-attr:placeholder" in html, (
        "`**{'bz-attr:x': …}` doit émettre la directive — c'est "
        "l'échappatoire dans l'autre sens."
    )

    # 3. Et l'ANCIENNE échappatoire, morte, lève au lieu de ne rien faire.
    from bretzel.components.base.attrs import ComponentUsageError

    with pytest.raises(ComponentUsageError, match="Alpine"), render_isolated():
        Input(**{":placeholder": "somePath"})
