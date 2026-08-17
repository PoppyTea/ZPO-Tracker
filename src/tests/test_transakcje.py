"""
Jawne transakcje. SQLite w pamięci, bez mocków. TDD.

Dlaczego własny helper, a nie wbudowane `with conn:` - przy
`isolation_level=None` (autocommit, ustawione w `repo.polacz` dla GH #4)
wbudowany menedżer kontekstu połączenia **nic nie wycofuje**. Kod używający
`with conn:` wygląda poprawnie, przechodzi pobieżny test i nie robi
absolutnie nic. Pierwszy test niżej pilnuje dokładnie tej różnicy.
"""
import sqlite3
from datetime import date

import pytest

from zpo_tracker import repo


@pytest.fixture
def conn():
    conn = repo.polacz(":memory:")
    repo.utworz_schemat(conn)
    yield conn
    conn.close()


# --- transakcja ---

def test_wbudowane_with_conn_nic_nie_wycofuje(conn):
    """
    Nie test naszego kodu, tylko PRZYPIĘCIE zachowania sqlite3, na którym
    opiera się istnienie `repo.transakcja`. Gdyby to kiedyś przestało być
    prawdą, ten test zapali się i będzie można uprościć implementację.
    """
    conn.execute("INSERT INTO kurierzy(imie_nazwisko) VALUES ('A')")
    try:
        with conn:
            conn.execute("INSERT INTO kurierzy(imie_nazwisko) VALUES ('B')")
            raise RuntimeError("awaria w środku")
    except RuntimeError:
        pass
    ile = conn.execute("SELECT count(*) FROM kurierzy").fetchone()[0]
    assert ile == 2, "gdyby with conn: działało, byłoby 1"


def test_transakcja_wycofuje_zmiany_przy_wyjatku(conn):
    try:
        with repo.transakcja(conn):
            conn.execute("INSERT INTO kurierzy(imie_nazwisko) VALUES ('A')")
            raise RuntimeError("awaria w środku")
    except RuntimeError:
        pass
    assert conn.execute("SELECT count(*) FROM kurierzy").fetchone()[0] == 0


def test_transakcja_zatwierdza_gdy_brak_wyjatku(conn):
    with repo.transakcja(conn):
        conn.execute("INSERT INTO kurierzy(imie_nazwisko) VALUES ('A')")
    assert conn.execute("SELECT count(*) FROM kurierzy").fetchone()[0] == 1


def test_transakcja_przepuszcza_wyjatek_dalej(conn):
    # wycofanie nie może zjadać błędu - warstwa wyżej musi się o nim dowiedzieć
    with pytest.raises(RuntimeError):
        with repo.transakcja(conn):
            raise RuntimeError("w górę")


def test_transakcja_zagniezdzona_nie_wybucha(conn):
    # fasada operacji opakuje zapisz_blok, które samo woła get_or_create_*
    # - zwykłe BEGIN by się zagnieździło i rzuciło
    # "cannot start a transaction within a transaction"
    with repo.transakcja(conn):
        conn.execute("INSERT INTO kurierzy(imie_nazwisko) VALUES ('A')")
        with repo.transakcja(conn):
            conn.execute("INSERT INTO kurierzy(imie_nazwisko) VALUES ('B')")
    assert conn.execute("SELECT count(*) FROM kurierzy").fetchone()[0] == 2


def test_wycofanie_wewnetrznej_transakcji_nie_wywala_zewnetrznej(conn):
    with repo.transakcja(conn):
        conn.execute("INSERT INTO kurierzy(imie_nazwisko) VALUES ('A')")
        try:
            with repo.transakcja(conn):
                conn.execute("INSERT INTO kurierzy(imie_nazwisko) VALUES ('B')")
                raise RuntimeError("tylko wewnętrzna")
        except RuntimeError:
            pass
        conn.execute("INSERT INTO kurierzy(imie_nazwisko) VALUES ('C')")

    nazwy = [r[0] for r in conn.execute(
        "SELECT imie_nazwisko FROM kurierzy ORDER BY imie_nazwisko")]
    assert nazwy == ["A", "C"]


