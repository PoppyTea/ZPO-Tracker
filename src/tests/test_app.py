"""
Testy dla domyślnej ścieżki bazy aplikacji. GH #4 (krytyczny): baza
tworzona pod ścieżką względną do CWD sprawiała, że każde uruchomienie
z innego miejsca (skrót na pulpicie, inny folder) wyglądało jak reset
danych. Ścieżka musi być stała niezależnie od miejsca odpalenia.

Import samego modułu app.py nie wymaga display (tylko tworzenie Tk()
go wymaga) - te testy nie tworzą żadnego okna.
"""
from pathlib import Path

from zpo_tracker.gui.app import (
    _domyslna_sciezka_bazy, _katalog_danych, _katalog_logow,
)


def test_domyslna_sciezka_windows_uzywa_localappdata(tmp_path):
    # %APPDATA% to Roaming: przy profilach mobilnych/przekierowanych (typowe
    # w dużej organizacji) baza i cała historia kopii lądowałyby na ścieżce
    # logowania i wylogowania. %LOCALAPPDATA% nigdy nie roamuje.
    lokalny = tmp_path / "Local"
    sciezka = _domyslna_sciezka_bazy(
        os_name="nt", localappdata=str(lokalny), home=str(tmp_path))
    assert sciezka == str(lokalny / "ZPO-Tracker" / "zpo_tracker.db")


def test_migracja_przenosi_baze_z_roaming_do_local(tmp_path):
    # użytkownicy z wcześniejszej wersji mają dane w Roaming - nie wolno
    # ich zgubić przy zmianie lokalizacji
    roaming = tmp_path / "Roaming" / "ZPO-Tracker"
    roaming.mkdir(parents=True)
    (roaming / "zpo_tracker.db").write_bytes(b"stare dane")
    lokalny = tmp_path / "Local"

    sciezka = _domyslna_sciezka_bazy(
        os_name="nt", localappdata=str(lokalny),
        appdata=str(tmp_path / "Roaming"), home=str(tmp_path))

    assert Path(sciezka).read_bytes() == b"stare dane"
    assert not (roaming / "zpo_tracker.db").exists()


def test_migracja_nie_nadpisuje_istniejacej_bazy_lokalnej(tmp_path):
    # jeśli obie istnieją, nowsza lokalizacja wygrywa - inaczej stara,
    # porzucona kopia z Roaming skasowałaby bieżącą pracę
    roaming = tmp_path / "Roaming" / "ZPO-Tracker"
    roaming.mkdir(parents=True)
    (roaming / "zpo_tracker.db").write_bytes(b"stare")
    lokalny_katalog = tmp_path / "Local" / "ZPO-Tracker"
    lokalny_katalog.mkdir(parents=True)
    (lokalny_katalog / "zpo_tracker.db").write_bytes(b"biezace")

    sciezka = _domyslna_sciezka_bazy(
        os_name="nt", localappdata=str(tmp_path / "Local"),
        appdata=str(tmp_path / "Roaming"), home=str(tmp_path))

    assert Path(sciezka).read_bytes() == b"biezace"


def test_domyslna_sciezka_linux_uzywa_katalogu_domowego(tmp_path):
    sciezka = _domyslna_sciezka_bazy(os_name="posix", home=str(tmp_path))
    assert sciezka == str(tmp_path / ".local" / "share" / "zpo-tracker" / "zpo_tracker.db")


def test_domyslna_sciezka_tworzy_katalog_jesli_brak(tmp_path):
    docelowy = tmp_path / "nieistniejacy"
    sciezka = _domyslna_sciezka_bazy(os_name="posix", home=str(docelowy))
    assert Path(sciezka).parent.is_dir()


def test_log_lezy_obok_bazy(tmp_path):
    # log i baza w jednym katalogu - inaczej "przyślij mi plik z logami"
    # przestaje być instrukcją wykonalną dla użytkownika
    katalog = _katalog_danych(os_name="posix", home=str(tmp_path))
    sciezka = _domyslna_sciezka_bazy(os_name="posix", home=str(tmp_path))
    assert Path(sciezka).parent == katalog


def test_katalog_logow_dla_bazy_w_pamieci_nie_jest_katalogiem_roboczym(monkeypatch, tmp_path):
    # ":memory:" nie ma katalogu nadrzędnego - Path(":memory:").parent to
    # ".", więc log wylądowałby tam, skąd akurat odpalono .exe
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HOME", str(tmp_path / "dom"))  # nie dotykać realnego $HOME
    assert _katalog_logow(":memory:") != Path(".")
    assert _katalog_logow(":memory:").is_absolute()


def test_katalog_logow_dla_zwyklej_bazy_to_jej_katalog(tmp_path):
    assert _katalog_logow(str(tmp_path / "baza.db")) == tmp_path


def test_domyslna_sciezka_niezalezna_od_cwd(tmp_path, monkeypatch):
    # sedno GH #4: ta sama baza niezależnie skąd odpalone
    monkeypatch.chdir(tmp_path)
    sciezka_1 = _domyslna_sciezka_bazy(os_name="posix", home=str(tmp_path / "home"))
    inny_katalog = tmp_path / "inny_folder_startowy"
    inny_katalog.mkdir()
    monkeypatch.chdir(inny_katalog)
    sciezka_2 = _domyslna_sciezka_bazy(os_name="posix", home=str(tmp_path / "home"))
    assert sciezka_1 == sciezka_2
