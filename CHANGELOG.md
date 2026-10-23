# Changelog

All notable changes to Bretzel are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow
[SemVer](https://semver.org/spec/v2.0.0.html). Bretzel is in alpha: APIs may
change between alpha releases.

## [Unreleased]

## [0.1.0a3] - 2026-10-23

### Added

- `Bretzel(api_docs=True)` publishes the app's JSON API: `/openapi.json` and a
  Swagger UI page at `/docs`. The schema lists only the routes the app declares
  on `app.fastapi`, and declares the bearer scheme, so "Authorize" takes an API
  key and "Try it out" sends it. Under `csp=`, the page carries its own policy.
  Off by default.
- `auth.session_key()` lets another program act in the current browser session:
  a request sending it as `Authorization: Bearer` reads and writes that
  session's `SessionState`, and the session's open windows follow. It carries
  the session, not the signed-in user.
- The Kanban example has an API: list, create and move cards, tried at `/docs`.
  The banner's API button shows a ready `curl` whose card lands on the
  visitor's own board, live.
- The package ships a PEP 561 `py.typed` marker: type checkers now read
  Bretzel's annotations in your project. Thanks to @sarel-myburgh (#5).
- `bretzel --version`. Thanks to @Muhtasim-Munif-Fahim (#14).
- htmx, idiomorph, the iconify component and the Lucide icon set (the default
  `ui.icon` set) ship inside the package: a production page loads nothing
  from a third-party host, with no command to run first. Licenses are in
  `bretzel/render/_vendor/THIRD_PARTY_LICENSES.md`.

### Changed

- The default scale is Tailwind's again: a 4 px spacing step (40 px
  controls at the default size) and text at 12 / 14 / 16 / 18 / 20 / 24 px.
  The denser 3 px / 14 px scale made control labels sit 1.6 px above centre
  (a fractional line height) and read cramped next to other frameworks; an
  app that wants it writes `Theme(spacing="0.1875rem", text={…})`.
- Corners are slightly squarer by default: 10 px for boxes (cards, panels,
  dialogs), 8 px for fields and buttons, 4 px for small marks (checkboxes,
  badges). Switches, radios and progress bars stay round.

- An app can serve a JSON API next to its pages: a `POST`, `PUT`, `PATCH` or
  `DELETE` carrying `Authorization: Bearer <token>` is no longer subject to the
  CSRF check, so another program can call a route declared on `app.fastapi`.
  The token is checked by the app's `@auth.source`. The origin check still
  applies (a program sends no `Origin`); requests without a bearer token,
  including `Basic` credentials, are checked as before.
- A `broadcast=[State]` signal for a `SessionState` now reaches only the tabs
  of the session that changed it; other sessions are no longer asked to
  refetch their own, unchanged zone. `AppState` and the other scopes still
  reach every subscribed session.
- Python 3.14 is tested in CI and declared in the package metadata.
- `ui.input(type=...)` refusing a native picker type now names the shipped
  component (`ui.date_picker`, `ui.week_picker`, …) instead of "coming soon".
- `bretzel new` creates a project that depends on `bretzel[css]`, so it serves
  a stylesheet compiled once in production instead of compiling it in the
  browser.
- `ui.form` leaves validation to the server (`novalidate`): an invalid
  `type="email"` no longer cancels the submit in silence, the state's messages
  show instead. `attrs={"novalidate": False}` restores the browser's check.
- In dev, a handler parameter that no submitted field fills is reported once
  (`set_search(q): no field named 'q'…`): it used to run on its default with
  no message, typically after a `str()` cast dropped an input's `name=`.
- Rendering is faster: a component at its default size or variant no longer
  resolves its theme to check it (a 50-row table's update: 122 → 101 ms).

### Fixed

- A multi-select re-rendered by its own `on_change` keeps showing its pills.
  The morph recycled the first pill's node into the placeholder, and the
  pills stayed hidden while the server held the value.
- A checkbox, radio or switch without a label sits on the middle of its line;
  in a table cell it stood 3 px above the row's centre. Its border is also
  easier to see in light mode.
- A multi-select with several picks stays on one line and reads
  "Alice Martin +3": its pills wrapped and spilled out of the field.
- An `overlay` sidebar closes when one of its links is followed; it stayed
  open over the new page on a phone.
- Switching between light and dark is instant. Each component's colour
  transition ran on the switch too, and the page repainted in a staggered
  wave.

- `pip install 'bretzel[css]'` works: the extra required `tailwindcss`, a
  placeholder name on PyPI; it now installs `tailwindcss-bin`, the Tailwind
  standalone CLI as wheels.
- A `ui.form_field` label names its control: screen readers and
  `get_by_label` find the input, select or combobox (`aria-labelledby` on the
  focusable element). Its `for=` pointed at an id no control carried. The
  `required=True` asterisk sits next to the label, not inside its text.
- `ui.select` and `ui.combobox` carry `aria-describedby` / `aria-invalid` on
  their focusable element, not on the layout wrapper.
- A drag that crosses the threshold and drops in a single pointer move (a
  quick flick) now moves the card; it used to drop in the origin zone.
- A page using `ui.viewport` no longer leaves `<body>` 0 px tall.
- The DOM ids of a loop over strings or tuples are the same in every process:
  they were derived from Python's per-process salted `hash()`, so they changed
  at each restart and between workers, and a partial from one worker no longer
  merged onto a page rendered by another.
- A route that is neither an action nor a page (a route declared on
  `app.fastapi`, a `@download`, a zone refetch) now reads the stored typed
  state and saves what it writes. It used to read the defaults and lose its
  writes, silently. A write method (POST, PUT, PATCH, DELETE) also notifies the
  open windows of a changed `broadcast=` state, as an action does. A 4xx or 5xx
  response keeps nothing the route wrote, and an `@error_page` no longer saves
  the writes of the code that failed before it.
- `ui.tabs` can be used from the keyboard: arrow keys, Home and End move the
  focus and the selection, skipping disabled tabs, and each tab is linked to
  its panel (`aria-controls` / `aria-labelledby`).
- The compiled-CSS cache in `.bretzel/css/` no longer grows without bound: it
  prunes orphaned pointers and abandoned scratch files, and a failed
  compilation leaves nothing behind.
- The Kanban example's windows follow each other again: the board stays one
  per visitor, and two tabs of the same browser share it live.
- The vendor download message is in English.
- The language cookie set by `Language.set` follows the same transport rule as
  the session cookies: `Secure` over https, `secure_cookies=` behind a
  TLS-terminating proxy. Thanks to @sarel-myburgh (#6).
- The screen cookie (`bz_screen`) follows the transport too: `Secure` on
  https pages, still usable over http (#9). Thanks to @sricharanreddycheruku
  (#11).

### Removed

- Three unused mark SVGs (1.5 MB) are no longer shipped in the wheel.
- The unused `docs` extra (mkdocs). Thanks to @Muhtasim-Munif-Fahim (#13).

## [0.1.0a2] - 2026-09-29

### Added

- A public component gallery, `examples/showcase` (live at
  <https://ui.bretzel-py.dev>): one page per component with realistic uses and
  their code, eight ready-made identities and a theme studio that exports the
  `Theme(...)` to paste.
- `ui.icon_button(href=…, external=…)` renders a link, like `ui.button`.
- Charts fill their container by default; `width=` is now a maximum.

### Changed

- Frame widths (sidebar, drawer, notification stack) are written in `rem`: they
  no longer shrink with the control density.
- The sidebar's rows sit closer, its groups further apart; its focus ring is
  drawn inside the row.
- Calendar weekday headers use one letter (the full name is in `title`) so they
  fit at every size and density.
- The chart series palette starts with the brand pair (`primary`, `secondary`).
- A link attribute (`href`, `target`, `rel`, `download`) passed to a component
  that does not render a link now raises instead of rendering inert HTML.

- User-facing API, CLI output, diagnostics and error pages are now in English.
- Public documentation entry points, the core documentation path and the
  application map guide are translated to English.

### Fixed

- `Bretzel(description=…)` is now the `<meta name="description">` of every page
  that declares none, as the configuration documented; it was never rendered.
- The package metadata points to the website, documentation, component gallery
  and issue tracker instead of the repository README.
- The README quickstart and the playground theme defaults.
- Test collection on a clean CI environment for every supported Python.
- The atelier example initializes its schema before importing its features.
- A form's whole-instance validators see the submission as one batch: two
  identical passwords were reported different after a previous mismatch.
- A refused submission with no other change now re-renders the form, so its
  messages appear (the action answered `204` before).
- An unbound, unnamed `ui.radio_group` gives its radios a common name, so they
  exclude each other again.
- A handler parameter annotated `int`, `bool`… receives that type.
- A client expression with quotes in `ui.icon(name=…)` no longer breaks the
  page's runtime scan.
- A dismissed badge inside a refreshed loop reappears when the server renders
  it again.
- The switch thumb is centred at any density; table headers follow their
  column's alignment; a carousel showing several cards no longer overflows;
  `ui.file_upload(variant="button")` no longer stretches; `ui.title` follows a
  zone refreshed by an action.

## [0.1.0a1] - 2026-09-15

First public alpha.

### Added

- Server-Driven UI: Python owns routes, typed state, actions and rendering;
  the browser applies partial updates.
- Typed state in four server scopes (`PageState`, `SessionState`,
  `UserState`, `AppState`) and one client scope (`ClientState`).
- 100+ UI components: inputs, actions, feedback, navigation, overlays,
  layout, data tables and server-rendered charts.
- A small in-house browser runtime — no application JavaScript and no npm
  pipeline in production.
- FastAPI/ASGI integration, signed actions, SSE realtime broadcast and
  drag-and-drop.
- Authentication primitives: signed session cookie, identity sources and
  OAuth/OIDC doors.
- Tailwind CSS v4 theming, compiled with the standalone binary in production.
- CLI: `bretzel new`, `bretzel dev`, `bretzel describe` and `bretzel check`.

[Unreleased]: https://github.com/JeanHoccart/bretzel/compare/v0.1.0a2...HEAD
[0.1.0a2]: https://github.com/JeanHoccart/bretzel/releases/tag/v0.1.0a2
[0.1.0a1]: https://github.com/JeanHoccart/bretzel/releases/tag/v0.1.0a1
