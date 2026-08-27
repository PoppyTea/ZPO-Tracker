"""
Ostatnie ogniwo łańcucha: zakładka Import podaje migawkę dialogowi
korekty, a ten przekazuje ją do `zaimportuj`.

Ten plik istnieje przez konkretną pomyłkę, którą warto pamiętać. Kaskada
dedukcji miejscowości była napisana, przetestowana i podpięta do
`get_or_create_adres` - a mimo to na żywo nie robiła NIC, bo nikt nie
przekazał jej migawki przez GUI. Wszystkie testy były zielone, bo każdy
sprawdzał swój kawałek. Luka siedziała dokładnie w miejscu, którego żaden
z nich nie dotykał: w przekazaniu parametru.

Stąd te testy sprawdzają WPIĘCIE, nie zachowanie kaskady - tamto ma
własne pliki. Pytanie brzmi wyłącznie: czy migawka dojeżdża tam, gdzie
ma dojechać.

Wymaga środowiska graficznego - pomijany tak samo jak reszta testów GUI.
"""
import subprocess
import sys
import tkinter as tk

import pytest

from zpo_tracker import rejonarz, repo
from zpo_tracker.gui.zakladka_import_export import ZakladkaImportExport


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


def _migawka(z_danymi):
    c = rejonarz.polacz(":memory:")
    if z_danymi:
        c.execute(
            """INSERT INTO adresy_rejony
               (klucz, klucz_ulica_nr, miejscowosc, ulica, nr, rejon)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (rejonarz.klucz_adresu("Ząbki", "Kwiatowa", "8"),
             rejonarz.klucz_ulica_nr("Kwiatowa", "8"), "Ząbki", "Kwiatowa", "8", "Z1"),
        )
    return c


def _zakladka(root, conn, tmp_path, conn_rejonarz):
    return ZakladkaImportExport(
        root, conn, str(tmp_path), conn_rejonarz=conn_rejonarz)


def test_zakladka_bez_migawki_nie_podaje_zrodla(root, conn, tmp_path):
    z = _zakladka(root, conn, tmp_path, None)
    assert z._szukaj_rejonarza() is None


def test_pusta_migawka_znaczy_to_samo_co_brak(root, conn, tmp_path):
    """Rozróżnienie „nie ma pliku" od „plik jest, ale pusty" dawałoby
    ciche różnice zachowania między stacjami - dla dedukcji obie sytuacje
    znaczą dokładnie tyle samo."""
    c = _migawka(z_danymi=False)
    try:
        assert _zakladka(root, conn, tmp_path, c)._szukaj_rejonarza() is None
    finally:
        c.close()


def test_niepusta_migawka_daje_dzialajace_zrodlo(root, conn, tmp_path):
    c = _migawka(z_danymi=True)
    try:
        szukaj = _zakladka(root, conn, tmp_path, c)._szukaj_rejonarza()
        assert szukaj is not None
        assert list(szukaj(rejonarz.klucz_ulica_nr("Kwiatowa", "8"))) == [("Ząbki", "Z1")]
    finally:
        c.close()


def test_dialog_korekty_przekazuje_zrodlo_do_importu(root, conn, tmp_path):
    """SEDNO tego pliku: parametr musi dojechać z dialogu aż do
    `zaimportuj`. To jest dokładnie to ogniwo, którego brak sprawił, że
    kaskada nie działała na żywo mimo zielonych testów wszystkich jej
    części z osobna."""
    from zpo_tracker.gui.zakladka_import_export import DialogKorektyImportu

    znacznik = object()
    przechwycone = {}

    dialog = DialogKorektyImportu(
        root, conn, str(tmp_path), "plik.xlsx", [], [], [], [],
        on_gotowe=lambda _w: None, szukaj_rejonarza=znacznik)
    try:
        dialog.czy_zaufany = lambda: False

        def falszywe_wykonaj(*_a, **kwargs):
            przechwycone.update(kwargs.get("kwargs", {}))
            return {"zaimportowano": 0, "wymagajace_uwagi": []}

        import zpo_tracker.gui.zakladka_import_export as modul
        oryginalne = modul.operacje.wykonaj
        modul.operacje.wykonaj = falszywe_wykonaj
        try:
            dialog._wykonaj_import()
        finally:
            modul.operacje.wykonaj = oryginalne
    finally:
        if dialog.winfo_exists():
            dialog.destroy()

    assert przechwycone.get("szukaj") is znacznik


# --- jeden przycisk na oba eksporty ------------------------------------

def test_podsumowanie_mowi_ile_POMINIETO_a_nie_tylko_ile_weszlo():
    """Użytkownik wskazuje plik ogólnopolski i musi zobaczyć, że z 22
    tysięcy wierszy wzięliśmy dwa i pół tysiąca. Bez tej liczby wygląda
    to na awarię importu, a jest poprawnym filtrowaniem."""
    from zpo_tracker.gui.zakladka_import_export import _podsumowanie_wczytania

    wynik = rejonarz.WynikImportuPunktow(
        wczytane=22393, zapisane=2354, pominiete=20039)
    tekst = _podsumowanie_wczytania(
        rejonarz.WynikWczytania(rejonarz.RODZAJ_PUNKTY_ZPO, wynik))

    assert "2354" in tekst and "20039" in tekst
    assert "WA" in tekst and "WW" in tekst


def test_podsumowanie_rejonarza_wymienia_pominiete_arkusze():
    from zpo_tracker.gui.zakladka_import_export import _podsumowanie_wczytania

    wynik = rejonarz.WynikImportu(zapisane=100, arkusze_pominiete=["Podsumowanie"])
    tekst = _podsumowanie_wczytania(
        rejonarz.WynikWczytania(rejonarz.RODZAJ_REJONARZ, wynik))
    assert "Podsumowanie" in tekst


def test_ostrzezenie_gdy_eksport_nie_dal_sie_przefiltrowac():
    """Cichy import CAŁEGO pliku ogólnopolskiego byłby gorszy od błędu -
    użytkownik miałby w rejestrze 22 tysiące cudzych punktów i nie
    dowiedziałby się o tym."""
    from zpo_tracker.gui.zakladka_import_export import _podsumowanie_wczytania

    wynik = rejonarz.WynikImportuPunktow(zapisane=22393, bez_filtrowania=True)
    tekst = _podsumowanie_wczytania(
        rejonarz.WynikWczytania(rejonarz.RODZAJ_PUNKTY_ZPO, wynik))
    assert "UWAGA" in tekst and "CAŁY plik" in tekst
