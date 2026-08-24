"""
Zakładka wprowadzania - formularz wzorowany na papierowym blankiecie
(docs/ux-ui.md): KURIER + DATA + WYKONAWCA (dedukowany) w nagłówku, pod
spodem płaska lista wierszy punkt+ilość (0.1-alpha.3.1: bloki REJON+DATA
zniknęły - jeden blankiet to jeden kurier na jeden dzień, rejon zszedł do
wiersza i jest dedukowany z adresu). Nad formularzem panel podglądu bazy
(scroll + Ctrl+scroll zoom, patrz widget_tabela.Tabela).

Cała logika walidacji/budowania modeli jest w formularz_logika.py i
models.py, dedukcja pól w dedukcja.py (w tym kolejność nawigacji -
`kolejnosc_pol`/`przesun_w_kolejnosci`) - tu tylko zbieranie wartości z
pól, wywołanie dedukcji i wyświetlenie wyniku/nawigacja klawiaturą.

Nawigacja (0.1-alpha.3.1): Tab I Enter są równoważne, wiodą przez
`dedukcja.kolejnosc_pol` (nie przez naturalny porządek widgetów w
gridzie - pole niejednoznaczne może aktywować się "za" polem, na którym
użytkownik już jest, więc naturalny Tab by go nie znalazł), Shift-Tab i
ISO_Left_Tab (X11) cofają. Nagłówek kolumn (Rejon/Nadawca/.../w tym ZPO)
jest wierszem 0 TEJ SAMEJ siatki co dane - jeden wspólny grid master sam
wyrównuje szerokość kolumny do najszerszej komórki, więc rozjazd
nagłówka z danymi jest konstrukcyjnie niemożliwy (dwa osobne kontenery,
jak poprzednio, tej gwarancji nie dawały).
"""
from datetime import date
import tkinter as tk
from tkinter import ttk

from pydantic import ValidationError

from zpo_tracker import dedukcja, operacje, repo
from zpo_tracker.gui.dialog_edycji import DialogEdycji
from zpo_tracker.gui.formularz_logika import wiersz_pusty, zbuduj_blankiet
from zpo_tracker.gui.widget_autocomplete import EntryZPodpowiedzia
from zpo_tracker.gui.widget_pole import KOLORY, PoleZeWskaznikiem
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

# kolejność kolumn w siatce wierszy - Rejon/Nadawca/Adres/PNI/Ilość/w tym ZPO
NAZWA_KOLUMNY = {"rejon": 0, "nadawca": 1, "adres": 2, "pni_zpo": 3,
                 "ilosc_total": 4, "ilosc_zpo": 5}


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


def _widget_ogniskowalny(pole):
    """EntryZPodpowiedzia jest ttk.Frame'em - fokus/bindowania muszą iść
    na jego wewnętrzny .entry, nie na wrapper."""
    w = pole.widget_pola
    return w.entry if hasattr(w, "entry") else w


