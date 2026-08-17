"""
Zakładka przeglądania → widok poprawek (0.1-alpha.3.2): filtrowanie
(kurier/zakres dat/tekst/bieżąca sesja), poprawka pojedynczego wiersza
(dwuklik → DialogEdycji) i operacje zbiorcze (ustaw jedno pole na
zaznaczonych, usuń zaznaczone). Cała logika w repo.py/dialog_edycji.py -
tu tylko zbieranie wartości z pól i wywołanie.
"""
import tkinter as tk
from tkinter import messagebox, ttk

from zpo_tracker import operacje, repo
from zpo_tracker.gui.dialog_edycji import DialogEdycji
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

# klucz -> tabela słownika, dla pól, które mają skończony zbiór wartości
# (data celowo poza tym słownikiem - wolny tekst, nie ma dictionary)
_TABELE_SLOWNIKOW_POLA = {"kurier": "kurierzy", "wykonawca": "wykonawcy", "rejon": "rejony"}
POLA_ZBIORCZE = [("kurier", "Kurier"), ("wykonawca", "Wykonawca"),
                  ("data", "Data"), ("rejon", "Rejon")]

LICZBA_PROBKI_USUWANIA = 3


class ZakladkaPrzeglad(ttk.Frame):
    def __init__(self, parent, conn, katalog_danych=None, sesja_uuid=None, on_zmieniono=None):
        super().__init__(parent)
        self.conn = conn
        self.katalog_danych = katalog_danych
        self.sesja_uuid = sesja_uuid
        self.on_zmieniono = on_zmieniono

        pasek_filtrow = ttk.Frame(self)
        pasek_filtrow.pack(fill="x", padx=6, pady=(6, 0))

        ttk.Label(pasek_filtrow, text="Kurier:").pack(side="left")
        self.var_kurier = tk.StringVar()
        ttk.Combobox(
            pasek_filtrow, textvariable=self.var_kurier, width=16,
            values=[w["nazwa"] for w in repo.pobierz_slownik(conn, "kurierzy")],
        ).pack(side="left", padx=(4, 10))

        ttk.Label(pasek_filtrow, text="Data od:").pack(side="left")
        self.var_data_od = tk.StringVar()
        ttk.Entry(pasek_filtrow, textvariable=self.var_data_od, width=11).pack(
            side="left", padx=(4, 10))

        ttk.Label(pasek_filtrow, text="do:").pack(side="left")
        self.var_data_do = tk.StringVar()
        ttk.Entry(pasek_filtrow, textvariable=self.var_data_do, width=11).pack(
            side="left", padx=(4, 10))

        ttk.Label(pasek_filtrow, text="Szukaj:").pack(side="left")
        self.var_tekst = tk.StringVar()
        ttk.Entry(pasek_filtrow, textvariable=self.var_tekst, width=18).pack(
            side="left", padx=(4, 10))

        self.var_tylko_sesja = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            pasek_filtrow, text="tylko bieżąca sesja", variable=self.var_tylko_sesja,
            command=self.odswiez,
        ).pack(side="left", padx=(0, 10))

        ttk.Button(pasek_filtrow, text="Filtruj", command=self.odswiez).pack(side="left")
        ttk.Button(pasek_filtrow, text="Wyczyść", command=self._wyczysc_filtry).pack(
            side="left", padx=(6, 0))

        pasek_akcji = ttk.Frame(self)
        pasek_akcji.pack(fill="x", padx=6, pady=6)
        ttk.Button(pasek_akcji, text="Odśwież", command=self.odswiez).pack(side="left")
        self.etykieta_liczby = ttk.Label(pasek_akcji, text="")
        self.etykieta_liczby.pack(side="left", padx=10)
        ttk.Button(
            pasek_akcji, text="Ustaw pole zaznaczonym…", command=self._ustaw_pole_zaznaczonym
        ).pack(side="right")
        ttk.Button(pasek_akcji, text="Usuń zaznaczone", command=self._usun_zaznaczone).pack(
            side="right", padx=(0, 6))

        self.tabela = Tabela(self, KOLUMNY, on_dwuklik=self._edytuj)
        self.tabela.pack(fill="both", expand=True, padx=6, pady=(0, 6))

        self.odswiez()

    def odswiez(self):
        filtry = {}
        if self.var_kurier.get().strip():
            filtry["kurier"] = self.var_kurier.get().strip()
        if self.var_data_od.get().strip():
            filtry["data_od"] = self.var_data_od.get().strip()
        if self.var_data_do.get().strip():
            filtry["data_do"] = self.var_data_do.get().strip()
        if self.var_tekst.get().strip():
            filtry["tekst"] = self.var_tekst.get().strip()
        if self.var_tylko_sesja.get() and self.sesja_uuid:
            filtry["sesja_uuid"] = self.sesja_uuid

        wiersze = repo.pobierz_transakcje(self.conn, limit=1000, **filtry)
        self.tabela.ustaw_dane(wiersze)
        self.etykieta_liczby.configure(text=f"{len(wiersze)} transakcji")

    def _wyczysc_filtry(self):
        self.var_kurier.set("")
        self.var_data_od.set("")
        self.var_data_do.set("")
        self.var_tekst.set("")
        self.var_tylko_sesja.set(False)
        self.odswiez()

    def _edytuj(self, wiersz):
        DialogEdycji(self, self.conn, self.katalog_danych, wiersz, on_zapisano=self._po_zmianie)

    def _po_zmianie(self):
        self.odswiez()
        if self.on_zmieniono:
            self.on_zmieniono()

    def _ustaw_pole_zaznaczonym(self):
        wiersze = self.tabela.wiersze_zaznaczone()
        if not wiersze:
            messagebox.showinfo("Ustaw pole", "Zaznacz co najmniej jeden wiersz.")
            return
        ids = [w["id"] for w in wiersze]
        _DialogUstawPoleZbiorczo(
            self, self.conn,
            on_zatwierdzono=lambda pole, wartosc: self._wykonaj_ustaw_pole(ids, pole, wartosc),
        )

    def _wykonaj_ustaw_pole(self, ids, pole, wartosc):
        try:
            operacje.wykonaj(
                self.conn, self.katalog_danych, rodzaj="edycja_zbiorcza",
                etykieta=f"{len(ids)} wierszy: {pole}",
                funkcja=repo.ustaw_pole_transakcji, args=(ids, pole, wartosc),
            )
        except repo.KolizjaTransakcji as e:
            messagebox.showerror("Nie udało się zmienić", str(e))
            return
        self._po_zmianie()

    def _usun_zaznaczone(self):
        wiersze = self.tabela.wiersze_zaznaczone()
        if not wiersze:
            messagebox.showinfo("Usuń", "Zaznacz co najmniej jeden wiersz.")
            return
        probka = "\n".join(
            f"• {w['data']} / {w['kurier']} / {w['nadawca']} ({w['adres']})"
            for w in wiersze[:LICZBA_PROBKI_USUWANIA]
        )
        if len(wiersze) > LICZBA_PROBKI_USUWANIA:
            probka += f"\n… i {len(wiersze) - LICZBA_PROBKI_USUWANIA} więcej"
        if not messagebox.askyesno(
            "Usuń zaznaczone",
            f"Usunąć {len(wiersze)} transakcji?\n\n{probka}\n\n"
            f"Tej operacji nie da się cofnąć inaczej niż przez zakładkę Historia.",
        ):
            return
        operacje.wykonaj(
            self.conn, self.katalog_danych, rodzaj="usuniecie_transakcji",
            etykieta=f"usunięto {len(wiersze)} wierszy",
            funkcja=repo.usun_transakcje, args=([w["id"] for w in wiersze],),
        )
        self._po_zmianie()


