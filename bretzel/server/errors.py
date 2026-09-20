"""Server-layer error types + ``abort`` + default error pages.

Three concerns in a short file, all at the same boundary: they are a
handler's **non-nominal** exits.

- :class:`BretzelError` — generic framework runtime error.
- :class:`AuthRequiredError` — raised by ``UserState()`` when no user.
- :func:`abort` — user-facing helper to short-circuit a handler with
  an HTTP status code.
- :func:`default_error_page` — minimal HTML5 fallback when no
  ``@error_page(status)`` handler is registered.

"""

from __future__ import annotations

from typing import NoReturn

from starlette.exceptions import HTTPException

# Canonical definitions live in ``core`` so persistence, dispatch and HTTP
# handling share the same classes without violating the import DAG
# (``core < state < server``). This module re-exports the server-facing names.
from bretzel.core.errors import AuthRequiredError, BretzelError

#: The module's explicit surface, two of them intentional re-exports.
__all__ = [
    "AuthRequiredError",
    "BretzelError",
    "abort",
    "default_error_page",
]

# ───────────────────────────────────────────────────────────────────────────
# abort — explicit short-circuit from a handler
# ───────────────────────────────────────────────────────────────────────────


def abort(status_code: int, detail: str = "") -> NoReturn:
    """Raise an HTTP error from inside a request handler."""
    raise HTTPException(status_code=status_code, detail=detail)


# ───────────────────────────────────────────────────────────────────────────
# Default HTML for unrouted error statuses
# ───────────────────────────────────────────────────────────────────────────


# Minimal stylesheet inlined so the page doesn't depend on the user's
# theme.css being available — useful for early-startup or
# theme-compilation failures.
def default_error_page(
    status_code: int,
    *,
    title: str | None = None,
    message: str | None = None,
) -> str:
    """Build a self-contained HTML5 error page.

    No Tailwind / JS dependencies — the page must work even if the
    framework's own assets fail to load.
    """
    final_title = title or _default_title_for(status_code)
    final_message = message or _default_message_for(status_code)
    return (
        "<!doctype html>\n"
        '<html lang="en">\n'
        "<head>\n"
        f"  <meta charset=\"utf-8\"/>\n"
        f'  <meta name="viewport" content="width=device-width, initial-scale=1"/>\n'
        f"  <title>{status_code} — {final_title}</title>\n"
        "  <style>\n"
        "    body { font-family: system-ui, sans-serif; "
        "max-width: 640px; margin: 96px auto; padding: 0 24px; "
        "color: #1f2937; }\n"
        "    h1 { font-size: 4rem; margin: 0 0 8px; color: #111827; }\n"
        "    p { font-size: 1.05rem; line-height: 1.6; }\n"
        "    a { color: #2563eb; }\n"
        "  </style>\n"
        "</head>\n"
        "<body>\n"
        f"  <h1>{status_code}</h1>\n"
        f"  <p><strong>{final_title}.</strong> {final_message}</p>\n"
        '  <p><a href="/">Back to home</a></p>\n'
        "</body>\n"
        "</html>"
    )


def _default_title_for(status_code: int) -> str:
    return {
        400: "Bad request",
        401: "Authentication required",
        403: "Forbidden",
        404: "Page not found",
        405: "Method not allowed",
        422: "Unprocessable entity",
        500: "Server error",
        502: "Bad gateway",
        503: "Service unavailable",
    }.get(status_code, "Error")


def _default_message_for(status_code: int) -> str:
    return {
        400: "The request could not be understood.",
        401: "You need to sign in to access this page.",
        403: "You don't have permission to view this page.",
        404: "The page you're looking for doesn't exist.",
        405: "The HTTP method used isn't allowed for this URL.",
        422: "The submitted data is invalid.",
        500: "Something went wrong on our side.",
        502: "Got an invalid response from upstream.",
        503: "The service is temporarily unavailable.",
    }.get(status_code, "An error occurred while processing your request.")
