"""
Zakładka wprowadzania - formularz wzorowany na papierowym blankiecie
(docs/ux-ui.md): KURIER + DATA + WYKONAWCA (dedukowany) w nagłówku, pod
spodem płaska lista wierszy punkt+ilość (0.1-alpha.3.1: bloki REJON+DATA
zniknęły - jeden blankiet to jeden kurier na jeden dzień, rejon zszedł do
wiersza i jest dedukowany z adresu). Nad formularzem panel podglądu bazy
(scroll + Ctrl+scroll zoom, patrz widget_tabela.Tabela).

Cała logika walidacji/budowania modeli jest w formularz_logika.py i
models.py, dedukcja pól w dedukcja.py - tu tylko zbieranie wartości z pól,
wywołanie dedukcji i wyświetlenie wyniku.
"""
from datetime import date
import tkinter as tk
from tkinter import ttk

from pydantic import ValidationError

from zpo_tracker import dedukcja, operacje, repo
from zpo_tracker.gui.formularz_logika import zbuduj_blankiet
from zpo_tracker.gui.widget_autocomplete import EntryZPodpowiedzia
from zpo_tracker.gui.widget_tabela import Tabela

KOLUMNY_PODGLADU = [
    ("data", "Data", 90),
    ("kurier", "Kurier", 150),
    ("nadawca", "Nadawca", 110),
    ("adres", "Adres", 200),
    ("rejon", "Rejon", 60),
    ("wykonawca", "Wykonawca", 90),
    ("ilosc_total", "Ilość", 55),
    ("ilosc_zpo", "w tym ZPO", 75),
]

_AKTYWNY = "normal"
_NIEAKTYWNY = "readonly"


def _podepnij_scroll_kolkiem(canvas):
    """Kółko myszy przewija obszar wierszy tylko, gdy kursor jest nad nim -
    Windows/Mac (<MouseWheel>) i Linux (<Button-4>/<Button-5>) osobno,
    bo wysyłają zupełnie inne zdarzenia."""
    canvas.bind_all("<MouseWheel>", lambda e: canvas.yview_scroll(-1 if e.delta > 0 else 1, "units"))
    canvas.bind_all("<Button-4>", lambda e: canvas.yview_scroll(-1, "units"))
    canvas.bind_all("<Button-5>", lambda e: canvas.yview_scroll(1, "units"))


def _odepnij_scroll_kolkiem(canvas):
    canvas.unbind_all("<MouseWheel>")
    canvas.unbind_all("<Button-4>")
    canvas.unbind_all("<Button-5>")


def _ustaw_stan(widget, aktywne):
    stan = _AKTYWNY if aktywne else _NIEAKTYWNY
    if hasattr(widget, "ustaw_stan"):
        widget.ustaw_stan(stan)  # EntryZPodpowiedzia - patrz widget_autocomplete.py
    else:
        widget.configure(state=stan)


