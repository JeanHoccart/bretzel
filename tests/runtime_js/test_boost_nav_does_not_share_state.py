"""Deux pages ne partagent plus leur ÉTAT CLIENT — au navigateur.

Le défaut, et comment il marchait
---------------------------------
Le magasin de scopes du runtime est une ``Map`` indexée par le ``bz-id``
**chaîne** (``03_scope.js``), et un ``hx-boost`` ne recharge pas le
runtime. Or un ``bz-id`` décrivait une POSITION dans l'arbre —
``outlet_shell_container_0_…_accordion_0`` — sans rien dire de la page.

Deux pages de même forme produisaient donc la même clé. Mesuré le
2026-08-13 sur les 68 pages du playground : **13 identifiants porteurs
d'un ``bz-data`` apparaissaient sur plusieurs pages** hors du shell — un
tooltip sur 13 pages, un dialog sur 7, les tabs sur 3, un accordéon sur
2. Après une navigation, le scope de la page précédente était retrouvé
par son id et ses valeurs l'emportaient sur le littéral frais que le
serveur venait de livrer : on ouvrait l'accordéon de ``/accordion``, on
cliquait ``/markdown``, et il y arrivait **ouvert**. Un F5 le rendait
correctement — ce qui est la signature d'un état client fantôme.

✅ **Réparé le 2026-08-29** : l'outlet donne à ses enfants un id
**qualifié par la page** (``ctx.page_scope``), tout en gardant STABLE
l'id qu'il rend — htmx renvoie ce dernier en ``HX-Target``, donc le
bouger casserait la navigation partielle suivante. Collisions sous
l'outlet : **13 → 0**, mesuré sur les mêmes pages.

Pourquoi ce fichier a changé de sujet
--------------------------------------
Sa version d'origine épinglait l'id partagé en dur et portait un
``xfail(strict=True)``. Elle avait aussi écrit son propre garde-fou : « le
jour où les ids cessent de se recouper — parce qu'on les aura rendus
page-dépendants, ce qui serait la bonne correction — ce fichier n'a plus
de sujet et doit le DIRE, pas passer en silence sur deux éléments
introuvables ». C'est exactement ce qui s'est produit, et il l'a dit.

Il garde donc désormais le COMPORTEMENT plutôt que la collision : peu
importe comment les ids sont formés, ouvrir un accordéon sur une page ne
doit rien changer à l'autre. Les ids sont découverts au rendu, plus
épinglés — sinon le prochain changement de forme rendrait ce fichier
muet au lieu de le faire rougir.

Son jumeau rapide, ``tests/consistency/test_no_two_pages_share_a_scope``,
compte les collisions sans navigateur et tourne à chaque commit.

Lourd (uvicorn + Chromium) — à lancer explicitement ::

    py -m pytest tests/runtime_js/test_boost_nav_does_not_share_state.py -q -m browser
"""

from __future__ import annotations

import pytest

from tests.audit.harness import audit_server, browser_page

pytestmark = pytest.mark.browser

#: Les deux pages du playground qui portent toutes deux un accordéon à la
#: même place — c'est ce qui produisait la collision.
_PAGE_A = "/accordion"
_PAGE_B = "/markdown"

#: Le premier accordéon de la page, avec son id RÉEL.
#:
#: ⚠️ Découvert et non épinglé. La version d'origine codait l'id en dur ;
#: le fix l'a change, et le fichier est devenu faux au lieu de devenir
#: vert. Un test qui pointe une adresse fixe meurt du fix qu'il attendait.
#:
#: ⚠️ Même leçon, un cran plus bas : le sélecteur a cherché
#: ``bz-data*="expanded"`` jusqu'au 2026-09-07, donc il désignait un
#: accordéon par le NOM DE SA CLÉ DE VALEUR — un nom qui n'a rien à voir
#: avec « être un accordéon », et qui a changé le jour où les treize clés
#: de scope se sont normalisées en ``value``. L'ancre est maintenant le
#: slab runtime que l'accordéon étale, ``$bz.accordion``, qui EST son
#: identité. (Il a rougi, pas verdi : le cas gardé disparaissait, et le
#: harnais le dit — contrairement à une assertion négative.)
_FIRST_ACCORDION = """
() => {
  const root = document.querySelector('[bz-id][bz-data*="$bz.accordion"]');
  if (!root) return {error: 'aucun accordeon sur ' + location.pathname};
  const head = root.querySelector('[aria-expanded]');
  return {
    id: root.getAttribute('bz-id'),
    url: location.pathname,
    expanded: head ? head.getAttribute('aria-expanded') : null,
  };
}
"""

