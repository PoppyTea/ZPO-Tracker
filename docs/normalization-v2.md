# Normalizacja v2 (propozycja, do wdrożenia)

Referencja dla `CLAUDE.md`. Odpowiadający draft schematu: `schema_v2_draft.sql`
(NIE zastępuje `schema.sql` automatycznie).

Wynik sesji "co zawiera się w czym" (interaktywny artefakt do układania
hierarchii encji). Cel: bardziej atomowe pola pod kątem (a) kompatybilności
z ewentualną integracją z innymi bazami w przyszłości, (b) elastyczniejszego
wyszukiwania/filtrowania, (c) odporności na duplikaty typu
`"Mińsk Mazowiecki ul. Długa 7c/2"` vs `"MIŃSK MAZOWIECKI DŁUGA 7C2"` —
rozbicie na atomowe wartości i normalizacja PO rozbiciu jest odporniejsze
na nieprzewidziane warianty zapisu niż normalizacja całego stringa naraz.

## Nowe encje względem `schema.sql` (v1)

- `kurierzy`: rozbite na `imie` + `nazwisko` (+ `pelne_nazwisko_raw` jako
  fallback), powiązane z `wykonawcy` (Wykonawca 1:N Kurier)
- `miejscowosci` → `ulice` (unikalna para nazwa+miejscowość, bo nazwy ulic
  potrafią się powtarzać w różnych miejscowościach) → `adresy`
  (nr budynku, nr lokalu, kod pocztowy)
- `rejony`: rozbite na `prefix` + `numer` (np. "WA87" → "WA"+"87"), z FK do
  `miejscowosci` (prefiks odpowiada największemu miastu w rejonie) i do
  `wykonawcy` (Wykonawca 1:N Rejon)
- **`firmy_zpo`** (Żabka, Duży Ben, Groszek, Delikatesy Centrum, ABC...) —
  rozdzielone od `wykonawcy`: to dwie różne role, łatwo je pomylić.
  Wykonawca = kto obsługuje trasę kurierską (Koli/Translist/Rekus/Poczta
  Polska). Firma ZPO = jaka sieć hostuje punkt odbioru.
- `nadawcy` (ZUS, PKO, Kruk...) — **celowo NIE znormalizowane do osobnej
  tabeli jeszcze**. Użytkownik nie pamięta dokładnie, gdzie/jak te wpisy
  pojawiają się w realnym procesie wprowadzania, i podejrzewa, że mogą
  docelowo okazać się jakoś powiązane z ZPO. Zamiast zgadywać strukturę,
  zostaje luźne pole `punkty.nadawca_surowy` (TEXT), do znormalizowania
  później, jak wzorzec stanie się jasny (np. po dłuższej obserwacji danych
  albo analogicznym przeglądzie jak przy kurierach)

## Dwa otwarte ryzyka do świadomej decyzji przed implementacją

1. `kod_pocztowy` **nie istnieje w danych źródłowych** (nie ma go w żadnej
   kolumnie `.xlsx`) — nie da się go zaimportować automatycznie, pole
   zostanie puste do ręcznego uzupełnienia później
2. Podział `Kurier` → `imie`/`nazwisko` jest ryzykowny parsingowo — dane mają
   niespójne białe znaki (np. `"Michalak Maciej "`) i nie ma formalnej
   gwarancji kolejności "nazwisko imię" dla wszystkich kurierów. Stąd
   `pelne_nazwisko_raw` jako pole zapasowe, dopóki podział nie zostanie
   ręcznie zweryfikowany na pełnym zbiorze 70 kurierów.
   **Rozwiązanie:** zaakceptowane jako jednorazowe ręczne przejście przez
   wszystkich kurierów — patrz `ux-ui.md`, sekcja "Narzędzie do przeglądu
   kurierów", i `demo/przeglad-kurierow-prototyp.html`

## Status

`schema_v2_draft.sql` to draft, NIE zastępuje `schema.sql`. Wdrożenie
wymaga: (1) potwierdzenia powyższych dwóch ryzyk, (2) przepisania
`importer.py` pod nowy model (parsowanie adresu na miejscowość/ulicę/nr,
parsowanie rejonu przez regex `^([A-Z]+)(\d+[A-Z]?)$`), (3) TDD dla całej
nowej logiki parsowania — to nie jest już czysty DDL, tu błędy parsowania
realnie namieszają w danych.
