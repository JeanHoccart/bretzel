# Audit harness — drive every playground, verify every binding

The interactive audit lives in `tests/audit/`. It boots the playground
in-process, opens each component page in headless Chromium, exercises
its controls, and asserts the rendered component reacts the way the
binding model says it should. New components inherit coverage
**automatically** if they follow the playground gabarit — no per-
component test code to write.

This doc is the contract : how to wire a new component into the audit,
which probes fire, and how to ack a structural limitation without
silencing the rest of the audit.

---

## Run

```bash
py -m tests.audit.driver button       # one component
py -m tests.audit.driver tier_2       # one tier
py -m tests.audit.driver --all        # full sweep
```

Parallel sweep — **via pytest, depuis le 2026-08-27** :

```bash
py -m pytest -m audit -q -n 4
```

`pytest-xdist` est installé et `audit_server` prend un port LIBRE, donc
les workers ne se marchent pas dessus. Mesuré sur `-m browser`, même
harnais : **395 s → 188 s** à `-n 4`. `-n 8` n'apporte rien de plus —
le goûlot est le navigateur, pas le CPU.

⚠️ Le lancement « un tier par sous-agent » qui vivait ici a été essayé
le 2026-08-27 et **s'est étranglé** : 8 Chromium + 8 uvicorn en même
temps sur cette machine, aucun tier terminé en 25 min. `-n 4` borne la
concurrence, `&` ne la borne pas.

Le navigateur est par ailleurs **partagé par processus** depuis la même
date (`harness._shared_browser`) : `browser_page` ouvrait un Chromium
neuf à chaque appel, soit 284 démarrages pour `-m browser` + `-m audit`.
Mesuré en A/B alterné : 633 ms → 408 ms par appel. **N'ouvre jamais
`sync_playwright()` dans un test** — utilise `browser_context()`.

Output : `[PASS] <name> (<route>)` or `[FAIL]` followed by which probes
failed and why. Exit code is non-zero if any audit failed.

---

## What runs per component

The driver dispatches every applicable probe :

| Probe | Catches | When |
|---|---|---|
| `probe_no_body_overflow` | double-scrollbar viewports | always |
| `probe_no_clip` | demo wrapped in an `overflow-hidden` clipped to 0 | always |
| `probe_color_distinctness` | theme uses `{bg_color}` only on transient states | when `has_color_axis=True` AND `color_at_rest=True` |
| `probe_size_distinctness` | size paliers collapse to one computed style | when `has_size_axis=True` |
| `probe_tab_order` | sr-only `<input>` ≠ `tabindex=-1` etc. | when `is_interactive=True` |
| `probe_client_binding_lands_on_carrier` | `bz-attr:disabled` on a `<div>` (no-op) | always (static, no clicks) — ⚠️ le contrat est d'abord gardé sans navigateur par `tests/consistency/test_binding_lands_on_carrier.py` (même table `tests/audit/carriers.py`) ; ce probe-ci ajoute le DOM *monté* |
| `probe_client_switches_drive_carrier` | client state flips but no DOM attr follows | when page has a "Client playground" h2 |
| `probe_server_props_drive_dom` | morph silently fails to apply a server-state change | when page has a "Server playground" h2 |

Probes 6-8 are the **interactive** layer added in 2026-06. They are
the reason carrier-vs-wrapper bugs and morph-guard regressions can no
longer slip through.

---

## How interactive probes work

### Enumerator

`_enumerate_controls(page)` walks the Server playground card AND the
Client playground card, finding every `input[name]` / `select[name]` /
`textarea[name]`. Each control is captured as a `PlaygroundControl` :

```python
PlaygroundControl(panel="client", name="disabled", kind="checkbox",
                  current_value="off", candidates=("on", "off"),
                  input_type="checkbox")
```

The probe consults this list — it doesn't hardcode any prop name.
**That's why new components inherit coverage** : if your playground
follows the gabarit (controls bound to state fields, named like the
fields), the probe finds them.

### Type-aware sentinels

For a control with no candidate values (text inputs, textareas), the
probe generates a sentinel pair based on the `<input type>` :

| `input type` | sentinels |
|---|---|
| `number` | `"42"`, `"137"` |
| `date` | `"2026-01-15"`, `"2026-07-04"` |
| `email` | `"alpha@audit.test"`, `"beta@audit.test"` |
| `color` | `"#ff0000"`, `"#00ff00"` |
| `range` | `"25"`, `"75"` |
| anything else | `"AUDIT_VALUE_ALPHA_42"`, `"AUDIT_VALUE_BETA_137"` |

