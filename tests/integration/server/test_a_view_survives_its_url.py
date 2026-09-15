"""Gate : un aller-retour par l'URL rend la MÊME vue.

L'invariant n'est pas « l'URL contient les bons paramètres » — ça, une
inspection de chaîne le dirait, et ça passerait avec une lecture cassée.
C'est **le tour complet** : muter un champ déclaré, prendre l'adresse
poussée, la redemander dans un contexte NEUF, et retrouver ce qu'on
regardait.

Le contexte neuf est le cœur du test. Tout ``PageState`` est indexé par
un uuid de rendu que le serveur forge à chaque navigation
(``registry.py:382``) : c'est précisément ce qui faisait qu'un filtre ne
survivait ni à un changement de page ni au bouton retour. Un test qui
rejouerait l'URL avec le même client garderait le même uuid, retrouverait
l'état par le magasin, et **passerait alors même que l'URL ne servirait à
rien**. D'où un second ``TestClient`` : il n'a ni cookie ni uuid, donc la
seule chose qui voyage est l'adresse.

Et le test doit être DISCRIMINANT — la vue restaurée doit différer de la
vue par défaut. Sans ça, trier par le premier champ dans l'ordre source
rend les mêmes lignes, et l'égalité serait vraie par coïncidence : c'est
le faux positif que l'écriture de cette gate a rencontré pour de vrai.
"""

from __future__ import annotations

import re

from fastapi.testclient import TestClient

from bretzel import Bretzel, page, refreshable, ui
from bretzel.components import DatatableState
from bretzel.runtime import HEADER_PAGE_ID
from bretzel.server.handlers import sign_action
from bretzel.state import PageState, field

_SECRET = "z" * 32

ROWS = [{"id": i, "name": f"n{i:02}", "score": (i * 7) % 100} for i in range(34)]
COLUMNS = [
    ui.column("name", label="Name", sortable=True),
    ui.column("score", label="Score", sortable=True),
]


class Issues(DatatableState):
    per_page: int = field(default=5)
    #: ``filters`` est ABSENT, et c'est la décision du 2026-08-29 : un
    #: champ déclaré part dans l'historique, les logs et le ``Referer``,
    #: et c'est celui qui porte le plus probablement une donnée
    #: sensible. Adressable sur demande, jamais par défaut.
    URL = {"sort_key": "sort", "sort_dir": "dir", "page": "p", "search": "q"}


class Plain(DatatableState):
    """La contre-épreuve : même composant, aucune déclaration."""

    per_page: int = field(default=5)


class Remembered(DatatableState, scope="session", addressable=True):
    """Mémoire de session ET adresse — la combinaison qui ment sans le
    ``replaceState``."""

    per_page: int = field(default=5)


_app = Bretzel(secret_key=_SECRET, mode="dev")


@refreshable(deps=[Issues])
def issues_zone() -> None:
    ui.datatable(state=Issues, columns=COLUMNS, rows=ROWS)


@refreshable(deps=[Plain])
def plain_zone() -> None:
    ui.datatable(state=Plain, columns=COLUMNS, rows=ROWS)


@page("/issues")
def issues_page() -> None:
    issues_zone()


@page("/plain")
def plain_page() -> None:
    plain_zone()


@refreshable(deps=[Remembered])
def remembered_zone() -> None:
    ui.datatable(state=Remembered, columns=COLUMNS, rows=ROWS)


@page("/remembered")
def remembered_page() -> None:
    remembered_zone()


_app.include(issues_page, plain_page, remembered_page)


# ── Helpers ───────────────────────────────────────────────────────────


def _page_id(html: str) -> str:
    match = re.search(r'data-bretzel-page-id="([^"]+)"', html)
    assert match, "le shell doit publier l'id de page"
    return match.group(1)


def _action(html: str, handler: str, tag: str) -> tuple[str, str]:
    for chunk in html.split(f"<{tag}")[1:]:
        head = chunk.split(">", 1)[0]
        if handler not in head:
            continue
        url = re.search(r'hx-post="([^"]+)"', head)
        args = re.search(r"_args&quot;: &quot;([^&]*)&quot;", head)
        if url and args:
            return url.group(1), args.group(1)
    raise AssertionError(f"pas d'action {handler!r} sur <{tag}>")


