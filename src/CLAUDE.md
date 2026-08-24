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
  **`znajdz_lub_utworz_punkt_niezaufany`** (`0.1-alpha.3.2`) — OSOBNA
  funkcja od `get_or_create_punkt`, nie flaga w tamtej: tamta obsługuje
  ścieżkę zaufaną ORAZ scalanie baz (gdzie źródłem jest nasza własna baza)
  i jej semantyka nie może dryfować razem z regułami zaufania importu.
  Trzy gałęzie: (1) dokładne `(nadawca, adres)` po DOWOLNYM punkcie —
  także z PNI, co rozwiązuje pułapkę predykatu `AND pni_zpo IS NULL`
  (bez tego adres znany już jako punkt ZPO dostawałby drugi punkt tej samej
  lokalizacji); (2) jeden punkt pod adresem, inny nadawca → podpięcie
  + ostrzeżenie; (3) wiele punktów, żaden nie pasuje → NOWY punkt bez PNI
  + ostrzeżenie, **nigdy automatyczny wybór** (adres z wieloma nadawcami
  nie rozstrzyga się sam — patrz `dedukcja.py`; duplikat punktu jest
  naprawialny, ciche podpięcie pod zły punkt nie).
- `models.py` — pydantic v2. `WierszImportu` (walidacja wiersza importu,
  konwersja `datetime`→`date`, normalizacja białych znaków na
  kurier/nadawca/adres — bez tego "Michalak Maciej " ląduje jako inny
  kurier niż "Michalak Maciej", patrz historia commitów). `Blankiet` /
  `WierszBlankietu` (dane z formularza wprowadzania) — `rejon` żyje PER
  WIERSZ od `0.1-alpha.3.1` (dedukowany z adresu, patrz `dedukcja.py`),
  `komentarz` per blok zniknął z formularza (kolumna w bazie zostaje).
- `normalizacja.py` — trzy poziomy pewności: `klucz_bialych_znakow`
  (bezpieczne automatyczne scalanie), `klucz_rozmyty` +
  `odleglosc_edycyjna`/`czy_literowka` (prawdopodobna literówka,
  automatyczny dedup z możliwością odrzucenia), `znajdz_podobne`
  (różnica WYŁĄCZNIE w diakrytykach — nigdy automat, patrz
  `../docs/domain-model.md`, przypadek "Wołczuk Rafal"/"Rafał").
  `normalizuj_rejon`/`REJON_NIEZNANY = "???"` — kanoniczny "rejon
  nieznany", stosowany na KAŻDEJ ścieżce zapisu rejonu (formularz, import,
  Słowniki, scalanie baz) i przy jednorazowej naprawie już zapisanych
  danych, patrz `repo.napraw_dane` niżej.
