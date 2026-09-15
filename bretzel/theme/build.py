"""Standalone Tailwind v4 binary downloader + compile orchestration.

Mirrors the strategy from v1's ``archive/V1/bretzel/build/tailwind.py`` but
targets the v4 binaries (which read ``@import "tailwindcss"`` +
``@theme {}`` directly from the input CSS — no separate
``tailwind.config.js`` needed).

Download → cache in ``.bretzel/bin/`` → invoke via
:func:`bretzel.theme.compiler.compile_with_lightning`. The download
runs once ; subsequent calls reuse the cached binary.

Used by :mod:`bretzel.server.lifecycle` when ``css="build"`` to produce
the compiled stylesheet. This setting is independent of ``debug`` and
``mode``. Downloading requires an explicit ``allow_download=True``;
normal application startup only looks for an installed binary or cache.
"""

from __future__ import annotations

import contextlib
import hashlib
import os
import platform
import re
import stat
import tempfile
import urllib.request
from collections.abc import Sequence
from pathlib import Path
from typing import Final

from bretzel.theme.compiler import (
    CompilerError,
    compile_with_lightning,
    find_lightning_binary,
)

# ───────────────────────────────────────────────────────────────────────────
# Tailwind v4 standalone binary — pinned, overridable via env
# ───────────────────────────────────────────────────────────────────────────

_DEFAULT_VERSION = "v4.3.2"   # >= 4.1 : `@source inline(...)` support (4.0.0 rejects it)
_VERSION = os.environ.get("BRETZEL_TAILWIND_VERSION", _DEFAULT_VERSION)
_BASE_URL = (
    f"https://github.com/tailwindlabs/tailwindcss/releases/download/{_VERSION}"
)

_BINARIES = {
    ("linux",   "x86_64"):  "tailwindcss-linux-x64",
    ("linux",   "aarch64"): "tailwindcss-linux-arm64",
    ("darwin",  "x86_64"):  "tailwindcss-macos-x64",
    ("darwin",  "arm64"):   "tailwindcss-macos-arm64",
    ("windows", "amd64"):   "tailwindcss-windows-x64.exe",
    ("windows", "arm64"):   "tailwindcss-windows-arm64.exe",
}


# ───────────────────────────────────────────────────────────────────────────
# Cache layout
# ───────────────────────────────────────────────────────────────────────────


def _cache_dir() -> Path:
    """Per-project cache root — ``./.bretzel/`` next to the cwd.

    Mirrors v1's layout so users moving over recognise the directory.
    """
    d = Path.cwd() / ".bretzel"
    d.mkdir(exist_ok=True)
    return d


def _binary_name() -> str:
    system = platform.system().lower()
    machine = platform.machine().lower()
    if system == "windows":
        arch = "arm64" if machine in ("arm64", "aarch64") else "amd64"
    elif system == "darwin":
        arch = "arm64" if machine in ("arm64", "aarch64") else "x86_64"
    else:
        system = "linux"
        arch = "aarch64" if machine in ("arm64", "aarch64") else "x86_64"
    name = _BINARIES.get((system, arch))
    if not name:
        raise CompilerError(
            f"No Tailwind v4 binary available for {system}/{machine}. "
            "Set BRETZEL_TAILWIND_BIN to a manually-installed path."
        )
    return name


def _binary_path() -> Path:
    return _cache_dir() / "bin" / _binary_name()


# ───────────────────────────────────────────────────────────────────────────
# Download
# ───────────────────────────────────────────────────────────────────────────


def download_binary() -> Path:
    """Download the Tailwind v4 standalone binary if absent.

    Returns the cached path. Subsequent calls are cheap : we just
    ``stat`` the file on disk.
    """
    path = _binary_path()
    if path.exists():
        return path

    path.parent.mkdir(parents=True, exist_ok=True)
    url = f"{_BASE_URL}/{_binary_name()}"
    print(f"[bretzel] Downloading Tailwind CLI {_VERSION} ...")

    def _progress(count: int, block_size: int, total_size: int) -> None:
        if total_size > 0:
            pct = int(count * block_size * 100 / total_size)
            print(f"\r[bretzel] {min(pct, 100)} %", end="", flush=True)

    urllib.request.urlretrieve(url, path, reporthook=_progress)
    print()

    if platform.system() != "Windows":
        path.chmod(path.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)

    print(f"[bretzel] Binary ready -> {path}")
    return path


# ───────────────────────────────────────────────────────────────────────────
# Compile
# ───────────────────────────────────────────────────────────────────────────


