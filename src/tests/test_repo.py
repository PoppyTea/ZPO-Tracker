"""
Testy warstwy dostępu do danych: zapis bloku z formularza wprowadzania
i odczyt do przeglądania. SQLite w pamięci, bez mocków. TDD.
"""
import sqlite3
from datetime import date

import pytest

from zpo_tracker import repo
from zpo_tracker.models import Blankiet, WierszBlankietu
from zpo_tracker.normalizacja import REJON_NIEZNANY


@pytest.fixture
def conn():
    conn = repo.polacz(":memory:")
    repo.utworz_schemat(conn)
    yield conn
    conn.close()


def _blok(rejon="WA87", **nadpisz):
    # `rejon` domyślnie tworzy jeden wiersz z tym rejonem - jeśli test podaje
    # własne `wiersze`, ten parametr jest ignorowany (rejon żyje per wiersz
    # od 0.1-alpha.3.1, nie na poziomie Blankietu)
    wiersze = nadpisz.pop("wiersze", None)
    if wiersze is None:
        wiersze = [WierszBlankietu(
            nadawca="Żabka", adres="Odkryta 24", rejon=rejon,
            ilosc_total=3, ilosc_zpo=3)]
    dane = dict(
        kurier="Kowalski Jan",
        data=date(2026, 8, 10),
        wykonawca="Koli",
        wiersze=wiersze,
    )
    dane.update(nadpisz)
    return Blankiet(**dane)


def test_zapisz_blok_tworzy_jedna_transakcje_na_wiersz(conn):
    blok = _blok(wiersze=[
        WierszBlankietu(nadawca="Żabka", adres="Odkryta 24", ilosc_total=3),
        WierszBlankietu(nadawca="ZUS", adres="Senatorska 6/8", ilosc_total=1),
    ])
    wyniki = repo.zapisz_blankiet(conn, blok)
    assert len(wyniki) == 2
    assert all(not w["pominieto"] for w in wyniki)
    count = conn.execute("SELECT COUNT(*) FROM transakcje").fetchone()[0]
    assert count == 2


def test_zapisz_blok_z_nieznanym_rejonem_zapisuje_wpis_kanoniczny(conn):
    # get_or_create_rejon nie zwraca już None dla pustego kodu - dostaje
    # wpis "???" (normalizuj_rejon), więc rejon_id NIE jest NULL
    blok = _blok(rejon=None)
    repo.zapisz_blankiet(conn, blok)
    row = conn.execute(
        "SELECT r.kod FROM transakcje t"
        " JOIN rejony r ON r.id = t.rejon_id LIMIT 1"
    ).fetchone()
    assert row[0] == REJON_NIEZNANY


def test_zapisz_blok_rejon_moze_byc_rozny_per_wiersz(conn):
    # rejon zszedł do wiersza w 0.1-alpha.3.1 - jeden blankiet (kurier+data)
    # może mieć wiersze w różnych rejonach, to zastąpiło bloki REJON+DATA
    blok = _blok(wiersze=[
        WierszBlankietu(nadawca="Żabka", adres="Odkryta 24", rejon="WA87", ilosc_total=3),
        WierszBlankietu(nadawca="ZUS", adres="Senatorska 6/8", rejon="WA88", ilosc_total=1),
    ])
    repo.zapisz_blankiet(conn, blok)
    kody = {r[0] for r in conn.execute(
        "SELECT r.kod FROM transakcje t JOIN rejony r ON r.id = t.rejon_id"
    ).fetchall()}
    assert kody == {"WA87", "WA88"}


def test_zapisz_blok_wykrywa_duplikat_bez_wybuchania(conn):
    blok = _blok()
    repo.zapisz_blankiet(conn, blok)
    wyniki = repo.zapisz_blankiet(conn, blok)  # ten sam blok drugi raz
    assert wyniki[0]["pominieto"] is True
    count = conn.execute("SELECT COUNT(*) FROM transakcje").fetchone()[0]
    assert count == 1


def test_zapisz_blok_reuzywa_istniejacego_kuriera(conn):
    repo.zapisz_blankiet(conn, _blok())
    repo.zapisz_blankiet(conn, _blok(data=date(2026, 8, 11)))
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


