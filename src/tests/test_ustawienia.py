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
