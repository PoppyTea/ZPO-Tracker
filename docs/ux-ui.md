# UX/UI — ustalenia i otwarte pytania

Referencja dla `CLAUDE.md`.

## Inspiracja blankietem (ustalone)

Dane wprowadzane są ze stosu papierowych blankietów — **jeden kurier = jeden
blankiet**, a wiersze blankietu to adres + ilość. Propozycja UX: domyślny
tryb wprowadzania zaczyna się od wyboru kuriera, potem pokazuje wszystkie
jego punkty pogrupowane po obsługiwanych rejonach, z łatwym zamknięciem
całego rejonu (jeśli nieaktualny danego dnia) lub dodaniem rejonu spoza
planu. To odwzorowuje fizyczną strukturę blankietu 1:1 — minimalizuje
mapowanie mentalne papier→ekran.

Konsekwencja: wymaga ustalonej hierarchii przynależności między encjami
(kurier / rejon / wykonawca / punkt) — patrz `normalization-v2.md`.

## "Idioto-odporność", nie tylko "nietechniczność" (ustalone, ważna korekta)

Określenie "użytkownicy nietechniczni" nie oddaje skali problemu dla części
osób, które będą z tego korzystać. Właściwe ramowanie to **odporność na
błędy na poziomie znacznie bardziej skrajnym niż zwykłe "prosty UX dla
nietechnicznych"** — projektuj z założeniem dużo niższej tolerancji na
niejednoznaczność, więcej ochrony przed przypadkowym błędem, mniej zaufania
do domyślnej ostrożności użytkownika, niż standardowe dobre praktyki UX by
sugerowały.

## Walidacja (ustalone)

Miękkie ostrzeżenia, nie twarde blokady. Przykład zaimplementowany:
duplikat PNI ZPO z innym adresem → ostrzeżenie z możliwością kontynuacji,
nie wyjątek/blokada (patrz `src/zpo_tracker/importer.py`).

## Zakres MVP formularza (ustalone)

W formularzu aktywne są tylko `ilosc_total` i `ilosc_zpo`. Pozostałe kolumny
ilościowe (`ilosc_vinted`, `ilosc_automaty`, `ilosc_kurier48`,
`ilosc_niezrealizowane`) są obecne w schemacie, ale nieaktywne w UI, dopóki
nie okaże się, że są potrzebne. Domyślnie `ilosc_total` == `ilosc_zpo` dla
punktów z PNI, oba pola niezależnie edytowalne.

## Silnik podpowiedzi (priorytet na MVP — ustalone, szczegóły otwarte)

Priorytet: mieć działający, przyjemny w użyciu **silnik generujący
podpowiedzi na bazie danych już wprowadzonych do lokalnej bazy** (kurierzy,
punkty) — ważniejsze na tym etapie niż zasobność zewnętrznych danych
referencyjnych. Zewnętrzne źródła (patrz `reference-data-sources.md`) można
dołożyć później bez przeprojektowywania silnika — architektura podpowiedzi
powinna to od razu uwzględniać (źródło danych jako wymienny komponent, nie
zaszyte na sztywno).

Mechanizm interakcji ustalony i zrealizowany w `0.1-alpha.3.1` — patrz
sekcja "Dedukcja pól, wskaźniki, tryb auto" niżej.

## Narzędzie do przeglądu kurierów (ustalone, osobne od głównego UI)

Jednorazowe narzędzie do ręcznego potwierdzenia podziału imię/nazwisko dla
istniejących kurierów (nie część głównego, codziennego UI wprowadzania
danych). Zaprojektowane i zaprototypowane jako klikalny artefakt HTML
(`demo/przeglad-kurierow-prototyp.html`): tabela Imię/Nazwisko/Drugie imię
z przyciskiem `[<=>]` per wiersz + "zamień wszystkich", pasek statusu
(szary/zielony/pomarańczowy) sygnalizujący przejrzane/zmienione wiersze.

Prototyp na realnych danych: 70 surowych wpisów → 67 rzeczywistych osób po
scaleniu czystych duplikatów białych znaków (bezpieczna automatyzacja) +
1 para różniąca się literą oznaczona jako miękkie ostrzeżenie, nie
automatyczne scalenie.

