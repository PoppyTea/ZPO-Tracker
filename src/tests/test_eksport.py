"""
Testy exportu do .xlsx: układ kolumn identyczny ze snapshotem źródłowym,
plus test wierności round-tripu na realnej próbce danych. TDD.
"""
from datetime import date
from pathlib import Path

import openpyxl
import pytest

from zpo_tracker import repo, eksport
from zpo_tracker.importer import import_row

REALNA_PROBKA = (
    Path(__file__).resolve().parent.parent.parent
    / "data" / "real-data-samples" / "2026-08-07-snapshot-ZPO.xlsx"
)


@pytest.fixture
def conn():
    conn = repo.polacz(":memory:")
    repo.utworz_schemat(conn)
    yield conn
    conn.close()


def _wstaw_prosta_transakcje(conn, **nadpisz):
    dane = dict(
        data="2026-08-03", kurier_id=None, punkt_id=None, rejon_id=None,
    )
    dane.update(nadpisz)
    kurier_id = conn.execute(
        "INSERT INTO kurierzy (imie_nazwisko) VALUES (?)", ("Kowalski Jan",)
    ).lastrowid
    punkt_id = conn.execute(
        "INSERT INTO punkty (nadawca, adres, pni_zpo) VALUES (?, ?, ?)",
        ("Żabka", "Odkryta 24", "228648"),
    ).lastrowid
    conn.execute(
        """INSERT INTO transakcje (data, kurier_id, punkt_id, ilosc_total, ilosc_zpo)
           VALUES (?, ?, ?, ?, ?)""",
        (dane["data"], kurier_id, punkt_id, 3, 3),
    )


def test_naglowki_identyczne_ze_snapshotem():
    assert eksport.NAGLOWKI[0] == "data"
    assert eksport.NAGLOWKI[3] == "Kurier"
    assert eksport.NAGLOWKI[7] == "PNI ZPO"
    assert eksport.NAGLOWKI[-1] == "Wykonawca"
    assert len(eksport.NAGLOWKI) == 13


def test_nazwa_arkusza_po_polsku():
    assert eksport.nazwa_arkusza(2026, 8) == "Sierpień"
    assert eksport.nazwa_arkusza(2026, 6) == "Czerwiec"


def test_eksportuj_miesiac_zapisuje_plik_z_poprawnym_arkuszem(conn, tmp_path):
    _wstaw_prosta_transakcje(conn)
    sciezka = tmp_path / "export.xlsx"
    liczba = eksport.eksportuj_miesiac(conn, 2026, 8, sciezka)
    assert liczba == 1

    wb = openpyxl.load_workbook(sciezka)
    assert wb.sheetnames == ["Sierpień"]
    ws = wb["Sierpień"]
    naglowki = [c.value for c in next(ws.iter_rows(min_row=1, max_row=1))]
    assert naglowki == eksport.NAGLOWKI

    wiersz = [c.value for c in next(ws.iter_rows(min_row=2, max_row=2))]
    assert wiersz[0].date() == date(2026, 8, 3)  # openpyxl zawsze odczytuje jako datetime
    assert wiersz[3] == "Kowalski Jan"
    assert wiersz[5] == 3  # ilosc_total jako int
    assert wiersz[7] == 228648  # PNI jako int, kanonicznie czyste


def test_eksportuj_miesiac_pomija_inne_miesiace(conn, tmp_path):
    _wstaw_prosta_transakcje(conn, data="2026-07-15")
    sciezka = tmp_path / "export.xlsx"
    liczba = eksport.eksportuj_miesiac(conn, 2026, 8, sciezka)
    assert liczba == 0


@pytest.mark.skipif(
    not REALNA_PROBKA.exists(),
    reason="wymaga realnej próbki danych (gitignored, patrz data/README.md)",
)
def test_round_trip_import_export_na_realnych_danych(conn, tmp_path):
    """
    Import realnego snapshotu -> export -> odczyt exportu -> porównanie
    liczby wierszy i typów komórek. Jedyny wiarygodny dowód wierności
    round-tripu (patrz plan MVP).
    """
    wb_zrodlo = openpyxl.load_workbook(REALNA_PROBKA, data_only=True)
    ws_zrodlo = wb_zrodlo["Czerwiec"]
    naglowki = [c.value for c in next(ws_zrodlo.iter_rows(min_row=1, max_row=1))]

    zaimportowano = 0
    for wartosci in ws_zrodlo.iter_rows(min_row=2, values_only=True):
        wiersz = dict(zip(naglowki, wartosci))
        wynik = import_row(conn, wiersz)
        if not wynik["skipped"]:
            zaimportowano += 1

    assert zaimportowano > 1000  # rząd wielkości z docs/backlog.md (1239)

    sciezka = tmp_path / "export.xlsx"
    liczba_wyeksportowanych = eksport.eksportuj_miesiac(conn, 2026, 8, sciezka)
    assert liczba_wyeksportowanych == zaimportowano

    wb_export = openpyxl.load_workbook(sciezka)
    ws_export = wb_export["Sierpień"]
    naglowki_export = [c.value for c in next(ws_export.iter_rows(min_row=1, max_row=1))]
    assert naglowki_export == eksport.NAGLOWKI

    # typy komórek: kanonicznie czyste, nie odtwarzają niespójności źródła
    for row in ws_export.iter_rows(min_row=2):
        assert isinstance(row[0].value, date)          # data
        assert isinstance(row[5].value, int)            # ilosc_total
        if row[7].value is not None:                    # PNI ZPO
            assert isinstance(row[7].value, int)
