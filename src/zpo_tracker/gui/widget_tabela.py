"""
Wspólna tabela (Treeview) z sortowaniem po kliknięciu nagłówka, scrollbarami
i powiększaniem (Ctrl+scroll skaluje czcionkę/wysokość wiersza) - używana
przez zakładkę przeglądania i panel podglądu DB nad formularzem
wprowadzania. Zero logiki biznesowej - tylko wyświetlanie tego, co dostanie.
"""
from tkinter import ttk


class Tabela(ttk.Frame):
    def __init__(self, parent, kolumny):
        """kolumny: lista (klucz, naglowek, szerokosc)."""
        super().__init__(parent)
        self.kolumny = kolumny
        self._dane = []
        self._sortowanie_odwrocone = {}
        self._rozmiar_czcionki = 10
        self._styl_nazwa = f"Tabela{id(self)}.Treeview"

        self.tree = ttk.Treeview(
            self, columns=[k for k, _, _ in kolumny], show="headings",
            style=self._styl_nazwa,
        )
        for klucz, naglowek, szerokosc in kolumny:
            self.tree.heading(
                klucz, text=naglowek, command=lambda k=klucz: self._sortuj(k)
            )
            self.tree.column(klucz, width=szerokosc, anchor="w")

        vsb = ttk.Scrollbar(self, orient="vertical", command=self.tree.yview)
        hsb = ttk.Scrollbar(self, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)

        self.tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)

        self.tree.bind("<Control-MouseWheel>", self._zoom_windows)
        self.tree.bind("<Control-Button-4>", lambda e: self._zoom_krok(1))
        self.tree.bind("<Control-Button-5>", lambda e: self._zoom_krok(-1))

        self._zastosuj_czcionke()

    def ustaw_dane(self, wiersze):
        """wiersze: lista dictów z kluczami odpowiadającymi kolumnom."""
        self._dane = list(wiersze)
        self._odswiez()

    def _odswiez(self):
        self.tree.delete(*self.tree.get_children())
        for wiersz in self._dane:
            wartosci = [wiersz.get(k, "") for k, _, _ in self.kolumny]
            self.tree.insert("", "end", values=wartosci)

    def _sortuj(self, klucz):
        odwroc = self._sortowanie_odwrocone.get(klucz, False)
        self._dane.sort(
            key=lambda w: (w.get(klucz) is None, w.get(klucz)), reverse=odwroc
        )
        self._sortowanie_odwrocone[klucz] = not odwroc
        self._odswiez()

    def _zoom_windows(self, event):
        self._zoom_krok(1 if event.delta > 0 else -1)

    def _zoom_krok(self, kierunek):
        self._rozmiar_czcionki = max(7, min(20, self._rozmiar_czcionki + kierunek))
        self._zastosuj_czcionke()

    def _zastosuj_czcionke(self):
        styl = ttk.Style()
        styl.configure(self._styl_nazwa, font=("TkDefaultFont", self._rozmiar_czcionki))
        styl.configure(self._styl_nazwa, rowheight=int(self._rozmiar_czcionki * 2.2))
