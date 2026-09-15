"""Bench + probe : le tiroir piloté par le SERVEUR se ferme-t-il ?

Signalé à l'œil le 2026-08-18 sur `/datatable_solo` du playground :
« quand je clique sur close, ça ne marche pas ».

Reproduit ici le montage exact de `examples/playground/features/
datatable_solo.py` — la forme la plus fragile du tiroir :

- ``open=`` lit une valeur d'ÉTAT SERVEUR (pas une binding client, pas
  l'API impérative) ;
- le corps vit dans un ``@refreshable(deps=[...])``, donc chaque
  ouverture/fermeture passe par un aller-retour et un morph ;
- ``on_close=`` est un handler serveur qui remet le drapeau à ``False``.

C'est la combinaison où un signal de scope périmé après morph ne se voit
pas : le premier clic marche, le second non — ou l'inverse. Un test SSR
ne peut rien en dire, il ne clique pas.

Le probe mesure, sur DEUX cycles :

1. ouvrir → le panneau est-il visible (``translate`` à zéro) ?
2. fermer par la croix → repart-il hors écran ?
3. re-ouvrir → **le deuxième cycle marche-t-il encore ?**

Lancer le bench (port 8953 — jamais le 8000, qui est à l'utilisateur) ::

    py -m tests.probes.bench_drawer_server_close

Lancer le probe ::

    py -m tests.probes.bench_drawer_server_close --probe

⚠️ ``project_probes_rot_silently`` : pas collecté par pytest. Relance-le
avant de croire ce qu'il affirme.
"""

from __future__ import annotations

import sys

from bretzel import Bretzel, page, refreshable, ui
from bretzel.components import DatatableState
from bretzel.components.data.table.table import column
from bretzel.state import PageState, field

PORT = 8953

app = Bretzel(
    secret_key="dev-drawer-close-bench-secret-key",
    title="Bretzel · drawer server-close bench",
    mode="dev",
)


class Detail(PageState):
    """Le drapeau que ``open=`` lit. Même forme que ``SoloDetail`` du
    playground : un ``bool`` d'état serveur, donc porteur du stamp qui
    fait émettre ``_serverSync``."""

    item_id: int = field(default=0)
    opened: bool = field(default=False)


def open_detail() -> None:
    d = Detail()
    d.item_id = d.item_id + 1
    d.opened = True


class Query(DatatableState):
    """La table du banc. Une par table, c'est la règle du composant."""


ROWS = [{"id": i, "titre": f"Ticket {i}"} for i in (1, 2, 3)]


def open_from_row(row_id) -> None:
    """⚠️ LE chemin du playground : le tiroir est ouvert par un CLIC DE
    LIGNE de datatable, pas par un bouton. C'est la seule différence
    structurelle avec le montage au-dessus, donc le seul endroit où le
    bug signalé peut vivre."""
    d = Detail()
    d.item_id = int(row_id)
    d.opened = True


@refreshable(deps=[Query])
def solo_table() -> None:
    ui.datatable(
        state=Query, columns=[column("titre", label="Titre")],
        rows=ROWS, row_key="id", on_item_click=open_from_row,
        search=False,
    )


def close_detail() -> None:
    Detail().opened = False


@refreshable(deps=[Detail])
def detail_drawer() -> None:
    d = Detail()
    with ui.drawer(
        open=d.opened, title=f"Item #{d.item_id}",
        on_close=close_detail, width="md", id="probe-drawer",
    ):
        ui.text(f"Contenu de l'item {d.item_id}")


@refreshable(deps=[Detail])
def server_state_readout() -> None:
    """Ce que le SERVEUR croit. C'est le seul témoin qui compte : le
    tiroir peut disparaître à l'écran (le client met ``open = false``)
    pendant que le serveur garde ``opened = True`` — et il rouvre alors
    au prochain morph."""
    ui.text(f"serveur: opened={Detail().opened}", id="readout")


@page("/")
def index() -> None:
    with ui.vstack(gap="md"):
        ui.heading("drawer piloté par l'état serveur", level=2)
        ui.button("Ouvrir", id="btn-open", on_click=open_detail)
        server_state_readout()
        solo_table()
        detail_drawer()


app.include(__name__)


# ───────────────────────────────────────────────────────────────────────
# Probe
# ───────────────────────────────────────────────────────────────────────


