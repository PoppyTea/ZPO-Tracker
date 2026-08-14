"""
Zakładka Historia: log operacji (dziennik.py) + cofanie do dowolnego punktu
w czasie (operacje.py + kopie.py). Zero logiki biznesowej - tylko
wyświetlanie wpisów i wywołanie `on_cofnij` po potwierdzeniu przez
użytkownika; samo cofnięcie (zamknięcie/podmiana pliku/ponowne otwarcie)
robi `Aplikacja.cofnij_do` w app.py, bo dotyka stanu całego okna, nie tylko
tej zakładki.
"""
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import messagebox, ttk

from zpo_tracker import dziennik, operacje
from zpo_tracker.gui.widget_tabela import Tabela

KOLUMNY = [
    ("seq", "#", 50),
    ("czas", "Czas", 150),
    ("rodzaj", "Rodzaj", 140),
    ("etykieta", "Opis", 280),
    ("liczba_wierszy", "Wierszy", 70),
    ("liczba_pominietych", "Pominięto", 80),
    ("wynik", "Wynik", 70),
]


def _formatuj_czas(iso):
    if not iso:
        return "?"
    try:
        return datetime.fromisoformat(iso).strftime("%Y-%m-%d %H:%M")
    except ValueError:
        return iso


class DialogAlternatywnychMigawek(tk.Toplevel):
    """
    Migawka wybranej operacji zniknęła (przycięta - kopie.przytnij_migawki).
    Zamiast ślepego błędu: dwie najbliższe operacje, które WCIĄŻ mają
    migawkę (jedna starsza, jedna nowsza), klikalne wprost do standardowego
    flow potwierdzenia i cofnięcia (`on_wybor`) - patrz `_cofnij_wybrany`.
    """

    def __init__(self, parent, wpis_docelowy, poprzednia, nastepna, on_wybor):
        super().__init__(parent)
        self.title("Migawka usunięta")
        self.on_wybor = on_wybor

        czas_docelowy = _formatuj_czas(wpis_docelowy.get("czas"))
        ttk.Label(
            self,
            text=f"Migawka operacji #{wpis_docelowy['seq']} z {czas_docelowy} "
                 f"już nie istnieje - została usunięta.\n\n"
                 f"Najbliższe istniejące migawki to:",
            wraplength=420, justify="left",
        ).pack(anchor="w", padx=14, pady=(14, 8))

        ramka = ttk.Frame(self)
        ramka.pack(fill="x", padx=14, pady=4)

        self._wiersz_alternatywy(ramka, "następna:", nastepna)
        wiersz_celu = ttk.Frame(ramka)
        wiersz_celu.pack(fill="x", pady=2)
        ttk.Label(wiersz_celu, text=f"{czas_docelowy}  —  Brak migawki",
                  foreground="#888").pack(anchor="w")
        self._wiersz_alternatywy(ramka, "poprzednia:", poprzednia)

        ttk.Button(self, text="Anuluj", command=self.destroy).pack(pady=(8, 14))
        self.transient(parent)
        # grab_set() wymaga zmapowanego okna - bez wait_visibility() bywa
        # migotliwe pod obciążeniem (TclError "window not viewable"),
        # jeśli X11 nie zdążył jeszcze zmapować okna
        self.wait_visibility()
        self.grab_set()

    def _wiersz_alternatywy(self, parent, etykieta, wpis):
        wiersz = ttk.Frame(parent)
        wiersz.pack(fill="x", pady=2)
        ttk.Label(wiersz, text=etykieta, width=10, anchor="w").pack(side="left")
        if wpis is None:
            ttk.Label(wiersz, text="Brak", foreground="#888").pack(side="left")
            return
        ttk.Button(
            wiersz, text=_formatuj_czas(wpis.get("czas")),
            command=lambda: self._wybierz(wpis),
        ).pack(side="left")

    def _wybierz(self, wpis):
        self.destroy()
        self.on_wybor(wpis)


class ZakladkaHistoria(ttk.Frame):
    def __init__(self, parent, katalog_danych, on_cofnij):
        super().__init__(parent)
        self.katalog_danych = katalog_danych
        self.on_cofnij = on_cofnij

        ttk.Label(
            self,
            text="Historia operacji. Cofnięcie przywraca stan SPRZED "
                 "wybranej operacji - cofa też wszystko, co wydarzyło się "
                 "PO niej (to powrót do punktu w czasie, nie cofnięcie "
                 "tylko jednej zmiany). Aplikacja zamyka się po cofnięciu - "
                 "uruchom ją ponownie, żeby zobaczyć przywrócony stan.",
            wraplength=760, justify="left",
        ).pack(anchor="w", padx=10, pady=(10, 6))

        self.tabela = Tabela(self, KOLUMNY)
        self.tabela.pack(fill="both", expand=True, padx=10, pady=6)

        pasek = ttk.Frame(self)
        pasek.pack(fill="x", padx=10, pady=(0, 10))
        ttk.Button(
            pasek, text="Cofnij do tego punktu", command=self._cofnij_wybrany
        ).pack(side="left")

        self.odswiez()

    def odswiez(self):
        wpisy = list(reversed(dziennik.wczytaj_operacje(self.katalog_danych)))
        self.tabela.ustaw_dane(wpisy)

    def _cofnij_wybrany(self):
        zaznaczenie = self.tabela.tree.selection()
        if not zaznaczenie:
            messagebox.showinfo("Cofnij", "Wybierz operację z listy.")
            return
        # seq odczytywany z wartości w wierszu (pierwsza kolumna), nie
        # z pozycji - po kliknięciu nagłówka Tabela sortuje wiersze,
        # więc pozycja w drzewie i pozycja w dzienniku mogą się rozjechać
        seq = int(self.tabela.tree.item(zaznaczenie[0], "values")[0])
        wpis = next(
            (w for w in dziennik.wczytaj_operacje(self.katalog_danych)
             if w["seq"] == seq),
            None,
        )
        if wpis is None:
            messagebox.showerror("Cofnij", "Nieznana operacja.")
            return

        plik = wpis.get("plik_migawki")
        if not plik or not Path(plik).exists():
            poprzednia, nastepna = operacje.znajdz_najblizsze_migawki(
                self.katalog_danych, seq)
            DialogAlternatywnychMigawek(
                self, wpis, poprzednia, nastepna, on_wybor=self._potwierdz_i_cofnij)
            return

        self._potwierdz_i_cofnij(wpis)

    def _potwierdz_i_cofnij(self, wpis):
        if not messagebox.askyesno(
            "Cofnij",
            f"Cofnąć do stanu SPRZED operacji #{wpis['seq']} "
            f"({wpis['etykieta']})?\n\n"
            "WSZYSTKIE zmiany od tego momentu zostaną cofnięte. Aplikacja "
            "zamknie się - uruchom ją ponownie, żeby zobaczyć przywrócony "
            "stan.",
        ):
            return
        try:
            self.on_cofnij(wpis["seq"])
        except Exception as e:
            messagebox.showerror("Błąd cofania", str(e))
