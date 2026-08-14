"""
Ręczne scalanie dwóch baz: docelowa (żywa) WCHŁANIA źródłową (plik .db,
NIETKNIĘTY - scalenie jednokierunkowe). Reguła z roadmap.md, nigdy nie
łamana: konflikt wartości (ta sama trójka data+kurier+punkt, różne ilości)
NIGDY nie jest rozstrzygany automatycznie. TDD.
"""
import sqlite3
from datetime import date

import pytest

from zpo_tracker import repo, scalanie
from zpo_tracker.normalizacja import REJON_NIEZNANY


@pytest.fixture
def docelowa():
    conn = repo.polacz(":memory:")
    repo.utworz_schemat(conn)
    yield conn
    conn.close()


@pytest.fixture
def zrodlowa():
    conn = repo.polacz(":memory:")
    repo.utworz_schemat(conn)
    yield conn
    conn.close()


@pytest.fixture
def plik_zrodlowy(tmp_path):
    """Baza źródłowa jako PLIK - zaplanuj_scalenie/wykonaj_scalenie
    otwierają źródło po ścieżce, nie po gotowym połączeniu."""
    sciezka = tmp_path / "zrodlo.db"
    conn = repo.polacz(str(sciezka))
    repo.utworz_schemat(conn)
    yield sciezka, conn
    conn.close()


# --- _dopasuj_prosty_slownik ---

def test_dopasowanie_identyczne_po_bialych_znakach(docelowa, zrodlowa):
    docelowa.execute("INSERT INTO kurierzy (imie_nazwisko) VALUES ('Kowalski Jan')")
    zrodlowa.execute("INSERT INTO kurierzy (imie_nazwisko) VALUES ('Kowalski Jan')")

    wynik = scalanie._dopasuj_prosty_slownik(docelowa, zrodlowa, "kurierzy", "imie_nazwisko")

    assert len(wynik["mapowanie"]) == 1
    assert wynik["nowe"] == []
    assert wynik["propozycje"] == []
    assert wynik["ostrzezenia"] == []


def test_dopasowanie_nowy_wpis_w_zrodle(docelowa, zrodlowa):
    zrodlowa.execute("INSERT INTO kurierzy (imie_nazwisko) VALUES ('Nowak Piotr')")

    wynik = scalanie._dopasuj_prosty_slownik(docelowa, zrodlowa, "kurierzy", "imie_nazwisko")

    assert wynik["mapowanie"] == {}
    assert len(wynik["nowe"]) == 1
    assert wynik["nowe"][0]["nazwa"] == "Nowak Piotr"


def test_dopasowanie_rejonu_smieciowego_trafia_w_kanoniczny_wiersz_celu(docelowa, zrodlowa):
    # źródło ma rejon "-" wpisany bezpośrednio (np. stara baza sprzed tej
    # reguły) - MUSI trafić w kanoniczny "???" celu (oba mają go od schema.sql),
    # nie stać się osobnym nowym wpisem "-" w celu
    zrodlowa.execute("INSERT INTO rejony (kod) VALUES ('-')")

    wynik = scalanie._dopasuj_prosty_slownik(docelowa, zrodlowa, "rejony", "kod")

    id_zrodlowy = zrodlowa.execute("SELECT id FROM rejony WHERE kod='-'").fetchone()[0]
    id_docelowy_kanoniczny = docelowa.execute(
        f"SELECT id FROM rejony WHERE kod='{REJON_NIEZNANY}'").fetchone()[0]
    assert wynik["mapowanie"][id_zrodlowy] == id_docelowy_kanoniczny
    assert wynik["nowe"] == []


