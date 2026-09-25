# Proces pracy — gdzie co mieszka

Referencja dla `CLAUDE.md`. Powstał 2026-08-23 razem z migracją zadań na
Linear, żeby granica „co jest zadaniem, a co wiedzą" nie była rozstrzygana
na wyczucie przy każdej sesji. Przebudowany 2026-09-23, gdy Linear zaczął
służyć za dziennik zamiast za rejestr zadań (hierarchia, R4).

## Linear jest jedynym rejestrem zadań

Projekt **ZPO-Tracker**, zespół **ZPO** (klucz `ZPO`), workspace `poppy-tea`:
<https://linear.app/poppy-tea/project/zpo-tracker-07c6d93278dd/overview>

Zastępuje wszystkie wcześniejsze miejsca: `docs/backlog.md` (usunięty),
checkboxy w `docs/roadmap.md` (usunięte), GitHub Issues (zamknięte
z odesłaniem 2026-08-23). Powód jest prozaiczny: przy wielu rejestrach
koszt zamknięcia **jednej** pozycji to edycja kilku plików, bo z góry nie
wiadomo, w którym rejestrze dana pozycja żyje.

Do 2026-09-23 issues żyły w zespole `Aid4u` (klucz `AID`); przeniesione
dostały nowe numery `ZPO-xx`. Stare numery `AID-xx` zostają w historii
commitów i nie są już rozpoznawane przez API — mapowania nie trzymamy,
bo tytuł issue wystarcza do wyszukania.

Agent obsługuje Linear przez CLI `linearis` (`linearis <domena> usage`),
nie przez MCP. Działa na tokenie Papavera, więc każda akcja agenta
wygląda w Linear jak jego własna.

### Każdy fakt ma jeden dom

| Typ faktu | Dom | Dlaczego nie gdzie indziej |
|---|---|---|
| Zadanie, bug, dług techniczny | Linear (`ZPO-XXX`) | to jest dokładnie ten przypadek |
| Decyzja do podjęcia | Linear, label `type/decision` | u nas decyzje realnie blokują konkretną pracę, więc muszą być widoczne w relacjach blokowania |
| Zakres i kolejność prac | Linear — milestones projektu | stan postępu, nie wiedza |
| Numer wersji, wydanie | tag w gicie + GitHub Release | wydanie to moment cięcia, nie praca do zaplanowania |
| Postęp i ustalenia w trakcie pracy | komentarz w issue, którego dotyczą | patrz R4 |
| Dlaczego akurat ta kolejność, bramki, reguły decyzyjne | `docs/roadmap.md` | wiedza trwała, nie odhacza się jej |
| Model domenowy, schemat, środowisko, UX | pozostałe `docs/*.md` | jak wyżej |
| Kontrakt kodu w danym podkatalogu | najbliższy `AGENTS.md` (DOX) | kontrakt lokalny, nie zdarzenie do zamknięcia |
| Reguła recenzji kodu | ten plik, sekcja „Reguły recenzji" | kontrakt trwały, nie zdarzenie do zamknięcia |

W tekście dokumentu wolno zostawić kotwicę `(→ ZPO-XXX)`. Tabela z kolumną
`Priorytet`/`Status` opisująca pojedyncze zadania — nie wolno, patrz R3.

### Hierarchia

Trzy poziomy issues pod milestone'em. Każdy odpowiada na inne pytanie,
i to pytanie rozstrzyga, na którym poziomie coś ląduje:

| Poziom | Pytanie | Jak się zamyka |
|---|---|---|
| Milestone | Co użytkownik dostaje, gdy ten zakres jest gotowy? | ręcznie; to sugestia, że warto wydać, nie obowiązek |
| Funkcja | **Po co** to jest i po czym użytkownik pozna, że działa? | automatycznie, gdy zamkną się dzieci |
| Element | **Jak** to działa — jaki mechanizm? | automatycznie; przez PR, jeśli nie ma dzieci |
| Zadanie | **Co** konkretnie zrobić i jaki test to potwierdza? | tylko przez PR z zielonymi testami |

- Głębokość to maksimum, nie wymóg. Zadanie wystarczająco małe wisi
  bezpośrednio pod funkcją; funkcja z jednym dzieckiem to przerost formy —
  wtedy zostaje samodzielnym issue.
- Funkcja w opisie ma dwie sekcje: `## Po co` i `## Po czym poznać, że
  działa`. Zadanie kończy się sekcją `## Warunek zamknięcia` nazywającą test.
- **PR zamyka wyłącznie liście drzewa** (magiczne słowo `Fixes ZPO-XX`).
  Opis PR wymienia testy, które potwierdzają zamknięcie, i krótko opisuje
  te, których nazwa nie mówi wszystkiego albo które kryją niuans ważny dla
  recenzenta. Rodziców zamyka Linear (ustawienie zespołu „auto-close parent
  issues”).
