"""
Zrzuty .sql.gz: warstwa zimna, osobna od migawek binarnych w kopie.py.
Migawki (kopie.py) chronią pojedynczą operację i są przycinane (retencja) -
zrzuty to długotrwałe, przenośne archiwum, jeden na dzień, NIE przycinany
(patrz `zrob_zrzut` niżej). Ten sam format jest planowanym formatem wymiany
dla synchronizacji między stacjami (X+3, patrz roadmap.md) - stąd zwykły
tekstowy SQL, nie binarny plik `.db`: czytelny do inspekcji po rozpakowaniu,
przenośny niezależnie od wersji SQLite między maszynami.
"""
import gzip
import sqlite3
from datetime import date
from pathlib import Path

NAZWA_KATALOGU = "zrzuty"


def katalog_zrzutow(katalog_danych):
    katalog = Path(katalog_danych) / NAZWA_KATALOGU
    katalog.mkdir(parents=True, exist_ok=True)
    return katalog


def _nazwa_pliku(dzien):
    return f"{dzien.isoformat()}.sql.gz"


def zrob_zrzut(conn, katalog_danych, dzis=None):
    """
    Zrzuca całą bazę jako gzipowany tekstowy SQL (`conn.iterdump`) do
    `zrzuty/{data}.sql.gz`. Jeden zrzut na dzień - kolejne wywołanie tego
    samego dnia NADPISUJE, nie dubluje (spójne z tym, że to zrzut stanu
    "na dziś", nie log operacji jak dziennik.py).

    `PRAGMA user_version` jest dopisywana jawnie - `conn.iterdump()` jej
    nie obejmuje (to nie DDL/DML w tabeli), a bez niej odzyskana baza
    wyglądałaby jak nowa/niemigrowana.
    """
    dzis = dzis or date.today()
    docelowy = katalog_zrzutow(katalog_danych) / _nazwa_pliku(dzis)
    wersja = conn.execute("PRAGMA user_version").fetchone()[0]

    with gzip.open(docelowy, "wt", encoding="utf-8") as f:
        for linia in conn.iterdump():
            f.write(linia + "\n")
        f.write(f"PRAGMA user_version = {wersja};\n")

    return docelowy


def istnieje_zrzut_na_dzien(katalog_danych, dzien):
    return (katalog_zrzutow(katalog_danych) / _nazwa_pliku(dzien)).exists()


def wczytaj_zrzut(sciezka_zrzutu, conn_docelowe):
    """Odtwarza zrzut w `conn_docelowe` - musi być pustym/świeżym połączeniem."""
    with gzip.open(sciezka_zrzutu, "rt", encoding="utf-8") as f:
        conn_docelowe.executescript(f.read())
