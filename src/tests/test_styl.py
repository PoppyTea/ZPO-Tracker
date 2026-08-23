"""
gui.styl: tokeny wyglądu (paleta, skala odstępów, rodziny czcionek) +
konfiguracja ttk.Style. Warstwa czysto prezentacyjna - nie wolno jej
podejmować żadnych decyzji o danych ani o nawigacji.

Testy dzielą się na dwie grupy: tokeny i dobór rodziny czcionki są czystymi
danymi/funkcjami i sprawdzają się bez środowiska graficznego; konfiguracja
ttk.Style wymaga Tk i jest pomijana tak samo jak reszta testów GUI
(patrz test_gui_smoke.py).
"""
import re
import subprocess
import sys
import tkinter as tk

import pytest

from zpo_tracker.gui import styl


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


wymaga_gui = pytest.mark.skipif(
    not _ma_display(), reason="wymaga środowiska graficznego (DISPLAY)"
)


# --- tokeny: bez Tk -----------------------------------------------------

KLUCZE_OBOWIAZKOWE = {
    "tlo", "powierzchnia", "powierzchnia_wglebiona",
    "tekst", "tekst_wyciszony", "tekst_slaby",
    "linia", "linia_mocna",
    "akcent", "akcent_tlo", "akcent_tekst",
}


def test_paleta_ma_komplet_kluczy():
    assert KLUCZE_OBOWIAZKOWE <= set(styl.PALETA)


def test_paleta_zawiera_wylacznie_kolory_hex():
    for nazwa, wartosc in styl.PALETA.items():
        assert re.fullmatch(r"#[0-9a-f]{6}", wartosc), f"{nazwa}={wartosc!r}"


def test_odstepy_zaczynaja_sie_od_czterech_i_rosna():
    assert styl.ODSTEPY[0] == 4
    assert list(styl.ODSTEPY) == sorted(set(styl.ODSTEPY))


def test_kolory_stanow_sa_te_same_co_w_widget_pole():
    """Wskaźniki stanu pól mają JEDNO źródło prawdy. Gdyby styl.py
    zdublował te kolory, rozjechałyby się po cichu przy pierwszej
    korekcie któregokolwiek z dwóch miejsc."""
    from zpo_tracker.gui import widget_pole
    assert styl.KOLORY_STANOW is widget_pole.KOLORY


# --- dobór rodziny czcionki: czysta funkcja, bez Tk ---------------------

def test_wybierz_rodzine_bierze_pierwsza_dostepna():
    assert styl.wybierz_rodzine(["Segoe UI", "Arial"], {"Arial", "Segoe UI"}) == "Segoe UI"


def test_wybierz_rodzine_pomija_niedostepne():
    assert styl.wybierz_rodzine(["Segoe UI", "Arial"], {"Arial"}) == "Arial"


def test_wybierz_rodzine_bez_zadnego_trafienia_oddaje_czcionke_tk():
    """Środowisko produkcyjne jest zablokowane - instalacja czcionki
    odpada, więc brak trafienia musi kończyć się czymś, co na pewno
    istnieje, a nie wyjątkiem przy starcie aplikacji."""
    assert styl.wybierz_rodzine(["Segoe UI"], set()) == "TkDefaultFont"


# --- świadomość DPI -----------------------------------------------------

def test_swiadomosc_dpi_poza_windowsem_jest_bezpiecznym_brakiem_dzialania():
    assert styl.wlacz_swiadomosc_dpi(system="Linux") is False


def test_swiadomosc_dpi_nie_wybucha_gdy_windows_nie_ma_api():
    """Starsze Windowsy nie mają shcore.dll. Rozmyta aplikacja jest do
    przeżycia, aplikacja, która nie wstaje - nie."""
    assert styl.wlacz_swiadomosc_dpi(system="Windows", ladowarka=lambda: (_ for _ in ()).throw(OSError())) is False


# --- ttk.Style: wymaga Tk ----------------------------------------------

@pytest.fixture
def root():
    r = tk.Tk()
    yield r
    r.destroy()


@wymaga_gui
def test_zastosuj_styl_przelacza_motyw_na_clam(root):
    """`clam` to jedyny wbudowany motyw ttk, który honoruje ustawione
    kolory tła/obramowania - `vista` na Windowsie ignoruje większość
    z nich, więc bez tej podmiany reszta konfiguracji jest bez efektu."""
    s = styl.zastosuj_styl(root)
    assert s.theme_use() == "clam"


@wymaga_gui
def test_zastosuj_styl_definiuje_przycisk_akcentu(root):
    s = styl.zastosuj_styl(root)
    assert s.lookup("Akcent.TButton", "background") == styl.PALETA["akcent"]
    assert s.lookup("Akcent.TButton", "foreground") == styl.PALETA["akcent_tekst"]


@wymaga_gui
def test_zastosuj_styl_definiuje_etykiete_kolumny(root):
    """Etykiety kolumn siatki mają być wyciszone i mniejsze od danych -
    dziś są tej samej wagi, więc nagłówek zlewa się z zawartością.

    Wyciszone, ale NIE `tekst_slaby`: ten ma na tle kontrast 2.85:1, czyli
    poniżej progu nawet dla grafiki. Etykieta kolumny mówi nietechnicznemu
    użytkownikowi, co ma wpisać - to najgorsze możliwe miejsce na
    oszczędzanie na czytelności (patrz docs/ux-ui.md, "idioto-odporność").
    """
    s = styl.zastosuj_styl(root)
    assert s.lookup("Etykieta.TLabel", "foreground") == styl.PALETA["tekst_wyciszony"]


@wymaga_gui
def test_naglowki_tabeli_sa_czytelne(root):
    """Ten sam powód co wyżej - nagłówek kolumny w podglądzie jest
    informacją, nie ozdobą."""
    s = styl.zastosuj_styl(root)
    assert s.lookup("Treeview.Heading", "foreground") == styl.PALETA["tekst_wyciszony"]


def test_tekst_slaby_nie_jest_uzywany_do_tekstu():
    """Token zostaje w palecie (linie pomocnicze, elementy wyłączone), ale
    żaden styl tekstowy nie ma prawa go użyć - kontrast 2.85:1. Test
    pilnuje, żeby nie wrócił tylnymi drzwiami przy kolejnej zmianie."""
    zrodlo = (styl.__file__)
    with open(zrodlo, encoding="utf-8") as f:
        tresc = f.read()
    for linia in tresc.splitlines():
        if "foreground=PALETA" in linia:
            assert "tekst_slaby" not in linia, f"kontrast 2.85:1 w: {linia.strip()}"


@wymaga_gui
def test_zastosuj_styl_jest_idempotentny(root):
    """app.py może zawołać to ponownie (np. przy zmianie użytkownika);
    druga konfiguracja nie ma prawa niczego popsuć."""
    styl.zastosuj_styl(root)
    s = styl.zastosuj_styl(root)
    assert s.theme_use() == "clam"
    assert s.lookup("Akcent.TButton", "background") == styl.PALETA["akcent"]


@wymaga_gui
def test_zastosuj_styl_ustawia_tlo_okna(root):
    styl.zastosuj_styl(root)
    assert root.cget("background") == styl.PALETA["tlo"]
