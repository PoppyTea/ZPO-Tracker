# demo

Jednorazowe, klikalne prototypy UX (HTML i skrypty tkinter) — materiał do
podjęcia decyzji, nie kod produkcyjny.

## Local Contracts

1. Obowiązek TDD z root `CLAUDE.md` tu **nie obowiązuje** — prototypy są
   wyrzucalne.
2. Pliki HTML są samodzielne: bez build stepu i bez zależności od reszty
   repo.
3. Skrypty `.py` wolno importować z `src/` wyłącznie po to, żeby pokazać
   RZECZYWISTY rendering widgetów produkcyjnych (`gui/styl.py`,
   `gui/widget_pole.py`), a nie jego imitację. Żaden inny powód nie
   uzasadnia sięgania do kodu produkcyjnego.
4. Prototyp, który dojrzewa do realnej implementacji, przenosi się do
   `src/zpo_tracker/` — ten katalog nie rośnie w stronę pełnego UI.

## Verification

Brak testów. HTML otwiera się bezpośrednio w przeglądarce, skrypty
uruchamia się z roota repo, np. `python demo/podglad-stylu.py`.
