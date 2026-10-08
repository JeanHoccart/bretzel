# Changelog

All notable changes to Bretzel are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow
[SemVer](https://semver.org/spec/v2.0.0.html). Bretzel is in alpha: APIs may
change between alpha releases.

## [Unreleased]

### Added

- The package ships a PEP 561 `py.typed` marker: type checkers now read
  Bretzel's annotations in your project. Thanks to @sarel-myburgh (#5).

### Changed

- A `broadcast=[State]` signal for a `SessionState` now reaches only the tabs
  of the session that changed it; other sessions are no longer asked to
  refetch their own, unchanged zone. `AppState` and the other scopes still
  reach every subscribed session.
- Python 3.14 is tested in CI and declared in the package metadata.
- `ui.input(type=...)` refusing a native picker type now names the shipped
  component (`ui.date_picker`, `ui.week_picker`, …) instead of "coming soon".

### Fixed

- The screen cookie includes `Secure` on https pages and remains usable over http (#9).
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

### Removed

- Three unused mark SVGs (1.5 MB) are no longer shipped in the wheel.

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