#: Le panneau est le nœud qui porte le ``translate`` de fermeture. On lit
#: sa position RÉELLE : un panneau fermé est hors du cadre, un panneau
#: ouvert le chevauche. Comparer un booléen d'attribut ne dirait rien —
#: c'est le rendu qui compte.
_STATE = """() => {
  const panel = document.querySelector('[role="dialog"]');
  if (!panel) return {error: 'panneau introuvable'};
  const b = panel.getBoundingClientRect();
  const cs = getComputedStyle(panel);
  return {
    x: Math.round(b.x), w: Math.round(b.width),
    visibility: cs.visibility, opacity: cs.opacity,
    translate: cs.translate || cs.transform,
    // Visible = il occupe une bande dans le viewport.
    onScreen: b.width > 0 && b.right > 0 && b.x < window.innerWidth,
    dataOpen: panel.getAttribute('data-open'),
    // Le témoin serveur, cherché par son TEXTE : ``ui.text(id=)`` ne
    // pose pas forcément l'id sur le nœud qui porte le texte.
    serveur: (() => {
      for (const el of document.querySelectorAll('span,div,p')) {
        const t = (el.textContent || '').trim();
        if (t.startsWith('serveur: opened=') && el.children.length === 0) {
          return t;
        }
      }
      return null;
    })(),
  };
}"""


def run_probe() -> int:
    import threading
    from pathlib import Path
    from tempfile import mkdtemp

    import uvicorn

    from tests.probes._serve import bench_port, use_local_tailwind
    from playwright.sync_api import sync_playwright

    cfg = uvicorn.Config(app, host="127.0.0.1", port=PORT, log_level="error")
    srv = uvicorn.Server(cfg)
    threading.Thread(target=srv.run, daemon=True).start()
    while not srv.started:
        pass

    tmp = Path(mkdtemp())
    failures: list[str] = []
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            pg = browser.new_page(viewport={"width": 1100, "height": 700})
            errors: list[str] = []
            pg.on("pageerror", lambda e: errors.append(str(e)))
            pg.on("console", lambda m: (
                errors.append(f"console.{m.type}: {m.text}")
                if m.type == "error" else None
            ))
            pg.goto(f"http://127.0.0.1:{PORT}/")
            pg.wait_for_timeout(900)

            print("depart      ->", pg.evaluate(_STATE))

            for cycle in (1, 2):
                # ⚠️ Ouvrir par le CLIC DE LIGNE, comme le playground —
                # pas par le bouton. C'est le chemin signalé.
                row = pg.query_selector("table tbody tr")
                if row is None:
                    failures.append(f"cycle {cycle} : aucune ligne de table")
                    break
                row.click()
                pg.wait_for_timeout(900)
                opened = pg.evaluate(_STATE)
                print(f"cycle {cycle} ouvert ->", opened)
                pg.screenshot(path=str(tmp / f"cycle{cycle}-open.png"))
                if not opened.get("onScreen"):
                    failures.append(
                        f"cycle {cycle} : le tiroir ne s'OUVRE pas "
                        f"({opened})"
                    )
                    continue

                # La croix — le geste signalé comme cassé.
                closer = pg.query_selector(
                    '[role="dialog"] button[aria-label*="lose"], '
                    '[role="dialog"] button[aria-label*="ermer"]'
                )
                if closer is None:
                    failures.append(f"cycle {cycle} : aucune croix trouvée")
                    break
                closer.click()
                pg.wait_for_timeout(900)
                closed = pg.evaluate(_STATE)
                print(f"cycle {cycle} fermé  ->", closed)
                pg.screenshot(path=str(tmp / f"cycle{cycle}-closed.png"))
                if closed.get("onScreen"):
                    failures.append(
                        f"cycle {cycle} : la CROIX ne ferme pas le tiroir "
                        f"({closed})"
                    )
                # ⚠️ L'assertion qui compte VRAIMENT. Le panneau peut
                # partir de l'écran (le client met ``open = false``)
                # pendant que le SERVEUR garde ``opened = True`` : le
                # tiroir rouvre alors au prochain morph, et le handler
                # ``on_close=`` n'a jamais tourné.
                if closed.get("serveur") != "serveur: opened=False":
                    failures.append(
                        f"cycle {cycle} : le handler ``on_close`` n'a pas "
                        f"tourné — le serveur dit {closed.get('serveur')!r}. "
                        f"Le tiroir est parti de l'écran côté CLIENT "
                        f"seulement."
                    )

            if errors:
                failures.append(f"erreurs JS : {errors[:4]}")
            print(f"\ncaptures : {tmp}")
            browser.close()
    finally:
        srv.should_exit = True

    print()
    if failures:
        print("ECHEC :")
        for f in failures:
            print("  -", f)
        return 1
    print("OK — le tiroir s'ouvre et se ferme, sur deux cycles.")
    return 0


if __name__ == "__main__":
    if "--probe" in sys.argv:
        raise SystemExit(run_probe())
    import uvicorn

    # Le compilateur CSS depuis 127.0.0.1 et non depuis unpkg :

    # une suite ne doit pas dependre d'un tiers (cf. `_serve`).

    use_local_tailwind()


    uvicorn.run(app, host="127.0.0.1", port=bench_port(PORT))
