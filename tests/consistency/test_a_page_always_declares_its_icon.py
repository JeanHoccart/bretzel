"""Gate : une page déclare TOUJOURS son icône, y compris quand on la retire.

Le défaut qu'elle ferme (2026-08-29)
------------------------------------
Jusqu'à ce jour, ``_build_head`` émettait charset, viewport,
``htmx-config``, ``<title>``, ``description``, les ``<meta>`` de
l'appelant et les feuilles — et **aucun ``<link rel="icon">``**. Un
navigateur qui n'en trouve pas va chercher ``/favicon.ico`` de sa propre
initiative ; une app Bretzel n'a pas cette route. Donc un 404 par
première visite, sur toutes les apps, invisible partout sauf dans les
logs.

L'invariant, et pourquoi il tient dans les TROIS cas
-----------------------------------------------------
``Bretzel(favicon=…)`` a trois valeurs, et la subtile est la troisième :

- ``None``    → la marque du framework (SVG + icône tactile iOS) ;
- une chaîne  → l'URL de l'app ;
- ``False``   → aucune icône **mais un ``<link>`` quand même**, en
  ``href="data:,"``.

Ce dernier cas est celui qui a besoin d'une gate. Il se lit « pas
d'icône », donc la correction évidente — ne rien émettre — est
exactement celle qui ramène le 404 qu'on venait de fermer. La règle
mécanique est donc : **au moins un ``rel="icon"`` dans le head, quoi
qu'on demande.**

Ce qu'elle vérifie en plus
---------------------------
Que les deux fichiers de la marque sont là, sous le paquet (donc
embarqués par ``packages = ["bretzel"]`` de hatchling), que les routes
les servent VRAIMENT — octets comparés à ceux du disque, pas seulement
un 200 — et qu'elles sont classées PUBLIQUES. Ce dernier point n'est pas
décoratif : une page de connexion demande son icône avant que quiconque
soit connecté, et une route fermée lui rendrait la page de login, du
HTML, là où le navigateur attend une image.

Ce qu'elle ne fait PAS
-----------------------
Elle ne regarde pas le DESSIN. Que le SVG soit joli, lisible à 16 px ou
qu'il suive le thème n'est pas mécanisable ici — c'est la planche de la
marque qui en répond.
"""

from __future__ import annotations

import re

import pytest
from starlette.testclient import TestClient

from bretzel import Bretzel
from bretzel.render.shell import default_shell
from bretzel.runtime.protocol import (
    ROUTE_FAVICON,
    ROUTE_TOUCH_ICON,
    is_public_asset_path,
)
from bretzel.server.routing.static import _FAVICON_FILE, _TOUCH_ICON_FILE

#: Les trois formes que ``favicon=`` accepte, et ce qu'on exige de chacune.
#: Le libellé sert d'``id`` de cas — un rouge nomme la forme fautive.
MODES: tuple[tuple[str, object, str | None], ...] = (
    ("defaut", None, ROUTE_FAVICON),
    ("chaine", "/static/logo.png", "/static/logo.png"),
    ("retiree", False, "data:,"),
)

#: Plancher ancré sur la DÉCOUVERTE, pas sur la population : si quelqu'un
#: vide ``MODES``, la gate resterait verte en n'ayant rien jugé.
_MODES_FLOOR = 3

_ICON_LINK = re.compile(r'<link rel="[^"]*icon"[^>]*/>')

#: La preuve que cette gate mord vit dans la gate — cf.
#: ``test_a_prohibition_gate_is_mutation_tested``, troisième voie.
MUTATION_PROOF = "test_the_detector_is_not_blind"


def _head(**kwargs: object) -> str:
    html = default_shell("<p>x</p>", "{}", page_uuid="u", **kwargs)  # type: ignore[arg-type]
    return html[: html.index("</head>")]


def test_the_sweep_really_judges_something() -> None:
    assert len(MODES) >= _MODES_FLOOR, (
        f"{len(MODES)} formes de `favicon=` jugées, plancher {_MODES_FLOOR} — "
        "une gate qui n'en juge plus qu'une reste verte sans rien affirmer."
    )
    assert "<title>" in _head(), (
        "le head rendu ne contient pas même son titre : la coque a changé "
        "de forme et les recherches ci-dessous ne veulent plus rien dire."
    )


@pytest.mark.parametrize(("label", "value", "expected"), MODES,
                         ids=[m[0] for m in MODES])
