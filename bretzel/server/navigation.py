"""Envoyer le navigateur ailleurs — depuis un handler ou depuis un middleware.

Pourquoi un module, et pourquoi celui-ci
-----------------------------------------
``server/`` donne son module nommé à chaque helper appelable : ``auth.py``,
``idempotency.py``. ``redirect`` faisait exception et cohabitait dans
``errors.py`` — dont le docstring avait dû s'élargir en « les sorties
non-nominales d'un handler » pour l'accueillir. Or une redirection après
un enregistrement réussi est la sortie **nominale** : c'est le cas
d'usage central de la fonction. Le nom du fichier disait le contraire de
ce que le code fait.

Les deux publics, et pourquoi il faut les deux
------------------------------------------------
Une app Bretzel envoie le navigateur ailleurs depuis **deux** endroits, et
ils n'ont pas les mêmes moyens :

- **un handler** — il a un :class:`RenderContext`, donc :func:`redirect`
  lui suffit : elle pose l'en-tête sur la réponse en cours ;
- **un middleware utilisateur** — il n'en a pas. Il est monté le plus
  EXTERNE (``lifecycle.py`` : « user middlewares last so they wrap
  everything above »), donc à l'inbound il tourne AVANT
  ``RenderContextMiddleware`` : ``current_context()`` lève. C'est là que
  vit la garde d'auth (« pas connecté → /login »), c'est-à-dire le cas de
  redirection le plus courant d'une vraie app.

Sans ce module, ce second public n'avait rien à appeler — seulement
quelque chose à recopier. Et ce qu'il aurait recopié est le piège
non-évident du sujet : **un middleware voit deux natures de requête.**

Sur un GET de page, il faut une vraie ``302``. Sur un POST d'action venant
du bridge, il faut un ``200`` + ``HX-Redirect`` : une 302 serait suivie de
façon transparente par ``fetch``, et le HTML de ``/login`` finirait swappé
**dans le bouton** qui a déclenché l'action. Chaque utilisateur
redécouvrirait ça au débogage.

:func:`redirect_response` est donc l'unité réutilisable — « envoyer ce
navigateur ailleurs, vu la nature de CETTE requête » — et :func:`redirect`
en devient l'enveloppe fine liée au contexte. Une seule décision
302-vs-200, écrite une fois.
"""

from __future__ import annotations

from typing import Any

from starlette.responses import RedirectResponse, Response

from bretzel.core.errors import BretzelError

__all__ = [
    "redirect",
    "redirect_response",
    "reload",
    "push_url",
    "response_is_read_by_htmx",
]

#: Caractères qui, dans une valeur d'en-tête, coupent l'en-tête et laissent
#: écrire les suivants (response splitting). Une URL de redirection vient
#: souvent d'une donnée utilisateur (``?next=``), donc on refuse plutôt que
#: de faire confiance à la couche du dessous.
_HEADER_UNSAFE = ("\r", "\n", "\0")

#: L'en-tête qu'htmx traite nativement (``render/shell.py`` charge htmx en
#: entier). Il n'y a donc AUCUN code runtime Bretzel derrière tout ce
#: module.
_HX_REDIRECT = "HX-Redirect"

#: Le TROISIÈME membre de la famille — celui qui change l'adresse SANS
#: naviguer. ``HX-Redirect`` fait aller ailleurs, ``HX-Refresh`` fait
#: recharger, ``HX-Push-Url`` se contente d'empiler une entrée
#: d'historique sur la page qu'on regarde déjà.
#:
#: C'est ce qui manquait pour qu'une vue ait une adresse : le contenu
#: arrive par le swap de l'action, l'adresse par cet en-tête, et le
#: bouton retour redemande l'URL au serveur (le cache htmx est à zéro,
#: cf. ``render/shell.py``) qui la relit et rend la même vue.
_HX_PUSH_URL = "HX-Push-Url"


def _validate(url: str) -> None:
    if not isinstance(url, str) or not url:
        raise TypeError("redirect() expects a non-empty URL")
    if any(ch in url for ch in _HEADER_UNSAFE):
        raise ValueError(
            "L'URL de redirection contient un caractère de contrôle "
            "(CR / LF / NUL) — refusé : dans un en-tête, il permettrait "
            "d'en écrire d'autres."
        )


