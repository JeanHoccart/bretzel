"""Handlers serveur du playground Diagram.

Chaque handler est un callable de NIVEAU MODULE : Bretzel l'adresse
par ``module::qualname`` et refuse une lambda ou une fermeture.

Aucun import de ``ui`` : les panneaux déclarent ``deps=[…]``, donc
muter l'état suffit à les re-rendre. C'est ce qui évite le cycle
handler ↔ panneau.
"""

from examples.playground.features.diagram.state import (
    DiagramPlayground,
    DiagramServerEvents,
    Picked,
)


def pick(key: str) -> None:
    """``on_item_click`` reçoit la CLÉ du nœud, rien d'autre.

    Recliquer le nœud centré rend la vue d'ensemble : sans ça on
    s'enferme dans un voisinage sans porte de sortie.
    """
    state = Picked()
    state.key = "" if state.key == key else key


def playground_click_handler(key: str) -> None:
    """Le handler du Server playground — module-level, donc adressable."""


def server_changed(state: DiagramPlayground) -> None:
    """Le dispatcher hydrate le contrôle changé dans ``state``."""




def log_item_click(key: str) -> None:
    """Journalise un clic serveur.

    Ré-AFFECTE la liste plutôt qu'un ``append`` en place : le descripteur
    de champ ne voit pas une mutation interne, donc l'état ne serait pas
    marqué sale et le panneau ne se re-rendrait pas.
    """
    state = DiagramServerEvents()
    state.log = [*state.log, f"item_click(key={key!r})"]


def clear_log() -> None:
    DiagramServerEvents().log = []
