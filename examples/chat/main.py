"""Chat — a demonstrator of server → browser STREAMING.

Run: ``py -m examples.chat.main``.

What this example shows, and why it exists: Bretzel has two ways of
changing the DOM, and a text filling up progressively is the case that
forces you to pick the right one.

- The **structure** (one more message in the log) can only change through
  a server re-render → ``@refreshable``, here with ``broadcast=[Log]`` so
  the other tabs follow.
- The **value** (the growing text of the message in progress) needs no
  HTML: the server reassigns a ``ClientState`` field, it comes back down
  in a JSON patch, and the browser writes into a text node.

And the **cadence** is pulled by the client (``ui.interval`` gated on a
``ClientBinding``), not pushed by the server. That is not a performance
detail, it is what makes the *Stop* button possible: a ``@background``
loop runs with no request context, so it cannot re-read the state that
would tell it to stop (``handlers.md`` § *background* — the playground's
stepper walked exactly that path in reverse).

The token generator is **simulated**: no LLM call, no API key. The
subject is the transport; wiring a real model would change only
``examples/chat/features/generator.py`` § ``answer_for``.
"""

from bretzel import Bretzel
from examples.chat.core.theme import THEME
from examples.chat.features import conversation, shell

app = Bretzel(
    title="Bretzel · Chat",
    secret_key="dev-chat-secret-change-me",
    theme=THEME,
    mode="dev",
    # Declaring the language sets ``<html lang>`` and picks the words the
    # framework writes itself. ``texts`` then overrides them one key at a
    # time — here two labels that read better in this app than the
    # defaults ("Toggle sidebar", "Collapse or expand the sidebar"). The
    # CRM shows the full table; two are enough here.
    lang="en",
    texts={
        "sidebar.toggle": "Show or hide the menu",
        "sidebar.rail_toggle": "Fold or unfold the side panel",
    },
)

app.include(shell, conversation)


if __name__ == "__main__":
    app.run(port=8003, reload=True)