def test_dopasowanie_diakrytyki_to_ostrzezenie_nie_automat(docelowa, zrodlowa):
    docelowa.execute("INSERT INTO kurierzy (imie_nazwisko) VALUES ('Wołczuk Rafał')")
    zrodlowa.execute("INSERT INTO kurierzy (imie_nazwisko) VALUES ('Wołczuk Rafal')")

    wynik = scalanie._dopasuj_prosty_slownik(docelowa, zrodlowa, "kurierzy", "imie_nazwisko")

    assert wynik["mapowanie"] == {}
    assert wynik["nowe"] == []
    assert len(wynik["ostrzezenia"]) == 1
    assert wynik["ostrzezenia"][0]["zrodlowa"] == "Wołczuk Rafal"
    assert wynik["ostrzezenia"][0]["docelowa"] == "Wołczuk Rafał"


def test_dopasowanie_literowka_to_propozycja_gdy_wlaczone(docelowa, zrodlowa):
    docelowa.execute("INSERT INTO kurierzy (imie_nazwisko) VALUES ('Kowalski')")
    zrodlowa.execute("INSERT INTO kurierzy (imie_nazwisko) VALUES ('Kowalksi')")  # transpozycja

    wynik = scalanie._dopasuj_prosty_slownik(
        docelowa, zrodlowa, "kurierzy", "imie_nazwisko", wykryj_literowki=True)

    assert len(wynik["propozycje"]) == 1
    assert wynik["propozycje"][0]["z"] == "Kowalksi"
    assert wynik["propozycje"][0]["na"] == "Kowalski"


def test_dopasowanie_literowka_bez_wlaczonego_wykrywania_ląduje_jako_nowa(docelowa, zrodlowa):
    # wykonawcy/rejony/firmy_zpo NIE dostają wykrywania literówek - to
    # świadome, wąskie rozwiązanie tylko dla kurierów (docs/domain-model.md)
    docelowa.execute("INSERT INTO wykonawcy (nazwa) VALUES ('Koli')")
    zrodlowa.execute("INSERT INTO wykonawcy (nazwa) VALUES ('Kolii')")

    wynik = scalanie._dopasuj_prosty_slownik(docelowa, zrodlowa, "wykonawcy", "nazwa")

    assert wynik["propozycje"] == []
    assert len(wynik["nowe"]) == 1


# --- _dopasuj_uzytkownikow ---

def test_uzytkownik_nowy_w_zrodle(docelowa, zrodlowa):
    zrodlowa.execute(
        "INSERT INTO users (id, login, alias, nr_kadrowy) VALUES (?, ?, ?, ?)",
        ("uid-1", "POCZTA\\jnowak", "Jan Nowak", "ab12X"),
    )

    wynik = scalanie._dopasuj_uzytkownikow(docelowa, zrodlowa)

    assert len(wynik["nowi"]) == 1
    assert wynik["nowi"][0]["id"] == "uid-1"
    assert wynik["ostrzezenia"] == []


def test_uzytkownik_juz_w_obu_bez_konfliktu(docelowa, zrodlowa):
    for conn in (docelowa, zrodlowa):
        conn.execute(
            "INSERT INTO users (id, login, alias, nr_kadrowy) VALUES (?, ?, ?, ?)",
            ("uid-1", "POCZTA\\jnowak", "Jan Nowak", "ab12X"),
        )

    wynik = scalanie._dopasuj_uzytkownikow(docelowa, zrodlowa)

    assert wynik["nowi"] == []
    assert wynik["ostrzezenia"] == []


def test_uzytkownik_ten_sam_id_inny_nr_kadrowy_to_ostrzezenie(docelowa, zrodlowa):
    docelowa.execute(
        "INSERT INTO users (id, login, alias, nr_kadrowy) VALUES (?, ?, ?, ?)",
        ("uid-1", "POCZTA\\jnowak", "Jan Nowak", "ab12X"),
    )
    zrodlowa.execute(
        "INSERT INTO users (id, login, alias, nr_kadrowy) VALUES (?, ?, ?, ?)",
        ("uid-1", "POCZTA\\jnowak", "Jan Nowak", "cd34Y"),
    )

    wynik = scalanie._dopasuj_uzytkownikow(docelowa, zrodlowa)

    assert wynik["nowi"] == []
    assert len(wynik["ostrzezenia"]) == 1