def _rows(html: str) -> list[str]:
    """Les trois premiers noms affichés — la signature de la VUE."""
    return re.findall(r"<td[^>]*>(n\d\d)</td>", html)[:3]


def _sort(client: TestClient, html: str, page_id: str, current: str):
    """Cliquer le premier en-tête triable, en disant où l'on est."""
    url, args = _action(html, "sort_by", "button")
    return client.post(
        url,
        headers={
            "X-Bz-Sig": sign_action(
                _app.config._action_key, url.rsplit("/", 1)[-1], args
            ),
            HEADER_PAGE_ID: page_id,
            "HX-Request": "true",
            "HX-Current-URL": current,
        },
        data={"_args": args},
    )


def _action_nth(html: str, handler: str, nth: int) -> tuple[str, str]:
    """La n-ième action ``handler`` de la page — pour viser la SECONDE
    colonne triable, celle dont le tri quitte le défaut."""
    hits = []
    for chunk in html.split("<button")[1:]:
        head = chunk.split(">", 1)[0]
        if handler not in head:
            continue
        url = re.search(r'hx-post="([^"]+)"', head)
        args = re.search(r"_args&quot;: &quot;([^&]*)&quot;", head)
        if url and args:
            hits.append((url.group(1), args.group(1)))
    return hits[nth]


def _post_action(client, url, args, page_id, current, form=None):
    """Poster une action en disant OÙ l'on est — le chemin vient de là."""
    return client.post(
        url,
        headers={
            "X-Bz-Sig": sign_action(
                _app.config._action_key, url.rsplit("/", 1)[-1], args
            ),
            HEADER_PAGE_ID: page_id,
            "HX-Request": "true",
            "HX-Current-URL": current,
        },
        data={"_args": args, **(form or {})},
    )


# ── La gate ───────────────────────────────────────────────────────────


def test_a_sorted_view_is_reachable_from_its_url_alone() -> None:
    """Le tour complet, avec un client NEUF pour rejouer l'adresse."""
    with TestClient(_app) as client:
        home = client.get("/issues").text
        page_id = _page_id(home)
        default_rows = _rows(home)

        # Deux clics : asc puis desc, pour que les lignes CHANGENT
        # vraiment. Un seul tri par le premier champ rend l'ordre source.
        first = _sort(client, home, page_id, "http://t/issues")
        second = _sort(
            client, first.text, page_id,
            "http://t" + first.headers["HX-Push-Url"],
        )
        pushed = second.headers.get("HX-Push-Url")
        assert pushed, (
            "aucun HX-Push-Url après un tri sur un champ déclaré : la vue "
            "n'a pas d'adresse, donc ni retour ni partage"
        )
        sorted_rows = _rows(second.text)

    assert sorted_rows != default_rows, (
        "le tri ne change pas les lignes — le test ne prouverait rien, "
        "l'égalité finale serait vraie par coïncidence"
    )

    # Client NEUF : ni cookie ni page_id. Seule l'adresse voyage.
    with TestClient(_app) as fresh:
        restored = _rows(fresh.get(pushed).text)

    assert restored == sorted_rows, (
        f"l'URL {pushed} ne restaure pas la vue : {restored} au lieu de "
        f"{sorted_rows}. C'est le bouton retour et le lien partagé qui "
        f"cassent, et rien ne le signale à l'utilisateur."
    )


def test_the_url_carries_only_what_moved() -> None:
    """Un champ à son défaut n'apparaît pas, et l'app garde ses params.

    Les deux versants d'une même exigence : une URL doit se LIRE. Poser
    ``?sort=name&dir=asc&p=1&q=`` pour dire « trié par nom » la rend
    illisible, et écraser un ``?utm=`` que l'app portait est une
    régression silencieuse.
    """
    with TestClient(_app) as client:
        home = client.get("/issues").text
        pushed = _sort(
            client, home, _page_id(home), "http://t/issues?utm=campagne",
        ).headers["HX-Push-Url"]

    assert "utm=campagne" in pushed, (
        f"le paramètre de l'app a disparu : {pushed}"
    )
    assert "sort=name" in pushed
    for noisy in ("dir=asc", "p=1", "q="):
        assert noisy not in pushed, (
            f"{noisy!r} est dans {pushed} alors que le champ est à son "
            f"défaut — l'absence DIT déjà le défaut, des deux côtés"
        )


