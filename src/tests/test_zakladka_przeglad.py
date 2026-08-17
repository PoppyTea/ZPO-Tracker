"""
ZakladkaPrzeglad jako widok poprawek (0.1-alpha.3.2): filtrowanie, dwuklik →
DialogEdycji, operacje zbiorcze (ustaw pole zaznaczonym, usuń zaznaczone).
Wymaga środowiska graficznego - pomijany automatycznie, jeśli niedostępne
(patrz test_gui_smoke.py, ten sam mechanizm).
"""
import subprocess
import sys
import tkinter as tk
from datetime import date

import pytest

from zpo_tracker import repo
from zpo_tracker.gui.zakladka_przeglad import ZakladkaPrzeglad
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


def _zapisz_z_sesja(conn, sesja_uuid, **nadpisz):
    dane = dict(
        kurier="Kowalski Jan", data=date(2026, 8, 10),
        wiersze=[WierszBlankietu(nadawca="Żabka", adres="Odkryta 24", ilosc_total=5)],
    )
    dane.update(nadpisz)
    repo.zapisz_blankiet(conn, Blankiet(**dane), sesja_uuid=sesja_uuid)


def test_domyslnie_pokazuje_wszystkie_transakcje(root, conn, tmp_path):
    _zapisz(conn)
    _zapisz(conn, wiersze=[WierszBlankietu(nadawca="Żabka", adres="Inna 5", ilosc_total=1)])
    zakladka = ZakladkaPrzeglad(root, conn, katalog_danych=tmp_path)
    assert len(zakladka.tabela._dane) == 2


def test_filtr_kuriera_zawezia_liste(root, conn, tmp_path):
    _zapisz(conn, kurier="Kowalski Jan")
    _zapisz(conn, kurier="Nowak Piotr", wiersze=[
        WierszBlankietu(nadawca="Żabka", adres="Inna 5", ilosc_total=1)])
    zakladka = ZakladkaPrzeglad(root, conn, katalog_danych=tmp_path)

    zakladka.var_kurier.set("Nowak Piotr")
    zakladka.odswiez()

    assert len(zakladka.tabela._dane) == 1
    assert zakladka.tabela._dane[0]["kurier"] == "Nowak Piotr"


def test_wyczysc_resetuje_filtry(root, conn, tmp_path):
    _zapisz(conn, kurier="Kowalski Jan")
    _zapisz(conn, kurier="Nowak Piotr", wiersze=[
        WierszBlankietu(nadawca="Żabka", adres="Inna 5", ilosc_total=1)])
    zakladka = ZakladkaPrzeglad(root, conn, katalog_danych=tmp_path)
    zakladka.var_kurier.set("Nowak Piotr")
    zakladka.odswiez()

    zakladka._wyczysc_filtry()

    assert zakladka.var_kurier.get() == ""
    assert len(zakladka.tabela._dane) == 2


def test_checkbox_sesji_filtruje_do_biezacej(root, conn, tmp_path):
    _zapisz_z_sesja(conn, "sesja-biezaca")
    _zapisz_z_sesja(conn, "sesja-inna", wiersze=[
        WierszBlankietu(nadawca="Żabka", adres="Inna 5", ilosc_total=1)])
    zakladka = ZakladkaPrzeglad(root, conn, katalog_danych=tmp_path, sesja_uuid="sesja-biezaca")

    zakladka.var_tylko_sesja.set(True)
    zakladka.odswiez()

    assert len(zakladka.tabela._dane) == 1
    assert zakladka.tabela._dane[0]["sesja_uuid"] == "sesja-biezaca"


def test_etykieta_sygnalizuje_obciecie_wyniku_do_limitu(root, conn, tmp_path, monkeypatch):
    # odswiez() pobiera maksymalnie 1000 wierszy - przy pełnym limicie
    # etykieta musi to zasygnalizować, inaczej "1000 transakcji" wygląda
    # jak cały zbiór, a operacje zbiorcze działają tylko na tym, co widać
    zakladka = ZakladkaPrzeglad(root, conn, katalog_danych=tmp_path)
    wiersze_obciete = [{"id": i} for i in range(1000)]
    monkeypatch.setattr(
        "zpo_tracker.gui.zakladka_przeglad.repo.pobierz_transakcje",
        lambda *a, **k: wiersze_obciete,
    )

    zakladka.odswiez()

    tekst = zakladka.etykieta_liczby.cget("text")
    assert "1000" in tekst
    assert "limit" in tekst.lower()


def test_etykieta_bez_obciecia_nie_wspomina_limitu(root, conn, tmp_path):
    _zapisz(conn)
    zakladka = ZakladkaPrzeglad(root, conn, katalog_danych=tmp_path)

    assert zakladka.etykieta_liczby.cget("text") == "1 transakcji"


