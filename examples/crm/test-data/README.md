# Test data for the "Import" screen

Two files, checked against the CRM's real parser (`parse_csv`) and its
real judge (`judge`), **signed in as a sales rep** — the default case.

⚠️ Both are written for **Aicha Benali** (`a.benali`). If you sign in as
another rep, replace the `owner` column with your own name: scoping
**refuses** a row that is not yours instead of rewriting its owner, and
the import is all-or-nothing — so a single row under the wrong name
blocks the whole file. A director who has picked no portfolio, on the
other hand, sees everything go through.

## `valid-accounts.csv` — 10 rows, 0 refusals

Imports in full.

## `accounts-to-fix.csv` — 9 rows, 8 refusals

One refusal per cause, to watch the check screen do its job:

| row | what it tests |
|---|---|
| Kieffer House | (the good one — the control) |
| *(empty name)* | missing name |
| Weber Haulage | unknown industry ("Transport" is not "Logistics") |
| Atlas Marine | a country outside the four accepted |
| Mirabel Studio | unknown size ("Startup") |
| Sanchez Group | unknown owner |
| Lorraine Workshops | ARR with spaces — `1 250 000` |
| Ried Farm | empty ARR |
| Aubert Practice | known owner but **outside the portfolio** |

The control is there so one can see the refusal is targeted and not
global.

## The accepted vocabulary

From `examples/crm/core/domain.py` and `import_data.py`:

- **industry**: Manufacturing, Health, Finance, Logistics, Retail,
  Energy, Education, Construction, Media, Food & drink
- **country**: France, Belgium, Switzerland, Canada
- **size**: Micro, Small, Mid-market, Enterprise
- **owner**: Aicha Benali, Marc Dubois, Sofia Rossi, Lea Martin,
  Tom Nguyen, Clara Weiss
- **arr**: digits, nothing else — no separator, no currency
