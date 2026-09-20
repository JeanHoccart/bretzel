# `examples/crm/` — the real-usage instrument

**All four slices are shipped**: the data base layer, the responsive
shell and the twelve screens (2026-08-19), then the accounts and
authentication (2026-08-20). The brief, the rule and the log of findings
live in
[`.claude/work/chantier-crm-2026-08-19.md`](../../.claude/work/chantier-crm-2026-08-19.md).

This is not an 18th demo. The 17 apps in `examples/` are isolated
screens — `contacts` (326 lines), `kanban` (228), `dashboard` (222) are
already pieces of a CRM, but none has navigation, state shared between
screens, or selection.

The rule that sets it apart: **no working around anything**. A `classes=`
placed to make up for a component is a lost measurement — it gets NOTED
in the worksite log, it does not get written. The four slices produced
**twenty-three** of those, for a single acknowledged patch-up class (the
height of the `ui.resizable`).

## Running it

```
py -m examples.crm.main        # port 8016
```

The first start seeds **262 000 rows** into `core/crm.db` (~4 s, 33 MB,
gitignored). Later starts do not re-seed: `core/db.py`'s `SEED_VERSION`
marker decides. Bump it to rebuild.

## Signing in

Everything is closed except `/login`: the guard is a **default-closed
middleware**, not a `@page(auth=…)` — a page added tomorrow is protected
without anyone thinking about it.

| login | role | what they see |
|---|---|---|
| `a.benali`, `m.dubois`, `s.rossi`, `l.martin`, `t.nguyen`, `c.weiss` | sales rep | **their portfolio only**, on all twelve screens. A sheet outside the portfolio returns **404**, not 403: saying "forbidden" would confirm it exists |
| `management` | management | everything, or the portfolio picked in the sidebar's selector |

One password for all: **`bretzel`**. The hashes are stdlib
PBKDF2-HMAC-SHA256 (240 000 rounds) — the app brings its own real auth,
the framework only supplies `bretzel.auth` (four functions) and the state
segmentation.

**Scoping is a PARAMETER**, not a global the repos go and read: every
read function takes its `owner: str | None` and puts it in its `WHERE`.
It is more verbose, and that is the point — one can READ a signature and
see whether it is scoped. `features/access.py` is the single door:
`visible_owner()`.

## Slice 1's screens

| route | screen | what it puts under strain |
|---|---|---|
| `/` | Pipeline | `dropzone` + `drag_each` in scrolling columns, the drop persisted in SQL with a rank by median insertion |
| `/accounts` | Accounts | `ui.datatable` in **callable mode** over 50 000 rows — sort, search, filters and CSV export translated into SQL |
| `/contacts` | Contacts | the **selectable list** (the named blind spot) and the master-detail shell, in a `ui.resizable` |
| `/contacts/{id}` | Contact sheet | the **first path-parameter page** of the 18 apps: tabs, inline editing, `file_upload` in a narrow column |

## Slice 2's screens

| route | screen | what it puts under strain |
|---|---|---|
| `/accounts/{id}` | Account sheet | **nesting**: two `ui.table` inside two `ui.card` inside a `ui.grid` |
| `/activities` | Activities | `date_range_picker`, `calendar` and `date_picker` **bound to server state**, in a filter bar and a form — not mounted on their own |
| `/reports` | Reports | the **five chart families** over `GROUP BY`s, not over hand-built lists |
| `/search` | Global search | the use case that would decide `ui.command_palette` — built without it, to measure what is missing |

## Slice 3's screens

| route | screen | what it puts under strain |
|---|---|---|
| `/import` | Import | `ui.stepper` + a preview in `ui.datatable` **list tier** — the component's other tier, which screen 2 mounts as a callable |
| `/settings` | Settings | `ui.form` under density: ten fields, server validation, simple and multiple `toggle_group`, `switch`, `select` |
| `/realtime` | Realtime | **SSE**: a `broadcast=True` zone that another tab makes move |
| *(the shell)* | Responsive shell | `Screen().is_mobile`: an eleven-route rail ⇆ a five-entry tab bar, one single tree in the DOM |

## Slice 4's screens

| route | screen | what it puts under strain |
|---|---|---|
| `/login` | Sign-in | `bretzel.auth` — `connect` / `disconnect` and session rotation, which **none of the 18 examples exercised**; the only page with no `layout=` |
| *(the shell)* | Identity | `ui.sidebar_footer` + `ui.sidebar_footer_item`, and a `ui.select` **inside a collapsible sidebar** |
| *(the shell)* | Theme | `ColorScheme` in light / dark / **system** — a framework `ClientState` bound to a `ui.toggle_group`, hence the app's only setting that switches with no server round trip |

