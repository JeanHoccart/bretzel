"""Bench app — le coût d'un clic, mesuré dans un vrai navigateur (port 8998).

Cinq zones de tailles très différentes, chacune sur SON état : sans ça un
clic les rafraîchit toutes et la pente disparaît. Chaque bouton bumpe un
compteur, sa zone se re-rend, le runtime applique le patch.

Run :  py tests/probes/bench_clic.py
"""

from __future__ import annotations

import os

from bretzel import Bretzel, page, refreshable, ui
from bretzel.state import PageState, field

TAILLES = (1, 10, 50, 100, 200, 400, 800, 1600)


class C100(PageState):
    n: int = field(default=0)


class C400(PageState):
    n: int = field(default=0)


class C1600(PageState):
    n: int = field(default=0)


class C1(PageState):
    n: int = field(default=0)


class C10(PageState):
    n: int = field(default=0)


class C50(PageState):
    n: int = field(default=0)


class C200(PageState):
    n: int = field(default=0)


class C800(PageState):
    n: int = field(default=0)


app = Bretzel(
    secret_key="dev-clic-bench-secret-key",
    title="Bretzel · coût d'un clic",
    # ⚠️ Le mode CHANGE la mesure, et pas qu'un peu : en ``dev`` la page
    # embarque ``@tailwindcss/browser``, qui OBSERVE le DOM et recompile
    # sa feuille à chaque mutation. Tout ce qu'on croirait mesurer du
    # runtime lui appartiendrait en partie. Le probe lance les deux.
    mode=os.environ.get("BZ_BENCH_MODE", "dev"),
)


def lignes(t: int, n: int) -> None:
    """La première ligne porte le COMPTEUR.

    Sans elle le re-rendu produit un HTML identique, idiomorph ne mute
    rien, et un observateur du DOM n'a rien à dater — mesuré : le probe
    attendait une mutation qui n'arrivait jamais.
    """
    ui.text(f"clic n°{n}", size="sm", weight="bold")
    for i in range(t - 1):
        ui.text(f"ligne {i}", size="sm")


@refreshable(deps=[C100])
def zone_100() -> None:
    lignes(100, C100().n)


@refreshable(deps=[C400])
def zone_400() -> None:
    lignes(400, C400().n)


@refreshable(deps=[C1600])
def zone_1600() -> None:
    lignes(1600, C1600().n)


@refreshable(deps=[C1])
def zone_1() -> None:
    lignes(1, C1().n)


@refreshable(deps=[C10])
def zone_10() -> None:
    lignes(10, C10().n)


@refreshable(deps=[C50])
def zone_50() -> None:
    lignes(50, C50().n)


@refreshable(deps=[C200])
def zone_200() -> None:
    lignes(200, C200().n)


@refreshable(deps=[C800])
def zone_800() -> None:
    lignes(800, C800().n)


ZONES = {t: globals()[f'zone_{t}'] for t in TAILLES}


def bump_100() -> None:
    C100().n += 1


def bump_400() -> None:
    C400().n += 1


def bump_1600() -> None:
    C1600().n += 1


def bump_1() -> None:
    C1().n += 1


def bump_10() -> None:
    C10().n += 1


def bump_50() -> None:
    C50().n += 1


def bump_200() -> None:
    C200().n += 1


def bump_800() -> None:
    C800().n += 1


ACTIONS = {t: globals()[f'bump_{t}'] for t in TAILLES}


# ── Le même contenu, découpé : 8 zones de 200 sur UN état partagé ─────
#
# Un seul clic les rafraîchit toutes les huit. Même total morphé qu'une
# zone de 1 600, mais huit fratries de 200 — c'est le paramètre dont
# idiomorph dépend au carré.


class CDecoupe(PageState):
    n: int = field(default=0)


def _fabrique_part(k: int):
    def part() -> None:
        lignes(200, CDecoupe().n)

    part.__name__ = f"part_{k}"
    part.__qualname__ = f"part_{k}"
    zone = refreshable(deps=[CDecoupe])(part)
    globals()[f"part_{k}"] = zone
    return zone


PARTS = [_fabrique_part(k) for k in range(8)]


def bump_decoupe() -> None:
    CDecoupe().n += 1


# ── La même zone de 1 600, mais chaque enfant porte un `id` stable ─────
#
# idiomorph n'apparie par identité que sur `id` — `bz-id` ne lui dit
# rien. Sans `id`, il « soft-matche » en balayant les frères suivants,
# et c'est de là que vient le carré.


class CIds(PageState):
    n: int = field(default=0)


@refreshable(deps=[CIds])
def zone_1600_ids() -> None:
    n = CIds().n
    ui.text(f"clic n°{n}", size="sm", weight="bold", id="li-0")
    for i in range(1599):
        ui.text(f"ligne {i}", size="sm", id=f"li-{i + 1}")


def bump_ids() -> None:
    CIds().n += 1


@page("/")
def home() -> None:
    with ui.vstack(gap="md", align="start", classes="p-8"):
        ui.text("Coût d'un clic", size="2xl", weight="bold")
        for t in TAILLES:
            ui.button(f"bump {t}", on_click=ACTIONS[t], id=f"btn-{t}")
            with ui.container(id=f"box-{t}", classes="max-h-24 overflow-auto"):
                ZONES[t]()
        ui.button("bump découpé (8 x 200)", on_click=bump_decoupe,
                  id="btn-decoupe")
        with ui.container(id="box-decoupe", classes="max-h-24 overflow-auto"):
            for part in PARTS:
                part()
        ui.button("bump 1600 avec id=", on_click=bump_ids, id="btn-ids")
        with ui.container(id="box-ids", classes="max-h-24 overflow-auto"):
            zone_1600_ids()


app.include(__name__)


if __name__ == "__main__":
    import uvicorn

    from tests.probes._serve import bench_port, use_local_tailwind

    # Le compilateur CSS depuis 127.0.0.1 et non depuis unpkg :

    # une suite ne doit pas dependre d'un tiers (cf. `_serve`).

    use_local_tailwind()


    uvicorn.run(app, host="127.0.0.1", port=bench_port(8998))
