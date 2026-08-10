"""
Zakładka wprowadzania - formularz wzorowany na papierowym blankiecie
(docs/ux-ui.md): KURIER na górze, potem jeden lub więcej bloków REJON+DATA
(rejon opcjonalny - 35% blankietów ma więcej niż jeden rejon, patrz plan
MVP), pod każdym powtarzalne wiersze punkt+ilość. Nad formularzem panel
podglądu bazy (scroll + Ctrl+scroll zoom, patrz widget_tabela.Tabela).

Cała logika walidacji/budowania modeli jest w formularz_logika.py i
models.py - tu tylko zbieranie wartości z pól i wyświetlanie wyniku.
"""
from datetime import date
import tkinter as tk
from tkinter import ttk

from pydantic import ValidationError

from zpo_tracker import repo
from zpo_tracker.gui.formularz_logika import zbuduj_bloki
from zpo_tracker.gui.widget_autocomplete import EntryZPodpowiedzia
from zpo_tracker.gui.widget_tabela import Tabela

KOLUMNY_PODGLADU = [
    ("data", "Data", 90),
    ("kurier", "Kurier", 150),
    ("nadawca", "Nadawca", 110),
    ("adres", "Adres", 200),
    ("rejon", "Rejon", 60),
    ("ilosc_total", "Ilość", 55),
    ("ilosc_zpo", "w tym ZPO", 75),
]


class WierszWidget(ttk.Frame):
    """Jeden wiersz bloku: punkt (nadawca + adres, opcjonalnie PNI) + ilość."""

    def __init__(self, parent, on_usun, pobierz_nadawcow, pobierz_adresy):
        super().__init__(parent)
        self.var_nadawca = tk.StringVar()
        self.var_adres = tk.StringVar()
        self.var_pni = tk.StringVar()
        self.var_ilosc_total = tk.StringVar()
        self.var_ilosc_zpo = tk.StringVar()

        EntryZPodpowiedzia(
            self, pobierz_nadawcow, textvariable=self.var_nadawca, width=16
        ).grid(row=0, column=0, padx=2)
        EntryZPodpowiedzia(
            self, pobierz_adresy, textvariable=self.var_adres, width=26
        ).grid(row=0, column=1, padx=2)
        ttk.Entry(self, textvariable=self.var_pni, width=10).grid(row=0, column=2, padx=2)
        ttk.Entry(self, textvariable=self.var_ilosc_total, width=6).grid(row=0, column=3, padx=2)
        ttk.Entry(self, textvariable=self.var_ilosc_zpo, width=6).grid(row=0, column=4, padx=2)
        ttk.Button(self, text="✕", width=2, command=lambda: on_usun(self)).grid(row=0, column=5, padx=2)

        # domyślnie ilosc_zpo == ilosc_total dla punktów z PNI, ale pole
        # zostaje niezależnie edytowalne (docs/domain-model.md)
        self.var_ilosc_total.trace_add("write", self._uzupelnij_ilosc_zpo)

    def _uzupelnij_ilosc_zpo(self, *_):
        if self.var_pni.get().strip() and not self.var_ilosc_zpo.get().strip():
            self.var_ilosc_zpo.set(self.var_ilosc_total.get())

    def pobierz_surowe(self):
        return {
            "nadawca": self.var_nadawca.get(),
            "adres": self.var_adres.get(),
            "pni_zpo": self.var_pni.get().strip() or None,
            "ilosc_total": self.var_ilosc_total.get().strip() or None,
            "ilosc_zpo": self.var_ilosc_zpo.get().strip() or None,
        }


class BlokRejonuWidget(ttk.LabelFrame):
    """Blok REJON + DATA + KOMENTARZ, z listą wierszy punkt+ilość."""

    def __init__(self, parent, data_domyslna, on_usun_blok, pobierz_nadawcow, pobierz_adresy):
        super().__init__(parent, text="Rejon", padding=6)
        self.on_usun_blok = on_usun_blok
        self.pobierz_nadawcow = pobierz_nadawcow
        self.pobierz_adresy = pobierz_adresy
        self.wiersze = []

        naglowek = ttk.Frame(self)
        naglowek.pack(fill="x")
        ttk.Label(naglowek, text="Rejon (puste = nieznany):").pack(side="left")
        self.var_rejon = tk.StringVar()
        ttk.Entry(naglowek, textvariable=self.var_rejon, width=10).pack(side="left", padx=(4, 14))
        ttk.Label(naglowek, text="Data:").pack(side="left")
        self.var_data = tk.StringVar(value=data_domyslna)
        ttk.Entry(naglowek, textvariable=self.var_data, width=12).pack(side="left", padx=4)
        ttk.Button(naglowek, text="usuń rejon", command=lambda: on_usun_blok(self)).pack(side="right")

        komentarz_ramka = ttk.Frame(self)
        komentarz_ramka.pack(fill="x", pady=(4, 6))
        ttk.Label(komentarz_ramka, text="Komentarz (np. gdy rejon nieznany):").pack(side="left")
        self.var_komentarz = tk.StringVar()
        ttk.Entry(komentarz_ramka, textvariable=self.var_komentarz, width=50).pack(
            side="left", padx=4, fill="x", expand=True
        )

        naglowek_kolumn = ttk.Frame(self)
        naglowek_kolumn.pack(fill="x")
        for tekst, w in [("Nadawca", 16), ("Adres", 26), ("PNI ZPO", 10), ("Ilość", 6), ("w tym ZPO", 6)]:
            ttk.Label(naglowek_kolumn, text=tekst, width=w, anchor="w").pack(side="left", padx=2)

        self.ramka_wierszy = ttk.Frame(self)
        self.ramka_wierszy.pack(fill="x")

        ttk.Button(self, text="+ wiersz", command=self.dodaj_wiersz).pack(anchor="w", pady=(4, 0))

        self.dodaj_wiersz()
        self.dodaj_wiersz()

    def dodaj_wiersz(self):
        wiersz = WierszWidget(
            self.ramka_wierszy, self._usun_wiersz, self.pobierz_nadawcow, self.pobierz_adresy
        )
        wiersz.pack(fill="x", pady=1)
        self.wiersze.append(wiersz)

    def _usun_wiersz(self, wiersz):
        if len(self.wiersze) <= 1:
            return  # zawsze zostaje co najmniej jeden wiersz do wypełnienia
        wiersz.destroy()
        self.wiersze.remove(wiersz)

    def pobierz_surowe(self):
        return {
            "rejon": self.var_rejon.get().strip() or None,
            "data": self.var_data.get().strip(),
            "komentarz": self.var_komentarz.get().strip() or None,
            "wiersze": [w.pobierz_surowe() for w in self.wiersze],
        }


