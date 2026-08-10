"""
Testy modeli pydantic v2 - walidacja na granicach (wiersz importu, blok
formularza), nie mirror tabel SQL. TDD.
"""
from datetime import date

import pytest
from pydantic import ValidationError

from zpo_tracker.models import WierszImportu, BlankietBlok, WierszBlankietu


# --- WierszImportu: walidacja wiersza z .xlsx ---

def test_wiersz_importu_poprawne_dane():
    w = WierszImportu(
        data=date(2026, 8, 3),
        nadawca="Żabka",
        adres="Solidarności 117",
        kurier="Leleka Konstantyn",
        rejon="WA87",
        wykonawca="Koli",
        pni_zpo="763765",
        ilosc_total=3,
        ilosc_zpo=3,
    )
    assert w.ilosc_total == 3
    assert w.rejon == "WA87"


def test_wiersz_importu_ilosc_total_wymagana():
    with pytest.raises(ValidationError):
        WierszImportu(
            data=date(2026, 8, 3), nadawca="ZUS", adres="Senatorska 6/8",
            kurier="X", ilosc_total=None,
        )


def test_wiersz_importu_ilosc_jako_spacja_to_brak_wartosci():
    # realny przypadek z pliku źródłowego: "puste" komórki bywają spacją
    w = WierszImportu(
        data=date(2026, 8, 3), nadawca="ZUS", adres="Senatorska 6/8",
        kurier="X", ilosc_total=5, ilosc_zpo=" ",
    )
    assert w.ilosc_zpo is None


def test_wiersz_importu_ilosc_jako_string_liczbowy():
    w = WierszImportu(
        data=date(2026, 8, 3), nadawca="ZUS", adres="Senatorska 6/8",
        kurier="X", ilosc_total="7",
    )
    assert w.ilosc_total == 7


def test_wiersz_importu_ujemna_ilosc_odrzucona():
    with pytest.raises(ValidationError):
        WierszImportu(
            data=date(2026, 8, 3), nadawca="ZUS", adres="Senatorska 6/8",
            kurier="X", ilosc_total=-1,
        )


def test_wiersz_importu_pusty_pni_to_none():
    w = WierszImportu(
        data=date(2026, 8, 3), nadawca="ZUS", adres="Senatorska 6/8",
        kurier="X", ilosc_total=1, pni_zpo="  ",
    )
    assert w.pni_zpo is None


# --- WierszBlankietu / BlankietBlok: dane z formularza wprowadzania ---

def test_wiersz_blankietu_normalizuje_biale_znaki():
    w = WierszBlankietu(nadawca="Żabka", adres="  Odkryta   24 ", ilosc_total=3)
    assert w.adres == "Odkryta 24"


def test_blok_z_nieznanym_rejonem_i_komentarzem():
    blok = BlankietBlok(
        kurier="Kowalski Jan",
        data=date(2026, 8, 10),
        rejon=None,
        komentarz="rejon nieznany, kurier mówił że to okolice Legionowa",
        wiersze=[WierszBlankietu(nadawca="Żabka", adres="Odkryta 24", ilosc_total=3)],
    )
    assert blok.rejon is None
    assert "Legionowa" in blok.komentarz


def test_blok_normalizuje_kuriera():
    blok = BlankietBlok(
        kurier="  Kowalski   Jan ",
        data=date(2026, 8, 10),
        wiersze=[WierszBlankietu(nadawca="Żabka", adres="Odkryta 24", ilosc_total=3)],
    )
    assert blok.kurier == "Kowalski Jan"


def test_blok_wymaga_co_najmniej_jednego_wiersza():
    with pytest.raises(ValidationError):
        BlankietBlok(kurier="Kowalski Jan", data=date(2026, 8, 10), wiersze=[])