- **Praca poza kodem** — blokady organizacyjne (`type/org`: klucz API,
  numery kadrowe, udział sieciowy) i decyzje (`type/decision`) — to
  samodzielne issues bez rodzica, zamykane ręcznie komentarzem z wynikiem.
  Ich wpływ na drzewo wyrażają relacje `blocks`, nie hierarchia.
- **Bug z testów na żywo** (`src/live-testing`) trafia jako dziecko
  funkcji, którą psuje; jeśli żadnej nie da się wskazać — do milestone'u
  bez rodzica.

### Zakładanie issue — warunki konieczne

Bez tych trzech rzeczy issue jest praktycznie nie do odnalezienia, bo
workspace obsługuje też inne, niepowiązane projekty:

1. **Zespół = ZPO.**
2. **Projekt = ZPO-Tracker.** Bez tego pozycja miesza się z innym projektem.
3. **Assignee = Aleksander Fijołek.** Projekt ma jednego wykonawcę;
   nieprzypisane issue wypada z jego widoków.

Issues zaimportowane z GitHub Issues (synchronizacja jednokierunkowa
GitHub → Linear) trzeba przy pierwszym kontakcie sprawdzić pod tym kątem:
uzupełnić brakujący projekt i assignee i wpiąć je w drzewo. Kierunek jest
jednokierunkowy celowo — repo jest publiczne, a issues w Linear mogą
zawierać wewnętrzne nazwy hostów i opisy systemów Poczty.

Poza tym:

- **Milestone**, jeśli pozycja należy do konkretnego zakresu. Brak
  milestone'u znaczy „nieprzypisane”, i to jest poprawny, świadomy stan —
  nie brak do uzupełnienia.
- **Relacje `blocks` / `blocked by`** wszędzie, gdzie realnie istnieją. To
  nie kosmetyka: bez nich milestone wygląda na gotowy do wzięcia, choć
  czeka na rozpoznanie albo na decyzję. Osobno zakładamy też blokady
  **organizacyjne**, żeby było widać, że przestój nie jest techniczny.
- **Relacja `related`** tam, gdzie rzeczy robi się razem, ale jedna nie
  wymaga drugiej.
- **Etykiety** (zespołowe, nie organizacji): `type/*` zawsze; `area/*` wg
  dotkniętego obszaru programu; `src/*`, gdy zgłoszenie ma szczególne
  źródło; `needs-verification` dla rozpoznania, które trzeba wykonać
  w świecie, nie w kodzie.

## Zero stanu w `docs/`

Pliki w `docs/` trzymają **wiedzę trwałą** — reguły, procedury, model
domenowy, uzasadnienia decyzji. Nie trzymają stanu: żadnych checkboxów
odbijających zadania, list „do zrobienia", kolumn `Status` ani dat
ostatniego wykonania.

**Powód:** dokument bez stanu nie może się zdezaktualizować, więc nie
wymaga rytuału synchronizacji, którego i tak nikt nie wykona. Ten projekt
ma jednego maintainera i przerwy w pracy liczone w dniach — rytuał, który
zawodzi, jest gorszy niż jego brak, bo zostawia dokument wyglądający na
aktualny.

