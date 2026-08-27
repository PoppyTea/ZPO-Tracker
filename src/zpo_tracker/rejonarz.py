"""
Lokalna migawka `adres -> rejon` z eksportu BaŚKi ("rejonarz").

**Osobny plik `.db`, nie tabele w głównej bazie.** Zbiór referencyjny jest
identyczny na wszystkich stacjach, więc nie ma po co wędrować przez
`scalanie.py` ani powiększać każdej migawki z `kopie.py` o setki tysięcy
wierszy. Skutek uboczny tej decyzji jest cenny sam w sobie: `schema.sql`
i `repo.WERSJA_SCHEMATU` zostają nietknięte, czyli integracja rejonarza
nie niesie ŻADNEGO ryzyka migracji dla danych rozliczeniowych.

Architektura uzgodniona 2026-08-19: migawka to "rampa załadunkowa"
budowana z plikowych eksportów, API DeliveryPath to "okienko pocztowe"
do weryfikacji pojedynczych adresów. Offline'owy `.exe` nigdy nie woła
API na żywo, więc ten moduł nie zna sieci.

Pierwszy kod w tym repo pracujący na realnie dużym zbiorze: odczyt idzie
generatorem przez `read_only=True`, zapis partiami przez `executemany`.
Reszta importów materializuje cały arkusz do listy dictów, co przy
>400 tys. wierszy nie przejdzie.
"""
import re
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path


from zpo_tracker import arkusze, normalizacja, profil_kolumn

WERSJA_SCHEMATU = 1
NAZWA_PLIKU = "rejonarz.db"

# Interesują nas wyłącznie rejony tego węzła i tego typu kierowania.
# UWAGA: `WW` to NIE to samo co węzeł `WA` (WER Warszawa W101 przy
# ul. Łączyny) - patrz ostrzeżenie w normalizacja.normalizuj_rejon_baska.
WEZEL_ZPO = "WW"
TYP_KIEROWANIA_ZPO = "1"

ROZMIAR_PARTII = 5_000

PROFIL = profil_kolumn.Profil(
    pola={
        "miejscowosc": ["Miejscowość", "Miasto"],
        "ulica": ["Ulica"],
        "nr": ["Nr", "Nr domu", "Numer domu"],
        # Rozpoznawany, ale NIE zapisywany - patrz `_do_zapisu`. Jest tu
        # po to, żeby kolumna lokalu nie wylądowała przypadkiem w innym
        # polu ani w "nierozpoznane".
        "lokal": ["Nr lokalu", "Lokal", "Nr mieszkania"],
        "pna": ["PNA", "Kod pocztowy"],
        "wezel": ["Węzeł", "Węzeł oddawczy", "WER"],
        "tk": ["TK", "Typ kier.", "Typ kierowania"],
        "rejon": ["Rejon", "Rejon doręczeń"],
    },
    wymagane=frozenset({"miejscowosc", "nr", "rejon"}),
)

# Ten sam profil, ale BEZ wymaganego rejonu - dla eksportu, w którym rejon
# jest nazwą arkusza, a nie kolumną. Osobna stała, nie mutacja tamtej:
# dwa kształty eksportu przychodzą z BaŚKi naprzemiennie i oba muszą dać
# się rozpoznać w tym samym przebiegu.
PROFIL_BEZ_REJONU = profil_kolumn.Profil(
    pola=PROFIL.pola,
    wymagane=frozenset({"miejscowosc", "nr"}),
)

_DDL = """
CREATE TABLE IF NOT EXISTS adresy_rejony (
    id           INTEGER PRIMARY KEY,
    klucz        TEXT NOT NULL,
    -- Drugi klucz, bez miejscowości: realne adresy w formularzu bywają
    -- zapisane bez miasta ("Odkryta 24"), a odmowa odpowiedzi dla nich
    -- wyłączyłaby rejonarz dla sporej części danych. Wyszukiwanie tym
    -- kluczem odpowiada TYLKO gdy trafienie jest jednoznaczne.
    klucz_ulica_nr TEXT NOT NULL,
    miejscowosc  TEXT NOT NULL,
    ulica        TEXT,
    nr           TEXT NOT NULL,
    pna          TEXT,
    rejon        TEXT NOT NULL,
    -- Ta sama para (adres, rejon) powtórzona w źródle to nie sprzeczność,
    -- tylko duplikat wiersza - UNIQUE zdejmuje go za darmo przy imporcie.
    -- Dwa RÓŻNE rejony pod tym samym kluczem zostają oba i dopiero
    -- `znajdz_rejon` odmawia rozstrzygnięcia.
    UNIQUE (klucz, rejon)
);
CREATE INDEX IF NOT EXISTS idx_rejonarz_klucz ON adresy_rejony(klucz);
CREATE INDEX IF NOT EXISTS idx_rejonarz_ulica_nr ON adresy_rejony(klucz_ulica_nr);
"""


