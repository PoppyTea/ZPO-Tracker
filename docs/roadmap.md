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
| **`0.1-alpha.4`** | planowane | przebudowa UI/UX pod realne potrzeby + kanał feedbacku |
| **`0.1-alpha.5`** | planowane | tryb pół-auto wprowadzania (wymaga sensownego interfejsu) |
| **`0.1-alpha.6`** | planowane | automatyczna synchronizacja między stacjami |

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

### 4. Rejonarz — docelowe źródło rejonów

Rejony pochodzą realnie z **rejonarza** (zewnętrzny rejestr przypisujący
rejon do adresu). Docelowo pole `rejon` ma **zniknąć z formularza
całkowicie** — zamiast wpisywać je albo dedukować z własnej historii,
program pytałby rejonarz o rejon dla adresu.

Dedukcja rejonu z adresu wprowadzona w `0.1-alpha.3.1` jest krokiem w tę
stronę: odwzorowuje docelowy wzorzec (adres → rejon) na danych, które już
mamy. Kiedy pojawi się integracja, zmienia się źródło odpowiedzi, nie
kształt formularza.

Do rozstrzygnięcia przed rozpoczęciem: w jakiej formie rejonarz jest
dostępny (plik? eksport? API?) i jak często się zmienia.
