#!/usr/bin/env python3
"""
Podgląd przejścia stylistycznego w REALNYM tkinterze - makieta HTML
pokazuje zamiar, ten plik pokazuje, co faktycznie wyrenderuje Tk.

    python demo/podglad-stylu.py            # z nowym stylem
    python demo/podglad-stylu.py --bez      # jak wygląda dziś (do porównania)

Prototyp jednorazowy (patrz demo/AGENTS.md) - nie podlega TDD i nie jest
częścią aplikacji. Odtwarza wycinek zakładki "Wprowadzanie" na sztywnych
danych; zero połączenia z bazą.
"""
import sys
import tkinter as tk
from pathlib import Path
from tkinter import ttk

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from zpo_tracker.gui import styl  # noqa: E402
from zpo_tracker.gui.widget_pole import PoleZeWskaznikiem  # noqa: E402

ZE_STYLEM = "--bez" not in sys.argv

WIERSZE = [
    ("WA119", "ZUS", "Grochowska 214, Warszawa", "201884", "148", "31",
     ["zielony"] * 6, [False, False, False, False, True, True]),
    ("WA119", "PKO BP", "Ostrobramska 75C, Warszawa", "", "96", "12",
     ["szary", "pomaranczowy", "zielony", "pomaranczowy", "szary", "szary"],
     [False, True, False, True, True, True]),
    ("???", "Kruk", "Fieldorfa 41, Warszawa", "", "54", "54",
     ["czerwony", "czerwony", "czerwony", "czerwony", "szary", "szary"],
     [False, True, True, True, True, True]),
]

PODGLAD = [
    ("2026-08-24", "Kowalczyk Marek", "ZUS", "Grochowska 214, Warszawa", "WA119", "148", "31"),
    ("2026-08-24", "Kowalczyk Marek", "PKO BP", "Ostrobramska 75C, Warszawa", "WA119", "96", "12"),
    ("2026-08-24", "Kowalczyk Marek", "Kruk", "Fieldorfa 41, Warszawa", "???", "54", "54"),
    ("2026-08-23", "Savchenko Dmytro", "ZUS", "Płowiecka 12, Warszawa", "WA124", "203", "47"),
    ("2026-08-23", "Savchenko Dmytro", "Kruk", "Marsa 56, Warszawa", "WA124", "77", "9"),
]


def pole(rodzic, wartosc, stan, aktywne, szerokosc):
    var = tk.StringVar(value=wartosc)
    p = PoleZeWskaznikiem(
        rodzic, lambda r: ttk.Entry(r, textvariable=var, width=szerokosc))
    p.ustaw_stan(stan)
    p.ustaw_aktywnosc(aktywne)
    p._var = var  # utrzymuje referencję, żeby GC nie zjadł StringVar
    return p


def main():
    root = tk.Tk()
    root.title("ZPO Tracker — podgląd stylu" + ("" if ZE_STYLEM else " (stan obecny)"))
    root.geometry("1000x700")

    etykieta_kol = "TLabel"
    if ZE_STYLEM:
        styl.zastosuj_styl(root)
        etykieta_kol = "Etykieta.TLabel"

    notebook = ttk.Notebook(root)
    notebook.pack(fill="both", expand=True)
    for nazwa in ["Przeglądanie"]:
        notebook.add(ttk.Frame(notebook), text=nazwa)

    karta = ttk.Frame(notebook)
    notebook.add(karta, text="Wprowadzanie")
    for nazwa in ["Import / Export", "Słowniki", "Scalanie", "Historia"]:
        notebook.add(ttk.Frame(notebook), text=nazwa)
    notebook.select(karta)

    odstep = styl.ODSTEPY[3] if ZE_STYLEM else 6

    # --- podgląd ---
    gora = ttk.Frame(karta)
    gora.pack(fill="both", expand=True, padx=odstep, pady=(odstep, 0))
    ttk.Label(gora, text="PODGLĄD", style=etykieta_kol).pack(anchor="w")

    kolumny = ("data", "kurier", "nadawca", "adres", "rejon", "ilosc", "zpo")
    naglowki = ("Data", "Kurier", "Nadawca", "Adres", "Rejon", "Ilość", "w tym ZPO")
    szer = (90, 140, 90, 230, 70, 60, 80)
    tabela = ttk.Treeview(gora, columns=kolumny, show="headings", height=6)
    for k, n, s in zip(kolumny, naglowki, szer):
        tabela.heading(k, text=n)
        tabela.column(k, width=s, anchor="e" if k in ("ilosc", "zpo") else "w")
    for w in PODGLAD:
        tabela.insert("", "end", values=w)
    tabela.pack(fill="both", expand=True, pady=(styl.ODSTEPY[0] if ZE_STYLEM else 2, 0))

    # --- blankiet ---
    dol = ttk.Frame(karta)
    dol.pack(fill="both", expand=True, padx=odstep, pady=odstep)

    naglowek = ttk.Frame(dol)
    naglowek.pack(fill="x", pady=(0, odstep))
    ttk.Label(naglowek, text="KURIER", style=etykieta_kol).pack(side="left", padx=(0, 6))
    pole(naglowek, "Kowalczyk Marek", "zielony", True, 26).pack(side="left")
    ttk.Label(naglowek, text="DATA", style=etykieta_kol).pack(side="left", padx=(odstep, 6))
    pole(naglowek, "2026-08-24", "zielony", True, 12).pack(side="left")
    ttk.Label(naglowek, text="WYKONAWCA", style=etykieta_kol).pack(side="left", padx=(odstep, 6))
    pole(naglowek, "Trans-Kurier", "zielony", False, 16).pack(side="left")

    siatka = ttk.Frame(dol)
    siatka.pack(fill="x")
    szerokosci = (9, 16, 30, 12, 8, 9)
    for kol, tekst in enumerate(["Rejon", "Nadawca", "Adres", "PNI ZPO", "Ilość", "w tym ZPO"]):
        ttk.Label(siatka, text=tekst, style=etykieta_kol, anchor="w").grid(
            row=0, column=kol, padx=2, sticky="ew", pady=(0, 2))
    for nr, (*wartosci, stany, aktywne) in enumerate(WIERSZE, start=1):
        for kol, (wart, stan, akt, s) in enumerate(zip(wartosci, stany, aktywne, szerokosci)):
            pole(siatka, wart, stan, akt, s).grid(row=nr, column=kol, padx=2, pady=2, sticky="ew")

    akcje = ttk.Frame(dol)
    akcje.pack(fill="x", pady=(odstep, 0))
    ttk.Button(akcje, text="+ wiersz").pack(side="left")
    ttk.Button(akcje, text="Zapisz blankiet",
               style="Akcent.TButton" if ZE_STYLEM else "TButton").pack(side="left", padx=8)
    ttk.Label(akcje, text="Zapisano 2 wiersze. Pominięto 1 — brak ilości.",
              foreground=styl.KOLORY_STANOW["zielony"]).pack(side="left", padx=8)

    if "--zrzut" in sys.argv:
        root.update()
        root.after(400, root.destroy)
    root.mainloop()


if __name__ == "__main__":
    main()
