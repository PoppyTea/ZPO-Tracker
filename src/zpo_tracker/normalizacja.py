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
from dataclasses import dataclass, field

_DIAKRYTYKI = str.maketrans("ąćęłńóśźż", "acelnoszz")

PROG_LITEROWKI = 1  # maks. dystans edycyjny uznawany za literówkę, nie inną wartość


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
