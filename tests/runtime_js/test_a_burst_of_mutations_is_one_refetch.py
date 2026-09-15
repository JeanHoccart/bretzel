"""Toute zone abonnée se rafraîchit, et une rafale ne fait qu'un tour.

Le fait gardé
--------------
Une zone ``@refreshable(broadcast=[X])`` s'abonne au flux SSE. À chaque
``state-dirty`` portant ``X``, le runtime tire un
``GET /_bretzel/refetch/{état}/{zone}``.

Ce banc garde DEUX choses, et la première est la plus grave.

1. LA ZONE DU MILIEU NE SE RAFRAÎCHISSAIT JAMAIS
-------------------------------------------------
Le refetch s'écrivait ``htmx.ajax("GET", url, {swap: "none"})`` — **sans
``source``**. htmx rattache alors la requête à ``document.body``, donc
les N zones d'une page partagent UN élément et son ``hx-sync`` implicite
les fait se supprimer les unes les autres.

Mesuré le 2026-09-04, trois zones abonnées au même état, sur un client
qui ne reçoit QUE le flux (pas les swaps OOB de sa propre action) ::

    tour 1   a=5    b=0    c=5      (attendu 5 partout)
    tour 2   a=5    b=0    c=10     (attendu 10)
    tour 3   a=10   b=0    c=15     (attendu 15)

La zone du milieu ne bouge **jamais**, la première reste un tour en
arrière, seule la dernière est juste. Ce n'est pas de la lenteur, c'est
de la **donnée fausse affichée indéfiniment** — et rien ne le signale :
les requêtes perdues n'ont jamais été émises, donc ni console, ni
onglet réseau, ni log serveur.

⚠️ Et ça ne se voit pas sur le client qui AGIT : sa propre réponse
d'action porte les swaps OOB de toutes ses zones. Il faut un second
client, spectateur, pour que le défaut apparaisse. C'est pour ça
qu'aucune suite ne l'avait vu.

2. UNE RAFALE NE VAUT QU'UN TOUR
----------------------------------
Rien ne coalesçait : cinq actions rapprochées valaient 5 × 3 = 15
requêtes par client, dont 12 décrivaient un état déjà périmé quand
elles arrivaient. Une fenêtre par zone les ramène à 3 — mesuré.

⚠️ **Cinq mutations dans UN handler ne font PAS une rafale** : l'état est
commité une fois par requête, donc un seul ``state-dirty``. La rafale
demande cinq ACTIONS. La première version de ce banc s'est trompée là
-dessus et mesurait un phénomène qui n'existe pas.

Ce que ce banc n'affirme PAS
-----------------------------
**Le décalage aléatoire entre clients n'est pas gardé ici.** Le remède
en porte un (le même événement SSE réveille tous les clients à la même
milliseconde ; un décalage par page étale la horde), et il est mesuré —
4,7 ms d'écart entre deux clients sur le relevé du 2026-09-04. Mais
avec deux clients et un tirage aléatoire, l'écart observé est
stochastique : un seuil dessus rougirait au hasard. On garde ce qui est
déterministe, et on dit ce qui ne l'est pas plutôt que d'écrire une
gate qui ment une fois sur dix.

Lourd (uvicorn + Chromium) — à lancer explicitement ::

    py -m pytest tests/runtime_js/test_a_burst_of_mutations_is_one_refetch.py -q -m browser
"""

from __future__ import annotations

import pytest

from bretzel import Bretzel, page, refreshable, ui
from bretzel.state import AppState, field
from tests.audit.harness import audit_server, browser_page

pytestmark = pytest.mark.browser

#: La fenêtre de coalescence du runtime + son étalement + la marge d'un
#: aller-retour. On attend ce délai avant de compter.
_SETTLE_MS = 1500

#: Le nombre d'actions de la rafale, et ce que ça vaudrait sans
#: coalescence : 5 × 3 zones = 15 requêtes par client.
_BURST = 5
_ZONES = 3


class Ticker(AppState):
    """Un compteur partagé par tous les clients."""

    rev: int = field(default=0)


def bump() -> None:
    Ticker().rev += 1


def _zone(nom: str) -> None:
    ui.text(f"{nom}={Ticker().rev}", classes=f"bz-probe-{nom}")


@refreshable(deps=[Ticker], broadcast=[Ticker])
def zone_a() -> None:
    _zone("a")


@refreshable(deps=[Ticker], broadcast=[Ticker])
def zone_b() -> None:
    _zone("b")


@refreshable(deps=[Ticker], broadcast=[Ticker])
def zone_c() -> None:
    _zone("c")


@page("/")
def fanout_page() -> None:
    #: TROIS zones, et c'est le minimum qui révèle le défaut : avec deux
    #: il n'y a pas de « milieu », et c'est le milieu qui disparaissait.
    with ui.vstack(gap="sm"):
        zone_a()
        zone_b()
        zone_c()
        ui.button("bump", on_click=bump)


def _app() -> Bretzel:
    """Une app MINIMALE plutôt qu'une page de plus au playground.

    ``audit_server`` prend une app en argument exactement pour ça : le
    fan-out se compte, et une page de démo apporterait des zones
    abonnées qu'on n'a pas décidées.
    """
    app = Bretzel(
        title="fanout", secret_key="fanout-bench-secret-0123456789", mode="dev"
    )
    app.include(fanout_page, zone_a, zone_b, zone_c)
    return app


