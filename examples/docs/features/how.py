"""Fondations — Comment Bretzel fonctionne.

La page-frontière : le concept universel client vs serveur, l'intérêt
de chacun, UI = f(state), et le cycle général de Bretzel. Conceptuel —
zéro signature. Tout le reste de la doc s'appuie là-dessus.
"""

from bretzel import page, ui

from examples.docs.features.shell import shell


_CYCLE = [
    ("mouse-pointer-click", "Une interaction se produit (un clic, une saisie)."),
    ("server", "Si elle change la vérité, elle passe côté serveur : "
               "une fonction Python s'exécute."),
    ("database", "Cette fonction mute l'état."),
    ("refresh-cw", "La partie de l'interface qui dépend de cet état est "
                   "re-rendue et renvoyée au navigateur."),
]


@page("/how", layout=shell, title="Comment Bretzel fonctionne")
def how_page() -> None:
    with ui.container(width="xl"):
        with ui.vstack(gap="lg"):
            ui.heading("Comment Bretzel fonctionne", level=1, size="3xl")
            ui.text(
                "Toute app web a deux moitiés : le navigateur (le client) et "
                "le serveur. Savoir où tourne le code — et quand on passe de "
                "l'un à l'autre — est le cadre qui éclaire tout le reste.",
                color="muted", size="lg",
            )

            # ── Les deux moitiés ─────────────────────────────────────
            with ui.card():
                with ui.vstack(gap="sm"):
                    ui.heading("Les deux moitiés", level=2)
                    ui.table(
                        columns=[
                            ui.column("cote", label="Moitié"),
                            ui.column("quoi", label="C'est quoi"),
                        ],
                        rows=[
                            {"cote": "Client",
                             "quoi": "le navigateur, sur la machine de "
                                     "l'utilisateur — il affiche et réagit"},
                            {"cote": "Serveur",
                             "quoi": "ta machine, où tourne le code Python — "
                                     "il détient la vérité"},
                        ],
                        size="sm",
                    )

            # ── Pourquoi le serveur ──────────────────────────────────
            with ui.card(color="primary"):
                with ui.vstack(gap="sm"):
                    ui.heading("Pourquoi côté serveur", level=2)
                    ui.text(
                        "Règle de base du web : le client a toujours tort. "
                        "Tout ce qui arrive du navigateur peut être trafiqué. "
                        "Donc ce qui compte vit côté serveur :",
                    )
                    with ui.vstack(gap="xs"):
                        for t in [
                            "Sécurité — on ne fait jamais confiance au client ; "
                            "la validation qui protège se fait ici.",
                            "Source de vérité — la donnée est stockée et "
                            "possédée par le serveur, pas par l'onglet.",
                            "Logique confidentielle — un calcul de prix, une "
                            "règle métier ne doivent pas partir dans le "
                            "navigateur.",
                            "Partage — un état serveur est vu par plusieurs "
                            "utilisateurs / onglets ; un état client, non.",
                        ]:
                            with ui.hstack(align="baseline", gap="sm"):
                                ui.icon("check", color="primary", size="sm")
                                ui.text(t, size="sm")

            # ── Pourquoi le client ───────────────────────────────────
            with ui.card():
                with ui.vstack(gap="sm"):
                    ui.heading("Pourquoi côté client", level=2)
                    ui.text(
                        "Passer par le serveur coûte une requête réseau. Pour "
                        "une interaction purement visuelle (ouvrir un menu, "
                        "cocher une case), c'est du gaspillage. Rester côté "
                        "client, c'est :",
                        color="muted", size="sm",
                    )
                    with ui.vstack(gap="xs"):
                        for t in [
                            "Aucune requête — ça marche sans aller-retour, "
                            "donc c'est instantané.",
                            "Allègement du serveur — c'est la machine de "
                            "l'utilisateur qui travaille, pas la tienne.",
                        ]:
                            with ui.hstack(align="baseline", gap="sm"):
                                ui.icon("check", color="success", size="sm")
                                ui.text(t, size="sm")

            # ── UI = f(state) ────────────────────────────────────────
            with ui.card(color="surface"):
                with ui.vstack(gap="xs"):
                    ui.heading("UI = f(state)", level=2)
                    ui.text(
                        "L'interface est une fonction de l'état. On ne "
                        "manipule pas le DOM à la main : on décrit ce que "
                        "l'UI doit être pour un état donné, on mute l'état, "
                        "et l'UI est recalculée.",
                    )

            # ── Le cycle de Bretzel ──────────────────────────────────
            with ui.card():
                with ui.vstack(gap="sm"):
                    ui.heading("Le cycle de Bretzel", level=2)
                    with ui.vstack(gap="sm"):
                        for i, (icon, text) in enumerate(_CYCLE, start=1):
                            with ui.hstack(align="center", gap="sm"):
                                ui.badge(str(i), color="primary", variant="soft")
                                ui.icon(icon, color="primary")
                                ui.text(text, size="sm")
                    ui.text(
                        "Une interaction qui NE change PAS la vérité (ouvrir "
                        "un panneau) court-circuite l'étape serveur et reste "
                        "dans le navigateur.",
                        color="muted", size="sm",
                    )

            # ── Les chemins d'un événement ───────────────────────────
            with ui.card():
                with ui.vstack(gap="sm"):
                    ui.heading("Les chemins d'un événement", level=2)
                    ui.text(
                        "Concrètement, un événement prend l'un de ces "
                        "chemins :",
                        color="muted", size="sm",
                    )
                    ui.table(
                        columns=[
                            ui.column("quoi", label="L'événement…"),
                            ui.column("ou", label="tourne"),
                            ui.column("ar", label="aller-retour ?"),
                        ],
                        rows=[
                            {"quoi": "appelle une fonction Python",
                             "ou": "serveur", "ar": "oui"},
                            {"quoi": "pilote un composant / un état client",
                             "ou": "client", "ar": "non"},
                        ],
                        size="sm",
                    )
                    ui.text(
                        "C'est la même frontière, appliquée partout : l'état, "
                        "les actions et la réactivité ont chacun un côté "
                        "serveur et un côté client. La suite de la doc suit ce "
                        "plan.",
                        color="muted", size="sm",
                    )
