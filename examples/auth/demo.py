"""Tout allumé, en UNE commande : ``py -m examples.auth.demo``.

Démarre le fournisseur OIDC local dans un sous-process, pose les quatre
variables qu'il faut, allume la lecture de l'en-tête de proxy, puis sert
l'app. Les quatre façons d'entrer sont actives, et on ferme tout avec un
seul Ctrl+C.

Pourquoi ce fichier existe : la marche à suivre du README demande **deux
terminaux et quatre variables**, et c'est une friction que la démo
n'avait pas à imposer. Le premier essai réel s'est soldé par un
``ERR_CONNECTION_REFUSED`` sur le port de l'app — le fournisseur seul
tournait, ce qui est exactement ce qu'on avait demandé, et pas du tout ce
qu'on voulait.

``main.py`` reste la vraie app, sans rien de tout ça : c'est elle qu'on
lit pour voir comment on branche une porte. Ce fichier n'est qu'un
démarreur de démonstration.

Ports : ``BZ_APP_PORT`` (8012) et ``BZ_IDP_PORT`` (8954) si l'un des deux
est déjà pris.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
import urllib.error
import urllib.request

#: ⚠️ Le jeton et l'en-tête viennent du domaine, ils ne sont PAS recopiés :
#: les changer laissait la bannière donner une commande qui rend 302, et
#: le lecteur accuse la démo.
from examples.auth.core.domain import API_TOKENS, PROXY_HEADER

IDP_PORT = os.environ.get("BZ_IDP_PORT", "8954")
APP_PORT = int(os.environ.get("BZ_APP_PORT", "8012"))
ISSUER = f"http://localhost:{IDP_PORT}"
TOKEN = next(iter(API_TOKENS))


def wait_for_idp(deadline: float = 20.0) -> bool:
    """Attend que la découverte réponde — sinon la porte ne se monterait pas."""
    url = f"{ISSUER}/.well-known/openid-configuration"
    started = time.monotonic()
    while time.monotonic() - started < deadline:
        try:
            with urllib.request.urlopen(url, timeout=1):
                return True
        except (urllib.error.URLError, OSError):
            time.sleep(0.3)
    return False


def main() -> int:
    env = dict(os.environ)
    env["BZ_IDP_PORT"] = IDP_PORT
    idp = subprocess.Popen(
        [sys.executable, "-m", "examples.auth.local_idp"], env=env
    )
    try:
        if not wait_for_idp():
            print(
                f"Le fournisseur n'a pas démarré sur {ISSUER} — le port est "
                "probablement pris. Relance avec BZ_IDP_PORT=8964.",
                flush=True,
            )
            return 1

        # ⚠️ Les variables sont posées AVANT d'importer l'app : c'est au
        # chargement de ``features/access.py`` que les portes sont
        # construites. Un import plus haut dans ce fichier aurait tout
        # figé sans porte, silencieusement.
        os.environ["BZ_OIDC_NAME"] = "testidp"
        os.environ["BZ_OIDC_ISSUER"] = ISSUER
        os.environ["BZ_OIDC_CLIENT_ID"] = "bretzel-test-client"
        os.environ["BZ_OIDC_CLIENT_SECRET"] = "bretzel-test-secret"
        os.environ["BZ_TRUST_PROXY_HEADER"] = "1"

        from examples.auth.main import app

        print(
            "\n"
            f"  Démo auth — les quatre façons sont actives\n"
            f"  ouvre  http://127.0.0.1:{APP_PORT}\n\n"
            "  1. mot de passe        jean@macorp.fr / demo\n"
            "  2. porte OIDC          bouton « Continuer avec testidp »\n"
            "\n  Les deux suivantes n'ont pas d'écran : colle la commande\n"
            "  dans un AUTRE terminal, elle répond trois lignes.\n\n"
            f'  3. jeton de machine    curl.exe -s -H "Authorization: Bearer '
            f'{TOKEN}" http://127.0.0.1:{APP_PORT}/moi\n'
            f'  4. en-tête de proxy    curl.exe -s -H "{PROXY_HEADER}: '
            f'jean@macorp.fr" http://127.0.0.1:{APP_PORT}/moi\n\n'
            "  Ctrl+C ferme les deux serveurs.\n",
            flush=True,
        )
        app.run(port=APP_PORT)
    except KeyboardInterrupt:
        pass
    finally:
        idp.terminate()
        try:
            idp.wait(timeout=10)
        except subprocess.TimeoutExpired:
            idp.kill()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