def test_zmiana_nazwy_nadawcy_jest_widoczna_w_punktach_bez_zadnej_propagacji(conn):
    """
    To jest cel schematu v4, nie efekt uboczny. Do v3 nazwa nadawcy żyła
    w DWÓCH miejscach naraz (`firmy_zpo.nazwa` i `punkty.nadawca`), więc
    rename w Słownikach musiał ją kopiować do drugiego miejsca, a każde
    pominięcie tej kopii rozjeżdżało obie na stałe i wymagało osobnej
    naprawy danych. W v4 nazwa istnieje raz - nie ma czego propagować
    ani czemu się rozjechać.
    """
    from zpo_tracker.importer import get_or_create_punkt
    get_or_create_punkt(conn, "Żabka", "Odkryta 24", "228648")
    nadawca_id = repo.pobierz_slownik(conn, "nadawcy")[0]["id"]

    repo.zmien_nazwe_w_slowniku(conn, "nadawcy", nadawca_id, "Żabka Polska")

    assert [p["nadawca"] for p in repo.pobierz_punkty(conn)] == ["Żabka Polska"]


def test_zmiana_nazwy_zwyklego_slownika_nie_rusza_punktow(conn):
    # kurierzy/wykonawcy/rejony są referencowane przez transakcje, nie przez
    # punkty - rename w nich nie ma prawa dotknąć nazwy nadawcy
    from zpo_tracker.importer import get_or_create_punkt
    get_or_create_punkt(conn, "Żabka", "Odkryta 24", "228648")
    wpis_id = repo.dodaj_do_slownika(conn, "wykonawcy", "Koli")

    repo.zmien_nazwe_w_slowniku(conn, "wykonawcy", wpis_id, "Koli sp. z o.o.")

    assert [p["nadawca"] for p in repo.pobierz_punkty(conn)] == ["Żabka"]


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


# --- nadawcy, dla których nie liczy się ZPO (ZUS/PKO/Kruk...) ---
# Podzakładka „Popraw / scal nadawcę": jedyna droga, w której rename na nazwę
# JUŻ ZAJĘTĄ jest scaleniem, a nie błędem UNIQUE - a to najczęstsza poprawka
# literówki, bo poprawna forma zwykle już w bazie jest.

def test_pobierz_nadawcow_bez_pni_pomija_nadawcow_liczacych_zpo(conn):
    from zpo_tracker.importer import get_or_create_punkt
    get_or_create_punkt(conn, "Żabka", "Odkryta 24", "228648")  # ma PNI
    get_or_create_punkt(conn, "ZUS", "Senatorska 6/8", None)     # bez PNI

    nadawcy = repo.pobierz_nadawcow_bez_pni(conn)

    assert [n["nazwa"] for n in nadawcy] == ["ZUS"]


def test_pobierz_nadawcow_bez_pni_liczy_punkty(conn):
    from zpo_tracker.importer import get_or_create_punkt
    get_or_create_punkt(conn, "ZUS", "Senatorska 6/8", None)
    get_or_create_punkt(conn, "ZUS", "Inna 5", None)

    nadawcy = repo.pobierz_nadawcow_bez_pni(conn)

    assert nadawcy == [{"nazwa": "ZUS", "liczba_punktow": 2}]


def test_zmien_nadawce_bez_pni_propaguje_do_wszystkich_punktow(conn):
    from zpo_tracker.importer import get_or_create_punkt
    get_or_create_punkt(conn, "ZUS", "Senatorska 6/8", None)
    get_or_create_punkt(conn, "ZUS", "Inna 5", None)

    repo.zmien_nadawce_bez_pni(conn, "ZUS", "Zakład Ubezpieczeń Społecznych")

    nadawcy = {p["nadawca"] for p in repo.pobierz_punkty(conn)}
    assert nadawcy == {"Zakład Ubezpieczeń Społecznych"}


def test_zmien_nadawce_bez_pni_nie_rusza_nadawcy_liczacego_zpo(conn):
    from zpo_tracker.importer import get_or_create_punkt
    get_or_create_punkt(conn, "Żabka", "Odkryta 24", "228648")

    repo.zmien_nadawce_bez_pni(conn, "Żabka", "Żabka Polska")

    assert repo.pobierz_punkty(conn)[0]["nadawca"] == "Żabka"


