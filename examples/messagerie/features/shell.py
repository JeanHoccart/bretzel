"""messagerie/shell — le cadre gelé, la recherche, et **pas de barre latérale**.

Écrire ``ui.viewport()``, c'est choisir un modèle de défilement. Bretzel
garde par défaut celui du web — le document défile sous un chrome fixe —
et celui-ci est l'autre : le document ne bouge JAMAIS, ce sont les
régions qui défilent, chacune la sienne. C'est le modèle des outils (VS
Code, Slack), et une messagerie est exactement ce cas : la liste des
messages défile sans emporter la colonne des dossiers, et le corps d'un
message long défile sans emporter la liste.

Le prix est une chaîne de hauteurs continue de la racine à la région,
d'où le ``flex-1 min-h-0`` sur l'outlet : ``ui.outlet`` rend un
``<main>`` block sans hauteur, qui n'hérite d'aucune contrainte (cf. la
coque de ``examples/chat``, qui porte la mesure).

**Aucune ``ui.sidebar``, et c'est délibéré.** Presque toutes les autres
démos du dépôt en ont une ; ici la colonne des dossiers EST la
navigation. Une barre latérale par-dessus ferait deux niveaux de menu
pour une app qui n'a qu'une page.
"""

from __future__ import annotations

from bretzel import layout, ui
from bretzel.theme import ColorScheme
from examples.messagerie.features.state import Filtre


@layout
def shell() -> None:
    with ui.viewport(direction="col"):
        with ui.hstack(
            align="center",
            gap="md",
            classes="px-4 py-2.5 border-b border-text/10 shrink-0",
        ):
            with ui.hstack(align="center", gap="sm", classes="w-52 shrink-0"):
                ui.icon("mail", color="primary", size="lg")
                ui.heading("Messagerie", level=1, size="md")

            # Aucun ``on_input``, aucun ``debounce``, aucune zone à
            # re-rendre : ``Filtre`` est un ``ClientState``, et la liste
            # itère en ``ui.filter_each``. Taper filtre DANS le
            # navigateur, sans une seule requête. La version d'avant
            # postait à chaque frappe temporisée — elle marchait, mais
            # elle réécrivait à la main une primitive du framework.
            ui.input(
                value=Filtre().q,
                placeholder="Rechercher dans les messages",
                icon_left="search",
                size="sm",
                clearable=True,
                classes="flex-1 max-w-2xl",
            )

            with ui.hstack(align="center", gap="xs", classes="shrink-0"):
                # ⚠️ Pas de bouton « effacer » ici. `clearable=True` sur
                # l'input en pose déjà un, CÔTÉ CLIENT. Un second, gaté
                # sur `visible=Filtre().q != ""`, aurait été mort-né :
                # `Filtre` est un état SERVEUR, donc l'expression est un
                # booléen Python évalué une seule fois au rendu de la
                # coque — et la coque n'est pas une zone rafraîchissable.
                # Il n'aurait jamais ni apparu ni disparu.
                #
                # Le bascule clair/sombre. Deux boutons et non un seul :
                # les variantes ``dark:`` de Tailwind en cachent toujours
                # un, donc l'icône affichée est celle de la destination.
                # ``ColorScheme`` appartient au framework — l'app ne
                # l'instancie jamais, elle appelle ses helpers de classe.
                ui.icon_button(
                    "moon", variant="ghost", size="sm",
                    on_click=ColorScheme.toggle(), tooltip="Passer en sombre",
                    classes="dark:!hidden",
                )
                ui.icon_button(
                    "sun", variant="ghost", size="sm",
                    on_click=ColorScheme.toggle(), tooltip="Passer en clair",
                    classes="!hidden dark:!inline-flex",
                )

        ui.outlet(classes="flex-1 min-h-0 flex")
