"""
Dedukcja miejscowości dla adresu, który jej nie zawiera.

Kurierzy miejscowości nie piszą - Warszawa jest dla nich domyślna, więc
w naszych danych dominuje goła "Kwiatowa 8". Skutek zmierzony na eksporcie
"WW - WER Ciemne": 15,04% kluczy `ulica|nr` wskazuje więcej niż jeden
rejon, czyli co siódmego adresu nie da się wyrejonizować bez miejscowości.
Ten moduł ma ją WYDEDUKOWAĆ - albo uczciwie powiedzieć, że nie potrafi.

**Kaskada reguł, malejąco po pewności, pierwsza trafiona wygrywa.**
Wynik zawsze niesie nazwę reguły (`Wynik.zrodlo`, do zapisu w
`adresy.zrodlo_miejscowosci`), bo bez niej człowiek przeglądający dane nie
odróżni "wiemy na pewno" od "zgadliśmy z dnia kuriera" - a to są dwa
zupełnie różne poziomy zaufania, które w tabeli wyglądają identycznie:

  0. `z_adresu`                - miejscowość podał człowiek, nie zgadujemy
  1. `jednoznaczny_w_rejonarzu`- klucz daje jedną miejscowość (55,3%)
  2. `zalozona_warszawa`       - jedyny kandydat z gminy Warszawa (+9,3%)
  3. `rejon_wskazuje_gmine`    - patrz GRANICA niżej
  4. `dzien_kuriera`           - reszta dnia tego kuriera (86% par w jednej gminie)
  5. `do_wyboru`               - kilku kandydatów, decyduje człowiek
  6. `brak`                    - nie mamy nic

GRANICA REGUŁY 3, najważniejsze rozstrzygnięcie tego modułu. Zmierzone:
rejony z prefiksem `WA` mieszczą się w dokładnie jednej gminie w **120 na
121** przypadków - tam wolno wpisać automatycznie. Rejony spoza `WA`
(`ND*`, `L*`, `R*`, `W*`, `XP*`, `MM*`, `XG*`, `XL*`) tylko w **32 na
59**: `ND4` obejmuje 36 miejscowości, `ND5` 35, `L9` 25. Dla nich
zgodność rejonu NIE dowodzi gminy, więc reguła wolno jej wyłącznie
ZAWĘZIĆ listę dla człowieka (`Wynik.zawezone_rejonem`), nigdy wpisać.
Dlatego też reguła 4 liczy się na PEŁNEJ liście kandydatów, nie na
zawężonej - inaczej rejon spoza `WA` rozstrzygałby automatycznie tylnymi
drzwiami, przez to, którzy kandydaci dotrwali do reguły 4.

ZERO ZALEŻNOŚCI OD BAZY. Rejonarz wchodzi jako wstrzykiwane callable
`szukaj(klucz_ulica_nr) -> iterable wierszy`, nie jako połączenie SQLite.
Powody, w kolejności ważności: (1) testy tej kaskady to testy REGUŁ, a nie
zapytań - z bazą każdy przypadek graniczny wymagałby postawienia migawki,
więc pisałoby się ich mniej; (2) `rejonarz.db` jest osobnym plikiem,
opcjonalnym na stacji - moduł, który potrafi żyć bez niego, nie musi
udawać, że go ma; (3) to samo callable obsłuży późniejsze źródła (API
DeliveryPath, migawka w pamięci) bez ruszania kaskady.

GMINA NIE JEST PARAMETREM WIERSZA, tylko jest wyliczana z miejscowości
(`gmina`). W migawce nie ma kolumny gminy - siedzi ona w samym napisie
("Warszawa (Śródmieście) - Warszawa"). Gmina podawana obok byłaby drugim
źródłem prawdy, mogącym po cichu przeczyć napisowi, który i tak pokazujemy
człowiekowi.

Funkcja `dedukuj` jest czysta i dla ZŁEGO WEJŚCIA nigdy nie rzuca - ta
sama zasada co w `adresy.rozbij`: wiersz, którego nie umiemy obsłużyć,
ma trafić do poprawy, a nie wywalić cały import. Wyjątek RZUCONY PRZEZ
`szukaj` idzie natomiast dalej i jest to decyzja świadoma: zepsute
połączenie z migawką to awaria infrastruktury, a nie brak danych.
Zamiecione tutaj, wyglądałoby jak zwyczajne "nie wiem" na 100% wierszy -
czyli cicha, globalna utrata funkcji nie do odróżnienia od normalnej
pracy. Co z nią zrobić, decyduje warstwa wywołująca.

ŚWIADOMIE NIE KANONIZUJEMY wchodzącego `rejon`. Migawka trzyma rejony po
`normalizuj_rejon_baska` (goły `87` staje się `WA87`), ale nasze ścieżki
zapisu używają `normalizuj_rejon`, który `WA` nie dokleja - stare wiersze
mogą więc nieść goły `87`, którego ta kaskada nie rozpozna. To NIE jest
przeoczenie do odruchowej naprawy: degraduje się dobrą stroną (program
pyta człowieka, zamiast wpisać cokolwiek), a doklejenie `WA` na wejściu
pozwoliłoby gołemu numerowi ze starych danych rozstrzygać automatycznie,
czyli ruszyłoby granicę 120/121. Decyzja należy do kroku integracji.
Przypięte w `test_goly_numer_rejonu_degraduje_sie_do_pytania_nie_do_bledu`.
"""
import re
from dataclasses import dataclass

