#!/usr/bin/env python3
"""
Siatka wariantów wyglądu pól formularza — do wyboru, nie do wdrożenia.

    python demo/warianty-wskaznikow.py

Dwa pytania naraz:

A. Jak pole ma sygnalizować, że MA rozwijaną listę wariantów. Dziś nie
   sygnalizuje tego wcale — pole z podpowiedziami i zwykłe Entry są
   wizualnie nierozróżnialne, lista wyskakuje dopiero po wpisaniu znaku.
B. Jak traktować obwódkę pola wymagającego uwagi. Dziś to gołe 2 px
   koloru stanu, bez cienkiej szarej, którą mają pola spokojne.

Świadomie zbudowane w tkinterze, nie w HTML: połowa pytania brzmi "czy da
się to narysować", a makieta w przeglądarce odpowiedziałaby na to
zmyśleniem. Każdy wariant tutaj albo działa, albo go nie ma.

Prototyp jednorazowy (demo/AGENTS.md) — nie podlega TDD, nie jest częścią
aplikacji. Warianty implementuje NA WŁASNĄ RĘKĘ, nie przez
widget_pole.PoleZeWskaznikiem, bo o to właśnie chodzi: sprawdzić, co by
trzeba było w tamtym zmienić.
"""
import sys
import tkinter as tk
from pathlib import Path
from tkinter import ttk

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from zpo_tracker.gui import styl  # noqa: E402

P = styl.PALETA
S = styl.KOLORY_STANOW


def przygas(kolor, ile=0.45):
    """Miesza kolor w stronę tła — do wariantu z obwódką stonowaną."""
    k = kolor.lstrip("#")
    t = P["tlo"].lstrip("#")
    zmiks = [
        round(int(k[i:i + 2], 16) * (1 - ile) + int(t[i:i + 2], 16) * ile)
        for i in (0, 2, 4)
    ]
    return "#%02x%02x%02x" % tuple(zmiks)


# ---------------------------------------------------------------- warianty
# Każdy wariant to funkcja (rodzic, stan, tekst, szerokosc) -> widget.
# GRUBOSC_CALKOWITA jest wspólna dla wszystkich: przełączanie stanu nie
# ma prawa zmieniać rozmiaru pola, bo inaczej cała siatka wierszy drga
# przy każdej dedukcji.
GRUBOSC_CALKOWITA = 3


def _rama(rodzic, **kw):
    return tk.Frame(rodzic, **kw)


def _pasek(rodzic, kolor, szerokosc=4):
    """Pasek wskaźnika. `pack_propagate(False)` jest OBOWIĄZKOWE — bez
    niego Tk zwija ramkę bez dzieci do zera i wskaźnik po prostu znika
    (dokładnie ten błąd popełniłem w pierwszej wersji tego pliku;
    widget_pole.py robi to poprawnie od początku)."""
    pasek = tk.Frame(rodzic, width=szerokosc, background=kolor)
    pasek.pack(side="left", fill="y")
    pasek.pack_propagate(False)
    return pasek


def _entry(rodzic, tekst, szer, fg=None):
    var = tk.StringVar(value=tekst)
    e = ttk.Entry(rodzic, textvariable=var, width=szer, foreground=fg or P["tekst"])
    e._var = var
    return e


def w0_obecny(rodzic, stan, tekst, szer):
    """Stan obecny: 2 px koloru stanu, zero szarej."""
    f = _rama(rodzic, highlightthickness=2, highlightbackground=S[stan],
              highlightcolor=S[stan], background=P["tlo"], padx=1, pady=1)
    _pasek(f, S[stan])
    _entry(f, tekst, szer).pack(side="left", fill="both", expand=True)
    return f


def w1_tylko_wskaznik(rodzic, stan, tekst, szer):
    """Obwódka zawsze szara; uwagę niesie wskaźnik i kolor tekstu."""
    f = _rama(rodzic, highlightthickness=1, highlightbackground=P["linia_mocna"],
              highlightcolor=P["linia_mocna"], background=P["tlo"], padx=1, pady=1)
    _pasek(f, S[stan])
    _entry(f, tekst, szer, fg=S[stan]).pack(side="left", fill="both", expand=True)
    return f


def w2_cienka_kolorowa(rodzic, stan, tekst, szer):
    """1 px w kolorze stanu + wskaźnik."""
    f = _rama(rodzic, highlightthickness=1, highlightbackground=S[stan],
              highlightcolor=S[stan], background=P["tlo"], padx=1, pady=1)
    _pasek(f, S[stan])
    _entry(f, tekst, szer).pack(side="left", fill="both", expand=True)
    return f


