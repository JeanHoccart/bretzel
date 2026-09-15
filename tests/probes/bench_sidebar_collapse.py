"""Bench : l'ouverture / fermeture de la sidebar, dans un cadre contraint.

Signalé à l'œil le 2026-08-18 sur `/sidebar` du playground : en mode
``rail`` replié, le chevron de repli sortait d'un grand contour arrondi et
l'icône d'entrée était **rognée** en bas de la bande. Rien ne l'attrapait
— ni les tests rapides, ni les tests navigateur.

Ce banc rend les quatre modes de ``collapsible=`` dans un cadre contraint
(comme le playground : ``h-[300px]``), **une config par route** : une
sidebar ``overlay`` est ``fixed inset-0``, donc les mettre sur une même
page les fait se recouvrir.

Son probe est :mod:`tests.probes.probe_sidebar_collapse`.

⚠️ **Il a vécu ICI, en ``--probe``, jusqu'au 2026-08-26**, et ça lui a
coûté cher : ``pytest -m probes`` ramasse ``probe_*.py``, donc cette
troisième forme n'était collectée par personne. Sorti, il s'est avéré
qu'il **plantait** sur un ``TimeoutError`` avant d'atteindre le moindre
verdict. La leçon est dans le README du dossier : un banc et son probe,
toujours par paire, et le probe s'appelle ``probe_*.py``.

Lancer le banc (port 8952 — jamais le 8000, qui est à l'utilisateur) ::

    py -m tests.probes.bench_sidebar_collapse
"""

from __future__ import annotations

from bretzel import Bretzel, page, ui

PORT = 8952
MODES = ("rail", "offcanvas", "overlay", "none")

#: Le playground contraint chaque démo dans une boîte : c'est ce cadre
#: qui révèle les débordements, et un montage plein écran les cacherait.
FIT = {"root": "h-full!"}

app = Bretzel(
    secret_key="dev-sidebar-collapse-bench-secret-key",
    title="Bretzel · sidebar collapse bench",
    mode="dev",
)


#: Une config par ROUTE. Les mettre sur une seule page ne marche pas :
#: une sidebar ``overlay`` est ``fixed inset-0``, donc elle sort de son
#: cadre et recouvre les autres démos. Mesuré — la première version de
#: ce bench était illisible pour ça.
CASES = [
    ("rail-titled", "rail", True, True, "h-[300px]"),
    ("rail-untitled", "rail", True, False, "h-[220px]"),
    ("none-untitled", "none", True, False, "h-[220px]"),
    ("offcanvas-open", "offcanvas", True, True, "h-[300px]"),
    ("overlay-open", "overlay", True, True, "h-[300px]"),
    ("rail-closed", "rail", False, True, "h-[300px]"),
    ("offcanvas-closed", "offcanvas", False, True, "h-[300px]"),
    ("overlay-closed", "overlay", False, True, "h-[300px]"),
]


def _build(mode: str, opened: bool, titled: bool, height: str) -> None:
    with ui.hstack(
        gap="none", align="stretch",
        classes=f"{height} w-[520px] border border-text/20 overflow-hidden",
    ):
        with ui.sidebar(
            slots=FIT, collapsible=mode, open=opened, id="probe-side",
        ):
            if titled:
                ui.sidebar_title("App", icon="zap")
            with ui.sidebar_section(label="MAIN"):
                ui.sidebar_item("Home", icon="home")
        with ui.vstack(classes="flex-1 min-w-0 p-3"):
            # ``offcanvas`` et ``overlay`` quittent l'écran en se
            # repliant : ``check_sidebars_are_reachable`` (a0cbab3f) les
            # refuse sans moyen de revenir, et les QUATRE pages de ces
            # deux modes rendaient 500 depuis. Personne ne l'avait vu :
            # la racine de ce banc est un 404, et son probe vivait ICI,
            # en ``--probe``, que ``pytest -m probes`` ne collecte pas.
            #
            # Posé pour les huit cas, pas seulement les quatre : ce banc
            # COMPARE des modes, donc l'échafaudage doit être identique
            # partout. Il est hors de ``#probe-side``, où toutes les
            # mesures du probe sont scopées.
            ui.sidebar_trigger()
            ui.text("page", color="muted", size="xs")


# ⚠️ Une page par ``def`` au niveau MODULE. Générer les routes dans une
# boucle avec une fabrique ne marche pas : ``app.include(__name__)``
# découvre les fonctions marquées qui sont des attributs du module, et
# une closure imbriquée n'en est pas une. Mesuré — les six routes
# répondaient 404.


@page("/rail-titled")
def p_rail_titled() -> None:
    _build("rail", True, True, "h-[300px]")


@page("/rail-untitled")
def p_rail_untitled() -> None:
    _build("rail", True, False, "h-[220px]")


@page("/none-untitled")
def p_none_untitled() -> None:
    _build("none", True, False, "h-[220px]")


@page("/offcanvas-open")
def p_offcanvas_open() -> None:
    _build("offcanvas", True, True, "h-[300px]")


@page("/overlay-open")
def p_overlay_open() -> None:
    _build("overlay", True, True, "h-[300px]")


@page("/rail-closed")
def p_rail_closed() -> None:
    _build("rail", False, True, "h-[300px]")


@page("/offcanvas-closed")
def p_offcanvas_closed() -> None:
    _build("offcanvas", False, True, "h-[300px]")


@page("/overlay-closed")
def p_overlay_closed() -> None:
    _build("overlay", False, True, "h-[300px]")


app.include(__name__)


if __name__ == "__main__":
    import uvicorn

    from tests.probes._serve import bench_port, use_local_tailwind

    # Le compilateur CSS depuis 127.0.0.1 et non depuis unpkg :

    # une suite ne doit pas dependre d'un tiers (cf. `_serve`).

    use_local_tailwind()


    uvicorn.run(app, host="127.0.0.1", port=bench_port(PORT))
