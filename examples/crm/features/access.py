"""features/access — logic: who is looking, and what they may see.

The CRM's shortest feature, and the one every other reads. It answers
**one** question — :func:`visible_owner` — and the app's whole access
policy sits in its answer:

- a **commercial** is brought back to their own portfolio, always,
  without any screen having to know;
- a **directeur** sees everything (``None``), or stands in for somebody
  by picking a portfolio.

⚠️ **The filter is a PARAMETER, not a global variable the repos would go
and read.** Every read function takes its ``owner`` and puts it in its
``WHERE``; the screen passes it. It is more verbose, and that is the
point: one can RE-READ a signature and see whether it is scoped. A repo
calling ``visible_owner()`` on its own would make the filtering invisible
at the call site — and a forgotten path would stay so.

⚠️ ``ViewerPrefs`` is a :class:`~bretzel.state.UserState`, so it **raises
``AuthRequiredError`` (401) outside a signed-in session**. It is the
state segmentation the framework provides, and the only thing it provides
in the way of a user: never touch it from a public page.
"""

from __future__ import annotations

from bretzel import Feature, redirect
from bretzel.render import current_context
from bretzel.server import auth
from bretzel.state import UserState, field
from examples.crm.core.domain import LOGIN_PATH, OWNERS
from examples.crm.features.auth_data import find_by_id


class ViewerPrefs(UserState):
    """The preferences attached to the ACCOUNT, not to the session.

    Two browsers signed in to the same account see the same setting; two
    accounts on the same browser share none. That is exactly what
    ``scope="user"`` means, and it is the class's reason to exist.
    """

    #: The portfolio a DIRECTOR is looking at. Empty = all. A commercial
    #: does not use it: their portfolio is not a choice.
    portefeuille: str = field(default='')


#: The name under which the profile is set on ``request.state``. A
#: constant rather than a repeated literal: it is a key shared with the
#: base layer, on an object that is not ours.
_PROFILE_SLOT = "crm_profile"


def current_profile() -> dict | None:
    """The signed-in account, joined from the cookie's identifier.

    ``None`` when nobody is signed in — or when the cookie names a
    deleted account, which must behave the same.

    ⚠️ **Memoised for the duration of the REQUEST**, on ``request.state``.
    Without this cache, every call reopened a SQLite connection: the
    choice "the scoping is a parameter" makes :func:`visible_owner` be
    called once per zone, and the reports screen counted **nine per
    render** (seven zones + two for the sidebar), that is nine file
    openings at 1.6 ms to answer "who is looking". Measured: 54.4 ms →
    36.6 ms on ``/rapports`` (−33 %).

    The cache is **per request**, not global (anti-rule 2): two requests
    share nothing, and a re-sign-in mid-request does not exist — the
    sign-in page reads no profile.
    """
    try:
        state = current_context().request.state
    except RuntimeError:
        # Outside a render context (a test calling directly): no
        # request to hang a cache on, we read every time.
        return read_profile()
    cached = getattr(state, _PROFILE_SLOT, _MISSING)
    if cached is _MISSING:
        cached = read_profile()
        setattr(state, _PROFILE_SLOT, cached)
    return cached


#: Sentinel: ``None`` is a LEGITIMATE cache value (nobody is signed in),
#: so it cannot mean "not read yet".
_MISSING = object()


def read_profile() -> dict | None:
    user_id = auth.user_id()
    return find_by_id(user_id) if user_id else None


def is_director() -> bool:
    profile = current_profile()
    return bool(profile) and profile["role"] == "directeur"


#: An ANONYMOUS visitor's scoping. It is not ``None`` — ``None`` means
#: "all", and an access policy's default cannot be "everything". No owner
#: is called ``""``, so ``WHERE owner = ''`` returns nothing: it is a
#: refusal going through the same path as the rest, without any read
#: having to know the case.
NOBODY = ""


def visible_owner() -> str | None:
    """The owner whose data one may see. ``None`` = all.

    The access policy's single door. Three cases, and the order matters:

    1. **nobody is signed in** → :data:`NOBODY`, so nothing. The
       middleware guard already sends them to the sign-in; this return is
       the second lock, for the day a route steps outside the guard.
       Returning ``None`` here would open the WHOLE database to an
       anonymous visitor — the form of error one never sees when
       re-reading, because the page renders perfectly;
    2. **commercial** → their own name, ALWAYS. There is no branch where
       they could obtain another: it is the property one wants to be able
       to re-read at a glance;
    3. **directeur** → what they chose, or ``None`` if they chose
       nothing. A choice not naming a known owner is ignored rather than
       refused — a stale setting must not block a page.
    """
    profile = current_profile()
    if profile is None:
        return NOBODY
    if profile["role"] != "directeur":
        return profile["owner"]
    chosen = str(ViewerPrefs().portefeuille)
    return chosen if chosen in OWNERS else None


def sign_out() -> None:
    """Sign out and go back to the sign-in page.

    Here and not in ``features/login.py``: the sidebar needs it, and
    making it depend on the sign-in PAGE made every screen transitively
    import that page. Signing out is access logic, not screen content.

    ``disconnect`` rotates the session identifier as well as clearing the
    cookie: everything attached to the previous session — an import
    draft, a filter — starts over, which is the expected behaviour when
    leaving an account on a shared machine.
    """
    auth.logout()
    redirect(LOGIN_PATH)


def portfolio_options() -> list[tuple[str, str]]:
    """The directorate selector's choices. ``""`` = all."""
    return [("", "Every portfolio"), *((o, o) for o in OWNERS)]


def set_portfolio(prefs: ViewerPrefs) -> None:
    """The director changes portfolio; ``deps=`` re-renders the zones.

    ⚠️ The body is empty **and that is the mechanism**: the base layer
    has already hydrated ``prefs.portefeuille`` before calling the
    handler, and the mutation alone triggers the re-render of the zones
    declaring ``deps=[ViewerPrefs]``. Writing anything here would be
    redundant.
    """


feature = Feature(
    name="access",
    kind="logic",
    provides=[ViewerPrefs, current_profile, is_director, visible_owner,
              portfolio_options, set_portfolio, sign_out],
    uses=["auth_data"],
)
