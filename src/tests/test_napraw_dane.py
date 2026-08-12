"""
repo.napraw_dane: jednorazowa, bezwarunkowa i idempotentna naprawa danych
sprzed reguły "???" i sprzed poprawki firmy_zpo/punkty.nadawca (patrz
importer.py, repo.zmien_nazwe_w_slowniku). CELOWO poza `migruj` - to nie
jest zmiana struktury, a `app.py` łapie tylko `NiezgodnaWersjaSchematu`,
więc wyjątek w `migruj` uniemożliwiałby start aplikacji na stałe.

Testy budują scenariusze RĘCZNIE (surowe INSERT-y), symulując bazy sprzed
tej wersji - `get_or_create_rejon`/`get_or_create_punkt` same w sobie już
nie potrafią wyprodukować takiego stanu, więc nie da się tego złapać przez
normalne API. TDD.
"""
import logging

import pytest

from zpo_tracker import repo
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
    punkt_id = conn.execute(
        "INSERT INTO punkty (nadawca, adres) VALUES ('Żabka', 'Odkryta 24')").lastrowid
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
    punkt_id = conn.execute(
        "INSERT INTO punkty (nadawca, adres) VALUES ('Żabka', 'Odkryta 24')").lastrowid
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


# --- firmy_zpo ---

def test_dopina_brakujaca_firme_dla_punktu_z_pni(conn):
    # get_or_create_punkt zawsze ustawia firma_zpo_id gdy jest PNI - to
    # symuluje stan, który mimo to teoretycznie mógłby powstać (np. import
    # bezpośrednio przez SQL, bug w innej wersji)
    conn.execute(
        "INSERT INTO punkty (nadawca, adres, pni_zpo) VALUES ('Żabka', 'Odkryta 24', '228648')")
    repo.napraw_dane(conn)
    row = conn.execute(
        "SELECT f.nazwa FROM punkty p JOIN firmy_zpo f ON f.id = p.firma_zpo_id"
    ).fetchone()
    assert row[0] == "Żabka"


def test_przemianowuje_firme_gdy_jeden_rozny_nadawca(conn):
    # importer.py bug (naprawiony w poprzednim commicie) zostawiał firmy_zpo
    # z nazwą inną niż punkty.nadawca - to naprawia istniejące już rozjazdy
    firma_id = conn.execute("INSERT INTO firmy_zpo (nazwa) VALUES ('ZABKA')").lastrowid
    conn.execute(
        "INSERT INTO punkty (nadawca, adres, pni_zpo, firma_zpo_id)"
        " VALUES ('Żabka', 'Odkryta 24', '228648', ?)", (firma_id,))

    repo.napraw_dane(conn)

    nazwa = conn.execute("SELECT nazwa FROM firmy_zpo WHERE id = ?", (firma_id,)).fetchone()[0]
    assert nazwa == "Żabka"


def test_przemianowanie_z_kolizja_scala_firmy_bez_utraty_punktow(conn):
    # "Żabka" i "ZABKA" to dwie osobne firmy_zpo (rozjazd sprzed bugfixu) -
    # jeden z punktów ZABKA ma nadawcę "Żabka" (druga poprawna pisownia) ->
    # rename zderzyłby się z UNIQUE, więc trzeba scalić: przepiąć punkty na
    # wygrywającą firmę, dopiero potem skasować przegrywającą
    poprawna_id = conn.execute("INSERT INTO firmy_zpo (nazwa) VALUES ('Żabka')").lastrowid
    bledna_id = conn.execute("INSERT INTO firmy_zpo (nazwa) VALUES ('ZABKA')").lastrowid
    conn.execute(
        "INSERT INTO punkty (nadawca, adres, pni_zpo, firma_zpo_id)"
        " VALUES ('Żabka', 'Stara 1', '111', ?)", (poprawna_id,))
    punkt_bledny_id = conn.execute(
        "INSERT INTO punkty (nadawca, adres, pni_zpo, firma_zpo_id)"
        " VALUES ('Żabka', 'Nowa 2', '222', ?)", (bledna_id,)).lastrowid

    repo.napraw_dane(conn)

    nazwy = [r[0] for r in conn.execute("SELECT nazwa FROM firmy_zpo")]
    assert nazwy == ["Żabka"]
    firma_punktu = conn.execute(
        "SELECT firma_zpo_id FROM punkty WHERE id = ?", (punkt_bledny_id,)).fetchone()[0]
    assert firma_punktu == poprawna_id


def test_nie_rozstrzyga_firmy_z_wieloma_roznymi_nadawcami(conn, caplog):
    # osiągalny stan: rename zrywa więź, potem import dopina nowy punkt do
    # tego samego wiersza pod inną nazwą - nie ma jednoznacznej odpowiedzi,
    # więc NIE ruszamy automatycznie (rozstrzyga człowiek)
    firma_id = conn.execute("INSERT INTO firmy_zpo (nazwa) VALUES ('Żabka')").lastrowid
    conn.execute(
        "INSERT INTO punkty (nadawca, adres, pni_zpo, firma_zpo_id)"
        " VALUES ('Żabka', 'Stara 1', '111', ?)", (firma_id,))
    conn.execute(
        "INSERT INTO punkty (nadawca, adres, pni_zpo, firma_zpo_id)"
        " VALUES ('Duży Ben', 'Nowa 2', '222', ?)", (firma_id,))

    with caplog.at_level(logging.WARNING, logger="zpo_tracker"):
        repo.napraw_dane(conn)

    nazwa = conn.execute("SELECT nazwa FROM firmy_zpo WHERE id = ?", (firma_id,)).fetchone()[0]
    assert nazwa == "Żabka"  # nietknięte
    assert any("nie rozstrzygnięto" in rec.message for rec in caplog.records)


def test_usuwa_osierocona_literowke_gdy_pasuje_do_uzywanej_firmy(conn):
    conn.execute("INSERT INTO firmy_zpo (nazwa) VALUES ('Żabka')")  # osierocona, ale UŻYWANA gdzie indziej
    conn.execute(
        "INSERT INTO punkty (nadawca, adres, pni_zpo, firma_zpo_id) VALUES"
        " ('Żabka', 'Odkryta 24', '228648', (SELECT id FROM firmy_zpo WHERE nazwa='Żabka'))")
    osierocona_id = conn.execute("INSERT INTO firmy_zpo (nazwa) VALUES ('ZABKA')").lastrowid

    repo.napraw_dane(conn)

    pozostale = [r[0] for r in conn.execute("SELECT id FROM firmy_zpo")]
    assert osierocona_id not in pozostale


def test_nie_usuwa_osieroconej_firmy_o_unikalnej_nazwie(conn):
    # mogła zostać dodana ręcznie w Słownikach zanim powstał pierwszy punkt -
    # firmy_zpo to zwykły słownik z UI, nie tylko efekt uboczny importu
    osierocona_id = conn.execute(
        "INSERT INTO firmy_zpo (nazwa) VALUES ('Nowa Sieć Bez Punktów')").lastrowid
    repo.napraw_dane(conn)
    pozostale = [r[0] for r in conn.execute("SELECT id FROM firmy_zpo")]
    assert osierocona_id in pozostale


# --- idempotencja ---

def test_jest_idempotentna(conn):
    conn.execute("INSERT INTO rejony (kod) VALUES ('-')")
    conn.execute("INSERT INTO firmy_zpo (nazwa) VALUES ('ZABKA')")
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
