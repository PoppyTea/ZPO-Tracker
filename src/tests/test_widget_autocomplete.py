"""
widget_autocomplete.EntryZPodpowiedzia: rozszerzenia pod dedukcję pól
(0.1-alpha.3.1) - stan+takefocus razem, podmienne źródło kandydatów,
Enter/Tab jako programowe "idź dalej", rozwijanie zawężonej listy na
pusty fokus. Wymaga środowiska graficznego - pomijany automatycznie,
jeśli niedostępne (patrz test_gui_smoke.py, ten sam mechanizm).
"""
import subprocess
import sys
import tkinter as tk

import pytest

from zpo_tracker.gui.widget_autocomplete import EntryZPodpowiedzia


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


def test_ustaw_stan_pola_normal_wlacza_takefocus(root):
    w = EntryZPodpowiedzia(root, lambda: [])
    w.ustaw_stan_pola("readonly", takefocus=0)
    w.ustaw_stan_pola("normal", takefocus=1)
    assert str(w.entry.cget("state")) == "normal"
    assert int(w.entry.cget("takefocus")) == 1


def test_ustaw_stan_pola_readonly_wylacza_takefocus(root):
    w = EntryZPodpowiedzia(root, lambda: [])
    w.ustaw_stan_pola("readonly", takefocus=0)
    assert str(w.entry.cget("state")) == "readonly"
    assert int(w.entry.cget("takefocus")) == 0


def test_ustaw_zrodlo_kandydatow_podmienia_funkcje(root):
    w = EntryZPodpowiedzia(root, lambda: ["a"])
    assert w.pobierz_kandydatow() == ["a"]
    w.ustaw_zrodlo_kandydatow(lambda: ["b", "c"])
    assert w.pobierz_kandydatow() == ["b", "c"]


def test_on_dalej_wolane_i_break_zwracane_gdy_podany(root):
    wolania = []
    w = EntryZPodpowiedzia(root, lambda: [], on_dalej=lambda: wolania.append(1))
    wynik = w._zatwierdz_i_dalej(None)
    assert wolania == [1]
    assert wynik == "break"


def test_brak_on_dalej_nie_przerywa_domyslnej_nawigacji(root):
    # bez "break" Tab/Return idą normalną ścieżką Tk (<<NextWindow>>) -
    # regresja tu oznaczałaby, że Tab przestaje działać w KAŻDYM polu
    # bez jawnie podanego on_dalej (patrz plan, sekcja B3)
    w = EntryZPodpowiedzia(root, lambda: [])
    assert w._zatwierdz_i_dalej(None) is None


def test_rozwijanie_na_pusty_fokus_pokazuje_zawezonych_kandydatow(root):
    w = EntryZPodpowiedzia(root, lambda: ["Żabka", "Gemartis"], rozwijaj_na_pusty_fokus=True)
    w.pack()
    root.update()
    w.entry.focus_set()
    root.update()
    assert w._aktywne_podpowiedzi == ["Żabka", "Gemartis"]
    assert w._lista_toplevel is not None
    assert w._lista_toplevel.state() != "withdrawn"


def test_bez_flagi_pusty_fokus_nic_nie_pokazuje(root):
    # domyślne zachowanie dla już wpiętych pól (kurier/nadawca/adres) -
    # nie chcemy, żeby setki kandydatów wyskakiwały na każdy fokus
    w = EntryZPodpowiedzia(root, lambda: ["Żabka", "Gemartis"])
    w.pack()
    root.update()
    w.entry.focus_set()
    root.update()
    assert w._aktywne_podpowiedzi == []


def test_rozwijanie_na_fokus_pomija_gdy_pole_ma_juz_tekst(root):
    w = EntryZPodpowiedzia(root, lambda: ["Żabka", "Gemartis"], rozwijaj_na_pusty_fokus=True)
    w.set("Żabka")
    w.pack()
    root.update()
    w.entry.focus_set()
    root.update()
    assert w._aktywne_podpowiedzi == []
