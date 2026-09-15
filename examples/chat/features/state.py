"""chat/state — trois états, et la frontière entre eux est le sujet.

Le découpage n'est pas cosmétique : c'est lui qui décide de ce qui voyage
sur le fil, et dans quel sens.

- :class:`Log` — ``SessionState``. La CONVERSATION : les messages validés.
  Elle est la source de vérité, elle vit côté serveur, et elle change de
  **structure** (une ligne de plus). Seul un re-rendu peut afficher ça,
  donc c'est une zone ``@refreshable``.

- :class:`Gen` — ``SessionState``. Le CURSEUR de génération. Le serveur
  seul sait où il en est dans le texte à débiter ; le client n'a aucune
  raison de le connaître, et surtout aucune autorité dessus.

- :class:`Draft` — ``ClientState``, **``send_to_server=False``**. Ce que
  l'utilisateur VOIT pendant la génération. Le serveur l'écrit, le client
  l'affiche, et il ne remonte jamais : c'est exactement la définition d'un
  état descendant. Sans ce réglage, le texte en cours d'écriture
  repartirait vers le serveur à chaque tick — soit, sur une réponse de
  2 000 tokens débitée en 100 morceaux, des centaines de kilo-octets
  d'upload pour des données que le client vient de recevoir.

⚠️ Le corollaire, qui surprend : ``Draft().answer`` lu dans un handler vaut
toujours ``""``. C'est voulu — le champ ne remonte pas. On n'accumule donc
JAMAIS côté serveur avec ``+=`` : on **réassigne** la tranche complète que
le curseur désigne (``logic.pull_chunk``). Le serveur reste l'auteur, le
client reste un afficheur.
"""

from __future__ import annotations

from bretzel.state import ClientState, SessionState, field


class Log(SessionState):
    """Les messages validés. ``role`` vaut ``"user"`` ou ``"bot"``."""

    messages: list[dict] = field(default_factory=list)


class Gen(SessionState):
    """Où en est la génération en cours, côté serveur uniquement."""

    #: Le texte complet que le générateur débite. Vide = rien en cours.
    full: str = field(default='')
    #: Combien de caractères de ``full`` ont déjà été publiés.
    cursor: int = field(default=0)

    # ── Instrumentation ────────────────────────────────────────────────
    # Le but déclaré de cet exemple : produire le CHIFFRE qui dit si le
    # transport actuel suffit, plutôt qu'une estimation de tête.
    ticks: int = field(default=0)
    #: Somme des tailles de ``answer`` publiées. Chaque tick renvoie la
    #: tranche ENTIÈRE, pas le delta — d'où une croissance quadratique que
    #: la page affiche sans la maquiller.
    bytes_down: int = field(default=0)


class Draft(ClientState, send_to_server=False):
    """Descendant seul : le serveur écrit, le client affiche.

    ``streaming`` gate le ``ui.interval`` de la page. C'est un
    ``ClientBinding``, donc le basculer côté serveur **arrête le timer
    instantanément**, sans attendre le tick suivant — c'est ce qui rend le
    bouton *Stop* honnête. Une boucle ``@background`` ne saurait pas
    faire : elle est sans contexte, donc incapable de relire l'état qui
    dit « arrête-toi » (cf. ``handlers.md`` § *background*).
    """

    answer: str = field(default='')
    streaming: bool = field(default=False)

    # ── Miroirs d'affichage des compteurs de Gen ───────────────────────
    # Duplication assumée, et c'est le motif qui compte : ``Gen`` porte la
    # VÉRITÉ (le serveur l'incrémente), ``Draft`` porte l'AFFICHAGE. Sans
    # ces miroirs, le panneau de mesure serait une zone ``@refreshable``
    # qui se re-rendrait à chaque tick — donc l'instrument fausserait sa
    # propre mesure en ajoutant du HTML à chacune des réponses qu'il
    # compte. Ici il n'est que du texte lié : zéro octet de plus.
    ticks: int = field(default=0)
    bytes_down: int = field(default=0)


class Prompt(ClientState):
    """Ce que l'utilisateur tape. **Sans** ``send_to_server=False``.

    C'est le contre-exemple de :class:`Draft`, et il vaut d'être lu en
    regard : cette valeur naît dans le navigateur, donc elle DOIT remonter
    — sinon le handler ne saurait pas quoi répondre. La déclarer
    descendante-seule la perdrait en silence, et le socle refuse d'ailleurs
    de lier une prop two-way (``ui.input(value=…)``) à un état qui ne
    remonte pas.

    Deux directions, deux états : c'est plus simple qu'un compromis, et
    ça se lit.
    """

    text: str = field(default='')
