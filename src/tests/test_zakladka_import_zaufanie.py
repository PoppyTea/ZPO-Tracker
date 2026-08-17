"""
Zakładka Import/Export a model zaufania (0.1-alpha.3.2): rozpoznanie
własnego eksportu, blokada dla pliku ze zmienioną zawartością, ukryty
przełącznik wymuszenia zaufania (odsłaniany wpisem w settings.json).
Wymaga środowiska graficznego - pomijany automatycznie, jeśli niedostępne
(patrz test_gui_smoke.py, ten sam mechanizm).
"""
import subprocess
import sys
import tkinter as tk

import openpyxl
import pytest

from zpo_tracker import eksport, repo, ustawienia
from zpo_tracker.gui.zakladka_import_export import DialogKorektyImportu, ZakladkaImportExport
from zpo_tracker.import_orchestrator import zwaliduj_wiersze


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


def _wiersze_do_dialogu():
    surowy = {
        "data": "2026-08-03",
        " Pełna Nazwa Nadawcy": "Żabka",
        "Adres odbioru dla wszystkich nadawców": "Odkryta 24",
        "Kurier": "Kowalski Jan",
        "Rejon": "WA87",
        " Wpisujemy łączną liczbę odebranych Pocztexów": 3,
        "PNI ZPO": "228648",
    }
    zwalidowane, _ = zwaliduj_wiersze([surowy])
    return zwalidowane


def _dialog(root, conn, tmp_path, status, **nadpisz):
    kwargs = dict(
        nazwa_pliku="plik.xlsx", zwalidowane=_wiersze_do_dialogu(),
        odrzucone=[], propozycje=[], ostrzezenia=[], on_gotowe=lambda _w: None,
        status_zaufania=status,
    )
    kwargs.update(nadpisz)
    return DialogKorektyImportu(root, conn, tmp_path, **kwargs)


# --- przełącznik wymuszenia: widoczny tylko z wpisem w settings ---

def test_bez_wpisu_w_ustawieniach_przelacznik_nie_istnieje(root, conn, tmp_path):
    dialog = _dialog(root, conn, tmp_path, eksport.PLIK_OBCY)
    assert dialog.checkbox_wymuszenia is None


def test_z_wpisem_w_ustawieniach_przelacznik_istnieje_ale_odznaczony(root, conn, tmp_path):
    ustawienia.zapisz(tmp_path, {"zaawansowane": {"pokaz_wymuszenie_zaufania": True}})
    dialog = _dialog(root, conn, tmp_path, eksport.PLIK_OBCY)
    assert dialog.checkbox_wymuszenia is not None
    assert dialog.var_wymus_zaufanie.get() is False  # per użycie, nigdy domyślnie


def test_dla_pliku_zmodyfikowanego_przelacznik_nie_istnieje_mimo_wpisu(root, conn, tmp_path):
    # sedno decyzji Papavera: plik z NASZYM znacznikiem, ale zmienioną
    # zawartością, nie może zostać uznany za zaufany ŻADNĄ drogą - również
    # nie przez tryb zaawansowany
    ustawienia.zapisz(tmp_path, {"zaawansowane": {"pokaz_wymuszenie_zaufania": True}})
    dialog = _dialog(root, conn, tmp_path, eksport.PLIK_ZMODYFIKOWANY)
    assert dialog.checkbox_wymuszenia is None


# --- czy_zaufany: rozstrzygnięcie przekazywane do importu ---

def test_wlasny_eksport_jest_zaufany(root, conn, tmp_path):
    dialog = _dialog(root, conn, tmp_path, eksport.PLIK_ZAUFANY)
    assert dialog.czy_zaufany() is True


def test_obcy_plik_nie_jest_zaufany(root, conn, tmp_path):
    dialog = _dialog(root, conn, tmp_path, eksport.PLIK_OBCY)
    assert dialog.czy_zaufany() is False


def test_obcy_plik_z_wymuszeniem_jest_zaufany(root, conn, tmp_path):
    ustawienia.zapisz(tmp_path, {"zaawansowane": {"pokaz_wymuszenie_zaufania": True}})
    dialog = _dialog(root, conn, tmp_path, eksport.PLIK_OBCY)
    dialog.var_wymus_zaufanie.set(True)
    assert dialog.czy_zaufany() is True


def test_plik_zmodyfikowany_nie_jest_zaufany_nawet_z_wymuszeniem(root, conn, tmp_path):
    ustawienia.zapisz(tmp_path, {"zaawansowane": {"pokaz_wymuszenie_zaufania": True}})
    dialog = _dialog(root, conn, tmp_path, eksport.PLIK_ZMODYFIKOWANY)
    dialog.var_wymus_zaufanie.set(True)  # nawet ustawione ręcznie
    assert dialog.czy_zaufany() is False


# --- zatwierdzenie faktycznie przekazuje rozstrzygnięcie do importu ---

def test_zatwierdzenie_niezaufanego_nie_zapisuje_pni(root, conn, tmp_path):
    dialog = _dialog(root, conn, tmp_path, eksport.PLIK_OBCY)
    dialog._zatwierdz()
    assert conn.execute("SELECT pni_zpo FROM punkty").fetchone()[0] is None


def test_zatwierdzenie_zaufanego_zapisuje_pni(root, conn, tmp_path):
    dialog = _dialog(root, conn, tmp_path, eksport.PLIK_ZAUFANY)
    dialog._zatwierdz()
    assert conn.execute("SELECT pni_zpo FROM punkty").fetchone()[0] == "228648"


# --- rozpoznanie pliku w zakładce (end-to-end, przez realny plik) ---

def test_zakladka_rozpoznaje_wlasny_eksport(root, conn, tmp_path):
    kurier_id = conn.execute(
        "INSERT INTO kurierzy (imie_nazwisko) VALUES ('Kowalski Jan')").lastrowid
    punkt_id = conn.execute(
        "INSERT INTO punkty (nadawca, adres, pni_zpo) VALUES ('Żabka', 'Odkryta 24', '228648')"
    ).lastrowid
    conn.execute(
        "INSERT INTO transakcje (data, kurier_id, punkt_id, ilosc_total)"
        " VALUES ('2026-08-03', ?, ?, 3)", (kurier_id, punkt_id))
    sciezka = tmp_path / "export.xlsx"
    eksport.eksportuj_miesiac(conn, 2026, 8, sciezka)

    assert eksport.zweryfikuj_plik(sciezka) == eksport.PLIK_ZAUFANY


def test_zakladka_import_export_konstruuje_sie(root, conn, tmp_path):
    zakladka = ZakladkaImportExport(root, conn, tmp_path)
    assert zakladka is not None
