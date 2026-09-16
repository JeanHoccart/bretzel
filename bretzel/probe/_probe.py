"""Le probe — sert l'app, ouvre les fenêtres, enregistre les constats.

Le harnais fournit les AXES, le probe fournit le SCÉNARIO. C'est la
raison d'être du module : dans ``tests/probes/``, 146 fichiers et 21 898
lignes réécrivaient les axes à la main — 75 ouvraient Playwright, 64
lançaient le serveur, 66 redéfinissaient leur propre ``check``.
"""

from __future__ import annotations

import contextlib
import sys
import time
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from bretzel.probe._browser import contexts
from bretzel.probe._server import serve as _serve_app
from bretzel.probe._sweep import sweep
from bretzel.probe._window import Seen, Window

__all__ = ["Probe", "Net", "ProbeFailedError", "ScopeNotReadableError", "probe"]


class ProbeFailedError(AssertionError):
    """Raised when at least one browser probe check fails."""


class ScopeNotReadableError(LookupError):
    """Raised when a probe cannot inspect the requested state scope."""


class Net:
    """Record the network cost of a browser interaction."""

    def __init__(self) -> None:
        self._done = False
        self._seen: tuple[Seen, ...] = ()

    def _close(self, seen: tuple[Seen, ...]) -> None:
        self._seen, self._done = seen, True

    def _guard(self) -> None:
        if not self._done:
            raise RuntimeError(
                "le compte de requêtes ne se lit qu'APRÈS le bloc "
                "`with p.requests() as net:` — pendant, le geste n'est pas fini."
            )

    @property
    def total(self) -> int:
        self._guard()
        return len(self._seen)

    @property
    def urls(self) -> tuple[str, ...]:
        self._guard()
        return tuple(s.url for s in self._seen)

    @property
    def methods(self) -> tuple[str, ...]:
        self._guard()
        return tuple(s.method for s in self._seen)

    @property
    def kinds(self) -> tuple[str, ...]:
        self._guard()
        return tuple(s.kind for s in self._seen)

    def __repr__(self) -> str:
        if not self._done:
            return "Net(en cours)"
        return f"Net({self.total} requêtes : {', '.join(self.urls) or '—'})"


def say(line: str) -> None:
    """Imprime, quoi qu'il arrive à l'encodage de la console.

    Un probe lancé à la main reconfigure sa sortie en UTF-8 ; un probe
    collecté par ``pytest`` n'a rien reconfiguré du tout, et la console
    Windows est en cp1252. Un nom de constat qui porte un « ① » faisait
    alors tomber le scénario sur un ``UnicodeEncodeError`` — depuis
    ``print``, c'est-à-dire depuis la ligne qui devait RENDRE COMPTE.
    Mesuré le 2026-09-11 en portant une mesure de banc vers une gate.

    Le remplacement est préférable au silence : le verdict reste lisible,
    seul le caractère qui ne passe pas devient un « ? ».
    """
    try:
        print(line)
    except UnicodeEncodeError:
        codec = getattr(sys.stdout, "encoding", None) or "ascii"
        print(line.encode(codec, "replace").decode(codec))


@dataclass(frozen=True, slots=True)
class Verdict:
    name: str
    ok: bool
    detail: str