_LIRE = (
    "[...document.querySelectorAll('[class*=bz-probe-]')]"
    ".map(e => e.textContent.trim())"
)

#: Le flux doit être OUVERT avant qu'on mute : un abonné qui arrive
#: après ne verra rien, et le banc conclurait « coalescé » sur un
#: silence.
_PRET = "window.$bz && $bz.state.LiveConnection.default.connected === true"


def _compteur(page_obj, seau: list[str]):
    page_obj.on(
        "request",
        lambda r: seau.append(r.url.split("::")[-1])
        if "/refetch/" in r.url
        else None,
    )


def test_every_subscribed_zone_refreshes_on_every_client() -> None:
    """Le défaut n°1 : la zone du milieu ne bougeait jamais."""
    with audit_server(_app()) as base_url:
        # ``wait_until="load"`` est OBLIGATOIRE : la page ouvre un
        # EventSource, donc ``networkidle`` n'arrive JAMAIS et le
        # ``goto`` expire au bout de 30 s. Le harnais le dit dans sa
        # docstring — payé quand même au premier essai.
        with (
            browser_page(base_url, "/", wait_until="load") as clicker,
            browser_page(base_url, "/", wait_until="load") as watcher,
        ):
            for pg in (clicker, watcher):
                pg.wait_for_function(_PRET, timeout=15000)

            for tour in (1, 2, 3):
                clicker.get_by_role("button", name="bump").click()
                clicker.wait_for_timeout(_SETTLE_MS)
                attendu = [f"a={tour}", f"b={tour}", f"c={tour}"]

                # Le SPECTATEUR est le seul qui mesure le chemin temps
                # réel : le client qui agit reçoit les swaps OOB de sa
                # propre réponse et masque le défaut entièrement.
                vu = watcher.evaluate(_LIRE)
                assert vu == attendu, (
                    f"tour {tour} : le client spectateur affiche {vu} au "
                    f"lieu de {attendu}. Une zone abonnée ne se "
                    f"rafraîchit pas — et rien ne le signale, puisque sa "
                    f"requête n'est jamais partie. Vérifiez que le "
                    f"refetch passe ``source: zone`` : sans lui, htmx "
                    f"rattache les N zones à ``document.body`` et elles "
                    f"se suppriment les unes les autres."
                )
                assert clicker.evaluate(_LIRE) == attendu, (
                    f"tour {tour} : même le client qui agit est faux — "
                    f"c'est le chemin OOB, pas le chemin SSE."
                )


#: La rafale, jouée sur le coalesceur DIRECTEMENT.
#:
#: ⚠️ Cliquer cinq fois n'en fait pas une : chaque clic paie son
#: aller-retour, donc les cinq signaux arrivent bien au-delà de la
#: fenêtre et se coalescent — à raison. Mesuré : 15 requêtes pour cinq
#: clics, et c'est CORRECT, chaque action étant un état que
#: l'utilisateur veut voir. La rafale réelle vient d'ailleurs : plusieurs
#: clients qui agissent ensemble, ou un travail de fond qui mute en
#: boucle. On la reproduit en poussant les signaux dans le même tour,
#: ce qui mesure le mécanisme et rien d'autre.
_RAFALE = """
(n) => {
  const zones = [...document.querySelectorAll('[data-bz-subscribe-state]')];
  for (let i = 0; i < n; i++) {
    for (const z of zones) {
      $bz._refetchZone(z, z.getAttribute('data-bz-subscribe-url'));
    }
  }
  return zones.length;
}
"""


def test_a_burst_of_signals_collapses_to_one_refetch_per_zone() -> None:
    """Le défaut n°2 : rien ne coalesçait."""
    with audit_server(_app()) as base_url:
        with browser_page(base_url, "/", wait_until="load") as pg:
            pg.wait_for_function(_PRET, timeout=15000)

            vus: list[str] = []
            _compteur(pg, vus)

            zones = pg.evaluate(_RAFALE, _BURST)
            assert zones == _ZONES, (
                f"{zones} zones abonnées au lieu de {_ZONES} — le banc ne "
                f"mesure plus ce qu'il annonce."
            )
            pg.wait_for_timeout(_SETTLE_MS)

            sans_coalescence = _BURST * _ZONES
            assert len(vus) == _ZONES, (
                f"{len(vus)} refetch pour {_BURST} signaux sur {_ZONES} "
                f"zones. Sans coalescence il y en a {sans_coalescence}, et "
                f"{sans_coalescence - _ZONES} décrivent un état déjà "
                f"périmé quand ils arrivent. Avec, il en faut exactement "
                f"{_ZONES} : un par zone, portant le dernier état."
            )
            assert set(vus) == {"zone_a", "zone_b", "zone_c"}, (
                f"la coalescence a mangé une ZONE, pas un doublon : "
                f"{sorted(set(vus))}. Elle doit garder la dernière demande "
                f"de chaque zone, pas la dernière demande tout court."
            )
