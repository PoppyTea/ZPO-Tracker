"""
Rozbicie wolnego tekstu adresu na części składowe.

Zastępuje `rejonarz.rozbij_adres`, które obsługiwało wyłącznie znaczniki
`m.`/`lok.`/`mieszk.` oddzielone spacją i wymagało, żeby lokal był liczbą.
Pomiar na realnym snapshocie pokazał, że to za mało: z 219 adresów
niemożliwych do wyrejonizowania **161 miało PNI**, czyli były to punkty
ZPO - a te siedzą w lokalach usługowych zapisywanych w kilkunastu
wariantach naraz.

Naczelna zasada: `rozbij` NIGDY nie rzuca. Nieudane rozbicie jest stanem
wyniku (`pewnosc='brak'`), nie wyjątkiem - wiersz, którego nie umiemy
rozłożyć, ma trafić do pliku do poprawy, a nie wywalić cały import.

Druga zasada: `surowy` jest źródłem prawdy i nigdy nie jest nadpisywany.
Struktura to tylko jego interpretacja. Kiedy parser się poprawi - a
poprawi się, bo to jest lista reguł, nie algorytm - da się przepuścić
całą bazę jeszcze raz. Bez zachowanego oryginału ta operacja jest
niemożliwa i każda poprawka wymagałaby ponownego importu z Excela.
"""
import re
from dataclasses import dataclass

from zpo_tracker import normalizacja

PEWNOSC_PELNA = "pelna"
PEWNOSC_BEZ_MIASTA = "bez_miasta"
PEWNOSC_BRAK = "brak"

# Numer budynku: cyfry, opcjonalna litera, potem dowolnie wiele członów po
# ukośniku lub myślniku ("6/8", "49-51", "143A/145/LU2"). Rozdzielenie
# budynku od lokalu dzieje się DOPIERO w `_odetnij_lokal_po_ukosniku` -
# tutaj łapiemy całość, bo inaczej wzorzec musiałby zgadywać.
_NUMER_NA_KONCU = re.compile(
    r"^(?P<ulica>.*?)[\s,]+(?P<nr>\d+[A-Za-z]?(?:[-/][A-Za-z0-9]+)*)$")

# Jawny znacznik lokalu. Wymaga białego znaku PRZED sobą, żeby "m" nie
# łapało się w środku nazwy ulicy, ale po sobie dopuszcza dowolną
# kombinację kropki, przecinka i spacji - w realnych danych występują
# wszystkie: "lok. U2", "lok.U2", "lok U2", "lok, U4".
_LOKAL_ZE_ZNACZNIKIEM = re.compile(
    r"^(?P<reszta>.*?)[\s,]+(?:m|lok|mieszk)\.?[\s,]*"
    r"(?P<lokal>[A-Za-z0-9][A-Za-z0-9./,\-]*)$",
    re.IGNORECASE)

# Prefiks alei. Wariant bez kropki musi mieć po sobie biały znak, inaczej
# "Aleksandra" zostałoby pocięte na "al" + "eksandra".
_PREFIKS_ULICY = re.compile(r"^(?:aleje|aleja|al\.|al\s)\s*", re.IGNORECASE)

_MA_CYFRE = re.compile(r"\d")


@dataclass(frozen=True)
class Rozbicie:
    surowy: str
    miejscowosc: str | None = None
    typ_ulicy: str | None = None
    ulica: str | None = None
    nr_budynku: str | None = None
    nr_lokalu: str | None = None
    pewnosc: str = PEWNOSC_BRAK

    @property
    def klucz(self) -> str:
        """Pełny klucz dopasowania - z miejscowością."""
        return "|".join([
            normalizacja.klucz_rozmyty(self.miejscowosc or ""),
            normalizacja.klucz_rozmyty(self.ulica or ""),
            _klucz_numeru(self.nr_budynku),
        ])

    @property
    def klucz_ulica_nr(self) -> str:
        """
        Klucz bez miejscowości. Odpowiada TYLKO przy jednoznacznym
        trafieniu - zmierzone na eksporcie WER Ciemne: 15,04% takich
        kluczy wskazuje więcej niż jeden rejon.
        """
        return "|".join([
            normalizacja.klucz_rozmyty(self.ulica or ""),
            _klucz_numeru(self.nr_budynku),
        ])


def _klucz_numeru(nr) -> str:
    """Numer budynku NIE jest normalizowany rozmyto - `56` i `56A` to dwa
    różne budynki, często w różnych rejonach."""
    return (nr or "").upper().replace(" ", "")


