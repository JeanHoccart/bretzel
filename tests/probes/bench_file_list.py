"""Bench + probe : les deux présentations de la liste de `file_upload`.

La liste de fichiers n'existe **qu'après un dépôt**, côté client — elle
est clonée depuis un ``<template bz-for>``. Aucune gate SSR ne peut donc
la voir : `tests/consistency/test_list_presentations_restructure.py`
prouve que les deux ARBRES diffèrent, pas que la puce tient sur une ligne
ni que son × est cliquable.

Ce probe comble ce trou. Il dépose de vrais fichiers via
``set_input_files``, attend le rendu, et **mesure** :

- la hauteur occupée par la liste dans chaque présentation ;
- la position du × relativement à sa carte (déborde-t-il, ou est-il dans
  le flux ?) ;
- que le × est réellement cliquable (retire bien une entrée) ;
- la direction de débordement (la bande de tuiles défile en X, les puces
  s'enroulent).

Lancer le bench seul (port 8951 — **jamais** le 8000, qui est à
l'utilisateur) ::

    py -m tests.probes.bench_file_list

Lancer le probe (démarre le bench lui-même, mesure, s'arrête) ::

    py -m tests.probes.bench_file_list --probe

⚠️ ``project_probes_rot_silently`` : ce fichier n'est PAS collecté par
pytest (pas de préfixe ``test_``). Il peut donc pourrir sans que rien ne
le dise. Relance-le avant de croire ce qu'il affirme.
"""

from __future__ import annotations

import sys

from bretzel import Bretzel, page, ui

PORT = 8951

app = Bretzel(
    secret_key="dev-file-list-bench-secret-key",
    title="Bretzel · file_upload list bench",
    mode="dev",
)


@page("/")
def index() -> None:
    with ui.vstack(gap="lg"):
        ui.heading("file_upload — tiles vs chips", level=2)

        ui.heading("tiles", level=3)
        with ui.container(id="zone-tiles"):
            ui.file_upload(multiple=True, list="tiles", id="up-tiles")

        ui.heading("chips", level=3)
        with ui.container(id="zone-chips"):
            ui.file_upload(multiple=True, list="chips", id="up-chips")


app.include(__name__)


# ───────────────────────────────────────────────────────────────────────
# Probe
# ───────────────────────────────────────────────────────────────────────


def _measure(page_obj, upload_id: str) -> dict:
    """Mesure la liste rendue d'un ``file_upload`` après dépôt."""
    return page_obj.evaluate(
        """(id) => {
        const root = document.getElementById(id);
        // La strip est le conteneur qui porte le <template bz-for>.
        const tpl = root.querySelector('template[bz-for]');
        const strip = tpl ? tpl.parentElement : null;
        if (!strip) return {error: 'strip introuvable'};
        const items = [...strip.children].filter(n => n.tagName !== 'TEMPLATE');
        if (!items.length) return {error: 'aucune entree rendue'};
        const card = items[0];
        const cardBox = card.getBoundingClientRect();
        const btn = card.querySelector('button');
        const btnBox = btn ? btn.getBoundingClientRect() : null;
        const cs = getComputedStyle(strip);
        return {
          entries: items.length,
          stripHeight: Math.round(strip.getBoundingClientRect().height),
          cardW: Math.round(cardBox.width),
          cardH: Math.round(cardBox.height),
          flexWrap: cs.flexWrap,
          overflowX: cs.overflowX,
          hasThumb: !!card.querySelector('img'),
          btnPosition: btn ? getComputedStyle(btn).position : null,
          // Deborde-t-il de sa carte ? (le badge de coin, oui ; la puce, non)
          btnOverflows: btnBox
            ? (btnBox.top < cardBox.top - 1 || btnBox.right > cardBox.right + 1)
            : null,
        };
    }""",
        upload_id,
    )


def run_probe() -> int:
    import tempfile
    import threading
    from pathlib import Path

    import uvicorn

    from tests.probes._serve import bench_port, use_local_tailwind
    from playwright.sync_api import sync_playwright

    config = uvicorn.Config(app, host="127.0.0.1", port=PORT, log_level="error")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    while not server.started:
        pass

    tmp = Path(tempfile.mkdtemp())
    files = []
    for name in ("rapport.pdf", "notes.txt", "budget.csv"):
        f = tmp / name
        f.write_text("x" * 2048, encoding="utf-8")
        files.append(str(f))

    failures: list[str] = []
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            pg = browser.new_page(viewport={"width": 900, "height": 900})
            pg.goto(f"http://127.0.0.1:{PORT}/")
            pg.wait_for_timeout(600)

            out = {}
            for pres in ("tiles", "chips"):
                pg.set_input_files(f"#up-{pres} input[type=file]", files)
                pg.wait_for_timeout(500)
                out[pres] = _measure(pg, f"up-{pres}")
                print(f"{pres:6} -> {out[pres]}")

            pg.screenshot(path=str(tmp / "file_list.png"), full_page=True)
            print(f"\ncapture : {tmp / 'file_list.png'}")

            for pres in ("tiles", "chips"):
                if out[pres].get("error"):
                    failures.append(f"{pres} : {out[pres]['error']}")
            if failures:
                return _report(failures)

            # 1. Les puces sont PLUS BASSES — c'est le besoin mesuré.
            if out["chips"]["stripHeight"] >= out["tiles"]["stripHeight"]:
                failures.append(
                    f"les puces ne gagnent pas de hauteur "
                    f"({out['chips']['stripHeight']} px contre "
                    f"{out['tiles']['stripHeight']} px en tuiles)"
                )
            # 2. Le x de la tuile deborde, celui de la puce non.
            if not out["tiles"]["btnOverflows"]:
                failures.append("le x de la tuile ne deborde plus du coin")
            if out["chips"]["btnOverflows"]:
                failures.append(
                    "le x de la puce DEBORDE de sa carte — il doit etre "
                    "dans le flux"
                )
            # 3. Vignette en tuiles seulement.
            if not out["tiles"]["hasThumb"]:
                failures.append("la tuile n'a plus de vignette")
            if out["chips"]["hasThumb"]:
                failures.append("la puce a une vignette")
            # 4. Les puces s'enroulent, la bande defile.
            if out["chips"]["flexWrap"] != "wrap":
                failures.append(
                    f"les puces ne s'enroulent pas "
                    f"(flex-wrap={out['chips']['flexWrap']})"
                )
            # 5. Le x retire vraiment une entree.
            before = out["chips"]["entries"]
            pg.click("#up-chips button")
            pg.wait_for_timeout(300)
            after = _measure(pg, "up-chips").get("entries")
            if after != before - 1:
                failures.append(
                    f"le x de la puce ne retire rien ({before} -> {after})"
                )

            browser.close()
    finally:
        server.should_exit = True

    return _report(failures)


def _report(failures: list[str]) -> int:
    print()
    if failures:
        print("ECHEC :")
        for f in failures:
            print("  -", f)
        return 1
    print("OK — les deux presentations different structurellement, "
          "et le x de la puce est dans le flux et cliquable.")
    return 0


if __name__ == "__main__":
    if "--probe" in sys.argv:
        raise SystemExit(run_probe())
    import uvicorn

    # Le compilateur CSS depuis 127.0.0.1 et non depuis unpkg :

    # une suite ne doit pas dependre d'un tiers (cf. `_serve`).

    use_local_tailwind()


    uvicorn.run(app, host="127.0.0.1", port=bench_port(PORT))