from zpo_tracker import normalizacja

ZRODLO_Z_ADRESU = "z_adresu"
ZRODLO_JEDNOZNACZNY = "jednoznaczny_w_rejonarzu"
ZRODLO_WARSZAWA = "zalozona_warszawa"
ZRODLO_REJON = "rejon_wskazuje_gmine"
ZRODLO_DZIEN_KURIERA = "dzien_kuriera"
ZRODLO_DO_WYBORU = "do_wyboru"
ZRODLO_BRAK = "brak"

GMINA_WARSZAWA = "Warszawa"

# Separator gminy w zapisie BaŚKi: "Nowa Wieś - Nadarzyn". PUŁAPKA, przez
# którą wymagamy spacji po obu stronach: sam myślnik jest normalnym
# znakiem w nazwach dwuczłonowych ("Konstancin-Jeziorna"), a cięcie po nim
# rozbiłoby połowę miejscowości na nieistniejące gminy.
_SEPARATOR_GMINY = " - "

# Rejon warszawski w postaci kanonicznej (`normalizacja.normalizuj_rejon_baska`
# dokleja "WA" do gołego numeru). Sprawdzamy CAŁY kształt, nie sam prefiks:
# hipotetyczne "WAB1" czy "WER" zaczyna się od "WA"/"W", a rejonem
# warszawskim nie jest - a od tej odpowiedzi zależy, czy program wpisze
# wartość sam, czy zapyta człowieka. Sam prefiks bierzemy ze stałej, żeby
# nie mieć dwóch źródeł tej samej wiedzy.
_REJON_WARSZAWSKI = re.compile(
    rf"^{re.escape(normalizacja.PREFIKS_REJONU_WARSZAWA)}\d+[A-Za-z]?$")


@dataclass(frozen=True)
class Kandydat:
    """Jeden wiersz migawki: co stoi pod tym `ulica|nr`."""
    miejscowosc: str
    rejon: str | None = None


@dataclass(frozen=True)
class Wynik:
    """
    `kandydaci` to PEŁNA lista miejscowości możliwych pod tym adresem,
    `zawezone_rejonem` - jej podzbiór wskazany przez rejon transakcji
    (pusty, gdy reguła 3 nie zadziałała albo niczego nie ucięła). Dwie
    listy, nie jedna, bo dla rejonów spoza `WA` zawężenie ma prawo pomóc
    człowiekowi wybrać, ale nie ma prawa wpłynąć na wynik automatyczny -
    zlanie ich w jedno pole zacierałoby dokładnie tę różnicę.

    Inwariant: jeśli `miejscowosc` jest wypełniona, należy do `kandydaci`.
    Nigdy nie wpisujemy wartości spoza listy, którą pokazalibyśmy
    człowiekowi.
    """
    miejscowosc: str | None = None
    zrodlo: str = ZRODLO_BRAK
    kandydaci: tuple = ()
    zawezone_rejonem: tuple = ()

    @property
    def rozstrzygniete(self) -> bool:
        return bool(self.miejscowosc)


def gmina(miejscowosc) -> str:
    """
    `"Warszawa (Śródmieście) - Warszawa"` -> `"Warszawa"`.

    Na tym zwinięciu stoją reguły 2 i 3: bez niego dzielnice Warszawy są
    osobnymi miejscowościami i "dokładnie jedna z gminą Warszawa" nie
    byłoby prawdą prawie nigdy.

    Brak separatora znaczy "źródło nie podało gminy" - zwracamy wtedy samą
    nazwę, bo miejscowość jest własną tożsamością, a dopisanie jej gminy
    z głowy byłoby wymyślaniem danych. Przy kilku separatorach liczy się
    OSTATNI człon: gmina stoi na końcu zapisu, a człon środkowy bywa
    częścią nazwy ("Nowa Górka - Kolonia - Ługowice").
    """
    tekst = _tekst(miejscowosc)
    if not tekst:
        return ""
    return tekst.rsplit(_SEPARATOR_GMINY, 1)[-1].strip()


