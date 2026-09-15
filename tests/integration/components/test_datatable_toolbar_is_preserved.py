"""Gate : changer de page ne renvoie pas la barre d'outils.

La barre pèse **44 %** de la zone — 35 Ko sur 79, mesuré sur un datatable
de cinq lignes avec trois filtres — et **aucun de ses octets ne dépend de
``page``**. Elle repartait pourtant sur le fil à chaque clic de
pagination, parce qu'une zone ``@refreshable`` se re-rend entière.

Le remède est ``hx-preserve`` : HTMX garde le nœud vivant et ignore
celui qui arrive, donc on envoie une coquille vide. Mesuré au navigateur
sur ``/datatable_solo`` : **92 Ko → 56 Ko** par changement de page, la
barre intacte dans le DOM (5 enfants, 3 filtres, export), zéro erreur JS.

**Le mode d'échec que cette gate garde est catastrophique, pas cosmétique.**
Si l'``id`` de la coquille ne correspond pas à celui de la barre vivante,
``hx-preserve`` ne préserve rien : le morph applique une div VIDE et la
barre — recherche, filtres, export — **disparaît de la page**. C'est
pourquoi `test_the_stub_matches_the_live_toolbar_id` existe et compare
les deux ids octet pour octet plutôt que de vérifier la seule présence de
l'attribut.

**Et la condition doit rester étroite.** Préserver quand la recherche ou
un filtre a bougé afficherait un état périmé — la valeur tapée absente,
le filtre actif non coloré, le bouton « Clear » manquant. D'où les tests
de contre-épreuve : un changement de recherche DOIT ramener la barre
complète.

**Ce à quoi la barre est aveugle DÉPEND de la table.** C'est
``Datatable._toolbar_blind_to()`` qui l'établit, et c'était une constante
— ``{"page"}`` — jusqu'au 2026-08-28. Elle décrivait une table
EXPORTABLE : l'URL signée du bouton CSV sérialise
``to_query(for_export=True)``, qui porte le tri et la taille de page.
``page`` seule y est normalisée à 1, et c'est ce qui rendait la
pagination préservable.

Sans bouton CSV — le cas par défaut, ``exportable=False`` — la barre ne
lit ni le tri ni la taille de page : rien n'y peint autre chose que la
valeur du champ de recherche et les étiquettes des filtres. Elle
repartait pourtant entière à chaque clic d'en-tête. Mesuré sur le
``Tickets`` de ce fichier : **12 257 octets identiques à l'octet près**
renvoyés pour un tri.

D'où les deux contre-épreuves symétriques ci-dessous : sans export un
tri PRÉSERVE, avec export il RENVOIE. La seconde est ce qui empêche
d'élargir l'ensemble aveugle jusqu'à geler une URL signée périmée.
"""

from __future__ import annotations

import re

import pytest
from fastapi.testclient import TestClient

from bretzel import Bretzel, page, refreshable, ui
from bretzel.components import DatatableState
from bretzel.components.base.testing import render_isolated
from bretzel.components.data.datatable import Datatable
from bretzel.core.serialize import serialize
from bretzel.runtime import HEADER_PAGE_ID
from bretzel.server.handlers import sign_action
from bretzel.state import MemoryBackend, field
from bretzel.state.registry import StateRegistry, use_registry

_SECRET = "z" * 32

ROWS = [{"id": i, "name": f"n{i}", "status": ["open", "merged", "closed"][i % 3]}
        for i in range(34)]
COLUMNS = [
    ui.column("name", label="Name", sortable=True),
    ui.column("status", label="Status", sortable=True,
              filter=["open", "merged", "closed"]),
]


class Tickets(DatatableState):
    per_page: int = field(default=5)


# ── La table EXPORTABLE ───────────────────────────────────────────────
#
# L'export exige le tier CALLABLE : le CSV doit contenir toutes les
# lignes qui matchent, donc le serveur rejoue la requête hors du rendu
# qui a produit la page — une liste n'existe plus à ce moment-là. Et un
# ``filter=True`` n'a alors plus de rows où découvrir son domaine, d'où
# le domaine explicite.


class Priced(DatatableState):
    per_page: int = field(default=5)


PRICED_COLUMNS = [
    ui.column("name", label="Name", sortable=True),
    ui.column("status", label="Status", sortable=True,
              filter=["open", "merged", "closed"]),
]


