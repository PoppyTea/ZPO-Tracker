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

Modernizacja procesu wprowadzania danych kurier/ZPO (dział rozliczeń,
Poczta Polska). Pełny kontekst decyzyjny — patrz [`CLAUDE.md`](./CLAUDE.md).

## Szybki start

```bash
uv sync --extra dev
uv run pytest
```

Realne dane robocze (`.xlsx`/`.csv`) wrzucaj do `data/` — katalog jest w
`.gitignore`, nic stąd nie trafi do repo.

## Struktura

```
schema.sql                  # schemat SQLite
src/zpo_tracker/importer.py # logika importu + walidacji (TDD)
src/tests/                  # testy pytest
demo/                       # prototypy UX (throwaway, nie produkcja)
data/                       # (gitignored poza README.md) realne eksporty do pracy lokalnej
```
