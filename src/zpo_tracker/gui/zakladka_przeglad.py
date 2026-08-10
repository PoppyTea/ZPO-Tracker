"""
Zakładka przeglądania - lista wprowadzonych transakcji, tylko odczyt.
"""
from tkinter import ttk

from zpo_tracker import repo
from zpo_tracker.gui.widget_tabela import Tabela

KOLUMNY = [
    ("data", "Data", 90),
    ("kurier", "Kurier", 160),
    ("nadawca", "Nadawca", 120),
    ("adres", "Adres", 220),
    ("rejon", "Rejon", 70),
    ("wykonawca", "Wykonawca", 100),
    ("ilosc_total", "Ilość", 60),
    ("ilosc_zpo", "w tym ZPO", 80),
    ("komentarz", "Komentarz", 200),
]


class ZakladkaPrzeglad(ttk.Frame):
    def __init__(self, parent, conn):
        super().__init__(parent)
        self.conn = conn

        pasek = ttk.Frame(self)
        pasek.pack(fill="x", padx=6, pady=6)
        ttk.Button(pasek, text="Odśwież", command=self.odswiez).pack(side="left")
        self.etykieta_liczby = ttk.Label(pasek, text="")
        self.etykieta_liczby.pack(side="left", padx=10)

        self.tabela = Tabela(self, KOLUMNY)
        self.tabela.pack(fill="both", expand=True, padx=6, pady=(0, 6))

        self.odswiez()

    def odswiez(self):
        wiersze = repo.pobierz_transakcje(self.conn, limit=1000)
        self.tabela.ustaw_dane(wiersze)
        self.etykieta_liczby.configure(text=f"{len(wiersze)} transakcji")