## Structure

```
crm/
├── main.py                 Bretzel(...) + app.include(...) + the seed at startup
├── core/
│   ├── theme.py            the only real global
│   ├── ui.py               the KPI card, shared by four screens
│   ├── domain.py           the business vocabulary (stages, statuses, industries…)
│   ├── db.py               infra: connection, schema, indexes, init_db
│   ├── security.py         the PBKDF2 hashing and its check
│   ├── texts.py            the one framework text this app overrides
│   └── seed.py             the deterministic factory for the 262 000 rows
└── features/
    ├── shell.py            the rail + the outlet + the identity
    ├── access.py           logic — the SINGLE door of the access policy
    ├── auth_data.py        data  — the accounts, and the password check
    ├── login.py            page  /login
    ├── accounts_data.py    data — the accounts repo, including the callable `rows=`
    ├── contacts_data.py    data — contacts, activities, notes
    ├── deals_data.py       data — the pipeline and the reordering
    ├── pipeline.py         page  /
    ├── accounts.py         page  /accounts
    ├── contacts.py         page  /contacts
    ├── contact_detail.py   page  /contacts/{id}
    ├── account_detail.py   page  /accounts/{id}
    ├── activities_data.py  data — the activity log
    ├── activities.py       page  /activities
    ├── reports_data.py     data — the reports' five aggregates
    ├── reports.py          page  /reports
    ├── search_data.py      data — the prefix search, three tables
    ├── search.py           page  /search
    ├── import_data.py      data — read a CSV, judge it, write it
    ├── import_screen.py    page  /import
    ├── settings.py         page  /settings
    ├── realtime.py         page  /realtime
    ├── app_map.py          page  /_map — the feature map
    └── errors.py           error — 404 / 403 inside the shell
```

## Verification

The twelve screens were looked at in a real Chromium before being called
shipped (charter discipline #3). On all of them: zero JS errors, no
double scrollbar, no horizontal overflow. And per screen, the gesture
that counts — drag and drop with the mouse **persisted in SQL**, sort and
search that move the SQL, selection without navigation, a `file_upload`
that holds in its narrow column, nested sub-tables on a real account, a
click in the calendar that closes the date window onto a day, five charts
rendered over `GROUP BY`s, a search that answers as you type (one
debounced request, not one per letter), a pasted CSV judged row by row
before anything is written, a boolean setting that stays `False` after
saving, a tab bar 812 px from the top on an 812 px screen, and — the only
one needing two tabs — counters that move on their own when the other tab
drags a card.

**Slice 4 added 54 measurements**: 28 on the repos (every scoped read
does return its portfolio, and the SAME one unscoped returns more) and 26
in the browser — the anonymous visitor sent back to `/login` from all
twelve screens **and** from `/_bretzel/sse`, `/_bretzel/refetch/…` and
`/_bretzel/datatable.csv`; a wrong password refused without saying which
of the two causes; no other owner's name on any of the twelve screens; a
`404` on somebody else's sheet and a `200` on their own; the sign-out
that closes it; and management's selector re-scoping the screens it
touches. Plus **14 measurements on the writes** (each of the four refuses
outside the portfolio without mutating the row) and **11 on the theme**
(the `.dark` class, the recomputed background, the persistence, following
the OS both ways).

⚠️ **And it was not enough.** Four adversarial reviews of the same diff
found a security hole the 54 measurements could not see — scoping was
missing on all four writes, and `contact_id` arrives from the browser.
The two instruments see disjoint things: measurement exercises the paths
the interface offers, review looks at the ones it does not. The worksite
log details all four.

The central invariant is now held by a **gate**:
`tests/consistency/test_crm_owned_reads_declare_their_scope.py` — it
reads the AST of `features/*_data.py` and demands that a function
touching an owned table declare its scoping, barring a named allowlist.

⚠️ An ad hoc verification server must avoid ports **8944–8996**:
thirty-four of them belong to `tests/probes/`'s benches. A server left
running on one of them makes a probe go red for nothing — measured once,
on `probe_tipiso`, which was interrogating the CRM instead of its own
bench.

The script used for that was **throwaway**, and it stayed that way. This
app has no probe in `tests/probes/`: it is not framework, it is the
instrument the framework gets measured with. What it produces is the
worksite's findings — not a 54th gate to maintain.
