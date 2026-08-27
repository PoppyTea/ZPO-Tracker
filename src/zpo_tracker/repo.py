"""
Warstwa dostępu do danych: połączenie z bazą, zapis bloku z formularza
wprowadzania, odczyt do przeglądania. Logika get_or_create_* zostaje
w importer.py (reużywana też przy imporcie .xlsx) - repo.py dokłada to,
czego sam import nie potrzebuje: komentarz per blok i odczyt z nazwami.
"""
import itertools
import logging
import sqlite3
import sys
import uuid
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

from zpo_tracker.importer import (
    get_or_create_adres,
    get_or_create_kurier,
    get_or_create_nadawca,
    get_or_create_punkt,
    get_or_create_rejon,
    get_or_create_wykonawca,
)
from zpo_tracker.normalizacja import (
    REJON_NIEZNANY, klucz_bialych_znakow, klucz_rozmyty, normalizuj_rejon,
)


def _resolve_schema_path(frozen=None, meipass=None):
    """
    Ścieżka do schema.sql. W spakowanym .exe (PyInstaller) plik danych
    leży w sys._MEIPASS, nie w drzewie źródeł - stąd rozróżnienie, inaczej
    wersja spakowana nie znajdzie schematu przy pierwszym starcie.
    """
    if frozen is None:
        frozen = getattr(sys, "frozen", False)
    if frozen:
        meipass = meipass or getattr(sys, "_MEIPASS", None)
        return Path(meipass) / "schema.sql"
    return Path(__file__).resolve().parent.parent.parent / "schema.sql"


SCHEMA_PATH = _resolve_schema_path()

# Musi być zgodna z `PRAGMA user_version` na końcu schema.sql - patrz tam.
WERSJA_SCHEMATU = 4

_licznik_savepointow = itertools.count()

# Słowniki proste: id + jedno pole tekstowe. Kolumna FK w transakcje jest
# potrzebna tylko dla scal_* (kurierzy) - patrz scal_kurierow.
_TABELE_PROSTE = {
    "kurierzy": "imie_nazwisko",
    "wykonawcy": "nazwa",
    "rejony": "kod",
    "nadawcy": "nazwa",
}


def polacz(sciezka=":memory:"):
    # isolation_level=None = autocommit: sqlite3 domyślnie wymaga jawnego
    # commit(), inaczej zamknięcie połączenia wycofuje niezapisane zmiany
    # (GH #4, krytyczny - "dane znikają po ponownym uruchomieniu")
    conn = sqlite3.connect(sciezka, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def utworz_schemat(conn):
    with open(SCHEMA_PATH, encoding="utf-8") as f:
        conn.executescript(f.read())


class NiezgodnaWersjaSchematu(Exception):
    """
    Baza pochodzi z NOWSZEJ wersji aplikacji. Komunikat trafia wprost do
    użytkownika, więc jest po polsku i bez żargonu.
    """


def wersja_schematu(conn):
    """
    Wersja struktury bazy (`PRAGMA user_version`). Pusta/nieznana baza
    zwraca 0. Potrzebne przy przywracaniu migawek i - docelowo - przy
    synchronizacji między stacjami: stacje aktualizowane w różnym czasie
    będą miały różne wersje schematu.
    """
    return conn.execute("PRAGMA user_version").fetchone()[0]


def wymaga_migracji(conn):
    """Baza starsza niż aplikacja - do podniesienia, nie do odrzucenia."""
    return 0 < wersja_schematu(conn) < WERSJA_SCHEMATU or wersja_schematu(conn) == 0


def _istnieje_tabela(conn, nazwa):
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (nazwa,)
    ).fetchone() is not None


def _kolumny(conn, tabela):
    return {r[1] for r in conn.execute(f"PRAGMA table_info({tabela})")}


# Kolumny dołożone do `transakcje` w `0.1-alpha.3` (atrybucja i tożsamość wiersza).
# UNIQUE na `uuid` NIE da się dodać przez ALTER TABLE, więc dla baz
# migrowanych zakłada się osobny indeks - patrz `migruj`.
_KOLUMNY_ATRYBUCJI = {
    "uuid": "TEXT",
    "autor_id": "TEXT REFERENCES users(id)",
    "utworzono": "TEXT",
    "zmodyfikowano": "TEXT",
}

# Kolumny dołożone do `transakcje` w `0.1-alpha.3.2` (sesja + pochodzenie
# wiersza) - patrz komentarz przy tych samych kolumnach w schema.sql.
_KOLUMNY_SESJI = {
    "sesja_uuid": "TEXT",
    "zrodlo": "TEXT",
}

# Tabele dołożone w `0.1-alpha.4` (schemat v4: adres strukturalny + jedna
# tabela nadawców). Powtórzone tutaj z `schema.sql` z tego samego powodu co
# `_DDL_USERS` niżej: `migruj` dokłada brakujące obiekty do ISTNIEJĄCEJ bazy,
# a `utworz_schemat` wykonałby cały skrypt i wywalił się na pierwszej tabeli,
# która już jest.
#
# Lista instrukcji, a NIE jeden skrypt dla `executescript`: ten robi
# niejawny COMMIT przed wykonaniem, co zwalnia otwarty SAVEPOINT i wywala
# `transakcja(conn)` na "no such savepoint" (złapane testem migracji).
_DDL_V4_SLOWNIKI = ("""
CREATE TABLE IF NOT EXISTS miejscowosci (
    id      INTEGER PRIMARY KEY,
    nazwa   TEXT NOT NULL UNIQUE,
    gmina   TEXT
)""", """
CREATE TABLE IF NOT EXISTS ulice (
    id              INTEGER PRIMARY KEY,
    nazwa           TEXT NOT NULL,
    typ             TEXT,
    miejscowosc_id  INTEGER NOT NULL REFERENCES miejscowosci(id),
    UNIQUE(nazwa, miejscowosc_id)
)""", """
CREATE TABLE IF NOT EXISTS adresy (
    id                  INTEGER PRIMARY KEY,
    surowy              TEXT NOT NULL UNIQUE,
    ulica_id            INTEGER REFERENCES ulice(id),
    nr_budynku          TEXT,
    nr_lokalu           TEXT,
    pna                 TEXT,
    stan                TEXT NOT NULL DEFAULT 'surowy',
    zrodlo_miejscowosci TEXT,
    rejon_baska         TEXT,
    rejon_potwierdzony  TEXT
)""", """
CREATE INDEX IF NOT EXISTS idx_adresy_ulica ON adresy(ulica_id)""", """
CREATE TABLE IF NOT EXISTS nadawcy (
    id          INTEGER PRIMARY KEY,
    nazwa       TEXT NOT NULL UNIQUE,
    liczy_zpo   INTEGER NOT NULL DEFAULT 0
)""")

_DDL_PUNKTY_V4 = """
CREATE TABLE punkty (
    id          INTEGER PRIMARY KEY,
    nadawca_id  INTEGER NOT NULL REFERENCES nadawcy(id),
    adres_id    INTEGER NOT NULL REFERENCES adresy(id),
    pni_zpo     TEXT UNIQUE,
    UNIQUE(nadawca_id, adres_id)
)
"""

