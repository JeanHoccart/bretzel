"""Life app entry point — run with ``py -m examples.life.main``."""

import os

from bretzel import Bretzel
from examples.life.features import board

#: A local run stays in dev with a throwaway key. ``BRETZEL_MODE=prod``
#: takes the key from ``$BRETZEL_SECRET_KEY`` (``secret_key=None`` falls
#: through to it), and the framework refuses to start without one.
MODE = os.environ.get("BRETZEL_MODE", "dev")

app = Bretzel(
    title="Bretzel · Life",
    secret_key="dev-life-secret-change-me" if MODE == "dev" else None,
    mode=MODE,
)

app.include(board)


if __name__ == "__main__":
    app.run(port=8021, reload=True)
