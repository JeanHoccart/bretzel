"""Playground entry point — run with ``py -m examples.playground.main``."""

from fastapi import Request, Response

from bretzel import PWA, Bretzel

app = Bretzel(
    title="Bretzel · Playground",
    secret_key="dev-playground-secret-change-me",
    mode="dev",
    # Le playground est aussi le banc d'essai de la CSP — en BLOCAGE,
    # pas en observation : une politique qu'on ne fait qu'observer ne
    # prouve rien. Bretzel calcule déjà ce qu'il se doit (les empreintes
    # de ses scripts inline, ``'unsafe-eval'``, les hôtes d'icônes, les
    # origines de ses assets) ; ce qui suit est ce que l'APP charge, et
    # rien d'autre. Cf. ``.claude/bretzel/security.md``.
    csp=True,
    csp_sources={
        "img-src": [
            # Les avatars de démonstration de ``/avatar``.
            "https://i.pravatar.cc",
            # ⚠️ Déclaré alors qu'il ne répondra JAMAIS : ``/avatar``
            # démontre le repli sur les initiales quand l'image échoue,
            # et cette URL est fausse exprès. Sans cette ligne elle
            # échouerait quand même — mais pour la mauvaise raison, en
            # laissant une violation CSP permanente dans la console du
            # banc d'essai, là où « zéro violation » est le signal utile.
            "https://invalid.example",
        ],
        # ``/iframe`` monte un ``ui.iframe(src="data:text/html,…")``.
        # Ce n'est PAS un défaut du framework : Bretzel ne peut pas
        # savoir qu'une app veut des iframes ``data:``, et l'autoriser
        # d'office élargirait la politique de toutes les autres.
        "frame-src": ["data:"],
    },
    # Le playground se déclare INSTALLABLE — c'est le banc d'essai de
    # ``PWA``, au même titre qu'il est celui des composants.
    #
    # ``icon=`` prend la marque du framework, qui est un SVG : c'est le
    # cas où ``sizes="any"`` est EXACT et non une approximation
    # tolérée. Pas de ``maskable`` — le dessin n'a pas la marge que le
    # rognage d'Android demande, et le déclarer ferait couper dedans.
    #
    # Pour l'essayer : ouvrir le playground sur ``localhost`` (un
    # contexte sécurisé), puis l'icône d'installation de la barre
    # d'adresse. ⚠️ Chrome a longtemps exigé EN PLUS un service worker
    # pour la proposer, et Bretzel n'en livre pas — si l'invite
    # n'apparaît pas, c'est ça, pas le manifeste : lui est validé par
    # Chromium (``tests/probes/probe_pwa.py``).
    pwa=PWA(
        name="Bretzel Playground",
        short_name="Bretzel",
        description="Le banc d'essai des composants Bretzel.",
        icon="/_bretzel/favicon.svg",
        theme_color="#2f5fd0",
        background_color="#f8fafc",
    ),
)

# Routes / error pages are pure declarations (they import only
# ``bretzel``). Importing runs the ``@page`` / ``@error`` marks ;
# ``include`` registers them. This is the only place that knows the app.
from examples.playground.app import routes      # noqa: E402 — builds routes.PAGES
from examples.playground.infra import errors    # noqa: E402 — @error handlers

app.include(routes.PAGES, errors)


@app.fastapi.post("/_demo/upload")
async def demo_upload(request: Request) -> dict[str, object]:
    """Cible d'upload pour les cartes ``upload_url=`` du playground.

    Le mode async de ``ui.file_upload`` POSTe chaque fichier et n'émet
    ``upload_complete`` que sur une réponse 2xx — sans vraie cible, la
    page ne peut démontrer ni la barre de progression ni l'event. On
    consomme le corps et on le jette : c'est une démo, rien n'est stocké.

    Le CSRF s'applique ici comme sur tout POST hors ``/_bretzel/action/*``
    (le slab envoie le header depuis ``$bz._csrf``) — donc cet endpoint
    exerce aussi ce chemin pour de vrai.
    """
    form = await request.form()
    upload = form.get("file")
    size = len(await upload.read()) if hasattr(upload, "read") else 0
    name = getattr(upload, "filename", "") or ""
    return {"ok": True, "name": name, "size": size}


@app.fastapi.post("/_demo/upload-fail")
async def demo_upload_fail() -> Response:
    """Cible qui échoue exprès, pour la carte ``upload_error``.

    ``upload_error`` ne fire que sur une réponse non-2xx. Tant que la
    carte pointait sur la cible qui réussit, l'event était indémontrable —
    il ne se déclenchait que par accident, quand l'upload était cassé pour
    une autre raison (c'était le cas avec le 403 CSRF).
    """
    return Response(status_code=500, content="demo failure")


if __name__ == "__main__":
    app.run(port=8001, reload=True)
