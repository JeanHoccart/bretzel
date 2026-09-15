"""Gate : chaque page des exemples RÉPOND, et répond 200.

Le trou que ça bouche est mesuré, pas supposé. Le 2026-08-07, la suite
rapide était verte sur **10 957 tests** pendant que deux pages du
playground renvoyaient une 500 en production :

- ``/datatable`` — un ``ui.datatable`` sorti de la zone qui surveille son
  état, refusé par le garde de construction du composant ;
- ``/app-map`` — un ``:class`` Alpine, refusé depuis la V3.

Aucun test ne les a vues, parce qu'aucun ne RENDAIT une page. Ce qui
existait s'arrêtait au seuil :

- ``test_fixture_apps_import`` **importe** les modules — il attrape une
  erreur d'import, jamais une erreur de rendu ;
- ``test_playground_demos_the_api`` **lit la source** en AST — il sait
  qu'un paramètre est écrit, pas qu'il rend ;
- la suite ``visual`` et les probes rendent pour de vrai, mais ils
  tournent **à part** (navigateur), donc pas sur un ``pytest`` courant.

Une page cassée est pourtant la panne la plus grossière qui soit, et la
plus facile à introduire : elle ne demande qu'un déplacement de zone ou
une directive d'une V précédente.

**Coût mesuré : 2,2 s pour 63 pages** (~35 ms la page). C'est assez peu
cher pour vivre dans la suite rapide — d'où sa place ici et non dans les
suites navigateur.

⚠️ Ce que la gate NE dit pas : que la page est JUSTE. Un 200 prouve que
le rendu s'est terminé, pas que la mise en page tient ni que les
handlers marchent. C'est le plancher, et il n'existait pas.
"""

from __future__ import annotations

import importlib
import pkgutil
import re
from collections import Counter

import pytest
from starlette.testclient import TestClient


def _playground_paths() -> list[str]:
    """Les chemins déclarés par les features, découverts et non listés.

    Une liste écrite à la main ne couvrirait que ce qu'on a pensé à y
    mettre — et la page suivante naîtrait hors gate.
    """
    import examples.playground.features as features

    paths: set[str] = set()
    for mod_info in pkgutil.iter_modules(features.__path__):
        module = importlib.import_module(
            f"examples.playground.features.{mod_info.name}"
        )
        path = getattr(module, "PATH", None)
        if isinstance(path, str):
            paths.add(path)
    return sorted(paths)


PLAYGROUND_PATHS = _playground_paths()


@pytest.fixture(scope="module")
def playground_client():
    from examples.playground.main import app

    # ``raise_server_exceptions=False`` : on veut le CODE, pas une
    # exception qui interrompt le paramétrage au premier échec. Sans ça
    # la première page cassée masque toutes les suivantes, et on répare
    # en aveugle, une par une.
    with TestClient(app, raise_server_exceptions=False) as client:
        yield client


@pytest.mark.parametrize("path", PLAYGROUND_PATHS)
def test_playground_page_renders(playground_client, path: str) -> None:
    response = playground_client.get(path)
    assert response.status_code == 200, (
        f"{path} renvoie {response.status_code}. Une page du playground "
        f"qui ne rend pas n'est vue par AUCUNE autre suite : les tests "
        f"d'import s'arrêtent à l'import, les gates de surface lisent "
        f"l'AST, et les suites navigateur tournent à part. Lance "
        f"`py -c \"from starlette.testclient import TestClient; "
        f"from examples.playground.main import app; "
        f"TestClient(app).get('{path}')\"` pour la trace complète."
    )


# ── Un ``bz-id`` par element, jamais deux ─────────────────────────────
#
# ``bz-id`` est la cle de DEUX mecanismes : celle par laquelle idiomorph
# apparie les noeuds apres un swap, et celle par laquelle
# ``scope.absorb`` retrouve un scope client. Deux elements qui la
# partagent, c'est un menu qui s'ouvre a la place d'un autre et un
# sous-arbre remplace au lieu d'etre fusionne — sans erreur, sans trace.
#
# Trouve le 2026-08-07 en cherchant pourquoi un pager restait dans un
# etat incoherent : ``/datatable`` portait SIX valeurs en double, dont
# ``root_dropdown_100`` sur NEUF elements — un par tableau affichant la
# ligne d'id 100. Cause : un composant ne dans un ``render=`` de cellule
# n'a aucun parent sur la pile, donc son id se reduisait a
# ``root_<kind>_<cle de ligne>``. Reparé par ``key_segment`` dans
# ``Table.render``.
#
# ``re`` et non un parseur : ``bz-attr:id`` est une LIAISON reactive
# (``bz-attr:id="t.id"`` dans un template ``bz-for``), pas un
# identifiant — le garde ``(?<![\w:-])`` l'exclut. Une premiere version
# de cette sonde le comptait comme un doublon et m'a fait annoncer un
# bug qui n'existait pas.
_BZ_ID = re.compile(r'(?<![\w:-])bz-id="([^"]+)"')

#: Plus de dette declaree : la gate exige ZERO doublon partout.
#:
#: Elle a porte ``{"/dialog": 3}`` pendant une journee, avec une piste
#: fausse (« le panneau teleporte est rendu deux fois »). Le vrai
#: coupable etait la branche keyed d'``IdGenerator``, qui rendait
#: ``{parent}_{kind}_{cle}`` sans compteur : trois freres du meme genre
#: sous une meme cle recevaient un seul id. Trois boutons d'un dialogue
#: la-bas, trois ``dropdown_item`` d'une cellule ici — meme cause, un
#: seul fix, et la ligne de dette s'est effacee toute seule.


