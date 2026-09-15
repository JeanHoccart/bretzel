"""Pomodoro app entry point — run with ``py -m examples.pomodoro.main``.

Showcases ``ui.interval`` : a client-side ticker whose ``active=`` gate is
a ``ClientState`` signal. Pressing Pause flips the signal and the timer
clears instantly — no held server connection, no cancellable task. Each
tick is a Python handler that decrements the countdown in ``SessionState``.

Flat structure : every feature self-decorates and imports only
``bretzel`` ; ``main`` is the only file that knows the app.
"""

from bretzel import Bretzel

from examples.pomodoro.features import errors, timer

app = Bretzel(
    title="Bretzel · Pomodoro",
    secret_key="dev-pomodoro-secret-change-me",
    mode="dev",
)

app.include(timer, errors)


if __name__ == "__main__":
    app.run(port=8011, reload=True)