_DDL_USERS = """
CREATE TABLE users (
    id          TEXT PRIMARY KEY,
    login       TEXT NOT NULL UNIQUE,
    alias       TEXT,
    nr_kadrowy  TEXT UNIQUE,
    utworzono   TEXT,
    CHECK (nr_kadrowy IS NULL OR (
        length(nr_kadrowy) = 5
        AND nr_kadrowy GLOB '[A-Za-z0-9][A-Za-z0-9][A-Za-z0-9][A-Za-z0-9][A-Za-z0-9]'
    ))
)
"""


def migruj(conn):
    """
    Podnosi istniejącą bazę do `WERSJA_SCHEMATU`. Migracja jest
    **addytywna i idempotentna**: sprawdza obecność każdego obiektu
    i dokłada tylko brakujące, zamiast wykonywać kroki po numerze wersji.
    Dzięki temu przeżywa też bazy w stanie pośrednim (np. z przerwanej
    wcześniej aktualizacji), które numerowana migracja by pominęła.

    Struktura, nie dane - z JEDNYM wyjątkiem: przejście na schemat v4
    przenosi `punkty.nadawca`/`punkty.adres` z tekstu na klucze obce
    (`_przebuduj_punkty_do_v4`). Tej zmiany nie da się wyrazić dokładaniem
    kolumn, a wystemplowanie bazy w kształcie v3 numerem v4 byłoby gorsze
    niż brak migracji: program czytałby wtedy kolumny, których tam nie ma,
    już po nadpisaniu dobrych danych migawką.

    Przebudowa idzie PIERWSZA i w osobnej transakcji, bo kolejne kroki
    zakładają kształt v4 (indeks po `punkty.adres_id`). Awaria między
    krokami zostawia `user_version` niepodniesioną, więc następny start
    powtarza całość - dokładnie po to ta funkcja jest idempotentna.
    """
    _przebuduj_punkty_do_v4(conn)

    with transakcja(conn):
        if not _istnieje_tabela(conn, "users"):
            conn.execute(_DDL_USERS)

        obecne = _kolumny(conn, "transakcje")
        for nazwa, typ in _KOLUMNY_ATRYBUCJI.items():
            if nazwa not in obecne:
                conn.execute(f"ALTER TABLE transakcje ADD COLUMN {nazwa} {typ}")
        # UNIQUE(uuid) jest w schema.sql częścią CREATE TABLE, ale ALTER
        # TABLE nie umie dodać ograniczenia - stąd równoważny indeks
        conn.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_transakcje_uuid"
            " ON transakcje(uuid)")

        # 0.1-alpha.3.1: indeksy pod zapytania dedukcyjne formularza -
        # patrz komentarz przy tych samych CREATE INDEX w schema.sql
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_transakcje_kurier ON transakcje(kurier_id)")
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_punkty_adres ON punkty(adres_id)")
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_punkty_nadawca ON punkty(nadawca_id)")

        # 0.1-alpha.3.2: sesja_uuid + zrodlo (dołożone niezależnie od
        # _KOLUMNY_ATRYBUCJI, żeby baza w stanie pośrednim - np. tylko
        # jedna z dwóch kolumn ręcznie dołożona - przeżyła, patrz test)
        obecne = _kolumny(conn, "transakcje")
        for nazwa, typ in _KOLUMNY_SESJI.items():
            if nazwa not in obecne:
                conn.execute(f"ALTER TABLE transakcje ADD COLUMN {nazwa} {typ}")
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_transakcje_sesja ON transakcje(sesja_uuid)")

        conn.execute(f"PRAGMA user_version = {WERSJA_SCHEMATU}")


def _przebuduj_punkty_do_v4(conn):
    """
    v3 -> v4: `punkty.nadawca`/`punkty.adres` (tekst) na klucze obce do
    `nadawcy` i `adresy`. No-op dla bazy, która już ma kształt v4.

    `punkty.id` jest ZACHOWYWANE, bo `transakcje.punkt_id` na nie wskazuje -
    przenumerowanie punktów oznaczałoby przepisanie całego dziennika
    transakcji, czyli tę jedną tabelę, której nie wolno ruszyć.

    Dwa wiersze v3 mogły opisywać ten sam punkt: v3 NIE miało
    `UNIQUE(nadawca, adres)`, więc wiersz z PNI potrafił powstać obok
    identycznego bez PNI. Takie pary zlepiają się teraz w jeden punkt,
    a ich transakcje przepina `_scal_punkty` - przy kolizji
    `UNIQUE(data, kurier, punkt)` rzuca `KolizjaTransakcji` i wycofuje
    całość, zamiast po cichu wyrzucić wiersz.

    PRAGMA foreign_keys jest ignorowana WEWNĄTRZ transakcji, więc
    przełączamy ją przed SAVEPOINT-em. `legacy_alter_table` jest tu
    konieczne razem z nią: bez niego `ALTER TABLE ... RENAME` przepisuje
    klauzulę REFERENCES w `transakcje` na nową nazwę tabeli i dziennik
    zostaje przypięty do tabeli, którą za chwilę kasujemy (sprawdzone
    empirycznie - `PRAGMA foreign_key_check` pokazuje wtedy każdy wiersz).
    """
    if not _istnieje_tabela(conn, "punkty") or "nadawca_id" in _kolumny(conn, "punkty"):
        return
    if conn.in_transaction:
        raise RuntimeError(
            "_przebuduj_punkty_do_v4 wymaga połączenia poza transakcją - "
            "PRAGMA foreign_keys nie działa w jej środku, a bez niej "
            "podmiana tabeli `punkty` rozpina dziennik transakcji.")

    fk_bylo_wlaczone = conn.execute("PRAGMA foreign_keys").fetchone()[0]
    conn.execute("PRAGMA foreign_keys = OFF")
    conn.execute("PRAGMA legacy_alter_table = ON")
    try:
        with transakcja(conn):
            for instrukcja in _DDL_V4_SLOWNIKI:
                conn.execute(instrukcja)
            _przenies_firmy_zpo_do_nadawcow(conn)
            stare = conn.execute(
                "SELECT id, nadawca, adres, pni_zpo FROM punkty ORDER BY id").fetchall()
            conn.execute("ALTER TABLE punkty RENAME TO punkty_v3")
            conn.execute(_DDL_PUNKTY_V4)
            for stary in stare:
                _przenies_punkt_do_v4(conn, stary)
            conn.execute("DROP TABLE punkty_v3")
            if _istnieje_tabela(conn, "firmy_zpo"):
                conn.execute("DROP TABLE firmy_zpo")
    finally:
        conn.execute("PRAGMA legacy_alter_table = OFF")
        conn.execute(f"PRAGMA foreign_keys = {'ON' if fk_bylo_wlaczone else 'OFF'}")


