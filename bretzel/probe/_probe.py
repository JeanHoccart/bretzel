"""The probe — serves the app, opens the windows, records the findings.

The harness supplies the AXES, the probe supplies the SCENARIO. That is
the module's reason to exist: in ``tests/probes/``, 146 files and 21 898
lines rewrote the axes by hand — 75 opened Playwright, 64 started the
server, 66 redefined their own ``check``.
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
                "the request count can only be read AFTER the "
                "`with p.requests() as net:` block — during it, the gesture "
                "is not finished."
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
        return f"Net({self.total} requests: {', '.join(self.urls) or '—'})"


def say(line: str) -> None:
    """Print, whatever happens to the console's encoding.

    A probe launched by hand reconfigures its output to UTF-8; a probe
    collected by ``pytest`` has reconfigured nothing at all, and the
    Windows console is in cp1252. A finding name carrying a "①" then
    brought the scenario down on a ``UnicodeEncodeError`` — from
    ``print``, that is to say from the line that was meant to REPORT.
    Measured on 2026-09-11 while porting a bench measurement into a gate.

    Replacement is preferable to silence: the verdict stays readable,
    only the character that does not pass becomes a "?".
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

    # ── measuring the network ─────────────────────────────────────────
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

    # ── reading what the SERVER believes ──────────────────────────────
    def state[S](self, klass: type[S], *, of: Window | None = None) -> S:
        """Return the shared backend state at the current instant."""
        from bretzel.state import AppState, StateRegistry

        if self._app is None:
            raise ScopeNotReadableError(
                "state() needs thread mode: in subprocess mode the app "
                "lives elsewhere, so its state backend is not in this "
                "process. Re-run without serve=\"subprocess\"."
            )
        if of is not None:
            raise ScopeNotReadableError(
                "of= is not shipped yet: reading a session scope requires "
                "decrypting the window's signed cookie."
            )
        if not (isinstance(klass, type) and issubclass(klass, AppState)):
            raise ScopeNotReadableError(
                f"{klass.__name__} is not an AppState. Only the shared "
                "scope can be read without a request: a PageState is indexed "
                "by a render uuid, a SessionState by a cookie."
            )

        backend = self._app.state_backend
        if backend is None:
            raise ScopeNotReadableError(
                "the app has no state backend yet — it is wired at "
                "startup, so before the lifespan there is nothing to read."
            )

        # ⚠️ We do NOT rewrite the hydration. ``try_sync_resolve``
        # composes the scope key, chooses between ``load_sync`` and the
        # loop, and builds through ``type.__call__`` — the metaclass
        # would intercept ``klass(...)`` and RESTART a hydration. A first
        # version of this body copied all three: that is exactly the
        # divergence ``_build`` carries the scar of.
        #
        # A throwaway registry is enough: the ``app`` scope depends on no
        # request identity, and its instance cache dies with it.
        resolved = StateRegistry(backend).try_sync_resolve(klass)
        # ``None`` = the backend carries nothing yet, so the state IS
        # its defaults. Outside a registry, ``klass()`` builds without
        # hydrating.
        return resolved if resolved is not None else klass()

    # ── rendre le verdict ─────────────────────────────────────────────
    def report(self) -> None:
        total = len(self._verdicts)
        bad = self.failures
        say("")
        say(f"  {total - len(bad)}/{total} green — screenshots in {self.out}")
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
            # The scenario raised: we still return the findings already
            # recorded — they often say WHERE it broke — but we do not
            # sweep a page whose state we no longer know.
            p.report()
            raise
        sweep(p.windows, p.size, p.check)
        p.report()
        if p.failures:
            raise ProbeFailedError(f"{len(p.failures)} constat(s) rouge(s).")
