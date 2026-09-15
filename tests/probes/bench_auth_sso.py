"""``examples/auth`` branchée sur le fournisseur de test (port 8953).

Le banc ne change pas une ligne de l'app : il pose les variables
d'environnement AVANT de l'importer, exactement comme un déploiement le
ferait. C'est ce qui rend la mesure honnête — ce qui tourne est le code
d'exemple, pas un montage.

Run :  py tests/probes/bench_auth_sso.py  (le fournisseur doit tourner)
"""

from __future__ import annotations

import os

# Les identifiants viennent du fournisseur lui-même : les recopier ici
# ferait échouer le probe sur « invalid_client » le jour où l'un change,
# avec un message qui ne désigne pas le fichier fautif.
from examples.auth.local_idp import CLIENT_ID, CLIENT_SECRET, ISSUER

os.environ["BZ_OIDC_NAME"] = "testidp"
os.environ["BZ_OIDC_ISSUER"] = ISSUER
os.environ["BZ_OIDC_CLIENT_ID"] = CLIENT_ID
os.environ["BZ_OIDC_CLIENT_SECRET"] = CLIENT_SECRET
# Le panneau de l'écran écrit ses commandes ``curl`` avec ce port : sans
# ça il proposerait 8012, qui ne répond pas sous ce banc.
os.environ["BZ_APP_PORT"] = "8953"

# Les imports viennent APRÈS l'environnement, exprès : ``access.py``
# construit ses portes au chargement du module, en lisant ces variables.
import uvicorn

from examples.auth.main import app

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8953, log_level="warning")