def _przenies_firmy_zpo_do_nadawcow(conn):
    """
    `firmy_zpo` trzymała nazwy sieci - czyli dokładnie tych nadawców, dla
    których wypełnia się "w tym ZPO". Wpis mógł tam powstać ręcznie w
    Słownikach, zanim powstał pierwszy punkt, więc przepisujemy CAŁĄ tabelę,
    nie tylko nazwy używane przez punkty.
    """
    if not _istnieje_tabela(conn, "firmy_zpo"):
        return
    for firma in conn.execute("SELECT nazwa FROM firmy_zpo").fetchall():
        get_or_create_nadawca(conn, firma["nazwa"], liczy_zpo=True)


def _przenies_punkt_do_v4(conn, stary):
    nadawca_id = get_or_create_nadawca(
        conn, stary["nadawca"], liczy_zpo=bool(stary["pni_zpo"]))
    adres_id = get_or_create_adres(conn, stary["adres"])
    istniejacy = conn.execute(
        "SELECT id, pni_zpo FROM punkty WHERE nadawca_id = ? AND adres_id = ?",
        (nadawca_id, adres_id),
    ).fetchone()
    if istniejacy is None:
        conn.execute(
            "INSERT INTO punkty (id, nadawca_id, adres_id, pni_zpo) VALUES (?, ?, ?, ?)",
            (stary["id"], nadawca_id, adres_id, stary["pni_zpo"]),
        )
        return

    if stary["pni_zpo"] and istniejacy["pni_zpo"] is None:
        conn.execute(
            "UPDATE punkty SET pni_zpo = ? WHERE id = ?",
            (stary["pni_zpo"], istniejacy["id"]))
    elif stary["pni_zpo"] and istniejacy["pni_zpo"] != stary["pni_zpo"]:
        # dwa PNI na tę samą parę nadawca+adres - v4 dopuszcza tam jeden
        # punkt, więc jedno z nich musi odpaść. NIE po cichu: to jedyna
        # informacja, która na tej ścieżce faktycznie ginie.
        logging.getLogger("zpo_tracker").warning(
            "migracja v4: punkty %s i %s to ta sama para nadawca+adres, ale "
            "mają różne PNI ZPO (%r vs %r) - zachowano pierwsze, drugie "
            "przepadło; wymaga człowieka",
            istniejacy["id"], stary["id"], istniejacy["pni_zpo"], stary["pni_zpo"])
    _scal_punkty(conn, stary["id"], istniejacy["id"],
                 powod="przy przejściu na schemat v4")


def napraw_dane(conn):
    """
    Naprawa rozjazdów danych sprzed reguły "???" (rejony) - BEZWARUNKOWA
    i idempotentna jak `migruj`, ale CELOWO POZA `migruj`:

    - `migruj` biegnie w konstruktorze `Aplikacja.__init__`, a `main()`
      łapie wyłącznie `NiezgodnaWersjaSchematu` - każdy inny wyjątek w
      `migruj` uniemożliwiałby start aplikacji PRZY KAŻDYM kolejnym
      uruchomieniu, u użytkownika bez uprawnień administratora i bez
      konsoli. Naprawa danych ma więcej sposobów, żeby pójść nie tak, niż
      dodanie kolumny - nie może dzielić z migracją struktury tego samego,
      nieprzepuszczającego błędów miejsca w kodzie.
    - `migruj` deklaruje strukturę, nie dane (patrz wyżej) - to nie jest
      miejsce na naprawę danych.
    - Naprawa w `migruj` odpaliłaby się raz (bramkowana numerem wersji) -
      po scaleniu (`scalanie.py`) z bazą, która sama tej naprawy jeszcze
      nie przeszła, rozjazd wróciłby i nic by go już nie naprawiło.

    Wołający (app.py) jest odpowiedzialny za migawkę PRZED wywołaniem
    (przez `operacje.wykonaj` - to największa jednorazowa mutacja danych
    w tym wydaniu) i za degradację "nie naprawiono, pracuj dalej" przy
    wyjątku - nie za przerwanie startu aplikacji.

    ZOSTAŁ TU JUŻ TYLKO JEDEN KROK, i to jest cel schematu v4, nie skutek
    uboczny. Drugim była naprawa rozjazdu `firmy_zpo.nazwa` z
    `punkty.nadawca`: nazwa nadawcy żyła w dwóch miejscach naraz, więc
    dawała się rozjechać, a naprawa musiała zgadywać, która kopia jest
    prawdziwa (i przy okazji robiła z samodzielnego sklepu jednoelementową
    sieć). W v4 nazwa istnieje w jednym miejscu - `nadawcy.nazwa` - i ten
    rozjazd nie ma jak powstać. Usunięto problem, nie obudowano go.
    """
    with transakcja(conn):
        _napraw_rejony(conn)


def _napraw_rejony(conn):
    kanoniczny_id = get_or_create_rejon(conn, None)
    for row in conn.execute("SELECT id, kod FROM rejony").fetchall():
        if row["id"] == kanoniczny_id:
            continue
        if normalizuj_rejon(row["kod"]) == REJON_NIEZNANY:
            conn.execute(
                "UPDATE transakcje SET rejon_id = ? WHERE rejon_id = ?",
                (kanoniczny_id, row["id"]),
            )
            conn.execute("DELETE FROM rejony WHERE id = ?", (row["id"],))
    conn.execute(
        "UPDATE transakcje SET rejon_id = ? WHERE rejon_id IS NULL", (kanoniczny_id,))


def sprawdz_zgodnosc_wersji(conn):
    """
    Odrzuca bazę pochodzącą z NOWSZEJ wersji aplikacji. Czytanie takiej
    bazy "jakoś" kończy się cichym gubieniem kolumn, których ta wersja nie
    zna - a przy synchronizacji między stacjami aktualizowanymi w różnym
    czasie to sytuacja spodziewana, nie egzotyczna.
    """
    wersja = wersja_schematu(conn)
    if wersja > WERSJA_SCHEMATU:
        raise NiezgodnaWersjaSchematu(
            f"Ta baza pochodzi z nowszej wersji programu (wersja danych "
            f"{wersja}, ten program obsługuje {WERSJA_SCHEMATU}). "
            f"Zaktualizuj program, zanim ją otworzysz - inaczej część "
            f"danych mogłaby zostać po cichu pominięta."
        )


