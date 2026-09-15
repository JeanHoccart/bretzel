"""RÉFÉRENCE — Cheat-sheet.

Tout sur une page, Ctrl-F friendly : état, actions, réactivité, et les
pièges qui reviennent. Chaque bloc est un rappel condensé — le détail
vit dans les chapitres. C'est un INDEX, donc il renvoie et
n'enseigne pas — cf. la règle en tête de ``examples/docs/main.py``.
"""

from __future__ import annotations

from bretzel import page, ui

from examples.docs.features.shell import shell
from examples.docs.lib.blocks import toplevel_surface_mirror

PATH = "/cheatsheet"


def section(title: str, code: str) -> None:
    with ui.card():
        with ui.vstack(gap="sm"):
            ui.heading(title, level=2)
            ui.code(code, lang="python")


@page(PATH, layout=shell, title="Cheat-sheet")
def cheatsheet_page() -> None:
    with ui.container(width="lg"):
        with ui.vstack(gap="lg"):
            ui.heading("Cheat-sheet", level=1, size="3xl")
            ui.text(
                "Le condensé de tout Bretzel sur une page. Ctrl-F ton besoin.",
                color="muted", size="lg",
            )

            # ── Ce qui existe, groupé par besoin — lu en direct ──────────
            # Tout le reste de cette page est de la prose écrite à la main :
            # utile, dense, et qui dérive. Ce bloc-ci ne peut pas : il
            # énumère ``bretzel.__all__`` depuis le paquet, et une entrée
            # sans catégorie fait rougir ``test_docs_coverage``.
            with ui.card():
                with ui.vstack(gap="md"):
                    ui.heading("Ce qu'on tape — la surface du paquet", level=2)
                    ui.text(
                        "Groupé par le besoin auquel chaque nom répond, pas "
                        "par sa nature Python. Un helper appelable depuis un "
                        "handler a exactement un point d'accès : celui-ci.",
                        color="muted", size="sm",
                    )
                    toplevel_surface_mirror()

            section(
                "État — serveur (4 scopes)",
                "from bretzel.state import PageState, SessionState, UserState, AppState\n"
                "from bretzel.state import field, validator, computed\n"
                "\n"
                "class Cart(SessionState):          # page / session / user / app\n"
                "    items: list[dict] = field(default_factory=list)\n"
                "    coupon: str = \"\"\n"
                "\n"
                "    @validator(\"coupon\")           # reçoit (self, value), RETOURNE la valeur\n"
                "    def _norm(self, v: str) -> str:\n"
                "        return v.strip().upper()\n"
                "\n"
                "    @computed                       # dérivé, auto-tracké\n"
                "    def total(self) -> float:\n"
                "        return sum(i[\"price\"] for i in self.items)\n",
            )

            section(
                "État — client (3 modes de persistance)",
                "from bretzel.state import ClientState\n"
                "\n"
                "class FilterUI(ClientState, persist=\"local\"):\n"
                "    #  \"memory\"  → jetable (perdu au reload)\n"
                "    #  \"session\" → survit au reload, pas à la fermeture\n"
                "    #  \"local\"   → survit à tout\n"
                "    sort_by: str = \"date\"\n",
            )

            section(
                "Actions — serveur vs client",
                "# Serveur : on_click = callable → hx-post, HMAC signé\n"
                "def save() -> None:\n"
                "    Cart().coupon = \"\"          # mutation → re-render auto\n"
                "ui.button(\"Save\", on_click=save)\n"
                "\n"
                "# Client : on_click = expression (string) → aucun aller-retour\n"
                "ui.button(\"Haut\", on_click=\"window.scrollTo(0, 0)\")\n"
                "\n"
                "# Impératif : la méthode RETOURNE la string cliente\n"
                "with ui.dialog() as d:\n"
                "    ui.text(\"Sûr ?\")\n"
                "ui.button(\"Ouvrir\", on_click=d.open())\n"
                "\n"
                "# Binding : piloter un ClientState\n"
                "panel = PanelUI()\n"
                "ui.button(\"Toggle\", on_click=panel.open.toggle())\n",
            )

            section(
                "Réactivité — muter → re-render",
                "from bretzel import refreshable, ui\n"
                "\n"
                "@refreshable(deps=[Cart])          # déclaratif : re-render quand Cart change\n"
                "def cart_view() -> None:\n"
                "    for it in ui.each(Cart().items, key=\"id\"):\n"
                "        ui.text(it[\"label\"])\n"
                "\n"
                "from bretzel import refresh\n"
                "refresh(cart_view)                 # impératif, depuis un handler\n"
                "# refresh sur une zone broadcast=[…] → fan-out SSE aux autres onglets\n",
            )

            with ui.card(color="surface"):
                with ui.vstack(gap="sm"):
                    ui.heading("⚠️ Le piège n°1", level=2)
                    ui.text(
                        "Tout fichier qui déclare un State DOIT commencer par "
                        "`from __future__ import annotations` (PEP 649) — sinon "
                        "les champs ne s'enregistrent pas, silencieusement.",
                        color="muted", size="sm",
                    )
                    ui.code(
                        "from __future__ import annotations   # ← EN PREMIER, toujours\n",
                        lang="python",
                    )
                    with ui.hstack(align="baseline", gap="sm", wrap=True):
                        ui.text("Les autres pièges :", color="muted", size="sm")
                        ui.link("Pièges →", href="/traps")
