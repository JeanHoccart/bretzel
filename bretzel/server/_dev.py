"""Bretzel-owned dev watcher.

Replaces uvicorn's ``--reload`` (broken on Windows : worker
subprocess never killed, cf. ``.claude/bretzel/traps.md`` section
*Hot-reload uvicorn fragile sur Windows*). Owns the kill/respawn
loop via :func:`watchfiles.run_process` in ``function`` mode so the
child runs in a clean ``multiprocessing.get_context('spawn').Process``
on every reload — no shell, no Windows-path quoting issues.

Private module (leading underscore) : not part of the public API.
The single user-facing entry is :meth:`bretzel.Bretzel.run`, which
delegates here when called with ``reload=True``.
"""

from __future__ import annotations

import socket


class PortAlreadyTakenError(OSError):
    """The port is already held — said BEFORE launching anything.

    It is the cheap half of the remedy for a flaw measured on
    2026-09-03: ``watchfiles.run_process`` launches uvicorn in a CHILD
    process, and when the parent dies without propagating — terminal
    closed, ``timeout``, kill — **the child survives and keeps the
    port**. The next launch then fails INSIDE the child, and depending on
    the terminal the ``[Errno 10048]`` does not even surface: one sees
    "watching: …" then the prompt, and nothing else. Seen for real, PID
    5640 holding 8006 while ``netstat`` said nothing about it.

    A bind attempt in the PARENT costs a millisecond and puts the error
    back where the user reads it.
    """


def ensure_port_is_free(host: str, port: int) -> None:
    """Raise :class:`PortAlreadyTakenError` if ``(host, port)`` is taken.

    ⚠️ We do NOT name the process holding the port: the 2026-09-03
    measurement showed ``netstat`` can return nothing where
    ``Get-NetTCPConnection`` sees the holder. Promising a PID we cannot
    obtain reliably would be worse than promising nothing — we say what
    we know, and we say how to find it.

    The test socket does NOT set ``SO_REUSEADDR``: we want exactly the
    question uvicorn will ask, not a more permissive one.
    """
    probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        probe.bind((host, port))
    except OSError as exc:
        raise PortAlreadyTakenError(
            f"port {port} is already taken on {host} — nothing was "
            f"launched.\n"
            f"  Most frequent cause: a previous dev server whose PARENT "
            f"was killed without propagating (terminal closed, timeout). "
            f"The uvicorn child survives and keeps the port.\n"
            f"  To find the holder on Windows:\n"
            f"      Get-NetTCPConnection -LocalPort {port} | "
            f"Select-Object OwningProcess\n"
            f"  (`netstat` can return NOTHING in this case — measured.)"
        ) from exc
    finally:
        probe.close()


def _run_uvicorn(target: str, host: str, port: int, log_level: str) -> None:
    """Run a uvicorn server against a ``"module:varname"`` target.

    Module-level so :func:`watchfiles.run_process` can re-import it
    in the spawned child process. Each child runs this once ; on a
    file change the parent kills it and respawns a fresh process
    that re-imports the user's app from scratch.
    """
    import uvicorn

    uvicorn.run(target, host=host, port=port, log_level=log_level)


def run_dev_server(
    target: str,
    host: str,
    port: int,
    log_level: str,
    watch_dirs: list,
) -> None:
    """Block on watchfiles' parent loop: spawn :func:`_run_uvicorn`
    as a child, restart it on every ``*.py`` change under
    ``watch_dirs``. Returns on Ctrl+C.

    ``watch_dirs`` accepts anything :func:`watchfiles.run_process`
    accepts as a path: :class:`pathlib.Path` or :class:`str`. We
    don't coerce — the caller (``Bretzel._derive_watch_dirs``)
    already passes resolved :class:`Path` objects.

    ⚠️ Raises :class:`PortAlreadyTakenError` before any launch if the
    port is already held — cf. its docstring for the flaw that closes.

    ⚠️ **What stays open**: the child's end of life. A parent killed
    abruptly propagates nothing to it, and that is what CREATES the
    situation detected here. The clean remedy on Windows is a Job Object
    that kills its children with it; it is not written. Detecting is
    better than suffering, but it is not the root.
    """
    from watchfiles import PythonFilter, run_process

    # BEFORE the "watching" message, and before launching the child:
    # otherwise the bind failure happens in a process whose output does
    # not always surface, and the user sees "watching" then the prompt,
    # with nothing to understand it by.
    ensure_port_is_free(host, port)

    print(f"[bretzel] watching: {[str(p) for p in watch_dirs]}")
    run_process(
        *watch_dirs,
        target=_run_uvicorn,
        args=(target, host, port, log_level),
        target_type="function",
        watch_filter=PythonFilter(),
    )
