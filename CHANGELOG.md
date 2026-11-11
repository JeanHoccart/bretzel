# Changelog

All notable changes to Bretzel are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow
[SemVer](https://semver.org/spec/v2.0.0.html). Bretzel is in alpha: APIs may
change between alpha releases.

## [Unreleased]

## [0.1.0a5] - 2026-11-11

### Added

- `ui.link(size=…)`, with the steps of `ui.text`. Without it a link keeps its
  parent's size, as before.
- `Topic`, `@reads` and `@writes` in `bretzel.state`: what is not a state (a
  database, a file, an API) is followed by declaring which functions read and
  write it. `refresh(topic)` redraws without a write. `bretzel features`
  shows who reads and writes each
  topic, and `bretzel check` reports one wired on a single side.


- Lint rule `unknown-theme-color`: a colour utility whose colour no theme
  has — `border-base-300`, `text-base-content` (DaisyUI's names),
  `bg-primary-500` (Bretzel's colours have no shades). Tailwind generates
  no rule for it, in dev as in production, and the property falls back to
  the text colour: a black line where a hairline was meant, with no error
  anywhere. Found in an app on 2026-10-30, written twice. The hint gives
  the theme's way (`border-text/10`).
- `t("Create")` translates an app's own sentences: the sentence as written
  in the code is the key (gettext's choice), `Bretzel(translations={"fr":
  {...}})` gives the other languages, a sentence nobody translated shows as
  written, and a counted sentence (`t("{n} task", n=n, plural="{n}
  tasks")`) takes the language's form. A table for an undeclared language
  or a renamed hole raises at startup. `bretzel translations <module:attr>`
  lists, per language, the sentences a table lacks and the entries no call
  uses any more. `examples/kanban` moved from its `tr(en, fr)` to `t()`.
- The framework's own sentences ship in French: `lang="fr"` is enough,
  `texts=` keeps only an app's real differences (three apps retyped the
  same table). A counted sentence follows the language's plural rule
  (CLDR, whole numbers): « 0 résultat » in French, Russian's `few` and
  `many`; `texts=` accepts the `_few` / `_many` forms.
- `python -m bretzel` runs the CLI where Python's `Scripts` folder is not on
  `PATH` (the `bretzel` command answered « not found » on Windows).
- `bretzel features <module:attr>` prints the map of an app's features —
  kind, first docstring line, routes, what each exposes, imports and is
  used by — then what to fix in the contracts: `uses` that differ from the
  real imports, a public symbol nothing outside its feature uses, a symbol
  taken from a feature that does not expose it (constants recognised by
  identity). `bretzel impact <module:attr> <file>…` names the features a
  change touches through the imports, their pages, and the probes that
  visit them.

- `Theme(spacing=…)` takes three families, like the radii: `field` (the
  controls — Tailwind's `--spacing`), `box` (the padding inside cards and
  panes) and `gap` (the space between blocks). A single length still sets
  all three. An app can now make its pages tighter or airier without
  resizing its buttons: `Theme(spacing={"gap": "0.1875rem"})`. The layout
  components' scales read `--bz-gap-N` / `--bz-pad-N`; the showcase studio
  has the three sliders.

- `follow(*states)` in `bretzel.state`: the zone being rendered follows these
  states without reading them. For data that is not a state — a database,
  the clock: bump a revision state on the write, and call
  `follow(ContactsRev)` in the function that reads the data; every zone
  calling it follows the writes.

- `bretzel check` reads four app idioms that break nothing and drift an app
  from the framework: a dialog opened by a server state that carries
  nothing but that boolean (`dialog-opened-by-a-server-flag` — open it with `dialog.open()`), a pill
  built by hand (`badge-built-by-hand` — `ui.badge`), a component forced
  with `!` classes and no comment saying why
  (`component-forced-with-important`), a breadcrumb drawn by hand
  (`breadcrumb-built-by-hand` — `ui.breadcrumb`).

- In debug mode, a list with no `key` that moves under a client state (an
  open menu, a ticked box) warns, naming the zone and the list: that
  state follows the rank, not the item — iterate with
  `ui.each(items, key=...)`. Only then: a `for` over a fixed list, or a
  list with no client state inside, never warns.
- `bretzel vendor [--force]` downloads the third-party scripts into
  `./.bretzel/vendor/`; the startup warning names it.
- `ui.scheduler` and `ui.scheduler_item`: events posed on a grid of time,
  to the minute — day, 3 days, week and month views; side-by-side lanes,
  all-day bars across days; drag a card, pull its bottom edge, and the
  server accepts, refuses (the card goes back) or asks first (the card
  waits). Today's number is filled — the one marked day.
  Its hours follow the page's language: « 8h », « 10h10 » in French.
  `on_create=`: a slot traced on the empty grid reaches the handler as a
  `Reschedule` with an empty `event_id`.

### Changed

- **Breaking:** Redis is an extra: `pip install 'bretzel[redis]'`. Only an app
  running several workers needs it (`redis_url`); `import bretzel` no longer
  imports it, and setting `redis_url` without it says how to install it.
- A Markdown title takes `ui.heading`'s scale: `## Why` is as large and as bold
  as `ui.heading("Why", level=2)` (it was a step smaller and lighter). The
  `markdown` theme only spaces its titles now; their size and weight follow
  the `heading` theme.
- `redirect()` called while a page renders for an ordinary navigation
  answers a real `307` instead of raising: `@page("/") def home():
  redirect("/strategies")`. Elsewhere outside htmx it still raises, naming
  `redirect_response()`.
- `refresh(zone)` redraws the zone in the acting tab only; to reach the
  other tabs, write a state they show or ring a `Topic`.
- **Breaking:** `ui.link` no longer takes a dedicated `download=` parameter. A
  link to a `@download` route now downloads from any component, with nothing to
  write; a file served by another route uses the HTML attribute,
  `attrs={"download": ""}`. Before, every component but `ui.link(download=True)`
  lost the page's content instead of downloading.
- `.set()` on the date, week, month, time and date-range pickers takes what
  `value=` takes: a `date`, a `time`, or a `(start, end)` pair. A `date` raised
  a `TypeError`.
- With several series, `on_item_click` on `ui.bar_chart` and `ui.scatter_chart`
  also receives the series name: `(label, value, series)`, `$event.detail.series`.
- `ui.notification(color=)` replaces `variant=`: elsewhere `variant` is the
  look, here it was the colour. `ui.message_input(loading=)` replaces `busy=`.
  The old names are refused with the new one.
- `ui.tabs` gains `.set()`, `ui.link(disabled=)` accepts a binding and
  `ui.scheduler` takes `week_start=`, like `ui.calendar`.
- `ui.radio_group` gains `.clear()`, which unticks every radio.
- `.deselect_all()` on a single-value `ui.select` or `ui.combobox` now refuses,
  like `.select_all()` and `ui.toggle_group`.
- `ui.sidebar(collapsible="overlay")` is a modal for the keyboard and the
  screen reader too: `role="dialog"`, `aria-modal`, and Tab stays in the panel.
- An opening dialog, drawer or overlay sidebar gives the focus to its first
  element actually displayed; a hidden one made it give up.
- A bound `disabled=` on `ui.month_picker` and `ui.week_picker` also reaches
  their calendar, as on `ui.date_picker`.
- A client `on_change=` on a picker runs once per entry, with the value. It
  also heard the visible field's own `change`: twice, the first time on the
  raw text.
- A server `on_focus=` / `on_blur=` on `ui.combobox` receives the field's
  values, like every other field.
- `Component.BINDABLE_CARRIERS` is gone: a component whose bindable prop
  acts on an inner element calls `self.forward_binding(prop, attrs)` in
  `render()`, which already covered every case the map did.
- An application owns its refreshable zones (`Bretzel.zones`). `@refreshable`
  only marks the function; the app finds its zones at startup. Two functions
  under one `name=` now stop the start with a sentence, where one of them
  silently never refreshed.
- A `ui.dropdown` (or any overlay) whose trigger is a
  `ui.message_input_tool` goes to the bar of `ui.message_input`: many tools
  behind one button.
- The colour picker's palette is shared by the page, like the calendar
  pickers' header: one `<template data-bz-part>` per distinct part, cloned
  into a panel the first time it opens (`render/shared_parts.py`,
  `$bz.parts`). Each `ui.color_picker` shipped its 31 swatches; the
  showcase's studio page (22 pickers) went from 1 085 KB to 607 KB, a
  `ui.color_picker` from 15.7 KB to 3.6 KB. A swatch reads and writes the
  picker's value through its scope (`_read` / `_write`), so a picker bound
  to a state shares the same palette. The API does not change.
- The calendar pickers of a page share ONE header. `ui.date_picker`,
  `ui.date_range_picker`, `ui.month_picker` and `ui.week_picker` each
  shipped their calendar's arrows and month / year menus — 14 KB a picker,
  each menu with its own scope and two listeners on `document`: 44 % of a
  settings page with 13 pickers. The page now carries one `<template>` per
  distinct header, with its theme, and a picker clones it the first time
  it opens; a picker never opened holds no header at all. The school's
  settings page went from 447 KB to 239 KB. The API does not change; an
  inline `ui.calendar` keeps its own header.
- One switch, `disabled` (API rule R4): `ui.tooltip(enabled=x)` is
  `ui.tooltip(disabled=…)`, and `ui.interval(active=x)` is
  `ui.interval(disabled=~x)` — a binding negates with `~`. The old names
  raise with the new one in the message. `ui.dropzone(locked=)` and
  `ui.scheduler_item(editable=)` keep theirs: they turn off a capability,
  not the component.
- One word, one meaning (API rule R1): `ui.date_range_picker(close_on_close=)`
  is `close_on_pick=`, as on the four other pickers; `weekstart=` is
  `week_start=` on `ui.calendar`, `ui.date_picker`, `ui.date_range_picker`
  and `ui.week_picker`; `ui.scheduler(on_select=)` is `on_item_click=`, as
  on `ui.table` and the charts. A component retires a name through
  `RENAMED_PROPS`, and the refusal names its successor.
- Every tooltip of a page is ONE panel, `#bz-tip`, rendered once with the
  app's merged tooltip theme and shown by the runtime (`25_tip.js`). A
  `tooltip="…"` is now a wrapper carrying `data-bz-tip*` attributes — no
  scope, no listener, no panel of its own: the kanban board went from
  328 KB to 257 KB, the grade book from 189 KB to 154 KB. The API does not
  change. The collapsed sidebar rail and the charts, which kept panels of
  their own with a COPY of the tooltip's look, show the same panel: a
  `Theme(components={"tooltip": …})` now restyles all of them. The colour
  picker's swatches and the scheduler's compact cards left the browser's
  `title` bubble for it. The panel sits at the top of the stacking scale
  (a swatch's tooltip showed under the picker's panel), and it describes
  the focusable control unless its name already says the same words.
- `ui.color_picker` shows its clear cross by default (`clearable=True`), like
  every picker: a picker empties with one click, a text field with the
  keyboard. A colour that may never be empty passes `clearable=False`.
- A fixed call order (API rule R5). A component with no identifier takes its
  text first: `ui.checkbox("I agree")`, and likewise `ui.switch`,
  `ui.form_field`, `ui.divider`, `ui.sidebar_section`, `ui.file_upload` —
  `label=` still works. A child a parent selects takes its `value` first,
  required, and its label named: `ui.accordion_item`, `ui.tree_node` and
  `ui.radio` no longer accept a missing `value` (two items sharing `""`
  opened together), and `ui.toggle_button("a", label="A")`. A field's
  value is always named: `ui.date_picker(value=…)`, and likewise
  `ui.calendar`, `ui.color_picker`, `ui.date_range_picker`,
  `ui.month_picker`, `ui.time_picker`, `ui.week_picker`.
- A feature's `kind` is now checked in `mode="dev"`, with the other
  contracts: a `data`, `logic`, `state`, `infra` or `job` feature that
  imports a `shell`, `layout`, `page` or `error` one, a page provided by a
  feature that is not a `page` (a layout by neither `shell` nor `layout`,
  an error page by no `error`), and a `page` that mounts no page stop the
  app with a `FeatureError`. None of the example apps broke either rule.
- A `@refreshable` zone directly inside a parent that draws its children
  itself — `ui.tabs`, `ui.stepper`, `ui.accordion`, `ui.tree`,
  `ui.breadcrumb`, `ui.toggle_group`, `ui.resizable`, `ui.scheduler` — is
  refused (`ComponentUsageError`). It rendered at load and lost its child
  the first time it refreshed alone, since its fragment came out without
  the parent: the tab left the bar, the step disappeared. Put the zone
  around the parent. `ui.form_field` refuses a zone too: the field goes
  inside the zone. `ui.fragment` is still traversed, and `ui.sidebar`,
  which only places its children, still takes a zone (its footer).
- `ui.tab`'s identifier is `value`, as on `ui.accordion_item` and
  `ui.tree_node`, and it is required: `ui.tab("messages", label=…)`. It
  was `tab_id`, with a default of `""`, so a tab written
  `ui.tab(label=…, id="x")` — `id` being the HTML id — had no identifier
  at all.

- In `mode="dev"`, an app whose `Feature` contracts lie no longer starts
  (`FeatureError`, every line listed): a `uses` that differs from the real
  imports, or a symbol taken from a feature whose `provides` does not hold
  it — constants included, recognised by identity. It used to be a startup
  WARN. Production never refuses to start over a contract. The example apps
  declare the 32 constants other features took from them.


- **Breaking:** `@refreshable` no longer takes `deps=`. A zone follows every
  state it obtains while it renders — `MyState()` or `await MyState.load()`,
  in its body, in any helper it calls, in a table's `rows=` — and re-renders
  when one of them changes. Nothing to declare, so nothing to declare wrong:
  a forgotten state froze the zone, a state too many re-rendered it for
  nothing. Migration: delete `deps=`; for data that is not a state, see
  `follow()`.
- A zone follows the FIELDS it read, not the whole class: an action redraws
  it only when one of those fields changed. On the comparison helpdesk,
  opening a ticket no longer redraws the status filter. A `@computed`
  makes the zone follow the fields its value was computed from. What a
  descriptor cannot see counts as the whole class: `to_dict()`, `errors`,
  `follow()`, a state obtained and handed on without a field read.
- `broadcast=` publishes only when a field its zones read changed: a
  channel stays quiet when the write touched nothing they show.
- What a zone follows is now known PER CLIENT: a zone's element carries
  what its render read (`data-bz-r`, one short id per field), and the
  runtime sends it back with the zone's fingerprint. Two clients in two
  branches each follow their own, on any worker. A runtime that does not
  send it falls back on what the process learned.
- A component's reads belong to ITS zone wherever it renders: a zone's
  tab that `ui.tabs` composes outside the zone's own render is still
  followed (and `ui.datatable` no longer works around it).
- The example apps follow their database by TABLE, in
  their SQL doors: `query()` reads the revision of every table it names,
  `execute()` bumps it. Their nine hand-written revision tokens, the
  `follow()` lines that read them and the zones that followed a dialog's
  draft in place of the table it wrote are gone.

### Removed

- **Breaking:** `Bretzel(texts=...)`. One table says every word on screen:
  `translations={"fr": {"sidebar.toggle": "Ouvrir le menu", "Save":
  "Enregistrer"}}`. A sentence Bretzel wrote is named by its key, an app's
  own by itself; a key shaped like Bretzel's that names none raises at
  startup, with the closest name. A monolingual app writes its language:
  `texts={...}` becomes `translations={"fr": {...}}`.
- **Breaking:** `@refreshable(broadcast=[...])`. A zone is now redrawn in
  every open tab showing it, as far as the scope of what it read allows: a
  `PageState` stays in its tab, a `SessionState` in its session, a
  `UserState` with its user, an `AppState` or a `Topic` reaches every tab.
  Remove the argument. The refetch route is now `/_bretzel/refetch/<zone>`.
- **Breaking:** `follow()`. Attach the functions that read the data with
  `@reads(TOPIC)`.
- **Breaking:** `refresh("name")`. Pass the zone itself, or a `Topic`. `name=`
  stays: it gives their identity to zones built in a factory.


- `refresh(zone, rows=[…])`, the `zone-rows` SSE event and the refetch
  route's `?rows=`: a second path for what the zone diff does by itself. A
  zone refreshed with `refresh(zone)` already ships only the rows that
  changed, and a row that came or left rides a list patch; a table too long
  to render on each change is a `ui.datatable`, which paginates. `rows=` now
  raises a `TypeError`. `RowReport` leaves `bretzel.render`, and a broker's
  `publish` loses `event=` and `data=`, which only that event used.
- `looks_like_client_expr`, `reads_as_client_expr` (`bretzel.components.base`)
  and `reactive_prop(never_code=…)`: the heuristic that read a string as
  client code is gone (see Security), and `never_code` only switched it
  off for one prop. An app that passed an expression as a plain string
  wraps it: `ClientExpression("count >= 10")`, or `bz-attr:` by hand.
- `zone_ids_watching` (`bretzel.render`): it read the `deps=` index, which
  no longer exists.
- The `bretzel check` rule `zone-listening-too-widely`: a zone no longer
  declares what it follows, so it can no longer declare its child's.

### Fixed

- `ui.icon(set="phosphor")` draws: Iconify knows the set as `ph`, and
  `phosphor:heart` answered 404 everywhere, so nothing was drawn. The
  everyday name becomes the prefix before it reaches the page, in the short
  form and in the full one (`"phosphor:moon"`).
- An icon nobody has gets an empty 404 from the relay, not the app's HTML
  error page (89 KB) that the icon component never finished receiving — a
  page holding one never reached network idle.
- A `redirect()` to a page of the same layout lands what the action changed
  in that layout (a sidebar counter, a banner) before htmx navigates: htmx
  never swaps an `HX-Location` response, and the next patch of such a zone
  missed (« a patch of zone … found the page changed under it »).
- An element whose `id` is legal HTML but not a CSS identifier (`"137"`,
  `"a b"`) is patched by its position: htmx selects an out-of-band element
  with an unescaped `"#" + id`, which threw and dropped the whole response.
  The rule lives once in `protocol.ADDRESSABLE_ID`, read by the server and
  the runtime.
- A loop key that is not a valid id segment (`"NOM01 Prénom01"`) becomes a
  stable digest, so a keyed row's id holds no space and its patch lands.
- A zone's fingerprint ignores its refetch URL, signed per session: two
  clients of one zone held two fingerprints of the same content.
- What someone is typing in a zone another tab redraws survives that
  redraw, unless the server changed that very field.
- A card dropped on a terminal `ui.dropzone` (an archive strip) leaves the
  board even when the pointer crossed another column on its way: it came
  back. The gesture had left it in that column, which the server never
  changed, so the zone diff (since 2026-10-23) never touched it and the
  drop was undone. A terminal or overwrite drop now puts the card back
  where it came from — and while the pointer is over the terminal zone,
  the card leaves the board: hidden, only the floating preview remains,
  until the answer removes it or shows it again on a refusal.
- A date field shows its day in the page's language, as people write it —
  `16/10/2026` in French, `10/16/2026` in American English — the month
  (« novembre 2026 ») and the week (`02/11/2026 – 08/11/2026`) too; the
  value posted stays ISO, and what the field shows reads back. It showed
  `2026-11-03` under a French calendar.
- `ui.number_input` takes the language's decimal mark: a French user types
  and reads « 2,5 », the form posts « 2.5 ». The comma was refused before
  it landed. The value now travels in a hidden input — a probe that typed
  into `input[name=…]` targets the text field beside it.
- `ui.filter_each` ignores accents: « emilie » finds « Émilie », as in a
  datatable or a combobox — it folded only the case. Four recipes folded a
  searched text (NFD, NFKD, `casefold`, an accent range); there is now one,
  `bretzel.core.text.fold`, and its browser twin `$bz.fold`, held equal.
- A card dropped on a `ui.dropzone` stays where it was dropped while the
  server asks something (a modal dialog, no redraw), and goes back only if
  the question ends without an answer that moved it — it went back at once,
  under the question. The end-of-drag click is swallowed too. Both rules
  came from `ui.scheduler`; they now live once (`$bz.gesture`) for both
  gesture engines, with the thresholds.
- The automatic busy state draws `ui.spinner`'s ring. A button waiting on
  its request turned in .7 s with its gap on the right and a fixed 2 px
  stroke, a busy field drew a pale full ring, `ui.spinner` (and so
  `loading=True`) turns in 1 s with its gap at the top and the theme's
  stroke: three looks for « waiting ». A gate holds them together.
- A `ui.sidebar_footer_item` row lights on hover like a `ui.dropdown_item`
  (4 %, it was 6 %): the same row, in the same kind of panel. A gate now
  holds every `MenuItem` row to the dropdown's theme.
- A node a swap removes is disposed. Idiomorph and htmx remove nodes
  without telling the runtime, so their effects stayed subscribed: an
  effect that read the client state (`$bz.state`) kept its node, and the
  whole previous page, alive — +7 386 DOM nodes per `/select` ⇄
  `/dropdown` round trip on the playground, after garbage collection.
  After each swap the runtime now disposes the bound nodes that left the
  document.
- A page left by a navigation gives back its listeners on `document`.
  Every overlay subscribes to Escape and to the click outside from its
  `bz-init`; nobody ever unsubscribed, and each `/select` ⇄ `/dropdown`
  round trip on the playground left 84 more, each holding the previous
  page's DOM. The running `bz-init` now owns what `$bz.helpers.escapeKey`,
  `clickOutside` and `onWindow` subscribe, and its node gives it back when
  a swap leaves it out of the document or a `bz-for` / `bz-if` disposes it.
- The pickers read a typed date with ONE reader, `$bz.dates.typed`, in the
  page language's order. Five copies had drifted: `ui.week_picker` read
  `03/11/2026` the American way (the week of March 11th on a French page),
  the month and week pickers sent every keystroke to `on_change` instead
  of the date once the field was left, and `ui.calendar`'s next / previous
  month buttons computed in UTC — west of Greenwich, « next month » stayed
  on the same month.
- A disabled option of `ui.select` can no longer be picked from the
  keyboard: the arrows skip it, Enter never picks it, and « select all »
  leaves it out. The mouse already could not; the combobox already
  skipped them.
- The child of `app.run(reload=True)` leaves when its parent dies. A
  parent killed abruptly (a terminal closed, a `timeout`, a stopped
  preview) told it nothing, and it stayed: fourteen orphans in one day,
  holding the folders they were started in.

- A server state that a request reads and does not write pushes back its
  expiration. A tab whose clicks only read lost its `PageState` an hour
  after the last write, and the next click found the defaults. A
  `Backend.merge` with nothing to write and a `ttl` now renews the
  expiration of a row that exists, and creates none.

- A boosted link into a page that does not live in the current shell — a
  page without a layout (a full-screen view), or one of another layout
  chain — loads that page whole (`HX-Redirect`). It used to be rendered
  whole and swapped into the old outlet, under the shell it meant to
  leave.

- One colour of the theme now shows as one colour. The text step of a
  colour keeps as much of it as stays readable, per colour and per mode,
  starting from the colour itself (it was always 55 % of it, mixed with
  the text): an outline's label is the colour of its border wherever the
  colour reads. A toggle group's selection and a tree's selection bar are
  the solid fill, like every other selection; an outline badge's border is
  the colour itself, like a button's; no theme lays an opacity on a step
  any more. The default palette gives `primary` and `secondary` a dark
  value that reads on a dark page (the plum measured 1.86:1); an app that
  sets an accent in light only keeps it in dark.

- A tooltip's colour paints its panel only: its root no longer carries the
  colour bridge, which reached the trigger it wraps — a selected toggle
  button with a tooltip filled in the tooltip's near-black instead of its
  group's colour.

- A panel projected under `<body>` (popover, dropdown, select, combobox,
  tooltip) now keeps what its place gave it: a link in an open popover navigates
  inside the page like any link (it reloaded the whole document — it had
  left the page container's `hx-boost`), and a `name=` field in a popover
  inside `ui.form` leaves with the form's submit (it was dropped, silently).

- A card with `on_click=` is now a button to the keyboard and to a screen
  reader: `role="button"`, a place in the Tab order, Enter and Space click
  it, and its focus shows. It used to be reachable by a mouse only.

- A change inside an open overlay's panel (a box ticked in a popover) no
  longer ships the whole overlay, nor makes its panel blink: the ids of a
  teleported panel are patch targets, and when its content does change
  the live panel is morphed in place, keeping its position. Ticking a
  calendar: 73 KB → 1.8 KB, no blink.
- A menu opened from a popover (a `ui.dropdown` in its panel) no longer
  closes the popover when one of its items is picked: a click in a panel
  projected from inside another overlay counts as inside it, at any
  depth. A click truly outside still closes both.
- A popover, tooltip, select or date picker that fits on neither its
  side nor the opposite one no longer leaves the screen: it tries the two
  other sides, and is clamped on both axes. Seen on a panel set to
  the right of a card in the last column of a narrow window.

Found by an agent that built the comparison's helpdesk from the public
docs alone:

- `@download("/attachments/{aid}")` passes the path parameters to the
  function, typed by its annotations (a value that does not convert is a
  404), and `filename=` may name them. A parameter missing on either side
  raises at decoration, not as a 500 at the first click.
- In a menu, only the most specific matching entry is lit: `/tickets` and
  `/tickets/mine` were both lit on `/tickets/mine`.
- A sidebar entry's accessible name includes its badge ("My tickets 666");
  a bound badge keeps it in step.
- A `render=` callback that builds components and returns `None` raises,
  instead of rendering an empty cell.
- `ui.dropdown_item("Sign out")` takes its label positionally, like
  `ui.button`.
- A checkbox, a switch or a radio takes the click on its real input:
  Playwright's `check()` works.
- `ui.file_upload`'s refusals ("exceeds 5 MB", "Only one file
  allowed."…) are framework texts, in the app's language.
- `bretzel check --deep` and `bretzel dev` find an app that is not
  installed (a uv virtual project), as the ASGI servers do.
- `bretzel check` no longer reports an `hx-trigger` set on a component
  that declares a handler as a hand-written request.
- `python -m bretzel.render.vendor --help` prints its help instead of
  downloading.

Found while rebuilding a teacher's calendar:

- A `key=` holding a `:` or a `.` (`"slot-10:2026-11-16"`) no longer stops
  its `@refreshable` zone from redrawing: the id it produces stays
  selectable, and two keys never merge into one id.
- A date typed by hand in `ui.date_picker` and `ui.date_range_picker` is
  read in the page's language order: on a French page "02/07/2027" is
  2 July, not 7 February, and "13/07/2027" is no longer erased.
- `ui.radio_group(direction=…)` refuses an unknown value and names the
  accepted ones, instead of rendering an empty class.
- Dialog, drawer and popover panels are painted `surface`, not
  `interface`: the fields they hold no longer blend into them.
- A dialog rendered already open (`open=True` in a zone) fades in, like
  one opened from a closed state.
- `ui.toggle_button(tooltip=…)` shows the framework's tooltip, like every
  other component, instead of the browser's `title` bubble; an icon-only
  button is named by it.
- A date or time typed in `ui.date_picker`, `ui.date_range_picker` or
  `ui.time_picker` reaches `on_change=` once, normalised (`2026-02-11`,
  `09:30`), not keystroke by keystroke as typed ("1", "11", "11/0"…).

### Security

- A logout revokes, server-side, the session it leaves, and so does the
  rotation at login. The auth cookie is signed for its session and opens
  nothing in another one; `SessionMiddleware` records a revoked session in
  the state backend for a session's lifetime and replaces it with a fresh
  one. A copy of the cookies taken before logout (a shared computer) kept
  the account and its session state open for thirty days. Existing logins
  are asked to sign in again once. A `user_id` holding a `:` now signs in:
  the cookie was cut at the first one and refused in silence. One state
  backend read per request that carries a session.
- A user-scoped broadcast with no user is not sent: it would have reached
  every session.
- A `PageState` belongs to the session that rendered the page: its rows
  and its witness are keyed by the session and the page id. Keyed by the
  page id alone, they were readable and writable by any session presenting
  that id, which sits in the page's HTML.
- `bretzel check` has a 22nd rule, `interpolated-handler-script`: an
  `on_*=` JavaScript handler built from a value (f-string, `+`,
  `.format()`) that is not a literal, `json.dumps(…)`, `int(…)`, a module
  constant, a framework path or a client-state action. `on_click="…"` stays
  JavaScript by design; pasting `eleve.nom` into it made the name code (a
  quote broke the button, a crafted name ran). The hint gives the fix:
  `f"alert('Bonjour ' + {json.dumps(eleve.nom)})"`.
- `ui.tooltip(disabled=…)` no longer takes a string as client code: it
  takes a `bool`, a binding, or a `ClientExpression` —
  `disabled=ClientExpression("window.innerWidth < 600")`. It was the last
  prop where a string was code; a string now raises with that remedy.
  `on_click="…"` keeps its JavaScript strings, by design.
- A dev-mode app answers only the names it is reached by, like Django's
  `ALLOWED_HOSTS`: with nothing declared, `localhost`, `*.localhost`,
  `127.0.0.1`, `[::1]` and `testserver`; `trusted_hosts=[…]` names others,
  in either mode. A dev server on a laptop answered a request addressed to
  any name, so a page from another site could read it (DNS rebinding). A
  refused request gets a 400 that says what to declare. In prod mode with
  nothing declared, every name is still answered (the proxy decides).
  The check is Bretzel's own `HostMiddleware`: Starlette's
  `TrustedHostMiddleware` cut `[::1]:8000` at the first colon.
- The session cookie carries its id signed: an id this server did not
  mint is replaced by a fresh one. A session minted by the request itself
  opens no SSE stream (a page always comes first). Unsigned, the cookie was
  whatever the client sent, and the eight-streams-per-session ceiling
  counted nothing: one script opened 300 streams by inventing a session on
  every request. Existing sessions are re-minted once after the upgrade.
- The zone cache answers a fingerprint for the session that was served it
  only (`ZoneMaps.scoped(session_id)`). A fingerprint is computable
  offline and the client presents it; with one cache for the whole app,
  an attacker learned whether another session's zone showed a guessed
  value (a patch came back, or the whole zone).
- A value given to a component never comes out as markup.
  `ui.calendar(weekday_names=…)` (and the date, range and week pickers
  built on it) pasted the names raw into HTML; `ui.heading(level=…)` built
  its tag from the value (`level="1><img onerror=…><h1"`), and now refuses
  anything but 1 to 6; the serializer refuses an element whose tag is not
  a name; the time picker's runtime pasted `hour_label=` / `minute_label=`
  raw into its buttons. The runtime has one escaper,
  `$bz.helpers.escapeHtml`, used by the calendar and the time picker.
- A form's token names the actions rendered under the form, and counts
  only when one of them is posted. It vouched for its fields on the whole
  page: the token of a search form holding a `role` select, joined to the
  POST of `save(form: Account)` whose form shows only `name`, wrote
  `role=admin`. A borrowed token now counts for nothing: the action
  reloads, nothing is written. `form_token` takes a required `action_id=`.
- After `auth.login()` or `auth.logout()`, the rest of the request reads
  and writes the NEW identity's state. The state registry kept the
  identity the request arrived with: a `SessionState` written in the login
  handler landed in the pre-login session (the one an attacker who planted
  a session cookie chose, so the rotation protected nothing), and a
  `UserState` raised `AuthRequiredError`.
- A `ClientState` key must be a name (letters, digits, `_`, not starting
  with a digit); any other is refused at construction. The key is written
  into the browser's code (`$bz.state.<Class>.<key>.<field>`): a dash or a
  leading digit broke the path silently, and a key built from a user's
  words (`Notes(key=folder)`) ran them. Build keys from ids:
  `Notes(key=f"task_{task_id}")`.
- A `javascript:` or `vbscript:` URL is never written where the browser
  follows or loads one (`href`, `src`, `action`, `formaction`…):
  `serialize_attrs` leaves the attribute out, and `bz-attr:` removes it
  when a client state sets one. `ui.link("Site", href=website)` with a
  website a user typed ran it on click, as did `ui.button(href=)`,
  `ui.icon_button(href=)` and `ui.card(href=)`. The scheme is read as the
  browser reads it (blanks and case dropped); `data:` and every other
  scheme are untouched.
- A urlencoded form holds at most 1 000 fields, the ceiling Starlette
  already puts on a multipart one. A single anonymous 32 MiB body of
  `a&a&…` was parsed on the event loop before any check: 25 s with the
  worker frozen, 1.3 GB at peak.
- A file part declared `filename=""` is held to its field's limits. It
  was taken out of every check (`accept`, `max_bytes`, `max_files`) and
  reached the handler: 20 MiB of `.exe` in an image field. The empty part
  a browser sends for "no file chosen" is still ignored; a non-empty part
  without a name is refused.
- The default error page escapes its title and message. `abort(404,
  f"No customer {cid}")` pasted the detail raw, so a request for
  `/customers/<img src=x onerror=…>` ran its script.
- A string passed to a component is data, never client code. A heuristic
  sent any string that "looked like" JS (`f(`, `||`, `==`, `$el`…) out as
  `bz-attr:<prop>`, compiled by the runtime: `ui.avatar(name="0||alert(1)")`,
  an image's `alt`, a select's `value`, a placeholder or a dialog's title
  ran a user's script in every browser that showed it. Client code is a
  `ClientBinding` / `ClientExpression`, or a `bz-attr:<prop>` written by
  hand (`**{"bz-attr:placeholder": "a && b"}`). `Dropdown` and `Popover`
  also pasted `position` / `align` between quotes of their `bz-effect`
  unescaped.
- The JSON inside `<bz-envelope>` and `<bz-patch>` writes `<`, `>` and `&`
  as JSON escapes. Both are ordinary elements, so a `ClientState` field or
  a notification holding `<img src=x onerror=…>` opened a real tag and ran
  its script; an `&amp;` also came back as `&`. Only `</` was defused.
- `/_bretzel/icons` answers only the icon component's request,
  `/<prefix>.json?icons=a,b`, each word in Iconify's grammar; anything else
  is a 404. The public route relayed any path and query: its prefix,
  joined as it came, read any `.json` of the disk (`..%2F`, `..\`, `C:/`)
  and, on Windows, opened an SMB connection to the host a `\\host\share`
  named; each invented query left a file in the cache; and its upstream
  call ran on the event loop, so one slow answer froze the worker. The
  call now runs on a thread, and the cache keeps icons, one file per set
  (`.bretzel/vendor/icons/<prefix>.json`): the old per-request files are
  no longer read and can be deleted.
- An action's signature is bound to the session it was rendered for, and so
  is the datatable's "Export CSV" link. A captured request, or an export
  link pasted into a ticket, no longer works in any other session — the
  export route does not pass through the page's access control. A login or
  logout rotates the session, so a page rendered before it reloads on its
  next action, as it already did for its CSRF token. The form token that
  lists a form's writable fields is bound the same way. `sign_action`,
  `verify_action`, `fields_token`, `form_token` and `idempotency_key` take a
  required `session_id=`.
- A real-time signal crossing Redis carries its filters as a JSON array.
  They were joined by tab characters, and two of them come from the client
  (the `X-Bretzel-Tab` header, the session cookie): a forged tab id shifted
  the fields on the other side, dropping the session filter and choosing
  the event. Workers of the previous release read the new filtered signals
  as unknown names until they are replaced — a rolling deployment misses
  a few refreshes, nothing else.
- An action that raises a `BretzelError` answers its message only with
  `expose_errors` — the rule a page already followed. In production the
  client reads "The action failed." and the message goes to the log.
- An OIDC door fills `OAuthProfile.email` only when the provider vouches
  for it (`email_verified`). A door that admits a domain no longer admits
  whoever typed that address at a provider that does not check. The claim
  stays in `profile.raw`.
- A `UserState` broadcast reaches only the tabs of its own user, on any of
  their devices: every SSE stream is opened in the name of its user. Until
  now every subscribed visitor learned WHEN another user acted.
- A weak `secret_key` in production — a `change-me` placeholder, under 32
  characters, or fewer than 10 distinct characters — is logged at startup
  with the command that generates one. A warning, not a refusal.
- A `@download` takes its type from the name its decorator DECLARES, not
  the one requested (`/files/x.html` no longer serves HTML), and its
  `Content-Disposition` — the datatable export's too — can no longer be
  broken out of by a quote in the name: the exact name rides encoded in
  `filename*`.

- A CSV export (`ui.datatable`'s, or a `@download` returning a `list[dict]`)
  no longer lets a cell run as a formula: a text cell that opens with `=`,
  `+`, `-`, `@`, a tab or a carriage return gets a leading `'`, which a
  spreadsheet shows as text (OWASP's rule). Numbers — the value's own type,
  or a signed plain number written as text — pass as they are.

- `ui.file_upload`'s `accept`, `max_size_mb`, `max_files` and `multiple` are
  enforced on the server too, in form mode: the enclosing `ui.form` signs
  them into its `_bz_fields` token, and the action answers 400 before the
  handler runs when a field gets more, bigger or other files than it
  accepts. A file is taken only into a field the form declares — dropping
  the token or naming another field is refused. Until now these limits
  lived only in the browser. The `upload_url=` mode posts to the app's own
  route, which keeps checking its uploads itself.

- `redirect()`, `redirect_response()` and `push_url()` accept only a path of
  this site — one leading `/`, not `//` nor `/\`, no control character.
  Until now they refused only CR / LF / NUL, so `redirect(next)` with a
  `?next=javascript:…` ran script in the app's origin (htmx executes
  `HX-Redirect`), and `//host` sent users elsewhere. **Breaking**: a
  redirect to another site now raises `ValueError`.

- `/_bretzel/refetch` serves a `@refreshable(broadcast=…)` zone only to the
  session it was rendered for: its `data-bz-subscribe-url` carries a
  signature tied to that session, and any other request gets a 403 `reload`.
  Until now any client that could spell the URL — module names are public —
  got the zone, without passing through the access checks of its page.

- A handler that takes a state (`def save(form: Account)`) is hydrated only
  with the fields the page rendered for that request. Until now it took
  every declared field present in the POST, so a form showing `name` let a
  client also write `role=admin`. A control signs its own `name` into its
  action, and `ui.form` adds a hidden `_bz_fields` input with the signed
  list of the controls it renders. A field outside both is not written and
  is logged once; a page rendered before this release asks to reload when
  it posts fields. A `<form>` written by hand carries no list: use
  `ui.form`, or read its fields as handler parameters.

## [0.1.0a4] - 2026-10-25

### Added

- A control whose action is still unanswered after 200 ms shows it is busy,
  with nothing to write: a button keeps its width and shows a spinner, a text
  field shows one at its end, a checkbox or a switch pulses, anything else
  dims — and a zone the runtime asks again (another tab's change) dims while
  it comes. A faster answer shows nothing. The element carries `aria-busy`.
  `loading=False` on a component turns it off for it and everything inside;
  a button with `loading=True` or `loading=ui.pending()` keeps its own
  spinner.
- `refresh(zone, rows=[key, …])` refreshes only those rows of the zone's
  keyed `ui.table`: the table renders and ships them alone, and a row that
  left the list is removed. The other tabs of a broadcast zone refetch
  those rows only. A new row asked for, a row that left and a new order
  ride a list patch on the table's body; a new row not asked for, an
  empty list or an unknown client copy ships the zone whole, and a whole
  refresh in the same action wins.
- In debug mode, every action or refetch response carries a
  `Server-Timing` header with each zone's render time, shown by the
  browser's DevTools next to the request.

### Changed

- A parent whose list of children changed — one more, one less, a new
  order — no longer ships whole: the zone diff compares the two lists and
  sends a list patch (keep this child, morph that one, insert this one),
  whether the children have an `id` or are found by position. The kept
  children keep their element, so their state and listeners stay. Removing
  a table in a layout editor: 32 KB → 0.4 KB; posing one: 1.7 KB.
  Drag and drop keeps working: a card the browser moved already is found
  by its `id`, wherever it is. `refresh(zone, rows=[…])` rides the same
  list patch: a new row or a new order no longer ships the zone whole. A
  keyed `ui.table`'s `<tbody>` carries an `id` (`<table id>__body`).
- A changed element with no `id` is sent alone too, found by its position
  under its nearest identified ancestor (the runtime checks the shape of
  each level before morphing, and ships the zone whole if the page moved).
  One status change on the comparison helpdesk: 8.9 → 3.9 KB gzipped — the
  ticket panel, with no ids inside, used to go whole.
- Building a component is cheaper: the bucket of each keyword, the
  client-expression check of a string, the props' defaults, a theme
  table's legal steps and a component's resolved theme are computed once
  instead of for every component. A 50-row table zone renders about 7 %
  faster.
- A refreshed zone sends only the elements that changed, each morphed in
  place by its `id`, instead of the whole zone: one status change on the
  comparison helpdesk went from 18.6 KB to 6.3 KB gzipped. A fingerprint the
  server does not know ships the zone whole, as before. An unchanged zone
  containing a button is also recognised as unchanged again: its render
  second made it look changed one second later.

### Fixed

- Another tab now sees a change whose action renders slowly: the "this
  state changed" signal to the other tabs went out before the action had
  rendered and committed, so a tab that asked again within that time read
  the old value and stayed on it. The signals now wait for the commit.
- A client expression on a navigation item's `active=` (`ui.sidebar_item`,
  `ui.navbar_item`, `ui.bottom_bar_item`) now drives its active state and
  `aria-current`, as a state binding does. It used to go out as a bare
  `bz-attr:active` that nothing read: the item never lit up.
- A control follows a value the server changed, even when the app passes
  a computed value (filters read from the URL, `int(state.x)`,
  `state.a or state.b`, a comparison): "Clear filters" left the toggles
  pressed, "Clear selection" left the boxes ticked. The rule is now
  explicit — the server wins when the value it renders has changed since
  its last render; a local choice the server did not touch survives an
  unrelated refresh, and the field being typed into never moves.
- An icon no longer pushes its label sideways when it scrolls into view:
  the icon web component's lazy mode is turned off when the page boots, so
  every icon — a component's, an app's, raw markup — is drawn at once, and
  keeps a 1em box until drawn. Off screen, it left icons empty (zero wide),
  and re-emptied them when scrolled away.
- A full page draws its icons while it parses, with the text beside them:
  each icon of the shipped Lucide set carries its glyph in a declarative
  shadow root, and the component, once its deferred script runs, draws it
  again from data the page hands over — no request, no empty frame. Before,
  the first frames showed the text one icon to the left, then the icon
  pushed it. Until the component registers, an icon also keeps its 1em box
  (it was an inline element, which ignores a minimum width).

### Removed

- `bretzel check`'s `state-lost-by-a-cast` rule: it worked around the
  behaviour fixed above, and its warning ("will not re-adopt after a
  refresh") is no longer true.

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

[Unreleased]: https://github.com/JeanHoccart/bretzel/compare/v0.1.0a5...HEAD
[0.1.0a5]: https://github.com/JeanHoccart/bretzel/releases/tag/v0.1.0a5
[0.1.0a4]: https://github.com/JeanHoccart/bretzel/releases/tag/v0.1.0a4
[0.1.0a3]: https://github.com/JeanHoccart/bretzel/releases/tag/v0.1.0a3
[0.1.0a2]: https://github.com/JeanHoccart/bretzel/releases/tag/v0.1.0a2
[0.1.0a1]: https://github.com/JeanHoccart/bretzel/releases/tag/v0.1.0a1
