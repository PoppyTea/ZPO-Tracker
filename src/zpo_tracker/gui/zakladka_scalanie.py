"""
Zakładka Scalanie: ręczne wchłonięcie drugiej bazy (.db) do bieżącej -
jednokierunkowe, źródło zostaje nietknięte (patrz scalanie.py). Cała
logika dopasowania/klasyfikacji jest w scalanie.py - tu tylko wybór pliku,
pokazanie planu i zebranie decyzji z ekranu korekty. Ekran korekty pokazuje
WYŁĄCZNIE to, co wymaga uwagi (ten sam wzorzec co DialogKorektyImportu) -
nowe wpisy i czyste duplikaty wchodzą/pomijają się cicho.
"""
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from zpo_tracker import operacje, scalanie
from zpo_tracker.gui.roznice import segmenty_roznicy
from zpo_tracker.gui.zakladka_import_export import _pole_z_roznicami


class DialogKorektyScalania(tk.Toplevel):
    def __init__(self, parent, conn, katalog_danych, sciezka_zrodlowa, plan, on_gotowe):
        super().__init__(parent)
        self.title("Korekta scalenia")
        self.geometry("720x560")
        self.conn = conn
        self.katalog_danych = katalog_danych
        self.sciezka_zrodlowa = sciezka_zrodlowa
        self.on_gotowe = on_gotowe

        self.zmienne_propozycji = []           # [(propozycja, BooleanVar)]
        self.zaakceptowane_ostrzezenia = {}     # {tabela: set(id_zrodlowe)}
        self.rozstrzygniecia_konfliktow = {}    # {id_transakcji_zrodlowej: "zrodlowa"}

        liczba_nowych_slownikow = (
            sum(len(s["nowe"]) for s in plan["slowniki"].values())
            + len(plan["punkty"]["nowe"]) + len(plan["uzytkownicy"]["nowi"])
        )
        ttk.Label(
            self,
            text=f"{len(plan['transakcje']['nowe'])} nowych transakcji, "
                 f"{len(plan['transakcje']['duplikaty'])} duplikatów (pominięte cicho), "
                 f"{liczba_nowych_slownikow} nowych wpisów w słownikach (dodane cicho). "
                 f"Poniżej tylko to, co wymaga uwagi.",
            wraplength=680, justify="left",
        ).pack(anchor="w", padx=10, pady=(10, 6))

        notebook = ttk.Notebook(self)
        notebook.pack(fill="both", expand=True, padx=10, pady=6)

        propozycje = plan["slowniki"]["kurierzy"]["propozycje"]
        if propozycje:
            ramka = ttk.Frame(notebook)
            notebook.add(ramka, text=f"Prawdopodobne literówki kurierów ({len(propozycje)})")
            for p in propozycje:
                var = tk.BooleanVar(value=True)
                ttk.Checkbutton(
                    ramka, variable=var, text=f"Scalić „{p['z']}” → „{p['na']}”",
                ).pack(anchor="w", padx=6, pady=2)
                self.zmienne_propozycji.append((p, var))

        wszystkie_ostrzezenia = [
            (tabela, o) for tabela, s in plan["slowniki"].items() for o in s["ostrzezenia"]
        ]
        if wszystkie_ostrzezenia:
            ramka = ttk.Frame(notebook)
            notebook.add(ramka, text=f"Różnice w zapisie ({len(wszystkie_ostrzezenia)})")
            ttk.Label(
                ramka,
                text="Różnią się WYŁĄCZNIE wielkością liter/polskimi znakami - NIE "
                     "scalono automatycznie. Domyślnie zostają osobnymi wpisami.",
                wraplength=660, justify="left",
            ).pack(anchor="w", padx=6, pady=6)
            for tabela, o in wszystkie_ostrzezenia:
                self._dodaj_wiersz_ostrzezenia(ramka, tabela, o)

        konflikty = plan["transakcje"]["konflikty"]
        if konflikty:
            ramka = ttk.Frame(notebook)
            notebook.add(ramka, text=f"Konflikty ilości ({len(konflikty)})")
            ttk.Label(
                ramka,
                text="Ta sama data+kurier+punkt, różna ilość - to zawsze błąd we "
                     "wprowadzaniu albo w papierowej dokumentacji, NIGDY nie "
                     "rozstrzygamy tego automatycznie. Domyślnie zostaje wartość "
                     "docelowa (obecna baza).",
                wraplength=660, justify="left",
            ).pack(anchor="w", padx=6, pady=6)
            for k in konflikty:
                self._dodaj_wiersz_konfliktu(ramka, k)

        pasek = ttk.Frame(self)
        pasek.pack(fill="x", padx=10, pady=10)
        ttk.Button(pasek, text="Zatwierdź scalenie", command=self._zatwierdz).pack(side="right")
        ttk.Button(pasek, text="Anuluj", command=self.destroy).pack(side="right", padx=6)

    def _dodaj_wiersz_ostrzezenia(self, parent, tabela, ostrzezenie):
        wiersz = ttk.Frame(parent)
        wiersz.pack(fill="x", padx=6, pady=3)

        seg_docelowa, seg_zrodlowa = segmenty_roznicy(
            ostrzezenie["docelowa"], ostrzezenie["zrodlowa"])
        etykieta_wyniku = ttk.Label(wiersz, text="→ zostają osobno", foreground="#888")

        def przelacz():
            klucz = ostrzezenie["id_zrodlowe"]
            zbior = self.zaakceptowane_ostrzezenia.setdefault(tabela, set())
            if klucz in zbior:
                zbior.discard(klucz)
                etykieta_wyniku.configure(text="→ zostają osobno", foreground="#888")
            else:
                zbior.add(klucz)
                etykieta_wyniku.configure(
                    text=f"→ scalone z „{ostrzezenie['docelowa']}”", foreground="#1e7a3a")

        ttk.Label(wiersz, text=f"[{tabela}]", width=10, anchor="w").pack(side="left")
        _pole_z_roznicami(wiersz, seg_docelowa).pack(side="left", padx=(4, 10))
        _pole_z_roznicami(wiersz, seg_zrodlowa).pack(side="left", padx=(0, 4))
        ttk.Button(wiersz, text="scal", width=8, command=przelacz).pack(side="left", padx=6)
        etykieta_wyniku.pack(side="left", padx=10)

    def _dodaj_wiersz_konfliktu(self, parent, konflikt):
        ramka = ttk.Frame(parent, relief="groove", borderwidth=1)
        ramka.pack(fill="x", padx=6, pady=4)
        etykieta_wyniku = ttk.Label(
            ramka, text="→ zostaje docelowa (domyślnie)", foreground="#888")

        def wybierz(zrodlowa):
            klucz = konflikt["id_transakcji_zrodlowej"]
            if zrodlowa:
                self.rozstrzygniecia_konfliktow[klucz] = "zrodlowa"
                etykieta_wyniku.configure(text="→ weź źródłową", foreground="#1e7a3a")
            else:
                self.rozstrzygniecia_konfliktow.pop(klucz, None)
                etykieta_wyniku.configure(
                    text="→ zostaje docelowa (domyślnie)", foreground="#888")

        opis = (f"{konflikt['data']}  {konflikt['kurier']} @ {konflikt['punkt']}: "
                f"docelowa={konflikt['docelowa']['ilosc_total']}  "
                f"źródłowa={konflikt['zrodlowa']['ilosc_total']}")
        ttk.Label(ramka, text=opis, wraplength=640, justify="left", anchor="w").pack(
            fill="x", padx=6, pady=(4, 2))

        pasek_przyciskow = ttk.Frame(ramka)
        pasek_przyciskow.pack(fill="x", padx=6, pady=(0, 4))
        ttk.Button(pasek_przyciskow, text="◄ zostaw docelową",
                   command=lambda: wybierz(False)).pack(side="left")
        ttk.Button(pasek_przyciskow, text="weź źródłową ►",
                   command=lambda: wybierz(True)).pack(side="left", padx=6)
        etykieta_wyniku.pack(side="left", padx=10)

    def _zatwierdz(self):
        odrzucone_propozycje = {
            p["id_zrodlowe"] for p, var in self.zmienne_propozycji if not var.get()
        }
        wynik = operacje.wykonaj(
            self.conn, self.katalog_danych, rodzaj="scalenie",
            etykieta=Path(self.sciezka_zrodlowa).name,
            funkcja=scalanie.wykonaj_scalenie, args=(self.sciezka_zrodlowa,),
            kwargs={
                "odrzucone_propozycje_kurierow": odrzucone_propozycje,
                "zaakceptowane_ostrzezenia": self.zaakceptowane_ostrzezenia,
                "rozstrzygniecia_konfliktow": self.rozstrzygniecia_konfliktow,
            },
            licz_wiersze=lambda w: w["dodano_transakcji"],
        )
        self.destroy()
        self.on_gotowe(wynik)


