"""
Dopasowanie kolumn arkusza po NAGŁÓWKU, nie po pozycji.

Powstał pod import rejonarza, ale celowo nie wie nic o rejonach - profil
jest parametrem, nie stałą modułową. Dwa powody istnienia:

1. **Odporność.** Dzisiejsze mapowanie (`import_orchestrator.MAPA_NAGLOWKOW`)
   porównuje stringi dokładnie, więc `" Pełna Nazwa Nadawcy"` ze spacją
   na początku jest czymś innym niż `"Pełna Nazwa Nadawcy"`, a instrukcja
   BaŚKi ma sześć lat i nikt nie obiecywał stabilności nagłówków co do
   znaku. Tutaj porównanie idzie po `normalizacja.klucz_rozmyty`,
   z literówką jako ostatnią deską ratunku.

2. **Selektywność.** Profil może pomijać kolumny, więc "wciągnij tylko te
   pozycje" wychodzi za darmo - przydatne przy danych historycznych.

Czego ten moduł NIE robi: nie czyta plików, nie zna openpyxl, nie dotyka
bazy. Dostaje listę nagłówków i oddaje mapowanie.

Świadomie NIE podpięty pod istniejącą ścieżkę importu Excela - tamta
działa i jej przepisywanie to osobna robota, nie efekt uboczny rejonarza.
"""
import re
from dataclasses import dataclass, field

from zpo_tracker import normalizacja


@dataclass(frozen=True)
class Profil:
    """`pola`: nazwa docelowa -> lista akceptowanych nagłówków.
    `wymagane`: podzbiór kluczy `pola`, bez których import nie ma sensu."""

    pola: dict
    wymagane: frozenset = frozenset()

    def __post_init__(self):
        nieznane = set(self.wymagane) - set(self.pola)
        if nieznane:
            raise ValueError(
                f"wymagane pola spoza profilu: {sorted(nieznane)}")


@dataclass
class OstrzezenieTresci:
    pole: str
    naglowek: str
    powod: str


@dataclass
class Dopasowanie:
    mapowanie: dict = field(default_factory=dict)   # naglowek -> pole
    braki: list = field(default_factory=list)       # wymagane bez kolumny
    nierozpoznane: list = field(default_factory=list)

    @property
    def kompletne(self) -> bool:
        return not self.braki

    def naglowek_dla(self, pole):
        for naglowek, cel in self.mapowanie.items():
            if cel == pole:
                return naglowek
        return None


def _klucz(naglowek) -> str:
    return normalizacja.klucz_rozmyty(str(naglowek))


def dopasuj_kolumny(naglowki, profil: Profil) -> Dopasowanie:
    """
    Nagłówki arkusza -> `Dopasowanie`. Nie rzuca wyjątkiem przy brakach:
    wywołujący ma zobaczyć PEŁNY obraz (czego brakuje ORAZ czego nie
    rozpoznano) i sam zdecydować, czy to jeszcze da się zaimportować.
    Rzucenie na pierwszym braku pokazywałoby jeden problem naraz.
    """
    warianty = {
        _klucz(w): pole
        for pole, lista in profil.pola.items()
        for w in lista
    }
    wynik = Dopasowanie()
    zajete = set()

    for naglowek in naglowki:
        if naglowek is None or not str(naglowek).strip():
            continue
        klucz = _klucz(naglowek)
        pole = warianty.get(klucz)
        if pole is None:
            pole = _dopasuj_po_literowce(klucz, warianty)
        # Powtórzona kolumna nie nadpisuje pierwszej po cichu - arkusze
        # bywają sklejane z kilku i cicha podmiana byłaby najgorszym
        # możliwym zachowaniem.
        if pole is None or pole in zajete:
            wynik.nierozpoznane.append(naglowek)
            continue
        wynik.mapowanie[naglowek] = pole
        zajete.add(pole)

    wynik.braki = sorted(set(profil.wymagane) - zajete)
    return wynik


def _dopasuj_po_literowce(klucz, warianty):
    """Ostatnia deska ratunku. `czy_literowka` dopuszcza dystans 1, więc
    'Ulcia' trafi w 'Ulica', ale 'Wykonawca' nie trafi w nic - i o to
    chodzi, żeby wybaczanie literówek nie zamieniło się w dopasowywanie
    czegokolwiek do czegokolwiek."""
    trafienia = [
        pole for wariant, pole in warianty.items()
        if normalizacja.czy_literowka(klucz, wariant)
    ]
    # Dwa kandydaci to nie jest literówka, tylko niejednoznaczność -
    # zgadywanie w takiej sytuacji jest gorsze od przyznania się.
    return trafienia[0] if len(trafienia) == 1 else None


def wyodrebnij(surowy_wiersz, dopasowanie: Dopasowanie) -> dict:
    """Surowy wiersz (nagłówek -> wartość) na wiersz w nazwach docelowych.
    Kolumny spoza mapowania po prostu nie wchodzą."""
    return {
        pole: surowy_wiersz[naglowek]
        for naglowek, pole in dopasowanie.mapowanie.items()
        if naglowek in surowy_wiersz
    }


# --- heurystyki treści: siatka bezpieczeństwa, nie walidacja -------------
#
# Nagłówek może się zgadzać, a kolumny i tak być przesunięte albo arkusz
# nie ten. Te wzorce mają wyłapać taki przypadek, nie sprawdzać poprawność
# danych - od tego jest pydantic w warstwie wyżej.

WZORCE_TRESCI = {
    "pna": re.compile(r"^\d{2}-\d{3}$"),
    "pni": re.compile(r"^\d{6}$"),
    "tk": re.compile(r"^[12X]$"),
    "wezel": re.compile(r"^[A-Z]{2}$"),
}

# Ile próbek musi pasować, żeby uznać kolumnę za swoją. Nie 100%, bo
# realne dane mają dziury i literówki; nie 50%, bo wtedy przesunięcie
# o jedną kolumnę mogłoby przejść.
PROG_ZGODNOSCI = 0.8


def pasuje_do_wzorca(pole, wartosci):
    """
    True/False dla pól ze wzorcem, **None dla pól bez wzorca**.

    None znaczy "nie wiem", nie "nie pasuje" - inaczej siatka
    bezpieczeństwa zamieniłaby się w generator fałszywych alarmów dla
    każdej kolumny tekstowej.
    """
    wzorzec = WZORCE_TRESCI.get(pole)
    if wzorzec is None:
        return None
    niepuste = [str(w).strip() for w in wartosci if w is not None and str(w).strip()]
    if not niepuste:
        return False
    trafione = sum(1 for w in niepuste if wzorzec.match(w))
    return trafione / len(niepuste) >= PROG_ZGODNOSCI


def sprawdz_tresc(dopasowanie: Dopasowanie, probki: dict):
    """
    `probki`: pole -> lista przykładowych wartości z tej kolumny.
    Oddaje ostrzeżenia dla kolumn, których treść przeczy nagłówkowi.
    """
    ostrzezenia = []
    for pole, wartosci in probki.items():
        if pasuje_do_wzorca(pole, wartosci) is False:
            ostrzezenia.append(OstrzezenieTresci(
                pole=pole,
                naglowek=dopasowanie.naglowek_dla(pole),
                powod=f"treść nie pasuje do wzorca pola '{pole}'",
            ))
    return ostrzezenia
