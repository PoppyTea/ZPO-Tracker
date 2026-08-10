"""
Testy warstwy dostępu do danych: zapis bloku z formularza wprowadzania
i odczyt do przeglądania. SQLite w pamięci, bez mocków. TDD.
"""
from datetime import date

import pytest

from zpo_tracker import repo
from zpo_tracker.models import BlankietBlok, WierszBlankietu


@pytest.fixture
def conn():
    conn = repo.polacz(":memory:")
    repo.utworz_schemat(conn)
    yield conn
    conn.close()


def _blok(**nadpisz):
    dane = dict(
        kurier="Kowalski Jan",
        data=date(2026, 8, 10),
        rejon="WA87",
        wykonawca="Koli",
        komentarz=None,
        wiersze=[WierszBlankietu(nadawca="Żabka", adres="Odkryta 24", ilosc_total=3, ilosc_zpo=3)],
    )
    dane.update(nadpisz)
    return BlankietBlok(**dane)


def test_zapisz_blok_tworzy_jedna_transakcje_na_wiersz(conn):
    blok = _blok(wiersze=[
        WierszBlankietu(nadawca="Żabka", adres="Odkryta 24", ilosc_total=3),
        WierszBlankietu(nadawca="ZUS", adres="Senatorska 6/8", ilosc_total=1),
    ])
    wyniki = repo.zapisz_blok(conn, blok)
    assert len(wyniki) == 2
    assert all(not w["pominieto"] for w in wyniki)
    count = conn.execute("SELECT COUNT(*) FROM transakcje").fetchone()[0]
    assert count == 2


def test_zapisz_blok_z_nieznanym_rejonem_zapisuje_null(conn):
    blok = _blok(rejon=None, komentarz="rejon nieznany, okolice Legionowa")
    repo.zapisz_blok(conn, blok)
    row = conn.execute(
        "SELECT rejon_id, komentarz FROM transakcje LIMIT 1"
    ).fetchone()
    assert row[0] is None
    assert row[1] == "rejon nieznany, okolice Legionowa"


def test_zapisz_blok_ten_sam_komentarz_dla_calego_bloku(conn):
    blok = _blok(
        komentarz="uwaga wspólna",
        wiersze=[
            WierszBlankietu(nadawca="Żabka", adres="Odkryta 24", ilosc_total=3),
            WierszBlankietu(nadawca="ZUS", adres="Senatorska 6/8", ilosc_total=1),
        ],
    )
    repo.zapisz_blok(conn, blok)
    komentarze = [r[0] for r in conn.execute("SELECT komentarz FROM transakcje").fetchall()]
    assert komentarze == ["uwaga wspólna", "uwaga wspólna"]


def test_zapisz_blok_wykrywa_duplikat_bez_wybuchania(conn):
    blok = _blok()
    repo.zapisz_blok(conn, blok)
    wyniki = repo.zapisz_blok(conn, blok)  # ten sam blok drugi raz
    assert wyniki[0]["pominieto"] is True
    count = conn.execute("SELECT COUNT(*) FROM transakcje").fetchone()[0]
    assert count == 1


def test_zapisz_blok_reuzywa_istniejacego_kuriera(conn):
    repo.zapisz_blok(conn, _blok())
    repo.zapisz_blok(conn, _blok(data=date(2026, 8, 11)))
    count = conn.execute("SELECT COUNT(*) FROM kurierzy").fetchone()[0]
    assert count == 1


def test_pobierz_transakcje_zwraca_czytelne_nazwy(conn):
    repo.zapisz_blok(conn, _blok())
    wiersze = repo.pobierz_transakcje(conn)
    assert len(wiersze) == 1
    w = wiersze[0]
    assert w["kurier"] == "Kowalski Jan"
    assert w["nadawca"] == "Żabka"
    assert w["rejon"] == "WA87"
    assert w["ilosc_total"] == 3
