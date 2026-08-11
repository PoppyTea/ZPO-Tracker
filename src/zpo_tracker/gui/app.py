"""
Okno główne aplikacji - Notebook z zakładkami. Zero logiki biznesowej -
tylko układ i spięcie zakładek z warstwą repo/db (docelowo: przeglądanie,
wprowadzanie, import/export, słowniki - dochodzą w kolejnych krokach).
"""
import logging
import os
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk

from zpo_tracker import dziennik, repo, uzytkownicy
from zpo_tracker.gui.dialog_uzytkownika import DialogUzytkownika
from zpo_tracker.gui.zakladka_przeglad import ZakladkaPrzeglad
from zpo_tracker.gui.zakladka_wprowadzanie import ZakladkaWprowadzanie
from zpo_tracker.gui.zakladka_import_export import ZakladkaImportExport
from zpo_tracker.gui.zakladka_slowniki import ZakladkaSlowniki


NAZWA_BAZY = "zpo_tracker.db"


def _katalog_danych(os_name=None, localappdata=None, home=None):
    """
    Katalog na wszystkie dane aplikacji: bazę, log, dziennik operacji
    i kopie. Trzymane razem, żeby "przyślij mi plik z logami" pozostało
    instrukcją wykonalną dla użytkownika.

    Windows: %LOCALAPPDATA%, NIE %APPDATA%. To drugie to Roaming - przy
    profilach mobilnych albo przekierowaniu folderów (typowe w dużej
    organizacji) baza i cała historia kopii lądują na ścieżce logowania
    i wylogowania, co kończy się wielominutowym logowaniem i zakazem
    używania narzędzia.
    """
    os_name = os_name if os_name is not None else os.name
    home = Path(home) if home is not None else Path.home()
    if os_name == "nt":
        if localappdata is None:
            localappdata = os.environ.get("LOCALAPPDATA", str(home))
        katalog = Path(localappdata) / "ZPO-Tracker"
    else:
        katalog = home / ".local" / "share" / "zpo-tracker"
    katalog.mkdir(parents=True, exist_ok=True)
    return katalog


def _katalog_roaming(os_name=None, appdata=None, home=None):
    """Stara lokalizacja (Roaming) - tylko na potrzeby migracji."""
    os_name = os_name if os_name is not None else os.name
    if os_name != "nt":
        return None
    home = Path(home) if home is not None else Path.home()
    if appdata is None:
        appdata = os.environ.get("APPDATA")
    return Path(appdata) / "ZPO-Tracker" if appdata else None


def _przenies_ze_starej_lokalizacji(docelowa, stary_katalog):
    """
    Jednorazowa migracja Roaming -> Local. Jeśli baza istnieje już
    w nowej lokalizacji, stara jest ZOSTAWIANA nietknięta: nadpisanie
    bieżącej pracy porzuconą kopią byłoby gorsze niż zduplikowany plik.
    """
    if docelowa.exists() or stary_katalog is None:
        return
    stara = stary_katalog / NAZWA_BAZY
    if not stara.exists():
        return
    try:
        stara.replace(docelowa)
    except OSError:
        # inny wolumin albo brak uprawnień - kopiuj i zostaw oryginał
        import shutil
        shutil.copy2(stara, docelowa)


def _domyslna_sciezka_bazy(os_name=None, localappdata=None, appdata=None, home=None):
    """
    Ścieżka do bazy NIEZALEŻNA od katalogu roboczego (GH #4, krytyczny):
    ścieżka względna "zpo_tracker.db" tworzyła nową, pustą bazę za każdym
    razem, gdy aplikacja była odpalana z innego miejsca (skrót na
    pulpicie, inny folder) - wyglądało to jak reset danych po każdym
    uruchomieniu. Windows: %LOCALAPPDATA%\\ZPO-Tracker\\. Reszta:
    ~/.local/share/zpo-tracker/.
    """
    katalog = _katalog_danych(
        os_name=os_name, localappdata=localappdata, home=home)
    docelowa = katalog / NAZWA_BAZY
    _przenies_ze_starej_lokalizacji(
        docelowa,
        _katalog_roaming(os_name=os_name, appdata=appdata, home=home),
    )
    return str(docelowa)