class Probe:
    def __init__(
        self,
        base_url: str,
        windows: tuple[Window, ...],
        *,
        size: tuple[int, int],
        out: Path,
        app: Any,
    ) -> None:
        self.base_url = base_url
        self.windows = windows
        self.size = size
        self.out = out
        self._app = app
        self._verdicts: list[Verdict] = []

    # ── constater ─────────────────────────────────────────────────────
    def check(self, name: str, ok: bool, detail: object = "") -> None:
        text = "" if ok else str(detail)
        self._verdicts.append(Verdict(name, bool(ok), text))
        mark = "PASS" if ok else "FAIL"
        say(f"  [{mark}] {name}" + (f" — {text}" if text else ""))

    @property
    def failures(self) -> tuple[Verdict, ...]:
        return tuple(v for v in self._verdicts if not v.ok)

    # ── attendre ──────────────────────────────────────────────────────
    def settle(self, *, timeout: float = 5.0) -> None:
        """Wait for every probe window to reach a stable state."""
        for window in self.windows:
            window.settle(timeout=timeout)

    def hold(self, seconds: float) -> None:
        """Wait deliberately for the requested duration."""
        time.sleep(seconds)

    # ── mesurer le réseau ─────────────────────────────────────────────
    @contextlib.contextmanager
    def requests(self) -> Iterator[Net]:
        """Return the network requests made by the current probe gesture."""
        marks = [(w, w.mark()) for w in self.windows]
        net = Net()
        try:
            yield net
            self.settle()
        finally:
            net._close(tuple(s for w, m in marks for s in w.since(m)))

    # ── lire ce que le SERVEUR croit ──────────────────────────────────
    def state[S](self, klass: type[S], *, of: Window | None = None) -> S:
        """Return the shared backend state at the current instant."""
        from bretzel.state import AppState, StateRegistry

        if self._app is None:
            raise ScopeNotReadableError(
                "state() a besoin du mode thread : en sous-processus l'app "
                "vit ailleurs, donc son backend d'état n'est pas dans ce "
                "processus. Relance sans serve=\"subprocess\"."
            )
        if of is not None:
            raise ScopeNotReadableError(
                "of= n'est pas encore livré : lire une portée de session "
                "demande de déchiffrer le cookie signé de la fenêtre."
            )
        if not (isinstance(klass, type) and issubclass(klass, AppState)):
            raise ScopeNotReadableError(
                f"{klass.__name__} n'est pas un AppState. Seule la portée "
                "partagée se lit sans requête : un PageState est indexé par "
                "un uuid de rendu, un SessionState par un cookie."
            )

        backend = self._app.state_backend
        if backend is None:
            raise ScopeNotReadableError(
                "l'app n'a pas encore de backend d'état — il est câblé au "
                "démarrage, donc avant le lifespan il n'y a rien à lire."
            )

        # ⚠️ On ne réécrit PAS l'hydratation. ``try_sync_resolve`` compose
        # la clé de portée, choisit entre ``load_sync`` et la boucle, et
        # construit par ``type.__call__`` — la métaclasse intercepterait
        # ``klass(...)`` et RELANCERAIT une hydratation. Une première
        # version de ce corps recopiait les trois : c'est exactement la
        # divergence dont ``_build`` porte la cicatrice.
        #
        # Un registre jetable suffit : la portée ``app`` ne dépend
        # d'aucune identité de requête, et son cache d'instances meurt
        # avec lui.
        resolved = StateRegistry(backend).try_sync_resolve(klass)
        # ``None`` = le backend ne porte rien encore, donc l'état EST ses
        # défauts. Hors registre, ``klass()`` construit sans hydrater.
        return resolved if resolved is not None else klass()

    # ── rendre le verdict ─────────────────────────────────────────────
    def report(self) -> None:
        total = len(self._verdicts)
        bad = self.failures
        say("")
        say(f"  {total - len(bad)}/{total} verts — captures dans {self.out}")
        for verdict in bad:
            say(f"  ROUGE  {verdict.name}" + (f" — {verdict.detail}" if verdict.detail else ""))


@contextlib.contextmanager
def probe(
    app: Any,
    *,
    windows: int = 1,
    size: tuple[int, int] = (1280, 700),
    headed: bool = False,
    out: Path | str | None = None,
    serve: str = "thread",
) -> Iterator[Probe]:
    """Serve an application, open browser windows, and run checks on exit."""
    out_dir = (
        Path(out)
        if out
        else Path(".bretzel") / "probe" / time.strftime("%Y%m%d-%H%M%S")
    )
    out_dir.mkdir(parents=True, exist_ok=True)

    with (
        _serve_app(app, mode=serve) as (base_url, served),
        contexts(windows, size=size, headed=headed) as ctxs,
    ):
        opened = tuple(
            Window(ctx.new_page(), base_url, out_dir, name=f"f{i + 1}")
            for i, ctx in enumerate(ctxs)
        )
        p = Probe(base_url, opened, size=size, out=out_dir, app=served)
        try:
            yield p
        except BaseException:
            # Le scénario a levé : on rend quand même les constats déjà
            # posés — ils disent souvent OÙ ça a cassé — mais on ne balaie
            # pas une page dont on ne sait plus dans quel état elle est.
            p.report()
            raise
        sweep(p.windows, p.size, p.check)
        p.report()
        if p.failures:
            raise ProbeFailedError(f"{len(p.failures)} constat(s) rouge(s).")