# --- pełny przepływ: zaplanuj_scalenie + wykonaj_scalenie ---

def _wstaw_transakcje(conn, kurier, nadawca, adres, data_, ilosc, pni=None):
    kurier_id = conn.execute(
        "INSERT INTO kurierzy (imie_nazwisko) VALUES (?)", (kurier,)
    ).lastrowid if not conn.execute(
        "SELECT id FROM kurierzy WHERE imie_nazwisko = ?", (kurier,)
    ).fetchone() else conn.execute(
        "SELECT id FROM kurierzy WHERE imie_nazwisko = ?", (kurier,)
    ).fetchone()[0]
    punkt = conn.execute(
        "SELECT id FROM punkty WHERE nadawca = ? AND adres = ?", (nadawca, adres)
    ).fetchone()
    punkt_id = punkt[0] if punkt else conn.execute(
        "INSERT INTO punkty (nadawca, adres, pni_zpo) VALUES (?, ?, ?)",
        (nadawca, adres, pni),
    ).lastrowid
    conn.execute(
        "INSERT INTO transakcje (data, kurier_id, punkt_id, ilosc_total, uuid)"
        " VALUES (?, ?, ?, ?, ?)",
        (data_.isoformat(), kurier_id, punkt_id, ilosc, f"uuid-{kurier}-{data_}-{ilosc}"),
    )


def test_zaplanuj_scalenie_zrodlo_pozostaje_nietkniete(docelowa, plik_zrodlowy):
    sciezka, zrodlowa = plik_zrodlowy
    _wstaw_transakcje(zrodlowa, "Nowak Piotr", "Żabka", "Odkryta 24", date(2026, 8, 1), 3)

    scalanie.zaplanuj_scalenie(docelowa, sciezka)

    # nic nie mogło zostać dopisane do źródła - otwarte read-only
    assert zrodlowa.execute("SELECT COUNT(*) FROM transakcje").fetchone()[0] == 1


def test_zaplanuj_scalenie_klasyfikuje_nowa_transakcje(docelowa, plik_zrodlowy):
    sciezka, zrodlowa = plik_zrodlowy
    _wstaw_transakcje(zrodlowa, "Nowak Piotr", "Żabka", "Odkryta 24", date(2026, 8, 1), 3)

    plan = scalanie.zaplanuj_scalenie(docelowa, sciezka)

    assert len(plan["transakcje"]["nowe"]) == 1
    assert plan["transakcje"]["duplikaty"] == []
    assert plan["transakcje"]["konflikty"] == []


def test_zaplanuj_scalenie_klasyfikuje_duplikat(docelowa, plik_zrodlowy):
    sciezka, zrodlowa = plik_zrodlowy
    for conn in (docelowa, zrodlowa):
        _wstaw_transakcje(conn, "Nowak Piotr", "Żabka", "Odkryta 24", date(2026, 8, 1), 3)

    plan = scalanie.zaplanuj_scalenie(docelowa, sciezka)

    assert plan["transakcje"]["nowe"] == []
    assert len(plan["transakcje"]["duplikaty"]) == 1
    assert plan["transakcje"]["konflikty"] == []


def test_zaplanuj_scalenie_klasyfikuje_konflikt(docelowa, plik_zrodlowy):
    sciezka, zrodlowa = plik_zrodlowy
    _wstaw_transakcje(docelowa, "Nowak Piotr", "Żabka", "Odkryta 24", date(2026, 8, 1), 3)
    _wstaw_transakcje(zrodlowa, "Nowak Piotr", "Żabka", "Odkryta 24", date(2026, 8, 1), 5)

    plan = scalanie.zaplanuj_scalenie(docelowa, sciezka)

    assert plan["transakcje"]["nowe"] == []
    assert plan["transakcje"]["duplikaty"] == []
    assert len(plan["transakcje"]["konflikty"]) == 1
    assert plan["transakcje"]["konflikty"][0]["zrodlowa"]["ilosc_total"] == 5
    assert plan["transakcje"]["konflikty"][0]["docelowa"]["ilosc_total"] == 3


