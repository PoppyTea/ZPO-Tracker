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
  `pobierz_punkty`. `zapisz_bloki` — kilka `BlankietBlok` (jeden formularz
  = kilka bloków rejonu) jako JEDNA operacja dla `operacje.wykonaj`, żeby
  cofnięcie cofało cały formularz, nie pojedynczy blok. `_resolve_schema_path`
  rozróżnia dev vs spakowany `.exe` (PyInstaller rozpakowuje dane do
  `sys._MEIPASS`).
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
- `blokada.py` — jedna instancja `app.main` na katalog danych: blokada
  PLIKU na poziomie systemu operacyjnego (`fcntl.flock`/`msvcrt.locking`),
  NIE zapis PID-u i sprawdzanie go później — PID martwego procesu bywa
  ponownie przydzielony innemu, żywemu procesowi (typowe po restarcie
  systemu), więc sam plik z PID-em niczego by nie gwarantował. System
  zwalnia blokadę pliku automatycznie nawet przy awarii procesu. Ścieżka
  Windows (`msvcrt`) nie jest odpalana w testach (maszyna dev to Linux) —
  zweryfikowana przeglądem kodu, nie testem.
- `dziennik.py` — diagnostyka. Dwa strumienie o różnym przeznaczeniu:
  log tekstowy (`zpo.log`, kanał wsparcia, może zawierać dane z
  komunikatów wyjątków, zostaje lokalnie) i **dziennik JSONL**
  (`operacje.jsonl`, indeks operacji dla migawek/cofania, patrz
  `operacje.py` niżej). Kształt wpisu JSONL jest **zamknięty**
  (`POLA_WPISU`, parametry nazwane zamiast `**kwargs`), bo ten plik jest
  kandydatem do wyniesienia na zewnątrz — żadnych nazwisk ani adresów.
  Oba żyją POZA bazą, żeby przetrwać jej uszkodzenie i podmianę przy
  cofaniu. Numeracja operacji po jawnym `seq`, nigdy po zegarze.
- `kopie.py` — migawki bazy: pełna kopia pliku `.db`. Dwie ścieżki
  kopiowania: `zrob_migawke` (z otwartego `conn`, przez SQLite Backup API —
  bezpieczne niezależnie od otwartych transakcji, działa nawet z
  `:memory:`) i `zrob_migawke_pliku` (zwykłe kopiowanie pliku, WYŁĄCZNIE
  gdy `conn` jest zamknięte, bo podmiana pliku pod żywym połączeniem jest
  niebezpieczna — na Windows w ogóle niedozwolona). Schemat-agnostyczne,
  żadnej wiedzy o `transakcje`/`users`. `przytnij_migawki` — rotacja
  retencji (`GRANICE_RETENCJI_DNI`: pełna rozdzielczość do 1 dnia, dalej
  dzień/3dni/tydzień/2tyg/miesiąc/3mc/pół roku/rok, **po roku 1/rok BEZ
  KOŃCA** — świadoma decyzja, nie twardy limit, patrz historia commitów).
  Bezstanowa i idempotentna: liczy kubełki od `teraz` przy każdym
  wywołaniu, więc migawka sama "awansuje" do rzadszej rozdzielczości
  z wiekiem. Usuwa WYŁĄCZNIE pliki — wpisy dziennika JSONL zostają
  (append-only), próba cofnięcia do przyciętej operacji kończy się
  czytelnym błędem w `operacje.cofnij` (sprawdzone PRZED zrobieniem
  migawki bezpieczeństwa, żeby jej nie marnować).
- `operacje.py` — fasada łącząca `kopie.py` z `dziennik.py`: `wykonaj`
  robi migawkę **PRZED** wywołaniem funkcji mutującej (nie po — inaczej
  cofnięcie przywracałoby stan już zepsuty przez tę samą operację), potem
  wpis w dzienniku z `czas` (wymagane przez `kopie.przytnij_migawki` do
  liczenia wieku — to jedyne miejsce w projekcie, gdzie zegar ścienny jest
  celowo używany, w odróżnieniu od numeracji operacji po `seq`) i wynikiem
  `ok`/`blad` (wyjątek zawsze idzie dalej). `cofnij` przywraca stan SPRZED
  wskazanej operacji — cofa też wszystko PO niej (punkt w czasie, nie
  selektywne cofnięcie jednej zmiany); samo cofnięcie jest też logowane
  z własną migawką, więc "cofnięcie cofnięcia" działa tym samym
  mechanizmem. **GUI woła WYŁĄCZNIE `operacje.wykonaj`/`cofnij`, nigdy
  `repo.*` bezpośrednio dla operacji mutujących** — inaczej mutacja
  ominęłaby migawkę i dziennik, i cofnięcie by jej nie objęło.
  `znajdz_najblizsze_migawki` — gdy migawka celu zniknęła (przycięta),
  szuka najbliższej starszej/nowszej operacji, która WCIĄŻ ma migawkę, do
  zaproponowania jako alternatywa (patrz `zakladka_historia.py` niżej).
