"""Handlers du banc ``Sidebar`` — ils MUTENT, les panneaux se re-rendent.

Chaque ``log_*`` empile une ligne dans ``SidebarEvents``, dont le
panneau d'événements déclare la dépendance : le re-rendu est celui du
socle, pas un appel explicite.
"""

from examples.playground.features.sidebar.state import (
    SidebarEvents,
    SidebarPlayground,
)


def log(name: str) -> None:
    state = SidebarEvents()
    state.log = [*state.log, name]


def log_home() -> None:
    log("click(item='Home')")


def log_issues() -> None:
    log("click(item='Issues')")


def log_settings() -> None:
    log("click(item='Settings')")


def log_logout() -> None:
    log("click(footer_item='Log out')")


def clear_log() -> None:
    SidebarEvents().log = []


def server_changed(state: SidebarPlayground) -> None:
    # Param typé → le dispatcher hydrate la valeur du contrôle changé dans
    # ``state`` (coercée + persistée). Le panneau déclare
    # ``deps=[SidebarPlayground]``, il se re-rend seul.
    pass


def parse_extra_attrs(blob: str) -> dict:
    result: dict = {}
    for raw in blob.splitlines():
        line = raw.strip()
        if not line or "=" not in line:
            continue
        key, _, value = line.partition("=")
        result[key.strip()] = value.strip()
    return result
