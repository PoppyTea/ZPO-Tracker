"""
Migawki bazy: pełna kopia pliku .db przed każdą operacją, żeby cofnięcie
(operacje.py) było zawsze możliwe. Mechanika schemat-agnostyczna - testy
celowo nie używają schema.sql, tylko własnej minimalnej tabeli. TDD.
"""
import sqlite3
from datetime import datetime, timedelta

import pytest

from zpo_tracker import kopie


def _polacz_z_tabela(sciezka):
    conn = sqlite3.connect(str(sciezka))
    conn.execute("CREATE TABLE t (x TEXT)")
    conn.commit()
    return conn


# --- katalog_migawek ---

def test_katalog_migawek_tworzy_podkatalog(tmp_path):
    katalog = kopie.katalog_migawek(tmp_path)
    assert katalog == tmp_path / "migawki"
    assert katalog.is_dir()


# --- zrob_migawke (z otwartego połączenia) ---

def test_zrob_migawke_kopiuje_aktualny_stan_danych(tmp_path):
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE t (x TEXT)")
    conn.execute("INSERT INTO t VALUES ('a')")
    conn.commit()

    plik = kopie.zrob_migawke(conn, tmp_path, seq=1)

    kopia = sqlite3.connect(str(plik))
    assert kopia.execute("SELECT x FROM t").fetchall() == [("a",)]
    kopia.close()
    conn.close()


def test_zrob_migawke_nie_lapie_zmian_po_wywolaniu(tmp_path):
    # migawka to zrzut W MOMENCIE wywołania - zmiany wprowadzone później
    # (przez tę samą funkcję, która ją zrobiła jako krok "przed") nie mogą
    # się do niej przedostać, inaczej cofnięcie przywracałoby stan już
    # zepsuty przez operację, przed którą migawka miała chronić
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE t (x TEXT)")
    conn.commit()

    plik = kopie.zrob_migawke(conn, tmp_path, seq=1)
    conn.execute("INSERT INTO t VALUES ('nowe')")
    conn.commit()

    kopia = sqlite3.connect(str(plik))
    assert kopia.execute("SELECT x FROM t").fetchall() == []
    kopia.close()
    conn.close()


def test_zrob_migawke_nazwa_pliku_zawiera_numer_seq(tmp_path):
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE t (x TEXT)")

    plik = kopie.zrob_migawke(conn, tmp_path, seq=42)

    assert "000042" in plik.name
    conn.close()


def test_zrob_migawke_umieszcza_plik_w_katalogu_migawek(tmp_path):
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE t (x TEXT)")

    plik = kopie.zrob_migawke(conn, tmp_path, seq=1)

    assert plik.parent == kopie.katalog_migawek(tmp_path)
    conn.close()


# --- zrob_migawke_pliku (bez otwartego połączenia) ---

def test_zrob_migawke_pliku_kopiuje_plik_bazy(tmp_path):
    sciezka_bazy = tmp_path / "baza.db"
    conn = _polacz_z_tabela(sciezka_bazy)
    conn.execute("INSERT INTO t VALUES ('b')")
    conn.commit()
    conn.close()

    plik = kopie.zrob_migawke_pliku(sciezka_bazy, tmp_path, seq=1)

    kopia = sqlite3.connect(str(plik))
    assert kopia.execute("SELECT x FROM t").fetchall() == [("b",)]
    kopia.close()


# --- lista_migawek ---

def test_lista_migawek_pustego_katalogu(tmp_path):
    assert kopie.lista_migawek(tmp_path) == []


def test_lista_migawek_posortowana_rosnaco_po_seq(tmp_path):
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE t (x TEXT)")
    for seq in (3, 1, 2):
        kopie.zrob_migawke(conn, tmp_path, seq=seq)
    conn.close()

    nazwy = [p.name for p in kopie.lista_migawek(tmp_path)]
    assert nazwy == sorted(nazwy)


# --- przywroc_migawke ---

def test_przywroc_migawke_podmienia_plik_bazy(tmp_path):
    sciezka_bazy = tmp_path / "baza.db"
    conn = _polacz_z_tabela(sciezka_bazy)
    conn.execute("INSERT INTO t VALUES ('stare')")
    conn.commit()
    plik_migawki = kopie.zrob_migawke(conn, tmp_path, seq=1)
    conn.execute("INSERT INTO t VALUES ('nowe')")
    conn.commit()
    conn.close()

    kopie.przywroc_migawke(sciezka_bazy, plik_migawki)

    po_przywroceniu = sqlite3.connect(str(sciezka_bazy))
    assert po_przywroceniu.execute("SELECT x FROM t").fetchall() == [("stare",)]
    po_przywroceniu.close()


