"""
repo.napraw_dane: bezwarunkowa i idempotentna naprawa danych sprzed reguły
"???". CELOWO poza `migruj` - to nie jest zmiana struktury, a `app.py` łapie
tylko `NiezgodnaWersjaSchematu`, więc wyjątek w `migruj` uniemożliwiałby
start aplikacji na stałe.

Drugi krok tej funkcji - naprawa rozjazdu `firmy_zpo.nazwa` z
`punkty.nadawca` - zniknął razem ze schematem v3 i jego testy razem z nim.
Nie zostały przepisane na `nadawcy`, bo naprawiałyby problem, którego v4
strukturalnie nie ma: nazwa nadawcy żyje w jednym miejscu, więc nie ma
drugiej kopii, z którą mogłaby się rozjechać. Własność, która to zastąpiła,
jest przypięta w `test_repo.py`
(`test_zmiana_nazwy_nadawcy_jest_widoczna_w_punktach_bez_zadnej_propagacji`).

Testy budują scenariusze RĘCZNIE (surowe INSERT-y), symulując bazy sprzed
tej wersji - `get_or_create_rejon` sam w sobie już nie potrafi wyprodukować
takiego stanu, więc nie da się tego złapać przez normalne API. TDD.
"""
import pytest

from zpo_tracker import repo
from zpo_tracker.importer import get_or_create_punkt
from zpo_tracker.normalizacja import REJON_NIEZNANY


@pytest.fixture
def conn():
    conn = repo.polacz(":memory:")
    repo.utworz_schemat(conn)
    yield conn
    conn.close()


# --- rejony ---

def test_tworzy_kanoniczny_rejon_gdy_brak(conn):
    # symulacja bazy sprzed seeda w schema.sql
    conn.execute("DELETE FROM rejony")
    repo.napraw_dane(conn)
    kody = [r[0] for r in conn.execute("SELECT kod FROM rejony")]
    assert kody == [REJON_NIEZNANY]


def test_scala_smieciowe_rejony_w_kanoniczny_i_przepina_transakcje(conn):
    kanoniczny_id = conn.execute(
        f"SELECT id FROM rejony WHERE kod = '{REJON_NIEZNANY}'").fetchone()[0]
    kurier_id = conn.execute(
        "INSERT INTO kurierzy (imie_nazwisko) VALUES ('Nowak Piotr')").lastrowid
    punkt_id, _ = get_or_create_punkt(conn, "Żabka", "Odkryta 24", None)
    smieciowy_id = conn.execute("INSERT INTO rejony (kod) VALUES ('-')").lastrowid
    conn.execute(
        "INSERT INTO transakcje (data, kurier_id, punkt_id, rejon_id, ilosc_total, uuid)"
        " VALUES ('2026-08-01', ?, ?, ?, 3, 'uuid-1')",
        (kurier_id, punkt_id, smieciowy_id),
    )

    repo.napraw_dane(conn)

    kody = [r[0] for r in conn.execute("SELECT kod FROM rejony")]
    assert kody == [REJON_NIEZNANY]
    nowy_rejon_id = conn.execute(
        "SELECT rejon_id FROM transakcje WHERE uuid = 'uuid-1'").fetchone()[0]
    assert nowy_rejon_id == kanoniczny_id


def test_przepina_transakcje_z_null_rejonem_na_kanoniczny(conn):
    kurier_id = conn.execute(
        "INSERT INTO kurierzy (imie_nazwisko) VALUES ('Nowak Piotr')").lastrowid
    punkt_id, _ = get_or_create_punkt(conn, "Żabka", "Odkryta 24", None)
    conn.execute(
        "INSERT INTO transakcje (data, kurier_id, punkt_id, rejon_id, ilosc_total, uuid)"
        " VALUES ('2026-08-01', ?, ?, NULL, 3, 'uuid-1')", (kurier_id, punkt_id))

    repo.napraw_dane(conn)

    kod = conn.execute(
        "SELECT r.kod FROM transakcje t JOIN rejony r ON r.id = t.rejon_id"
        " WHERE t.uuid = 'uuid-1'"
    ).fetchone()[0]
    assert kod == REJON_NIEZNANY


def test_nie_rusza_prawidlowych_rejonow(conn):
    conn.execute("INSERT INTO rejony (kod) VALUES ('WA87')")
    repo.napraw_dane(conn)
    kody = sorted(r[0] for r in conn.execute("SELECT kod FROM rejony"))
    assert kody == sorted(["WA87", REJON_NIEZNANY])


# --- idempotencja ---

def test_jest_idempotentna(conn):
    conn.execute("INSERT INTO rejony (kod) VALUES ('-')")
    repo.napraw_dane(conn)
    stan_po_pierwszej = sorted(r[0] for r in conn.execute("SELECT kod FROM rejony"))

    repo.napraw_dane(conn)  # drugie wywołanie nie może nic zepsuć ani rzucić

    stan_po_drugiej = sorted(r[0] for r in conn.execute("SELECT kod FROM rejony"))
    assert stan_po_pierwszej == stan_po_drugiej


def test_nie_zmienia_wersji_schematu(conn):
    # to naprawa DANYCH, nie struktury - patrz docstring modułu
    przed = repo.wersja_schematu(conn)
    repo.napraw_dane(conn)
    assert repo.wersja_schematu(conn) == przed
