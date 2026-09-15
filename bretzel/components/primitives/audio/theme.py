"""Default :class:`Audio` theme — le plus mince du dépôt, et c'est normal.

Un ``<audio controls>`` est entièrement dessiné par le navigateur : sa
barre, ses boutons, sa hauteur. Un thème qui prétendrait le styler
mentirait — ``background``, ``border-radius`` et ``width`` sont à peu près
tout ce qui traverse.

Pas de ratio ici, contrairement à ``image`` / ``video`` / ``iframe`` : un
lecteur audio a une hauteur FIXE, connue avant le chargement. Il ne
provoque donc aucun saut de page, et la prop n'aurait rien à réserver.
"""

from __future__ import annotations

from typing import Any

AUDIO_THEME: dict[str, Any] = {
    "slots": {
        # ``w-full`` : le lecteur natif prend sinon une largeur arbitraire
        # (~300 px) qui ne s'accorde à aucune colonne.
        "root": "block w-full",
    },
}
