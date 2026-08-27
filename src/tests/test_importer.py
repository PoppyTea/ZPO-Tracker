"""
Testy dla logiki importu. Pisane PRZED implementacją (TDD).
Baza SQLite w pamięci (:memory:) - realne zapytania, bez mocków.
"""
import sqlite3
from pathlib import Path
import pytest
from zpo_tracker.importer import (
    parse_quantity,
    get_or_create_adres,
    get_or_create_kurier,
    get_or_create_nadawca,
    get_or_create_punkt,
    get_or_create_rejon,
    get_or_create_ulica,
    import_row,
)
from zpo_tracker.normalizacja import REJON_NIEZNANY


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


# --- get_or_create_rejon: normalizuj_rejon na wejściu, nigdy nie zwraca None ---

def test_get_or_create_rejon_tworzy_nowy(conn):
    rid = get_or_create_rejon(conn, "WA87")
    row = conn.execute("SELECT kod FROM rejony WHERE id=?", (rid,)).fetchone()
    assert row[0] == "WA87"


def test_get_or_create_rejon_reuzywa_istniejacego(conn):
    rid1 = get_or_create_rejon(conn, "WA87")
    rid2 = get_or_create_rejon(conn, "WA87")
    assert rid1 == rid2


def test_get_or_create_rejon_puste_daje_wpis_nieznany_nie_none(conn):
    # dawniej: None, brak wpisu w rejony, rejon_id transakcji = NULL.
    # teraz: kanoniczny wpis "???" - zawsze jest CO pokazać w podglądzie/eksporcie
    rid = get_or_create_rejon(conn, None)
    assert rid is not None
    row = conn.execute("SELECT kod FROM rejony WHERE id=?", (rid,)).fetchone()
    assert row[0] == REJON_NIEZNANY


def test_get_or_create_rejon_smieciowe_wartosci_dzielą_ten_sam_wpis(conn):
    rid1 = get_or_create_rejon(conn, "-")
    rid2 = get_or_create_rejon(conn, "n/a")
    rid3 = get_or_create_rejon(conn, "  ")
    assert rid1 == rid2 == rid3


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


def test_get_or_create_nadawca_creates_new(conn):
    nid = get_or_create_nadawca(conn, "Żabka")
    assert nid is not None
    row = conn.execute("SELECT nazwa, liczy_zpo FROM nadawcy WHERE id=?", (nid,)).fetchone()
    assert row[0] == "Żabka"
    assert row[1] == 0


def test_get_or_create_nadawca_reuses_existing(conn):
    nid1 = get_or_create_nadawca(conn, "Żabka")
    nid2 = get_or_create_nadawca(conn, "Żabka")
    assert nid1 == nid2


def test_get_or_create_nadawca_zapala_flage_ale_nigdy_jej_nie_gasi(conn):
    """
    `liczy_zpo` mówi, czy dla nadawcy wypełnia się "w tym ZPO". Jeden wiersz
    bez PNI nie dowodzi, że nadawca przestał być punktem ZPO - PNI zwykle
    po prostu jeszcze nie znamy. Zgaszona flaga wygasza pole w formularzu,
    czego użytkownik nie ma jak zauważyć.
    """
    nid = get_or_create_nadawca(conn, "Żabka", liczy_zpo=False)
    get_or_create_nadawca(conn, "Żabka", liczy_zpo=True)
    assert conn.execute(
        "SELECT liczy_zpo FROM nadawcy WHERE id=?", (nid,)).fetchone()[0] == 1

    get_or_create_nadawca(conn, "Żabka", liczy_zpo=False)
    assert conn.execute(
        "SELECT liczy_zpo FROM nadawcy WHERE id=?", (nid,)).fetchone()[0] == 1


def test_get_or_create_punkt_zapala_liczy_zpo_gdy_jest_pni(conn):
    # nadawca punktu z PNI to nazwa sieci (Żabka/Duży Ben/Groszek/...) -
    # to dla niego wypełnia się kolumnę "w tym ZPO"
    get_or_create_punkt(conn, "Żabka", "Odkryta 24", "228648")
    row = conn.execute("SELECT liczy_zpo FROM nadawcy WHERE nazwa='Żabka'").fetchone()
    assert row[0] == 1


