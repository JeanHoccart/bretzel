"""Toute route montée sous ``/_bretzel`` est classée : ouverte ou fermée.

Une app qui veut une garde d'auth doit savoir lesquelles des routes du
FRAMEWORK laisser passer sans être connecté. Le premier exemple à en
écrire une (``examples/crm``, 2026-08-20) a dû les énumérer à la main —
et raisonner pour comprendre que ``/_bretzel/refetch`` re-rend une zone
d'app alors que ``/_bretzel/runtime.js`` ne porte rien.

C'est de la connaissance du framework dans du code d'app, et son mode
d'échec est **silencieux dans les deux sens** : une route interne
ajoutée demain sera soit refusée à un anonyme qui en a besoin (la page
de connexion s'affiche sans style), soit ouverte alors qu'elle rend du
HTML d'app. Personne ne verra ni l'un ni l'autre en relisant un diff de
routing.

Cette gate **oblige à trancher**. Elle démarre une vraie app, lit les
routes que FastAPI a réellement montées, et exige que chacune soit soit
dans :data:`~bretzel.runtime.PUBLIC_ASSET_ROUTES` (publique), soit dans
:data:`CLOSED_ROUTES` ci-dessous (fermée, avec sa raison). Une route
neuve n'est dans aucun des deux : rouge.

⚠️ **La liste des fermées vit ICI, pas dans le framework**, et c'est
délibéré : elle n'a aucun usage à l'exécution. Ce qu'une app importe,
c'est la liste des ouvertes ; ce qu'un relecteur doit voir, c'est
pourquoi chacune des autres est fermée. Les mettre toutes dans
``protocol.py`` donnerait une surface publique qui ne sert qu'à ce test.
"""

from __future__ import annotations

from starlette.testclient import TestClient

from bretzel import Bretzel
from bretzel.runtime import (
    PUBLIC_ASSET_ROUTES,
    ROUTE_PREFIX,
    ROUTE_ICONS,
    ROUTE_VENDOR,
    is_public_asset_path,
    protocol,
)

#: Les routes du framework qui doivent rester DERRIÈRE une garde, et
#: pourquoi. Ajouter une ligne ici, c'est signer.
CLOSED_ROUTES: dict[str, str] = {
    "/_bretzel/action/{action_id:path}":
        "exécute un handler de l'app — la signature HMAC est une barrière "
        "d'intégrité, pas d'autorisation",
    "/_bretzel/refetch/{state_qualname}/{zone_qualname:path}":
        "re-rend une zone : c'est du HTML de page, servi hors du chemin "
        "de la page",
    "/_bretzel/sse":
        "pousse les signaux qui déclenchent ces refetch",
    "/_bretzel/datatable.csv":
        "exporte les lignes que la datatable montre — de la donnée d'app, "
        "en clair",
}

#: Le nombre de routes que le framework monte sous ``/_bretzel``. Un
#: plancher lu de LA DÉCOUVERTE de cette gate, pas d'un comptage à part :
#: si le démarrage cassait, ``mounted_routes()`` rendrait l'ensemble vide
#: et les deux interdictions passeraient sur rien.
ROUTES_FLOOR = 7


def mounted_routes() -> set[str]:
    """Les chemins sous ``/_bretzel`` que FastAPI a RÉELLEMENT montés.

    On démarre une app plutôt que de grepper les ``register_*_route`` :
    une route ajoutée par un chemin qu'on n'a pas prévu (un ``Mount``,
    un router inclus) doit sortir ici quand même. C'est la seule lecture
    qui ne peut pas rater une route.
    """
    app = Bretzel(secret_key="dev-secret-key-for-the-route-gate", mode="dev")
    with TestClient(app):
        return {
            path
            for route in app.fastapi.routes
            if isinstance(path := getattr(route, "path", None), str)
            and path.startswith(ROUTE_PREFIX)
        }


def declared_route_constants() -> dict[str, str]:
    """Les constantes ``ROUTE_*`` de ``protocol.py`` qui promettent un
    chemin sous ``/_bretzel``.

    ``ROUTE_PREFIX`` est exclu : c'est la racine, pas une route — il
    serait préfixe de tout et passerait toujours. ``ROUTE_STATIC_DIR``
    l'est par le filtre (il vit hors de ``/_bretzel``, et n'est monté
    que si l'app passe ``static_dir=``).
    """
    return {
        name: value
        for name in dir(protocol)
        if name.startswith("ROUTE_") and name != "ROUTE_PREFIX"
        and isinstance(value := getattr(protocol, name), str)
        and value.startswith(ROUTE_PREFIX)
    }


def promised_but_unmounted() -> list[str]:
    """Les constantes qui nomment un chemin que personne ne sert.

    Le test est un PRÉFIXE, pas une égalité : ``ROUTE_ACTION`` vaut
    ``/_bretzel/action`` alors que la route montée est
    ``/_bretzel/action/{action_id:path}``. Exiger l'égalité rendrait
    trois constantes fautives à tort.
    """
    mounted = mounted_routes()
    return sorted(
        f"{name} → {value}"
        for name, value in declared_route_constants().items()
        if not any(path.startswith(value) for path in mounted)
    )


