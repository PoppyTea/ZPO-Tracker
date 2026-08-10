# src

## Purpose

Python package `zpo_tracker` — pełne MVP: import/export `.xlsx`,
normalizacja/dedup, walidacja pydantic v2, dostęp do danych i aplikacja
desktopowa (tkinter). Układ `src/` (nie flat-layout) — pakiet leży pod
`src/zpo_tracker/`, testy pod `src/tests/`.

## Ownership

Jak w całym projekcie — patrz root `CLAUDE.md`.

## Local Contracts

Warstwa logiki (bez GUI, w pełni testowalna bez display):

- `importer.py` — najniższy poziom: `parse_quantity`, `get_or_create_*`,
  `import_row` (jeden wiersz `.xlsx` → SQLite). Reużywane przez
  `repo.py` i `import_orchestrator.py`, nie duplikować.
- `models.py` — pydantic v2. `WierszImportu` (walidacja wiersza importu,
  konwersja `datetime`→`date`, normalizacja białych znaków na
  kurier/nadawca/adres — bez tego "Michalak Maciej " ląduje jako inny
  kurier niż "Michalak Maciej", patrz historia commitów). `BlankietBlok`
  / `WierszBlankietu` (dane z formularza wprowadzania).
- `normalizacja.py` — trzy poziomy pewności: `klucz_bialych_znakow`
  (bezpieczne automatyczne scalanie), `klucz_rozmyty` +
  `odleglosc_edycyjna`/`czy_literowka` (prawdopodobna literówka,
  automatyczny dedup z możliwością odrzucenia), `znajdz_podobne`
  (różnica WYŁĄCZNIE w diakrytykach — nigdy automat, patrz
  `../docs/domain-model.md`, przypadek "Wołczuk Rafal"/"Rafał").
- `repo.py` — dostęp do danych: `zapisz_blok` (formularz → transakcje),
  słowniki proste (`pobierz_slownik`/`dodaj_do_slownika`/
  `zmien_nazwe_w_slowniku`/`usun_z_slownika`), `scal_kurierow` (droga
  naprawy dla ostrzeżeń o podobieństwie), `pobierz_transakcje`,
  `pobierz_punkty`. `_resolve_schema_path` rozróżnia dev vs spakowany
  `.exe` (PyInstaller rozpakowuje dane do `sys._MEIPASS`).
- `import_orchestrator.py` — cały import w partii: `zwaliduj_wiersze`,
  `znajdz_propozycje_scalenia_kurierow` (literówki, auto-merge PRZED
  zapisem, nie cofanie po fakcie), `znajdz_ostrzezenia_podobienstwa_kurierow`
  (diakrytyki, tylko sygnał), `zaimportuj`.
- `eksport.py` — transakcje → `.xlsx`. `NAGLOWKI` to stała z dokładnymi
  nagłówkami ze snapshotu źródłowego (białe znaki są częścią danych, nie
  literówką do poprawienia). Typy komórek eksportowane kanonicznie czysto
  (int/date), świadome odstępstwo od niespójności źródła — patrz plan MVP.
- `podpowiedzi.py` — silnik podpowiedzi (`podpowiedz`,
  `najlepsza_podpowiedz`), źródło kandydatów wstrzykiwane, nie zaszyte.

Warstwa GUI (tkinter, `gui/`) — **zero logiki biznesowej**, tylko zbieranie
wartości z pól i wywołanie warstwy logiki:

- `app.py` — okno główne, `Notebook` z czterema zakładkami.
- `zakladka_przeglad.py`, `zakladka_wprowadzanie.py` (formularz
  blankietowy: bloki REJON+DATA, rejon opcjonalny/nieznany + komentarz
  per blok), `zakladka_import_export.py` (+ `DialogKorektyImportu` —
  ekran korekty pokazuje WYŁĄCZNIE wiersze wymagające uwagi),
  `zakladka_slowniki.py` (podzakładki kurierzy/punkty ZPO/wykonawcy/
  rejony/firmy ZPO).
- `formularz_logika.py` — jedyny most między formularzem a
  `models.py`/pydantic; GUI wyświetla błędy walidacji, nie decyduje o nich.
- `widget_tabela.py` — wspólna tabela z sortowaniem i Ctrl+scroll zoom.
- `widget_autocomplete.py` — dropdown + klawiatura (bez ghost textu).
  **Niewpięty do formularza i niezweryfikowany nawet razem odpalony** —
  patrz Verification.

## Work Guidance

- TDD (red→green→refactor) obowiązkowe dla nowego kodu w tym katalogu —
  patrz root `CLAUDE.md`. Wyjątek na czyste DDL/schema nie dotyczy tego
  katalogu (schema.sql leży w root).
- Komentarze w kodzie po polsku, zgodnie z konwencją całego repo.
- Logika biznesowa nigdy nie trafia do `gui/` — jeśli widget zaczyna
  decydować (walidować, szeregować, scalać), to sygnał, że kod należy
  do modułu logiki, nie do widoku.

## Verification

```
uv sync --extra dev
uv run pytest
```

Uruchamiać z katalogu głównego repo (`testpaths` w root `pyproject.toml`
wskazuje na `src/tests`).

**Stan środowiska graficznego (ważne, przeczytać przed dotykaniem `gui/`):**
w trakcie budowy MVP środowisko X11 tej maszyny zaczęło fatalnie ubijać
proces (`SIGABRT`) przy tworzeniu JAKIEGOKOLWIEK widgetu Tk — potwierdzone
nawet dla zwykłego `tk.Entry` na świeżym `Xvfb`, więc to nie błąd w kodzie
projektu. `test_gui_smoke.py` sonduje display w osobnym podprocesie i
pomija się czysto, gdy środowisko jest w tym stanie — dwa pominięcia w
wyniku testów to ten mechanizm, nie usterka. Jeśli display działa,
`test_gui_smoke.py` powinien realnie odpalić okno — jeśli nadal pomija,
środowisko wciąż jest niesprawne.

`widget_autocomplete.py` nie został odpalony ani razu (nawet raz
zainstancjonowany) — zweryfikować i wpiąć do `zakladka_wprowadzanie.py`
jako pierwszy krok, gdy display wróci do działania, zamiast dowierzać
kodowi napisanemu w ciemno.

Build PyInstaller: proxy-build na Linuksie sprawdzony (pakuje się bez
błędów importu `pydantic_core`, dochodzi do tworzenia okna Tk) — realny
`.exe` wymaga budowy na Windowsie, patrz `../docs/environment.md`.

## Child DOX Index

Brak — pakiet rozrósł się w warstwy logiki + `gui/`, ale to wciąż jedna
spójna granica pracy (patrz Local Contracts wyżej). Rozbić na osobny
`gui/AGENTS.md` dopiero, jeśli podzakładki dorosną do własnych, odrębnych
reguł wykraczających poza "zero logiki biznesowej" już opisane tutaj.
