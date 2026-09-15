"""Le fournisseur OIDC local, lancé pour la sonde (port 8954).

Cinq lignes : l'implémentation vit dans ``examples/auth/local_idp``,
parce qu'un humain la lance aussi pour essayer la porte à la main. Deux
copies auraient dérivé, et c'est celle qu'on clique qui doit être celle
qu'on mesure.

Run :  py tests/probes/bench_oidc_provider.py
"""

from __future__ import annotations

import uvicorn

from examples.auth.local_idp import PORT, app

if __name__ == "__main__":
    # ⚠️ ``PORT`` vient du module, il n'est PAS réécrit ici : l'issuer en
    # est dérivé (``local_idp`` le lie exprès), et servir sur un autre
    # port ferait annoncer une identité de fournisseur qu'on ne sert pas —
    # la connexion échouerait sur « id_token émis par un autre issuer ».
    uvicorn.run(app, host="127.0.0.1", port=PORT, log_level="warning")