def load_priced(query):
    from bretzel.components import apply_query

    return apply_query(ROWS, PRICED_COLUMNS, query)


_app = Bretzel(secret_key=_SECRET, mode="dev")


@refreshable(deps=[Tickets])
def tickets_zone() -> None:
    ui.datatable(state=Tickets, columns=COLUMNS, rows=ROWS)


@page("/")
def home() -> None:
    tickets_zone()


@refreshable(deps=[Priced])
def priced_zone() -> None:
    ui.datatable(state=Priced, columns=PRICED_COLUMNS, rows=load_priced,
                 exportable=True)


@page("/exportable")
def exportable_home() -> None:
    priced_zone()


_app.include(home, exportable_home)


# ── Helpers ───────────────────────────────────────────────────────────

_TOOLBAR_ID = re.compile(r'id="(bzdt_\w+_toolbar)"')


def _page_id(html: str) -> str:
    # ``data-bretzel-page-id`` et pas le JSON d'``hx-headers`` : les
    # deux portent la MÊME valeur, mais l'attribut nu est stable
    # tandis que le JSON dépend de son échappement — quatre copies de
    # cette ligne ont rougi le 2026-08-28 quand ``hx-headers`` est
    # passé en doubles quotes, sans qu'aucun comportement ne change.
    match = re.search(r'data-bretzel-page-id="([^"]+)"', html)
    assert match, "le shell doit publier l'id de page"
    return match.group(1)


def _action(html: str, handler: str, tag: str) -> tuple[str, str]:
        # La fenêtre s'arrête au PREMIER ``>`` — la fin de la balise —
        # et non à N caractères. Une fenêtre fixe déborde sur le balisage
        # suivant : celle de 2 500 caractères posée ici au départ voyait
        # « SecondQuery » dans la queue du pager de la PREMIÈRE table et
        # rendait son action à sa place. Le test passait par chance, et a
        # rougi le jour où un octet a bougé ailleurs. Les ``>`` des
        # valeurs d'attribut sont échappés en ``&gt;``, donc le premier
        # ``>`` brut est bien la fin de la balise.
    for chunk in html.split(f"<{tag}")[1:]:
        head = chunk.split(">", 1)[0]
        if handler not in head:
            continue
        url = re.search(r'hx-post="([^"]+)"', head)
        args = re.search(r"_args&quot;: &quot;([^&]*)&quot;", head)
        if url and args:
            return url.group(1), args.group(1)
    raise AssertionError(f"pas d'action {handler!r} sur <{tag}>")


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


def _go_to_page(client: TestClient, html: str, n: int, state: str = "Tickets"):
    # ``state`` : le nom de champ du pager est suffixé par la classe
    # d'état (``_field()``), pour que deux tables d'une même page ne
    # lisent pas la soumission l'une de l'autre. Le poster en dur ferait
    # lire ``None`` au handler, qui sortirait sans muter — donc un 204 et
    # un corps vide, ce qui ressemble beaucoup à « rien à re-rendre ».
    url, args = _action(html, "go_to_page", "input")
    return _post(client, url, args, _page_id(html),
                 {f"bz_dt_page__{state}": str(n)})


def _built(**kwargs) -> Datatable:
    """Une instance de ``Datatable``, construite dans une VRAIE zone.

    Le composant refuse de se construire hors d'un ``@refreshable`` qui
    surveille son état — c'est son garde central, et le contourner
    testerait autre chose que ce qui tourne.
    """
    box: list[Datatable] = []

    @refreshable(deps=[kwargs["state"]])
    def zone() -> None:
        box.append(Datatable(**kwargs))

    zone()
    return box[0]


# ── La gate ───────────────────────────────────────────────────────────


def test_a_page_change_does_not_resend_the_toolbar() -> None:
    with TestClient(_app) as client:
        full = client.get("/").text
        assert "bzf_Tickets_status" in full, "la page complète doit porter le filtre"

        body = _go_to_page(client, full, 3).text
        assert "hx-preserve" in body, (
            "la barre n'est pas préservée : elle repart en entier à chaque "
            "clic de pagination alors qu'aucun de ses octets ne dépend de "
            "`page`. Cf. `Datatable._toolbar_can_be_preserved`."
        )
        assert "bzf_Tickets_status" not in body, (
            "le filtre de colonne est TOUJOURS dans la réponse — la "
            "coquille est émise mais son contenu aussi, donc l'économie "
            "est nulle."
        )
        assert 'name="bz_dt_search__Tickets"' not in body, (
            "la recherche est toujours renvoyée"
        )


