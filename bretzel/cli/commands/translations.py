"""``bretzel translations`` — the sentences a language still lacks.

gettext extracts the sentences marked ``_()`` into a ``.po`` per language;
here the tables are a dict given to ``Bretzel(translations=…)``, and this
command does the extraction's job: it reads the app's code for every
``t("…")`` and says, language by language, which sentences its table
lacks — where they are called — and which entries no call uses any more.

A call counts when its first argument is written out (``t("Create")``):
the sentence IS the key, a computed one cannot be looked for. A module
counts when it imports ``t`` from ``bretzel``, so a local ``t`` of
another meaning is not read. The app is imported (``module:attribute``)
for its languages and its tables; it is not started.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path

_SKIPPED = {"tests", "__pycache__", "node_modules", "build", "dist"}


def _imports_t(tree: ast.Module) -> bool:
    return any(isinstance(node, ast.ImportFrom) and node.module == "bretzel"
               and any(alias.name == "t" for alias in node.names)
               for node in ast.walk(tree))


def calls(root: Path) -> list[dict]:
    """Every ``t("…")`` of the app's modules: the sentence, its plural, where."""
    found = []
    for path in sorted(root.rglob("*.py")):
        if any(part in _SKIPPED or part.startswith(".") for part in path.relative_to(root).parts):
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError):
            continue
        if not _imports_t(tree):
            continue
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                    and node.func.id == "t" and node.args
                    and isinstance(node.args[0], ast.Constant)
                    and isinstance(node.args[0].value, str)):
                continue
            plural = next((k.value.value for k in node.keywords if k.arg == "plural"
                           and isinstance(k.value, ast.Constant)), None)
            found.append({"sentence": node.args[0].value, "plural": plural,
                          "file": path.relative_to(root).as_posix(), "line": node.lineno})
    return found


def report(app, root: Path) -> dict:
    """Per language: the sentences its table lacks, the entries nobody calls."""
    config = app.config
    tables = config.translation_tables
    said = calls(root)
    sentences = {c["sentence"] for c in said}
    # The languages to translate into: every declared one but the default,
    # whose sentences are written in the code — unless it has a table too.
    wanted = [code for code in dict.fromkeys([config.lang, *config.languages])
              if code != config.lang or code in tables.languages()]
    languages = {}
    for code in wanted:
        table = tables.for_language(code)
        languages[code] = {
            "missing": [c for c in said if c["sentence"] not in table],
            "unused": sorted(set(table) - sentences),
        }
    return {"sentences": len(sentences), "calls": len(said),
            "files": len({c["file"] for c in said}), "languages": languages}


def run_translations(target: str, *, as_json: bool = False) -> int:
    from bretzel.introspect._target import load_target

    app, origin = load_target(target)
    root = origin.resolve().parent
    found = report(app, root)
    if as_json:
        print(json.dumps(found, ensure_ascii=False, indent=2))
        return 0
    print(f"{target} — {found['sentences']} sentences in t(), {found['calls']} calls "
          f"in {found['files']} files")
    if not found["languages"]:
        print("No language to translate into: languages= declares none but the default.")
    for code, rows in found["languages"].items():
        missing, unused = rows["missing"], rows["unused"]
        if not missing and not unused:
            print(f"\n{code}: every sentence is translated.")
            continue
        if missing:
            print(f"\n{code}: {len(missing)} missing")
            for call in missing:
                print(f"  - {call['sentence']!r}  {call['file']}:{call['line']}")
        if unused:
            print(f"\n{code}: {len(unused)} unused — no t() says them any more")
            for sentence in unused:
                print(f"  - {sentence!r}")
    return 0
