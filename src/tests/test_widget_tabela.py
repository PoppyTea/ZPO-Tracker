"""
widget_tabela.Tabela: mapowanie zaznaczenia (iid) na pełny wiersz danych +
callback dwukliku (0.1-alpha.3.2, widok poprawek). Wymaga środowiska
graficznego - pomijany automatycznie, jeśli niedostępne (patrz
test_gui_smoke.py, ten sam mechanizm).
"""
import subprocess
import sys
import tkinter as tk

import pytest

from zpo_tracker.gui.widget_tabela import Tabela


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

KOLUMNY = [("data", "Data", 90), ("kurier", "Kurier", 160)]


@pytest.fixture
def root():
    r = tk.Tk()
    yield r
    r.destroy()


def test_wiersz_zaznaczony_zwraca_pelny_dict_nie_tylko_wyswietlane_kolumny(root):
    tabela = Tabela(root, KOLUMNY)
    tabela.ustaw_dane([{"id": 7, "data": "2026-08-10", "kurier": "Kowalski Jan"}])
    tabela.tree.selection_set(tabela.tree.get_children()[0])

    wiersz = tabela.wiersz_zaznaczony()

    assert wiersz["id"] == 7  # "id" nie jest w KOLUMNY - musi mimo to być dostępne


def test_wiersz_zaznaczony_brak_zaznaczenia_zwraca_none(root):
    tabela = Tabela(root, KOLUMNY)
    tabela.ustaw_dane([{"id": 1, "data": "2026-08-10", "kurier": "A"}])
    assert tabela.wiersz_zaznaczony() is None


def test_wiersz_zaznaczony_odporny_na_sortowanie(root):
    # zakladka_historia.py: sortowanie po kliknięciu nagłówka zmienia
    # kolejność wierszy - identyfikacja MUSI iść po wartości, nie pozycji
    tabela = Tabela(root, KOLUMNY)
    tabela.ustaw_dane([
        {"id": 1, "data": "2026-08-10", "kurier": "B"},
        {"id": 2, "data": "2026-08-11", "kurier": "A"},
    ])
    tabela._sortuj("kurier")  # przestawia kolejność, regeneruje iid

    iid_pierwszego = tabela.tree.get_children()[0]
    tabela.tree.selection_set(iid_pierwszego)
    wiersz = tabela.wiersz_zaznaczony()

    assert wiersz["kurier"] == tabela.tree.item(iid_pierwszego, "values")[1]


def test_wiersze_zaznaczone_wiele_naraz(root):
    tabela = Tabela(root, KOLUMNY)
    tabela.ustaw_dane([
        {"id": 1, "data": "2026-08-10", "kurier": "A"},
        {"id": 2, "data": "2026-08-11", "kurier": "B"},
    ])
    dzieci = tabela.tree.get_children()
    tabela.tree.selection_set(dzieci)

    wiersze = tabela.wiersze_zaznaczone()

    assert {w["id"] for w in wiersze} == {1, 2}


def test_dwuklik_wola_callback_z_pelnym_wierszem(root):
    wolania = []
    tabela = Tabela(root, KOLUMNY, on_dwuklik=wolania.append)
    tabela.ustaw_dane([{"id": 5, "data": "2026-08-10", "kurier": "A"}])
    tabela.tree.selection_set(tabela.tree.get_children()[0])

    tabela._na_dwuklik(None)

    assert len(wolania) == 1
    assert wolania[0]["id"] == 5


def test_bez_on_dwuklik_nie_binduje_zdarzenia(root):
    # domyślne zachowanie (Przegląd bez edycji, podgląd formularza) -
    # konstrukcja bez on_dwuklik nie może wybuchnąć
    Tabela(root, KOLUMNY)