#: Ce que Tailwind lit en plus du CSS d'entrée : il balaie l'espace de
#: travail à la recherche de classes. Ces dossiers n'en portent pas, ou
#: pas de vivantes, et les inclure ferait de l'empreinte un coût inutile.
_SCAN_SKIP: frozenset[str] = frozenset({
    ".bretzel", ".git", ".venv", "venv", "__pycache__", "node_modules",
    ".mypy_cache", ".pytest_cache", ".ruff_cache", "build", "dist",
    "archive",          # le V1 est READ-ONLY par charte, il ne bouge pas
})

#: Les extensions où une classe peut vivre. Un `.py` en porte (les thèmes
#: de composants sont du Python), un `.html` aussi.
_SCAN_SUFFIXES: frozenset[str] = frozenset({".py", ".html", ".js", ".md"})


def _content_fingerprint(roots: Sequence[Path]) -> str:
    """Empreinte des fichiers que le compilateur BALAIE.

    Tailwind v4 ne compile pas seulement le CSS d'entrée : il lit
    l'espace de travail pour savoir quelles classes existent. Le compilé
    dépend donc de DEUX choses, et le cache doit refléter les deux.

    **Sans ça, un changement de classe ne parvient jamais en prod.** Le
    2026-08-27, remplacer ``transition-all`` par une liste explicite dans
    ``sidebar/theme.py`` n'a rien changé : la classe ne touche aucune
    couleur, donc elle n'entre pas dans la safelist, donc l'empreinte du
    CSS d'entrée ne bouge pas, donc le cache rendait l'ancien fichier. Le
    rendu restait celui d'avant, sans une seule erreur.

    Le piège était masqué jusque-là : le cache tenait une seule place et
    deux apps se la reprenaient sans cesse, donc il recompilait presque à
    chaque démarrage — frais par accident. Le réparer a découvert ceci.

    On lit ``(chemin, taille, mtime_ns)``, jamais le contenu : c'est un
    parcours de ``stat``, pas une lecture.

    ⚠️ **L'élagage se fait EN DESCENDANT, pas en filtrant après.** Une
    première version faisait ``root.rglob("*")`` puis écartait les
    chemins indésirables : elle descendait donc dans ``.git`` et
    ``archive/`` avant de les jeter. Mesuré sur ce dépôt : **1 462 ms**
    contre 60 ms avec l'élagage — pour une fonction qui tourne au
    démarrage de chaque app en mode prod.
    """
    parts: list[str] = []
    for root in roots:
        prefix = root.as_posix()
        for folder, subfolders, filenames in os.walk(root):
            subfolders[:] = [d for d in subfolders if d not in _SCAN_SKIP]
            base = Path(folder)
            for name in filenames:
                if os.path.splitext(name)[1] not in _SCAN_SUFFIXES:
                    continue
                path = base / name
                try:
                    st = path.stat()
                except OSError:
                    continue
                # Le chemin de la racine PRÉFIXE l'entrée : deux racines
                # peuvent porter le même chemin relatif (``theme/css.py``
                # existe dans le paquet ET dans un dossier d'app qui
                # l'imiterait), et deux entrées identiques s'annuleraient
                # dans le hash.
                parts.append(
                    f"{prefix}/{path.relative_to(root).as_posix()}"
                    f":{st.st_size}:{st.st_mtime_ns}"
                )
    parts.sort()
    return hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest()


#: Une racine déclarée dans le CSS de thème, telle que
#: :func:`bretzel.theme.tailwind.generate_source_directives` l'écrit.
_SOURCE_PATH_RE = re.compile(r'@source "([^"]+)";')


def scan_roots(theme_css: str) -> list[Path]:
    """Les dossiers que le compilateur va lire, pour CE CSS d'entrée.

    **Le CSS est la source de vérité, pas un paramètre.** Les racines y
    sont déjà écrites — c'est ce que le binaire lira. Les relire ici
    plutôt que de les faire redescendre par la pile garantit que
    l'empreinte couvre exactement ce qui est balayé : un appelant ne peut
    pas déclarer une racine au compilateur en oubliant de la déclarer au
    cache, ce qui rendrait un ``style.css`` périmé **sans erreur**.

    Le ``cwd`` ouvre la liste parce que Tailwind le balaie de lui-même,
    sans qu'aucune directive ne le dise.

    Une racine imbriquée dans une autre est écartée : la parcourir deux
    fois doublerait le coût du walk sans changer une seule entrée (les
    deux passes produiraient le même préfixe pour les mêmes fichiers).
    """
    roots: list[Path] = [Path.cwd().resolve()]
    for raw in _SOURCE_PATH_RE.findall(theme_css):
        path = Path(raw).resolve()
        if not path.is_dir():
            # Une racine absente n'est pas rattrapée en silence : le
            # binaire, lui, échouera dessus, et ``get_or_build_css``
            # transforme cet échec en repli explicite. Ici on l'ignore
            # seulement pour ne pas faire tomber le calcul du cache.
            continue
        roots.append(path)
    # Élagage des imbriquées, dans les deux sens : le cas normal du dépôt
    # en développement est ``cwd`` = la racine du dépôt, donc le paquet
    # est DEDANS et ne doit pas être parcouru une seconde fois.
    return [
        r for r in roots
        if not any(other != r and other in r.parents for other in roots)
    ]


