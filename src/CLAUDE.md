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
  Zweryfikowany w izolacji (zrzuty ekranu: dropdown renderuje się
  poprawnie, dopasowanie rozmyte działa, Tab/strzałki/zatwierdzanie
  działają) — patrz Verification. **Wciąż NIEWPIĘTY do
  `zakladka_wprowadzanie.py`** — integracja z prawdziwym, wielowierszowym
  formularzem to osobny krok.

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
python -m venv .venv && source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r ../requirements-dev.txt && pip install -e ..
pytest
```

Uruchamiać z katalogu głównego repo (`testpaths` w root `pyproject.toml`
wskazuje na `src/tests`). `uv sync --extra dev && uv run pytest` też
działa, ale patrz zastrzeżenie niżej.

**Stan środowiska graficznego:** `uv`-owy Python na tej konkretnej maszynie
ma reprodukowalny fatalny `SIGABRT` przy tworzeniu JAKIEGOKOLWIEK widgetu
Tk (nawet gołego `tk.Entry`) — zdiagnozowane jako problem konkretnej
binarki python-build-standalone, NIE monitora/DPMS/sesji X11 ani kodu
projektu (pełna diagnoza: `../docs/environment.md`). Systemowy Python
nie ma tego problemu. `test_gui_smoke.py` sonduje display w osobnym
podprocesie i pomija się czysto, jeśli trafi na tę wadliwą binarkę —
pominięcia to ten mechanizm, nie usterka.

`.venv/` w repo jest zbudowany systemowym Pythonem (naprawione
2026-08-11, wcześniej przez pomyłkę wskazywał na `uv`) — pełny zestaw,
łącznie z GUI, przechodzi pod nim bez pominięć. Osobny `.venv-sys/` nie
jest już potrzebny. Jeśli po `python -m venv .venv` testy GUI zaczną się
pomijać, sprawdź `.venv/pyvenv.cfg` — prawdopodobnie `python3` w `PATH`
wskazuje na `uv`/inny menedżer zamiast na systemowego Pythona.

`widget_autocomplete.py` zweryfikowany w izolacji przez systemowy Python:
dropdown renderuje się poprawnie, dopasowanie rozmyte i klawiatura działają
zgodnie z projektem. Integracja z `zakladka_wprowadzanie.py` (podpięcie
do pól nadawca/adres/kurier, źródło kandydatów z `repo.pobierz_punkty`/
`pobierz_slownik`) to następny krok — nie zrobiona jeszcze, bo to
realna zmiana w już działającym, przetestowanym formularzu.

Build PyInstaller: proxy-build na Linuksie sprawdzony (pakuje się bez
błędów importu `pydantic_core`, dochodzi do tworzenia okna Tk) — realny
`.exe` wymaga budowy na Windowsie, patrz `../docs/environment.md`.

## Child DOX Index

Brak — pakiet rozrósł się w warstwy logiki + `gui/`, ale to wciąż jedna
spójna granica pracy (patrz Local Contracts wyżej). Rozbić na osobny
`gui/AGENTS.md` dopiero, jeśli podzakładki dorosną do własnych, odrębnych
reguł wykraczających poza "zero logiki biznesowej" już opisane tutaj.
