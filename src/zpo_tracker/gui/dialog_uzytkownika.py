"""
Popup przy pierwszym uruchomieniu: kto siedzi przy tej stacji.

Zero logiki biznesowej - walidacja formatu i kontrola krzyżowa siedzą
w `uzytkownicy.py`, tutaj tylko zebranie wartości i pokazanie wyniku.

Ostrzeżenia o niezgodności numeru kadrowego są MIĘKKIE: pokazujemy je
i pozwalamy zapisać (docs/ux-ui.md). Twardo blokowany jest tylko format,
bo zły format to zawsze pomyłka, nigdy świadoma decyzja.
"""
import tkinter as tk
from tkinter import ttk

from zpo_tracker import uzytkownicy


class DialogUzytkownika(tk.Toplevel):
    def __init__(self, parent, conn, login, on_gotowe=None):
        super().__init__(parent)
        self.conn = conn
        self.login = login
        self.on_gotowe = on_gotowe
        self.wynik_id = None

        self.title("Kto wprowadza dane?")
        self.resizable(False, False)
        self.transient(parent)

        istniejacy = uzytkownicy.pobierz_uzytkownika(conn, login)
        self.var_alias = tk.StringVar(
            value=(istniejacy["alias"] if istniejacy else "") or "")
        self.var_nr = tk.StringVar(
            value=(istniejacy["nr_kadrowy"] if istniejacy else "") or "")

        ramka = ttk.Frame(self, padding=14)
        ramka.pack(fill="both", expand=True)

        ttk.Label(
            ramka,
            text="Twoje dane zostaną zapisane przy każdym wpisie, żeby było\n"
                 "wiadomo, kogo zapytać, gdy coś się nie zgadza.",
            justify="left",
        ).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 10))

        ttk.Label(ramka, text="Imię i nazwisko:").grid(row=1, column=0, sticky="w")
        self.pole_alias = ttk.Entry(ramka, textvariable=self.var_alias, width=32)
        self.pole_alias.grid(row=1, column=1, sticky="w", padx=(8, 0), pady=3)

        ttk.Label(ramka, text="Numer kadrowy:").grid(row=2, column=0, sticky="w")
        ttk.Entry(ramka, textvariable=self.var_nr, width=12).grid(
            row=2, column=1, sticky="w", padx=(8, 0), pady=3)
        ttk.Label(
            ramka,
            text="(opcjonalnie - 5 znaków, litery i cyfry, wielkość liter ma "
                 "znaczenie, jeśli już go masz)",
            foreground="#666",
        ).grid(row=3, column=1, sticky="w", padx=(8, 0))

        ttk.Label(ramka, text=f"Konto Windows: {login}", foreground="#666").grid(
            row=4, column=0, columnspan=2, sticky="w", pady=(8, 0))

        self.etykieta_status = ttk.Label(ramka, text="", foreground="red",
                                         wraplength=380, justify="left")
        self.etykieta_status.grid(row=5, column=0, columnspan=2, sticky="w",
                                  pady=(8, 0))

        przyciski = ttk.Frame(ramka)
        przyciski.grid(row=6, column=0, columnspan=2, sticky="e", pady=(12, 0))
        ttk.Button(przyciski, text="Zapisz", command=self._zatwierdz).pack(side="right")
        ttk.Button(przyciski, text="Później", command=self.destroy).pack(
            side="right", padx=(0, 6))

        self.pole_alias.focus_set()
        self.bind("<Return>", lambda _: self._zatwierdz())

    def _zatwierdz(self):
        alias = self.var_alias.get().strip()
        nr = self.var_nr.get().strip() or None  # "" -> None: CHECK w bazie
        # dopuszcza NULL, nie pusty string (0.1-alpha.3.2: nr kadrowy
        # przestał być wymagany, patrz uzytkownicy.wymaga_uzupelnienia)

        if not alias:
            self.etykieta_status.configure(text="Podaj imię i nazwisko.")
            return
        if nr is not None and not uzytkownicy.poprawny_nr_kadrowy(nr):
            self.etykieta_status.configure(
                text="Jeśli podajesz numer kadrowy, musi mieć dokładnie "
                     "5 znaków (litery i cyfry, bez spacji i myślników). "
                     "Możesz też zostawić to pole puste.")
            return

        # miękkie ostrzeżenie: pokazujemy raz, drugie kliknięcie zapisuje
        ostrzezenia = uzytkownicy.ostrzezenia_tozsamosci(self.conn, self.login, nr)
        if ostrzezenia and not getattr(self, "_ostrzezono", False):
            self._ostrzezono = True
            self.etykieta_status.configure(
                text=" ".join(ostrzezenia) + "\nKliknij „Zapisz” ponownie, "
                     "jeśli mimo to chcesz zapisać.",
                foreground="#b35c00")
            return

        self.wynik_id = uzytkownicy.zapewnij_uzytkownika(
            self.conn, login=self.login, alias=alias, nr_kadrowy=nr)
        if self.on_gotowe:
            self.on_gotowe(self.wynik_id)
        self.destroy()