def _theme_digest(theme_css: str) -> str:
    """Empreinte de l'entrée — elle NOMME le fichier compilé.

    Elle vivait dans un ``style.css.sha256`` posé à côté d'un
    ``style.css`` unique, ce qui ne laissait de place qu'à UN thème
    par dossier. Cf. :func:`get_or_build_css`.
    """
    return hashlib.sha256(theme_css.encode("utf-8")).hexdigest()


#: Combien de feuilles compilées le cache garde. Chacune pèse 230 à
#: 740 Ko, et la clé inclut l'empreinte des sources balayées : **toute**
#: édition d'un ``theme.py`` du framework crée une entrée neuve. Sans
#: éviction, mesuré le 2026-08-30 sur la machine de dev : **470 fichiers,
#: 298 Mo** accumulés en deux jours de travail sur les thèmes.
#:
#: Douze parce que c'est ce qu'un aller-retour normal consomme — deux ou
#: trois apps d'exemple, chacune avec ses variations de thème — sans
#: qu'on paie 3 s de recompilation à chaque bascule.
CACHE_KEEP: Final[int] = 12


def _touch(path: Path) -> None:
    """Remet la date à maintenant. Ne lève jamais — perdre un rang de
    LRU est sans conséquence, perdre un démarrage d'app ne l'est pas."""
    with contextlib.suppress(OSError):
        path.touch()


def _sheet_for(pointer: Path) -> Path | None:
    """La feuille que désigne ce pointeur, ou ``None``.

    Un pointeur ORPHELIN — dont la feuille a été évincue — rend ``None``,
    donc se comporte comme une absence de cache : on recompile. C'est le
    bon défaut, et c'est pour ça que l'éviction n'a pas à toucher aux
    pointeurs pour rester correcte.
    """
    try:
        sheet = pointer.parent / pointer.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    return sheet if sheet.is_file() else None


def _store_sheet(scratch: Path, css_dir: Path, pointer: Path) -> Path:
    """Range la feuille fraîchement compilée SOUS L'EMPREINTE DE SON
    CONTENU, et fait pointer la clé dessus.

    Pourquoi deux niveaux. La clé de cache inclut l'empreinte des
    sources balayées — il le FAUT, sinon changer une classe qui ne
    touche aucune couleur ne parviendrait jamais en prod (cf.
    :func:`_content_fingerprint`). Mais la réciproque est fausse :
    toucher un ``theme.py`` sans changer une seule classe produit une
    clé neuve pour une sortie IDENTIQUE.

    Mesuré le 2026-08-31 : **6 des 7 feuilles en cache étaient octet
    pour octet identiques** — deux contenus distincts pour sept entrées.
    Le cache annonçait douze places et en tenait deux utiles pendant une
    session de travail sur les thèmes, et la feuille du CRM pouvait se
    faire évincer par six copies de celle du playground.

    Adresser par le contenu règle ça sans toucher à la clé : douze
    places tiennent maintenant douze thèmes DIFFÉRENTS.
    """
    payload = scratch.read_bytes()
    sheet = css_dir / f"{hashlib.sha256(payload).hexdigest()[:16]}.css"
    if sheet.is_file():
        # Déjà là, octet pour octet : on jette le doublon et on relève
        # sa date, puisqu'on vient de s'en servir.
        with contextlib.suppress(OSError):
            scratch.unlink()
        _touch(sheet)
    else:
        try:
            scratch.replace(sheet)
        except OSError:
            # Un autre processus a pu la ranger entre-temps. Sa copie
            # vaut la nôtre — elles ont la même empreinte.
            if not sheet.is_file():
                raise
    with contextlib.suppress(OSError):
        pointer.write_text(sheet.name, encoding="utf-8")
    return sheet


