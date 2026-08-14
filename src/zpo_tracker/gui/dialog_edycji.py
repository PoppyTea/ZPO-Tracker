"""
Poprawka jednej zapisanej transakcji (0.1-alpha.3.2, widok poprawek w
zakladka_przeglad.py). ŚWIADOMIE bez maszynerii dedukcji
(dedukcja.py/widget_pole.PoleZeWskaznikiem) - korekta to jawna, świadoma
decyzja człowieka nad JUŻ zapisanym wierszem, nie ponowne wypełnianie
formularza. Nadawca/adres/PNI są NIEedytowalne (patrz
repo.KOLUMNY_EDYTOWALNE_TRANSAKCJI) - zmiana punktu to inna klasa ryzyka
(cicha zmiana historii punktu) niż poprawka daty/kuriera/ilości/rejonu;
korekta punktu w tym wydaniu to usuń wiersz + wpisz ponownie w formularzu,
z pełną dedukcją (docs/roadmap.md).
"""
import tkinter as tk
from tkinter import ttk

from zpo_tracker import operacje, repo


def _sparsuj_ilosc(tekst, wymagane):
    """int/None, albo rzuca ValueError przy pustym-gdy-wymagane/nie-liczbie/ujemnej."""
    tekst = tekst.strip()
    if not tekst:
        if wymagane:
            raise ValueError("pole wymagane")
        return None
    wartosc = int(tekst)  # rzuca ValueError samo, jeśli to nie liczba całkowita
    if wartosc < 0:
        raise ValueError("wartość ujemna")
    return wartosc


class DialogEdycji(tk.Toplevel):
    def __init__(self, parent, conn, katalog_danych, wiersz, on_zapisano=None):
        super().__init__(parent)
        self.conn = conn
        self.katalog_danych = katalog_danych
        self.wiersz = wiersz
        self.on_zapisano = on_zapisano

        self.title(f"Popraw transakcję #{wiersz['id']}")
        self.resizable(False, False)
        self.transient(parent)

        ramka = ttk.Frame(self, padding=14)
        ramka.pack(fill="both", expand=True)

        ttk.Label(
            ramka, text=f"{wiersz['nadawca']} ({wiersz['adres']})",
            foreground="#666",
        ).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 10))

        self.var_data = tk.StringVar(value=wiersz.get("data") or "")
        self.var_kurier = tk.StringVar(value=wiersz.get("kurier") or "")
        self.var_wykonawca = tk.StringVar(value=wiersz.get("wykonawca") or "")
        self.var_rejon = tk.StringVar(value=wiersz.get("rejon") or "")
        self.var_ilosc_total = tk.StringVar(
            value="" if wiersz.get("ilosc_total") is None else str(wiersz["ilosc_total"]))
        self.var_ilosc_zpo = tk.StringVar(
            value="" if wiersz.get("ilosc_zpo") is None else str(wiersz["ilosc_zpo"]))

        ttk.Label(ramka, text="Data (RRRR-MM-DD):").grid(row=1, column=0, sticky="w")
        ttk.Entry(ramka, textvariable=self.var_data, width=14).grid(
            row=1, column=1, sticky="w", padx=(8, 0), pady=3)

        ttk.Label(ramka, text="Kurier:").grid(row=2, column=0, sticky="w")
        ttk.Combobox(
            ramka, textvariable=self.var_kurier, width=26,
            values=[w["nazwa"] for w in repo.pobierz_slownik(conn, "kurierzy")],
        ).grid(row=2, column=1, sticky="w", padx=(8, 0), pady=3)

        ttk.Label(ramka, text="Wykonawca:").grid(row=3, column=0, sticky="w")
        ttk.Combobox(
            ramka, textvariable=self.var_wykonawca, width=26,
            values=[w["nazwa"] for w in repo.pobierz_slownik(conn, "wykonawcy")],
        ).grid(row=3, column=1, sticky="w", padx=(8, 0), pady=3)

        ttk.Label(ramka, text="Rejon:").grid(row=4, column=0, sticky="w")
        ttk.Combobox(
            ramka, textvariable=self.var_rejon, width=26,
            values=[w["nazwa"] for w in repo.pobierz_slownik(conn, "rejony")],
        ).grid(row=4, column=1, sticky="w", padx=(8, 0), pady=3)

        ttk.Label(ramka, text="Ilość:").grid(row=5, column=0, sticky="w")
        ttk.Entry(ramka, textvariable=self.var_ilosc_total, width=8).grid(
            row=5, column=1, sticky="w", padx=(8, 0), pady=3)

        ttk.Label(ramka, text="w tym ZPO:").grid(row=6, column=0, sticky="w")
        ttk.Entry(ramka, textvariable=self.var_ilosc_zpo, width=8).grid(
            row=6, column=1, sticky="w", padx=(8, 0), pady=3)

        self.etykieta_status = ttk.Label(
            ramka, text="", foreground="red", wraplength=340, justify="left")
        self.etykieta_status.grid(row=7, column=0, columnspan=2, sticky="w", pady=(8, 0))

        przyciski = ttk.Frame(ramka)
        przyciski.grid(row=8, column=0, columnspan=2, sticky="e", pady=(12, 0))
        ttk.Button(przyciski, text="Zapisz", command=self._zatwierdz).pack(side="right")
        ttk.Button(przyciski, text="Anuluj", command=self.destroy).pack(
            side="right", padx=(0, 6))

    def _zatwierdz(self):
        data = self.var_data.get().strip()
        kurier = self.var_kurier.get().strip()
        if not data:
            self.etykieta_status.configure(text="Podaj datę.")
            return
        if not kurier:
            self.etykieta_status.configure(text="Podaj kuriera.")
            return
        try:
            ilosc_total = _sparsuj_ilosc(self.var_ilosc_total.get(), wymagane=True)
            ilosc_zpo = _sparsuj_ilosc(self.var_ilosc_zpo.get(), wymagane=False)
        except ValueError:
            self.etykieta_status.configure(
                text="Ilość musi być liczbą całkowitą nieujemną "
                     "(„w tym ZPO” może zostać puste).")
            return

        zmiany = {
            "data": data, "kurier": kurier,
            "wykonawca": self.var_wykonawca.get().strip() or None,
            "rejon": self.var_rejon.get().strip() or None,
            "ilosc_total": ilosc_total, "ilosc_zpo": ilosc_zpo,
        }
        try:
            operacje.wykonaj(
                self.conn, self.katalog_danych, rodzaj="edycja_transakcji",
                etykieta=f"transakcja #{self.wiersz['id']}",
                funkcja=repo.zaktualizuj_transakcje,
                args=(self.wiersz["id"], zmiany),
            )
        except repo.KolizjaTransakcji as e:
            self.etykieta_status.configure(text=str(e))
            return

        if self.on_zapisano:
            self.on_zapisano()
        self.destroy()
