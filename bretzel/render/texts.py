"""Les mots que le framework a écrits lui-même, et comment les remplacer.

Un composant Bretzel écrit des phrases : « Clear filters » sur le bouton
de la datatable, « Dismiss alert » sur la croix d'une alerte, « Accepted:
… » sous une zone de dépôt. Elles sont en anglais, et **aucune API au
monde ne sait les traduire** — contrairement aux noms de mois, aux
formats de date ou aux séparateurs de nombres, qui se DÉRIVENT d'un code
de langue et que :attr:`~bretzel.server.config.BretzelConfig.lang` suffit
à obtenir (cf. la docstring de ce champ).

D'où ce module : une table plate, une clé par phrase, surchargeable par
l'app en un seul endroit ::

    Bretzel(lang="fr", texts={
        "datatable.clear_filters": "Effacer les filtres",
        "alert.dismiss": "Fermer l'alerte",
    })

Ce module possède les **mots**. Le choix de la LANGUE — négociation,
cookie, table du visiteur — vit à côté, dans :mod:`bretzel.render.lang` :
deux questions, deux modules, et c'est le découpage qui rend chacun
lisible seul.

⚠️ Ça ne fait **pas** de l'i18n (hors périmètre v2.0), et il faut savoir
où s'arrête la promesse : le framework traduit LES MOTS QU'IL A ÉCRITS.
Les tiennes — « Contacts », « Enregistrer » — n'ont ni catalogue, ni
extraction, ni marquage. :attr:`bretzel.Language.code` rend la langue résolue, et
un dict par langue dans ton app fait le reste en six lignes. La seule
règle de pluriel est *un / autre*, ce qui couvre l'anglais et le
français, pas le russe.

C'est aussi la réparation d'une incohérence : jusqu'ici la moitié des
textes visibles étaient des props (``search_placeholder=``, ``empty_text=``,
``label=``) et l'autre moitié était en dur, sans qu'aucune règle ne dise
laquelle serait laquelle.

Pourquoi une table plutôt qu'une prop par phrase
------------------------------------------------
Une prop par phrase, ce sont vingt-six props de plus sur seize composants,
à repasser **à chaque montage** — exactement le défaut que
``month_names=`` avait déjà, et qui coûtait trois répétitions sur un seul
écran du CRM. La table se déclare une fois pour l'app.

Comment y ajouter une entrée
----------------------------
Une phrase neuve dans un composant s'écrit ``text("mon_composant.ma_clé")``
et sa valeur anglaise se pose ici. L'ordre inverse — écrire la chaîne en
dur « pour l'instant » — est ce que
``tests/consistency/test_framework_words_go_through_the_table.py``
interdit : elle est invisible en revue et ne se voit qu'à l'écran, dans
une langue qu'on ne parle pas.
"""

from __future__ import annotations

from collections.abc import Mapping
from string import Formatter
from typing import Any

__all__ = [
    "DEFAULT_TEXTS", "TextsError", "plural", "resolve_texts", "template", "text",
]