def test_the_stub_matches_the_live_toolbar_id() -> None:
    """Le test qui compte. Un id qui diverge fait DISPARAÎTRE la barre.

    ``hx-preserve`` ne s'applique qu'à l'élément de même ``id`` déjà
    présent. Si la coquille en porte un autre, le morph insère une div
    vide : recherche, filtres et export s'évaporent, sans erreur.
    """
    with TestClient(_app) as client:
        full = client.get("/").text
        live = _TOOLBAR_ID.findall(full)
        assert len(live) == 1, f"attendu un id de barre, trouvé {live}"

        body = _go_to_page(client, full, 2).text
        stub = _TOOLBAR_ID.findall(body)
        assert stub == live, (
            f"la coquille porte {stub}, la barre vivante {live}. "
            f"`hx-preserve` ne s'applique qu'à un id DÉJÀ présent : "
            f"divergents, le morph remplace la barre par une div vide et "
            f"recherche / filtres / export disparaissent de la page."
        )


def test_a_search_change_does_resend_the_toolbar() -> None:
    """Contre-épreuve. Sans elle, « ne jamais rien renvoyer » passerait
    le test du haut tout en gelant un état périmé à l'écran."""
    with TestClient(_app) as client:
        full = client.get("/").text
        url, args = _action(full, "search_for", "input")
        body = _post(client, url, args, _page_id(full),
                     {"bz_dt_search__Tickets": "n1"}).text
        assert "bzf_Tickets_status" in body, (
            "la recherche a changé : la barre DOIT revenir complète — sa "
            "valeur tapée s'y affiche, et le bouton « Clear filters » "
            "apparaît ou disparaît avec `state.filters`."
        )
        assert 'value="n1"' in body
        assert "hx-preserve" not in body, (
            "la barre COMPLÈTE part avec `hx-preserve`. HTMX lit "
            "l'attribut sur le nœud qui ARRIVE et garde alors l'ANCIEN : "
            "la barre fraîche est ignorée, donc « Clear filters » "
            "n'apparaît jamais et le filtre actif ne se colore pas. "
            "L'attribut n'appartient qu'à la coquille."
        )


def test_a_sort_change_preserves_a_toolbar_with_no_export() -> None:
    """Sans bouton CSV, un tri ne change pas UN OCTET de la barre.

    ``Tickets`` n'est pas exportable — ``exportable=False`` est le
    défaut, et ``rows=`` est une liste, ce que l'export refuse. Rien
    dans sa barre ne peint le tri : ni la recherche, ni les étiquettes
    de filtre, ni le bouton « Clear ». Elle repartait pourtant entière à
    chaque clic d'en-tête.
    """
    with TestClient(_app) as client:
        full = client.get("/").text
        url, args = _action(full, "sort_by", "button")
        body = _post(client, url, args, _page_id(full), {}).text
        assert "hx-preserve" in body, (
            "la barre repart en entier sur un tri alors qu'aucun de ses "
            "octets n'en dépend : cette table n'a pas de bouton CSV, donc "
            "rien n'y sérialise `sort_key`."
        )
        assert "bzf_Tickets_status" not in body


def test_a_sort_change_does_resend_an_exportable_toolbar() -> None:
    """Avec un bouton CSV, ``sort_key`` change son URL SIGNÉE.

    La contre-épreuve qui borne l'élargissement. Sans elle, « aveugle au
    tri » se généraliserait à toutes les tables et le lecteur
    téléchargerait un CSV trié comme il l'était deux clics plus tôt — une
    faute silencieuse, dans un fichier qu'il ouvre ailleurs.
    """
    with TestClient(_app) as client:
        full = client.get("/exportable").text
        assert "bzf_Priced_status" in full
        url, args = _action(full, "sort_by", "button")
        body = _post(client, url, args, _page_id(full), {}).text
        assert "hx-preserve" not in body, (
            "la barre d'une table EXPORTABLE est préservée sur un tri : "
            "l'URL signée du bouton CSV reste celle du tri précédent, "
            "donc le fichier téléchargé ne correspond plus à l'écran."
        )
        assert "bzf_Priced_status" in body


