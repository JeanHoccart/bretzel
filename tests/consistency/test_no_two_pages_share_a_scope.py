"""Gate : deux pages ne portent jamais le meme ``bz-id`` porteur d'etat.

Le defaut qu'elle ferme
-----------------------
Le magasin de scopes du runtime est une ``Map`` indexee par le ``bz-id``
**chaine** (``03_scope.js``), et un ``hx-boost`` ne recharge pas le
runtime. Un ``bz-id`` decrivait une POSITION dans l'arbre
(``outlet_shell_container_0_…_accordion_0``) sans rien dire de la page :
deux pages de meme forme produisaient donc la meme cle, et apres une
navigation le scope de la page precedente etait retrouve par son id et
l'emportait sur le litteral frais du serveur.

Symptome : on ouvre l'accordeon de ``/accordion``, on clique
``/markdown``, il y arrive **ouvert**. Un F5 le rend correctement — la
signature d'un etat client fantome.

Mesure, sur les memes pages du playground :

    avant le fix : 13 collisions sous l'outlet
                   (un dialog sur 7 pages, un tooltip sur 2, les tabs
                   sur 3, un accordeon sur 2, deux date_picker)
    apres        : 0

Pourquoi une gate en plus de la sonde navigateur
-------------------------------------------------
``tests/runtime_js/test_boost_nav_does_not_share_state`` prouve le
COMPORTEMENT sur deux pages, dans un vrai Chromium — c'est ce qui compte,
et c'est lent. Celle-ci compte les collisions sur TOUTES les pages, sans
navigateur, a chaque commit. La sonde dit « ca marche ici », la gate dit
« et nulle part ailleurs ».

Ce qu'elle NE garde pas
------------------------
Les ids du SHELL. Deux pages partagent legitimement la barre laterale et
son en-tete : c'est le meme element d'une page a l'autre, et c'est tout
l'interet du partial-nav. Ils se reconnaissent a ce qu'ils ne descendent
pas d'un outlet.
"""

from __future__ import annotations

import re
from collections import defaultdict

import pytest

#: Un element qui porte A LA FOIS un ``bz-id`` et un ``bz-data`` — donc
#: un porteur d'etat client, donc une entree dans la ``Map`` du runtime.
#: Les deux ordres d'attributs, parce que le serialiseur ne garantit pas
#: lequel sort en premier.
_PORTEURS = (
    re.compile(r'<[a-zA-Z][^>]*\bbz-id="([^"]+)"[^>]*\bbz-data="'),
    re.compile(r'<[a-zA-Z][^>]*\bbz-data="[^"]*"[^>]*\bbz-id="([^"]+)"'),
)

#: Un id qui descend d'un outlet appartient a la PAGE ; les autres sont
#: du shell, partages a dessein.
_SOUS_OUTLET = "outlet"


def _scopes_par_page() -> dict[str, set[str]]:
    """``bz-id -> pages qui l'emettent``, sur tout le playground."""
    from starlette.testclient import TestClient

    from examples.playground.main import app
    from tests.integration.test_example_pages_render import PLAYGROUND_PATHS

    par_id: dict[str, set[str]] = defaultdict(set)
    with TestClient(app, raise_server_exceptions=False) as client:
        for chemin in PLAYGROUND_PATHS:
            reponse = client.get(chemin)
            if reponse.status_code != 200:
                continue
            for motif in _PORTEURS:
                for bz_id in motif.findall(reponse.text):
                    par_id[bz_id].add(chemin)
    return par_id


@pytest.fixture(scope="module")
def scopes() -> dict[str, set[str]]:
    return _scopes_par_page()


def test_the_sweep_is_not_vacuous(scopes: dict[str, set[str]]) -> None:
    """Plancher : on a bien LU des porteurs d'etat, et beaucoup.

    « Zero collision » passe exactement aussi bien quand le detecteur ne
    reconnait plus aucun porteur — serialiseur change, prefixe renomme,
    pages a 500. Mesure du 2026-08-29 : 2 567 porteurs sur 75 pages.
    """
    assert len(scopes) >= 1500, (
        f"seulement {len(scopes)} porteurs de bz-data trouves — le "
        f"detecteur ne lit plus grand-chose, verifie le rendu ou les "
        f"motifs avant de croire que la gate passe."
    )
    sous_outlet = [i for i in scopes if i.startswith(_SOUS_OUTLET)]
    assert len(sous_outlet) >= 1000, (
        f"seulement {len(sous_outlet)} porteurs SOUS un outlet — c'est la "
        f"population que la gate juge, et elle a fondu."
    )


