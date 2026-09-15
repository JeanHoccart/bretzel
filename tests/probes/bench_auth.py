"""Bench de l'app ``examples/auth`` (port 8951).

Le banc ne redéfinit RIEN : il sert l'app d'exemple telle quelle. C'est
tout l'objet de la vérification — ce qu'on regarde doit être ce que le
lecteur ouvrira.

Run :  py tests/probes/bench_auth.py
"""

from __future__ import annotations

import os

from tests.probes._serve import bench_port, use_local_tailwind

# ⚠️ Le port se résout AVANT l'import de l'app : l'écran écrit ses
# commandes ``curl`` avec ``BZ_APP_PORT``, et sans lui il proposerait
# 8012, qui ne répond pas sous ce banc. L'ordre compte donc — poser la
# variable après l'import la poserait trop tard.
PORT = bench_port(8951)
os.environ.setdefault("BZ_APP_PORT", str(PORT))

import uvicorn

from examples.auth.main import app

if __name__ == "__main__":
    # Le compilateur CSS depuis 127.0.0.1 et non depuis unpkg :
    # une suite ne doit pas dependre d'un tiers (cf. `_serve`).
    use_local_tailwind()

    uvicorn.run(app, host="127.0.0.1", port=PORT, log_level="warning")
