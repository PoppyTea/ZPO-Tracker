"""
Zrzuty .sql.gz: warstwa zimna (osobna od migawek binarnych w kopie.py -
te są długotrwałym, przenośnym archiwum, nie przycinane) i format wymiany
dla przyszłej synchronizacji między stacjami (X+3, patrz roadmap.md).
Zwykły tekstowy SQL (conn.iterdump), gzipowany - czytelny do inspekcji po
rozpakowaniu, przenośny między maszynami niezależnie od wersji SQLite. TDD.
"""
import gzip
import sqlite3
from datetime import date

import pytest

from zpo_tracker import repo, zrzuty


@pytest.fixture
def conn():
    conn = repo.polacz(":memory:")
    repo.utworz_schemat(conn)
    conn.execute("INSERT INTO kurierzy (imie_nazwisko) VALUES ('Kowalski Jan')")
    yield conn
    conn.close()


def test_katalog_zrzutow_tworzy_podkatalog(tmp_path):
    katalog = zrzuty.katalog_zrzutow(tmp_path)
    assert katalog == tmp_path / "zrzuty"
    assert katalog.is_dir()


def test_zrob_zrzut_tworzy_plik_sql_gz(conn, tmp_path):
    plik = zrzuty.zrob_zrzut(conn, tmp_path, dzis=date(2026, 8, 11))
    assert plik.exists()
    assert plik.suffix == ".gz"


def test_zrob_zrzut_nazwa_zawiera_date(conn, tmp_path):
    plik = zrzuty.zrob_zrzut(conn, tmp_path, dzis=date(2026, 8, 11))
    assert "2026-08-11" in plik.name


def test_zrob_zrzut_zawiera_dane_jako_czysty_sql_po_gzip(conn, tmp_path):
    plik = zrzuty.zrob_zrzut(conn, tmp_path, dzis=date(2026, 8, 11))
    tresc = gzip.decompress(plik.read_bytes()).decode("utf-8")
    assert "CREATE TABLE" in tresc
    assert "Kowalski Jan" in tresc


def test_zrob_zrzut_domyslnie_uzywa_dzisiejszej_daty(conn, tmp_path):
    plik = zrzuty.zrob_zrzut(conn, tmp_path)
    assert date.today().isoformat() in plik.name


def test_zrob_zrzut_ten_sam_dzien_nadpisuje_a_nie_dubluje(conn, tmp_path):
    zrzuty.zrob_zrzut(conn, tmp_path, dzis=date(2026, 8, 11))
    zrzuty.zrob_zrzut(conn, tmp_path, dzis=date(2026, 8, 11))
    assert len(list(zrzuty.katalog_zrzutow(tmp_path).glob("*.sql.gz"))) == 1


def test_istnieje_zrzut_na_dzis(conn, tmp_path):
    assert zrzuty.istnieje_zrzut_na_dzien(tmp_path, date(2026, 8, 11)) is False
    zrzuty.zrob_zrzut(conn, tmp_path, dzis=date(2026, 8, 11))
    assert zrzuty.istnieje_zrzut_na_dzien(tmp_path, date(2026, 8, 11)) is True


def test_wczytaj_zrzut_odtwarza_dane_w_swiezym_polaczeniu(conn, tmp_path):
    plik = zrzuty.zrob_zrzut(conn, tmp_path, dzis=date(2026, 8, 11))

    docelowe = sqlite3.connect(":memory:")
    zrzuty.wczytaj_zrzut(plik, docelowe)

    wiersz = docelowe.execute(
        "SELECT imie_nazwisko FROM kurierzy").fetchone()
    assert wiersz[0] == "Kowalski Jan"
    docelowe.close()


def test_wczytaj_zrzut_zachowuje_wersje_schematu(conn, tmp_path):
    # PRAGMA user_version NIE jest częścią conn.iterdump() (nie jest DDL/DML
    # w tabelach) - musi być odtworzona jawnie, inaczej odzyskana baza
    # wygląda jak nowa/niemigrowana
    plik = zrzuty.zrob_zrzut(conn, tmp_path, dzis=date(2026, 8, 11))

    docelowe = sqlite3.connect(":memory:")
    zrzuty.wczytaj_zrzut(plik, docelowe)

    assert docelowe.execute("PRAGMA user_version").fetchone()[0] == repo.WERSJA_SCHEMATU
    docelowe.close()
