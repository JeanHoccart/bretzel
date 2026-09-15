"""Messagerie — démonstrateur de **l'adresse comme état**, dans un document gelé.

Run : ``py -m examples.messagerie.main`` (port 8005).

Ce que cet exemple montre, et pourquoi il existe. Une boîte mail est la
forme la plus reconnaissable de deux mécaniques que rien d'autre ne
mettait en scène ici :

1. **La vue vit dans l'URL.** ``Vue`` déclare ``URL = {…}`` : le dossier
   ouvert et le message lu deviennent des paramètres d'adresse. Le socle
   réécrit la barre du navigateur à chaque mutation, sans navigation ni
   rechargement, et la relit au rendu suivant. Trois comportements
   arrivent d'un coup sans qu'une ligne les code — le lien se partage, le
   favori retrouve la vue, et les flèches du navigateur font
   l'aller-retour. Le CRM publiait déjà le tri d'une table, mais avec les
   noms hérités de ``DatatableState`` ; ici les noms sont écrits.

2. **Le document ne défile pas, ses régions oui.** ``ui.viewport`` +
   trois ``ui.pane`` : la liste défile sans emporter les dossiers, le
   corps d'un message long défile sans emporter la liste. C'est le modèle
   des outils, et Bretzel garde l'autre par défaut — celui-ci s'écrit.

S'y ajoute le **glisser-déposer vers un dossier**
(``ui.dropzone`` / ``ui.drag_each``), qui n'est pas un extra dans une
messagerie mais son verbe principal, et qui raconte la même histoire :
ranger un message change la vue, donc change l'adresse.

**Aucune barre latérale**, délibérément : la colonne des dossiers est la
navigation. **Aucune base de données** : la boîte est un ``AppState``
semé en mémoire, donc redémarrer le serveur la remet à zéro. Et **rien
ne part** — « Envoyer » range le message dans *Envoyés*, il n'y a pas de
SMTP derrière.

Cette app n'utilise pas les contrats ``Feature``. Ce n'est pas un oubli :
la structure d'app est ce que ``examples/mad`` met en scène, et l'ajouter
ici mettrait deux sujets dans un exemple qui en démontre un.
"""

from bretzel import Bretzel
from examples.messagerie.core.theme import THEME
from examples.messagerie.features import boite, shell

app = Bretzel(
    title="Bretzel · Messagerie",
    secret_key="dev-messagerie-secret-change-me",
    theme=THEME,
    mode="dev",
    lang="fr",
    texts={
        "file_upload.dropzone": "Dépose des fichiers ici, ou clique pour choisir",
        "file_upload.button": "Envoyer le fichier",
        "file_upload.remove": "Retirer le fichier",
        "file_upload.multiple_capped": "Plusieurs fichiers (jusqu'à {max})",
    },
)

app.include(shell, boite)


if __name__ == "__main__":
    app.run(port=8005, reload=True)
