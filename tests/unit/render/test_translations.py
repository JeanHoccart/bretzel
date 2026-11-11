"""Les mots de l'app dans chaque langue — ``t()``, le versant Python.

Jusqu'au 2026-10-28, le framework disait qu'il ne connaîtrait jamais les
mots d'une app : le kanban écrivait ``tr("Create", "Créer")``, toutes les
langues dans chaque appel. ``t("Create")`` prend la phrase écrite comme
clé (le choix de gettext), une table par langue, et le pluriel de la
langue.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from bretzel.render.context import RenderContext, use_context
from bretzel.render.translations import (
    TranslationsError,
    TranslationTables,
    split_translations,
    t,
)

TABLES = {"fr": {
    "Create": "Créer",
    "Hello {name}": "Bonjour {name}",
    "{n} task": {"one": "{n} tâche", "other": "{n} tâches"},
}}


def app_in(lang: str, raw=TABLES, languages=("en", "fr", "fr-CA", "de")):
    tables = TranslationTables(raw, languages=languages, default="en")
    app = SimpleNamespace(config=SimpleNamespace(translation_tables=tables))
    return use_context(RenderContext(app=app, request=None, lang=lang))


# ── Les tables, lues au démarrage ─────────────────────────────────────

def test_a_table_for_an_undeclared_language_raises() -> None:
    with pytest.raises(TranslationsError, match="does not declare"):
        TranslationTables({"it": {"Create": "Crea"}}, languages=("en", "fr"), default="en")


def test_a_renamed_hole_raises() -> None:
    with pytest.raises(TranslationsError, match="holes"):
        TranslationTables({"fr": {"Hello {name}": "Bonjour {nom}"}}, languages=("fr",),
                          default="en")


def test_a_counted_sentence_needs_its_other_form() -> None:
    with pytest.raises(TranslationsError, match="other"):
        TranslationTables({"fr": {"{n} task": {"one": "{n} tâche"}}}, languages=("fr",),
                          default="en")


def test_a_regional_language_takes_its_language_s_table() -> None:
    tables = TranslationTables(TABLES, languages=("fr",), default="en")
    assert tables.for_language("fr-CA")["Create"] == "Créer"
    assert tables.for_language("de") == {}


# ── t(), au rendu ─────────────────────────────────────────────────────

def test_outside_a_request_the_sentence_is_as_written() -> None:
    assert t("Hello {name}", name="Jean") == "Hello Jean"


def test_a_french_visitor_reads_french() -> None:
    with app_in("fr"):
        assert t("Create") == "Créer"
        assert t("Hello {name}", name="Jean") == "Bonjour Jean"
    with app_in("fr-CA"):
        assert t("Create") == "Créer"


def test_a_sentence_nobody_translated_shows_as_written() -> None:
    with app_in("fr"):
        assert t("Delete") == "Delete"
    with app_in("de"):
        assert t("Create") == "Create"


@pytest.mark.parametrize(("lang", "n", "said"), [
    ("fr", 0, "0 tâche"), ("fr", 1, "1 tâche"), ("fr", 2, "2 tâches"),
    ("en", 0, "0 tasks"), ("en", 1, "1 task"), ("en", 5, "5 tasks"),
])
def test_a_counted_sentence_takes_the_language_s_form(lang: str, n: int, said: str) -> None:
    with app_in(lang):
        assert t("{n} task", n=n, plural="{n} tasks") == said


def test_a_counted_sentence_must_be_given_n() -> None:
    with pytest.raises(TypeError, match="n="):
        t("{n} task", plural="{n} tasks")


def test_a_missing_hole_says_which() -> None:
    with app_in("fr"), pytest.raises(TypeError, match="name"):
        t("Hello {name}")


class TestOneTableForEveryWord:
    """Bretzel's sentences and the app's live in the same ``translations=``:
    whoever changes a word on screen does not have to know who wrote it."""

    def test_a_framework_name_replaces_bretzel_s_word(self) -> None:
        framework, own = split_translations({"fr": {
            "sidebar.toggle": "Ouvrir le menu", "Save": "Enregistrer"}})
        assert framework == {"fr": {"sidebar.toggle": "Ouvrir le menu"}}
        assert own == {"fr": {"Save": "Enregistrer"}}

    def test_a_counted_framework_form_is_a_framework_name(self) -> None:
        framework, _ = split_translations({"cs": {"datatable.results_few": "{n} výsledky"}})
        assert framework == {"cs": {"datatable.results_few": "{n} výsledky"}}

    def test_a_misspelt_framework_name_raises_with_the_closest(self) -> None:
        with pytest.raises(TranslationsError, match="did you mean 'sidebar.toggle'"):
            split_translations({"fr": {"sidebar.togle": "Ouvrir le menu"}})

    @pytest.mark.parametrize("sentence", [
        "Save", "v1.2", "e.g. a file", "{n} task", "Hello {name}", "file name"])
    def test_an_app_sentence_never_reads_as_a_framework_name(self, sentence: str) -> None:
        framework, own = split_translations({"fr": {sentence: "x"}})
        assert framework == {} and own == {"fr": {sentence: "x"}}

    def test_every_language_is_still_checked(self) -> None:
        """A table holding only Bretzel's words keeps its language on the
        app's side, so an undeclared one is still refused."""
        _, own = split_translations({"de": {"sidebar.toggle": "Menü"}})
        with pytest.raises(TranslationsError, match="does not declare"):
            TranslationTables(own, languages=("en",), default="en")
