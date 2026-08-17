"""
Wspólna tabela (Treeview) z sortowaniem po kliknięciu nagłówka, scrollbarami
i powiększaniem (Ctrl+scroll skaluje czcionkę/wysokość wiersza) - używana
przez zakładkę przeglądania i panel podglądu DB nad formularzem
wprowadzania. Zero logiki biznesowej - tylko wyświetlanie tego, co dostanie.
"""
from tkinter import ttk


class Tabela(ttk.Frame):
    def __init__(self, parent, kolumny, on_dwuklik=None):
        """
        kolumny: lista (klucz, naglowek, szerokosc). `on_dwuklik` (opcjonalny,
        0.1-alpha.3.2): wołane z PEŁNYM dictem wiersza (nie tylko kolumnami
        wyświetlanymi) po dwukliku - widok poprawek dostaje w ten sposób
        `id`/`uuid` mimo że tabela ich nie pokazuje. Bez `on_dwuklik`
        zdarzenie w ogóle nie jest podpinane (istniejący, tylko-do-odczytu
        użytkownicy tego widgetu mają zostać nietknięci).
        """
        super().__init__(parent)
        self.kolumny = kolumny
        self.on_dwuklik = on_dwuklik
        self._dane = []
        self._iid_do_wiersza = {}
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
        if on_dwuklik:
            self.tree.bind("<Double-Button-1>", self._na_dwuklik)

        self._zastosuj_czcionke()

    def ustaw_dane(self, wiersze):
        """wiersze: lista dictów z kluczami odpowiadającymi kolumnom."""
        self._dane = list(wiersze)
        self._odswiez()

    def _odswiez(self):
        self.tree.delete(*self.tree.get_children())
        # mapa PRZEBUDOWANA przy każdym odświeżeniu (razem z iid, które
        # Treeview przydziela na nowo przy każdym insert) - bezpieczne po
        # sortowaniu, patrz zakladka_historia.py (ten sam problem, ten sam
        # powód: identyfikacja po wartości, nie po pozycji w drzewie)
        self._iid_do_wiersza = {}
        for wiersz in self._dane:
            wartosci = [wiersz.get(k, "") for k, _, _ in self.kolumny]
            iid = self.tree.insert("", "end", values=wartosci)
            self._iid_do_wiersza[iid] = wiersz

    def wiersz_zaznaczony(self):
        """Pełny dict (WSZYSTKIE klucze z `ustaw_dane`, nie tylko kolumny
        wyświetlane) pierwszego zaznaczonego wiersza, albo None."""
        zaznaczenie = self.tree.selection()
        if not zaznaczenie:
            return None
        return self._iid_do_wiersza.get(zaznaczenie[0])

    def wiersze_zaznaczone(self):
        """Pełne dicty wszystkich zaznaczonych wierszy (Treeview ma domyślnie
        `selectmode='extended'`, więc Ctrl/Shift-klik działają od ręki)."""
        return [self._iid_do_wiersza[iid] for iid in self.tree.selection()
                if iid in self._iid_do_wiersza]

    def _na_dwuklik(self, _event):
        wiersz = self.wiersz_zaznaczony()
        if wiersz is not None:
            self.on_dwuklik(wiersz)

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
