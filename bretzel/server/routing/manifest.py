"""``GET /manifest.webmanifest`` — le manifeste de l'app, quand elle en déclare un.

Route montée seulement si ``Bretzel(pwa=…)`` est renseigné : une app qui
ne demande rien ne porte pas le vocabulaire.

⚠️ Le type MIME est ``application/manifest+json`` et pas
``application/json``. Ce n'est pas de la coquetterie : c'est ce que la
spec impose, et les outils de diagnostic des navigateurs refusent le
manifeste servi autrement — donc l'app paraîtrait non installable sans
qu'aucune erreur ne le dise.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from starlette.responses import Response

from bretzel.server.pwa import MANIFEST_ROUTE

if TYPE_CHECKING:
    from fastapi import FastAPI

    from bretzel.render.types import BretzelApp


def register_manifest_route(fastapi: FastAPI, bretzel_app: BretzelApp) -> None:
    """Monte la route du manifeste, s'il y a un manifeste."""
    pwa = getattr(bretzel_app.config, "pwa", None)
    if pwa is None:
        return

    corps = pwa.as_json()

    @fastapi.get(MANIFEST_ROUTE, include_in_schema=False)
    async def _manifest() -> Response:
        return Response(corps, media_type="application/manifest+json")
