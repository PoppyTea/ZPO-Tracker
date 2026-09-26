# zpo-tracker

Local Python + SQLite desktop tool (tkinter) replacing the manual monthly
Excel copy-paste of courier/pickup-point (ZPO) rows in a Poczta Polska
settlements department. Runs fully offline on locked-down Windows machines
for non-technical users. Solo project, single maintainer (Papaver).

## Local Contracts

1. **Tasks live in Linear, never in this repo.** Project ZPO-Tracker, team
   `ZPO` (<https://linear.app/poppy-tea/project/zpo-tracker-07c6d93278dd/overview>),
   driven through the `linearis` CLI, not the Linear MCP. Linear is not a
   logbook: an issue answers "what must be done?" and has a closing
   condition; progress goes into comments, durable reasoning into `docs/`.
   No TODO lists, backlog files or status tables anywhere in the repo.
2. **Version numbers live only in git tags.** Milestones are scopes of work.
3. **The agent never pushes to `main`.** Every change goes through a branch
   and a PR, however small. The agent acts under Papaver's GitHub identity,
   which is on the `main-protection` ruleset's bypass list, so GitHub will
   not stop an agent push; this rule is the only guard.
4. **TDD is mandatory for new production code**: red test → watch it fail →
   minimal implementation → green → refactor. Never implementation before a
   test without Papaver's explicit permission. Only exception: pure
   schema/config definitions (SQL DDL).
5. **Not deployed yet — every `0.1-alpha.x` is a pre-user phase.** Nobody
   keeps working data in the program, so "we must migrate/merge what users
   already have on disk" must not constrain a design decision; test
   databases are disposable. Existing migration/repair paths (`repo.migruj`,
   `repo.napraw_dane`, `app._przenies_ze_starej_lokalizacji`, the
   `transakcje.zrodlo IS NULL` cohort) stay in the code. Remove this item
   on Papaver's word only.
6. **Language:** this file is English; every other file (code comments,
   docstrings, `docs/`, child `CLAUDE.md`, commit messages) is Polish.
   Talk to Papaver in Polish.
7. **The repository is public.** Never commit anything from `data/` or
   `docs/internal/`, and never quote real names, addresses, PNI numbers or
   internal Poczta Polska hostnames in code, docs, commits or PR text.
8. **DOX:** each directory's `AGENTS.md` is a symlink to its `CLAUDE.md` —
   edit `CLAUDE.md`. After a change that alters a contract, a verification
   command or the directory layout, update the nearest `CLAUDE.md` in the
   same commit and delete text the change made stale. These files hold
   contracts, verification commands and pointers only — never state,
   history, dates, test counts, or descriptions derivable from the code.

## Pointers

| Name | Governs | File | Binding in | Apply when |
|---|---|---|---|---|
| proces | issue hierarchy (feature/element/task), who closes what, issue conventions, zero-state docs, review rules R1–R4 | `docs/proces.md` | whole repo | creating, closing or retitling a Linear issue; writing a PR description; creating a `.md` file |
| domain-model | real source-data layout and its traps (PNI reliability, template rows, formatting) | `docs/domain-model.md` | `src/zpo_tracker/` import, normalization, deduction | changing how source spreadsheets are read or interpreted |
| tech-decisions | chosen stack and every rejected alternative | `docs/tech-decisions.md` | whole repo | adding a dependency or proposing a different technology |
| environment | production Windows constraints vs dev machine, venv/tkinter trap | `docs/environment.md` | build, tests, distribution | building the `.exe`, GUI tests skipping, anything needing network on the workstation |
| ux-ui | "idiot-proof" UX direction, validation approach | `docs/ux-ui.md` | `src/zpo_tracker/gui/` | changing what the user sees, a message, or when a field blocks |
| roadmap | selection filter for next work, cross-version design rules | `docs/roadmap.md` | planning | choosing or scoping the next piece of work |
| normalization-v2 | proposed schema v2 and its open risks | `docs/normalization-v2.md`, `schema_v2_draft.sql` | `schema.sql`, `src/zpo_tracker/repo.py` | changing the database schema |
| reference-data | external datasets for the suggestion engine | `docs/reference-data-sources.md` | `src/zpo_tracker/podpowiedzi.py` | adding a suggestion data source |
| baska | BaŚKa / DeliveryPath vendor docs (local only, gitignored — absent in a fresh clone) | `docs/internal/baska/AGENTS.md` | `src/zpo_tracker/rejonarz.py` | working with a BaŚKa export or the DeliveryPath API |

Child `CLAUDE.md`: `src/` (package and tests), `demo/` (throwaway
prototypes), `data/` (gitignored real-data scratch space).

## Verification

```
python -m venv .venv && source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt && pip install -e .
pytest                     # full suite
pytest -m "not slow"       # without the large-import scale check
```

- All tests must pass with **zero skips**; a skip means a broken
  environment, not a neutral state.
- `.venv/` must be built by the system Python. `uv`'s managed Python has a
  tkinter SIGABRT on the dev machine that silently skips the GUI tests; if
  they skip, check `.venv/pyvenv.cfg` (see `docs/environment.md`).
- After editing `.coderabbit.yaml` (an invalid file silently falls back to
  defaults):

```
curl -sL https://coderabbit.ai/integrations/schema.v2.json -o /tmp/cr.json
uvx check-jsonschema --schemafile /tmp/cr.json .coderabbit.yaml
```

  The schema does not reject unknown keys — check key names against it by
  hand.
