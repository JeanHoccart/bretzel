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
        raise TypeError("redirect() attend une URL non vide.")
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
    """Faire naviguer le navigateur vers ``url`` à la fin de cette requête.

    Le cas que ça couvre est celui qu'un ``ui.link`` ne PEUT pas couvrir :
    l'URL n'existe qu'après la mutation. ::

        def save():
            invoice = create_invoice(...)
            redirect(f"/factures/{invoice.id}")

    Pour tout le reste — un menu, une ligne cliquable, un fil d'Ariane —
    la navigation est déclarative et reste un ``ui.link(href=…)``.

    Mécanique : on pose l'en-tête ``HX-Redirect``, qu'htmx traite
    nativement. Il n'y a donc **aucun** code runtime derrière cette
    fonction, et l'en-tête voyage par le canal qui existait déjà —
    ``ctx.response_headers``, que les trois sorties recopient (page,
    partiel, action). C'est le même schéma que :func:`bretzel.auth.login` :
    une fonction appelée depuis un handler, dont l'effet transite par le
    contexte de requête.

    Pas de sortie non-locale, contrairement à :func:`bretzel.abort` :
    l'appel pose l'en-tête et le handler continue. C'est ce que lit un
    humain de haut en bas, et ça évite d'avoir à rattraper une exception
    de contrôle dans les trois routes.

    Lève :class:`BretzelError` si la réponse ne sera pas lue par htmx —
    un rendu de page classique, où l'en-tête serait parfaitement invisible.
    Depuis un **middleware**, ce n'est pas la bonne fonction : il n'a pas
    de contexte de rendu, et il peut répondre une vraie 302. Appeler
    :func:`redirect_response`, qui tranche 302-vs-200 pour lui.
    """
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
    """Changer l'adresse affichée, **sans** naviguer ni recharger.

    C'est le mécanisme par lequel une vue devient adressable : trier une
    table, choisir un filtre, ouvrir un onglet — le contenu arrive par le
    swap que l'action renvoie déjà, et cette fonction fait suivre la
    barre d'adresse. Le bouton retour redemande alors l'URL au serveur,
    qui la relit et rend la même vue.

    **Le socle l'appelle pour toi** quand un champ déclaré ``URL = {…}``
    sur un état a bougé (cf. :mod:`bretzel.state.url`). L'appel direct
    est l'échappatoire : une adresse que le framework ne peut pas
    deviner. ::

        def open_step(n: int) -> None:
            Wizard().step = n
            push_url(f"/inscription/etape-{n}")

    Même canal et mêmes gardes que :func:`redirect` — un caractère de
    contrôle est refusé, parce que dans un en-tête il permettrait d'en
    écrire d'autres.

    ⚠️ Ne PAS confondre avec :func:`redirect` : celle-ci fait charger une
    autre page, celle-là ne fait que renommer celle qu'on regarde. Poser
    l'une pour l'autre donne soit une navigation qu'on n'a pas demandée,
    soit une adresse qui ment sur ce qui est affiché.
    """
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
    """Recharger la page que le navigateur affiche, à la fin de la requête.

    Le pendant de :func:`redirect` pour le cas où la cible EST la page
    courante — un changement de langue, de locataire, de devise : quelque
    chose qui rend toute la page autrement, y compris la coque et les
    zones qu'aucune action ne touche.

    ``redirect()`` ne peut pas le faire, et ce n'est pas un oubli : une
    action POSTe vers ``/_bretzel/action/<id>``, donc le serveur n'a PAS
    l'URL de la page sous la main. La lui faire deviner voudrait dire lire
    le ``Referer`` — exactement la fragilité du décorateur ``@loading`` de
    la V1. ``HX-Refresh`` évite la question : le navigateur, lui, connaît
    son URL.

    Pourquoi RECHARGER plutôt que re-rendre : une réponse d'action ne
    rapporte que les zones qu'elle a rafraîchies. Sur un changement qui
    touche toute la page, un re-rendu partiel laisse une moitié dans
    l'ancien état — pire que d'attendre un aller-retour.

    Comme :func:`redirect`, sans effet hors d'une réponse lue par htmx.

    À distinguer de :func:`bretzel.refresh`, qui re-rend un sous-arbre côté
    serveur et le renvoie en swap OOB.
    """
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