def response_is_read_by_htmx(request: Any) -> bool:
    """``True`` si htmx traitera les en-têtes de la réponse à ``request``.

    Le marqueur est l'en-tête ``HX-Request``, qu'htmx pose sur toute
    requête qu'il émet. Comparaison à ``"true"`` et non à ``None`` : c'est
    la valeur qu'htmx envoie, et c'est déjà la lecture que fait
    ``server/routing/pages.py``.

    Le ``getattr`` sur ``.headers`` suit la convention de
    ``auth.request_scheme`` : les stubs bas niveau des tests unitaires
    passent ``request=object()``, donc l'absence de ``headers`` est le
    seul cas réel à absorber. Une requête sans en-têtes est traitée comme
    non-htmx : le défaut sûr est celui qui parle.

    ⚠️ ``ctx.is_action`` aurait l'air d'un meilleur proxy. Il ne l'est pas,
    pour deux raisons : il raterait la nav partielle et le rafraîchissement,
    et surtout **rien ne l'affecte à ``True``** dans le framework. Ce champ
    réservé est suivi dans ``.claude/work/todo.md``.
    """
    headers = getattr(request, "headers", None)
    return headers is not None and headers.get("HX-Request") == "true"


def redirect_response(request: Any, url: str, *, status_code: int = 302) -> Response:
    """Une réponse qui envoie ``request`` vers ``url``, quelle que soit sa nature.

    **C'est la primitive du middleware.** Elle ne touche à aucun contexte
    de rendu, donc elle est appelable là où ``redirect()`` ne l'est pas —
    typiquement une garde d'auth ::

        from bretzel.server.navigation import redirect_response

        @app.middleware
        async def require_login(request, call_next):
            if request.url.path not in PUBLIC and not signed_in(request):
                return redirect_response(request, "/login")
            return await call_next(request)

    Elle tranche la seule question qui compte ici, et une fois pour
    toutes : **qui va lire cette réponse ?**

    - une navigation ordinaire → une vraie ``302``, que le navigateur
      suit ;
    - une requête émise par htmx (action, rafraîchissement, nav partielle
      boostée) → un ``200`` + ``HX-Redirect``. Une 302 y serait suivie de
      façon **transparente** par ``fetch``, et le HTML de la cible
      finirait swappé dans l'élément qui a déclenché la requête — le
      bouton, la ligne de tableau. C'est le bug que tout le monde
      redécouvre au débogage, et la raison d'être de cette fonction.

    ``status_code`` ne s'applique qu'à la branche navigateur (303 après un
    POST de formulaire nu, 307/308 pour préserver la méthode).
    """
    _validate(url)
    if response_is_read_by_htmx(request):
        # Corps vide : htmx lit l'en-tête et navigue, il ne swappe rien.
        return Response(status_code=200, headers={_HX_REDIRECT: url})
    return RedirectResponse(url, status_code=status_code)


def redirect(url: str) -> None:
    """Navigate the browser to ``url`` after the current request."""
    from bretzel.render.context import current_context

    _validate(url)
    ctx = current_context()
    if not response_is_read_by_htmx(ctx.request):
        raise BretzelError(
            "redirect() n'a d'effet que sur une réponse lue par htmx "
            "(une action, un rafraîchissement, ou une navigation partielle "
            "boostée) — la requête courante est un rendu de page classique, "
            "où l'en-tête HX-Redirect serait ignoré en silence. Depuis un "
            "middleware, appelle redirect_response(request, url) : il n'a "
            "pas de contexte de rendu et peut répondre une vraie 302. Pour "
            "refuser la page plutôt que rediriger, abort(401) + @error_page(401)."
        )
    ctx.set_header(_HX_REDIRECT, url)


def push_url(url: str) -> None:
    """Change the displayed URL without navigating or reloading the page."""
    from bretzel.render.context import current_context

    _validate(url)
    ctx = current_context()
    if not response_is_read_by_htmx(ctx.request):
        raise BretzelError(
            "push_url() n'a d'effet que sur une réponse lue par htmx — "
            "la requête courante est un rendu de page classique, où "
            "l'en-tête serait ignoré en silence. Sur un rendu de page, "
            "l'adresse est DÉJÀ celle que le navigateur affiche : il n'y "
            "a rien à pousser."
        )
    ctx.set_header(_HX_PUSH_URL, url)


#: L'en-tête par lequel htmx recharge la page qu'il affiche. TROISIÈME
#: membre de la famille de ``_HX_REDIRECT`` : les trois façons d'agir sur
#: la barre d'adresse depuis une réponse — aller ailleurs, recharger, ou
#: renommer sans bouger — et ce module les possède toutes, comme son
#: en-tête le revendique.
_HX_REFRESH = "HX-Refresh"


def reload() -> None:
    """Reload the page displayed by the browser after the current request."""
    from bretzel.render.context import current_context

    ctx = current_context()
    if not response_is_read_by_htmx(ctx.request):
        raise BretzelError(
            "reload() n'a d'effet que sur une réponse lue par htmx "
            "(une action, un rafraîchissement, ou une navigation partielle "
            "boostée) — la requête courante est un rendu de page classique, "
            "où l'en-tête HX-Refresh serait ignoré en silence."
        )
    ctx.set_header(_HX_REFRESH, "true")
