"""
Testy warstwy dostępu do danych: zapis bloku z formularza wprowadzania
i odczyt do przeglądania. SQLite w pamięci, bez mocków. TDD.
"""
import sqlite3
from datetime import date

import pytest

from zpo_tracker import repo
from zpo_tracker.models import BlankietBlok, WierszBlankietu
from zpo_tracker.normalizacja import REJON_NIEZNANY


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


def test_zapisz_bloki_laczy_wyniki_z_kilku_blokow(conn):
    blok_a = _blok(rejon="WA87", wiersze=[
        WierszBlankietu(nadawca="Żabka", adres="Odkryta 24", ilosc_total=3),
    ])
    blok_b = _blok(rejon="WA88", wiersze=[
        WierszBlankietu(nadawca="ZUS", adres="Senatorska 6/8", ilosc_total=1),
        WierszBlankietu(nadawca="PKO", adres="Marszałkowska 1", ilosc_total=2),
    ])
    wyniki = repo.zapisz_bloki(conn, [blok_a, blok_b])
    assert len(wyniki) == 3
    assert conn.execute("SELECT COUNT(*) FROM transakcje").fetchone()[0] == 3


def test_zapisz_blok_z_nieznanym_rejonem_zapisuje_wpis_kanoniczny(conn):
    # get_or_create_rejon nie zwraca już None dla pustego kodu - dostaje
    # wpis "???" (normalizuj_rejon), więc rejon_id NIE jest NULL
    from zpo_tracker.normalizacja import REJON_NIEZNANY
    blok = _blok(rejon=None, komentarz="rejon nieznany, okolice Legionowa")
    repo.zapisz_blok(conn, blok)
    row = conn.execute(
        "SELECT r.kod, t.komentarz FROM transakcje t"
        " JOIN rejony r ON r.id = t.rejon_id LIMIT 1"
    ).fetchone()
    assert row[0] == REJON_NIEZNANY
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


# --- ścieżka do schema.sql musi działać też spakowana w .exe (PyInstaller
#     rozpakowuje pliki danych do sys._MEIPASS, nie do drzewa źródeł) ---

def test_resolve_schema_path_dev_wskazuje_na_schema_sql_w_repo(tmp_path):
    sciezka = repo._resolve_schema_path(frozen=False)
    assert sciezka.name == "schema.sql"
    assert sciezka.is_file()


def test_resolve_schema_path_w_trybie_spakowanym_uzywa_meipass(tmp_path):
    (tmp_path / "schema.sql").write_text("-- test")
    sciezka = repo._resolve_schema_path(frozen=True, meipass=str(tmp_path))
    assert sciezka == tmp_path / "schema.sql"


def test_pobierz_slownik_kurierzy(conn):
    repo.dodaj_do_slownika(conn, "kurierzy", "Nowak Piotr")
    wpisy = repo.pobierz_slownik(conn, "kurierzy")
    assert wpisy == [{"id": 1, "nazwa": "Nowak Piotr"}]


def test_dodaj_do_slownika_normalizuje_biale_znaki(conn):
    repo.dodaj_do_slownika(conn, "wykonawcy", "  Koli  ")
    wpisy = repo.pobierz_slownik(conn, "wykonawcy")
    assert wpisy[0]["nazwa"] == "Koli"


def test_zmien_nazwe_w_slowniku(conn):
    # rejony mają od schema.sql zaseedowany kanoniczny wiersz "???"
    # (patrz normalizacja.REJON_NIEZNANY) - stąd sprawdzenie PO id, nie
    # zakładanie, że to jedyny wiersz w słowniku
    wpis_id = repo.dodaj_do_slownika(conn, "rejony", "WA87")
    repo.zmien_nazwe_w_slowniku(conn, "rejony", wpis_id, "WA88")
    wpisy = {w["id"]: w["nazwa"] for w in repo.pobierz_slownik(conn, "rejony")}
    assert wpisy[wpis_id] == "WA88"


