# Changelog

All notable changes to Bretzel are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow
[SemVer](https://semver.org/spec/v2.0.0.html). Bretzel is in alpha: APIs may
change between alpha releases.

## [Unreleased]

### Changed

- User-facing API, CLI output, diagnostics and error pages are now in English.
- Public documentation entry points, the core documentation path and the
  application map guide are translated to English.

### Fixed

- The README quickstart and the playground theme defaults.
- Test collection on a clean CI environment for every supported Python.
- The atelier example initializes its schema before importing its features.

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

[Unreleased]: https://github.com/JeanHoccart/bretzel/compare/v0.1.0a1...HEAD
[0.1.0a1]: https://github.com/JeanHoccart/bretzel/releases/tag/v0.1.0a1
