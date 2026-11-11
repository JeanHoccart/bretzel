"""Unit tests for the runtime.js build pipeline (V3).

The full JS-side functional tests live under ``tests/runtime_js/``
(Playwright). At the unit level we just want to ensure :

- The 7 source modules concatenate deterministically.
- The output is in sync with the on-disk ``runtime.js`` (CI gate).
- The ``__PROTOCOL_VERSION__`` token is substituted at concat time.
- The bundle parses as valid JavaScript (delegated to ``node --check``
  when available — skipped otherwise).
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from bretzel.runtime.protocol import PROTOCOL_VERSION

RUNTIME_DIR = Path(__file__).resolve().parent.parent.parent.parent / "bretzel" / "runtime"
SRC_DIR = RUNTIME_DIR / "_src"
RUNTIME_JS = RUNTIME_DIR / "runtime.js"
# V3 : the build script lives at the package root (``python -m
# bretzel.runtime._build``), no longer inside ``_src/``.
BUILD_SCRIPT = RUNTIME_DIR / "_build.py"

# Spec ``spec/V3/03-runtime.md`` § *Internal directory structure* — the
# ``0N_`` prefix guarantees topological concat order (signals before
# directives before scope, …).
EXPECTED_MODULES = [
    "index.js",
    "signals.js",
    "directives.js",
    "scope.js",
    "persistence.js",
    "bridge.js",
    "helpers.js",
    # Stateful-widget slabs load after the core 7 (they use window.$bz
    # which 00-06 set up). ``<bz-calendar>`` custom element + the
    # ``$bz.fileUpload`` scope factory.
    "locale.js",
    "calendar.js",
    "file_upload.js",
    "notification.js",
    "charts.js",
    # ``$bz.numberInput.scope`` factory — the heavy NumberInput client
    # logic, shared once instead of inlined per instance.
    "number_input.js",
    # ``$bz.slider.scope`` factory — drag/keyboard/clamp logic shared.
    "slider.js",
    # ``$bz.select.single`` / ``.multi`` factory scopes.
    "select.js",
    # ``$bz.combobox.common`` / ``.single`` / ``.multi`` factory scopes.
    "combobox.js",
    # Le scope de Pagination. L'algorithme ``range()`` était sérialisé dans
    # le ``bz-data`` de chaque instance — 957 octets, le plus gros du dépôt,
    # avec la config cuite dans les corps de méthode. Migré le 2026-07-29 :
    # 957 → 142 octets par instance.
    "pagination.js",
    # Les scopes d'Accordion (622 o/instance) et de Tree (293 o), migrés le
    # 2026-07-29. Accordion cuisait sa config dans les corps de méthode
    # (``if (true)`` pour collapsible) — d'où deux CODES pour deux configs.
    "accordion.js",
    # Le scope du Carousel. Il tient dans un fichier à lui — contrairement
    # aux quatre scopes que ``16_`` héberge, il ne se contente pas d'un
    # setter gardé : il LIT la géométrie du DOM (foulée entre deux slides,
    # borne de défilement) pour que le ``per_view`` responsive ne coûte
    # aucun calcul de breakpoint.
    "carousel.js",
    # Le scope du TimePicker. Un fichier à lui plutôt qu'une entrée dans
    # ``16_`` : ses méthodes portent une vraie découpe (``_parts`` tolère
    # ce que le champ texte accepte avant normalisation), pas un simple
    # setter gardé.
    "time_picker.js",
    # Le moteur de geste node-DnD (`dropzone` / `draggable`). Le seul module
    # de la liste qui n'est PAS une fabrique de scope : il n'expose rien à
    # un `bz-data` et se branche par délégation au document, parce qu'un
    # listener par zone devrait se rebrancher à chaque morph. Il lit un
    # contrat de `data-*` attributes ; `$bz.dnd` n'expose que ses constantes
    # d'activation et des lecteurs, pour les tests.
    "dnd.js",
    # Le scope du Resizable (split panes). Un fichier à lui, et surtout PAS
    # une extension de ``19_`` : le node-DnD déplace un nœud, celui-ci ne
    # déplace rien — deux voisins se repartagent la place qu'ils occupent
    # déjà. C'est la famille du Slider (pointeur → dimension), dont il
    # reprend la capture de pointeur sans en partager le code : le slider
    # projette sur UNE échelle bornée, ici on redistribue une somme
    # invariante entre deux panneaux.
    "resizable.js",
    # Le scope du SignaturePad. Le PREMIER et le seul <canvas> du depot
    # (les charts sont en SVG), d'ou un fichier a lui : un canvas n'a
    # aucune taille intrinseque et se VIDE quand on le redimensionne,
    # deux proprietes qu'aucun autre module n'a a gerer.
    "signature_pad.js",
        "verbs.js",
        "diagram.js",
        "scheduler.js",
        "tip.js",
        "message_input.js",
        "message_list.js",
    # Les noms de mois et de jours, derives de ``<html lang>`` par
    # ``Intl``. Le seul module qui n'expose ni scope ni element : une
    # table de consultation, appelee par ``calendar.js`` ET par des
    # expressions ``bz-text`` du calendrier rendu cote serveur. Il vit
    # ici plutot que cote Python parce que Python n'a aucun moyen sur de
    # nommer un mois : le module ``locale`` est un etat global au
    # processus, et Babel serait une dependance.
]


# ───────────────────────────────────────────────────────────────────────────
# Source layout
# ───────────────────────────────────────────────────────────────────────────


class TestSourceLayout:
    def test_src_dir_exists(self) -> None:
        assert SRC_DIR.is_dir()

    def test_declared_modules_layout(self) -> None:
        from bretzel.runtime.sources import SOURCES

        assert [m.name for m in SOURCES] == EXPECTED_MODULES

    def test_build_script_present(self) -> None:
        assert BUILD_SCRIPT.is_file()


# ───────────────────────────────────────────────────────────────────────────
# Build determinism + sync
# ───────────────────────────────────────────────────────────────────────────


class TestBuildOutput:
    def test_runtime_js_exists(self) -> None:
        assert RUNTIME_JS.is_file()

    def test_runtime_js_in_sync(self) -> None:
        # Run the build script in --check mode ; non-zero exit means
        # the on-disk artifact diverges from the sources.
        proc = subprocess.run(
            [sys.executable, str(BUILD_SCRIPT), "--check"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert proc.returncode == 0, (
            f"runtime.js is stale — re-run python -m bretzel.runtime._build.\n"
            f"stdout: {proc.stdout}\nstderr: {proc.stderr}"
        )

    def test_protocol_version_substituted(self) -> None:
        # The literal placeholder must NOT survive into the bundle.
        bundle = RUNTIME_JS.read_text(encoding="utf-8")
        assert "__PROTOCOL_VERSION__" not in bundle
        # And the actual version string MUST appear (assigned to
        # ``$bz.version`` in index.js).
        assert f'$bz.version = "{PROTOCOL_VERSION}"' in bundle

    def test_bundle_concatenates_all_modules(self) -> None:
        bundle = RUNTIME_JS.read_text(encoding="utf-8")
        # Each source opens with a ``/* NN_name.js — …`` header comment
        # — verify all 7 show up in the concatenated output.
        for name in EXPECTED_MODULES:
            assert f"/* {name}" in bundle, f"missing module : {name}"


# ───────────────────────────────────────────────────────────────────────────
# Optional : node --check (skipped if node not installed)
# ───────────────────────────────────────────────────────────────────────────


class TestNodeSyntax:
    @pytest.mark.skipif(
        shutil.which("node") is None,
        reason="node not installed in test environment",
    )
    def test_runtime_js_parses(self) -> None:
        proc = subprocess.run(
            ["node", "--check", str(RUNTIME_JS)],
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert proc.returncode == 0, (
            f"node --check failed :\nstdout: {proc.stdout}\nstderr: {proc.stderr}"
        )