def test_przywroc_migawke_brakujacy_plik_rzuca_wyjatek(tmp_path):
    with pytest.raises(FileNotFoundError):
        kopie.przywroc_migawke(tmp_path / "baza.db", tmp_path / "brak.db")


# --- przytnij_migawki: rotacja dzień/3dni/tydzień/2tyg/miesiąc/3mc/pół
# roku/rok, dalej 1/rok bez końca ---

def _wpis(seq, dni_temu, teraz, katalog):
    czas = teraz - timedelta(days=dni_temu)
    plik = kopie.katalog_migawek(katalog) / f"{seq:06d}.db"
    plik.write_bytes(b"x")
    return {"seq": seq, "czas": czas.isoformat(timespec="seconds"),
            "plik_migawki": str(plik)}


def test_przytnij_migawki_nie_rusza_ostatniej_doby(tmp_path):
    teraz = datetime(2026, 8, 11, 12, 0, 0)
    wpisy = [_wpis(1, 0.1, teraz, tmp_path), _wpis(2, 0.9, teraz, tmp_path)]
    kopie.przytnij_migawki(tmp_path, wpisy, teraz=teraz)
    assert len(kopie.lista_migawek(tmp_path)) == 2


def test_przytnij_migawki_1_do_3_dni_zostaje_jedna_na_kubelek(tmp_path):
    teraz = datetime(2026, 8, 11, 12, 0, 0)
    # trzy migawki w tej samej dobie wieku (1-2 dni) - jeden kubełek
    wpisy = [_wpis(1, 1.1, teraz, tmp_path), _wpis(2, 1.5, teraz, tmp_path),
             _wpis(3, 1.9, teraz, tmp_path)]
    kopie.przytnij_migawki(tmp_path, wpisy, teraz=teraz)
    pozostale = kopie.lista_migawek(tmp_path)
    assert len(pozostale) == 1
    assert pozostale[0].name == "000001.db"  # najnowsza (najmniejszy wiek: 1.1 dnia) w kubełku zostaje


def test_przytnij_migawki_rozne_kubelki_zostaja_osobno(tmp_path):
    teraz = datetime(2026, 8, 11, 12, 0, 0)
    # wiek 1.5 i 2.5 - ta sama rozdzielczość (1 dzień), różne kubełki
    wpisy = [_wpis(1, 1.5, teraz, tmp_path), _wpis(2, 2.5, teraz, tmp_path)]
    kopie.przytnij_migawki(tmp_path, wpisy, teraz=teraz)
    assert len(kopie.lista_migawek(tmp_path)) == 2


def test_przytnij_migawki_powyzej_roku_zostaje_jedna_na_rok(tmp_path):
    teraz = datetime(2026, 8, 11, 12, 0, 0)
    wpisy = [_wpis(1, 400, teraz, tmp_path), _wpis(2, 430, teraz, tmp_path)]
    kopie.przytnij_migawki(tmp_path, wpisy, teraz=teraz)
    assert len(kopie.lista_migawek(tmp_path)) == 1


def test_przytnij_migawki_powyzej_roku_dwa_lata_to_osobne_kubelki(tmp_path):
    # 1/rok NA ZAWSZE - nie twardy limit, więc odległe lata nie są tym samym kubełkiem
    teraz = datetime(2026, 8, 11, 12, 0, 0)
    wpisy = [_wpis(1, 400, teraz, tmp_path), _wpis(2, 800, teraz, tmp_path)]
    kopie.przytnij_migawki(tmp_path, wpisy, teraz=teraz)
    assert len(kopie.lista_migawek(tmp_path)) == 2


def test_przytnij_migawki_pomija_wpisy_bez_czasu_lub_migawki(tmp_path):
    wpisy = [{"seq": 1, "czas": None, "plik_migawki": None}]
    kopie.przytnij_migawki(tmp_path, wpisy, teraz=datetime.now())  # nie wybucha
    assert kopie.lista_migawek(tmp_path) == []


def test_przytnij_migawki_domyslnie_uzywa_aktualnego_czasu(tmp_path):
    wpis = _wpis(1, 0, datetime.now(), tmp_path)
    kopie.przytnij_migawki(tmp_path, [wpis])
    assert len(kopie.lista_migawek(tmp_path)) == 1