#: Les six champs de :class:`DatatableState`, et une valeur qui les change
#: vraiment. Une valeur égale au défaut ferait passer la gate par le vide.
_FIELD_PROBES = {
    "sort_key": "name",
    "sort_dir": "desc",
    "page": 3,
    "per_page": 2,
    "search": "n1",
    "filters": {"status": ["open"]},
}


#: L'HORLOGE, retirée avant toute comparaison. ``data-bz-ts`` est un
#: horodatage en SECONDES et ``data-bz-sig`` est calculée dessus, donc les
#: deux tournent ensemble à chaque seconde qui passe.
#:
#: ⚠️ Sans ça, cette gate est fausse une fois sur N, et le N dépend de la
#: charge de la machine. Mesuré le 2026-08-29 : deux rendus consécutifs
#: sont identiques, deux rendus séparés de 1,2 s ne le sont pas — aucun
#: champ n'ayant bougé. En parallèle (``-n 4``), les trois rendus que fait
#: ce test s'étalent assez pour qu'un tic tombe entre deux, et un champ
#: DÉCLARÉ AVEUGLE se lit alors comme sensible. C'est ce qui faisait
#: passer ce fichier pour un membre de la famille « dépendance à l'ordre »
#: — il n'en était pas : il dépend de l'heure.
#:
#: Neutraliser la signature ne rend la gate aveugle à rien : elle couvre
#: le chemin d'action et le blob ``_args`` (la CLASSE d'état), jamais la
#: valeur d'un champ. Ce qu'un champ change reste visible ailleurs dans
#: les octets — la valeur du champ de recherche, les étiquettes de
#: filtre, la requête de l'URL d'export.
_HORLOGE = re.compile(r'data-bz-(ts|sig)="[^"]*"')


def _toolbar_bytes(built, **mutation) -> str:
    """Les octets de la barre, rendue dans un CONTEXTE NEUF.

    Trois précautions, chacune pour une façon de rendre la gate fausse :

    - **un contexte de rendu NEUF**, sinon le compteur d'ids monte d'un
      appel à l'autre et deux barres rigoureusement identiques se lisent
      comme différentes — la gate dirait « sensible à tout » ;
    - **un registre d'état NEUF**, sinon la mutation du champ précédent
      survit — et sans registre du tout, elle ne survivrait même pas
      jusqu'au rendu, donc TOUT se lirait comme aveugle ;
    - **l'horloge retirée**, cf. :data:`_HORLOGE`.
    """
    with use_registry(StateRegistry(MemoryBackend())):
        with render_isolated():
            state = built["state"]()
            for name, value in mutation.items():
                setattr(state, name, value)
            table = _built(**built)
            return _HORLOGE.sub("", serialize(table.render().children[0]))


@pytest.mark.parametrize("field", sorted(_FIELD_PROBES))
@pytest.mark.parametrize("exportable", [False, True], ids=["plain", "export"])
def test_the_declared_reads_match_the_bytes(field: str, exportable: bool) -> None:
    """La gate qui empêche les deux ensembles déclarés de pourrir.

    ``_TOOLBAR_READS`` et ``_EXPORT_READS`` sont écrits à la main, donc
    ils dérivent — quelqu'un ajoute un contrôle qui lit ``per_page``, et
    la barre est préservée alors qu'elle a changé, ce qui gèle un état
    périmé à l'écran sans erreur ni trace.

    Ici on ne relit pas la liste : on **mute le champ et on compare les
    octets**. Aveugle et identique doivent coïncider exactement, dans les
    deux sens.
    """
    built = (
        {"state": Priced, "columns": PRICED_COLUMNS, "rows": load_priced,
         "exportable": True}
        if exportable else
        {"state": Tickets, "columns": COLUMNS, "rows": ROWS}
    )
    with render_isolated():
        blind = _built(**built)._toolbar_blind_to()

    base = _toolbar_bytes(built)
    assert base == _toolbar_bytes(built), (
        "deux rendus identiques diffèrent déjà — la mesure est bruitée, "
        "et tout ce que cette gate dira ensuite est faux"
    )
    unchanged = _toolbar_bytes(built, **{field: _FIELD_PROBES[field]}) == base

    if field in blind:
        assert unchanged, (
            f"`{field}` est déclaré aveugle, mais changer sa valeur change "
            f"la barre. Elle sera PRÉSERVÉE alors qu'elle a bougé : le "
            f"lecteur garde à l'écran un contrôle périmé, sans erreur ni "
            f"trace. Retire-le de _TOOLBAR_READS / _EXPORT_READS."
        )
    else:
        assert not unchanged, (
            f"`{field}` n'est pas déclaré aveugle, mais la barre est "
            f"identique à l'octet près quand il change — elle repart donc "
            f"sur le fil pour rien. Ajoute-le à l'ensemble aveugle."
        )