def test_a_sort_cycled_back_to_neutral_leaves_the_url() -> None:
    """Le bug du 2026-08-29, et c'est le pire mode d'échec du mécanisme.

    Rapporté par l'utilisateur : « je ne peux plus trier en décroissant »,
    « avec un filtre actif plus rien ne bouge ».

    L'URL était FUSIONNÉE, pas recomposée. Un champ revenu à son défaut
    sort de la liste des paramètres à écrire — donc l'ancienne valeur
    restait. Et comme l'URL fait foi à l'action suivante, elle
    **re-semait** ce que l'utilisateur venait de quitter : chaque clic
    retombait sur le tri précédent.

    Une adresse périmée ne se contente pas de mentir sur ce qui est
    affiché — elle PILOTE. C'est ce qui rend ce test indispensable, et
    ce que la première version de cette gate n'a pas vu : elle ne triait
    qu'UNE colonne dans un seul sens, donc aucun champ ne revenait jamais
    à son défaut.

    Le tri est à trois positions (asc → desc → neutre), donc trois clics
    ramènent ``sort_key`` à ``""``, qui EST son défaut.
    """
    with TestClient(_app) as client:
        home = client.get("/issues").text
        page_id = _page_id(home)
        url, args = _action(home, "sort_by", "button")

        current, pushed = "http://t/issues", []
        for _ in range(3):
            response = _post_action(client, url, args, page_id, current)
            pushed.append(response.headers.get("HX-Push-Url", ""))
            current = "http://t" + pushed[-1]

    assert "sort=name" in pushed[0], pushed
    assert "dir=desc" in pushed[1], pushed
    assert "sort=" not in pushed[2], (
        f"le tri est revenu au neutre mais l'adresse garde {pushed[2]!r}. "
        f"L'action suivante le re-sèmera et écrasera le clic — c'est "
        f"exactement « je ne peux plus trier en décroissant »."
    )
    # ⚠️ ``dir=desc`` SURVIT, et c'est juste. ``sort_dir`` est
    # délibérément conservé quand le tri repasse au neutre — pour qu'un
    # re-tri de la même colonne reparte où on l'avait laissé plutôt que
    # de toujours redémarrer en ascendant (cf. ``DatatableState``).
    # L'URL reflète donc un état RÉEL. Ce test l'affirme pour que
    # personne ne le « répare » : ce serait retirer de l'adresse ce que
    # l'état dit vraiment, et casser la reprise après un rechargement.
    assert "dir=desc" in pushed[2], (
        f"{pushed[2]!r} a perdu la direction mémorisée — un re-tri "
        f"repartirait en ascendant au lieu de reprendre en descendant"
    )


def test_the_url_drops_what_returned_to_its_default() -> None:
    """La forme minimale et directe du même bug.

    On pousse ``search`` hors de son défaut, puis on le ramène : le
    paramètre doit DISPARAÎTRE de l'adresse, pas y rester périmé.
    """
    with TestClient(_app) as client:
        home = client.get("/issues").text
        page_id = _page_id(home)
        url, args = _action(home, "search_for", "input")

        typed = _post_action(
            client, url, args, page_id, "http://t/issues",
            {"bz_dt_search__Issues": "pagination"},
        )
        assert "q=pagination" in typed.headers["HX-Push-Url"]

        cleared = _post_action(
            client, url, args, page_id,
            "http://t" + typed.headers["HX-Push-Url"],
            {"bz_dt_search__Issues": ""},
        )

    assert "q=" not in cleared.headers.get("HX-Push-Url", ""), (
        f"la recherche vidée laisse {cleared.headers.get('HX-Push-Url')!r} : "
        f"l'action suivante re-sèmerait le terme effacé"
    )


def test_an_undeclared_table_pushes_nothing() -> None:
    """La contre-épreuve, et elle borne tout le reste.

    Sans elle, « pousser toujours » passerait le test du haut. Or c'est
    l'opt-in qui protège : un champ déclaré part dans l'historique, les
    logs serveur et le ``Referer``. Une table qui n'a rien demandé ne
    doit rien publier.
    """
    with TestClient(_app) as client:
        home = client.get("/plain").text
        response = _sort(client, home, _page_id(home), "http://t/plain")

    assert "HX-Push-Url" not in response.headers, (
        "une table SANS déclaration ``URL`` a poussé une adresse : "
        f"{response.headers.get('HX-Push-Url')!r}. L'opt-in ne protège "
        "plus rien, et chaque app publie sa recherche dans les logs."
    )


