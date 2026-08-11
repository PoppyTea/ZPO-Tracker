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
- `repo.py` — **`transakcja(conn)`**: jawna transakcja na SAVEPOINT,
  re-entrant (fasady opakowują `zapisz_blok`, które samo woła
  `get_or_create_*` — zwykłe `BEGIN` by się zagnieździło i rzuciło).
  **NIE używać wbudowanego `with conn:`** — przy `isolation_level=None`
  on nic nie wycofuje; kod wygląda poprawnie i nie robi nic (przypięte
  testem `test_wbudowane_with_conn_nic_nie_wycofuje`). Złapany
  `IntegrityError` NIE unieważnia transakcji, więc per-wierszowe `except`
  w `zapisz_blok`/`zaimportuj` działają wewnątrz bez zmian.
  `WERSJA_SCHEMATU` + `wersja_schematu`/`sprawdz_zgodnosc_wersji`/
  `wymaga_migracji`/`migruj` — musi zgadzać się z `PRAGMA user_version`
  na końcu `schema.sql`. **`migruj` jest addytywna i idempotentna**
  (sprawdza obecność każdego obiektu zamiast wykonywać kroki po numerze
  wersji), więc przeżywa też bazy w stanie pośrednim po przerwanej
  aktualizacji. Zweryfikowana na realnym imporcie z alpha.2: 1239
  transakcji / 68 kurierów / 671 punktów zachowane, `integrity_check` ok. Dostęp do danych: `zapisz_blok` (formularz → transakcje,
  **atomowy**),
  słowniki proste (`pobierz_slownik`/`dodaj_do_slownika`/
  `zmien_nazwe_w_slowniku`/`usun_z_slownika`), `scal_kurierow` (droga
  naprawy dla ostrzeżeń o podobieństwie, **atomowy**; przy kolizji
  `UNIQUE(data,kurier,punkt)` scalenie się nie uda — ale nie zostawi
  stanu połowicznego), `pobierz_transakcje`,
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
- `uzytkownicy.py` — tożsamość osoby wprowadzającej dane. `users.id` to
  **UUIDv5 z `domena\login`** (`NAMESPACE_ZPO` — nie zmieniać, zmiana
  rozdwoiłaby każdą osobę), NIE losowy UUID: losowy rozjechałby się między
  stacjami i po synchronizacji (X+3) ta sama osoba istniałaby wielokrotnie.
  `nr_kadrowy` (`[a-zA-Z0-9]{5}`, case sensitive) to atrybut biznesowy
  **obok** UUID, nie zamiast — wpisuje go człowiek, więc literówka jest
  niewykrywalna. Para daje kontrolę krzyżową (`ostrzezenia_tozsamosci`,
  miękkie ostrzeżenia). W SQLite pilnuje formatu `GLOB`, nie `LIKE`
  (`LIKE` jest niewrażliwy na wielkość liter). Numery kadrowe KURIERÓW to
  inny byt: inny format i relacja 1:N — patrz `../docs/roadmap.md`.
- `dziennik.py` — diagnostyka. Dwa strumienie o różnym przeznaczeniu:
  log tekstowy (`zpo.log`, kanał wsparcia, może zawierać dane z
  komunikatów wyjątków, zostaje lokalnie) i **dziennik JSONL**
  (`operacje.jsonl`, indeks operacji dla migawek/cofania). Kształt wpisu
  JSONL jest **zamknięty** (`POLA_WPISU`, parametry nazwane zamiast
  `**kwargs`), bo ten plik jest kandydatem do wyniesienia na zewnątrz —
  żadnych nazwisk ani adresów. Oba żyją POZA bazą, żeby przetrwać jej
  uszkodzenie i podmianę przy cofaniu. Numeracja operacji po jawnym
  `seq`, nigdy po zegarze.

Warstwa GUI (tkinter, `gui/`) — **zero logiki biznesowej**, tylko zbieranie
wartości z pól i wywołanie warstwy logiki:

- `app.py` — okno główne, `Notebook` z czterema zakładkami.
  `_katalog_danych` — na Windows **`%LOCALAPPDATA%`, nie `%APPDATA%`**
  (Roaming przy profilach mobilnych wciąga bazę i historię kopii na
  ścieżkę logowania); `_przenies_ze_starej_lokalizacji` robi jednorazową
  migrację z Roaming, ale NIE nadpisuje istniejącej bazy lokalnej.
  Baza + log + dziennik razem; `_katalog_logow`
  (obsługuje bazy specjalne typu `:memory:`, które nie mają katalogu
  nadrzędnego). Haki diagnostyczne podpinane **dwukrotnie i celowo**:
  w `main()` przed zbudowaniem okna (awaria w konstruktorze) oraz na
  instancji Tk (`report_callback_exception` — `sys.excepthook` NIE łapie
  wyjątków z callbacków widgetów).
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
  działają) — patrz Verification. **Wpięty do `zakladka_wprowadzanie.py`**
  (pola kurier, nadawca, adres), źródło kandydatów z
  `repo.pobierz_punkty`/`pobierz_slownik`.

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

Zmiany w `gui/` weryfikować przez `.venv-sys/bin/python -m pytest`
(systemowy Python) — patrz „Stan środowiska graficznego”.

**Stan środowiska graficznego:** `uv`-owy Python na tej konkretnej maszynie
ma reprodukowalny fatalny `SIGABRT` przy tworzeniu JAKIEGOKOLWIEK widgetu
Tk (nawet gołego `tk.Entry`) — zdiagnozowane jako problem konkretnej
binarki python-build-standalone, NIE monitora/DPMS/sesji X11 ani kodu
projektu (pełna diagnoza: `../docs/environment.md`). Systemowy Python
nie ma tego problemu. `test_gui_smoke.py` sonduje display w osobnym
podprocesie i pomija się czysto, jeśli trafi na tę wadliwą binarkę —
pominięcia to ten mechanizm, nie usterka.

**Uwaga praktyczna:** `.venv/` w repo jest obecnie zbudowany przez `uv`
(`pyvenv.cfg` → `~/.local/share/uv/python/...`), więc testy GUI pod nim
się POMIJAJĄ. Do realnego odpalenia testów GUI służy osobne
`.venv-sys/` na systemowym Pythonie (gitignorowane) — pod nim przechodzi
pełny zestaw bez pominięć. Zmiany dotykające `gui/` weryfikować tam,
inaczej „wszystko zielone” nie obejmuje warstwy, którą się właśnie
zmieniło.

`widget_autocomplete.py` zweryfikowany w izolacji przez systemowy Python:
dropdown renderuje się poprawnie, dopasowanie rozmyte i klawiatura działają
zgodnie z projektem. Wpięty do `zakladka_wprowadzanie.py` (pola
kurier/nadawca/adres, źródło kandydatów z `repo.pobierz_punkty`/
`pobierz_slownik`).

Build PyInstaller: proxy-build na Linuksie sprawdzony (pakuje się bez
błędów importu `pydantic_core`, dochodzi do tworzenia okna Tk) — realny
`.exe` wymaga budowy na Windowsie, patrz `../docs/environment.md`.

## Child DOX Index

Brak — pakiet rozrósł się w warstwy logiki + `gui/`, ale to wciąż jedna
spójna granica pracy (patrz Local Contracts wyżej). Rozbić na osobny
`gui/AGENTS.md` dopiero, jeśli podzakładki dorosną do własnych, odrębnych
reguł wykraczających poza "zero logiki biznesowej" już opisane tutaj.