class NiezgodnyArkusz(Exception):
    """Arkusz nie ma kolumn, bez których import nie miałby sensu."""


@dataclass
class WynikImportu:
    wczytane: int = 0
    zapisane: int = 0
    pominiete: int = 0        # inny węzeł albo inny typ kierowania
    bez_rejonu: int = 0       # wartownik albo śmieć w kolumnie rejonu
    bez_filtrowania: bool = False   # arkusz nie miał kolumn Węzeł/TK
    # Arkusze, z których nie dało się nic wziąć. JAWNIE, nie po cichu:
    # eksport bywa sklejany z kilku i arkusz "Podsumowanie" jest realny,
    # ale gdyby znikał bez śladu, tak samo zniknąłby arkusz z literówką
    # w nazwie rejonu - czyli realna strata danych.
    arkusze_pominiete: list = field(default_factory=list)


# --- schemat i połączenie -----------------------------------------------

def sciezka_domyslna(katalog_danych) -> Path:
    return Path(katalog_danych) / NAZWA_PLIKU


def polacz(sciezka) -> sqlite3.Connection:
    conn = sqlite3.connect(str(sciezka), isolation_level=None)
    utworz_schemat(conn)
    return conn


def utworz_schemat(conn) -> None:
    """Idempotentne - wszystkie obiekty z `IF NOT EXISTS`."""
    conn.executescript(_DDL)
    conn.execute(f"PRAGMA user_version = {WERSJA_SCHEMATU}")


def wersja_schematu(conn) -> int:
    return conn.execute("PRAGMA user_version").fetchone()[0]


def policz(conn) -> int:
    return conn.execute("SELECT COUNT(*) FROM adresy_rejony").fetchone()[0]


def czy_dostepny(conn) -> bool:
    """Pusta migawka ma znaczyć dokładnie to samo, co brak pliku -
    dedukcja nie może zachowywać się inaczej w tych dwóch przypadkach."""
    return policz(conn) > 0


# --- klucz adresu -------------------------------------------------------

def klucz_adresu(miejscowosc, ulica, nr) -> str:
    """
    Kanoniczna postać adresu do wyszukiwania: bez diakrytyków, bez
    wielkości liter, bez nadmiarowych spacji.

    Numer budynku celowo NIE jest normalizowany rozmyto - `56` i `56A`
    to dwa różne budynki, często w różnych rejonach.
    """
    czesci = [
        normalizacja.klucz_rozmyty(_tekst(miejscowosc)),
        normalizacja.klucz_rozmyty(_tekst(ulica)),
        _tekst(nr).upper().replace(" ", ""),
    ]
    return "|".join(czesci)


def klucz_ulica_nr(ulica, nr) -> str:
    """Klucz bez miejscowości - patrz komentarz przy kolumnie w schemacie."""
    return "|".join([
        normalizacja.klucz_rozmyty(_tekst(ulica)),
        _tekst(nr).upper().replace(" ", ""),
    ])


def _tekst(wartosc) -> str:
    """openpyxl oddaje liczby jako int/float, więc `56` bywa intem,
    a `119` floatem `119.0` - a my kluczujemy po tekście."""
    if wartosc is None:
        return ""
    if isinstance(wartosc, float) and wartosc.is_integer():
        return str(int(wartosc))
    return str(wartosc).strip()


# --- import -------------------------------------------------------------

