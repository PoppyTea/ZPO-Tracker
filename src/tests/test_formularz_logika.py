"""
Logika przygotowania blankietu formularza wprowadzania do zapisu - czysta,
bez GUI. TDD.
"""
import pytest
from pydantic import ValidationError

from zpo_tracker.gui.formularz_logika import wiersz_pusty, zbuduj_blankiet


def test_zbuduj_blankiet_dwa_wiersze():
    blankiet = zbuduj_blankiet("Kowalski Jan", "2026-08-10", "Koli", [
        {"nadawca": "Żabka", "adres": "Odkryta 24", "rejon": "WA87", "ilosc_total": 3},
        {"nadawca": "ZUS", "adres": "Senatorska 6/8", "rejon": "WA87", "ilosc_total": 1},
    ])
    assert len(blankiet.wiersze) == 2
    assert blankiet.wykonawca == "Koli"
    assert blankiet.kurier == "Kowalski Jan"


def test_zbuduj_blankiet_pomija_puste_wiersze_placeholder():
    blankiet = zbuduj_blankiet("Kowalski Jan", "2026-08-10", None, [
        {"nadawca": "Żabka", "adres": "Odkryta 24", "ilosc_total": 3},
        {"nadawca": "", "adres": "", "ilosc_total": None},
    ])
    assert len(blankiet.wiersze) == 1


def test_zbuduj_blankiet_calkiem_pusty_zwraca_none():
    # np. wiersz dodany "+ wiersz", ale nigdy nieuzupełniony
    blankiet = zbuduj_blankiet("Kowalski Jan", "2026-08-10", None, [
        {"nadawca": "", "adres": "", "ilosc_total": None},
    ])
    assert blankiet is None


def test_zbuduj_blankiet_rejon_per_wiersz_moze_byc_rozny():
    # 0.1-alpha.3.1: rejon zszedł do wiersza, jeden blankiet może mieć
    # wiersze w różnych rejonach - to właśnie zastąpiło bloki REJON+DATA
    blankiet = zbuduj_blankiet("Kowalski Jan", "2026-08-10", None, [
        {"nadawca": "Żabka", "adres": "Odkryta 24", "rejon": "WA87", "ilosc_total": 3},
        {"nadawca": "ZUS", "adres": "Senatorska 6/8", "rejon": "WA88", "ilosc_total": 1},
    ])
    assert [w.rejon for w in blankiet.wiersze] == ["WA87", "WA88"]


def test_zbuduj_blankiet_nieznany_rejon_zostaje_none():
    # normalizacja do kanonicznego "???" dzieje się dopiero w repo, nie tu
    blankiet = zbuduj_blankiet("Kowalski Jan", "2026-08-10", None, [
        {"nadawca": "Żabka", "adres": "Odkryta 24", "rejon": None, "ilosc_total": 3},
    ])
    assert blankiet.wiersze[0].rejon is None


def test_zbuduj_blankiet_brak_ilosci_w_niepustym_wierszu_rzuca_blad():
    with pytest.raises(ValidationError):
        zbuduj_blankiet("Kowalski Jan", "2026-08-10", None, [
            {"nadawca": "Żabka", "adres": "Odkryta 24", "ilosc_total": None},
        ])


def test_zbuduj_blankiet_brak_kuriera_rzuca_blad():
    with pytest.raises(ValidationError):
        zbuduj_blankiet("", "2026-08-10", None, [
            {"nadawca": "Żabka", "adres": "Odkryta 24", "ilosc_total": 3},
        ])


# --- wiersz_pusty (0.1-alpha.3.2: publiczne, reużywane przy selektywnym
# czyszczeniu siatki po zapisie - patrz zakladka_wprowadzanie.py) ---

def test_wiersz_pusty_bez_nadawcy_i_adresu():
    assert wiersz_pusty({"nadawca": "", "adres": ""}) is True


def test_wiersz_pusty_falsz_gdy_ma_adres():
    assert wiersz_pusty({"nadawca": "", "adres": "Odkryta 24"}) is False


def test_wiersz_pusty_falsz_gdy_ma_nadawce():
    assert wiersz_pusty({"nadawca": "Żabka", "adres": ""}) is False
