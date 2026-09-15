"""features/geo — facade : le géocodeur, derrière une API stable.

Feature ``kind="facade"`` : elle cache un système externe derrière une
surface qui ne bouge pas. Stubbée ici — une vraie app taperait une HTTP
et gérerait son quota, son cache et ses pannes. Ce que la feature
DÉCLARE, c'est que ses appelants ne connaissent que :func:`geocode` :
le jour où le fournisseur change, un seul fichier bouge.

Les comptes portent une ville et un pays (`accounts.city`,
`accounts.country`), donc le besoin est réel dans cette app : c'est ce
qui permet de grouper un portefeuille par zone.

Reprise du géocodeur de l'app `mad` le 2026-09-10, quand elle a été
retirée. Le geste n'est pas un déménagement de
politesse : `facade` et `job` n'étaient exercés QUE là, et rien ne
gatait cette couverture — c'est
``tests/consistency/test_every_feature_kind_is_exercised.py`` qui la
tient depuis.
"""

from __future__ import annotations

from bretzel import Feature

#: Stub : ville → (latitude, longitude). Les villes du jeu de test.
_COORDS: dict[str, tuple[float, float]] = {
    "Paris": (48.86, 2.35),
    "Lyon": (45.76, 4.84),
    "Marseille": (43.30, 5.37),
    "Toulouse": (43.60, 1.44),
    "Bordeaux": (44.84, -0.58),
    "Lille": (50.63, 3.07),
    "Nantes": (47.22, -1.55),
    "Strasbourg": (48.57, 7.75),
}


def geocode(ville: str) -> tuple[float, float]:
    """Coordonnées d'une ville — ``(0.0, 0.0)`` si le géocodeur ne sait pas.

    Rendre un couple neutre plutôt que de lever est le choix d'une
    façade : l'appelant trace une carte, il n'a pas à traiter l'échec
    d'un service tiers pour une ligne de portefeuille.
    """
    return _COORDS.get(ville, (0.0, 0.0))


def distance_km(ville_a: str, ville_b: str) -> float:
    """Distance à vol d'oiseau, en kilomètres.

    Approximation équirectangulaire : suffisante pour ordonner des
    visites à l'échelle d'un pays, et sans dépendance.
    """
    import math

    (lat_a, lon_a), (lat_b, lon_b) = geocode(ville_a), geocode(ville_b)
    moyenne = math.radians((lat_a + lat_b) / 2)
    dx = math.radians(lon_b - lon_a) * math.cos(moyenne)
    dy = math.radians(lat_b - lat_a)
    return round(math.hypot(dx, dy) * 6371.0, 1)


feature = Feature(name="geo", kind="facade", provides=[geocode, distance_km])
