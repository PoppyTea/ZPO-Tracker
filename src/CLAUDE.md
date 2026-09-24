# src

Pakiet `zpo_tracker` (`src/zpo_tracker/`, warstwa logiki + `gui/` w
tkinterze) i jego testy (`src/tests/`).

## Local Contracts

1. **Reguły i pułapki modułów żyją w ich docstringach**, przy kodzie,
   którego dotyczą — nie tutaj. Nowa reguła albo pułapka trafia do
   docstringu w tym samym commicie, co kod.
2. **Logika jest testowalna bez display'a; `gui/` nie zawiera logiki
   biznesowej.** Jeśli widget zaczyna walidować, szeregować albo scalać,
   ten kod należy do modułu logiki.
3. **Niejednoznaczne nigdy nie rozstrzyga się automatycznie** — w dedukcji
   pól, scalaniu baz ani dopasowaniu nazw. Program wypełnia tylko to, co
   jednoznaczne; resztę pokazuje człowiekowi jako kandydatów albo
   ostrzeżenie.
4. **Nic nie ginie po cichu.** Wiersz, którego nie da się zapisać, wraca do
   użytkownika z powodem; operacja, która nie może się udać w całości, jest
   wycofywana w całości.

## Operacje i reguły

| Operacja | Reguły | Severity | Plik | Jak sprawdzić |
|---|---|---|---|---|
| zmiana kodu produkcyjnego | test przed kodem (TDD) | ERROR | root `CLAUDE.md`, kontrakt 4 | `pytest` |
| mutacja danych z GUI | wyłącznie `operacje.wykonaj`/`cofnij`, nigdy `repo.*` wprost — inaczej operacja omija migawkę i dziennik | ERROR | `zpo_tracker/operacje.py` | `pytest src/tests/test_gui_smoke.py` |
| callback Tk | wyjątku nie połykać: w buildzie `console=False` nie ma `stderr` | ERROR | `zpo_tracker/dziennik.py`, `zpo_tracker/gui/app.py` | recenzja |
| transakcja w bazie | `repo.transakcja`, nigdy wbudowane `with conn:` (niczego nie wycofuje) | ERROR | `zpo_tracker/repo.py` (`transakcja`) | `pytest src/tests/test_transakcje.py` |
| zmiana schematu | `WERSJA_SCHEMATU` = `PRAGMA user_version` w `schema.sql`; podbicie wyłącznie przy zmianie struktury, nie przy naprawie danych; `migruj` addytywna i idempotentna | ERROR | `zpo_tracker/repo.py` (`WERSJA_SCHEMATU`, `migruj`), `../schema.sql` | `pytest src/tests/test_transakcje.py` |
| import pliku | plik niezaufany nie wnosi PNI ani rejonu; `zrodlo` wyprowadza się z `zaufany`, nigdy nie jest wolnym parametrem | ERROR | `zpo_tracker/import_orchestrator.py` (`zaimportuj`), `zpo_tracker/importer.py` | `pytest src/tests/test_zaufanie_importu.py` |
| PNI | tekst, nigdy liczba (`"007"` ≠ `"7"`) | ERROR | `zpo_tracker/eksport.py`, `zpo_tracker/repo.py` (`znajdz_punkt_po_pni`) | `pytest src/tests/test_eksport.py` |
| nowy odczyt skoroszytu | przez `arkusze.py` (format po zawartości, `.xls` = `.xlsx`), nie `openpyxl` wprost; wiersz przez `profil_kolumn.zbuduj_wiersz`, nigdy `dict(zip(...))` | ERROR | `zpo_tracker/arkusze.py`, `zpo_tracker/profil_kolumn.py` | `pytest src/tests/test_arkusze.py src/tests/test_profil_kolumn.py` |
| kolor, odstęp, czcionka w GUI | tylko tokeny z `gui/styl.py`; `tekst_slaby` nigdy jako kolor tekstu | WARNING | `zpo_tracker/gui/styl.py` | `pytest src/tests/test_styl.py` |

## Verification

Z roota repo (`testpaths` w `pyproject.toml` wskazuje na `src/tests`):

```
pytest
pytest -m "not slow"
```

Wymóg zera pominięć i pułapka z Pythonem zarządzanym przez `uv` — patrz
root `CLAUDE.md`, sekcja Verification.
