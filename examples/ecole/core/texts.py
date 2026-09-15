"""core/texts — les mots que le FRAMEWORK écrit lui-même, en français.

``lang="fr"`` suffit à faire nommer les mois et les jours par le
navigateur. Ces phrases-ci, non : aucune API ne traduit « Dismiss alert »,
donc elles se remplacent une par une.

Les clés valides sont dans ``bretzel.render.texts.DEFAULT_TEXTS`` ; une
clé inconnue LÈVE au démarrage — une faute de frappe dans un dict de
traduction ne produit sinon aucune erreur, juste une phrase restée en
anglais que personne ne relira.

⚠️ Cette table est **la même** que celle d'``examples/crm``, à la
monnaie près. C'est un manque du framework — du français générique
retapé d'une app à l'autre — déjà instruit dans ``.claude/work/todo.md``.
Elle est recopiée plutôt qu'importée du CRM : une app d'exemple n'importe
pas une autre app d'exemple, et le jour où le framework livrera ses
tables de langue, les deux copies disparaîtront ensemble.
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
    "chart.empty": "Aucune donnée",
}
