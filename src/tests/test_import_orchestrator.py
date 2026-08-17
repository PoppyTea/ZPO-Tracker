"""
Testy orkiestracji importu: walidacja partii, wykrywanie literówek kuriera
w partii, zapis z rozdzieleniem na "ciche" i "wymagające uwagi" (ekran
korekty pokazuje wyłącznie drugie, patrz plan MVP). TDD.

Surowe wiersze używają dokładnych nagłówków xlsx (jak w test_importer.py) -
zwaliduj_wiersze operuje na tym samym formacie co istniejący import_row.
"""
from datetime import date

import pytest

from zpo_tracker import repo
from zpo_tracker.import_orchestrator import (
    zwaliduj_wiersze,
    znajdz_propozycje_scalenia_kurierow,
    znajdz_ostrzezenia_podobienstwa_kurierow,
    zaimportuj,
)


@pytest.fixture
def conn():
    conn = repo.polacz(":memory:")
    repo.utworz_schemat(conn)
    yield conn
    conn.close()


def _surowy(**nadpisz):
    dane = {
        "data": date(2026, 8, 3),
        " Pełna Nazwa Nadawcy": "Żabka",
        "Adres odbioru dla wszystkich nadawców": "Odkryta 24",
        "Kurier": "Kowalski Jan",
        "Rejon": "WA87",
        " Wpisujemy łączną liczbę odebranych Pocztexów": 3,
        "PNI ZPO": "228648",
    }
    dane.update(nadpisz)
    return dane


# --- zwaliduj_wiersze ---

def test_zwaliduj_wiersze_poprawny_wiersz():
    zwalidowane, odrzucone = zwaliduj_wiersze([_surowy()])
    assert len(zwalidowane) == 1
    assert odrzucone == []
    assert zwalidowane[0].kurier == "Kowalski Jan"


def test_zwaliduj_wiersze_pomija_bez_zglaszania_pusty_wiersz_szablonu():
    # realny przypadek z pliku: wiersz bez daty/kuriera to szablon, nie błąd
    zwalidowane, odrzucone = zwaliduj_wiersze([_surowy(data=None, Kurier=None)])
    assert zwalidowane == []
    assert odrzucone == []


def test_zwaliduj_wiersze_zglasza_brak_ilosci_jako_odrzucone():
    zwalidowane, odrzucone = zwaliduj_wiersze(
        [_surowy(**{" Wpisujemy łączną liczbę odebranych Pocztexów": None})]
    )
    assert zwalidowane == []
    assert len(odrzucone) == 1
    assert odrzucone[0]["wiersz"]["Kurier"] == "Kowalski Jan"


# --- znajdz_propozycje_scalenia_kurierow ---

def test_znajdz_propozycje_wykrywa_literowke():
    zwalidowane, _ = zwaliduj_wiersze([
        _surowy(Kurier="Kowalski Jan"),
        _surowy(Kurier="Kowalski Jan"),
        _surowy(Kurier="Kowalksi Jan"),  # literówka, mniej częsta
    ])
    propozycje = znajdz_propozycje_scalenia_kurierow(zwalidowane)
    assert len(propozycje) == 1
    assert propozycje[0]["z"] == "Kowalksi Jan"
    assert propozycje[0]["na"] == "Kowalski Jan"  # kanoniczna = liczniejsza


def test_znajdz_propozycje_nie_zglasza_roznych_nazwisk():
    zwalidowane, _ = zwaliduj_wiersze([_surowy(Kurier="Kowalski Jan"), _surowy(Kurier="Nowak Piotr")])
    assert znajdz_propozycje_scalenia_kurierow(zwalidowane) == []


# --- znajdz_ostrzezenia_podobienstwa_kurierow: NIGDY automatyczne scalanie ---

def test_znajdz_ostrzezenia_podobienstwa_wykrywa_roznice_diakrytykow():
    # przypadek "Wołczuk Rafal"/"Wołczuk Rafał" z docs/domain-model.md -
    # to decyzja człowieka, nie automat
    zwalidowane, _ = zwaliduj_wiersze([
        _surowy(Kurier="Wołczuk Rafał"), _surowy(Kurier="Wołczuk Rafal"),
    ])
    ostrzezenia = znajdz_ostrzezenia_podobienstwa_kurierow(zwalidowane)
    assert len(ostrzezenia) == 1
    # ten przypadek nie może się pojawić jako propozycja automatycznego scalenia
    assert znajdz_propozycje_scalenia_kurierow(zwalidowane) == []


# --- zaimportuj ---

def test_zaimportuj_zapisuje_wszystkie_poprawne_wiersze(conn):
    zwalidowane, _ = zwaliduj_wiersze([
        _surowy(),
        _surowy(**{"Adres odbioru dla wszystkich nadawców": "Inny adres", "PNI ZPO": "999",
                   " Wpisujemy łączną liczbę odebranych Pocztexów": 1}),
    ])
    wynik = zaimportuj(conn, zwalidowane)
    assert wynik["zaimportowano"] == 2
    assert wynik["wymagajace_uwagi"] == []


