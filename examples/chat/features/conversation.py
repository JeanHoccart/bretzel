"""chat/conversation — la page, et la frontière qu'elle rend visible.

Trois blocs, et chacun illustre un mécanisme DIFFÉRENT. C'est le sujet de
l'exemple, pas un effet de mise en page :

1. **Le journal** (:func:`message_log`) — une zone ``@refreshable``, parce
   qu'un message de plus est un changement de **structure** : un nœud
   apparaît. Seul un re-rendu serveur peut faire ça. ``broadcast=[Log]``
   parce que la conversation est une propriété de la session, pas d'un
   onglet — ouvrir la page deux fois montre les deux au même endroit.

2. **La bulle en cours** — pas une zone du tout. Un ``<span>`` lié à un
   champ ``ClientState`` : quand le serveur réassigne ``Draft().answer``,
   la valeur redescend dans un patch JSON et le navigateur écrit dans un
   nœud de texte. Aucun HTML analysé, aucun morphing. C'est un changement
   de **valeur**, pas de structure.

3. **Le panneau de mesure** — également des valeurs liées, donc gratuit :
   s'il était une zone refreshable, il ajouterait du HTML à chacune des
   réponses qu'il prétend compter.

⚠️ La bulle en cours affiche du **texte brut**, alors que les messages
validés passent par ``ui.markdown``. Ce n'est pas un oubli :
``ui.markdown`` refuse un ``ClientBinding`` au constructeur, parce qu'un
chemin de binding réduirait toute la structure (titres, listes, blocs de
code) à du texte plat et mentirait en silence. Pendant la génération on
montre donc le brut ; à la validation, le markdown est rendu par le
serveur. C'est aussi ce que font la plupart des UI de chat, pour une
raison voisine : un markdown à moitié écrit n'est pas du markdown valide.
"""

from __future__ import annotations

from bretzel import Screen, page, refreshable, ui
from examples.chat.features.logic import pull_chunk, reset, send, stop
from examples.chat.features.shell import shell
from examples.chat.features.state import Draft, Log, Prompt

#: La boîte d'une bulle. Sans ``w-fit``, « test » occupe les 42 rem du
#: ``max-w`` et la conversation ressemble à un mur : ``max-w`` BORNE, il ne
#: dimensionne pas.
#:
#: Ce ``w-fit`` a exigé un ``!w-fit`` pendant quelques heures — le thème de
#: ``ui.card`` bake ``w-full``, et l'ordre dans l'attribut ``class`` ne
#: décide de rien face à Tailwind. C'est réparé dans le socle : une largeur
#: passée en ``classes=`` retire désormais celle du thème (``_append_attr``,
#: ``components/base/component.py``). Le ``!`` n'est plus nécessaire, et sa
#: disparition ici est le témoin du correctif.
BUBBLE = "w-fit max-w-[85%] md:max-w-[42rem]"


@refreshable(deps=[Log], broadcast=[Log])
def message_log() -> None:
    """Les messages validés — une STRUCTURE, donc une zone."""
    messages = Log().messages
    with ui.vstack(gap="md"):
        if not messages:
            ui.empty_state(
                "Pose une question pour voir le texte arriver par tranches.",
                icon="message-circle",
            )
        for message in messages:
            user = message["role"] == "user"
            with ui.flex(justify="end" if user else "start"):
                with ui.card(
                    color="primary" if user else "surface",
                    padding="md",
                    classes=BUBBLE,
                ):
                    ui.markdown(message["text"])


def streaming_bubble() -> None:
    """La réponse en cours — une VALEUR, donc pas de zone.

    ``visible=`` prend un ``ClientBinding`` : la bulle se montre et se
    cache côté client, sans aller-retour. Et ``ui.text`` lié émet un
    ``bz-text``, donc chaque tranche est une simple écriture de
    ``textContent``.
    """
    with ui.flex(justify="start", visible=Draft().streaming):
        with ui.card(color="surface", padding="md", classes=BUBBLE):
            with ui.hstack(gap="sm", align="start"):
                # ``shrink-0`` : un enfant de flex est compressible par
                # défaut, donc le spinner s'écrasait en ellipse à mesure
                # que le texte grandissait — il maigrissait à vue d'œil
                # pendant la génération.
                ui.spinner(size="sm", color="primary", classes="shrink-0")
                ui.text(
                    Draft().answer,
                    id="bz-stream-answer",
                    classes="whitespace-pre-wrap",
                )