def w3_cienka_przygaszona(rodzic, stan, tekst, szer):
    """Jak W2, ale obwódka zmieszana z tłem — wskaźnik zostaje pełny."""
    stonowany = przygas(S[stan])
    f = _rama(rodzic, highlightthickness=1, highlightbackground=stonowany,
              highlightcolor=stonowany, background=P["tlo"], padx=1, pady=1)
    _pasek(f, S[stan])
    _entry(f, tekst, szer).pack(side="left", fill="both", expand=True)
    return f


def w4_szara_na_zewnatrz(rodzic, stan, tekst, szer):
    """Szara 1 px NA ZEWNĄTRZ, kolor 2 px wewnątrz.

    Kolor wewnętrzny nie jest osobną obwódką — to `background` ramki
    prześwitujący przez pas `borderwidth`. Tk nie ma opcji koloru
    obramowania Frame'a, ale ma kolor tła, a przy relief="flat" pas
    obramowania jest po prostu tłem.
    """
    f = _rama(rodzic, highlightthickness=1, highlightbackground=P["linia_mocna"],
              highlightcolor=P["linia_mocna"], background=S[stan],
              borderwidth=2, relief="flat")
    _pasek(f, S[stan])
    _entry(f, tekst, szer).pack(side="left", fill="both", expand=True)
    return f


def w5_szara_wewnatrz(rodzic, stan, tekst, szer):
    """Kolor 2 px na zewnątrz, szara 1 px wewnątrz — odwrotnie niż W4."""
    f = _rama(rodzic, highlightthickness=2, highlightbackground=S[stan],
              highlightcolor=S[stan], background=P["linia_mocna"],
              borderwidth=1, relief="flat")
    _pasek(f, S[stan])
    _entry(f, tekst, szer).pack(side="left", fill="both", expand=True)
    return f


def w6_szara_z_obu_stron(rodzic, stan, tekst, szer):
    """Szara — kolor — szara. Trzecia warstwa to własna obwódka ttk.Entry
    (pod motywem clam `bordercolor` jest ustawialny), nie kolejna ramka."""
    f = _rama(rodzic, highlightthickness=1, highlightbackground=P["linia_mocna"],
              highlightcolor=P["linia_mocna"], background=S[stan],
              borderwidth=2, relief="flat")
    _pasek(f, S[stan])
    e = _entry(f, tekst, szer)
    e.configure(style="Obwiedziony.TEntry")
    e.pack(side="left", fill="both", expand=True)
    return f


WARIANTY_OBWODEK = [
    ("W0", "stan obecny — 2 px koloru, bez szarej", w0_obecny),
    ("W1", "same wskaźniki; obwódka zawsze szara, kolor w tekście", w1_tylko_wskaznik),
    ("W2", "cienka 1 px w kolorze stanu", w2_cienka_kolorowa),
    ("W3", "cienka 1 px, kolor przygaszony ku tłu", w3_cienka_przygaszona),
    ("W4", "szara na zewnątrz, kolor 2 px wewnątrz", w4_szara_na_zewnatrz),
    ("W5", "kolor 2 px na zewnątrz, szara wewnątrz", w5_szara_wewnatrz),
    ("W6", "szara — kolor — szara (trzecia z ttk.Entry)", w6_szara_z_obu_stron),
]


# ------------------------------------------------------- afordancje listy

def _baza_pola(rodzic, stan):
    return _rama(rodzic, highlightthickness=1, highlightbackground=S[stan],
                 highlightcolor=S[stan], background=P["tlo"], padx=1, pady=1)


def a1_wskaznik_z_trojkatem(rodzic, stan, tekst, ile):
    """Wskaźnik rozszerza się i sam niesie trójkąt."""
    f = _baza_pola(rodzic, stan)
    pasek = tk.Frame(f, width=14, background=S[stan])
    pasek.pack(side="left", fill="y")
    pasek.pack_propagate(False)
    tk.Label(pasek, text="▾", background=S[stan], foreground=P["tlo"],
             font=("TkDefaultFont", 7)).pack(expand=True)
    _entry(f, tekst, 22).pack(side="left", fill="both", expand=True)
    return f