def test_zlapany_integrityerror_nie_przerywa_transakcji(conn):
    """
    PRZYPIĘCIE zachowania, od którego zależy, czy opakowanie importu
    w transakcję jest bezpieczne: `zaimportuj` i `zapisz_blok` łapią
    IntegrityError per wiersz i lecą dalej. Gdyby złapany błąd unieważniał
    całą transakcję, opakowanie zmieniłoby semantykę importu.
    """
    with repo.transakcja(conn):
        conn.execute("INSERT INTO kurierzy(imie_nazwisko) VALUES ('A')")
        try:
            conn.execute("INSERT INTO kurierzy(imie_nazwisko) VALUES ('A')")
        except sqlite3.IntegrityError:
            pass
        conn.execute("INSERT INTO kurierzy(imie_nazwisko) VALUES ('B')")
    assert conn.execute("SELECT count(*) FROM kurierzy").fetchone()[0] == 2


# --- scal_kurierow: atomowość ---

class _PolaczenieZAwaria:
    """
    Proxy połączenia psujące wskazaną instrukcję. `sqlite3.Connection.execute`
    jest tylko do odczytu, więc nie da się go podmienić monkeypatchem.
    """

    def __init__(self, conn, psuj_prefiks, po_ilu=0):
        self._conn = conn
        self._psuj = psuj_prefiks.upper()
        self._po_ilu = po_ilu   # ile pasujących instrukcji przepuścić najpierw
        self._trafien = 0

    def execute(self, sql, *a, **kw):
        if sql.strip().upper().startswith(self._psuj):
            self._trafien += 1
            if self._trafien > self._po_ilu:
                raise sqlite3.OperationalError("symulowana awaria")
        return self._conn.execute(sql, *a, **kw)


def test_scal_kurierow_jest_atomowe(conn):
    # realny błąd: UPDATE i DELETE leciały jako dwa niezależne autocommity,
    # więc awaria pomiędzy zostawiała transakcje przepięte na kuriera,
    # którego już nie ma
    conn.execute("INSERT INTO kurierzy(imie_nazwisko) VALUES ('Wołczuk Rafal')")
    conn.execute("INSERT INTO kurierzy(imie_nazwisko) VALUES ('Wołczuk Rafał')")
    conn.execute("INSERT INTO punkty(nadawca, adres) VALUES ('Żabka', 'Odkryta 24')")
    conn.execute(
        "INSERT INTO transakcje(data, kurier_id, punkt_id, ilosc_total)"
        " VALUES ('2026-08-10', 1, 1, 5)")

    with pytest.raises(sqlite3.OperationalError):
        repo.scal_kurierow(
            _PolaczenieZAwaria(conn, "DELETE FROM KURIERZY"), id_z=1, id_do=2)

    # UPDATE musi być wycofany razem z nieudanym DELETE
    assert conn.execute("SELECT count(*) FROM kurierzy").fetchone()[0] == 2
    assert conn.execute("SELECT kurier_id FROM transakcje").fetchone()[0] == 1


