"""
Normalizacja tekstu i dedup literówek dla danych wpisywanych ręcznie.
Trzy poziomy pewności, świadomie rozdzielone (patrz docs/domain-model.md,
przypadek "Wołczuk Rafal"/"Wołczuk Rafał"):
  1. Identyczne po klucz_bialych_znakow -> ten sam string, bezpieczne
     automatyczne scalenie (czysty artefakt wpisywania, np. spacja na końcu).
  2. Identyczne po klucz_rozmyty, ale różne po klucz_bialych_znakow
     (różnica w wielkości liter/diakrytykach) -> WYŁĄCZNIE miękkie
     ostrzeżenie, nigdy automatyczne scalanie - to decyzja człowieka.
  3. Bliski dystans edycyjny, ale nie #1 ani #2 -> prawdopodobna literówka
     klawiaturowa, automatyczny dedup z możliwością odrzucenia (przywrócenia).

Wzorzec kluczy przeniesiony z demo/przeglad-kurierow-prototyp.html
(wsKey/fuzzyKey), tam sprawdzony na realnej liście 70 kurierów.
"""
import re
from dataclasses import dataclass, field

_DIAKRYTYKI = str.maketrans("ąćęłńóśźż", "acelnoszz")

PROG_LITEROWKI = 1  # maks. dystans edycyjny uznawany za literówkę, nie inną wartość

REJON_NIEZNANY = "???"
_REJON_SMIECI = {"-", "n/a", "null"}


def normalizuj_rejon(kod: str | None) -> str:
    """
    Kanoniczny "rejon nieznany". Pusty kod oraz każdy zawierający "?",
    zawierający spację, albo równy (bez uwzględniania wielkości liter)
    "-"/"n/a"/"null" -> REJON_NIEZNANY. Idempotentna: normalizuj_rejon(
    REJON_NIEZNANY) == REJON_NIEZNANY, bo "???" sam zawiera "?".

    Obowiązuje we WSZYSTKICH ścieżkach zapisu (formularz, import, scalanie
    baz) - inaczej ten sam śmieciowy rejon istniałby w bazie pod różnymi
    postaciami zależnie od tego, którędy trafił.
    """
    if kod is None:
        return REJON_NIEZNANY
    kod = kod.strip()
    if not kod:
        return REJON_NIEZNANY
    if "?" in kod or " " in kod:
        return REJON_NIEZNANY
    if kod.lower() in _REJON_SMIECI:
        return REJON_NIEZNANY
    return kod


PREFIKS_REJONU_WARSZAWA = "WA"

# Pięć wartości, które stoją w drzewie ścieżek BaŚKi jako rodzeństwo
# rejonów numerycznych, ale kodami rejonu NIE są. Instrukcja mówi wprost
# o pierwszej z nich: "należy zmienić pozycje oznaczone *UP poprzez
# uzupełnienie właściwego rejonu doręczeń", a o ZPO: "ZPO LUB właściwy
# nr rejonu doręczeń". Czyli oba znaczą dokładnie tyle, co nasze "???".
_WARTOWNICY_BASKI = frozenset({"*up", "zpo", "up", "ap", "fup"})

_GOLY_NUMER = re.compile(r"^\d+[A-Za-z]?$")
_Z_PREFIKSEM = re.compile(r"^[A-Za-z]{1,3}\d+[A-Za-z]?$")
# Kody czysto literowe (MIG, POU, PP, RDH, WER, WRC, WRT) - potwierdzone
# w realnym eksporcie "WW - WER Ciemne", gdzie stoją w liście rejonów na
# równi z numerycznymi, a RDH niesie realne adresy. Granica 2-4 liter
# wzięta z tego samego zbioru; luźniejszy wzorzec zacząłby przepuszczać
# nazwy miejscowości.
_CZYSTO_LITEROWY = re.compile(r"^[A-Za-z]{2,4}$")