def a2_szary_box(rodzic, stan, tekst, ile):
    """Klasyczny combobox: szary kwadrat z trójkątem po prawej."""
    f = _baza_pola(rodzic, stan)
    _pasek(f, S[stan])
    _entry(f, tekst, 19).pack(side="left", fill="both", expand=True)
    box = tk.Frame(f, background=P["linia_mocna"], width=18)
    box.pack(side="right", fill="y")
    box.pack_propagate(False)
    tk.Label(box, text="▾", background=P["linia_mocna"],
             foreground=P["tekst"], font=("TkDefaultFont", 7)).pack(expand=True)
    return f


def a3_pasek_segmentowy(rodzic, stan, tekst, ile):
    """Pasek na dole podzielony na tyle segmentów, ile jest wariantów;
    podświetlony mówi, który jest wybrany."""
    zew = tk.Frame(rodzic, background=P["tlo"])
    f = _baza_pola(zew, stan)
    _pasek(f, S[stan])
    _entry(f, tekst, 22).pack(side="left", fill="both", expand=True)
    f.pack(fill="x")
    segmenty = tk.Frame(zew, background=P["tlo"], height=3)
    segmenty.pack(fill="x")
    for i in range(ile):
        tk.Frame(segmenty, background=S[stan] if i == 0 else P["linia"],
                 height=3).pack(side="left", fill="x", expand=True, padx=(0, 1))
    return zew


def a4_box_akcentu(rodzic, stan, tekst, ile):
    """Box w błękitno-szarym tonie akcentu zamiast jaskrawego stanu."""
    f = _baza_pola(rodzic, stan)
    _pasek(f, S[stan])
    _entry(f, tekst, 19).pack(side="left", fill="both", expand=True)
    box = tk.Frame(f, background=P["akcent"], width=18)
    box.pack(side="right", fill="y")
    box.pack_propagate(False)
    tk.Label(box, text="▾", background=P["akcent"],
             foreground=P["akcent_tekst"], font=("TkDefaultFont", 7)).pack(expand=True)
    return f


def a5_pastylka_z_liczba(rodzic, stan, tekst, ile):
    """Liczba wariantów wprost + trójkąt."""
    f = _baza_pola(rodzic, stan)
    _pasek(f, S[stan])
    _entry(f, tekst, 16).pack(side="left", fill="both", expand=True)
    box = tk.Frame(f, background=P["akcent_tlo"], width=34)
    box.pack(side="right", fill="y")
    box.pack_propagate(False)
    tk.Label(box, text=f"{ile} ▾", background=P["akcent_tlo"],
             foreground=P["akcent"], font=("TkDefaultFont", 8)).pack(expand=True)
    return f


def a6_sam_trojkat(rodzic, stan, tekst, ile):
    """Minimum: trójkąt w kolorze stanu, bez tła."""
    f = _baza_pola(rodzic, stan)
    _pasek(f, S[stan])
    _entry(f, tekst, 20).pack(side="left", fill="both", expand=True)
    tk.Label(f, text="▾", background=P["powierzchnia"], foreground=S[stan],
             font=("TkDefaultFont", 8), width=2).pack(side="right", fill="y")
    return f


WARIANTY_AFORDANCJI = [
    ("A1", "wskaźnik szerszy, trójkąt w nim", a1_wskaznik_z_trojkatem),
    ("A2", "szary box z trójkątem (klasyczny combobox)", a2_szary_box),
    ("A3", "pasek segmentowy na dole — 1 segment = 1 wariant", a3_pasek_segmentowy),
    ("A4", "box w tonie akcentu, nie w kolorze stanu", a4_box_akcentu),
    ("A5", "pastylka z liczbą wariantów", a5_pastylka_z_liczba),
    ("A6", "sam trójkąt w kolorze stanu", a6_sam_trojkat),
]


# ------------------------------------------------------------------- okno

def naglowek(rodzic, tekst):
    ttk.Label(rodzic, text=tekst, style="Naglowek.TLabel").pack(
        anchor="w", pady=(styl.ODSTEPY[4], styl.ODSTEPY[1]))


def podpis(rodzic, kod, opis):
    wiersz = ttk.Frame(rodzic)
    ttk.Label(wiersz, text=kod, style="Mono.TLabel", width=4).pack(side="left")
    ttk.Label(wiersz, text=opis, style="Wyciszony.TLabel").pack(side="left")
    return wiersz


