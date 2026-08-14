"""
PodzakladkaNadawcowBezPni (0.1-alpha.3.2): naprawa literówek nadawców bez
PNI (ZUS/PKO/Kruk...), dotąd nienaprawialnych w aplikacji - patrz
repo.pobierz_nadawcow_bez_pni/zmien_nadawce_bez_pni. Wymaga środowiska
graficznego - pomijany automatycznie, jeśli niedostępne (patrz
test_gui_smoke.py, ten sam mechanizm).
"""
import subprocess
import sys
import tkinter as tk

import pytest

from zpo_tracker import repo
from zpo_tracker.gui.zakladka_slowniki import PodzakladkaNadawcowBezPni, ZakladkaSlowniki
from zpo_tracker.importer import get_or_create_punkt


def _ma_display():
    try:
        wynik = subprocess.run(
            [sys.executable, "-c",
             "import tkinter as tk; r = tk.Tk(); tk.Entry(r).pack(); r.update(); r.destroy()"],
            capture_output=True, timeout=10,
        )
        return wynik.returncode == 0
    except Exception:
        return False


pytestmark = pytest.mark.skipif(
    not _ma_display(), reason="wymaga środowiska graficznego (DISPLAY)"
)


@pytest.fixture
def root():
    r = tk.Tk()
    yield r
    r.destroy()


@pytest.fixture
def conn():
    c = repo.polacz(":memory:")
    repo.utworz_schemat(c)
    yield c
    c.close()


def test_lista_pokazuje_tylko_nadawcow_bez_pni(root, conn, tmp_path):
    get_or_create_punkt(conn, "Żabka", "Odkryta 24", "228648")  # ma PNI - pominięty
    get_or_create_punkt(conn, "ZUS", "Senatorska 6/8", None)

    podzakladka = PodzakladkaNadawcowBezPni(root, conn, tmp_path)

    assert [w["nazwa"] for w in podzakladka._wpisy] == ["ZUS"]


def test_zastosuj_zmiane_przemianowuje_i_odswieza(root, conn, tmp_path):
    get_or_create_punkt(conn, "ZUS", "Senatorska 6/8", None)
    podzakladka = PodzakladkaNadawcowBezPni(root, conn, tmp_path)

    podzakladka._zastosuj_zmiane("ZUS", "Zakład Ubezpieczeń Społecznych")

    assert conn.execute("SELECT nadawca FROM punkty").fetchone()[0] == \
        "Zakład Ubezpieczeń Społecznych"
    assert [w["nazwa"] for w in podzakladka._wpisy] == ["Zakład Ubezpieczeń Społecznych"]


def test_zastosuj_zmiane_tworzy_wpis_w_dzienniku(root, conn, tmp_path):
    from zpo_tracker import dziennik

    get_or_create_punkt(conn, "ZUS", "Senatorska 6/8", None)
    podzakladka = PodzakladkaNadawcowBezPni(root, conn, tmp_path)

    podzakladka._zastosuj_zmiane("ZUS", "ZUS Warszawa")

    wpisy = dziennik.wczytaj_operacje(tmp_path)
    assert any(w["rodzaj"] == "zmien_nadawce" for w in wpisy)


def test_zastosuj_zmiane_kolizja_pokazuje_blad_bez_zmiany(root, conn, tmp_path, monkeypatch):
    id_a, _ = get_or_create_punkt(conn, "ZUS", "Senatorska 6/8", None)
    id_b, _ = get_or_create_punkt(conn, "Zaklad Ubezpieczen", "Senatorska 6/8", None)
    kurier_id = conn.execute(
        "INSERT INTO kurierzy(imie_nazwisko) VALUES ('Kowalski Jan')").lastrowid
    conn.execute(
        "INSERT INTO transakcje(data, kurier_id, punkt_id, ilosc_total) VALUES (?,?,?,?)",
        ("2026-08-10", kurier_id, id_a, 1))
    conn.execute(
        "INSERT INTO transakcje(data, kurier_id, punkt_id, ilosc_total) VALUES (?,?,?,?)",
        ("2026-08-10", kurier_id, id_b, 2))
    podzakladka = PodzakladkaNadawcowBezPni(root, conn, tmp_path)
    bledy = []
    monkeypatch.setattr(
        "zpo_tracker.gui.zakladka_slowniki.messagebox.showerror",
        lambda tytul, tresc: bledy.append(tresc),
    )

    podzakladka._zastosuj_zmiane("Zaklad Ubezpieczen", "ZUS")

    assert len(bledy) == 1
    nadawcy = {r[0] for r in conn.execute("SELECT nadawca FROM punkty")}
    assert nadawcy == {"ZUS", "Zaklad Ubezpieczen"}  # bez zmian


def test_zakladka_slowniki_ma_podzakladke_nadawcow(root, conn, tmp_path):
    zakladka = ZakladkaSlowniki(root, conn, tmp_path)
    # kurierzy zostaje na indeksie 0 - test_gui_smoke.py na tym polega
    assert zakladka._podzakladki[0].__class__.__name__ == "PodzakladkaProstegoSlownika"
    assert any(isinstance(p, PodzakladkaNadawcowBezPni) for p in zakladka._podzakladki)