#: Les valeurs anglaises. La clé est ``<composant>.<rôle>`` — le préfixe
#: n'est pas décoratif : « Clear », « Clear date », « Clear time » et
#: « Clear range » sont QUATRE phrases distinctes, et les fusionner
#: donnerait un bouton qui ment dans la moitié des cas.
DEFAULT_TEXTS: Mapping[str, str] = {
    # ── Champs de saisie ─────────────────────────────────────────────
    "input.clear": "Clear",
    "combobox.clear": "Clear",
    "select.clear": "Clear",
    "combobox.empty": "No results",
    "slider.range_start": "Range start",
    "slider.range_end": "Range end",
    # ── Dates et heures ──────────────────────────────────────────────
    # Les NOMS de mois et de jours ne sont pas ici : ils se dérivent de
    # ``lang`` via ``Intl`` dans le navigateur. Seuls les mots que nous
    # avons écrits nous-mêmes ont une clé.
    "calendar.month": "Month",
    "calendar.year": "Year",
    # Le nom accessible d'une case MARQUÉE. ``{day}`` est le numéro du
    # jour, ``{n}`` le compte passé à ``marks=``. Une phrase entière : la
    # virgule et l'ordre changent d'une langue à l'autre.
    "calendar.marked": "{day}, {n} events",
    "calendar.previous_month": "Previous month",
    "calendar.next_month": "Next month",
    "calendar.previous_year": "Previous year",
    "calendar.next_year": "Next year",
    "month_picker.clear": "Clear month",
    "month_picker.open": "Open month picker",
    "week_picker.clear": "Clear week",
    "week_picker.open": "Open week picker",
    "signature_pad.placeholder": "Sign here",
    "signature_pad.clear": "Clear",
    "date_picker.clear": "Clear date",
    "date_picker.open": "Open date picker",
    "date_range_picker.clear": "Clear range",
    "date_range_picker.open": "Open date range picker",
    "color_picker.clear": "Clear color",
    "color_picker.open": "Open color palette",
    "time_picker.clear": "Clear time",
    "time_picker.open": "Open time picker",
    # ── Dépôt de fichiers ────────────────────────────────────────────
    # Les trois aides sous la zone de dépôt. ``{types}`` est la liste
    # d'extensions acceptées, ``{size}`` le plafond déjà formaté avec son
    # unité, ``{max}`` le nombre maximum de fichiers.
    "file_upload.accepted": "Accepted: {types}",
    "file_upload.max_size": "Max size: {size}",
    "file_upload.multiple": "Multiple files allowed",
    "file_upload.multiple_capped": "Multiple files allowed (up to {max})",
    "file_upload.remove": "Remove file",
    "file_upload.dropzone": "Drop files here or click to browse",
    "file_upload.button": "Upload file",
    "file_upload.drop_more": "Drop more files here",
    "file_upload.drop_replace": "Drop a different file to replace",
    # ── Tableau de données ───────────────────────────────────────────
    "datatable.clear_filters": "Clear filters",
    "datatable.filter_placeholder": "Filter values…",
    # Quatre phrases ENTIÈRES plutôt qu'un mot recollé à un nombre : une
    # traduction déplace l'ordre des morceaux, et «  of  » n'est pas une
    # brique réutilisable. ``{n}`` = ce qui est affiché, ``{total}`` = ce
    # qui existe avant filtrage.
    "datatable.results_one": "{n} result",
    "datatable.results_other": "{n} results",
    "datatable.results_narrowed_one": "{n} result of {total}",
    "datatable.results_narrowed_other": "{n} results of {total}",
    # ── Retours et surimpressions ────────────────────────────────────
    "alert.dismiss": "Dismiss alert",
    "badge.remove": "Remove",
    "banner.dismiss": "Dismiss",
    "modal.close": "Close",
    # ── Contrôles composés ───────────────────────────────────────────
    # Ces huit-là ne s'écrivaient pas ``aria_label=`` mais
    # ``attrs={"aria-label": …}``, une forme qu'aucun ``grep`` ne trouve
    # quand on cherche l'autre — d'où la gate qui lit l'AST plutôt que le
    # texte. La huitième était même écrite en FRANÇAIS dans le framework,
    # seule de tout le dépôt.
    "picker.remove": "Remove",
    "picker.select_all": "Select all",
    "picker.clear": "Clear",
    "carousel.choose_slide": "Choose slide",
    "carousel.go_to_slide": "Go to slide {n}",
    "carousel.previous": "Previous slide",
    "carousel.next": "Next slide",
    "show_more.label": "Show more",
    "resizable.resize_panel": "Resize panel {n}",
    "draggable.reorder": "Drag to reorder",
    "file_upload.complete": "Upload complete",
    "file_upload.error": "Upload error",
    "number_input.increment": "Increment",
    "number_input.decrement": "Decrement",
    "sidebar.rail_toggle": "Collapse or expand the sidebar",
    # Le nom accessible du logo quand la barre est repliée : il ne lui
    # reste que son glyphe, donc il s'annoncerait « lien » tout court.
    # Écrit en FRANÇAIS dans le framework jusqu'au 2026-08-24 — la
    # deuxième de deux, et la première avait été déclarée « seule de
    # tout le dépôt » faute d'un détecteur qui voyait cette forme-là.
    "sidebar.home": "Home",
    # ── Graphiques ───────────────────────────────────────────────────
    # Le nom du graphique part dans l'``aria-label`` de son ``<svg>``
    # quand il est vide — c'est ce qu'un lecteur d'écran annonce.
    "chart.bar": "Bar chart",
    "chart.line": "Line chart",
    "chart.pie": "Pie chart",
    "chart.donut": "Donut chart",
    "chart.scatter": "Scatter plot",
    "chart.scatter_date_axis": "Scatter plot (date axis)",
    "chart.empty": "No data",
    "chart.series": "Series",
    # Le résumé que lit un lecteur d'écran sur le ``<svg>``. Des phrases
    # ENTIÈRES : « Bar chart — 12 categories across Nord, Sud » ne se
    # traduit pas en recollant « across » à deux fragments. ``{kind}``
    # est le nom du graphique, déjà traduit par sa propre clé.
    "chart.summary": "{kind} — {what}",
    "chart.summary_across": "{kind} — {what} across {names}",
    "chart.categories": "{n} categories",
    "chart.points": "{n} points",
    "chart.slices": "{n} slices",
    "chart.series_count": "{n} series",
    "chart.sparkline": "Sparkline",
    "chart.sparkline_empty": "Sparkline — no data",
    "chart.sparkline_summary": "Sparkline — {n} points, min {low}, max {high}",
    # ``fmt="currency"`` codait le dollar EN DUR, et sa docstring
    # l'assumait (« USD-only v1 »). Un CRM français y lisait ses montants
    # en ``$1,234.50``. ``{value}`` arrive déjà groupé — la SÉPARATION
    # des milliers, elle, reste anglaise : ce serait un axe de formatage
    # de nombres, pas un mot du framework.
    "chart.currency": "${value}",
    # ── Navigation ───────────────────────────────────────────────────
    "pagination.previous": "Previous page",
    "pagination.next": "Next page",
    "sidebar.toggle": "Toggle sidebar",
}


