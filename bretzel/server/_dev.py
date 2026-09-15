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
    """Le port est déjà tenu — dit AVANT de lancer quoi que ce soit.

    C'est le remède de la moitié cheap d'un défaut mesuré le 2026-09-03 :
    ``watchfiles.run_process`` lance uvicorn dans un processus ENFANT, et
    quand le parent meurt sans propager — terminal fermé, ``timeout``,
    kill — **l'enfant survit et garde le port**. Le lancement suivant
    échoue alors DANS l'enfant, et selon le terminal l'``[Errno 10048]``
    ne remonte même pas : on voit « watching: … » puis le prompt, et rien
    d'autre. Constaté en vrai, PID 5640 tenant le 8006 alors que
    ``netstat`` n'en disait rien.

    Un essai de liaison dans le PARENT coûte une milliseconde et remet
    l'erreur là où l'utilisateur la lit.
    """


def ensure_port_is_free(host: str, port: int) -> None:
    """Lève :class:`PortAlreadyTakenError` si ``(host, port)`` est pris.

    ⚠️ On ne nomme PAS le processus qui tient le port : la mesure du
    2026-09-03 a montré que ``netstat`` peut ne rien rendre là où
    ``Get-NetTCPConnection`` voit le tenant. Promettre un PID qu'on ne
    sait pas obtenir de façon fiable serait pire que ne rien promettre —
    on dit ce qu'on sait, et on dit comment le trouver.

    La socket d'essai ne pose PAS ``SO_REUSEADDR`` : on veut exactement
    la question que se posera uvicorn, pas une plus permissive.
    """
    probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        probe.bind((host, port))
    except OSError as exc:
        raise PortAlreadyTakenError(
            f"le port {port} est déjà pris sur {host} — rien n'a été "
            f"lancé.\n"
            f"  Cause la plus fréquente : un serveur de dev précédent dont "
            f"le PARENT a été tué sans propager (terminal fermé, timeout). "
            f"L'enfant uvicorn survit et garde le port.\n"
            f"  Pour trouver le tenant sous Windows :\n"
            f"      Get-NetTCPConnection -LocalPort {port} | "
            f"Select-Object OwningProcess\n"
            f"  (`netstat` peut ne RIEN rendre dans ce cas — mesuré.)"
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
    """Block on watchfiles' parent loop : spawn :func:`_run_uvicorn`
    as a child, restart it on every ``*.py`` change under
    ``watch_dirs``. Returns on Ctrl+C.

    ``watch_dirs`` accepts anything :func:`watchfiles.run_process`
    accepts as a path : :class:`pathlib.Path` or :class:`str`. We
    don't coerce — the caller (``Bretzel._derive_watch_dirs``)
    already passes resolved :class:`Path` objects.

    ⚠️ Lève :class:`PortAlreadyTakenError` avant tout lancement si le port
    est déjà tenu — cf. sa docstring pour le défaut que ça ferme.

    ⚠️ **Ce qui reste ouvert** : la fin de vie de l'enfant. Un parent tué
    brutalement ne lui propage rien, et c'est ce qui CRÉE la situation
    détectée ici. Le remède propre sous Windows est un Job Object qui tue
    ses enfants avec lui ; il n'est pas écrit. Détecter vaut mieux que
    subir, mais ce n'est pas la racine.
    """
    from watchfiles import PythonFilter, run_process

    # AVANT le message « watching », et avant de lancer l'enfant : sinon
    # l'échec de liaison arrive dans un processus dont la sortie ne
    # remonte pas toujours, et l'utilisateur voit « watching » puis le
    # prompt, sans rien pour comprendre.
    ensure_port_is_free(host, port)

    print(f"[bretzel] watching: {[str(p) for p in watch_dirs]}")
    run_process(
        *watch_dirs,
        target=_run_uvicorn,
        args=(target, host, port, log_level),
        target_type="function",
        watch_filter=PythonFilter(),
    )
