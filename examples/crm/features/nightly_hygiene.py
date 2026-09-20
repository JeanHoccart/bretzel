"""features/nightly_hygiene — job: the nightly hygiene pass.

A ``kind="job"`` feature: a background task. No route, no rendering, no
`Request` — it is what the kind declares, and it is why a job does NOT
anchor the optimal placement in the app map (only pages and layouts
anchor). Wired to a scheduler in a real app; exposed as a function here,
so it is callable and testable without a clock.

What it does is a CRM's real need: open deals whose close date has passed
are noise in the pipeline. Nobody closes them during their day, so the
night takes care of it — it COUNTS them and returns them, it does not
decide in a salesperson's place.

Taken over from the `mad` app's nightly recomputation on 2026-09-10, when
it was removed: `job` was exercised only there. The coverage has been
gated since, by
``tests/consistency/test_every_feature_kind_is_exercised.py``.
"""

from __future__ import annotations

from bretzel import Feature
from examples.crm.core.db import query
from examples.crm.core.domain import OPEN_STAGES, TODAY


def stale_deals() -> list[dict]:
    """The OPEN deals whose close date has passed.

    With no portfolio scoping: a job runs with no user, so it has no
    identity to restrict the read to. It is exactly the reason why
    ``test_crm_owned_reads_declare_their_scope`` carries a named
    allowlist rather than a blind rule.
    """
    marques = ", ".join("?" for _ in OPEN_STAGES)
    return query(
        f"SELECT id, name, owner, stage, close_date FROM deals "
        f"WHERE stage IN ({marques}) AND close_date < ? "
        f"ORDER BY close_date",
        (*OPEN_STAGES, TODAY.isoformat()),
    )


def run_nightly_hygiene() -> int:
    """The complete pass — returns the number of deals to review."""
    return len(stale_deals())


feature = Feature(
    name="nightly_hygiene",
    kind="job",
    provides=[run_nightly_hygiene, stale_deals],
    uses=["db"],
)
