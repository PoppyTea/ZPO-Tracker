"""
Zapis z formularza wprowadzania (0.1-alpha.3.2): status kolorowy z powodami
pominięć, selektywne czyszczenie siatki (zapisane znikają, pominięte
zostają), podgląd filtrowany do bieżącej sesji, dwuklik → DialogEdycji.
Wymaga środowiska graficznego - pomijany automatycznie, jeśli niedostępne
(patrz test_gui_smoke.py, ten sam mechanizm).
"""
import subprocess
import sys
import tkinter as tk
from datetime import date

import pytest

from zpo_tracker import dziennik, repo
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
    z = ZakladkaWprowadzanie(root, conn, str(tmp_path), sesja_uuid="sesja-testowa")
    z.pack()
    root.update()
    return z


def _wypelnij_wiersz(wiersz, adres="Odkryta 24", ilosc="3"):
    wiersz.var_nadawca.set("Żabka")
    wiersz.var_adres.set(adres)
    wiersz.var_ilosc_total.set(ilosc)


# --- status: pełny sukces ---

def test_pelny_sukces_status_zielony_i_formularz_sie_czysci(zakladka, root):
    from zpo_tracker.gui.widget_pole import KOLORY

    _wypelnij_wiersz(zakladka.wiersze[0])
    zakladka.var_kurier.set("Kowalski Jan")
    root.update()

    zakladka.zapisz()

    assert str(zakladka.etykieta_status.cget("foreground")) == KOLORY["zielony"]
    assert "Zapisano 1" in zakladka.etykieta_status.cget("text")
    assert len(zakladka.wiersze) == 2  # reset do dwóch pustych
    assert zakladka.var_kurier.get() == ""


# --- status: pominięcie częściowe/całkowite ---

def test_duplikat_zostaje_w_siatce_z_czerwonym_komunikatem(zakladka, root):
    from zpo_tracker.gui.widget_pole import KOLORY

    repo.zapisz_blankiet(zakladka.conn, Blankiet(
        kurier="Kowalski Jan", data=date(2026, 8, 10),
        wiersze=[WierszBlankietu(nadawca="Żabka", adres="Odkryta 24", ilosc_total=5)],
    ))
    zakladka.var_kurier.set("Kowalski Jan")
    zakladka.var_data.set("2026-08-10")
    _wypelnij_wiersz(zakladka.wiersze[0])  # ta sama trójka -> duplikat
    root.update()

    zakladka.zapisz()

    assert str(zakladka.etykieta_status.cget("foreground")) == KOLORY["czerwony"]
    assert "duplikat" in zakladka.etykieta_status.cget("text").lower()
    # wiersz pominięty NIE znika - dane wciąż w polu, do poprawki
    assert any(w.var_adres.get() == "Odkryta 24" for w in zakladka.wiersze)
    assert zakladka.var_kurier.get() == "Kowalski Jan"  # nagłówek NIE czyszczony


def test_zapis_czesciowy_usuwa_tylko_zapisane_wiersze(zakladka, root):
    _wypelnij_wiersz(zakladka.wiersze[0], adres="Odkryta 24")
    zakladka.dodaj_wiersz()
    _wypelnij_wiersz(zakladka.wiersze[-1], adres="Inna 5")
    zakladka.var_kurier.set("Kowalski Jan")
    root.update()

    zakladka.zapisz()  # oba nowe, oba wchodzą
    assert zakladka.conn.execute("SELECT COUNT(*) FROM transakcje").fetchone()[0] == 2

    # drugi zapis tej samej pary (Odkryta 24) koliduje, Inna 5 by była nowa,
    # ale tym razem dajemy TYLKO duplikat, żeby sprawdzić że zostaje sam
    zakladka.var_kurier.set("Kowalski Jan")
    _wypelnij_wiersz(zakladka.wiersze[0], adres="Odkryta 24")
    root.update()
    liczba_wierszy_przed = len(zakladka.wiersze)

    zakladka.zapisz()

    assert "Odkryta 24" in [w.var_adres.get() for w in zakladka.wiersze]
    assert len(zakladka.wiersze) == liczba_wierszy_przed  # nic nie zniknęło (0 zapisanych)


def test_dziennik_dostaje_liczbe_pominietych(zakladka, root):
    repo.zapisz_blankiet(zakladka.conn, Blankiet(
        kurier="Kowalski Jan", data=date(2026, 8, 10),
        wiersze=[WierszBlankietu(nadawca="Żabka", adres="Odkryta 24", ilosc_total=5)],
    ))
    zakladka.var_kurier.set("Kowalski Jan")
    zakladka.var_data.set("2026-08-10")
    _wypelnij_wiersz(zakladka.wiersze[0])
    root.update()

    zakladka.zapisz()

    wpisy = dziennik.wczytaj_operacje(zakladka.katalog_danych)
    assert wpisy[-1]["liczba_pominietych"] == 1


# --- podgląd sesyjny ---

def test_podglad_domyslnie_pokazuje_tylko_biezaca_sesje(zakladka, root):
    # wiersz z INNEJ sesji już w bazie - nie powinien pojawić się w podglądzie
    repo.zapisz_blankiet(
        zakladka.conn,
        Blankiet(kurier="Nowak Piotr", data=date(2026, 8, 1),
                  wiersze=[WierszBlankietu(nadawca="Żabka", adres="Stara 1", ilosc_total=1)]),
        sesja_uuid="inna-sesja",
    )
    _wypelnij_wiersz(zakladka.wiersze[0])
    zakladka.var_kurier.set("Kowalski Jan")
    root.update()
    zakladka.zapisz()

    assert len(zakladka.podglad._dane) == 1
    assert zakladka.podglad._dane[0]["kurier"] == "Kowalski Jan"


def test_checkbox_pokaz_wszystko_pokazuje_inne_sesje(zakladka, root):
    repo.zapisz_blankiet(
        zakladka.conn,
        Blankiet(kurier="Nowak Piotr", data=date(2026, 8, 1),
                  wiersze=[WierszBlankietu(nadawca="Żabka", adres="Stara 1", ilosc_total=1)]),
        sesja_uuid="inna-sesja",
    )

    zakladka.var_pokaz_wszystko.set(True)
    zakladka.odswiez_podglad()

    assert len(zakladka.podglad._dane) == 1
    assert zakladka.podglad._dane[0]["kurier"] == "Nowak Piotr"


def test_dwuklik_na_podgladzie_otwiera_dialog_edycji(zakladka, root, monkeypatch):
    repo.zapisz_blankiet(
        zakladka.conn,
        Blankiet(kurier="Kowalski Jan", data=date(2026, 8, 1),
                  wiersze=[WierszBlankietu(nadawca="Żabka", adres="Stara 1", ilosc_total=1)]),
        sesja_uuid="sesja-testowa",
    )
    zakladka.odswiez_podglad()
    wolania = []
    monkeypatch.setattr(
        "zpo_tracker.gui.zakladka_wprowadzanie.DialogEdycji",
        lambda *a, **k: wolania.append((a, k)),
    )
    iid = zakladka.podglad.tree.get_children()[0]
    zakladka.podglad.tree.selection_set(iid)

    zakladka.podglad._na_dwuklik(None)

    assert len(wolania) == 1
