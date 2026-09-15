"""Une zone qui lève au drain n'emporte plus la réponse.

Avant le 2026-09-05, elle emportait TROIS choses d'un coup, et la
troisième est la pire :

1. les autres zones — valides, parfois déjà rendues — n'atteignaient
   jamais le navigateur ;
2. htmx ne swappe pas sur un non-2xx, donc l'utilisateur voyait
   simplement sa page ne rien faire ;
3. ``commit()`` venant **après** le drain, les mutations du handler
   étaient annulées — un bug d'AFFICHAGE annulait l'enregistrement
   demandé, sans un mot.

Le drain va maintenant au bout : la zone fautive rend une erreur
visible, les autres rendent normalement, et le commit s'exécute.

⚠️ La frontière est délibérée et gardée ici aussi : une zone qui lève
pendant le rendu d'une **page** fait toujours remonter l'exception, où
``@error_page`` l'attend. Là, il n'y a pas d'autre contenu valide à
sauver, et avaler l'erreur donnerait une page à moitié vraie.
"""

from __future__ import annotations

import pytest
from starlette.testclient import TestClient

from bretzel import Bretzel, page, refreshable, ui
from bretzel.server.handlers import encode_action_id, sign_action
from bretzel.state import SessionState, field

_SECRET = "x" * 32


class Etat(SessionState):
    n: int = field(default=0)


@refreshable(deps=[Etat])
def zone_saine() -> None:
    ui.text(f"SAINE={Etat().n}")


@refreshable(deps=[Etat])
def zone_fragile() -> None:
    """Rend bien au chargement, casse au drain.

    C'est la seule forme qui isole le drain : une zone qui lève TOUJOURS
    ferait déjà tomber la page initiale, et le test mesurerait le rendu
    de page au lieu du rafraîchissement.
    """
    if Etat().n > 0:
        raise RuntimeError("la zone casse")
    ui.text("FRAGILE=ok")


@refreshable(deps=[Etat])
def zone_saine_2() -> None:
    ui.text(f"SAINE2={Etat().n}")


def incrementer() -> None:
    Etat().n += 1


def _monter(**kwargs) -> Bretzel:
    app = Bretzel(secret_key=_SECRET, mode="dev", **kwargs)

    @page("/")
    def home() -> None:
        zone_saine()
        zone_fragile()
        zone_saine_2()

    app.include(home)
    return app


def _agir(client: TestClient, app: Bretzel):
    action_id = encode_action_id(incrementer)
    sig = sign_action(app.config._action_key, action_id, "")
    return client.post(
        f"/_bretzel/action/{action_id}",
        headers={"X-Bz-Sig": sig},
        data={"_args": ""},
    )


def test_the_page_renders_with_all_three_zones() -> None:
    """Plancher. Sans les trois zones au départ, il n'y a rien à sauver
    et l'interdiction passerait sur un montage vide."""
    app = _monter()
    with TestClient(app) as client:
        html = client.get("/").text
    for marqueur in ("SAINE=", "FRAGILE=ok", "SAINE2="):
        assert marqueur in html, f"{marqueur} absent de la page initiale"


def test_the_healthy_zones_still_reach_the_browser() -> None:
    """L'interdiction."""
    app = _monter()
    with TestClient(app, raise_server_exceptions=False) as client:
        client.get("/")
        reponse = _agir(client, app)
    assert reponse.status_code == 200, (
        f"la réponse est un {reponse.status_code} : une zone fautive "
        f"emporte encore tout le reste."
    )
    assert "SAINE=1" in reponse.text and "SAINE2=1" in reponse.text, (
        "les zones valides n'ont pas atteint le navigateur"
    )


def test_the_action_is_not_rolled_back() -> None:
    """Le gain le plus important, et le moins visible.

    ``commit()`` vient après le drain : un drain qui lève annulait donc
    l'écriture du handler. Un bug d'affichage effaçait un enregistrement.
    """
    app = _monter()
    with TestClient(app, raise_server_exceptions=False) as client:
        client.get("/")
        _agir(client, app)
        lignes = dict(getattr(app._state_backend, "_data", {}))
    ecrits = [v.data for k, v in lignes.items() if k.endswith("Etat:default")]
    assert ecrits and ecrits[0].get("n") == 1, (
        f"l'état du handler n'a pas été persisté ({ecrits}) : la zone "
        f"fautive annule encore l'action de l'utilisateur."
    )