def test_no_two_pages_share_a_scope_under_the_outlet(
    scopes: dict[str, set[str]],
) -> None:
    partages = {
        bz_id: pages
        for bz_id, pages in scopes.items()
        if len(pages) > 1 and bz_id.startswith(_SOUS_OUTLET)
    }
    detail = "".join(
        f"\n  {bz_id}  →  {len(pages)} pages : {sorted(pages)[:4]}"
        for bz_id, pages in sorted(partages.items())[:10]
    )
    assert not partages, (
        f"{len(partages)} identifiant(s) porteur(s) d'etat apparaissent "
        f"sur plusieurs pages sous l'outlet.{detail}\n\n"
        f"Le magasin de scopes du runtime est indexe par cette chaine et "
        f"un hx-boost ne le vide pas : la seconde page recevra l'etat de "
        f"la premiere, et un F5 la rendra correctement — la signature "
        f"d'un etat client fantome.\n"
        f"  L'outlet doit qualifier par la page l'id qu'il donne a ses "
        f"ENFANTS (``ctx.page_scope``), sans toucher a l'id qu'il REND "
        f"(htmx le renvoie en HX-Target)."
    )


def test_the_shell_still_shares_its_own(scopes: dict[str, set[str]]) -> None:
    """Le versant LICITE — sans lui, la gate passerait aussi bien si le
    partial-nav cessait de partager quoi que ce soit.

    La barre laterale et son en-tete SONT le meme element d'une page a
    l'autre : c'est ce qui permet a htmx de ne remplacer que l'outlet.
    """
    partages_hors_outlet = [
        bz_id for bz_id, pages in scopes.items()
        if len(pages) > 1 and not bz_id.startswith(_SOUS_OUTLET)
    ]
    assert partages_hors_outlet, (
        "aucun id partage HORS outlet : la coque ne serait donc plus "
        "commune aux pages, et le partial-nav n'aurait plus d'objet. "
        "C'est soit une regression, soit un playground qui n'a plus de "
        "layout."
    )


def test_the_detector_still_bites() -> None:
    """Preuve fabriquee : le detecteur voit une collision, et la laisse
    passer sur le cas licite.

    On ne remonte pas l'app — on eprouve les motifs et la regle de tri
    sur du HTML ecrit a la main, dans les quatre formes qui comptent.
    """
    fautif = (
        '<div bz-id="outlet_shell_card_0_accordion_0" '
        'bz-data="{expanded: false}"></div>'
    )
    trouve = [m for motif in _PORTEURS for m in motif.findall(fautif)]
    assert trouve == ["outlet_shell_card_0_accordion_0"], (
        "le detecteur doit reconnaitre un porteur bz-id + bz-data"
    )

    # L'ordre INVERSE des attributs — le serialiseur ne garantit pas
    # lequel sort en premier, et un motif seul en raterait la moitie.
    inverse = (
        '<div bz-data="{expanded: false}" '
        'bz-id="outlet_shell_card_0_accordion_0"></div>'
    )
    assert [m for motif in _PORTEURS for m in motif.findall(inverse)], (
        "l'ordre inverse des attributs doit etre reconnu aussi"
    )

    # Un bz-id SANS bz-data ne porte aucun etat : il ne peut pas
    # collisionner dans la Map du runtime, donc il sort.
    sans_etat = '<div bz-id="outlet_shell_card_0_text_0"></div>'
    assert not [m for motif in _PORTEURS for m in motif.findall(sans_etat)], (
        "un bz-id sans bz-data n'est pas un porteur de scope"
    )

    # Et le tri outlet / shell, qui est ce qui distingue une collision
    # d'un partage LEGITIME.
    assert "outlet_shell_card_0_accordion_0".startswith(_SOUS_OUTLET)
    assert not "root_sidebar_0".startswith(_SOUS_OUTLET), (
        "un id de shell ne doit pas etre compte comme collision — c'est "
        "le meme element d'une page a l'autre, et c'est le principe meme "
        "du partial-nav"
    )