def test_zmiana_nazwy_firmy_zpo_propaguje_do_punktow(conn):
    # firmy_zpo to jedyny "prosty słownik", który ma zdenormalizowanego
    # bliźniaka w punkty.nadawca - bez propagacji rename w Słownikach
    # natychmiast rozjeżdża obie kopie i nic tego nie naprawia
    from zpo_tracker.importer import get_or_create_punkt
    get_or_create_punkt(conn, "Żabka", "Odkryta 24", "228648")
    firma_id = repo.pobierz_slownik(conn, "firmy_zpo")[0]["id"]

    repo.zmien_nazwe_w_slowniku(conn, "firmy_zpo", firma_id, "Żabka Polska")

    nadawcy = [r[0] for r in conn.execute("SELECT nadawca FROM punkty")]
    assert nadawcy == ["Żabka Polska"]


def test_zmiana_nazwy_zwyklego_slownika_nie_rusza_punktow(conn):
    # kurierzy/wykonawcy/rejony są referencowane wyłącznie przez FK -
    # propagacja dotyczy TYLKO firmy_zpo, nie wszystkich słowników
    from zpo_tracker.importer import get_or_create_punkt
    get_or_create_punkt(conn, "Żabka", "Odkryta 24", "228648")
    wpis_id = repo.dodaj_do_slownika(conn, "wykonawcy", "Koli")

    repo.zmien_nazwe_w_slowniku(conn, "wykonawcy", wpis_id, "Koli sp. z o.o.")

    assert [r[0] for r in conn.execute("SELECT nadawca FROM punkty")] == ["Żabka"]


def test_dodaj_do_slownika_rejon_smieciowy_trafia_w_kanoniczny_wiersz(conn):
    # dodaj_do_slownika("rejony", ...) idzie przez get_or_create_rejon - baza
    # ma zaseedowany kanoniczny wiersz od startu, więc "+ dodaj" ze śmieciową
    # wartością musi trafić w NIEGO, nie próbować stworzyć drugi taki sam
    kanoniczny_id = repo.pobierz_slownik(conn, "rejony")[0]["id"]
    wpis_id = repo.dodaj_do_slownika(conn, "rejony", "-")
    assert wpis_id == kanoniczny_id
    assert repo.pobierz_slownik(conn, "rejony") == [
        {"id": kanoniczny_id, "nazwa": REJON_NIEZNANY}]


def test_zmien_nazwe_na_smiec_koliduje_z_kanonicznym_wierszem(conn):
    # normalizuj_rejon() jest stosowane przy renamie, więc zmiana nazwy na
    # śmieć trafia w ten sam klucz co zaseedowany "???" - kolizja UNIQUE,
    # dokładnie tak samo jak rename na dowolną już istniejącą nazwę w
    # jakimkolwiek innym słowniku. To NIE crashuje aplikacji (Tk łapie
    # nieobsłużone wyjątki z callbacków - patrz dziennik.py), ale funkcja
    # "scal" dla rejonów nie istnieje, więc na razie to twardy błąd, nie
    # ciche scalenie.
    wpis_id = repo.dodaj_do_slownika(conn, "rejony", "WA87")
    with pytest.raises(sqlite3.IntegrityError):
        repo.zmien_nazwe_w_slowniku(conn, "rejony", wpis_id, "n/a")


def test_nie_mozna_zmienic_nazwy_kanonicznego_rejonu_nieznanego(conn):
    wpis_id = repo.dodaj_do_slownika(conn, "rejony", "???")
    with pytest.raises(ValueError, match="kanoniczn"):
        repo.zmien_nazwe_w_slowniku(conn, "rejony", wpis_id, "WA87")


def test_nie_mozna_usunac_kanonicznego_rejonu_nieznanego(conn):
    wpis_id = repo.dodaj_do_slownika(conn, "rejony", "???")
    with pytest.raises(ValueError, match="kanoniczn"):
        repo.usun_z_slownika(conn, "rejony", wpis_id)


def test_mozna_usunac_zwykly_nieuzywany_rejon(conn):
    wpis_id = repo.dodaj_do_slownika(conn, "rejony", "WA87")
    repo.usun_z_slownika(conn, "rejony", wpis_id)
    nazwy = [w["nazwa"] for w in repo.pobierz_slownik(conn, "rejony")]
    assert nazwy == [REJON_NIEZNANY]  # kanoniczny wiersz z seeda zostaje


