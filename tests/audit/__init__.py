"""Component audit framework.

Catches the classes of bugs that ``tests/unit/`` doesn't :

- ``Visual`` : ``getComputedStyle`` based — color distinctness across
  the 7 palette colors, size distinctness across the 5 paliers, tab
  order, parasite scrollbars, overflow clipping of absolute children.
- ``Interaction`` : Playwright click / type / keyboard / drag, then
  assert the resulting DOM / state matches what the component spec
  promises.
- ``State machinery`` : server-side refresh round-trips (change a
  prop via ``on_change``, verify the panel re-renders with the new
  value) and client-binding propagation (render with
  ``value=client_state.X``, verify the right ``bz-model`` /
  ``bz-attr`` is emitted).
- ``Static`` : declared ``BINDABLE_PROPS`` / ``EVENTS`` /
  ``AUTONAME_FROM`` consistent with the component's actual behaviour.

Architecture :

- :mod:`tests.audit.checklist` — canonical list of checks, each one
  a callable that takes ``(page, component_meta)`` and returns
  pass / fail + detail.
- :mod:`tests.audit.probes` — reusable Playwright probes (color,
  size, tab, scrollbar, click, type, ...). The checklist composes
  these.
- :mod:`tests.audit.harness` — spins up a uvicorn server in a
  background thread, exposes a Playwright ``page`` fixture, manages
  per-component navigation.
- :mod:`tests.audit.driver` — top-level runner used by subagents.
  Take a component name → run every applicable check → return a
  structured report.

The ``tests/runtime_js/test_<component>_visual.py`` files use this
infra to lock down behaviour permanently after the first audit pass.
"""
