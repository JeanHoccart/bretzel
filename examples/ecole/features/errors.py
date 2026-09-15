"""features/errors — error : les deux pages d'erreur, dans la coque.

Dans la COQUE et pas nues : une 404 qui perd la barre latérale enferme —
on se retrouve devant un message sans aucun moyen de repartir autrement
qu'avec la flèche du navigateur.
"""

from __future__ import annotations

from bretzel import Feature, error_page, ui
from examples.ecole.features.shell import shell


@error_page(404, layout=shell)
def introuvable() -> None:
    ui.empty_state(
        title="Cette page n'existe pas",
        icon="search-x",
        description="L'application se construit lot par lot ; l'écran que "
                    "vous cherchez n'est peut-être pas encore livré.",
    )


@error_page(500, layout=shell)
def panne() -> None:
    ui.empty_state(
        title="Quelque chose s'est mal passé",
        icon="triangle-alert",
        description="Rien n'a été enregistré. Revenez à l'accueil et "
                    "recommencez.",
    )


feature = Feature(name="errors", kind="error",
                  provides=[introuvable, panne], uses=["shell"])
