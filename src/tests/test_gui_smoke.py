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
from zpo_tracker.models import Blankiet, WierszBlankietu


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
        blok = Blankiet(
            kurier="Testowy Kurier", data=date(2026, 8, 10),
            wiersze=[WierszBlankietu(nadawca="Żabka", adres="Testowa 1", rejon="WA1", ilosc_total=2)],
        )
        repo.zapisz_blankiet(app.conn, blok, autor_id=app.autor_id)

        wiersz = app.conn.execute(
            "SELECT u.alias, t.utworzono FROM transakcje t"
            " JOIN users u ON u.id = t.autor_id").fetchone()
        assert wiersz["alias"] == "Jan Kowalski"
        assert wiersz["utworzono"]
    finally:
        app.destroy()
        dziennik.odepnij()


# --- 0.1-alpha.3.2: menu Użytkownik (zmiana/wylogowanie na współdzielonym koncie) ---

def test_menu_uzytkownika_ma_zmien_i_wyloguj(tmp_path):
    from zpo_tracker.gui.app import Aplikacja
    from zpo_tracker import dziennik

    app = Aplikacja(sciezka_bazy=str(tmp_path / "test.db"))
    try:
        etykiety = [
            app._menu_uzytkownika.entrycget(i, "label")
            for i in range(app._menu_uzytkownika.index("end") + 1)
        ]
        assert "Zmień użytkownika…" in etykiety
        assert "Wyloguj" in etykiety
    finally:
        app.destroy()
        dziennik.odepnij()


def test_wyloguj_usuwa_aktywny_login_i_otwiera_wybor(tmp_path, monkeypatch):
    monkeypatch.setenv("USERDOMAIN", "POCZTA-POLSKA")
    monkeypatch.setenv("USERNAME", "jkowalski")
    from zpo_tracker.gui.app import Aplikacja
    from zpo_tracker import dziennik, ustawienia

    app = Aplikacja(sciezka_bazy=str(tmp_path / "test.db"))
    try:
        ustawienia.zapisz(app.katalog_danych, {"aktywny_login": "cokolwiek"})
        wolania = []
        monkeypatch.setattr(
            "zpo_tracker.gui.app.DialogWyboruUzytkownika",
            lambda *a, **k: wolania.append((a, k)),
        )

        app._wyloguj()

        assert "aktywny_login" not in ustawienia.wczytaj(app.katalog_danych)
        assert len(wolania) == 1
    finally:
        app.destroy()
        dziennik.odepnij()


def test_wybor_uzytkownika_aktualizuje_autora_we_wszystkich_zakladkach(tmp_path, monkeypatch):
    monkeypatch.setenv("USERDOMAIN", "POCZTA-POLSKA")
    monkeypatch.setenv("USERNAME", "jkowalski")
    from zpo_tracker.gui.app import Aplikacja
    from zpo_tracker import dziennik, uzytkownicy

    app = Aplikacja(sciezka_bazy=str(tmp_path / "test.db"))
    try:
        nowy_login = uzytkownicy.login_rozszerzony("POCZTA-POLSKA\\jkowalski", "Anna Nowak")
        uzytkownicy.zapewnij_uzytkownika(app.conn, login=nowy_login, alias="Anna Nowak")

        app._na_wybrano_uzytkownika(nowy_login)

        oczekiwany_id = uzytkownicy.uuid_uzytkownika(nowy_login)
        assert app.autor_id == oczekiwany_id
        assert app.zakladka_wprowadzanie.autor_id == oczekiwany_id
        assert app.zakladka_import_export.autor_id == oczekiwany_id
    finally:
        app.destroy()
        dziennik.odepnij()


def test_start_aplikacji_uzywa_aktywnego_loginu_z_ustawien(tmp_path, monkeypatch):
    monkeypatch.setenv("USERDOMAIN", "POCZTA-POLSKA")
    monkeypatch.setenv("USERNAME", "jkowalski")
    from zpo_tracker.gui.app import Aplikacja
    from zpo_tracker import dziennik, ustawienia, uzytkownicy

    katalog = tmp_path
    login_rozszerzony = uzytkownicy.login_rozszerzony(
        "POCZTA-POLSKA\\jkowalski", "Anna Nowak")
    ustawienia.zapisz(katalog, {"aktywny_login": login_rozszerzony})

    app = Aplikacja(sciezka_bazy=str(tmp_path / "test.db"))
    try:
        assert app.autor_id == uzytkownicy.uuid_uzytkownika(login_rozszerzony)
    finally:
        app.destroy()
        dziennik.odepnij()


