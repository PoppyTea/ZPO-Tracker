# zpo-tracker

Modernization of the manual, error-prone monthly courier/pickup-point
(ZPO) data entry process for a settlements department at Poczta Polska.
Replaces spreadsheet copy-paste with a local Python + SQLite tool for
non-technical users, built to run fully offline on locked-down Windows
machines.

## Purpose

Eliminate the repetitive part of a monthly Excel workflow (copying last
month's courier+pickup-point rows by hand) and add soft validation where
none currently exists. Full narrative context: `docs/domain-model.md`.

## Ownership

Solo project, single maintainer (Papaver), built for their own department.
No other contributors yet.

## Local Contracts

This file is intentionally an index, not a knowledge dump. Durable project
knowledge lives in `docs/`, one topic per file:

- `docs/domain-model.md` — why this project exists, real column layout,
  and the specific findings from analyzing real source data (PNI ZPO
  reliability, conditional formatting caveats, template/blank rows, etc.)
- `docs/tech-decisions.md` — the chosen stack and every rejected
  alternative, with the reasoning
- `docs/environment.md` — the real production environment (locked-down
  Windows) vs. the development environment, and why the gap matters
- `docs/ux-ui.md` — UX direction (courier-first entry modeled on the paper
  form), the "idiot-proof, not just non-technical" framing, validation
  approach, and what's still undecided about the suggestion engine
- `docs/roadmap.md` — version sequence (`0.1-alpha.3` … `0.1-alpha.6`), the
  gate that must be cleared before `0.1-alpha.4` starts, and the open
  direction-setting questions that would reshape it; read before planning
  any multi-version work
- `docs/backlog.md` — full backlog, grouped by topic
- `docs/normalization-v2.md` — proposed relational schema v2 and the two
  open risks it depends on (see also `schema_v2_draft.sql`)
- `docs/reference-data-sources.md` — external reference datasets
  (Polish/Ukrainian names, Mazowieckie addresses, retail-chain locations)
  for enriching the suggestion engine later; low priority before MVP

Read the relevant doc before touching the area it covers — don't rely on
this file alone.

## Work Guidance

- **TDD is mandatory for new production code**: red test → watch it fail →
  minimal implementation → green → refactor. Do not write implementation
  before a test without the user's explicit permission. Exception: pure
  schema/config definitions (e.g. SQL DDL) don't need a test per se.
- This file (`CLAUDE.md`) is written in English. Every other file in this
  repo — code comments, commit-adjacent docs, the `docs/` folder — is
  written in Polish, matching the user's working language.
- Talk to the user in Polish.

## Verification

```
python -m venv .venv && source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt && pip install -e .
pytest
```

`uv sync --extra dev && uv run pytest` still works too (see
`docs/environment.md` for why pip is now the documented default).

528/528 tests currently pass under the pip/system-Python setup above, no
skips (verified against a real 1294-row slice of source data, both import
and export round-trip). `.venv/` must be built by the system Python, not
`uv`'s managed one — `uv`'s python-build-standalone binary has a
reproducible tkinter/X11 SIGABRT on this dev machine, which silently skips
the GUI tests instead of running them (see `docs/environment.md`). If GUI
tests start skipping again, check `python3 -m venv` actually resolved to
the system interpreter, not `uv`/`pyenv`/another manager on `PATH`.

---

# DOX framework

- DOX is highly performant AGENTS.md hierarchy installed here
- Agent must follow DOX instructions across any edits

## Core Contract

- AGENTS.md files are binding work contracts for their subtrees
- Work products, source materials, instructions, records, assets, and durable docs must stay understandable from the nearest applicable AGENTS.md plus every parent AGENTS.md above it

## Read Before Editing

1. Read the root AGENTS.md
2. Identify every file or folder you expect to touch
3. Walk from the repository root to each target path
4. Read every AGENTS.md found along each route
5. If a parent AGENTS.md lists a child AGENTS.md whose scope contains the path, read that child and continue from there
6. Use the nearest AGENTS.md as the local contract and parent docs for repo-wide rules
7. If docs conflict, the closer doc controls local work details, but no child doc may weaken DOX

Do not rely on memory. Re-read the applicable DOX chain in the current session before editing.

## Update After Editing

Every meaningful change requires a DOX pass before the task is done.

Update the closest owning AGENTS.md when a change affects:

- purpose, scope, ownership, or responsibilities
- durable structure, contracts, workflows, or operating rules
- required inputs, outputs, permissions, constraints, side effects, or artifacts
- user preferences about behavior, communication, process, organization, or quality
- AGENTS.md creation, deletion, move, rename, or index contents

Update parent docs when parent-level structure, ownership, workflow, or child index changes. Update child docs when parent changes alter local rules. Remove stale or contradictory text immediately. Small edits that do not change behavior or contracts may leave docs unchanged, but the DOX pass still must happen.

## Hierarchy

- Root AGENTS.md is the DOX rail: project-wide instructions, global preferences, durable workflow rules, and the top-level Child DOX Index
- Child AGENTS.md files own domain-specific instructions and their own Child DOX Index
- Each parent explains what its direct children cover and what stays owned by the parent
- The closer a doc is to the work, the more specific and practical it must be

## Child Doc Shape

- Create a child AGENTS.md when a folder becomes a durable boundary with its own purpose, rules, responsibilities, workflow, materials, or quality standards
- Work Guidance must reflect the current standards of the project or user instructions; if there are no specific standards or instructions yet, leave it empty
- Verification must reflect an existing check; if no verification framework exists yet, leave it empty and update it when one exists

Default section order:
- Purpose
- Ownership
- Local Contracts
- Work Guidance
- Verification
- Child DOX Index

## Style

- Keep docs concise, current, and operational
- Document stable contracts, not diary entries
- Put broad rules in parent docs and concrete details in child docs
- Prefer direct bullets with explicit names
- Do not duplicate rules across many files unless each scope needs a local version
- Delete stale notes instead of explaining history
- Trim obvious statements, repeated rules, misplaced detail, and warnings for risks that no longer exist

## Closeout

1. Re-check changed paths against the DOX chain
2. Update nearest owning docs and any affected parents or children
3. Refresh every affected Child DOX Index
4. Remove stale or contradictory text
5. Run existing verification when relevant
6. Report any docs intentionally left unchanged and why

## User Preferences

- TDD (red-green-refactor) is mandatory for new production code; schema/DDL
  is the only standing exception. Do not skip without explicit permission.
- Root `CLAUDE.md` stays English and stays an index — durable knowledge goes
  in `docs/*.md`, not inline here. Everything else in the repo is Polish.
- Talk to the user in Polish.
- `AGENTS.md` at repo root is a symlink to `CLAUDE.md`, not a separate file
  — edit `CLAUDE.md`, never `AGENTS.md` directly.

## Child DOX Index

- `src/AGENTS.md` — the `zpo_tracker` package (`src/zpo_tracker/`) and its
  pytest suite (`src/tests/`)
- `demo/AGENTS.md` — throwaway HTML UX prototypes, not production code
- `data/AGENTS.md` — local real-data scratch space, gitignored contract
- Root-owned reference docs, see `docs/`: `domain-model.md`,
  `tech-decisions.md`, `environment.md`, `ux-ui.md`, `roadmap.md`,
  `backlog.md`, `normalization-v2.md`, `reference-data-sources.md`
- Root-owned project files: `README.md`, `schema.sql`, `schema_v2_draft.sql`,
  `pyproject.toml`, `.gitignore`, `zpo_tracker.spec` (PyInstaller, must be
  built on Windows — see `docs/environment.md`)