def czy_rejon_warszawski(rejon) -> bool:
    """
    Czy ten kod rejonu wolno traktować jako wskazanie gminy (reguła 3).

    To jedyne miejsce, w którym przebiega granica 120/121 vs 32/59 -
    stąd osobna, publiczna funkcja: ma być testowalna wprost i widoczna
    dla czytającego kaskadę.
    """
    kod = _tekst(rejon).upper()
    if normalizacja.normalizuj_rejon(kod) == normalizacja.REJON_NIEZNANY:
        return False
    return bool(_REJON_WARSZAWSKI.match(kod))


def dedukuj(rozbicie, szukaj, *, rejon=None, miejscowosci_dnia=()) -> Wynik:
    """
    Kaskada. `rozbicie` to `adresy.Rozbicie`, `szukaj` to wstrzyknięty
    rejonarz (patrz docstring modułu).

    `rejon` - kod rejonu ZNANY DLA TEJ TRANSAKCJI (z papieru, z importu
    zaufanego albo z wcześniejszej dedukcji). `miejscowosci_dnia` -
    miejscowości ustalone już dla innych transakcji tego samego kuriera
    tego samego dnia; wywołujący nie musi ich odsiewać ani odróżniać
    dedukowanych od podanych, bo reguła 4 i tak sprowadza je do gmin.
    """
    podana = _tekst(getattr(rozbicie, "miejscowosc", None))
    if podana:
        # Człowiek, który miejscowość napisał, jest lepszym źródłem niż
        # cała kaskada. Rejonarza nawet nie pytamy - to nie oszczędność
        # zapytania, tylko gwarancja, że migawka nie ma jak nadpisać
        # tego, co podał kurier.
        return Wynik(podana, ZRODLO_Z_ADRESU, (podana,))

    if not _ma_klucz(rozbicie):
        return Wynik()

    kandydaci = _kandydaci(szukaj(rozbicie.klucz_ulica_nr))
    if not kandydaci:
        # "Nie mam wpisu" to nie to samo, co "mam kilka" - `do_wyboru`
        # z pustą listą byłoby dla człowieka wyborem z niczego.
        return Wynik()

    # Kolejność alfabetyczna, bo SELECT bez ORDER BY nie gwarantuje
    # żadnej, a lista wariantów ma być stabilna między odświeżeniami.
    miejscowosci = tuple(sorted({k.miejscowosc for k in kandydaci}))

    # Reguła 1.
    if len(miejscowosci) == 1:
        return Wynik(miejscowosci[0], ZRODLO_JEDNOZNACZNY, miejscowosci)

    # Reguła 2. Sama gmina Warszawa nie wystarczy - wpisujemy nazwę
    # MIEJSCOWOŚCI, więc przy dwóch pasujących dzielnicach wybór jednej
    # z nich byłby losowaniem.
    warszawskie = tuple(m for m in miejscowosci if _czy_gmina_warszawa(m))
    if len(warszawskie) == 1:
        return Wynik(warszawskie[0], ZRODLO_WARSZAWA, miejscowosci)

    # Reguła 3.
    zawezone = _zawez_rejonem(kandydaci, miejscowosci, rejon)
    if zawezone and len(zawezone) == 1 and czy_rejon_warszawski(rejon):
        return Wynik(zawezone[0], ZRODLO_REJON, miejscowosci, zawezone)

    # Reguła 4 - świadomie na `miejscowosci`, nie na `zawezone`; patrz
    # akapit o granicy w docstringu modułu.
    z_dnia = _wskazanie_dnia(miejscowosci, miejscowosci_dnia)
    if z_dnia:
        return Wynik(z_dnia, ZRODLO_DZIEN_KURIERA, miejscowosci, zawezone)

    # Reguła 5.
    return Wynik(None, ZRODLO_DO_WYBORU, miejscowosci, zawezone)


def _ma_klucz(rozbicie) -> bool:
    """
    Bez ulicy albo bez numeru nie ma czego szukać - `klucz_ulica_nr`
    zbudowałby się wtedy z pustych członów i pasowałby do przypadkowych
    wierszy migawki. `getattr` zamiast `isinstance`, bo moduł nie ma
    powodu wymagać konkretnej klasy, a i tak nie wolno mu rzucić.
    """
    return bool(_tekst(getattr(rozbicie, "ulica", None))
                and _tekst(getattr(rozbicie, "nr_budynku", None))
                and _tekst(getattr(rozbicie, "klucz_ulica_nr", None)))


