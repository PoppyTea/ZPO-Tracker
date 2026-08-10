"""
Smoke test GUI: okno się tworzy, zakładka przeglądania pokazuje dane,
nic nie wybucha przy zamknięciu. Wymaga środowiska graficznego (DISPLAY) -
pomijany automatycznie, jeśli niedostępne.
"""
import subprocess
import sys
from datetime import date

import pytest

from zpo_tracker import repo
from zpo_tracker.models import BlankietBlok, WierszBlankietu


def _ma_display():
    """
    Sprawdza w OSOBNYM procesie, czy da się realnie stworzyć widget Tk.
    Celowo subprocess, nie import w tym procesie: w tym środowisku
    stworzenie widgetu bywa fatalnym SIGABRT na poziomie Xlib/XCB (nie
    Python TclError - tego nie da się przechwycić try/except), co
    zabiłoby cały proces pytest. Awaria w podprocesie = czyste
    pominięcie tego modułu, nie ubicie całego zestawu testów.
    """
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


def test_aplikacja_startuje_i_pokazuje_notebook():
    from zpo_tracker.gui.app import Aplikacja

    app = Aplikacja(sciezka_bazy=":memory:")
    try:
        app.update()
        assert app.zakladka_przeglad is not None
    finally:
        app.destroy()


def test_zakladka_przeglad_pokazuje_wpisana_transakcje():
    from zpo_tracker.gui.app import Aplikacja

    app = Aplikacja(sciezka_bazy=":memory:")
    try:
        blok = BlankietBlok(
            kurier="Testowy Kurier",
            data=date(2026, 8, 10),
            rejon="WA1",
            wiersze=[WierszBlankietu(nadawca="Żabka", adres="Testowa 1", ilosc_total=2)],
        )
        repo.zapisz_blok(app.conn, blok)
        app.zakladka_przeglad.odswiez()
        app.update()
        assert "1 transakcji" in app.zakladka_przeglad.etykieta_liczby.cget("text")
    finally:
        app.destroy()