class WierszWidget:
    """
    Jeden wiersz danych: rejon + punkt (nadawca+adres, opcjonalnie PNI) +
    ilość. NIE jest Frame'em - komórki (PoleZeWskaznikiem) wchodzą
    bezpośrednio do wspólnej siatki z nagłówkiem kolumn (patrz docstring
    modułu), `grid(wiersz)` tylko pozycjonuje je we właściwym rzędzie.

    Rejon/nadawca/PNI/wartość "w tym ZPO" dedukowane z adresu (dedukcja.py)
    - ta klasa tylko zbiera wartości i aplikuje wynik dedukcji/nawigacji,
    nie decyduje o żadnym z nich.
    """

    def __init__(self, siatka, on_usun, pobierz_nadawcow, pobierz_adresy,
                 on_zmiana, idz_dalej, idz_wstecz):
        self.on_zmiana = on_zmiana
        self._pobierz_nadawcow = pobierz_nadawcow
        self._ustawiam_programowo = False
        self._ilosc_zpo_aktywne = False
        self.ostatni_wynik = None  # dedukcja.WynikWiersza - potrzebne kolejnosc_pol

        self.var_rejon = tk.StringVar()
        self.var_nadawca = tk.StringVar()
        self.var_adres = tk.StringVar()
        self.var_pni = tk.StringVar()
        self.var_ilosc_total = tk.StringVar()
        self.var_ilosc_zpo = tk.StringVar()

        self.pole_rejon = PoleZeWskaznikiem(siatka, lambda p: EntryZPodpowiedzia(
            p, lambda: [], textvariable=self.var_rejon, width=8,
            on_dalej=lambda: idz_dalej(self, "rejon"), rozwijaj_na_pusty_fokus=True))
        self.pole_nadawca = PoleZeWskaznikiem(siatka, lambda p: EntryZPodpowiedzia(
            p, pobierz_nadawcow, textvariable=self.var_nadawca, width=16,
            on_dalej=lambda: idz_dalej(self, "nadawca"), rozwijaj_na_pusty_fokus=True))
        self.pole_adres = PoleZeWskaznikiem(siatka, lambda p: EntryZPodpowiedzia(
            p, pobierz_adresy, textvariable=self.var_adres, width=26,
            on_dalej=lambda: idz_dalej(self, "adres")))
        self.pole_pni = PoleZeWskaznikiem(
            siatka, lambda p: ttk.Entry(p, textvariable=self.var_pni, width=10))
        self.pole_ilosc_total = PoleZeWskaznikiem(
            siatka, lambda p: ttk.Entry(p, textvariable=self.var_ilosc_total, width=6))
        self.pole_ilosc_zpo = PoleZeWskaznikiem(
            siatka, lambda p: ttk.Entry(p, textvariable=self.var_ilosc_zpo, width=6))
        self.przycisk_usun = ttk.Button(
            siatka, text="✕", width=2, takefocus=0, command=lambda: on_usun(self))

        self._pola = {
            "rejon": self.pole_rejon, "nadawca": self.pole_nadawca,
            "adres": self.pole_adres, "pni_zpo": self.pole_pni,
            "ilosc_total": self.pole_ilosc_total, "ilosc_zpo": self.pole_ilosc_zpo,
        }
        self.pole_adres.ustaw_aktywnosc(True)        # pole główne - zawsze edytowalne
        self.pole_ilosc_total.ustaw_aktywnosc(True)  # pole główne - zawsze edytowalne

        # rejon/nadawca/adres to EntryZPodpowiedzia - Tab/Return idą przez
        # on_dalej (patrz konstruktory wyżej); reszta to zwykłe Entry,
        # trzeba spiąć ręcznie
        for nazwa in ("pni_zpo", "ilosc_total", "ilosc_zpo"):
            entry = self._pola[nazwa].widget_pola
            entry.bind("<Tab>", lambda e, n=nazwa: (idz_dalej(self, n), "break")[1])
            entry.bind("<Return>", lambda e, n=nazwa: (idz_dalej(self, n), "break")[1])
        # Shift-Tab/ISO_Left_Tab (X11) - EntryZPodpowiedzia ich nie obsługuje
        # wcale, więc zewnętrzne bindowanie nie koliduje z niczym
        for nazwa in self._pola:
            entry = _widget_ogniskowalny(self._pola[nazwa])
            entry.bind("<Shift-Tab>", lambda e, n=nazwa: (idz_wstecz(self, n), "break")[1])
            entry.bind("<ISO_Left_Tab>", lambda e, n=nazwa: (idz_wstecz(self, n), "break")[1])

        self.var_adres.trace_add("write", self._na_zmiane)
        self.var_nadawca.trace_add("write", self._na_zmiane)
        # autouzupełnienie "w tym ZPO" z "Ilość" - JEDNOKIERUNKOWE, osobne
        # od dedukcji (Ilość nigdy nie jest źródłem ani bramą dedukcji
        # innych pól, patrz dedukcja.py); bramowane wynikiem OSTATNIEJ
        # dedukcji (_ilosc_zpo_aktywne), nie ręcznie wpisanym PNI
        self.var_ilosc_total.trace_add("write", self._uzupelnij_ilosc_zpo)

    def grid(self, wiersz):
        self.pole_rejon.grid(row=wiersz, column=0, padx=2, pady=1, sticky="ew")
        self.pole_nadawca.grid(row=wiersz, column=1, padx=2, pady=1, sticky="ew")
        self.pole_adres.grid(row=wiersz, column=2, padx=2, pady=1, sticky="ew")
        self.pole_pni.grid(row=wiersz, column=3, padx=2, pady=1, sticky="ew")
        self.pole_ilosc_total.grid(row=wiersz, column=4, padx=2, pady=1, sticky="ew")
        self.pole_ilosc_zpo.grid(row=wiersz, column=5, padx=2, pady=1, sticky="ew")
        self.przycisk_usun.grid(row=wiersz, column=6, padx=2, pady=1)

    def destroy(self):
        for pole in self._pola.values():
            pole.destroy()
        self.przycisk_usun.destroy()

    def widget_pola(self, nazwa):
        return _widget_ogniskowalny(self._pola[nazwa])

    def _na_zmiane(self, *_):
        if self._ustawiam_programowo:
            return
        self.on_zmiana(self)

    def _uzupelnij_ilosc_zpo(self, *_):
        if self._ustawiam_programowo:
            return
        if self._ilosc_zpo_aktywne and not self.var_ilosc_zpo.get().strip():
            self.var_ilosc_zpo.set(self.var_ilosc_total.get())

    def zastosuj_dedukcje(self, wynik):
        """wynik: dedukcja.WynikWiersza. Wypełnia pola dedukowane
        jednoznacznie, przełącza aktywność/kolor/kandydatów podpowiedzi
        pozostałych - kolejność nawigacji dochodzi osobno, patrz
        ZakladkaWprowadzanie._odswiez_kolejnosc."""
        self.ostatni_wynik = wynik
        self._ustawiam_programowo = True
        try:
            for klucz, var in (
                ("rejon", self.var_rejon), ("nadawca", self.var_nadawca),
                ("pni_zpo", self.var_pni),
            ):
                stan = wynik.pola[klucz]
                if stan.wartosc is not None:
                    var.set(stan.wartosc)
                pole = self._pola[klucz]
                pole.ustaw_stan(stan.stan)
                pole.ustaw_aktywnosc(stan.aktywne)
                # Afordancja rozwijanej listy (A2): pokazujemy strzałkę
                # WYŁĄCZNIE gdy dedukcja realnie dała warianty do wyboru.
                # Doklejenie jej wszędzie, gdzie technicznie jest
                # EntryZPodpowiedzia, zabiłoby sens rozróżnienia - rejon
                # też jest tym widgetem, a listy nie ma nigdy.
                pole.ustaw_liste(len(stan.kandydaci or ()))
                widget = pole.widget_pola
                if not hasattr(widget, "ustaw_zrodlo_kandydatow"):
                    continue
                if stan.kandydaci:
                    widget.ustaw_zrodlo_kandydatow(lambda k=stan.kandydaci: list(k))
                elif klucz == "nadawca":
                    widget.ustaw_zrodlo_kandydatow(self._pobierz_nadawcow)
                else:
                    widget.ustaw_zrodlo_kandydatow(lambda: [])

            stan_zpo = wynik.pola["ilosc_zpo"]
            self._ilosc_zpo_aktywne = stan_zpo.aktywne
            self.pole_ilosc_zpo.ustaw_stan(stan_zpo.stan)
            self.pole_ilosc_zpo.ustaw_aktywnosc(stan_zpo.aktywne)
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
    def __init__(self, parent, conn, katalog_danych, on_zapisano=None, sesja_uuid=None,
                 conn_rejonarz=None):
        super().__init__(parent)
        self.conn = conn
        self.katalog_danych = katalog_danych
        # Opcjonalne: bez migawki rejonarza dedukcja działa dokładnie tak
        # jak przedtem (przypięte testem w obie strony).
        self.conn_rejonarz = conn_rejonarz
        self.on_zapisano = on_zapisano
        # 0.1-alpha.3.2: grupuje wiersze zapisane w tym uruchomieniu
        # aplikacji - mintowane raz w gui/app.py, patrz repo.zapisz_blankiet.
        self.sesja_uuid = sesja_uuid
        self.wiersze = []
        self._ustawiam_programowo = False
        self._kolejnosc = []
        self._wynik_naglowka = {}
        self._klucz_podswietlony = None

        panel = ttk.PanedWindow(self, orient="vertical")
        panel.pack(fill="both", expand=True)

        gora = ttk.Frame(panel)
        pasek_podgladu = ttk.Frame(gora)
        pasek_podgladu.pack(fill="x", padx=6, pady=(4, 0))
        ttk.Label(
            pasek_podgladu, text="Podgląd (scroll / Ctrl+scroll = powiększenie, "
                                  "dwuklik = popraw):",
        ).pack(side="left")
        # 0.1-alpha.3.2: domyślnie tylko to, co wpisano W TYM uruchomieniu -
        # "czy to się zapisało?" ma być odpowiadalne bez przewijania 500
        # najnowszych wierszy całej bazy (patrz docs/roadmap.md)
        self.var_pokaz_wszystko = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            pasek_podgladu, text="pokaż całą bazę", variable=self.var_pokaz_wszystko,
            command=self.odswiez_podglad,
        ).pack(side="left", padx=(10, 0))
        self.podglad = Tabela(gora, KOLUMNY_PODGLADU, on_dwuklik=self._edytuj_z_podgladu)
        self.podglad.pack(fill="both", expand=True, padx=6, pady=6)
        panel.add(gora, weight=1)

        dol = ttk.Frame(panel)
        panel.add(dol, weight=2)

        naglowek = ttk.Frame(dol)
        naglowek.pack(fill="x", padx=6, pady=6)
        ttk.Label(naglowek, text="KURIER:", font=("TkDefaultFont", 12, "bold")).pack(side="left")
        self.var_kurier = tk.StringVar()
        self.pole_kurier = PoleZeWskaznikiem(naglowek, lambda p: EntryZPodpowiedzia(
            p, self._pobierz_kurierow, textvariable=self.var_kurier, width=30,
            font=("TkDefaultFont", 12), on_dalej=lambda: self._idz_dalej_naglowek("kurier")))
        self.pole_kurier.pack(side="left", padx=8)
        self.pole_kurier.ustaw_aktywnosc(True)

        ttk.Label(naglowek, text="Data:").pack(side="left", padx=(16, 0))
        self.var_data = tk.StringVar(value=date.today().isoformat())
        self.pole_data = PoleZeWskaznikiem(
            naglowek, lambda p: ttk.Entry(p, textvariable=self.var_data, width=12))
        self.pole_data.pack(side="left", padx=4)
        self.pole_data.ustaw_aktywnosc(True)

        ttk.Label(naglowek, text="Wykonawca:").pack(side="left", padx=(16, 0))
        self.var_wykonawca = tk.StringVar()
        self.pole_wykonawca = PoleZeWskaznikiem(naglowek, lambda p: EntryZPodpowiedzia(
            p, lambda: [], textvariable=self.var_wykonawca, width=16,
            on_dalej=lambda: self._idz_dalej_naglowek("wykonawca"), rozwijaj_na_pusty_fokus=True))
        self.pole_wykonawca.pack(side="left", padx=4)

        self._pola_naglowka = {
            "kurier": self.pole_kurier, "data": self.pole_data, "wykonawca": self.pole_wykonawca,
        }
        entry_data = self.pole_data.widget_pola
        entry_data.bind("<Tab>", lambda e: (self._idz_dalej_naglowek("data"), "break")[1])
        entry_data.bind("<Return>", lambda e: (self._idz_dalej_naglowek("data"), "break")[1])
        for nazwa, pole in self._pola_naglowka.items():
            entry = _widget_ogniskowalny(pole)
            entry.bind("<Shift-Tab>", lambda e, n=nazwa: (self._idz_wstecz_naglowek(n), "break")[1])
            entry.bind("<ISO_Left_Tab>", lambda e, n=nazwa: (self._idz_wstecz_naglowek(n), "break")[1])
            entry.bind("<FocusIn>", lambda e, n=nazwa: self._na_fokus(("naglowek", n)), add="+")

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

        # nagłówek kolumn = wiersz 0 TEJ SAMEJ siatki co dane (patrz
        # docstring modułu) - wyrównanie szerokości kolumn konstrukcyjne,
        # nie zależne od dwóch osobnych kontenerów
        self._siatka = ttk.Frame(canvas_wierszy)
        okno_id = canvas_wierszy.create_window((0, 0), window=self._siatka, anchor="nw")
        self._siatka.bind(
            "<Configure>", lambda e: canvas_wierszy.configure(scrollregion=canvas_wierszy.bbox("all"))
        )
        canvas_wierszy.bind(
            "<Configure>", lambda e: canvas_wierszy.itemconfig(okno_id, width=e.width)
        )
        canvas_wierszy.bind("<Enter>", lambda e: _podepnij_scroll_kolkiem(canvas_wierszy))
        canvas_wierszy.bind("<Leave>", lambda e: _odepnij_scroll_kolkiem(canvas_wierszy))

        for tekst, kolumna in [("Rejon", 0), ("Nadawca", 1), ("Adres", 2),
                                ("PNI ZPO", 3), ("Ilość", 4), ("w tym ZPO", 5)]:
            ttk.Label(self._siatka, text=tekst, anchor="w").grid(
                row=0, column=kolumna, padx=2, sticky="ew")

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
            self._siatka, self._usun_wiersz, self._pobierz_nadawcow,
            self._pobierz_adresy, self._na_zmiane_wiersza,
            self._idz_dalej_wiersz, self._idz_wstecz_wiersz,
        )
        self.wiersze.append(wiersz)
        wiersz.zastosuj_dedukcje(dedukcja.dedukuj_wiersz(
            self.conn, kurier="", adres="", conn_rejonarz=self.conn_rejonarz))
        self._bind_fokus_wiersza(wiersz)
        self._przelicz_wiersze_siatki()
        self._odswiez_kolejnosc()

    def _bind_fokus_wiersza(self, wiersz):
        for nazwa in wiersz._pola:
            wiersz.widget_pola(nazwa).bind(
                "<FocusIn>",
                lambda e, w=wiersz, n=nazwa: self._na_fokus(self._klucz_wiersza(w, n)),
                add="+",
            )

    def _usun_wiersz(self, wiersz):
        if len(self.wiersze) <= 1:
            return  # zawsze zostaje co najmniej jeden wiersz do wypełnienia
        wiersz.destroy()
        self.wiersze.remove(wiersz)
        self._klucz_podswietlony = None
        self._przelicz_wiersze_siatki()
        self._odswiez_kolejnosc()

    def _przelicz_wiersze_siatki(self):
        for i, w in enumerate(self.wiersze):
            w.grid(i + 1)  # wiersz 0 siatki = etykiety kolumn

    def _na_zmiane_naglowka(self, *_):
        if self._ustawiam_programowo:
            return
        kurier = self.var_kurier.get().strip()
        self._wynik_naglowka = dedukcja.dedukuj_naglowek(
            self.conn, kurier=kurier, data=self.var_data.get().strip())
        stan = self._wynik_naglowka["wykonawca"]
        self._ustawiam_programowo = True
        try:
            if stan.wartosc is not None:
                self.var_wykonawca.set(stan.wartosc)
            self.pole_wykonawca.ustaw_stan(stan.stan)
            self.pole_wykonawca.ustaw_aktywnosc(stan.aktywne)
            self.pole_wykonawca.ustaw_liste(len(stan.kandydaci or ()))
            self.pole_wykonawca.widget_pola.ustaw_zrodlo_kandydatow(
                (lambda k=stan.kandydaci: list(k)) if stan.kandydaci else (lambda: []))
        finally:
            self._ustawiam_programowo = False
        self._odswiez_kolejnosc()

    def _na_zmiane_wiersza(self, wiersz):
        kurier = self.var_kurier.get().strip()
        adres = wiersz.var_adres.get().strip()
        nadawca = wiersz.var_nadawca.get().strip() or None
        wynik = dedukcja.dedukuj_wiersz(
            self.conn, kurier=kurier, adres=adres, nadawca=nadawca,
            conn_rejonarz=self.conn_rejonarz)
        wiersz.zastosuj_dedukcje(wynik)
        self._odswiez_kolejnosc()

    def _odswiez_kolejnosc(self):
        self._kolejnosc = dedukcja.kolejnosc_pol(
            "auto", self._wynik_naglowka, [w.ostatni_wynik for w in self.wiersze])

    def _klucz_wiersza(self, wiersz, nazwa):
        return ("wiersz", self.wiersze.index(wiersz), nazwa)

    def _idz_dalej_naglowek(self, nazwa):
        self._skocz(("naglowek", nazwa), 1)

    def _idz_wstecz_naglowek(self, nazwa):
        self._skocz(("naglowek", nazwa), -1)

    def _idz_dalej_wiersz(self, wiersz, nazwa):
        self._skocz(self._klucz_wiersza(wiersz, nazwa), 1)

    def _idz_wstecz_wiersz(self, wiersz, nazwa):
        self._skocz(self._klucz_wiersza(wiersz, nazwa), -1)

    def _skocz(self, klucz_biezace, kierunek):
        # 0.1-alpha.3.2: Tab/Enter z ostatniego pola CAŁEJ sekwencji (zawsze
        # wewnątrz ostatniego wiersza, patrz dedukcja.czy_koniec_ostatniego_wiersza)
        # dodaje nowy wiersz zamiast zawijać do nagłówka - ale TYLKO gdy ten
        # ostatni wiersz jest faktycznie wypełniony; pusty ostatni wiersz
        # dalej zawija (nie ma sensu mnożyć pustych wierszy).
        if (kierunek == 1
                and dedukcja.czy_koniec_ostatniego_wiersza(self._kolejnosc, klucz_biezace)
                and self.wiersze and not wiersz_pusty(self.wiersze[-1].pobierz_surowe())):
            self.dodaj_wiersz()
            self.wiersze[-1].widget_pola("adres").focus_set()
            return
        docelowy = dedukcja.przesun_w_kolejnosci(self._kolejnosc, klucz_biezace, kierunek)
        widget = self._widget_dla_klucza(docelowy)
        if widget is not None:
            widget.focus_set()

    def _pole_dla_klucza(self, klucz):
        if klucz is None:
            return None
        if klucz[0] == "naglowek":
            return self._pola_naglowka.get(klucz[1])
        _, i, nazwa = klucz
        if i >= len(self.wiersze):
            return None
        return self.wiersze[i]._pola.get(nazwa)

    def _widget_dla_klucza(self, klucz):
        pole = self._pole_dla_klucza(klucz)
        return _widget_ogniskowalny(pole) if pole is not None else None

    def _na_fokus(self, klucz_biezace):
        """Podświetla NASTĘPNE pole w kolejności nawigacji względem tego,
        które właśnie dostało fokus - ten sam motyw co "wymaga uwagi",
        cieńsza obwódka (patrz widget_pole.PoleZeWskaznikiem)."""
        docelowy = dedukcja.przesun_w_kolejnosci(self._kolejnosc, klucz_biezace, 1)
        if docelowy == self._klucz_podswietlony:
            return
        stare_pole = self._pole_dla_klucza(self._klucz_podswietlony)
        if stare_pole is not None:
            stare_pole.ustaw_nastepne(False)
        nowe_pole = self._pole_dla_klucza(docelowy)
        if nowe_pole is not None:
            nowe_pole.ustaw_nastepne(True)
        self._klucz_podswietlony = docelowy

    def odswiez_podglad(self):
        # import używa TEGO SAMEGO sesja_uuid, gdy odpalony w tym samym
        # uruchomieniu - zrodlo="formularz" wyklucza jego wiersze, bo import
        # ma własny ekran korekty do przeglądania swoich wyników
        filtr_sesji = ({} if self.var_pokaz_wszystko.get()
                        else {"sesja_uuid": self.sesja_uuid, "zrodlo": "formularz"})
        self.podglad.ustaw_dane(repo.pobierz_transakcje(self.conn, limit=500, **filtr_sesji))

    def _edytuj_z_podgladu(self, wiersz):
        DialogEdycji(self, self.conn, self.katalog_danych, wiersz, on_zapisano=self._po_edycji)

    def _po_edycji(self):
        self.odswiez_podglad()
        if self.on_zapisano:
            self.on_zapisano()

    def zapisz(self):
        dane_wierszy = [w.pobierz_surowe() for w in self.wiersze]
        try:
            blankiet = zbuduj_blankiet(
                self.var_kurier.get(), self.var_data.get().strip(),
                self.var_wykonawca.get().strip() or None, dane_wierszy,
            )
        except ValidationError as e:
            self.etykieta_status.configure(
                text=f"Błąd: {_pierwszy_blad(e)}", foreground=KOLORY["czerwony"])
            return

        if blankiet is None:
            self.etykieta_status.configure(
                text="Brak wypełnionych wierszy do zapisania.", foreground=KOLORY["czerwony"])
            return

        # widgety wierszy NIEPUSTYCH, w TEJ SAMEJ kolejności co blankiet.wiersze
        # (zbuduj_blankiet filtruje puste tym samym predykatem) - `wyniki`
        # z zapisz_blankiet jest z nimi indeksowo równoległe (repo.py: "jeden
        # na wiersz, w kolejności wejściowej"), puste wiersze-placeholdery
        # nigdy do zapisu nie trafiają, więc nie mają odpowiednika w wyniki
        widgety_probowane = [w for w in self.wiersze if not wiersz_pusty(w.pobierz_surowe())]

        wyniki = operacje.wykonaj(
            self.conn, self.katalog_danych, rodzaj="zapis_blankietu",
            etykieta=f"{self.var_kurier.get().strip()}, {len(blankiet.wiersze)} wiersz(y)",
            funkcja=repo.zapisz_blankiet,
            args=(blankiet,),
            kwargs={"autor_id": getattr(self, "autor_id", None),
                    "sesja_uuid": self.sesja_uuid},
            licz_wiersze=operacje.licz_zapisane_wiersze,
            licz_pominiete=operacje.licz_pominiete_wiersze,
        )

        ostrzezenia = []
        powody_pominietych = []  # (numer_1_based_wsrod_probowanych, powod)
        for numer, wynik in enumerate(wyniki, start=1):
            ostrzezenia.extend(wynik["ostrzezenia"])
            if wynik["pominieto"]:
                powody_pominietych.append((numer, wynik["powod"]))
        pominiete = len(powody_pominietych)
        zapisane = len(wyniki) - pominiete

        if pominiete == 0:
            # pełny sukces - świeży start, jak przed 0.1-alpha.3.2 (razem ze
            # sprzątnięciem ewentualnych pustych wierszy-placeholderów)
            data_zachowana = self.var_data.get()
            for wiersz_widget in list(self.wiersze):
                wiersz_widget.destroy()
            self.wiersze.clear()
            self.var_kurier.set("")
            self.var_wykonawca.set("")
            self.var_data.set(data_zachowana)
            self.dodaj_wiersz()
            self.dodaj_wiersz()
        else:
            # 0.1-alpha.3.2: TYLKO zapisane znikają - pominięte zostają
            # widoczne i wypełnione, do poprawki i ponownego zapisu; nagłówek
            # (kurier/wykonawca) NIE jest czyszczony, użytkownik wciąż
            # pracuje nad tym samym blankietem
            widgety_do_usuniecia = [
                widget for widget, wynik in zip(widgety_probowane, wyniki)
                if not wynik["pominieto"]
            ]
            for widget in widgety_do_usuniecia:
                widget.destroy()
                self.wiersze.remove(widget)
            self._przelicz_wiersze_siatki()
            self._odswiez_kolejnosc()

        if pominiete == 0:
            tekst = f"Zapisano {zapisane} wierszy."
            kolor = KOLORY["zielony"]
        else:
            opis = "; ".join(f"wiersz {n}: {powod}" for n, powod in powody_pominietych)
            tekst = f"Zapisano {zapisane} z {zapisane + pominiete} wierszy. Pominięto - {opis}."
            kolor = KOLORY["czerwony"]
        if ostrzezenia:
            tekst += f" Ostrzeżeń: {len(ostrzezenia)}."
        self.etykieta_status.configure(text=tekst, foreground=kolor)

        self.odswiez_podglad()
        if self.on_zapisano:
            self.on_zapisano()


def _pierwszy_blad(wyjatek: ValidationError) -> str:
    blad = wyjatek.errors()[0]
    pole = ".".join(str(p) for p in blad["loc"])
    return f"{pole}: {blad['msg']}"
