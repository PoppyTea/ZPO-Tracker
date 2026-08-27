"""
ustawienia.py: plik settings.json per stacja, poza bazą (ustawienia
"odsłaniające" przełączniki zaawansowane muszą być lokalne dla stacji,
NIE podlegać scalaniu/synchronizacji między stacjami). TDD.
"""
import json

from zpo_tracker import ustawienia


def test_wczytaj_bez_pliku_zwraca_puste(tmp_path):
    assert ustawienia.wczytaj(tmp_path) == {}


def test_wczytaj_uszkodzony_json_zwraca_puste_zamiast_wybuchac(tmp_path):
    (tmp_path / ustawienia.NAZWA_PLIKU).write_text("{nie-jest-to-json", encoding="utf-8")
    assert ustawienia.wczytaj(tmp_path) == {}


def test_wczytaj_plik_ktory_nie_jest_obiektem_zwraca_puste(tmp_path):
    (tmp_path / ustawienia.NAZWA_PLIKU).write_text("[1, 2, 3]", encoding="utf-8")
    assert ustawienia.wczytaj(tmp_path) == {}


def test_wczytaj_plik_w_zlym_kodowaniu_zwraca_puste_zamiast_wybuchac(tmp_path):
    # UnicodeDecodeError dziedziczy z ValueError, nie z OSError - plik
    # zapisany w innym kodowaniu (albo uszkodzony bajtowo) nie może
    # zablokować startu aplikacji, tak samo jak uszkodzony JSON
    (tmp_path / ustawienia.NAZWA_PLIKU).write_bytes(
        '{"aktywny_login": "Zażółć"}'.encode("cp1250"))
    assert ustawienia.wczytaj(tmp_path) == {}


def test_zapisz_i_wczytaj_round_trip(tmp_path):
    ustawienia.zapisz(tmp_path, {"aktywny_login": "DOM\\a#Jan Kowalski"})
    assert ustawienia.wczytaj(tmp_path) == {"aktywny_login": "DOM\\a#Jan Kowalski"}


def test_zapisz_tworzy_katalog_jesli_brak(tmp_path):
    katalog = tmp_path / "nieistniejacy"
    ustawienia.zapisz(katalog, {"a": 1})
    assert ustawienia.wczytaj(katalog) == {"a": 1}


def test_zapisz_jest_atomowe_nie_zostawia_pliku_tymczasowego(tmp_path):
    ustawienia.zapisz(tmp_path, {"a": 1})
    pliki = {p.name for p in tmp_path.iterdir()}
    assert ustawienia.NAZWA_PLIKU in pliki
    assert not any(p.endswith(".tmp") for p in pliki)


def test_nieznane_klucze_przetrwaja_read_modify_write(tmp_path):
    # przyszła wersja mogła dopisać klucz, którego ta wersja nie zna -
    # zapis nie może go ubić
    (tmp_path / ustawienia.NAZWA_PLIKU).write_text(
        json.dumps({"przyszla_funkcja": {"x": 1}, "aktywny_login": "a"}),
        encoding="utf-8",
    )
    dane = ustawienia.wczytaj(tmp_path)
    dane["aktywny_login"] = "b"
    ustawienia.zapisz(tmp_path, dane)

    wynik = ustawienia.wczytaj(tmp_path)
    assert wynik["aktywny_login"] == "b"
    assert wynik["przyszla_funkcja"] == {"x": 1}


# --- tryb testowy ------------------------------------------------------

def test_tryb_testowy_jest_domyslnie_wlaczony_w_alfie(tmp_path):
    """
    Program jest wydawany wyłącznie do testów - nikt nie trzyma w nim
    danych roboczych (patrz root CLAUDE.md). Dopóki to prawda, tryb
    testowy jest stanem NORMALNYM, a nie wyjątkiem, który trzeba włączyć.

    Ta domyślność jest tymczasowa i ma zniknąć razem z akapitem
    "not deployed yet" w CLAUDE.md - stąd jawna stała, a nie zaszyte
    `True` w kilku miejscach.
    """
    assert ustawienia.czy_tryb_testowy(ustawienia.wczytaj(tmp_path)) is True


def test_tryb_testowy_da_sie_wylaczyc_wpisem(tmp_path):
    ustawienia.zapisz(tmp_path, {"tryb_testowy": False})
    assert ustawienia.czy_tryb_testowy(ustawienia.wczytaj(tmp_path)) is False


def test_uszkodzony_wpis_nie_wywraca_startu(tmp_path):
    """`ustawienia.wczytaj` nigdy nie rzuca - ta sama zasada musi objąć
    odczyt trybu, bo inaczej literówka w pliku blokuje uruchomienie
    programu u osoby bez konsoli i bez uprawnień administratora."""
    for smiec in ["tak", 1, None, [], {"a": 1}]:
        assert ustawienia.czy_tryb_testowy({"tryb_testowy": smiec}) in (True, False)


def test_tryb_testowy_wylacza_pytanie_o_dane_uzytkownika(tmp_path):
    """Powód istnienia tego trybu dzisiaj: proces logowania jest
    wstrzymany, więc program nie ma witać człowieka okienkiem, którego
    nie da się sensownie wypełnić."""
    from zpo_tracker import repo, uzytkownicy

    c = repo.polacz(":memory:")
    repo.utworz_schemat(c)
    login = "DOMENA\\jkowalski"
    uzytkownicy.zapewnij_uzytkownika(c, login)

    assert uzytkownicy.czy_pytac_o_dane(c, login, {"tryb_testowy": True}) is False
    assert uzytkownicy.czy_pytac_o_dane(c, login, {"tryb_testowy": False}) is True
    c.close()
