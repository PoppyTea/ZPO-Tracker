"""
Testy dla logiki importu. Pisane PRZED implementacją (TDD).
Baza SQLite w pamięci (:memory:) - realne zapytania, bez mocków.
"""
import sqlite3
from pathlib import Path
import pytest
from zpo_tracker.importer import (
    parse_quantity,
    get_or_create_kurier,
    get_or_create_punkt,
    get_or_create_firma_zpo,
    import_row,
)


@pytest.fixture
def conn():
    conn = sqlite3.connect(":memory:")
    with open(Path(__file__).parent.parent.parent / "schema.sql") as f:
        conn.executescript(f.read())
    yield conn
    conn.close()


# --- parse_quantity: obsługa pustych/dziwnych wartości z realnych danych ---

def test_parse_quantity_returns_int_for_number():
    assert parse_quantity(3) == 3


def test_parse_quantity_returns_none_for_none():
    assert parse_quantity(None) is None


def test_parse_quantity_returns_none_for_stray_space():
    # w realnym pliku niektóre "puste" komórki to pojedyncza spacja, nie None
    assert parse_quantity(" ") is None


def test_parse_quantity_parses_numeric_string():
    # kolumna z CSV bywa odczytana jako string
    assert parse_quantity("7") == 7


# --- get_or_create_kurier: deduplikacja po nazwisku ---

def test_get_or_create_kurier_creates_new(conn):
    kid = get_or_create_kurier(conn, "Testowy Kurier")
    assert kid is not None
    row = conn.execute("SELECT imie_nazwisko FROM kurierzy WHERE id=?", (kid,)).fetchone()
    assert row[0] == "Testowy Kurier"


def test_get_or_create_kurier_reuses_existing(conn):
    kid1 = get_or_create_kurier(conn, "Jan Kowalski")
    kid2 = get_or_create_kurier(conn, "Jan Kowalski")
    assert kid1 == kid2


# --- get_or_create_punkt: sedno logiki, z realnym przypadkiem z danych ---

def test_get_or_create_punkt_creates_new_with_pni(conn):
    pid, warnings = get_or_create_punkt(conn, "Żabka", "Odkryta 24", "228648")
    assert pid is not None
    assert warnings == []


def test_get_or_create_punkt_reuses_same_pni_same_address(conn):
    pid1, w1 = get_or_create_punkt(conn, "Żabka", "Odkryta 24", "228648")
    pid2, w2 = get_or_create_punkt(conn, "Żabka", "Odkryta 24", "228648")
    assert pid1 == pid2
    assert w2 == []


def test_get_or_create_punkt_warns_on_pni_with_different_address(conn):
    # to jest dokładnie przypadek Odkryta 24 / Odkryta 82B pod PNI 228648
    pid1, w1 = get_or_create_punkt(conn, "Żabka", "Odkryta 24", "228648")
    pid2, w2 = get_or_create_punkt(conn, "Żabka", "Odkryta 82B", "228648")
    assert pid1 == pid2  # to nadal ten sam punkt referencyjny (kanoniczny adres)
    assert len(w2) == 1
    assert "228648" in w2[0]


def test_get_or_create_firma_zpo_creates_new(conn):
    fid = get_or_create_firma_zpo(conn, "Żabka")
    assert fid is not None
    row = conn.execute("SELECT nazwa FROM firmy_zpo WHERE id=?", (fid,)).fetchone()
    assert row[0] == "Żabka"


def test_get_or_create_firma_zpo_reuses_existing(conn):
    fid1 = get_or_create_firma_zpo(conn, "Żabka")
    fid2 = get_or_create_firma_zpo(conn, "Żabka")
    assert fid1 == fid2


def test_get_or_create_punkt_links_firma_zpo_when_pni_present(conn):
    # nadawca punktu z PNI to nazwa sieci (Żabka/Duży Ben/Groszek/...) -
    # ma trafić do słownika firmy_zpo, nie zostać luźnym stringiem
    pid, _ = get_or_create_punkt(conn, "Żabka", "Odkryta 24", "228648")
    row = conn.execute("SELECT firma_zpo_id FROM punkty WHERE id=?", (pid,)).fetchone()
    assert row[0] is not None
    firma = conn.execute(
        "SELECT nazwa FROM firmy_zpo WHERE id=?", (row[0],)
    ).fetchone()
    assert firma[0] == "Żabka"