def test_zmien_nadawce_bez_pni_zlepienie_przepina_transakcje_i_usuwa_przegrywajacy(conn):
    # dwa RÓŻNE punkty (różne pisownie nadawcy), ten sam adres - po scaleniu
    # nadawców obie pary (nadawca_id, adres_id) byłyby identyczne, czego
    # zabrania UNIQUE, więc kolizję trzeba wykryć PRZED przepięciem
    from zpo_tracker.importer import get_or_create_punkt
    id_a, _ = get_or_create_punkt(conn, "ZUS", "Senatorska 6/8", None)
    id_b, _ = get_or_create_punkt(conn, "Zaklad Ubezpieczen", "Senatorska 6/8", None)
    kurier_id = conn.execute(
        "INSERT INTO kurierzy(imie_nazwisko) VALUES ('Kowalski Jan')").lastrowid
    conn.execute(
        "INSERT INTO transakcje(data, kurier_id, punkt_id, ilosc_total) VALUES (?,?,?,?)",
        ("2026-08-10", kurier_id, id_b, 3))

    repo.zmien_nadawce_bez_pni(conn, "Zaklad Ubezpieczen", "ZUS")

    punkty = [p for p in repo.pobierz_punkty(conn) if p["nadawca"] == "ZUS"]
    assert len(punkty) == 1  # zlepione w jeden
    transakcja = conn.execute("SELECT punkt_id FROM transakcje").fetchone()
    assert transakcja["punkt_id"] == id_a  # przepięta na wygrywający (najniższe id)
    assert conn.execute(
        "SELECT COUNT(*) FROM punkty WHERE id = ?", (id_b,)).fetchone()[0] == 0


def test_zmien_nadawce_bez_pni_kolizja_transakcji_blokuje_calosc(conn):
    from zpo_tracker.importer import get_or_create_punkt
    id_a, _ = get_or_create_punkt(conn, "ZUS", "Senatorska 6/8", None)
    id_b, _ = get_or_create_punkt(conn, "Zaklad Ubezpieczen", "Senatorska 6/8", None)
    kurier_id = conn.execute(
        "INSERT INTO kurierzy(imie_nazwisko) VALUES ('Kowalski Jan')").lastrowid
    # OBA punkty mają transakcję tego samego kuriera+daty -> po zlepieniu
    # kolidowałyby na UNIQUE(data, kurier_id, punkt_id)
    conn.execute(
        "INSERT INTO transakcje(data, kurier_id, punkt_id, ilosc_total) VALUES (?,?,?,?)",
        ("2026-08-10", kurier_id, id_a, 1))
    conn.execute(
        "INSERT INTO transakcje(data, kurier_id, punkt_id, ilosc_total) VALUES (?,?,?,?)",
        ("2026-08-10", kurier_id, id_b, 2))

    with pytest.raises(repo.KolizjaTransakcji):
        repo.zmien_nadawce_bez_pni(conn, "Zaklad Ubezpieczen", "ZUS")

    # CAŁOŚĆ zablokowana - nawet sam rename się nie utrzymał
    nadawcy = {p["nadawca"] for p in repo.pobierz_punkty(conn)}
    assert nadawcy == {"ZUS", "Zaklad Ubezpieczen"}
    assert conn.execute("SELECT COUNT(*) FROM transakcje").fetchone()[0] == 2


def test_mozna_usunac_zwykly_nieuzywany_rejon(conn):
    wpis_id = repo.dodaj_do_slownika(conn, "rejony", "WA87")
    repo.usun_z_slownika(conn, "rejony", wpis_id)
    nazwy = [w["nazwa"] for w in repo.pobierz_slownik(conn, "rejony")]
    assert nazwy == [REJON_NIEZNANY]  # kanoniczny wiersz z seeda zostaje


def test_usun_z_slownika_nieuzywany_wpis(conn):
    wpis_id = repo.dodaj_do_slownika(conn, "nadawcy", "Testowa Sieć")
    repo.usun_z_slownika(conn, "nadawcy", wpis_id)
    assert repo.pobierz_slownik(conn, "nadawcy") == []


def test_scal_kurierow_przenosi_transakcje_i_usuwa_stary(conn):
    blok = _blok(kurier="Wołczuk Rafal")
    repo.zapisz_blankiet(conn, blok)
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