def test_scal_kurierow_przy_kolizji_unique_nie_zostawia_polowicznego_stanu(conn):
    """
    Realny scenariusz, nie symulowany: obaj kurierzy mają transakcję na tę
    samą datę i ten sam punkt, więc UPDATE łamie UNIQUE(data,kurier,punkt).
    Scalenie ma prawo się nie udać - ale nie ma prawa zostawić bazy
    w połowicznym stanie.
    """
    conn.execute("INSERT INTO kurierzy(imie_nazwisko) VALUES ('Wołczuk Rafal')")
    conn.execute("INSERT INTO kurierzy(imie_nazwisko) VALUES ('Wołczuk Rafał')")
    conn.execute("INSERT INTO punkty(nadawca, adres) VALUES ('Żabka', 'Odkryta 24')")
    for kurier_id in (1, 2):
        conn.execute(
            "INSERT INTO transakcje(data, kurier_id, punkt_id, ilosc_total)"
            " VALUES ('2026-08-10', ?, 1, 5)", (kurier_id,))

    with pytest.raises(sqlite3.IntegrityError):
        repo.scal_kurierow(conn, id_z=1, id_do=2)

    assert conn.execute("SELECT count(*) FROM kurierzy").fetchone()[0] == 2
    przypisania = sorted(
        r[0] for r in conn.execute("SELECT kurier_id FROM transakcje"))
    assert przypisania == [1, 2]


def test_scal_kurierow_przenosi_transakcje_i_usuwa_zrodlo(conn):
    conn.execute("INSERT INTO kurierzy(imie_nazwisko) VALUES ('Wołczuk Rafal')")
    conn.execute("INSERT INTO kurierzy(imie_nazwisko) VALUES ('Wołczuk Rafał')")
    conn.execute("INSERT INTO punkty(nadawca, adres) VALUES ('Żabka', 'Odkryta 24')")
    conn.execute(
        "INSERT INTO transakcje(data, kurier_id, punkt_id, ilosc_total)"
        " VALUES ('2026-08-10', 1, 1, 5)")

    repo.scal_kurierow(conn, id_z=1, id_do=2)

    assert conn.execute("SELECT kurier_id FROM transakcje").fetchone()[0] == 2
    assert conn.execute(
        "SELECT count(*) FROM kurierzy WHERE id = 1").fetchone()[0] == 0


# --- wersja schematu ---

def test_utworzenie_schematu_ustawia_user_version(conn):
    # bez wersji schematu przywrócenie starej migawki po aktualizacji
    # aplikacji kończy się "no such column" na dobrych danych
    assert conn.execute("PRAGMA user_version").fetchone()[0] == repo.WERSJA_SCHEMATU
    assert repo.WERSJA_SCHEMATU >= 1


def test_wersja_schematu_odczytywalna_z_polaczenia(conn):
    assert repo.wersja_schematu(conn) == repo.WERSJA_SCHEMATU


def test_pusta_baza_ma_wersje_zero():
    pusta = repo.polacz(":memory:")
    try:
        assert repo.wersja_schematu(pusta) == 0
    finally:
        pusta.close()


def test_zgodna_wersja_przechodzi(conn):
    repo.sprawdz_zgodnosc_wersji(conn)  # nie rzuca


def test_nowsza_baza_niz_aplikacja_jest_odrzucana(conn):
    # stacja z nieaktualnym .exe otwierająca bazę zsynchronizowaną z nowszej
    # stacji - czytanie jej "jakoś" kończy się cichym gubieniem kolumn
    conn.execute(f"PRAGMA user_version = {repo.WERSJA_SCHEMATU + 1}")
    with pytest.raises(repo.NiezgodnaWersjaSchematu) as e:
        repo.sprawdz_zgodnosc_wersji(conn)
    # komunikat trafia wprost do użytkownika, więc po polsku i bez żargonu
    assert "nowsz" in str(e.value).lower()


def test_zapisz_blok_jest_atomowy(conn):
    """
    Jeden blankiet = jeden zapis. Bez transakcji awaria w połowie
    zostawiała część wierszy w bazie, a użytkownik widział "nie zapisało
    się" i wpisywał wszystko od nowa - powstawały duplikaty.
    """
    from datetime import date
    from zpo_tracker.models import Blankiet, WierszBlankietu

    blok = Blankiet(
        kurier="Kowalski Jan", data=date(2026, 8, 10),
        wiersze=[
            WierszBlankietu(nadawca="Żabka", adres=f"Ulica {i}", rejon="WA87", ilosc_total=1)
            for i in range(5)
        ],
    )
    # awaria na 3. z 5 wierszy - dwa pierwsze są już zapisane i MUSZĄ
    # zostać wycofane (psucie pierwszego wiersza nie dowiodłoby niczego)
    with pytest.raises(sqlite3.OperationalError):
        repo.zapisz_blankiet(
            _PolaczenieZAwaria(conn, "INSERT INTO TRANSAKCJE", po_ilu=2), blok)

    assert conn.execute("SELECT count(*) FROM transakcje").fetchone()[0] == 0


