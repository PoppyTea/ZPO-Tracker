"""
Warstwa dostępu do danych: połączenie z bazą, zapis bloku z formularza
wprowadzania, odczyt do przeglądania. Logika get_or_create_* zostaje
w importer.py (reużywana też przy imporcie .xlsx) - repo.py dokłada to,
czego sam import nie potrzebuje: komentarz per blok i odczyt z nazwami.
"""
import itertools
import sqlite3
import sys
import uuid
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

from zpo_tracker.importer import (
    get_or_create_kurier,
    get_or_create_punkt,
    get_or_create_rejon,
    get_or_create_wykonawca,
)
from zpo_tracker.normalizacja import REJON_NIEZNANY, klucz_bialych_znakow, normalizuj_rejon


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
WERSJA_SCHEMATU = 1

_licznik_savepointow = itertools.count()

# Słowniki proste: id + jedno pole tekstowe. Kolumna FK w transakcje jest
# potrzebna tylko dla scal_* (kurierzy) - patrz scal_kurierow.
_TABELE_PROSTE = {
    "kurierzy": "imie_nazwisko",
    "wykonawcy": "nazwa",
    "rejony": "kod",
    "firmy_zpo": "nazwa",
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

    Nie rusza danych - wyłącznie struktura.
    """
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

        conn.execute(f"PRAGMA user_version = {WERSJA_SCHEMATU}")


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


def zapisz_blok(conn, blok, autor_id=None, teraz=None, operacja_id=None):
    """
    Zapisuje BlankietBlok jako jedną transakcję na WierszBlankietu, z tym
    samym komentarzem dla całego bloku. Zwraca listę dictów:
    {"id", "pominieto", "ostrzezenia", "powod"} - jeden na wiersz, w
    kolejności wejściowej.

    Całość jest ATOMOWA: jeden blankiet = jeden zapis. Bez tego awaria
    w połowie zostawiała część wierszy w bazie, użytkownik widział "nie
    zapisało się" i wpisywał wszystko od nowa - powstawały duplikaty.
    Pomijanie pojedynczych duplikatów (IntegrityError niżej) działa
    wewnątrz transakcji bez zmian - patrz `transakcja`.

    `autor_id` jest opcjonalny: atrybucja nie może być warunkiem
    zapisania danych.
    """
    with transakcja(conn):
        return _zapisz_blok_bez_transakcji(
            conn, blok, autor_id=autor_id, teraz=teraz)


def _zapisz_blok_bez_transakcji(conn, blok, autor_id=None, teraz=None):
    kurier_id = get_or_create_kurier(conn, blok.kurier)
    rejon_id = get_or_create_rejon(conn, blok.rejon)
    wykonawca_id = get_or_create_wykonawca(conn, blok.wykonawca)
    teraz = teraz or datetime.now().isoformat(timespec="seconds")

    wyniki = []
    for wiersz in blok.wiersze:
        punkt_id, ostrzezenia = get_or_create_punkt(
            conn, wiersz.nadawca, wiersz.adres, wiersz.pni_zpo
        )
        try:
            cur = conn.execute(
                """INSERT INTO transakcje
                   (data, kurier_id, punkt_id, rejon_id, wykonawca_id,
                    ilosc_total, ilosc_zpo, komentarz,
                    uuid, autor_id, utworzono, zmodyfikowano)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    blok.data.isoformat(), kurier_id, punkt_id, rejon_id,
                    wykonawca_id, wiersz.ilosc_total, wiersz.ilosc_zpo,
                    blok.komentarz,
                    str(uuid.uuid4()), autor_id, teraz, teraz,
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


def zapisz_bloki(conn, bloki, autor_id=None):
    """
    Zapisuje kilka BlankietBlok (jeden formularz może mieć kilka bloków
    rejonu) jako jedną operację dla dziennika/migawek (operacje.wykonaj) -
    "ZAPISZ" w formularzu to dla użytkownika jedna czynność, niezależnie od
    liczby bloków, więc cofnięcie też powinno cofać ją w całości.
    """
    wyniki = []
    for blok in bloki:
        wyniki.extend(zapisz_blok(conn, blok, autor_id=autor_id))
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
    `firmy_zpo` wymaga dodatkowej propagacji: w odróżnieniu od pozostałych
    słowników (referencowanych wyłącznie przez FK) nazwa sieci istnieje
    DRUGI raz jako tekst w `punkty.nadawca`. Bez tego rename w Słownikach
    rozjeżdżał obie kopie na stałe i nic tego nie naprawiało.

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
        if tabela == "firmy_zpo":
            conn.execute(
                "UPDATE punkty SET nadawca = ? WHERE firma_zpo_id = ?",
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
    """Kandydaci do podpowiedzi w polu 'nadawca' (widget_autocomplete)."""
    return [
        r[0] for r in conn.execute(
            "SELECT DISTINCT nadawca FROM punkty ORDER BY nadawca"
        ).fetchall()
    ]


def pobierz_unikalne_adresy(conn):
    """Kandydaci do podpowiedzi w polu 'adres' (widget_autocomplete)."""
    return [
        r[0] for r in conn.execute(
            "SELECT DISTINCT adres FROM punkty ORDER BY adres"
        ).fetchall()
    ]


def pobierz_punkty(conn):
    """Lista punktów z nazwą firmy ZPO (jeśli ma PNI), do zakładki słowników."""
    wiersze = conn.execute(
        """SELECT p.id, p.nadawca, p.adres, p.pni_zpo, f.nazwa AS firma_zpo
           FROM punkty p
           LEFT JOIN firmy_zpo f ON f.id = p.firma_zpo_id
           ORDER BY p.nadawca, p.adres"""
    ).fetchall()
    return [dict(w) for w in wiersze]


def pobierz_transakcje(conn, limit=200):
    """Lista transakcji do przeglądania, najnowsze pierwsze, z nazwami zamiast ID."""
    wiersze = conn.execute(
        """SELECT t.id, t.data, k.imie_nazwisko AS kurier, p.nadawca,
                  p.adres, r.kod AS rejon, w.nazwa AS wykonawca,
                  t.ilosc_total, t.ilosc_zpo, t.komentarz
           FROM transakcje t
           JOIN kurierzy k ON k.id = t.kurier_id
           JOIN punkty p ON p.id = t.punkt_id
           LEFT JOIN rejony r ON r.id = t.rejon_id
           LEFT JOIN wykonawcy w ON w.id = t.wykonawca_id
           ORDER BY t.data DESC, t.id DESC
           LIMIT ?""",
        (limit,),
    ).fetchall()
    return [dict(w) for w in wiersze]