def test_zakladka_przeglad_pokazuje_wpisana_transakcje(tmp_path):
    from zpo_tracker.gui.app import Aplikacja
    from zpo_tracker import dziennik

    app = Aplikacja(sciezka_bazy=str(tmp_path / "test.db"))
    try:
        blok = Blankiet(
            kurier="Testowy Kurier",
            data=date(2026, 8, 10),
            wiersze=[WierszBlankietu(nadawca="Żabka", adres="Testowa 1", rejon="WA1", ilosc_total=2)],
        )
        repo.zapisz_blankiet(app.conn, blok)
        app.zakladka_przeglad.odswiez()
        app.update()
        assert "1 transakcji" in app.zakladka_przeglad.etykieta_liczby.cget("text")
    finally:
        app.destroy()
        dziennik.odepnij()


# --- migawki + cofanie (`0.1-alpha.3`): zakładka Historia, operacje.wykonaj/cofnij ---

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
        wiersz = wprowadzanie.wiersze[0]
        wiersz.var_rejon.set("WA1")
        wiersz.var_nadawca.set("Żabka")
        wiersz.var_adres.set("Testowa 1")
        wiersz.var_ilosc_total.set("2")

        wprowadzanie.zapisz()

        # start aplikacji sam robi jeden wpis (naprawa_danych, patrz
        # test_start_aplikacji_naprawia_dane_i_loguje_operacje) - stąd
        # szukamy KONKRETNEGO wpisu, nie zakładamy, że jest jedyny
        wpisy = dziennik.wczytaj_operacje(app.katalog_danych)
        wpis_zapisu = wpisy[-1]
        assert wpis_zapisu["rodzaj"] == "zapis_blankietu"
        assert wpis_zapisu["liczba_wierszy"] == 1
        assert len(kopie.lista_migawek(app.katalog_danych)) == len(wpisy)
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

        # start aplikacji sam robi jeden wpis (naprawa_danych) - szukamy
        # ostatniego, nie zakładamy że jest jedyny
        wpisy = dziennik.wczytaj_operacje(app.katalog_danych)
        assert wpisy[-1]["rodzaj"] == "dodaj_slownik"
    finally:
        app.destroy()
        dziennik.odepnij()


def test_start_aplikacji_naprawia_dane_i_loguje_operacje(tmp_path):
    from zpo_tracker.gui.app import Aplikacja
    from zpo_tracker import dziennik
    from zpo_tracker.normalizacja import REJON_NIEZNANY

    # baza sprzed tej wersji: rejon "-" zamiast kanonicznego "???"
    sciezka = tmp_path / "test.db"
    przygotowanie = repo.polacz(str(sciezka))
    repo.utworz_schemat(przygotowanie)
    przygotowanie.execute("DELETE FROM rejony")
    przygotowanie.execute("INSERT INTO rejony (kod) VALUES ('-')")
    przygotowanie.close()

    app = Aplikacja(sciezka_bazy=str(sciezka))
    try:
        kody = [r[0] for r in app.conn.execute("SELECT kod FROM rejony")]
        assert kody == [REJON_NIEZNANY]

        wpisy = dziennik.wczytaj_operacje(app.katalog_danych)
        assert any(w["rodzaj"] == "naprawa_danych" for w in wpisy)
    finally:
        app.destroy()
        dziennik.odepnij()


def test_start_aplikacji_przezywa_awarie_naprawy_danych(tmp_path, monkeypatch):
    # naprawa danych NIE może zablokować startu aplikacji na stałe -
    # użytkownik bez uprawnień administratora i bez konsoli nie ma jak
    # tego obejść, gdyby awaria wystąpiła przy KAŻDYM uruchomieniu
    from zpo_tracker.gui import app as app_modul
    from zpo_tracker import dziennik, repo as repo_modul

    def _wybuchnij(conn):
        raise RuntimeError("awaria symulowana w naprawie danych")

    monkeypatch.setattr(repo_modul, "napraw_dane", _wybuchnij)

    app = app_modul.Aplikacja(sciezka_bazy=str(tmp_path / "test.db"))
    try:
        assert app.zakladka_przeglad is not None  # okno jednak powstało
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
        # 1 z dwóch starych (przycięte do kubełka "1-3 dni") + 1 świeża
        # migawka z naprawy_danych, która sama biegnie PRZED przycinaniem
        # (patrz app.py) - wiek ~0 dni, więc nigdy nie jest przycinana
        assert len(kopie.lista_migawek(katalog)) == 2
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


