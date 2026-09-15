"""Chat — démonstrateur du STREAMING serveur → navigateur.

Run : ``py -m examples.chat.main``.

Ce que cet exemple montre, et pourquoi il existe : Bretzel a deux façons
de changer le DOM, et un texte qui se remplit progressivement est le cas
qui oblige à choisir la bonne.

- La **structure** (un message de plus dans le journal) ne peut changer
  que par un re-rendu serveur → ``@refreshable``, ici en
  ``broadcast=[Log]`` pour que les autres onglets suivent.
- La **valeur** (le texte du message en cours qui grandit) n'a pas besoin
  de HTML : le serveur réassigne un champ ``ClientState``, il redescend
  dans un patch JSON, et le navigateur écrit dans un nœud de texte.

Et la **cadence** est tirée par le client (``ui.interval`` gaté sur un
``ClientBinding``), pas poussée par le serveur. Ce n'est pas un détail de
performance, c'est ce qui rend le bouton *Stop* possible : une boucle
``@background`` tourne sans contexte de requête, donc ne peut pas
relire l'état qui lui dirait de s'arrêter (``handlers.md`` § *background*
— le stepper du playground a fait exactement ce chemin en sens inverse).

Le générateur de tokens est **simulé** : aucun appel LLM, aucune clé
d'API. Le sujet est le transport ; brancher un vrai modèle ne changerait
qu'``examples/chat/features/generator.py`` § ``answer_for``.
"""

from bretzel import Bretzel
from examples.chat.core.theme import THEME
from examples.chat.features import conversation, shell

app = Bretzel(
    title="Bretzel · Chat",
    secret_key="dev-chat-secret-change-me",
    theme=THEME,
    mode="dev",
    # L'app est écrite en français : la déclarer pose ``<html lang>`` et
    # traduit les mots que le framework écrit lui-même. Le CRM en montre
    # la table complète ; ici trois suffisent.
    lang="fr",
    texts={
        "sidebar.toggle": "Afficher ou masquer le menu",
        "sidebar.rail_toggle": "Replier ou déplier la barre latérale",
        "input.clear": "Effacer",
    },
)

app.include(shell, conversation)


if __name__ == "__main__":
    app.run(port=8003, reload=True)