def test_dwuklik_otwiera_dialog_edycji_z_wlasciwym_wierszem(root, conn, tmp_path, monkeypatch):
    _zapisz(conn)
    zakladka = ZakladkaPrzeglad(root, conn, katalog_danych=tmp_path)
    wolania = []
    monkeypatch.setattr(
        "zpo_tracker.gui.zakladka_przeglad.DialogEdycji",
        lambda *a, **k: wolania.append((a, k)),
    )
    iid = zakladka.tabela.tree.get_children()[0]
    zakladka.tabela.tree.selection_set(iid)

    zakladka.tabela._na_dwuklik(None)

    assert len(wolania) == 1
    wiersz_przekazany = wolania[0][0][3]  # (self, conn, katalog_danych, wiersz)
    assert wiersz_przekazany["kurier"] == "Kowalski Jan"


def test_ustaw_pole_zaznaczonym_aktualizuje_baze(root, conn, tmp_path):
    _zapisz(conn, kurier="Kowalski Jan")
    _zapisz(conn, kurier="Kowalski Jan", wiersze=[
        WierszBlankietu(nadawca="Żabka", adres="Inna 5", ilosc_total=1)])
    zakladka = ZakladkaPrzeglad(root, conn, katalog_danych=tmp_path)
    zakladka.tabela.tree.selection_set(zakladka.tabela.tree.get_children())

    zakladka._wykonaj_ustaw_pole(
        [w["id"] for w in zakladka.tabela.wiersze_zaznaczone()], "wykonawca", "Koli")

    nazwy = [r[0] for r in conn.execute(
        "SELECT w.nazwa FROM transakcje t JOIN wykonawcy w ON w.id = t.wykonawca_id")]
    assert nazwy == ["Koli", "Koli"]


def test_dialog_ustaw_pole_zbiorczo_odrzuca_zla_date(root, conn):
    from zpo_tracker.gui.zakladka_przeglad import _DialogUstawPoleZbiorczo

    wolania = []
    dialog = _DialogUstawPoleZbiorczo(root, conn, on_zatwierdzono=lambda *a: wolania.append(a))
    dialog.var_pole.set("data")
    dialog.var_wartosc.set("10-08-2026")

    dialog._zatwierdz()

    assert wolania == []
    assert dialog.winfo_exists()
    assert dialog.etykieta_status.cget("text") != ""


def test_usun_zaznaczone_z_potwierdzeniem_usuwa(root, conn, tmp_path, monkeypatch):
    _zapisz(conn)
    zakladka = ZakladkaPrzeglad(root, conn, katalog_danych=tmp_path)
    zakladka.tabela.tree.selection_set(zakladka.tabela.tree.get_children())
    monkeypatch.setattr(
        "zpo_tracker.gui.zakladka_przeglad.messagebox.askyesno", lambda *a, **k: True)

    zakladka._usun_zaznaczone()

    assert conn.execute("SELECT COUNT(*) FROM transakcje").fetchone()[0] == 0


def test_usun_zaznaczone_bez_potwierdzenia_nic_nie_usuwa(root, conn, tmp_path, monkeypatch):
    _zapisz(conn)
    zakladka = ZakladkaPrzeglad(root, conn, katalog_danych=tmp_path)
    zakladka.tabela.tree.selection_set(zakladka.tabela.tree.get_children())
    monkeypatch.setattr(
        "zpo_tracker.gui.zakladka_przeglad.messagebox.askyesno", lambda *a, **k: False)

    zakladka._usun_zaznaczone()

    assert conn.execute("SELECT COUNT(*) FROM transakcje").fetchone()[0] == 1


def test_usun_zaznaczone_potwierdzenie_pokazuje_probke_wierszy(root, conn, tmp_path, monkeypatch):
    _zapisz(conn)
    zakladka = ZakladkaPrzeglad(root, conn, katalog_danych=tmp_path)
    zakladka.tabela.tree.selection_set(zakladka.tabela.tree.get_children())
    tresci = []
    monkeypatch.setattr(
        "zpo_tracker.gui.zakladka_przeglad.messagebox.askyesno",
        lambda tytul, tresc: tresci.append(tresc) or True,
    )

    zakladka._usun_zaznaczone()

    assert "Żabka" in tresci[0]
    assert "Odkryta 24" in tresci[0]


def test_on_zmieniono_wolane_po_operacji_zbiorczej(root, conn, tmp_path):
    _zapisz(conn)
    wolania = []
    zakladka = ZakladkaPrzeglad(
        root, conn, katalog_danych=tmp_path, on_zmieniono=lambda: wolania.append(1))
    zakladka.tabela.tree.selection_set(zakladka.tabela.tree.get_children())

    zakladka._wykonaj_ustaw_pole(
        [w["id"] for w in zakladka.tabela.wiersze_zaznaczone()], "wykonawca", "Koli")

    assert wolania == [1]