def test_zaimportuj_stosuje_zaakceptowane_scalenie(conn):
    zwalidowane, _ = zwaliduj_wiersze([_surowy(Kurier="Kowalksi Jan")])
    zaimportuj(conn, zwalidowane, mapowanie_scalen={"Kowalksi Jan": "Kowalski Jan"})
    nazwiska = [r[0] for r in conn.execute("SELECT imie_nazwisko FROM kurierzy").fetchall()]
    assert nazwiska == ["Kowalski Jan"]


def test_zaimportuj_flaguje_duplikat_jako_wymagajacy_uwagi(conn):
    zwalidowane, _ = zwaliduj_wiersze([_surowy(), _surowy()])  # identyczny wiersz dwa razy
    wynik = zaimportuj(conn, zwalidowane)
    assert wynik["zaimportowano"] == 1
    assert len(wynik["wymagajace_uwagi"]) == 1
    assert "duplikat" in wynik["wymagajace_uwagi"][0]["powod"].lower()


def test_zaimportuj_scala_automatycznie_warianty_bialych_znakow(conn):
    # bezpieczne, automatyczne scalanie (tier 1 normalizacji) - musi
    # dziać się realnie przy zapisie, nie tylko przy wykrywaniu literówek
    zwalidowane, _ = zwaliduj_wiersze([
        _surowy(Kurier="Michalak Maciej"),
        _surowy(Kurier="Michalak Maciej ", data=date(2026, 8, 4)),
    ])
    zaimportuj(conn, zwalidowane)
    nazwiska = [r[0] for r in conn.execute("SELECT imie_nazwisko FROM kurierzy").fetchall()]
    assert nazwiska == ["Michalak Maciej"]


def test_zaimportuj_flaguje_konflikt_pni_adres_jako_wymagajacy_uwagi(conn):
    # konflikt PNI/adres dotyczy WYŁĄCZNIE ścieżki zaufanej - w niezaufanej
    # PNI w ogóle nie wchodzi do bazy, więc nie ma czemu kolidować
    # (0.1-alpha.3.2, patrz test_zaufanie_importu.py)
    zwalidowane, _ = zwaliduj_wiersze([
        _surowy(**{"Adres odbioru dla wszystkich nadawców": "Odkryta 24"}),
        _surowy(**{"Adres odbioru dla wszystkich nadawców": "Odkryta 82B", "data": date(2026, 8, 4)}),
    ])
    wynik = zaimportuj(conn, zwalidowane, zaufany=True)
    assert wynik["zaimportowano"] == 2  # obie transakcje wchodzą, PNI tylko ostrzega
    assert len(wynik["wymagajace_uwagi"]) == 1
    assert "228648" in wynik["wymagajace_uwagi"][0]["powod"]


# --- 0.1-alpha.3.2: sesja_uuid, zrodlo, i atrybucja dołożona do importu ---

def test_zaimportuj_zapisuje_zrodlo_domyslnie_import(conn):
    zwalidowane, _ = zwaliduj_wiersze([_surowy()])
    zaimportuj(conn, zwalidowane)
    wiersz = conn.execute("SELECT zrodlo, sesja_uuid FROM transakcje").fetchone()
    assert wiersz["zrodlo"] == "import"
    assert wiersz["sesja_uuid"] is None


def test_zaimportuj_zapisuje_podana_sesje_a_zrodlo_wynika_z_zaufania(conn):
    # `zrodlo` NIE jest wolnym parametrem - wyprowadza się z `zaufany`, żeby
    # nie dało się zapisać "import_zaufany" dla pliku, któremu nie ufamy
    zwalidowane, _ = zwaliduj_wiersze([_surowy()])
    zaimportuj(conn, zwalidowane, sesja_uuid="sesja-xyz", zaufany=True)
    wiersz = conn.execute("SELECT zrodlo, sesja_uuid FROM transakcje").fetchone()
    assert wiersz["zrodlo"] == "import_zaufany"
    assert wiersz["sesja_uuid"] == "sesja-xyz"


def test_zaimportuj_zapisuje_atrybucje_i_znaczniki_czasu(conn):
    # dotąd import nie pisał uuid/utworzono/autor_id w ogóle - wiersze
    # z importu były "drugiej kategorii" względem formularza
    conn.execute(
        "INSERT INTO users (id, login, alias) VALUES ('uid-1', 'POCZTA\\jnowak', 'Jan Nowak')")
    zwalidowane, _ = zwaliduj_wiersze([_surowy()])
    zaimportuj(conn, zwalidowane, autor_id="uid-1", teraz="2026-08-13T10:00:00")
    wiersz = conn.execute(
        "SELECT uuid, autor_id, utworzono, zmodyfikowano FROM transakcje").fetchone()
    assert wiersz["uuid"] is not None
    assert wiersz["autor_id"] == "uid-1"
    assert wiersz["utworzono"] == "2026-08-13T10:00:00"
    assert wiersz["zmodyfikowano"] == "2026-08-13T10:00:00"