def test_starsza_baza_jest_do_migracji_a_nie_do_odrzucenia(conn):
    conn.execute("PRAGMA user_version = 0")
    assert repo.wymaga_migracji(conn) is True
    conn.execute(f"PRAGMA user_version = {repo.WERSJA_SCHEMATU}")
    assert repo.wymaga_migracji(conn) is False


# --- migracja z bazy sprzed `0.1-alpha.3` (czyli z alpha.2) ---

def _baza_alpha2():
    """
    Baza dokładnie taka, jaką zostawiła wersja alpha.2: bez user_version,
    bez tabeli users, bez kolumn atrybucji w transakcje. Realny stan bazy
    użytkownika, nie hipoteza.
    """
    conn = repo.polacz(":memory:")
    conn.executescript("""
        CREATE TABLE kurierzy (id INTEGER PRIMARY KEY, imie_nazwisko TEXT NOT NULL UNIQUE);
        CREATE TABLE rejony (id INTEGER PRIMARY KEY, kod TEXT NOT NULL UNIQUE);
        CREATE TABLE wykonawcy (id INTEGER PRIMARY KEY, nazwa TEXT NOT NULL UNIQUE);
        CREATE TABLE firmy_zpo (id INTEGER PRIMARY KEY, nazwa TEXT NOT NULL UNIQUE);
        CREATE TABLE punkty (
            id INTEGER PRIMARY KEY, nadawca TEXT NOT NULL, adres TEXT NOT NULL,
            pni_zpo TEXT UNIQUE, firma_zpo_id INTEGER REFERENCES firmy_zpo(id));
        CREATE TABLE transakcje (
            id INTEGER PRIMARY KEY, data TEXT NOT NULL,
            kurier_id INTEGER NOT NULL REFERENCES kurierzy(id),
            punkt_id INTEGER NOT NULL REFERENCES punkty(id),
            rejon_id INTEGER REFERENCES rejony(id),
            wykonawca_id INTEGER REFERENCES wykonawcy(id),
            ilosc_total INTEGER NOT NULL, ilosc_zpo INTEGER,
            ilosc_vinted INTEGER, ilosc_automaty INTEGER,
            ilosc_kurier48 INTEGER, ilosc_niezrealizowane INTEGER,
            komentarz TEXT, UNIQUE(data, kurier_id, punkt_id));
    """)
    conn.execute("INSERT INTO kurierzy(imie_nazwisko) VALUES ('Kowalski Jan')")
    conn.execute("INSERT INTO punkty(nadawca, adres) VALUES ('Żabka', 'Odkryta 24')")
    conn.execute(
        "INSERT INTO transakcje(data, kurier_id, punkt_id, ilosc_total)"
        " VALUES ('2026-08-10', 1, 1, 7)")
    return conn


def test_baza_alpha2_wymaga_migracji():
    conn = _baza_alpha2()
    try:
        assert repo.wersja_schematu(conn) == 0
        assert repo.wymaga_migracji(conn) is True
    finally:
        conn.close()


def test_migracja_zachowuje_dane_uzytkownika():
    # to jest cała stawka: migracja nie może zgubić ani jednego wiersza
    conn = _baza_alpha2()
    try:
        repo.migruj(conn)
        assert conn.execute(
            "SELECT ilosc_total FROM transakcje").fetchone()[0] == 7
        assert conn.execute(
            "SELECT imie_nazwisko FROM kurierzy").fetchone()[0] == "Kowalski Jan"
    finally:
        conn.close()