def zaimportuj(conn, sciezka, rozmiar_partii=ROZMIAR_PARTII) -> WynikImportu:
    """
    Wczytuje eksport z BaŚKi i PODMIENIA całą migawkę.

    Podmiana, nie dopisanie: to jest migawka stanu, nie dziennik
    przyrostowy. Gdyby import dopisywał, adresy wycofane z BaŚKi
    zostawałyby u nas na zawsze i to właśnie one byłyby najbardziej
    mylące, bo wyglądałyby na potwierdzone.

    Obsługiwane są DWA kształty eksportu, bo oba przychodzą z BaŚKi:

    * jednoarkuszowy z kolumną `Rejon`,
    * **per-arkusz, gdzie rejon jest NAZWĄ ZAKŁADKI** a w środku stoi samo
      `Miejscowość | Ulica | Nr | PNA` (tak wygląda realny eksport
      „WW - WER Ciemne": 219 arkuszy, 277 tys. adresów).

    Kolumna ma pierwszeństwo przed nazwą arkusza. Odwrotna kolejność
    psułaby eksport jednoarkuszowy o przypadkowej nazwie („Arkusz1"),
    nadpisując poprawne dane etykietą zakładki.

    Format pliku (`.xls` / `.xlsx`) rozpoznaje `arkusze.otworz` po
    zawartości - patrz tamten moduł.
    """
    wynik = WynikImportu()
    with arkusze.otworz(sciezka) as skoroszyt:
        nazwy = skoroszyt.nazwy_arkuszy()
        with conn:
            conn.execute("BEGIN")
            conn.execute("DELETE FROM adresy_rejony")
            uzyte = 0
            for nazwa in nazwy:
                if _wczytaj_arkusz(conn, skoroszyt, nazwa, wynik, rozmiar_partii):
                    uzyte += 1
                else:
                    wynik.arkusze_pominiete.append(nazwa)
            if not uzyte:
                # Wyjątek LECI W ŚRODKU transakcji, żeby `DELETE` wyżej
                # został wycofany. Inaczej nieudany import kasowałby
                # działającą migawkę i zostawiał użytkownika z niczym.
                raise NiezgodnyArkusz(
                    "Żaden arkusz nie nadaje się do wczytania. Sprawdzone: "
                    + ", ".join(nazwy)
                    + ". Arkusz musi mieć kolumny "
                    + ", ".join(sorted(PROFIL_BEZ_REJONU.wymagane))
                    + " oraz rejon - w kolumnie `Rejon` albo w nazwie zakładki."
                )
    return wynik


def _wczytaj_arkusz(conn, skoroszyt, nazwa, wynik, rozmiar_partii) -> bool:
    """
    Wciąga jeden arkusz. `False`, gdy nie da się z niego nic wziąć.

    Zwrócenie `False` zamiast wyjątku jest celowe: jeden nieużyteczny
    arkusz nie może przewrócić importu 219 pozostałych, a jego nazwa
    i tak trafia do `WynikImportu.arkusze_pominiete`.
    """
    iterator = skoroszyt.wiersze(nazwa)
    try:
        naglowki = list(next(iterator))
    except StopIteration:
        return False                      # pusty arkusz

    dopasowanie = profil_kolumn.dopasuj_kolumny(naglowki, PROFIL)
    rejon_arkusza = None
    if not dopasowanie.kompletne:
        dopasowanie = profil_kolumn.dopasuj_kolumny(naglowki, PROFIL_BEZ_REJONU)
        if not dopasowanie.kompletne:
            iterator.close()
            return False
        rejon_arkusza = normalizacja.normalizuj_rejon_baska(nazwa)
        if rejon_arkusza == normalizacja.REJON_NIEZNANY:
            # Nazwa zakładki nie jest kodem rejonu (np. "Podsumowanie")
            # ani jest wartownikiem ("ZPO", "*UP") - nie ma czego przypisać.
            iterator.close()
            return False

    if not _umie_filtrowac(dopasowanie):
        wynik.bez_filtrowania = True

    partia = []
    for surowy in iterator:
        wiersz = profil_kolumn.wyodrebnij(dict(zip(naglowki, surowy)), dopasowanie)
        if not any(_tekst(w) for w in wiersz.values()):
            continue                      # pusty wiersz na końcu arkusza
        wynik.wczytane += 1

        if _umie_filtrowac(dopasowanie) and not _nasz_wiersz(wiersz):
            wynik.pominiete += 1
            continue

        rejon = rejon_arkusza or normalizacja.normalizuj_rejon_baska(
            _tekst(wiersz.get("rejon")))
        if rejon == normalizacja.REJON_NIEZNANY:
            # Wartownik zapisany do migawki sprawiłby, że dedukcja
            # odpowiadałaby "???" zamiast milczeć. To dwie różne rzeczy:
            # "wiem, że nie wiem" kontra "nie mam wpisu".
            wynik.bez_rejonu += 1
            continue

        partia.append(_do_zapisu(wiersz, rejon))
        if len(partia) >= rozmiar_partii:
            wynik.zapisane += _zapisz_partie(conn, partia)
            partia = []
    if partia:
        wynik.zapisane += _zapisz_partie(conn, partia)
    return True


