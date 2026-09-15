"""École — les trois cahiers d'un professeur de physique-chimie, en un.

``py -m examples.ecole.main`` (port 8019).

**Une seule application**, et c'est la première décision du cahier des
charges (``.claude/work/ecole-cahier-des-charges.md``, § 1.1). Dans le
monde réel ce sont deux programmes, deux serveurs, deux ports, et le
second lit la base du premier en lecture seule pour connaître les classes
et l'emploi du temps. Cette couture n'existe que parce qu'il y a deux
processus ; ici il n'y en a qu'un, et les deux « dépendances croisées »
deviennent des lectures ordinaires.

Ce que l'app met en scène — sa mécanique, en une phrase : **un métier
entier tient dans un seul modèle de données typé, et chaque écran n'est
qu'une lecture de ce modèle sous un angle.** Trois cahiers — les élèves,
le calendrier, le cahier de texte — que le professeur tient aujourd'hui à
la main ou dans deux programmes séparés.

État de la construction
-----------------------
Le cahier découpe le travail en dix lots, chacun livré seul, chacun
consommant le précédent. **Les dix lots sont livrés** : le modèle de données complet
(§ 5), le jeu semé aux volumes réels (§ 13), la coque, l'accueil, le
sélecteur d'année et la barrière RT-1 ; l'écran des réglages —
l'année, ses trimestres par cycle, ses jours sans classe et ce que
chacun fait perdre comme cours ; et la grille de la semaine, avec son
alternance déduite, ses blocs, ses TP, ses heures exceptionnelles et
son retour en arrière ; et les classes — la grille de photos, la
fiche d'un élève, ses particularités, son parcours, les quatre
mouvements et la recherche par nom ou prénom ; et les notes — les
évaluations, la répartition par compétences, la saisie de masse, les
refus métier, l'histogramme et le report sur École Directe ; et les
appréciations — les tuiles d'observation, la rédaction sous 400
caractères, la règle du texte écrit à la main, la relecture de classe
et le bilan ; et le plan de classe — le tracé de la salle, les allées
en couloir, le glisser arbitré par le serveur, les contraintes de
classe, la répartition automatique, les versions et le fige ; et le
suivi — le travail à vérifier, les deux rappels calculés à la demande,
et les cadres d'entrée en cours ; et le cahier de texte — la saisie du
soir pré-remplie, les deux boutons de copie, la reprise d'une classe
sœur, le tableau de progression et les fiches de séance ; et les
entrées-sorties — l'import en deux temps, le remplacement des photos
apparié par nom, et les archives imprimables.

``main`` est le seul fichier à connaître l'instance : il ``include`` les
features, sème la base au démarrage, et laisse le contrat se valider.
"""

from bretzel import Bretzel
from examples.ecole.core import db
from examples.ecole.core.db import init_db
from examples.ecole.core.texts import FR_TEXTS
from examples.ecole.core.theme import THEME
from examples.ecole.features import (
    accueil,
    annees,
    appreciations,
    appreciations_data,
    cahier,
    cahier_data,
    calendrier_data,
    classe,
    classes_data,
    eleve,
    eleves_data,
    emploi_du_temps,
    errors,
    evaluation,
    evaluations,
    grille_data,
    import_data,
    import_screen,
    notes_data,
    plan,
    plan_data,
    recherche,
    reglages,
    shell,
    suivi,
    suivi_data,
    vue_classe,
)

app = Bretzel(
    title="École · physique-chimie",
    secret_key="dev-ecole-secret-change-me",
    theme=THEME,
    # ``dev`` : le professeur lance l'app lui-même et la rouvre souvent.
    # Le CSS est compilé DANS le navigateur, donc aucun binaire Tailwind
    # n'est requis pour un premier démarrage. Le CRM est en ``prod`` pour
    # mesurer la vitesse réelle ; ce n'est pas ce que cette app mesure.
    mode="prod",
    # La langue, déclarée une fois : elle pose ``<html lang="fr">``, fait
    # nommer les mois et les jours par le navigateur, et voyage jusqu'aux
    # composants de date — dont l'app sera pleine dès le lot 2.
    lang="fr",
    texts=FR_TEXTS,
)


@app.startup
async def semer() -> None:
    # Idempotent : ne resème que si la version du seed ou l'année de la
    # rentrée a bougé. ~1 s la première fois, zéro les suivantes.
    init_db()


app.include(
    db,                 # infra  — le fichier SQLite et ses portes
    annees,             # logic  — l'année regardée, la barrière RT-1
    classes_data,       # data   — les lectures de classes
    calendrier_data,    # data   — l'année, ses trimestres, ses jours
    grille_data,        # data   — la grille type et ses exceptions
    eleves_data,        # data   — les élèves et leurs inscriptions
    notes_data,         # data   — les évaluations, les notes, les refus
    appreciations_data,  # data  — les fiches d'observation
    plan_data,          # data   — les salles, les places, les contraintes
    suivi_data,         # data   — le travail à vérifier, les rappels
    cahier_data,        # data   — le cahier de texte, la progression
    import_data,        # data   — l'import en deux temps, l'archive
    vue_classe,         # state  — ce qu'on regarde d'une classe
    suivi,              # logic  — les cadres, les rappels, les vérifs
    evaluations,        # logic  — l'onglet Évaluations d'une classe
    shell,              # shell  — le cadre
    emploi_du_temps,    # page   — la grille de la semaine (l'ouverture)
    accueil,            # page   — la tuile par classe
    classe,             # page   — une classe et ses élèves
    eleve,              # page   — la fiche d'un élève
    evaluation,         # page   — la saisie des notes d'un devoir
    appreciations,      # page   — tuiles, texte, relecture, bilan
    plan,               # page   — le plan de classe, glisser arbitré
    cahier,             # page   — la saisie du soir, les fiches
    import_screen,      # page   — importer une liste, archiver
    recherche,          # page   — chercher par nom ou prénom
    reglages,           # page   — année, trimestres, jours sans classe
    errors,             # error
)


if __name__ == "__main__":
    app.run(port=8019, reload=True)