class ZakladkaWprowadzanie(ttk.Frame):
    def __init__(self, parent, conn, on_zapisano=None):
        super().__init__(parent)
        self.conn = conn
        self.on_zapisano = on_zapisano
        self.bloki = []

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

        pasek_kuriera = ttk.Frame(dol)
        pasek_kuriera.pack(fill="x", padx=6, pady=6)
        ttk.Label(pasek_kuriera, text="KURIER:", font=("TkDefaultFont", 12, "bold")).pack(side="left")
        self.var_kurier = tk.StringVar()
        EntryZPodpowiedzia(
            pasek_kuriera, self._pobierz_kurierow, textvariable=self.var_kurier,
            width=30, font=("TkDefaultFont", 12),
        ).pack(side="left", padx=8)
        ttk.Label(pasek_kuriera, text="Wykonawca:").pack(side="left", padx=(16, 0))
        self.var_wykonawca = tk.StringVar()
        ttk.Entry(pasek_kuriera, textvariable=self.var_wykonawca, width=16).pack(side="left", padx=4)

        self.ramka_blokow = ttk.Frame(dol)
        self.ramka_blokow.pack(fill="both", expand=True, padx=6)

        pasek_akcji = ttk.Frame(dol)
        pasek_akcji.pack(fill="x", padx=6, pady=6)
        ttk.Button(pasek_akcji, text="+ dodaj rejon", command=self.dodaj_blok).pack(side="left")
        ttk.Button(pasek_akcji, text="ZAPISZ", command=self.zapisz).pack(side="left", padx=8)
        self.etykieta_status = ttk.Label(pasek_akcji, text="")
        self.etykieta_status.pack(side="left", padx=8)

        self._data_domyslna = date.today().isoformat()
        self.dodaj_blok()
        self.odswiez_podglad()

    def _pobierz_kurierow(self):
        return [w["nazwa"] for w in repo.pobierz_slownik(self.conn, "kurierzy")]

    def _pobierz_nadawcow(self):
        return repo.pobierz_unikalne_nadawcow(self.conn)

    def _pobierz_adresy(self):
        return repo.pobierz_unikalne_adresy(self.conn)

    def dodaj_blok(self):
        data_domyslna = self.bloki[-1].var_data.get() if self.bloki else self._data_domyslna
        blok = BlokRejonuWidget(
            self.ramka_blokow, data_domyslna, self._usun_blok,
            self._pobierz_nadawcow, self._pobierz_adresy,
        )
        blok.pack(fill="x", pady=4)
        self.bloki.append(blok)

    def _usun_blok(self, blok):
        if len(self.bloki) <= 1:
            return
        blok.destroy()
        self.bloki.remove(blok)

    def odswiez_podglad(self):
        self.podglad.ustaw_dane(repo.pobierz_transakcje(self.conn, limit=500))

    def zapisz(self):
        dane_blokow = [b.pobierz_surowe() for b in self.bloki]
        try:
            bloki = zbuduj_bloki(self.var_kurier.get(), self.var_wykonawca.get().strip() or None, dane_blokow)
        except ValidationError as e:
            self.etykieta_status.configure(text=f"Błąd: {_pierwszy_blad(e)}", foreground="red")
            return

        if not bloki:
            self.etykieta_status.configure(text="Brak wypełnionych wierszy do zapisania.", foreground="red")
            return

        ostrzezenia, pominiete = [], 0
        for blok in bloki:
            for wynik in repo.zapisz_blok(self.conn, blok):
                if wynik["pominieto"]:
                    pominiete += 1
                ostrzezenia.extend(wynik["ostrzezenia"])

        data_zachowana = self.bloki[0].var_data.get()
        for blok_widget in list(self.bloki):
            blok_widget.destroy()
        self.bloki.clear()
        self.var_kurier.set("")
        self.var_wykonawca.set("")
        self._data_domyslna = data_zachowana
        self.dodaj_blok()

        tekst = f"Zapisano {sum(len(b.wiersze) for b in bloki) - pominiete} wierszy."
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