- `repo.py` — **`transakcja(conn)`**: jawna transakcja na SAVEPOINT,
  re-entrant (fasady opakowują `zapisz_blankiet`, które samo woła
  `get_or_create_*` — zwykłe `BEGIN` by się zagnieździło i rzuciło).
  **NIE używać wbudowanego `with conn:`** — przy `isolation_level=None`
  on nic nie wycofuje; kod wygląda poprawnie i nie robi nic (przypięte
  testem `test_wbudowane_with_conn_nic_nie_wycofuje`). Złapany
  `IntegrityError` NIE unieważnia transakcji, więc per-wierszowe `except`
  w `zapisz_blankiet`/`zaimportuj` działają wewnątrz bez zmian.
  `WERSJA_SCHEMATU` (**2** od `0.1-alpha.3.1` — dwa indeksy,
  `idx_transakcje_kurier`/`idx_punkty_adres`, dla zapytań dedukcyjnych
  niżej; jedyny uprawniony powód bumpa — sama naprawa danych wersji NIE
  podbija, bo nie zmienia struktury) + `wersja_schematu`/
  `sprawdz_zgodnosc_wersji`/`wymaga_migracji`/`migruj` — musi zgadzać się
  z `PRAGMA user_version` na końcu `schema.sql`. **`migruj` jest
  addytywna i idempotentna** (sprawdza obecność każdego obiektu zamiast
  wykonywać kroki po numerze wersji), więc przeżywa też bazy w stanie
  pośrednim po przerwanej aktualizacji. Zweryfikowana na realnym
  imporcie z alpha.2: 1239 transakcji / 68 kurierów / 671 punktów
  zachowane, `integrity_check` ok.
  `napraw_dane(conn)` — celowo POZA `migruj`: bezwarunkowa, idempotentna
  (sprawdza stan, nie numer wersji — inaczej odpaliłaby się raz i baza
  scalona później z niepoprawioną kopią zostałaby zepsuta na trwałe),
  wołana z `app.py` po starcie, opakowana w `operacje.wykonaj` (migawka +
  dziennik — to największa mutacja danych w wydaniu, musi mieć punkt
  powrotu) wewnątrz `try/except` z degradacją "nie naprawiono, pracuj
  dalej" — `main()` łapie wyłącznie `NiezgodnaWersjaSchematu`, więc każdy
  inny wyjątek w naprawie zablokowałby start aplikacji NA STAŁE u
  użytkownika bez admina i konsoli. Sprząta rejony spoza
  `normalizacja.REJON_NIEZNANY` i rozjazd `firmy_zpo.nazwa`/
  `punkty.nadawca` (patrz `importer.py` niżej).
  Dostęp do danych: `zapisz_blankiet` (formularz → transakcje,
  **atomowy**, `rejon_id` liczone PER WIERSZ od `0.1-alpha.3.1` — rejon
  zszedł z bloku do wiersza, `zapisz_bloki` zniknęło), słowniki proste
  (`pobierz_slownik`/`dodaj_do_slownika`/`zmien_nazwe_w_slowniku`/
  `usun_z_slownika` — rename `firmy_zpo` propaguje do `punkty.nadawca`,
  kanoniczny wiersz `???` nie da się zmienić/skasować),
  **`pobierz_nadawcow_bez_pni`/`zmien_nadawce_bez_pni`** (`0.1-alpha.3.2` —
  nadawcy bez PNI istnieją WYŁĄCZNIE jako `punkty.nadawca` z
  `firma_zpo_id IS NULL`, bo `firmy_zpo` powstaje tylko w gałęzi z PNI
  `get_or_create_punkt`; do 3.2 literówka w ZUS/PKO/Kruk była
  nienaprawialna w aplikacji. Rename może zlepić punkty identyczne pod
  `(nadawca, adres)` — schemat NIE ma na to UNIQUE — więc scalamy je:
  wygrywa najniższe id, transakcje przegrywającego przepinamy, kolizja
  `UNIQUE(data,kurier,punkt)` rzuca `KolizjaTransakcji` i wycofuje CAŁOŚĆ),
  **`zaktualizuj_transakcje`/`usun_transakcje`/`ustaw_pole_transakcji`**
  (`0.1-alpha.3.2` — pierwsze destrukcyjne prymitywy na `transakcje` poza
  importem/formularzem. `KOLUMNY_EDYTOWALNE_TRANSAKCJI` świadomie BEZ
  nadawcy/adresu/PNI: przepięcie na inny punkt to cicha zmiana historii
  punktu, inna klasa ryzyka niż poprawka daty/ilości — korekta punktu to
  usuń + wpisz ponownie. Kolizja klucza naturalnego sprawdzana jawnym
  SELECT-em PRZED UPDATE i tylko gdy `data`/`kurier` faktycznie się
  zmieniają; `KolizjaTransakcji` niesie OPIS kolidującego wiersza, nie gołe
  „UNIQUE failed". Edycja zbiorcza w jednym SAVEPOINT — pierwsza kolizja
  wycofuje wszystko, „zmień 5 wierszy ale nie ten jeden" byłoby ciche
  i mylące), `scal_kurierow`
  (droga naprawy dla ostrzeżeń o podobieństwie, **atomowy**; przy kolizji
  `UNIQUE(data,kurier,punkt)` scalenie się nie uda — ale nie zostawi
  stanu połowicznego), `pobierz_transakcje`, `pobierz_punkty`. **`znajdz_punkt_po_pni`** (`0.1-alpha.3.3`) — odwraca kierunek
  dedukcji: PNI jest tu WEJŚCIEM, nie wyjściem. Jednoznaczność gwarantuje
  schemat (`punkty.pni_zpo UNIQUE`), więc nie ma tu żadnego rozstrzygania.
  Porównanie **tekstowe, nigdy liczbowe** — `"007"` i `"7"` to dwa różne
  punkty, a ich zrównanie to dokładnie błąd koercji naprawiony w 3.2.
  Zapytania
  dedukcyjne (`znajdz_punkty_po_adresie`/`czy_nadawca_ma_pni`/
  `historia_rejonow_punktu`/`historia_wykonawcow_kuriera`) — jedyny
  konsument to `dedukcja.py` niżej. `pobierz_transakcje` ma od
  `0.1-alpha.3.2` opcjonalne filtry (`kurier`/`data_od`/`data_do`/
  `utworzono_od`/`utworzono_do`/`sesja_uuid`/`tekst`/`zrodlo`, łączone
  koniunkcją; `tekst` escapuje `%`/`_` przed doklejeniem do wzorca `LIKE` -
  to wejście użytkownika, nie wzorzec) i zwraca też
  `id`/`uuid`/`utworzono`/`sesja_uuid`/`zrodlo` — widok
  poprawek potrzebuje ich mimo że tabela ich nie pokazuje.
  `_resolve_schema_path` rozróżnia dev vs spakowany `.exe` (PyInstaller
  rozpakowuje dane do `sys._MEIPASS`).
- `ustawienia.py` (`0.1-alpha.3.2`) — `settings.json` w katalogu danych.
  Celowo POZA bazą: ustawienia typu „odsłoń przełącznik zaawansowany"
  muszą być lokalne dla KONKRETNEJ stacji i nie mogą wędrować przy
  scalaniu baz. `wczytaj` nigdy nie rzuca (brak pliku / uszkodzony JSON /
  nie-obiekt → `{}`) — ustawienia nie mogą zablokować startu aplikacji.
  `zapisz` atomowo (plik tymczasowy + `os.replace`) i zapisuje CAŁY dict,
  więc klucze nieznane tej wersji przeżywają read-modify-write.