def test_a_page_render_pushes_nothing_either() -> None:
    """Rendre une page ne pousse pas : l'adresse est déjà la bonne.

    Le cas qui produirait une boucle — pousser à chaque rendu ferait
    empiler une entrée d'historique par navigation, donc le retour
    demanderait deux clics pour un mouvement.
    """
    with TestClient(_app) as client:
        response = client.get("/issues?sort=score&dir=desc")
    assert response.status_code == 200
    assert "HX-Push-Url" not in response.headers


def test_a_hostile_param_does_not_break_the_page() -> None:
    """Une URL est tapée par des humains et bricolée par des robots.

    ``?p=banane`` doit rendre la page avec le défaut, pas une 500. La
    coercition est best-effort **par conception** : c'est la seule
    posture tenable pour une entrée qui n'est pas sous notre contrôle.
    """
    with TestClient(_app) as client:
        for hostile in ("?p=banane", "?p=-1", "?p=", "?q=" + "x" * 500):
            response = client.get("/issues" + hostile)
            assert response.status_code == 200, (hostile, response.status_code)

        # Le versant injection, avec une charge RECONNAISSABLE. Chercher
        # ``<script>`` tout court ne prouverait rien : la coque en pose
        # déjà trois pour le thème et l'écran — c'est le faux positif que
        # la première écriture de ce test a produit.
        payload = "<script>bzXSS</script>"
        reflected = client.get("/issues", params={"q": payload}).text

    assert "<script>bzXSS" not in reflected, (
        "la valeur d'URL est réfléchie SANS échappement — un lien suffit "
        "alors à exécuter du script chez qui l'ouvre"
    )
    assert "bzXSS" in reflected, (
        "la recherche n'atteint plus le champ : le test ne mesure plus "
        "l'échappement, il mesure une absence"
    )


def test_the_one_line_optin_names_the_scalars_and_skips_the_dict() -> None:
    """``addressable=True`` : le nommage vient du socle, la décision de toi.

    C'est la forme courante, et elle porte la décision du 2026-08-29 dans
    le CODE plutôt que dans une consigne : ``filters`` n'a pas de
    ``field(url=…)``, donc l'opt-in ne peut pas l'allumer. « Non
    adressable par défaut » devient une propriété du socle.
    """
    from bretzel.state.url import addressable_fields

    class Opted(DatatableState, addressable=True):
        pass

    named = addressable_fields(Opted)
    assert named == {
        "sort_key": "tri", "sort_dir": "sens",
        "page": "p", "per_page": "taille", "search": "q",
    }, named
    assert "filters" not in named, (
        "l'opt-in a allumé ``filters`` — la décision « jamais par "
        "défaut » ne tient plus par construction, seulement par la doc"
    )

    class NotOpted(DatatableState):
        pass

    assert addressable_fields(NotOpted) == {}, (
        "un état qui n'a rien demandé publie quand même — l'opt-in ne "
        "protège plus rien"
    )


def test_overriding_a_default_keeps_the_url_name() -> None:
    """Le piège trouvé en câblant le CRM, et il était SILENCIEUX.

    ``sort_key: str = "name"`` sur une sous-classe crée un nouveau
    ``Field`` : sans héritage du ``url=``, le tri cessait d'être dans
    l'adresse — sans erreur, sans trace, juste un paramètre qui
    n'apparaît plus.

    Surcharger une VALEUR n'est pas renoncer au vocabulaire.
    """
    from bretzel.state.url import addressable_fields

    class Overridden(DatatableState, addressable=True):
        per_page: int = field(default=25)
        sort_key: str = field(default='name')

    named = addressable_fields(Overridden)
    assert named.get("sort_key") == "tri", (
        f"la surcharge du défaut a perdu le nom d'URL : {named}"
    )
    assert Overridden().sort_key == "name", "et le défaut surchargé tient"
    assert Overridden().per_page == 25


