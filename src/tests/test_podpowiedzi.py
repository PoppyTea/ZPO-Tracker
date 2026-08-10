"""
Testy silnika podpowiedzi: dopasowanie prefiksu/podciągu, szeregowanie po
częstości i ostatnim użyciu, dopasowanie rozmyte (diakrytyki/wielkość
liter). TDD. Bez GUI - widget tylko wywołuje te funkcje.
"""
from zpo_tracker.podpowiedzi import podpowiedz, najlepsza_podpowiedz


def test_podpowiedz_pusty_prefiks_brak_wynikow():
    assert podpowiedz("", ["Żabka Odkryta 24"]) == []


def test_podpowiedz_dopasowanie_od_poczatku_przed_podciagiem():
    kandydaci = ["Odkryta Żabka", "Żabka Odkryta 24"]
    wynik = podpowiedz("Żabka", kandydaci)
    assert wynik[0] == "Żabka Odkryta 24"  # zaczyna się od prefiksu


def test_podpowiedz_ignoruje_diakrytyki_i_wielkosc_liter():
    assert podpowiedz("zabka", ["Żabka Odkryta 24"]) == ["Żabka Odkryta 24"]


def test_podpowiedz_nie_dopasowuje_niezwiazanych():
    assert podpowiedz("Żabka", ["ZUS Senatorska 6/8"]) == []


def test_podpowiedz_czestosc_rozstrzyga_remis():
    kandydaci = ["Żabka Odkryta 24", "Żabka Solidarności 117"]
    uzycia = {"Żabka Solidarności 117": 5, "Żabka Odkryta 24": 1}
    wynik = podpowiedz("Żabka", kandydaci, uzycia=uzycia)
    assert wynik[0] == "Żabka Solidarności 117"


def test_podpowiedz_ostatnio_uzywane_rozstrzyga_dalszy_remis():
    kandydaci = ["Żabka Odkryta 24", "Żabka Solidarności 117"]
    ostatnio = ["Żabka Odkryta 24"]
    wynik = podpowiedz("Żabka", kandydaci, ostatnio_uzywane=ostatnio)
    assert wynik[0] == "Żabka Odkryta 24"


def test_podpowiedz_respektuje_limit():
    kandydaci = [f"Żabka {i}" for i in range(20)]
    assert len(podpowiedz("Żabka", kandydaci, limit=5)) == 5


def test_najlepsza_podpowiedz_zwraca_pierwszy_wynik():
    assert najlepsza_podpowiedz("Żabka", ["Żabka Odkryta 24"]) == "Żabka Odkryta 24"


def test_najlepsza_podpowiedz_none_gdy_brak_dopasowania():
    assert najlepsza_podpowiedz("Żabka", ["ZUS"]) is None