def measurement_panel() -> None:
    """Ce que le transport a réellement coûté — des valeurs liées.

    Le chiffre qui compte est ``octets descendus`` : chaque tick renvoie
    la tranche ENTIÈRE, pas le delta, donc le total croît comme le carré
    de la longueur de la réponse. C'est la propriété qu'on veut voir en
    face, parce que c'est elle qui décidera si le canal SSE doit un jour
    porter un patch d'ajout.
    """
    with ui.card(color="surface", padding="sm"):
        with ui.hstack(gap="lg", align="center", wrap=True):
            ui.text("Mesure du transport", size="xs", weight="medium", color="muted")
            with ui.hstack(gap="xs"):
                ui.text("requêtes :", size="xs", color="muted")
                ui.text(Draft().ticks, size="xs", weight="medium")
            with ui.hstack(gap="xs"):
                ui.text("octets descendus :", size="xs", color="muted")
                ui.text(Draft().bytes_down, size="xs", weight="medium")
            # L'explication saute sur mobile : sur 375 px elle passe à la
            # ligne et pousse les chiffres hors de vue, donc elle coûte
            # exactement ce qu'elle sert à montrer.
            if not Screen().is_mobile:
                ui.text(
                    "chaque tick renvoie la tranche entière — le total croît en O(n²)",
                    size="xs",
                    color="muted",
                    italic=True,
                )


def composer() -> None:
    """La saisie. ``Prompt`` remonte, contrairement à ``Draft``.

    ``Screen().is_mobile`` est un simple ``bool`` résolu au rendu depuis un
    cookie de viewport — donc un ``if`` Python ordinaire, pas une zone
    réactive ni une media-query. Sur un écran étroit, les libellés cèdent
    la place à des icônes : deux boutons texte plus un champ ne tiennent
    pas sur une rangée de 375 px.
    """
    mobile = Screen().is_mobile
    with ui.hstack(gap="sm", align="center"):
        ui.input(
            value=Prompt().text,
            placeholder="Essaie « bretzel »…" if mobile else "Essaie « bretzel » ou « stream »…",
            clearable=True,
            disabled=Draft().streaming,
            classes="flex-1 min-w-0",
        )
        if mobile:
            ui.icon_button(
                "send",
                color="primary",
                on_click=send,
                visible=~Draft().streaming,
                tooltip="Envoyer",
                id="bz-send",
            )
            ui.icon_button(
                "square",
                color="error",
                variant="soft",
                on_click=stop,
                visible=Draft().streaming,
                tooltip="Stop",
            )
        else:
            ui.button(
                "Envoyer",
                color="primary",
                icon_left="send",
                on_click=send,
                visible=~Draft().streaming,
                id="bz-send",
            )
            ui.button(
                "Stop",
                color="error",
                variant="soft",
                icon_left="square",
                on_click=stop,
                visible=Draft().streaming,
            )


@page("/", layout=shell)
def conversation() -> None:
    with ui.vstack(gap="lg", classes="flex-1 min-h-0"):
        # En-tête et composeur : ``shrink-0``, sinon flexbox les comprime
        # pour faire de la place au journal au lieu de le faire défiler.
        with ui.hstack(justify="between", align="center", classes="shrink-0"):
            ui.heading("Conversation", level=2, size="xl")
            ui.button(
                "Effacer",
                variant="ghost",
                color="muted",
                icon_left="trash-2",
                on_click=reset,
            )

        # ``ui.pane`` porte le ``min-h-0`` qui fait apparaître la barre :
        # sans lui, le plancher ``min-height:auto`` d'un enfant de flex
        # empêche la zone de descendre sous la hauteur de son contenu, elle
        # grandit avec la conversation, et ``overflow-y-auto`` n'a jamais
        # rien à faire. Reproduit en écrivant cet exemple, avant que le
        # composant existe.
        with ui.pane(gap="md"):
            message_log()
            streaming_bubble()

        with ui.vstack(gap="sm", classes="shrink-0"):
            composer()
            measurement_panel()

    # Le métronome. ``active=`` est un ``ClientBinding`` : le serveur le
    # bascule à False et le timer s'arrête au même instant, sans attendre
    # le tick suivant. C'est ce qui rend le bouton Stop honnête — et ce
    # qu'une boucle ``@background`` ne saurait pas faire, étant sans
    # contexte donc incapable de relire l'état qui l'arrête.
    ui.interval(on_tick=pull_chunk, seconds=0.12, active=Draft().streaming)
