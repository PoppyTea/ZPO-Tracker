# Model domenowy — ustalenia z analizy realnych danych

Referencja dla `CLAUDE.md`. Ostatnia aktualizacja: analiza pliku
`2026-08-07-snapshot-ZPO_055210.xlsx` (arkusz "Czerwiec", dane sierpniowe —
nazwa arkusza nieaktualizowana, **każdy nowy miesiąc to nowy arkusz**, nie
czyszczenie starego).

## Cel i kontekst

Dział odziedziczył obowiązek prowadzenia miesięcznego zestawienia (Excel)
transakcji kurier↔punkt odbioru. Obecny proces: ręczne kopiowanie wiersza
z zeszłego miesiąca (ten sam kurier+punkt) i aktualizacja ilości z papierowej
dokumentacji. Brak jakiejkolwiek weryfikacji poprawności — błędy wychodzą na
jaw dopiero, gdy kurier zgłosi złą wypłatę.

Cel: zminimalizować powtarzalne elementy procesu (docelowo min. 12 000
wpisów/mies., nawet jeśli obecny ruch jest niższy z powodu utraty klienta)
i wprowadzić miękką walidację (ostrzeżenia, nie twarde blokady) tam, gdzie
dziś jej brak.

**Aktualizacja 2026-08-11 — aprobata kierownictwa WER Ciemne:** kierowniczka
całej jednostki (WER Ciemne, największa rozdzielnia w Polsce — nie tylko
dział, dla którego projekt powstał) zatwierdziła narzędzie jako element
zapewniający wyższą jakość danych rozliczeniowych, żeby nie musiała martwić
się o pomyłki wynikające ze sposobu wprowadzania danych. To nieformalne, ale
umocowane wysoko poparcie merytoryczne — nie formalne przyjęcie do
zatwierdzonego przez IT pipeline'u (brak przeglądu bezpieczeństwa,
podpisanego binarium czy formalnego właściciela po stronie IT). Potwierdza
trafność diagnozy problemu i podnosi stawkę błędu/utraty danych wyraźnie
powyżej poziomu prywatnego eksperymentu — konsekwencja dla kierunku prac po
`0.1-alpha.x` opisana w `roadmap.md`.

## Kolumny realne

Nie tylko "kurier + ZPO + ilość", jak zakładaliśmy na starcie: data, nadawca,
adres, kurier, rejon, wykonawca (Koli/Poczta Polska/Translist/Rekus),
ilość_total, ilość_zpo, PNI ZPO, ilość_vinted, ilość_automaty, kurier_48
(nieużywane w próbce), niezrealizowane (nieużywane w próbce).

## Kluczowe ustalenia

- **PNI ZPO jest wiarygodnym unikalnym identyfikatorem punktu** — pozorne
  "kolizje" (np. Kordeckiego 26 raz jako Legionowo, raz jako Chotomów) to
  niekonsekwentny zapis TEGO SAMEGO adresu, nie duplikat ID (zweryfikowane
  przez użytkownika ze zdjęciami/wyszukiwarką)
- **Zewnętrzny punkt odbioru ≠ tylko Żabka** — 883/892 punktów z PNI to
  Żabka, ale są też Duży Ben, Groszek, Delikatesy Centrum, ABC. Reguła to
  "ma PNI ZPO", nie "nadawca == Żabka"
- Formatowanie warunkowe (szare tło = 2 pola do wypełnienia, białe = 1 pole)
  **jest wiarygodne tylko dla pierwszej realnej partii wierszy** w tej
  konkretnej próbce (rows 2–1259) — dalej ktoś pociągnął formatowanie w dół
  bez związku z treścią. Nie polegać na formatowaniu jako źródle reguły w
  kodzie — liczy się wyłącznie obecność `PNI ZPO`
- W tej samej próbce: z 4573 wierszy tylko 1294 miało realną datę; reszta to
  puste, presformatowane wiersze-szablon (plus 35 "wierszy-widmo" z samą
  datą, bez reszty danych) — importer musi to pomijać, nie traktować jako błąd
- Domyślnie `ilosc_total` == `ilosc_zpo` dla punktów z PNI, ale pola muszą
  zostać **niezależnie edytowalne** w UI
- 70 surowych wpisów kurierów → **67 rzeczywistych osób** po scaleniu
  czystych duplikatów białych znaków; dodatkowo 1 para różniąca się literą
  ("Wołczuk Rafal"/"Wołczuk Rafał") wymaga decyzji człowieka, nie
  automatycznego scalenia (patrz `ux-ui.md` i `demo/przeglad-kurierow-prototyp.html`)

Zobacz też `normalization-v2.md` dla propozycji rozbicia tych ustaleń na
znormalizowany schemat relacyjny.
