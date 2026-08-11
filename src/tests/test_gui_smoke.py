"""
Smoke test GUI: okno się tworzy, zakładka przeglądania pokazuje dane,
nic nie wybucha przy zamknięciu. Wymaga środowiska graficznego (DISPLAY) -
pomijany automatycznie, jeśli niedostępne.
"""
import subprocess
import sys
import tkinter as tk
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


def test_zapis_z_formularza_stempluje_autora(tmp_path, monkeypatch):
    # bez tego kolumny atrybucji istnieją, ale w praktyce zawsze są puste
    monkeypatch.setenv("USERDOMAIN", "POCZTA-POLSKA")
    monkeypatch.setenv("USERNAME", "jkowalski")
    from zpo_tracker.gui.app import Aplikacja
    from zpo_tracker import dziennik, uzytkownicy

    app = Aplikacja(sciezka_bazy=str(tmp_path / "test.db"))
    try:
        uzytkownicy.zapewnij_uzytkownika(
            app.conn, login="POCZTA-POLSKA\\jkowalski",
            alias="Jan Kowalski", nr_kadrowy="ab12X")
        blok = BlankietBlok(
            kurier="Testowy Kurier", data=date(2026, 8, 10), rejon="WA1",
            wiersze=[WierszBlankietu(nadawca="Żabka", adres="Testowa 1", ilosc_total=2)],
        )
        repo.zapisz_blok(app.conn, blok, autor_id=app.autor_id)

        wiersz = app.conn.execute(
            "SELECT u.alias, t.utworzono FROM transakcje t"
            " JOIN users u ON u.id = t.autor_id").fetchone()
        assert wiersz["alias"] == "Jan Kowalski"
        assert wiersz["utworzono"]
    finally:
        app.destroy()
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


# --- migawki + cofanie (X+1): zakładka Historia, operacje.wykonaj/cofnij ---

def test_zakladka_historia_istnieje(tmp_path):
    from zpo_tracker.gui.app import Aplikacja
    from zpo_tracker import dziennik

    app = Aplikacja(sciezka_bazy=str(tmp_path / "test.db"))
    try:
        assert app.zakladka_historia is not None
    finally:
        app.destroy()
        dziennik.odepnij()


def test_zapisz_z_formularza_tworzy_wpis_w_dzienniku_z_migawka(tmp_path):
    # kliknięcie ZAPISZ musi przejść przez operacje.wykonaj (migawka +
    # dziennik), nie wołać repo.zapisz_blok bezpośrednio - inaczej cofnięcie
    # byłoby dla tej operacji niemożliwe
    from zpo_tracker.gui.app import Aplikacja
    from zpo_tracker import dziennik, kopie

    app = Aplikacja(sciezka_bazy=str(tmp_path / "test.db"))
    try:
        wprowadzanie = app.zakladka_wprowadzanie
        wprowadzanie.var_kurier.set("Testowy Kurier")
        blok = wprowadzanie.bloki[0]
        blok.var_rejon.set("WA1")
        wiersz = blok.wiersze[0]
        wiersz.var_nadawca.set("Żabka")
        wiersz.var_adres.set("Testowa 1")
        wiersz.var_ilosc_total.set("2")

        wprowadzanie.zapisz()

        wpisy = dziennik.wczytaj_operacje(app.katalog_danych)
        assert len(wpisy) == 1
        assert wpisy[0]["rodzaj"] == "zapis_blankietu"
        assert wpisy[0]["liczba_wierszy"] == 1
        assert len(kopie.lista_migawek(app.katalog_danych)) == 1
    finally:
        app.destroy()
        dziennik.odepnij()


def test_dodanie_do_slownika_tworzy_wpis_w_dzienniku(tmp_path):
    from zpo_tracker.gui.app import Aplikacja
    from zpo_tracker import dziennik

    app = Aplikacja(sciezka_bazy=str(tmp_path / "test.db"))
    try:
        podzakladka_kurierzy = app.zakladka_slowniki._podzakladki[0]
        podzakladka_kurierzy.var_nowy.set("Nowak Piotr")
        podzakladka_kurierzy.dodaj()

        wpisy = dziennik.wczytaj_operacje(app.katalog_danych)
        assert len(wpisy) == 1
        assert wpisy[0]["rodzaj"] == "dodaj_slownik"
    finally:
        app.destroy()
        dziennik.odepnij()


