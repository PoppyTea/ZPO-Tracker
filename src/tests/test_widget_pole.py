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

from zpo_tracker.gui import styl
from zpo_tracker.gui.widget_pole import (
    GRUBOSC_OBWODKI, KOLORY, KOLORY_POLPRZYGASZONE, KOLORY_PRZYGASZONE,
    PoleZeWskaznikiem,
)


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


# --- obwódka: stała grubość, sygnał niesie kolor -----------------------
#
# Kontrakt zmieniony 2026-08-24 decyzją Papavera: wariant obwódki zależy
# od FOKUSU (czy pole jest właśnie wypełniane), nie od tego, czy jest
# edytowalne. W2 (pełny kolor) dla pola z kursorem, W3 (przygaszony)
# dla reszty.

@pytest.mark.parametrize("aktywne,nastepne,fokus", [
    (False, False, False), (True, False, False), (False, True, False),
    (True, True, True), (True, False, True),
])
def test_grubosc_obwodki_jest_stala_w_kazdej_kombinacji(pole, aktywne, nastepne, fokus):
    """Anty-regresja na realny błąd: grubość przełączana między 0, 1 i 2 px
    zmienia żądany rozmiar widgetu, więc zawartość komórek siatki skakała
    przy każdej dedukcji."""
    pole.ustaw_stan("pomaranczowy")
    pole.ustaw_aktywnosc(aktywne)
    pole.ustaw_nastepne(nastepne)
    pole.ustaw_fokus(fokus)
    assert int(pole.cget("highlightthickness")) == GRUBOSC_OBWODKI


def test_pole_bez_kursora_ma_obwodke_przygaszona(pole):
    pole.ustaw_stan("zielony")
    pole.ustaw_aktywnosc(True)
    assert pole.cget("highlightbackground") == KOLORY_PRZYGASZONE["zielony"]


def test_pole_z_kursorem_ma_pelny_kolor_stanu(pole):
    pole.ustaw_stan("pomaranczowy")
    pole.ustaw_aktywnosc(True)
    pole.ustaw_fokus(True)
    assert pole.cget("highlightbackground") == KOLORY["pomaranczowy"]


def test_nastepne_w_kolejce_jest_posrodku_rampy(pole):
    pole.ustaw_stan("czerwony")
    pole.ustaw_nastepne(True)
    assert pole.cget("highlightbackground") == KOLORY_POLPRZYGASZONE["czerwony"]


def test_kursor_wygrywa_nad_nastepnym(pole):
    """Pole może być jednocześnie wypełniane i następne w kolejce -
    kursor jest silniejszym sygnałem."""
    pole.ustaw_stan("czerwony")
    pole.ustaw_nastepne(True)
    pole.ustaw_fokus(True)
    assert pole.cget("highlightbackground") == KOLORY["czerwony"]


def test_utrata_kursora_wraca_do_przygaszonego(pole):
    pole.ustaw_stan("zielony")
    pole.ustaw_fokus(True)
    pole.ustaw_fokus(False)
    assert pole.cget("highlightbackground") == KOLORY_PRZYGASZONE["zielony"]


@pytest.mark.parametrize("stan", ["szary", "zielony", "pomaranczowy", "czerwony"])
def test_rampa_jest_monotoniczna(stan):
    """Trzy stopnie muszą różnić się na tyle, żeby dało się je odróżnić -
    inaczej rampa jest ozdobą, nie sygnałem."""
    tlo = styl.PALETA["tlo"]
    k = [styl.kontrast(m[stan], tlo)
         for m in (KOLORY_PRZYGASZONE, KOLORY_POLPRZYGASZONE, KOLORY)]
    assert k[0] < k[1] < k[2]
    assert k[2] / k[0] > 1.5


# --- afordancja rozwijanej listy (wariant A2) --------------------------

def test_bez_wariantow_nie_ma_strzalki(pole):
    """Pole bez listy ma wyglądać jak zwykłe pole - dokładanie strzałki
    wszędzie zabiłoby cały sens tego rozróżnienia."""
    pole.ustaw_liste(0)
    assert pole._strzalka is None


def test_warianty_pokazuja_strzalke(pole):
    pole.ustaw_liste(2)
    assert pole._strzalka is not None
    assert pole._strzalka in pole.winfo_children()


def test_zejscie_do_zera_chowa_strzalke(pole):
    """Dedukcja potrafi przejść z niejednoznacznego w jednoznaczne -
    strzałka musi wtedy zniknąć, nie zostać sierotą."""
    pole.ustaw_liste(3)
    pole.ustaw_liste(0)
    assert pole._strzalka is None


def test_strzalka_nie_rozwala_struktury_widgetu(pole):
    """Testy nawigacji polegają na tym, że widget pola jest BEZPOŚREDNIM
    dzieckiem wrappera - strzałka jest rodzeństwem, nie warstwą pośrednią."""
    pole.ustaw_liste(2)
    assert pole.widget_pola.winfo_parent() == str(pole)


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
