"""Fondations — Décrire l'UI.

Avant toute interactivité : comment on décrit une interface. Des
composants Python composés avec `with`, une page, et le rendu DEPUIS
un état typé. Le catalogue complet des composants vit dans la Référence.
"""

from bretzel import page, ui

from examples.docs.features.shell import shell


@page("/describe", layout=shell, title="Décrire l'UI")
def describe_page() -> None:
    with ui.container(width="xl"):
        with ui.vstack(gap="lg"):
            ui.heading("Décrire l'UI", level=1, size="3xl")
            ui.text(
                "Avant de rendre quoi que ce soit interactif, il faut savoir "
                "décrire une interface. En Bretzel, une UI est un arbre de "
                "composants Python — statique tant qu'aucun état ne bouge.",
                color="muted", size="lg",
            )

            with ui.card():
                with ui.vstack(gap="sm"):
                    ui.heading("Des composants composés avec `with`", level=2)
                    ui.text(
                        "Les composants `ui.*` sont des fonctions. Les "
                        "conteneurs (stack, card, grid…) s'ouvrent avec un "
                        "bloc `with` ; leurs enfants se déclarent dedans.",
                        color="muted", size="sm",
                    )
                    ui.code(
                        "with ui.card():\n"
                        "    with ui.vstack(gap=\"sm\"):\n"
                        "        ui.heading(\"Profil\", level=2)\n"
                        "        ui.text(\"Membre depuis 2024\", color=\"muted\")\n"
                        "        ui.button(\"Éditer\")\n",
                        lang="python",
                    )
                    with ui.hstack(align="baseline", gap="sm", wrap=True):
                        ui.text("La liste complète (inputs, overlays, tables, "
                                "charts…) est dans", color="muted", size="sm")
                        ui.link("le catalogue", href="/components")
                        ui.text(".", color="muted", size="sm")

            with ui.card():
                with ui.vstack(gap="sm"):
                    ui.heading("Une page", level=2)
                    ui.text(
                        "Une page est une fonction décorée `@page` avec son "
                        "URL. Un `@layout` dessine le cadre commun (une "
                        "sidebar, un header) et expose une région via "
                        "`ui.outlet()` où les pages se rendent.",
                        color="muted", size="sm",
                    )
                    ui.code(
                        "@page(\"/profil\", layout=shell)\n"
                        "def profil() -> None:\n"
                        "    ui.heading(\"Profil\", level=1)\n",
                        lang="python",
                    )

            with ui.card(color="surface"):
                with ui.vstack(gap="sm"):
                    ui.heading("Rendre depuis l'état", level=2)
                    ui.text(
                        "Le point clé : l'UI se construit EN LISANT l'état. "
                        "On ne modifie jamais l'affichage à la main — on "
                        "décrit ce qu'il doit être pour l'état courant. "
                        "Quand l'état change, l'UI est recalculée (c'est la "
                        "réactivité, plus loin). Le flux va dans un seul "
                        "sens : état → UI.",
                        color="muted", size="sm",
                    )
                    ui.code(
                        "def cart_summary() -> None:\n"
                        "    cart = Cart()\n"
                        "    ui.text(f\"{len(cart.items)} articles\")\n"
                        "    for item in cart.items:\n"
                        "        ui.text(item[\"name\"])\n",
                        lang="python",
                    )
                    with ui.hstack(align="baseline", gap="sm", wrap=True):
                        ui.text("D'où vient cet état ? C'est la suite :",
                                color="muted", size="sm")
                        ui.link("L'état serveur →", href="/state-server")