def unclassified_routes() -> list[str]:
    return sorted(mounted_routes() - PUBLIC_ASSET_ROUTES - set(CLOSED_ROUTES))


def stale_classifications() -> list[str]:
    return sorted(
        (PUBLIC_ASSET_ROUTES | set(CLOSED_ROUTES)) - mounted_routes()
    )


# ── ① le plancher ────────────────────────────────────────────────────


def test_the_route_sweep_is_not_vacuous() -> None:
    routes = mounted_routes()
    assert len(routes) >= ROUTES_FLOOR, (
        f"seulement {len(routes)} routes montées sous {ROUTE_PREFIX} "
        f"(>= {ROUTES_FLOOR} attendues) — l'app ne démarre plus comme "
        f"prévu, et les interdictions ci-dessous s'affirmeraient sur rien."
    )


# ── ② les interdictions ──────────────────────────────────────────────


def test_every_framework_route_is_classified() -> None:
    unknown = unclassified_routes()
    assert not unknown, (
        "ces routes du framework ne sont ni publiques ni fermées :\n  "
        + "\n  ".join(unknown)
        + "\n\nTranche : soit elle ne porte aucune donnée d'app et entre "
          "dans ``PUBLIC_ASSET_ROUTES`` (protocol.py) — une garde la "
          "laissera passer ; soit elle en porte, et entre dans "
          "``CLOSED_ROUTES`` ci-dessus AVEC sa raison. Ne pas trancher, "
          "c'est laisser chaque app deviner."
    )


def test_no_route_constant_promises_a_ghost() -> None:
    """Une constante ``ROUTE_*`` qui ne désigne aucune route montée.

    ⚠️ Ce bras a été ajouté APRÈS coup, parce que la gate ne le voyait
    pas : elle partait des routes montées, donc un chemin **déclaré et
    jamais servi** passait entre les mailles. C'était le cas de
    ``ROUTE_THEME_JS`` (``/_bretzel/theme.js``), planifié, exporté,
    introspecté — et monté par personne depuis toujours. Le CRM l'avait
    mis dans sa liste publique : inoffensif par chance.

    Une constante de route est une promesse publique. Si personne ne la
    sert, elle ment — et le premier à écrire une garde d'auth la
    recopiera, comme je l'ai fait.
    """
    ghosts = promised_but_unmounted()
    assert not ghosts, (
        "ces constantes nomment un chemin que le framework ne sert pas :\n  "
        + "\n  ".join(ghosts)
        + "\n\nSoit la route doit être montée, soit la constante doit "
          "partir — une promesse publique sans route derrière finit "
          "recopiée dans la liste publique d'une app."
    )


def test_no_classification_is_stale() -> None:
    """Une route classée qui n'est plus montée est un aveu périmé.

    Sans ça, les deux listes grossissent et ne rétrécissent jamais — et
    ``PUBLIC_ASSET_ROUTES`` finirait par dire à toutes les gardes du
    monde de laisser passer un chemin qui n'existe plus.
    """
    stale = stale_classifications()
    assert not stale, (
        f"ces chemins sont classés mais plus montés : {stale}"
    )


def test_the_two_lists_do_not_overlap() -> None:
    both = sorted(PUBLIC_ASSET_ROUTES & set(CLOSED_ROUTES))
    assert not both, f"classées ouvertes ET fermées : {both}"


# ── ③ la mutation, dans les deux sens ────────────────────────────────


def test_the_gate_catches_a_new_route() -> None:
    """Le versant qui MORD : une route neuve, non classée, rougit."""
    ghost = f"{ROUTE_PREFIX}/quelque-chose-de-neuf"
    assert ghost not in PUBLIC_ASSET_ROUTES
    assert ghost not in CLOSED_ROUTES
    assert sorted((mounted_routes() | {ghost})
                  - PUBLIC_ASSET_ROUTES - set(CLOSED_ROUTES)) == [ghost]


def test_the_ghost_detector_still_bites() -> None:
    """Les deux versants : un chemin fantôme sort, une vraie constante
    ne sort jamais — y compris celles dont la route montée porte un
    paramètre (``ROUTE_ACTION``, ``ROUTE_REFETCH``), qui sont
    précisément celles qu'une égalité stricte accuserait à tort."""
    mounted = mounted_routes()
    ghost = f"{ROUTE_PREFIX}/theme.js"
    assert not any(path.startswith(ghost) for path in mounted)
    for value in declared_route_constants().values():
        assert any(path.startswith(value) for path in mounted), value


def test_the_gate_spares_a_classified_route() -> None:
    """Le versant qui ÉPARGNE, et c'est celui qui trouve les faux
    positifs : une route classée ne doit JAMAIS ressortir, quel que soit
    le côté où elle est classée."""
    for path in (*PUBLIC_ASSET_ROUTES, *CLOSED_ROUTES):
        assert path not in unclassified_routes()


