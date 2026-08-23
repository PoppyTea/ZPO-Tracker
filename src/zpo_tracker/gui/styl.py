"""
Tokeny wyglądu i konfiguracja ttk.Style - JEDYNE miejsce w projekcie,
które ustala kolory, odstępy i czcionki interfejsu.

Warstwa czysto prezentacyjna: nie podejmuje żadnych decyzji o danych ani
o nawigacji (patrz src/CLAUDE.md - "jeśli widget zaczyna decydować... to
kod należy do modułu logiki"). Zmiana czegokolwiek tutaj nie ma prawa
zmienić zachowania aplikacji.

Kolory wskaźników stanu pól NIE są tu zdublowane - `KOLORY_STANOW` jest
tym samym obiektem co `widget_pole.KOLORY`. Dwie kopie tej samej palety
rozjeżdżają się po cichu przy pierwszej korekcie jednej z nich.
"""
import platform
import tkinter as tk
from tkinter import font as tkfont
from tkinter import ttk

from zpo_tracker.gui.widget_pole import KOLORY as KOLORY_STANOW

# Neutralne mają lekki skręt w niebieski (ku akcentowi) - czysta szarość
# czyta się jak brak decyzji. Akcent musi być niebieski: cztery kolory
# semantyczne wskaźników (zielony/pomarańczowy/czerwony/szary) są zajęte,
# a akcent kolidujący z którymkolwiek z nich zabiłby ich czytelność.
PALETA = {
    "tlo": "#f7f8fa",
    "powierzchnia": "#ffffff",
    "powierzchnia_wglebiona": "#eef1f5",
    "tekst": "#16191f",
    "tekst_wyciszony": "#5a6473",
    # UWAGA: kontrast 2.85:1 na tle - poniżej progu nawet dla grafiki.
    # Wyłącznie do elementów nieinformacyjnych (obramowania pomocnicze,
    # widgety wyłączone). NIGDY jako `foreground` tekstu; test
    # test_tekst_slaby_nie_jest_uzywany_do_tekstu tego pilnuje.
    "tekst_slaby": "#8b95a5",
    "linia": "#dde1e8",
    "linia_mocna": "#c3cad6",
    "akcent": "#1f3a5f",
    "akcent_tlo": "#e7edf5",
    "akcent_tekst": "#ffffff",
}

# Jedna skala zamiast czterech rytmów (padx=2/6/8/16) rozsianych dziś po
# zakladka_wprowadzanie.py.
ODSTEPY = (4, 8, 12, 16, 24, 32)

RODZINY_UI = ["Segoe UI", "Cantarell", "DejaVu Sans", "Liberation Sans", "Arial"]
RODZINY_MONO = ["Consolas", "DejaVu Sans Mono", "Liberation Mono", "Courier New"]

ROZMIAR_BAZOWY = 10
ROZMIAR_MALY = 8
ROZMIAR_DUZY = 12

_ZAPASOWA_UI = "TkDefaultFont"


def wybierz_rodzine(kandydaci, dostepne):
    """Pierwsza rodzina z `kandydaci` obecna w `dostepne`.

    Brak trafienia oddaje nazwę czcionki wbudowanej w Tk, a nie wyjątek:
    środowisko produkcyjne jest zablokowane i bez uprawnień administratora,
    więc doinstalowanie kroju odpada, a aplikacja, która z tego powodu nie
    wstaje, jest znacznie gorsza od aplikacji brzydkiej.
    """
    for rodzina in kandydaci:
        if rodzina in dostepne:
            return rodzina
    return _ZAPASOWA_UI


def _domyslna_ladowarka_dpi():  # pragma: no cover - tylko Windows
    import ctypes

    ctypes.windll.shcore.SetProcessDpiAwareness(1)


def wlacz_swiadomosc_dpi(system=None, ladowarka=None):
    """Zdejmuje rozmycie na monitorach ze skalowaniem (Windows 8.1+).

    Zwraca True, jeśli faktycznie zadziałało. Poza Windowsem i na starszych
    Windowsach bez `shcore.dll` jest świadomym brakiem działania - rozmyta
    aplikacja jest do przeżycia, aplikacja, która nie startuje, nie jest.

    UWAGA: włączenie tego zmienia rzeczywisty rozmiar okna w pikselach,
    więc układ trzeba obejrzeć na docelowej maszynie. Dlatego jest to
    osobne, jawne wywołanie, a nie efekt uboczny `zastosuj_styl`.
    """
    if (system or platform.system()) != "Windows":
        return False
    try:
        (ladowarka or _domyslna_ladowarka_dpi)()
    except Exception:
        return False
    return True