class ZakladkaScalanie(ttk.Frame):
    def __init__(self, parent, conn, katalog_danych, on_scalono=None):
        super().__init__(parent)
        self.conn = conn
        self.katalog_danych = katalog_danych
        self.on_scalono = on_scalono

        ramka = ttk.LabelFrame(self, text="Scalanie z inną bazą", padding=10)
        ramka.pack(fill="x", padx=10, pady=10)
        ttk.Label(
            ramka,
            text="Wybierz plik bazy (.db) z innej stacji - jej dane zostaną "
                 "wchłonięte do TEJ bazy. Plik źródłowy pozostaje nietknięty, "
                 "można go bezpiecznie scalić ponownie gdzie indziej.",
            wraplength=620, justify="left",
        ).pack(anchor="w")
        ttk.Button(
            ramka, text="Wybierz plik i scal...", command=self.scal
        ).pack(anchor="w", pady=(6, 0))
        self.etykieta_status = ttk.Label(ramka, text="")
        self.etykieta_status.pack(anchor="w", pady=(6, 0))

    def scal(self):
        sciezka = filedialog.askopenfilename(filetypes=[("Baza SQLite", "*.db")])
        if not sciezka:
            return
        try:
            plan = scalanie.zaplanuj_scalenie(self.conn, sciezka)
        except Exception as e:
            messagebox.showerror(
                "Błąd scalania", f"Nie udało się otworzyć bazy źródłowej:\n{e}")
            return

        t = plan["transakcje"]
        if not t["nowe"] and not t["duplikaty"] and not t["konflikty"]:
            self.etykieta_status.configure(
                text="Wybrana baza nie zawiera żadnych transakcji do scalenia.")
            return

        DialogKorektyScalania(
            self, self.conn, self.katalog_danych, sciezka, plan,
            on_gotowe=self._po_scaleniu,
        )

    def _po_scaleniu(self, wynik):
        self.etykieta_status.configure(
            text=f"Scalono: {wynik['dodano_transakcji']} nowych transakcji, "
                 f"{wynik['pominieto_duplikatow']} duplikatów pominiętych, "
                 f"{wynik['rozstrzygnieto_konfliktow']} konfliktów rozstrzygniętych "
                 f"na korzyść źródła."
        )
        if self.on_scalono:
            self.on_scalono()