def test_start_aplikacji_przycina_stare_migawki(tmp_path):
    # kubełek retencji "1-3 dni" - dwie migawki tego samego wieku, tylko
    # jedna powinna przetrwać start aplikacji (kopie.przytnij_migawki)
    from datetime import datetime, timedelta
    from zpo_tracker.gui.app import Aplikacja
    from zpo_tracker import dziennik, kopie

    sciezka = str(tmp_path / "test.db")
    katalog = tmp_path
    dziennik.skonfiguruj(katalog)
    teraz = datetime.now()
    for seq, dni_temu in [(1, 1.2), (2, 1.8)]:
        plik = kopie.katalog_migawek(katalog) / f"{seq:06d}.db"
        plik.write_bytes(b"x")
        dziennik.zapisz_operacje(
            katalog, seq=seq, rodzaj="test", etykieta="e",
            plik_migawki=str(plik),
            czas=(teraz - timedelta(days=dni_temu)).isoformat(timespec="seconds"),
        )
    dziennik.odepnij()
    assert len(kopie.lista_migawek(katalog)) == 2

    app = Aplikacja(sciezka_bazy=sciezka)
    try:
        assert len(kopie.lista_migawek(katalog)) == 1
    finally:
        app.destroy()
        dziennik.odepnij()


def _dodaj_kuriera(conn, nazwa):
    conn.execute("INSERT INTO kurierzy (imie_nazwisko) VALUES (?)", (nazwa,))


def test_dialog_alternatyw_gdy_brak_poprzedniej_nie_wybucha(tmp_path):
    # cel to najstarsza operacja w ogóle - "poprzednia" nie istnieje
    from zpo_tracker.gui.app import Aplikacja
    from zpo_tracker import dziennik
    from zpo_tracker.gui.zakladka_historia import DialogAlternatywnychMigawek

    app = Aplikacja(sciezka_bazy=str(tmp_path / "test.db"))
    try:
        wpis_docelowy = {"seq": 1, "etykieta": "e", "czas": "2026-08-11T00:00:00"}
        wpis_nastepna = {"seq": 2, "etykieta": "e2", "czas": "2026-08-12T00:00:00"}
        dialog = DialogAlternatywnychMigawek(
            app, wpis_docelowy, poprzednia=None, nastepna=wpis_nastepna,
            on_wybor=lambda w: None,
        )
        dialog.update()
        dialog.destroy()
    finally:
        app.destroy()
        dziennik.odepnij()


def test_dialog_alternatyw_gdy_brak_nastepnej_nie_wybucha(tmp_path):
    from zpo_tracker.gui.app import Aplikacja
    from zpo_tracker import dziennik
    from zpo_tracker.gui.zakladka_historia import DialogAlternatywnychMigawek

    app = Aplikacja(sciezka_bazy=str(tmp_path / "test.db"))
    try:
        wpis_docelowy = {"seq": 2, "etykieta": "e", "czas": "2026-08-12T00:00:00"}
        wpis_poprzednia = {"seq": 1, "etykieta": "e1", "czas": "2026-08-11T00:00:00"}
        dialog = DialogAlternatywnychMigawek(
            app, wpis_docelowy, poprzednia=wpis_poprzednia, nastepna=None,
            on_wybor=lambda w: None,
        )
        dialog.update()
        dialog.destroy()
    finally:
        app.destroy()
        dziennik.odepnij()


def test_cofnij_przez_dialog_alternatyw_poprzednia_przywraca_wlasciwy_stan(tmp_path, monkeypatch):
    # migawka "B" przycięta - wybór "poprzednia" (A) musi przywrócić stan
    # SPRZED A (0 kurierów), nie jakikolwiek inny punkt
    from pathlib import Path
    from zpo_tracker.gui.app import Aplikacja
    from zpo_tracker import dziennik, operacje, repo as repo_modul

    monkeypatch.setattr(
        "zpo_tracker.gui.zakladka_historia.messagebox.askyesno",
        lambda *a, **k: True)

    sciezka = str(tmp_path / "test.db")
    app = Aplikacja(sciezka_bazy=sciezka)
    seqi = {}
    try:
        for etykieta in ("A", "B", "C"):
            operacje.wykonaj(
                app.conn, app.katalog_danych, rodzaj="test", etykieta=etykieta,
                funkcja=_dodaj_kuriera, args=(etykieta,),
            )
            seqi[etykieta] = dziennik.wczytaj_operacje(app.katalog_danych)[-1]["seq"]

        wpis_b = next(w for w in dziennik.wczytaj_operacje(app.katalog_danych)
                      if w["seq"] == seqi["B"])
        Path(wpis_b["plik_migawki"]).unlink()

        poprzednia, nastepna = operacje.znajdz_najblizsze_migawki(
            app.katalog_danych, seqi["B"])
        assert poprzednia["seq"] == seqi["A"]
        assert nastepna["seq"] == seqi["C"]

        app.zakladka_historia._potwierdz_i_cofnij(poprzednia)  # zamyka `app`
    finally:
        dziennik.odepnij()

    po_cofnieciu = repo_modul.polacz(sciezka)
    nazwiska = [r[0] for r in po_cofnieciu.execute(
        "SELECT imie_nazwisko FROM kurierzy").fetchall()]
    po_cofnieciu.close()
    assert nazwiska == []  # migawka A = stan SPRZED wstawienia A


