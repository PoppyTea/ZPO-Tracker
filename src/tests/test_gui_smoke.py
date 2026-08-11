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


def test_aplikacja_startuje_i_pokazuje_notebook(tmp_path):
    from zpo_tracker.gui.app import Aplikacja
    from zpo_tracker import dziennik

    # ścieżka w tmp_path, nie ":memory:" - inaczej log i dziennik lądują
    # w PRAWDZIWYM katalogu danych użytkownika (~/.local/share/zpo-tracker)
    app = Aplikacja(sciezka_bazy=str(tmp_path / "test.db"))
    try:
        app.update()
        assert app.zakladka_przeglad is not None
    finally:
        app.destroy()
        dziennik.odepnij()


def test_aplikacja_podpina_hak_na_wyjatki_z_callbackow(tmp_path):
    # sedno kroku 1: bez tego wyjątek z callbacku Tk leci do sys.stderr,
    # który w buildzie console=False jest None - awaria niewidzialna
    from zpo_tracker.gui.app import Aplikacja
    from zpo_tracker import dziennik

    app = Aplikacja(sciezka_bazy=str(tmp_path / "test.db"))
    try:
        try:
            raise ValueError("awaria z widgetu")
        except ValueError:
            app.report_callback_exception(*sys.exc_info())
        tresc = (tmp_path / dziennik.NAZWA_LOGU).read_text(encoding="utf-8")
        assert "awaria z widgetu" in tresc
    finally:
        app.destroy()
        dziennik.odepnij()


def test_aplikacja_odmawia_otwarcia_bazy_z_nowszej_wersji(tmp_path):
    # stacja z nieaktualnym .exe otwierająca bazę z nowszej stacji - lepiej
    # odmówić z komunikatem niż po cichu pominąć nieznane kolumny
    from zpo_tracker.gui.app import Aplikacja
    from zpo_tracker import dziennik, repo

    sciezka = str(tmp_path / "nowsza.db")
    przygotowanie = repo.polacz(sciezka)
    repo.utworz_schemat(przygotowanie)
    przygotowanie.execute(f"PRAGMA user_version = {repo.WERSJA_SCHEMATU + 1}")
    przygotowanie.close()

    try:
        with pytest.raises(repo.NiezgodnaWersjaSchematu):
            Aplikacja(sciezka_bazy=sciezka)
    finally:
        dziennik.odepnij()


def test_zakladka_przeglad_pokazuje_wpisana_transakcje(tmp_path):
    from zpo_tracker.gui.app import Aplikacja
    from zpo_tracker import dziennik

    app = Aplikacja(sciezka_bazy=str(tmp_path / "test.db"))
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
        dziennik.odepnij()