- `dedukcja.py` — silnik dedukcji pól formularza (`0.1-alpha.3.1`), bez
  display. Rozstrzyga najpierw **punkt** (z adresu, przez
  `repo.znajdz_punkty_po_adresie`, opcjonalnie zawężony ręcznie wpisanym
  nadawcą), dopiero z rozstrzygniętego punktu wyprowadza nadawcę/PNI/
  rejon — PNI NIGDY nie jest dedukowane niezależnie od nadawcy (adres
  z dwoma nadawcami inaczej podpinałby transakcję pod zły punkt po
  cichu, skoro `importer.get_or_create_punkt` kluczuje po PNI, nie po
  adresie). Wykonawca dedukowany z historii kuriera na poziomie
  NAGŁÓWKA blankietu, nie wiersza (`dedukuj_naglowek` — jeden blankiet =
  jeden kurier = jeden wykonawca). Zasada jednolita: jednoznaczne →
  wypełnia; niejednoznaczne → NIE wypełnia, aktywuje pole, warianty jako
  `StanPola.kandydaci`. Ilość/„w tym ZPO" nigdy nie bramują ani nie są
  źródłem dedukcji innych pól — dedukcja rusza z kuriera/adresu
  niezależnie od stanu Ilości; jej jedyna rola to jednokierunkowe
  autouzupełnienie „w tym ZPO", bramowane `czy_nadawca_ma_pni`.
  `sprawdz_niezmienniki` — stany zakazane (pomarańcz/czerwień bez
  `aktywne`, aktywne+niekolorowe-szare bez `w_nawigacji`), wołane
  w testach. `kolejnosc_pol(tryb, ...)` zwraca KLUCZE pól (krotki), nie
  widgety — mapowanie klucz→widget zostaje w `gui/` (patrz Work Guidance
  niżej); pole pomarańczowe/czerwone wchodzi do kolejności niezależnie od
  tego, czy jest polem głównym, inaczej nie da się go wypełnić
  z klawiatury. `przesun_w_kolejnosci` — czysty next/prev po tej liście
  (zawija na końcach), napędza Tab/Enter/Shift-Tab w
  `gui/zakladka_wprowadzanie.py`. `czy_koniec_ostatniego_wiersza`
  (`0.1-alpha.3.2`) — predykat „to ostatni klucz CAŁEJ sekwencji", na
  którym GUI opiera auto-dodawanie wiersza (decyzja tutaj, akcja w widoku).
  **Rejon od `0.1-alpha.3.2` NIE jest już wpisywalny ręcznie**: jednoznaczna
  historia punktu → zielone wypełnienie, brak historii ALBO historia
  sprzeczna → szare/nieaktywne (zapis rozstrzyga na kanoniczne `???`).
  Wcześniej pole aktywowało się do ręcznego zgadywania — czyli dokładnie
  tego, co rejonarz (`0.1-alpha.3.3/3.4`) ma zastąpić źródłem prawdy.
  **Od `0.1-alpha.3.3` `dedukuj_wiersz` przyjmuje opcjonalne `conn_rejonarz`.**
  Pominięte ALBO wskazujące na pustą migawkę daje zachowanie bit w bit
  dotychczasowe — własność celowa, przypięta testem w obie strony:
  na stacji bez zaimportowanej migawki program ma działać dokładnie tak
  jak przedtem. Migawka WYPEŁNIA LUKĘ (historia pusta lub sprzeczna),
  nigdy nie nadpisuje jednoznacznej historii punktu — reguły kolizji
  „historia vs rejonarz" to §10 raportu BaŚKi i osobna robota.
