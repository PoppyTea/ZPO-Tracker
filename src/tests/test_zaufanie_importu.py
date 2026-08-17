"""
Model zaufania importu (0.1-alpha.3.2): pliki bez naszego znacznika (albo
z niezgodnym odciskiem) NIE wnoszą PNI ani rejonu - to dwie kolumny, którym
w istniejących Excelach nie można ufać, a PNI jest kluczem tożsamości punktu
(`punkty.pni_zpo UNIQUE`), więc śmieciowa wartość po cichu podpina transakcję
pod cudzy punkt.

Najsubtelniejsza część: podpinanie punktu dla wiersza niezaufanego. Predykat
`AND pni_zpo IS NULL` w `get_or_create_punkt` ominąłby istniejący punkt z PNI
pod tym samym adresem i utworzył duplikat - stąd OSOBNA funkcja, nie flaga
w starej (ścieżka zaufana i scalanie baz nie mogą dryfować). TDD.
"""
from datetime import date

import pytest

from zpo_tracker import repo
from zpo_tracker.importer import get_or_create_punkt, znajdz_lub_utworz_punkt_niezaufany
from zpo_tracker.import_orchestrator import zaimportuj, zwaliduj_wiersze


@pytest.fixture
def conn():
    conn = repo.polacz(":memory:")
    repo.utworz_schemat(conn)
    yield conn
    conn.close()


def _surowy(**nadpisz):
    dane = {
        "data": date(2026, 8, 3),
        " Pełna Nazwa Nadawcy": "Żabka",
        "Adres odbioru dla wszystkich nadawców": "Odkryta 24",
        "Kurier": "Kowalski Jan",
        "Rejon": "WA87",
        " Wpisujemy łączną liczbę odebranych Pocztexów": 3,
        "PNI ZPO": "228648",
        "Wykonawca": "Koli",
    }
    dane.update(nadpisz)
    return dane


# --- znajdz_lub_utworz_punkt_niezaufany: trzy gałęzie ---

def test_dokladne_dopasowanie_nadawcy_i_adresu_podpina_istniejacy(conn):
    id_istniejacy, _ = get_or_create_punkt(conn, "Żabka", "Odkryta 24", None)

    id_znaleziony, ostrzezenia = znajdz_lub_utworz_punkt_niezaufany(
        conn, "Żabka", "Odkryta 24")

    assert id_znaleziony == id_istniejacy
    assert ostrzezenia == []


def test_dokladne_dopasowanie_dziala_takze_dla_punktu_Z_PNI(conn):
    # SEDNO: predykat `AND pni_zpo IS NULL` z get_or_create_punkt ominąłby
    # ten punkt i utworzył duplikat tej samej fizycznej lokalizacji
    id_z_pni, _ = get_or_create_punkt(conn, "Żabka", "Odkryta 24", "228648")

    id_znaleziony, _ = znajdz_lub_utworz_punkt_niezaufany(conn, "Żabka", "Odkryta 24")

    assert id_znaleziony == id_z_pni
    assert conn.execute("SELECT COUNT(*) FROM punkty").fetchone()[0] == 1


def test_jeden_punkt_pod_adresem_innego_nadawcy_podpina_z_ostrzezeniem(conn):
    id_istniejacy, _ = get_or_create_punkt(conn, "Żabka", "Odkryta 24", "228648")

    id_znaleziony, ostrzezenia = znajdz_lub_utworz_punkt_niezaufany(
        conn, "Zabka", "Odkryta 24")  # inna pisownia nadawcy

    assert id_znaleziony == id_istniejacy
    assert len(ostrzezenia) == 1
    assert "Zabka" in ostrzezenia[0]


def test_wiele_punktow_pod_adresem_bez_dopasowania_tworzy_nowy_z_ostrzezeniem(conn):
    # adres z kilkoma nadawcami - wybór "na oko" po cichu zepsułby historię
    # punktu; duplikat punktu jest naprawialny, ciche złe podpięcie nie
    get_or_create_punkt(conn, "Żabka", "Odkryta 24", "228648")
    get_or_create_punkt(conn, "Gemartis", "Odkryta 24", "999999")

    id_nowy, ostrzezenia = znajdz_lub_utworz_punkt_niezaufany(
        conn, "Nowy Nadawca", "Odkryta 24")

    assert conn.execute("SELECT COUNT(*) FROM punkty").fetchone()[0] == 3
    assert conn.execute(
        "SELECT pni_zpo FROM punkty WHERE id = ?", (id_nowy,)).fetchone()[0] is None
    assert len(ostrzezenia) == 1


def test_nowy_adres_tworzy_punkt_bez_pni_i_bez_ostrzezen(conn):
    id_nowy, ostrzezenia = znajdz_lub_utworz_punkt_niezaufany(conn, "ZUS", "Senatorska 6/8")

    wiersz = conn.execute(
        "SELECT pni_zpo, firma_zpo_id FROM punkty WHERE id = ?", (id_nowy,)).fetchone()
    assert wiersz["pni_zpo"] is None
    assert wiersz["firma_zpo_id"] is None
    assert ostrzezenia == []