def test_znany_pni_z_inna_nazwa_sieci_nie_tworzy_osieroconego_nadawcy(conn):
    # PNI jest kluczem punktu, więc druga pisownia sieci ma zostać
    # ZIGNOROWANA, a nie założyć wpis w słowniku, którego nie referencuje
    # żaden punkt - cichy śmieć przy każdym imporcie tego samego punktu
    get_or_create_punkt(conn, "Żabka", "Odkryta 24", "228648")
    get_or_create_punkt(conn, "ZABKA", "Odkryta 24", "228648")

    nazwy = [r[0] for r in conn.execute("SELECT nazwa FROM nadawcy")]
    assert nazwy == ["Żabka"]


def test_pni_dopisuje_sie_do_istniejacego_punktu_bez_pni(conn):
    """
    PNI zdobywa się później (z paragonu), a `UNIQUE(nadawca_id, adres_id)`
    mówi, że to jeden i ten sam punkt. Drugi wiersz byłby duplikatem tej
    samej fizycznej lokalizacji - i w v3 dokładnie tak powstawał.
    """
    pid_bez, _ = get_or_create_punkt(conn, "Żabka", "Odkryta 24", None)
    pid_z, ostrzezenia = get_or_create_punkt(conn, "Żabka", "Odkryta 24", "228648")

    assert pid_z == pid_bez
    assert ostrzezenia == []
    assert conn.execute("SELECT COUNT(*) FROM punkty").fetchone()[0] == 1
    assert conn.execute(
        "SELECT pni_zpo FROM punkty WHERE id=?", (pid_bez,)).fetchone()[0] == "228648"


def test_drugie_pni_dla_tej_samej_pary_nadawca_adres_ostrzega_i_nie_nadpisuje(conn):
    get_or_create_punkt(conn, "Żabka", "Odkryta 24", "228648")
    pid, ostrzezenia = get_or_create_punkt(conn, "Żabka", "Odkryta 24", "999111")

    assert conn.execute(
        "SELECT pni_zpo FROM punkty WHERE id=?", (pid,)).fetchone()[0] == "228648"
    assert len(ostrzezenia) == 1
    assert "228648" in ostrzezenia[0] and "999111" in ostrzezenia[0]


def test_znany_pni_z_inna_nazwa_sieci_ostrzega(conn):
    # rozjazd adresu przy tym samym PNI już ostrzegał, rozjazd nadawcy nie -
    # a to ta sama klasa problemu i tak samo wymaga oka człowieka
    get_or_create_punkt(conn, "Żabka", "Odkryta 24", "228648")
    _, ostrzezenia = get_or_create_punkt(conn, "Groszek", "Odkryta 24", "228648")

    assert len(ostrzezenia) == 1
    assert "Żabka" in ostrzezenia[0] and "Groszek" in ostrzezenia[0]


def test_get_or_create_punkt_nie_zapala_liczy_zpo_dla_zwyklego_klienta(conn):
    # zwykły nadawca (ZUS, PKO...) bez PNI - "w tym ZPO" ma zostać wygaszone
    get_or_create_punkt(conn, "ZUS", "Senatorska 6/8", None)
    row = conn.execute("SELECT liczy_zpo FROM nadawcy WHERE nazwa='ZUS'").fetchone()
    assert row[0] == 0


def test_get_or_create_punkt_regular_client_deduped_by_nadawca_and_adres(conn):
    # klient bez PNI (np. ZUS) - deduplikacja po nadawca+adres, nie tworzymy
    # nowego punktu za każdym razem
    pid1, _ = get_or_create_punkt(conn, "ZUS", "Senatorska 6/8", None)
    pid2, _ = get_or_create_punkt(conn, "ZUS", "Senatorska 6/8", None)
    assert pid1 == pid2


# --- get_or_create_adres: OCHRONA SŁOWNIKA ---------------------------------
#
# Najdroższy błąd całej normalizacji: wpis w `miejscowosci`/`ulice` założony
# z BŁĘDNIE zinterpretowanego adresu. Kolejne adresy podepną się pod niego
# i sprzątanie przestaje być edycją pola, a staje się scalaniem słownika.
# Stąd twarda reguła: słownik widzi wyłącznie to, co parser rozłożył.

def _slowniki_adresowe(conn):
    return (
        conn.execute("SELECT COUNT(*) FROM miejscowosci").fetchone()[0],
        conn.execute("SELECT COUNT(*) FROM ulice").fetchone()[0],
    )


def test_adres_z_pewnoscia_brak_nie_zaklada_miejscowosci_ani_ulicy(conn):
    aid = get_or_create_adres(conn, "Metro Ratusz")

    assert _slowniki_adresowe(conn) == (0, 0)
    wiersz = conn.execute(
        "SELECT surowy, ulica_id, nr_budynku, stan FROM adresy WHERE id=?", (aid,)
    ).fetchone()
    assert wiersz[0] == "Metro Ratusz"
    assert wiersz[1] is None
    assert wiersz[2] is None
    assert wiersz[3] == "surowy"