class DialogWyboruUzytkownika(tk.Toplevel):
    """
    "Kto teraz pracuje?" - wybór osoby na WSPÓŁDZIELONYM koncie Windows
    (0.1-alpha.3.2). Listuje konto bazowe i wszystkie jego warianty
    rozszerzone (`uzytkownicy.znajdz_konta_dla_loginu`) + pozwala dodać
    nową osobę (`uzytkownicy.login_rozszerzony`). Używane zarówno przez
    "Zmień użytkownika…" jak i "Wyloguj" (patrz gui/app.py) - to ten sam
    wybór, różni się tylko tym, co dzieje się PRZED otwarciem tego okna.
    """

    def __init__(self, parent, conn, login_bazowy, on_wybrano):
        super().__init__(parent)
        self.conn = conn
        self.login_bazowy = login_bazowy
        self.on_wybrano = on_wybrano
        self.konta = uzytkownicy.znajdz_konta_dla_loginu(conn, login_bazowy)

        self.title("Kto teraz pracuje?")
        self.resizable(False, False)
        self.transient(parent)

        ramka = ttk.Frame(self, padding=14)
        ramka.pack(fill="both", expand=True)

        ttk.Label(
            ramka, text="Wybierz, kto teraz wprowadza dane na tej stacji:",
        ).pack(anchor="w", pady=(0, 8))

        for konto in self.konta:
            ttk.Button(
                ramka, text=konto["alias"] or konto["login"],
                command=lambda login=konto["login"]: self._wybierz(login),
            ).pack(fill="x", pady=2)

        ttk.Separator(ramka).pack(fill="x", pady=8)

        ramka_nowy = ttk.Frame(ramka)
        ramka_nowy.pack(fill="x")
        ttk.Label(ramka_nowy, text="Ktoś nowy:").pack(side="left")
        self.var_nazwa = tk.StringVar()
        ttk.Entry(ramka_nowy, textvariable=self.var_nazwa, width=22).pack(
            side="left", padx=6)
        ttk.Button(ramka_nowy, text="Dodaj", command=self._dodaj_nowego).pack(
            side="left")

        self.etykieta_status = ttk.Label(
            ramka, text="", foreground="red", wraplength=320, justify="left")
        self.etykieta_status.pack(anchor="w", pady=(8, 0))

    def _wybierz(self, login):
        self.on_wybrano(login)
        self.destroy()

    def _dodaj_nowego(self):
        nazwa = self.var_nazwa.get().strip()
        if not nazwa:
            self.etykieta_status.configure(text="Podaj imię i nazwisko.")
            return
        nowy_login = uzytkownicy.login_rozszerzony(self.login_bazowy, nazwa)
        # alias ustawiony od razu z nazwy podanej tutaj - bez tego kroku
        # dalej trzeba by pytać o alias osobnym dialogiem (DialogUzytkownika)
        uzytkownicy.zapewnij_uzytkownika(self.conn, login=nowy_login, alias=nazwa)
        self._wybierz(nowy_login)
