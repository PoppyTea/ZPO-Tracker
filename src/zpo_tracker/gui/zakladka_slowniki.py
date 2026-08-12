"""
Zakładka słowników - dodawanie/edycja kurierów, punktów ZPO, wykonawców,
rejonów i firm ZPO. Osobna od głównego wprowadzania danych (docs/ux-ui.md).
Cała logika w repo.py - tu tylko zbieranie wartości z pól i wyświetlanie.
"""
import tkinter as tk
from tkinter import messagebox, ttk

from zpo_tracker import operacje, repo


class PodzakladkaProstegoSlownika(ttk.Frame):
    """Kurierzy / Wykonawcy / Rejony / Firmy ZPO - jedno pole tekstowe."""

    def __init__(self, parent, conn, katalog_danych, tabela, etykieta_pola,
                 obsluguje_scalanie=False):
        super().__init__(parent)
        self.conn = conn
        self.katalog_danych = katalog_danych
        self.tabela = tabela
        self.obsluguje_scalanie = obsluguje_scalanie

        pasek = ttk.Frame(self)
        pasek.pack(fill="x", padx=6, pady=6)
        ttk.Label(pasek, text=f"{etykieta_pola}:").pack(side="left")
        self.var_nowy = tk.StringVar()
        ttk.Entry(pasek, textvariable=self.var_nowy, width=30).pack(side="left", padx=6)
        ttk.Button(pasek, text="+ dodaj", command=self.dodaj).pack(side="left")
        if obsluguje_scalanie:
            ttk.Button(pasek, text="Scal wybrane (2)", command=self.scal_wybrane).pack(
                side="left", padx=(12, 0)
            )

        select_mode = "extended" if obsluguje_scalanie else "browse"
        self.lista = tk.Listbox(self, selectmode=select_mode)
        self.lista.pack(fill="both", expand=True, padx=6, pady=(0, 6))
        self.lista.bind("<Double-Button-1>", self._edytuj_wybrany)

        self._wpisy = []
        self.odswiez()

    def odswiez(self):
        self._wpisy = repo.pobierz_slownik(self.conn, self.tabela)
        self.lista.delete(0, "end")
        for wpis in self._wpisy:
            self.lista.insert("end", wpis["nazwa"])

    def dodaj(self):
        nazwa = self.var_nowy.get().strip()
        if not nazwa:
            return
        try:
            operacje.wykonaj(
                self.conn, self.katalog_danych, rodzaj="dodaj_slownik",
                etykieta=f"{self.tabela}: dodano „{nazwa}”",
                funkcja=repo.dodaj_do_slownika, args=(self.tabela, nazwa),
            )
        except Exception as e:
            messagebox.showerror("Błąd", str(e))
            return
        self.var_nowy.set("")
        self.odswiez()

    def _edytuj_wybrany(self, _event):
        zaznaczone = self.lista.curselection()
        if not zaznaczone:
            return
        wpis = self._wpisy[zaznaczone[0]]
        nowa = _zapytaj_o_tekst("Zmień nazwę", wpis["nazwa"], self)
        if nowa and nowa.strip() and nowa.strip() != wpis["nazwa"]:
            try:
                operacje.wykonaj(
                    self.conn, self.katalog_danych, rodzaj="zmien_slownik",
                    etykieta=f"{self.tabela}: „{wpis['nazwa']}” → „{nowa.strip()}”",
                    funkcja=repo.zmien_nazwe_w_slowniku,
                    args=(self.tabela, wpis["id"], nowa.strip()),
                )
            except Exception as e:
                # np. kanoniczny rejon "???" (repo._czy_kanoniczny_rejon)
                # albo kolizja UNIQUE po normalizacji - bez tego callback
                # Tk kończy się cicho (dziennik.py łapie i loguje, ale
                # użytkownik nie widzi żadnej informacji)
                messagebox.showerror("Błąd", str(e))
                return
            self.odswiez()

    def scal_wybrane(self):
        zaznaczone = self.lista.curselection()
        if len(zaznaczone) != 2:
            messagebox.showinfo("Scalanie", "Wybierz dokładnie dwa wpisy do scalenia (Ctrl+klik).")
            return
        a, b = (self._wpisy[i] for i in zaznaczone)
        if not messagebox.askyesno(
            "Scalanie", f"Scalić „{a['nazwa']}” w „{b['nazwa']}”?\n"
                        f"Wszystkie transakcje „{a['nazwa']}” zostaną przepisane na „{b['nazwa']}”."
        ):
            return
        operacje.wykonaj(
            self.conn, self.katalog_danych, rodzaj="scal_slownik",
            etykieta=f"{self.tabela}: „{a['nazwa']}” → „{b['nazwa']}”",
            funkcja=repo.scal_kurierow, kwargs={"id_z": a["id"], "id_do": b["id"]},
        )
        self.odswiez()


