"""
Poprawki po zapisie: edycja i usuwanie transakcji (0.1-alpha.3.2). Pierwsze
w projekcie destrukcyjne prymitywy na `transakcje` - dotąd istniał tylko
INSERT (i jeden UPDATE ilości wyłącznie w scalanie.py). Konflikt wartości
(ta sama trójka data+kurier+punkt) NIGDY nie jest rozstrzygany automatycznie
(reguła z roadmap.md) - musi blokować z czytelnym komunikatem, baza bez
zmian. TDD.
"""
from datetime import date

import pytest

from zpo_tracker import repo
from zpo_tracker.models import Blankiet, WierszBlankietu


@pytest.fixture
def conn():
    conn = repo.polacz(":memory:")
    repo.utworz_schemat(conn)
    yield conn
    conn.close()


def _zapisz(conn, kurier="Kowalski Jan", adres="Odkryta 24", data_=date(2026, 8, 10),
            ilosc_total=5, nadawca="Żabka", rejon=None):
    wyniki = repo.zapisz_blankiet(conn, Blankiet(
        kurier=kurier, data=data_,
        wiersze=[WierszBlankietu(nadawca=nadawca, adres=adres,
                                   rejon=rejon, ilosc_total=ilosc_total)],
    ))
    return wyniki[0]["id"]


def _wiersz(conn, id_):
    return dict(conn.execute("SELECT * FROM transakcje WHERE id = ?", (id_,)).fetchone())


# --- zaktualizuj_transakcje: edycja per pole ---

def test_edycja_ilosci(conn):
    id_ = _zapisz(conn, ilosc_total=5)
    repo.zaktualizuj_transakcje(conn, id_, {"ilosc_total": 9})
    assert _wiersz(conn, id_)["ilosc_total"] == 9


def test_edycja_daty(conn):
    id_ = _zapisz(conn, data_=date(2026, 8, 10))
    repo.zaktualizuj_transakcje(conn, id_, {"data": date(2026, 8, 11)})
    assert _wiersz(conn, id_)["data"] == "2026-08-11"


def test_edycja_daty_jako_string_iso(conn):
    id_ = _zapisz(conn, data_=date(2026, 8, 10))
    repo.zaktualizuj_transakcje(conn, id_, {"data": "2026-08-12"})
    assert _wiersz(conn, id_)["data"] == "2026-08-12"


def test_edycja_kuriera_przepina_na_istniejacego_lub_nowego(conn):
    id_ = _zapisz(conn, kurier="Kowalski Jan")
    repo.zaktualizuj_transakcje(conn, id_, {"kurier": "Nowak Piotr"})
    wiersz = conn.execute(
        "SELECT k.imie_nazwisko FROM transakcje t JOIN kurierzy k ON k.id = t.kurier_id"
        " WHERE t.id = ?", (id_,)).fetchone()
    assert wiersz[0] == "Nowak Piotr"


def test_edycja_wykonawcy(conn):
    id_ = _zapisz(conn)
    repo.zaktualizuj_transakcje(conn, id_, {"wykonawca": "Koli"})
    wiersz = conn.execute(
        "SELECT w.nazwa FROM transakcje t JOIN wykonawcy w ON w.id = t.wykonawca_id"
        " WHERE t.id = ?", (id_,)).fetchone()
    assert wiersz[0] == "Koli"


def test_edycja_rejonu(conn):
    id_ = _zapisz(conn)
    repo.zaktualizuj_transakcje(conn, id_, {"rejon": "WA87"})
    wiersz = conn.execute(
        "SELECT r.kod FROM transakcje t JOIN rejony r ON r.id = t.rejon_id"
        " WHERE t.id = ?", (id_,)).fetchone()
    assert wiersz[0] == "WA87"


def test_edycja_kilku_pol_naraz(conn):
    id_ = _zapisz(conn, ilosc_total=5)
    repo.zaktualizuj_transakcje(conn, id_, {"ilosc_total": 7, "ilosc_zpo": 3})
    w = _wiersz(conn, id_)
    assert w["ilosc_total"] == 7
    assert w["ilosc_zpo"] == 3


def test_edycja_bumpuje_zmodyfikowano_i_nie_rusza_reszty_atrybucji(conn):
    id_ = _zapisz(conn)
    przed = _wiersz(conn, id_)
    repo.zaktualizuj_transakcje(conn, id_, {"ilosc_total": 99}, teraz="2026-08-13T12:00:00")
    po = _wiersz(conn, id_)
    assert po["zmodyfikowano"] == "2026-08-13T12:00:00"
    assert po["uuid"] == przed["uuid"]
    assert po["utworzono"] == przed["utworzono"]
    assert po["zrodlo"] == przed["zrodlo"] == "formularz"


def test_edycja_nieznanego_pola_rzuca_value_error(conn):
    id_ = _zapisz(conn)
    with pytest.raises(ValueError):
        repo.zaktualizuj_transakcje(conn, id_, {"nadawca": "Coś innego"})
    assert _wiersz(conn, id_)["ilosc_total"] == 5  # bez zmian


