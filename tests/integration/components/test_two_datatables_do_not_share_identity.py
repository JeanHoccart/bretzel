"""Gate : une zone re-rendue seule revient avec SES ids, pas ceux d'à côté.

C'est l'invariant que la génération d'ids doit à idiomorph, et il est
invisible tant qu'on ne regarde qu'une page entière.

Une zone ``@refreshable`` se re-rend **seule**, dans un contexte de rendu
neuf : les compteurs positionnels d'``IdGenerator`` repartent de zéro. Or
un composant construit pendant ``render()`` — le pager d'un datatable, sa
recherche, ses boutons de barre — n'a aucun parent sur la pile, parce que
le rendu arrive APRÈS la sortie de la zone. Son id vaut donc
``root_<genre>_<n>``, où ``n`` compte **à l'échelle de la page**.

Deuxième table de la page : ``root_pagination_1``. La même table
re-rendue seule : ``root_pagination_0`` — l'id de la PREMIÈRE. Mesuré au
navigateur le 2026-08-07 ::

    avant le clic : ['root_pagination_0', 'root_pagination_1']
    clic page 5 sur la table B
    après le clic : ['root_pagination_0', 'root_pagination_0']

``bz-id`` étant la clé d'appariement d'idiomorph ET celle de
``scope.absorb``, le pager de B adopte le scope de A : il affiche les 7
pages de A au lieu de ses 5, puis l'entrée cachée de A voit sa valeur
changer et POSTe à son tour. **Un clic, deux requêtes, et la mauvaise
table qui navigue.** C'est le symptôme rapporté par l'utilisateur, resté
trois benches sans reproduction faute d'une seconde table sur la page.

**Pourquoi cette gate est ici et pas en unitaire.** Une première version
vivait dans ``tests/consistency/``, montait les zones à la main et
passait avec le fix RETIRÉ — donc ne prouvait rien. La raison est
exactement celle du bug : appeler ``Datatable(...).render()`` dans le
corps de la zone laisse la zone sur la pile des parents, ce que la
production ne fait pas. Il faut le vrai aller-retour — page rendue,
action signée, fragment OOB — pour que le composant se rende là où il se
rend vraiment. Un harnais qui rate le décalage qu'il teste est pire
qu'aucune gate : il rassure.

Le fix vit dans ``Datatable.render`` (``key_segment`` sur le nom de la
classe d'état). La gate teste la CONSÉQUENCE, donc elle reste vraie quel
que soit le mécanisme retenu demain.
"""

from __future__ import annotations

import re

from fastapi.testclient import TestClient

from bretzel import Bretzel, page, refreshable, ui
from bretzel.state import field
from bretzel.components import DatatableState
from bretzel.runtime import HEADER_PAGE_ID
from bretzel.server.handlers import sign_action

_SECRET = "y" * 32

ROWS = [{"id": i, "name": f"n{i}", "score": (i * 7) % 40} for i in range(34)]
COLUMNS = [
    ui.column("name", label="Name", sortable=True),
    ui.column("score", label="Score", sortable=True),
]


class FirstQuery(DatatableState):
    """34 lignes / 5 → 7 pages."""

    per_page: int = field(default=5)


class SecondQuery(DatatableState):
    """Les MÊMES lignes / 8 → 5 pages. Deux tailles de pager, donc une
    fuite d'identité se lit à l'œil nu."""

    per_page: int = field(default=8)


_app = Bretzel(secret_key=_SECRET, mode="dev")


@refreshable(deps=[FirstQuery])
def first_zone() -> None:
    ui.datatable(state=FirstQuery, columns=COLUMNS, rows=ROWS)


@refreshable(deps=[SecondQuery])
def second_zone() -> None:
    ui.datatable(state=SecondQuery, columns=COLUMNS, rows=ROWS)


@page("/")
def home() -> None:
    first_zone()
    second_zone()


_app.include(home)


# ── Helpers ───────────────────────────────────────────────────────────

_BZ_ID = re.compile(r'(?<![\w:-])bz-id="([^"]+)"')


def _ids(html: str) -> list[str]:
    return _BZ_ID.findall(html)


def _page_id(html: str) -> str:
    # ``data-bretzel-page-id`` et pas le JSON d'``hx-headers`` : les
    # deux portent la MÊME valeur, mais l'attribut nu est stable
    # tandis que le JSON dépend de son échappement — quatre copies de
    # cette ligne ont rougi le 2026-08-28 quand ``hx-headers`` est
    # passé en doubles quotes, sans qu'aucun comportement ne change.
    match = re.search(r'data-bretzel-page-id="([^"]+)"', html)
    assert match, "le shell doit publier l'id de page"
    return match.group(1)