def _katalog_logow(sciezka_bazy):
    """
    Katalog na log i dziennik, wyprowadzony ze ścieżki bazy. Bazy
    specjalne (":memory:", "file::memory:?cache=shared") nie mają katalogu
    nadrzędnego - `Path(":memory:").parent` to ".", co wysypywałoby logi do
    katalogu roboczego, czyli tam, skąd akurat odpalono .exe.
    """
    if not sciezka_bazy or sciezka_bazy.startswith(("file:", ":memory:")):
        return _katalog_danych()
    return Path(sciezka_bazy).parent


class Aplikacja(tk.Tk):
    def __init__(self, sciezka_bazy=None):
        super().__init__()
        self.title("ZPO Tracker")
        self.geometry("1000x700")

        self.conn = repo.polacz(sciezka_bazy or _domyslna_sciezka_bazy())
        _upewnij_schemat(self.conn)

        # haki muszą wisieć na instancji Tk: sys.excepthook NIE łapie
        # wyjątków z callbacków widgetów (patrz dziennik.py)
        self.katalog_danych = _katalog_logow(sciezka_bazy)
        dziennik.skonfiguruj(self.katalog_danych)
        dziennik.zainstaluj_haki(self, katalog=self.katalog_danych)

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

        self._ustal_uzytkownika()

    def _ustal_uzytkownika(self):
        """
        Kto siedzi przy tej stacji. Wykrycie konta Windows jest ciche;
        popup pojawia się tylko wtedy, gdy brakuje imienia/nazwiska albo
        numeru kadrowego. Brak atrybucji NIE blokuje pracy - `autor_id`
        zostaje pusty i tyle.
        """
        self.login = uzytkownicy.biezacy_login()
        self.autor_id = None
        if not self.login:
            return
        self.autor_id = uzytkownicy.zapewnij_uzytkownika(self.conn, self.login)
        if uzytkownicy.wymaga_uzupelnienia(self.conn, self.login):
            # after_idle: okno główne musi być już narysowane, inaczej
            # modal wisi nad pustym prostokątem
            self.after_idle(self._popros_o_dane_uzytkownika)

    def _popros_o_dane_uzytkownika(self):
        DialogUzytkownika(self, self.conn, self.login,
                          on_gotowe=self._zapamietaj_autora)

    def _zapamietaj_autora(self, autor_id):
        self.autor_id = autor_id
        self.zakladka_wprowadzanie.autor_id = autor_id

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
        return
    # baza z nowszej wersji programu: czytanie jej "jakoś" kończy się cichym
    # pominięciem kolumn, których ta wersja nie zna
    repo.sprawdz_zgodnosc_wersji(conn)
    if repo.wymaga_migracji(conn):
        repo.migruj(conn)


def main():
    # log konfigurowany PRZED zbudowaniem okna - awaria w trakcie
    # konstrukcji Aplikacji (np. uszkodzona baza) inaczej nie zostawiłaby
    # żadnego śladu, bo haki na instancji Tk jeszcze nie istnieją
    katalog = _katalog_danych()
    dziennik.skonfiguruj(katalog)
    dziennik.zainstaluj_haki(katalog=katalog)
    try:
        app = Aplikacja()
    except repo.NiezgodnaWersjaSchematu as e:
        # czytelny komunikat zamiast crashu bez śladu - w buildzie
        # console=False użytkownik nie zobaczyłby nawet tracebacku
        logging.getLogger("zpo_tracker").error("Odmowa otwarcia bazy: %s", e)
        okno = tk.Tk()
        okno.withdraw()
        messagebox.showerror("Nie można otworzyć bazy", str(e))
        okno.destroy()
        return
    app.mainloop()


if __name__ == "__main__":
    main()