def _umie_filtrowac(dopasowanie) -> bool:
    pola = set(dopasowanie.mapowanie.values())
    return {"wezel", "tk"} <= pola


def _nasz_wiersz(wiersz) -> bool:
    return (_tekst(wiersz.get("wezel")).upper() == WEZEL_ZPO
            and _tekst(wiersz.get("tk")) == TYP_KIEROWANIA_ZPO)


def _do_zapisu(wiersz, rejon):
    # `lokal` jest świadomie POMIJANY. Rejon jest przypisany do budynku
    # ("rejon per numer budynku"), więc lokal nie wnosi informacji, a
    # wciągnięty do klucza rozbiłby deduplikację: pięć mieszkań w jednym
    # budynku dałoby pięć wierszy mówiących dokładnie to samo.
    miejscowosc = _tekst(wiersz.get("miejscowosc"))
    ulica = _tekst(wiersz.get("ulica"))
    nr = _tekst(wiersz.get("nr"))
    return (
        klucz_adresu(miejscowosc, ulica, nr),
        klucz_ulica_nr(ulica, nr),
        miejscowosc, ulica or None, nr,
        _tekst(wiersz.get("pna")) or None,
        rejon,
    )


def _zapisz_partie(conn, partia) -> int:
    """`INSERT OR IGNORE` zdejmuje powtórzone pary (adres, rejon) bez
    osobnego przebiegu deduplikującego - UNIQUE robi to w silniku."""
    przed = policz(conn)
    conn.executemany(
        "INSERT OR IGNORE INTO adresy_rejony "
        "(klucz, klucz_ulica_nr, miejscowosc, ulica, nr, pna, rejon) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        partia,
    )
    return policz(conn) - przed


# --- odczyt -------------------------------------------------------------

def zbuduj_szukaj(conn):
    """
    Fabryka wstrzykiwanej zależności dla `dedukcja_miejscowosci.dedukuj`.

    Kaskada nie zna SQLite i nie ma go poznać - dostaje callable
    `klucz_ulica_nr -> wiersze`. Dzięki temu jej testy nie stawiają
    migawki, a to samo callable obsłuży kiedyś inne źródło (np. API),
    bez ruszania reguł.

    Pusta migawka oddaje pustą listę, czyli to samo co brak migawki -
    "zaimportowałem, ale plik był pusty" nie może zachowywać się inaczej
    niż "nie zaimportowałem".
    """
    def szukaj(klucz):
        return conn.execute(
            "SELECT miejscowosc, rejon FROM adresy_rejony WHERE klucz_ulica_nr = ?",
            (klucz,),
        ).fetchall()
    return szukaj


def znajdz_rejon(conn, miejscowosc, ulica, nr):
    """
    Rejon dla adresu albo `None`.

    `None` znaczy zarówno "nie ma takiego adresu", jak i "migawka podaje
    dla niego dwa różne rejony". Oba przypadki muszą kończyć się tak samo:
    **brakiem rozstrzygnięcia**. Wybranie jednego z dwóch sprzecznych
    byłoby zgadywaniem, a rejonarz istnieje właśnie po to, żeby przestać
    zgadywać - dane z papierowych blankietów są zakłamane i to od nich
    uciekamy.
    """
    rejony = conn.execute(
        "SELECT DISTINCT rejon FROM adresy_rejony WHERE klucz = ?",
        (klucz_adresu(miejscowosc, ulica, nr),),
    ).fetchall()
    return rejony[0][0] if len(rejony) == 1 else None


# --- most do formularza -------------------------------------------------
#
# Formularz trzyma adres jako JEDEN wolny tekst, a migawka kluczuje po
# (miejscowość, ulica, nr). Ta różnica to dokładnie odłożona normalizacja
# adresu z docs/normalization-v2.md. Do czasu jej wdrożenia rozbijamy
# tekst heurystycznie - ale konserwatywnie: przy wątpliwości NIC.

_NUMER_NA_KONCU = re.compile(r"^(?P<ulica>.*?)[\s,]+(?P<nr>\d+[A-Za-z]?(?:/\d+[A-Za-z]?)?)$")

