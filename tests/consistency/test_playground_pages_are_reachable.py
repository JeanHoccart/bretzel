"""Gate : une page du playground enregistrée DOIT être dans la nav.

Les deux listes sont écrites à la main, dans deux fichiers différents :
``app/routes.py`` construit ``PAGES``, ``app/nav.py`` construit ``NAV``.
Rien ne les réconciliait — et les deux sens de la dérive coûtent :

- **route sans entrée de nav** → la page existe, répond 200, passe toutes
  ses gates, et *personne ne peut la trouver*. C'est arrivé le 2026-08-10
  avec ``/dnd`` : le composant était livré, testé au navigateur et
  documenté à l'inventaire, mais absent de la barre latérale. Aucun des
  11 000 tests n'avait de raison de s'en apercevoir, parce que chacun
  visite l'URL directement.
- **entrée de nav sans route** → un lien mort dans la barre, qui rend un
  404 à chaque clic.

⚠️ Ce que cette gate NE fait PAS : juger la section ou l'icône. Le
classement d'une page dans « ACTIONS & LAYOUT » plutôt que « FORMS » est
un choix éditorial, pas un invariant.
"""

from __future__ import annotations

import pytest

from examples.playground.app import nav as nav_module
from examples.playground.app import routes as routes_module

#: Preuve de morsure : contrôle POSITIF sur les DEUX découvertes (pages enregistrées et
#: entrées de nav) — un `⊆` passe trivialement si l'une est vide.
MUTATION_PROOF = "test_both_populations_are_non_trivial"

#: Chemins qui n'ont volontairement PAS d'entrée de nav.
#: Chacun doit porter sa raison — une exemption sans raison est une
#: dérive qui a trouvé un endroit où se garer.
_NOT_IN_NAV: dict[str, str] = {
    "/screen-demo":"le SEUL montage possible d'un ui.viewport — il est "
                    "`fixed inset-0`, donc il recouvrirait la barre "
                    "latérale ; la page est donc enregistrée sans coque, "
                    "et atteinte par un bouton depuis /screen",
}

# ⚠️ Il n'y a plus d'exemption de FAMILLE. ``_REACHED_VIA_HUB`` — le dict
# préfixe→hub qui exemptait les 56 pages de ``/matrix`` — est parti avec
# elles le 2026-08-30, et le test qui le gardait avec. Il n'a pas été
# laissé vide : un ``parametrize`` sur un dict vide ne collecte RIEN et
# ressemble pourtant à de la couverture. Le jour où un hub revient, la
# mécanique se réécrit en dix lignes ; d'ici là, elle ne doit pas donner
# l'illusion de veiller sur quelque chose.


def _is_exempt(path: str) -> bool:
    return path in _NOT_IN_NAV


def _registered_paths() -> set[str]:
    """Les chemins que ``routes.PAGES`` enregistre réellement.

    Lus sur les objets rendus par ``page(...)`` plutôt que sur le source :
    le décorateur est ce qui fait foi, et un renommage de constante
    (``PATH``) ne doit pas rendre cette gate aveugle.
    """
    paths: set[str] = set()
    for entry in routes_module.PAGES:
        path = getattr(entry, "path", None) or getattr(entry, "_bz_path", None)
        if path is None:
            meta = getattr(entry, "_bz_page", None)
            path = getattr(meta, "path", None) if meta else None
        if path:
            paths.add(path)
    return paths


def _nav_paths() -> set[str]:
    return {
        href
        for _section, entries in nav_module.NAV
        for _label, href, _icon in entries
    }


def test_both_populations_are_non_trivial() -> None:
    """Plancher : sans lui, une extraction cassée rendrait les deux
    ensembles vides et les deux tests ci-dessous passeraient à vide."""
    registered, in_nav = _registered_paths(), _nav_paths()
    assert len(registered) > 40, (
        f"seulement {len(registered)} routes extraites de routes.PAGES — "
        f"l'extraction est cassée, pas le playground"
    )
    assert len(in_nav) > 40, (
        f"seulement {len(in_nav)} entrées extraites de nav.NAV — "
        f"l'extraction est cassée"
    )


def test_every_registered_page_is_in_the_nav() -> None:
    missing = sorted(
        p for p in _registered_paths() - _nav_paths() if not _is_exempt(p)
    )
    assert not missing, (
        f"ces pages sont enregistrées mais absentes de la barre latérale : "
        f"{missing}.\n"
        f"  Elles répondent 200 et passent toutes leurs gates — et personne "
        f"ne peut les trouver.\n"
        f"  Ajoute-les à `examples/playground/app/nav.py`, ou déclare "
        f"l'exemption dans _NOT_IN_NAV avec sa raison."
    )


def test_every_nav_entry_points_at_a_real_page() -> None:
    dead = sorted(_nav_paths() - _registered_paths())
    assert not dead, (
        f"ces entrées de nav ne correspondent à aucune page enregistrée : "
        f"{dead} — un clic dessus rend un 404."
    )


@pytest.mark.parametrize("path", sorted(_NOT_IN_NAV))
def test_exemptions_still_correspond_to_a_real_page(path: str) -> None:
    """Une exemption qui survit à la suppression de sa page est du bruit
    que la prochaine lecture prendra pour une décision."""
    assert path in _registered_paths(), (
        f"_NOT_IN_NAV garde {path!r}, qui n'est plus enregistrée — "
        f"retire la ligne."
    )
