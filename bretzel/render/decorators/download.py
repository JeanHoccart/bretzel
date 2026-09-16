"""``@download`` — le routable qui rend un FICHIER, pas une page.

Tranché en séance (``these-portee-2026-08-19.md`` § 7), livré le
2026-09-02 ::

    @download("/clients.csv")
    async def clients_csv() -> list[dict]:
        return await db.clients()

Pourquoi ce n'est pas une action
---------------------------------
Contrainte héritée, déjà documentée par l'export du datatable : la
réponse d'une action est **avalée par le bridge** et appliquée en
``<bz-patch>``. Un téléchargement doit ÊTRE le fichier. C'est donc un
vrai lien — ``ui.link("Exporter", href="/clients.csv")`` — et pas un
``on_click=``.

Pourquoi il n'est PAS signé, contrairement à l'export du datatable
-------------------------------------------------------------------
C'est la différence qui justifie le nouveau routable, et elle va dans le
bon sens. Le lien du datatable porte dans son URL le NOM de la fonction
à invoquer (``rows_ref``, un ``module::qualname``), donc il doit être
signé — sans quoi l'endpoint deviendrait un « appelle la fonction de mon
choix ». Il en hérite d'être une **capacité au porteur** : quiconque
tient l'URL obtient les lignes, sans lien avec l'utilisateur ni
expiration.

Un ``@download`` ne porte rien de tout ça : la fonction est fixée à la
DÉCORATION, comme pour ``@page``. L'URL ne décide de rien, donc il n'y a
rien à signer — et la route passe par le même middleware que les pages,
donc une app qui protège ses pages protège ses téléchargements sans
écrire une ligne.

Ce que la fonction peut rendre
-------------------------------
=================  ==========================================================
``list[dict]``     un CSV — en-têtes déduits des clés du premier
                   enregistrement
``str``            le texte tel quel
``bytes``          les octets tels quels (un PDF, une image, un zip)
une ``Response``   l'échappatoire — tout ce que le reste ne couvre pas
=================  ==========================================================

Le nom du fichier et le type MIME sont déduits du chemin
(``/clients.csv`` → ``clients.csv``, ``text/csv``), et tous deux se
surchargent.

⚠️ Ce que ça ne fait PAS encore
--------------------------------
``ui.datatable(exportable=True)`` n'est pas rebranché dessus. Le § 7 de
la thèse annonçait que « ``exportable=True`` se réduit à poser un
``@download`` » ; ce n'est pas si simple, et il vaut mieux l'écrire que
de le forcer : l'export du datatable a besoin de la **requête du
lecteur** — le tri, les filtres, la recherche au moment du clic — qui
n'existe pas dans une route statique. C'est ce que son payload signé
transporte. Les rebrancher demande de décider comment une vue voyage
jusqu'à un ``@download``, et c'est une décision, pas un ménage.
"""

from __future__ import annotations

import inspect
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from bretzel.core.errors import BretzelError


class DownloadAlreadyMarkedError(BretzelError):
    """Deux ``@download`` sur la MÊME fonction — la seconde effacerait la première.

    Même refus, même raison et même mesure que
    :class:`~bretzel.render.decorators.page.PageAlreadyMarkedError` : la
    marque vit sur l'objet fonction, donc une seconde décoration rend la
    première route introuvable, en 404, sans un mot.
    """


@dataclass(frozen=True, slots=True)
class DownloadMeta:
    """Capturé à la décoration, lu par l'enregistreur de routes."""

    path: str
    filename: str
    media_type: str | None
    signature: inspect.Signature


def _filename_of(path: str) -> str:
    """``/exports/clients.csv`` → ``clients.csv``.

    Le dernier segment, et rien d'autre : un ``Content-Disposition`` qui
    porterait des barres obliques laisserait le navigateur choisir, et
    ils ne choisissent pas pareil.
    """
    dernier = path.rstrip("/").rsplit("/", 1)[-1]
    return dernier or "download"


def download(
    path: str,
    *,
    filename: str | None = None,
    media_type: str | None = None,
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Mark a function as the producer for a file served at ``GET path``."""
    if not path.startswith("/"):
        raise ValueError(
            f"@download({path!r}) : un chemin de route commence par '/'. "
            f"Sans ça la route se monte à un endroit que personne ne "
            f"devine, et le lien de l'app rend 404."
        )

    def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
        meta = DownloadMeta(
            path=path,
            filename=filename or _filename_of(path),
            media_type=media_type,
            signature=inspect.signature(fn),
        )
        vue = getattr(fn, "_bz_download", None)
        if vue is not None and vue != meta:
            raise DownloadAlreadyMarkedError(
                f"{getattr(fn, '__qualname__', fn)!r} est déjà marquée pour "
                f"{vue.path!r} et on la remarque pour {path!r}. La marque "
                f"vit sur l'objet fonction : la seconde ÉCRASE la "
                f"première, donc {vue.path!r} deviendrait un 404 sans un "
                f"mot. Pour servir le même fichier à deux endroits, "
                f"donne-lui deux fonctions."
            )
        fn._bz_download = meta  # type: ignore[attr-defined]
        return fn

    return decorator
