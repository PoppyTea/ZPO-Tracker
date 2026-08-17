# Roadmap

Referencja dla `CLAUDE.md`. Źródło prawdy o kolejności prac.

Podział odpowiedzialności między dokumentami:

- **`roadmap.md`** (ten plik) — co i w jakiej kolejności, plus otwarte
  pytania kierunkowe: decyzje, które przemodelują samą roadmapę
- **`backlog.md`** — konkretne jednostki pracy do wzięcia
- GitHub milestones — odzwierciedlają wersje niżej; GitHub issues —
  bieżące bugi i pojedyncze funkcje

## Kierunek po serii 0.1-alpha.x

Aprobata kierownictwa WER Ciemne (patrz `domain-model.md`, sekcja "Cel
i kontekst") nadaje projektowi wyraźny cel nadrzędny: **zapewnienie
i utrzymanie jakości danych rozliczeniowych to główny cel programu, nie
efekt uboczny.** Seria `0.1-alpha.x` adresuje komfort i szybkość
wprowadzania danych — po jej zamknięciu kolejne kierunki prac budowane są
WOKÓŁ tego celu, jako środowisko, które jakość danych zapewnia lub wręcz
gwarantuje, a nie tylko na nią pozwala. Konkretny zakres tej fazy do
ustalenia po `0.1-alpha.3` (info od Papavera).

## Wersje

| Wersja | Status | Zakres |
|---|---|---|
| `v0.1.0-alpha.2` | wydane | MVP: import/export, formularz blankietowy, słowniki, podpowiedzi |
| `v0.1.0-alpha.3` | wydane | trwałość danych, atrybucja, ręczne scalanie baz (niżej) |
| **`0.1-alpha.3.1`** | wydane | dedukcja pól formularza, wskaźniki stanu, tryb auto |
| **`0.1-alpha.3.2`** | w toku | **używalność + zdrowie danych**: poprawki po zapisie, zaufanie importu |
| **`0.1-alpha.3.3/3.4`** | planowane | rejonarz jako źródło prawdy rejonów (+ backfill), narzędzie naprawy starych Exceli |
| **`0.1-alpha.4`** | planowane | przebudowa UI/UX pod realne potrzeby + kanał feedbacku |
| **`0.1-alpha.5`** | planowane | tryb pół-auto wprowadzania (wymaga sensownego interfejsu) |
| **`0.1-alpha.6`** | planowane | automatyczna synchronizacja między stacjami |

**Warunek przejścia do `0.1-alpha.4`:** program uznany za nadający się do
użytku. Funkcjonalności mogą być podstawowe, ale muszą być. Filtr, przez
który musi przejść każdy kandydat do `0.1-alpha.3.x`:

1. Czy przybliża nas to do umożliwienia realnej pracy na programie?
2. Czy pomaga powstrzymać wpływ skorumpowanych danych z wcześniejszych
   miesięcy na nowo tworzone dane?
3. Czy naraża dane na zepsucie lub niekompletność, którą trudno będzie
   naprawić później? (jak wyglądałaby taka naprawa? czy mamy źródło prawdy?)

### `0.1-alpha.3` — domknięcie MVP: trwałość, atrybucja, scalanie

Cel: żaden pojedynczy błąd (użytkownika, aplikacji, dysku) nie kosztuje
więcej niż jedną operację pracy, a każda zmiana ma znanego autora.

Trzy fundamenty, których dziś brakuje, a które przy ~10 stacjach i realnych
danych rozliczeniowych zamieniają się w utratę pracy:

1. **Brak transakcji** — `repo.polacz` działa w autocommit, więc
   `scal_kurierow` (UPDATE + DELETE) może zostawić bazę w stanie połowicznym
2. **Brak logowania** — w buildzie `console=False` `sys.stderr is None`,
   więc każdy wyjątek w callbacku Tk jest dziś całkowicie niewidoczny
3. **Brak kopii i cofania** — zły import oznacza ręczną odbudowę miesiąca

Zakres:

- transakcje (SAVEPOINT, re-entrant), `PRAGMA user_version` + migracje
- `%LOCALAPPDATA%` zamiast `%APPDATA%` (Roaming = profil mobilny)
- `dziennik.py` — log tekstowy + JSONL dziennik operacji, przechwytywanie
  awarii (`sys.excepthook`, `Tk.report_callback_exception`, `faulthandler`)
- atrybucja: tabela `users`, `transakcje.autor_id`/`uuid`/znaczniki czasu
- migawki + cofanie (`kopie.py`, `operacje.py`, zakładka Historia)
- zrzuty `.sql.gz` — warstwa zimna **i zarazem format wymiany dla
  synchronizacji między stacjami**
- **ręczne scalanie dwóch baz** z obsługą konfliktów
- blokada uruchomienia drugiej instancji

### `0.1-alpha.3.1` — dedukcja pól, wskaźniki, tryb auto

Cel: **program przestaje wymuszać pracę po staremu.** Po wpisaniu kuriera,
daty, adresu i ilości reszta wiersza (nadawca, PNI, rejon, wykonawca) wchodzi
sama z bazy, a każde pole kolorowym paskiem po lewej mówi, czy jest OK
(zielony), wymaga uwagi (pomarańczowy), czy blokuje zapis (czerwony).

Zakres:

- **blankiet = 1 na (kurier, data)** — bloki rejonów znikają, zostaje
  nagłówek + płaska lista wierszy
- **`rejon` schodzi do wiersza** i jest dedukowany z adresu; `wykonawca`
  z kuriera
- reguła jednolita: jednoznaczne → wypełniamy; niejednoznaczne → NIE
  wypełniamy, aktywujemy pole, warianty dajemy jako podpowiedzi
- `dedukcja.py` — silnik rozstrzygający najpierw **punkt**, a dopiero z niego
  nadawcę/PNI/rejon (PNI dedukowane niezależnie podpinałoby transakcje pod
  zły punkt)
- wskaźniki stanu pól + nawigacja TAB/Enter wyłącznie po polach głównych,
  Enter działa jak TAB, podświetlenie następnego pola
- `???` jako kanoniczny „rejon nieznany" we wszystkich ścieżkach zapisu
- naprawa błędu `firmy_zpo` ↔ `punkty.nadawca` + naprawa istniejących baz

### `0.1-alpha.3.2` — używalność i zdrowie danych

Po `0.1-alpha.3.1` program był „feature-complete" wg tej roadmapy, ale
**bezużyteczny do realnej pracy** (feedback pracowników, 2026-08-13). Dwa
RÓWNORZĘDNE filary — samo szybkie wdrożenie nie ma sensu, jeśli nie umiemy
zagwarantować, że wprowadzone tak dane będą zdrowe:

1. UI faktycznie umożliwia pracę,
2. dane wprowadzane i importowane są zdrowe — powstrzymujemy wpływ
   skorumpowanych Exceli na nowo tworzone dane.

Co konkretnie blokowało pracę (potwierdzone w kodzie, nie domysł):
**nie istniała ŻADNA ścieżka edycji ani usunięcia zapisanej transakcji.**
`UNIQUE(data, kurier, punkt)` odrzucał naturalny gest korekty („wpiszę
poprawnie jeszcze raz") jako duplikat — zła wartość zostawała, poprawka
znikała, komunikat leciał czarnym tekstem. Jedynym wyjściem było cofnięcie
punkt-w-czasie, zamykające aplikację i cofające też całą pracę po tym punkcie.

Zakres:

- **schemat v3**: `transakcje.sesja_uuid` (grupuje „co wpisałem w tym
  uruchomieniu") + `transakcje.zrodlo` (`formularz`/`import`/`import_zaufany`;
  **NULL = sprzed 3.2**, celowo bez backfillu — to zbiór wejściowy przyszłego
  narzędzia naprawy starych danych)
- **edycja i usuwanie transakcji** (`repo.zaktualizuj_transakcje`,
  `usun_transakcje`, `ustaw_pole_transakcji`) — kolizja klucza naturalnego
  blokuje z opisem kolidującego wiersza, nigdy nie rozstrzyga po cichu;
  edycja zbiorcza atomowa (jedna kolizja wycofuje całość)
- **Przegląd → widok poprawek**: filtry (kurier / zakres dat / tekst /
  bieżąca sesja), dwuklik → edycja, operacje zbiorcze + usuwanie
- **formularz**: podgląd domyślnie tylko bieżąca sesja, Tab z końca
  wypełnionego ostatniego wiersza dodaje nowy wiersz, status zapisu
  kolorowy i z powodami pominięć, **wiersze pominięte zostają w siatce**
  (dotąd formularz czyścił się nawet gdy nie zapisał nic)
- **rejon przestaje być wpisywalny ręcznie** — tylko wyświetlacz dedukcji;
  brak jednoznacznej historii → zapis `???` do uzupełnienia przez rejonarz
- **nadawcy bez PNI naprawialni** — `firmy_zpo` powstaje wyłącznie w gałęzi
  z PNI, więc literówki w ZUS/PKO/Kruk były nienaprawialne w aplikacji
- **model zaufania importu**: eksport dostaje znacznik pochodzenia + SHA-256
  odcisk danych; plik bez znacznika nie wnosi PNI ani rejonu, plik ze
  znacznikiem ale zmienioną zawartością **nie da się odblokować żadną drogą**
  (pliki `.xlsx` są trywialnie edytowalne — sam znacznik nic nie dowodzi);
  wymuszenie zaufania dla obcych plików to ukryty przełącznik, odsłaniany
  wpisem w `settings.json`
- **naprawa koercji PNI w eksporcie** — `"007"` → int `7` → reimport `"7"`
  rozdwajał ten sam fizyczny punkt; PNI to klucz, nie liczba
- `ustawienia.py` (`settings.json` per stacja), nr kadrowy przestaje być
  wymagany, „Wyloguj"/zmiana użytkownika na współdzielonych kontach Windows

**Świadomie NIE w tym wydaniu** (ławka rezerwowa — nie przechodzą filtra
„czy przybliża do realnej pracy"): tryb pół-auto i manualny, przełącznik
trybów, blokowanie pola kliknięciem we wskaźnik. Patrz `0.1-alpha.5`.

### `0.1-alpha.3.3 / 3.4` — rejonarz i naprawa zaległych Exceli

**Rejonarz** — zewnętrzny rejestr z pełną rejonizacją kraju (eksport `.xlsx`,
>400 tys. rekordów: rejon per numer budynku). Dostęp załatwiony 2026-08-13;
tylko eksporty plikowe, brak API. Kompresowalny do zakresów („ulica X,
numery 0<N≤120"), realnie potrzebna ok. 1/3 rekordów — do potwierdzenia na
pliku. To jest **źródło prawdy o rejonach**, w odróżnieniu od danych
z papierowych blankietów, które są zakłamane.

Zakres do rozstrzygnięcia przy planowaniu:

- import + kompresja do zakresów; szew dedukcji jest już gotowy
  (`dedukcja.dedukuj_wiersz` — jedyne miejsce, które rozstrzyga rejon)
- backfill wszystkich rekordów bez rejonu (`???`) po integracji
- **adresy**: rejonarz jako źródło prawdy także dla adresów, czy raczej
  otwarte zbiory adresowe? (patrz `reference-data-sources.md`) — ostrzeżenie
  przy adresie spoza bazy + propozycje najbliższych po podobieństwie nazwy
- formularz przechowuje adres bliżej `schema v2` (osobno miejscowość / ulica
  / nr budynku) — integracja rejonarza to naturalny moment na tę zmianę
  schematu, patrz `normalization-v2.md`

**Narzędzie naprawy starych Exceli** — osobny, jednorazowy program czyszczący
zaległe miesiące PRZED importem do głównej aplikacji (docelowo dane przestają
płynąć z Excela w ogóle). Zbiór wejściowy jest już wyznaczony przez
`transakcje.zrodlo IS NULL OR 'import'`.

### `0.1-alpha.4` — UI/UX

Przebudowa interfejsu pod realne potrzeby i wygodę użytkowników, z łatwym
kanałem zbierania feedbacku. Poprzedzona rozstrzygnięciem pytania
o architekturę docelową (patrz Otwarte pytania, punkt 1) — nawigacja
w hubie wygląda inaczej niż w aplikacji monolitycznej, więc odwrotna
kolejność oznacza projektowanie UI dwa razy.

### `0.1-alpha.5` — tryb pół-auto

Trzeci tryb wprowadzania obok auto i manualnego: dedukcje są wypełniane,
ale **wszystkie** pola pozostają aktywne, a TAB/Enter skacze jak w trybie
auto. Wejście na pole drugorzędne pokazuje wydedukowaną wartość zaznaczoną;
znika ona dopiero przy pierwszym wpisanym znaku. Dopuszcza ręcznie
zablokowane pola (klik we wskaźnik).

Świadomie odłożone: tryb ma sens tylko z sensownym interfejsem do blokowania
pól, a ten wymaga wskaźników z `0.1-alpha.3.1` jako fundamentu.

### `0.1-alpha.6` — synchronizacja między stacjami

Ok. 10 stacji w dziale, wymiana raz dziennie. Kluczowe rozpoznanie:
**„scalanie dwóch baz" i „synchronizacja" to ta sama maszyneria** —
sync = scalanie + transport + wyzwalacz. Dlatego `0.1-alpha.3` dostarczyła
scalanie i format wymiany, a ta wersja dokłada wyłącznie transport
i harmonogram.

Transport: katalog wymiany (udział SMB i/lub wydzielona przestrzeń na
firmowym OneDrive), **wymienny** — konfigurowalna ścieżka, nie zaszyta.
Zasada, która eliminuje konflikty zapisu: **każda stacja zapisuje wyłącznie
swój własny plik**, nigdy cudzy.

Do sprawdzenia przed rozpoczęciem:

- [ ] czy w LAN jest zapisywalny udział SMB dla działu
- [ ] wydzielenie przestrzeni na firmowym OneDrive (wymaga konfiguracji)

Uwagi projektowe:

- Konflikt wartości (ta sama trójka data+kurier+punkt, różne ilości)
  **nigdy nie jest rozstrzygany automatycznie** — świadczy o błędzie we
  wprowadzaniu albo w dokumentach źródłowych, więc wymaga sprawdzenia
  papieru przez człowieka. To usuwa najtrudniejszy problem systemów
  rozproszonych: nie potrzebujemy reguł rozstrzygania ani zaufania do
  zegarów (które na firmowych maszynach bywają rozjechane).
- `PRAGMA user_version` musi bramkować nie tylko przywracanie migawek,
  ale i synchronizację — stacje aktualizowane w różnym czasie będą miały
  różne wersje schematu.
- **Nie trzymać żywej bazy SQLite na udziale sieciowym** — blokady SQLite
  nie działają poprawnie po sieci, to realne ryzyko uszkodzenia bazy.
  Udział służy wyłącznie do wymiany plików.

#### Synchronizacja nie zastępuje kopii zapasowych

Replikacja na ~10 stacji chroni przed **awarią sprzętu**, ale wiernie
powiela **błąd logiczny** — zły import rozejdzie się na wszystkie stacje.
Nie chroni też danych wpisanych dziś, jeszcze niezsynchronizowanych.
Migawki lokalne zostają potrzebne niezależnie od synchronizacji; to
mechanizmy komplementarne, nie zamienne.

## Otwarte pytania kierunkowe (wersja nieprzypisana)

To nie są zadania do wzięcia, tylko decyzje, które przemodelują samą
roadmapę — dlatego są tutaj, a nie w `backlog.md`.

### 1. Dane dodatkowe i architektura docelowa

Temat na osobną dyskusję. Pytania:

- Dodatkowe informacje (np. kontaktowe) w bazie — jedna baza czy osobne?
- Jakie dane wolno dodać, a jakich nie? (RODO — dane kontaktowe kurierów
  to inna kategoria niż same nazwiska w zestawieniu rozliczeniowym)
- **Decyzja nadrzędna: osobne programy, all-in-one, czy micro-apps + hub?**
  (obecny faworyt: micro-apps + hub)

To nie jest pytanie o funkcję, tylko o granice systemu — rozstrzyga, czy
`zpo_tracker` zostaje aplikacją, czy staje się jednym modułem większej
całości. **Warto rozstrzygnąć przed `0.1-alpha.4`**, z powodu opisanego wyżej.

### 2. Aktualizacje

- [ ] **Test: czy GitHub Releases jest osiągalny przy włączonych zaporach?**
      `environment.md` mówi, że `github.com` jest „częściowo dostępny" —
      trzeba sprawdzić, czy obejmuje to pobieranie artefaktów. Tanie do
      sprawdzenia, a bramkuje całą strategię aktualizacji.

Powiązanie z resztą: jeśli synchronizacja da katalog wymiany, **ten sam katalog może
rozdawać nowe wersje `.exe`** — GitHub przestaje być wtedy potrzebny jako
kanał dystrybucji.

### 3. Numery kadrowe kurierów

Nie mylić z `users.nr_kadrowy` (pracownicy działu, 1:1, 5 znaków
`[a-zA-Z0-9]`). **Numery kadrowe kurierów mają inny format i są w relacji
1 kurier : N numerów.**

Konsekwencja: `schema_v2_draft.sql` zawiera
`kurierzy.identyfikator_zewnetrzny TEXT UNIQUE` — pojedyncza kolumna
**nie jest w stanie wyrazić 1:N**. Wymaga osobnej tabeli
`numery_kadrowe_kurierow(kurier_id, numer)`. Poprawione w drafcie, żeby
nikt nie zaimplementował wadliwego wzorca.

### 4. Rejonarz — ROZSTRZYGNIĘTE (2026-08-13)

Pytanie „w jakiej formie rejonarz jest dostępny" jest już zamknięte:
**eksport `.xlsx`, bez API.** Dostęp załatwiony. Ręczne wpisywanie rejonu
zniknęło z formularza już w `0.1-alpha.3.2`, sama integracja jest
zaplanowana jako `0.1-alpha.3.3/3.4` — patrz sekcja tej wersji wyżej.

Otwarte zostaje tylko jedno, do rozstrzygnięcia przy planowaniu tamtej
wersji: czy rejonarz ma być źródłem prawdy także dla **adresów**, czy
lepsze są do tego otwarte zbiory adresowe (`reference-data-sources.md`).