class TextsError(ValueError):
    """Raised when a ``texts=`` key does not match a known framework phrase."""


def resolve_texts(overrides: Mapping[str, str] | None) -> Mapping[str, str]:
    """Merge application text overrides into the built-in English values."""
    if not overrides:
        return DEFAULT_TEXTS
    unknown = sorted(set(overrides) - set(DEFAULT_TEXTS))
    if unknown:
        raise TextsError(
            f"texts= a {len(unknown)} clé(s) inconnue(s) : "
            f"{', '.join(repr(k) for k in unknown)}. "
            f"Les clés valides sont listées dans "
            f"bretzel.render.texts.DEFAULT_TEXTS."
        )
    # Et les TROUS, pas seulement les clés. Une surcharge qui renomme
    # ``{size}`` en ``{taille}`` démarre sans un mot et lève un
    # ``KeyError`` nu sur la page qui l'affiche — soit exactement la
    # panne que la validation ci-dessus existe pour empêcher, une case
    # plus loin.
    for key, template in overrides.items():
        expected = _holes(DEFAULT_TEXTS[key])
        got = _holes(template)
        if got != expected:
            raise TextsError(
                f"texts[{key!r}] n'a pas les mêmes trous que le modèle : "
                f"attendu {sorted(expected) or 'aucun'}, reçu "
                f"{sorted(got) or 'aucun'}. Modèle de référence : "
                f"{DEFAULT_TEXTS[key]!r}."
            )
    return {**DEFAULT_TEXTS, **overrides}


def _holes(template: str) -> set[str]:
    """Les noms de champ d'un modèle — ``"{n} sur {total}"`` → ``{n, total}``."""
    return {
        field for _, field, _, _ in Formatter().parse(template) if field
    }


def text(key: str, /, **fmt: Any) -> str:
    """Return a framework phrase for ``key`` in the application's language."""
    from bretzel.render.context import maybe_current_context

    ctx = maybe_current_context()
    table = getattr(ctx, "texts", None) or DEFAULT_TEXTS
    try:
        template = table[key]
    except KeyError:
        raise TextsError(
            f"{key!r} n'est pas une clé de texte du framework. "
            f"Ajoute-la à bretzel.render.texts.DEFAULT_TEXTS."
        ) from None
    try:
        return template.format(**fmt)
    except (KeyError, IndexError) as exc:
        raise TextsError(
            f"le texte {key!r} attend un trou que l'appelant n'a pas "
            f"fourni ({exc}). Modèle : {template!r}."
        ) from None


def template(key: str, /) -> str:
    """Return the raw framework text template before interpolation."""
    from bretzel.render.context import maybe_current_context

    ctx = maybe_current_context()
    table = getattr(ctx, "texts", None) or DEFAULT_TEXTS
    try:
        return table[key]
    except KeyError:
        raise TextsError(
            f"{key!r} n'est pas une clé de texte du framework."
        ) from None


def plural(key: str, n: int, /, **fmt: Any) -> str:
    """Return the ``…_one`` or ``…_other`` variant of ``key`` for ``n``."""
    return text(f"{key}_one" if n == 1 else f"{key}_other", n=n, **fmt)
