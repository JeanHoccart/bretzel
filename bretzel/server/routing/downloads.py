"""Le montage des routes ``@download``.

Une route par fonction marquée, en ``GET``, servie comme un fichier
(``Content-Disposition: attachment``). Aucune signature dans l'URL —
cf. la docstring du décorateur pour la raison, qui est la différence de
fond avec l'export du datatable.
"""

from __future__ import annotations

import mimetypes
from contextlib import nullcontext
from typing import TYPE_CHECKING, Any

from starlette.responses import Response

from bretzel.core import call_without_blocking
from bretzel.render.context import maybe_current_context
from bretzel.server.routing._csv import columns_of, to_csv
from bretzel.state.registry import use_registry

if TYPE_CHECKING:
    from fastapi import FastAPI

    from bretzel.render.types import BretzelApp


#: Les types que le framework CONNAÎT, consultés AVANT ``mimetypes``.
#:
#: ⚠️ ``mimetypes.guess_type`` n'est pas reproductible : sous Windows il
#: lit le REGISTRE (``HKCR``), donc sa réponse dépend des logiciels
#: installés sur la machine. Mesuré le 2026-09-02 sur une machine avec
#: Excel : ``.csv`` → ``application/vnd.ms-excel``. Sur un serveur Linux
#: sans Excel, le même code aurait rendu ``text/csv``.
#:
#: Un en-tête de réponse qui change selon le poste du développeur est un
#: mode d'échec silencieux : ça marche chez toi, ça se comporte
#: autrement en production, et rien ne le dit. Cette table est ce qui
#: rend la sortie déterministe pour les formats que Bretzel produit
#: lui-même ; ``mimetypes`` reste le repli pour tout le reste.
_TYPES_CONNUS: dict[str, str] = {
    ".csv": "text/csv; charset=utf-8",
    ".txt": "text/plain; charset=utf-8",
    ".json": "application/json",
    ".md": "text/markdown; charset=utf-8",
    ".svg": "image/svg+xml",
}


def _type_de(nom: str, defaut: str) -> str:
    """Le type MIME de ``nom`` — table connue, puis ``mimetypes``, puis défaut."""
    point = nom.rfind(".")
    if point != -1:
        extension = nom[point:].lower()
        if extension in _TYPES_CONNUS:
            return _TYPES_CONNUS[extension]
        devine, _ = mimetypes.guess_type(nom)
        if devine:
            return devine
    return defaut


def _read_dict_cell(row: Any, key: str) -> Any:
    return row.get(key)


def _coerce(valeur: Any, meta: Any) -> Response:
    """La valeur rendue par la fonction → une réponse HTTP de fichier.

    Quatre formes acceptées, et l'ordre des tests compte : une
    ``Response`` passe AVANT tout le reste, sinon l'échappatoire ne
    serait pas une échappatoire.
    """
    if isinstance(valeur, Response):
        return valeur

    if isinstance(valeur, bytes):
        corps: Any = valeur
        type_defaut = "application/octet-stream"
    elif isinstance(valeur, str):
        corps = valeur
        type_defaut = "text/plain; charset=utf-8"
    elif isinstance(valeur, list):
        corps = to_csv(valeur, columns_of(valeur), _read_dict_cell)
        type_defaut = "text/csv; charset=utf-8"
    else:
        raise TypeError(
            f"@download({meta.path!r}) a rendu un {type(valeur).__name__}. "
            f"Les formes acceptées sont : list[dict] (→ CSV), str, bytes, "
            f"ou une ``Response`` construite à la main. Rendre autre chose "
            f"ne peut pas être deviné — un fichier a un type et un "
            f"encodage, et les inventer ferait télécharger n'importe quoi "
            f"sous n'importe quel nom."
        )

    # Le type déduit du NOM prime sur le défaut de la forme : un
    # ``@download("/plan.svg")`` qui rend une ``str`` sert bien du SVG.
    return Response(
        corps,
        media_type=meta.media_type or _type_de(meta.filename, type_defaut),
        headers={
            "Content-Disposition": f'attachment; filename="{meta.filename}"'
        },
    )


def register_download_routes(
    fastapi: FastAPI, bretzel_app: BretzelApp, fonctions: Any
) -> None:
    """Monte une route ``GET`` par fonction portant ``_bz_download``."""
    for fonction in fonctions:
        meta = getattr(fonction, "_bz_download", None)
        if meta is None:      # pragma: no cover — l'appelant filtre déjà
            continue
        _monter(fastapi, fonction, meta)


def _monter(fastapi: FastAPI, fonction: Any, meta: Any) -> None:
    """Une fermeture par route — sinon les N routes partagent la
    dernière ``fonction`` de la boucle, le piège classique."""

    @fastapi.get(meta.path, include_in_schema=False)
    async def _servir() -> Response:
        # Le code de l'appelant tourne DANS le registre d'état de la
        # requête, comme aux quatre autres points d'entrée (rendu de
        # page, action, refetch temps réel, export datatable). Sans ça,
        # deux ``MonEtat()`` dans la même fonction rendent deux objets
        # DIFFÉRENTS — mesuré sur l'export, qui avait été écrit nu.
        contexte = maybe_current_context()
        registre = getattr(contexte, "state_registry", None) if contexte else None
        with use_registry(registre) if registre is not None else nullcontext():
            # Une fonction qui va chercher des lignes en base est la
            # raison d'être de ce routable : awaitée si ``async``,
            # délestée sur le threadpool si ``def`` — sinon elle gèle la
            # boucle le temps du téléchargement (cf. ``core/invoke``).
            valeur = await call_without_blocking(fonction)
        return _coerce(valeur, meta)

    _servir.__name__ = f"_download_{meta.filename.replace('.', '_')}"
