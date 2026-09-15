"""Auth — les quatre façons d'entrer, une seule identité en sortie.

Run : ``py -m examples.auth.main`` (port 8012).

Ce que cette app met sous contrainte, et qu'aucune autre n'exerçait :

1. **le formulaire** — l'app vérifie, ``auth.login(user_id)`` transporte ;
2. **une porte OAuth / OIDC** — ``@auth.door``, configurée par
   l'environnement, qui finit sur le même ``auth.login`` ;
3. **un jeton de machine** — ``@auth.source``, sans cookie ni session,
   revérifié à chaque requête ;
4. **un en-tête de proxy SSO** — ``@auth.source`` aussi, éteint par défaut.

Les quatre aboutissent au même ``auth.user_id()``, donc au même
``UserState``. Les deux derniers n'ont pas d'écran : ils répondent sur
``/moi``, en texte ::

    curl.exe -s -H "Authorization: Bearer jeton-demo" http://127.0.0.1:8012/moi

Tout allumer en une commande : ``py -m examples.auth.demo``.

⚠️ ``secret_key`` est en clair ici parce que c'est une démo locale. Une
app réelle la lit dans son environnement — c'est elle qui dérive la clé
qui signe le cookie d'identité.
"""

from __future__ import annotations

from starlette.requests import Request
from starlette.responses import PlainTextResponse

from bretzel import Bretzel
from bretzel.runtime import is_public_asset_path
from bretzel.server import action_path, auth, redirect_response

from examples.auth.core.domain import LOGIN_PATH, PROXY_HEADER, by_id
from examples.auth.features import access, home, login

app = Bretzel(
    title="Bretzel · Auth",
    secret_key="dev-auth-secret-change-me",
    mode="dev",
)

@app.middleware
async def require_login(request, call_next):
    """La garde. Écrite en premier, donc la plus externe.

    ``auth.user_id(request)`` — avec la requête — parce qu'à ce niveau ni
    le contexte de rendu ni ``request.state`` n'existent encore. C'est
    elle qui joue la chaîne complète : le cookie signé, puis les
    ``@auth.source`` de l'app. Sans ça, un appel au jeton serait renvoyé sur
    la page de connexion.

    ``redirect_response`` et non ``redirect`` : le premier tranche entre
    une vraie 302 (navigation) et un ``HX-Redirect`` (action du bridge) ;
    le second lève hors d'un contexte de rendu.

    ⚠️ **``is_public_asset_path`` et pas seulement l'appartenance à
    ``PUBLIC``.** ``app.public_paths`` contient un MOTIF de route —
    ``/_bretzel/vendor/{filename}`` — qui n'est égal à aucun chemin
    réel, donc l'égalité seule refuse les trois scripts tiers. La garde
    les redirige alors vers la page de connexion, et le navigateur
    reçoit du HTML là où il attend du JavaScript : ``Unexpected token
    '<'`` en boucle, htmx jamais chargé, plus aucun POST. L'app paraît
    morte sans qu'une seule erreur serveur soit émise.

    Ça ne se voit **que si ``.bretzel/vendor/`` existe** : sans cache
    vendorisé, les ``<script>`` pointent les CDN et cette route n'est
    jamais demandée. Donc le symptôme apparaît le jour où quelqu'un
    lance la vendorisation, pas le jour où la garde est écrite.
    """
    if (request.url.path in PUBLIC
            or is_public_asset_path(request.url.path)
            or auth.user_id(request)):
        return await call_next(request)
    return redirect_response(request, LOGIN_PATH)


@app.fastapi.get("/moi")
async def qui_suis_je(request: Request) -> PlainTextResponse:
    """« Qui suis-je ? », en TEXTE — la réponse aux deux façons sans écran.

    Un jeton de machine et un en-tête de proxy n'ouvrent pas de page :
    ils s'essaient au terminal, et le HTML d'une vraie page y est
    illisible. Cette route rend trois lignes, donc la commande ``curl``
    montre enfin quelque chose.

    Elle est DERRIÈRE la garde, exprès : sans identité, on reçoit la
    redirection vers ``/login``, ce qui prouve que c'est bien la garde
    qui a lu le jeton — et pas la route qui serait ouverte.

    ⚠️ Une route brute sur ``app.fastapi`` (échappatoire publique) : le
    framework n'a pas de décorateur pour un routable qui ne rend pas du
    HTML. C'est noté dans ``.claude/work/todo.md`` (@download), et ça
    dépasse cette démo.

    ``request.state.user_id`` est ce que ``AuthMiddleware`` a résolu —
    la même valeur que ``auth.user_id()`` verrait au rendu.
    """
    user_id = getattr(request.state, "user_id", None)
    user = by_id(user_id)
    porte = "cookie de session (navigateur)"
    if request.headers.get("authorization", "").lower().startswith("bearer "):
        porte = "jeton de machine (Authorization: Bearer)"
    elif request.headers.get(PROXY_HEADER):
        porte = f"en-tête de proxy ({PROXY_HEADER})"
    adresse = user["email"] if user else "—"
    return PlainTextResponse(
        "\n".join(
            [
                f"user_id     : {user_id}",
                f"adresse     : {adresse}",
                f"reconnu par : {porte}",
                "",
            ]
        )
    )


app.include(access, login, home)

#: Ce que la garde laisse passer. ``app.public_paths`` porte les assets du
#: runtime ET les deux routes de chaque porte montée — l'app n'a donc rien
#: à énumérer du framework, et une porte ajoutée demain n'oblige à rien.
#:
#: Calculé APRÈS ``include`` : c'est lui qui fait connaître les portes. Le
#: middleware lit ce nom au moment de l'appel, pas au moment où il est
#: décoré, donc l'ordre d'écriture ci-dessus est sans effet.
PUBLIC = {
    LOGIN_PATH,
    # ⚠️ Le formulaire de connexion POSTe une action, et une garde en
    # défaut-fermé la bloque comme le reste. Le symptôme ne ressemble à
    # rien : htmx suit la redirection en transparence, le HTML de /login
    # revient, et le bouton paraît mort — aucune erreur nulle part.
    action_path(login.sign_in),
    *app.public_paths,
}


if __name__ == "__main__":
    app.run(port=8012, reload=True)