def test_cofnij_przez_dialog_alternatyw_nastepna_przywraca_wlasciwy_stan(tmp_path, monkeypatch):
    # ten sam scenariusz, ale wybór "następna" (C) musi przywrócić stan
    # SPRZED C - czyli A i B obecne, nie 0 i nie wszystkie trzy
    from pathlib import Path
    from zpo_tracker.gui.app import Aplikacja
    from zpo_tracker import dziennik, operacje, repo as repo_modul

    monkeypatch.setattr(
        "zpo_tracker.gui.zakladka_historia.messagebox.askyesno",
        lambda *a, **k: True)

    sciezka = str(tmp_path / "test.db")
    app = Aplikacja(sciezka_bazy=sciezka)
    seqi = {}
    try:
        for etykieta in ("A", "B", "C"):
            operacje.wykonaj(
                app.conn, app.katalog_danych, rodzaj="test", etykieta=etykieta,
                funkcja=_dodaj_kuriera, args=(etykieta,),
            )
            seqi[etykieta] = dziennik.wczytaj_operacje(app.katalog_danych)[-1]["seq"]

        wpis_b = next(w for w in dziennik.wczytaj_operacje(app.katalog_danych)
                      if w["seq"] == seqi["B"])
        Path(wpis_b["plik_migawki"]).unlink()

        poprzednia, nastepna = operacje.znajdz_najblizsze_migawki(
            app.katalog_danych, seqi["B"])

        app.zakladka_historia._potwierdz_i_cofnij(nastepna)  # zamyka `app`
    finally:
        dziennik.odepnij()

    po_cofnieciu = repo_modul.polacz(sciezka)
    nazwiska = {r[0] for r in po_cofnieciu.execute(
        "SELECT imie_nazwisko FROM kurierzy").fetchall()}
    po_cofnieciu.close()
    assert nazwiska == {"A", "B"}  # migawka C = stan SPRZED wstawienia C


def test_cofnij_wybrany_pokazuje_dialog_alternatyw_gdy_migawka_zniknela(tmp_path):
    # koniec-do-końca przez _cofnij_wybrany (wybór w tabeli), nie tylko
    # bezpośrednie wywołanie _potwierdz_i_cofnij
    from pathlib import Path
    from zpo_tracker.gui.app import Aplikacja
    from zpo_tracker import dziennik, operacje

    app = Aplikacja(sciezka_bazy=str(tmp_path / "test.db"))
    try:
        operacje.wykonaj(
            app.conn, app.katalog_danych, rodzaj="test", etykieta="A",
            funkcja=_dodaj_kuriera, args=("A",),
        )
        seq_a = dziennik.wczytaj_operacje(app.katalog_danych)[-1]["seq"]
        operacje.wykonaj(
            app.conn, app.katalog_danych, rodzaj="test", etykieta="B",
            funkcja=_dodaj_kuriera, args=("B",),
        )
        wpis_a = next(w for w in dziennik.wczytaj_operacje(app.katalog_danych)
                      if w["seq"] == seq_a)
        Path(wpis_a["plik_migawki"]).unlink()

        app.zakladka_historia.odswiez()
        for item in app.zakladka_historia.tabela.tree.get_children():
            if int(app.zakladka_historia.tabela.tree.item(item, "values")[0]) == seq_a:
                app.zakladka_historia.tabela.tree.selection_set(item)
                break
        app.zakladka_historia._cofnij_wybrany()
        app.update()

        toplevele = [w for w in app.winfo_children() if isinstance(w, tk.Toplevel)]
        assert len(toplevele) == 1
    finally:
        app.destroy()
        dziennik.odepnij()


def test_cofnij_do_przywraca_stan_i_zamyka_aplikacje(tmp_path):
    from zpo_tracker.gui.app import Aplikacja
    from zpo_tracker import dziennik, operacje, repo as repo_modul

    sciezka = str(tmp_path / "test.db")
    app = Aplikacja(sciezka_bazy=sciezka)
    try:
        blok = BlankietBlok(
            kurier="Testowy Kurier", data=date(2026, 8, 10), rejon="WA1",
            wiersze=[WierszBlankietu(nadawca="Żabka", adres="Testowa 1", ilosc_total=2)],
        )
        operacje.wykonaj(
            app.conn, app.katalog_danych, rodzaj="zapis_blankietu", etykieta="test",
            funkcja=repo_modul.zapisz_blok, args=(blok,),
        )
        seq = dziennik.wczytaj_operacje(app.katalog_danych)[-1]["seq"]

        app.cofnij_do(seq)  # zamyka `app` w środku (patrz Aplikacja.cofnij_do)

        po_cofnieciu = repo_modul.polacz(sciezka)
        assert po_cofnieciu.execute("SELECT COUNT(*) FROM transakcje").fetchone()[0] == 0
        po_cofnieciu.close()
    finally:
        dziennik.odepnij()