def test_pobierz_punkty_pokazuje_nadawce_adres_i_flage_zpo(conn):
    blok = _blok(wiersze=[
        WierszBlankietu(nadawca="Żabka", adres="Odkryta 24", pni_zpo="228648", ilosc_total=3),
    ])
    repo.zapisz_blankiet(conn, blok)
    punkty = repo.pobierz_punkty(conn)
    assert len(punkty) == 1
    assert punkty[0]["nadawca"] == "Żabka"
    assert punkty[0]["adres"] == "Odkryta 24"
    assert punkty[0]["pni_zpo"] == "228648"
    assert punkty[0]["liczy_zpo"] == 1


def test_dane_przetrwaja_zamkniecie_i_ponowne_otwarcie_polaczenia(tmp_path):
    # GH #4 (krytyczny): "zapisane dane znikają po ponownym uruchomieniu"
    # - sqlite3 domyślnie wymaga jawnego commit(), inaczej zamknięcie
    # połączenia po prostu wycofuje niezapisane zmiany
    sciezka = str(tmp_path / "test.db")

    polaczenie_1 = repo.polacz(sciezka)
    repo.utworz_schemat(polaczenie_1)
    repo.zapisz_blankiet(polaczenie_1, _blok())
    polaczenie_1.close()

    polaczenie_2 = repo.polacz(sciezka)
    liczba = polaczenie_2.execute("SELECT COUNT(*) FROM transakcje").fetchone()[0]
    polaczenie_2.close()
    assert liczba == 1


def test_pobierz_unikalne_nadawcow(conn):
    repo.zapisz_blankiet(conn, _blok(wiersze=[
        WierszBlankietu(nadawca="Żabka", adres="Odkryta 24", ilosc_total=1),
        WierszBlankietu(nadawca="ZUS", adres="Senatorska 6/8", ilosc_total=1),
    ]))
    repo.zapisz_blankiet(conn, _blok(data=date(2026, 8, 11), wiersze=[
        WierszBlankietu(nadawca="Żabka", adres="Odkryta 24", ilosc_total=1),
    ]))
    assert repo.pobierz_unikalne_nadawcow(conn) == ["ZUS", "Żabka"]


def test_pobierz_unikalne_adresy(conn):
    repo.zapisz_blankiet(conn, _blok(wiersze=[
        WierszBlankietu(nadawca="Żabka", adres="Odkryta 24", ilosc_total=1),
        WierszBlankietu(nadawca="ZUS", adres="Senatorska 6/8", ilosc_total=1),
    ]))
    assert repo.pobierz_unikalne_adresy(conn) == ["Odkryta 24", "Senatorska 6/8"]


def test_pobierz_transakcje_zwraca_czytelne_nazwy(conn):
    repo.zapisz_blankiet(conn, _blok())
    wiersze = repo.pobierz_transakcje(conn)
    assert len(wiersze) == 1
    w = wiersze[0]
    assert w["kurier"] == "Kowalski Jan"
    assert w["nadawca"] == "Żabka"
    assert w["rejon"] == "WA87"
    assert w["ilosc_total"] == 3


# --- pobierz_transakcje: filtry widoku poprawek (0.1-alpha.3.2) ---

def test_pobierz_transakcje_zawiera_pola_do_edycji_i_sesji(conn):
    repo.zapisz_blankiet(conn, _blok(), sesja_uuid="sesja-1")
    w = repo.pobierz_transakcje(conn)[0]
    assert w["id"] is not None
    assert w["uuid"] is not None
    assert w["utworzono"] is not None
    assert w["sesja_uuid"] == "sesja-1"
    assert w["zrodlo"] == "formularz"


def test_pobierz_transakcje_filtruje_po_kurierze(conn):
    repo.zapisz_blankiet(conn, _blok(kurier="Kowalski Jan"))
    repo.zapisz_blankiet(conn, _blok(kurier="Nowak Piotr", wiersze=[
        WierszBlankietu(nadawca="Żabka", adres="Inna 5", ilosc_total=1)]))
    wiersze = repo.pobierz_transakcje(conn, kurier="Nowak Piotr")
    assert len(wiersze) == 1
    assert wiersze[0]["kurier"] == "Nowak Piotr"