def test_the_blind_set_narrows_when_the_table_exports() -> None:
    """L'ensemble aveugle, lu directement sur les deux formes.

    Les deux tests au-dessus prouvent le COMPORTEMENT ; celui-ci nomme
    la différence, pour qu'un échec dise laquelle des deux tables a
    bougé plutôt que « hx-preserve manquant ».
    """
    with render_isolated():
        plain = _built(state=Tickets, columns=COLUMNS, rows=ROWS)
        rich = _built(state=Priced, columns=PRICED_COLUMNS,
                      rows=load_priced, exportable=True)
    assert plain._toolbar_blind_to() == {
        "sort_key", "sort_dir", "page", "per_page",
    }, plain._toolbar_blind_to()
    assert rich._toolbar_blind_to() == {"page"}, rich._toolbar_blind_to()


def test_the_export_query_does_not_depend_on_the_page() -> None:
    """Le fait qui rend la préservation démontrable.

    L'URL du bouton CSV sérialise ``to_query(for_export=True)``. Si elle
    portait la page courante, elle changerait à chaque pagination — et la
    barre ne serait plus aveugle à ``page``, donc plus préservable.

    Normaliser à 1 ne change AUCUN comportement : ``Query.offset`` rend
    déjà 0 en mode export. C'est ce qui rend le fix gratuit.
    """
    with TestClient(_app) as client:
        client.get("/")   # ouvre un contexte de rendu + un registre
        state = Tickets()
        state.page = 7
        assert state.to_query().page == 7, "la requête normale garde la page"
        assert state.to_query(for_export=True).page == 1, (
            "l'export sérialise la page courante : l'URL signée du bouton "
            "CSV change alors à chaque pagination, donc la barre d'outils "
            "n'est plus identique d'une page à l'autre et ne peut plus "
            "être préservée."
        )
        assert state.to_query(for_export=True).offset == 0


# ── Le cas sans barre du tout ─────────────────────────────────────────
#
# Une table qui pagine mais n'offre AUCUN contrôle : pas de recherche,
# pas de filtre, pas d'export. Elle est bien « interactive » au sens de
# ``_is_interactive`` (elle a un pager), donc elle traverse toute la
# mécanique de préservation — mais sa barre est vide.


class Bare(DatatableState):
    per_page: int = field(default=5)


@refreshable(deps=[Bare])
def bare_zone() -> None:
    ui.datatable(
        state=Bare,
        columns=[ui.column("name", label="Name")],
        rows=ROWS,
        search=False,
    )


@page("/bare")
def bare_home() -> None:
    bare_zone()


_app.include(bare_home)


def test_a_toolbar_with_no_control_is_not_rendered_at_all() -> None:
    """Ni barre vide au rendu complet, ni coquille au rendu partiel.

    Le risque n'est pas la ``<div>`` vide en elle-même — elle ne se voit
    pas. C'est qu'elle poserait dans le DOM une **cible ``hx-preserve``**
    portant l'``id`` de la barre : le rendu partiel suivant enverrait sa
    coquille, HTMX trouverait bien un nœud à garder, et la barre serait
    « préservée » à l'état vide pour de bon. Un jour où quelqu'un ajoute
    un filtre à cette table, il ne le verrait jamais apparaître.
    """
    with TestClient(_app) as client:
        full = client.get("/bare").text
        assert "bzdt_Bare_toolbar" not in full, (
            "une table sans recherche, sans filtre et sans export ne doit "
            "rendre AUCUNE barre — pas même une <div> vide portant son id."
        )
        partial = _go_to_page(client, full, 3, state="Bare").text
        assert "hx-preserve" not in partial, (
            "le rendu partiel envoie une coquille hx-preserve alors "
            "qu'aucune barre n'existe dans le DOM : elle n'a rien à "
            "préserver et se contenterait d'insérer une div morte."
        )
        # La contre-épreuve : la pagination marche quand même.
        assert 'name="bz_dt_page__Bare"' in partial
