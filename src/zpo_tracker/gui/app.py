"""
Okno główne aplikacji - Notebook z zakładkami. Zero logiki biznesowej -
tylko układ i spięcie zakładek z warstwą repo/db (docelowo: przeglądanie,
wprowadzanie, import/export, słowniki - dochodzą w kolejnych krokach).
"""
import os
import tkinter as tk
from pathlib import Path
from tkinter import ttk

from zpo_tracker import repo
from zpo_tracker.gui.zakladka_przeglad import ZakladkaPrzeglad
from zpo_tracker.gui.zakladka_wprowadzanie import ZakladkaWprowadzanie
from zpo_tracker.gui.zakladka_import_export import ZakladkaImportExport
from zpo_tracker.gui.zakladka_slowniki import ZakladkaSlowniki


def _domyslna_sciezka_bazy(os_name=None, appdata=None, home=None):
    """
    Ścieżka do bazy NIEZALEŻNA od katalogu roboczego (GH #4, krytyczny):
    ścieżka względna "zpo_tracker.db" tworzyła nową, pustą bazę za każdym
    razem, gdy aplikacja była odpalana z innego miejsca (skrót na
    pulpicie, inny folder) - wyglądało to jak reset danych po każdym
    uruchomieniu. Windows: %APPDATA%\\ZPO-Tracker\\. Reszta:
    ~/.local/share/zpo-tracker/.
    """
    os_name = os_name if os_name is not None else os.name
    home = Path(home) if home is not None else Path.home()
    if os_name == "nt":
        appdata = appdata if appdata is not None else os.environ.get("APPDATA", str(home))
        katalog = Path(appdata) / "ZPO-Tracker"
    else:
        katalog = home / ".local" / "share" / "zpo-tracker"
    katalog.mkdir(parents=True, exist_ok=True)
    return str(katalog / "zpo_tracker.db")


class Aplikacja(tk.Tk):
    def __init__(self, sciezka_bazy=None):
        super().__init__()
        self.title("ZPO Tracker")
        self.geometry("1000x700")

        self.conn = repo.polacz(sciezka_bazy or _domyslna_sciezka_bazy())
        _upewnij_schemat(self.conn)

        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill="both", expand=True)

        self.zakladka_przeglad = ZakladkaPrzeglad(self.notebook, self.conn)
        self.notebook.add(self.zakladka_przeglad, text="Przeglądanie")

        self.zakladka_slowniki = ZakladkaSlowniki(self.notebook, self.conn)

        # dane wchodzą do bazy w kilku miejscach (formularz, import) i
        # wpływają na wszystkie zakładki, które je pokazują - jeden wspólny
        # callback zamiast osobno pamiętać, co trzeba odświeżyć gdzie
        def odswiez_po_zmianie():
            self.zakladka_przeglad.odswiez()
            self.zakladka_slowniki.odswiez_wszystko()

        self.zakladka_wprowadzanie = ZakladkaWprowadzanie(
            self.notebook, self.conn, on_zapisano=odswiez_po_zmianie
        )
        self.notebook.add(self.zakladka_wprowadzanie, text="Wprowadzanie")

        self.zakladka_import_export = ZakladkaImportExport(
            self.notebook, self.conn, on_zaimportowano=odswiez_po_zmianie
        )
        self.notebook.add(self.zakladka_import_export, text="Import / Export")

        self.notebook.add(self.zakladka_slowniki, text="Słowniki")

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