# Jawne znaczniki lokalu. Tylko one rozstrzygają - goły ukośnik NIE, bo
# w polskim adresowaniu "12/14" bywa podwójnym numerem jednego budynku
# równie często, co budynkiem z mieszkaniem.
_LOKAL_NA_KONCU = re.compile(
    r"^(?P<reszta>.*?)[\s,]+(?:m|lok|mieszk)\.?[\s]+(?P<lokal>\d+[A-Za-z]?)$",
    re.IGNORECASE)


def rozbij_adres(adres):
    """
    Wolny tekst -> `(miejscowosc | None, ulica, budynek, lokal | None)`
    albo `None`.

    Rozpoznaje dwa układy spotykane w danych: `"Ulica 12, Miasto"` oraz
    `"Miasto, Ulica 12"` - decyduje o tym, która część kończy się numerem
    budynku. Adres bez miejscowości (`"Odkryta 24"`) jest poprawnym
    wynikiem z `miejscowosc=None`, bo takich w bazie jest sporo.

    Brak numeru budynku oznacza `None`: bez niego nie ma czego szukać,
    a zgadywanie rejonu dla samej ulicy byłoby dokładnie tym, co rejonarz
    ma wyeliminować.

    **Lokal odcinają wyłącznie jawne znaczniki** (`m.`, `lok.`, `mieszk.`).
    Goły ukośnik zostaje częścią numeru budynku, bo `"12/14"` bywa
    podwójnym numerem JEDNEGO budynku równie często, co budynkiem
    z mieszkaniem - rozstrzyga dopiero `znajdz_rejon_dla_adresu`,
    próbując obu odczytów.
    """
    if not adres or not str(adres).strip():
        return None
    czesci = [c.strip() for c in str(adres).split(",") if c.strip()]
    if not czesci:
        return None

    # Część z numerem na końcu to ulica; pozostała - miejscowość.
    for i, czesc in enumerate(czesci):
        czesc, lokal = _odetnij_lokal(czesc)
        dopasowanie = _NUMER_NA_KONCU.match(czesc)
        if dopasowanie and dopasowanie.group("ulica").strip():
            miejscowosc = ", ".join(czesci[:i] + czesci[i + 1:]).strip() or None
            return (miejscowosc,
                    dopasowanie.group("ulica").strip(),
                    dopasowanie.group("nr"),
                    lokal)
    return None


def _odetnij_lokal(czesc):
    """`("Marsa 56 m. 3")` -> `("Marsa 56", "3")`. Bez znacznika - bez zmian."""
    dopasowanie = _LOKAL_NA_KONCU.match(czesc)
    if not dopasowanie:
        return czesc, None
    return dopasowanie.group("reszta").strip(), dopasowanie.group("lokal")


def znajdz_rejon_dla_adresu(conn, adres):
    """
    Rejon dla adresu w postaci, w jakiej trzyma go formularz, albo `None`.

    Gdy adres niesie miejscowość - zwykłe wyszukiwanie po pełnym kluczu.
    Gdy jej nie ma, szukamy po samej ulicy i numerze, ale odpowiadamy
    **wyłącznie przy jednoznacznym trafieniu**: ta sama ulica i numer
    w dwóch miastach to nie jest przypadek do rozstrzygnięcia losowaniem.
    """
    rozbite = rozbij_adres(adres)
    if rozbite is None:
        return None
    miejscowosc, ulica, budynek, _lokal = rozbite

    # Dosłowny odczyt numeru ma pierwszeństwo; dopiero gdy nie ma go
    # w migawce, próbujemy odczytu "budynek/lokal" (patrz rozbij_adres).
    for kandydat in _odczyty_numeru(budynek):
        kod = (znajdz_rejon(conn, miejscowosc, ulica, kandydat) if miejscowosc
               else _po_ulicy_i_numerze(conn, ulica, kandydat))
        if kod:
            return kod
    return None


def _odczyty_numeru(budynek):
    """`"12/14"` -> `["12/14", "12"]`; bez ukośnika jeden odczyt."""
    if "/" in budynek:
        return [budynek, budynek.split("/", 1)[0]]
    return [budynek]


def _po_ulicy_i_numerze(conn, ulica, nr):
    rejony = conn.execute(
        "SELECT DISTINCT rejon FROM adresy_rejony WHERE klucz_ulica_nr = ?",
        (klucz_ulica_nr(ulica, nr),),
    ).fetchall()
    return rejony[0][0] if len(rejony) == 1 else None
