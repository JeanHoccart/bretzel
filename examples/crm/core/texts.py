"""Les mots que le FRAMEWORK écrit lui-même, en français.

``lang="fr"`` fait nommer les mois et les jours par le navigateur — ça,
un code de langue suffit à le dériver. Ces phrases-ci, non : aucune API
ne traduit « Clear filters » ou « Dismiss alert », donc elles se
remplacent une par une.

**Cette table est une MESURE, pas de la configuration.** Sa longueur
répond à « combien d'anglais Bretzel met-il sur un écran français ? », et
c'est exactement ce que le CRM existe pour produire. La raccourcir en
acceptant de l'anglais à l'écran perdrait la mesure.

Elle vit ici et plus dans ``main.py`` : ce fichier-là déclare qu'il est
« le seul à connaître l'instance — il ``include`` les features, sème la
base, et laisse le contrat se valider », et cinquante lignes de
traduction ne sont aucune des trois.

⚠️ **La plupart de ces lignes ne sont pas propres au CRM.** « Fermer »,
« Effacer », « Page précédente » sont du français générique que la
prochaine app française retapera à l'identique ; seule une poignée est
vraiment d'ici (``chart.currency`` en euros). C'est un manque du
framework, pas de cette app, et il est instruit dans
``.claude/work/todo.md``.

Les clés valides sont dans ``bretzel.render.texts.DEFAULT_TEXTS`` ; une
clé inconnue LÈVE au démarrage.
"""

FR_TEXTS: dict[str, str] = {
    "datatable.clear_filters": "Effacer les filtres",
    "datatable.results_one": "{n} résultat",
    "datatable.results_other": "{n} résultats",
    "datatable.results_narrowed_one": "{n} résultat sur {total}",
    "datatable.results_narrowed_other": "{n} résultats sur {total}",
    "combobox.empty": "Aucun résultat",
    "input.clear": "Effacer",
    "combobox.clear": "Effacer",
    "select.clear": "Effacer",
    "alert.dismiss": "Fermer l'alerte",
    "banner.dismiss": "Fermer",
    "badge.remove": "Retirer",
    "modal.close": "Fermer",
    "pagination.previous": "Page précédente",
    "pagination.next": "Page suivante",
    "sidebar.toggle": "Afficher ou masquer le menu",
    "sidebar.rail_toggle": "Replier ou déplier la barre latérale",
    # Le logo replié n'a plus que son glyphe : c'est son seul nom.
    "sidebar.home": "Accueil",
    "calendar.month": "Mois",
    "calendar.year": "Année",
    "date_picker.clear": "Effacer la date",
    "date_picker.open": "Ouvrir le calendrier",
    "date_range_picker.clear": "Effacer la période",
    "date_range_picker.open": "Ouvrir le calendrier",
    "time_picker.clear": "Effacer l'heure",
    "time_picker.open": "Ouvrir le sélecteur d'heure",
    "number_input.increment": "Augmenter",
    "number_input.decrement": "Diminuer",
    "file_upload.accepted": "Formats acceptés : {types}",
    "file_upload.max_size": "Taille maximale : {size}",
    "file_upload.multiple": "Plusieurs fichiers autorisés",
    "file_upload.multiple_capped": "Plusieurs fichiers ({max} maximum)",
    "file_upload.remove": "Retirer le fichier",
    "file_upload.complete": "Envoi terminé",
    "file_upload.error": "Échec de l'envoi",
    # Les montants d'un CRM français : le défaut codait le dollar.
    "chart.currency": "{value} €",
    # Le résumé que lit un lecteur d'écran sur chaque graphique.
    "chart.line": "Graphique en courbes",
    "chart.bar": "Graphique en barres",
    "chart.pie": "Graphique circulaire",
    "chart.donut": "Graphique en anneau",
    "chart.points": "{n} points",
    "chart.categories": "{n} catégories",
    "chart.slices": "{n} parts",
    "chart.series_count": "{n} séries",
    "chart.series": "Série",
    "chart.summary": "{kind} — {what}",
    "chart.summary_across": "{kind} — {what} réparties sur {names}",
    "chart.empty": "Aucune donnée",}
