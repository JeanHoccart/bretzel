"""core/texts — the words the FRAMEWORK writes itself, in French.

``lang="fr"`` is enough to make the browser name the months and the days.
These sentences, no: no API translates "Dismiss alert", so they are
replaced one by one.

The valid keys are in ``bretzel.render.texts.DEFAULT_TEXTS``; an unknown
key RAISES at startup — a typo in a translation dict would otherwise
produce no error at all, just a sentence left in English that nobody will
re-read.

⚠️ This table is **the same** as ``examples/crm``'s, up to the currency.
It is a gap in the framework — generic French retyped from one app to the
next — already filed in ``.claude/work/todo.md``. It is copied rather
than imported from the CRM: an example app does not import another
example app, and the day the framework ships its language tables, both
copies will disappear together.
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
