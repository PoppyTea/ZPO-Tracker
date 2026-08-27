"""
Przepuszczenie rejonarza przez cały łańcuch importu aż do `adresy`.

Kaskada dedukcji miejscowości jest podpięta do `get_or_create_adres`, ale
to nie wystarcza: `import_orchestrator.zaimportuj` wołało ją bez migawki,
więc na żywo zachowywała się tak, jakby jej nie było. Ten plik pilnuje
łańcucha, nie samej kaskady - ta ma własne testy.

Najważniejsze jest tu `miejscowosci_dnia`: reguła 4 kaskady opiera się na
tym, że kurier w ciągu jednego dnia nie krąży po całym WER-ze (zmierzone:
86% par (kurier, dzień) mieści się w jednej gminie). Żeby mogła z tego
skorzystać, import musi ZBIERAĆ miejscowości ustalone dla wcześniejszych
wierszy tej samej pary i podawać je kolejnym. Bez tego reguła 4 nigdy nie
dostaje wejścia i jest martwym kodem.
"""
import pytest

from zpo_tracker import dedukcja_miejscowosci, rejonarz, repo
from zpo_tracker.import_orchestrator import (
    MAPA_NAGLOWKOW, zaimportuj, zwaliduj_wiersze)


@pytest.fixture
def conn():
    c = repo.polacz(":memory:")
    repo.utworz_schemat(c)
    yield c
    c.close()


@pytest.fixture
def migawka():
    c = rejonarz.polacz(":memory:")
    yield c
    c.close()


