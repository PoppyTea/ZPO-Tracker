"""
Warstwa dostępu do danych: połączenie z bazą, zapis bloku z formularza
wprowadzania, odczyt do przeglądania. Logika get_or_create_* zostaje
w importer.py (reużywana też przy imporcie .xlsx) - repo.py dokłada to,
czego sam import nie potrzebuje: komentarz per blok i odczyt z nazwami.
"""
import sqlite3
from pathlib import Path

from zpo_tracker.importer import (
    get_or_create_kurier,
    get_or_create_punkt,
    get_or_create_rejon,
    get_or_create_wykonawca,
)
from zpo_tracker.normalizacja import klucz_bialych_znakow

SCHEMA_PATH = Path(__file__).resolve().parent.parent.parent / "schema.sql"

# Słowniki proste: id + jedno pole tekstowe. Kolumna FK w transakcje jest
# potrzebna tylko dla scal_* (kurierzy) - patrz scal_kurierow.
_TABELE_PROSTE = {
    "kurierzy": "imie_nazwisko",
    "wykonawcy": "nazwa",
    "rejony": "kod",
    "firmy_zpo": "nazwa",
}


def polacz(sciezka=":memory:"):
    conn = sqlite3.connect(sciezka)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def utworz_schemat(conn):
    with open(SCHEMA_PATH, encoding="utf-8") as f:
        conn.executescript(f.read())


def zapisz_blok(conn, blok):
    """
    Zapisuje BlankietBlok jako jedną transakcję na WierszBlankietu, z tym
    samym komentarzem dla całego bloku. Zwraca listę dictów:
    {"id", "pominieto", "ostrzezenia", "powod"} - jeden na wiersz, w
    kolejności wejściowej.
    """
    kurier_id = get_or_create_kurier(conn, blok.kurier)
    rejon_id = get_or_create_rejon(conn, blok.rejon)
    wykonawca_id = get_or_create_wykonawca(conn, blok.wykonawca)

    wyniki = []
    for wiersz in blok.wiersze:
        punkt_id, ostrzezenia = get_or_create_punkt(
            conn, wiersz.nadawca, wiersz.adres, wiersz.pni_zpo
        )
        try:
            cur = conn.execute(
                """INSERT INTO transakcje
                   (data, kurier_id, punkt_id, rejon_id, wykonawca_id,
                    ilosc_total, ilosc_zpo, komentarz)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    blok.data.isoformat(), kurier_id, punkt_id, rejon_id,
                    wykonawca_id, wiersz.ilosc_total, wiersz.ilosc_zpo,
                    blok.komentarz,
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


def dodaj_do_slownika(conn, tabela, nazwa):
    kolumna = _TABELE_PROSTE[tabela]
    cur = conn.execute(
        f"INSERT INTO {tabela} ({kolumna}) VALUES (?)", (klucz_bialych_znakow(nazwa),)
    )
    return cur.lastrowid


def zmien_nazwe_w_slowniku(conn, tabela, wpis_id, nowa_nazwa):
    kolumna = _TABELE_PROSTE[tabela]
    conn.execute(
        f"UPDATE {tabela} SET {kolumna} = ? WHERE id = ?",
        (klucz_bialych_znakow(nowa_nazwa), wpis_id),
    )


def usun_z_slownika(conn, tabela, wpis_id):
    """Usuwa wpis. Jeśli jest gdzieś użyty jako FK, sqlite3.IntegrityError
    (PRAGMA foreign_keys=ON) - GUI wyświetla błąd, nie decyduje o nim."""
    if tabela not in _TABELE_PROSTE:
        raise ValueError(f"nieznany słownik: {tabela}")
    conn.execute(f"DELETE FROM {tabela} WHERE id = ?", (wpis_id,))


def scal_kurierow(conn, id_z, id_do):
    """Przenosi wszystkie transakcje z kuriera id_z na id_do i usuwa id_z -
    droga naprawy dla par typu "Wołczuk Rafal"/"Wołczuk Rafał"
    (docs/domain-model.md), zgłoszonych jako ostrzeżenie, nie scalonych
    automatycznie."""
    conn.execute("UPDATE transakcje SET kurier_id = ? WHERE kurier_id = ?", (id_do, id_z))
    conn.execute("DELETE FROM kurierzy WHERE id = ?", (id_z,))


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
