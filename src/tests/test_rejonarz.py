"""
rejonarz: lokalna migawka adres -> rejon z eksportu BaŚKi.

Świadomie OSOBNY plik .db, nie tabele w głównej bazie. Zbiór jest
identyczny na wszystkich stacjach, więc nie ma po co wędrować przez
scalanie baz ani powiększać każdej migawki kopii zapasowej o setki
tysięcy wierszy. Skutek uboczny: schema.sql i WERSJA_SCHEMATU głównej
bazy zostają nietknięte.

Testy budują PRAWDZIWE pliki .xlsx - w odróżnieniu od testów importu
Excela, które operują na surowych dictach. Dla rejonarza ścieżka odczytu
pliku jest częścią tego, co trzeba sprawdzić (read_only + generator).
"""
import sqlite3
import time

import openpyxl
import pytest

from zpo_tracker import normalizacja, profil_kolumn, rejonarz


NAGLOWKI = ["Miejscowość", "Ulica", "Nr", "PNA", "Węzeł", "TK", "Rejon"]


def zbuduj_xlsx(sciezka, wiersze, naglowki=None):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(naglowki if naglowki is not None else NAGLOWKI)
    for w in wiersze:
        ws.append(w)
    wb.save(sciezka)
    return sciezka


def wiersz(miejscowosc="Warszawa", ulica="Marsa", nr="56", pna="04-028",
           wezel="WW", tk="1", rejon="119"):
    return [miejscowosc, ulica, nr, pna, wezel, tk, rejon]


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    rejonarz.utworz_schemat(c)
    yield c
    c.close()


# --- schemat ------------------------------------------------------------

def test_utworzenie_schematu_ustawia_wersje(conn):
    assert rejonarz.wersja_schematu(conn) == rejonarz.WERSJA_SCHEMATU


def test_utworzenie_schematu_jest_idempotentne(conn):
    rejonarz.utworz_schemat(conn)
    assert rejonarz.wersja_schematu(conn) == rejonarz.WERSJA_SCHEMATU


def test_pusty_rejonarz_nie_jest_dostepny(conn):
    """Brak danych ma znaczyć to samo co brak pliku - dedukcja nie może
    zachowywać się inaczej dla pustej migawki niż dla żadnej."""
    assert rejonarz.czy_dostepny(conn) is False


# --- klucz adresu -------------------------------------------------------

def test_klucz_adresu_ignoruje_wielkosc_liter_i_diakrytyki():
    assert (rejonarz.klucz_adresu("Warszawa", "Żelazna", "12")
            == rejonarz.klucz_adresu("WARSZAWA", "zelazna", "12"))


def test_klucz_adresu_ignoruje_biale_znaki():
    assert (rejonarz.klucz_adresu(" Warszawa ", "Marsa  56".split()[0], "56")
            == rejonarz.klucz_adresu("Warszawa", "Marsa", " 56 "))


def test_klucz_adresu_rozroznia_numer_z_litera():
    assert rejonarz.klucz_adresu("Warszawa", "Marsa", "56") != \
           rejonarz.klucz_adresu("Warszawa", "Marsa", "56A")


def test_klucz_adresu_znosi_brak_ulicy():
    """Wsie bywają bez ulicy - sam numer budynku w miejscowości."""
    assert rejonarz.klucz_adresu("Ciemne", None, "14")


# --- import -------------------------------------------------------------

def test_importuje_poprawny_wiersz(conn, tmp_path):
    plik = zbuduj_xlsx(tmp_path / "r.xlsx", [wiersz()])
    wynik = rejonarz.zaimportuj(conn, plik)
    assert wynik.zapisane == 1
    assert rejonarz.znajdz_rejon(conn, "Warszawa", "Marsa", "56") == "WA119"


def test_import_dokleja_prefiks_przez_normalizacje(conn, tmp_path):
    plik = zbuduj_xlsx(tmp_path / "r.xlsx", [wiersz(rejon="21A")])
    rejonarz.zaimportuj(conn, plik)
    assert rejonarz.znajdz_rejon(conn, "Warszawa", "Marsa", "56") == "WA21A"