def test_pobierz_transakcje_filtruje_po_zakresie_dat(conn):
    repo.zapisz_blankiet(conn, _blok(data=date(2026, 8, 1)))
    repo.zapisz_blankiet(conn, _blok(data=date(2026, 8, 10), wiersze=[
        WierszBlankietu(nadawca="Żabka", adres="Inna 5", ilosc_total=1)]))
    wiersze = repo.pobierz_transakcje(conn, data_od=date(2026, 8, 5), data_do=date(2026, 8, 15))
    assert len(wiersze) == 1
    assert wiersze[0]["data"] == "2026-08-10"


def test_pobierz_transakcje_filtruje_po_sesji(conn):
    repo.zapisz_blankiet(conn, _blok(), sesja_uuid="sesja-a")
    repo.zapisz_blankiet(conn, _blok(wiersze=[
        WierszBlankietu(nadawca="Żabka", adres="Inna 5", ilosc_total=1)]), sesja_uuid="sesja-b")
    wiersze = repo.pobierz_transakcje(conn, sesja_uuid="sesja-a")
    assert len(wiersze) == 1
    assert wiersze[0]["sesja_uuid"] == "sesja-a"


def test_pobierz_transakcje_filtruje_po_tekscie_nadawcy_lub_adresu(conn):
    repo.zapisz_blankiet(conn, _blok(wiersze=[
        WierszBlankietu(nadawca="Żabka", adres="Odkryta 24", ilosc_total=1)]))
    repo.zapisz_blankiet(conn, _blok(wiersze=[
        WierszBlankietu(nadawca="ZUS", adres="Inna 5", ilosc_total=1)]))
    wiersze = repo.pobierz_transakcje(conn, tekst="Odkryta")
    assert len(wiersze) == 1
    assert wiersze[0]["adres"] == "Odkryta 24"

    wiersze_nadawcy = repo.pobierz_transakcje(conn, tekst="ZUS")
    assert len(wiersze_nadawcy) == 1
    assert wiersze_nadawcy[0]["nadawca"] == "ZUS"


def test_pobierz_transakcje_tekst_nie_traktuje_procenta_jako_wieloznacznika(conn):
    # pole "Szukaj" to wejście użytkownika, nie wzorzec LIKE - "%"/"_"
    # muszą szukać dosłownego znaku, inaczej "%" dopasowuje wszystko i
    # "Odkryta_24" dopasowuje też "Odkryta 24"
    repo.zapisz_blankiet(conn, _blok(wiersze=[
        WierszBlankietu(nadawca="Żabka", adres="Odkryta 24", ilosc_total=1)]))
    assert repo.pobierz_transakcje(conn, tekst="%") == []
    assert repo.pobierz_transakcje(conn, tekst="Odkryta_24") == []


def test_pobierz_transakcje_filtry_laczone_koniunkcja(conn):
    repo.zapisz_blankiet(conn, _blok(kurier="Kowalski Jan", data=date(2026, 8, 1)))
    repo.zapisz_blankiet(conn, _blok(kurier="Kowalski Jan", data=date(2026, 8, 20), wiersze=[
        WierszBlankietu(nadawca="Żabka", adres="Inna 5", ilosc_total=1)]))
    wiersze = repo.pobierz_transakcje(
        conn, kurier="Kowalski Jan", data_od=date(2026, 8, 15))
    assert len(wiersze) == 1
    assert wiersze[0]["data"] == "2026-08-20"


def test_pobierz_transakcje_bez_filtrow_zwraca_wszystko(conn):
    repo.zapisz_blankiet(conn, _blok())
    repo.zapisz_blankiet(conn, _blok(wiersze=[
        WierszBlankietu(nadawca="Żabka", adres="Inna 5", ilosc_total=1)]))
    assert len(repo.pobierz_transakcje(conn)) == 2


# --- zapytania dedukcyjne (0.1-alpha.3.1, patrz dedukcja.py) ---

def test_znajdz_punkty_po_adresie_trafienie_dokladne(conn):
    repo.zapisz_blankiet(conn, _blok())
    wynik = repo.znajdz_punkty_po_adresie(conn, "Odkryta 24")
    assert len(wynik) == 1
    assert wynik[0]["nadawca"] == "Żabka"
    assert wynik[0]["adres"] == "Odkryta 24"