Dopuszczalne wyjątki: ✅/❌ jako przykłady dobrze/źle, trwała właściwość
rzeczy zewnętrznej (np. „BaŚKa nie zna `PNI ZPO`"), placeholdery
w szablonach, generyczne kryteria wyjścia z procedury, których się nie
odhacza (jak filtr trzech pytań w `roadmap.md`).

Test rozstrzygający: **czy ktoś kiedyś to odhaczy?** Tak → Linear.
Nie → `docs/`.

## Reguły recenzji

R1–R3 przeniesione 2026-08-23 z projektu `aid4u` (`strategy/rules/`),
gdzie powstały i zostały wypróbowane; R4 jest lokalna. Numeracja lokalna — tamtejsza nie ma tu
sensu, bo większość tamtych reguł dotyczy `httpx`, `tenacity` i pętli
agentowej, których w tym projekcie nie ma.

Reguły są widoczne dla CodeRabbita przez `.coderabbit.yaml`
(`knowledge_base.code_guidelines`).

Egzekwowanie: `ERROR` — nienegocjowalne. `WARNING` — domyślnie stosuj,
pominięcie wymaga jednozdaniowego uzasadnienia.

### R1 — rozjazdy propagacji poprawek (`WARNING`)

*Źródło: `r16` w aid4u.*

Recenzja pojedynczego PR-a widzi tylko jego diff — nie zauważy, że poprawka
przyjęta w jednym miejscu nie została zastosowana w trzech innych, bo tamte
pliki się w tym PR-ze nie zmieniają. Zmerge'owany kod przestaje być oglądany
przez kogokolwiek.

**Heurystyka:** znajdź wzorzec obronny obecny w co najmniej jednym miejscu,
a nieobecny tam, gdzie miałby zastosowanie. Dla każdego rozjazdu podaj
**oba** miejsca — to z zabezpieczeniem i to bez. Skopiowanie własnego,
przyjętego już rozwiązania jest tańsze i bezpieczniejsze niż wymyślanie
nowego.

Znane w tym repo miejsca tego kształtu, warte szczególnej uwagi:

- `importer.znajdz_lub_utworz_punkt_niezaufany` jest **celowo osobne** od
  `get_or_create_punkt` — to drugie obsługuje też scalanie baz. Ich
  semantyki nie wolno zbliżać „dla porządku"; to jest wyjątek od R1,
  nie jego instancja.
- naprawy walidacji na ścieżce formularza a ścieżka edycji transakcji
  (`repo.zaktualizuj_transakcje`, `ustaw_pole_transakcji`) — ścieżka edycji
  jest młodsza i nie ma za sobą tego samego przebiegu walidacji.
- `scalanie.py` — porównania pól przy klasyfikacji wierszy.

### R2 — filtr cichych awarii (`WARNING`)

*Źródło: `r17` w aid4u.* Bramka stosowana **po** znalezieniu kandydata przez
R1, przed zgłoszeniem. Zgłaszać wolno tylko to, co spełnia **wszystkie
trzy** warunki:

1. Naruszenie może zawieść **cicho** — bez wyjątku, bez czerwonego testu,
   bez wpisu w dzienniku. Rzeczy wywalające się głośno przy pierwszym
   uruchomieniu pomijamy: te znajdzie autor, uruchamiając kod.
2. Dotyczy kodu, który realnie się wykonuje — nie martwej gałęzi, nie
   zakomentowanego bloku.
3. Nie zostało wcześniej świadomie zaakceptowane.

**Limit twardy: maksymalnie 3 pozycje na przebieg**, posortowane po
potencjale cichej awarii; nadmiar → „Pominięto N pozycji niższej wagi".
Powód limitu: audyt ma pomagać dowieźć program, nie stać się osobnym
projektem sprzątania.

### R3 — zakaz nowych lokalnych rejestrów zadań (`ERROR`)

*Źródło: `r18` w aid4u.* Ramię egzekucyjne sekcji „Linear jest jedynym
rejestrem" wyżej.

**Wzorzec wykrywany:** nowy plik `.md` z tabelą albo listą zawierającą
kolumnę `Priorytet`/`Status`/`TODO` opisującą stan pojedynczych zadań lub
defektów, a także listy `- [ ]` odbijające pracę do wykonania. Poza
dozwolonymi wyjątkami: kotwica `(→ ZPO-XXX)` w tekście istniejącego
dokumentu, generyczne kryteria wyjścia z procedury.

Zgłoszenie jest informacyjne — recenzja nie usuwa pliku sama.

### R4 — Linear nie jest dziennikiem (`ERROR`)

Ramię egzekucyjne sekcji „Hierarchia”. Powstała, bo bez niej Linear
zamienił się w zapis wszystkiego, co zauważono po drodze: issues
z tytułami-stwierdzeniami, bez warunku zamknięcia, których nikt nigdy
nie odhaczy.

**Issue odpowiada na pytanie „co trzeba zrobić?” i ma warunek zamknięcia.**
Wpis, który odpowiada na „co się stało?”, „co się zmieniło?”, „co
ustaliliśmy?” albo „co zauważyłem?”, nie jest nowym issue:

- postęp i ustalenia dotyczące istniejącej pracy → komentarz w tym issue;
- wiedza trwała (dlaczego tak, co rozważaliśmy i odrzuciliśmy) → `docs/`,
  a issue najwyżej do niej linkuje; uzasadnienie zostawione w komentarzu
  zamkniętego issue ginie razem z nim;
- obserwacja, z której nic nie wynika do zrobienia, nie trafia nigdzie.

**Test tytułu:** tytuł mówi, co ma powstać albo działać („Obsłużyć `.xls`
z rejonarza”), a nie co stwierdzono („Eksport ma inny kształt, niż zakłada
importer”). Bug może w tytule opisywać objaw, ale jego opis kończy się
oczekiwanym zachowaniem.

**Wzorzec wykrywany w recenzji:** nowe issue lub komentarz w PR, który
zakłada w Linear pozycję bez warunku zamknięcia albo z tytułem-
stwierdzeniem; zmiana tytułu istniejącego issue na relację z przebiegu
prac.