_TOGGLE_FIRST = """
() => {
  const root = document.querySelector('[bz-id][bz-data*="$bz.accordion"]');
  if (!root) return {error: 'aucun accordeon'};
  const head = root.querySelector('[aria-expanded]');
  if (!head) return {error: 'aucun en-tete'};
  const before = head.getAttribute('aria-expanded');
  head.click();
  return {before: before};
}
"""

_CLICK_LINK = """
(href) => {
  const link = document.querySelector('a[href="' + href + '"]');
  if (!link) return false;
  link.click();
  return true;
}
"""


@pytest.fixture(scope="module")
def base_url():
    with audit_server() as url:
        yield url


def test_the_two_pages_no_longer_share_that_id(base_url: str) -> None:
    """Le fix, vu de l'exterieur : deux accordeons, deux ids.

    C'est le CONTROLE POSITIF du fichier. S'il rougissait, ce serait que
    la qualification par page a saute — et tout ce que les tests suivants
    disent redeviendrait faux sans qu'ils le voient.
    """
    vu = {}
    for path in (_PAGE_A, _PAGE_B):
        with browser_page(base_url, path) as page:
            page.wait_for_function("() => !!window.$bz")
            vu[path] = page.evaluate(_FIRST_ACCORDION)

    for path, row in vu.items():
        assert "error" not in row, f"{path} : {row.get('error')}"

    a, b = vu[_PAGE_A]["id"], vu[_PAGE_B]["id"]
    assert a != b, (
        f"les deux pages emettent encore le MEME bz-id ({a!r}) : la "
        f"qualification par page a saute, et le magasin de scopes du "
        f"runtime rendra a l'une l'etat de l'autre."
    )


def test_an_accordion_opened_on_one_page_stays_closed_on_the_other(
    base_url: str,
) -> None:
    """Le comportement, bout en bout, avec une VRAIE navigation boostee.

    La reference est la meme page atteinte au chargement direct, jamais
    une valeur ecrite en dur — c'est ce que l'utilisateur fait pour
    contourner ce genre de bug (F5), donc c'est la formulation la plus
    fidele de ce qui doit tenir.
    """
    with browser_page(base_url, _PAGE_B) as page:
        page.wait_for_function("() => !!window.$bz")
        frais = page.evaluate(_FIRST_ACCORDION)
        assert "error" not in frais, frais

    with browser_page(base_url, _PAGE_A) as page:
        page.wait_for_function("() => !!window.$bz")

        bascule = page.evaluate(_TOGGLE_FIRST)
        assert "error" not in bascule, bascule
        page.wait_for_timeout(150)
        ouvert = page.evaluate(_FIRST_ACCORDION)
        assert ouvert["expanded"] != bascule["before"], (
            f"TEMOIN muet : le clic n'a rien change sur {_PAGE_A} "
            f"({bascule['before']!r} -> {ouvert['expanded']!r}). Le test "
            f"qui suit ne prouverait rien."
        )

        assert page.evaluate(_CLICK_LINK, _PAGE_B), (
            f"aucun lien vers {_PAGE_B} dans la barre laterale — la "
            f"navigation boostee ne peut pas etre exercee"
        )
        page.wait_for_function(
            "(p) => location.pathname === p", arg=_PAGE_B, timeout=5000
        )
        page.wait_for_timeout(300)

        apres = page.evaluate(_FIRST_ACCORDION)
        assert "error" not in apres, apres
        assert apres["expanded"] == frais["expanded"], (
            f"apres navigation, l'accordeon de {_PAGE_B} est dans l'etat "
            f"{apres['expanded']!r} alors qu'un chargement direct le rend "
            f"{frais['expanded']!r}. L'etat client de {_PAGE_A} a fuit : "
            f"le magasin de scopes du runtime est indexe par bz-id, et un "
            f"hx-boost ne le vide pas."
        )
