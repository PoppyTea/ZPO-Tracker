# Roadmap

Referencja dla `CLAUDE.md`. Źródło prawdy o kolejności prac.

Podział odpowiedzialności między dokumentami:

- **`roadmap.md`** (ten plik) — co i w jakiej kolejności, plus otwarte
  pytania kierunkowe: decyzje, które przemodelują samą roadmapę
- **`backlog.md`** — konkretne jednostki pracy do wzięcia
- GitHub milestones — odzwierciedlają wersje niżej; GitHub issues —
  bieżące bugi i pojedyncze funkcje

## Wersje

| Wersja | Status | Zakres |
|---|---|---|
| `v0.1.0-alpha.2` | wydane | MVP: import/export, formularz blankietowy, słowniki, podpowiedzi |
| **X+1** | w toku | trwałość danych, atrybucja, ręczne scalanie baz (niżej) |
| **X+2** | planowane | przebudowa UI/UX pod realne potrzeby + kanał feedbacku |
| **X+3** | planowane | automatyczna synchronizacja między stacjami |

### X+1 — domknięcie MVP: trwałość, atrybucja, scalanie

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
- zrzuty `.sql.gz` — warstwa zimna **i zarazem format wymiany dla X+3**
- **ręczne scalanie dwóch baz** z obsługą konfliktów
- blokada uruchomienia drugiej instancji

### X+2 — UI/UX

Przebudowa interfejsu pod realne potrzeby i wygodę użytkowników, z łatwym
kanałem zbierania feedbacku. Poprzedzona rozstrzygnięciem pytania
o architekturę docelową (patrz Otwarte pytania, punkt 1) — nawigacja
w hubie wygląda inaczej niż w aplikacji monolitycznej, więc odwrotna
kolejność oznacza projektowanie UI dwa razy.

### X+3 — synchronizacja między stacjami

Ok. 10 stacji w dziale, wymiana raz dziennie. Kluczowe rozpoznanie:
**„scalanie dwóch baz" i „synchronizacja" to ta sama maszyneria** —
sync = scalanie + transport + wyzwalacz. Dlatego X+1 dostarcza scalanie
i format wymiany, a X+3 dokłada wyłącznie transport i harmonogram.

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
Migawki lokalne zostają potrzebne niezależnie od X+3; to mechanizmy
komplementarne, nie zamienne.

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
całości. **Warto rozstrzygnąć przed X+2**, z powodu opisanego wyżej.

### 2. Aktualizacje

- [ ] **Test: czy GitHub Releases jest osiągalny przy włączonych zaporach?**
      `environment.md` mówi, że `github.com` jest „częściowo dostępny" —
      trzeba sprawdzić, czy obejmuje to pobieranie artefaktów. Tanie do
      sprawdzenia, a bramkuje całą strategię aktualizacji.

Powiązanie z resztą: jeśli X+3 da katalog wymiany, **ten sam katalog może
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