def test_migracja_dodaje_users_i_kolumny_atrybucji():
    conn = _baza_alpha2()
    try:
        repo.migruj(conn)
        conn.execute("SELECT id, login, alias, nr_kadrowy FROM users")  # nie rzuca
        kolumny = {r[1] for r in conn.execute("PRAGMA table_info(transakcje)")}
        assert {"uuid", "autor_id", "utworzono", "zmodyfikowano"} <= kolumny
    finally:
        conn.close()


def test_migracja_podnosi_user_version():
    conn = _baza_alpha2()
    try:
        repo.migruj(conn)
        assert repo.wersja_schematu(conn) == repo.WERSJA_SCHEMATU
        assert repo.wymaga_migracji(conn) is False
    finally:
        conn.close()


def test_migracja_jest_idempotentna():
    # uruchomienie na już zmigrowanej bazie nie może niczego zepsuć ani
    # zdublować - inaczej każdy start aplikacji byłby ryzykiem
    conn = _baza_alpha2()
    try:
        repo.migruj(conn)
        repo.migruj(conn)
        assert conn.execute("SELECT count(*) FROM transakcje").fetchone()[0] == 1
    finally:
        conn.close()


def test_migracja_swiezej_bazy_nic_nie_psuje(conn):
    repo.migruj(conn)
    assert repo.wersja_schematu(conn) == repo.WERSJA_SCHEMATU


# --- migracja `0.1-alpha.3.1`: indeksy pod dedukcję pól formularza ---

def _nazwy_indeksow(conn, tabela):
    return {r[1] for r in conn.execute(f"PRAGMA index_list({tabela})")}


def test_swieza_baza_ma_indeksy_pod_dedukcje(conn):
    assert "idx_transakcje_kurier" in _nazwy_indeksow(conn, "transakcje")
    assert "idx_punkty_adres" in _nazwy_indeksow(conn, "punkty")


def test_migracja_z_alpha2_dokłada_indeksy():
    conn = _baza_alpha2()
    try:
        repo.migruj(conn)
        assert "idx_transakcje_kurier" in _nazwy_indeksow(conn, "transakcje")
        assert "idx_punkty_adres" in _nazwy_indeksow(conn, "punkty")
    finally:
        conn.close()


def test_migracja_z_alpha3_bez_indeksow_dokłada_je():
    # baza już z kolumnami atrybucji (alpha.3), ale sprzed indeksów tego
    # wydania - migruj musi je dołożyć mimo że reszta jest już aktualna
    conn = _baza_alpha2()
    try:
        repo.migruj(conn)
        conn.execute("DROP INDEX idx_transakcje_kurier")
        conn.execute("DROP INDEX idx_punkty_adres")
        conn.execute("PRAGMA user_version = 1")  # cofnij, jakby to była realna baza v1

        repo.migruj(conn)

        assert "idx_transakcje_kurier" in _nazwy_indeksow(conn, "transakcje")
        assert "idx_punkty_adres" in _nazwy_indeksow(conn, "punkty")
        assert repo.wersja_schematu(conn) == repo.WERSJA_SCHEMATU
    finally:
        conn.close()


# --- migracja `0.1-alpha.3.2`: sesja_uuid + zrodlo ---

def test_swieza_baza_ma_kolumny_sesji(conn):
    kolumny = {r[1] for r in conn.execute("PRAGMA table_info(transakcje)")}
    assert {"sesja_uuid", "zrodlo"} <= kolumny
    assert "idx_transakcje_sesja" in _nazwy_indeksow(conn, "transakcje")
    assert repo.wersja_schematu(conn) == 3
    assert repo.WERSJA_SCHEMATU == 3