def test_edycja_nieistniejacej_transakcji_rzuca_value_error(conn):
    with pytest.raises(ValueError):
        repo.zaktualizuj_transakcje(conn, 999, {"ilosc_total": 1})


# --- zaktualizuj_transakcje: kolizja UNIQUE(data, kurier, punkt) ---

def test_edycja_w_kolizje_rzuca_i_nie_zmienia_bazy(conn):
    id_a = _zapisz(conn, kurier="Kowalski Jan", data_=date(2026, 8, 10),
                   adres="Odkryta 24", ilosc_total=5)
    id_b = _zapisz(conn, kurier="Kowalski Jan", data_=date(2026, 8, 11),
                   adres="Odkryta 24", ilosc_total=7)

    with pytest.raises(repo.KolizjaTransakcji) as wyjatek:
        repo.zaktualizuj_transakcje(conn, id_b, {"data": "2026-08-10"})

    assert "2026-08-10" in str(wyjatek.value)
    assert _wiersz(conn, id_b)["data"] == "2026-08-11"  # bez zmian
    assert _wiersz(conn, id_a)["ilosc_total"] == 5


def test_edycja_bez_zmiany_klucza_naturalnego_nie_sprawdza_kolizji(conn):
    # zmiana WYŁĄCZNIE ilości nigdy nie może kolidować - to nie jest część
    # UNIQUE(data, kurier, punkt)
    id_a = _zapisz(conn, kurier="Kowalski Jan", ilosc_total=5)
    repo.zaktualizuj_transakcje(conn, id_a, {"ilosc_total": 6})
    assert _wiersz(conn, id_a)["ilosc_total"] == 6


# --- usun_transakcje ---

def test_usuniecie_pojedynczej_transakcji(conn):
    id_ = _zapisz(conn)
    usuniete = repo.usun_transakcje(conn, [id_])
    assert usuniete == 1
    assert conn.execute("SELECT COUNT(*) FROM transakcje").fetchone()[0] == 0


def test_usuniecie_wielu_transakcji(conn):
    id_a = _zapisz(conn, adres="Odkryta 24")
    id_b = _zapisz(conn, adres="Inna 5")
    usuniete = repo.usun_transakcje(conn, [id_a, id_b])
    assert usuniete == 2
    assert conn.execute("SELECT COUNT(*) FROM transakcje").fetchone()[0] == 0


def test_usuniecie_pustej_listy_nic_nie_robi(conn):
    _zapisz(conn)
    assert repo.usun_transakcje(conn, []) == 0
    assert conn.execute("SELECT COUNT(*) FROM transakcje").fetchone()[0] == 1


# --- ustaw_pole_transakcji: edycja zbiorcza ---

def test_ustaw_pole_na_kilku_transakcjach(conn):
    id_a = _zapisz(conn, adres="Odkryta 24", kurier="Kowalski Jan")
    id_b = _zapisz(conn, adres="Inna 5", kurier="Kowalski Jan")
    repo.ustaw_pole_transakcji(conn, [id_a, id_b], "wykonawca", "Koli")
    for id_ in (id_a, id_b):
        wiersz = conn.execute(
            "SELECT w.nazwa FROM transakcje t JOIN wykonawcy w ON w.id = t.wykonawca_id"
            " WHERE t.id = ?", (id_,)).fetchone()
        assert wiersz[0] == "Koli"


def test_ustaw_pole_kolizja_w_srodku_wycofuje_wszystko(conn):
    # trzy wiersze, ustawienie wspólnego kuriera na WSZYSTKIE koliduje dla
    # trzeciego (bo pod tym kurierem+datą+punktem już istnieje inny wiersz)
    # - atomowo: NIC się nie zmienia, nie tylko trzeci wiersz
    id_a = _zapisz(conn, kurier="A", data_=date(2026, 8, 10), adres="Odkryta 24")
    id_b = _zapisz(conn, kurier="A", data_=date(2026, 8, 11), adres="Inna 5")
    _kolidujacy = _zapisz(conn, kurier="B", data_=date(2026, 8, 10), adres="Odkryta 24")

    with pytest.raises(repo.KolizjaTransakcji):
        repo.ustaw_pole_transakcji(conn, [id_a, id_b], "kurier", "B")

    wiersz_a = conn.execute(
        "SELECT k.imie_nazwisko FROM transakcje t JOIN kurierzy k ON k.id = t.kurier_id"
        " WHERE t.id = ?", (id_a,)).fetchone()
    assert wiersz_a[0] == "A"  # NIE zmienione mimo że id_a samo w sobie nie kolidowało


def test_ustaw_pole_nieznane_pole_rzuca_value_error(conn):
    id_ = _zapisz(conn)
    with pytest.raises(ValueError):
        repo.ustaw_pole_transakcji(conn, [id_], "adres", "Coś innego")
