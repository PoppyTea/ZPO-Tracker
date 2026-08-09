# src

## Purpose

Python package `zpo_tracker` (import/walidacja danych kurier/ZPO) i jego
zestaw testów pytest. Układ `src/` (nie flat-layout) — pakiet leży pod
`src/zpo_tracker/`, testy pod `src/tests/`.

## Ownership

Jak w całym projekcie — patrz root `CLAUDE.md`.

## Local Contracts

- `zpo_tracker/importer.py` — logika importu wiersza `.xlsx` do SQLite i
  walidacji miękkiej (PNI ZPO, deduplikacja, pomijanie wierszy-szablonów).
  Zasady biznesowe, które koduje, opisane są w `../docs/domain-model.md`.
- `zpo_tracker/__init__.py` — pusty marker pakietu.
- `tests/test_importer.py` — testy pytest, SQLite `:memory:`, bez mocków;
  fixture ładuje schemat z `../schema.sql` (root repo, trzy poziomy wyżej
  względem pliku testu).

## Work Guidance

- TDD (red→green→refactor) obowiązkowe dla nowego kodu w tym katalogu —
  patrz root `CLAUDE.md`. Wyjątek na czyste DDL/schema nie dotyczy tego
  katalogu (schema.sql leży w root).
- Komentarze w kodzie po polsku, zgodnie z konwencją całego repo.

## Verification

```
uv sync --extra dev
uv run pytest
```

Uruchamiać z katalogu głównego repo (`testpaths` w root `pyproject.toml`
wskazuje na `src/tests`).

## Child DOX Index

Brak — pakiet to obecnie jeden moduł, testy to jeden plik. Rozbić dopiero
gdy `importer.py` przestanie mieścić się w jednym pliku (patrz
`../docs/normalization-v2.md` — przepisanie pod schemat v2 może być tym
momentem).