@contextmanager
def transakcja(conn):
    """
    Jawna transakcja na SAVEPOINT - **re-entrant**, więc można zagnieżdżać
    (fasada operacji opakowuje `zapisz_blok`, które samo woła
    `get_or_create_*`; zwykłe BEGIN rzuciłoby "cannot start a transaction
    within a transaction").

    NIE używać wbudowanego `with conn:` - przy `isolation_level=None`
    (autocommit, ustawione w `polacz` dla GH #4) on **nic nie wycofuje**.
    Kod z `with conn:` wygląda poprawnie i nie robi nic; przypięte testem
    `test_wbudowane_with_conn_nic_nie_wycofuje`.

    Uwaga: złapany `IntegrityError` NIE unieważnia transakcji (domyślne
    ON CONFLICT ABORT wycofuje samą instrukcję), więc per-wierszowe
    `except` w `zapisz_blok`/`zaimportuj` działają wewnątrz bez zmian.
    """
    nazwa = f"zpo_sp_{next(_licznik_savepointow)}"
    conn.execute(f"SAVEPOINT {nazwa}")
    try:
        yield conn
    except BaseException:
        # ROLLBACK TO cofa zmiany, ale ZOSTAWIA savepoint na stosie -
        # bez RELEASE zostałby otwarty i zablokował zewnętrzną transakcję
        conn.execute(f"ROLLBACK TO {nazwa}")
        conn.execute(f"RELEASE {nazwa}")
        raise
    conn.execute(f"RELEASE {nazwa}")


def zapisz_blankiet(conn, blankiet, autor_id=None, teraz=None, sesja_uuid=None):
    """
    Zapisuje Blankiet (jeden kurier, jeden dzień) jako jedną transakcję na
    WierszBlankietu. Rejon i wykonawca liczone PER WIERSZ (0.1-alpha.3.1):
    rejon bo zszedł do wiersza (dedukowany z adresu), wykonawca bo mimo
    dedukcji na poziomie nagłówka wciąż jest atrybutem wiersza w bazie -
    patrz `models.Blankiet`. Zwraca listę dictów:
    {"id", "pominieto", "ostrzezenia", "powod"} - jeden na wiersz, w
    kolejności wejściowej.

    Całość jest ATOMOWA: jeden blankiet = jeden zapis. Bez tego awaria
    w połowie zostawiała część wierszy w bazie, użytkownik widział "nie
    zapisało się" i wpisywał wszystko od nowa - powstawały duplikaty.
    Pomijanie pojedynczych duplikatów (IntegrityError niżej) działa
    wewnątrz transakcji bez zmian - patrz `transakcja`.

    `autor_id` jest opcjonalny: atrybucja nie może być warunkiem
    zapisania danych. `sesja_uuid` (0.1-alpha.3.2) grupuje wiersze
    wpisane w tym samym uruchomieniu aplikacji - podgląd formularza
    filtruje po niej domyślnie, patrz gui/zakladka_wprowadzanie.py.
    """
    with transakcja(conn):
        return _zapisz_blankiet_bez_transakcji(
            conn, blankiet, autor_id=autor_id, teraz=teraz, sesja_uuid=sesja_uuid)


