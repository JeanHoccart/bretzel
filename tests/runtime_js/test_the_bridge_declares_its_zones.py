"""Le VRAI runtime envoie la liste de ses zones sur une action.

Le filtre côté serveur est testé ailleurs avec un en-tête fabriqué à la
main (``tests/integration/server/test_a_drain_renders_only_live_zones.py``).
Ça ne prouve rien sur la moitié qui compte : que le pont le pose
vraiment, depuis un document réel, en lisant le DOM.

C'est le mode d'échec le plus vicieux de ce mécanisme — si le pont
n'envoie rien, le serveur retombe sur « je ne filtre pas », donc **tout
continue de marcher** et l'optimisation est simplement morte. Aucun test
d'intégration ne peut le voir : seul un navigateur exécute
``05_bridge.js``.
"""

from __future__ import annotations

import pytest

from bretzel import Bretzel, page, refreshable, ui
from bretzel.state import SessionState, field
from tests.audit.harness import audit_server, browser_context

pytestmark = pytest.mark.browser

_SECRET = "x" * 32

_app = Bretzel(secret_key=_SECRET, mode="dev")


class Tour(SessionState):
    n: int = field(default=0)


@refreshable(deps=[Tour])
def zone_ici() -> None:
    ui.text(f"ICI={Tour().n}")


@refreshable(deps=[Tour])
def zone_la_bas() -> None:
    ui.text(f"LABAS={Tour().n}")


def bouger() -> None:
    Tour().n += 1


@page("/")
def ici() -> None:
    zone_ici()
    ui.button("bouger", on_click=bouger)


@page("/la-bas")
def la_bas() -> None:
    zone_la_bas()


_app.include(ici)
_app.include(la_bas)


def test_the_bridge_sends_the_zones_header_on_an_action() -> None:
    """Le pont déclare ce que le document porte, et rien d'autre."""
    with audit_server(_app) as base_url, browser_context() as ctx:
        page_ = ctx.new_page()
        vus: list[dict] = []
        page_.on(
            "request",
            lambda r: vus.append({"url": r.url, "headers": r.headers})
            if "/_bretzel/action/" in r.url
            else None,
        )
        page_.goto(base_url + "/", wait_until="load")
        page_.wait_for_timeout(700)
        page_.get_by_text("bouger").click()
        page_.wait_for_timeout(900)
        corps = page_.content()

    assert vus, "aucune requête d'action n'est partie — le montage est cassé"
    entete = vus[0]["headers"].get("x-bretzel-zones")
    assert entete, (
        "le pont n'a PAS envoyé X-Bretzel-Zones. Le serveur retombe alors "
        "sur « je ne filtre pas », donc tout marche et l'optimisation est "
        "morte en silence — c'est exactement ce que ce test existe pour "
        "voir."
    )
    declarees = {p for p in entete.split(",") if p}
    assert zone_ici.id in declarees, (
        f"le pont a envoyé {sorted(declarees)}, sans la zone que la page "
        f"porte ({zone_ici.id}) : le filtre la ferait taire."
    )
    assert zone_la_bas.id not in declarees, (
        "le pont déclare une zone qui n'est PAS dans ce document — il ne "
        "lit donc pas le DOM, et le filtre ne servira à rien."
    )
    assert "ICI=1" in corps, (
        "la zone de la page ne s'est pas rafraîchie : le filtre a écarté "
        "ce qu'il fallait garder."
    )


def test_the_page_carries_the_marker_the_bridge_reads() -> None:
    """Le plancher : sans marqueur, le pont ne peut rien énumérer.

    Sans ce test, retirer ``data-bz-zone`` du HTML rendrait l'en-tête
    vide, donc absent, donc le serveur ne filtrerait plus — et le test
    ci-dessus échouerait sur un message qui parlerait du PONT alors que
    la faute serait dans le rendu.
    """
    with audit_server(_app) as base_url, browser_context() as ctx:
        page_ = ctx.new_page()
        page_.goto(base_url + "/", wait_until="load")
        page_.wait_for_timeout(400)
        combien = page_.evaluate(
            "document.querySelectorAll('[data-bz-zone]').length"
        )
    assert combien >= 1, (
        "aucun élément ne porte data-bz-zone dans le document rendu"
    )
