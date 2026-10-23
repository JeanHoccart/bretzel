"""Les trois scripts tiers restent épinglés, livrés, et le shell les suit.

Ce que cette gate ferme
-----------------------

``bretzel.render.vendor`` rapatrie htmx, idiomorph et iconify dans
``./.bretzel/vendor/`` pour que la page ne dépende plus de trois origines
extérieures. Mesuré le 2026-08-27, app en mode prod, cache froid : le
``DOMContentLoaded`` passe de **644 ms à 110 ms**, parce que les trois
scripts tombent de 593 / 592 / 489 ms à ~50 ms chacun.

Trois dérives possibles, aucune bruyante :

1. **une empreinte qui ne correspond plus** — on servirait sous notre
   propre origine un fichier qu'on n'a pas vérifié, ce qui est pire que
   de laisser le CDN le servir : on lui prête notre nom ;
2. **le shell qui cesse de suivre le cache** — soit il pointe sur le CDN
   alors que la copie est là (le gain disparaît en silence), soit il
   pointe sur une copie absente (la page casse) ;
3. **la route qui joint le nom de l'URL au chemin** — ``../`` et elle
   sert tout le disque.

Depuis la 0.1.0a3 (décidé le 2026-10-22), les trois scripts et le jeu
d'icônes Lucide sont **livrés dans le wheel** (``bretzel/render/_vendor/``) :
une page de production ne parle à aucun hôte tiers, sans commande à lancer.
Deux dérives de plus à fermer :

4. **un fichier livré qui manque ou ne correspond plus** — la prod
   retomberait en silence sur le CDN, ou servirait un octet non vérifié ;
5. **une icône Lucide qui repasse par le réseau** — la route relaierait
   vers api.iconify.design ce que le paquet sait répondre seul.
"""

from __future__ import annotations

import hashlib
import re

from bretzel.render import vendor

_HEX64 = re.compile(r"^[0-9a-f]{64}$")


def test_the_population_is_three_pinned_assets() -> None:
    """Le plancher : la table existe, et chaque entrée est épinglable."""
    declared = vendor.vendored_assets()
    assert len(declared) == 3, (
        f"{len(declared)} scripts tiers déclarés — la gate ne couvre plus "
        "ce que le shell charge."
    )
    for asset in declared:
        assert asset.url.startswith("https://"), asset
        assert _HEX64.match(asset.sha256), (
            f"{asset.filename} : empreinte absente ou mal formée "
            f"({asset.sha256!r})."
        )


def test_every_script_ships_in_the_package() -> None:
    """Le plancher de la 0.1.0a3 : les trois sont DANS le paquet."""
    missing = [
        a.filename for a in vendor.vendored_assets()
        if not vendor.packaged_path(a).is_file()
    ]
    assert not missing, (
        f"{missing} absents de bretzel/render/_vendor/ — la prod les "
        "chargerait depuis leur CDN."
    )


def test_a_served_file_matches_its_pin() -> None:
    """L'invariant : ce qui est servi est ce qu'on a épinglé.

    Attrape le cas où quelqu'un monte la version dans ``shell.py`` sans
    toucher l'empreinte : le paquet garde alors l'ANCIEN fichier, que
    ``is_available`` déclare bon et que l'app sert.
    """
    for asset in vendor.vendored_assets():
        digest = hashlib.sha256(vendor.vendored_local_path(asset).read_bytes()).hexdigest()
        assert digest == asset.sha256, (
            f"{asset.filename} en cache ne correspond pas à son empreinte.\n"
            f"  déclarée : {asset.sha256}\n  sur disque : {digest}\n"
            "Soit la version a bougé sans que l'empreinte suive, soit le "
            "fichier est corrompu. Retélécharger le fichier dans "
            "bretzel/render/_vendor/ après avoir vérifié la table."
        )


def test_the_detector_still_bites_and_spares_both_ways(
    tmp_path, monkeypatch
) -> None:
    """Le versant qui MORD **et** le versant licite, dans le même test.

    Ni livré ni en cache → l'URL du CDN, sinon une installation cassée
    chargerait un 404. Livré → la route locale, sans rien lancer.
    Seulement en cache → la route locale aussi.
    """
    monkeypatch.chdir(tmp_path)
    asset = vendor.vendored_assets()[0]
    assert vendor.url_for(asset) == vendor.route_for(asset), (
        "le script est livré dans le paquet et le shell appelle encore le "
        "CDN — la 0.1.0a3 ne servirait à rien."
    )

    monkeypatch.setattr(vendor, "PACKAGED_DIR", tmp_path / "rien-de-livre")
    assert vendor.url_for(asset) == asset.url, (
        "ni livré ni en cache, et le shell pointe sur la route locale — la "
        "page chargerait un 404."
    )

    target = vendor.vendored_local_path(asset)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(b"// peu importe le contenu ici")
    assert vendor.url_for(asset) == vendor.route_for(asset), (
        "le fichier est dans le cache et le shell continue d'appeler le "
        "CDN — les 593 ms mesurés reviennent sans que rien ne rougisse."
    )


def test_the_route_refuses_anything_it_did_not_declare() -> None:
    """La route confronte le nom à la table ; elle ne joint pas de chemin."""
    from fastapi.testclient import TestClient

    from bretzel import Bretzel, ui
    from bretzel.render import page

    app = Bretzel(secret_key="v" * 32, mode="prod")

    @page("/")
    def home() -> None:
        ui.text("ok")

    app.include(home)
    with TestClient(app) as client:
        for suspect in (
            "../../../etc/passwd",
            "..%2f..%2fpyproject.toml",
            "inconnu.js",
            "",
        ):
            status = client.get(f"/_bretzel/vendor/{suspect}").status_code
            assert status in (404, 405, 307), (
                f"/_bretzel/vendor/{suspect!r} a répondu {status} — la route "
                "sert autre chose que les trois assets déclarés."
            )


def test_a_lucide_icon_never_touches_the_network(monkeypatch) -> None:
    """Le jeu par défaut répond depuis le paquet, réseau coupé.

    Versant licite : une icône Lucide connue revient avec son corps.
    Versant qui mord : un nom absent revient dans ``not_found`` (pas
    d'appel réseau pour autant), et un jeu non livré n'est PAS répondu
    par le paquet — il reste au relais.
    """
    import json
    import urllib.request

    def no_network(*args, **kwargs):
        raise AssertionError("la route d'icônes est sortie sur le réseau")

    monkeypatch.setattr(urllib.request, "urlopen", no_network)
    body = vendor.icon_payload("/lucide.json?icons=x,check,pas-une-icone")
    assert body is not None
    data = json.loads(body)
    assert data["prefix"] == "lucide"
    assert {"x", "check"} <= set(data["icons"]), data["icons"].keys()
    assert "<path" in data["icons"]["x"]["body"]
    assert data["not_found"] == ["pas-une-icone"]
    assert vendor.packaged_icon_payload("/mdi.json?icons=home") is None
