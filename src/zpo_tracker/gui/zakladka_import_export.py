"""
Zakładka import/export. Import: wczytanie .xlsx, ekran korekty pokazujący
WYŁĄCZNIE wiersze wymagające uwagi (odrzucone, propozycje scalenia
literówek do zatwierdzenia/odznaczenia, ostrzeżenia o różnicach
diakrytyków), reszta importuje się cicho z podsumowaniem liczbowym.
Export: wybór miesiąca, układ kolumn identyczny ze snapshotem.

Cała logika jest w import_orchestrator.py/eksport.py - tu tylko zbieranie
wartości z pól, wywołanie i wyświetlenie wyniku.
"""
from datetime import date
import tkinter as tk
from tkinter import filedialog, ttk

import openpyxl

from zpo_tracker import eksport
from zpo_tracker.import_orchestrator import (
    zaimportuj,
    znajdz_ostrzezenia_podobienstwa_kurierow,
    znajdz_propozycje_scalenia_kurierow,
    zwaliduj_wiersze,
)


def _wczytaj_surowe_wiersze(sciezka):
    wb = openpyxl.load_workbook(sciezka, data_only=True)
    ws = wb[wb.sheetnames[0]]
    naglowki = [c.value for c in next(ws.iter_rows(min_row=1, max_row=1))]
    return [dict(zip(naglowki, wiersz)) for wiersz in ws.iter_rows(min_row=2, values_only=True)]


class DialogKorektyImportu(tk.Toplevel):
    """Ekran korekty: tylko to, co wymaga uwagi. Reszta importuje się cicho."""

    def __init__(self, parent, conn, zwalidowane, odrzucone, propozycje, ostrzezenia, on_gotowe):
        super().__init__(parent)
        self.title("Korekta importu")
        self.geometry("640x520")
        self.conn = conn
        self.zwalidowane = zwalidowane
        self.odrzucone = odrzucone
        self.ostrzezenia = ostrzezenia
        self.on_gotowe = on_gotowe
        self.zmienne_propozycji = []

        ttk.Label(
            self,
            text=f"{len(zwalidowane)} wierszy do zaimportowania. "
                 f"Poniżej tylko to, co wymaga uwagi - reszta wejdzie cicho.",
            wraplength=600, justify="left",
        ).pack(anchor="w", padx=10, pady=(10, 6))

        notebook = ttk.Notebook(self)
        notebook.pack(fill="both", expand=True, padx=10, pady=6)

        if odrzucone:
            ramka = ttk.Frame(notebook)
            notebook.add(ramka, text=f"Odrzucone ({len(odrzucone)})")
            tekst = tk.Text(ramka, wrap="word")
            tekst.pack(fill="both", expand=True)
            for o in odrzucone:
                tekst.insert("end", f"• {o['wiersz'].get('Kurier', '?')}: {o['powod']}\n")
            tekst.configure(state="disabled")

        ramka_literowki = ttk.Frame(notebook)
        notebook.add(ramka_literowki, text=f"Prawdopodobne literówki ({len(propozycje)})")
        if not propozycje:
            ttk.Label(ramka_literowki, text="Brak.").pack(anchor="w", padx=6, pady=6)
        for p in propozycje:
            var = tk.BooleanVar(value=True)
            ttk.Checkbutton(
                ramka_literowki, variable=var,
                text=f"Scalić „{p['z']}” → „{p['na']}”",
            ).pack(anchor="w", padx=6, pady=2)
            self.zmienne_propozycji.append((p, var))

        if ostrzezenia:
            ramka_o = ttk.Frame(notebook)
            notebook.add(ramka_o, text=f"Różnice w zapisie ({len(ostrzezenia)})")
            tekst = tk.Text(ramka_o, wrap="word")
            tekst.pack(fill="both", expand=True)
            tekst.insert(
                "end",
                "Te pary różnią się tylko wielkością liter/polskimi znakami - "
                "NIE scalono automatycznie, wymaga ręcznej decyzji "
                "(zakładka Słowniki):\n\n",
            )
            for o in ostrzezenia:
                tekst.insert("end", f"• „{o.a}” / „{o.b}”\n")
            tekst.configure(state="disabled")

        pasek = ttk.Frame(self)
        pasek.pack(fill="x", padx=10, pady=10)
        ttk.Button(pasek, text="Zatwierdź import", command=self._zatwierdz).pack(side="right")
        ttk.Button(pasek, text="Anuluj", command=self.destroy).pack(side="right", padx=6)

    def _zatwierdz(self):
        mapowanie = {p["z"]: p["na"] for p, var in self.zmienne_propozycji if var.get()}
        wynik = zaimportuj(self.conn, self.zwalidowane, mapowanie_scalen=mapowanie)
        self.destroy()
        self.on_gotowe(wynik)