def test_migracja_z_alpha3_1_dokłada_sesje_i_zrodlo():
    # baza już z kolumnami atrybucji + indeksami dedukcji (alpha.3.1), ale
    # sprzed sesja_uuid/zrodlo tego wydania
    conn = _baza_alpha2()
    try:
        repo.migruj(conn)
        conn.execute("PRAGMA user_version = 2")  # cofnij, jakby to była realna baza v2

        repo.migruj(conn)

        kolumny = {r[1] for r in conn.execute("PRAGMA table_info(transakcje)")}
        assert {"sesja_uuid", "zrodlo"} <= kolumny
        assert "idx_transakcje_sesja" in _nazwy_indeksow(conn, "transakcje")
        assert repo.wersja_schematu(conn) == repo.WERSJA_SCHEMATU
    finally:
        conn.close()


def test_migracja_do_v3_zachowuje_dane_i_jest_idempotentna():
    conn = _baza_alpha2()
    try:
        repo.migruj(conn)
        repo.migruj(conn)  # drugi przebieg nie może niczego zepsuć/zdublować
        assert conn.execute("SELECT count(*) FROM transakcje").fetchone()[0] == 1
        assert conn.execute("SELECT ilosc_total FROM transakcje").fetchone()[0] == 7
    finally:
        conn.close()


def test_migracja_ze_stanu_posredniego_jednej_kolumny_przezywa():
    # baza w kształcie "alpha.3.1 + tylko połowa 3.2" - jedna z dwóch nowych
    # kolumn dołożona ręcznie (np. przerwana wcześniejsza aktualizacja).
    # Budowana ręcznie (nie przez `migruj`, który za jednym razem dokłada
    # OBIE kolumny) - inaczej nie da się odtworzyć tego konkretnego stanu.
    conn = _baza_alpha2()
    try:
        for nazwa, typ in repo._KOLUMNY_ATRYBUCJI.items():
            conn.execute(f"ALTER TABLE transakcje ADD COLUMN {nazwa} {typ}")
        conn.execute(repo._DDL_USERS)
        conn.execute("ALTER TABLE transakcje ADD COLUMN sesja_uuid TEXT")  # tylko ta jedna
        conn.execute("PRAGMA user_version = 2")

        repo.migruj(conn)

        kolumny = {r[1] for r in conn.execute("PRAGMA table_info(transakcje)")}
        assert {"sesja_uuid", "zrodlo"} <= kolumny
        assert repo.wersja_schematu(conn) == repo.WERSJA_SCHEMATU
    finally:
        conn.close()


def test_zapisz_blankiet_zapisuje_sesje_i_zrodlo_formularz(conn):
    from zpo_tracker.models import Blankiet, WierszBlankietu

    blankiet = Blankiet(
        kurier="Kowalski Jan", data=date(2026, 8, 10), wykonawca="Koli",
        wiersze=[WierszBlankietu(nadawca="Żabka", adres="Odkryta 24",
                                   ilosc_total=3, ilosc_zpo=3)],
    )
    repo.zapisz_blankiet(conn, blankiet, sesja_uuid="sesja-abc")
    wiersz = conn.execute("SELECT sesja_uuid, zrodlo FROM transakcje").fetchone()
    assert wiersz["sesja_uuid"] == "sesja-abc"
    assert wiersz["zrodlo"] == "formularz"


def test_zapisz_blankiet_bez_sesji_zapisuje_null(conn):
    from zpo_tracker.models import Blankiet, WierszBlankietu

    blankiet = Blankiet(
        kurier="Kowalski Jan", data=date(2026, 8, 10), wykonawca="Koli",
        wiersze=[WierszBlankietu(nadawca="Żabka", adres="Odkryta 24",
                                   ilosc_total=3, ilosc_zpo=3)],
    )
    repo.zapisz_blankiet(conn, blankiet)
    wiersz = conn.execute("SELECT sesja_uuid, zrodlo FROM transakcje").fetchone()
    assert wiersz["sesja_uuid"] is None
    assert wiersz["zrodlo"] == "formularz"
