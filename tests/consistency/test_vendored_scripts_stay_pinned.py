"""Les trois scripts tiers restent épinglés, et le shell suit le cache.

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

⚠️ Le cache est **facultatif**. Un dépôt qui n'a jamais lancé
``python -m bretzel.render.vendor`` n'a pas ces fichiers, et c'est
correct : le repli CDN est la règle de départ. Les tests qui ont besoin
des fichiers se sautent alors plutôt que de rougir — mais le test
d'empreinte, lui, mord dès qu'ils sont là.
"""

from __future__ import annotations

import hashlib
import re

import pytest

from bretzel.render import vendor

_HEX64 = re.compile(r"^[0-9a-f]{64}$")


def test_three_assets_are_declared_with_a_pin() -> None:
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


def test_a_cached_file_matches_its_pin() -> None:
    """L'invariant : ce qui est sur le disque est ce qu'on a épinglé.

    Attrape le cas où quelqu'un monte la version dans ``shell.py`` sans
    toucher l'empreinte : le cache garde alors l'ANCIEN fichier, que
    ``is_available`` déclare bon et que l'app sert.
    """
    present = [a for a in vendor.vendored_assets() if vendor.vendored_is_available(a)]
    if not present:
        pytest.skip("cache vide — `python -m bretzel.render.vendor` non lancé")
    for asset in present:
        digest = hashlib.sha256(vendor.vendored_local_path(asset).read_bytes()).hexdigest()
        assert digest == asset.sha256, (
            f"{asset.filename} en cache ne correspond pas à son empreinte.\n"
            f"  déclarée : {asset.sha256}\n  sur disque : {digest}\n"
            "Soit la version a bougé sans que l'empreinte suive, soit le "
            "fichier est corrompu. Relancer `python -m bretzel.render.vendor "
            "--force` après avoir vérifié la table."
        )


def test_the_detector_still_bites_and_spares_both_ways(
    tmp_path, monkeypatch
) -> None:
    """Le versant qui MORD **et** le versant licite, dans le même test.

    Absent → l'URL du CDN, sinon une app fraîchement clonée casserait.
    Présent → la route locale, sinon le rapatriement ne sert à rien.
    """
    monkeypatch.chdir(tmp_path)
    asset = vendor.vendored_assets()[0]

    assert vendor.url_for(asset) == asset.url, (
        "cache vide et le shell pointe déjà sur la route locale — la page "
        "chargerait un 404."
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
