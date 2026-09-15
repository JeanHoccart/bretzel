"""Assembler les sources ``_src/[0-9]*_*.js`` dans l'ordre de leur nom.

``python -m bretzel.runtime._build`` produit ``runtime.js`` et
``runtime.min.js``. L'option ``--check`` vérifie que les deux fichiers
commités correspondent aux sources, sans les réécrire.

Chaque source garde son IIFE. Les substitutions déclarées dans ``_TOKENS``
reprennent les constantes de :mod:`bretzel.runtime.protocol` ; la réduction
est fournie par :mod:`bretzel.runtime._minify`.

Le serveur sert le bundle lisible en mode dev et sa réduction en prod.
La fraîcheur des bundles est testée ; aucun budget de taille n'est imposé.
Voir ``.claude/bretzel/runtime.md`` pour le contrat du runtime.
"""

from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent          # bretzel/runtime
SRC = HERE / "_src"
PROJECT = HERE.parent.parent                    # repo root
sys.path.insert(0, str(PROJECT))

from bretzel.runtime._minify import minify  # noqa: E402
from bretzel.runtime.protocol import (  # noqa: E402
    ENVELOPE_TAG_NAME,
    NAV_PENDING_KEY,
    PATCH_TAG_NAME,
    PROTOCOL_VERSION,
    ROUTE_ACTION,
    SCREEN_SYNC_FN,
)

_TOKENS = {
    "__PROTOCOL_VERSION__": PROTOCOL_VERSION,
    "__ENVELOPE_TAG__": ENVELOPE_TAG_NAME,
    "__PATCH_TAG__": PATCH_TAG_NAME,
    "__SCREEN_SYNC_FN__": SCREEN_SYNC_FN,
    "__ROUTE_ACTION__": ROUTE_ACTION,
    "__NAV_PENDING_KEY__": NAV_PENDING_KEY,
}


def _bundle() -> str:
    parts = [
        source.read_text(encoding="utf-8")
        for source in sorted(SRC.glob("[0-9]*_*.js"))
    ]
    bundle = "\n\n".join(parts)
    for token, value in _TOKENS.items():
        bundle = bundle.replace(token, value)
    return bundle


#: Le bundle lisible (servi en dev) et sa réduction (servie en prod).
#: Les deux sont committés : un paquet installé ne rejoue pas le build.
READABLE = HERE / "runtime.js"
MINIFIED = HERE / "runtime.min.js"


def build() -> Path:
    bundle = _bundle()
    READABLE.write_text(bundle, encoding="utf-8", newline="\n")
    small = minify(bundle)
    MINIFIED.write_text(small, encoding="utf-8", newline="\n")
    count = len(list(SRC.glob("[0-9]*_*.js")))
    print(
        f"Built {READABLE} - {len(bundle):,} chars from {count} modules "
        f"(+ {MINIFIED.name}, {len(small):,} chars)."
    )
    return READABLE


def check() -> int:
    """CI helper : non-zero when either bundle is stale vs ``_src/``.

    Les DEUX sont vérifiés. Un ``runtime.min.js`` périmé ne se voit pas
    en dev — qui sert l'autre fichier — et ne casserait qu'en
    production, c'est-à-dire à l'endroit où on le découvre le plus mal.
    """
    bundle = _bundle()
    for target, expected in ((READABLE, bundle), (MINIFIED, minify(bundle))):
        if not target.exists():
            print(
                f"[bretzel] {target.name} missing - run "
                "python -m bretzel.runtime._build"
            )
            return 1
        if target.read_text(encoding="utf-8") != expected:
            print(
                f"[bretzel] {target.name} is stale - run "
                "python -m bretzel.runtime._build and commit the result."
            )
            return 1
    return 0


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--check":
        sys.exit(check())
    build()
