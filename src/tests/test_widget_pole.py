"""
widget_pole.PoleZeWskaznikiem: pasek koloru stanu (dedukcja.StanPola) +
obwódka sygnalizująca uwagę/kolejność nawigacji. Wymaga środowiska
graficznego - pomijany automatycznie, jeśli niedostępne (patrz
test_gui_smoke.py, ten sam mechanizm).
"""
import subprocess
import sys
import tkinter as tk

import pytest

from zpo_tracker.gui.widget_pole import GRUBOSC_AKTYWNE, GRUBOSC_NASTEPNE, KOLORY, PoleZeWskaznikiem


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
def pole(root):
    p = PoleZeWskaznikiem(root, tk.Entry)
    p.pack()
    return p


def test_widget_pola_jest_realnie_zagniezdzony_w_wrapperze(pole):
    # regresja: `widget_pola.pack()` pakuje widget do JEGO WŁASNEGO
    # rodzica tkinter (ustalonego przy tworzeniu), nie do tego, w czym
    # ktoś go później pack()/grid() - gdyby widget_pola powstawał z innym
    # parentem niż `self`, pasek koloru i pole żyłyby jako RODZEŃSTWO w
    # oknie nadrzędnym, nie wewnątrz tego samego wrappera (sprawdzone
    # eksperymentalnie przed napisaniem tego testu)
    assert pole.widget_pola in pole.winfo_children()
    assert pole.widget_pola.winfo_parent() == str(pole)


def test_domyslny_stan_jest_szary(pole):
    assert pole.pasek.cget("background") == KOLORY["szary"]


def test_ustaw_stan_koloruje_pasek(pole):
    pole.ustaw_stan("czerwony")
    assert pole.pasek.cget("background") == KOLORY["czerwony"]


def test_ustaw_aktywnosc_true_wlacza_edycje_i_takefocus(pole):
    pole.ustaw_aktywnosc(True)
    assert str(pole.widget_pola.cget("state")) == "normal"
    assert int(pole.widget_pola.cget("takefocus")) == 1


def test_ustaw_aktywnosc_false_readonly_i_pomija_tabem(pole):
    pole.ustaw_aktywnosc(False)
    assert str(pole.widget_pola.cget("state")) == "readonly"
    assert int(pole.widget_pola.cget("takefocus")) == 0


def test_pole_aktywne_dostaje_grubsza_obwodke_w_kolorze_stanu(pole):
    pole.ustaw_stan("pomaranczowy")
    pole.ustaw_aktywnosc(True)
    assert int(pole.cget("highlightthickness")) == GRUBOSC_AKTYWNE
    assert pole.cget("highlightbackground") == KOLORY["pomaranczowy"]


def test_pole_nieaktywne_bez_obwodki(pole):
    pole.ustaw_stan("zielony")
    pole.ustaw_aktywnosc(False)
    assert int(pole.cget("highlightthickness")) == 0


def test_ustaw_nastepne_daje_cienszy_motyw_niz_aktywne(pole):
    pole.ustaw_stan("zielony")
    pole.ustaw_nastepne(True)
    assert int(pole.cget("highlightthickness")) == GRUBOSC_NASTEPNE
    assert pole.cget("highlightbackground") == KOLORY["zielony"]


def test_aktywne_wygrywa_nad_nastepne(pole):
    # pole może być JEDNOCZEŚNIE "wymaga uwagi" i "następne w kolejce Tab" -
    # grubsza obwódka (uwaga) ma priorytet, nie ma cichej nadpisywalności
    pole.ustaw_stan("czerwony")
    pole.ustaw_nastepne(True)
    pole.ustaw_aktywnosc(True)
    assert int(pole.cget("highlightthickness")) == GRUBOSC_AKTYWNE


def test_wylaczenie_nastepne_zdejmuje_obwodke(pole):
    pole.ustaw_nastepne(True)
    pole.ustaw_nastepne(False)
    assert int(pole.cget("highlightthickness")) == 0


def test_zablokuj_nie_wybucha_i_nic_jeszcze_nie_robi(pole):
    # 3.2 - dziś tylko miejsce na przyszłą blokadę kliknięciem wskaźnika
    pole.zablokuj(True)
    pole.zablokuj(False)


def test_wspiera_widget_z_ustaw_stan_pola(root):
    # EntryZPodpowiedzia ma własny ustaw_stan_pola(state, takefocus) -
    # PoleZeWskaznikiem musi go użyć zamiast surowego configure
    class _Fejk(tk.Frame):
        def __init__(self, parent):
            super().__init__(parent)
            self.wolania = []

        def ustaw_stan_pola(self, state, takefocus):
            self.wolania.append((state, takefocus))

    p = PoleZeWskaznikiem(root, _Fejk)
    p.ustaw_aktywnosc(True)
    p.ustaw_aktywnosc(False)
    assert p.widget_pola.wolania == [("normal", 1), ("readonly", 0)]