def test_the_asset_routes_really_answer_without_a_session() -> None:
    """La preuve par l'usage : chaque route dite « publique » répond
    bien à un client qui n'a aucun cookie.

    Une constante peut dire n'importe quoi. Ce test est ce qui la rend
    vraie — et il attraperait le cas où un asset se mettrait à exiger
    une session, ce qui ferait s'afficher toutes les pages de connexion
    du monde sans style.
    """
    app = Bretzel(secret_key="dev-secret-key-for-the-route-gate", mode="dev")
    with TestClient(app) as client:
        for path in sorted(PUBLIC_ASSET_ROUTES):
            if "{" in path:
                _assert_parameterised_asset_is_open(client, path)
                continue
            response = client.get(path)
            assert response.status_code == 200, (
                f"{path} est déclarée publique mais répond "
                f"{response.status_code} sans session."
            )


def test_a_guard_can_actually_match_every_public_route() -> None:
    """Une route publique doit être RECONNAISSABLE par une garde d'app.

    C'est le bras qui manquait, et il a coûté un bug : le 2026-08-27,
    ouvrir ``/_bretzel/vendor/{filename}`` a mis un **motif** dans
    ``PUBLIC_ASSET_ROUTES``, alors qu'``examples/crm`` écrivait
    ``path in PUBLIC_PATHS`` — une égalité. Aucun chemin réel n'est égal
    à un motif : les trois scripts tiers recevaient la page de connexion,
    le navigateur affichait trois ``Unexpected token '<'``, la page
    rendait 100 nœuds au lieu de 1 700, et le serveur ne signalait
    **rien**.

    La classification seule ne suffisait donc pas : une route pouvait
    être déclarée publique et rester injoignable. C'est
    :func:`~bretzel.runtime.is_public_asset_path` qui répond, et ce test
    exige que chaque route publique montée soit reconnue par elle.
    """
    for route in sorted(PUBLIC_ASSET_ROUTES):
        sample = _ASSET_ROUTE_SAMPLES.get(route, route)
        assert is_public_asset_path(sample), (
            f"{sample} est classée publique mais `is_public_asset_path` "
            "la refuse — une garde d'app la fermerait."
        )


def test_no_closed_route_is_mistaken_for_a_public_asset() -> None:
    """Le versant qui ÉPARGNE : la reconnaissance ne déborde pas.

    Un motif ne couvre qu'un segment. Si ``is_public_asset_path``
    ouvrait un sous-arbre, elle laisserait passer des chemins que
    ``CLOSED_ROUTES`` ferme — donc du HTML d'app à un anonyme.
    """
    for closed in (
        "/_bretzel/sse",
        "/_bretzel/datatable.csv",
        "/_bretzel/action/mon.module::handler",
        "/_bretzel/refetch/State/zone",
        f"{ROUTE_VENDOR}/sous/dossier",
        f"{ROUTE_VENDOR}/",
    ):
        assert not is_public_asset_path(closed), (
            f"{closed} est reconnue comme un asset public — une garde "
            "l'ouvrirait."
        )


#: Ce qu'on substitue au paramètre d'une route d'asset paramétrée, pour
#: qu'elle soit interrogeable. Une entrée par route — pas de règle
#: devinée : le jour où une route paramétrée est ajoutée sans venir ici,
#: le test le dit plutôt que d'inventer une valeur qui passera.
_ASSET_ROUTE_SAMPLES: dict[str, str] = {
    f"{ROUTE_VENDOR}/{{filename}}": f"{ROUTE_VENDOR}/htmx.min.js",
    # Les données d'icône : une page de connexion affiche des glyphes
    # avant que quiconque soit connecté, donc la route doit répondre sans
    # session — comme les feuilles et l'icône de l'onglet.
    f"{ROUTE_ICONS}/{{chemin:path}}": f"{ROUTE_ICONS}/lucide.json",
}


def _assert_parameterised_asset_is_open(client: TestClient, path: str) -> None:
    """Une route d'asset paramétrée ne demande jamais de session.

    Elle peut légitimement répondre **404** : ``/_bretzel/vendor/…`` ne
    sert que les fichiers réellement rapatriés, et un dépôt qui n'a pas
    lancé ``python -m bretzel.render.vendor`` n'en a aucun. Ce que la
    classification promet n'est pas « ce fichier existe », c'est « aucun
    cookie n'est exigé » — donc le refus qu'on interdit ici est un refus
    d'AUTH, pas une absence.
    """
    sample = _ASSET_ROUTE_SAMPLES.get(path)
    assert sample is not None, (
        f"{path} est publique et paramétrée, mais aucun exemple n'est "
        "déclaré dans `_ASSET_ROUTE_SAMPLES` — le test ne peut pas "
        "l'interroger, donc il ne prouve rien sur elle."
    )
    status = client.get(sample, follow_redirects=False).status_code
    assert status in (200, 404), (
        f"{sample} est déclarée publique mais répond {status} sans "
        "session — une redirection ou un 401/403 ici casserait toute page "
        "de connexion."
    )