def test_main_druga_instancja_pokazuje_ostrzezenie_i_nie_otwiera_okna(tmp_path, monkeypatch):
    # jedna instancja na katalog danych (`0.1-alpha.3`) - main() musi wrócić PRZED
    # app.mainloop(), inaczej ten test zawiesiłby cały zestaw
    from zpo_tracker.gui import app as app_modul
    from zpo_tracker import blokada, dziennik

    monkeypatch.setattr(app_modul, "_katalog_danych", lambda *a, **k: tmp_path)
    trzymajaca = blokada.Blokada(tmp_path)
    trzymajaca.zdobadz()
    try:
        ostrzezenia = []
        monkeypatch.setattr(
            app_modul.messagebox, "showwarning",
            lambda tytul, tresc: ostrzezenia.append((tytul, tresc)))
        app_modul.main()
        assert len(ostrzezenia) == 1
    finally:
        trzymajaca.zwolnij()
        dziennik.odepnij()


def test_start_aplikacji_tworzy_dzisiejszy_zrzut(tmp_path):
    from datetime import date
    from zpo_tracker.gui.app import Aplikacja
    from zpo_tracker import dziennik, zrzuty

    app = Aplikacja(sciezka_bazy=str(tmp_path / "test.db"))
    try:
        assert zrzuty.istnieje_zrzut_na_dzien(tmp_path, date.today())
    finally:
        app.destroy()
        dziennik.odepnij()


def test_start_aplikacji_drugi_raz_tego_samego_dnia_nie_dubluje_zrzutu(tmp_path):
    from zpo_tracker.gui.app import Aplikacja
    from zpo_tracker import dziennik, zrzuty

    sciezka = str(tmp_path / "test.db")
    app1 = Aplikacja(sciezka_bazy=sciezka)
    app1.destroy()
    dziennik.odepnij()

    app2 = Aplikacja(sciezka_bazy=sciezka)
    try:
        assert len(list(zrzuty.katalog_zrzutow(tmp_path).glob("*.sql.gz"))) == 1
    finally:
        app2.destroy()
        dziennik.odepnij()


def test_zakladka_scalanie_istnieje(tmp_path):
    from zpo_tracker.gui.app import Aplikacja
    from zpo_tracker import dziennik

    app = Aplikacja(sciezka_bazy=str(tmp_path / "test.db"))
    try:
        assert app.zakladka_scalanie is not None
    finally:
        app.destroy()
        dziennik.odepnij()


def test_scalanie_end_to_end_dodaje_nowa_transakcje_i_loguje_operacje(tmp_path):
    from zpo_tracker.gui.app import Aplikacja
    from zpo_tracker import dziennik, repo as repo_modul, scalanie
    from zpo_tracker.gui.zakladka_scalanie import DialogKorektyScalania

    sciezka_zrodlowa = tmp_path / "zrodlo.db"
    zrodlowa = repo_modul.polacz(str(sciezka_zrodlowa))
    repo_modul.utworz_schemat(zrodlowa)
    kurier_id = zrodlowa.execute(
        "INSERT INTO kurierzy (imie_nazwisko) VALUES ('Nowak Piotr')").lastrowid
    punkt_id = zrodlowa.execute(
        "INSERT INTO punkty (nadawca, adres) VALUES ('Żabka', 'Odkryta 24')").lastrowid
    zrodlowa.execute(
        "INSERT INTO transakcje (data, kurier_id, punkt_id, ilosc_total, uuid)"
        " VALUES ('2026-08-01', ?, ?, 3, 'uuid-1')", (kurier_id, punkt_id))
    zrodlowa.close()

    app = Aplikacja(sciezka_bazy=str(tmp_path / "docelowa.db"))
    try:
        plan = scalanie.zaplanuj_scalenie(app.conn, sciezka_zrodlowa)
        wyniki = {}
        dialog = DialogKorektyScalania(
            app, app.conn, app.katalog_danych, sciezka_zrodlowa, plan,
            on_gotowe=lambda w: wyniki.setdefault("wynik", w),
        )
        dialog._zatwierdz()

        assert wyniki["wynik"]["dodano_transakcji"] == 1
        assert app.conn.execute(
            "SELECT COUNT(*) FROM transakcje").fetchone()[0] == 1

        wpisy = dziennik.wczytaj_operacje(app.katalog_danych)
        assert wpisy[-1]["rodzaj"] == "scalenie"
        assert wpisy[-1]["etykieta"] == "zrodlo.db"
    finally:
        app.destroy()
        dziennik.odepnij()