@pytest.mark.parametrize("path", PLAYGROUND_PATHS)
def test_page_has_no_duplicate_bz_id(playground_client, path: str) -> None:
    html = playground_client.get(path).text
    dupes = {k: n for k, n in Counter(_BZ_ID.findall(html)).items() if n > 1}
    assert not dupes, (
        f"{path} : {len(dupes)} valeur(s) de `bz-id` en double — "
        f"{list(dupes.items())[:3]}. "
        f"C'est la cle qu'idiomorph utilise pour apparier apres un swap "
        f"et que `scope.absorb` utilise pour retrouver un scope : deux "
        f"elements qui la partagent produisent des swaps erratiques, "
        f"sans erreur ni trace. Deux causes vues : un composant ne dans "
        f"un `render=` de cellule dont le conteneur ne pousse pas son "
        f"identite (cf. `key_segment` dans `Table.render`), et des freres "
        f"du meme genre sous une meme cle d'iteration (cf. la branche "
        f"keyed d'`IdGenerator.next`)."
    )


#: L'``id`` HTML, pas le ``bz-id``. Même garde ``(?<![\w:-])`` pour exclure
#: ``bz-attr:id`` (une liaison réactive, pas un identifiant).
_HTML_ID = re.compile(r'(?<![\w:-])id="([^"]+)"')

#: Dette MESURÉE le 2026-08-15 : 1 page sur 74. L'id se répète sur trois
#: lignes d'une table — même famille que le défaut ``key_segment`` déjà
#: documenté plus haut (un conteneur qui ne pousse pas son identité), et
#: antérieure à cette gate. Déclarée plutôt que tolérée en silence :
#: chantier dans ``.claude/work/todo.md``.
_HTML_ID_DEBT: dict[str, int] = {"/sparkline": 1}


@pytest.mark.parametrize("path", PLAYGROUND_PATHS)
def test_page_has_no_duplicate_html_id(playground_client, path: str) -> None:
    """Le pendant du test ci-dessus, sur l'``id`` HTML — et il manquait.

    ``bz-id`` et ``id`` sont DEUX identités, gardées par deux mécanismes.
    Celle-ci est celle que résout ``document.getElementById``, donc celle
    par laquelle passe toute l'API impérative : ``sb.toggle()`` compile en
    ``document.getElementById('<id>').dispatchEvent(...)``.

    Deux nœuds portant le même ``id`` = ``getElementById`` renvoie le
    PREMIER. Si l'écouteur est sur le second, le bouton ne fait rien — pas
    d'erreur, pas de trace, et l'état comme le rendu restent corrects, ce
    qui envoie chercher partout ailleurs.

    Mesuré le 2026-08-15 : en donnant une racine ``display:contents`` à
    ``ui.sidebar``, le socle a estampillé l'``id`` du composant sur cette
    racine (``_stamp_scope_id`` le fait pour tout hôte de ``bz-data`` sans
    ``id``) alors que l'aside le portait déjà. Le hamburger a cessé
    d'ouvrir le menu, deux fois de suite, et AUCUNE gate ne l'a vu : celle
    des ``bz-id`` ne couvre pas les ``id``, et rien ne cliquait.
    """
    html = playground_client.get(path).text
    dupes = {k: n for k, n in Counter(_HTML_ID.findall(html)).items() if n > 1}
    allowed = _HTML_ID_DEBT.get(path, 0)
    assert len(dupes) <= allowed, (
        f"{path} : {len(dupes)} valeur(s) d'`id` HTML en double (dette "
        f"déclarée : {allowed}) — {list(dupes.items())[:3]}.\n\n"
        f"C'est l'identite que resout `document.getElementById`, donc "
        f"celle de toute l'API imperative (`.open()` / `.close()` / "
        f"`.toggle()`). Deux noeuds qui la partagent : le premier gagne, "
        f"et si l'ecouteur est sur l'autre le controle devient inerte "
        f"sans rien signaler."
    )


def test_the_sweep_is_not_vacuous() -> None:
    """Une découverte qui rendrait zéro chemin passerait en silence."""
    assert len(PLAYGROUND_PATHS) >= 50, PLAYGROUND_PATHS


def test_the_declared_html_id_debt_is_still_real() -> None:
    """Une dette déclarée qui a disparu doit être RETIRÉE, pas oubliée.

    Sans ce test, la ligne ``{"/sparkline": 1}`` survivrait à sa cause et
    autoriserait pour toujours un doublon que plus personne n'aurait — le
    mode d'échec exact d'une allowlist qu'on n'audite jamais.
    """
    from starlette.testclient import TestClient

    from examples.playground.main import app

    with TestClient(app, raise_server_exceptions=False) as client:
        for path, expected in _HTML_ID_DEBT.items():
            html = client.get(path).text
            found = len({
                k for k, n in Counter(_HTML_ID.findall(html)).items() if n > 1
            })
            assert found == expected, (
                f"la dette declaree pour {path} vaut {expected} mais on en "
                f"mesure {found}. Si c'est 0, retirer la ligne de "
                f"_HTML_ID_DEBT — la dette est payee."
            )
