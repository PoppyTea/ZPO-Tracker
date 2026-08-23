# Proces pracy — gdzie co mieszka

Referencja dla `CLAUDE.md`. Powstał 2026-08-23 razem z migracją zadań na
Linear, żeby granica „co jest zadaniem, a co wiedzą" nie była rozstrzygana
na wyczucie przy każdej sesji.

## Linear jest jedynym rejestrem zadań

Projekt **ZPO-Tracker** w workspace `aid4u` (team `Aid4u`, klucz `AID`):
<https://linear.app/aid4u/project/zpo-tracker-07c6d93278dd/overview>

Zastępuje wszystkie wcześniejsze miejsca: `docs/backlog.md` (usunięty),
checkboxy w `docs/roadmap.md` (usunięte), GitHub Issues (pięć otwartych
zamkniętych z odesłaniem 2026-08-23). Powód jest prozaiczny: przy wielu
rejestrach koszt zamknięcia **jednej** pozycji to edycja kilku plików, bo
z góry nie wiadomo, w którym rejestrze dana pozycja żyje.

### Każdy fakt ma jeden dom

| Typ faktu | Dom | Dlaczego nie gdzie indziej |
|---|---|---|
| Zadanie, bug, dług techniczny | Linear (`AID-XXX`) | to jest dokładnie ten przypadek |
| Decyzja do podjęcia | Linear, label `type/decision` | u nas decyzje realnie blokują konkretne wydania, więc muszą być widoczne w relacjach blokowania |
| Kolejność wersji i ich zakres | Linear — milestones projektu | stan postępu, nie wiedza |
| Dlaczego akurat ta kolejność, bramki, reguły decyzyjne | `docs/roadmap.md` | wiedza trwała, nie odhacza się jej |
| Model domenowy, schemat, środowisko, UX | pozostałe `docs/*.md` | jak wyżej |
| Kontrakt kodu w danym podkatalogu | najbliższy `AGENTS.md` (DOX) | kontrakt lokalny, nie zdarzenie do zamknięcia |
| Reguła recenzji kodu | ten plik, sekcja „Reguły recenzji" | kontrakt trwały, nie zdarzenie do zamknięcia |

W tekście dokumentu wolno zostawić kotwicę `(→ AID-XXX)`. Tabela z kolumną
`Priorytet`/`Status` opisująca pojedyncze zadania — nie wolno, patrz R3.

### Zakładanie issue — warunki konieczne

Bez obu tych rzeczy issue jest praktycznie nie do odnalezienia, bo
workspace `aid4u` obsługuje też inne, niepowiązane projekty:

1. **Projekt = ZPO-Tracker.** Bez tego pozycja miesza się z innym projektem.
2. **Assignee = Aleksander Fijołek.** Projekt ma jednego wykonawcę;
   nieprzypisane issue wypada z jego widoków.

Poza tym:

- **Milestone**, jeśli pozycja należy do konkretnej wersji. Brak milestone'u
  znaczy „nieprzypisane do wydania", i to jest poprawny, świadomy stan —
  nie brak do uzupełnienia.
- **Relacje `blocks` / `blocked by`** wszędzie, gdzie realnie istnieją. To
  nie kosmetyka: bez nich milestone wygląda na gotowy do wzięcia, choć
  czeka na rozpoznanie albo na decyzję. Osobno zakładamy też blokady
  **organizacyjne** (klucz API, przydzielenie numerów kadrowych), żeby było
  widać, że przestój nie jest techniczny.
- **Relacja `related`** tam, gdzie rzeczy robi się razem, ale jedna nie
  wymaga drugiej.
- **Labele**: `type/*` zawsze; `area/*` wg dotkniętego obszaru;
  `needs-verification` dla rozpoznania, które trzeba wykonać w świecie,
  nie w kodzie.

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

Przeniesione 2026-08-23 z projektu `aid4u` (`strategy/rules/`), gdzie
powstały i zostały wypróbowane. Numeracja lokalna — tamtejsza nie ma tu
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
dozwolonymi wyjątkami: kotwica `(→ AID-XXX)` w tekście istniejącego
dokumentu, generyczne kryteria wyjścia z procedury.

Zgłoszenie jest informacyjne — recenzja nie usuwa pliku sama.
