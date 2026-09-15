"""End-to-end tests — real browser, real uvicorn, no mocks.

These cover the layer-to-layer integration unit tests can't see :
Alpine directive matching, HTMX OOB swaps actually applying, the JS
runtime hydrating ``$bz.state``, persistence backends writing through
on mutations, etc.

Marked with ``pytest.mark.e2e`` so the fast unit suite stays fast :

    py -m pytest -m "not e2e"        # default fast feedback loop
    py -m pytest tests/e2e/          # the slow stack-wide checks
    py -m pytest                     # everything (CI)
"""