def test_zaplanuj_scalenie_konflikt_ma_czytelne_dane_do_wyswietlenia(docelowa, plik_zrodlowy):
    # GUI nie może pokazywać surowych FK id - potrzebuje nazwy kuriera,
    # punktu i id transakcji źródłowej (do rozstrzygniecia_konfliktow)
    sciezka, zrodlowa = plik_zrodlowy
    _wstaw_transakcje(docelowa, "Nowak Piotr", "Żabka", "Odkryta 24", date(2026, 8, 1), 3)
    _wstaw_transakcje(zrodlowa, "Nowak Piotr", "Żabka", "Odkryta 24", date(2026, 8, 1), 5)
    id_zrodlowej = zrodlowa.execute("SELECT id FROM transakcje").fetchone()[0]

    plan = scalanie.zaplanuj_scalenie(docelowa, sciezka)
    konflikt = plan["transakcje"]["konflikty"][0]

    assert konflikt["id_transakcji_zrodlowej"] == id_zrodlowej
    assert konflikt["kurier"] == "Nowak Piotr"
    assert konflikt["punkt"] == "Żabka / Odkryta 24"
    assert konflikt["data"] == "2026-08-01"


def test_wykonaj_scalenie_dodaje_nowa_transakcje_z_nowym_kurierem_i_punktem(docelowa, plik_zrodlowy):
    sciezka, zrodlowa = plik_zrodlowy
    _wstaw_transakcje(zrodlowa, "Nowak Piotr", "Żabka", "Odkryta 24", date(2026, 8, 1), 3)

    wynik = scalanie.wykonaj_scalenie(docelowa, sciezka)

    assert wynik["dodano_transakcji"] == 1
    wiersz = docelowa.execute(
        "SELECT k.imie_nazwisko, p.nadawca, t.ilosc_total FROM transakcje t"
        " JOIN kurierzy k ON k.id = t.kurier_id JOIN punkty p ON p.id = t.punkt_id"
    ).fetchone()
    assert wiersz["imie_nazwisko"] == "Nowak Piotr"
    assert wiersz["ilosc_total"] == 3


def test_wykonaj_scalenie_pomija_prawdziwy_duplikat(docelowa, plik_zrodlowy):
    sciezka, zrodlowa = plik_zrodlowy
    for conn in (docelowa, zrodlowa):
        _wstaw_transakcje(conn, "Nowak Piotr", "Żabka", "Odkryta 24", date(2026, 8, 1), 3)

    wynik = scalanie.wykonaj_scalenie(docelowa, sciezka)

    assert wynik["dodano_transakcji"] == 0
    assert wynik["pominieto_duplikatow"] == 1
    assert docelowa.execute("SELECT COUNT(*) FROM transakcje").fetchone()[0] == 1


def test_wykonaj_scalenie_konflikt_domyslnie_zostawia_wartosc_docelowa(docelowa, plik_zrodlowy):
    sciezka, zrodlowa = plik_zrodlowy
    _wstaw_transakcje(docelowa, "Nowak Piotr", "Żabka", "Odkryta 24", date(2026, 8, 1), 3)
    _wstaw_transakcje(zrodlowa, "Nowak Piotr", "Żabka", "Odkryta 24", date(2026, 8, 1), 5)

    wynik = scalanie.wykonaj_scalenie(docelowa, sciezka)

    assert wynik["rozstrzygnieto_konfliktow"] == 0
    assert docelowa.execute(
        "SELECT ilosc_total FROM transakcje").fetchone()[0] == 3  # docelowa, NIE nadpisana


