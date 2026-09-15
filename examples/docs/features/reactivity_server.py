"""LA RÉACTIVITÉ — Réactivité serveur.

Le côté serveur de la réactivité : ce qui se re-rend après une action.
Une zone déclare les états qu'elle lit ; muter l'un d'eux la re-rend
automatiquement. Plus le déclencheur manuel (`refresh`) et le temps réel
(`broadcast=[…]` / SSE). API vérifiée dans
``render/decorators/refreshable.py`` (seuls ``refreshable`` et ``refresh``
sont exportés).
"""

from bretzel import page, ui
from examples.docs.features.shell import shell


@page("/reactivity-server", layout=shell, title="Réactivité serveur")
def reactivity_server_page() -> None:
    with ui.container(width="lg"), ui.vstack(gap="lg"):
        ui.heading("Réactivité serveur", level=1, size="3xl")
        with ui.hstack(align="baseline", gap="sm", wrap=True):
            ui.text(
                "Une fois qu'un handler a modifié l'état "
                "(cf.",
                color="muted", size="lg",
            )
            ui.link("Actions serveur", href="/actions-server")
            ui.text("), voici ce qui se re-rend à l'écran, et comment "
                    "le contrôler.", color="muted", size="lg")

        # ── @refreshable(deps=) ──────────────────────────────────
        with ui.card(), ui.vstack(gap="sm"):
            ui.heading("Le re-render automatique", level=2)
            ui.text(
                "Une zone `@refreshable(deps=[…])` déclare les états "
                "qu'elle lit. Quand un handler mute l'un d'eux, la "
                "zone est re-rendue automatiquement — pas de refresh "
                "à appeler.",
                color="muted", size="sm",
            )
            ui.code(
                "@refreshable(deps=[Cart])\n"
                "def cart_summary() -> None:\n"
                '    ui.text(f"{len(Cart().items)} articles")\n'
                "\n"
                "\n"
                "def add_to_cart(product_id: str) -> None:\n"
                "    Cart().items.append(product_id)\n"
                "    # cart_summary se re-rend : Cart est dans ses deps\n",
                lang="python",
            )

        # ── Mutation = re-render ─────────────────────────────────
        with ui.card(), ui.vstack(gap="sm"):
            ui.heading("Mutation = re-render", level=2)
            ui.text(
                "En fin d'action, le serveur compare l'état avant / "
                "après — y compris les modifications en place "
                "(`items.append(...)`, `d[k] = v`). Toute zone dont "
                "un `deps=` a changé est re-rendue et renvoyée au "
                "navigateur.",
                color="muted", size="sm",
            )
            ui.text(
                "À l'inverse, si un handler ne change aucun état "
                "déclaré dans un `deps=`, aucune zone n'est re-rendue "
                "— l'aller-retour ne renvoie rien à rafraîchir.",
                color="muted", size="sm",
            )

        # ── refresh() ────────────────────────────────────────────
        with ui.card(), ui.vstack(gap="sm"):
            ui.heading("Déclencher manuellement — refresh()", level=2)
            ui.text(
                "`refresh(zone)` force le re-render d'une zone. Utile "
                "quand le changement ne vient pas d'un état déclaré, "
                "ou depuis un endroit qui n'est pas un handler "
                "d'action. On peut aussi l'adresser par son `name`.",
                color="muted", size="sm",
            )
            ui.code(
                "from bretzel import refresh\n"
                "\n"
                "def reload_prices() -> None:\n"
                "    fetch_latest()\n"
                "    refresh(price_table)          # par la zone\n"
                '    # ou : refresh("price_table")  # par son name=\n',
                lang="python",
            )

        # ── broadcast ────────────────────────────────────────────
        with ui.card(), ui.vstack(gap="sm"):
            ui.heading("Temps réel entre clients — broadcast", level=2)
            ui.text(
                "`deps` et `broadcast` sont deux listes ORTHOGONALES, et "
                "la question qu'elles posent est la même : qui change cet "
                "état ?",
                color="muted", size="sm",
            )
            with ui.vstack(gap="xs", classes="pl-4"):
                ui.text(
                    "• MOI → `deps`. La zone est re-rendue dans la "
                    "réponse de l'action : un aller-retour, un swap.",
                    color="muted", size="sm",
                )
                ui.text(
                    "• LES AUTRES → `broadcast`. Un signal SSE, puis un "
                    "refetch : deux allers-retours, mais l'onglet qui n'a "
                    "rien fait suit.",
                    color="muted", size="sm",
                )
                ui.text(
                    "• LES DEUX → les deux listes. Ce n'est pas une "
                    "redondance : ça dit « instantané pour moi, poussé "
                    "aux autres ».",
                    color="muted", size="sm",
                )
            ui.code(
                "@refreshable(deps=[Cart])                     # local\n"
                "@refreshable(broadcast=[FileAttente])         # je ne le\n"
                "                                              # change jamais\n"
                "@refreshable(deps=[Presence], broadcast=[Presence],\n"
                '             name="online_users")             # les deux\n',
                lang="python",
            )
            ui.text(
                "Ce qui traverse n'est qu'un SIGNAL : chaque client "
                "refetch dans son propre contexte, aucune donnée ne passe "
                "d'un client à l'autre. `name=` donne une adresse stable "
                "pour `refresh(\"…\")`.",
                color="muted", size="xs",
            )

        # ── Frontière ────────────────────────────────────────────
        with ui.card(color="surface"), ui.vstack(gap="xs"):
            ui.heading("Et ensuite", level=3)
            with ui.hstack(align="baseline", gap="sm", wrap=True):
                ui.text(
                    "La réactivité qui vit dans le navigateur, sans "
                    "aller-retour :",
                    color="muted", size="sm",
                )
                ui.link("Réactivité client →", href="/reactivity-client")
