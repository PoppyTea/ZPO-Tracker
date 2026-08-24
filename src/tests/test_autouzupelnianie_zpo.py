"""
Autouzupełnianie „w tym ZPO" z „Ilości" — AID-119, zgłoszone z testów
na żywo build'a v0.1.0-alpha.4.1.

Mechanizm istniał od 0.1-alpha.3.1 i był CAŁKOWICIE nieprzetestowany.
Błąd: po pierwszym skopiowaniu wartości kolejne zmiany „Ilości" nie
aktualizowały już „w tym ZPO", bo strażnik chroniący ręczne wpisy
rozpoznawał je po PUSTOŚCI pola docelowego — a to przestaje być prawdą
w chwili, gdy autouzupełnienie zadziała pierwszy raz.

Kluczowe napięcie, które te testy trzymają z obu stron: wyrównanie ma
nadążać za każdą zmianą „Ilości", ale NIE WOLNO mu skasować liczby,
którą człowiek wpisał świadomie. Scenariusz „10 przesyłek, z czego 7 to
ZPO" jest realny i częsty, a pole jest edytowalne i w nawigacji Tab.

Wymaga środowiska graficznego - pomijany tak samo jak reszta testów GUI.
"""
import subprocess
import sys
import tkinter as tk

import pytest

from zpo_tracker import repo
from zpo_tracker.gui.zakladka_wprowadzanie import ZakladkaWprowadzanie


def _ma_display():
    try:
        wynik = subprocess.run(
            [sys.executable, "-c",
             "import tkinter as tk; r = tk.Tk(); tk.Entry(r).pack(); r.update(); r.destroy()"],
            capture_output=True, timeout=10,
        )
        return wynik.returncode == 0
    except Exception:
        return False


pytestmark = pytest.mark.skipif(
    not _ma_display(), reason="wymaga środowiska graficznego (DISPLAY)"
)


@pytest.fixture
def root():
    r = tk.Tk()
    yield r
    r.destroy()


@pytest.fixture
def conn():
    """Baza z jednym punktem ZPO (Żabka z PNI) i jednym bez PNI (ZUS).
    PNI jest tym, co włącza pole „w tym ZPO" - patrz dedukcja.py."""
    c = repo.polacz(":memory:")
    repo.utworz_schemat(c)
    c.execute("INSERT INTO firmy_zpo (nazwa) VALUES ('Żabka')")
    c.execute(
        "INSERT INTO punkty (nadawca, adres, pni_zpo, firma_zpo_id) "
        "VALUES ('Żabka', 'Odkryta 24', '228648', 1)")
    c.execute("INSERT INTO punkty (nadawca, adres) VALUES ('ZUS', 'Marsa 56')")
    yield c
    c.close()


@pytest.fixture
def wiersz(root, conn, tmp_path):
    z = ZakladkaWprowadzanie(root, conn, str(tmp_path), sesja_uuid="sesja-testowa")
    z.pack()
    root.update()
    w = z.wiersze[0]
    w.var_adres.set("Odkryta 24")
    root.update()
    return w


def test_pole_zpo_jest_aktywne_dla_nadawcy_z_pni(wiersz):
    """Warunek wstępny reszty testów - gdyby to nie działało, wszystkie
    poniższe przechodziłyby z niewłaściwego powodu."""
    assert wiersz._ilosc_zpo_aktywne is True


# --- objaw zgłoszony przez Papavera ------------------------------------

def test_pierwsze_wpisanie_kopiuje_sie(wiersz):
    wiersz.var_ilosc_total.set("5")
    assert wiersz.var_ilosc_zpo.get() == "5"


def test_dopisanie_cyfry_aktualizuje(wiersz):
    """Krok 3 ze zgłoszenia: „albo dopiszę drugą cyfrę"."""
    wiersz.var_ilosc_total.set("5")
    wiersz.var_ilosc_total.set("58")
    assert wiersz.var_ilosc_zpo.get() == "58"


def test_poprawienie_liczby_aktualizuje(wiersz):
    """Krok 4 ze zgłoszenia: „jak ją poprawię to już nie"."""
    wiersz.var_ilosc_total.set("5")
    wiersz.var_ilosc_total.set("")
    wiersz.var_ilosc_total.set("7")
    assert wiersz.var_ilosc_zpo.get() == "7"


def test_wyczyszczenie_ilosci_czysci_takze_zpo(wiersz):
    """Wyrównanie znaczy wyrównanie - zostawienie sieroty po skasowanej
    Ilości byłoby gorsze od nieuzupełniania w ogóle."""
    wiersz.var_ilosc_total.set("5")
    wiersz.var_ilosc_total.set("")
    assert wiersz.var_ilosc_zpo.get() == ""


# --- ochrona wartości wpisanej ręcznie: druga strona napięcia ----------

def test_reczna_wartosc_przezywa_zmiane_ilosci(wiersz):
    """NAJWAŻNIEJSZY test tego pliku. Samo zdjęcie strażnika naprawiłoby
    zgłoszony objaw i jednocześnie zamieniło błąd irytujący na błąd
    niszczący dane."""
    wiersz.var_ilosc_total.set("10")
    wiersz.var_ilosc_zpo.set("7")      # człowiek: 7 z 10 to ZPO
    wiersz.var_ilosc_total.set("12")
    assert wiersz.var_ilosc_zpo.get() == "7"


def test_reczna_wartosc_przezywa_wyczyszczenie_ilosci(wiersz):
    wiersz.var_ilosc_total.set("10")
    wiersz.var_ilosc_zpo.set("7")
    wiersz.var_ilosc_total.set("")
    assert wiersz.var_ilosc_zpo.get() == "7"


def test_wyczyszczenie_recznej_wartosci_wraca_do_automatu(wiersz):
    """„Nie chcę tu własnej wartości" to sensowny gest i musi dać się
    wykonać - inaczej jedna pomyłkowa cyfra blokuje automat do końca
    życia wiersza."""
    wiersz.var_ilosc_total.set("10")
    wiersz.var_ilosc_zpo.set("7")
    wiersz.var_ilosc_zpo.set("")       # człowiek kasuje swoją wartość
    wiersz.var_ilosc_total.set("12")
    assert wiersz.var_ilosc_zpo.get() == "12"


def test_reczna_wartosc_rowna_ilosci_tez_jest_reczna(wiersz):
    """Podchwytliwy przypadek: człowiek wpisuje dokładnie tę samą liczbę,
    którą wpisałby automat. Rozpoznanie po WARTOŚCI byłoby tu ślepe -
    dlatego pochodzenie musi być śledzone, a nie zgadywane."""
    wiersz.var_ilosc_total.set("10")
    wiersz.var_ilosc_zpo.set("10")
    wiersz.var_ilosc_total.set("3")
    assert wiersz.var_ilosc_zpo.get() == "10"


# --- nadawca bez PNI ----------------------------------------------------

def test_bez_pni_pole_nieaktywne_i_bez_autouzupelniania(root, conn, tmp_path):
    z = ZakladkaWprowadzanie(root, conn, str(tmp_path), sesja_uuid="s")
    z.pack()
    root.update()
    w = z.wiersze[0]
    w.var_adres.set("Marsa 56")        # ZUS, bez PNI
    root.update()

    assert w._ilosc_zpo_aktywne is False
    w.var_ilosc_total.set("5")
    assert w.var_ilosc_zpo.get() == ""