class PodzakladkaPunktowZpo(ttk.Frame):
    """Punkty ZPO - nadawca (firma ZPO) + adres + PNI, tylko odczyt + dodawanie."""

    def __init__(self, parent, conn, katalog_danych):
        super().__init__(parent)
        self.conn = conn
        self.katalog_danych = katalog_danych

        ramka_nowy = ttk.LabelFrame(self, text="Nowy punkt", padding=6)
        ramka_nowy.pack(fill="x", padx=6, pady=6)
        self.var_nadawca = tk.StringVar()
        self.var_adres = tk.StringVar()
        self.var_pni = tk.StringVar()
        for etykieta, var, szer in [
            ("Nadawca/firma ZPO", self.var_nadawca, 18),
            ("Adres", self.var_adres, 28),
            ("PNI ZPO (opcjonalnie)", self.var_pni, 10),
        ]:
            ttk.Label(ramka_nowy, text=etykieta + ":").pack(side="left")
            ttk.Entry(ramka_nowy, textvariable=var, width=szer).pack(side="left", padx=(2, 10))
        ttk.Button(ramka_nowy, text="+ dodaj", command=self.dodaj).pack(side="left")

        # nadawca i firma ZPO to DWIE różne wartości (punkty.nadawca vs
        # firmy_zpo.nazwa) - pokazywanie ich pod jednym nagłówkiem chowało
        # rozjazd między nimi, czyli dokładnie to, co trzeba było zobaczyć
        kolumny = [
            ("nadawca", "Nadawca (punkt)", 150),
            ("firma_zpo", "Firma ZPO (słownik)", 150),
            ("adres", "Adres", 240),
            ("pni_zpo", "PNI ZPO", 90),
        ]
        self.tree = ttk.Treeview(self, columns=[k for k, _, _ in kolumny], show="headings")
        for klucz, naglowek, szerokosc in kolumny:
            self.tree.heading(klucz, text=naglowek)
            self.tree.column(klucz, width=szerokosc, anchor="w")
        self.tree.pack(fill="both", expand=True, padx=6, pady=(0, 6))

        self.odswiez()

    def odswiez(self):
        self.tree.delete(*self.tree.get_children())
        for p in repo.pobierz_punkty(self.conn):
            self.tree.insert("", "end", values=(
                p["nadawca"], p["firma_zpo"] or "", p["adres"], p["pni_zpo"] or "",
            ))

    def dodaj(self):
        nadawca, adres = self.var_nadawca.get().strip(), self.var_adres.get().strip()
        if not nadawca or not adres:
            messagebox.showinfo("Nowy punkt", "Nadawca i adres są wymagane.")
            return
        from zpo_tracker.importer import get_or_create_punkt
        _, ostrzezenia = operacje.wykonaj(
            self.conn, self.katalog_danych, rodzaj="nowy_punkt",
            etykieta=f"{nadawca} / {adres}",
            funkcja=get_or_create_punkt,
            args=(nadawca, adres, self.var_pni.get().strip() or None),
        )
        if ostrzezenia:
            messagebox.showwarning("Uwaga", "\n".join(ostrzezenia))
        self.var_nadawca.set("")
        self.var_adres.set("")
        self.var_pni.set("")
        self.odswiez()


def _zapytaj_o_tekst(tytul, wartosc_domyslna, parent):
    okno = tk.Toplevel(parent)
    okno.title(tytul)
    wynik = {"wartosc": None}
    var = tk.StringVar(value=wartosc_domyslna)
    ttk.Entry(okno, textvariable=var, width=30).pack(padx=10, pady=10)

    def zatwierdz():
        wynik["wartosc"] = var.get()
        okno.destroy()

    ttk.Button(okno, text="OK", command=zatwierdz).pack(pady=(0, 10))
    okno.transient(parent)
    okno.grab_set()
    parent.wait_window(okno)
    return wynik["wartosc"]


class ZakladkaSlowniki(ttk.Frame):
    def __init__(self, parent, conn, katalog_danych):
        super().__init__(parent)
        notebook = ttk.Notebook(self)
        notebook.pack(fill="both", expand=True)

        self._podzakladki = [
            PodzakladkaProstegoSlownika(notebook, conn, katalog_danych, "kurierzy", "Kurier", obsluguje_scalanie=True),
            PodzakladkaPunktowZpo(notebook, conn, katalog_danych),
            PodzakladkaProstegoSlownika(notebook, conn, katalog_danych, "wykonawcy", "Wykonawca"),
            PodzakladkaProstegoSlownika(notebook, conn, katalog_danych, "rejony", "Rejon"),
            PodzakladkaProstegoSlownika(notebook, conn, katalog_danych, "firmy_zpo", "Firma ZPO"),
        ]
        for widget, etykieta in zip(
            self._podzakladki,
            ["Kurierzy", "Punkty ZPO", "Wykonawcy", "Rejony", "Firmy ZPO"],
        ):
            notebook.add(widget, text=etykieta)

    def odswiez_wszystko(self):
        for podzakladka in self._podzakladki:
            podzakladka.odswiez()
