# Zewnętrzne źródła danych referencyjnych (dla przyszłego wzbogacenia podpowiedzi)

Referencja dla `CLAUDE.md`. Zebrane 2026-08-09.

**Priorytet: NISKI przed MVP.** Silnik podpowiedzi oparty na już
wprowadzonych danych jest ważniejszy niż zasobność zewnętrznych źródeł —
patrz `ux-ui.md`. Te dane można dołożyć w dowolnym momencie później, o ile
silnik jest od początku zaprojektowany z wymiennym źródłem danych.

## A. Imiona polskie

Źródło: `dane.gov.pl` (Ministerstwo Cyfryzacji, rejestr PESEL) — "Lista
imion występujących w rejestrze PESEL, osoby żyjące". Darmowe, oficjalne,
aktualizowane raz w roku (ostatnio 20 stycznia 2026).
https://dane.gov.pl/pl/dataset/1667,lista-imion-wystepujacych-w-rejestrze-pesel-osoby-zyjace

Rozmiar: przefiltrowane lustro (imiona ≥150 wystąpień, dane z 2021) pokazuje
~960 żeńskich / ~976 męskich. Pełna, nieprzycięta lista będzie większa —
sprawdzić dokładną liczbę przy pobraniu.

Analogiczny zbiór nazwisk (przydatny do dalszej normalizacji kurierów):
https://dane.gov.pl/pl/dataset/1681,nazwiska-osob-zyjacych-wystepujace-w-rejestrze-pesel
(~590 tys.–800 tys. unikalnych nazwisk, w zależności od progu filtrowania)

## A1. + imiona ukraińskie

**Ważne odkrycie:** prawie 988 tys. uchodźców z Ukrainy ma nadany PESEL
(stan grudzień 2024). Ich imiona w rejestrze są zapisane w transliteracji
z oficjalnych dokumentów (np. "Ihor", "Dmytro", "Vladyslav") — dokładnie tej
samej, co w danych źródłowych projektu. **Zbiór z punktu A prawdopodobnie
już pokrywa większość tych imion** — osobna baza "imion ukraińskich pisanych
po polsku" może być zbędna.

## B. Miejscowości w woj. mazowieckim

Źródło: TERYT (GUS) — darmowy, oficjalny rejestr, aktualizowany na bieżąco
przy zmianach administracyjnych.
https://eteryt.stat.gov.pl/eTeryt/rejestr_teryt/udostepnianie_danych/baza_teryt/uzytkownicy_indywidualni/wyszukiwanie/wyszukiwanie.aspx

Mazowieckie: 42 powiaty, 314 gmin, **12 832 miejscowości** (obejmuje wsie,
kolonie, osady — nie tylko formalne "miasta" w wąskim sensie).

## B1. + ulice

Ten sam TERYT prowadzi przeszukiwalny rejestr ulic wg województwa (to samo
źródło co B). Dokładna liczba dla Mazowieckiego nie została sprawdzona.

## B2. Pełne adresy w woj. mazowieckim + aktualność

Źródło: GUGiK, Państwowy Rejestr Granic (PRG) — ok. 7 mln punktów
adresowych dla całej Polski, największa taka baza w kraju, darmowa,
w podziale na województwa (format GML).
https://www.gov.pl/web/gugik/dane-udostepniane-bez-platnie-do-pobrania-z-serwisu-wwwgeoportalgovpl

Mazowieckie (~15% populacji kraju): szacunkowo rząd kilkuset tysięcy do
ponad miliona punktów — brak potwierdzonej dokładnej liczby dla samego
województwa. Aktualność: gminy mają prawny obowiązek zgłaszać zmiany na
bieżąco; formalna aktualizacja raz w roku (stan na 1 stycznia).

## b) Sieci handlowe (Żabka, Pocztomaty, inne) — Google Maps API vs OpenStreetMap

**Google Places API — ODRZUCONE dla tego celu.** Regulamin Google Maps
Platform wprost zabrania trwałego przechowywania większości zwracanych
danych (nazwa, adres) — jedyny wyjątek to `place_id` (bezterminowo)
i same współrzędne (max 30 dni, potem trzeba usunąć).
https://cloud.google.com/maps-platform/terms/maps-service-terms
Budowa stałej, lokalnej bazy do offline'owych podpowiedzi łamie ten
regulamin — niezależnie od tego, że środowisko produkcyjne i tak nie ma
internetu, żeby odpytywać na bieżąco. (Koszt też nie byłby trywialny przy
pełnym pokryciu województwa, ale to drugorzędne wobec problemu z ToS.)

**OpenStreetMap — właściwe narzędzie.** Licencja ODbL wprost pozwala
pobierać, przechowywać i redystrybuować dane (przy zachowaniu atrybucji).
Geofabrik ma gotowy, darmowy wycinek tylko dla woj. mazowieckiego:
https://download.geofabrik.de/europe/poland/mazowieckie.html
(`mazowieckie-latest.osm.pbf`, ~283MB, aktualizowany codziennie).

Podejście: pobrać raz, filtrować lokalnie (np. `osmium`/`pyosmium`
w Pythonie) po tagach typu `shop=convenience` + `brand=Żabka` (analogicznie
ABC, Groszek, Delikatesy Centrum). Zero zapytań w środowisku produkcyjnym —
pasuje do ograniczenia offline.

**Korekta nazewnictwa:** automaty paczkowe Poczty Polskiej nazywają się
**"Pocztomat"**, nie "Paczkomat" (to zastrzeżona nazwa InPostu) — ważne przy
doborze właściwych tagów/brandów w OSM.

**Zastrzeżenie jakości:** OSM jest współtworzony społecznościowo, pokrycie
nie jest gwarantowane w 100%. W praktyce duże sieci w zurbanizowanym
Mazowieckiem są całkiem dobrze zmapowane, ale będą białe plamy — pasuje to
do reszty projektu: źródło pod miękkie podpowiedzi, nie twardą walidację.
