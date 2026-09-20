"""Everything switched on, in ONE command: ``py -m examples.auth.demo``.

Starts the local OIDC provider in a subprocess, sets the four variables
it needs, turns on proxy-header reading, then serves the app. The four
ways in are all live, and one Ctrl+C closes everything.

Why this file exists: the README's walkthrough asks for **two terminals
and four variables**, and that is friction the demo did not have to
impose. The first real attempt ended in an ``ERR_CONNECTION_REFUSED`` on
the app's port — the provider alone was running, which is exactly what
had been asked for, and not at all what was wanted.

``main.py`` stays the real app, with none of this: it is the one you read
to see how a door is wired. This file is only a demonstration launcher.

Ports: ``BZ_APP_PORT`` (8012) and ``BZ_IDP_PORT`` (8954) if either is
already taken.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
import urllib.error
import urllib.request

#: ⚠️ The token and the header come from the domain, they are NOT copied:
#: changing them left the banner handing out a command that returns 302,
#: and the reader blames the demo.
from examples.auth.core.domain import API_TOKENS, PROXY_HEADER

IDP_PORT = os.environ.get("BZ_IDP_PORT", "8954")
APP_PORT = int(os.environ.get("BZ_APP_PORT", "8012"))
ISSUER = f"http://localhost:{IDP_PORT}"
TOKEN = next(iter(API_TOKENS))


def wait_for_idp(deadline: float = 20.0) -> bool:
    """Wait until discovery answers — otherwise the door would not mount."""
    url = f"{ISSUER}/.well-known/openid-configuration"
    started = time.monotonic()
    while time.monotonic() - started < deadline:
        try:
            with urllib.request.urlopen(url, timeout=1):
                return True
        except (urllib.error.URLError, OSError):
            time.sleep(0.3)
    return False


def main() -> int:
    env = dict(os.environ)
    env["BZ_IDP_PORT"] = IDP_PORT
    idp = subprocess.Popen(
        [sys.executable, "-m", "examples.auth.local_idp"], env=env
    )
    try:
        if not wait_for_idp():
            print(
                f"The provider did not start on {ISSUER} — the port "
                "is probably taken. Retry with BZ_IDP_PORT=8964.",
                flush=True,
            )
            return 1

        # ⚠️ The variables are set BEFORE importing the app: the doors
        # are built while ``features/access.py`` loads. An import higher
        # up in this file would have frozen everything door-less, in
        # silence.
        os.environ["BZ_OIDC_NAME"] = "testidp"
        os.environ["BZ_OIDC_ISSUER"] = ISSUER
        os.environ["BZ_OIDC_CLIENT_ID"] = "bretzel-test-client"
        os.environ["BZ_OIDC_CLIENT_SECRET"] = "bretzel-test-secret"
        os.environ["BZ_TRUST_PROXY_HEADER"] = "1"

        from examples.auth.main import app

        print(
            "\n"
            f"  Auth demo — the four ways are live\n"
            f"  open   http://127.0.0.1:{APP_PORT}\n\n"
            "  1. password          jean@macorp.fr / demo\n"
            "  2. OIDC door         “Continue with testidp” button\n"
            "\n  The last two have no screen: paste the command in\n"
            "  ANOTHER terminal, and it answers three lines.\n\n"
            f'  3. machine token     curl.exe -s -H "Authorization: Bearer '
            f'{TOKEN}" http://127.0.0.1:{APP_PORT}/me\n'
            f'  4. proxy header      curl.exe -s -H "{PROXY_HEADER}: '
            f'jean@macorp.fr" http://127.0.0.1:{APP_PORT}/me\n\n'
            "  Ctrl+C closes both servers.\n",
            flush=True,
        )
        app.run(port=APP_PORT)
    except KeyboardInterrupt:
        pass
    finally:
        idp.terminate()
        try:
            idp.wait(timeout=10)
        except subprocess.TimeoutExpired:
            idp.kill()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
