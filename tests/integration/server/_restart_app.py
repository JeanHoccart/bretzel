"""The app ``test_a_state_survives_a_restart`` starts twice, in two processes.

Module level on purpose: the action route resolves its handlers through
``sys.modules``. Its ``state_url`` comes from the environment so that the
same app runs on a file and on memory — the test's two sides.
"""

from __future__ import annotations

import os

from bretzel import Bretzel, page, refreshable, ui
from bretzel.state import AppState, SessionState, field


class Compte(AppState):
    n: int = field(default=0, merge="add")


class Vue(SessionState):
    fil: str = field(default="aucun")


app = Bretzel(
    secret_key="restart-" * 4,
    mode="dev",
    state_url=os.environ.get("BZ_TEST_STATE_URL") or None,
)


@refreshable
def compte() -> None:
    ui.text(f"compte={Compte().n} fil={Vue().fil}")


def avancer() -> None:
    Compte().n += 1
    Vue().fil = "42"


@page("/")
def accueil() -> None:
    compte()


app.include(accueil)