def test_a_structured_field_is_refused() -> None:
    """``filters`` déclaré aujourd'hui CORROMPRAIT l'état.

    Une query ne porte que des chaînes. Sans format pour une structure,
    ``apply_url_params`` remplacerait le ``dict`` par une ``str`` — et le
    premier ``state.filters.get(...)`` du composant casserait, alors que
    la déclaration n'avait rien signalé. Mesuré le 2026-08-29 :
    ``filters`` passait de ``{}`` à ``'secteur:Agro'``.

    Refuser à la déclaration est le seul endroit où ça se voit. C'est
    aussi ce qui rend « ``filters`` non adressable » une PROPRIÉTÉ du
    socle et pas une consigne de doc.
    """
    import pytest

    from bretzel.state.url import AddressableFieldError, addressable_fields

    class Structured(DatatableState):
        URL = {"filters": "f"}

    with pytest.raises(AddressableFieldError, match="dict"):
        addressable_fields(Structured)

    # Le versant licite : les scalaires du même état restent déclarables.
    class Scalars(DatatableState):
        URL = {"sort_key": "tri", "page": "p"}

    assert addressable_fields(Scalars) == {"sort_key": "tri", "page": "p"}


def test_two_states_claiming_the_same_param_is_refused() -> None:
    """Le conflit se lève, il ne se subit pas.

    Deux tables sur une page qui déclarent toutes deux ``p`` : l'une
    écraserait l'autre à chaque navigation, en silence. Le contrôle vit
    dans la composition — donc par requête — parce que la collision n'est
    une faute que si les deux états se rencontrent VRAIMENT (anti-règle 2
    interdit par ailleurs un registre global de noms réservés).
    """
    import pytest

    from bretzel.state.url import AddressableFieldError, collect_url_params

    class Left(PageState):
        page: int = field(default=2)
        URL = {"page": "p"}

    class Right(PageState):
        page: int = field(default=2)
        URL = {"page": "p"}

    with pytest.raises(AddressableFieldError, match="p"):
        collect_url_params([Left(), Right()])


def _envelope_address(html: str) -> str:
    """L'adresse corrigée que le serveur pose dans l'``<bz-envelope>``."""
    match = re.search(r'"address":"([^"]*)"', html)
    return match.group(1) if match else "(absente de l'envelope)"


def test_a_remembered_view_corrects_its_address() -> None:
    """Mémoire de session + adressabilité : l'adresse ne doit pas se taire.

    Un état ``scope="session"`` se souvient d'un tri par-delà les
    navigations. Revenir sur ``/remembered`` NU rend donc une vue triée
    sous une adresse qui n'en dit rien — et le lien copié montre autre
    chose chez qui le reçoit. Deux personnes « sur la même page », et
    rien ne le signale.

    Le serveur, lui, sait les deux : il compose l'adresse juste et la
    pose dans l'envelope, que le runtime passe à ``replaceState``
    (**replace**, pas push : corriger n'est pas naviguer).
    """
    with TestClient(_app) as client:
        home = client.get("/remembered").text
        assert _envelope_address(home) == "", (
            "rien n'a bougé et le serveur corrige déjà l'adresse — chaque "
            "chargement réécrirait la barre pour rien"
        )

        url, args = _action(home, "sort_by", "button")
        _post_action(client, url, args, _page_id(home), "http://t/remembered")

        # On revient sur l'adresse NUE, comme le ferait un clic de menu.
        bare = client.get("/remembered").text

    assert _envelope_address(bare) == "/remembered?tri=name", (
        f"la vue est triée mais l'adresse dit /remembered — "
        f"envelope : {_envelope_address(bare)!r}"
    )


def test_a_page_that_says_the_truth_corrects_nothing() -> None:
    """Le versant qui borne : pas de réécriture gratuite.

    Sans lui, « corriger toujours » passerait le test du dessus tout en
    réécrivant la barre d'adresse à chaque chargement de chaque page.
    """
    with TestClient(_app) as client:
        url, args = _action(client.get("/remembered").text, "sort_by", "button")
        home = client.get("/remembered").text
        _post_action(client, url, args, _page_id(home), "http://t/remembered")
        exact = client.get("/remembered?tri=name").text

    assert _envelope_address(exact) == "", (
        f"l'adresse était déjà juste et le serveur la réécrit quand même : "
        f"{_envelope_address(exact)!r}"
    )


def test_a_table_without_memory_never_corrects() -> None:
    """Et une page sans état adressable ne paie rien du tout."""
    with TestClient(_app) as client:
        assert _envelope_address(client.get("/plain").text) == ""
