"""
DialogEdycji: poprawka jednej zapisanej transakcji (0.1-alpha.3.2), widok
poprawek (zakladka_przeglad.py). ŚWIADOMIE bez maszynerii dedukcji - zwykły
modal, nadawca/adres/PNI nieedytowalne. Wymaga środowiska graficznego -
pomijany automatycznie, jeśli niedostępne (patrz test_gui_smoke.py, ten sam
mechanizm).
"""
import subprocess
import sys
import tkinter as tk
from datetime import date

import pytest

from zpo_tracker import dziennik, repo
from zpo_tracker.gui.dialog_edycji import DialogEdycji
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
    conn = repo.polacz(":memory:")
    repo.utworz_schemat(conn)
    yield conn
    conn.close()


def _zapisz(conn, **nadpisz):
    dane = dict(
        kurier="Kowalski Jan", data=date(2026, 8, 10),
        wiersze=[WierszBlankietu(nadawca="Żabka", adres="Odkryta 24", ilosc_total=5)],
    )
    dane.update(nadpisz)
    repo.zapisz_blankiet(conn, Blankiet(**dane))
    return repo.pobierz_transakcje(conn)[0]


def test_pola_wypelnione_wartosciami_wiersza(root, conn, tmp_path):
    wiersz = _zapisz(conn)
    dialog = DialogEdycji(root, conn, tmp_path, wiersz)
    assert dialog.var_data.get() == "2026-08-10"
    assert dialog.var_kurier.get() == "Kowalski Jan"
    assert dialog.var_ilosc_total.get() == "5"


def test_zapis_aktualizuje_transakcje_i_zamyka_dialog(root, conn, tmp_path):
    wiersz = _zapisz(conn)
    wolania = []
    dialog = DialogEdycji(root, conn, tmp_path, wiersz, on_zapisano=lambda: wolania.append(1))
    dialog.var_ilosc_total.set("9")

    dialog._zatwierdz()

    assert conn.execute("SELECT ilosc_total FROM transakcje").fetchone()[0] == 9
    assert wolania == [1]
    assert not dialog.winfo_exists()


def test_zapis_tworzy_wpis_w_dzienniku(root, conn, tmp_path):
    wiersz = _zapisz(conn)
    dialog = DialogEdycji(root, conn, tmp_path, wiersz)
    dialog.var_ilosc_total.set("9")

    dialog._zatwierdz()

    wpisy = dziennik.wczytaj_operacje(tmp_path)
    assert any(w["rodzaj"] == "edycja_transakcji" for w in wpisy)


def test_kolizja_pokazuje_blad_i_nie_zamyka_dialogu(root, conn, tmp_path):
    _zapisz(conn, kurier="Kowalski Jan", data=date(2026, 8, 10))
    wiersz_b = _zapisz(conn, kurier="Kowalski Jan", data=date(2026, 8, 11), wiersze=[
        WierszBlankietu(nadawca="Żabka", adres="Odkryta 24", ilosc_total=5)])
    dialog = DialogEdycji(root, conn, tmp_path, wiersz_b)
    dialog.var_data.set("2026-08-10")  # koliduje z pierwszym wierszem

    dialog._zatwierdz()

    assert dialog.winfo_exists()
    assert dialog.etykieta_status.cget("text") != ""
    niezmieniona = conn.execute(
        "SELECT data FROM transakcje WHERE id = ?", (wiersz_b["id"],)).fetchone()[0]
    assert niezmieniona == "2026-08-11"


def test_pusta_ilosc_total_pokazuje_blad_i_nie_zapisuje(root, conn, tmp_path):
    wiersz = _zapisz(conn)
    dialog = DialogEdycji(root, conn, tmp_path, wiersz)
    dialog.var_ilosc_total.set("")

    dialog._zatwierdz()

    assert dialog.winfo_exists()
    assert conn.execute("SELECT ilosc_total FROM transakcje").fetchone()[0] == 5


def test_ilosc_zpo_moze_byc_puste(root, conn, tmp_path):
    wiersz = _zapisz(conn, wiersze=[
        WierszBlankietu(nadawca="Żabka", adres="Odkryta 24", ilosc_total=5, ilosc_zpo=3)])
    dialog = DialogEdycji(root, conn, tmp_path, wiersz)
    dialog.var_ilosc_zpo.set("")

    dialog._zatwierdz()

    assert conn.execute("SELECT ilosc_zpo FROM transakcje").fetchone()[0] is None


def test_zla_data_pokazuje_blad_i_nie_zapisuje(root, conn, tmp_path):
    # kolumna `data` w SQLite nie ma typu i nic dotąd nie sprawdzało formatu
    # ISO - śmieciowa wartość wypadałaby z filtrów zakresu dat
    # (`t.data >= ?` porównuje leksykograficznie) i psuła sortowanie/eksport
    wiersz = _zapisz(conn)
    dialog = DialogEdycji(root, conn, tmp_path, wiersz)
    dialog.var_data.set("10-08-2026")

    dialog._zatwierdz()

    assert dialog.winfo_exists()
    assert dialog.etykieta_status.cget("text") != ""
    niezmieniona = conn.execute("SELECT data FROM transakcje").fetchone()[0]
    assert niezmieniona == "2026-08-10"


def test_ilosc_ujemna_pokazuje_blad(root, conn, tmp_path):
    wiersz = _zapisz(conn)
    dialog = DialogEdycji(root, conn, tmp_path, wiersz)
    dialog.var_ilosc_total.set("-1")

    dialog._zatwierdz()

    assert dialog.winfo_exists()
    assert conn.execute("SELECT ilosc_total FROM transakcje").fetchone()[0] == 5