class WierszWidget(ttk.Frame):
    """
    Jeden wiersz: rejon + punkt (nadawca + adres, opcjonalnie PNI) + ilość.
    Rejon/nadawca/PNI dedukowane z adresu (0.1-alpha.3.1, patrz dedukcja.py)
    - ta klasa tylko zbiera wartości i aplikuje wynik dedukcji, nie decyduje.
    """

    def __init__(self, parent, on_usun, pobierz_nadawcow, pobierz_adresy, on_adres_lub_nadawca):
        super().__init__(parent)
        self.on_adres_lub_nadawca = on_adres_lub_nadawca
        self._ustawiam_programowo = False
        self._ilosc_zpo_aktywne = False

        self.var_rejon = tk.StringVar()
        self.var_nadawca = tk.StringVar()
        self.var_adres = tk.StringVar()
        self.var_pni = tk.StringVar()
        self.var_ilosc_total = tk.StringVar()
        self.var_ilosc_zpo = tk.StringVar()

        self.entry_rejon = ttk.Entry(self, textvariable=self.var_rejon, width=8)
        self.entry_rejon.grid(row=0, column=0, padx=2)
        self.entry_nadawca = EntryZPodpowiedzia(
            self, pobierz_nadawcow, textvariable=self.var_nadawca, width=16)
        self.entry_nadawca.grid(row=0, column=1, padx=2)
        self.entry_adres = EntryZPodpowiedzia(
            self, pobierz_adresy, textvariable=self.var_adres, width=26)
        self.entry_adres.grid(row=0, column=2, padx=2)
        self.entry_pni = ttk.Entry(self, textvariable=self.var_pni, width=10)
        self.entry_pni.grid(row=0, column=3, padx=2)
        self.entry_ilosc_total = ttk.Entry(self, textvariable=self.var_ilosc_total, width=6)
        self.entry_ilosc_total.grid(row=0, column=4, padx=2)
        self.entry_ilosc_zpo = ttk.Entry(self, textvariable=self.var_ilosc_zpo, width=6)
        self.entry_ilosc_zpo.grid(row=0, column=5, padx=2)
        ttk.Button(self, text="✕", width=2, command=lambda: on_usun(self)).grid(row=0, column=6, padx=2)

        self.var_adres.trace_add("write", self._na_zmiane)
        self.var_nadawca.trace_add("write", self._na_zmiane)
        # autouzupełnienie "w tym ZPO" z "Ilość" - JEDNOKIERUNKOWE, osobne
        # od dedukcji (Ilość nigdy nie jest źródłem ani bramą dedukcji
        # innych pól, patrz dedukcja.py); bramowane wynikiem OSTATNIEJ
        # dedukcji (_ilosc_zpo_aktywne), nie ręcznie wpisanym PNI
        self.var_ilosc_total.trace_add("write", self._uzupelnij_ilosc_zpo)

    def _na_zmiane(self, *_):
        if self._ustawiam_programowo:
            return
        self.on_adres_lub_nadawca(self)

    def _uzupelnij_ilosc_zpo(self, *_):
        if self._ustawiam_programowo:
            return
        if self._ilosc_zpo_aktywne and not self.var_ilosc_zpo.get().strip():
            self.var_ilosc_zpo.set(self.var_ilosc_total.get())

    def zastosuj_dedukcje(self, wynik):
        """wynik: dedukcja.WynikWiersza. Wypełnia pola dedukowane
        jednoznacznie, przełącza aktywność pozostałych (kolor wskaźnika
        dochodzi w kolejnym kroku - widget_pole.py, 0.1-alpha.3.1 c.d.)."""
        self._ustawiam_programowo = True
        try:
            for klucz, var, widget in (
                ("rejon", self.var_rejon, self.entry_rejon),
                ("nadawca", self.var_nadawca, self.entry_nadawca),
                ("pni_zpo", self.var_pni, self.entry_pni),
            ):
                stan = wynik.pola[klucz]
                if stan.wartosc is not None:
                    var.set(stan.wartosc)
                _ustaw_stan(widget, stan.aktywne)

            stan_zpo = wynik.pola["ilosc_zpo"]
            self._ilosc_zpo_aktywne = stan_zpo.aktywne
            _ustaw_stan(self.entry_ilosc_zpo, stan_zpo.aktywne)
            if stan_zpo.wartosc is not None and not self.var_ilosc_zpo.get().strip():
                self.var_ilosc_zpo.set(str(stan_zpo.wartosc))
        finally:
            self._ustawiam_programowo = False

    def pobierz_surowe(self):
        return {
            "nadawca": self.var_nadawca.get(),
            "adres": self.var_adres.get(),
            "pni_zpo": self.var_pni.get().strip() or None,
            "rejon": self.var_rejon.get().strip() or None,
            "ilosc_total": self.var_ilosc_total.get().strip() or None,
            "ilosc_zpo": self.var_ilosc_zpo.get().strip() or None,
        }