def test_pomija_wiersze_z_innego_wezla(conn, tmp_path):
    """Interesuje nas wyłącznie węzeł WW. Węzeł WA to WER Warszawa W101
    przy Łączyny - zupełnie inny byt, mimo mylącej zbieżności liter."""
    plik = zbuduj_xlsx(tmp_path / "r.xlsx", [
        wiersz(wezel="WW", nr="1"),
        wiersz(wezel="WA", nr="2"),
        wiersz(wezel="PO", nr="3"),
    ])
    wynik = rejonarz.zaimportuj(conn, plik)
    assert wynik.zapisane == 1
    assert wynik.pominiete == 2
    assert rejonarz.znajdz_rejon(conn, "Warszawa", "Marsa", "2") is None


def test_pomija_typ_kierowania_dwa(conn, tmp_path):
    plik = zbuduj_xlsx(tmp_path / "r.xlsx", [
        wiersz(tk="1", nr="1"),
        wiersz(tk="2", nr="2"),
    ])
    wynik = rejonarz.zaimportuj(conn, plik)
    assert wynik.zapisane == 1
    assert rejonarz.znajdz_rejon(conn, "Warszawa", "Marsa", "2") is None


@pytest.mark.parametrize("wartownik", ["*UP", "ZPO", "AP", "FUP", "UP"])
def test_nie_zapisuje_wartownikow_jako_rejonu(conn, tmp_path, wartownik):
    """Wartownik znaczy 'rejon nieznany'. Zapisanie go do migawki
    sprawiłoby, że dedukcja odpowiadałaby '???' zamiast milczeć -
    a to dwie różne rzeczy: 'wiem, że nie wiem' vs 'nie mam wpisu'."""
    plik = zbuduj_xlsx(tmp_path / "r.xlsx", [wiersz(rejon=wartownik)])
    wynik = rejonarz.zaimportuj(conn, plik)
    assert wynik.zapisane == 0
    assert wynik.bez_rejonu == 1
    assert rejonarz.znajdz_rejon(conn, "Warszawa", "Marsa", "56") is None


def test_import_jest_podmiana_calej_migawki(conn, tmp_path):
    """To migawka, nie dziennik przyrostowy. Drugi import zastępuje
    pierwszy w całości - inaczej wycofane adresy zostawałyby na zawsze."""
    rejonarz.zaimportuj(conn, zbuduj_xlsx(tmp_path / "a.xlsx", [wiersz(nr="1")]))
    rejonarz.zaimportuj(conn, zbuduj_xlsx(tmp_path / "b.xlsx", [wiersz(nr="2")]))
    assert rejonarz.znajdz_rejon(conn, "Warszawa", "Marsa", "1") is None
    assert rejonarz.znajdz_rejon(conn, "Warszawa", "Marsa", "2") == "WA119"
    assert rejonarz.policz(conn) == 1


def test_brak_wymaganej_kolumny_przerywa_import_bez_zapisu(conn, tmp_path):
    plik = zbuduj_xlsx(
        tmp_path / "zle.xlsx",
        [["Warszawa", "Marsa", "04-028"]],
        naglowki=["Miejscowość", "Ulica", "PNA"],
    )
    with pytest.raises(rejonarz.NiezgodnyArkusz) as e:
        rejonarz.zaimportuj(conn, plik)
    assert "nr" in str(e.value) and "rejon" in str(e.value)
    assert rejonarz.policz(conn) == 0


def test_import_znosi_przestawione_kolumny(conn, tmp_path):
    """Cała racja bytu profilu: kolejność kolumn nie ma znaczenia."""
    plik = zbuduj_xlsx(
        tmp_path / "r.xlsx",
        [["119", "56", "Marsa", "WW", "Warszawa", "1"]],
        naglowki=["Rejon", "Nr", "Ulica", "Węzeł", "Miejscowość", "TK"],
    )
    rejonarz.zaimportuj(conn, plik)
    assert rejonarz.znajdz_rejon(conn, "Warszawa", "Marsa", "56") == "WA119"


