# ZPO Tracker

Ten projekt wziął się z dość przyziemnego problemu: spory kawałek pracy
w firmie polega na żmudnym, ręcznym przepisywaniu tych samych danych
z miesiąca na miesiąc — bez żadnej automatyzacji i bez żadnej podpowiedzi,
gdy coś nie zgadza się z poprzednim wpisem. W pewnym momencie stwierdziłem,
że zamiast czekać, aż ktoś kiedyś to zautomatyzuje, prościej będzie zrobić
to samemu — najpierw dla własnej wygody, a skoro problem dotyczy całego
zespołu, to przy okazji może ułatwić życie też kolegom.

This project grew out of a pretty mundane problem: a good chunk of my work
involves tediously retyping the same data by hand every month, with zero
automation and no safety net for when something doesn't add up. At some
point I decided that instead of waiting for someone to eventually fix
this, it would be simpler to just build it myself — first for my own
sanity, and since the pain is shared across the team, hopefully it makes
life a bit easier for my colleagues too.

Modernizacja procesu wprowadzania danych otrzymywanych w formie papierowej + zmiana przechowywania danych z "tabelki w excelu" -> na prostą DB.

## Status i plan

Wydane: `v0.1.0-alpha.3` — MVP (import/export `.xlsx`, formularz blankietowy,
słowniki, podpowiedzi) plus trwałość danych: transakcje, migawki i cofanie
operacji, logi diagnostyczne, atrybucja zmian do autora, ręczne scalanie
dwóch baz.

W toku (**`0.1-alpha.3.1`**): automatyczna dedukcja pól formularza z bazy,
kolorowe wskaźniki stanu pól, tryb auto. Dalej: **`0.1-alpha.4`** przebudowa
UI/UX, **`0.1-alpha.5`** tryb pół-auto, **`0.1-alpha.6`** automatyczna
synchronizacja między stacjami. Pełna kolejność i otwarte pytania
kierunkowe: `docs/roadmap.md`.

## Szybki start

```bash
python -m venv .venv
# Linux/Mac:
source .venv/bin/activate
# Windows:
.venv\Scripts\activate

pip install -r requirements-dev.txt
pip install -e .
pytest
zpo-tracker
```

(Historycznie środowisko było zarządzane przez `uv` — `uv.lock`/`pyproject.toml`
wciąż działają, `uv sync --extra dev && uv run pytest` też zadziała, ale
`requirements*.txt` to teraz podstawowa, udokumentowana ścieżka, dopasowana
do środowiska na Windows w pracy.)

## Struktura

```
schema.sql                  # schemat SQLite (v1 + firmy_zpo)
zpo_tracker.spec             # PyInstaller (budowa .exe TYLKO na Windows)
src/zpo_tracker/
    importer.py               # import wiersza .xlsx (TDD)
    models.py                 # walidacja pydantic v2
    normalizacja.py           # scalanie/dedup (białe znaki, literówki, diakrytyki)
    repo.py                   # dostęp do danych, słowniki
    import_orchestrator.py    # import partii + ekran korekty
    eksport.py                # export do .xlsx (round-trip ze snapshotem)
    podpowiedzi.py            # silnik podpowiedzi
    gui/                      # aplikacja tkinter (przeglądanie/wprowadzanie/import-export/słowniki)
src/tests/                  # testy pytest
demo/                       # prototypy UX (throwaway, nie produkcja)
data/                       # (gitignored poza README.md) realne eksporty do pracy lokalnej
```
