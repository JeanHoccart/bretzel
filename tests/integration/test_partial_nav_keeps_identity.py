"""Un composant garde son ``bz-id`` quel que soit le CHEMIN D'ARRIVÉE.

Trouvé le 2026-08-13, en cherchant à couvrir la navigation — le trou que
la memory ``project_no_suite_navigates`` décrit depuis le 2026-08-05.

Le même accordéon de ``/markdown`` a **deux** identités :

===================  ==================================================
arrivée              ``bz-id``
===================  ==================================================
chargement direct    ``outlet_shell_container_0_…_accordion_0``
navigation boostée   ``root_container_0_…_accordion_0``
===================  ==================================================

Le rendu complet imbrique la page dans le layout, donc le chemin d'id
traverse l'``outlet_shell``. Le fragment partiel ne rend que la page :
``ctx.parent_stack`` est vide, et ``component.py`` retombe alors sur le
littéral ``"root"``.

**Ce n'est pas une nouveauté, c'est une récidive.** Le commentaire de
``bretzel/render/partials.py`` raconte EXACTEMENT le même défaut, trouvé
et réparé pour les partials de ``@refreshable`` : « every child's
``Component.__init__`` fell back to the literal "root" ID prefix —
producing IDs incompatible with what the initial full-page render
emitted. Idiomorph keys morphs by id ; the mismatch silently downgraded
to subtree REPLACEMENT, destroying every ``bz-data`` scope on the swapped
subtree ». Le chemin de la NAVIGATION n'a jamais reçu ce fix.

Conséquence, la même que celle déjà documentée là-bas : après une
navigation boostée, aucun nœud de la région échangée ne peut être
APPARIÉ par idiomorph — chaque navigation détruit et reconstruit le
sous-arbre au lieu de le fusionner.

Le fix : ``render/pipeline.py`` sème ``ctx.parent_stack`` avec un parent
portant l'id ``ctx.partial_target`` — l'information était déjà là, le
routeur venait de la poser (``server/routing/pages.py``).

✅ **Réparé le 2026-08-13**, quelques heures après avoir été écrit : la
graine d'identité vit dans ``render/pipeline.py`` (``_PartialRoot``), et
ce fichier est passé d'``xfail(strict=True)`` à un test ordinaire. Le
compte à rebours a servi — c'est la raison de ne jamais écrire un
``skip`` à sa place.
"""

from __future__ import annotations

import re

import pytest
from starlette.testclient import TestClient

#: L'accordéon unique de ``/markdown`` — une page volontairement simple,
#: pour que l'écart mesuré ne puisse pas venir d'une ambiguïté de
#: sélection (``/accordion`` en porte une quarantaine).
_PAGE = "/markdown"
_BZ_ID = re.compile(r'(?<![\w:-])bz-id="([^"]*_accordion_0)"')

#: L'outlet du layout ``shell`` du playground, ce que htmx envoie en
#: ``HX-Target`` quand un lien de la barre latérale est boosté.
_OUTLET = "outlet_shell"


@pytest.fixture(scope="module")
def client():
    from examples.playground.main import app

    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


def test_the_two_renders_are_both_reachable(client) -> None:
    """Garde-fou : si le rendu partiel cesse d'être partiel, la
    comparaison ci-dessous devient tautologique et passerait toute
    seule — sans rien prouver."""
    full = client.get(_PAGE)
    partial = client.get(
        _PAGE, headers={"HX-Request": "true", "HX-Target": _OUTLET}
    )
    assert full.status_code == partial.status_code == 200
    assert len(partial.text) < len(full.text) / 2, (
        f"le rendu « partiel » fait {len(partial.text)} octets contre "
        f"{len(full.text)} — il n'est plus partiel, donc l'en-tête "
        f"`HX-Target` n'est plus reconnu et ce fichier ne mesure rien."
    )
    assert _BZ_ID.search(full.text) and _BZ_ID.search(partial.text)


def test_identity_does_not_depend_on_the_arrival_path(client) -> None:
    full = _BZ_ID.search(client.get(_PAGE).text).group(1)
    partial = _BZ_ID.search(
        client.get(
            _PAGE, headers={"HX-Request": "true", "HX-Target": _OUTLET}
        ).text
    ).group(1)
    assert partial == full, (
        f"le même accordéon rend `{full}` en chargement direct et "
        f"`{partial}` après une navigation boostée.\n"
        f"  `bz-id` est la clé de DEUX mécanismes — l'appariement "
        f"idiomorph et la résolution de scope — donc l'identité ne peut "
        f"pas dépendre de la façon dont l'utilisateur est arrivé."
    )