class ZakladkaImportExport(ttk.Frame):
    def __init__(self, parent, conn, on_zaimportowano=None):
        super().__init__(parent)
        self.conn = conn
        self.on_zaimportowano = on_zaimportowano

        ramka_import = ttk.LabelFrame(self, text="Import z .xlsx", padding=10)
        ramka_import.pack(fill="x", padx=10, pady=10)
        ttk.Button(ramka_import, text="Wybierz plik i importuj", command=self.importuj).pack(anchor="w")
        self.etykieta_import = ttk.Label(ramka_import, text="")
        self.etykieta_import.pack(anchor="w", pady=(6, 0))

        ramka_export = ttk.LabelFrame(self, text="Export do .xlsx", padding=10)
        ramka_export.pack(fill="x", padx=10, pady=10)

        dzis = date.today()
        ttk.Label(ramka_export, text="Rok:").grid(row=0, column=0, sticky="w")
        self.var_rok = tk.IntVar(value=dzis.year)
        ttk.Entry(ramka_export, textvariable=self.var_rok, width=6).grid(row=0, column=1, padx=6)

        ttk.Label(ramka_export, text="Miesiąc:").grid(row=0, column=2, sticky="w", padx=(12, 0))
        self.var_miesiac = tk.StringVar(value=eksport.NAZWY_MIESIECY_PL[dzis.month - 1])
        ttk.Combobox(
            ramka_export, textvariable=self.var_miesiac,
            values=eksport.NAZWY_MIESIECY_PL, width=12, state="readonly",
        ).grid(row=0, column=3, padx=6)

        ttk.Button(ramka_export, text="Eksportuj...", command=self.eksportuj).grid(
            row=0, column=4, padx=(12, 0)
        )
        self.etykieta_export = ttk.Label(ramka_export, text="")
        self.etykieta_export.grid(row=1, column=0, columnspan=5, sticky="w", pady=(6, 0))

    def importuj(self):
        sciezka = filedialog.askopenfilename(filetypes=[("Excel", "*.xlsx")])
        if not sciezka:
            return
        surowe = _wczytaj_surowe_wiersze(sciezka)
        zwalidowane, odrzucone = zwaliduj_wiersze(surowe)
        if not zwalidowane and not odrzucone:
            self.etykieta_import.configure(text="Brak wierszy do zaimportowania w tym pliku.")
            return
        propozycje = znajdz_propozycje_scalenia_kurierow(zwalidowane)
        ostrzezenia = znajdz_ostrzezenia_podobienstwa_kurierow(zwalidowane)
        DialogKorektyImportu(
            self, self.conn, zwalidowane, odrzucone, propozycje, ostrzezenia,
            on_gotowe=self._po_imporcie,
        )

    def _po_imporcie(self, wynik):
        tekst = f"Zaimportowano {wynik['zaimportowano']} wierszy."
        if wynik["wymagajace_uwagi"]:
            tekst += f" Do przejrzenia: {len(wynik['wymagajace_uwagi'])} (konflikty PNI/adres, duplikaty)."
        self.etykieta_import.configure(text=tekst)
        if self.on_zaimportowano:
            self.on_zaimportowano()

    def eksportuj(self):
        try:
            rok = int(self.var_rok.get())
            miesiac = eksport.NAZWY_MIESIECY_PL.index(self.var_miesiac.get()) + 1
        except ValueError:
            self.etykieta_export.configure(text="Nieprawidłowy rok.")
            return

        sciezka = filedialog.asksaveasfilename(
            defaultextension=".xlsx",
            initialfile=f"zpo-{rok}-{miesiac:02d}.xlsx",
            filetypes=[("Excel", "*.xlsx")],
        )
        if not sciezka:
            return
        liczba = eksport.eksportuj_miesiac(self.conn, rok, miesiac, sciezka)
        self.etykieta_export.configure(text=f"Wyeksportowano {liczba} transakcji do {sciezka}.")