def _prune_css_cache(css_dir: Path, *, keep: int = CACHE_KEEP) -> int:
    """Ne garder que les ``keep`` feuilles les plus RÉCEMMENT UTILISÉES.

    Sur la date de modification, et le chemin du cache-hit la remet à
    jour : sans ce ``touch``, l'ordre serait celui des compilations, donc
    la feuille qu'on sert dix fois par jour se ferait évincer par une
    variation compilée une fois et jamais relue.

    Ne lève jamais. Un fichier qu'un autre processus tient ouvert refuse
    d'être supprimé sous Windows, et perdre une éviction est sans
    conséquence — perdre le démarrage de l'app ne l'est pas.
    """
    try:
        entries = sorted(
            css_dir.glob("*.css"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
    except OSError:
        return 0
    removed = 0
    for stale in entries[keep:]:
        try:
            stale.unlink()
            removed += 1
        except OSError:
            continue
    return removed


def get_or_build_css(
    theme_css: str, *, rebuild: bool = False, allow_download: bool = False
) -> str:
    """Return a compiled ``style.css`` string for ``theme_css``.

    Tries (in order) :

    1. Le compilé déjà en cache pour CETTE entrée —
       ``./.bretzel/css/<empreinte>.css``, sauf ``rebuild=True``.
    2. A binary already locatable via :func:`find_lightning_binary`
       (env var / wheel / ``$PATH``) — runs the compile, caches the
       result.
    3. Un binaire déjà présent dans ``./.bretzel/bin/``.
       Son téléchargement n'est permis que si ``allow_download=True``.

    Errors :class:`CompilerError` if every path fails.

    La clé combine le CSS d'entrée et l'empreinte des sources scannées.
    Un fichier ``.key`` pointe vers la feuille nommée par son contenu :
    plusieurs entrées peuvent partager le même CSS compilé. Le cache est
    borné par :data:`CACHE_KEEP` et peut être reconstruit après suppression.
    """
    cache = _cache_dir()
    # DEUX entrées, donc deux moitiés de clé : le CSS de thème, et les
    # fichiers que le compilateur balaie pour y trouver des classes.
    # Les racines balayées sortent du CSS lui-même (``scan_roots``) : le
    # ``cwd``, plus le paquet installé et ce que l'app a déclaré.
    digest = _theme_digest(
        theme_css + _content_fingerprint(scan_roots(theme_css))
    )
    css_dir = cache / "css"
    css_dir.mkdir(parents=True, exist_ok=True)
    pointer = css_dir / f"{digest[:16]}.key"

    if not rebuild:
        sheet = _sheet_for(pointer)
        if sheet is not None:
            # ``touch`` : c'est ce qui fait de l'éviction un LRU plutôt
            # qu'un FIFO. Sans lui, la feuille servie tous les jours
            # porterait la date de sa compilation et tomberait avant une
            # variation compilée une fois par erreur.
            _touch(sheet)
            _touch(pointer)
            return sheet.read_text(encoding="utf-8")

    # Aucun téléchargement implicite au démarrage : l'appelant doit
    # autoriser explicitement cet accès réseau avec ``allow_download``.
    try:
        binary = find_lightning_binary()
    except CompilerError:
        # ``find_lightning_binary`` ne connaît que l'env, le wheel et le
        # PATH — pas notre propre cache. Un binaire déjà téléchargé dans
        # ``.bretzel/bin/`` doit évidemment servir.
        cached = _binary_path()
        if cached.is_file():
            binary = cached
        elif allow_download:
            binary = download_binary()
        else:
            raise

    print("[bretzel] Compiling Tailwind CSS ...")
    import time

    t0 = time.time()
    # On compile vers un nom PROVISOIRE : le nom définitif est
    # l'empreinte de ce qui sort, et on ne la connaît qu'après.
    #
    # ⚠️ **Le nom doit être unique par APPELANT, pas par clé.** Il était
    # dérivé de la clé, donc deux processus compilant le MÊME thème en
    # même temps se partageaient le fichier : le premier le renommait,
    # le second lisait un chemin disparu et mourait sur
    # ``FileNotFoundError`` au démarrage de l'app. Or « deux apps qui
    # démarrent ensemble depuis la même racine » est précisément la
    # situation pour laquelle ce cache tient plusieurs places.
    #
    # Trouvé le 2026-08-31 dans `-m browser -n 4`, et l'apprentissage
    # vaut plus que le correctif : ça se manifestait comme une erreur de
    # COLLECTE pytest (« Different tests were collected between gw3 and
    # gw0 »), à trois runs sur six, parce que la gate qui monte les
    # bancs le fait à l'import. J'avais d'abord attribué ça à mes
    # propres éditions — faux.
    fd, tmp_name = tempfile.mkstemp(
        dir=css_dir, prefix=f".{digest[:16]}.", suffix=".tmp",
    )
    os.close(fd)
    scratch = Path(tmp_name)
    result = compile_with_lightning(
        theme_css,
        output_path=scratch,
        binary=binary,
        minify=True,
    )
    elapsed = round(time.time() - t0, 1)
    css_path = _store_sheet(scratch, css_dir, pointer)
    size_kb = result.bytes_written // 1024
    print(
        f"[bretzel] CSS ready - {size_kb} KB raw "
        f"(~{max(size_kb // 5, 1)} KB gzip) ({elapsed}s) -> {css_path}"
    )
    _prune_css_cache(css_dir)
    return css_path.read_text(encoding="utf-8")


__all__ = [
    "CACHE_KEEP",
    "download_binary",
    "get_or_build_css",
    "scan_roots",
]