def rozbij(adres) -> Rozbicie:
    """
    Wolny tekst -> `Rozbicie`. Nigdy nie rzuca.

    Kolejność jest istotna i wynika z tego, które sygnały są najmniej
    dwuznaczne: najpierw odcinamy miejscowość (przecinek), potem lokal ze
    znacznikiem, potem numer budynku, na końcu prefiks ulicy. Odwrócenie
    dowolnej pary psuje przypadki z realnych danych.
    """
    if adres is None:
        return Rozbicie(surowy="")
    surowy = str(adres)
    if not surowy.strip():
        return Rozbicie(surowy=surowy)

    miejscowosc, reszta = _odetnij_miejscowosc(surowy)
    reszta, lokal = _odetnij_lokal_ze_znacznikiem(reszta)

    dopasowanie = _NUMER_NA_KONCU.match(reszta)
    if not dopasowanie or not dopasowanie.group("ulica").strip():
        return Rozbicie(surowy=surowy, miejscowosc=miejscowosc)

    nr, lokal_z_ukosnika = _odetnij_lokal_po_ukosniku(dopasowanie.group("nr"))
    typ, ulica = _odetnij_prefiks(dopasowanie.group("ulica").strip())

    return Rozbicie(
        surowy=surowy,
        miejscowosc=miejscowosc,
        typ_ulicy=typ,
        ulica=ulica,
        nr_budynku=nr,
        nr_lokalu=lokal or lokal_z_ukosnika,
        pewnosc=PEWNOSC_PELNA if miejscowosc else PEWNOSC_BEZ_MIASTA,
    )


def _odetnij_miejscowosc(surowy):
    """
    Rozdziela po przecinku na część adresową i miejscowość.

    PUŁAPKA, przez którą to nie jest zwykłe `split(",")[-1]`: zapis
    `"lok.U13,U14"` ma przecinek, który NIE oddziela miejscowości.
    Rozróżnienie idzie po cyfrach - nazwy miejscowości ich nie zawierają,
    a numery lokali owszem. Przy jednym członie nie zgadujemy w ogóle,
    bo wtedy adres bez numeru ("Metro Ratusz") zostałby wzięty za miasto.
    """
    czesci = [c.strip() for c in surowy.split(",") if c.strip()]
    if len(czesci) < 2:
        return None, surowy.strip()

    adresowe = [c for c in czesci if _MA_CYFRE.search(c)]
    miasta = [c for c in czesci if not _MA_CYFRE.search(c)]
    if not adresowe:
        return None, surowy.strip()
    # Człony adresowe sklejamy z powrotem BEZ spacji po przecinku - to
    # odtwarza oryginał, a wzorzec lokalu ("lok.U13,U14") nie dopuszcza
    # spacji w środku i na sklejeniu ze spacją przestawał pasować.
    return (", ".join(miasta) or None), ",".join(adresowe)


def _odetnij_lokal_ze_znacznikiem(czesc):
    dopasowanie = _LOKAL_ZE_ZNACZNIKIEM.match(czesc)
    if not dopasowanie:
        return czesc, None
    return dopasowanie.group("reszta").strip(), dopasowanie.group("lokal")


def _odetnij_lokal_po_ukosniku(nr):
    """
    `"13/U1"` -> `("13", "U1")`, ale `"6/8"` -> `("6/8", None)`.

    Człon zaczynający się literą nie może być numerem budynku, więc jest
    lokalem. Człon czysto cyfrowy zostaje w budynku: `"6/8"` bywa
    podwójnym numerem JEDNEGO budynku równie często, co budynkiem
    z mieszkaniem, i rozstrzyga to dopiero wyszukiwanie, próbując obu
    odczytów - parser nie ma podstaw, żeby zgadywać.
    """
    if "/" not in nr:
        return nr, None
    czlony = nr.split("/")
    for i, czlon in enumerate(czlony[1:], start=1):
        if czlon[:1].isalpha():
            return "/".join(czlony[:i]), "/".join(czlony[i:])
    return nr, None


def _odetnij_prefiks(ulica):
    """
    `"Aleja Kwiatowa"` -> `("Aleja", "Kwiatowa")`.

    W danych ta sama ulica występuje w obu wariantach naraz - raz z
    prefiksem, raz bez. Wyniesienie prefiksu do osobnego pola sprawia,
    że oba dają ten sam klucz wyszukiwania.
    """
    if _PREFIKS_ULICY.match(ulica):
        return "Aleja", _PREFIKS_ULICY.sub("", ulica).strip()
    return None, ulica
