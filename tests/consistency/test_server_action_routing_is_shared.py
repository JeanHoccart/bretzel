"""Le routage du bundle d'action serveur n'est pas re-décidé composant par composant.

Un composant riche a deux porteurs, et ils ne sont pas interchangeables :

- le **porteur de valeur** — un ``<input type="hidden">`` avec ``name`` +
  ``value``, qui dispatche un ``change`` synthétique ; c'est lui que la
  FormData doit trouver ;
- l'**élément focusable** — le seul à recevoir nativement ``focus`` /
  ``blur``.

Le choix se lit dans ``hx-trigger``, que ``action_attrs`` a déjà posé d'après
l'event que le handler écoute vraiment. :func:`relocate_server_action` retire
cette décision à l'appelant.

Le bug qui a motivé la primitive
---------------------------------
``slider.py`` déplaçait le bundle vers l'input caché **sans regarder**
``hx-trigger``, puis forçait ``hx-trigger="change"``. Un ``on_focus=``
callable partait donc sur l'input caché — qui ne fire jamais ``focus`` — et
se déclenchait au ``change``. **Pas mort, pire que mort** : le handler
s'exécutait au mauvais moment (un ``on_focus`` d'analytics à chaque drag).

Le fix a été propagé À LA MAIN sur les sites concernés. Les bugs sont morts,
mais aucune primitive n'avait été extraite — donc le composant suivant
re-déciderait seul. C'est une réparation, pas un mécanisme.

⚠️ Pourquoi la dette n'est pas vide, et ce n'est pas de la paresse
-------------------------------------------------------------------
Les sites restants ont des formes **réellement différentes**, mesurées :

- ``calendar`` route à **trois** voies (``change`` / ``month_change`` /
  reste) — une cible de plus que la primitive ;
- ``date_picker`` / ``date_range_picker`` / ``file_upload`` / ``toggle_group``
  n'ont **qu'une** cible : c'est la forme de :func:`pop_change_handler`,
  pas celle-ci ;
- ``combobox`` pope dans un bundle unique puis route plus loin.

Forcer une primitive unique sur les cinq formes produirait une soupe de
paramètres — l'inverse du geste. La gate fige donc la DIRECTION : la
primitive couvre la forme à deux porteurs (celle qui avait le bug), et aucun
site NOUVEAU ne re-décide à la main.
"""

from __future__ import annotations

import re

import pytest

from tests.consistency._discovery import (
    COMPONENTS_DIR,
    assert_sweep_is_not_vacuous,
    component_sources,
)

# Une boucle / compréhension qui déplace le bundle à la main.
_MANUAL_ROUTING = re.compile(
    r"(for\s+\w+\s+in\s+\w*(?:SERVER_)?_?ACTION_ATTRS)"
    r"|(for\s+\w+\s+in\s+_ACTION_ATTRS_TO_RELOCATE)"
)

# Dette déclarée, à ÉGALITÉ STRICTE — mesurée le 2026-07-29. Chaque entrée
# porte la RAISON de sa forme : la retirer demande de vérifier que la forme
# a convergé, pas seulement que la ligne a bougé.
_MANUAL_ROUTING_DEBT: dict[str, str] = {
    "components/inputs/calendar/calendar.py":
        "route à 3 voies (change / month_change / reste)",
    "components/inputs/combobox/combobox.py":
        "pope dans un bundle unique, route plus loin",
    "components/inputs/file_upload/file_upload.py":
        "une seule cible, compréhension de dict",
    "components/inputs/toggle_group/toggle_group.py":
        "helper module-level, une seule cible",
}


def _rel(path) -> str:
    """Clé stable : chemin relatif à ``bretzel/``, donc ``components/…``.

    Calculé depuis ``COMPONENTS_DIR`` et pas par un ``split("bretzel/")`` :
    le dépôt s'appelle lui-même ``bretzel``, donc le chemin absolu contient
    ``bretzel/bretzel/`` et le split produisait une clé décalée — les 6
    entrées de dette ne matchaient aucune."""
    return f"components/{path.relative_to(COMPONENTS_DIR).as_posix()}"


def test_the_sweep_visits_the_components() -> None:
    assert_sweep_is_not_vacuous()


@pytest.mark.parametrize("path", component_sources(), ids=lambda p: p.name)
def test_no_new_manual_routing(path) -> None:
    if path.parts[-2] == "base" or path.name == "_wiring.py":
        pytest.skip("le socle possède la primitive")

    text = path.read_text(encoding="utf8")
    hits = [
        i for i, line in enumerate(text.splitlines(), 1)
        if not line.strip().startswith("#") and _MANUAL_ROUTING.search(line)
    ]
    rel = _rel(path)
    owed = rel in _MANUAL_ROUTING_DEBT

    if hits and not owed:
        pytest.fail(
            f"{path.name} route le bundle d'action serveur à la main "
            f"(ligne(s) {hits}).\n"
            f"  Passe par `relocate_server_action(root_attrs, "
            f"value_carrier=…, focusable=…)` : elle lit `hx-trigger` et "
            f"choisit le porteur. Écrit à la main, c'est le bug Slider qui "
            f"revient — un `on_focus=` callable posé sur l'input caché, qui "
            f"ne fire jamais focus, et qui part au change.\n"
            f"  Si ta forme est vraiment différente (3 cibles, cible "
            f"unique…), déclare-la dans _MANUAL_ROUTING_DEBT avec sa RAISON."
        )
    if owed and not hits:
        pytest.fail(
            f"{rel} est déclaré en dette de routage manuel "
            f"({_MANUAL_ROUTING_DEBT[rel]}) mais n'en porte plus. "
            f"La dette est payée — retire la ligne."
        )


def test_the_primitive_routes_by_trigger() -> None:
    """Le contrat de la primitive, figé indépendamment de ses appelants."""
    from bretzel.components.base._wiring import relocate_server_action

    # Bundle ``change`` → porteur de valeur, trigger épinglé.
    root = {"hx-post": "/a", "hx-trigger": "change", "hx-target": "#t"}
    carrier: dict[str, object] = {}
    focusable: dict[str, object] = {}
    relocate_server_action(root, value_carrier=carrier, focusable=focusable)
    assert carrier["hx-post"] == "/a"
    assert carrier["hx-trigger"] == "change"
    assert not focusable, "un bundle change ne doit pas toucher le focusable"
    assert "hx-post" not in root, "le bundle doit QUITTER la root"

    # Bundle ``focus`` → élément focusable, trigger PRÉSERVÉ.
    root = {"hx-post": "/b", "hx-trigger": "focus"}
    carrier, focusable = {}, {}
    relocate_server_action(root, value_carrier=carrier, focusable=focusable)
    assert focusable["hx-post"] == "/b"
    assert focusable["hx-trigger"] == "focus", (
        "le trigger focus doit être PRÉSERVÉ — l'écraser en 'change' est "
        "exactement le bug Slider"
    )
    assert not carrier

    # Pas de handler serveur → no-op.
    root = {"class": "x"}
    carrier, focusable = {}, {}
    relocate_server_action(root, value_carrier=carrier, focusable=focusable)
    assert not carrier and not focusable and root == {"class": "x"}