def test_znajdz_punkty_po_adresie_pusty_wynik(conn):
    assert repo.znajdz_punkty_po_adresie(conn, "Nieistniejąca 1") == []


def test_znajdz_punkty_po_adresie_trafienie_rozmyte_gdy_brak_dokladnego(conn):
    # punkt w bazie znormalizowany (klucz_bialych_znakow), ale to, co
    # wpisuje użytkownik, nie musi być - bez fuzzy fallbacku "odkryta  24"
    # (podwójna spacja, mała litera) dałoby zero trafień
    repo.zapisz_blankiet(conn, _blok())
    wynik = repo.znajdz_punkty_po_adresie(conn, "odkryta  24")
    assert len(wynik) == 1
    assert wynik[0]["adres"] == "Odkryta 24"


def test_znajdz_punkty_po_adresie_wiele_nadawcow_pod_tym_samym_adresem(conn):
    repo.zapisz_blankiet(conn, _blok(wiersze=[
        WierszBlankietu(nadawca="Żabka", adres="Solidarności 117",
                        pni_zpo="228648", ilosc_total=3),
    ]))
    repo.zapisz_blankiet(conn, _blok(wiersze=[
        WierszBlankietu(nadawca="Gemartis", adres="Solidarności 117", ilosc_total=1),
    ]))
    wynik = repo.znajdz_punkty_po_adresie(conn, "Solidarności 117")
    nadawcy = {w["nadawca"] for w in wynik}
    assert nadawcy == {"Żabka", "Gemartis"}


def test_czy_nadawca_liczy_zpo_prawda(conn):
    repo.zapisz_blankiet(conn, _blok(wiersze=[
        WierszBlankietu(nadawca="Żabka", adres="Odkryta 24",
                        pni_zpo="228648", ilosc_total=3),
    ]))
    assert repo.czy_nadawca_liczy_zpo(conn, "Żabka") is True


def test_czy_nadawca_liczy_zpo_falsz_dla_zwyklego_nadawcy(conn):
    repo.zapisz_blankiet(conn, _blok(wiersze=[
        WierszBlankietu(nadawca="ZUS", adres="Senatorska 6/8", ilosc_total=1),
    ]))
    assert repo.czy_nadawca_liczy_zpo(conn, "ZUS") is False


def test_czy_nadawca_liczy_zpo_nieznany_nadawca(conn):
    assert repo.czy_nadawca_liczy_zpo(conn, "Nikt Taki") is False


def test_czy_nadawca_liczy_zpo_nie_wymaga_znanego_pni(conn):
    """
    Sedno zmiany w v4: punkt JEST ZPO, ale PNI trzeba dopiero zdobyć
    z paragonu. Do v3 pytaliśmy o obecność PNI, więc pole "w tym ZPO" było
    wtedy wygaszone i kurierowej liczby nie dało się w ogóle wpisać -
    a to najczęstszy przypadek, nie brzegowy.
    """
    repo.zapisz_blankiet(conn, _blok(wiersze=[
        WierszBlankietu(nadawca="Żabka", adres="Odkryta 24",
                        pni_zpo="228648", ilosc_total=3),
    ]))
    conn.execute("UPDATE punkty SET pni_zpo = NULL")

    assert repo.czy_nadawca_liczy_zpo(conn, "Żabka") is True


def test_historia_rejonow_punktu_jednoznaczna(conn):
    repo.zapisz_blankiet(conn, _blok(rejon="WA87"))
    punkt_id = conn.execute("SELECT id FROM punkty").fetchone()[0]
    historia = repo.historia_rejonow_punktu(conn, punkt_id)
    assert historia == [{"kod": "WA87", "liczba": 1, "ostatnia_data": "2026-08-10"}]


def test_historia_rejonow_punktu_posortowana_po_liczbie(conn):
    repo.zapisz_blankiet(conn, _blok(rejon="WA87", data=date(2026, 8, 1)))
    repo.zapisz_blankiet(conn, _blok(rejon="WA87", data=date(2026, 8, 2)))
    repo.zapisz_blankiet(conn, _blok(rejon="WA88", data=date(2026, 8, 3)))
    punkt_id = conn.execute("SELECT id FROM punkty").fetchone()[0]
    historia = repo.historia_rejonow_punktu(conn, punkt_id)
    assert [h["kod"] for h in historia] == ["WA87", "WA88"]
    assert historia[0]["liczba"] == 2


