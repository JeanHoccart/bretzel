"""chat/shell — le cadre. Une feature comme une autre, qui expose une région.

``fixed inset-0`` et non ``h-screen`` : ça sort le shell du flux, sinon un
panneau scrollable gonfle ``html.scrollHeight`` et le viewport se retrouve
avec une seconde barre de défilement (cf. ``traps.md`` § *Shell layout
h-screen*). Le conteneur de conversation scrolle tout seul.
"""

from __future__ import annotations

from bretzel import LiveConnection, Screen, layout, ui


@layout
def shell() -> None:
    with ui.viewport():
        # UN seul ``ui.sidebar``, MÊMES enfants, deux modes de repli. Le
        # ternaire est tout le responsive de cette app.
        #
        # - desktop → ``offcanvas`` : replié, la sidebar s'efface. Sur une
        #   app à UNE page, une bande d'icônes permanente (``rail``)
        #   occuperait de la largeur sans rien offrir.
        # - mobile  → ``overlay`` : elle sort du flux et glisse au-dessus
        #   du contenu, fond assombri, Escape, scroll bloqué. C'est le
        #   SEUL mode non gaté ``md:`` ; ``offcanvas`` sur un téléphone ne
        #   se fermerait tout simplement pas.
        #
        # ``Screen().is_mobile`` est un ``if`` SERVEUR (cookie lu au
        # rendu), donc une seule branche existe dans le DOM : un seul
        # composant, un seul état ``open``, un seul ``.toggle()``.
        sidebar = ui.sidebar(
            collapsible="overlay" if Screen().is_mobile else "offcanvas",
            # Sur mobile la sidebar démarre FERMÉE — elle couvrirait la
            # conversation. Sur desktop elle démarre ouverte.
            open=not Screen().is_mobile,
        )
        with sidebar:
            ui.sidebar_title(
                "Chat",
                icon=ui.icon("message-square", color="primary", size="lg"),
            )
            with ui.sidebar_section(label="DÉMO"):
                ui.sidebar_item("Conversation", icon="message-circle", href="/")

        with ui.vstack(gap="none", classes="flex-1 min-w-0 overflow-hidden"):
            with ui.hstack(
                justify="between", align="center", gap="sm",
                classes="px-6 py-3 border-b border-text/10",
            ):
                # Le déclencheur vit DANS la topbar de l'app, pas dans le
                # composant : la sidebar n'auto-rend plus de bouton de
                # ré-ouverture, elle en aurait posé un deuxième, flottant,
                # à côté de celui-ci. ``ui.sidebar_trigger`` est la pièce
                # à poser — elle câble la barre, émet l'``aria-controls``,
                # et satisfait la garde d'atteignabilité.
                ui.sidebar_trigger(sidebar, size="sm")
                # ``LiveConnection`` est un ClientState du framework : le runtime
                # y bascule l'état de la connexion SSE. On ne le pilote
                # pas, on le LIT — l'indicateur dit si les autres onglets
                # recevront bien le journal en direct.
                with ui.hstack(align="center", gap="sm"):
                    ui.badge("live", color="success",
                             visible=LiveConnection().connected)
                    ui.badge("hors ligne", color="muted",
                             visible=~LiveConnection().connected)

            # ⚠️ La chaîne de hauteurs doit être CONTINUE jusqu'à la page,
            # sinon aucune zone interne ne peut défiler. Deux maillons sont
            # à poser à la main :
            #
            # 1. ``ui.container`` est un ``block`` par défaut — son enfant
            #    ne peut donc pas prendre ``flex-1``. D'où ``flex flex-col``.
            # 2. ``ui.outlet`` rend un ``<main>`` **block sans hauteur**. Il
            #    n'hérite d'aucune contrainte : mesuré à 1 888 px dans un
            #    parent de 855 px, clippé en silence par l'``overflow-hidden``.
            #    Le ``h-full`` de la page ne résolvait alors jamais, et sa
            #    zone de messages grandissait au lieu de défiler.
            #
            # C'est le prix d'un layout pleine hauteur aujourd'hui : l'outlet
            # ne transmet pas la contrainte, il faut la lui donner.
            with ui.container(
                width="lg",
                classes="flex-1 min-h-0 overflow-hidden flex flex-col",
            ):
                ui.outlet(classes="flex-1 min-h-0 flex flex-col")
