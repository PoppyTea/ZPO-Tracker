# demo

## Purpose

Jednorazowe, klikalne prototypy UX — walidacja przepływu przed
implementacją produkcyjną, nie produkcja sama w sobie.

## Ownership

Jak w całym projekcie — patrz root `CLAUDE.md`.

## Local Contracts

- `przeglad-kurierow-prototyp.html` — prototyp narzędzia do ręcznego
  potwierdzenia podziału imię/nazwisko kurierów (kontekst i wynik na
  realnych danych: `../docs/ux-ui.md`, sekcja "Narzędzie do przeglądu
  kurierów"). Samodzielny plik HTML/JS, bez build stepu, bez zależności
  od reszty repo.
- `wprowadzanie-restyl-prototyp.html` — makieta przejścia stylistycznego
  zakładki Wprowadzanie (2026-08-24), do akceptacji przed zmianami
  w produkcji. Zawiera też listę tego, czego tkinter NIE narysuje
  (zaokrąglenia, cienie, gradienty), żeby makieta była kontraktem, a nie
  wizją. Samodzielna, bez zależności.
- `warianty-wskaznikow.py` + `.html` — siatka wariantów do wyboru
  (2026-08-24): afordancja rozwijanej listy (A1-A6), traktowanie obwódki
  pola wymagającego uwagi (W0-W6), wskaźnik przy wierszach bez danych.
  **Warianty implementowane na własną rękę, NIE przez
  `widget_pole.PoleZeWskaznikiem`** — o to właśnie chodzi, żeby sprawdzić,
  co trzeba by w tamtym zmienić. Plik `.html` to strona z zrzutami
  wklejonymi jako `data:` URI, nie osobna makieta — źródłem prawdy jest
  tkinter, przeglądarka tylko go pokazuje.
- `podglad-stylu.py` — ten sam ekran w REALNYM tkinterze, do porównania
  z makietą: `python demo/podglad-stylu.py` (nowy styl) albo z flagą
  `--bez` (stan obecny). **Jedyny plik w tym katalogu importujący z
  `src/`** — świadomie, bo jego sensem jest pokazanie rzeczywistego
  renderingu `gui/styl.py`, nie jego imitacji. Sztywne dane, zero
  połączenia z bazą.

## Work Guidance

- Pliki w tym katalogu NIE podlegają obowiązkowi TDD z root `CLAUDE.md` —
  to jednorazowe, wyrzucalne prototypy, nie produkcja.
- Docelowy interfejs produkcyjny to tkinter (patrz `../docs/ux-ui.md`) —
  nie rozbudowywać zawartości tego katalogu w stronę pełnego UI; jeśli
  prototyp dojrzewa do realnej implementacji, kod przenosi się do
  `src/zpo_tracker/`, nie zostaje tutaj.

## Verification

Brak — otworzyć plik bezpośrednio w przeglądarce, żeby sprawdzić przepływ.

## Child DOX Index

Brak.