def test_historia_rejonow_punktu_brak_historii(conn):
    assert repo.historia_rejonow_punktu(conn, 999999) == []


def test_historia_wykonawcow_kuriera_jednoznaczna(conn):
    repo.zapisz_blankiet(conn, _blok(wykonawca="Koli"))
    historia = repo.historia_wykonawcow_kuriera(conn, "Kowalski Jan")
    assert historia == [{"nazwa": "Koli", "liczba": 1, "ostatnia_data": "2026-08-10"}]


def test_historia_wykonawcow_kuriera_posortowana_po_ostatniej_dacie(conn):
    # 69/70 kurierów w realnych danych ma jednego wykonawcę - niejednoznaczność
    # to realna zmiana firmy, więc sortujemy po świeżości, nie po liczbie
    repo.zapisz_blankiet(conn, _blok(wykonawca="Koli", data=date(2026, 8, 1)))
    repo.zapisz_blankiet(conn, _blok(wykonawca="Koli", data=date(2026, 8, 2)))
    repo.zapisz_blankiet(conn, _blok(wykonawca="Translist", data=date(2026, 8, 5)))
    historia = repo.historia_wykonawcow_kuriera(conn, "Kowalski Jan")
    assert [h["nazwa"] for h in historia] == ["Translist", "Koli"]


def test_historia_wykonawcow_kuriera_nowy_kurier(conn):
    assert repo.historia_wykonawcow_kuriera(conn, "Nikt Taki") == []


# --- wyszukiwanie punktu po PNI (0.1-alpha.3.3) ------------------------
#
# Prośba użytkowników: "wyszukiwanie sklepów po PNI, jeśli było już kiedyś
# w bazie". Odwraca dzisiejszy kierunek dedukcji, w której PNI jest
# WYŁĄCZNIE polem wyjściowym, wyprowadzanym z rozstrzygniętego punktu.

def _punkt_z_pni(conn, pni, nadawca="Żabka", adres="Odkryta 24"):
    from zpo_tracker.importer import get_or_create_punkt
    get_or_create_punkt(conn, nadawca, adres, pni)


def test_znajduje_punkt_po_pni(conn):
    _punkt_z_pni(conn, "231270")
    punkt = repo.znajdz_punkt_po_pni(conn, "231270")
    assert punkt["nadawca"] == "Żabka"
    assert punkt["adres"] == "Odkryta 24"


def test_nieznane_pni_daje_nic(conn):
    _punkt_z_pni(conn, "231270")
    assert repo.znajdz_punkt_po_pni(conn, "999999") is None


def test_biale_znaki_wokol_pni_nie_przeszkadzaja(conn):
    _punkt_z_pni(conn, "231270")
    assert repo.znajdz_punkt_po_pni(conn, "  231270 ")["nadawca"] == "Żabka"


def test_pni_porownywane_jest_tekstowo_nie_liczbowo(conn):
    """PNI to KLUCZ, nie wielkość liczbowa. Zrównanie "007" z "7" to
    dokładnie ten błąd koercji, który w 0.1-alpha.3.2 rozdwajał ten sam
    fizyczny punkt na dwa wpisy przy round-tripie eksport-import."""
    _punkt_z_pni(conn, "007", nadawca="Orlen", adres="Marsa 1")
    _punkt_z_pni(conn, "7", nadawca="RUCH", adres="Marsa 2")
    assert repo.znajdz_punkt_po_pni(conn, "007")["nadawca"] == "Orlen"
    assert repo.znajdz_punkt_po_pni(conn, "7")["nadawca"] == "RUCH"


def test_pni_podane_jako_liczba_tez_dziala(conn):
    """GUI może przekazać int, jeśli ktoś wpisze same cyfry."""
    _punkt_z_pni(conn, "231270")
    assert repo.znajdz_punkt_po_pni(conn, 231270)["nadawca"] == "Żabka"


@pytest.mark.parametrize("puste", [None, "", "   "])
def test_puste_pni_nie_szuka(conn, puste):
    _punkt_z_pni(conn, "231270")
    assert repo.znajdz_punkt_po_pni(conn, puste) is None
