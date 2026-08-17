"""
DialogUzytkownika (nr kadrowy opcjonalny od 0.1-alpha.3.2) i
DialogWyboruUzytkownika (wybór/zmiana osoby na współdzielonym koncie
Windows, patrz uzytkownicy.login_rozszerzony). Wymaga środowiska
graficznego - pomijany automatycznie, jeśli niedostępne (patrz
test_gui_smoke.py, ten sam mechanizm).
"""
import subprocess
import sys
import tkinter as tk

import pytest

from zpo_tracker import repo, uzytkownicy
from zpo_tracker.gui.dialog_uzytkownika import DialogUzytkownika, DialogWyboruUzytkownika


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


# --- DialogUzytkownika: nr kadrowy opcjonalny ---

def test_zapisuje_bez_podanego_nr_kadrowego(root, conn):
    wyniki = []
    dialog = DialogUzytkownika(root, conn, "DOM\\a", on_gotowe=wyniki.append)
    dialog.var_alias.set("Jan Kowalski")
    dialog.var_nr.set("")

    dialog._zatwierdz()

    assert len(wyniki) == 1
    wiersz = conn.execute(
        "SELECT alias, nr_kadrowy FROM users WHERE id = ?", (wyniki[0],)).fetchone()
    assert wiersz["alias"] == "Jan Kowalski"
    assert wiersz["nr_kadrowy"] is None


def test_nadal_odrzuca_zly_format_gdy_podany(root, conn):
    wyniki = []
    dialog = DialogUzytkownika(root, conn, "DOM\\a", on_gotowe=wyniki.append)
    dialog.var_alias.set("Jan Kowalski")
    dialog.var_nr.set("abc")  # za krótki

    dialog._zatwierdz()

    assert wyniki == []
    assert "5 znak" in dialog.etykieta_status.cget("text")


def test_wciaz_wymaga_aliasu(root, conn):
    wyniki = []
    dialog = DialogUzytkownika(root, conn, "DOM\\a", on_gotowe=wyniki.append)
    dialog.var_alias.set("")

    dialog._zatwierdz()

    assert wyniki == []


# --- DialogWyboruUzytkownika ---

def test_listuje_konta_bazowe_i_rozszerzone(root, conn):
    uzytkownicy.zapewnij_uzytkownika(conn, login="DOM\\a", alias="Konto bazowe")
    uzytkownicy.zapewnij_uzytkownika(
        conn, login=uzytkownicy.login_rozszerzony("DOM\\a", "Jan Kowalski"),
        alias="Jan Kowalski")

    dialog = DialogWyboruUzytkownika(root, conn, "DOM\\a", on_wybrano=lambda *_: None)

    aliasy = {k["alias"] for k in dialog.konta}
    assert aliasy == {"Konto bazowe", "Jan Kowalski"}


def test_wybor_istniejacego_konta_wola_on_wybrano(root, conn):
    uzytkownicy.zapewnij_uzytkownika(conn, login="DOM\\a", alias="Konto bazowe")
    wybory = []
    dialog = DialogWyboruUzytkownika(root, conn, "DOM\\a", on_wybrano=wybory.append)

    dialog._wybierz("DOM\\a")

    assert wybory == ["DOM\\a"]


def test_dodanie_nowej_osoby_tworzy_konto_rozszerzone_i_wola_on_wybrano(root, conn):
    uzytkownicy.zapewnij_uzytkownika(conn, login="DOM\\a", alias="Konto bazowe")
    wybory = []
    dialog = DialogWyboruUzytkownika(root, conn, "DOM\\a", on_wybrano=wybory.append)
    dialog.var_nazwa.set("Anna Nowak")

    dialog._dodaj_nowego()

    oczekiwany_login = uzytkownicy.login_rozszerzony("DOM\\a", "Anna Nowak")
    assert wybory == [oczekiwany_login]
    wiersz = conn.execute(
        "SELECT alias FROM users WHERE login = ?", (oczekiwany_login,)).fetchone()
    assert wiersz["alias"] == "Anna Nowak"


def test_dodanie_nowej_osoby_bez_nazwy_pokazuje_blad_i_nie_wola(root, conn):
    wybory = []
    dialog = DialogWyboruUzytkownika(root, conn, "DOM\\a", on_wybrano=wybory.append)
    dialog.var_nazwa.set("")

    dialog._dodaj_nowego()

    assert wybory == []