def test_wykonaj_scalenie_konflikt_jawnie_wybrana_wartosc_zrodlowa(docelowa, plik_zrodlowy):
    sciezka, zrodlowa = plik_zrodlowy
    _wstaw_transakcje(docelowa, "Nowak Piotr", "Żabka", "Odkryta 24", date(2026, 8, 1), 3)
    _wstaw_transakcje(zrodlowa, "Nowak Piotr", "Żabka", "Odkryta 24", date(2026, 8, 1), 5)
    id_zrodlowej = zrodlowa.execute("SELECT id FROM transakcje").fetchone()[0]

    wynik = scalanie.wykonaj_scalenie(
        docelowa, sciezka,
        rozstrzygniecia_konfliktow={id_zrodlowej: "zrodlowa"},
    )

    assert wynik["rozstrzygnieto_konfliktow"] == 1
    assert docelowa.execute(
        "SELECT ilosc_total FROM transakcje").fetchone()[0] == 5


def test_wykonaj_scalenie_dopasowuje_istniejacego_kuriera_po_bialych_znakach(docelowa, plik_zrodlowy):
    sciezka, zrodlowa = plik_zrodlowy
    docelowa.execute("INSERT INTO kurierzy (imie_nazwisko) VALUES ('Nowak Piotr')")
    _wstaw_transakcje(zrodlowa, "Nowak Piotr", "Żabka", "Odkryta 24", date(2026, 8, 1), 3)

    scalanie.wykonaj_scalenie(docelowa, sciezka)

    assert docelowa.execute("SELECT COUNT(*) FROM kurierzy").fetchone()[0] == 1


def test_wykonaj_scalenie_wiele_smieciowych_rejonow_bez_kanonicznego_wiersza_w_celu(
        docelowa, plik_zrodlowy):
    # symulacja baz sprzed zaseedowania "???" (repo.napraw_dane jeszcze nie
    # uruchomiona na żadnej z nich) - bez get_or_create_rejon przy wstawianiu
    # "nowych" wpisów słownikowych trzy różne id o różnej pisowni śmiecia
    # dają trzy kolejne INSERT tego samego znormalizowanego kodu -> kolizja
    # UNIQUE -> IntegrityError -> repo.transakcja wycofuje CAŁE scalenie
    docelowa.execute("DELETE FROM rejony")
    sciezka, zrodlowa = plik_zrodlowy
    zrodlowa.execute("DELETE FROM rejony")
    for smiec in ("-", "n/a", "?"):
        zrodlowa.execute("INSERT INTO rejony (kod) VALUES (?)", (smiec,))
    zrodlowa.commit()

    scalanie.wykonaj_scalenie(docelowa, sciezka)  # nie może rzucić IntegrityError

    kody = [r[0] for r in docelowa.execute("SELECT kod FROM rejony")]
    assert kody == [REJON_NIEZNANY]  # wszystkie trzy zjechały się w jeden wiersz


def test_wykonaj_scalenie_transakcja_z_null_rejonem_dostaje_kanoniczny(docelowa, plik_zrodlowy):
    # źródło z transakcją bez rejonu w ogóle (rejon_id IS NULL - stara,
    # niereperowana baza sprzed tej reguły) - scalenie NIE może przepisać
    # tego NULL-a wprost do bazy docelowej, która ma już naprawione dane
    sciezka, zrodlowa = plik_zrodlowy
    kurier_id = zrodlowa.execute(
        "INSERT INTO kurierzy (imie_nazwisko) VALUES ('Nowak Piotr')").lastrowid
    punkt_id = zrodlowa.execute(
        "INSERT INTO punkty (nadawca, adres) VALUES ('Żabka', 'Odkryta 24')").lastrowid
    zrodlowa.execute(
        "INSERT INTO transakcje (data, kurier_id, punkt_id, rejon_id, ilosc_total, uuid)"
        " VALUES ('2026-08-01', ?, ?, NULL, 3, 'uuid-1')", (kurier_id, punkt_id))
    zrodlowa.commit()

    scalanie.wykonaj_scalenie(docelowa, sciezka)

    kod = docelowa.execute(
        "SELECT r.kod FROM transakcje t JOIN rejony r ON r.id = t.rejon_id"
    ).fetchone()[0]
    assert kod == REJON_NIEZNANY