def test_adres_bez_miejscowosci_nie_zaklada_slownikow_ale_zapisuje_numer(conn):
    """
    `ulice.miejscowosc_id` jest NOT NULL, a domyślenie miasta to osobna
    kaskada - zgadnięcie go tylko po to, żeby mieć na czym zawiesić ulicę,
    byłoby tym samym zakładaniem bytu z niepewnej interpretacji. Numer
    budynku zapisujemy, bo nie zakłada niczego w żadnym słowniku.
    """
    aid = get_or_create_adres(conn, "Kwiatowa 8")

    assert _slowniki_adresowe(conn) == (0, 0)
    wiersz = conn.execute(
        "SELECT ulica_id, nr_budynku, stan FROM adresy WHERE id=?", (aid,)).fetchone()
    assert wiersz[0] is None
    assert wiersz[1] == "8"
    assert wiersz[2] == "sparsowany"


def test_adres_ktory_po_odcieciu_prefiksu_nie_ma_ulicy_nie_zaklada_slownikow(conn):
    """
    „Piaseczno, al. 5" ma niepusty człon ulicy DOPÓKI nie odetnie się
    prefiksu „al." - a potem nie ma go wcale. Do poprawki w `adresy.rozbij`
    dawało to Rozbicie o pewności „pelna" i pustej nazwie ulicy, czyli
    najgorszy możliwy kształt: parser był go PEWNY, więc trafiał prosto do
    słownika i zbierał pod jednym pustym wpisem wszystkie takie adresy.
    """
    get_or_create_adres(conn, "Piaseczno, al. 5")
    get_or_create_adres(conn, "Piaseczno, Aleja 12")

    assert _slowniki_adresowe(conn) == (0, 0)


def test_adres_z_miejscowoscia_zaklada_miejscowosc_i_ulice(conn):
    aid = get_or_create_adres(conn, "Piaseczno, Kwiatowa 8 m. 3")

    assert _slowniki_adresowe(conn) == (1, 1)
    wiersz = conn.execute(
        """SELECT m.nazwa, u.nazwa, a.nr_budynku, a.nr_lokalu, a.stan,
                  a.zrodlo_miejscowosci
           FROM adresy a JOIN ulice u ON u.id = a.ulica_id
           JOIN miejscowosci m ON m.id = u.miejscowosc_id
           WHERE a.id=?""",
        (aid,),
    ).fetchone()
    assert tuple(wiersz) == ("Piaseczno", "Kwiatowa", "8", "3", "sparsowany", "z_adresu")


def test_get_or_create_adres_jest_get_or_create_po_surowym(conn):
    # `surowy` jest tożsamością adresu (UNIQUE), więc drugi zapis tego samego
    # tekstu nie może ani założyć drugiego wiersza, ani zdublować ulicy
    aid1 = get_or_create_adres(conn, "Piaseczno, Kwiatowa 8")
    aid2 = get_or_create_adres(conn, "Piaseczno, Kwiatowa 8")
    assert aid1 == aid2
    assert _slowniki_adresowe(conn) == (1, 1)


def test_ta_sama_ulica_z_prefiksem_i_bez_to_jeden_wpis(conn):
    # w realnych danych ta sama ulica występuje w obu wariantach naraz;
    # gdyby typ wchodził do klucza, byłyby to dwie różne ulice
    get_or_create_adres(conn, "Piaseczno, Kwiatowa 8")
    get_or_create_adres(conn, "Piaseczno, Aleja Kwiatowa 10")

    ulice = conn.execute("SELECT nazwa, typ FROM ulice").fetchall()
    assert [tuple(u) for u in ulice] == [("Kwiatowa", "Aleja")]


def test_typ_ulicy_uzupelnia_sie_w_luke_ale_nie_nadpisuje(conn):
    # pierwszy napotkany zapis bez prefiksu nie może przesądzić, że ulica
    # prefiksu nie ma - ale kolejne warianty nie mogą nadpisywać ustalonego
    mid = conn.execute("INSERT INTO miejscowosci (nazwa) VALUES ('Piaseczno')").lastrowid
    uid = get_or_create_ulica(conn, "Kwiatowa", mid, None)
    get_or_create_ulica(conn, "Kwiatowa", mid, "Aleja")
    get_or_create_ulica(conn, "Kwiatowa", mid, "Plac")

    assert conn.execute("SELECT typ FROM ulice WHERE id=?", (uid,)).fetchone()[0] == "Aleja"


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
