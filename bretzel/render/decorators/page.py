"""``@page`` — register a function as a routed page handler.

Decorators in Bretzel are intentionally pure markers. The decorated
function gets a ``_bz_page`` :class:`PageMeta` attached and is added
to the app's ``_pages`` list ; the routing layer (Layer 6) walks that
list at startup to register FastAPI routes.

"""

from __future__ import annotations

import inspect
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from bretzel.core.errors import BretzelError


class PageAlreadyMarkedError(BretzelError):
    """Deux ``@page`` sur la MEME fonction — la seconde effacerait la premiere.

    Levee a la DECORATION, donc a l'import : elle ne voyage jamais
    jusqu'a la couche serveur, et le mapping ``500`` de sa classe mere ne
    s'applique pas. Elle porte son propre nom pour qu'un test puisse la
    viser sans attraper toutes les pannes du framework.
    """


@dataclass(frozen=True, slots=True)
class PageMeta:
    """Captured at decoration time, read by the route registrar."""

    path: str
    layout: Callable[..., Any] | None
    title: str | None
    description: str | None
    shell: Callable[..., Any] | None
    methods: tuple[str, ...]
    signature: inspect.Signature


def page(
    path: str,
    *,
    layout: Callable[..., Any] | None = None,
    title: str | None = None,
    description: str | None = None,
    shell: Callable[..., Any] | None = None,
    methods: tuple[str, ...] = ("GET",),
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Mark ``fn`` as the handler for ``GET path`` (or other methods).

    Free decorator — imported from ``bretzel``, needs no app instance.
    It only MARKS the function (stamps ``_bz_page``) ; the app picks it
    up at :meth:`Bretzel.include` time and registers the FastAPI route.
    Import order has no effect (charter anti-rule #4). Usage ::

        from bretzel import page

        @page("/cart", layout=main_layout, title="Your Cart")
        def cart_page():
            ...

    Static title / description bake into the document head ; for
    dynamic meta drop ``ui.title(...)`` inside the page function.
    """

    def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
        # Capture inspection now — at decoration time we still have
        # the user's original annotations / defaults intact.
        meta = PageMeta(
            path=path,
            layout=layout,
            title=title,
            description=description,
            shell=shell,
            methods=tuple(m.upper() for m in methods),
            signature=inspect.signature(fn),
        )
        # ⚠️ La marque vit SUR L'OBJET FONCTION, donc une seconde
        # décoration de la MÊME fonction écrase la première — et la
        # première route disparaît, en 404, dans une app qu'on n'est même
        # pas en train de lire.
        #
        # Mesuré le 2026-08-29 : deux bancs de ``tests/probes/`` faisaient
        # ``page("/")(sidebar_feat.page)`` sur la fonction que le
        # playground montait déjà en ``/sidebar``. Importer l'un des deux
        # bancs — ce que fait n'importe quelle gate qui balaie
        # ``tests/probes`` — suffisait à rendre ``/sidebar`` et
        # ``/datatable_solo`` introuvables. C'est la cause des deux rouges
        # « la suite rapide dépend de l'ORDRE » : sous ``xdist``, le
        # worker qui hérite d'un banc perd les deux pages ; en séquentiel
        # l'ordre les épargnait.
        #
        # Le refus est explicite plutôt que silencieux, et il ne coûte
        # rien au cas légitime : monter la même fonction deux fois se
        # dit ``page("/b")(lambda: feat.page())`` — une fonction par
        # route, ce que la marque suppose déjà.
        seen = getattr(fn, "_bz_page", None)
        if seen is not None and seen != meta:
            raise PageAlreadyMarkedError(
                f"{getattr(fn, '__qualname__', fn)!r} est déjà marquée pour "
                f"{seen.path!r} et on la remarque pour {path!r}. La marque "
                f"vit sur l'objet fonction : la seconde ÉCRASE la première, "
                f"donc {seen.path!r} deviendrait un 404 sans un mot — y "
                f"compris dans une autre app du meme process. "
                f"Pour monter la meme page a deux endroits, donne-lui "
                f"deux fonctions : `page({path!r})(lambda: mod.page())`."
            )
        fn._bz_page = meta  # type: ignore[attr-defined]
        return fn

    return decorator