def test_wykonaj_scalenie_jest_atomowe(docelowa, plik_zrodlowy):
    # awaria w trakcie nie może zostawić bazy w stanie połowicznym
    sciezka, zrodlowa = plik_zrodlowy
    _wstaw_transakcje(zrodlowa, "Nowak Piotr", "Żabka", "Odkryta 24", date(2026, 8, 1), 3)

    with pytest.raises(RuntimeError):
        with repo.transakcja(docelowa):
            scalanie._wykonaj_scalenie_bez_transakcji(
                docelowa, scalanie._otworz_zrodlo_tylko_do_odczytu(sciezka),
                set(), {}, {},
            )
            raise RuntimeError("awaria symulowana W ŚRODKU scalenia")

    assert docelowa.execute("SELECT COUNT(*) FROM transakcje").fetchone()[0] == 0
    assert docelowa.execute("SELECT COUNT(*) FROM kurierzy").fetchone()[0] == 0


def test_wykonaj_scalenie_kopiuje_atrybucje_ze_zrodla(docelowa, plik_zrodlowy):
    sciezka, zrodlowa = plik_zrodlowy
    zrodlowa.execute(
        "INSERT INTO users (id, login, alias, nr_kadrowy) VALUES (?, ?, ?, ?)",
        ("uid-1", "POCZTA\\jnowak", "Jan Nowak", "ab12X"),
    )
    kurier_id = zrodlowa.execute(
        "INSERT INTO kurierzy (imie_nazwisko) VALUES ('Nowak Piotr')").lastrowid
    punkt_id = zrodlowa.execute(
        "INSERT INTO punkty (nadawca, adres) VALUES ('Żabka', 'Odkryta 24')").lastrowid
    zrodlowa.execute(
        "INSERT INTO transakcje (data, kurier_id, punkt_id, ilosc_total, uuid, autor_id, utworzono)"
        " VALUES (?, ?, ?, ?, ?, ?, ?)",
        ("2026-08-01", kurier_id, punkt_id, 3, "uuid-oryginalny", "uid-1", "2026-08-01T09:00:00"),
    )

    scalanie.wykonaj_scalenie(docelowa, sciezka)

    wiersz = docelowa.execute(
        "SELECT autor_id, uuid, utworzono FROM transakcje").fetchone()
    assert wiersz["autor_id"] == "uid-1"
    assert wiersz["uuid"] == "uuid-oryginalny"
    assert wiersz["utworzono"] == "2026-08-01T09:00:00"


def test_wykonaj_scalenie_przenosi_sesje_i_zrodlo_ze_zrodla(docelowa, plik_zrodlowy):
    # pochodzenie wiersza to miejsce, gdzie POWSTAŁ - scalenie go przenosi,
    # nie nadpisuje wartością "scalanie" (patrz roadmap.md/repo.py)
    sciezka, zrodlowa = plik_zrodlowy
    kurier_id = zrodlowa.execute(
        "INSERT INTO kurierzy (imie_nazwisko) VALUES ('Nowak Piotr')").lastrowid
    punkt_id = zrodlowa.execute(
        "INSERT INTO punkty (nadawca, adres) VALUES ('Żabka', 'Odkryta 24')").lastrowid
    zrodlowa.execute(
        "INSERT INTO transakcje (data, kurier_id, punkt_id, ilosc_total, sesja_uuid, zrodlo)"
        " VALUES (?, ?, ?, ?, ?, ?)",
        ("2026-08-01", kurier_id, punkt_id, 3, "sesja-zrodlowa", "formularz"),
    )

    scalanie.wykonaj_scalenie(docelowa, sciezka)

    wiersz = docelowa.execute("SELECT sesja_uuid, zrodlo FROM transakcje").fetchone()
    assert wiersz["sesja_uuid"] == "sesja-zrodlowa"
    assert wiersz["zrodlo"] == "formularz"


