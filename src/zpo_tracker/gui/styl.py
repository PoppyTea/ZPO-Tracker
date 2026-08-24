"""
Tokeny wyglądu i konfiguracja ttk.Style - JEDYNE miejsce w projekcie,
które ustala kolory, odstępy i czcionki interfejsu.

Warstwa czysto prezentacyjna: nie podejmuje żadnych decyzji o danych ani
o nawigacji (patrz src/CLAUDE.md - "jeśli widget zaczyna decydować... to
kod należy do modułu logiki"). Zmiana czegokolwiek tutaj nie ma prawa
zmienić zachowania aplikacji.

Kolory wskaźników stanu pól mieszkają TUTAJ - `widget_pole.KOLORY` to
re-eksport tego samego obiektu, nie kopia. Zależność szła kiedyś odwrotnie
(styl importował z widgetu), co było przekręcone: moduł tokenów wyglądu
nie powinien pytać widgetu o kolory.
"""
import platform
import tkinter as tk
from tkinter import font as tkfont
from tkinter import ttk


def luminancja(kolor):
    """Względna luminancja wg WCAG 2.1 dla `#rrggbb`."""
    kolor = kolor.lstrip("#")
    skladowe = [int(kolor[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    skladowe = [
        s / 12.92 if s <= 0.04045 else ((s + 0.055) / 1.055) ** 2.4
        for s in skladowe
    ]
    return 0.2126 * skladowe[0] + 0.7152 * skladowe[1] + 0.0722 * skladowe[2]


def kontrast(pierwszy, drugi):
    """Współczynnik kontrastu wg WCAG 2.1, od 1.0 do 21.0.

    Istnieje po to, żeby dobór kolorów w tym projekcie był LICZONY, a nie
    oceniany na oko - raz już to kosztowało etykiety kolumn o kontraście
    2.85:1, czyli poniżej progu nawet dla grafiki, na napisach mówiących
    nietechnicznemu użytkownikowi, co ma wpisać. Progi pilnują testy.
    """
    jasniejsza = max(luminancja(pierwszy), luminancja(drugi))
    ciemniejsza = min(luminancja(pierwszy), luminancja(drugi))
    return (jasniejsza + 0.05) / (ciemniejsza + 0.05)


# Neutralne mają lekki skręt w niebieski (ku akcentowi) - czysta szarość
# czyta się jak brak decyzji. Akcent musi być niebieski: cztery kolory
# semantyczne wskaźników (zielony/pomarańczowy/czerwony/szary) są zajęte,
# a akcent kolidujący z którymkolwiek z nich zabiłby ich czytelność.
#
# DOMYŚLNY JEST TRYB CIEMNY - na takim realnie pracują użytkownicy
# w dziale. Jasny zestaw zostaje niżej jako PALETA_JASNA, żeby ewentualne
# przełączenie było podmianą słownika, a nie ponownym dobieraniem barw.
PALETA = {
    "tlo": "#14181f",
    "powierzchnia": "#1c212a",
    # W ciemnym motywie "wgłębione" jest CIEMNIEJSZE od powierzchni
    # (odwrotnie niż w jasnym) - inaczej pole readonly czytałoby się jako
    # wyróżnione, a ma się czytać jako bezwładne.
    "powierzchnia_wglebiona": "#0f1216",
    "tekst": "#e6e9ef",
    "tekst_wyciszony": "#9aa5b5",
    # UWAGA: 3.77:1 na tle - wystarcza na grafikę, NIE na tekst (próg 4.5).
    # Wyłącznie do elementów nieinformacyjnych: obramowania pomocnicze,
    # widgety wyłączone. NIGDY jako `foreground`; test
    # test_tekst_slaby_nie_jest_uzywany_do_tekstu skanuje ten plik.
    "tekst_slaby": "#6b7482",
    "linia": "#2a313c",
    "linia_mocna": "#3d4653",
    "akcent": "#7fa8d4",
    "akcent_tlo": "#1e2c3d",
    # Akcent jest jasny, więc tekst NA nim musi być ciemny - odwrotnie
    # niż w motywie jasnym.
    "akcent_tekst": "#0e1116",
}

PALETA_JASNA = {
    "tlo": "#f7f8fa",
    "powierzchnia": "#ffffff",
    "powierzchnia_wglebiona": "#eef1f5",
    "tekst": "#16191f",
    "tekst_wyciszony": "#5a6473",
    "tekst_slaby": "#8b95a5",
    "linia": "#dde1e8",
    "linia_mocna": "#c3cad6",
    "akcent": "#1f3a5f",
    "akcent_tlo": "#e7edf5",
    "akcent_tekst": "#ffffff",
}

# Wskaźniki stanu pola (dedukcja.STANY). Przestrojone pod ciemne tło -
# poprzedni zestaw był dobrany pod jasne i na ciemnym schodził poniżej
# progu czytelności. Progi pilnuje test_kolory_stanow_widoczne_na_tle.
KOLORY_STANOW = {
    "szary": "#8b95a5",
    "zielony": "#4caf6a",
    "pomaranczowy": "#e0913c",
    "czerwony": "#e4695c",
}


def przygas(kolor, ile):
    """Miesza kolor z tłem. `ile=0` to kolor pełny, `ile=1` to samo tło."""
    k = kolor.lstrip("#")
    t = PALETA["tlo"].lstrip("#")
    return "#%02x%02x%02x" % tuple(
        round(int(k[i:i + 2], 16) * (1 - ile) + int(t[i:i + 2], 16) * ile)
        for i in (0, 2, 4)
    )


# Trzystopniowa rampa na tej samej barwie zastępuje trzy różne grubości
# obwódki (decyzja Papavera 2026-08-24). Grubość jest teraz stała, bo jej
# przełączanie zmieniało rozmiar widgetu i zawartość komórek skakała przy
# każdej dedukcji.
KOLORY_STANOW_POLPRZYGASZONE = {k: przygas(v, 0.30) for k, v in KOLORY_STANOW.items()}
KOLORY_STANOW_PRZYGASZONE = {k: przygas(v, 0.58) for k, v in KOLORY_STANOW.items()}

# Box afordancji rozwijanej listy (wariant A2). Uczestniczy w tej samej
# rampie co obwódka: pole bez kursora ma przygaszoną obwódkę, więc jasny
# prostokąt obok niej rozbijałby całość na dwa niezależne sygnały.
STRZALKA_TLO = PALETA["linia_mocna"]
STRZALKA_TLO_PRZYGASZONE = przygas(PALETA["linia_mocna"], 0.55)
STRZALKA_ZNAK = PALETA["tekst"]
STRZALKA_ZNAK_PRZYGASZONY = PALETA["tekst_wyciszony"]

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