def _wstaw(conn_rej, miejscowosc, ulica, nr, rejon):
    conn_rej.execute(
        """INSERT INTO adresy_rejony
           (klucz, klucz_ulica_nr, miejscowosc, ulica, nr, rejon)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (rejonarz.klucz_adresu(miejscowosc, ulica, nr),
         rejonarz.klucz_ulica_nr(ulica, nr), miejscowosc, ulica, nr, rejon),
    )


# `zwaliduj_wiersze` przyjmuje wiersz w postaci SUROWEJ - z nagłówkami
# dokładnie takimi, jak w pliku źródłowym (razem z ich białymi znakami,
# które są częścią danych, nie literówką). Budujemy go przez odwrócenie
# `MAPA_NAGLOWKOW` zamiast przepisywać te nagłówki tutaj: przepisane
# rozjechałyby się po cichu przy pierwszej zmianie mapy, a test nadal
# przechodziłby - tyle że sprawdzając zupełnie inną ścieżkę.
_POLE_NA_NAGLOWEK = {pole: naglowek for naglowek, pole in MAPA_NAGLOWKOW.items()}


def _wiersz(adres, kurier="Kowalski Jan", data="2026-06-01", rejon=None):
    pola = {"data": data, "nadawca": "Sklep", "adres": adres, "kurier": kurier,
            "rejon": rejon, "ilosc_total": 1, "pni_zpo": None}
    return {_POLE_NA_NAGLOWEK[k]: v for k, v in pola.items()}


def _miejscowosc_adresu(conn, surowy):
    return conn.execute(
        """SELECT m.nazwa FROM adresy a
           JOIN ulice u ON u.id = a.ulica_id
           JOIN miejscowosci m ON m.id = u.miejscowosc_id
           WHERE a.surowy = ?""", (surowy,)).fetchone()


# --- fabryka `szukaj` ---------------------------------------------------

def test_szukaj_oddaje_kandydatow_z_migawki(migawka):
    _wstaw(migawka, "Ząbki - Ząbki", "Kwiatowa", "8", "Z1")
    szukaj = rejonarz.zbuduj_szukaj(migawka)

    kandydaci = list(szukaj(rejonarz.klucz_ulica_nr("Kwiatowa", "8")))
    assert kandydaci == [("Ząbki - Ząbki", "Z1")]


def test_szukaj_na_pustej_migawce_nie_rzuca(migawka):
    assert list(rejonarz.zbuduj_szukaj(migawka)("cokolwiek|1")) == []


# --- łańcuch importu ----------------------------------------------------

def test_import_bez_migawki_nie_domysla_miejscowosci(conn):
    """Kontrakt zgodności wstecznej dla stacji bez `rejonarz.db`."""
    zwalidowane, _ = zwaliduj_wiersze([_wiersz("Kwiatowa 8")])
    zaimportuj(conn, zwalidowane)
    assert _miejscowosc_adresu(conn, "Kwiatowa 8") is None


def test_import_z_migawka_domysla_miejscowosc(conn, migawka):
    _wstaw(migawka, "Ząbki - Ząbki", "Kwiatowa", "8", "Z1")
    zwalidowane, _ = zwaliduj_wiersze([_wiersz("Kwiatowa 8")])

    zaimportuj(conn, zwalidowane, szukaj=rejonarz.zbuduj_szukaj(migawka))

    assert _miejscowosc_adresu(conn, "Kwiatowa 8")[0] == "Ząbki - Ząbki"


# --- reguła 4: dzień kuriera, czyli po co w ogóle zbierać kontekst ------

def test_wczesniejszy_wiersz_tego_dnia_rozstrzyga_pozniejszy(conn, migawka):
    """SEDNO tego pliku. Drugi adres jest sam w sobie dwuznaczny -
    ta sama ulica i numer istnieją w dwóch gminach. Rozstrzyga go dopiero
    to, że ten sam kurier tego samego dnia był już pod adresem
    jednoznacznie wskazującym jedną z nich."""
    _wstaw(migawka, "Marki - Marki", "Kwiatowa", "8", "M1")     # jednoznaczny
    _wstaw(migawka, "Marki - Marki", "Polna", "3", "M1")        # dwuznaczny...
    _wstaw(migawka, "Ząbki - Ząbki", "Polna", "3", "Z1")        # ...w dwóch gminach

    zwalidowane, _ = zwaliduj_wiersze([
        _wiersz("Kwiatowa 8"),
        _wiersz("Polna 3"),
    ])
    zaimportuj(conn, zwalidowane, szukaj=rejonarz.zbuduj_szukaj(migawka))

    assert _miejscowosc_adresu(conn, "Polna 3")[0] == "Marki - Marki"
    zrodlo = conn.execute(
        "SELECT zrodlo_miejscowosci FROM adresy WHERE surowy = 'Polna 3'"
    ).fetchone()[0]
    assert zrodlo == dedukcja_miejscowosci.ZRODLO_DZIEN_KURIERA


def test_kontekst_nie_przecieka_miedzy_kurierami(conn, migawka):
    """Kontekst dnia jest wspólny dla pary (kurier, data), nie dla całej
    partii importu. Zlanie ich dałoby regule 4 przesłanki z tras, których
    ten kurier tego dnia nie jechał - czyli zgadywanie udające pomiar."""
    _wstaw(migawka, "Marki - Marki", "Kwiatowa", "8", "M1")
    _wstaw(migawka, "Marki - Marki", "Polna", "3", "M1")
    _wstaw(migawka, "Ząbki - Ząbki", "Polna", "3", "Z1")

    zwalidowane, _ = zwaliduj_wiersze([
        _wiersz("Kwiatowa 8", kurier="Kowalski Jan"),
        _wiersz("Polna 3", kurier="Nowak Anna"),
    ])
    zaimportuj(conn, zwalidowane, szukaj=rejonarz.zbuduj_szukaj(migawka))

    assert _miejscowosc_adresu(conn, "Polna 3") is None


def test_kontekst_nie_przecieka_miedzy_dniami(conn, migawka):
    _wstaw(migawka, "Marki - Marki", "Kwiatowa", "8", "M1")
    _wstaw(migawka, "Marki - Marki", "Polna", "3", "M1")
    _wstaw(migawka, "Ząbki - Ząbki", "Polna", "3", "Z1")

    zwalidowane, _ = zwaliduj_wiersze([
        _wiersz("Kwiatowa 8", data="2026-06-01"),
        _wiersz("Polna 3", data="2026-06-02"),
    ])
    zaimportuj(conn, zwalidowane, szukaj=rejonarz.zbuduj_szukaj(migawka))

    assert _miejscowosc_adresu(conn, "Polna 3") is None


# --- rejon z wiersza --------------------------------------------------

def test_rejon_z_wiersza_zawezaja_kandydatow(conn, migawka):
    """Rejon warszawski mieści się w jednej gminie w 120/121 przypadków,
    więc wolno mu rozstrzygnąć - ale musi najpierw dojechać z wiersza
    importu do kaskady."""
    _wstaw(migawka, "Warszawa (Wola) - Warszawa", "Kwiatowa", "8", "WA1")
    _wstaw(migawka, "Warszawa (Ochota) - Warszawa", "Kwiatowa", "8", "WA2")

    zwalidowane, _ = zwaliduj_wiersze([_wiersz("Kwiatowa 8", rejon="WA2")])
    zaimportuj(conn, zwalidowane, zaufany=True,
               szukaj=rejonarz.zbuduj_szukaj(migawka))

    assert _miejscowosc_adresu(conn, "Kwiatowa 8")[0] == "Warszawa (Ochota) - Warszawa"


def test_rejon_z_pliku_NIEZAUFANEGO_nie_wplywa_na_miejscowosc(conn, migawka):
    """Druga strona tej samej granicy, co `rejon_id` w transakcji: rejon
    z papieru bywa zakłamany, więc plik niezaufany go nie wnosi. Tutaj
    stawka jest wyższa niż przy samej transakcji - zły rejon wybrałby
    miejscowość, która trafi do SŁOWNIKA i pod którą podepną się kolejne
    adresy. Ten sam wiersz co wyżej, jedyna różnica to brak zaufania."""
    _wstaw(migawka, "Warszawa (Wola) - Warszawa", "Kwiatowa", "8", "WA1")
    _wstaw(migawka, "Warszawa (Ochota) - Warszawa", "Kwiatowa", "8", "WA2")

    zwalidowane, _ = zwaliduj_wiersze([_wiersz("Kwiatowa 8", rejon="WA2")])
    zaimportuj(conn, zwalidowane, szukaj=rejonarz.zbuduj_szukaj(migawka))

    assert _miejscowosc_adresu(conn, "Kwiatowa 8") is None