def test_scalanie_konflikt_domyslnie_zostawia_docelowa_przez_dialog(tmp_path):
    from zpo_tracker.gui.app import Aplikacja
    from zpo_tracker import dziennik, operacje, repo as repo_modul, scalanie
    from zpo_tracker.gui.zakladka_scalanie import DialogKorektyScalania

    sciezka_zrodlowa = tmp_path / "zrodlo.db"
    zrodlowa = repo_modul.polacz(str(sciezka_zrodlowa))
    repo_modul.utworz_schemat(zrodlowa)
    kurier_id = zrodlowa.execute(
        "INSERT INTO kurierzy (imie_nazwisko) VALUES ('Nowak Piotr')").lastrowid
    punkt_id = zrodlowa.execute(
        "INSERT INTO punkty (nadawca, adres) VALUES ('Żabka', 'Odkryta 24')").lastrowid
    zrodlowa.execute(
        "INSERT INTO transakcje (data, kurier_id, punkt_id, ilosc_total, uuid)"
        " VALUES ('2026-08-01', ?, ?, 5, 'uuid-1')", (kurier_id, punkt_id))
    zrodlowa.close()

    app = Aplikacja(sciezka_bazy=str(tmp_path / "docelowa.db"))
    try:
        def wstaw(conn, nazwa):
            conn.execute("INSERT INTO kurierzy (imie_nazwisko) VALUES (?)", (nazwa,))

        operacje.wykonaj(
            app.conn, app.katalog_danych, rodzaj="test", etykieta="e",
            funkcja=lambda conn: conn.execute(
                "INSERT INTO kurierzy (imie_nazwisko) VALUES ('Nowak Piotr')"))
        app.conn.execute("INSERT INTO punkty (nadawca, adres) VALUES ('Żabka', 'Odkryta 24')")
        app.conn.execute(
            "INSERT INTO transakcje (data, kurier_id, punkt_id, ilosc_total, uuid)"
            " VALUES ('2026-08-01', 1, 1, 3, 'uuid-docelowa')")

        plan = scalanie.zaplanuj_scalenie(app.conn, sciezka_zrodlowa)
        assert len(plan["transakcje"]["konflikty"]) == 1

        wyniki = {}
        dialog = DialogKorektyScalania(
            app, app.conn, app.katalog_danych, sciezka_zrodlowa, plan,
            on_gotowe=lambda w: wyniki.setdefault("wynik", w),
        )
        dialog._zatwierdz()  # bez klikania "weź źródłową" - domyślnie zostaje docelowa

        assert wyniki["wynik"]["rozstrzygnieto_konfliktow"] == 0
        assert app.conn.execute(
            "SELECT ilosc_total FROM transakcje").fetchone()[0] == 3
    finally:
        app.destroy()
        dziennik.odepnij()


def test_cofnij_do_przywraca_stan_i_zamyka_aplikacje(tmp_path):
    from zpo_tracker.gui.app import Aplikacja
    from zpo_tracker import dziennik, operacje, repo as repo_modul

    sciezka = str(tmp_path / "test.db")
    app = Aplikacja(sciezka_bazy=sciezka)
    try:
        blok = Blankiet(
            kurier="Testowy Kurier", data=date(2026, 8, 10),
            wiersze=[WierszBlankietu(nadawca="Żabka", adres="Testowa 1", rejon="WA1", ilosc_total=2)],
        )
        operacje.wykonaj(
            app.conn, app.katalog_danych, rodzaj="zapis_blankietu", etykieta="test",
            funkcja=repo_modul.zapisz_blankiet, args=(blok,),
        )
        seq = dziennik.wczytaj_operacje(app.katalog_danych)[-1]["seq"]

        app.cofnij_do(seq)  # zamyka `app` w środku (patrz Aplikacja.cofnij_do)

        po_cofnieciu = repo_modul.polacz(sciezka)
        assert po_cofnieciu.execute("SELECT COUNT(*) FROM transakcje").fetchone()[0] == 0
        po_cofnieciu.close()
    finally:
        dziennik.odepnij()
