"""La langue de l'app et les mots du framework — le versant Python.

Pourquoi ces tests existent
----------------------------
Le mécanisme livré le 2026-08-24 (``Bretzel(lang=…, texts=…)``) n'était
couvert QUE par ``tests/probes/probe_locale.py``, qui vit derrière
``-m probes`` — un marqueur que personne ne lance par réflexe, et dont ce
dépôt a mesuré qu'il pourrit en silence (17 rouges sur 52 accumulés sans
que rien ne le dise). Or trois des quatre promesses du mécanisme sont du
Python pur et n'ont aucun besoin d'un navigateur :

- une clé inconnue LÈVE au démarrage — c'est ce qui rend une faute de
  frappe visible, et c'est cité quatre fois dans la doc comme la raison
  d'être de la validation ;
- une surcharge qui renomme un trou lève AUSSI, sinon la panne se
  déplace d'une case et sort en ``KeyError`` nu sur la page ;
- ``text()`` lit la table de la REQUÊTE, pas la table anglaise.

Le navigateur reste indispensable pour la quatrième — que ``Intl`` nomme
les mois — et c'est le probe qui la tient.
"""

from __future__ import annotations

import pytest

from bretzel.render.context import RenderContext, use_context
from bretzel.render.lang import LanguageTables, negotiate_language
from bretzel.render.texts import (
    DEFAULT_TEXTS,
    TextsError,
    plural,
    resolve_texts,
    text,
)


def in_context(**fields):
    """Un contexte de rendu minimal — deux sites le construisent en prod."""
    return use_context(RenderContext(app=None, request=None, **fields))


# ── La table elle-même ────────────────────────────────────────────────

def test_every_default_is_a_non_empty_string() -> None:
    empty = sorted(k for k, v in DEFAULT_TEXTS.items() if not isinstance(v, str) or not v.strip())
    assert not empty, f"des valeurs vides ou non-textuelles : {empty}"


def test_a_key_is_namespaced_by_its_component() -> None:
    """``<composant>.<rôle>`` — sans quoi « Clear » et « Clear date »
    finiraient par se confondre, et un bouton mentirait la moitié du
    temps."""
    flat = sorted(k for k in DEFAULT_TEXTS if "." not in k)
    assert not flat, f"des clés sans préfixe de composant : {flat}"


# ── resolve_texts : ce qui lève AU DÉMARRAGE ──────────────────────────

def test_no_override_returns_the_defaults_untouched() -> None:
    assert resolve_texts(None) is DEFAULT_TEXTS
    assert resolve_texts({}) is DEFAULT_TEXTS


def test_an_override_wins_and_the_rest_survives() -> None:
    merged = resolve_texts({"alert.dismiss": "Fermer"})
    assert merged["alert.dismiss"] == "Fermer"
    assert merged["badge.remove"] == DEFAULT_TEXTS["badge.remove"]
    assert len(merged) == len(DEFAULT_TEXTS)


def test_an_unknown_key_raises_rather_than_being_ignored() -> None:
    with pytest.raises(TextsError, match="unknown"):
        resolve_texts({"alert.dismis": "Fermer"})


def test_the_error_names_the_offending_key() -> None:
    with pytest.raises(TextsError) as caught:
        resolve_texts({"nope.nope": "x"})
    assert "nope.nope" in str(caught.value)


def test_a_renamed_hole_raises_too() -> None:
    """Le cran d'après : la clé existe, mais le trou a changé de nom.

    Sans ça, l'app démarre et c'est la PAGE qui lève, en ``KeyError``
    nu — la panne exacte que la validation des clés existe pour éviter.
    """
    with pytest.raises(TextsError, match="holes"):
        resolve_texts({"file_upload.max_size": "Taille max : {taille}"})


def test_a_dropped_hole_raises() -> None:
    with pytest.raises(TextsError, match="holes"):
        resolve_texts({"datatable.results_one": "un résultat"})


def test_an_override_that_keeps_its_holes_passes() -> None:
    merged = resolve_texts({"file_upload.max_size": "Taille maximale : {size}"})
    assert merged["file_upload.max_size"] == "Taille maximale : {size}"


# ── text() : ce qui se lit AU RENDU ───────────────────────────────────

def test_text_falls_back_to_english_outside_a_render() -> None:
    """Un composant construit hors requête reste utilisable — c'est le
    cas de toute la suite unitaire."""
    assert text("alert.dismiss") == "Dismiss alert"


def test_text_reads_the_table_of_the_current_request() -> None:
    table = resolve_texts({"alert.dismiss": "Fermer l'alerte"})
    with in_context(texts=table):
        assert text("alert.dismiss") == "Fermer l'alerte"
    # Et le contexte suivant ne garde rien du précédent.
    assert text("alert.dismiss") == "Dismiss alert"


def test_text_fills_its_holes() -> None:
    assert text("file_upload.max_size", size="8 MB") == "Max size: 8 MB"


def test_a_missing_hole_raises_rather_than_printing_a_brace() -> None:
    with pytest.raises(TextsError, match="hole"):
        text("carousel.go_to_slide")


def test_an_unknown_key_raises_at_render_too() -> None:
    with pytest.raises(TextsError):
        text("nope.nope")


# ── plural : une forme, l'autre ───────────────────────────────────────

def test_plural_picks_the_singular_at_one() -> None:
    assert plural("datatable.results", 1) == "1 result"


@pytest.mark.parametrize("count", [0, 2, 50_000])
def test_plural_picks_the_other_form_everywhere_else(count: int) -> None:
    assert plural("datatable.results", count) == f"{count} results"


def test_plural_passes_the_extra_holes_through() -> None:
    assert plural("datatable.results_narrowed", 34, total=100) == "34 results of 100"