def _pager_action(html: str, state_name: str) -> tuple[str, str]:
    """``(url, args)`` du ``go_to_page`` de la table nommée.

    Le pager relocalise son bundle HTMX sur son ``<input>`` caché, dont
    le ``name`` porte le nom de la classe d'état — c'est ce qui permet de
    désigner UNE des deux tables sans dépendre de l'ordre du document.
    """
        # La fenêtre s'arrête au PREMIER ``>`` — la fin de la balise —
        # et non à N caractères. Une fenêtre fixe déborde sur le balisage
        # suivant : celle de 2 500 caractères posée ici au départ voyait
        # « SecondQuery » dans la queue du pager de la PREMIÈRE table et
        # rendait son action à sa place. Le test passait par chance, et a
        # rougi le jour où un octet a bougé ailleurs. Les ``>`` des
        # valeurs d'attribut sont échappés en ``&gt;``, donc le premier
        # ``>`` brut est bien la fin de la balise.
    for chunk in html.split("<input")[1:]:
        head = chunk.split(">", 1)[0]
        if "go_to_page" not in head or state_name not in head:
            continue
        url = re.search(r'hx-post="([^"]+)"', head)
        args = re.search(r"_args&quot;: &quot;([^&]*)&quot;", head)
        if url and args:
            return url.group(1), args.group(1)
    raise AssertionError(f"pas de go_to_page pour {state_name!r}")


def _post(client: TestClient, url: str, args: str, page_id: str, form: dict):
    action_id = url.rsplit("/", 1)[-1]
    return client.post(
        url,
        headers={
            "X-Bz-Sig": sign_action(_app.config._action_key, action_id, args),
            HEADER_PAGE_ID: page_id,
        },
        data={"_args": args, **form},
    )


# ── La gate ───────────────────────────────────────────────────────────


def test_the_second_table_comes_back_with_its_own_ids() -> None:
    with TestClient(_app) as client:
        full = client.get("/").text
        pagers = re.findall(r'bz-id="([^"]*pagination[^"]*)"', full)
        assert len(pagers) == 2, pagers
        assert pagers[0] != pagers[1], (
            f"les deux pagers de la PAGE portent déjà le même id : {pagers}"
        )

        url, args = _pager_action(full, "SecondQuery")
        response = _post(client, url, args, _page_id(full),
                         {"bz_dt_page__SecondQuery": "3"})
        assert response.status_code == 200, response.text[:400]

        returned = set(_ids(response.text))
        assert pagers[1] in returned, (
            f"la zone re-rendue seule ne ramène pas son propre pager "
            f"({pagers[1]}) — elle a renvoyé {sorted(returned)[:6]}. Un "
            f"composant construit pendant `render()` n'a pas de parent "
            f"sur la pile : son id est positionnel et GLOBAL À LA PAGE, "
            f"donc il change quand la zone se rend seule. Il lui faut "
            f"une identité qui ne dépende pas de la page — cf. "
            f"`key_segment` dans `Datatable.render`."
        )
        assert pagers[0] not in returned, (
            f"la zone de la DEUXIÈME table est revenue avec le pager de "
            f"la PREMIÈRE ({pagers[0]}). idiomorph apparie par `bz-id` et "
            f"`scope.absorb` retrouve un scope par `bz-id` : la table B "
            f"adopte alors le scope de A — son nombre de pages — et "
            f"l'entrée cachée de A, se voyant changer, POSTe à son tour. "
            f"Un clic, deux requêtes, et la mauvaise table qui navigue."
        )


def test_the_first_table_is_not_privileged_either() -> None:
    """La contre-épreuve. Sans elle, un « fix » qui donnerait à toutes
    les tables l'identité de la première passerait le test ci-dessus."""
    with TestClient(_app) as client:
        full = client.get("/").text
        pagers = re.findall(r'bz-id="([^"]*pagination[^"]*)"', full)

        url, args = _pager_action(full, "FirstQuery")
        response = _post(client, url, args, _page_id(full),
                         {"bz_dt_page__FirstQuery": "4"})
        assert response.status_code == 200, response.text[:400]

        returned = set(_ids(response.text))
        assert pagers[0] in returned and pagers[1] not in returned, (
            f"attendu {pagers[0]} seul ; reçu {sorted(returned)[:6]}"
        )


def test_the_two_zones_share_no_id_at_all() -> None:
    """Au-delà du pager : recherche, boutons de barre, cellules. Tout ce
    que la table construit pendant son rendu appartient à cette famille.
    """
    with TestClient(_app) as client:
        html = client.get("/").text
    zones = re.split(r'bz-id="(?=refresh_)', html)
    assert len(zones) >= 3, "les deux zones doivent être repérables"
    first, second = set(_ids(zones[1])), set(_ids(zones[2]))
    assert first and second
    assert not (first & second), sorted(first & second)[:5]


def test_the_probe_is_not_vacuous() -> None:
    """Une page sans `bz-id` ferait passer tout ce fichier en comparant
    des ensembles vides."""
    with TestClient(_app) as client:
        ids = _ids(client.get("/").text)
    assert len(ids) >= 6, ids
