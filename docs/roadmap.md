# Roadmapa — zasady kierunkowe

Referencja dla `CLAUDE.md`.

**Ten dokument nie jest harmonogramem.** Co i w jakiej kolejności — to
milestones i issues projektu ZPO-Tracker w Linear
(<https://linear.app/aid4u/project/zpo-tracker-07c6d93278dd/overview>).
Tutaj zostaje to, czego milestone nie udźwignie: **dlaczego** akurat taka
kolejność, jakie bramki muszą paść przed przejściem dalej i które zasady
projektowe obowiązują niezależnie od wersji. Podział ról między Linear
a `docs/` opisuje `proces.md`.

## Cel nadrzędny po serii `0.1-alpha.x`

Aprobata kierownictwa WER Ciemne (patrz `domain-model.md`, sekcja „Cel
i kontekst") nadaje projektowi wyraźny cel nadrzędny: **zapewnienie
i utrzymanie jakości danych rozliczeniowych to główny cel programu, nie
efekt uboczny.**

Seria `0.1-alpha.x` adresuje komfort i szybkość wprowadzania danych. Po jej
zamknięciu kolejne kierunki budowane są WOKÓŁ tego celu — jako środowisko,
które jakość danych zapewnia lub wręcz gwarantuje, a nie tylko na nią
pozwala.

## Bramka przed `0.1-alpha.4`

**Warunek przejścia:** program uznany za nadający się do użytku.
Funkcjonalności mogą być podstawowe, ale muszą być.

Filtr, przez który musi przejść każdy kandydat do `0.1-alpha.3.x`:

1. Czy przybliża nas to do umożliwienia realnej pracy na programie?
2. Czy pomaga powstrzymać wpływ skorumpowanych danych z wcześniejszych
   miesięcy na nowo tworzone dane?
3. Czy naraża dane na zepsucie lub niekompletność, którą trudno będzie
   naprawić później? (jak wyglądałaby taka naprawa? czy mamy źródło prawdy?)

Wcześniej obowiązywał drugi warunek — rozstrzygnięcie architektury
docelowej (osobne programy / all-in-one / micro-apps + hub) przed pracami
nad UI. **Zniesiony 2026-08-23.** Pytanie jest przedwczesne, dopóki
`zpo_tracker` jest jedynym projektem i nie planujemy tak szerokiej
rozbudowy — hub nie ma czego spinać. Koszt tej decyzji jest jawny
i przyjęty: część projektu interfejsu może wymagać powtórzenia, jeśli
kiedyś powstanie druga aplikacja. Pierwsze wrażenie u nietechnicznych
odbiorców jest dziś warte więcej niż ta oszczędność.

## Lekcje, z których te bramki wyrosły

**Po `0.1-alpha.3.1` program był „feature-complete" wedle ówczesnej
roadmapy i bezużyteczny do realnej pracy.** Ustalone na feedbacku
pracowników 2026-08-13. To jest najdrożej kupiona wiedza w tym projekcie
i bezpośredni powód, dla którego filtr wyżej w ogóle istnieje: zgodność
z planem nie jest dowodem użyteczności.

Co konkretnie blokowało pracę — potwierdzone w kodzie, nie domysł:
**nie istniała ŻADNA ścieżka edycji ani usunięcia zapisanej transakcji.**
`UNIQUE(data, kurier, punkt)` odrzucał naturalny gest korekty („wpiszę
poprawnie jeszcze raz") jako duplikat: zła wartość zostawała, poprawka
znikała, komunikat leciał czarnym tekstem. Jedynym wyjściem było cofnięcie
punkt-w-czasie, zamykające aplikację i cofające też całą pracę po tym
punkcie.

Wniosek ogólniejszy, obowiązujący dalej: **ścieżka naprawy błędu jest
funkcją pierwszej klasy, nie dodatkiem.** Program, w którym da się wpisać
dane, ale nie da się ich poprawić, generuje dług szybciej, niż go spłaca.

## Zasady projektowe niezależne od wersji

### Scalanie i synchronizacja to ta sama maszyneria

`sync = scalanie + transport + wyzwalacz`. Dlatego `0.1-alpha.3` dostarczyła
scalanie baz i format wymiany (`.sql.gz`), a synchronizacja między stacjami
dokłada wyłącznie transport i harmonogram. Konsekwencja praktyczna: **błąd
w `scalanie.py` jest błędem przyszłej synchronizacji** — to, co dziś gubi
wiersz raz przy ręcznym scalaniu, po włączeniu synchronizacji będzie gubić
go automatycznie i cyklicznie na dziesięciu stacjach.

### Konflikt wartości nigdy nie jest rozstrzygany automatycznie

Ta sama trójka `data + kurier + punkt` z różnymi ilościami świadczy o błędzie
we wprowadzaniu albo w dokumentach źródłowych, więc wymaga sprawdzenia
papieru przez człowieka. To usuwa najtrudniejszy problem systemów
rozproszonych: nie potrzebujemy reguł rozstrzygania ani zaufania do zegarów,
które na firmowych maszynach bywają rozjechane.

### Migawka offline, nie żywe API

Offline'owy `.exe` nigdy nie woła API na żywo. Dane referencyjne wchodzą
jako **lokalna migawka** produkowana przez osobne narzędzie operatorskie
i przepuszczona przez istniejący model zaufania importu (znacznik
pochodzenia + odcisk SHA-256). API jest okienkiem do weryfikacji
pojedynczych przypadków, gdy akurat jest sieć — nigdy bramką przed zapisem.

### Wartości kanoniczne i celowe luki

- **`???`** to kanoniczny „rejon nieznany" we wszystkich ścieżkach zapisu.
  Rejon nie jest wpisywalny ręcznie — wyłącznie dedukowany.
- **`transakcje.zrodlo IS NULL`** znaczy „sprzed `0.1-alpha.3.2`". Brak
  backfillu tej kolumny był decyzją, nie przeoczeniem: to gotowy zbiór
  wejściowy dla narzędzia naprawy zaległych danych.

### Ograniczenia trwałe

- `PRAGMA user_version` bramkuje nie tylko przywracanie migawek, ale
  i synchronizację — stacje aktualizowane w różnym czasie mają różne wersje
  schematu.
- **Nie trzymać żywej bazy SQLite na udziale sieciowym.** Blokady SQLite nie
  działają poprawnie po sieci; udział służy wyłącznie do wymiany plików.
- **Synchronizacja nie zastępuje kopii zapasowych.** Replikacja na ~10 stacji
  chroni przed awarią sprzętu, ale wiernie powiela błąd logiczny — zły import
  rozejdzie się wszędzie. Nie chroni też danych wpisanych dziś, jeszcze
  niezsynchronizowanych. Mechanizmy są komplementarne, nie zamienne.
- **Numery kadrowe kurierów są w relacji 1 kurier : N numerów** i nie da się
  ich wyrazić pojedynczą kolumną. Nie mylić z `users.nr_kadrowy`
  (pracownicy działu, 1:1, `[a-zA-Z0-9]{5}`). Szczegóły schematu:
  `normalization-v2.md` i `schema_v2_draft.sql`.

## Rejonarz — stan rozpoznania

Rejonarz to **BaŚKa** (Baza Ścieżek Kierowania Przesyłek), źródło prawdy
o rejonach — w odróżnieniu od danych z papierowych blankietów, które są
zakłamane.

- **Reguła rejonu, potwierdzona naocznie w przeglądarce (2026-08-23):**
  interesują nas rejony węzła **`WW`** o **typie kierowania `1`** (typ `2`
  odrzucamy). Do numeru rejonu doklejamy literał **`WA`**.

  **Pułapka, w którą łatwo wpaść przy czytaniu samej dokumentacji:** w BaŚce
  istnieje osobny **węzeł o kodzie `WA`** — to WER Warszawa W101 przy
  ul. Łączyny, zupełnie inny byt. Prefiks `WA` NIE jest kodem węzła
  źródłowego, mimo że litery się zgadzają i mimo że kiedyś tak było.
  Wnioskowanie „prefiks = kod węzła" jest błędne, a dokumentacja i przykłady
  w API pozornie je potwierdzają. Zweryfikowane wyłącznie wzrokiem.
- **Wartownicy w kolumnie `Rejon`**, wszystkie mapowane na `???`, nigdy
  zapisywane jako rejon: `*UP` (rejon nieprzypisany), `ZPO` (punkt zewnętrzny
  bez rejonu), `UP`, `AP`, `FUP` (placówki PP). Ścieżki częściowe również
  odrzucane — BaŚKa sama je oznacza.
- **Podział źródeł:** masowo działają eksporty `.xlsx` z ekranów BaŚKi
  (nie wymagają klucza). API SOAP DeliveryPath jest sprawdzarką pojedynczych
  adresów — nie enumeruje i nie zna `PNI ZPO`. Wcześniejszy zapis „bez API"
  był błędny; klucza API jeszcze nie ma i jest to blokada organizacyjna.

Pełna analiza, ograniczenia, checklista weryfikacji w UI i reguły kolizji
z importem: `internal/raports/baska-raport-zastosowania.md` — **dokument
lokalny, celowo poza repozytorium** (zawiera wewnętrzne adresy i opis
schematu uwierzytelniania).