def test_plural_follows_the_request_table() -> None:
    table = resolve_texts({
        "datatable.results_one": "{n} résultat",
        "datatable.results_other": "{n} résultats",
    })
    with in_context(texts=table):
        assert plural("datatable.results", 1) == "1 résultat"
        assert plural("datatable.results", 7) == "7 résultats"


# ── La langue voyage jusqu'au contexte ────────────────────────────────

def test_the_context_defaults_to_english() -> None:
    ctx = RenderContext(app=None, request=None)
    assert ctx.lang == "en"
    assert ctx.texts is DEFAULT_TEXTS


# ───────────────────────────────────────────────────────────────────────────
# L'axe de langue — négociation et tables par langue
# ───────────────────────────────────────────────────────────────────────────


class TestNegotiate:
    """``Accept-Language`` → la langue servie.

    Chaque cas est une chose que le navigateur dit vraiment ; c'est la
    raison pour laquelle ils sont énumérés plutôt que résumés.
    """

    def _n(self, header, available=("en", "fr"), default="en"):
        return negotiate_language(header, available, default=default)

    def test_regional_tag_falls_back_to_its_primary(self) -> None:
        """``fr-CA`` doit être servi par une app qui déclare ``fr``.

        Sans ce dégroupage, un navigateur canadien — ou n'importe quel
        ``en-US``, qui est le réglage par défaut de Chrome aux
        États-Unis — ne matcherait jamais.
        """
        assert self._n("fr-CA,fr;q=0.9,en;q=0.8") == "fr"

    def test_exact_tag_wins_over_the_primary(self) -> None:
        assert self._n("fr-CA", available=("en", "fr", "fr-CA")) == "fr-CA"

    def test_quality_orders_the_preferences(self) -> None:
        assert self._n("fr;q=0.2,en;q=0.9") == "en"
        assert self._n("fr;q=0.9,en;q=0.2") == "fr"

    def test_equal_quality_keeps_the_written_order(self) -> None:
        """C'est ce que le navigateur veut dire quand il n'arbitre pas."""
        assert self._n("fr,en") == "fr"
        assert self._n("en,fr") == "en"

    def test_zero_quality_is_a_refusal(self) -> None:
        """``q=0`` n'est pas « peu importe », c'est « pas celle-là »."""
        assert self._n("fr;q=0,en") == "en"

    def test_unknown_languages_fall_back(self) -> None:
        assert self._n("de,es;q=0.7") == "en"

    def test_wildcard_takes_the_default(self) -> None:
        assert self._n("*") == "en"

    def test_absent_or_malformed_never_raises(self) -> None:
        """Un en-tête est du bruit venu du réseau, pas une entrée d'app."""
        assert self._n(None) == "en"
        assert self._n("") == "en"
        assert self._n("poubelle;;;,,,") == "en"
        assert self._n("fr;q=abc") == "en"

    def test_no_declared_languages_means_monolingual(self) -> None:
        assert self._n("fr", available=()) == "en"

    def test_case_is_ignored(self) -> None:
        assert self._n("FR-ca", available=("en", "fr-CA")) == "fr-CA"


class TestTablesByLanguage:
    def _tables(self, overrides, languages=("en", "fr"), default="en"):
        return LanguageTables(overrides, languages=languages, default=default)

    def _resolve(self, overrides, languages=("en", "fr")):
        tables = self._tables(overrides, languages)
        return {code: tables.for_language(code) for code in tables.languages()}

    def test_flat_form_overrides_the_default_language(self) -> None:
        """La forme d'avant l'axe de langue marche à l'identique.

        Elle porte sur la langue par DÉFAUT, déclarée — pas sur « la
        première de la liste », qui était une convention positionnelle
        que le lecteur devait deviner.
        """
        tables = self._tables({"alert.dismiss": "Fermer"},
                              languages=("fr",), default="fr")
        assert tables.for_language("fr")["alert.dismiss"] == "Fermer"

    def test_nested_form_gives_one_table_per_language(self) -> None:
        tables = self._resolve({"fr": {"alert.dismiss": "Fermer"}})
        assert tables["fr"]["alert.dismiss"] == "Fermer"
        assert tables["en"]["alert.dismiss"] == DEFAULT_TEXTS["alert.dismiss"]

    def test_an_unknown_code_falls_back_instead_of_raising(self) -> None:
        """Le point de la classe : on l'INTERROGE, elle ne rate pas.

        La première version rangeait ``{code: table}`` dans la config et
        le middleware l'indexait — un ``KeyError`` sur CHAQUE requête le
        jour où l'invariant réparti sur trois fichiers aurait glissé.
        """
        tables = self._tables({"fr": {"alert.dismiss": "Fermer"}})
        assert tables.for_language("zz") is tables.for_language("en")

    def test_a_declared_but_untranslated_language_falls_back(self) -> None:
        """Une app peut servir ``de`` en anglais plutôt que refuser de
        démarrer — sinon ajouter une langue exigerait de tout traduire
        d'un coup."""
        tables = self._resolve({"fr": {"alert.dismiss": "Fermer"}},
                               languages=("en", "fr", "de"))
        assert tables["de"] == DEFAULT_TEXTS

    def test_mixing_the_two_forms_raises(self) -> None:
        """Un dict qui contient une phrase ET une table n'a pas de
        lecture juste : deviner rangerait la moitié des clés dans une
        langue nommée « alert.dismiss »."""
        with pytest.raises(TextsError, match="mixes"):
            self._resolve({"alert.dismiss": "Fermer", "fr": {"x": "y"}})

    def test_overriding_an_undeclared_language_raises(self) -> None:
        """Une table que rien ne peut sélectionner est du travail perdu."""
        with pytest.raises(TextsError, match="undeclared"):
            self._resolve({"de": {"alert.dismiss": "Schliessen"}})
