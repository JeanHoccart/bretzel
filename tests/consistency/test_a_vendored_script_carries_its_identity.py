"""Un cache sur DISQUE nomme ce qu'il contient — sinon rien ne l'invalide.

Ce que cette gate ferme
-----------------------

Un memo en mémoire meurt avec le processus : une clé incomplète s'y
répare toute seule au redémarrage suivant. Un cache sur **disque**, non.
Ce qu'il contient survit à tout, donc son nom doit suffire à décider s'il
est encore bon.

Les trois scripts tiers s'appelaient ``htmx.min.js`` & consorts. Monter
la version dans :mod:`bretzel.render.shell` laissait donc chaque checkout
existant servir l'ANCIENNE pour toujours : ``download()`` rendait la main
sur un ``is_file()``, et ``vendored_is_available`` ne regardait pas
davantage. Mesuré le 2026-08-27 — ``htmx.min.js`` remplacé par 38 octets
de n'importe quoi : disponible ``True``, servi par ``url_for``, et
``download()`` refusait de le remplacer.

C'est la MÊME classe de bug que le cache CSS du même jour (une clé qui ne
couvre pas toutes ses entrées), et le même correctif : l'identité entre
dans le nom. Le dépôt l'applique déjà au binaire Tailwind, dont le nom
porte la version.
"""

from __future__ import annotations

from bretzel.render import vendor


def test_the_sweep_is_not_vacuous() -> None:
    """Le plancher : il y a bien des scripts à surveiller."""
    assert len(vendor.vendored_assets()) >= 3, (
        "moins de trois scripts tiers — la gate ne mesure plus rien."
    )


def test_every_cached_name_carries_its_digest() -> None:
    """L'interdiction : aucun nom de cache n'est stable d'une version
    à l'autre."""
    for asset in vendor.vendored_assets():
        nom = vendor.cached_name(asset)
        assert asset.sha256[:8] in nom, (
            f"{nom} ne porte pas l'empreinte de {asset.filename} — monter "
            "la version amont laisserait ce fichier servir l'ancienne."
        )
        assert nom != asset.filename, (
            f"{nom} est le nom amont nu : rien ne distingue deux versions."
        )


def test_the_served_route_carries_it_too() -> None:
    """Le nom sur le disque et le nom dans l'URL sont le MÊME.

    Sans ça, le navigateur garderait l'ancien en cache ``immutable``
    même une fois le disque à jour — on aurait déplacé le problème
    d'un cache à l'autre.
    """
    for asset in vendor.vendored_assets():
        route = vendor.route_for(asset)
        assert route.endswith(vendor.cached_name(asset)), route
        assert asset.sha256[:8] in route, route


def test_the_name_still_bites_when_a_version_is_bumped() -> None:
    """Le versant qui MORD : deux empreintes, deux noms, jamais confondus.

    On fabrique la même ressource avec une empreinte différente — ce
    qu'est exactement une montée de version — et on exige que le cache
    ne la confonde pas avec l'ancienne.
    """
    ancien = vendor.vendored_assets()[0]
    monte = ancien._replace(sha256="f" * 64)
    assert vendor.cached_name(monte) != vendor.cached_name(ancien), (
        "une version montée retombe sur le nom de l'ancienne — le cache "
        "servirait l'ancienne pour toujours."
    )
    assert vendor.vendored_local_path(monte) != vendor.vendored_local_path(ancien)


def test_two_assets_do_not_collide() -> None:
    """Le versant LICITE : des ressources distinctes gardent des noms
    distincts, et lisibles — le nom amont reste devant l'empreinte."""
    noms = [vendor.cached_name(a) for a in vendor.vendored_assets()]
    assert len(set(noms)) == len(noms), f"collision de noms : {noms}"
    for asset, nom in zip(vendor.vendored_assets(), noms, strict=True):
        tige = asset.filename.rpartition(".")[0]
        assert nom.startswith(tige), (
            f"{nom} ne commence plus par {tige} — illisible dans un cache "
            "qu'un humain doit pouvoir inspecter."
        )


def test_the_url_the_shell_emits_is_actually_served() -> None:
    """Le bras qui MANQUAIT, et son absence a coûté trois 404.

    Les tests au-dessus comparent ``route_for`` à ``cached_name`` : deux
    fonctions du même module, donc ils restent verts même quand la ROUTE
    qui sert le fichier, elle, compare à autre chose. C'est exactement ce
    qui s'est passé le 2026-08-27 — la route confrontait le nom d'URL au
    ``filename`` amont pendant que le shell émettait le nom à empreinte.
    L'app perdait htmx et iconify d'un coup : plus d'icônes, plus de
    transport, et **aucune erreur serveur** — trois lignes de log.

    On monte donc une vraie app et on DEMANDE l'URL.
    """
    from starlette.testclient import TestClient

    from bretzel import Bretzel, ui
    from bretzel.render import page

    app = Bretzel(secret_key="v" * 32, mode="prod")

    @page("/")
    def home() -> None:
        ui.text("ok")

    app.include(home)

    with TestClient(app) as client:
        html = client.get("/").text
        for asset in vendor.vendored_assets():
            if not vendor.vendored_is_available(asset):
                continue          # non téléchargé : le shell pointe le CDN
            route = vendor.route_for(asset)
            assert route in html, (
                f"{route} n'est pas dans le HTML alors que le fichier est là."
            )
            reponse = client.get(route)
            assert reponse.status_code == 200, (
                f"{route} rend {reponse.status_code} — le shell émet une URL "
                "que la route ne sert pas."
            )
            assert len(reponse.content) > 1000, (
                f"{route} rend {len(reponse.content)} octets — ce n'est pas "
                "le script."
            )