def test_import_znosi_brak_kolumn_nieobowiazkowych(conn, tmp_path):
    """Bez Węzła i TK nie da się filtrować, więc bierzemy wszystko -
    ale to musi być świadome, nie ciche."""
    plik = zbuduj_xlsx(
        tmp_path / "r.xlsx",
        [["Warszawa", "Marsa", "56", "119"]],
        naglowki=["Miejscowość", "Ulica", "Nr", "Rejon"],
    )
    wynik = rejonarz.zaimportuj(conn, plik)
    assert wynik.zapisane == 1
    assert wynik.bez_filtrowania is True


def test_pusty_arkusz_nie_wybucha(conn, tmp_path):
    plik = zbuduj_xlsx(tmp_path / "r.xlsx", [])
    wynik = rejonarz.zaimportuj(conn, plik)
    assert wynik.zapisane == 0
    assert rejonarz.czy_dostepny(conn) is False


# --- odczyt -------------------------------------------------------------

def test_znajdz_rejon_jest_odporny_na_zapis_adresu(conn, tmp_path):
    rejonarz.zaimportuj(conn, zbuduj_xlsx(
        tmp_path / "r.xlsx", [wiersz(miejscowosc="Warszawa", ulica="Żelazna", nr="12")]))
    assert rejonarz.znajdz_rejon(conn, "  warszawa ", "ZELAZNA", "12") == "WA119"


def test_znajdz_rejon_milczy_dla_nieznanego_adresu(conn, tmp_path):
    rejonarz.zaimportuj(conn, zbuduj_xlsx(tmp_path / "r.xlsx", [wiersz()]))
    assert rejonarz.znajdz_rejon(conn, "Warszawa", "Nieistniejąca", "1") is None


def test_sprzeczna_migawka_nie_zgaduje(conn, tmp_path):
    """Ten sam adres z dwoma różnymi rejonami w źródle. Wybranie
    któregokolwiek byłoby zgadywaniem - a rejonarz istnieje po to,
    żeby przestać zgadywać."""
    plik = zbuduj_xlsx(tmp_path / "r.xlsx", [
        wiersz(rejon="119"),
        wiersz(rejon="124"),
    ])
    rejonarz.zaimportuj(conn, plik)
    assert rejonarz.znajdz_rejon(conn, "Warszawa", "Marsa", "56") is None


def test_powtorzony_ten_sam_rejon_nie_jest_sprzecznoscia(conn, tmp_path):
    plik = zbuduj_xlsx(tmp_path / "r.xlsx", [wiersz(rejon="119"), wiersz(rejon="119")])
    rejonarz.zaimportuj(conn, plik)
    assert rejonarz.znajdz_rejon(conn, "Warszawa", "Marsa", "56") == "WA119"


def test_dostepny_po_udanym_imporcie(conn, tmp_path):
    rejonarz.zaimportuj(conn, zbuduj_xlsx(tmp_path / "r.xlsx", [wiersz()]))
    assert rejonarz.czy_dostepny(conn) is True


# --- skala --------------------------------------------------------------

@pytest.mark.slow
def test_import_duzego_pliku_konczy_sie_w_rozsadnym_czasie(conn, tmp_path):
    """Realny eksport ma >400 tys. wierszy. 'Działa' musi tu znaczyć też
    'kończy się' - dotąd nic w tym repo nie pracowało na takiej skali
    (zero executemany, zero read_only, cały arkusz materializowany
    do listy dictów)."""
    ile = 50_000
    wiersze = [wiersz(ulica=f"Ulica {i % 900}", nr=str(i % 300 + 1),
                      rejon=str(100 + i % 40)) for i in range(ile)]
    plik = zbuduj_xlsx(tmp_path / "duzy.xlsx", wiersze)

    start = time.monotonic()
    wynik = rejonarz.zaimportuj(conn, plik)
    czas = time.monotonic() - start

    assert wynik.wczytane == ile
    assert czas < 60, f"import {ile} wierszy zajął {czas:.1f}s"