def test_znany_pni_z_inna_nazwa_sieci_nie_tworzy_osieroconej_firmy(conn):
    # get_or_create_firma_zpo wołane PRZED sprawdzeniem PNI zostawiało wpis
    # w firmy_zpo, którego nie referencuje żaden punkt i którego nie widać
    # w żadnej podpowiedzi - cichy śmieć w słowniku przy każdym imporcie
    # tego samego punktu zapisanego inaczej
    get_or_create_punkt(conn, "Żabka", "Odkryta 24", "228648")
    get_or_create_punkt(conn, "ZABKA", "Odkryta 24", "228648")

    nazwy = [r[0] for r in conn.execute("SELECT nazwa FROM firmy_zpo")]
    assert nazwy == ["Żabka"]


def test_znany_pni_z_inna_nazwa_sieci_ostrzega(conn):
    # rozjazd adresu przy tym samym PNI już ostrzegał, rozjazd nadawcy nie -
    # a to ta sama klasa problemu i tak samo wymaga oka człowieka
    get_or_create_punkt(conn, "Żabka", "Odkryta 24", "228648")
    _, ostrzezenia = get_or_create_punkt(conn, "Groszek", "Odkryta 24", "228648")

    assert len(ostrzezenia) == 1
    assert "Żabka" in ostrzezenia[0] and "Groszek" in ostrzezenia[0]


def test_get_or_create_punkt_no_firma_zpo_for_regular_client(conn):
    # zwykły nadawca (ZUS, PKO...) bez PNI nie ma firmy ZPO
    pid, _ = get_or_create_punkt(conn, "ZUS", "Senatorska 6/8", None)
    row = conn.execute("SELECT firma_zpo_id FROM punkty WHERE id=?", (pid,)).fetchone()
    assert row[0] is None


def test_get_or_create_punkt_regular_client_deduped_by_nadawca_and_adres(conn):
    # klient bez PNI (np. ZUS) - deduplikacja po nadawca+adres, nie tworzymy
    # nowego punktu za każdym razem
    pid1, _ = get_or_create_punkt(conn, "ZUS", "Senatorska 6/8", None)
    pid2, _ = get_or_create_punkt(conn, "ZUS", "Senatorska 6/8", None)
    assert pid1 == pid2


# --- import_row: cały wiersz, z realnymi przypadkami brzegowymi ---

def test_import_row_skips_row_without_date(conn):
    row = {"data": None, " Pełna Nazwa Nadawcy": "ZUS", "Kurier": "X"}
    result = import_row(conn, row)
    assert result["skipped"] is True
    count = conn.execute("SELECT COUNT(*) FROM transakcje").fetchone()[0]
    assert count == 0


def test_import_row_skips_row_with_date_but_no_kurier(conn):
    # realny przypadek z pliku: 35 wierszy majacych wylacznie date,
    # reszta kolumn pusta (najpewniej przygotowane z gory miejsce na wpisy)
    row = {"data": "2026-08-07", "Kurier": None, " Pełna Nazwa Nadawcy": None}
    result = import_row(conn, row)
    assert result["skipped"] is True
    count = conn.execute("SELECT COUNT(*) FROM transakcje").fetchone()[0]
    assert count == 0


def test_import_row_inserts_valid_transaction(conn):
    row = {
        "data": "2026-08-03",
        " Pełna Nazwa Nadawcy": "Żabka",
        "Adres odbioru dla wszystkich nadawców": "Solidarności 117",
        "Kurier": "Leleka Konstantyn",
        "Rejon": "WA87",
        " Wpisujemy łączną liczbę odebranych Pocztexów": 3,
        " Wpisujemy   w tym liczbę z Zewnetrznych Punktów Odbiorów ": 3,
        "PNI ZPO": "763765",
        "Wykonawca": "Koli",
    }
    result = import_row(conn, row)
    assert result["skipped"] is False
    count = conn.execute("SELECT COUNT(*) FROM transakcje").fetchone()[0]
    assert count == 1


def test_import_row_flags_duplicate_transaction_without_crashing(conn):
    row = {
        "data": "2026-08-03",
        " Pełna Nazwa Nadawcy": "Żabka",
        "Adres odbioru dla wszystkich nadawców": "Solidarności 117",
        "Kurier": "Leleka Konstantyn",
        "Rejon": "WA87",
        " Wpisujemy łączną liczbę odebranych Pocztexów": 3,
        " Wpisujemy   w tym liczbę z Zewnetrznych Punktów Odbiorów ": 3,
        "PNI ZPO": "763765",
        "Wykonawca": "Koli",
    }
    import_row(conn, row)
    result = import_row(conn, row)  # dokładnie ten sam wiersz drugi raz
    assert result["skipped"] is True
    assert "duplikat" in result["reason"].lower()