def test_niezaufany_punkt_nigdy_nie_zaklada_wpisu_w_firmy_zpo(conn):
    znajdz_lub_utworz_punkt_niezaufany(conn, "Żabka", "Odkryta 24")
    assert conn.execute("SELECT COUNT(*) FROM firmy_zpo").fetchone()[0] == 0


# --- zaimportuj: ścieżka niezaufana ---

def test_import_niezaufany_nie_zapisuje_pni(conn):
    zwalidowane, _ = zwaliduj_wiersze([_surowy(**{"PNI ZPO": "228648"})])

    zaimportuj(conn, zwalidowane, zaufany=False)

    assert conn.execute("SELECT pni_zpo FROM punkty").fetchone()[0] is None


def test_import_niezaufany_zapisuje_rejon_jako_kanoniczny_nieznany(conn):
    from zpo_tracker.normalizacja import REJON_NIEZNANY

    zwalidowane, _ = zwaliduj_wiersze([_surowy(Rejon="WA87")])

    zaimportuj(conn, zwalidowane, zaufany=False)

    kod = conn.execute(
        "SELECT r.kod FROM transakcje t JOIN rejony r ON r.id = t.rejon_id").fetchone()[0]
    assert kod == REJON_NIEZNANY


def test_import_niezaufany_wciaz_wnosi_kuriera_adres_i_ilosci(conn):
    # dane czytelne dla człowieka i poprawialne w aplikacji wchodzą normalnie -
    # odcinamy WYŁĄCZNIE to, czego nie da się zweryfikować ani poprawić
    zwalidowane, _ = zwaliduj_wiersze([_surowy()])

    wynik = zaimportuj(conn, zwalidowane, zaufany=False)

    assert wynik["zaimportowano"] == 1
    wiersz = conn.execute(
        """SELECT k.imie_nazwisko AS kurier, p.nadawca, p.adres, t.ilosc_total,
                  w.nazwa AS wykonawca
           FROM transakcje t
           JOIN kurierzy k ON k.id = t.kurier_id
           JOIN punkty p ON p.id = t.punkt_id
           LEFT JOIN wykonawcy w ON w.id = t.wykonawca_id"""
    ).fetchone()
    assert wiersz["kurier"] == "Kowalski Jan"
    assert wiersz["adres"] == "Odkryta 24"
    assert wiersz["ilosc_total"] == 3
    assert wiersz["wykonawca"] == "Koli"


def test_import_niezaufany_ustawia_zrodlo_import(conn):
    zwalidowane, _ = zwaliduj_wiersze([_surowy()])
    zaimportuj(conn, zwalidowane, zaufany=False)
    assert conn.execute("SELECT zrodlo FROM transakcje").fetchone()[0] == "import"


def test_import_zaufany_ustawia_zrodlo_import_zaufany_i_zachowuje_pni(conn):
    zwalidowane, _ = zwaliduj_wiersze([_surowy(**{"PNI ZPO": "228648"})])

    zaimportuj(conn, zwalidowane, zaufany=True)

    wiersz = conn.execute(
        "SELECT t.zrodlo, p.pni_zpo FROM transakcje t JOIN punkty p ON p.id = t.punkt_id"
    ).fetchone()
    assert wiersz["zrodlo"] == "import_zaufany"
    assert wiersz["pni_zpo"] == "228648"


def test_import_niezaufany_nie_aktywuje_pola_w_tym_zpo(conn):
    # czy_nadawca_ma_pni to JEDYNA brama pola "w tym ZPO" (dedukcja.py) -
    # niezaufany import konstrukcyjnie nie może jej otworzyć
    zwalidowane, _ = zwaliduj_wiersze([_surowy(**{"PNI ZPO": "228648"})])

    zaimportuj(conn, zwalidowane, zaufany=False)

    assert repo.czy_nadawca_ma_pni(conn, "Żabka") is False


def test_import_niezaufany_nie_zasmieca_slownika_firm(conn):
    zwalidowane, _ = zwaliduj_wiersze([_surowy(**{"PNI ZPO": "228648"})])

    zaimportuj(conn, zwalidowane, zaufany=False)

    assert conn.execute("SELECT COUNT(*) FROM firmy_zpo").fetchone()[0] == 0


def test_import_niezaufany_nie_dubluje_punktu_istniejacego_z_pni(conn):
    # ten sam adres+nadawca jest już w bazie jako punkt Z PNI (z zaufanego
    # źródła) - niezaufany import ma się do niego PODPIĄĆ, nie tworzyć drugi
    get_or_create_punkt(conn, "Żabka", "Odkryta 24", "228648")
    zwalidowane, _ = zwaliduj_wiersze([_surowy()])

    zaimportuj(conn, zwalidowane, zaufany=False)

    assert conn.execute("SELECT COUNT(*) FROM punkty").fetchone()[0] == 1
    assert conn.execute("SELECT pni_zpo FROM punkty").fetchone()[0] == "228648"


def test_import_domyslnie_jest_niezaufany(conn):
    # bezpieczna wartość domyślna: brak jawnego zaufania == brak zaufania
    zwalidowane, _ = zwaliduj_wiersze([_surowy(**{"PNI ZPO": "228648"})])

    zaimportuj(conn, zwalidowane)

    assert conn.execute("SELECT pni_zpo FROM punkty").fetchone()[0] is None
