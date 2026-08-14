"""
Okno główne aplikacji - Notebook z zakładkami. Zero logiki biznesowej -
tylko układ i spięcie zakładek z warstwą repo/db (docelowo: przeglądanie,
wprowadzanie, import/export, słowniki - dochodzą w kolejnych krokach).
"""
import logging
import os
import tkinter as tk
import uuid
from datetime import date
from pathlib import Path
from tkinter import messagebox, ttk

from zpo_tracker import blokada, dziennik, kopie, operacje, repo, ustawienia, uzytkownicy, zrzuty
from zpo_tracker.gui.dialog_uzytkownika import DialogUzytkownika, DialogWyboruUzytkownika
from zpo_tracker.gui.zakladka_przeglad import ZakladkaPrzeglad
from zpo_tracker.gui.zakladka_wprowadzanie import ZakladkaWprowadzanie
from zpo_tracker.gui.zakladka_import_export import ZakladkaImportExport
from zpo_tracker.gui.zakladka_slowniki import ZakladkaSlowniki
from zpo_tracker.gui.zakladka_scalanie import ZakladkaScalanie
from zpo_tracker.gui.zakladka_historia import ZakladkaHistoria


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

        self.sciezka_bazy = sciezka_bazy or _domyslna_sciezka_bazy()
        self.conn = repo.polacz(self.sciezka_bazy)
        _upewnij_schemat(self.conn)

        # 0.1-alpha.3.2: losowy klucz grupujący "co wpisałem w TYM
        # uruchomieniu" (podgląd formularza, widok poprawek) - NIE
        # tożsamość jak UUIDv5 w uzytkownicy.py, więc losowy jest tu
        # poprawny mimo że niedeterministyczny między stacjami.
        self.sesja_uuid = str(uuid.uuid4())

        # haki muszą wisieć na instancji Tk: sys.excepthook NIE łapie
        # wyjątków z callbacków widgetów (patrz dziennik.py)
        self.katalog_danych = _katalog_logow(sciezka_bazy)
        dziennik.skonfiguruj(self.katalog_danych)
        dziennik.zainstaluj_haki(self, katalog=self.katalog_danych)

        # naprawa rozjazdów danych sprzed tej wersji (rejony "???",
        # firmy_zpo <-> punkty.nadawca) - CELOWO poza `_upewnij_schemat`/
        # `migruj`, patrz docstring `repo.napraw_dane`. Migawka PRZED (przez
        # `operacje.wykonaj`) bo to największa jednorazowa mutacja danych
        # w tym wydaniu; awaria NIE może zablokować startu aplikacji na
        # stałe - zdegraduj do "nie naprawiono, pracuj dalej" zamiast
        # pozwolić wyjątkowi przerwać konstruktor.
        try:
            operacje.wykonaj(
                self.conn, self.katalog_danych, rodzaj="naprawa_danych",
                etykieta="rejony ??? + firmy_zpo", funkcja=repo.napraw_dane,
            )
        except Exception:
            logging.getLogger("zpo_tracker").exception(
                "Naprawa danych przy starcie nie powiodła się - kontynuuję bez niej.")

        # przycinanie migawek raz na uruchomienie (realnie ~raz dziennie) -
        # tanio, bez dokładania skanu katalogu do każdego zapisu w trakcie
        # pracy; katalog migawki/ inaczej rósłby bez ograniczeń
        kopie.przytnij_migawki(
            self.katalog_danych, dziennik.wczytaj_operacje(self.katalog_danych))

        # zrzut .sql.gz "na dziś" - warstwa zimna, osobna od migawek
        # i NIE przycinana (patrz zrzuty.py); jeden na dzień, więc kolejne
        # uruchomienie tego samego dnia nic dodatkowego nie robi
        if not zrzuty.istnieje_zrzut_na_dzien(self.katalog_danych, date.today()):
            zrzuty.zrob_zrzut(self.conn, self.katalog_danych)

        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill="both", expand=True)

        # dane wchodzą do bazy w kilku miejscach (formularz, import,
        # poprawki w Przeglądzie) i wpływają na wszystkie zakładki, które
        # je pokazują - jeden wspólny callback zamiast osobno pamiętać, co
        # trzeba odświeżyć gdzie. Zdefiniowany PRZED zakładkami, bo
        # ZakladkaPrzeglad (0.1-alpha.3.2, widok poprawek) potrzebuje go
        # już przy konstrukcji - domknięcie odwołuje się do `self.*`
        # rozstrzyganych dopiero przy WYWOŁANIU, więc kolejność jest
        # bezpieczna mimo że część zakładek jeszcze nie istnieje.
        def odswiez_po_zmianie():
            self.zakladka_przeglad.odswiez()
            self.zakladka_slowniki.odswiez_wszystko()
            self.zakladka_historia.odswiez()

        self.zakladka_przeglad = ZakladkaPrzeglad(
            self.notebook, self.conn, katalog_danych=self.katalog_danych,
            sesja_uuid=self.sesja_uuid, on_zmieniono=odswiez_po_zmianie,
        )
        self.notebook.add(self.zakladka_przeglad, text="Przeglądanie")

        self.zakladka_slowniki = ZakladkaSlowniki(
            self.notebook, self.conn, self.katalog_danych)

        self.zakladka_wprowadzanie = ZakladkaWprowadzanie(
            self.notebook, self.conn, self.katalog_danych, on_zapisano=odswiez_po_zmianie,
            sesja_uuid=self.sesja_uuid,
        )
        self.notebook.add(self.zakladka_wprowadzanie, text="Wprowadzanie")

        self.zakladka_import_export = ZakladkaImportExport(
            self.notebook, self.conn, self.katalog_danych, on_zaimportowano=odswiez_po_zmianie,
            sesja_uuid=self.sesja_uuid,
        )
        self.notebook.add(self.zakladka_import_export, text="Import / Export")

        self.notebook.add(self.zakladka_slowniki, text="Słowniki")

        self.zakladka_scalanie = ZakladkaScalanie(
            self.notebook, self.conn, self.katalog_danych, on_scalono=odswiez_po_zmianie
        )
        self.notebook.add(self.zakladka_scalanie, text="Scalanie")

        self.zakladka_historia = ZakladkaHistoria(
            self.notebook, self.katalog_danych, on_cofnij=self.cofnij_do)
        self.notebook.add(self.zakladka_historia, text="Historia")

        self._zbuduj_menu_uzytkownika()
        self._ustal_uzytkownika()

    def _zbuduj_menu_uzytkownika(self):
        """
        0.1-alpha.3.2: konta Windows bywają współdzielone przez kilka osób
        na jednej stacji - to menu pozwala jawnie powiedzieć "teraz pracuję
        ja", bez polegania wyłącznie na cichym wykryciu konta systemowego.
        """
        pasek = tk.Menu(self)
        self.config(menu=pasek)
        self._menu_uzytkownika = tk.Menu(pasek, tearoff=False)
        self._menu_uzytkownika.add_command(
            label="Zmień użytkownika…", command=self._zmien_uzytkownika)
        self._menu_uzytkownika.add_command(label="Wyloguj", command=self._wyloguj)
        pasek.add_cascade(label="Użytkownik", menu=self._menu_uzytkownika)

    def cofnij_do(self, seq_docelowy):
        """
        Przywraca bazę do stanu SPRZED operacji `seq_docelowy` (patrz
        `operacje.cofnij`) i zamyka aplikację. Podmiana pliku bazy pod
        żywymi połączeniami/widgetami w kilku zakładkach naraz jest
        ryzykowna - prostszy i bezpieczniejszy jest restart: użytkownik
        widzi przywrócony stan po ponownym uruchomieniu, nie po "gorącym"
        odświeżeniu całego okna.
        """
        self.conn.close()
        operacje.cofnij(self.katalog_danych, self.sciezka_bazy, seq_docelowy)
        self.destroy()

    def _ustal_uzytkownika(self):
        """
        Kto siedzi przy tej stacji. Wykrycie konta Windows jest ciche;
        popup pojawia się tylko wtedy, gdy brakuje imienia/nazwiska. Brak
        atrybucji NIE blokuje pracy - `autor_id` zostaje pusty i tyle.

        0.1-alpha.3.2: `self.login` to zawsze SUROWE konto Windows (baza do
        listowania w oknie wyboru, `uzytkownicy.znajdz_konta_dla_loginu`).
        Faktyczna tożsamość atrybucji to `self.login_aktywny` - domyślnie
        taki sam jak `self.login`, ale może to być login rozszerzony
        (`uzytkownicy.login_rozszerzony`) zapamiętany w `settings.json`,
        gdy na koncie pracuje kilka osób (patrz _na_wybrano_uzytkownika).
        """
        self.login = uzytkownicy.biezacy_login()
        self.login_aktywny = self.login
        self.autor_id = None
        if not self.login:
            return
        dane_ustawien = ustawienia.wczytaj(self.katalog_danych)
        self.login_aktywny = dane_ustawien.get("aktywny_login") or self.login
        self.autor_id = uzytkownicy.zapewnij_uzytkownika(self.conn, self.login_aktywny)
        if uzytkownicy.wymaga_uzupelnienia(self.conn, self.login_aktywny):
            # after_idle: okno główne musi być już narysowane, inaczej
            # modal wisi nad pustym prostokątem
            self.after_idle(self._popros_o_dane_uzytkownika)

    def _popros_o_dane_uzytkownika(self):
        DialogUzytkownika(self, self.conn, self.login_aktywny,
                          on_gotowe=self._zapamietaj_autora)

    def _zapamietaj_autora(self, autor_id):
        self.autor_id = autor_id
        self.zakladka_wprowadzanie.autor_id = autor_id
        self.zakladka_import_export.autor_id = autor_id

    def _zmien_uzytkownika(self):
        DialogWyboruUzytkownika(
            self, self.conn, self.login, on_wybrano=self._na_wybrano_uzytkownika)

    def _wyloguj(self):
        """Usuwa zapamiętany wybór i od razu każe wybrać ponownie - inaczej
        następne uruchomienie po prostu wróciłoby do tej samej osoby."""
        dane_ustawien = ustawienia.wczytaj(self.katalog_danych)
        dane_ustawien.pop("aktywny_login", None)
        ustawienia.zapisz(self.katalog_danych, dane_ustawien)
        self._zmien_uzytkownika()

    def _na_wybrano_uzytkownika(self, login):
        dane_ustawien = ustawienia.wczytaj(self.katalog_danych)
        dane_ustawien["aktywny_login"] = login
        ustawienia.zapisz(self.katalog_danych, dane_ustawien)

        self.login_aktywny = login
        self.autor_id = uzytkownicy.zapewnij_uzytkownika(self.conn, login)
        self.zakladka_wprowadzanie.autor_id = self.autor_id
        self.zakladka_import_export.autor_id = self.autor_id
        if uzytkownicy.wymaga_uzupelnienia(self.conn, login):
            self.after_idle(self._popros_o_dane_uzytkownika)

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

    # jedna instancja na katalog danych - dwie otwarte naraz to dwa okna
    # cicho nadpisujące sobie zmiany, mylące dla nietechnicznego użytkownika
    blokada_instancji = blokada.Blokada(katalog)
    if not blokada_instancji.zdobadz():
        okno = tk.Tk()
        okno.withdraw()
        messagebox.showwarning(
            "ZPO Tracker już działa",
            "Program jest już uruchomiony. Przełącz się na istniejące okno "
            "zamiast otwierać kolejne.",
        )
        okno.destroy()
        return

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
        blokada_instancji.zwolnij()
        return
    try:
        app.mainloop()
    finally:
        blokada_instancji.zwolnij()


if __name__ == "__main__":
    main()