def test_the_broken_zone_says_so_rather_than_going_quiet() -> None:
    """Pas de mensonge silencieux : la zone dit qu'elle a cassé.

    La laisser inchangée afficherait des données périmées dans une page
    d'apparence correcte — le mode d'échec que ce dépôt refuse ailleurs.
    """
    app = _monter()
    with TestClient(app, raise_server_exceptions=False) as client:
        client.get("/")
        corps = _agir(client, app).text
    assert zone_fragile.id in corps, (
        "la zone fautive n'est pas dans la réponse : elle reste donc à "
        "l'écran avec ses anciennes données, sans rien dire."
    )
    assert "FRAGILE=ok" not in corps, (
        "la réponse re-affiche l'ancien contenu de la zone comme s'il "
        "était frais"
    )


@pytest.mark.parametrize(
    "expose, attendu", [(True, True), (False, False)]
)
def test_the_detail_follows_expose_errors(expose: bool, attendu: bool) -> None:
    """Le détail est une décision d'EXPOSITION, pas de verbosité.

    C'est déjà la ligne de partage du framework pour les pages d'erreur
    (``server/routing/errors.py``) — une seconde politique divergerait.
    """
    app = _monter(expose_errors=expose)
    with TestClient(app, raise_server_exceptions=False) as client:
        client.get("/")
        corps = _agir(client, app).text
    assert ("la zone casse" in corps) is attendu, (
        f"expose_errors={expose} : le détail de l'exception "
        f"{'devrait' if attendu else 'ne devrait pas'} être dans la réponse."
    )


def test_a_page_render_still_raises() -> None:
    """La frontière. Le rendu de PAGE n'est PAS isolé, et c'est voulu.

    Sans ce test, élargir l'isolation au pipeline de page passerait
    inaperçu — et donnerait des pages à moitié vraies au lieu de la page
    d'erreur que ``@error_page`` sert.
    """
    app = _monter()
    with TestClient(app, raise_server_exceptions=False) as client:
        client.get("/")
        _agir(client, app)  # met l'état à 1, donc la zone lèvera au rendu
        rechargement = client.get("/")
    assert rechargement.status_code == 500, (
        "le rendu de page avale maintenant l'erreur d'une zone : la page "
        "s'affiche à moitié au lieu de laisser @error_page répondre."
    )


def test_the_error_fragment_keeps_the_zone_enumerable() -> None:
    """Le croisement que deux gates séparées ne voyaient pas.

    Le fragment de secours a été composé à la main pendant une journée,
    et il omettait ``data-bz-zone``. Conséquence, en chaîne : le pont
    n'énumère que ``[data-bz-zone]``, donc l'en-tête ``X-Bretzel-Zones``
    perdait la zone, donc ``enqueue_deps`` la filtrait — **elle ne se
    rafraîchissait plus jamais**, même une fois le bug d'affichage
    disparu, et jusqu'au rechargement complet.

    Ni la gate du filtre ni celle de l'isolation ne pouvait le voir :
    chacune vérifiait son mécanisme seul. Celle-ci vérifie leur
    RENCONTRE, et c'est pour ça qu'elle existe.

    Trouvé en revue le 2026-09-06, pas par un test.
    """
    app = _monter()
    with TestClient(app, raise_server_exceptions=False) as client:
        client.get("/")
        corps = _agir(client, app).text
    assert "data-bz-zone" in corps, (
        "le fragment d'erreur ne porte pas le marqueur de zone : après un "
        "échec, le navigateur cesse de déclarer cette zone et le drain la "
        "filtre pour toujours."
    )
    # Et l'identité, sans laquelle le morph raterait sa cible.
    assert f'bz-id="{zone_fragile.id}"' in corps