def main():
    root = tk.Tk()
    root.title("ZPO Tracker — warianty wskaźników")
    root.geometry("1180x1080")
    style = styl.zastosuj_styl(root)
    style.configure("Obwiedziony.TEntry", bordercolor=P["linia_mocna"],
                    lightcolor=P["linia_mocna"], darkcolor=P["linia_mocna"])

    ramka = ttk.Frame(root)
    ramka.pack(fill="both", expand=True, padx=styl.ODSTEPY[4], pady=styl.ODSTEPY[3])

    # --- A: afordancja rozwijanej listy
    naglowek(ramka, "A · Skąd użytkownik ma wiedzieć, że tu jest lista wariantów")
    ttk.Label(
        ramka, style="Wyciszony.TLabel",
        text="Wszystkie na tym samym przypadku: pole nadawcy, stan pomarańczowy, dwa warianty do wyboru.",
    ).pack(anchor="w", pady=(0, styl.ODSTEPY[2]))

    siatka_a = ttk.Frame(ramka)
    siatka_a.pack(anchor="w")
    for i, (kod, opis, buduj) in enumerate(WARIANTY_AFORDANCJI):
        podpis(siatka_a, kod, opis).grid(row=i, column=0, sticky="w", pady=6, padx=(0, 16))
        buduj(siatka_a, "pomaranczowy", "PKO BP", 2).grid(row=i, column=1, sticky="w", pady=6)

    # --- B: obwódki
    naglowek(ramka, "B · Jak gruba i jak kolorowa ma być obwódka pola wymagającego uwagi")
    ttk.Label(
        ramka, style="Wyciszony.TLabel",
        text="Ten sam wariant w czterech stanach. Sumaryczna grubość jest wszędzie równa —"
             " przełączanie stanu nie może przesuwać zawartości siatki.",
    ).pack(anchor="w", pady=(0, styl.ODSTEPY[2]))

    siatka_b = ttk.Frame(ramka)
    siatka_b.pack(anchor="w")
    stany = [("zielony", "ZUS"), ("pomaranczowy", "PKO BP"),
             ("czerwony", "Kruk"), ("szary", "")]
    for kol, (stan, _) in enumerate(stany):
        ttk.Label(siatka_b, text=stan, style="Etykieta.TLabel").grid(
            row=0, column=kol + 1, sticky="w", padx=6, pady=(0, 4))
    for i, (kod, opis, buduj) in enumerate(WARIANTY_OBWODEK, start=1):
        podpis(siatka_b, kod, opis).grid(row=i, column=0, sticky="w", pady=5, padx=(0, 16))
        for kol, (stan, tekst) in enumerate(stany):
            buduj(siatka_b, stan, tekst, 14).grid(row=i, column=kol + 1, padx=6, pady=5)

    # --- C: wiersze bez danych
    naglowek(ramka, "C · Wiersze z brakiem danych w podglądzie")
    ttk.Label(
        ramka, style="Wyciszony.TLabel",
        text="Po lewej dzisiejszy stan (sam kolorowy napis), po prawej z kolorowym wskaźnikiem wiersza.",
    ).pack(anchor="w", pady=(0, styl.ODSTEPY[2]))

    porownanie = ttk.Frame(ramka)
    porownanie.pack(anchor="w", fill="x")
    for kolumna, z_wskaznikiem in enumerate([False, True]):
        blok = ttk.Frame(porownanie)
        blok.grid(row=0, column=kolumna, sticky="nw", padx=(0, 40))
        for adres, rejon, brak in [("Grochowska 214", "WA119", False),
                                   ("Fieldorfa 41", "???", True),
                                   ("Marsa 56", "WA124", False)]:
            w = tk.Frame(blok, background=P["powierzchnia"])
            w.pack(fill="x", pady=1)
            kolor = S["czerwony"] if brak else P["powierzchnia"]
            if z_wskaznikiem:
                wsk = tk.Frame(w, width=3, background=kolor)
                wsk.pack(side="left", fill="y")
                wsk.pack_propagate(False)
            tk.Label(w, text=adres, background=P["powierzchnia"], width=18,
                     anchor="w", foreground=P["tekst"]).pack(side="left", padx=6)
            tk.Label(w, text=rejon, background=P["powierzchnia"], width=8, anchor="w",
                     foreground=S["czerwony"] if brak else P["tekst"]).pack(side="left")

    if "--zrzut" in sys.argv:
        root.update()
        root.after(300, root.destroy)
    root.mainloop()


if __name__ == "__main__":
    main()
