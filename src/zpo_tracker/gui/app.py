"""
Okno główne aplikacji - Notebook z zakładkami. Zero logiki biznesowej -
tylko układ i spięcie zakładek z warstwą repo/db (docelowo: przeglądanie,
wprowadzanie, import/export, słowniki - dochodzą w kolejnych krokach).
"""
import tkinter as tk
from tkinter import ttk

from zpo_tracker import repo
from zpo_tracker.gui.zakladka_przeglad import ZakladkaPrzeglad
from zpo_tracker.gui.zakladka_wprowadzanie import ZakladkaWprowadzanie
from zpo_tracker.gui.zakladka_import_export import ZakladkaImportExport

DOMYSLNA_BAZA = "zpo_tracker.db"


class Aplikacja(tk.Tk):
    def __init__(self, sciezka_bazy=DOMYSLNA_BAZA):
        super().__init__()
        self.title("ZPO Tracker")
        self.geometry("1000x700")

        self.conn = repo.polacz(sciezka_bazy)
        _upewnij_schemat(self.conn)

        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill="both", expand=True)

        self.zakladka_przeglad = ZakladkaPrzeglad(self.notebook, self.conn)
        self.notebook.add(self.zakladka_przeglad, text="Przeglądanie")

        self.zakladka_wprowadzanie = ZakladkaWprowadzanie(
            self.notebook, self.conn, on_zapisano=self.zakladka_przeglad.odswiez
        )
        self.notebook.add(self.zakladka_wprowadzanie, text="Wprowadzanie")

        self.zakladka_import_export = ZakladkaImportExport(
            self.notebook, self.conn, on_zaimportowano=self.zakladka_przeglad.odswiez
        )
        self.notebook.add(self.zakladka_import_export, text="Import / Export")

    def destroy(self):
        self.conn.close()
        super().destroy()


def _upewnij_schemat(conn):
    """Tworzy tabele, jeśli baza jest pusta (świeży plik / :memory:)."""
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='transakcje'"
    ).fetchone()
    if row is None:
        repo.utworz_schemat(conn)


def main():
    app = Aplikacja()
    app.mainloop()


if __name__ == "__main__":
    main()