def test_every_mode_still_declares_an_icon(
    label: str, value: object, expected: str
) -> None:
    links = _ICON_LINK.findall(_head(favicon=value))
    assert links, (
        f"`favicon={value!r}` ({label}) n'émet AUCUN `rel=\"icon\"`. "
        "Le navigateur ira donc chercher /favicon.ico tout seul, et une "
        "app Bretzel n'a pas cette route : un 404 par page, silencieux."
    )
    assert any(expected in link for link in links), (
        f"`favicon={value!r}` ({label}) émet {links} — on y attendait "
        f"{expected!r}."
    )


def test_the_detector_is_not_blind() -> None:
    """La preuve de morsure, dans les DEUX sens.

    Le détecteur de cette gate est une regex sur le head. Une regex qui
    ne reconnaît plus rien rend la gate verte sur n'importe quoi — c'est
    la pathologie que ``test_a_prohibition_gate_is_mutation_tested``
    garde. On la ferme ici en fabriquant les deux états EN MÉMOIRE,
    plutôt qu'en mutant un fichier du framework.

    Versant LICITE : le head réel, tel qu'il est émis aujourd'hui, est
    reconnu. Versant ILLICITE : le même head privé de ses liens — ce que
    produirait un ``_icon_links`` qui se remettrait à rendre une liste
    vide — ne l'est plus. Le second versant est le seul qui prouve que
    les assertions au-dessus peuvent tomber.
    """
    head = _head()
    assert _ICON_LINK.findall(head), (
        "versant licite : le head RÉEL n'est plus reconnu par le "
        "détecteur — la regex a cessé de décrire ce que la coque émet, "
        "et toutes les assertions de ce fichier sont devenues vides."
    )
    regressed = _ICON_LINK.sub("", head)
    assert not _ICON_LINK.findall(regressed), (
        "versant illicite : un head SANS lien d'icône est quand même "
        "reconnu. Le détecteur voit quelque chose qui n'est pas un "
        "`rel=\"icon\"`, donc il ne peut pas rougir sur la vraie dérive."
    )
    assert "<title>" in regressed, (
        "la mutation a emporté autre chose que les liens d'icône : elle "
        "ne prouve donc pas ce qu'elle prétend."
    )


def test_removing_the_mark_still_costs_no_request() -> None:
    """Le cas ``False`` en entier : un ``<link>``, et un seul, qui ne
    télécharge rien. C'est ce qui rend le retrait de notre marque gratuit."""
    links = _ICON_LINK.findall(_head(favicon=False))
    assert links == ['<link rel="icon" href="data:,"/>'], (
        f"`favicon=False` émet {links}. Attendu : exactement un lien vide. "
        "Plusieurs liens, ou un href réel, et le retrait coûte une requête."
    )


def test_the_mark_ships_inside_the_package() -> None:
    for path in (_FAVICON_FILE, _TOUCH_ICON_FILE):
        assert path.is_file(), (
            f"{path} manque. La roue est construite depuis "
            "`packages = [\"bretzel\"]` : un asset hors du paquet ne "
            "voyage pas, et l'icône rend 404 chez qui `pip install`."
        )
        assert path.stat().st_size > 0, f"{path} est vide."
        assert path.parent.parent.name == "bretzel", (
            f"{path} vit hors du paquet `bretzel/` — hatchling ne "
            "l'embarquera pas."
        )


def test_the_icon_routes_serve_the_shipped_files() -> None:
    app = Bretzel(secret_key="x" * 32, mode="dev")
    with TestClient(app) as client:
        for route, path, mime in (
            (ROUTE_FAVICON, _FAVICON_FILE, "image/svg+xml"),
            (ROUTE_TOUCH_ICON, _TOUCH_ICON_FILE, "image/png"),
        ):
            resp = client.get(route)
            assert resp.status_code == 200, f"{route} rend {resp.status_code}."
            assert resp.headers["content-type"].startswith(mime), (
                f"{route} rend {resp.headers['content-type']!r} au lieu de "
                f"{mime!r} — un type faux fait ignorer l'icône."
            )
            assert resp.content == path.read_bytes(), (
                f"{route} ne sert pas {path.name} : la route pointe "
                "ailleurs, et le 200 ne le dit pas."
            )


def test_the_icon_routes_stay_public() -> None:
    for route in (ROUTE_FAVICON, ROUTE_TOUCH_ICON):
        assert is_public_asset_path(route), (
            f"{route} n'est pas classée publique. Une page de connexion "
            "demande son icône AVANT que quiconque soit connecté : fermée, "
            "la route lui rend la page de login — du HTML là où le "
            "navigateur attend une image."
        )
