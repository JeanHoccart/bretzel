"""chat/logic — les trois actions : envoyer, tirer un morceau, arrêter.

Le cœur du démonstrateur est :func:`pull_chunk`, et sa forme mérite d'être
lue avant d'être copiée.

**On réassigne, on n'accumule pas.** ``Draft`` est déclaré
``send_to_server=False`` : ses champs ne remontent jamais, donc
``Draft().answer`` vaut ``""`` dans un handler. Un ``+=`` repartirait de
zéro à chaque tick. Le serveur publie donc la tranche que le curseur
désigne — ``full[:cursor]`` — et reste seul auteur de la valeur.

**C'est le client qui bat la mesure.** ``ui.interval`` tire un morceau
toutes les 120 ms tant que ``Draft().streaming`` est vrai. Basculer ce
champ depuis le serveur coupe le timer instantanément, ce qui rend *Stop*
honnête. Une boucle serveur (``@background``) ne saurait pas s'arrêter :
elle est sans contexte de requête, donc incapable de relire l'état qui le
lui dirait — c'est écrit noir sur blanc dans ``handlers.md`` § *background*,
et le stepper du playground est passé de ce motif à ``ui.interval``
exactement pour cette raison.
"""

from __future__ import annotations

from examples.chat.features.generator import advance, answer_for
from examples.chat.features.state import Draft, Gen, Log, Prompt


def send() -> None:
    """Valider le message de l'utilisateur et armer la génération.

    Le texte vient de ``Prompt``, un ``ClientState`` ordinaire — donc il
    remonte avec le POST et se lit ici en valeur Python brute. C'est la
    direction inverse de ``Draft``, et c'est pour ça que ce sont deux
    états et pas un.
    """
    draft_prompt = Prompt()
    prompt = (draft_prompt.text or "").strip()
    if not prompt:
        return
    draft_prompt.text = ""  # vider le champ de saisie

    log = Log()
    # Réassignation et non ``.append()`` : une liste mutée en place ne
    # déclenche pas la détection de changement, donc la zone ne se
    # re-rendrait pas (cf. traps.md § mutation de collection).
    log.messages = [*log.messages, {"role": "user", "text": prompt}]

    gen = Gen()
    gen.full = answer_for(prompt)
    gen.cursor = 0
    gen.ticks = 0
    gen.bytes_down = 0

    draft = Draft()
    draft.answer = ""
    draft.streaming = True
    draft.ticks = 0
    draft.bytes_down = 0


def pull_chunk() -> None:
    """Publier un mot de plus. Appelé par ``ui.interval``, côté client."""
    gen = Gen()
    if not gen.full or gen.cursor >= len(gen.full):
        stop()
        return

    gen.cursor = advance(gen.full, gen.cursor)
    slice_ = gen.full[: gen.cursor]

    gen.ticks += 1
    # La tranche ENTIÈRE repart à chaque tick — c'est la propriété qu'on
    # veut rendre visible, pas cacher. Le total croît en O(n²) sur la
    # longueur de la réponse, et la page l'affiche.
    gen.bytes_down += len(slice_.encode("utf-8"))

    draft = Draft()
    draft.answer = slice_
    draft.ticks = gen.ticks
    draft.bytes_down = gen.bytes_down

    if gen.cursor >= len(gen.full):
        stop()


def stop() -> None:
    """Arrêter la génération et verser ce qui a été produit dans le log.

    Appelé par le bouton *Stop* comme par la fin naturelle du texte : dans
    les deux cas ce qui a été écrit est conservé, parce qu'une réponse
    interrompue reste une réponse — la jeter punirait l'utilisateur d'avoir
    cliqué.
    """
    gen = Gen()
    draft = Draft()

    produced = gen.full[: gen.cursor]
    if produced:
        log = Log()
        log.messages = [*log.messages, {"role": "bot", "text": produced}]

    gen.full = ""
    gen.cursor = 0
    draft.answer = ""
    draft.streaming = False
    # ``ticks`` / ``bytes_down`` ne sont PAS remis à zéro ici : la mesure
    # ne devient lisible qu'une fois la génération finie. Les effacer à
    # l'arrivée viderait le panneau à la seconde où il devient utile.


def reset() -> None:
    """Vider la conversation — et là, oui, remettre les compteurs à zéro."""
    Log().messages = []
    gen = Gen()
    gen.full = ""
    gen.cursor = 0
    gen.ticks = 0
    gen.bytes_down = 0
    draft = Draft()
    draft.answer = ""
    draft.streaming = False
    draft.ticks = 0
    draft.bytes_down = 0
    Prompt().text = ""
