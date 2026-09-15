"""Kanban — démonstrateur du **tableau partagé**, glissé à plusieurs.

Run : ``py -m examples.kanban.main`` (port 8009).

Ce que cet exemple montre, et pourquoi il existe. Le tableau est un
``AppState`` : un objet UNIQUE dont toutes les fenêtres ouvertes parlent.
Chaque zone déclare deux listes distinctes —

    @refreshable(deps=[Tableau, Filtres], broadcast=[Tableau])

— et la question qu'elles posent n'est pas la même. ``deps`` dit *ce qui
me re-rend, moi*, dans la réponse de ma propre action. ``broadcast`` dit
*ce que les autres fenêtres doivent refaire*, par un signal SSE. Le
tableau est dans les deux : je le change, ils doivent le voir. Les
filtres ne sont que dans ``deps`` — ce que je masque ne regarde que moi,
et le diffuser ferait retravailler toute l'équipe à chaque frappe d'une
seule personne.

**L'essai qui prouve quelque chose se fait à DEUX fenêtres.** Une seule
ne montre rien : elle aurait de toute façon re-rendu sa propre zone.
Ouvre l'app deux fois côte à côte — une fenêtre privée pour être
quelqu'un d'autre — et glisse une carte à gauche : elle bouge à droite,
et le fil d'activité y écrit qui l'a fait.

Le **glisser-déposer** est le verbe du tableau, et il est arbitré par le
serveur. « En cours » et « En revue » portent une limite d'en-cours ;
au-delà, le handler ne mute rien — et comme le navigateur avait déjà
bougé la carte, le rendu qui le contredit la remet en place. Il n'y a pas
de ``reject()`` : refuser, c'est ne rien écrire. La zone « Archiver » du
bandeau montre l'autre porte, ``locked=True`` : elle accepte tout et ne
laisse rien repartir.

**Aucune base de données** : redémarrer le serveur remet le tableau à son
état de départ. **Aucune authentification** : le sélecteur « Tu es… »
change d'identité en un clic, parce que le sujet de cet exemple est
l'état partagé et pas la connexion (``examples/auth`` fait l'autre).
Et **aucun champ adressable** : ``URL = {…}`` est la mécanique de
``examples/messagerie``, la reprendre ici donnerait deux sujets à une app
qui en démontre un.

Cette app n'utilise pas les contrats ``Feature`` : la structure d'app est
ce que ``examples/mad`` met en scène.
"""

from bretzel import Bretzel
from examples.kanban.core.theme import THEME
from examples.kanban.features import (
    donnees,
    fiche,
    logic,
    shell,
    state,
    tableau,
)

app = Bretzel(
    title="Bretzel · Kanban",
    secret_key="dev-kanban-secret-change-me",
    theme=THEME,
    mode="dev",
    lang="fr",
)

app.include(donnees, state, logic, shell, fiche, tableau)


if __name__ == "__main__":
    app.run(port=8009, reload=True)
