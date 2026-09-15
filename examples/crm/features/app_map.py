"""Feature ``app_map`` — la carte de l'app CRM.

Tout le rendu vit dans le renderer partagé ``examples/shared/app_map_view.py``,
réutilisé par mad. Ici il ne reste que le ``@page`` qui fournit le
shell du CRM.

C'est l'app du dépôt où la carte dit le plus. Elle ne cite pas de chiffre :
la version précédente en annonçait dix, et la tranche suivante en a ajouté
huit sans que la phrase bouge — un compte recopié à la main dérive plus vite
qu'il ne sert, et la page l'affiche elle-même, à jour par construction.
"""

from __future__ import annotations

from bretzel import Feature, page
from examples.crm.features.shell import shell
from examples.shared.app_map_view import render_app_map


@page("/_map", layout=shell, title="Carte de l'app")
def app_map_page() -> None:
    render_app_map()


feature = Feature(name="app_map", kind="page", provides=[app_map_page])
