"""features/geo — facade: the geocoder, behind a stable API.

A ``kind="facade"`` feature: it hides an external system behind a surface
that does not move. Stubbed here — a real app would make an HTTP call and
handle its quota, its cache and its outages. What the feature DECLARES is
that its callers know only :func:`geocode`: the day the provider changes,
one file moves.

The accounts carry a city and a country (`accounts.city`,
`accounts.country`), so the need is real in this app: it is what allows
grouping a portfolio by area.

Taken over from the `mad` app's geocoder on 2026-09-10, when it was
removed. The gesture is not a courtesy relocation: `facade` and `job`
were exercised ONLY there, and nothing gated that coverage — it is
``tests/consistency/test_every_feature_kind_is_exercised.py`` that has
held it since.
"""

from __future__ import annotations

from bretzel import Feature

#: Stub: city → (latitude, longitude). The test set's cities.
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
    """A city's coordinates — ``(0.0, 0.0)`` if the geocoder does not know.

    Returning a neutral pair rather than raising is a facade's choice:
    the caller is drawing a map, it does not have to handle a third-party
    service's failure for one portfolio row.
    """
    return _COORDS.get(ville, (0.0, 0.0))


def distance_km(ville_a: str, ville_b: str) -> float:
    """As-the-crow-flies distance, in kilometres.

    An equirectangular approximation: enough to order visits at the scale
    of a country, and with no dependency.
    """
    import math

    (lat_a, lon_a), (lat_b, lon_b) = geocode(ville_a), geocode(ville_b)
    moyenne = math.radians((lat_a + lat_b) / 2)
    dx = math.radians(lon_b - lon_a) * math.cos(moyenne)
    dy = math.radians(lat_b - lat_a)
    return round(math.hypot(dx, dy) * 6371.0, 1)


feature = Feature(name="geo", kind="facade", provides=[geocode, distance_km])