class _DialogUstawPoleZbiorczo(tk.Toplevel):
    """Wybór pola + wartości dla operacji zbiorczej. Wartość dla pól ze
    skończonym słownikiem (kurier/wykonawca/rejon) podpowiada się z
    dictionary; dla daty zostaje wolnym tekstem."""

    def __init__(self, parent, conn, on_zatwierdzono):
        super().__init__(parent)
        self.conn = conn
        self.on_zatwierdzono = on_zatwierdzono

        self.title("Ustaw pole na zaznaczonych")
        self.resizable(False, False)
        self.transient(parent)

        ramka = ttk.Frame(self, padding=14)
        ramka.pack(fill="both", expand=True)

        ttk.Label(ramka, text="Pole:").grid(row=0, column=0, sticky="w")
        self.var_pole = tk.StringVar(value=POLA_ZBIORCZE[0][0])
        combo_pole = ttk.Combobox(
            ramka, textvariable=self.var_pole, state="readonly", width=16,
            values=[klucz for klucz, _ in POLA_ZBIORCZE],
        )
        combo_pole.grid(row=0, column=1, sticky="w", padx=(8, 0), pady=3)
        combo_pole.bind("<<ComboboxSelected>>", lambda _e: self._na_zmiane_pola())

        ttk.Label(ramka, text="Wartość:").grid(row=1, column=0, sticky="w")
        self.var_wartosc = tk.StringVar()
        self.combo_wartosc = ttk.Combobox(ramka, textvariable=self.var_wartosc, width=26)
        self.combo_wartosc.grid(row=1, column=1, sticky="w", padx=(8, 0), pady=3)

        self.etykieta_status = ttk.Label(ramka, text="", foreground="red")
        self.etykieta_status.grid(row=2, column=0, columnspan=2, sticky="w", pady=(6, 0))

        przyciski = ttk.Frame(ramka)
        przyciski.grid(row=3, column=0, columnspan=2, sticky="e", pady=(10, 0))
        ttk.Button(przyciski, text="Zastosuj", command=self._zatwierdz).pack(side="right")
        ttk.Button(przyciski, text="Anuluj", command=self.destroy).pack(side="right", padx=(0, 6))

        self._na_zmiane_pola()

    def _na_zmiane_pola(self):
        tabela_slownika = _TABELE_SLOWNIKOW_POLA.get(self.var_pole.get())
        self.combo_wartosc.configure(
            values=([w["nazwa"] for w in repo.pobierz_slownik(self.conn, tabela_slownika)]
                    if tabela_slownika else []))

    def _zatwierdz(self):
        wartosc = self.var_wartosc.get().strip()
        if not wartosc:
            self.etykieta_status.configure(text="Podaj wartość.")
            return
        self.on_zatwierdzono(self.var_pole.get(), wartosc)
        self.destroy()