def _kandydaci(wiersze) -> list:
    """
    Wiersze z rejonarza -> lista `Kandydat`. Wiersz nierozpoznany albo
    bez miejscowości jest POMIJANY, nie zgłaszany wyjątkiem: pusta
    miejscowość niczego nie identyfikuje, a jeden śmieć w migawce nie może
    unieważnić pozostałych kandydatów tego adresu.
    """
    wynik = []
    for wiersz in wiersze or ():
        kandydat = _do_kandydata(wiersz)
        if kandydat is not None:
            wynik.append(kandydat)
    return wynik


def _do_kandydata(wiersz):
    if isinstance(wiersz, Kandydat):
        return wiersz if _tekst(wiersz.miejscowosc) else None

    # Kształt produkcyjny: `sqlite3.Row`/dict z zapytania po nazwach
    # kolumn. `Row` nie jest `Mapping`, więc rozpoznajemy go po `keys()`;
    # brakująca kolumna to u niego `IndexError`, u dicta `KeyError`.
    if hasattr(wiersz, "keys"):
        try:
            miejscowosc = _tekst(wiersz["miejscowosc"])
        except (KeyError, IndexError, TypeError):
            return None
        try:
            rejon = _tekst(wiersz["rejon"])
        except (KeyError, IndexError, TypeError):
            rejon = ""
        return Kandydat(miejscowosc, rejon or None) if miejscowosc else None

    # Kształt skrótowy `(miejscowosc, rejon)`. Napis odrzucamy jawnie,
    # bo rozpakowałby się na dwa znaki i udał poprawny wiersz.
    if isinstance(wiersz, (str, bytes)):
        return None
    try:
        miejscowosc, rejon = wiersz
    except (TypeError, ValueError):
        return None
    miejscowosc = _tekst(miejscowosc)
    return Kandydat(miejscowosc, _tekst(rejon) or None) if miejscowosc else None


def _zawez_rejonem(kandydaci, miejscowosci, rejon) -> tuple:
    """
    Podzbiór miejscowości, pod którymi migawka zna podany rejon.

    Zwraca `()`, gdy zawężenie nic nie wnosi: brak rejonu, rejon
    nieznany (`???`), rejon nieobecny pod tym adresem albo zawężenie do
    całej listy. Rejon, którego pod tym adresem nie ma, jest szczególnie
    ważny - wycięcie WSZYSTKICH kandydatów zostawiłoby człowieka z pustą
    listą, czyli w gorszym miejscu niż przed regułą.
    """
    kod = _tekst(rejon).upper()
    if not kod or normalizacja.normalizuj_rejon(kod) == normalizacja.REJON_NIEZNANY:
        return ()
    pasujace = tuple(sorted({
        k.miejscowosc for k in kandydaci if _tekst(k.rejon).upper() == kod}))
    return pasujace if 0 < len(pasujace) < len(miejscowosci) else ()


def _wskazanie_dnia(miejscowosci, miejscowosci_dnia):
    """
    Reguła 4. 86% par (kurier, dzień) mieści się w jednej gminie, 9%
    w dwóch - więc dzień jest przesłanką TYLKO wtedy, gdy wskazuje jedną
    gminę i gdy ta gmina trafia w dokładnie jednego kandydata. Dwie gminy
    w dniu to nie jest słabszy sygnał, tylko żaden.
    """
    gminy = {_klucz_gminy(m) for m in miejscowosci_dnia or () if _tekst(m)}
    gminy.discard("")
    if len(gminy) != 1:
        return None
    szukana = gminy.pop()
    pasujace = [m for m in miejscowosci if _klucz_gminy(m) == szukana]
    return pasujace[0] if len(pasujace) == 1 else None


def _czy_gmina_warszawa(miejscowosc) -> bool:
    return _klucz_gminy(miejscowosc) == normalizacja.klucz_rozmyty(GMINA_WARSZAWA)


def _klucz_gminy(miejscowosc) -> str:
    """Porównania gmin idą po kluczu rozmytym - migawka i nasze dane
    bywają zapisane różną wielkością liter, a to nie jest różnica gmin."""
    return normalizacja.klucz_rozmyty(gmina(miejscowosc))


def _tekst(wartosc) -> str:
    """Cokolwiek -> przycięty napis. `None` i typy nietekstowe nie mogą
    tu rzucić, bo wejściem bywa surowa komórka arkusza."""
    if wartosc is None:
        return ""
    if not isinstance(wartosc, str):
        wartosc = str(wartosc)
    return wartosc.strip()