**Docelowy interfejs produkcyjny to wciąż tkinter** (offline, bez
instalacji, bez przeglądarki) — HTML służy wyłącznie do prototypowania
i walidacji przepływu UX przed implementacją.

## Dedukcja pól, wskaźniki, tryb auto (`0.1-alpha.3.1`, zrealizowane)

Odpowiedź na pytanie z sekcji "Silnik podpowiedzi" wyżej — jak dokładnie
działa mechanizm interakcji. Silnik dedukcji: `src/zpo_tracker/dedukcja.py`.

**Pola główne:** Kurier, Data, Adres, Ilość, „w tym ZPO". **Drugorzędne
(dedukowane):** Nadawca, PNI ZPO, Rejon, Wykonawca. Ilość/„w tym ZPO" mają
status wyjątkowy: główne pod względem aktywności/nawigacji/blokady
zapisu, ale nigdy nie bramują ani nie są źródłem dedukcji pozostałych pól
— dedukcja rusza z kuriera/adresu niezależnie od tego, czy Ilość jest
jeszcze wypełniona.

**Zasada jednolita:** jednoznaczne → pole wypełnia się samo i staje
readonly (zaznaczalne, ale niepomijane wzrokiem — zielone); niejednoznaczne
→ pole NIE wypełnia się, aktywuje się, sprzeczne warianty pokazują się
jako podpowiedzi (pomarańczowe). Nowy adres bez żadnego dopasowania →
czerwone, aktywne, do wypełnienia ręcznie.

Kolejność rozstrzygania w wierszu: **najpierw punkt** (z adresu,
opcjonalnie zawężony ręcznie wpisanym nadawcą), dopiero z rozstrzygniętego
punktu nadawca/PNI/rejon. PNI nigdy nie jest dedukowane niezależnie od
nadawcy. Wykonawca dedukowany z historii kuriera na poziomie nagłówka
blankietu (jeden blankiet = jeden kurier = jeden wykonawca).

**Kolory wskaźnika** (pasek po lewej stronie pola,
`gui/widget_pole.PoleZeWskaznikiem`): szary (nieaktywne/brak danych),
zielony (wypełnione, OK), pomarańczowy (wymaga wyboru spośród wariantów),
czerwony (nowy punkt/brak dopasowania, wymaga ręcznego wpisania). Pole
aktywne (pomarańczowe/czerwone) dostaje dodatkowo obwódkę w tym samym
kolorze.

**Nawigacja — tryb auto:** TAB/Enter są równoważne i prowadzą WYŁĄCZNIE
przez pola główne plus każde pole, które akurat wymaga uwagi (aktywne
drugorzędne) — kolejność liczona dynamicznie z wyniku dedukcji
(`dedukcja.kolejnosc_pol`), nie z układu widgetów na ekranie, bo pole
może aktywować się "za" tym, na którym użytkownik już jest. Pole następne
w kolejności (dokądkolwiek doprowadzi kolejny Tab) dostaje własne,
cieńsze podświetlenie tym samym motywem koloru — widoczny sygnał "tu
wyląduję dalej", nawet gdy pole jest wciąż "w przygotowaniu" (dedukcja
jeszcze nie zdążyła go rozstrzygnąć).

**Świadomie odłożone do `0.1-alpha.5`** (patrz `roadmap.md`): tryb pół-auto
i manualny, przełącznik trybów, blokowanie pola kliknięciem we wskaźnik. Nie
weszły do `0.1-alpha.3.2`, bo nie przechodzą filtra „czy przybliża nas to do
realnej pracy" — to wygoda, nie warunek używalności. (`settings.json`
powstał w `0.1-alpha.3.2`, ale w innej roli — patrz niżej.)

## Poprawki po zapisie i zdrowie danych (`0.1-alpha.3.2`, zrealizowane)

Feedback pracowników (2026-08-13) wskazał jedną rzecz jako faktycznie
blokującą pracę: **brak możliwości poprawiania danych po zapisie.**
W kodzie okazało się to dosłowne — nie istniała żadna ścieżka edycji ani
usunięcia zapisanej transakcji, a `UNIQUE(data, kurier, punkt)` odrzucał
ponowne wpisanie poprawionego wiersza jako duplikat.

