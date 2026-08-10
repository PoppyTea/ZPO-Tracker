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

## Szybki start

```bash
uv sync --extra dev
uv run pytest
uv run zpo-tracker
```

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