def zastosuj_styl(root):
    """Konfiguruje wygląd wszystkich widgetów ttk w oknie `root`.

    Idempotentne - wolno wołać wielokrotnie. Zwraca `ttk.Style`, żeby
    wywołujący mógł dopisać własne style, nie tworząc drugiej instancji.
    """
    style = ttk.Style(root)

    # `clam` jako jedyny wbudowany motyw honoruje ustawiane niżej kolory
    # tła i obramowania. `vista` (domyślny na Windowsie) ignoruje
    # większość z nich - bez tej podmiany reszta konfiguracji nie ma
    # żadnego widocznego efektu.
    style.theme_use("clam")

    dostepne = set(tkfont.families(root))
    rodzina_ui = wybierz_rodzine(RODZINY_UI, dostepne)
    rodzina_mono = wybierz_rodzine(RODZINY_MONO, dostepne)

    czcionka_ui = (rodzina_ui, ROZMIAR_BAZOWY)
    czcionka_mala = (rodzina_ui, ROZMIAR_MALY)
    czcionka_duza = (rodzina_ui, ROZMIAR_DUZY, "bold")
    czcionka_mono = (rodzina_mono, ROZMIAR_BAZOWY)

    root.configure(background=PALETA["tlo"])

    style.configure(".", font=czcionka_ui,
                    background=PALETA["tlo"], foreground=PALETA["tekst"])
    style.configure("TFrame", background=PALETA["tlo"])
    style.configure("TLabel", background=PALETA["tlo"], foreground=PALETA["tekst"])
    style.configure("TCheckbutton", background=PALETA["tlo"], foreground=PALETA["tekst_wyciszony"])

    style.configure("TButton", background=PALETA["powierzchnia"],
                    foreground=PALETA["tekst"], bordercolor=PALETA["linia_mocna"],
                    focuscolor=PALETA["akcent"], padding=(ODSTEPY[3], ODSTEPY[0] + 2),
                    relief="flat")
    style.map("TButton",
              background=[("active", PALETA["akcent_tlo"])],
              bordercolor=[("active", PALETA["akcent"])])

    # Jedyny przycisk z wypełnieniem w całej aplikacji - akcja główna ma
    # być rozpoznawalna bez czytania etykiety.
    style.configure("Akcent.TButton", background=PALETA["akcent"],
                    foreground=PALETA["akcent_tekst"], bordercolor=PALETA["akcent"],
                    padding=(ODSTEPY[3], ODSTEPY[0] + 2), relief="flat")
    style.map("Akcent.TButton", background=[("active", PALETA["tekst"])])

    style.configure("TEntry", fieldbackground=PALETA["powierzchnia"],
                    foreground=PALETA["tekst"], bordercolor=PALETA["linia_mocna"],
                    lightcolor=PALETA["linia_mocna"], darkcolor=PALETA["linia_mocna"],
                    insertcolor=PALETA["tekst"], padding=ODSTEPY[0])
    style.map("TEntry",
              fieldbackground=[("readonly", PALETA["powierzchnia_wglebiona"])],
              foreground=[("readonly", PALETA["tekst_wyciszony"])])

    style.configure("TNotebook", background=PALETA["powierzchnia_wglebiona"], borderwidth=0)
    style.configure("TNotebook.Tab", background=PALETA["powierzchnia_wglebiona"],
                    foreground=PALETA["tekst_wyciszony"],
                    padding=(ODSTEPY[3], ODSTEPY[1]), borderwidth=0)
    style.map("TNotebook.Tab",
              background=[("selected", PALETA["tlo"])],
              foreground=[("selected", PALETA["tekst"])])

    style.configure("Treeview", background=PALETA["powierzchnia"],
                    fieldbackground=PALETA["powierzchnia"], foreground=PALETA["tekst"],
                    bordercolor=PALETA["linia"], rowheight=22)
    style.configure("Treeview.Heading", background=PALETA["tlo"],
                    foreground=PALETA["tekst_wyciszony"], font=czcionka_mala, relief="flat")
    style.map("Treeview",
              background=[("selected", PALETA["akcent_tlo"])],
              foreground=[("selected", PALETA["tekst"])])

    # Etykiety kolumn siatki: mniejsze i wyciszone. Dziś mają tę samą wagę
    # co dane pod nimi, więc nagłówek zlewa się z zawartością.
    style.configure("Etykieta.TLabel", background=PALETA["tlo"],
                    foreground=PALETA["tekst_wyciszony"], font=czcionka_mala)
    style.configure("Naglowek.TLabel", background=PALETA["tlo"],
                    foreground=PALETA["tekst"], font=czcionka_duza)
    style.configure("Wyciszony.TLabel", background=PALETA["tlo"],
                    foreground=PALETA["tekst_wyciszony"], font=czcionka_mala)
    style.configure("Mono.TLabel", background=PALETA["tlo"],
                    foreground=PALETA["tekst"], font=czcionka_mono)

    return style
