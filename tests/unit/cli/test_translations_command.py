"""``bretzel translations`` — ce qu'une langue n'a pas encore, et ce que plus rien ne dit.

Le pendant de l'extraction de gettext : la commande lit le code de l'app
pour chaque ``t("…")`` et confronte chaque table.
"""

from __future__ import annotations

from types import SimpleNamespace

from bretzel.cli.commands.translations import calls, report
from bretzel.render.translations import TranslationTables


def app_with(fr: dict) -> SimpleNamespace:
    tables = TranslationTables({"fr": fr}, languages=("en", "fr"), default="en")
    return SimpleNamespace(config=SimpleNamespace(lang="en", languages=("en", "fr"),
                                                  translation_tables=tables))


def write_app(root) -> None:
    (root / "features").mkdir()
    (root / "features" / "board.py").write_text(
        'from bretzel import t, ui\n\n'
        'def board(n):\n'
        '    ui.button(t("Create"))\n'
        '    ui.text(t("{n} task", n=n, plural="{n} tasks"))\n'
        '    ui.text(t("Delete"))\n', encoding="utf-8")
    # A ``t`` that is not bretzel's: not read.
    (root / "features" / "other.py").write_text(
        'def t(x):\n    return x\n\nt("Not a sentence")\n', encoding="utf-8")
    (root / "tests").mkdir()
    (root / "tests" / "test_board.py").write_text(
        'from bretzel import t\nt("Only in a test")\n', encoding="utf-8")


def test_the_calls_are_read_where_t_is_bretzel_s(tmp_path) -> None:
    write_app(tmp_path)
    found = calls(tmp_path)
    assert [(c["sentence"], c["plural"], c["line"]) for c in found] == [
        ("Create", None, 4), ("{n} task", "{n} tasks", 5), ("Delete", None, 6)]
    assert {c["file"] for c in found} == {"features/board.py"}


def test_a_language_s_missing_and_unused_sentences(tmp_path) -> None:
    write_app(tmp_path)
    found = report(app_with({"Create": "Créer", "{n} task": {"one": "{n} tâche",
                                                             "other": "{n} tâches"},
                             "Old": "Ancien"}), tmp_path)
    fr = found["languages"]["fr"]
    assert [c["sentence"] for c in fr["missing"]] == ["Delete"]
    assert fr["unused"] == ["Old"]
    # The default language is the code's own: nothing to translate into.
    assert list(found["languages"]) == ["fr"]