def _zrodlo_plikowa_v2(tmp_path):
    """
    Baza źródłowa w kształcie sprzed `0.1-alpha.3.2`: ma już users +
    atrybucję (alpha.3) i indeksy dedukcji (alpha.3.1), ale NIE ma
    sesja_uuid/zrodlo. `wykonaj_scalenie` (`w.get(...)` w `scalanie.py`)
    musi to przeżyć bez wybuchania - brakujące kolumny stają się NULL.
    """
    sciezka = tmp_path / "zrodlo_v2.db"
    conn = sqlite3.connect(str(sciezka))
    conn.row_factory = sqlite3.Row
    conn.executescript("""
        PRAGMA foreign_keys = ON;
        CREATE TABLE kurierzy (id INTEGER PRIMARY KEY, imie_nazwisko TEXT NOT NULL UNIQUE);
        CREATE TABLE rejony (id INTEGER PRIMARY KEY, kod TEXT NOT NULL UNIQUE);
        INSERT INTO rejony (kod) VALUES ('???');
        CREATE TABLE wykonawcy (id INTEGER PRIMARY KEY, nazwa TEXT NOT NULL UNIQUE);
        CREATE TABLE firmy_zpo (id INTEGER PRIMARY KEY, nazwa TEXT NOT NULL UNIQUE);
        CREATE TABLE punkty (
            id INTEGER PRIMARY KEY, nadawca TEXT NOT NULL, adres TEXT NOT NULL,
            pni_zpo TEXT UNIQUE, firma_zpo_id INTEGER REFERENCES firmy_zpo(id));
        CREATE TABLE users (
            id TEXT PRIMARY KEY, login TEXT NOT NULL UNIQUE,
            alias TEXT, nr_kadrowy TEXT UNIQUE, utworzono TEXT);
        CREATE TABLE transakcje (
            id INTEGER PRIMARY KEY, data TEXT NOT NULL,
            kurier_id INTEGER NOT NULL REFERENCES kurierzy(id),
            punkt_id INTEGER NOT NULL REFERENCES punkty(id),
            rejon_id INTEGER REFERENCES rejony(id),
            wykonawca_id INTEGER REFERENCES wykonawcy(id),
            ilosc_total INTEGER NOT NULL, ilosc_zpo INTEGER,
            ilosc_vinted INTEGER, ilosc_automaty INTEGER,
            ilosc_kurier48 INTEGER, ilosc_niezrealizowane INTEGER,
            komentarz TEXT, uuid TEXT UNIQUE,
            autor_id TEXT REFERENCES users(id), utworzono TEXT, zmodyfikowano TEXT,
            UNIQUE(data, kurier_id, punkt_id));
        PRAGMA user_version = 2;
    """)
    conn.commit()
    return sciezka, conn


def test_wykonaj_scalenie_ze_zrodla_v2_bez_kolumn_sesji_daje_null(docelowa, tmp_path):
    sciezka, zrodlowa = _zrodlo_plikowa_v2(tmp_path)
    kurier_id = zrodlowa.execute(
        "INSERT INTO kurierzy (imie_nazwisko) VALUES ('Nowak Piotr')").lastrowid
    punkt_id = zrodlowa.execute(
        "INSERT INTO punkty (nadawca, adres) VALUES ('Żabka', 'Odkryta 24')").lastrowid
    zrodlowa.execute(
        "INSERT INTO transakcje (data, kurier_id, punkt_id, ilosc_total)"
        " VALUES (?, ?, ?, ?)",
        ("2026-08-01", kurier_id, punkt_id, 3),
    )
    zrodlowa.commit()
    zrodlowa.close()

    scalanie.wykonaj_scalenie(docelowa, sciezka)

    wiersz = docelowa.execute("SELECT sesja_uuid, zrodlo FROM transakcje").fetchone()
    assert wiersz["sesja_uuid"] is None
    assert wiersz["zrodlo"] is None