def test_usun_z_slownika_nieuzywany_wpis(conn):
    wpis_id = repo.dodaj_do_slownika(conn, "firmy_zpo", "Testowa Sieć")
    repo.usun_z_slownika(conn, "firmy_zpo", wpis_id)
    assert repo.pobierz_slownik(conn, "firmy_zpo") == []


def test_scal_kurierow_przenosi_transakcje_i_usuwa_stary(conn):
    blok = _blok(kurier="Wołczuk Rafal")
    repo.zapisz_blok(conn, blok)
    id_stary = conn.execute(
        "SELECT id FROM kurierzy WHERE imie_nazwisko='Wołczuk Rafal'"
    ).fetchone()[0]
    id_nowy = repo.dodaj_do_slownika(conn, "kurierzy", "Wołczuk Rafał")

    repo.scal_kurierow(conn, id_z=id_stary, id_do=id_nowy)

    nazwiska = [r[0] for r in conn.execute("SELECT imie_nazwisko FROM kurierzy").fetchall()]
    assert nazwiska == ["Wołczuk Rafał"]
    kurier_transakcji = conn.execute(
        "SELECT kurier_id FROM transakcje"
    ).fetchone()[0]
    assert kurier_transakcji == id_nowy


def test_pobierz_punkty_z_nazwa_firmy_zpo(conn):
    blok = _blok(wiersze=[
        WierszBlankietu(nadawca="Żabka", adres="Odkryta 24", pni_zpo="228648", ilosc_total=3),
    ])
    repo.zapisz_blok(conn, blok)
    punkty = repo.pobierz_punkty(conn)
    assert len(punkty) == 1
    assert punkty[0]["nadawca"] == "Żabka"
    assert punkty[0]["firma_zpo"] == "Żabka"


def test_dane_przetrwaja_zamkniecie_i_ponowne_otwarcie_polaczenia(tmp_path):
    # GH #4 (krytyczny): "zapisane dane znikają po ponownym uruchomieniu"
    # - sqlite3 domyślnie wymaga jawnego commit(), inaczej zamknięcie
    # połączenia po prostu wycofuje niezapisane zmiany
    sciezka = str(tmp_path / "test.db")

    polaczenie_1 = repo.polacz(sciezka)
    repo.utworz_schemat(polaczenie_1)
    repo.zapisz_blok(polaczenie_1, _blok())
    polaczenie_1.close()

    polaczenie_2 = repo.polacz(sciezka)
    liczba = polaczenie_2.execute("SELECT COUNT(*) FROM transakcje").fetchone()[0]
    polaczenie_2.close()
    assert liczba == 1


def test_pobierz_unikalne_nadawcow(conn):
    repo.zapisz_blok(conn, _blok(wiersze=[
        WierszBlankietu(nadawca="Żabka", adres="Odkryta 24", ilosc_total=1),
        WierszBlankietu(nadawca="ZUS", adres="Senatorska 6/8", ilosc_total=1),
    ]))
    repo.zapisz_blok(conn, _blok(data=date(2026, 8, 11), wiersze=[
        WierszBlankietu(nadawca="Żabka", adres="Odkryta 24", ilosc_total=1),
    ]))
    assert repo.pobierz_unikalne_nadawcow(conn) == ["ZUS", "Żabka"]


def test_pobierz_unikalne_adresy(conn):
    repo.zapisz_blok(conn, _blok(wiersze=[
        WierszBlankietu(nadawca="Żabka", adres="Odkryta 24", ilosc_total=1),
        WierszBlankietu(nadawca="ZUS", adres="Senatorska 6/8", ilosc_total=1),
    ]))
    assert repo.pobierz_unikalne_adresy(conn) == ["Odkryta 24", "Senatorska 6/8"]


def test_pobierz_transakcje_zwraca_czytelne_nazwy(conn):
    repo.zapisz_blok(conn, _blok())
    wiersze = repo.pobierz_transakcje(conn)
    assert len(wiersze) == 1
    w = wiersze[0]
    assert w["kurier"] == "Kowalski Jan"
    assert w["nadawca"] == "Żabka"
    assert w["rejon"] == "WA87"
    assert w["ilosc_total"] == 3