- `zrzuty.py` — warstwa ZIMNA, osobna od `kopie.py`: gzipowany tekstowy SQL
  (`conn.iterdump()`, NIE binarny `.db`) — czytelny po rozpakowaniu,
  przenośny między maszynami/wersjami SQLite, planowany format wymiany dla
  synchronizacji stacji (X+3). Jeden zrzut na dzień (`zrob_zrzut` nadpisuje
  przy powtórnym wywołaniu tego samego dnia), **NIE przycinany** jak
  migawki — to archiwum długoterminowe, nie punkty przywracania pojedynczej
  operacji, a przy tej skali danych (dept-owa baza) rozmiar jest
  pomijalny. `PRAGMA user_version` dopisywana jawnie po `iterdump()`, bo
  ten nie obejmuje PRAGMA.

Warstwa GUI (tkinter, `gui/`) — **zero logiki biznesowej**, tylko zbieranie
wartości z pól i wywołanie warstwy logiki:

- `app.py` — okno główne, `Notebook` z pięcioma zakładkami.
  `_katalog_danych` — na Windows **`%LOCALAPPDATA%`, nie `%APPDATA%`**
  (Roaming przy profilach mobilnych wciąga bazę i historię kopii na
  ścieżkę logowania); `_przenies_ze_starej_lokalizacji` robi jednorazową
  migrację z Roaming, ale NIE nadpisuje istniejącej bazy lokalnej.
  Baza + log + dziennik razem; `_katalog_logow`
  (obsługuje bazy specjalne typu `:memory:`, które nie mają katalogu
  nadrzędnego). Haki diagnostyczne podpinane **dwukrotnie i celowo**:
  w `main()` przed zbudowaniem okna (awaria w konstruktorze) oraz na
  instancji Tk (`report_callback_exception` — `sys.excepthook` NIE łapie
  wyjątków z callbacków widgetów). `kopie.przytnij_migawki` wołane RAZ,
  zaraz po skonfigurowaniu `katalog_danych` — świadomie przy starcie, nie
  po każdej operacji (tanio, realnie ~raz dziennie, nie dokłada skanu
  katalogu do każdego zapisu). `cofnij_do` (wołane przez zakładkę
  Historia): zamyka `conn`, woła `operacje.cofnij`, **zamyka całą
  aplikację** — podmiana pliku bazy pod żywymi połączeniami/widgetami
  w kilku zakładkach naraz jest ryzykowna, restart jest prostszy
  i bezpieczniejszy niż "gorący" refresh całego okna. `main()` zdobywa
  `blokada.Blokada` PRZED zbudowaniem okna — druga instancja dostaje
  ostrzeżenie i kończy się przed `mainloop()`, nie po cichu otwiera drugie
  okno na tej samej bazie. `zrzuty.zrob_zrzut` wołane obok przycinania
  migawek, tylko jeśli dzisiejszy zrzut jeszcze nie istnieje.
- `zakladka_przeglad.py`, `zakladka_wprowadzanie.py` (formularz
  blankietowy: bloki REJON+DATA, rejon opcjonalny/nieznany + komentarz
  per blok), `zakladka_import_export.py` (+ `DialogKorektyImportu` —
  ekran korekty pokazuje WYŁĄCZNIE wiersze wymagające uwagi),
  `zakladka_slowniki.py` (podzakładki kurierzy/punkty ZPO/wykonawcy/
  rejony/firmy ZPO), `zakladka_historia.py` (log operacji + "Cofnij do
  tego punktu"; seq czytany z WARTOŚCI wiersza, nie z pozycji w drzewie —
  sortowanie po kliknięciu nagłówka w `widget_tabela.Tabela` zmienia
  kolejność wierszy). Gdy migawka celu jest przycięta,
  `DialogAlternatywnychMigawek` proponuje najbliższą starszą/nowszą
  operację z żywą migawką — obie klikalne, prowadzą do tego samego
  potwierdzenia co zwykłe cofnięcie (`_potwierdz_i_cofnij`), sprawdzenie
  istnienia pliku dzieje się PRZED tym dialogiem, nie w środku (patrz
  `operacje.znajdz_najblizsze_migawki` wyżej). **Wszystkie cztery pozostałe zakładki wołają
  `operacje.wykonaj` zamiast `repo.*` bezpośrednio przy każdej mutacji**
  (zapis blankietu, import, dodanie/zmiana/scalenie w słownikach, nowy
  punkt ZPO) — patrz `operacje.py` wyżej.
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
zgodnie z projektem. Wpięty do `zakladka_wprowadzanie.py` (pola
kurier/nadawca/adres, źródło kandydatów z `repo.pobierz_punkty`/
`pobierz_slownik`).

`zakladka_historia.py` + `operacje.wykonaj`/`cofnij` zweryfikowane end-to-end
(zrzut ekranu i testy w `test_gui_smoke.py`): zapis z formularza,
dodanie do słownika i import tworzą wpis w dzienniku z migawką;
`cofnij_do` przywraca stan pliku bazy i zamyka aplikację.

Build PyInstaller: proxy-build na Linuksie sprawdzony (pakuje się bez
błędów importu `pydantic_core`, dochodzi do tworzenia okna Tk) — realny
`.exe` wymaga budowy na Windowsie, patrz `../docs/environment.md`.

## Child DOX Index

Brak — pakiet rozrósł się w warstwy logiki + `gui/`, ale to wciąż jedna
spójna granica pracy (patrz Local Contracts wyżej). Rozbić na osobny
`gui/AGENTS.md` dopiero, jeśli podzakładki dorosną do własnych, odrębnych
reguł wykraczających poza "zero logiki biznesowej" już opisane tutaj.