def _zapisz_blankiet_bez_transakcji(conn, blankiet, autor_id=None, teraz=None,
                                     sesja_uuid=None):
    kurier_id = get_or_create_kurier(conn, blankiet.kurier)
    wykonawca_id = get_or_create_wykonawca(conn, blankiet.wykonawca)
    teraz = teraz or datetime.now().isoformat(timespec="seconds")

    wyniki = []
    for wiersz in blankiet.wiersze:
        punkt_id, ostrzezenia = get_or_create_punkt(
            conn, wiersz.nadawca, wiersz.adres, wiersz.pni_zpo
        )
        rejon_id = get_or_create_rejon(conn, wiersz.rejon)
        try:
            cur = conn.execute(
                """INSERT INTO transakcje
                   (data, kurier_id, punkt_id, rejon_id, wykonawca_id,
                    ilosc_total, ilosc_zpo,
                    uuid, autor_id, utworzono, zmodyfikowano,
                    sesja_uuid, zrodlo)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    blankiet.data.isoformat(), kurier_id, punkt_id, rejon_id,
                    wykonawca_id, wiersz.ilosc_total, wiersz.ilosc_zpo,
                    str(uuid.uuid4()), autor_id, teraz, teraz,
                    sesja_uuid, "formularz",
                ),
            )
            wyniki.append({
                "id": cur.lastrowid, "pominieto": False,
                "ostrzezenia": ostrzezenia, "powod": None,
            })
        except sqlite3.IntegrityError:
            wyniki.append({
                "id": None, "pominieto": True, "ostrzezenia": ostrzezenia,
                "powod": "duplikat (ta sama data+kurier+punkt już istnieje)",
            })
    return wyniki


def pobierz_slownik(conn, tabela):
    """Lista {"id", "nazwa"} dla jednego z _TABELE_PROSTE, alfabetycznie."""
    kolumna = _TABELE_PROSTE[tabela]
    wiersze = conn.execute(
        f"SELECT id, {kolumna} AS nazwa FROM {tabela} ORDER BY {kolumna}"
    ).fetchall()
    return [dict(w) for w in wiersze]


def _znormalizuj_dla_tabeli(tabela, nazwa):
    """`rejony` ma dodatkową regułę (pusty/śmieciowy kod -> REJON_NIEZNANY,
    patrz normalizacja.py) - pozostałe słowniki tylko białe znaki."""
    nazwa = klucz_bialych_znakow(nazwa)
    if tabela == "rejony":
        nazwa = normalizuj_rejon(nazwa)
    return nazwa


def _czy_kanoniczny_rejon(conn, tabela, wpis_id):
    if tabela != "rejony":
        return False
    row = conn.execute("SELECT kod FROM rejony WHERE id = ?", (wpis_id,)).fetchone()
    return row is not None and row[0] == REJON_NIEZNANY


def dodaj_do_slownika(conn, tabela, nazwa):
    """
    `rejony`: get-or-create (przez `get_or_create_rejon`, ta sama ścieżka co
    formularz/import), nie ślepy INSERT - baza ma zaseedowany kanoniczny
    wiersz REJON_NIEZNANY, więc "+ dodaj" ze śmieciową wartością MUSI
    trafić w istniejący wiersz, a nie próbować stworzyć drugi taki sam
    (co i tak skończyłoby się `IntegrityError` na `UNIQUE`).
    """
    if tabela == "rejony":
        return get_or_create_rejon(conn, nazwa)
    kolumna = _TABELE_PROSTE[tabela]
    cur = conn.execute(
        f"INSERT INTO {tabela} ({kolumna}) VALUES (?)", (klucz_bialych_znakow(nazwa),)
    )
    return cur.lastrowid


def zmien_nazwe_w_slowniku(conn, tabela, wpis_id, nowa_nazwa):
    """
    Zwykły UPDATE jednego wiersza dla KAŻDEGO słownika, łącznie z `nadawcy`.
    Do v3 `firmy_zpo` wymagała tu dodatkowej propagacji, bo nazwa sieci
    istniała drugi raz jako tekst w `punkty.nadawca` - w v4 drugiej kopii
    nie ma, więc nie ma czego propagować ani czemu się rozjechać.

    `rejony`: kanoniczny wpis REJON_NIEZNANY nie może zostać przemianowany -
    to punkt zbiorczy dla wszystkich pustych/śmieciowych rejonów, zmiana
    jego nazwy rozjechałaby tę zbieżność.
    """
    if _czy_kanoniczny_rejon(conn, tabela, wpis_id):
        raise ValueError(
            f"„{REJON_NIEZNANY}” to kanoniczny rejon nieznany - nie można zmienić jego nazwy.")
    kolumna = _TABELE_PROSTE[tabela]
    nowa_nazwa = _znormalizuj_dla_tabeli(tabela, nowa_nazwa)
    with transakcja(conn):
        conn.execute(
            f"UPDATE {tabela} SET {kolumna} = ? WHERE id = ?",
            (nowa_nazwa, wpis_id),
        )


def usun_z_slownika(conn, tabela, wpis_id):
    """Usuwa wpis. Jeśli jest gdzieś użyty jako FK, sqlite3.IntegrityError
    (PRAGMA foreign_keys=ON) - GUI wyświetla błąd, nie decyduje o nim.
    Kanoniczny rejon nieznany (REJON_NIEZNANY) nie może zostać usunięty."""
    if tabela not in _TABELE_PROSTE:
        raise ValueError(f"nieznany słownik: {tabela}")
    if _czy_kanoniczny_rejon(conn, tabela, wpis_id):
        raise ValueError(
            f"„{REJON_NIEZNANY}” to kanoniczny rejon nieznany - nie można go usunąć.")
    conn.execute(f"DELETE FROM {tabela} WHERE id = ?", (wpis_id,))


def scal_kurierow(conn, id_z, id_do):
    """Przenosi wszystkie transakcje z kuriera id_z na id_do i usuwa id_z -
    droga naprawy dla par typu "Wołczuk Rafal"/"Wołczuk Rafał"
    (docs/domain-model.md), zgłoszonych jako ostrzeżenie, nie scalonych
    automatycznie."""
    # atomowo: bez tego awaria między UPDATE a DELETE zostawiała transakcje
    # przepięte na kuriera, który zaraz miał zniknąć - albo odwrotnie
    with transakcja(conn):
        conn.execute("UPDATE transakcje SET kurier_id = ? WHERE kurier_id = ?", (id_do, id_z))
        conn.execute("DELETE FROM kurierzy WHERE id = ?", (id_z,))


def pobierz_unikalne_nadawcow(conn):
    """
    Kandydaci do podpowiedzi w polu 'nadawca' (widget_autocomplete).

    Prosto ze słownika, bez DISTINCT po punktach: `nadawcy.nazwa` jest
    UNIQUE, więc powtórek nie ma z definicji. Wchodzą tu też nadawcy dodani
    ręcznie w Słownikach, którzy nie mają jeszcze żadnego punktu - a to jest
    dokładnie moment, w którym podpowiedź jest najbardziej potrzebna.
    """
    return [
        r[0] for r in conn.execute("SELECT nazwa FROM nadawcy ORDER BY nazwa").fetchall()
    ]


def pobierz_unikalne_adresy(conn):
    """Kandydaci do podpowiedzi w polu 'adres' (widget_autocomplete).
    `adresy.surowy` jest UNIQUE, więc bez DISTINCT - patrz wyżej."""
    return [
        r[0] for r in conn.execute("SELECT surowy FROM adresy ORDER BY surowy").fetchall()
    ]


def pobierz_nadawcow_bez_pni(conn):
    """
    Nadawcy, dla których NIE wypełnia się "w tym ZPO" (ZUS, PKO, Kruk...),
    razem z liczbą ich punktów - do podzakładki „Nadawcy (bez PNI)".

    ZBIÓR JEST WĘŻSZY NIŻ W v3 i to jest zmiana, nie przeoczenie. W v3
    predykat (`firma_zpo_id IS NULL`) działał NA POZIOMIE PUNKTU, więc sieć,
    dla której znaliśmy PNI tylko jednego z dwóch sklepów, pokazywała się tu
    z tym drugim - mimo że była siecią ZPO. W v4 `liczy_zpo` opisuje
    NADAWCĘ, a nie jego pojedynczy punkt, więc taki nadawca znika z listy
    w całości i to jest poprawne: "w tym ZPO" wypełnia się dla niego wszędzie.

    INNER JOIN, a nie LEFT: nadawca dodany ręcznie w Słownikach, bez ani
    jednego punktu, tu nie wchodzi. Ta podzakładka służy poprawianiu nazw,
    które przyszły z danych, i pokazuje przy nich liczbę dotkniętych punktów -
    wiersz z "0 pkt." nie niósłby żadnej informacji. Pełną listę nadawców,
    razem z takimi wpisami, daje `pobierz_slownik(conn, "nadawcy")`.
    """
    wiersze = conn.execute(
        """SELECT n.nazwa AS nazwa, COUNT(p.id) AS liczba_punktow
           FROM nadawcy n JOIN punkty p ON p.nadawca_id = n.id
           WHERE n.liczy_zpo = 0
           GROUP BY n.id ORDER BY n.nazwa"""
    ).fetchall()
    return [dict(w) for w in wiersze]


def zmien_nadawce_bez_pni(conn, stara, nowa):
    """
    Zmienia nazwę nadawcy bez PNI - naprawa literówek (ZUS/PKO/Kruk...).
    Atomowe.

    Po v4 to NIE jest już jedyna droga do zmiany nazwy nadawcy: `nadawcy`
    jest zwykłym słownikiem, więc `zmien_nazwe_w_slowniku` też to potrafi.
    Ta funkcja istnieje dla jednej rzeczy, której tamta nie robi - rename na
    nazwę JUŻ ZAJĘTĄ przez innego nadawcę traktuje jako SCALENIE, nie jako
    błąd. Literówka i jej poprawna forma to dwa wiersze opisujące tę samą
    firmę, a `nadawcy.nazwa` jest UNIQUE, więc gołe UPDATE rzuciłoby
    `IntegrityError` dokładnie w najczęstszym przypadku użycia.

    Nadawca DOCELOWY celowo nie jest filtrowany po `liczy_zpo`: jeśli
    człowiek mówi, że "Zabka" to literówka od "Żabka", to jest to ta sama
    firma i punkty mają trafić pod nią razem z jej flagą. Flaga może się tak
    tylko zapalić, nigdy zgasnąć - ta sama asymetria co w
    `importer.get_or_create_nadawca` i z tego samego powodu.

    Po scaleniu dwa punkty tego samego nadawcy mogą wskazywać ten sam adres,
    czego zabrania `UNIQUE(nadawca_id, adres_id)` - dlatego kolizję wykrywamy
    PRZED przepięciem, nie łapiemy po fakcie. Wygrywa punkt o najniższym id
    (najstarszy), transakcje przegrywającego lądują na nim. Kolizja
    `UNIQUE(data, kurier_id, punkt_id)` przy przepinaniu (oba punkty mają
    transakcję tego samego dnia/kuriera) rzuca `KolizjaTransakcji` i wycofuje
    CAŁOŚĆ - konflikt nigdy nie jest rozstrzygany po cichu (reguła projektu,
    patrz repo.KolizjaTransakcji).
    """
    with transakcja(conn):
        zrodlowy = conn.execute(
            "SELECT id FROM nadawcy WHERE nazwa = ? AND liczy_zpo = 0", (stara,)
        ).fetchone()
        if zrodlowy is None:
            return
        docelowy = conn.execute(
            "SELECT id FROM nadawcy WHERE nazwa = ? AND id != ?", (nowa, zrodlowy["id"])
        ).fetchone()
        if docelowy is None:
            conn.execute(
                "UPDATE nadawcy SET nazwa = ? WHERE id = ?", (nowa, zrodlowy["id"]))
            return
        _scal_nadawcow(conn, zrodlowy["id"], docelowy["id"])


def _scal_nadawcow(conn, id_zrodlowy, id_docelowy):
    """Przepina punkty i usuwa nadawcę źródłowego - patrz
    `zmien_nadawce_bez_pni`, jedyny wołający."""
    for p in conn.execute(
        "SELECT id, adres_id FROM punkty WHERE nadawca_id = ? ORDER BY id",
        (id_zrodlowy,),
    ).fetchall():
        zajety = conn.execute(
            "SELECT id FROM punkty WHERE nadawca_id = ? AND adres_id = ?",
            (id_docelowy, p["adres_id"]),
        ).fetchone()
        if zajety is None:
            conn.execute(
                "UPDATE punkty SET nadawca_id = ? WHERE id = ?", (id_docelowy, p["id"]))
        else:
            _scal_punkty(conn, p["id"], zajety["id"])
    conn.execute("DELETE FROM nadawcy WHERE id = ?", (id_zrodlowy,))


def _scal_punkty(conn, punkt_zrodlowy, punkt_docelowy, powod="po zmianie nazwy nadawcy"):
    kolidujaca = conn.execute(
        """SELECT z.id FROM transakcje z
           JOIN transakcje d ON d.data = z.data AND d.kurier_id = z.kurier_id
           WHERE z.punkt_id = ? AND d.punkt_id = ?""",
        (punkt_zrodlowy, punkt_docelowy),
    ).fetchone()
    if kolidujaca:
        raise KolizjaTransakcji(
            f"Nie można scalić punktów {powod} - " +
            _opisz_transakcje(conn, kolidujaca["id"]) +
            " koliduje z transakcją drugiego punktu tego samego dnia/kuriera.")
    conn.execute(
        "UPDATE transakcje SET punkt_id = ? WHERE punkt_id = ?",
        (punkt_docelowy, punkt_zrodlowy))
    conn.execute("DELETE FROM punkty WHERE id = ?", (punkt_zrodlowy,))


def pobierz_punkty(conn):
    """
    Lista punktów do zakładki Słowniki. Kolumny „nadawca" i „firma ZPO"
    zlały się w jedną razem z tabelami: w v4 nazwa nadawcy jest jedna,
    a to, czy liczy się dla niego ZPO, mówi osobna flaga `liczy_zpo`.
    """
    wiersze = conn.execute(
        """SELECT p.id, n.nazwa AS nadawca, a.surowy AS adres, p.pni_zpo,
                  n.liczy_zpo
           FROM punkty p
           JOIN nadawcy n ON n.id = p.nadawca_id
           JOIN adresy a ON a.id = p.adres_id
           ORDER BY n.nazwa, a.surowy"""
    ).fetchall()
    return [dict(w) for w in wiersze]


def pobierz_transakcje(conn, limit=200, *, kurier=None, data_od=None, data_do=None,
                        utworzono_od=None, utworzono_do=None, sesja_uuid=None, tekst=None,
                        zrodlo=None):
    """
    Lista transakcji do przeglądania, najnowsze pierwsze, z nazwami zamiast
    ID. Dokłada `id`/`uuid`/`utworzono`/`sesja_uuid`/`zrodlo` (0.1-alpha.3.2)
    - potrzebne przez widok poprawek (edycja/usuwanie po `id`, filtr sesji)
    mimo że część z nich nie jest wyświetlana w tabeli.

    Filtry (wszystkie opcjonalne, łączone koniunkcją - "kurier ORAZ zakres
    dat ORAZ ..."): `kurier` (dokładne dopasowanie nazwy), `data_od`/
    `data_do` (zakres daty TRANSAKCJI, `date` albo string ISO), `utworzono_od`/
    `utworzono_do` (zakres znacznika wprowadzenia), `sesja_uuid` (dokładne
    dopasowanie), `tekst` (dopasowanie częściowe nadawcy LUB adresu),
    `zrodlo` (dokładne dopasowanie - podgląd formularza filtruje po
    `"formularz"`, żeby import w tej samej sesji nie wskakiwał obok).
    """
    warunki, parametry = [], []
    if zrodlo is not None:
        warunki.append("t.zrodlo = ?")
        parametry.append(zrodlo)
    if kurier is not None:
        warunki.append("k.imie_nazwisko = ?")
        parametry.append(kurier)
    if data_od is not None:
        warunki.append("t.data >= ?")
        parametry.append(data_od.isoformat() if hasattr(data_od, "isoformat") else data_od)
    if data_do is not None:
        warunki.append("t.data <= ?")
        parametry.append(data_do.isoformat() if hasattr(data_do, "isoformat") else data_do)
    if utworzono_od is not None:
        warunki.append("t.utworzono >= ?")
        parametry.append(utworzono_od)
    if utworzono_do is not None:
        warunki.append("t.utworzono <= ?")
        parametry.append(utworzono_do)
    if sesja_uuid is not None:
        warunki.append("t.sesja_uuid = ?")
        parametry.append(sesja_uuid)
    if tekst is not None:
        # tekst to wejście użytkownika, nie wzorzec LIKE - "%"/"_" muszą
        # szukać dosłownego znaku, więc escapujemy je PRZED doklejeniem
        # otaczających "%" i mówimy SQLite, że "\" jest znakiem ucieczki
        warunki.append("(n.nazwa LIKE ? ESCAPE '\\' OR a.surowy LIKE ? ESCAPE '\\')")
        tekst_escapowany = tekst.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        wzorzec = f"%{tekst_escapowany}%"
        parametry.extend([wzorzec, wzorzec])

    gdzie = f"WHERE {' AND '.join(warunki)}" if warunki else ""
    wiersze = conn.execute(
        f"""SELECT t.id, t.data, k.imie_nazwisko AS kurier, n.nazwa AS nadawca,
                   a.surowy AS adres, r.kod AS rejon, w.nazwa AS wykonawca,
                   t.ilosc_total, t.ilosc_zpo, t.komentarz,
                   t.uuid, t.utworzono, t.sesja_uuid, t.zrodlo
            FROM transakcje t
            JOIN kurierzy k ON k.id = t.kurier_id
            JOIN punkty p ON p.id = t.punkt_id
            JOIN nadawcy n ON n.id = p.nadawca_id
            JOIN adresy a ON a.id = p.adres_id
            LEFT JOIN rejony r ON r.id = t.rejon_id
            LEFT JOIN wykonawcy w ON w.id = t.wykonawca_id
            {gdzie}
            ORDER BY t.data DESC, t.id DESC
            LIMIT ?""",
        (*parametry, limit),
    ).fetchall()
    return [dict(w) for w in wiersze]


# --- zapytania dedukcyjne dla formularza wprowadzania (dedukcja.py) ---

# Punkt w postaci, jakiej oczekuje `dedukcja.py`: nadawca i adres jako TEKST,
# nie jako klucze obce. Warstwa dedukcji pracuje na tym, co człowiek wpisuje
# w formularzu, więc rozbicie adresu na miejscowość/ulicę jest tam bez
# znaczenia - stąd jeden wspólny SELECT zamiast powtarzania joinów.
_SQL_PUNKT_Z_NAZWAMI = """
    SELECT p.id, n.nazwa AS nadawca, a.surowy AS adres, p.pni_zpo
    FROM punkty p
    JOIN nadawcy n ON n.id = p.nadawca_id
    JOIN adresy a ON a.id = p.adres_id
"""

def znajdz_punkty_po_adresie(conn, adres):
    """
    Kandydaci punktów dla adresu wpisanego w formularzu - z preferencją
    trafienia DOKŁADNEGO (po `adresy.surowy UNIQUE`) nad rozmytym.
    Punkty w bazie są znormalizowane (`models.py`: `klucz_bialych_znakow`),
    a to, co wpisuje człowiek, nie musi być - bez fuzzy fallbacku
    "odkryta  24" dałoby zero trafień, a przy zapisie zduplikowany punkt.

    Porównanie idzie po `adresy.surowy`, nie po strukturze: dopasowanie ma
    działać tak samo dla adresu, którego parser nie rozłożył (`ulica_id`
    puste), a tych jest w danych realnie dużo.
    """
    dokladne = conn.execute(_SQL_PUNKT_Z_NAZWAMI + " WHERE a.surowy = ?", (adres,)).fetchall()
    if dokladne:
        return [dict(r) for r in dokladne]

    klucz = klucz_rozmyty(adres)
    wszystkie = conn.execute(_SQL_PUNKT_Z_NAZWAMI).fetchall()
    return [dict(r) for r in wszystkie if klucz_rozmyty(r["adres"]) == klucz]


def znajdz_punkt_po_pni(conn, pni):
    """
    Punkt o podanym PNI albo None. Odwraca dzisiejszy kierunek dedukcji,
    w której PNI jest WYŁĄCZNIE polem wyjściowym (wyprowadzanym
    z rozstrzygniętego punktu, patrz `dedukcja.py`) - tutaj jest wejściem.

    Jednoznaczność jest gwarantowana schematem: `punkty.pni_zpo UNIQUE`,
    więc nie ma tu żadnego rozstrzygania ani zgadywania.

    **Porównanie jest TEKSTOWE, nigdy liczbowe.** PNI to klucz, nie
    wielkość: "007" i "7" to dwa różne punkty. Zrównanie ich to dokładnie
    ten błąd koercji, który do `0.1-alpha.3.2` rozdwajał ten sam fizyczny
    punkt przy round-tripie eksport-import (patrz `eksport.py`).
    """
    if pni is None:
        return None
    pni = str(pni).strip()
    if not pni:
        return None
    wiersz = conn.execute(
        _SQL_PUNKT_Z_NAZWAMI + " WHERE p.pni_zpo = ?", (pni,)).fetchone()
    return dict(wiersz) if wiersz else None


def czy_nadawca_liczy_zpo(conn, nadawca):
    """
    Rządzi aktywnością pola "w tym ZPO" w trybie auto.

    Do v3 pytaliśmy, czy nadawca ma JAKIŚ punkt z PNI - i to było błędne
    dokładnie w przypadku, który zdarza się najczęściej: punkt JEST ZPO,
    ale PNI dopiero trzeba zdobyć z paragonu, więc pole było wygaszone
    i nie dało się wpisać liczby, którą kurier miał na kartce. W v4
    odpowiada na to jawna flaga `nadawcy.liczy_zpo` (patrz schema.sql),
    niezależna od tego, czy PNI już znamy.
    """
    wiersz = conn.execute(
        "SELECT liczy_zpo FROM nadawcy WHERE nazwa = ?", (nadawca,)).fetchone()
    return bool(wiersz[0]) if wiersz else False


def historia_rejonow_punktu(conn, punkt_id):
    """Rejony, którymi historycznie jeżdżono do tego punktu, najczęstszy
    pierwszy - źródło dedukcji rejonu (dedukcja.py)."""
    wiersze = conn.execute(
        """SELECT r.kod AS kod, COUNT(*) AS liczba, MAX(t.data) AS ostatnia_data
           FROM transakcje t JOIN rejony r ON r.id = t.rejon_id
           WHERE t.punkt_id = ?
           GROUP BY r.kod
           ORDER BY liczba DESC""",
        (punkt_id,),
    ).fetchall()
    return [dict(w) for w in wiersze]


# --- korekty (0.1-alpha.3.2): edycja i usuwanie transakcji ---
#
# Pierwsze w projekcie destrukcyjne prymitywy na `transakcje` poza importem/
# formularzem - dotąd istniał wyłącznie INSERT (plus jeden UPDATE ilości,
# WYŁĄCZNIE w scalanie.py, przy jawnym rozstrzygnięciu konfliktu). Świadomie
# BEZ nadawcy/adresu/PNI: przepięcie wiersza na inny punkt to inna klasa
# ryzyka (cicha zmiana historii punktu) niż poprawka daty/ilości/rejonu -
# korekta punktu w tym wydaniu to usuń + wpisz ponownie w formularzu,
# z pełną dedukcją. Patrz docs/roadmap.md.

KOLUMNY_EDYTOWALNE_TRANSAKCJI = {
    "data", "kurier", "wykonawca", "rejon", "ilosc_total", "ilosc_zpo",
}


class KolizjaTransakcji(Exception):
    """
    Docelowa trójka (data, kurier, punkt) już istnieje na INNYM wierszu.
    Reguła projektu: konflikt wartości nigdy nie jest rozstrzygany
    automatycznie (docs/roadmap.md) - operacja się nie udaje, baza zostaje
    całkowicie nietknięta, użytkownik dostaje czytelny opis kolidującego
    wiersza (patrz `_opisz_transakcje`) zamiast gołego "UNIQUE failed".
    """


def _opisz_transakcje(conn, transakcja_id):
    w = conn.execute(
        """SELECT t.data, k.imie_nazwisko AS kurier, n.nazwa AS nadawca,
                  a.surowy AS adres, t.ilosc_total, t.ilosc_zpo
           FROM transakcje t
           JOIN kurierzy k ON k.id = t.kurier_id
           JOIN punkty p ON p.id = t.punkt_id
           JOIN nadawcy n ON n.id = p.nadawca_id
           JOIN adresy a ON a.id = p.adres_id
           WHERE t.id = ?""",
        (transakcja_id,),
    ).fetchone()
    if w is None:
        return f"transakcja #{transakcja_id}"
    opis = f"{w['data']} / {w['kurier']} / {w['nadawca']} ({w['adres']}) - ilość {w['ilosc_total']}"
    if w["ilosc_zpo"] is not None:
        opis += f", w tym ZPO {w['ilosc_zpo']}"
    return opis


def _zaktualizuj_transakcje_bez_transakcji(conn, transakcja_id, zmiany, teraz):
    nieznane = set(zmiany) - KOLUMNY_EDYTOWALNE_TRANSAKCJI
    if nieznane:
        raise ValueError(
            f"nieedytowalne/nieznane pole(a): {', '.join(sorted(nieznane))} - "
            f"dozwolone: {', '.join(sorted(KOLUMNY_EDYTOWALNE_TRANSAKCJI))}")

    obecna = conn.execute(
        "SELECT data, kurier_id, punkt_id FROM transakcje WHERE id = ?",
        (transakcja_id,),
    ).fetchone()
    if obecna is None:
        raise ValueError(f"transakcja #{transakcja_id} nie istnieje")

    if "data" in zmiany:
        wartosc_daty = zmiany["data"]
        nowa_data = (wartosc_daty.isoformat() if hasattr(wartosc_daty, "isoformat")
                     else wartosc_daty)
    else:
        nowa_data = obecna["data"]
    nowy_kurier_id = (get_or_create_kurier(conn, zmiany["kurier"])
                       if "kurier" in zmiany else obecna["kurier_id"])

    # kolizja sprawdzana WYŁĄCZNIE gdy zmienia się faktycznie część klucza
    # naturalnego (data/kurier) - zmiana samej ilości/rejonu/wykonawcy nigdy
    # nie może kolidować, bo nie są częścią UNIQUE(data, kurier_id, punkt_id)
    if (nowa_data, nowy_kurier_id) != (obecna["data"], obecna["kurier_id"]):
        kolidujaca = conn.execute(
            "SELECT id FROM transakcje"
            " WHERE data = ? AND kurier_id = ? AND punkt_id = ? AND id != ?",
            (nowa_data, nowy_kurier_id, obecna["punkt_id"], transakcja_id),
        ).fetchone()
        if kolidujaca:
            raise KolizjaTransakcji(
                "Taka transakcja już istnieje: " + _opisz_transakcje(conn, kolidujaca["id"]))

    kolumny_sql, wartosci = [], []
    if "data" in zmiany:
        kolumny_sql.append("data = ?")
        wartosci.append(nowa_data)
    if "kurier" in zmiany:
        kolumny_sql.append("kurier_id = ?")
        wartosci.append(nowy_kurier_id)
    if "wykonawca" in zmiany:
        kolumny_sql.append("wykonawca_id = ?")
        wartosci.append(get_or_create_wykonawca(conn, zmiany["wykonawca"]))
    if "rejon" in zmiany:
        kolumny_sql.append("rejon_id = ?")
        wartosci.append(get_or_create_rejon(conn, zmiany["rejon"]))
    if "ilosc_total" in zmiany:
        kolumny_sql.append("ilosc_total = ?")
        wartosci.append(zmiany["ilosc_total"])
    if "ilosc_zpo" in zmiany:
        kolumny_sql.append("ilosc_zpo = ?")
        wartosci.append(zmiany["ilosc_zpo"])

    if not kolumny_sql:
        return

    kolumny_sql.append("zmodyfikowano = ?")
    wartosci.append(teraz)
    wartosci.append(transakcja_id)
    conn.execute(
        f"UPDATE transakcje SET {', '.join(kolumny_sql)} WHERE id = ?", wartosci)


def zaktualizuj_transakcje(conn, transakcja_id, zmiany, teraz=None):
    """
    Poprawia jeden zapisany wiersz. `zmiany`: dict, klucze z
    `KOLUMNY_EDYTOWALNE_TRANSAKCJI` (data/kurier/wykonawca/rejon/
    ilosc_total/ilosc_zpo - patrz komentarz nad sekcją). Rzuca
    `KolizjaTransakcji`, jeśli docelowa trójka (data, kurier, punkt) już
    należy do INNEGO wiersza - baza zostaje wtedy całkowicie nietknięta.
    Atomowe (`transakcja`).
    """
    teraz = teraz or datetime.now().isoformat(timespec="seconds")
    with transakcja(conn):
        _zaktualizuj_transakcje_bez_transakcji(conn, transakcja_id, zmiany, teraz)


def usun_transakcje(conn, ids):
    """Usuwa podane transakcje atomowo. Zwraca liczbę faktycznie usuniętych
    wierszy (0 dla pustej listy, bez zapytania do bazy)."""
    ids = list(ids)
    if not ids:
        return 0
    with transakcja(conn):
        cur = conn.execute(
            f"DELETE FROM transakcje WHERE id IN ({','.join('?' * len(ids))})", ids)
        return cur.rowcount


def ustaw_pole_transakcji(conn, ids, pole, wartosc, teraz=None):
    """
    Ustawia JEDNO pole na wielu transakcjach naraz, w jednym SAVEPOINT -
    pierwsza kolizja (`KolizjaTransakcji`) wycofuje CAŁOŚĆ, nie tylko
    kolidujący wiersz (ten sam wzorzec co `scal_kurierow`): "zmień 5
    wierszy, ale nie ten jeden" byłoby ciche i mylące dla użytkownika,
    który zaznaczył je jako jedną operację.
    """
    if pole not in KOLUMNY_EDYTOWALNE_TRANSAKCJI:
        raise ValueError(
            f"nieedytowalne/nieznane pole: {pole} - "
            f"dozwolone: {', '.join(sorted(KOLUMNY_EDYTOWALNE_TRANSAKCJI))}")
    teraz = teraz or datetime.now().isoformat(timespec="seconds")
    with transakcja(conn):
        for transakcja_id in ids:
            _zaktualizuj_transakcje_bez_transakcji(conn, transakcja_id, {pole: wartosc}, teraz)


def historia_wykonawcow_kuriera(conn, kurier):
    """
    Wykonawcy, dla których historycznie jeździł ten kurier - świeższy
    pierwszy, NIE najliczniejszy: 69/70 kurierów w realnych danych ma
    jednego wykonawcę, więc niejednoznaczność to najczęściej realna zmiana
    firmy, nie szum - wartość dominująca liczebnie byłaby wtedy tą
    NIEAKTUALNĄ. `kurier` to nazwa, nie id - nowy kurier bez historii
    zwraca po prostu pustą listę.
    """
    wiersze = conn.execute(
        """SELECT w.nazwa AS nazwa, COUNT(*) AS liczba, MAX(t.data) AS ostatnia_data
           FROM transakcje t
           JOIN kurierzy k ON k.id = t.kurier_id
           JOIN wykonawcy w ON w.id = t.wykonawca_id
           WHERE k.imie_nazwisko = ?
           GROUP BY w.nazwa
           ORDER BY ostatnia_data DESC""",
        (kurier,),
    ).fetchall()
    return [dict(w) for w in wiersze]
