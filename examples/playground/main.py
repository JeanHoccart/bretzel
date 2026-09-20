"""Playground entry point — run with ``py -m examples.playground.main``."""

from fastapi import Request, Response

from bretzel import PWA, Bretzel

app = Bretzel(
    title="Bretzel · Playground",
    secret_key="dev-playground-secret-change-me",
    mode="dev",
    # The playground is also the CSP test bench — in BLOCKING mode, not
    # in report-only: a policy one only observes proves nothing. Bretzel
    # already computes what it owes (the digests of its inline scripts,
    # ``'unsafe-eval'``, the icon hosts, its assets' origins); what
    # follows is what the APP loads, and nothing else. Cf.
    # ``.claude/bretzel/security.md``.
    csp=True,
    csp_sources={
        "img-src": [
            # ``/avatar``'s demonstration avatars.
            "https://i.pravatar.cc",
            # ⚠️ Declared although it will NEVER answer: ``/avatar``
            # demonstrates falling back on the initials when the image
            # fails, and this URL is wrong on purpose. Without this line
            # it would fail anyway — but for the wrong reason, leaving a
            # permanent CSP violation in the test bench's console, where
            # "zero violations" is the useful signal.
            "https://invalid.example",
        ],
        # ``/iframe`` mounts a ``ui.iframe(src="data:text/html,…")``.
        # It is NOT a framework defect: Bretzel cannot know an app wants
        # ``data:`` iframes, and allowing it by default would widen every
        # other app's policy.
        "frame-src": ["data:"],
    },
    # The playground declares itself INSTALLABLE — it is ``PWA``'s test
    # bench, just as it is the components'.
    #
    # ``icon=`` takes the framework's mark, which is an SVG: it is the
    # case where ``sizes="any"`` is EXACT and not a tolerated
    # approximation. No ``maskable`` — the drawing has not the margin
    # Android's masking asks for, and declaring it would cut into it.
    #
    # To try it: open the playground on ``localhost`` (a secure
    # context), then the address bar's install icon. ⚠️ Chrome long
    # required a service worker ON TOP to offer it, and Bretzel ships
    # none — if the prompt does not appear, that is why, not the
    # manifest: that one is validated by Chromium
    # (``tests/probes/probe_pwa.py``).
    pwa=PWA(
        name="Bretzel Playground",
        short_name="Bretzel",
        description="The test bench for Bretzel's components.",
        icon="/_bretzel/favicon.svg",
        theme_color="#2f5fd0",
        background_color="#f8fafc",
    ),
)

# Routes / error pages are pure declarations (they import only
# ``bretzel``). Importing runs the ``@page`` / ``@error`` marks ;
# ``include`` registers them. This is the only place that knows the app.
from examples.playground.app import routes      # noqa: E402 — builds routes.PAGES
from examples.playground.infra import errors    # noqa: E402 — @error handlers

app.include(routes.PAGES, errors)


@app.fastapi.post("/_demo/upload")
async def demo_upload(request: Request) -> dict[str, object]:
    """Upload target for the playground's ``upload_url=`` cards.

    ``ui.file_upload``'s async mode POSTs every file and only emits
    ``upload_complete`` on a 2xx response — with no real target, the page
    can demonstrate neither the progress bar nor the event. We consume
    the body and throw it away: it is a demo, nothing is stored.

    CSRF applies here as on every POST outside ``/_bretzel/action/*``
    (the slab sends the header from ``$bz._csrf``) — so this endpoint
    also exercises that path for real.
    """
    form = await request.form()
    upload = form.get("file")
    size = len(await upload.read()) if hasattr(upload, "read") else 0
    name = getattr(upload, "filename", "") or ""
    return {"ok": True, "name": name, "size": size}


@app.fastapi.post("/_demo/upload-fail")
async def demo_upload_fail() -> Response:
    """A target that fails on purpose, for the ``upload_error`` card.

    ``upload_error`` only fires on a non-2xx response. As long as the
    card pointed at the target that succeeds, the event was
    undemonstrable — it only fired by accident, when the upload was
    broken for another reason (which was the case with the CSRF 403).
    """
    return Response(status_code=500, content="demo failure")


if __name__ == "__main__":
    app.run(port=8001, reload=True)
