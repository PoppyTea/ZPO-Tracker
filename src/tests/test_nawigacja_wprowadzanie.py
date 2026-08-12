"""
Nawigacja formularza wprowadzania (Tab/Enter/Shift-Tab, 0.1-alpha.3.1):
kolejność liczona z dedukcja.kolejnosc_pol, NIE z naturalnego porządku
widgetów w gridzie - pole niejednoznaczne może aktywować się "za" polem,
na którym użytkownik już jest (np. rejon w kolumnie 0, adres w kolumnie
2), więc naturalny Tab by go nigdy nie znalazł. Testowane bezgłowo
(focus_get, jedno event_generate jako dowód end-to-end) - wymaga
środowiska graficznego, pomijane automatycznie (patrz test_gui_smoke.py,
ten sam mechanizm).
"""
import subprocess
import sys
import tkinter as tk
from datetime import date

import pytest

from zpo_tracker import repo
from zpo_tracker.gui.zakladka_wprowadzanie import ZakladkaWprowadzanie
from zpo_tracker.models import Blankiet, WierszBlankietu


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
    c = repo.polacz(":memory:")
    repo.utworz_schemat(c)
    yield c
    c.close()


@pytest.fixture
def zakladka(root, conn, tmp_path):
    z = ZakladkaWprowadzanie(root, conn, str(tmp_path))
    z.pack()
    root.update()
    return z


def test_kolejnosc_poczatkowa_pomija_puste_pola_dedukowane(zakladka, root):
    # dwa puste wiersze na starcie: rejon/nadawca/pni/ilosc_zpo są szare i
    # nieaktywne (adres pusty), więc Tab musi je pominąć - tylko
    # kurier/data/adres/ilosc_total są w kolejności
    zakladka._idz_dalej_naglowek("kurier")
    assert root.focus_get() is zakladka.pole_data.widget_pola

    zakladka._idz_dalej_naglowek("data")
    assert root.focus_get() is zakladka.wiersze[0].widget_pola("adres")

    zakladka._idz_dalej_wiersz(zakladka.wiersze[0], "adres")
    assert root.focus_get() is zakladka.wiersze[0].widget_pola("ilosc_total")

    zakladka._idz_dalej_wiersz(zakladka.wiersze[0], "ilosc_total")
    assert root.focus_get() is zakladka.wiersze[1].widget_pola("adres")

    zakladka._idz_dalej_wiersz(zakladka.wiersze[1], "adres")
    assert root.focus_get() is zakladka.wiersze[1].widget_pola("ilosc_total")

    zakladka._idz_dalej_wiersz(zakladka.wiersze[1], "ilosc_total")  # zawija
    assert root.focus_get() is zakladka.pole_kurier.widget_pola.entry


def test_shift_tab_cofa(zakladka, root):
    zakladka._idz_wstecz_naglowek("data")
    assert root.focus_get() is zakladka.pole_kurier.widget_pola.entry


def test_pole_niejednoznaczne_wchodzi_do_kolejnosci_i_jest_osiagalne(zakladka, root):
    # dwóch nadawców pod tym samym adresem -> nadawca pomarańczowy,
    # aktywny, w_nawigacji=True - MUSI wejść do kolejności między adresem
    # a ilością, inaczej nie da się go wypełnić z klawiatury (dokładnie
    # ten defekt złapał przegląd poprzedniej wersji planu)
    repo.zapisz_blankiet(zakladka.conn, Blankiet(
        kurier="Kowalski Jan", data=date(2026, 8, 10),
        wiersze=[WierszBlankietu(nadawca="Żabka", adres="Odkryta 24", ilosc_total=1)],
    ))
    repo.zapisz_blankiet(zakladka.conn, Blankiet(
        kurier="Kowalski Jan", data=date(2026, 8, 11),
        wiersze=[WierszBlankietu(nadawca="Gemartis", adres="Odkryta 24", ilosc_total=1)],
    ))

    wiersz = zakladka.wiersze[0]
    wiersz.var_adres.set("Odkryta 24")
    root.update()

    assert wiersz.ostatni_wynik.pola["nadawca"].stan == "pomaranczowy"
    assert ("wiersz", 0, "nadawca") in zakladka._kolejnosc

    zakladka._idz_dalej_wiersz(wiersz, "adres")
    assert root.focus_get() is wiersz.widget_pola("nadawca")


def test_pole_jednoznacznie_dedukowane_pomijane(zakladka, root):
    repo.zapisz_blankiet(zakladka.conn, Blankiet(
        kurier="Kowalski Jan", data=date(2026, 8, 10),
        wiersze=[WierszBlankietu(nadawca="Żabka", adres="Odkryta 24", rejon="WA87", ilosc_total=1)],
    ))

    wiersz = zakladka.wiersze[0]
    wiersz.var_adres.set("Odkryta 24")
    root.update()

    assert wiersz.ostatni_wynik.pola["nadawca"].stan == "zielony"
    assert ("wiersz", 0, "nadawca") not in zakladka._kolejnosc
    assert ("wiersz", 0, "rejon") not in zakladka._kolejnosc

    zakladka._idz_dalej_wiersz(wiersz, "adres")
    assert root.focus_get() is wiersz.widget_pola("ilosc_total")


def test_nastepne_pole_dostaje_podswietlenie_po_fokusie(zakladka, root):
    zakladka.pole_kurier.widget_pola.entry.focus_set()
    root.update()
    assert zakladka._klucz_podswietlony == ("naglowek", "data")
    assert zakladka.pole_data._nastepne is True


def test_event_generate_tab_dziala_end_to_end(zakladka, root):
    # dowód, że rzeczywiste wiązanie <Tab> (nie tylko wewnętrzna metoda
    # _skocz) faktycznie przenosi fokus - patrz plan, sekcja Weryfikacja
    root.deiconify()
    zakladka.pole_kurier.widget_pola.entry.focus_set()
    root.update()
    zakladka.pole_kurier.widget_pola.entry.event_generate("<Tab>")
    root.update()
    assert root.focus_get() is zakladka.pole_data.widget_pola


def test_event_generate_return_rowna_sie_tab(zakladka, root):
    zakladka.pole_data.widget_pola.focus_set()
    root.update()
    zakladka.pole_data.widget_pola.event_generate("<Return>")
    root.update()
    assert root.focus_get() is zakladka.wiersze[0].widget_pola("adres")