**Widok poprawek** = przebudowana zakładka Przeglądanie (nie nowa zakładka —
„znajdź i popraw" ma być jednym miejscem): filtry po kurierze, zakresie dat,
tekście (nadawca/adres) i bieżącej sesji wprowadzania; dwuklik otwiera
edycję wiersza; zaznaczenie wielu wierszy pozwala ustawić jedno wspólne pole
albo usunąć je razem (z potwierdzeniem pokazującym próbkę tego, co znika).

**Dialog edycji jest świadomie zwykły** — bez maszynerii dedukcji
i wskaźników. Korekta to jawna decyzja człowieka nad już zapisanym wierszem;
dedukcja walcząca z ręczną poprawką byłaby antywzorcem. Nadawca/adres/PNI
pozostają nieedytowalne: przepięcie wiersza na inny punkt to inna klasa
ryzyka (cicha zmiana historii punktu) niż poprawka daty czy ilości — na
razie robi się to przez usunięcie i ponowne wpisanie w formularzu.
**Docelowo** ta mechanika ma być niewidoczna dla użytkownika (czy pod maską
punkt jest tworzony na nowo, nie powinno go obchodzić) — wymaga to jednak
sprzężenia z dedukcją i blokad przy sprzecznościach, czyli powielenia logiki
formularza. Za duże na to wydanie, warte uwagi później.

**Zmiany w formularzu wprowadzania:**

- podgląd pokazuje domyślnie **tylko bieżącą sesję** („czy to się zapisało?"
  ma być odpowiadalne bez przewijania całej bazy); checkbox odsłania resztę
- dwuklik w podglądzie otwiera ten sam dialog edycji
- Tab/Enter z końca **wypełnionego** ostatniego wiersza tworzy nowy wiersz
  zamiast zawijać do nagłówka (pusty ostatni wiersz dalej zawija — nie ma
  sensu mnożyć pustych)
- status zapisu ma realny kolor: zielony przy pełnym sukcesie, **czerwony
  gdy cokolwiek pominięto**, z wypisaniem którego wiersza i dlaczego
- **wiersze pominięte zostają w siatce, wypełnione** — do poprawki
  i ponownego zapisu. Dotąd formularz czyścił się bezwarunkowo, także gdy
  nie zapisał ani jednego wiersza: praca użytkownika przepadała bez śladu.
- Historia pokazuje osobną kolumnę „Pominięto" — zapis samych duplikatów
  przestaje wyglądać identycznie jak pełny sukces

**Rejon przestał być polem do wpisywania.** Wypełnia się tylko wtedy, gdy
historia punktu jest jednoznaczna; przy braku albo sprzeczności zostaje
pusty i zapisuje się jako `???`. Dane o rejonach z papierowych blankietów są
zakłamane, a rejonarz (`0.1-alpha.3.3/3.4`) będzie źródłem prawdy — do tego
czasu lepiej mieć jawnie „nieznany" niż cudzą pomyłkę przepisaną z papieru.

**Nadawcy bez PNI** (ZUS, PKO, Kruk…) dostali własną podzakładkę
w Słownikach. Wcześniej istnieli wyłącznie jako tekst w `punkty.nadawca`
i literówki w ich nazwach były w aplikacji nienaprawialne — słownik „Firmy
ZPO" z konstrukcji pokazuje tylko sieci mające PNI.

**Zaufanie do importowanych plików.** Eksport znakuje plik i dokłada
kryptograficzny odcisk (SHA-256) zawartości. Plik bez znacznika nie wnosi
PNI ani rejonu (reszta danych wchodzi normalnie — są czytelne i poprawialne).
Plik z naszym znacznikiem, ale zmienioną zawartością, **nie może zostać
uznany za zaufany żadną drogą**, także nie przez tryb zaawansowany: pliki
`.xlsx` są trywialnie edytowalne w Excelu, więc sam znacznik niczego nie
dowodzi. Wymuszenie zaufania dla obcych plików istnieje, ale jest ukryte —
pojawia się dopiero, gdy `settings.json` zawiera wpis odsłaniający tryb
zaawansowany, i wymaga osobnego zaznaczenia przy każdym użyciu.