This stops the probe from typing `"AUDIT_VALUE_…"` into a numeric
input and crashing the server's `int(value)` coercion before reaching
the binding.

### Carrier-landing whitelist

Pure static check : every `bz-attr:<attr>` directive in the page is
mapped to the set of tags where `<attr>` is meaningful. Sourced from
MDN ; see `_FORM_CARRIER_ATTRS` in `tests/audit/interaction.py`.

Custom elements (anything matching `bz-*` with a hyphen) are auto-
trusted — they handle attribute reactivity via
`attributeChangedCallback`.

### Snapshot

For interaction probes, the "did the carrier react ?" oracle compares
the demo subtree before / after the toggle. The snapshot includes :

1. Every attribute on every element under the demo root.
2. `demo.textContent` (so `bz-text` bindings register).
3. Every direct child of every `template[bz-teleport]`'s target —
   tooltip / popover / dropdown panels live as `<body>` siblings
   after the runtime binds, not as descendants of the trigger.

`bz-id` / auto-generated `id` are stripped from the
signature so framework cache busters don't read as "the prop did
something".

---

## Adding a new component

1. Write the component + its playground following the gabarit.
2. Add a `ComponentSpec` entry to `tests/audit/checklist.py`. Set the
   feature flags (`has_color_axis`, `has_size_axis`, `is_interactive`,
   `is_overlay`). The `root_selector` must match the demo instance in
   each card.
3. Run `py -m tests.audit.driver <name>` once. If any probe fails,
   triage : real bug → fix the component ; structural probe limit →
   add the prop to `skip_dynamic_props`.

That's it. The audit runs on every component the next time anyone
sweeps.

---

## Structural probe limits (the `skip_dynamic_props` allowlist)

Some bindings can't be observed by a black-box probe without the
probe deciding what's "correct". These get acked per-component in
the `skip_dynamic_props` tuple on the spec :

- **Render branch needs a non-empty initial value** — Avatar's `src`
  binding can't flip the picture if the SSR rendered no `<img>`
  because the initial src was empty. The forwarding is correct ; the
  probe just can't observe a missing element. Skip `src`.
- **Int-typed playground state with text-input rendering** —
  Pagination's `value` / `total_pages` are typed `int` on
  `PaginationClient` but the playground renders them as
  `<input type="text">`. The probe's string sentinel hits
  `int("AUDIT_VALUE_…")` in `_coerce_scalar` and crashes the server.
  Skip those props.
- **Teleported panel content** — Tooltip's `text` lands in a panel
  that bz-teleports to `<body>` after the runtime binds. The probe includes
  teleport targets (see "Snapshot" above) but the panel is hidden
  at rest, so the rendered text isn't observable without forcing
  hover. Skip `text`.

When you `skip_dynamic_props=("foo",)` a control, add a Why comment
right above the tuple. It's documentation for the next maintainer
who'll ask "should we still skip this in 2027 ?".

---

## What the audit has already caught

Production-blocking bugs the static unit tests missed and the
interactive probes flagged within their first sweep :

| Bug | Found by | Fix |
|---|---|---|
| `file_upload` variant=button kept dropzone classes after switch | `probe_server_props_drive_dom` (via the morph guard trap path) | `02_morph_hook.js` releases `:X` when new render drops it ; cf. [traps.md](traps.md) |
| `file_upload` disabled / multiple ClientBinding landed on the wrapper `<div>` (no-op on a div) | `probe_client_binding_lands_on_carrier` | Forward bindings to inner `<input type="file">` |
| `date_picker` / `date_range_picker` auto-emitted `bz-attr:value` on the wrapper `<div>` | `probe_client_binding_lands_on_carrier` | `root_attrs.pop("bz-attr:value")` — the component manages val sync via bz-init |
| `avatar.src` ClientBinding stayed on wrapper `<span>` | `probe_client_binding_lands_on_carrier` | Forward to inner `<img>` |
| `progress.value` ClientBinding produced no `aria-valuenow` updates | `probe_client_switches_drive_carrier` | Emit `:aria-valuenow="Math.round(...)"` binding client |

All five would have shipped silently with TestClient-only coverage.