class ZakladkaWprowadzanie(ttk.Frame):
    def __init__(self, parent, conn, katalog_danych, on_zapisano=None):
        super().__init__(parent)
        self.conn = conn
        self.katalog_danych = katalog_danych
        self.on_zapisano = on_zapisano
        self.wiersze = []
        self._ustawiam_programowo = False

        panel = ttk.PanedWindow(self, orient="vertical")
        panel.pack(fill="both", expand=True)

        gora = ttk.Frame(panel)
        ttk.Label(gora, text="Podgląd bazy (scroll / Ctrl+scroll = powiększenie):").pack(
            anchor="w", padx=6, pady=(4, 0)
        )
        self.podglad = Tabela(gora, KOLUMNY_PODGLADU)
        self.podglad.pack(fill="both", expand=True, padx=6, pady=6)
        panel.add(gora, weight=1)

        dol = ttk.Frame(panel)
        panel.add(dol, weight=2)

        naglowek = ttk.Frame(dol)
        naglowek.pack(fill="x", padx=6, pady=6)
        ttk.Label(naglowek, text="KURIER:", font=("TkDefaultFont", 12, "bold")).pack(side="left")
        self.var_kurier = tk.StringVar()
        EntryZPodpowiedzia(
            naglowek, self._pobierz_kurierow, textvariable=self.var_kurier,
            width=30, font=("TkDefaultFont", 12),
        ).pack(side="left", padx=8)
        ttk.Label(naglowek, text="Data:").pack(side="left", padx=(16, 0))
        self.var_data = tk.StringVar(value=date.today().isoformat())
        ttk.Entry(naglowek, textvariable=self.var_data, width=12).pack(side="left", padx=4)
        ttk.Label(naglowek, text="Wykonawca:").pack(side="left", padx=(16, 0))
        self.var_wykonawca = tk.StringVar()
        self.entry_wykonawca = ttk.Entry(naglowek, textvariable=self.var_wykonawca, width=16)
        self.entry_wykonawca.pack(side="left", padx=4)

        naglowek_kolumn = ttk.Frame(dol)
        naglowek_kolumn.pack(fill="x", padx=6)
        for tekst, w in [("Rejon", 8), ("Nadawca", 16), ("Adres", 26), ("PNI ZPO", 10),
                          ("Ilość", 6), ("w tym ZPO", 6)]:
            ttk.Label(naglowek_kolumn, text=tekst, width=w, anchor="w").pack(side="left", padx=2)

        # wiersze mogą urosnąć poza widoczny obszar okna (GH #3) - bez tego
        # użytkownik nie miał jak dodać kolejnego wiersza, gdy poprzednie
        # już wypełniły ekran
        obszar_wierszy = ttk.Frame(dol)
        obszar_wierszy.pack(fill="both", expand=True, padx=6)
        canvas_wierszy = tk.Canvas(obszar_wierszy, highlightthickness=0)
        pasek_scroll = ttk.Scrollbar(obszar_wierszy, orient="vertical", command=canvas_wierszy.yview)
        canvas_wierszy.configure(yscrollcommand=pasek_scroll.set)
        canvas_wierszy.pack(side="left", fill="both", expand=True)
        pasek_scroll.pack(side="right", fill="y")

        self.ramka_wierszy = ttk.Frame(canvas_wierszy)
        okno_id = canvas_wierszy.create_window((0, 0), window=self.ramka_wierszy, anchor="nw")
        self.ramka_wierszy.bind(
            "<Configure>", lambda e: canvas_wierszy.configure(scrollregion=canvas_wierszy.bbox("all"))
        )
        canvas_wierszy.bind(
            "<Configure>", lambda e: canvas_wierszy.itemconfig(okno_id, width=e.width)
        )
        canvas_wierszy.bind("<Enter>", lambda e: _podepnij_scroll_kolkiem(canvas_wierszy))
        canvas_wierszy.bind("<Leave>", lambda e: _odepnij_scroll_kolkiem(canvas_wierszy))

        pasek_akcji = ttk.Frame(dol)
        pasek_akcji.pack(fill="x", padx=6, pady=6)
        ttk.Button(pasek_akcji, text="+ wiersz", command=self.dodaj_wiersz).pack(side="left")
        ttk.Button(pasek_akcji, text="ZAPISZ", command=self.zapisz).pack(side="left", padx=8)
        self.etykieta_status = ttk.Label(pasek_akcji, text="")
        self.etykieta_status.pack(side="left", padx=8)

        self.var_kurier.trace_add("write", self._na_zmiane_naglowka)
        self.var_data.trace_add("write", self._na_zmiane_naglowka)

        self.dodaj_wiersz()
        self.dodaj_wiersz()
        self.odswiez_podglad()

    def _pobierz_kurierow(self):
        return [w["nazwa"] for w in repo.pobierz_slownik(self.conn, "kurierzy")]

    def _pobierz_nadawcow(self):
        return repo.pobierz_unikalne_nadawcow(self.conn)

    def _pobierz_adresy(self):
        return repo.pobierz_unikalne_adresy(self.conn)

    def dodaj_wiersz(self):
        wiersz = WierszWidget(
            self.ramka_wierszy, self._usun_wiersz, self._pobierz_nadawcow,
            self._pobierz_adresy, self._na_zmiane_wiersza,
        )
        wiersz.pack(fill="x", pady=1)
        self.wiersze.append(wiersz)

    def _usun_wiersz(self, wiersz):
        if len(self.wiersze) <= 1:
            return  # zawsze zostaje co najmniej jeden wiersz do wypełnienia
        wiersz.destroy()
        self.wiersze.remove(wiersz)

    def _na_zmiane_naglowka(self, *_):
        if self._ustawiam_programowo:
            return
        kurier = self.var_kurier.get().strip()
        if not kurier:
            return
        pola = dedukcja.dedukuj_naglowek(self.conn, kurier=kurier, data=self.var_data.get().strip())
        stan = pola["wykonawca"]
        self._ustawiam_programowo = True
        try:
            if stan.wartosc is not None:
                self.var_wykonawca.set(stan.wartosc)
            _ustaw_stan(self.entry_wykonawca, stan.aktywne)
        finally:
            self._ustawiam_programowo = False

    def _na_zmiane_wiersza(self, wiersz):
        kurier = self.var_kurier.get().strip()
        adres = wiersz.var_adres.get().strip()
        nadawca = wiersz.var_nadawca.get().strip() or None
        wynik = dedukcja.dedukuj_wiersz(self.conn, kurier=kurier, adres=adres, nadawca=nadawca)
        wiersz.zastosuj_dedukcje(wynik)

    def odswiez_podglad(self):
        self.podglad.ustaw_dane(repo.pobierz_transakcje(self.conn, limit=500))

    def zapisz(self):
        dane_wierszy = [w.pobierz_surowe() for w in self.wiersze]
        try:
            blankiet = zbuduj_blankiet(
                self.var_kurier.get(), self.var_data.get().strip(),
                self.var_wykonawca.get().strip() or None, dane_wierszy,
            )
        except ValidationError as e:
            self.etykieta_status.configure(text=f"Błąd: {_pierwszy_blad(e)}", foreground="red")
            return

        if blankiet is None:
            self.etykieta_status.configure(text="Brak wypełnionych wierszy do zapisania.", foreground="red")
            return

        wyniki = operacje.wykonaj(
            self.conn, self.katalog_danych, rodzaj="zapis_blankietu",
            etykieta=f"{self.var_kurier.get().strip()}, {len(blankiet.wiersze)} wiersz(y)",
            funkcja=repo.zapisz_blankiet,
            args=(blankiet,), kwargs={"autor_id": getattr(self, "autor_id", None)},
            licz_wiersze=operacje.licz_zapisane_wiersze,
        )
        ostrzezenia, pominiete = [], 0
        for wynik in wyniki:
            if wynik["pominieto"]:
                pominiete += 1
            ostrzezenia.extend(wynik["ostrzezenia"])

        data_zachowana = self.var_data.get()
        for wiersz_widget in list(self.wiersze):
            wiersz_widget.destroy()
        self.wiersze.clear()
        self.var_kurier.set("")
        self.var_wykonawca.set("")
        self.var_data.set(data_zachowana)
        self.dodaj_wiersz()
        self.dodaj_wiersz()

        tekst = f"Zapisano {len(blankiet.wiersze) - pominiete} wierszy."
        if pominiete:
            tekst += f" Pominięto {pominiete} (duplikat)."
        if ostrzezenia:
            tekst += f" Ostrzeżeń: {len(ostrzezenia)}."
        self.etykieta_status.configure(text=tekst, foreground="black")

        self.odswiez_podglad()
        if self.on_zapisano:
            self.on_zapisano()


def _pierwszy_blad(wyjatek: ValidationError) -> str:
    blad = wyjatek.errors()[0]
    pole = ".".join(str(p) for p in blad["loc"])
    return f"{pole}: {blad['msg']}"
