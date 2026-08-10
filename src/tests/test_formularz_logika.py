"""
Logika przygotowania bloków formularza wprowadzania do zapisu - czysta,
bez GUI. TDD.
"""
import pytest
from pydantic import ValidationError

from zpo_tracker.gui.formularz_logika import zbuduj_bloki


def test_zbuduj_bloki_pojedynczy_blok_z_dwoma_wierszami():
    bloki = zbuduj_bloki("Kowalski Jan", "Koli", [{
        "rejon": "WA87", "data": "2026-08-10", "komentarz": None,
        "wiersze": [
            {"nadawca": "Żabka", "adres": "Odkryta 24", "ilosc_total": 3},
            {"nadawca": "ZUS", "adres": "Senatorska 6/8", "ilosc_total": 1},
        ],
    }])
    assert len(bloki) == 1
    assert len(bloki[0].wiersze) == 2
    assert bloki[0].wykonawca == "Koli"


def test_zbuduj_bloki_pomija_puste_wiersze_placeholder():
    bloki = zbuduj_bloki("Kowalski Jan", None, [{
        "rejon": "WA87", "data": "2026-08-10", "komentarz": None,
        "wiersze": [
            {"nadawca": "Żabka", "adres": "Odkryta 24", "ilosc_total": 3},
            {"nadawca": "", "adres": "", "ilosc_total": None},
        ],
    }])
    assert len(bloki[0].wiersze) == 1


def test_zbuduj_bloki_pomija_calkiem_pusty_blok():
    # np. dodany przyciskiem "dodaj rejon", ale nigdy nieuzupełniony
    bloki = zbuduj_bloki("Kowalski Jan", None, [
        {"rejon": "WA87", "data": "2026-08-10", "komentarz": None, "wiersze": [
            {"nadawca": "Żabka", "adres": "Odkryta 24", "ilosc_total": 3},
        ]},
        {"rejon": "ND1", "data": "2026-08-10", "komentarz": None, "wiersze": [
            {"nadawca": "", "adres": "", "ilosc_total": None},
        ]},
    ])
    assert len(bloki) == 1


def test_zbuduj_bloki_nieznany_rejon_i_komentarz():
    bloki = zbuduj_bloki("Kowalski Jan", None, [{
        "rejon": None, "data": "2026-08-10", "komentarz": "okolice Legionowa",
        "wiersze": [{"nadawca": "Żabka", "adres": "Odkryta 24", "ilosc_total": 3}],
    }])
    assert bloki[0].rejon is None
    assert bloki[0].komentarz == "okolice Legionowa"


def test_zbuduj_bloki_brak_ilosci_w_niepustym_wierszu_rzuca_blad():
    with pytest.raises(ValidationError):
        zbuduj_bloki("Kowalski Jan", None, [{
            "rejon": "WA87", "data": "2026-08-10", "komentarz": None,
            "wiersze": [{"nadawca": "Żabka", "adres": "Odkryta 24", "ilosc_total": None}],
        }])


def test_zbuduj_bloki_brak_kuriera_rzuca_blad():
    with pytest.raises(ValidationError):
        zbuduj_bloki("", None, [{
            "rejon": "WA87", "data": "2026-08-10", "komentarz": None,
            "wiersze": [{"nadawca": "Żabka", "adres": "Odkryta 24", "ilosc_total": 3}],
        }])