def normalizuj_rejon_baska(kod: str | None) -> str:
    """
    Rejon z eksportu BaŚKi -> kanoniczny kod albo REJON_NIEZNANY.

    Reguła potwierdzona naocznie w przeglądarce (2026-08-23): interesują
    nas rejony węzła `WW` o typie kierowania `1`, a do gołego numeru
    doklejamy literał `WA`.

    UWAGA, pułapka: **`WA` NIE jest kodem węzła źródłowego.** W BaŚce
    istnieje osobny węzeł o kodzie `WA` - to WER Warszawa W101 przy
    ul. Łączyny, zupełnie inny byt. Wnioskowanie "prefiks = kod węzła"
    jest błędne, mimo że pozornie potwierdzają je i zrzuty siatki dla
    Warszawy, i przykładowa odpowiedź w dokumentacji API
    (`<endNode>WA</endNode>` obok `<deliveryRegion>100</deliveryRegion>`).
    Kiedyś ta reguła była prawdziwa, dziś nie jest.

    Filtrowanie po węźle i typie kierowania NIE należy tutaj - to zadanie
    warstwy importu, która widzi cały wiersz, nie samą wartość rejonu.

    Kod z innym prefiksem literowym (`ND1`, `L11`, `Z3`) zostaje nietknięty
    poza podniesieniem wielkości liter; doklejenie `WA` dałoby `WAND1`,
    czyli gorzej niż zostawienie jak jest. Potwierdzone realnym eksportem
    „WW - WER Ciemne": pod JEDNYM węzłem współistnieją kody gołe (`87`,
    `106`) i literowe (`K1`, `L11`, `Z3`), a w naszej bazie żyją zarówno
    `WA87`, jak i `Z3` - czyli reguła jest zgodna z danymi.

    Kody CZYSTO LITEROWE (`PP`, `WER`, `RDH`) też są prawidłowymi
    rejonami. Nie da się ich odróżnić kształtem od wartowników (`UP`,
    `AP`, `FUP`) - dlatego lista wartowników jest jawna i sprawdzana
    PRZED regułą kształtu, a nie wyprowadzana z niej.
    """
    if kod is None:
        return REJON_NIEZNANY
    kod = kod.strip()
    if not kod:
        return REJON_NIEZNANY
    if kod.lower() in _WARTOWNICY_BASKI:
        return REJON_NIEZNANY
    # Stare reguły śmieci (spacja w środku, "?", "-", "n/a", "null")
    # obowiązują dalej - nie powielamy ich tutaj.
    if normalizuj_rejon(kod) == REJON_NIEZNANY:
        return REJON_NIEZNANY
    if _GOLY_NUMER.match(kod):
        return PREFIKS_REJONU_WARSZAWA + kod.upper()
    if _Z_PREFIKSEM.match(kod) or _CZYSTO_LITEROWY.match(kod):
        return kod.upper()
    # Wszystko inne to najczęściej ścieżka częściowa ("PO-1----") albo
    # kształt, którego nie rozpoznajemy. Zgadywanie tutaj byłoby dokładnie
    # tym, co rejonarz ma wyeliminować.
    return REJON_NIEZNANY


def klucz_bialych_znakow(s: str) -> str:
    """Trim + collapse wielokrotnych białych znaków (spacje/taby/nowe linie)."""
    return " ".join(s.split())


def klucz_rozmyty(s: str) -> str:
    """klucz_bialych_znakow + lowercase + bez polskich diakrytyków."""
    return klucz_bialych_znakow(s).lower().translate(_DIAKRYTYKI)


def odleglosc_edycyjna(a: str, b: str) -> int:
    """
    Dystans edycyjny (wstawienie/usunięcie/zamiana), z transpozycją dwóch
    sąsiednich znaków liczoną jako pojedyncza operacja - to najczęstszy typ
    literówki z klawiatury (np. "Kowalksi" zamiast "Kowalski").
    """
    m, n = len(a), len(b)
    d = [[0] * (n + 1) for _ in range(m + 1)]
    for i in range(m + 1):
        d[i][0] = i
    for j in range(n + 1):
        d[0][j] = j
    for i in range(1, m + 1):
        for j in range(1, n + 1):
            koszt = 0 if a[i - 1] == b[j - 1] else 1
            d[i][j] = min(
                d[i - 1][j] + 1,
                d[i][j - 1] + 1,
                d[i - 1][j - 1] + koszt,
            )
            if i > 1 and j > 1 and a[i - 1] == b[j - 2] and a[i - 2] == b[j - 1]:
                d[i][j] = min(d[i][j], d[i - 2][j - 2] + 1)
    return d[m][n]


def czy_literowka(a: str, b: str) -> bool:
    """
    Prawdopodobna literówka klawiaturowa: bliski dystans edycyjny po
    normalizacji, ale NIE identyczne po klucz_rozmyty (te przypadki to
    różnica w diakrytykach/wielkości liter - obsługuje je znajdz_podobne
    jako decyzję człowieka, nie automat).
    """
    ka, kb = klucz_rozmyty(a), klucz_rozmyty(b)
    if ka == kb:
        return False
    if abs(len(ka) - len(kb)) > PROG_LITEROWKI:
        return False
    return odleglosc_edycyjna(ka, kb) <= PROG_LITEROWKI


@dataclass
class GrupaWpisow:
    kanoniczna: str
    warianty: list = field(default_factory=list)

    @property
    def liczba(self) -> int:
        return len(self.warianty)


@dataclass
class Podobienstwo:
    a: str
    b: str


def grupuj_bezpiecznie(wartosci):
    """
    Bezpieczne automatyczne scalanie: identyczne po klucz_bialych_znakow.
    Kanoniczna forma = pierwsze napotkane wystąpienie.
    """
    grupy = {}
    for w in wartosci:
        klucz = klucz_bialych_znakow(w)
        if klucz not in grupy:
            grupy[klucz] = GrupaWpisow(kanoniczna=klucz)
        grupy[klucz].warianty.append(w)
    return list(grupy.values())


def znajdz_podobne(grupy):
    """
    Miękkie ostrzeżenie: różne grupy (różne po białych znakach), ten sam
    klucz_rozmyty. Nigdy automatyczne scalanie.
    """
    ostrzezenia = []
    for i, g1 in enumerate(grupy):
        for g2 in grupy[i + 1:]:
            if klucz_rozmyty(g1.kanoniczna) == klucz_rozmyty(g2.kanoniczna):
                ostrzezenia.append(Podobienstwo(g1.kanoniczna, g2.kanoniczna))
    return ostrzezenia