- `import_orchestrator.py` — cały import w partii: `zwaliduj_wiersze`,
  `znajdz_propozycje_scalenia_kurierow` (literówki, auto-merge PRZED
  zapisem, nie cofanie po fakcie), `znajdz_ostrzezenia_podobienstwa_kurierow`
  (diakrytyki, tylko sygnał), `zaimportuj`.
  **`zaimportuj(..., zaufany=False)`** (`0.1-alpha.3.2`) — domyślnie
  NIEZAUFANY, bo brak jawnego zaufania musi znaczyć brak zaufania. Plik
  niezaufany NIE wnosi **PNI** (klucz tożsamości punktu — śmieć podpina
  transakcję pod cudzy punkt, zamienia kolejne wiersze w „duplikaty" i
  trwale otwiera pole „w tym ZPO" przez `czy_nadawca_ma_pni`) ani **rejonu**
  (dane z papieru zakłamane; wiersze lądują na `???` i stają się
  kandydatami dla rejonarza). Reszta wchodzi normalnie — odcinamy WYŁĄCZNIE
  to, czego nie da się ani zweryfikować, ani poprawić ręcznie. `zrodlo`
  **wyprowadza się z `zaufany`**, nie jest wolnym parametrem — nie da się
  zapisać `'import_zaufany'` dla pliku, któremu nie ufamy.
- `eksport.py` — transakcje → `.xlsx`. `NAGLOWKI` to stała z dokładnymi
  nagłówkami ze snapshotu źródłowego (białe znaki są częścią danych, nie
  literówką do poprawienia). Typy komórek eksportowane kanonicznie czysto
  (int/date), świadome odstępstwo od niespójności źródła — patrz plan MVP.
  **PNI jest wyjątkiem i zostaje TEKSTEM** (`0.1-alpha.3.2`): to klucz
  (`punkty.pni_zpo UNIQUE`), nie wielkość liczbowa — rzutowanie na int
  zamieniało `"007"` w `7`, reimport czytał `"7"` i ten sam fizyczny punkt
  dostawał dwa klucze (samo-zadana korupcja, bez obcego pliku).
  **Znacznik pochodzenia + odcisk** (`NAZWA_ZNACZNIKA`/`NAZWA_ODCISKU`,
  właściwości niestandardowe dokumentu): `odcisk_wierszy` liczy SHA-256
  kanonicznej postaci komórek, `zweryfikuj_plik` zwraca `PLIK_ZAUFANY` /
  `PLIK_OBCY` / `PLIK_ZMODYFIKOWANY`. Odcisk liczony z GOTOWEGO arkusza
  (`ws.iter_rows`), nie z wierszy z bazy — import policzy hash z tych samych
  komórek, więc obie strony muszą wyjść z tej samej reprezentacji.
  Nieczytelny plik to `PLIK_OBCY`, nie wyjątek: „nie umiem zweryfikować"
  znaczy dokładnie tyle co „nie ufam", a decyzja o zaufaniu nie może
  wysadzić importu.
- `profil_kolumn.py` (`0.1-alpha.3.3`) — dopasowanie kolumn arkusza po
  NAGŁÓWKU, nie po pozycji. Profil jest parametrem, nie stałą modułową,
  więc moduł nie wie nic o rejonach. Porównanie idzie po
  `normalizacja.klucz_rozmyty` z `czy_literowka` jako ostatnią deską
  ratunku — a ta wymaga DOKŁADNIE jednego kandydata, bo dwóch to już
  niejednoznaczność. `dopasuj_kolumny` **nie rzuca przy pierwszym braku**:
  oddaje pełny obraz (`braki` + `nierozpoznane`), bo rzucanie pokazywałoby
  jeden problem naraz. Powtórzony nagłówek nie nadpisuje pierwszego —
  arkusze bywają sklejane z kilku. `pasuje_do_wzorca` zwraca **None dla
  pól bez wzorca**, nie False: "nie wiem" i "nie pasuje" to dwie różne
  odpowiedzi, a ich zlanie zamieniłoby siatkę bezpieczeństwa w generator
  fałszywych alarmów. **Świadomie NIE podpięty pod
  `import_orchestrator.MAPA_NAGLOWKOW`** — tamta ścieżka działa, jej
  przepisanie to osobna robota.
- `rejonarz.py` (`0.1-alpha.3.3`) — migawka `adres → rejon` z eksportu
  BaŚKi w **OSOBNYM pliku `rejonarz.db`**, nie w głównej bazie. Zbiór jest
  identyczny na wszystkich stacjach, więc nie ma po co wędrować przez
  `scalanie.py` ani powiększać każdej migawki z `kopie.py`; skutkiem
  ubocznym `schema.sql` i `WERSJA_SCHEMATU` zostają nietknięte, czyli
  integracja nie niesie ryzyka migracji dla danych rozliczeniowych.
  Pierwszy kod w repo pracujący na dużym zbiorze: `read_only=True` +
  generator przy odczycie, `executemany` partiami przy zapisie (reszta
  importów materializuje cały arkusz — przy >400 tys. wierszy nie
  przejdzie). Trzy rozstrzygnięcia, nie szczegóły implementacji:
  (1) **import PODMIENIA całą migawkę**, bo to stan, nie dziennik
  przyrostowy — przy dopisywaniu adresy wycofane z BaŚKi zostawałyby
  u nas na zawsze, wyglądając na potwierdzone; (2) **wartownik nie trafia
  do migawki** — zapisane `???` kazałoby dedukcji mówić "wiem, że nie
  wiem" tam, gdzie prawdą jest "nie mam wpisu"; (3) **sprzeczna migawka
  daje `None`**, nigdy pierwszego lepszego — `UNIQUE(klucz, rejon)`
  zdejmuje powtórzone pary, a dwa różne rejony pod jednym kluczem zostają
  oba i `znajdz_rejon` odmawia rozstrzygnięcia. Filtr `WEZEL_ZPO="WW"` +
  `TYP_KIEROWANIA_ZPO="1"` jest tutaj, nie w normalizacji (wymaga widoku
  na cały wiersz); brak tych kolumn w arkuszu oznacza brak filtrowania,
  ale **jawnie zaznaczony** w `WynikImportu.bez_filtrowania`.
  `rozbij_adres`/`znajdz_rejon_dla_adresu` — most do formularza, który
  trzyma adres jako jeden wolny tekst; to proteza na czas do wdrożenia
  strukturalnego adresu (`../docs/normalization-v2.md`). Adres bez
  miejscowości (`"Odkryta 24"`, w realnych danych bardzo częsty) szuka po
  samej ulicy i numerze, ale odpowiada **wyłącznie przy jednoznacznym
  trafieniu** — ta sama ulica w dwóch miastach to nie przypadek do
  rozstrzygnięcia losowaniem.
  **Lokal** (format adresu to miejscowość / ulica / budynek / lokal,
  lokal opcjonalny): odcinają go WYŁĄCZNIE jawne znaczniki (`m.`, `lok.`,
  `mieszk.`). Goły ukośnik zostaje częścią numeru budynku, bo `"12/14"`
  bywa podwójnym numerem JEDNEGO budynku równie często, co budynkiem
  z mieszkaniem — rozstrzyga dopiero wyszukiwanie, próbując obu odczytów
  z pierwszeństwem dosłownego. Lokal jest **rozpoznawany przy imporcie,
  ale nie zapisywany**: rejon jest przypisany do budynku, więc lokal nie
  wnosi informacji, a w kluczu rozbiłby deduplikację (pięć mieszkań =
  pięć wierszy mówiących to samo).
- `podpowiedzi.py` — silnik podpowiedzi (`podpowiedz`,
  `najlepsza_podpowiedz`), źródło kandydatów wstrzykiwane, nie zaszyte.
- `uzytkownicy.py` — tożsamość osoby wprowadzającej dane. `users.id` to
  **UUIDv5 z `domena\login`** (`NAMESPACE_ZPO` — nie zmieniać, zmiana
  rozdwoiłaby każdą osobę), NIE losowy UUID: losowy rozjechałby się między
  stacjami i po ich zsynchronizowaniu ta sama osoba istniałaby wielokrotnie.
  `nr_kadrowy` (`[a-zA-Z0-9]{5}`, case sensitive) to atrybut biznesowy
  **obok** UUID, nie zamiast — wpisuje go człowiek, więc literówka jest
  niewykrywalna. Para daje kontrolę krzyżową (`ostrzezenia_tozsamosci`,
  miękkie ostrzeżenia). W SQLite pilnuje formatu `GLOB`, nie `LIKE`
  (`LIKE` jest niewrażliwy na wielkość liter). Numery kadrowe KURIERÓW to
  inny byt: inny format i relacja 1:N — patrz `../docs/roadmap.md`.
  Od `0.1-alpha.3.2` `wymaga_uzupelnienia` NIE sprawdza już `nr_kadrowy`
  (pracownicy jeszcze go nie mają — nie może blokować pierwszego
  uruchomienia; pole zostało w dialogu jako opcjonalne, przywrócenie
  wymagalności to jedna linia, → AID-99).
  **`login_rozszerzony`/`znajdz_konta_dla_loginu`** — konta Windows bywają
  współdzielone przez kilka osób na jednej stacji; login
  `DOMENA\login#Imię Nazwisko` daje im osobną tożsamość BEZ nowego
  mechanizmu identyfikacji (to wciąż zwykły string wchodzący do
  `uuid_uzytkownika`, więc pozostaje deterministyczny między stacjami —
  kluczowe dla przyszłej synchronizacji). Który z nich jest aktywny,
  trzyma `settings.json` (`aktywny_login`), nie baza.
- `scalanie.py` — ręczne, JEDNOKIERUNKOWE scalanie dwóch baz: docelowa
  (żywa) WCHŁANIA źródłową (plik `.db`, otwierany WYŁĄCZNIE do odczytu
  przez URI SQLite `mode=ro` — twarda gwarancja silnika, nie tylko
  konwencja; źródło zostaje nietknięte, bezpieczne do ponownego scalenia
  gdzie indziej). Dwuetapowe jak `import_orchestrator.py`:
  `zaplanuj_scalenie` (WYŁĄCZNIE odczyt, buduje pełny plan) →
  `wykonaj_scalenie` (stosuje, atomowo przez `repo.transakcja`).
  Dopasowanie słowników po kluczu NATURALNYM, nie po `id` (różne
  surogatowe ID na różnych stacjach): `_dopasuj_prosty_slownik` reużywa
  trójpoziomowe podejście z importu (białe znaki → automat, literówka →
  propozycja — WYŁĄCZNIE kurierzy, jak przy imporcie, diakrytyki →
  ostrzeżenie, nigdy automat). Punkty reużywają `importer.get_or_create_punkt`
  wprost przy wykonaniu (ten sam klucz PNI/adres, żadnej osobnej logiki).
  `users.id` to już UUIDv5 — dopisanie brakujących, rozjazd nr_kadrowego
  tylko informacyjny (niska stawka vs. konflikt ilości).
  **Konflikt wartości (ta sama trójka data+kurier+punkt, różne ilości)
  NIGDY nie jest rozstrzygany automatycznie** (roadmap.md) — domyślnie
  zostaje wartość DOCELOWA (nigdy nie nadpisuje po cichu), zmiana
  wyłącznie przez jawne `rozstrzygniecia_konfliktow`.
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
  `liczba_pominietych` dołożona w `0.1-alpha.3.2` (licznik, więc kontraktu
  no-PII nie narusza): bez niej zapis blankietu, w którym WSZYSTKO odpadło
  jako duplikat, wyglądał w Historii identycznie jak pełny sukces.
  Uwaga na napięcie: istniejące `etykieta` przy zapisie blankietu/imporcie
  zawierają nazwisko kuriera i nazwę pliku, nowe wpisy (`edycja_transakcji`,
  `usuniecie_transakcji`, `edycja_zbiorcza`, `zmien_nadawce`) trzymają
  kontrakt ostrzej — same identyfikatory i liczniki.
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
  synchronizacji między stacjami. Jeden zrzut na dzień (`zrob_zrzut` nadpisuje
  przy powtórnym wywołaniu tego samego dnia), **NIE przycinany** jak
  migawki — to archiwum długoterminowe, nie punkty przywracania pojedynczej
  operacji, a przy tej skali danych (dept-owa baza) rozmiar jest
  pomijalny. `PRAGMA user_version` dopisywana jawnie po `iterdump()`, bo
  ten nie obejmuje PRAGMA.

Warstwa GUI (tkinter, `gui/`) — **zero logiki biznesowej**, tylko zbieranie
wartości z pól i wywołanie warstwy logiki:

- `styl.py` — JEDYNE miejsce ustalające kolory, odstępy i czcionki
  (`PALETA`, `ODSTEPY`, `zastosuj_styl(root)`). **Jeszcze NIE wpięty do
  `app.py`** — czeka na akceptację, makieta i podgląd w `../demo/`.
  `theme_use("clam")` jest warunkiem koniecznym, nie estetycznym: `vista`
  (domyślny na Windowsie) ignoruje większość ustawianych kolorów, więc bez
  podmiany motywu reszta konfiguracji nie ma żadnego efektu.
  `KOLORY_STANOW` **jest tym samym obiektem** co `widget_pole.KOLORY`, nie
  kopią — dwie palety wskaźników rozjechałyby się po cichu przy pierwszej
  korekcie jednej z nich (przypięte testem).
  `PALETA["tekst_slaby"]` ma kontrast 2.85:1 i **nie wolno go użyć jako
  koloru tekstu** — test `test_tekst_slaby_nie_jest_uzywany_do_tekstu`
  skanuje źródło i tego pilnuje; etykiety kolumn mówią nietechnicznemu
  użytkownikowi, co ma wpisać, więc to najgorsze miejsce na oszczędzanie
  na czytelności. `wlacz_swiadomosc_dpi()` jest ŚWIADOMIE osobnym
  wywołaniem, nie efektem ubocznym `zastosuj_styl` — zmienia rzeczywisty
  rozmiar okna w pikselach, więc układ trzeba obejrzeć na docelowej
  maszynie; poza Windowsem i bez `shcore.dll` jest bezpiecznym brakiem
  działania (rozmyta aplikacja jest do przeżycia, aplikacja, która nie
  startuje — nie).
- `app.py` — okno główne, `Notebook` z sześcioma zakładkami.
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
- `zakladka_przeglad.py`, `zakladka_wprowadzanie.py` (formularz: nagłówek
  kurier+data+wykonawca(dedukowany) + płaska lista wierszy — bloki
  REJON+DATA i komentarz per blok zniknęli w `0.1-alpha.3.1`, rejon
  zszedł do wiersza i jest dedukowany z adresu razem z nadawcą/PNI przez
  `dedukcja.py`. `WierszWidget` NIE jest już `Frame'em`: jego komórki
  (`widget_pole.PoleZeWskaznikiem`) grid-ują się wprost do jednej
  wspólnej siatki z etykietami nagłówka kolumn (wiersz 0), więc rozjazd
  szerokości kolumn jest konstrukcyjnie niemożliwy. Nawigacja
  Tab/Enter/Shift-Tab/`ISO_Left_Tab` idzie przez `dedukcja.kolejnosc_pol`
  + `przesun_w_kolejnosci`, NIE przez naturalny porządek widgetów w
  gridzie — pole aktywowane niejednoznacznie (np. nadawca) może wylądować
  "za" polem, na którym użytkownik już jest.
  **Zmiany `0.1-alpha.3.2`:** podgląd filtruje domyślnie po `sesja_uuid`
  ORAZ `zrodlo="formularz"` (checkbox odsłania całą bazę, bez żadnego
  z tych filtrów) - sam `sesja_uuid` nie wystarcza, bo import odpalony
  w tym samym uruchomieniu dzieli sesję z formularzem, a ma własny ekran
  korekty do przeglądania swoich wyników. Dwuklik w podglądzie otwiera
  `DialogEdycji`; Tab z ostatniego pola CAŁEJ kolejności dodaje nowy
  wiersz, ale tylko gdy ostatni wiersz nie jest pusty (predykat
  `dedukcja.czy_koniec_ostatniego_wiersza` — decyzja w logice, akcja w GUI);
  po zapisie znikają WYŁĄCZNIE wiersze faktycznie zapisane, pominięte
  zostają wypełnione do poprawki (`wyniki` z `zapisz_blankiet` są indeksowo
  równoległe do wierszy niepustych, filtrowanych tym samym
  `formularz_logika.wiersz_pusty` co `zbuduj_blankiet`), a status dostaje
  kolor z `widget_pole.KOLORY` i wypisuje numery+powody pominięć),
  `zakladka_import_export.py` (+ `DialogKorektyImportu` —
  ekran korekty pokazuje WYŁĄCZNIE wiersze wymagające uwagi; od
  `0.1-alpha.3.2` na górze panel zaufania: `czy_zaufany()` rozstrzyga, czy
  import wniesie PNI/rejon, a checkbox wymuszenia renderuje się TYLKO gdy
  `settings.json` ma wpis `zaawansowane.pokaz_wymuszenie_zaufania` I plik
  jest `PLIK_OBCY` — dla `PLIK_ZMODYFIKOWANY` nie powstaje w ogóle, więc
  sfałszowanego pliku nie da się odblokować żadną drogą),
  `zakladka_slowniki.py` (podzakładki kurierzy/punkty ZPO/wykonawcy/
  rejony/firmy ZPO + **„Nadawcy (bez PNI)"** dołożona na KOŃCU listy, żeby
  nie przesunąć istniejących indeksów `_podzakladki[...]`),
  `zakladka_scalanie.py` (`DialogKorektyScalania` -
  ten sam wzorzec ekranu korekty co import: pokazuje WYŁĄCZNIE propozycje
  literówek/różnice w zapisie/konflikty ilości, reszta wchodzi/pomija się
  cicho; reużywa `gui.roznice.segmenty_roznicy` i
  `zakladka_import_export._pole_z_roznicami` do podświetlania różnic),
  `zakladka_historia.py` (log operacji + "Cofnij do
  tego punktu"; seq czytany z WARTOŚCI wiersza, nie z pozycji w drzewie —
  sortowanie po kliknięciu nagłówka w `widget_tabela.Tabela` zmienia
  kolejność wierszy). Gdy migawka celu jest przycięta,
  `DialogAlternatywnychMigawek` proponuje najbliższą starszą/nowszą
  operację z żywą migawką — obie klikalne, prowadzą do tego samego
  potwierdzenia co zwykłe cofnięcie (`_potwierdz_i_cofnij`), sprawdzenie
  istnienia pliku dzieje się PRZED tym dialogiem, nie w środku (patrz
  `operacje.znajdz_najblizsze_migawki` wyżej). **Wszystkie pozostałe
  zakładki wołają `operacje.wykonaj` zamiast `repo.*` bezpośrednio przy
  każdej mutacji** (zapis blankietu, import, dodanie/zmiana/scalenie
  w słownikach, nowy punkt ZPO, scalanie dwóch baz) — patrz `operacje.py`
  wyżej.
- `formularz_logika.py` — jedyny most między formularzem a
  `models.py`/pydantic; GUI wyświetla błędy walidacji, nie decyduje o nich.
  `wiersz_pusty` jest PUBLICZNE od `0.1-alpha.3.2` — `zbuduj_blankiet`
  i selektywne czyszczenie siatki po zapisie MUSZĄ filtrować tym samym
  predykatem, inaczej rozjeżdżają się indeksy wyników.
- `zakladka_przeglad.py` jest od `0.1-alpha.3.2` **widokiem poprawek**, nie
  listą tylko do odczytu: pasek filtrów (kurier/daty/tekst/bieżąca sesja),
  dwuklik → `DialogEdycji`, operacje zbiorcze (`_DialogUstawPoleZbiorczo`)
  i usuwanie z potwierdzeniem pokazującym PRÓBKĘ znikających wierszy
  (idioto-odporność — patrz `../docs/ux-ui.md`). Świadomie przebudowa
  istniejącej zakładki, nie nowa: „znajdź i popraw" ma być jednym miejscem.
- `dialog_edycji.py` (`0.1-alpha.3.2`) — poprawka jednej transakcji.
  ŚWIADOMIE zwykły modal, BEZ `dedukcja.py`/`PoleZeWskaznikiem`: korekta to
  jawna decyzja człowieka nad już zapisanym wierszem, dedukcja walcząca
  z ręczną poprawką byłaby antywzorcem. Współdzielony przez Przegląd
  i podgląd w formularzu.
- `widget_tabela.py` — wspólna tabela z sortowaniem i Ctrl+scroll zoom.
  `wiersz_zaznaczony`/`wiersze_zaznaczone` zwracają PEŁNE dicty (nie tylko
  kolumny wyświetlane — stąd dostępne `id`/`uuid`), mapa `iid → wiersz`
  przebudowywana przy każdym odświeżeniu, więc przeżywa sortowanie (ta sama
  lekcja co `seq` w `zakladka_historia.py`). `on_dwuklik` opcjonalny — bez
  niego zdarzenie nie jest w ogóle bindowane, żeby nie ruszać istniejących
  użytkowników tylko-do-odczytu.
- `widget_autocomplete.py` — dropdown + klawiatura (bez ghost textu).
  Zweryfikowany w izolacji (zrzuty ekranu: dropdown renderuje się
  poprawnie, dopasowanie rozmyte działa, Tab/strzałki/zatwierdzanie
  działają) — patrz Verification. `ustaw_stan_pola(state, takefocus)` —
  NIE samo `state`: `readonly` samo w sobie nie wypada z nawigacji Tab,
  dopiero razem z `takefocus=0` (zweryfikowane empirycznie).
  `ustaw_zrodlo_kandydatow` — podmiana źródła w locie, pole dedukowane
  niejednoznacznie dostaje własną zawężoną listę (`dedukcja.StanPola.
  kandydaci`) zamiast pełnego słownika. `on_dalej` — Tab/Return go wołają
  zamiast domyślnego przejścia Tk; `_zatwierdz_i_dalej` zwraca `"break"`
  TYLKO gdy podany, inaczej Tab w tym polu przestałby działać całkowicie.
  `rozwijaj_na_pusty_fokus` — pokazuje kandydatów na pustym polu od razu
  po fokusie (bo `podpowiedz("")` zwraca `[]` — bez tego pole
  pomarańczowe z konkretnymi wariantami nie pokazałoby nic akurat wtedy,
  gdy afordancja jest najbardziej potrzebna); domyślnie WYŁĄCZONE, żeby
  pełny słownik (kurier/nadawca/adres) nie wyskakiwał na każdy fokus.
  **Wpięty do `zakladka_wprowadzanie.py`** (kurier, nadawca, adres, a od
  `0.1-alpha.3.1` też wykonawca — dla pokazywania kandydatów dedukcji),
  źródło kandydatów z `repo.pobierz_punkty`/`pobierz_slownik`/
  `dedukcja.StanPola.kandydaci`. Pole `rejon` korzysta z tego samego
  widgetu, ale WYŁĄCZNIE jako prezentacja dedukcji (puste źródło
  kandydatów) — od `0.1-alpha.3.2` nie jest już ręcznie edytowalne, patrz
  `dedukcja.py` niżej.
- `widget_pole.py` — **przebudowany 2026-08-24** (decyzja Papavera po
  obejrzeniu siatki wariantów). Trzy zmiany kontraktu:
  (1) **grubość obwódki jest STAŁA** (`GRUBOSC_OBWODKI = 1`); wcześniej
  przełączała się 0/1/2 px, co zmienia żądany rozmiar widgetu i zawartość
  komórek skakała przy każdej dedukcji — sygnał niesie teraz wyłącznie
  kolor. (2) **Wyglądem rządzi FOKUS, nie `aktywne`**: pole z kursorem
  dostaje pełny kolor stanu (wariant W2), pole bez kursora przygaszony
  (W3), a „następne w kolejce Tab" trafia w środek rampy. `aktywne`
  zostaje wyłącznie tym, czym było zawsze — edytowalność i obecność
  w nawigacji. `ustaw_fokus` jest publiczne mimo automatycznych bindingów
  `<FocusIn>`/`<FocusOut>`, żeby dało się je testować bez symulowania
  zdarzeń Tk. (3) **`ustaw_liste(ile)`** — afordancja rozwijanej listy
  (wariant A2, szary box z `▾`). Widget nie zna liczby kandydatów sam:
  `StanPola` rozpakowuje warstwa wyżej, a pytanie dziecka przy renderze
  byłoby zapytaniem do bazy. Strzałka pakuje się z `before=widget_pola`,
  bo pole ma `expand=True` i inaczej zabrałoby całą szerokość; jest
  RODZEŃSTWEM pola, nie warstwą pośrednią, więc test struktury zostaje
  spełniony. **Box strzałki uczestniczy w tej samej rampie co obwódka**
  (`styl.STRZALKA_TLO*`): pole bez kursora przygasza się CAŁE, bo jasny
  prostokąt obok przygaszonej obwódki rozbijałby pole na dwa niezależne
  sygnały. Kolor odświeża się przy każdej zmianie fokusu, nie tylko przy
  tworzeniu strzałki — dedukcja potrafi dać warianty już po tym, jak
  użytkownik wszedł w pole. `KOLORY` to re-eksport `styl.KOLORY_STANOW`, nie kopia —
  zależność odwrócona, bo moduł tokenów nie powinien pytać widgetu
  o kolory.
- `widget_pole.py` (wcześniejszy opis) — `PoleZeWskaznikiem` (`0.1-alpha.3.1`): `tk.Frame`
  (NIE `ttk.Frame` — `highlightthickness`/`highlightbackground` na
  obwódkę jest opcją tk-ową) owijający widget pola paskiem koloru stanu
  (`dedukcja.STANY`) + obwódką: "wymaga uwagi" (2px, wygrywa przy
  konflikcie) albo "następne w kolejce Tab" (1px, ten sam motyw koloru).
  Konstruktor bierze FABRYKĘ widgetu (`parent -> widget`), nie gotowy
  widget — Tk pakuje/griduje widget do jego rzeczywistego rodzica
  z konstrukcji, więc gotowy widget zbudowany z innym rodzicem
  wylądowałby jako rodzeństwo wrappera, nie w jego środku (złapane
  eksperymentalnie przed napisaniem finalnej wersji, patrz historia
  commitów).

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
zgodnie z projektem. Wpięty do `zakladka_wprowadzanie.py` (kurier, nadawca,
adres, wykonawca — rejon też, ale wyłącznie jako prezentacja dedukcji, patrz
Local Contracts).

Dedukcja pól, wskaźniki i nawigacja (`0.1-alpha.3.1`) zweryfikowane
bezgłowo pod Xvfb (`test_dedukcja.py`, `test_widget_pole.py`,
`test_widget_autocomplete.py`, `test_nawigacja_wprowadzanie.py` —
`focus_get()` po Tab/Enter/Shift-Tab/`ISO_Left_Tab`, w tym jedno
`event_generate("<Tab>")` jako dowód end-to-end, nie tylko wywołania
metod bezpośrednio) oraz zrzutem ekranu: nagłówek kolumn wyrównany z
danymi, kolorowa obwódka na polu niejednoznacznym (nadawca/wykonawca
pomarańczowe), szare tło na polu nieaktywnym/dedukowanym. **Nie
zweryfikowane pod motywem `vista`** — `PoleZeWskaznikiem` to `tk.Frame`
w aplikacji poza tym `ttk`, więc tło może odróżniać się wizualnie od
reszty formularza tylko na Windowsie (`clam`/`default` pod Xvfb tego nie
pokażą), patrz `../docs/environment.md`.

`zakladka_historia.py` + `operacje.wykonaj`/`cofnij` zweryfikowane end-to-end
(zrzut ekranu i testy w `test_gui_smoke.py`): zapis z formularza,
dodanie do słownika i import tworzą wpis w dzienniku z migawką;
`cofnij_do` przywraca stan pliku bazy i zamyka aplikację.

`0.1-alpha.3.2` zweryfikowane bezgłowo pod Xvfb, nowe pliki testowe:
`test_korekty.py` (edycja/usuwanie/kolizje — każda ścieżka błędu sprawdza,
że baza zostaje NIETKNIĘTA), `test_zakladka_przeglad.py`,
`test_dialog_edycji.py`, `test_zakladka_wprowadzanie_zapis.py` (status,
selektywne czyszczenie siatki, podgląd sesyjny), `test_widget_tabela.py`
(zaznaczenie odporne na sortowanie), `test_ustawienia.py`,
`test_dialog_uzytkownika.py`, `test_zakladka_slowniki_nadawcy.py`,
**`test_zaufanie_importu.py`** (trzy gałęzie podpinania punktu
niezaufanego, w tym adres istniejący już jako punkt Z PNI → BEZ duplikatu)
i `test_zakladka_import_zaufanie.py` (przełącznik wymuszenia niedostępny
dla pliku ze złamanym odciskiem — test sprawdza to wprost).
Znacznik i odcisk eksportu testowane przez REALNY round-trip plikowy
(zapis → `load_workbook` → weryfikacja), łącznie z testem manipulacji:
zmiana jednej komórki musi dać `PLIK_ZMODYFIKOWANY`.

Build PyInstaller: proxy-build na Linuksie sprawdzony (pakuje się bez
błędów importu `pydantic_core`, dochodzi do tworzenia okna Tk) — realny
`.exe` wymaga budowy na Windowsie, patrz `../docs/environment.md`.

## Child DOX Index

Brak — pakiet rozrósł się w warstwy logiki + `gui/`, ale to wciąż jedna
spójna granica pracy (patrz Local Contracts wyżej). Rozbić na osobny
`gui/AGENTS.md` dopiero, jeśli podzakładki dorosną do własnych, odrębnych
reguł wykraczających poza "zero logiki biznesowej" już opisane tutaj.
